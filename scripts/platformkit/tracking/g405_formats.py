"""Pure G405 format-admission parsing, draw, and additive sidecar helpers."""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping
from typing import Any

DRAW_SIZE = 30
YES, NO, UNKNOWN = "YES", "NO", "UNKNOWN"


def even_draw(records: Iterable[Mapping[str, Any]], count: int = DRAW_SIZE) -> list[dict[str, Any]]:
    """Return the sealed evenly spaced unique-source draw."""
    ordered = sorted((dict(row) for row in records), key=lambda row: (
        str(row.get("competition", "")), str(row.get("query", "")), str(row.get("source_id", ""))))
    source_ids = [str(row.get("source_id", "")) for row in ordered]
    if len(ordered) < count:
        raise ValueError("insufficient-unique-sources:%d" % len(ordered))
    if not all(source_ids) or len(set(source_ids)) != len(source_ids):
        raise ValueError("duplicate-or-empty-source-id")
    return [dict(ordered[math.floor(j * (len(ordered) - 1) / (count - 1) + 0.5)],
                 draw_j=j) for j in range(count)]


def _number(value: Any) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(str(value).strip())
    except ValueError:
        return None


def is_h264(codec: Any) -> bool:
    """H.264/AVC is listed as h264 or as its avc1/avc3 fourcc profile string."""
    return str(codec or "").strip().lower().startswith(("h264", "avc1", "avc3"))


def is_qualifying_format(item: Mapping[str, Any]) -> bool:
    """Require explicit HLS, h264, height, and measured 30 fps evidence."""
    protocol, codec = str(item.get("protocol", "")).lower(), item.get("vcodec", item.get("codec", ""))
    height, fps = _number(item.get("height")), _number(item.get("fps"))
    return "m3u8" in protocol and is_h264(codec) and height is not None and fps is not None and 720 <= height <= 1080 and 29 <= fps <= 31


def format_bucket(item: Mapping[str, Any]) -> str | None:
    """Name a requested measured rendition bucket without inferring from ids."""
    height, fps = _number(item.get("height")), _number(item.get("fps"))
    if height not in (720.0, 1080.0) or fps is None:
        return None
    if 29 <= fps <= 31:
        return "%dp30" % height
    if 59 <= fps <= 61:
        return "%dp60" % height
    return None


def availability(listing: Iterable[Mapping[str, Any]] | None, metadata: Iterable[Mapping[str, Any]] | None,
                 listing_complete: bool, metadata_complete: bool) -> dict[str, Any]:
    """Bind availability to both inventories; incomplete evidence stays UNKNOWN."""
    left, right = list(listing or []), list(metadata or [])
    left_ids = {str(row.get("format_id", "")) for row in left if is_qualifying_format(row)}
    right_ids = {str(row.get("format_id", "")) for row in right if is_qualifying_format(row)}
    buckets = {name: any(format_bucket(row) == name for row in left + right)
               for name in ("720p30", "1080p30", "720p60", "1080p60")}
    if left_ids and right_ids:
        state = YES
    elif bool(left_ids) != bool(right_ids):
        state = UNKNOWN
    elif listing_complete and metadata_complete:
        state = NO
    else:
        state = UNKNOWN
    return {"compatible_30fps": state, "qualifying_format_ids": sorted(left_ids | right_ids),
            "listing_qualifying_ids": sorted(left_ids), "metadata_qualifying_ids": sorted(right_ids),
            "listing_complete": listing_complete, "metadata_complete": metadata_complete, **buckets}


def raw_inventory_digest(listing_bytes: bytes, metadata_bytes: bytes) -> str:
    """Return the deterministic digest binding the two retained raw inventories."""
    digest = hashlib.sha256()
    digest.update(listing_bytes)
    digest.update(b"\n--G405-METADATA--\n")
    digest.update(metadata_bytes)
    return digest.hexdigest()


def sidecar_row(inherited: Mapping[str, Any], result: Mapping[str, Any], *, discovered_at: str,
                format_probe_at: str, query: str, digest: str, probe_status: str) -> dict[str, Any]:
    """Extend one queue record without removing or renaming inherited fields."""
    row = dict(inherited)
    if not row.get("source_id"):
        raise ValueError("source-id-required")
    row.update({"discovered_at": discovered_at, "format_probe_at": format_probe_at, "query": query,
                "compatible_30fps": result["compatible_30fps"],
                "qualifying_format_ids": result["qualifying_format_ids"],
                "preferred_format_if_available": result["qualifying_format_ids"][0] if result["compatible_30fps"] == YES else None,
                "fallback_reason": None if result["compatible_30fps"] == YES else result["compatible_30fps"],
                "raw_inventory_digest": digest, "probe_status": probe_status})
    return row
