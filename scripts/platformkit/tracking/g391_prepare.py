"""Pure preparation guards for the G391 blind audit; no scoring route is imported."""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path


OBJECT_CATEGORIES = frozenset((
    "BALL", "PERSON_OR_APPAREL", "CROWD", "SIGNAGE_OR_GRAPHIC", "EQUIPMENT",
    "COURT_OR_LOGO", "OTHER", "UNKNOWN",
))
REFERENCE_LABELS = frozenset(("VISIBLE", "ABSENT", "UNKNOWN"))
HIDDEN_PACKET_FIELDS = frozenset((
    "label", "reference_label", "confidence", "score", "split", "tp", "fp",
    "outcome", "scorer_outcome",
))
SEAL_PREFIX = b"SEAL sha256 "


def verify_preregistration(path: Path) -> str:
    """Validate the LF-normalized seal that must precede every measurement."""
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
    body, marker, recorded = raw.rpartition(b"\n" + SEAL_PREFIX)
    if not marker or body.endswith(b"\n"):
        raise ValueError("invalid-preregistration-seal-layout")
    expected = hashlib.sha256(body + b"\n").hexdigest()
    actual = recorded.decode("ascii").strip()
    if len(actual) != 64 or actual != expected:
        raise ValueError("preregistration-seal-mismatch")
    return actual


def _sort_key(row: Mapping[str, str]) -> tuple[str, str, int, str]:
    try:
        frame_index = int(str(row["frame_index"]))
    except (KeyError, ValueError):
        raise ValueError("invalid-frame-index") from None
    return (str(row.get("game", "")), str(row.get("section", "")), frame_index,
            str(row.get("frame_key", "")))


def freeze_packets(calls: Iterable[Mapping[str, str]], bins: int = 30) -> list[dict[str, str]]:
    """Create a deterministic 30-bin round-robin packet order with opaque identifiers."""
    rows = [dict(row) for row in calls]
    keys = [row.get("frame_key", "") for row in rows]
    if bins != 30 or len(rows) < bins or "" in keys or len(keys) != len(set(keys)):
        raise ValueError("invalid-call-packet-universe")
    if any(HIDDEN_PACKET_FIELDS.intersection(row) for row in rows):
        raise ValueError("packet-source-exposes-hidden-field")
    ordered = sorted(rows, key=_sort_key)
    groups = [ordered[index * len(ordered) // bins:(index + 1) * len(ordered) // bins]
              for index in range(bins)]
    round_robin = []
    for depth in range(max(len(group) for group in groups)):
        round_robin.extend(group[depth] for group in groups if depth < len(group))
    packets = []
    for ordinal, row in enumerate(round_robin, start=1):
        packet_id = hashlib.sha256(row["frame_key"].encode("ascii")).hexdigest()[:16]
        packets.append({"packet_id": "G391-%03d-%s" % (ordinal, packet_id),
                        "game": row.get("game", ""), "section": row.get("section", ""),
                        "frame_index": row.get("frame_index", ""),
                        "native_path": row.get("native_path", ""),
                        "crop_path": row.get("crop_path", "")})
    return packets


def assert_packets_blind(packets: Iterable[Mapping[str, str]]) -> None:
    """Refuse a packet whose fields disclose labels, split, confidence, or outcome."""
    for packet in packets:
        if HIDDEN_PACKET_FIELDS.intersection(packet):
            raise ValueError("packet-label-visibility-refused")
        if not str(packet.get("packet_id", "")).startswith("G391-"):
            raise ValueError("opaque-packet-id-required")


def review_effect(label: str, call_is_false: bool) -> dict[str, int]:
    """Account for a false call without discarding an UNKNOWN or visible-frame miss."""
    if label not in REFERENCE_LABELS:
        raise ValueError("unknown-reference-label")
    return {"false_call": int(call_is_false),
            "false_negative": int(call_is_false and label == "VISIBLE"),
            "unknown_retained": int(call_is_false and label == "UNKNOWN")}


def nearest_rank_p95(speeds: Sequence[float]) -> float:
    """Return the predeclared nearest-rank p95 only from at least 30 DEV pairs."""
    if len(speeds) < 30 or any(speed < 0 for speed in speeds):
        raise ValueError("insufficient-disjoint-dev-speeds")
    return sorted(speeds)[math.ceil(0.95 * len(speeds)) - 1]


def shadow_decision(previous: Sequence[Mapping[str, object]], p95_speed: float | None) -> str:
    """Apply only the fixed causal rule; missing history preserves the raw call."""
    if p95_speed is None:
        return "RETAINED_INSUFFICIENT_DEV"
    if p95_speed < 0:
        raise ValueError("negative-speed-limit")
    if len(previous) != 2:
        return "RETAINED_MISSING_HISTORY"
    for row in previous:
        seconds = float(row.get("seconds_before", -1.0))
        if seconds < 0:
            raise ValueError("future-or-current-context-refused")
        if seconds > 0.2 or row.get("availability") == "MISSING":
            return "RETAINED_MISSING_HISTORY"
    if any(row.get("observation") == "NO_DETECTION" for row in previous):
        return "SUPPRESSED_CONFIRMED_NO_DETECTION"
    if any(row.get("observation") != "OBSERVED" for row in previous):
        return "RETAINED_MISSING_HISTORY"
    if any(float(row.get("speed", p95_speed + 1.0)) > p95_speed for row in previous):
        return "SUPPRESSED_SPEED_LIMIT"
    return "RETAINED_OBSERVED"


def assert_suppression_subset(raw_calls: Iterable[str], suppressed_calls: Iterable[str]) -> None:
    """Require suppression to remove calls only; it may never introduce a call."""
    raw, output = set(raw_calls), set(suppressed_calls)
    if not output.issubset(raw):
        raise ValueError("suppression-created-call")


def assert_all_states_survive(raw_states: Iterable[str], output_states: Iterable[str]) -> None:
    """Keep the full 549-state denominator even when a call is suppressed."""
    if set(raw_states) != set(output_states):
        raise ValueError("state-denominator-drop")
