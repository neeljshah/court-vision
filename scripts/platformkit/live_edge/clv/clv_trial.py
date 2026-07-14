"""scripts.platformkit.live_edge.clv.clv_trial -- the month-long CLV trial's
aggregation/scoreboard layer.

Consumes rows already graded by shadow_ledger.grade_row (imported, never
reimplemented): each row carries unconditioned_clv_units, conditioned_clv_units,
is_clv_suspect, sq_err_vs_close. This module ONLY aggregates + selects + reports
-- it does not compute per-row CLV.

CLV DISCIPLINE (binding, see .planning/omni/live_edge_STATE.md + memory
reference_crossvenue_clv_basis_2026_07_06): cross-venue CLV is BASIS, not edge.
Every headline number here is SAME-BOOK ONLY (row["book"] == row["close_source"]
=> is_clv_suspect False). Suspect rows are counted and shown separately, never
folded into a headline. Units only, never $/ROI/bankroll. edge_claimed is
always False; every verdict is stamped PROVISIONAL -- a CLV number here is NOT
an edge claim until an explicit edge_greenlight elsewhere in the repo says so.

INVARIANTS: stdlib only; ASCII; <=300 LOC; never writes the claims journal;
never mutates shadow_ledger rows.
"""
from __future__ import annotations

import random
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

Row = Dict[str, Any]

_BOOT_N = 2000
_BOOT_SEED = 0
_ALPHA = 0.05


def market_family(market: str) -> str:
    """Last dot-segment of a market string, e.g. 'pregame.moneyline' ->
    'moneyline'. Groups pregame/ingame variants of the same bet shape."""
    m = str(market or "")
    return m.rsplit(".", 1)[-1] if m else "unknown"


def group_key(row: Row) -> Tuple[str, str]:
    return (str(row.get("sport") or "unknown"), market_family(row.get("market")))


# ---------------------------------------------------------------------------
# Distribution stats (stdlib only; bootstrap CI on the mean)
# ---------------------------------------------------------------------------

def _bootstrap_ci_mean(values: Sequence[float], *, n_boot: int = _BOOT_N,
                        seed: int = _BOOT_SEED, alpha: float = _ALPHA
                        ) -> Tuple[Optional[float], Optional[float]]:
    n = len(values)
    if n < 2:
        return (None, None)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int((alpha / 2) * n_boot)
    hi_idx = min(n_boot - 1, int((1 - alpha / 2) * n_boot))
    return (round(means[lo_idx], 4), round(means[hi_idx], 4))


def clv_distribution(values: Sequence[float]) -> Dict[str, Any]:
    """n, median, IQR, mean + bootstrap 95% CI on the mean. Empty input is
    reported honestly (all None / n=0), never fabricated."""
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return {"n": 0, "median": None, "iqr": [None, None], "mean": None,
                "ci95": [None, None]}
    q = statistics.quantiles(vals, n=4, method="inclusive") if n >= 2 else [vals[0], vals[0], vals[0]]
    lo, hi = _bootstrap_ci_mean(vals)
    return {
        "n": n,
        "median": round(statistics.median(vals), 4),
        "iqr": [round(q[0], 4), round(q[2], 4)],
        "mean": round(sum(vals) / n, 4),
        "ci95": [lo, hi],
    }


# ---------------------------------------------------------------------------
# Same-book / suspect split (the binding CLV discipline)
# ---------------------------------------------------------------------------

def same_book_split(rows: Sequence[Row]) -> Tuple[List[Row], List[Row]]:
    """(same_book_rows, suspect_rows). Trusts row['is_clv_suspect'] as set by
    shadow_ledger.grade_row -- never recomputed here."""
    same, suspect = [], []
    for r in rows:
        (suspect if r.get("is_clv_suspect") else same).append(r)
    return same, suspect


# ---------------------------------------------------------------------------
# Conditioned-vs-unconditioned delta
# ---------------------------------------------------------------------------

def conditioned_delta(rows: Sequence[Row]) -> Dict[str, Any]:
    """Per-row (conditioned_clv_units - unconditioned_clv_units), distributed.
    Positive => conditioning moved CLV in the market's favor vs the raw pred."""
    deltas = [
        float(r["conditioned_clv_units"]) - float(r["unconditioned_clv_units"])
        for r in rows
        if r.get("conditioned_clv_units") is not None
        and r.get("unconditioned_clv_units") is not None
    ]
    return clv_distribution(deltas)


# ---------------------------------------------------------------------------
# Selection policy hook -- which predictions would become "paper bets"
# ---------------------------------------------------------------------------

