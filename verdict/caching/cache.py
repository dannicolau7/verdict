"""Cache key and mode definitions for the Verdict harness caching layer.

CacheMode controls how the adapter interacts with the cache:
  OFF:    No caching. Behaves exactly as v0.1.0 (default).
  RECORD: Read from cache if available; execute and save on miss.
  REPLAY: Read from cache only; raise CacheMissError on miss (for deterministic CI).
  UPDATE: Always execute and overwrite the cache entry.

Cache key:
  SHA-256 of (adapter_name, adapter_version, prompt_text, prompt_id).
  Including prompt_id allows same prompt text under different IDs to be cached
  independently — useful for variant / A-B testing scenarios.

Security note:
  Cache files may contain LLM responses, which can include sensitive information
  submitted in test prompts.  Add .verdict_cache/ to .gitignore (already done).
  Do not commit cache files to version control.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum


class CacheMode(StrEnum):
    """Controls adapter interaction with the cache backend."""

    OFF = "off"
    RECORD = "record"
    REPLAY = "replay"
    UPDATE = "update"


class CacheMissError(Exception):
    """Raised in REPLAY mode when a prompt is not in the cache."""


def compute_cache_key(
    adapter_name: str,
    adapter_version: str,
    prompt_text: str,
    prompt_id: str,
) -> str:
    """Compute a deterministic cache key for a single prompt execution.

    Args:
        adapter_name:    Adapter.name property value.
        adapter_version: Adapter.version property value.
        prompt_text:     The raw prompt string sent to the target.
        prompt_id:       The TestPrompt UUID (allows same text under different IDs).

    Returns:
        64-char lowercase hex SHA-256 digest.
    """
    payload = json.dumps(
        [adapter_name, adapter_version, prompt_text, prompt_id],
        ensure_ascii=True,
        sort_keys=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
