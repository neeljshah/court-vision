"""scripts.platformkit.execution.markout -- fee-netted markout for paper maker fills.

Audit 2026-09-17 defect #9: no markout existed anywhere, and no realized number
netted a venue fee -- fees were charged into the PRE-TRADE EV gate only
(inplay_edge_signal.py:175). This scores a fill AFTER the fact: where did the
market go once we were filled, minus what the fill cost.

UNITS ONLY. A markout here is in PROBABILITY POINTS per contract, never dollars
and never a return. A positive markout means the mid moved our way after the
fill; it is a microstructure diagnostic, NOT an edge or a profit claim, and a
single fill or a single game is never evidence of either.

Input is paper_maker._fill_record()'s dict: {side, price, qty, fee_units, ...}.
*side* is the ORDER side ("yes"/"no"); *later_mid* is the YES-home mid observed
some agreed horizon after the fill, so the "no" leg is scored against 1 - mid.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; stdlib only; no writes.
Test: python -m pytest tests/platformkit/execution/test_markout.py -q
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from scripts.platformkit.execution.entry_timing.study import cluster_boot_ci


def _f(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN -> None


def markout(fill: Dict[str, Any], later_mid: Any, fee: Any = None) -> Optional[float]:
    """Fee-netted markout of ONE fill against *later_mid*, in probability points.

    yes: later_mid - fill_price. no: (1 - later_mid) - fill_price. The fee is
    SUBTRACTED and always as a magnitude, so it can only ever reduce the number.
    *fee* defaults to the fill's own recorded fee_units (per contract, stamped at
    fill time by the then-current schedule). None when the fill or the mid is
    unusable -- never a fabricated 0.0, which would read as a flat result.
    """
    if not isinstance(fill, dict):
        return None
    price, mid = _f(fill.get("price")), _f(later_mid)
    if price is None or mid is None or not 0.0 <= mid <= 1.0:
        return None
    cost = _f(fill.get("fee_units") if fee is None else fee) or 0.0
    side = str(fill.get("side") or "").strip().lower()
    if side == "yes":
        gross = mid - price
    elif side == "no":
        gross = (1.0 - mid) - price
    else:
        return None  # unknown side: refuse rather than guess a direction
    return gross - abs(cost)


def markout_summary(fills: Iterable[Dict[str, Any]], later_mids: Sequence[Any],
                    *, cluster_key: str = "game_id") -> Dict[str, Any]:
    """Mean fee-netted markout over paired (fill, later_mid), with a
    GAME-CLUSTERED bootstrap 95% CI.

    Ticks inside one game are not independent, so the CI resamples whole games --
    reusing entry_timing.study.cluster_boot_ci, the same estimator the entry-timing
    study already reports. It returns (None, None) below 5 clusters; that is
    surfaced here as verdict INSUFFICIENT rather than dressed up as a result.
    Fills whose markout cannot be computed are counted in n_unscored, never
    silently dropped to 0.0.
    """
    values: List[float] = []
    clusters: List[Any] = []
    unscored = 0
    for fill, mid in zip(fills, later_mids):
        value = markout(fill, mid)
        if value is None:
            unscored += 1
            continue
        values.append(value)
        clusters.append((fill.get(cluster_key) or fill.get("ticker") or len(clusters)))
    n_clusters = len(set(clusters))
    if not values:
        return {"n": 0, "n_clusters": 0, "n_unscored": unscored, "mean_units": None,
                "ci_95_units": [None, None], "verdict": "INSUFFICIENT",
                "units": "probability_points", "edge_claimed": False}
    lo, hi = cluster_boot_ci(values, clusters)
    mean = sum(values) / len(values)
    verdict = "INSUFFICIENT" if lo is None or hi is None else (
        "POSITIVE" if lo > 0.0 else "NEGATIVE" if hi < 0.0 else "INDISTINGUISHABLE")
    return {"n": len(values), "n_clusters": n_clusters, "n_unscored": unscored,
            "mean_units": round(mean, 6),
            "ci_95_units": [lo if lo is None else round(lo, 6),
                            hi if hi is None else round(hi, 6)],
            "verdict": verdict, "units": "probability_points", "edge_claimed": False}


def _demo() -> None:
    """Smallest runnable self-check (assert-based); not a test framework."""
    fill = {"side": "yes", "price": 0.65, "qty": 1, "fee_units": 0.01}
    assert abs(markout(fill, 0.70) - 0.04) < 1e-9          # moved our way, net of fee
    assert abs(markout(fill, 0.65) - (-0.01)) < 1e-9       # flat mid -> we paid the fee
    no_fill = {"side": "no", "price": 0.35, "fee_units": 0.01}
    assert abs(markout(no_fill, 0.60) - 0.04) < 1e-9
    assert markout({"side": "maybe", "price": 0.5}, 0.5) is None
    assert markout_summary([], [])["verdict"] == "INSUFFICIENT"
    print("markout self-check OK")


if __name__ == "__main__":
    _demo()


__all__ = ["markout", "markout_summary"]
