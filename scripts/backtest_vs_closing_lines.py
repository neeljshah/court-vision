"""backtest_vs_closing_lines.py — historical backtest vs REAL sportsbook lines.

Cycle 42 (loop 5): the previous backtests (`betting_backtest.py`,
`betting_backtest_smart_line.py`) score the model against a synthetic L5-
based line proxy. The +25-32% ROI numbers they report are vs that proxy,
not vs real sportsbook closing lines, so the honest answer to "would this
have made money" is unknown.

This script answers it. Input CSV schema:
    date,player,opp,venue,stat,closing_line,over_odds,under_odds,actual_value

For each row we (a) ask the production prop model for q50/q10/q90,
(b) calibrate the interval, (c) compute P(actual > closing_line) under a
normal centered at q50 with sigma = (q90_cal - q10_cal) / (2 * 1.2816)
(same logic as `compare_to_lines.py`), (d) take the side with positive EV
above `--threshold-edge`, (e) settle vs `actual_value`. Output is a
profit/loss summary with per-stat breakdown, hit rate, ROI, and max
drawdown — flat $1 by default, Kelly when `--kelly --bankroll N`.

IMPORTANT — TIME-TRAVEL CAVEAT
This script uses the CURRENT production models for every historical row,
which means a 2022-11 line is scored with weights that have already "seen"
data from 2022-12 onward via the training set. ROI here is therefore an
UPPER BOUND. A future cycle should add date-aware retraining (train on
data strictly < row.date for every row) so the backtest is fully out-of-
sample. The relative shape (which stats are profitable, where the edge
threshold breaks even) is still informative.

Run:
    python scripts/backtest_vs_closing_lines.py historical.csv
    python scripts/backtest_vs_closing_lines.py historical.csv \\
        --threshold-edge 0.5 --kelly --bankroll 1000
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import warnings
from collections import defaultdict
from datetime import datetime
from math import erf, sqrt

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_prediction_row, predict_pergame,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    predict_pergame_quantiles,
)
from src.prediction.quantile_calibration import apply as apply_quantile_calibration  # noqa: E402


# ---------- helpers (parallel to compare_to_lines.py) ----------

def _strip_accents(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _resolve_player_id(name: str):
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
    except Exception:
        return None
    needle = _strip_accents(name).lower()
    cands = players.get_players()
    for p in cands:
        if _strip_accents(p["full_name"]).lower() == needle:
            return int(p["id"])
    for p in cands:
        if needle in _strip_accents(p["full_name"]).lower():
            return int(p["id"])
    return None


def _season_for_date(d: str) -> str:
    """NBA season string for ISO date 'YYYY-MM-DD'."""
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        now = datetime.now()
        dt = now
    start = dt.year if dt.month >= 10 else dt.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _american_payout(odds: int, stake: float = 1.0) -> float:
    odds = int(odds)
    if odds > 0:
        return stake * (odds / 100)
    return stake * (100 / -odds)


def _asym_hit_prob_enabled() -> bool:
    """H5 fix gate. Default OFF — the symmetric-sigma path stays byte-identical
    so the validated book is preserved. Set CV_ASYM_HIT_PROB=1 to switch the
    served hit-prob to the split-normal that respects the asymmetric calibrated
    band. See docs/_audits/ASYM_HIT_PROB_AB_2026-06-02.md."""
    return os.environ.get("CV_ASYM_HIT_PROB", "0").strip().lower() in (
        "1", "true", "yes", "on")


def _split_normal_p_over(line, center, sigma_lo, sigma_hi) -> float:
    """P(X > line) for a two-piece (split / Fechner) normal whose CDF passes
    through (center, 0.5). Below the center the dispersion is sigma_lo, above it
    sigma_hi; the two halves are spliced at the median so the result is a proper
    distribution (continuous CDF, integrates to 1). When sigma_lo == sigma_hi it
    reduces exactly to the symmetric Normal."""
    sigma_lo = max(float(sigma_lo), 1e-6)
    sigma_hi = max(float(sigma_hi), 1e-6)
    if line <= center:
        z = (line - center) / sigma_lo
        cdf = 0.5 * (1 + erf(z / sqrt(2)))
    else:
        z = (line - center) / sigma_hi
        cdf = 0.5 * (1 + erf(z / sqrt(2)))
    return 1.0 - cdf


def _model_hit_prob(stat, point_pred, qint, line, side):
    """P(side wins) under the calibrated interval centred at q50.

    Default (CV_ASYM_HIT_PROB OFF): a single symmetric Gaussian sigma derived
    from the full calibrated 80% width — byte-identical to the historical path.

    When CV_ASYM_HIT_PROB is ON (H5 fix): a SPLIT-NORMAL respecting the
    asymmetric calibrated band — sigma_lo from (q50 - cal_q10), sigma_hi from
    (cal_q90 - q50), both /1.2816, centred at q50 — so the served CDF passes
    through (cal_q10, .10), (q50, .50), (cal_q90, .90). For symmetric bands this
    collapses to the OFF result exactly."""
    q10 = qint.get("q10"); q50 = qint.get("q50"); q90 = qint.get("q90")
    if q10 is None or q90 is None or point_pred is None:
        return None
    cal_q10, cal_q90 = apply_quantile_calibration(
        stat, q10, q50 or point_pred, q90
    )
    if _asym_hit_prob_enabled():
        center = q50 if q50 is not None else point_pred
        sigma_lo = max((center - cal_q10) / 1.2816, 1e-6)
        sigma_hi = max((cal_q90 - center) / 1.2816, 1e-6)
        p_over = _split_normal_p_over(line, center, sigma_lo, sigma_hi)
        return p_over if side == "OVER" else 1 - p_over
    sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1 - cdf_at_line
    return p_over if side == "OVER" else 1 - p_over


def _kelly_fraction(prob, odds):
    b = _american_payout(odds, 1.0)
    p = prob; q = 1 - p
    f = (b * p - q) / b
    return max(0.0, f)


# ---------- core: score one row ----------

def _score_row(row, gamelog_dir, model_dir,
               predict_fn=None, quantile_fn=None):
    """Return dict with model output + bet decision, or None on skip.

    `predict_fn` / `quantile_fn` are injected for tests so we don't need
    the trained models on disk to unit-test the bet-math + accounting.
    """
    predict_fn  = predict_fn  or predict_pergame
    quantile_fn = quantile_fn or predict_pergame_quantiles

    stat = row["stat"].lower()
    if stat not in STATS:
        return None
    name = row["player"].strip(); opp = row["opp"].strip().upper()
    venue = row.get("venue", "home").lower()
    try:
        line   = float(row["closing_line"])
        actual = float(row["actual_value"])
    except (KeyError, ValueError):
        return None
    over_odds  = int(row.get("over_odds")  or -110)
    under_odds = int(row.get("under_odds") or -110)
    date = row.get("date", "")
    season = _season_for_date(date)
    is_home = venue.startswith("h")

    pid = _resolve_player_id(name)
    if pid is None:
        return None
    prow = build_prediction_row(
        pid, opp, season, is_home=is_home, rest_days=2.0,
        gamelog_dir=gamelog_dir,
    )
    if prow is None:
        return None
    pred = predict_fn(stat, prow, model_dir)
    qint = quantile_fn(stat, prow, model_dir)
    if pred is None or qint is None:
        return None

    return {
        "date": date, "player": name, "stat": stat, "line": line,
        "actual": actual, "pred": pred, "qint": qint,
        "over_odds": over_odds, "under_odds": under_odds,
    }


def _decide_bet(scored: dict, threshold_edge: float = 0.0):
    """Pick the side with higher positive EV above `threshold_edge`.

    Returns (side, odds, prob, ev) or (None, ...) if no qualifying bet.
    Edge is computed in EV-per-dollar space — `threshold_edge` filters in
    the same units the caller controls in compare_to_lines.
    """
    stat = scored["stat"]; line = scored["line"]; pred = scored["pred"]
    qint = scored["qint"]
    p_over  = _model_hit_prob(stat, pred, qint, line, "OVER")
    p_under = _model_hit_prob(stat, pred, qint, line, "UNDER")
    if p_over is None or p_under is None:
        return (None, None, None, None)

    ev_over  = p_over  * _american_payout(scored["over_odds"])  - (1 - p_over)
    ev_under = p_under * _american_payout(scored["under_odds"]) - (1 - p_under)

    side = None; odds = None; prob = None; ev = None
    if ev_over >= ev_under and ev_over > threshold_edge:
        side, odds, prob, ev = "OVER",  scored["over_odds"],  p_over,  ev_over
    elif ev_under > ev_over and ev_under > threshold_edge:
        side, odds, prob, ev = "UNDER", scored["under_odds"], p_under, ev_under
    return (side, odds, prob, ev)


def _settle(side: str, line: float, actual: float, odds: int,
            stake: float) -> float:
    """Return P&L delta on this bet (NOT including stake — net profit)."""
    if actual == line:        # push
        return 0.0
    won = (actual > line) if side == "OVER" else (actual < line)
    return _american_payout(odds, stake) if won else -stake


# ---------- main loop ----------

def run_backtest(csv_path, *, threshold_edge=0.0, kelly=False, bankroll=1000.0,
                 gamelog_dir=None, model_dir=None,
                 predict_fn=None, quantile_fn=None,
                 progress=True):
    """Process the CSV and return the summary dict. Pure function — the CLI
    main() prints; tests call this and assert."""
    gamelog_dir = gamelog_dir or os.path.join(PROJECT_DIR, "data", "nba")
    model_dir   = model_dir   or os.path.join(PROJECT_DIR, "data", "models")

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    n_rows = len(rows)

    bets = []
    per_stat = defaultdict(lambda: {"n_bets": 0, "n_wins": 0, "pnl": 0.0})
    running_bankroll = bankroll
    peak = bankroll
    max_dd = 0.0
    total_pnl = 0.0
    n_bets = 0; n_wins = 0; n_push = 0

    for i, raw in enumerate(rows):
        if progress and (i % 50 == 0):
            print(f"  ... {i}/{n_rows}", flush=True)
        scored = _score_row(raw, gamelog_dir, model_dir,
                            predict_fn=predict_fn, quantile_fn=quantile_fn)
        if scored is None:
            continue
        side, odds, prob, ev = _decide_bet(scored, threshold_edge)
        if side is None:
            continue
        if kelly:
            kf = _kelly_fraction(prob, odds)
            stake = round(kf * running_bankroll, 2)
            if stake <= 0:
                continue
        else:
            stake = 1.0
        pnl = _settle(side, scored["line"], scored["actual"], odds, stake)
        total_pnl += pnl
        running_bankroll += pnl
        peak = max(peak, running_bankroll)
        dd = peak - running_bankroll
        if dd > max_dd:
            max_dd = dd
        n_bets += 1
        won = pnl > 0; push = (pnl == 0.0 and scored["actual"] == scored["line"])
        if won: n_wins += 1
        if push: n_push += 1
        ps = per_stat[scored["stat"]]
        ps["n_bets"] += 1
        ps["n_wins"] += int(won)
        ps["pnl"] += pnl
        bets.append({**scored, "side": side, "odds": odds, "prob": prob,
                     "stake": stake, "pnl": pnl})

    total_stake = sum(b["stake"] for b in bets)
    roi_pct = (100.0 * total_pnl / total_stake) if total_stake else 0.0
    selectivity = (100.0 * n_bets / n_rows) if n_rows else 0.0
    win_pct = (100.0 * n_wins / n_bets) if n_bets else 0.0

    return {
        "n_rows": n_rows, "n_bets": n_bets, "n_wins": n_wins,
        "n_push": n_push, "total_pnl": total_pnl,
        "total_stake": total_stake, "roi_pct": roi_pct,
        "win_pct": win_pct, "selectivity_pct": selectivity,
        "max_dd": max_dd, "final_bankroll": running_bankroll,
        "per_stat": dict(per_stat), "bets": bets,
    }


def print_summary(s: dict):
    print("\n== Historical backtest vs CLOSING LINES ==")
    print(f"Rows: {s['n_rows']}   |   Bets placed: {s['n_bets']}   |   "
          f"Selectivity: {s['selectivity_pct']:.1f}%")
    if s['n_bets']:
        print(f"Won: {s['n_wins']} / {s['n_bets']} = {s['win_pct']:.1f}%   |   "
              f"ROI: {s['roi_pct']:+.2f}%   |   Max DD: -${s['max_dd']:.2f}")
        print(f"Total P&L: {s['total_pnl']:+.2f}   |   "
              f"Final bankroll: ${s['final_bankroll']:.2f}")
        print("Per-stat breakdown:")
        for stat in STATS:
            ps = s["per_stat"].get(stat)
            if not ps or ps["n_bets"] == 0:
                continue
            hr = 100.0 * ps["n_wins"] / ps["n_bets"]
            # ROI per stat uses unit stake count as denominator approximation;
            # for Kelly the per-stat ROI is total stake -> tracked below.
            stake_stat = sum(b["stake"] for b in s["bets"]
                             if b["stat"] == stat)
            roi = (100.0 * ps["pnl"] / stake_stat) if stake_stat else 0.0
            print(f"  {stat.upper():4s} bets={ps['n_bets']:4d} "
                  f"hit={hr:5.1f}%  roi={roi:+6.2f}%  "
                  f"pnl={ps['pnl']:+.2f}")
    else:
        print("No bets passed the threshold-edge filter.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="historical lines CSV")
    ap.add_argument("--threshold-edge", type=float, default=0.0,
                    help="Only place bets where EV per dollar exceeds this "
                         "threshold. Default 0.0 (any positive-EV bet).")
    ap.add_argument("--kelly", action="store_true",
                    help="Stake using fractional Kelly instead of flat $1")
    ap.add_argument("--bankroll", type=float, default=1000.0,
                    help="Starting bankroll for Kelly sizing (default $1000)")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print(f"[fail] not found: {args.csv}"); sys.exit(1)
    s = run_backtest(
        args.csv,
        threshold_edge=args.threshold_edge,
        kelly=args.kelly,
        bankroll=args.bankroll,
    )
    print_summary(s)


if __name__ == "__main__":
    main()
