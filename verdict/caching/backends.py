"""Cache backend implementations for the Verdict harness caching layer.

Backends are synchronous (no async overhead for local file I/O).
The abstract CacheBackend interface is designed to allow a Redis backend
to be added later without changing the adapter integration code.

CacheBackend interface:
    get(key) -> ExecutionResult | None
    set(key, value)
    delete(key)
    exists(key) -> bool
    stats()    -> dict[str, int]  {'hits': N, 'misses': N, 'writes': N}
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from verdict.models.schemas import ExecutionResult


class CacheBackend(ABC):
    """Abstract cache backend.  Thread-safe by contract — subclasses must ensure it."""

    @abstractmethod
    def get(self, key: str) -> ExecutionResult | None:
        """Return the cached ExecutionResult for key, or None on miss."""

    @abstractmethod
    def set(self, key: str, value: ExecutionResult) -> None:
        """Store value under key, overwriting any existing entry."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the entry for key (no-op if not present)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if key is present in the cache."""

    @abstractmethod
    def stats(self) -> dict[str, int]:
        """Return cumulative hit/miss/write counts since creation."""


# ---------------------------------------------------------------------------
# Filesystem backend
# ---------------------------------------------------------------------------


class FileSystemCacheBackend(CacheBackend):
    """Stores cached responses as JSON files under cache_dir/{adapter_name}/{key}.json.

    Directory structure:
        .verdict_cache/
          {adapter_name}/
            {sha256_key}.json   <- serialized ExecutionResult

    File format: JSON produced by ExecutionResult.model_dump_json()
    """

    def __init__(self, cache_dir: Path, adapter_name: str) -> None:
        self._dir = Path(cache_dir) / _sanitize(adapter_name)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0
        self._writes = 0

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, key: str) -> ExecutionResult | None:
        p = self._path(key)
        if not p.exists():
            self._misses += 1
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self._hits += 1
            return ExecutionResult(**data)
        except Exception:
            self._misses += 1
            return None

    def set(self, key: str, value: ExecutionResult) -> None:
        self._path(key).write_text(value.model_dump_json(), encoding="utf-8")
        self._writes += 1

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "writes": self._writes}


# ---------------------------------------------------------------------------
# In-memory backend (for tests)
# ---------------------------------------------------------------------------


class InMemoryCacheBackend(CacheBackend):
    """In-memory cache backend for unit tests and ephemeral use.

    Not persistent across process restarts.  Thread-safe via dict operations
    (GIL-protected in CPython).
    """

    def __init__(self) -> None:
        self._store: dict[str, ExecutionResult] = {}
        self._hits = 0
        self._misses = 0
        self._writes = 0

    def get(self, key: str) -> ExecutionResult | None:
        result = self._store.get(key)
        if result is None:
            self._misses += 1
        else:
            self._hits += 1
        return result

    def set(self, key: str, value: ExecutionResult) -> None:
        self._store[key] = value
        self._writes += 1

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._store

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "writes": self._writes}

    def clear(self) -> None:
        """Remove all entries (test helper)."""
        self._store.clear()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _sanitize(name: str) -> str:
    """Convert adapter name to a safe directory component."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
