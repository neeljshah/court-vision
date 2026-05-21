"""
predictive_cache.py — Two-tier (in-memory L1 + JSON-file L2) content-addressed cache
for slate prop predictions.

Cache key = (game_id, market, state_hash) where state_hash is a stable SHA-1 of every
input that affects the prediction (lineup, injuries, lines, model version).  Repeated or
consecutive slate runs return results in sub-100 ms instead of recomputing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from typing import Any, Optional

# Two levels up from src/cache/ → project root
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.data.cache_utils import cache_is_fresh, load_json_cache, save_json_cache

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_SAFE_CHAR = re.compile(r"[^a-zA-Z0-9._-]")


def state_hash(state: dict) -> str:
    """Return a deterministic 16-char hex digest for *state*.

    Order of keys does not matter — json.dumps with sort_keys ensures
    a canonical byte string before hashing.
    """
    canonical = json.dumps(state, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(canonical).hexdigest()[:16]


def make_key(game_id: str, market: str, state: dict) -> str:
    """Build the compound cache key string."""
    return f"{game_id}|{market}|{state_hash(state)}"


# ---------------------------------------------------------------------------
# PredictiveCache
# ---------------------------------------------------------------------------


class PredictiveCache:
    """Two-tier content-addressed prediction cache.

    L1 is a plain in-process dict (microsecond reads).
    L2 is a directory of JSON files (millisecond reads, survives restarts).
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        ttl_seconds: float = 6 * 3600,
    ) -> None:
        """Initialise the cache.

        Args:
            cache_dir:   Directory where L2 JSON files are stored.  Defaults to
                         ``<project_root>/data/cache/predictive``.
            ttl_seconds: Maximum age (seconds) before a cached entry is considered
                         stale.  Default is 6 hours, matching a typical slate window.
        """
        self.cache_dir = cache_dir or os.path.join(
            PROJECT_DIR, "data", "cache", "predictive"
        )
        self.ttl_seconds = ttl_seconds
        self._mem: dict[str, Any] = {}
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, key: str) -> str:
        """Turn a compound key into a safe filesystem path under *cache_dir*."""
        safe = _SAFE_CHAR.sub("_", key)
        return os.path.join(self.cache_dir, f"{safe}.json")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, game_id: str, market: str, state: dict) -> Optional[Any]:
        """Return a cached prediction or *None* on miss.

        Checks L1 (in-memory) first, then L2 (JSON file).  Populates L1 from
        L2 on a cold-start hit so the next call is free.
        """
        key = make_key(game_id, market, state)

        # L1 hit
        if key in self._mem:
            self._hits += 1
            return self._mem[key]["prediction"]

        # L2 hit
        path = self._path(key)
        if cache_is_fresh(path, self.ttl_seconds):
            payload = load_json_cache(path, self.ttl_seconds)
            if payload is not None:
                self._mem[key] = payload
                self._hits += 1
                return payload["prediction"]

        self._misses += 1
        return None

    def put(self, game_id: str, market: str, state: dict, prediction: Any) -> None:
        """Store *prediction* under the key derived from *(game_id, market, state)*.

        Writes to both L1 and L2.  *prediction* must be JSON-serialisable
        (a dict of stats/floats in practice).
        """
        key = make_key(game_id, market, state)
        payload = {
            "key": key,
            "prediction": prediction,
            "cached_at": datetime.now().isoformat(),
        }
        self._mem[key] = payload
        save_json_cache(self._path(key), payload)

    def stats(self) -> dict:
        """Return hit/miss counters and current L1 size."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
            "size": len(self._mem),
        }

    def invalidate(self, game_id: Optional[str] = None) -> int:
        """Remove entries from L1 and delete their L2 files.

        Args:
            game_id: If provided, only entries whose key starts with
                     ``f"{game_id}|"`` are removed.  Pass *None* to purge all.

        Returns:
            Number of entries removed.
        """
        if game_id is None:
            keys_to_remove = list(self._mem.keys())
        else:
            prefix = f"{game_id}|"
            keys_to_remove = [k for k in self._mem if k.startswith(prefix)]

        for key in keys_to_remove:
            del self._mem[key]
            path = self._path(key)
            try:
                os.remove(path)
            except FileNotFoundError:
                pass  # L2 file may already be gone

        return len(keys_to_remove)

    def clear(self) -> None:
        """Reset L1 and counters.

        L2 files are left on disk intentionally — they will be considered
        stale once TTL expires and are inexpensive to retain.  Call
        ``invalidate()`` first if you also want L2 purged.
        """
        self._mem.clear()
        self._hits = 0
        self._misses = 0
