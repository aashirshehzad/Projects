"""Semantic cache backed by embedded Qdrant + FastEmbed.

All methods here are synchronous (ONNX inference and the embedded Qdrant client
both block). The API layer calls them through a threadpool, and a lock
serialises access because Qdrant's local mode is not thread-safe.
"""

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .config import Settings
from .guard import entities_match
from .schemas import Message, Usage

CANDIDATES = 5  # look past the top match in case it fails the entity guard


@dataclass(frozen=True)
class Partition:
    """Hits are only served within the same tenant, model and system context."""

    tenant: str
    model: str
    context_hash: str

    @classmethod
    def from_request(cls, messages: List[Message], model: str, tenant: Optional[str]) -> "Partition":
        system = "\n".join(m.content for m in messages if m.role == "system")
        digest = hashlib.sha256(system.encode()).hexdigest()[:16]
        return cls(tenant=tenant or "default", model=model, context_hash=digest)

    @property
    def key(self) -> str:
        # One keyword condition instead of three: ~2.6x faster in embedded mode.
        return hashlib.sha256(f"{self.tenant}\x00{self.model}\x00{self.context_hash}".encode()).hexdigest()[:32]


@dataclass
class CacheHit:
    point_id: str
    score: float
    query: str
    response: str
    usage: Usage


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    guard_rejections: int = 0
    tokens_saved: int = 0
    evicted_expired: int = 0
    evicted_capacity: int = 0
    started_at: float = field(default_factory=time.time)


