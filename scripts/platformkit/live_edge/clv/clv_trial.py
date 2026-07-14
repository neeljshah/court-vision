"""scripts.platformkit.live_edge.clv.clv_trial -- the month-long CLV trial's
aggregation/scoreboard layer.

Consumes rows already graded by shadow_ledger.grade_row (imported, never
reimplemented). This module ONLY aggregates + selects + reports -- it does
not compute per-row CLV.

CLV DISCIPLINE (binding, reference_crossvenue_clv_basis_2026_07_06):
cross-venue CLV is BASIS, not edge; headlines are SAME-BOOK ONLY, suspect
rows counted but never folded in, units only (never $/ROI/bankroll),
edge_claimed always False, every verdict PROVISIONAL.

ROBUST VERDICT: legacy mean-CI verdict_label is FOOLABLE ("CLV fattest on
losers" -- longshots can make the mean positive while the median loses).
robust_verdict_label requires median>0 AND share-beating-close>50% AND a
trimmed-mean CI excluding 0 AND probability-point agreement, else PAR/BEHIND.

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
    """Last dot-segment, e.g. 'pregame.moneyline' -> 'moneyline'."""
    m = str(market or "")
    return m.rsplit(".", 1)[-1] if m else "unknown"


def group_key(row: Row) -> Tuple[str, str]:
    return (str(row.get("sport") or "unknown"), market_family(row.get("market")))


# -- Distribution stats (stdlib only; bootstrap CI on the mean) --

def _bootstrap_ci_estimator(values: Sequence[float], estimator, *,
                             n_boot: int = _BOOT_N, seed: int = _BOOT_SEED,
                             alpha: float = _ALPHA
                             ) -> Tuple[Optional[float], Optional[float]]:
    """Generic bootstrap CI for any point estimator (mean, trimmed mean, ...)."""
    n = len(values)
    if n < 2:
        return (None, None)
    rng = random.Random(seed)
    ests = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        est = estimator(sample)
        if est is not None:
            ests.append(est)
    if not ests:
        return (None, None)
    ests.sort()
    m = len(ests)
    lo_idx = int((alpha / 2) * m)
    hi_idx = min(m - 1, int((1 - alpha / 2) * m))
    return (round(ests[lo_idx], 4), round(ests[hi_idx], 4))


def clv_distribution(values: Sequence[float]) -> Dict[str, Any]:
    """n, median, IQR, mean + bootstrap 95% CI. Empty input -> all None."""
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return {"n": 0, "median": None, "iqr": [None, None], "mean": None,
                "ci95": [None, None]}
    q = statistics.quantiles(vals, n=4, method="inclusive") if n >= 2 else [vals[0], vals[0], vals[0]]
    lo, hi = _bootstrap_ci_estimator(vals, lambda s: sum(s) / len(s))
    return {
        "n": n,
        "median": round(statistics.median(vals), 4),
        "iqr": [round(q[0], 4), round(q[2], 4)],
        "mean": round(sum(vals) / n, 4),
        "ci95": [lo, hi],
    }


# -- Same-book / suspect split (the binding CLV discipline) --

def same_book_split(rows: Sequence[Row]) -> Tuple[List[Row], List[Row]]:
    """(same_book_rows, suspect_rows), trusting row['is_clv_suspect']."""
    same, suspect = [], []
    for r in rows:
        (suspect if r.get("is_clv_suspect") else same).append(r)
    return same, suspect


# -- Conditioned-vs-unconditioned delta --

def conditioned_delta(rows: Sequence[Row]) -> Dict[str, Any]:
    """Per-row (conditioned - unconditioned) clv_units, distributed."""
    deltas = [
        float(r["conditioned_clv_units"]) - float(r["unconditioned_clv_units"])
        for r in rows
        if r.get("conditioned_clv_units") is not None
        and r.get("unconditioned_clv_units") is not None
    ]
    return clv_distribution(deltas)


# -- Selection policy hook -- which predictions would become "paper bets" --

def selection_policy(rows: Sequence[Row], *, threshold: float = 0.03,
                      pred_field: str = "conditioned_pred") -> Dict[str, Any]:
    """Threshold on |model_pred - market_price_at_capture|. PARAMETERIZED
    HOOK, not a validated trigger -- report only, never claim +EV."""
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


# -- Verdict language -- calibration, never edge --

def verdict_label(ci95: Tuple[Optional[float], Optional[float]], n: int, *, min_n: int = 10) -> str:
    """LEGACY mean-CI verdict (FOOLABLE by longshot skew, see module doc).
    Kept for backward compat; headline verdict is robust_verdict_label."""
    lo, hi = ci95
    if n < min_n or lo is None or hi is None:
        return "INSUFFICIENT_DATA"
    if lo > 0.0:
        return "AHEAD_OF_CLOSE (provisional)"
    if hi < 0.0:
        return "BEHIND_CLOSE (provisional)"
    return "PAR_WITH_CLOSE (provisional)"


# -- Robust verdict -- outlier-resistant (fixes the mean-only false-positive) --

def share_beating_close(values: Sequence[float]) -> Optional[float]:
    """Fraction of bets with clv > 0 (typical-bet win rate vs the close)."""
    vals = [float(v) for v in values]
    if not vals:
        return None
    return round(sum(1 for v in vals if v > 0.0) / len(vals), 4)


def trimmed_mean(values: Sequence[float], trim: float = 0.1) -> Optional[float]:
    """Mean after dropping the top/bottom `trim` fraction (skew-resistant)."""
    vals = sorted(float(v) for v in values)
    n = len(vals)
    if n == 0:
        return None
    k = int(n * trim)
    core = vals[k:n - k] if n - 2 * k > 0 else vals
    return round(sum(core) / len(core), 4)


def stake_weighted_mean(values: Sequence[float], weights: Sequence[float]
                         ) -> Optional[float]:
    """Mean weighted by stake_units so a longshot can't outvote many bets."""
    pairs = [(float(v), float(w)) for v, w in zip(values, weights) if w]
    tot_w = sum(w for _, w in pairs)
    if not pairs or tot_w <= 0:
        return None
    return round(sum(v * w for v, w in pairs) / tot_w, 4)


