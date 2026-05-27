"""iter34_isotonic_edge_calibration.py — Per-stat isotonic edge calibration.

Iter-21 linear-shrinkage analysis found slopes 0.21-0.68 (model overconfident).
Linear shrinkage REVERTed. This iteration fits a non-parametric IsotonicRegression
on (predicted_edge, actual_margin) pairs to capture the non-linear edge→margin map.

Method:
  Training:
    - FG3M/STL/BLK: load from iter23_preds.json (2024 playoffs, 2411 rows).
    - PTS/REB/AST:  generate fresh predictions on 2024 playoffs canonical CSV.
      Each stat uses predict_pergame() with _build_asof_row() features.

  Fit:
    - sklearn IsotonicRegression(increasing=True) per stat.
    - Fitted on 80% of training data (temporal split: chronological first 80%).
    - Cross-validated on remaining 20% of 2024 playoffs (internal check).

  Eval:
    - Apply isotonic to per-bet edge values in the iter33 simulation framework.
    - Bet accepted when calibrated_edge >= threshold (same thresholds as iter-25).
    - Kelly-B sizing on calibrated edge.
    - Compare aggregate ROI vs iter-33 baseline (+22.03%).

  Ship criterion: aggregate ROI improves >= +0.5pp AND <= 1 stat regression.

Output:
    data/cache/iter34_isotonic_backtest.json
    data/models/oos_pre_playoffs/edge_isotonic_<stat>.joblib  (per-stat)

Usage:
    python scripts/iter34_isotonic_edge_calibration.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# ── Paths ─────────────────────────────────────────────────────────────────────

LINES_DIR       = os.path.join(PROJECT_DIR, "data", "external", "historical_lines")
GAMELOG_DIR     = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR         = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
CACHE_DIR       = os.path.join(PROJECT_DIR, "data", "cache")
BASELINE_JSON   = os.path.join(CACHE_DIR, "holdout_baseline.json")
ITER33_JSON     = os.path.join(CACHE_DIR, "iter33_kelly_backtest.json")
ITER23_PREDS    = os.path.join(CACHE_DIR, "iter23_preds.json")
PO2024_CSV      = os.path.join(LINES_DIR, "playoffs_2024_canonical.csv")
OUTPUT_JSON     = os.path.join(CACHE_DIR, "iter34_isotonic_backtest.json")
ISO_MODEL_DIR   = OOS_DIR

ALL_STATS  = ["pts", "reb", "ast", "fg3m", "stl", "blk"]
ITER23_STATS = {"fg3m", "stl", "blk"}   # available in iter23_preds.json
GEN_STATS    = {"pts", "reb", "ast"}    # need fresh predictions

# iter-25 thresholds (production)
THRESHOLDS: Dict[str, float] = {
    "pts": 0.7, "reb": 1.5, "ast": 1.0,
    "fg3m": 0.7, "stl": 0.4, "blk": 0.4,
}

# iter-33 Kelly-B params
KELLY_FRAC_B    = 0.25
MAX_STAKE_U     = 3.0
PAYOUT_M110     = 100.0 / 110.0   # ≈ 0.9091

SHIP_DELTA_PP   = 0.5              # aggregate ROI lift required
MAX_REGRESSIONS = 1                # max per-stat regressions allowed


# ── Helpers ───────────────────────────────────────────────────────────────────

def _odds_to_profit(odds: int = -110) -> float:
    """Decimal profit per 1u at given American odds."""
    if odds < 0:
        return 100.0 / abs(odds)
    return odds / 100.0


PROFIT_FLAT = _odds_to_profit(-110)


# ── Step 1: Load iter23_preds for FG3M/STL/BLK ───────────────────────────────

def load_iter23_training(stats=ITER23_STATS) -> Dict[str, List[dict]]:
    """Load (edge, margin) pairs from iter23_preds.json for FG3M/STL/BLK."""
    with open(ITER23_PREDS, encoding="utf-8") as f:
        preds = json.load(f)

    by_stat: Dict[str, List[dict]] = defaultdict(list)
    for r in preds:
        stat = r.get("stat", "").lower()
        if stat not in stats:
            continue
        edge = float(r["edge_signed"])   # pred - line (signed, absolute units)
        actual = float(r["actual"])
        line = float(r["line"])
        margin = actual - line           # positive = went over

        # Skip pushes
        if abs(actual - line) < 1e-6:
            continue

        by_stat[stat].append({
            "date":   r["date"],
            "player": r["player"],
            "edge":   edge,
            "margin": margin,
            "line":   line,
        })

    for stat, rows in by_stat.items():
        rows.sort(key=lambda x: x["date"])
        print(f"  [iter23] {stat}: {len(rows)} training pairs loaded")
    return dict(by_stat)


# ── Step 2: Generate predictions for PTS/REB/AST on 2024 playoffs ─────────────

def generate_pts_reb_ast_training() -> Dict[str, List[dict]]:
    """Generate (edge, margin) pairs for PTS/REB/AST via predict_pergame()."""
    from scripts.backtest_closing_lines_2024_playoffs import (
        _build_asof_row,
        _resolve_player_id,
        _season_for_date,
    )
    from src.prediction.prop_pergame import predict_pergame

    gen_stats = list(GEN_STATS)
    by_stat: Dict[str, List[dict]] = defaultdict(list)

    # Load 2024 playoffs rows for PTS/REB/AST
    rows = []
    with open(PO2024_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["stat"].lower() in gen_stats:
                rows.append(r)
    print(f"  [gen] loaded {len(rows)} rows from 2024 playoffs for {gen_stats}")

    # Resolve player IDs (unique names first)
    unique_names = sorted({r["player"] for r in rows})
    name2pid = {}
    t0 = time.time()
    for nm in unique_names:
        name2pid[nm] = _resolve_player_id(nm)
    resolved = sum(1 for v in name2pid.values() if v)
    print(f"  [gen] resolved {resolved}/{len(unique_names)} players in {time.time()-t0:.1f}s")

    # Build feature rows with caching on player-date-venue-opp key
    feat_cache: dict = {}
    skip_counts: dict = defaultdict(int)
    processed = 0
    t_start = time.time()

    for idx, r in enumerate(rows):
        stat = r["stat"].lower()
        player = r["player"]
        pid = name2pid.get(player)
        if pid is None:
            skip_counts["no_pid"] += 1
            continue

        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
        except (TypeError, ValueError):
            skip_counts["bad_numeric"] += 1
            continue

        # Skip pushes
        if abs(actual - line) < 1e-6:
            skip_counts["push"] += 1
            continue

        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip_counts["bad_date"] += 1
            continue

        opp = r["opp"]
        venue = r.get("venue", "home")
        is_home = venue == "home"
        season = _season_for_date(d)

        # Cache key = (pid, date, venue, opp) — per-player-date-matchup
        feat_key = (pid, r["date"], venue, opp)
        if feat_key not in feat_cache:
            feat = _build_asof_row(
                pid, opp, d, season, is_home=is_home,
                rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
            feat_cache[feat_key] = feat
        feat = feat_cache[feat_key]

        if feat is None:
            skip_counts["no_history"] += 1
            continue

        try:
            pred = predict_pergame(stat, feat)
        except Exception:
            skip_counts["predict_err"] += 1
            continue

        if pred is None:
            skip_counts["no_model"] += 1
            continue

        pred = float(pred)
        edge = pred - line
        margin = actual - line

        by_stat[stat].append({
            "date":   r["date"],
            "player": player,
            "edge":   edge,
            "margin": margin,
            "line":   line,
        })
        processed += 1

        if (idx + 1) % 200 == 0:
            elapsed = time.time() - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            print(f"  [gen] {idx+1}/{len(rows)} rows "
                  f"({processed} predictions, {rate:.1f}/s, "
                  f"{elapsed/60:.1f}min)")

    elapsed = time.time() - t_start
    print(f"  [gen] done: {processed} predictions in {elapsed:.1f}s ({elapsed/60:.1f}min)")
    print(f"  [gen] skipped: {dict(skip_counts)}")

    for stat in gen_stats:
        rows_s = by_stat.get(stat, [])
        if rows_s:
            rows_s.sort(key=lambda x: x["date"])
        print(f"  [gen] {stat}: {len(rows_s)} training pairs")

    return dict(by_stat)


# ── Step 3: Fit IsotonicRegression per stat ───────────────────────────────────

def fit_isotonic_models(
    train_data: Dict[str, List[dict]],
) -> Dict[str, object]:
    """Fit IsotonicRegression(increasing=True) on (edge, margin) pairs per stat.

    Returns dict of {stat: fitted_model}.
    """
    from sklearn.isotonic import IsotonicRegression

    models = {}
    for stat in ALL_STATS:
        rows = train_data.get(stat, [])
        if len(rows) < 20:
            print(f"  [fit] {stat}: too few rows ({len(rows)}) — skipping")
            continue

        edges = np.array([r["edge"] for r in rows], dtype=float)
        margins = np.array([r["margin"] for r in rows], dtype=float)

        # IsotonicRegression: calibrated edge = f(raw_edge)
        # We fit on ALL training data first, then save.
        # For the threshold gate, the calibrated edge replaces the raw edge.
        ir = IsotonicRegression(increasing=True, out_of_bounds="clip")
        ir.fit(edges, margins)
        models[stat] = ir

        # Summary stats: what does edge=threshold map to?
        thr = THRESHOLDS.get(stat, 0.5)
        cal_at_thr = float(ir.predict([thr])[0])
        cal_at_2thr = float(ir.predict([2 * thr])[0])
        cal_at_3thr = float(ir.predict([3 * thr])[0])

        # Quick linear slope check (for comparison with iter21)
        if np.var(edges) > 1e-9:
            ols_slope = float(np.dot(edges, margins) / np.dot(edges, edges))
        else:
            ols_slope = 0.0

        print(f"  [fit] {stat}: n={len(rows)}  OLS_slope={ols_slope:.3f}  "
              f"iso(thr={thr})={cal_at_thr:.3f}  "
              f"iso({2*thr:.1f})={cal_at_2thr:.3f}  "
              f"iso({3*thr:.1f})={cal_at_3thr:.3f}")

    return models


# ── Step 4: Cross-validate on internal 20% holdout ───────────────────────────

def cv_isotonic(
    train_data: Dict[str, List[dict]],
) -> Dict[str, dict]:
    """Fit isotonic on first 80% of training data, evaluate on last 20%.

    Returns CV metrics per stat for logging.
    """
    from sklearn.isotonic import IsotonicRegression

    cv_results = {}
    for stat in ALL_STATS:
        rows = train_data.get(stat, [])
        if len(rows) < 30:
            cv_results[stat] = {"skip": True, "n": len(rows)}
            continue

        n_train = int(len(rows) * 0.80)
        fit_rows  = rows[:n_train]
        hold_rows = rows[n_train:]

        e_fit  = np.array([r["edge"]   for r in fit_rows],  dtype=float)
        m_fit  = np.array([r["margin"] for r in fit_rows],  dtype=float)
        e_hold = np.array([r["edge"]   for r in hold_rows], dtype=float)
        m_hold = np.array([r["margin"] for r in hold_rows], dtype=float)

        ir = IsotonicRegression(increasing=True, out_of_bounds="clip")
        ir.fit(e_fit, m_fit)

        cal_edges_hold = ir.predict(e_hold)
        raw_mae  = float(np.mean(np.abs(e_hold - m_hold)))
        cal_mae  = float(np.mean(np.abs(cal_edges_hold - m_hold)))
        delta    = raw_mae - cal_mae   # positive = calibrated is better predictor of margin

        # ROI simulation on holdout: bet when calibrated_edge >= threshold
        thr = THRESHOLDS.get(stat, 0.5)
        bets = wins = 0
        for i, (ce, mg) in enumerate(zip(cal_edges_hold, m_hold)):
            raw_e = e_hold[i]
            # Threshold applied on CALIBRATED edge:
            if abs(ce) < thr:
                continue
            direction = "over" if ce > 0 else "under"
            bets += 1
            if direction == "over" and mg > 0:
                wins += 1
            elif direction == "under" and mg < 0:
                wins += 1

        roi_iso = ((wins * PROFIT_FLAT - (bets - wins)) / bets * 100
                   if bets > 0 else 0.0)

        # Baseline: raw edge threshold
        bets_raw = wins_raw = 0
        for i, (re, mg) in enumerate(zip(e_hold, m_hold)):
            if abs(re) < thr:
                continue
            direction = "over" if re > 0 else "under"
            bets_raw += 1
            if direction == "over" and mg > 0:
                wins_raw += 1
            elif direction == "under" and mg < 0:
                wins_raw += 1
        roi_raw = ((wins_raw * PROFIT_FLAT - (bets_raw - wins_raw)) / bets_raw * 100
                   if bets_raw > 0 else 0.0)

        cv_results[stat] = {
            "n_fit":   n_train,
            "n_hold":  len(hold_rows),
            "raw_mae": round(raw_mae, 4),
            "cal_mae": round(cal_mae, 4),
            "delta_mae": round(delta, 4),
            "cv_roi_raw": round(roi_raw, 2),
            "cv_roi_iso": round(roi_iso, 2),
            "cv_delta_roi": round(roi_iso - roi_raw, 2),
            "n_bets_raw": bets_raw,
            "n_bets_iso": bets,
        }
        sign = "+" if delta >= 0 else ""
        print(f"  [cv]  {stat}: MAE {sign}{delta:.4f}  "
              f"roi_raw={roi_raw:+.1f}% ({bets_raw}b)  "
              f"roi_iso={roi_iso:+.1f}% ({bets}b)  "
              f"delta={roi_iso-roi_raw:+.1f}pp")

    return cv_results


# ── Step 5: Save isotonic models ──────────────────────────────────────────────

def save_isotonic_models(models: Dict[str, object]) -> List[str]:
    """Save fitted isotonic models to disk. Returns list of saved paths."""
    import joblib
    saved = []
    os.makedirs(ISO_MODEL_DIR, exist_ok=True)
    for stat, model in models.items():
        path = os.path.join(ISO_MODEL_DIR, f"edge_isotonic_{stat}.joblib")
        joblib.dump(model, path)
        saved.append(path)
        print(f"  [save] {path}")
    return saved


# ── Step 6: Apply isotonic to iter33 simulation and recompute ROI ─────────────

def apply_isotonic_to_iter33(models: Dict[str, object]) -> dict:
    """Re-run the iter33 simulation with isotonic-calibrated edges.

    The iter33 simulation:
    - Reconstructs per-bet edge distributions from edge_history (empirical CDFs)
    - Assigns outcomes matching actual production hit rates
    - Computes flat-1u and Kelly-B ROI

    We replace: raw_edge → iso_calibrated_edge for both threshold gating
    and Kelly-B stake sizing. Outcome distribution is PRESERVED (same wins/losses).
    """
    # Load iter33 params
    with open(ITER33_JSON, encoding="utf-8") as f:
        iter33 = json.load(f)
    with open(BASELINE_JSON, encoding="utf-8") as f:
        baseline = json.load(f)

    baseline_g = baseline["__global__"]
    payout_b = PAYOUT_M110

    # Derive wins/losses per stat from holdout_baseline (same as iter33 does)
    def _derive_wins_losses(n: int, roi_units: float):
        wins_f = (roi_units + n) / (payout_b + 1.0)
        return int(round(wins_f)), n - int(round(wins_f))

    # Load edge history for empirical edge distributions
    edge_hist_path = os.path.join(PROJECT_DIR, "data", "models",
                                   "prop_residuals_edge_history.json")
    if os.path.exists(edge_hist_path):
        with open(edge_hist_path, encoding="utf-8") as f:
            hist_raw = json.load(f)
        edge_hist: Dict[str, List[float]] = defaultdict(list)
        for r in hist_raw:
            ep = abs(float(r.get("edge_pct", 0.0) or 0.0))
            if ep > 0:
                edge_hist[r["stat"]].append(ep)
        edge_hist = dict(edge_hist)
    else:
        edge_hist = {}

    prod_stats_list = sorted(baseline_g.keys())
    rng = np.random.default_rng(42)   # same seed as iter33

    # ── Reproduce iter33's edge generation ────────────────────────────────────
    def _mean_above_thr(stat, thr):
        raw = edge_hist.get(stat, [])
        if len(raw) >= 50:
            arr = np.array(sorted(raw))
            cut = int(len(arr) * 0.70)
            above = arr[cut:]
            if len(above) > 0:
                return float(np.mean(above))
        return thr + 0.5

    def _build_edges(n, stat, thr, mean_target):
        raw = edge_hist.get(stat, [])
        if len(raw) >= 50:
            arr = np.array(sorted(raw))
            cut = int(len(arr) * 0.70)
            above = arr[cut:] if cut < len(arr) else arr
            emp_mean = float(np.mean(above)) if len(above) > 0 else 1.0
            scale = mean_target / max(emp_mean, 1e-6)
            idx = rng.integers(0, len(above), size=n)
            edges = above[idx] * scale
        else:
            lam = 1.0 / max(mean_target - thr, 0.1)
            edges = thr + rng.exponential(1.0 / lam, size=n)
        return np.clip(edges, thr + 1e-6, None).astype(float)

    def _edge_to_p_win(edge_abs, thr, baseline_hit):
        frac = min(1.0, max(0.0, (edge_abs - thr) / max(thr * 2.0, 0.1)))
        p_hi = min(0.85, baseline_hit + 0.08)
        return min(0.90, max(0.50, baseline_hit + frac * (p_hi - baseline_hit)))

    # Accumulate results per strategy
    stat_flat     = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})
    stat_iso_flat = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})
    stat_iso_kb   = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})

    iso_curve_summary = {}

    # Additional accumulators for Choice B (raw threshold, iso Kelly sizing)
    stat_iso_kb_b = defaultdict(lambda: {"pnl": 0.0, "stake": 0.0, "n": 0, "wins": 0})

    for stat in prod_stats_list:
        sv = baseline_g[stat]
        n = sv["n_bets"]
        roi_units = sv["roi_units"]
        wins, losses = _derive_wins_losses(n, roi_units)
        hit = wins / n if n > 0 else 0.52
        thr = THRESHOLDS.get(stat, 0.5)
        mean_e = _mean_above_thr(stat, thr)

        # Generate edges (same algorithm as iter33, same rng state)
        edges = _build_edges(n, stat, thr, mean_e)
        rng.shuffle(edges)

        # Generate outcomes (same as iter33)
        outcomes = np.array(["win"] * wins + ["loss"] * losses)
        rng.shuffle(outcomes)

        # Isotonic model for this stat
        iso_model = models.get(stat)

        # Curve summary: what does the model predict at key edge values?
        if iso_model is not None:
            key_edges = [thr, thr * 1.5, thr * 2.0, thr * 3.0]
            cal_vals = iso_model.predict(key_edges)
            iso_curve_summary[stat] = {
                f"edge={e:.2f}": round(float(c), 4)
                for e, c in zip(key_edges, cal_vals)
            }
        else:
            iso_curve_summary[stat] = {"note": "no model (identity)"}

        for i in range(n):
            raw_edge = float(edges[i])
            outcome  = str(outcomes[i])

            # ── FLAT (baseline, same as iter33 flat, for cross-check) ──────
            pnl_flat = payout_b if outcome == "win" else -1.0
            stat_flat[stat]["pnl"]   += pnl_flat
            stat_flat[stat]["stake"] += 1.0
            stat_flat[stat]["n"]     += 1
            if outcome == "win":
                stat_flat[stat]["wins"] += 1

            # Compute calibrated edge once
            if iso_model is not None:
                cal_edge = float(iso_model.predict([raw_edge])[0])
            else:
                cal_edge = raw_edge

            # ── CHOICE A: threshold on CALIBRATED edge, flat 1u ──────────
            # (stringent filter: only bets where model uncertainty is well-calibrated)
            if abs(cal_edge) >= thr:
                pnl_iso_f = payout_b if outcome == "win" else -1.0
                stat_iso_flat[stat]["pnl"]   += pnl_iso_f
                stat_iso_flat[stat]["stake"] += 1.0
                stat_iso_flat[stat]["n"]     += 1
                if outcome == "win":
                    stat_iso_flat[stat]["wins"] += 1

            # ── CHOICE A: threshold on CALIBRATED edge + Kelly-B sizing ────
            if abs(cal_edge) >= thr:
                p_win  = _edge_to_p_win(abs(cal_edge), thr, hit)
                q      = 1.0 - p_win
                full_k = (p_win * payout_b - q) / payout_b
                if full_k > 0:
                    stake_b = min(KELLY_FRAC_B * full_k, MAX_STAKE_U)
                    pnl_iso_k = stake_b * payout_b if outcome == "win" else -stake_b
                    stat_iso_kb[stat]["pnl"]   += pnl_iso_k
                    stat_iso_kb[stat]["stake"] += stake_b
                    stat_iso_kb[stat]["n"]     += 1
                    if outcome == "win":
                        stat_iso_kb[stat]["wins"] += 1

            # ── CHOICE B: RAW threshold (same n_bets), iso for Kelly sizing ─
            # Same bet selection as iter33, calibrated stake via iso(raw_edge).
            # p_win is informed by calibrated edge (better size accuracy).
            p_win_b  = _edge_to_p_win(abs(cal_edge), thr, hit)
            q_b      = 1.0 - p_win_b
            full_k_b = (p_win_b * payout_b - q_b) / payout_b
            if full_k_b > 0:
                stake_b2 = min(KELLY_FRAC_B * full_k_b, MAX_STAKE_U)
            else:
                stake_b2 = 0.0
            # Always include this bet (raw threshold already passed since all
            # simulated edges are above threshold by construction)
            pnl_kb_b = stake_b2 * payout_b if outcome == "win" else -stake_b2
            stat_iso_kb_b[stat]["pnl"]   += pnl_kb_b
            stat_iso_kb_b[stat]["stake"] += max(stake_b2, 1e-9)
            stat_iso_kb_b[stat]["n"]     += 1
            if outcome == "win":
                stat_iso_kb_b[stat]["wins"] += 1

    # ── Summaries ──────────────────────────────────────────────────────────────

    def _summarize(sv):
        per_stat = {}
        tot_pnl = tot_stake = 0.0
        for stat, d in sv.items():
            roi = d["pnl"] / d["stake"] * 100 if d["stake"] > 0 else 0.0
            per_stat[stat] = {
                "n": d["n"],
                "pnl": round(d["pnl"], 4),
                "stake": round(d["stake"], 4),
                "wins": d["wins"],
                "roi_pct": round(roi, 2),
            }
            tot_pnl   += d["pnl"]
            tot_stake += d["stake"]
        agg = tot_pnl / tot_stake * 100 if tot_stake > 0 else 0.0
        return {"per_stat": per_stat,
                "total_pnl": round(tot_pnl, 4),
                "total_stake": round(tot_stake, 4),
                "agg_roi_pct": round(agg, 2)}

    flat_s      = _summarize(stat_flat)
    iso_f_s     = _summarize(stat_iso_flat)
    iso_kb_s    = _summarize(stat_iso_kb)
    iso_kb_b_s  = _summarize(stat_iso_kb_b)

    # iter33 baseline values (Kelly-B)
    iter33_kb_roi   = iter33["kelly_b"]["agg_roi_pct"]
    iter33_flat_roi = iter33["flat"]["agg_roi_pct"]

    # Our flat should match iter33's flat within ~1pp
    sim_flat_roi = flat_s["agg_roi_pct"]
    flat_drift   = abs(sim_flat_roi - iter33_flat_roi)

    # Decisions vs iter33 Kelly-B (+22.03%)
    prod_baseline_roi = iter33_kb_roi   # 22.03%

    def _decide(variant_s, description=""):
        delta = variant_s["agg_roi_pct"] - prod_baseline_roi
        regressions = 0
        iter33_kb_per_stat = iter33["kelly_b"]["per_stat"]
        for stat in prod_stats_list:
            base_roi = iter33_kb_per_stat.get(stat, {}).get("roi_pct", 0.0)
            var_roi  = variant_s["per_stat"].get(stat, {}).get("roi_pct", 0.0)
            # For n=0 (all bets filtered), treat as -100% regression
            if variant_s["per_stat"].get(stat, {}).get("n", 0) == 0:
                regressions += 1
            elif base_roi - var_roi > 1.0:
                regressions += 1
        if delta >= SHIP_DELTA_PP and regressions <= MAX_REGRESSIONS:
            dec = "SHIP"
        elif delta < -SHIP_DELTA_PP or regressions >= 2:
            dec = "REVERT"
        else:
            dec = "INCONCLUSIVE"
        return dec, round(delta, 4), regressions

    dec_iso_f,   delta_iso_f,   reg_iso_f   = _decide(iso_f_s,    "ChoiceA-Flat")
    dec_iso_kb,  delta_iso_kb,  reg_iso_kb  = _decide(iso_kb_s,   "ChoiceA-KB")
    dec_iso_kb_b, delta_iso_kb_b, reg_iso_kb_b = _decide(iso_kb_b_s, "ChoiceB-KB")

    # Primary decision: Choice B (raw threshold, iso Kelly sizing)
    # This is the fairer comparison — same bet selection as iter33, better stake accuracy
    primary_dec   = dec_iso_kb_b
    primary_delta = delta_iso_kb_b
    primary_reg   = reg_iso_kb_b

    # Print results table
    print("\n" + "=" * 80)
    print("  ITER-34 ISOTONIC EDGE CALIBRATION -- RESULTS")
    print("=" * 80)
    print(f"  Baseline (iter33 Kelly-B): {prod_baseline_roi:+.2f}%")
    print(f"  Sim flat cross-check:      {sim_flat_roi:+.2f}% (iter33 flat={iter33_flat_roi:+.2f}%, drift={flat_drift:.2f}pp)")
    print()
    print(f"  {'Stat':<6} {'N_base':>6}  {'Base%':>8}  {'ChoiceA-Flat%':>14}  "
          f"{'ChoiceA-KB%':>12}  {'ChoiceB-KB%':>12}  {'dA':>6}  {'dB':>6}")
    print("  " + "-" * 84)

    iter33_kb_per = iter33["kelly_b"]["per_stat"]
    for stat in sorted(prod_stats_list):
        base_r  = iter33_kb_per.get(stat, {}).get("roi_pct", 0.0)
        iso_f   = iso_f_s["per_stat"].get(stat, {})
        iso_kb  = iso_kb_s["per_stat"].get(stat, {})
        iso_kbb = iso_kb_b_s["per_stat"].get(stat, {})
        d_a     = iso_kb.get("roi_pct", 0.0)  - base_r
        d_b     = iso_kbb.get("roi_pct", 0.0) - base_r
        n_base  = iter33_kb_per.get(stat, {}).get("n", 0)
        n_a     = iso_kb.get("n", 0)
        n_b     = iso_kbb.get("n", 0)
        print(f"  {stat:<6} {n_base:>6}  "
              f"{base_r:>+7.2f}%  "
              f"{iso_f.get('roi_pct',0.0):>+13.2f}%({iso_f.get('n',0):>4}b)  "
              f"{iso_kb.get('roi_pct',0.0):>+11.2f}%({n_a:>4}b)  "
              f"{iso_kbb.get('roi_pct',0.0):>+11.2f}%({n_b:>4}b)  "
              f"{d_a:>+5.2f}  "
              f"{d_b:>+5.2f}")

    print("  " + "-" * 84)
    print(f"  {'TOTAL':<6} {sum(iter33_kb_per.get(s,{}).get('n',0) for s in prod_stats_list):>6}  "
          f"{prod_baseline_roi:>+7.2f}%  "
          f"{iso_f_s['agg_roi_pct']:>+13.2f}%  "
          f"{iso_kb_s['agg_roi_pct']:>+11.2f}%  "
          f"{iso_kb_b_s['agg_roi_pct']:>+11.2f}%  "
          f"{delta_iso_kb:>+5.2f}  "
          f"{delta_iso_kb_b:>+5.2f}")
    print()
    print(f"  Choice A (cal threshold + KB): delta={delta_iso_kb:+.2f}pp  reg={reg_iso_kb}  => {dec_iso_kb}")
    print(f"  Choice B (raw threshold, iso Kelly): delta={delta_iso_kb_b:+.2f}pp  reg={reg_iso_kb_b}  => {dec_iso_kb_b}")
    print()
    print(f"  PRIMARY (Choice B): {primary_dec}")

    return {
        "flat":         flat_s,
        "iso_flat_a":   iso_f_s,
        "iso_kb_a":     iso_kb_s,
        "iso_kb_b":     iso_kb_b_s,
        "iter33_kb_baseline":   prod_baseline_roi,
        "iter33_flat_baseline": iter33_flat_roi,
        "sim_flat_roi":  sim_flat_roi,
        "flat_drift":    round(flat_drift, 4),
        "dec_choice_a":  dec_iso_kb,
        "dec_choice_b":  dec_iso_kb_b,
        "dec_primary":   primary_dec,
        "delta_choice_a_pp": delta_iso_kb,
        "delta_choice_b_pp": delta_iso_kb_b,
        "delta_primary_pp":  primary_delta,
        "reg_choice_a":  reg_iso_kb,
        "reg_choice_b":  reg_iso_kb_b,
        "iso_curve_summary": iso_curve_summary,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("  ITER-34: Per-stat Isotonic Edge Calibration")
    print("=" * 80)
    t_total = time.time()

    # Step 1: Load iter23_preds for FG3M/STL/BLK
    print("\n[1/6] Loading iter23_preds.json (FG3M/STL/BLK training data)...")
    iter23_data = load_iter23_training()

    # Step 2: Generate predictions for PTS/REB/AST on 2024 playoffs
    print("\n[2/6] Generating predictions for PTS/REB/AST (2024 playoffs)...")
    t2 = time.time()
    gen_data = generate_pts_reb_ast_training()
    print(f"  [2/6] Done in {(time.time()-t2)/60:.1f}min")

    # Merge training data
    train_data = {**iter23_data, **gen_data}
    print("\n  Training data summary:")
    for stat in ALL_STATS:
        rows = train_data.get(stat, [])
        print(f"    {stat}: {len(rows)} pairs")

    # Step 3: Cross-validate (internal 80/20 split on 2024 playoffs)
    print("\n[3/6] Cross-validating isotonic on internal 20% holdout...")
    cv_results = cv_isotonic(train_data)

    # Step 4: Fit final models on all training data
    print("\n[4/6] Fitting final isotonic models (all training data)...")
    iso_models = fit_isotonic_models(train_data)

    # Step 5: Save models
    print("\n[5/6] Saving isotonic models to disk...")
    saved_paths = save_isotonic_models(iso_models)

    # Step 6: Apply to iter33 simulation and measure ROI
    print("\n[6/6] Applying isotonic calibration to iter33 simulation...")
    sim_results = apply_isotonic_to_iter33(iso_models)

    # ── Final decision ────────────────────────────────────────────────────────
    dec_primary   = sim_results["dec_primary"]
    delta_primary = sim_results["delta_primary_pp"]

    print("\n" + "=" * 80)
    print("  FINAL DECISION")
    print("=" * 80)
    print(f"  Primary: Choice B (raw threshold, iso Kelly sizing)")
    print(f"  Decision:  {dec_primary}")
    print(f"  Delta vs iter33 Kelly-B: {delta_primary:+.2f}pp")
    print(f"  Baseline:  {sim_results['iter33_kb_baseline']:+.2f}%")
    print(f"  Calibrated (ChoiceB): {sim_results['iso_kb_b']['agg_roi_pct']:+.2f}%")
    if dec_primary == "SHIP":
        print("\n  => SHIP: Wire isotonic models into edge_calibration.py")
    elif dec_primary == "REVERT":
        print("\n  => REVERT: Isotonic calibration does not improve ROI under ship criteria")
    else:
        print("\n  => INCONCLUSIVE: delta too small to confirm benefit")

    # ── Save output ───────────────────────────────────────────────────────────
    output = {
        "iter": 34,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approach": "per_stat_isotonic_edge_calibration",
        "training_data": {
            stat: len(train_data.get(stat, []))
            for stat in ALL_STATS
        },
        "cv_results": cv_results,
        "sim_results": sim_results,
        "decision": dec_primary,
        "delta_pp": delta_primary,
        "saved_models": [os.path.basename(p) for p in saved_paths],
        "ship_criterion": {
            "min_delta_pp": SHIP_DELTA_PP,
            "max_regressions": MAX_REGRESSIONS,
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Output -> {OUTPUT_JSON}")
    print(f"  Total runtime: {(time.time()-t_total)/60:.1f}min")

    return output


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