class SemanticCache:
    def __init__(self, cfg: Settings, embedder=None, client: Optional[QdrantClient] = None):
        self.cfg = cfg
        if embedder is None:
            from fastembed import TextEmbedding

            embedder = TextEmbedding(model_name=cfg.embedding_model)
        self.embedder = embedder
        self.server_mode = bool(cfg.qdrant_url)
        if client is None:
            if self.server_mode:
                client = QdrantClient(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None)
            elif cfg.qdrant_path == ":memory:":
                client = QdrantClient(location=":memory:")
            else:
                client = QdrantClient(path=cfg.qdrant_path)
        self.client = client
        self.stats = CacheStats()
        self._lock = threading.Lock()
        self._ensure_collection()

    # --- setup -----------------------------------------------------------------
    def _ensure_collection(self) -> None:
        if not self.client.collection_exists(self.cfg.collection_name):
            self.client.create_collection(
                collection_name=self.cfg.collection_name,
                vectors_config=qm.VectorParams(size=self.cfg.embedding_dim, distance=qm.Distance.COSINE),
            )
            if self.server_mode:  # indexes are a no-op (with a warning) in embedded mode
                for field_name, schema in (("partition", qm.PayloadSchemaType.KEYWORD),
                                           ("created_at", qm.PayloadSchemaType.FLOAT),
                                           ("last_accessed", qm.PayloadSchemaType.FLOAT)):
                    self.client.create_payload_index(self.cfg.collection_name, field_name, field_schema=schema)

    def close(self) -> None:
        self.client.close()

    # --- hot path --------------------------------------------------------------
    def embed(self, text: str) -> List[float]:
        return next(iter(self.embedder.embed([text]))).tolist()

    def lookup(self, vector: List[float], query: str, partition: Partition) -> tuple[Optional[CacheHit], Optional[float]]:
        """Return (hit, best_score). best_score is reported even on a miss."""
        cutoff = time.time() - self.cfg.ttl_seconds
        must = [qm.FieldCondition(key="partition", match=qm.MatchValue(value=partition.key))]
        if self.server_mode:
            # Indexed on a server, so filter expired entries out of the search itself.
            # Embedded mode checks candidates below instead; the evictor purges the rest.
            must.append(qm.FieldCondition(key="created_at", range=qm.Range(gte=cutoff)))
        flt = qm.Filter(must=must)
        with self._lock:
            points = self.client.query_points(
                collection_name=self.cfg.collection_name,
                query=vector,
                query_filter=flt,
                # Headroom for expired entries awaiting eviction (embedded mode).
                limit=CANDIDATES if self.server_mode else CANDIDATES * 4,
                with_payload=True,
            ).points

        points = [p for p in points if p.payload["created_at"] >= cutoff][:CANDIDATES]
        best = points[0].score if points else None
        for p in points:
            if p.score < self.cfg.similarity_threshold:
                break  # results are sorted by score
            if self.cfg.entity_guard and not entities_match(query, p.payload["query"]):
                self.stats.guard_rejections += 1
                continue
            usage = Usage(**p.payload.get("usage", {}))
            self.stats.hits += 1
            self.stats.tokens_saved += usage.total_tokens
            return (
                CacheHit(
                    point_id=str(p.id),
                    score=p.score,
                    query=p.payload["query"],
                    response=p.payload["response"],
                    usage=usage,
                ),
                best,
            )
        self.stats.misses += 1
        return None, best

    def touch(self, point_id: str) -> None:
        """Record access for LRU eviction. Called after the response is sent."""
        with self._lock:
            points = self.client.retrieve(self.cfg.collection_name, ids=[point_id], with_payload=["hit_count"])
            if not points:
                return
            self.client.set_payload(
                collection_name=self.cfg.collection_name,
                payload={"last_accessed": time.time(), "hit_count": points[0].payload.get("hit_count", 0) + 1},
                points=[point_id],
            )

    def store(self, vector: List[float], query: str, response: str, partition: Partition, usage: Usage) -> str:
        now = time.time()
        point_id = str(uuid.uuid4())
        with self._lock:
            self.client.upsert(
                collection_name=self.cfg.collection_name,
                points=[
                    qm.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "query": query,
                            "response": response,
                            "partition": partition.key,
                            "tenant": partition.tenant,
                            "model": partition.model,
                            "context_hash": partition.context_hash,
                            "usage": usage.model_dump(),
                            "created_at": now,
                            "last_accessed": now,
                            "hit_count": 0,
                        },
                    )
                ],
            )
        return point_id

    # --- maintenance -----------------------------------------------------------
    def count(self) -> int:
        with self._lock:
            return self.client.count(self.cfg.collection_name, exact=True).count

    def evict(self) -> dict:
        """Delete expired entries, then trim to max_entries by least-recent access."""
        name = self.cfg.collection_name
        cutoff = time.time() - self.cfg.ttl_seconds
        expired_filter = qm.Filter(must=[qm.FieldCondition(key="created_at", range=qm.Range(lt=cutoff))])

        with self._lock:
            expired = self.client.count(name, count_filter=expired_filter, exact=True).count
            if expired:
                self.client.delete(name, points_selector=qm.FilterSelector(filter=expired_filter))

            over = self.client.count(name, exact=True).count - self.cfg.max_entries
            trimmed = 0
            if over > 0:
                entries, offset = [], None
                while True:
                    batch, offset = self.client.scroll(
                        name, limit=1000, offset=offset, with_payload=["last_accessed"], with_vectors=False
                    )
                    entries.extend((p.payload.get("last_accessed", 0), p.id) for p in batch)
                    if offset is None:
                        break
                entries.sort()
                victims = [pid for _, pid in entries[:over]]
                self.client.delete(name, points_selector=qm.PointIdsList(points=victims))
                trimmed = len(victims)

        self.stats.evicted_expired += expired
        self.stats.evicted_capacity += trimmed
        return {"expired": expired, "over_capacity": trimmed}

    def clear(self) -> None:
        # Not delete_collection + recreate: embedded Qdrant on Windows can't unlink the
        # collection's sqlite file while this same process still has it open, and
        # shutil.rmtree(..., ignore_errors=True) swallows that failure silently, leaving
        # the "cleared" collection populated with all its old points. Deleting every
        # point via a match-all filter avoids touching the file at all.
        with self._lock:
            self.client.delete(
                collection_name=self.cfg.collection_name,
                points_selector=qm.FilterSelector(filter=qm.Filter()),
            )
        self.stats = CacheStats()
