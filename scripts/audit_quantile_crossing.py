"""audit_quantile_crossing.py — iter-14 of autonomous data-completion loop.

Measures how often `predict_pergame_quantiles` (the production live predictor)
returns crossed quantiles (q90 < q50, q50 < q10, or q90 < q10) on a real
historical workload — the 5108-row 2024 playoffs canonical CSV.

Why this matters: iter-8 spotted Wemby BLK with q10=0.00 q50=2.14 q90=1.11
(q90 < q50). The three quantile heads (q10, q50, q90) are trained as three
independent XGB regressors with `objective=reg:quantileerror`, so monotonicity
across q-levels is NOT guaranteed. This audit quantifies the bug's blast
radius before we ship the (gated) fix (`sorted([q10, q50, q90])`).

Outputs:
  * per-stat crossing-rate table
  * top-10 worst cases (most negative interval widths)
  * count of iter-4 bet decisions that would FLIP / APPEAR / DISAPPEAR
    if we applied the `sorted_q` projection
  * recommendation tier (urgent / nice-to-have / minor)

Read-only: this script does NOT mutate `prop_quantiles.py` nor any model on
disk. It imports `predict_pergame_quantiles` and `predict_pergame` and uses
the iter-6 `_build_asof_row` helper.

Runtime budget: ~5–8 minutes for 5108 rows on local CPU.
"""
from __future__ import annotations

import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from math import erf, sqrt
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Disable injury wire — playoff CSV already encodes availability via actual_value.
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
)
from src.prediction.prop_pergame import predict_pergame  # noqa: E402
from src.prediction.prop_quantiles import predict_pergame_quantiles  # noqa: E402

try:
    from src.prediction.quantile_calibration import apply as apply_quantile_calibration
except Exception:  # pragma: no cover — calibration optional
    apply_quantile_calibration = None  # type: ignore


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
MIN_EDGE = 0.5  # iter-4 default — same as backtest_closing_lines_2024_playoffs


# ────────────────────────────────────────────── helpers (copied from iter-4) ──

def _american_payout(odds: int) -> float:
    odds = int(odds)
    return (odds / 100.0) if odds > 0 else (100.0 / -odds)


def _model_hit_prob(point_pred: float, q10: float, q50: float, q90: float,
                    line: float, side: str) -> Optional[float]:
    """Raw (uncalibrated) Normal-CDF mapping. Use raw so the audit reflects what
    the bug affects directly; calibration only rescales the interval."""
    if q10 is None or q90 is None or point_pred is None:
        return None
    if apply_quantile_calibration is not None:
        try:
            # Use the same flavour predict_slate / compare_to_lines uses.
            stat_label = None  # set by caller below; we wrap properly
        except Exception:
            stat_label = None
    sigma = max((q90 - q10) / (2 * 1.2816), 1e-6)
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1.0 + erf(z / sqrt(2)))
    p_over = 1.0 - cdf_at_line
    return p_over if side == "OVER" else 1.0 - p_over


def _hit_prob_for_stat(stat: str, point_pred: float, q10: float, q50: float,
                        q90: float, line: float, side: str) -> Optional[float]:
    """Cycle-40 calibrated version, matching compare_to_lines._model_hit_prob."""
    if q10 is None or q90 is None or point_pred is None:
        return None
    if apply_quantile_calibration is not None:
        try:
            c10, c90 = apply_quantile_calibration(stat, q10, q50 or point_pred, q90)
            q10, q90 = c10, c90
        except Exception:
            pass
    sigma = max((q90 - q10) / (2 * 1.2816), 1e-6)
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1.0 + erf(z / sqrt(2)))
    p_over = 1.0 - cdf_at_line
    return p_over if side == "OVER" else 1.0 - p_over


def _bet_decision(point_pred: float, line: float, stat: str,
                  q10: float, q50: float, q90: float,
                  over_odds: int, under_odds: int) -> Optional[dict]:
    """Replicates iter-4 / compare_to_lines.py recommendation logic.
    Returns dict with side / prob / ev / kelly_pct, or None if |edge| < MIN_EDGE."""
    edge = point_pred - line
    if abs(edge) < MIN_EDGE:
        return None
    side = "OVER" if edge > 0 else "UNDER"
    odds = over_odds if side == "OVER" else under_odds
    prob = _hit_prob_for_stat(stat, point_pred, q10, q50, q90, line, side)
    if prob is None:
        return None
    net_payout = _american_payout(odds)
    ev = prob * net_payout - (1.0 - prob) * 1.0
    return {
        "side": side, "odds": odds, "prob": prob, "ev": ev,
        "is_positive_ev": ev > 0.0,
    }


