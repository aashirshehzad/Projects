import time
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.cache import Partition, SemanticCache
from app.config import Settings
from app.guard import entities_match, extract_entities
from app.main import create_app
from app.schemas import Usage
from app.upstream import UpstreamClient


class ConstantEmbedder:
    """Every text maps to the same vector (cosine 1.0), isolating filters and the guard."""

    def embed(self, texts):
        for _ in texts:
            yield np.ones(384, dtype=np.float32)


BASE = Settings(
    qdrant_path=":memory:",
    upstream_provider="mock",
    mock_latency_ms_min=0,
    mock_latency_ms_max=0,
    eviction_interval_seconds=3600,
)


def make_client(**overrides):
    cfg = replace(BASE, **overrides)
    cache = SemanticCache(cfg, embedder=ConstantEmbedder())
    app = create_app(cfg, cache=cache, upstream=UpstreamClient(cfg))
    return TestClient(app), cache


def ask(client, text, headers=None, **body):
    payload = {"messages": [{"role": "user", "content": text}], **body}
    return client.post("/v1/chat/completions", json=payload, headers=headers or {})


def test_miss_then_hit():
    client, _ = make_client()
    with client:
        first = ask(client, "How do I reverse a linked list in Python?")
        second = ask(client, "Reverse a linked list, Python please")
    assert first.json()["source"] == "UPSTREAM_LLM" and first.headers["x-cache"] == "MISS"
    body = second.json()
    assert body["source"] == "CACHE_HIT" and second.headers["x-cache"] == "HIT"
    assert body["response"] == first.json()["response"]
    assert body["tokens_saved"] == first.json()["usage"]["total_tokens"] > 0


def test_entity_guard_blocks_wrong_language():
    client, cache = make_client()
    with client:
        ask(client, "How do I reverse a linked list in Python?")
        res = ask(client, "How do I reverse a linked list in Java?")
    assert res.json()["source"] == "UPSTREAM_LLM"
    assert cache.stats.guard_rejections == 1


def test_guard_can_be_disabled():
    client, _ = make_client(entity_guard=False)
    with client:
        ask(client, "How do I reverse a linked list in Python?")
        res = ask(client, "How do I reverse a linked list in Java?")
    assert res.json()["source"] == "CACHE_HIT"


def test_guard_falls_through_to_next_candidate():
    client, _ = make_client()
    with client:
        ask(client, "Sort a list in Java")
        python = ask(client, "Sort a list in Python").json()
        res = ask(client, "sort a list in python").json()
    assert res["source"] == "CACHE_HIT" and res["response"] == python["response"]


def test_tenant_isolation():
    client, _ = make_client()
    with client:
        ask(client, "What is a monad?", headers={"X-Tenant-ID": "alice"})
        bob = ask(client, "What is a monad?", headers={"X-Tenant-ID": "bob"})
        alice = ask(client, "What is a monad?", user="alice")  # OpenAI `user` field works too
    assert bob.json()["source"] == "UPSTREAM_LLM"
    assert alice.json()["source"] == "CACHE_HIT"


def test_model_and_system_prompt_partition():
    client, _ = make_client()
    with client:
        ask(client, "Tell me a joke")
        other_model = ask(client, "Tell me a joke", model="llama-3.3-70b-versatile")
        with_system = client.post("/v1/chat/completions", json={"messages": [
            {"role": "system", "content": "Answer only in French."},
            {"role": "user", "content": "Tell me a joke"},
        ]})
    assert other_model.json()["source"] == "UPSTREAM_LLM"
    assert with_system.json()["source"] == "UPSTREAM_LLM"


def test_ttl_expired_entries_are_not_served_and_get_evicted():
    client, cache = make_client(ttl_seconds=1)
    with client:
        ask(client, "What is entropy?")
        time.sleep(1.1)
        assert ask(client, "What is entropy?").json()["source"] == "UPSTREAM_LLM"
        time.sleep(1.1)
        result = client.post("/cache/evict").json()
    assert result["expired"] == 2 and cache.count() == 0


def test_capacity_eviction_drops_least_recently_used():
    # Driven at the cache level: over HTTP, touch() is a post-response background
    # task, so an immediate /cache/evict could race it.
    cfg = replace(BASE, max_entries=2)
    cache = SemanticCache(cfg, embedder=ConstantEmbedder())
    part = Partition.from_request([], "m", None)
    vec = cache.embed("x")
    ids = {}
    for q in ("Explain Docker", "Explain Kubernetes", "Explain Terraform", None):
        time.sleep(0.03)  # time.time() ticks at ~15.6ms on Windows/Python 3.12; avoid timestamp ties
        if q:
            ids[q] = cache.store(vec, q, f"answer {q}", part, Usage())
    cache.touch(ids["Explain Docker"])

    assert cache.evict() == {"expired": 0, "over_capacity": 1}
    assert cache.lookup(vec, "explain docker", part)[0].response == "answer Explain Docker"
    assert cache.lookup(vec, "explain kubernetes", part)[0] is None


def test_bypass_skips_cache_entirely():
    client, cache = make_client()
    with client:
        res = ask(client, "Hello there", headers={"X-Cache-Bypass": "true"})
        stats = client.get("/cache/stats").json()
    assert res.headers["x-cache"] == "BYPASS"
    assert stats["entries"] == 0 and stats["hits"] + stats["misses"] == 0


def test_rejects_request_without_user_message():
    client, _ = make_client()
    with client:
        res = client.post("/v1/chat/completions", json={"messages": [{"role": "system", "content": "hi"}]})
    assert res.status_code == 400


@pytest.mark.parametrize(
    "a,b,same",
    [
        ("How do I reverse a singly linked list in Python?", "Write Python code to reverse a single linked list", True),
        ("How do I reverse a singly linked list in Python?", "How do I reverse a singly linked list in Java?", False),
        ("Explain the difference between TCP and UDP", "What are the differences between UDP and TCP?", True),
        ("What is the capital of France?", "What is the capital of Germany?", False),
        ("Why does Earth have seasons?", "What causes the seasons on Earth?", True),
        ("What is 15% of 80?", "What is 20% of 80?", False),
        ("how to use pandas groupby", "Pandas groupby usage", True),
        ("REST vs GraphQL: how do they differ?", "What is the difference between REST and GraphQL?", True),
        ("World War I causes", "What caused World War II?", False),
    ],
)
def test_entity_guard_cases(a, b, same):
    assert entities_match(a, b) is same, (extract_entities(a), extract_entities(b))
