"""iter16_cv_filter_probe.py — CV-as-filter probe.

After iter-14/15 showed CV-as-features yields WASH at current 1.99% train coverage,
pivot: use per-player CV signals as a *post-hoc filter* on Strategy D bet recs.

For each BLK/FG3M/STL bet recommended by the baseline (iter-13/iter-14 pipeline):
    1. Look up the player's leak-safe CV prior (career mean of cvb_* before bet date).
    2. Apply candidate filters that REJECT bets matching a CV-derived pattern.
    3. Grid-search filter threshold (50/60/70/80th percentile of prior dist).
    4. Recompute hit% + ROI on remaining bets.

Coverage handling: bets with NO prior CV data are KEPT (filter has no opinion).

No production files / models touched. Reads iter-14 baseline artifacts +
oos_pre_playoffs models to regenerate per-bet recs for FG3M and STL.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.prediction.prop_quantiles import _inverse  # noqa: E402
from src.prediction.prop_pergame import feature_columns  # noqa: E402
from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row, _resolve_player_id, _season_for_date,
    _classify_result, _recommend, _odds_to_decimal_profit,
)

BASE_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "playoffs_2024_canonical.csv")
CV_PATH = os.path.join(PROJECT_DIR, "data", "player_cv_per_game.parquet")
THRESHOLD = 0.5

# Filters specified in the iter-16 brief (hypothesis-driven).
# Each: (filter_name, signal_col, direction_to_reject, side_to_reject)
# direction_to_reject = "high" => bets where prior > pct(p) are rejected
# side_to_reject = "UNDER" or "OVER" or "BOTH"
FILTERS_BY_STAT = {
    "blk": [
        # Paint dwellers should NOT be UNDER on BLK (more block opps)
        ("paint_time_high_rej_UNDER", "cvb_paint_time_pct", "high", "UNDER"),
        # Near-basket pct high -> reject UNDER on BLK
        ("near_basket_high_rej_UNDER", "cvb_near_basket_pct", "high", "UNDER"),
        # Avg dist to basket LOW -> player lives near rim -> reject UNDER
        ("dist_basket_low_rej_UNDER", "cvb_avg_dist_to_basket", "low", "UNDER"),
        # Jump frequency high -> reject UNDER
        ("jump_freq_high_rej_UNDER", "cvb_jump_frequency", "high", "UNDER"),
        # Contest arm high -> reject UNDER
        ("contest_arm_high_rej_UNDER", "cvb_contest_arm_mean", "high", "UNDER"),
    ],
    "fg3m": [
        # Off-ball distance high -> player gets open looks -> reject UNDER
        ("off_ball_high_rej_UNDER", "cvb_off_ball_dist", "high", "UNDER"),
        # Avg spacing high -> open team -> reject UNDER
        ("spacing_high_rej_UNDER", "cvb_avg_spacing", "high", "UNDER"),
        # Avg defender dist high -> open looks -> reject UNDER
        ("def_dist_high_rej_UNDER", "cvb_avg_defender_dist", "high", "UNDER"),
        # Avg dist to basket high -> perimeter player -> reject UNDER
        ("dist_basket_high_rej_UNDER", "cvb_avg_dist_to_basket", "high", "UNDER"),
        # Paint time pct low -> rarely paints -> perimeter -> reject UNDER
        ("paint_time_low_rej_UNDER", "cvb_paint_time_pct", "low", "UNDER"),
    ],
    "stl": [
        # Avg velocity high -> active -> more steal chances -> reject UNDER
        ("velocity_high_rej_UNDER", "cvb_avg_velocity", "high", "UNDER"),
        # Off-ball distance high -> active off-ball -> reject UNDER
        ("off_ball_high_rej_UNDER", "cvb_off_ball_dist", "high", "UNDER"),
        # Paint pressure opp high -> aggressive D -> reject UNDER
        ("paint_press_opp_high_rej_UNDER", "cvb_paint_pressure_opp", "high", "UNDER"),
        # Fatigue score low -> fresh -> active -> reject UNDER
        ("fatigue_low_rej_UNDER", "cvb_fatigue_score", "low", "UNDER"),
        # Dribbles per 100 high -> ball-handler -> reject UNDER
        ("dribbles_high_rej_UNDER", "cvb_dribbles_per100", "high", "UNDER"),
    ],
}

ALL_CV_FEATURES = [
    "cvb_avg_defender_dist", "cvb_avg_spacing", "cvb_off_ball_dist",
    "cvb_avg_velocity", "cvb_paint_pressure_own", "cvb_paint_pressure_opp",
    "cvb_fatigue_score", "cvb_paint_time_pct", "cvb_near_basket_pct",
    "cvb_avg_dist_to_basket", "cvb_jump_frequency", "cvb_contest_arm_mean",
    "cvb_dribbles_per100",
]

BASELINE_HEADLINE = {
    "blk":  {"n": 33,  "hit": 0.6970, "roi": 33.06},
    "fg3m": {"n": 231, "hit": 0.6450, "roi": 23.14},
    "stl":  {"n": 154, "hit": 0.7143, "roi": 36.36},
}


def load_gid_to_date():
    gid2date = {}
    for season in ("2021-22", "2022-23", "2023-24", "2024-25", "2025-26"):
        p = os.path.join(GAMELOG_DIR, f"season_games_{season}.json")
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        for r in d.get("rows", []):
            gid2date[str(r["game_id"])] = r["game_date"]
    return gid2date


def build_player_cv_priors(gid2date):
    """Return DataFrame keyed by (nba_player_id, date) with all cvb_* signals sorted."""
    cv = pd.read_parquet(CV_PATH)
    cv["date"] = cv["game_id"].astype(str).map(gid2date)
    cv = cv.dropna(subset=["date", "nba_player_id"]).copy()
    cv["nba_player_id"] = cv["nba_player_id"].astype(int)
    cv = cv.sort_values(["nba_player_id", "date"]).reset_index(drop=True)
    return cv


def lookup_player_prior(cv_df, pid, target_date, cols):
    """Return dict of leak-safe career-mean cvb_* signals for player pid prior to target_date."""
    sub = cv_df[(cv_df["nba_player_id"] == pid) & (cv_df["date"] < target_date)]
    if len(sub) == 0:
        return None
    return {c: float(sub[c].mean()) if sub[c].notna().any() else np.nan for c in cols}


def load_baseline_model(stat):
    import xgboost as xgb
    path = os.path.join(BASE_MODEL_DIR, f"quantile_pergame_{stat}_q50.json")
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def gen_baseline_bets(stat):
    """Re-run the baseline backtest for stat against playoffs_2024_canonical.csv.
    Returns list of bet dicts: {player, date, pid, line, actual, pred, edge, rec, outcome}.
    """
    cols_base = feature_columns()
    model = load_baseline_model(stat)
    rows_csv = []
    with open(CSV_PATH, encoding="utf-8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == stat:
                rows_csv.append(r)
    name2pid = {nm: _resolve_player_id(nm) for nm in sorted({r["player"] for r in rows_csv})}
    bets = []
    skip = defaultdict(int)
    for r in rows_csv:
        try:
            line = float(r["closing_line"]); actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_row"] += 1; continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skip["no_pid"] += 1; continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        feat = _build_asof_row(pid, r["opp"], d, season, is_home=is_home, rest_days=2.0, gamelog_dir=GAMELOG_DIR)
        if feat is None:
            skip["no_history"] += 1; continue
        X = np.array([[float(feat.get(c, 0.0) or 0.0) for c in cols_base]], dtype=float)
        try:
            pred_t = float(model.predict(X)[0])
            pred = max(0.0, float(_inverse(stat, np.array([pred_t]))[0]))
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1; continue
        edge = pred - line
        rec = _recommend(edge, THRESHOLD)
        if rec == "NO_BET":
            continue
        actual_result = _classify_result(actual, line)
        if actual_result == "PUSH":
            outcome = "PUSH"
        else:
            outcome = "WIN" if rec == actual_result else "LOSS"
        bets.append({
            "player": r["player"], "date": r["date"], "pid": pid,
            "line": line, "actual": actual, "pred": pred, "edge": edge,
            "rec": rec, "outcome": outcome,
        })
    return bets, dict(skip)


def attach_priors_to_bets(bets, cv_df, cols):
    """For each bet, attach prior CV dict (or None)."""
    by_player = defaultdict(list)
    for _, r in cv_df.iterrows():
        by_player[int(r["nba_player_id"])].append((r["date"], r))
    for pid in by_player:
        by_player[pid].sort(key=lambda x: x[0])

    out = []
    n_cov = 0
    for b in bets:
        pid = b["pid"]; date = b["date"]
        priors = None
        if pid in by_player:
            sub_rows = [x[1] for x in by_player[pid] if x[0] < date]
            if sub_rows:
                sub_df = pd.DataFrame(sub_rows)
                priors = {c: (float(sub_df[c].mean()) if sub_df[c].notna().any() else np.nan) for c in cols}
                if any(not (isinstance(v, float) and np.isnan(v)) for v in priors.values()):
                    n_cov += 1
        bcopy = dict(b)
        bcopy["priors"] = priors
        out.append(bcopy)
    return out, n_cov


def hit_roi(bets):
    """Compute hit% & ROI @ -110 (drop PUSH from denominator)."""
    nb = 0; w = 0
    for b in bets:
        if b["outcome"] == "PUSH":
            continue
        nb += 1
        if b["outcome"] == "WIN":
            w += 1
    if nb == 0:
        return 0, 0.0, 0.0, 0.0
    profit = _odds_to_decimal_profit(-110)
    roi_u = w * profit - (nb - w) * 1.0
    return nb, w / nb, roi_u / nb * 100.0, roi_u


def apply_filter(bets, signal, direction, side, threshold_value):
    """Drop bets whose rec == side AND priors[signal] passes the threshold test.
    Keep bets where priors is None or signal is NaN (filter has no opinion).
    Returns (kept_bets, n_dropped).
    """
    kept = []
    dropped = 0
    for b in bets:
        if b["rec"] != side:
            kept.append(b); continue
        p = b.get("priors")
        if p is None:
            kept.append(b); continue
        v = p.get(signal)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            kept.append(b); continue
        if direction == "high" and v >= threshold_value:
            dropped += 1
        elif direction == "low" and v <= threshold_value:
            dropped += 1
        else:
            kept.append(b)
    return kept, dropped


def main():
    t_start = time.time()
    print("iter-16 CV-as-filter probe")
    print("=" * 70)
    gid2date = load_gid_to_date()
    cv_df = build_player_cv_priors(gid2date)
    print(f"CV per-game rows: {len(cv_df)}")
    print(f"Distinct CV players: {cv_df['nba_player_id'].nunique()}")
    print()

    all_results = []
    coverage_report = {}
    bets_by_stat = {}

    for stat in ("blk", "fg3m", "stl"):
        print(f"\n===== {stat.upper()} =====")
        t0 = time.time()
        bets, skip = gen_baseline_bets(stat)
        print(f"  Baseline bets generated: {len(bets)} ({time.time()-t0:.1f}s) skip={skip}")
        bets, n_cov = attach_priors_to_bets(bets, cv_df, ALL_CV_FEATURES)
        bets_by_stat[stat] = bets
        coverage_report[stat] = {"n_bets": len(bets), "n_with_prior": n_cov}
        nb, hit, roi, _ = hit_roi(bets)
        print(f"  Baseline (recomputed): n={nb} hit={hit*100:.2f}% ROI={roi:+.2f}%")
        print(f"  CV prior coverage: {n_cov}/{len(bets)} ({n_cov/max(1,len(bets))*100:.1f}%)")

        # Grid search per filter
        filters = FILTERS_BY_STAT[stat]
        rows = []
        for fname, signal, direction, side in filters:
            # Compute percentile thresholds from the population of priors for this signal
            sig_vals = [b["priors"][signal] for b in bets
                        if b.get("priors") and signal in b["priors"]
                        and not (isinstance(b["priors"][signal], float) and np.isnan(b["priors"][signal]))]
            if len(sig_vals) < 5:
                continue
            for pct in (50, 60, 70, 80):
                thr = float(np.percentile(sig_vals, pct))
                kept, dropped = apply_filter(bets, signal, direction, side, thr)
                if dropped < 1:
                    continue
                nb2, hit2, roi2, _ = hit_roi(kept)
                d_hit = (hit2 - hit) * 100
                d_roi = roi2 - roi
                rows.append({
                    "stat": stat, "filter": fname, "signal": signal,
                    "direction": direction, "side": side, "pct": pct, "threshold": thr,
                    "n_dropped": dropped, "n_remaining": nb2,
                    "hit_pct": hit2 * 100, "roi_pct": roi2,
                    "d_hit_pp": d_hit, "d_roi_pp": d_roi,
                })
        rows.sort(key=lambda r: (r["d_hit_pp"], r["d_roi_pp"]), reverse=True)
        all_results.append({"stat": stat, "baseline_hit": hit * 100, "baseline_roi": roi, "rows": rows})

        # Print top of grid
        print(f"\n  {stat.upper()} grid (top 10 by d_hit):")
        print(f"  {'filter':<35} {'pct':>4} {'drop':>5} {'rem':>5} {'hit%':>6} {'ROI%':>7} {'d_hit':>7} {'d_ROI':>7}")
        for r in rows[:10]:
            print(f"  {r['filter']:<35} {r['pct']:>4} {r['n_dropped']:>5} {r['n_remaining']:>5} "
                  f"{r['hit_pct']:>6.2f} {r['roi_pct']:>+7.2f} {r['d_hit_pp']:>+7.2f} {r['d_roi_pp']:>+7.2f}")

    # Pick best winning filter per stat (must drop >=10, improve hit, not regress ROI by >1pp)
    winners = {}
    print("\n\n===== WINNING FILTERS PER STAT =====")
    for res in all_results:
        stat = res["stat"]
        candidates = [r for r in res["rows"] if r["n_dropped"] >= 10
                      and r["d_hit_pp"] > 0 and r["d_roi_pp"] > -1.0]
        if not candidates:
            print(f"  {stat.upper()}: NO winning filter")
            continue
        # Best by Δhit then Δroi
        best = max(candidates, key=lambda r: (r["d_hit_pp"], r["d_roi_pp"]))
        winners[stat] = best
        print(f"  {stat.upper()}: {best['filter']} pct{best['pct']} thr={best['threshold']:.3f} "
              f"drop={best['n_dropped']} rem={best['n_remaining']} "
              f"hit {best['hit_pct']:.2f}% (Δ{best['d_hit_pp']:+.2f}pp) "
              f"ROI {best['roi_pct']:+.2f}% (Δ{best['d_roi_pp']:+.2f}pp)")

    # Apply stacked filters to combined Strategy D bet set
    print("\n===== STACKED FILTERS ON COMBINED STRATEGY D BET SET =====")
    combined = []
    for stat in ("blk", "fg3m", "stl"):
        for b in bets_by_stat[stat]:
            b2 = dict(b); b2["stat"] = stat
            combined.append(b2)
    # Baseline combined
    nb_c, hit_c, roi_c, units_c = hit_roi(combined)
    pnl_c = units_c * 100.0  # flat $100
    print(f"  Combined baseline (BLK+FG3M+STL only): n={nb_c} hit={hit_c*100:.2f}% "
          f"ROI={roi_c:+.2f}% PnL@$100={pnl_c:+.2f}")

    # Apply each winning filter
    stacked = list(combined)
    total_dropped = 0
    for stat, w in winners.items():
        prev = [b for b in stacked if b["stat"] == stat]
        kept_stat, dropped_n = apply_filter(prev, w["signal"], w["direction"], w["side"], w["threshold"])
        other = [b for b in stacked if b["stat"] != stat]
        stacked = other + kept_stat
        total_dropped += dropped_n
        print(f"  Applied {stat.upper()} filter ({w['filter']}): dropped {dropped_n}, remaining {len(stacked)}")
    nb_s, hit_s, roi_s, units_s = hit_roi(stacked)
    pnl_s = units_s * 100.0
    print(f"\n  STACKED: n={nb_s} hit={hit_s*100:.2f}% ROI={roi_s:+.2f}% PnL@$100={pnl_s:+.2f}")
    print(f"  d_hit={(hit_s-hit_c)*100:+.2f}pp  d_ROI={roi_s-roi_c:+.2f}pp  d_PnL={pnl_s-pnl_c:+.2f}")

    # Compare to iter-10 strategy D baseline of 418b / +28.80% ROI / +$12,036
    print(f"\n  Note iter-10 Strategy D headline: 418 bets, +28.80% ROI, +$12,036.")
    print(f"  This probe only re-runs BLK+FG3M+STL ({nb_c} of 418); other stats unchanged.")

    # Save full output
    out_dir = os.path.join(PROJECT_DIR, "data", "models", "oos_cv_filter")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "iter16_filter_grid.json")
    payload = {
        "generated_at": datetime.now().isoformat(),
        "elapsed_s": time.time() - t_start,
        "coverage": coverage_report,
        "results": [
            {"stat": r["stat"], "baseline_hit": r["baseline_hit"], "baseline_roi": r["baseline_roi"],
             "grid": r["rows"]} for r in all_results
        ],
        "winners": winners,
        "stacked": {
            "n_baseline": nb_c, "hit_baseline": hit_c * 100, "roi_baseline": roi_c,
            "pnl_baseline": pnl_c,
            "n_stacked": nb_s, "hit_stacked": hit_s * 100, "roi_stacked": roi_s,
            "pnl_stacked": pnl_s,
            "delta_hit_pp": (hit_s - hit_c) * 100, "delta_roi_pp": roi_s - roi_c,
            "delta_pnl": pnl_s - pnl_c,
            "total_dropped": total_dropped,
        },
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"\nSaved -> {out_path}")
    print(f"Total elapsed: {time.time()-t_start:.1f}s")


if __name__ == "__main__":
    main()
