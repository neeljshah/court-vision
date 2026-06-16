"""Freshness X1 -- the fallback-proxy quarantine (honest-discipline firewall).

Where true vintage extracted_at is unavailable, the validation blueprint allows a conservative
proxy (extracted_at = tip - 90min) ONLY for status=OUT rows that the historical box score
confirms as a DNP-injury. That selection is OUTCOME-CONDITIONED -- we know the player was OUT
only because the game already happened -- so ANY metric computed on the proxy subset is an
OPTIMISTIC UPPER BOUND, never a leak-free calibration result.

This module makes that distinction mechanical: make_fallback_proxy() stamps the firewall flag,
and label_metric() refuses to tag a proxy-derived number as leak_free. The headline verdict may
ONLY come from forward-captured vintage; the proxy bounds how large the effect could be if timing
were perfect, nothing more.

Stdlib only. Reuses the eval_gate label_metric pattern (honesty tag travels with the value).
"""
from __future__ import annotations
from typing import Dict

OPTIMISTIC = "OPTIMISTIC_UPPER_BOUND"
LEAK_FREE = "leak_free"
_KINDS = (LEAK_FREE, "fallback_proxy")


def make_fallback_proxy(delta: dict, tip_off_iso: str, minutes_before: int = 90) -> dict:
    """Return a copy of `delta` stamped is_fallback_proxy=True with a conservative pre-tip stamp.

    extracted_at is set to (tip - minutes_before). The proxy is honest ONLY as an upper bound;
    label any metric computed on it via label_metric('fallback_proxy', ...). This function does
    NOT make the row leak-free -- it explicitly marks it as the opposite.
    """
    from datetime import datetime, timedelta
    tip = datetime.fromisoformat(tip_off_iso)
    stamp = (tip - timedelta(minutes=minutes_before)).isoformat()
    out = dict(delta)
    out["is_fallback_proxy"] = True
    out["extracted_at"] = stamp
    return out


def label_metric(subset_kind: str, value: float) -> Dict[str, object]:
    """Tag a metric with its honesty status so an upper bound is never read as a real win."""
    assert subset_kind in _KINDS, f"unknown subset kind {subset_kind}"
    return {
        "value": float(value),
        "kind": subset_kind,
        "honesty": LEAK_FREE if subset_kind == LEAK_FREE else OPTIMISTIC,
    }


def assert_not_proxy_leak_free(metric: Dict[str, object]) -> None:
    """Firewall: refuse to let a proxy-derived number masquerade as leak_free.

    Raises AssertionError if a fallback_proxy metric is tagged anything other than the optimistic
    upper bound. Call this before any number is reported as a validated calibration result.
    """
    if metric.get("kind") == "fallback_proxy":
        assert metric.get("honesty") == OPTIMISTIC, (
            "FIREWALL: fallback_proxy metric must be OPTIMISTIC_UPPER_BOUND, "
            f"got {metric.get('honesty')}"
        )