def selection_policy(rows: Sequence[Row], *, threshold: float = 0.03,
                      pred_field: str = "conditioned_pred") -> Dict[str, Any]:
    """Threshold on |model_pred - market_price_at_capture| (divergence from
    the price we could transact at when the prediction was made). This is a
    PARAMETERIZED HOOK, not a validated trigger -- selecting bigger-divergence
    rows can select for noise as easily as signal; the honest use is to report
    what the selected subset's CLV looks like, not to claim it is +EV."""
    selected = []
    for r in rows:
        pred = r.get(pred_field)
        price = r.get("market_price")
        if pred is None or price is None:
            continue
        if abs(float(pred) - float(price)) >= threshold:
            selected.append(r)
    same, suspect = same_book_split(selected)
    field = "conditioned_clv_units" if pred_field == "conditioned_pred" else "unconditioned_clv_units"
    return {
        "policy": "abs(pred - market_price_at_capture) >= threshold",
        "pred_field": pred_field,
        "threshold": threshold,
        "n_candidates": len(rows),
        "n_selected": len(selected),
        "n_selected_same_book": len(same),
        "n_selected_suspect": len(suspect),
        "selected_same_book_clv": clv_distribution([r[field] for r in same if r.get(field) is not None]),
        "note": "selection hook, NOT a validated +EV trigger -- report only.",
    }


# ---------------------------------------------------------------------------
# Verdict language -- calibration, never edge
# ---------------------------------------------------------------------------

def verdict_label(ci95: Tuple[Optional[float], Optional[float]], n: int, *, min_n: int = 10) -> str:
    lo, hi = ci95
    if n < min_n or lo is None or hi is None:
        return "INSUFFICIENT_DATA"
    if lo > 0.0:
        return "AHEAD_OF_CLOSE (provisional)"
    if hi < 0.0:
        return "BEHIND_CLOSE (provisional)"
    return "PAR_WITH_CLOSE (provisional)"


# ---------------------------------------------------------------------------
# Top-level aggregation
# ---------------------------------------------------------------------------

def aggregate_trial(rows: Sequence[Row], *, selection_threshold: float = 0.03) -> Dict[str, Any]:
    """Per (sport, market_family) CLV scoreboard + overall selection-policy
    demo + per-sport verdict. Headline numbers are SAME-BOOK ONLY throughout;
    cross-venue (is_clv_suspect) rows are counted but never folded in.
    edge_claimed is always False -- this is a calibration/CLV MEASUREMENT
    tool, not an edge-decision tool."""
    groups: Dict[Tuple[str, str], List[Row]] = {}
    for r in rows:
        groups.setdefault(group_key(r), []).append(r)

    families: Dict[str, Any] = {}
    per_sport_same: Dict[str, List[Row]] = {}
    for (sport, fam), grp in sorted(groups.items()):
        same, suspect = same_book_split(grp)
        per_sport_same.setdefault(sport, []).extend(same)
        key = "%s.%s" % (sport, fam)
        families[key] = {
            "sport": sport,
            "market_family": fam,
            "n_total": len(grp),
            "n_same_book": len(same),
            "n_suspect_cross_venue": len(suspect),
            "unconditioned_clv": clv_distribution(
                [r["unconditioned_clv_units"] for r in same if r.get("unconditioned_clv_units") is not None]),
            "conditioned_clv": clv_distribution(
                [r["conditioned_clv_units"] for r in same if r.get("conditioned_clv_units") is not None]),
            "conditioned_minus_unconditioned": conditioned_delta(same),
        }

    per_sport: Dict[str, Any] = {}
    for sport, same_rows in sorted(per_sport_same.items()):
        cond = clv_distribution([r["conditioned_clv_units"] for r in same_rows
                                  if r.get("conditioned_clv_units") is not None])
        per_sport[sport] = {
            "n_same_book": len(same_rows),
            "conditioned_clv": cond,
            "verdict": verdict_label(tuple(cond["ci95"]), cond["n"]),
        }

    all_same, all_suspect = same_book_split(rows)
    return {
        "edge_claimed": False,
        "n_rows_total": len(rows),
        "n_same_book": len(all_same),
        "n_suspect_cross_venue": len(all_suspect),
        "families": families,
        "per_sport": per_sport,
        "selection_policy_demo": selection_policy(all_same, threshold=selection_threshold),
        "note": "Every number here is PROVISIONAL calibration/CLV measurement, "
                "same-book only, edge_claimed=False. Cross-venue rows are basis, "
                "not edge (excluded from headlines, counted above).",
    }


__all__ = [
    "market_family", "group_key", "clv_distribution", "same_book_split",
    "conditioned_delta", "selection_policy", "verdict_label", "aggregate_trial",
]