def prob_point_clv(fair_close_prob: float, taken_implied_prob: float) -> float:
    """fair_close_prob - taken_implied_prob, in points (bounded, unlike
    clv_pct which divides by taken_p and explodes for longshots)."""
    return round((float(fair_close_prob) - float(taken_implied_prob)) * 100.0, 4)


def robust_clv_stats(clv_pct_values: Sequence[float], *,
                      prob_point_values: Optional[Sequence[float]] = None,
                      weights: Optional[Sequence[float]] = None,
                      trim: float = 0.1) -> Dict[str, Any]:
    """Outlier-robust scoreboard: median/share/trimmed+CI/stake-weighted/pp."""
    vals = [float(v) for v in clv_pct_values]
    n = len(vals)
    tmean_ci = _bootstrap_ci_estimator(vals, lambda s: trimmed_mean(s, trim)) if n >= 2 else (None, None)
    out: Dict[str, Any] = {
        "n": n,
        "median": round(statistics.median(vals), 4) if n else None,
        "share_beating_close": share_beating_close(vals),
        "trimmed_mean": trimmed_mean(vals, trim) if n else None,
        "trimmed_mean_ci95": list(tmean_ci),
        "stake_weighted_mean": (stake_weighted_mean(vals, weights)
                                 if weights is not None and n else None),
        "prob_point_median": None,
        "prob_point_trimmed_mean": None,
    }
    if prob_point_values:
        pp = [float(v) for v in prob_point_values]
        out["prob_point_median"] = round(statistics.median(pp), 4) if pp else None
        out["prob_point_trimmed_mean"] = trimmed_mean(pp, trim) if pp else None
    return out


def robust_verdict_label(stats: Dict[str, Any], *, min_n: int = 10) -> str:
    """See module docstring for the rule; disagreement/CI-straddles-0 -> PAR."""
    n = stats.get("n") or 0
    median = stats.get("median")
    share = stats.get("share_beating_close")
    lo, hi = (stats.get("trimmed_mean_ci95") or (None, None))
    if n < min_n or median is None or share is None or lo is None or hi is None:
        return "INSUFFICIENT_DATA"
    pp_trim = stats.get("prob_point_trimmed_mean")
    ahead = (median > 0.0 and share > 0.5 and lo > 0.0
             and (pp_trim is None or pp_trim > 0.0))
    behind = (median < 0.0 and share <= 0.5)
    if ahead:
        return "AHEAD_OF_CLOSE (provisional)"
    if behind:
        return "BEHIND_CLOSE (provisional)"
    return "PAR_WITH_CLOSE (provisional)"


# -- Top-level aggregation --

def aggregate_trial(rows: Sequence[Row], *, selection_threshold: float = 0.03) -> Dict[str, Any]:
    """Per (sport, market_family) CLV scoreboard + selection-policy demo +
    per-sport verdict. Headlines SAME-BOOK ONLY; cross-venue rows counted,
    never folded in. edge_claimed always False -- a measurement, not a
    decision tool."""
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
        cond_vals = [r["conditioned_clv_units"] for r in same_rows
                     if r.get("conditioned_clv_units") is not None]
        cond = clv_distribution(cond_vals)
        robust = robust_clv_stats(cond_vals)
        per_sport[sport] = {
            "n_same_book": len(same_rows),
            "conditioned_clv": cond,
            "verdict": verdict_label(tuple(cond["ci95"]), cond["n"]),
            "robust": robust,
            "robust_verdict": robust_verdict_label(robust),
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
        "note": "PROVISIONAL calibration/CLV measurement, same-book only, "
                "edge_claimed=False. Cross-venue rows are basis, not edge.",
    }


__all__ = [
    "market_family", "group_key", "clv_distribution", "same_book_split",
    "conditioned_delta", "selection_policy", "verdict_label", "aggregate_trial",
    "share_beating_close", "trimmed_mean", "stake_weighted_mean",
    "prob_point_clv", "robust_clv_stats", "robust_verdict_label",
]
