"""FastAPI semantic caching proxy."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from .cache import Partition, SemanticCache
from .config import Settings, settings
from .schemas import ChatCompletionRequest, Message, ProxyResponse
from .upstream import UpstreamClient, UpstreamError

log = logging.getLogger("semantic_cache")


def extract_query(messages: list[Message]) -> str:
    """The latest user turn is the cache key; system context goes into the partition."""
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content.strip()
    return ""


async def _eviction_loop(cache: SemanticCache, interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            result = await run_in_threadpool(cache.evict)
            if any(result.values()):
                log.info("eviction: %s", result)
        except Exception:
            log.exception("eviction failed")


def create_app(cfg: Settings = settings, cache: Optional[SemanticCache] = None,
               upstream: Optional[UpstreamClient] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.cache = cache or SemanticCache(cfg)
        app.state.upstream = upstream or UpstreamClient(cfg)
        await app.state.upstream.start()
        evictor = asyncio.create_task(_eviction_loop(app.state.cache, cfg.eviction_interval_seconds))
        try:
            yield
        finally:
            evictor.cancel()
            await app.state.upstream.close()
            if cache is None:
                app.state.cache.close()

    app = FastAPI(title="Semantic Caching Proxy", lifespan=lifespan)

    @app.post("/v1/chat/completions", response_model=ProxyResponse)
    async def handle_completion(
        req: ChatCompletionRequest,
        request: Request,
        response: Response,
        background: BackgroundTasks,
        x_tenant_id: Optional[str] = Header(default=None),
        x_cache_bypass: bool = Header(default=False),
    ):
        start = time.perf_counter()
        cache: SemanticCache = request.app.state.cache
        upstream: UpstreamClient = request.app.state.upstream

        user_query = extract_query(req.messages)
        if not user_query:
            raise HTTPException(status_code=400, detail="No user query provided in messages.")

        # Bypass = the "direct LLM" baseline: no embedding, no lookup, no store.
        if x_cache_bypass:
            result = await _call_upstream(upstream, req)
            response.headers["X-Cache"] = "BYPASS"
            return ProxyResponse(
                source="UPSTREAM_LLM",
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                response=result.text,
                usage=result.usage,
            )

        partition = Partition.from_request(req.messages, req.model, x_tenant_id or req.user)
        vector = await run_in_threadpool(cache.embed, user_query)
        hit, best_score = await run_in_threadpool(cache.lookup, vector, user_query, partition)

        if hit:
            background.add_task(run_in_threadpool, cache.touch, hit.point_id)
            response.headers["X-Cache"] = "HIT"
            return ProxyResponse(
                source="CACHE_HIT",
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                similarity_score=round(hit.score, 4),
                matched_query=hit.query,
                response=hit.response,
                usage=hit.usage,
                tokens_saved=hit.usage.total_tokens,
            )

        result = await _call_upstream(upstream, req)
        await run_in_threadpool(cache.store, vector, user_query, result.text, partition, result.usage)
        response.headers["X-Cache"] = "MISS"
        return ProxyResponse(
            source="UPSTREAM_LLM",
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            similarity_score=round(best_score, 4) if best_score is not None else None,
            response=result.text,
            usage=result.usage,
        )

    @app.get("/health")
    async def health():
        return {"status": "ok", "upstream": cfg.upstream_provider}

    @app.get("/cache/stats")
    async def cache_stats(request: Request):
        cache: SemanticCache = request.app.state.cache
        s = cache.stats
        lookups = s.hits + s.misses
        return {
            "entries": await run_in_threadpool(cache.count),
            "hits": s.hits,
            "misses": s.misses,
            "hit_rate": round(s.hits / lookups, 4) if lookups else 0.0,
            "guard_rejections": s.guard_rejections,
            "tokens_saved": s.tokens_saved,
            "evicted_expired": s.evicted_expired,
            "evicted_capacity": s.evicted_capacity,
            "config": {
                "similarity_threshold": cfg.similarity_threshold,
                "entity_guard": cfg.entity_guard,
                "ttl_seconds": cfg.ttl_seconds,
                "max_entries": cfg.max_entries,
            },
        }

    @app.post("/cache/evict")
    async def cache_evict(request: Request):
        return await run_in_threadpool(request.app.state.cache.evict)

    @app.delete("/cache")
    async def cache_clear(request: Request):
        await run_in_threadpool(request.app.state.cache.clear)
        return {"cleared": True}

    return app


async def _call_upstream(upstream: UpstreamClient, req: ChatCompletionRequest):
    try:
        return await upstream.complete(req)
    except UpstreamError as e:
        raise HTTPException(status_code=502, detail=f"Upstream provider error: {e}")


app = create_app()
