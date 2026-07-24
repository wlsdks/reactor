from __future__ import annotations

from reactor.cache.response import InMemoryResponseCache


def test_in_memory_response_cache_tracks_stats_and_hit_rate() -> None:
    cache = InMemoryResponseCache(max_size=2)

    cache.put("key_1", "response 1")
    assert cache.get("key_1") == "response 1"
    assert cache.get("missing") is None
    cache.record_semantic_hit()

    assert cache.stats() == {
        "enabled": True,
        "semantic_enabled": False,
        "total_exact_hits": 1,
        "total_semantic_hits": 1,
        "total_misses": 1,
        "ttl_minutes": 0,
        "max_size": 2,
        "similarity_threshold": 0.0,
        "max_candidates": 0,
        "cacheable_temperature": 0.0,
    }


def test_in_memory_response_cache_invalidates_single_key_pattern_and_all_entries() -> None:
    cache = InMemoryResponseCache(max_size=10)
    cache.put("tenant_1:chat:one", "one")
    cache.put("tenant_1:chat:two", "two")
    cache.put("tenant_2:chat:one", "other")

    assert cache.invalidate("tenant_1:chat:one") is True
    assert cache.invalidate("tenant_1:chat:one") is False
    assert cache.invalidate_by_pattern("tenant_1:chat:*") == 1
    assert cache.get("tenant_2:chat:one") == "other"
    assert cache.invalidate_all() is True
    assert cache.get("tenant_2:chat:one") is None