# ─────────────────────────────────────────────────────────────────── main ────

def main():
    t0 = time.time()
    with open(CSV_PATH, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    print(f"  Loaded {len(rows)} rows from {os.path.basename(CSV_PATH)}")

    unique_names = sorted({r["player"] for r in rows})
    name2pid: Dict[str, Optional[int]] = {}
    for nm in unique_names:
        name2pid[nm] = _resolve_player_id(nm)
    print(f"  Resolved {sum(1 for v in name2pid.values() if v)}/{len(unique_names)} players")

    row_cache: Dict[Tuple[int, str, str, str], Optional[Dict[str, float]]] = {}

    per_stat = defaultdict(lambda: {
        "n_pred": 0,
        "n_q90_lt_q50": 0,
        "n_q50_lt_q10": 0,
        "n_q90_lt_q10": 0,
        "n_any_crossing": 0,
        "violations": [],         # (severity, record)
    })
    worst_global: List[Tuple[float, dict]] = []
    skip_reasons: Dict[str, int] = defaultdict(int)

    # Bet-decision impact tally
    bets_buggy: int = 0          # positive-EV bets recommended under current (buggy) code
    bets_fixed: int = 0          # positive-EV bets recommended under sorted_q fix
    bets_flip_side: int = 0      # OVER↔UNDER swap (impossible since edge doesn't change, but track)
    bets_appear: int = 0         # not bet now, bet under fix
    bets_disappear: int = 0      # bet now, not bet under fix
    bets_changed_anything: int = 0  # |Δprob| > 0.01 OR |Δev| > 0.005

    for idx, r in enumerate(rows):
        player = r["player"]; opp = r["opp"]; venue = r["venue"]
        stat = r["stat"].lower()
        try:
            line = float(r["closing_line"])
            over_odds = int(r.get("over_odds", -110))
            under_odds = int(r.get("under_odds", -110))
        except (TypeError, ValueError):
            skip_reasons["bad_numeric"] += 1; continue
        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip_reasons["bad_date"] += 1; continue
        pid = name2pid.get(player)
        if pid is None:
            skip_reasons["no_pid"] += 1; continue

        season = _season_for_date(d)
        is_home = (venue == "home")
        key = (pid, r["date"], venue, opp)
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, opp, d, season, is_home=is_home, rest_days=2.0,
                gamelog_dir=GAMELOG_DIR,
            )
        feat_row = row_cache[key]
        if feat_row is None:
            skip_reasons["no_history"] += 1; continue

        try:
            qint = predict_pergame_quantiles(stat, feat_row, MODEL_DIR)
        except Exception as e:
            skip_reasons[f"q_err:{type(e).__name__}"] += 1; continue
        if qint is None:
            skip_reasons["no_q_model"] += 1; continue
        q10 = float(qint.get("q10", 0.0))
        q50 = float(qint.get("q50", 0.0))
        q90 = float(qint.get("q90", 0.0))

        try:
            point_pred = predict_pergame(stat, feat_row)
        except Exception:
            point_pred = None
        if point_pred is None:
            # Not blocking the crossing audit, but bet decision will be skipped.
            point_pred = q50

        crossed_90_50 = q90 < q50
        crossed_50_10 = q50 < q10
        crossed_90_10 = q90 < q10
        any_crossed = crossed_90_50 or crossed_50_10 or crossed_90_10

        s = per_stat[stat]
        s["n_pred"] += 1
        s["n_q90_lt_q50"] += int(crossed_90_50)
        s["n_q50_lt_q10"] += int(crossed_50_10)
        s["n_q90_lt_q10"] += int(crossed_90_10)
        s["n_any_crossing"] += int(any_crossed)

        # Severity = signed interval width. Negative => crossed/inverted.
        severity = q90 - q10
        if any_crossed:
            rec = {
                "player": player, "date": r["date"], "stat": stat,
                "q10": q10, "q50": q50, "q90": q90,
                "interval_width": severity, "point": point_pred,
                "line": line,
            }
            s["violations"].append((severity, rec))
            worst_global.append((severity, rec))

        # Bet-decision impact — only computed when point_pred is real.
        dec_buggy = _bet_decision(point_pred, line, stat, q10, q50, q90,
                                  over_odds, under_odds)
        sq10, sq50, sq90 = sorted([q10, q50, q90])
        dec_fixed = _bet_decision(point_pred, line, stat, sq10, sq50, sq90,
                                  over_odds, under_odds)

        bug_bet = dec_buggy is not None and dec_buggy["is_positive_ev"]
        fix_bet = dec_fixed is not None and dec_fixed["is_positive_ev"]
        if bug_bet:
            bets_buggy += 1
        if fix_bet:
            bets_fixed += 1
        if bug_bet and not fix_bet:
            bets_disappear += 1
        if fix_bet and not bug_bet:
            bets_appear += 1
        if bug_bet and fix_bet and dec_buggy["side"] != dec_fixed["side"]:
            bets_flip_side += 1
        if dec_buggy is not None and dec_fixed is not None:
            dp = abs(dec_buggy["prob"] - dec_fixed["prob"])
            dev = abs(dec_buggy["ev"] - dec_fixed["ev"])
            if dp > 0.01 or dev > 0.005:
                bets_changed_anything += 1

        if (idx + 1) % 500 == 0:
            print(f"  ...{idx+1}/{len(rows)} processed "
                  f"({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"\n  Audit finished in {elapsed:.1f}s")
    print(f"  Skip reasons: {dict(skip_reasons)}")

    # ── per-stat table ──────────────────────────────────────────────────────
    print("\n  Per-stat quantile-crossing rates")
    header = (f"  {'stat':4s} | {'n_pred':>6s} | {'n_q90<q50':>9s} | "
              f"{'n_q50<q10':>9s} | {'n_q90<q10':>9s} | "
              f"{'n_any':>6s} | {'cross%':>6s} | {'med_sev':>8s}")
    print(header); print("  " + "-" * (len(header) - 2))
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
        s = per_stat.get(stat)
        if not s or s["n_pred"] == 0:
            continue
        cross_pct = 100.0 * s["n_any_crossing"] / s["n_pred"]
        if s["violations"]:
            sevs = [v[0] for v in s["violations"]]
            med = float(np.median(sevs))
        else:
            med = 0.0
        print(f"  {stat.upper():4s} | {s['n_pred']:6d} | "
              f"{s['n_q90_lt_q50']:9d} | {s['n_q50_lt_q10']:9d} | "
              f"{s['n_q90_lt_q10']:9d} | {s['n_any_crossing']:6d} | "
              f"{cross_pct:5.2f}% | {med:8.3f}")

    # ── top-10 worst cases ──────────────────────────────────────────────────
    worst_global.sort(key=lambda t: t[0])  # most negative first
    print("\n  Top-10 worst crossings (most-negative interval width):")
    print(f"  {'#':>2s}  {'player':<22s} {'date':10s} {'stat':4s} "
          f"{'q10':>5s} {'q50':>5s} {'q90':>5s} {'width':>6s}")
    for i, (sev, rec) in enumerate(worst_global[:10]):
        print(f"  {i+1:2d}  {rec['player'][:22]:<22s} {rec['date']:10s} "
              f"{rec['stat'].upper():4s} {rec['q10']:5.2f} {rec['q50']:5.2f} "
              f"{rec['q90']:5.2f} {sev:6.2f}")

    # ── player concentration (top 5 players by crossing count) ──────────────
    by_player: Dict[str, int] = defaultdict(int)
    for _sev, rec in worst_global:
        by_player[rec["player"]] += 1
    top_players = sorted(by_player.items(), key=lambda kv: -kv[1])[:5]
    print("\n  Top-5 players by # crossings:")
    for p, n in top_players:
        print(f"    {p:<26s} {n:3d} crossings")

    # ── bet impact ──────────────────────────────────────────────────────────
    print("\n  Bet-decision impact (iter-4 logic, MIN_EDGE=0.5, positive-EV only):")
    print(f"    bets under BUGGY code:   {bets_buggy:5d}")
    print(f"    bets under FIXED code:   {bets_fixed:5d}")
    print(f"    bets that APPEAR:        {bets_appear:5d}")
    print(f"    bets that DISAPPEAR:     {bets_disappear:5d}")
    print(f"    bets that FLIP side:     {bets_flip_side:5d}")
    print(f"    any prob/EV change (>0.01 prob OR >0.005 EV): {bets_changed_anything:5d}")

    # ── recommendation ──────────────────────────────────────────────────────
    total_pred = sum(s["n_pred"] for s in per_stat.values())
    total_cross = sum(s["n_any_crossing"] for s in per_stat.values())
    overall_rate = 100.0 * total_cross / max(total_pred, 1)
    total_bet_changes = bets_appear + bets_disappear + bets_flip_side
    print(f"\n  Overall crossing rate: {overall_rate:.2f}% "
          f"({total_cross}/{total_pred})")
    print(f"  Total bet-decision changes: {total_bet_changes}")

    if overall_rate > 5.0 or total_bet_changes > 50:
        tier = "URGENT"
    elif overall_rate > 1.0 or total_bet_changes > 10:
        tier = "NICE-TO-HAVE"
    else:
        tier = "MINOR"
    print(f"  Recommendation tier: {tier}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
