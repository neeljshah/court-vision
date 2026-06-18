"""Freshness pipeline -- typed extraction schema + vintage leak guard (blueprint X1).

Self-contained (stdlib only). The freshness lever (injury/lineup deltas -> vacated-load) lives or dies
on VINTAGE ALIGNMENT: a delta may only inform a prediction if it was KNOWN before tip-off. This module
provides the typed record, schema validation, the vintage guard, and -- per the QA finding -- the
quarantine that marks any metric computed on the outcome-conditioned FALLBACK PROXY as an OPTIMISTIC
UPPER BOUND, never a leak-free result.

The LLM produces these structured rows; it never emits a probability. No dollar edge is computed.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

STATUSES = ("OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "AVAILABLE", "GTD")
SEVERITIES = ("none", "minor", "moderate", "major")


@dataclass(frozen=True)
class InjuryDelta:
    player_id: str
    team_id: str
    status: str            # one of STATUSES
    severity: str          # one of SEVERITIES
    game_date: str         # ISO date of the game
    source: str            # provenance (url / feed name)
    extracted_at: str      # ISO datetime the row became known -- the vintage key
    confidence: float      # 0..1 extraction confidence
    is_fallback_proxy: bool = False  # True => reconstructed post-hoc (outcome-conditioned)


def validate_delta(d: dict) -> None:
    """Raise AssertionError on a malformed row (run downstream of any constrained decoding --
    constrained decoding still fails ~12% semantically on hard nested cases)."""
    req = ("player_id", "team_id", "status", "severity", "game_date",
           "source", "extracted_at", "confidence")
    for k in req:
        assert k in d and d[k] not in (None, ""), f"missing/empty field {k}"
    assert d["status"] in STATUSES, f"bad status {d['status']}"
    assert d["severity"] in SEVERITIES, f"bad severity {d['severity']}"
    assert 0.0 <= float(d["confidence"]) <= 1.0, "confidence out of [0,1]"
    datetime.fromisoformat(d["extracted_at"])  # raises ValueError if not ISO


def assert_vintage(delta: dict, tip_off_iso: str) -> None:
    """LEAK GUARD: the row may inform the prediction only if known strictly before tip."""
    extracted = datetime.fromisoformat(delta["extracted_at"])
    tip = datetime.fromisoformat(tip_off_iso)
    assert extracted < tip, (
        f"LEAK: extracted_at {delta['extracted_at']} >= tip {tip_off_iso} "
        f"for {delta.get('player_id')}"
    )


def partition_for_eval(deltas: List[dict], tip_off_iso: str) -> Tuple[List[dict], List[dict]]:
    """Split into (leak_free, fallback_proxy).

    leak_free: forward-captured rows with extracted_at < tip (the only ones allowed in the
               headline 'shipped + validated' calibration verdict).
    fallback_proxy: rows flagged is_fallback_proxy=True -- reconstructed from post-game truth
               (selection conditioned on realized DNP). Metrics on these are OPTIMISTIC UPPER
               BOUNDS, NOT leak-free wins. (The QA fix.)
    """
    leak_free, proxy = [], []
    for d in deltas:
        if d.get("is_fallback_proxy"):
            proxy.append(d)
            continue
        assert_vintage(d, tip_off_iso)  # forward-captured rows MUST pass the vintage guard
        leak_free.append(d)
    return leak_free, proxy


def label_metric(subset_kind: str, value: float) -> Dict[str, object]:
    """Tag a metric with its honesty status so an upper bound is never read as a win."""
    assert subset_kind in ("leak_free", "fallback_proxy")
    return {
        "value": float(value),
        "kind": subset_kind,
        "honesty": "leak_free" if subset_kind == "leak_free" else "OPTIMISTIC_UPPER_BOUND",
    }


def vacated_usage_share(delta: dict, player_usage: float) -> float:
    """Mapping stub: an OUT player's usage is vacated for redistribution by the existing
    vacated-load model. Returns the share to redistribute (0 if the player still plays)."""
    return float(player_usage) if delta["status"] == "OUT" else 0.0
