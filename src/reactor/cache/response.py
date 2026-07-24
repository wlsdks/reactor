from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResponseCacheConfig:
    ttl_minutes: int = 0
    max_size: int = 1024
    semantic_enabled: bool = False
    similarity_threshold: float = 0.0
    max_candidates: int = 0
    cacheable_temperature: float = 0.0


class InMemoryResponseCache:
    def __init__(self, config: ResponseCacheConfig | None = None, *, max_size: int | None = None):
        resolved = config or ResponseCacheConfig()
        if max_size is not None:
            resolved = ResponseCacheConfig(
                ttl_minutes=resolved.ttl_minutes,
                max_size=max_size,
                semantic_enabled=resolved.semantic_enabled,
                similarity_threshold=resolved.similarity_threshold,
                max_candidates=resolved.max_candidates,
                cacheable_temperature=resolved.cacheable_temperature,
            )
        if resolved.max_size <= 0:
            raise ValueError("max_size must be positive")
        self._config = resolved
        self._entries: OrderedDict[str, Any] = OrderedDict()
        self._exact_hits = 0
        self._semantic_hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        normalized_key = require_key(key)
        if normalized_key not in self._entries:
            self._misses += 1
            return None
        self._entries.move_to_end(normalized_key)
        self._exact_hits += 1
        return self._entries[normalized_key]

    def put(self, key: str, value: Any) -> None:
        normalized_key = require_key(key)
        self._entries[normalized_key] = value
        self._entries.move_to_end(normalized_key)
        while len(self._entries) > self._config.max_size:
            self._entries.popitem(last=False)

    def record_semantic_hit(self) -> None:
        self._semantic_hits += 1

    def invalidate_all(self) -> bool:
        had_entries = bool(self._entries)
        self._entries.clear()
        return had_entries

    def invalidate(self, key: str) -> bool:
        normalized_key = require_key(key)
        return self._entries.pop(normalized_key, None) is not None

    def invalidate_by_pattern(self, pattern: str) -> int:
        normalized_pattern = require_key(pattern)
        if "*" not in normalized_pattern:
            return int(self.invalidate(normalized_pattern))
        prefix, suffix = normalized_pattern.split("*", 1)
        matched = [
            key
            for key in self._entries
            if key.startswith(prefix) and (not suffix or key.endswith(suffix))
        ]
        for key in matched:
            self._entries.pop(key, None)
        return len(matched)

    def stats(self) -> dict[str, object]:
        return {
            "enabled": True,
            "semantic_enabled": self._config.semantic_enabled,
            "total_exact_hits": self._exact_hits,
            "total_semantic_hits": self._semantic_hits,
            "total_misses": self._misses,
            "ttl_minutes": self._config.ttl_minutes,
            "max_size": self._config.max_size,
            "similarity_threshold": self._config.similarity_threshold,
            "max_candidates": self._config.max_candidates,
            "cacheable_temperature": self._config.cacheable_temperature,
        }


def require_key(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("cache key is required")
    return normalized
