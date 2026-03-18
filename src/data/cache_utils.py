"""
cache_utils.py — Shared JSON cache helpers for NBA data modules.

All data modules that cache NBA API responses to disk use the same
load/save/freshness-check pattern.  This module centralises that
pattern so each caller only needs to supply the file path and TTL.

Public API
----------
    load_json_cache(path, ttl_seconds)  -> Optional[dict | list]
    save_json_cache(path, data)         -> None
    cache_is_fresh(path, ttl_seconds)   -> bool
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional, Union


def load_json_cache(
    path: str,
    ttl_seconds: Optional[float] = None,
) -> Optional[Union[dict, list]]:
    """Load a JSON cache file if it exists and is within the TTL window.

    Args:
        path:        Absolute path to the cache file.
        ttl_seconds: Maximum allowed age in seconds.  ``None`` means the
                     cache never expires (useful for historical data).

    Returns:
        Parsed JSON (dict or list), or ``None`` if the cache is missing
        or stale.
    """
    if not os.path.exists(path):
        return None
    if ttl_seconds is not None:
        age = time.time() - os.path.getmtime(path)
        if age > ttl_seconds:
            return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json_cache(path: str, data: Union[dict, list]) -> None:
    """Persist data to a JSON cache file, creating parent dirs as needed.

    Args:
        path: Absolute path to write.
        data: JSON-serialisable dict or list.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def cache_is_fresh(path: str, ttl_seconds: float) -> bool:
    """Return True if *path* exists and is younger than *ttl_seconds*.

    Args:
        path:        Absolute path to the cache file.
        ttl_seconds: Maximum allowed age in seconds.
    """
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < ttl_seconds
