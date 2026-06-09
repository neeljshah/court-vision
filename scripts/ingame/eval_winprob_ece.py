"""W-034 — Win-probability reliability / ECE harness.

Bins predicted P(home win) vs observed win frequency per period-bucket and
computes Expected Calibration Error (ECE) for each win-prob method and period.
This is a READ-ONLY analysis tool: it never touches serve-path files and writes
outputs only to ``.planning/ingame/``.

Methods evaluated
-----------------
- ``logistic``      parameter-free time/score sigmoid (baseline_winprob from
                    eval_second_by_second — no model, no artifacts)
- ``inplay_wp``     ``src.prediction.inplay_winprob.predict_home_win_prob`` at
                    end-of-quarter snapshots (endQ1/endQ2/endQ3) where the model
                    can build complete quarter-score features.  The model falls
                    back gracefully through v6_hp -> v3 -> v2 -> v1 depending on
                    which artifacts are present.

Period buckets
--------------
Each grid point is assigned a period label:
  Q1  : t=360 (06min midQ1), t=720 (12min endQ1)
  Q2  : t=1080 (18min midQ2), t=1440 (24min endQ2)
  Q3  : t=1800 (30min midQ3), t=2160 (36min endQ3)
  Q4  : t=2520 (42min midQ4)

ECE is computed per method per period using 10 equal-width probability bins
over [0, 1].  The reliability table (mean_predicted_p, observed_freq, bin_n,
ece_contribution) is emitted for each (method, period).

Outputs
-------
  .planning/ingame/eval_winprob_ece.json   full results
  .planning/ingame/eval_winprob_ece.md     readable reliability table + ECE

Validation command (per INGAME_CALIBRATION_PROTOCOL.md):
  python scripts/ingame/eval_routed_ensemble.py --max-games 220 --folds 3
  # (this harness is read-only; the validate command produces the Brier reference)

Run:
  set NBA_OFFLINE=1
  python scripts/ingame/eval_winprob_ece.py --max-games 220 --folds 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402

from scripts.ingame.eval_second_by_second import (  # noqa: E402
    GamelogStore, load_season_games, build_game_record,
    baseline_winprob, _parse_iso_date, GRID_LABELS, GRID_SEC,
)
from src.ingame.state_featurizer import discover_game_ids  # noqa: E402
from src.prediction.inplay_winprob import (  # noqa: E402
    predict_home_win_prob, active_stack, SNAPSHOTS,
)

PLAN_DIR = os.path.join(ROOT, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

# Number of ECE bins (equal-width, [0,1]).
N_BINS = 10

# Map grid-second -> period label (for grouping).
_PERIOD_OF_GRID: Dict[int, str] = {
    360:  "Q1",   # 06min midQ1
    720:  "Q1",   # 12min endQ1
    1080: "Q2",   # 18min midQ2
    1440: "Q2",   # 24min endQ2/half
    1800: "Q3",   # 30min midQ3
    2160: "Q3",   # 36min endQ3
    2520: "Q4",   # 42min midQ4
}

# End-of-quarter grid seconds where full quarter scores are available (required
# for inplay_winprob.predict_home_win_prob via features_from_snapshot).
_END_OF_QTR_SEC: Dict[int, str] = {
    720:  "endQ1",
    1440: "endQ2",
    2160: "endQ3",
}

# Canonical period ordering for display.
_PERIOD_ORDER = ["Q1", "Q2", "Q3", "Q4"]


# ---------------------------------------------------------------------------
# Quarter-score reconstruction from the full-game row list
# ---------------------------------------------------------------------------

def _reconstruct_quarter_scores(
    game_rows: List[Dict[str, Any]],
    snap_sec: int,
    orientation: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Reconstruct per-quarter scores from end-of-quarter PBP rows.

    For the inplay_winprob model we need ``home_q1``, ``home_q2``, ``home_q3``
    (and equivalent away columns).  These are derived by taking the cumulative
    home/away score at the START of each quarter (= end of the previous quarter)
    and computing the diff.

    Returns None when insufficient rows are available.
    """
    # Identify the last game row at / just before snap_sec.
    chosen: Optional[Dict[str, Any]] = None
    for row in game_rows:
        if row.get("game_elapsed_sec", 0) <= snap_sec:
            chosen = row
        else:
            break
    if chosen is None:
        return None

    # To get per-quarter scores we need the cumulative score at the end of each
    # prior quarter.  The featurizer emits game rows in strict event order; we
    # find the LAST row with game_elapsed_sec <= end_of_period for each quarter.
    _Q_END_SEC = {1: 720, 2: 1440, 3: 2160}
    q_scores: Dict[int, Tuple[float, float]] = {}  # qtr -> (home, away)
    for q, qend in _Q_END_SEC.items():
        if snap_sec < qend:
            break
        last_q: Optional[Dict[str, Any]] = None
        for row in game_rows:
            if row.get("game_elapsed_sec", 0) <= qend:
                last_q = row
            else:
                break
        if last_q is None:
            break
        q_scores[q] = (float(last_q.get("home_score", 0) or 0),
                       float(last_q.get("away_score", 0) or 0))

    n_qtrs = len(q_scores)
    if n_qtrs == 0:
        return None

    # Convert cumulative to per-quarter deltas.
    result: Dict[str, Any] = {}
    prev_h, prev_a = 0.0, 0.0
    for q in range(1, n_qtrs + 1):
        if q not in q_scores:
            return None
        h_cum, a_cum = q_scores[q]
        result[f"home_q{q}"] = h_cum - prev_h
        result[f"away_q{q}"] = a_cum - prev_a
        prev_h, prev_a = h_cum, a_cum

    return result


# ---------------------------------------------------------------------------
# Build win-prob features dict from a game_row + optional quarter scores
# ---------------------------------------------------------------------------

def _wp_features(
    game_row: Dict[str, Any],
    snap_name: str,
    q_scores: Optional[Dict[str, Any]],
    season: Optional[str],
) -> Dict[str, Any]:
    """Assemble the feature dict expected by predict_home_win_prob.

    Uses the same v1 feature schema: score_margin, total_pts, pace_so_far,
    q*_delta, last_q_margin, pregame_win_prob, home_team_id, season.

    For v2 features (projected_final_margin, etc.) we derive from the same
    quantities so they are available even without the snap bundle.
    """
    period_of_snap = {"endQ1": 1, "endQ2": 2, "endQ3": 3}.get(snap_name, 1)
    minutes_played = period_of_snap * 12.0
    rem_minutes = 48.0 - minutes_played

    # v1 features from the game_row + q_scores
    h_cum = float(game_row.get("home_score", 0) or 0)
    a_cum = float(game_row.get("away_score", 0) or 0)
    score_margin = h_cum - a_cum
    total_pts = h_cum + a_cum
    pace_so_far = (total_pts / minutes_played) if minutes_played > 0 else 0.0
    margin_per_min = (score_margin / minutes_played) if minutes_played > 0 else 0.0
    projected_final_margin = score_margin + margin_per_min * rem_minutes
    projected_total_score = total_pts + pace_so_far * rem_minutes

    feats: Dict[str, Any] = {
        "score_margin": score_margin,
        "total_pts": total_pts,
        "pace_so_far": pace_so_far,
        "projected_final_margin": projected_final_margin,
        "projected_total_score": projected_total_score,
        # pregame WP defaults to 0.5 (neutral); no pregame source in retro replay.
        "pregame_win_prob": 0.5,
        "home_team_id": game_row.get("home_team"),
        "season": season,
        # v2 higher-order features (approximated from available state)
        "qtr_margin_var": 0.0,
        "qtr_margin_mean": 0.0,
        "net_rtg_diff": 0.0,
        "pace_diff": 0.0,
        "elo_diff": 0.0,
        "stars_diff": 0.0,
        "rest_diff": 0.0,
        "b2b_diff": 0.0,
        "last5_diff": 0.0,
    }

    if q_scores:
        q_deltas = []
        prev_h_q, prev_a_q = 0.0, 0.0
        for q in range(1, period_of_snap + 1):
            hq = float(q_scores.get(f"home_q{q}", 0) or 0)
            aq = float(q_scores.get(f"away_q{q}", 0) or 0)
            delta = hq - aq
            q_deltas.append(delta)
            if q == 1:
                feats["q1_delta"] = delta
                feats["last_q_margin"] = delta
            elif q == 2:
                feats["q2_delta"] = delta
                feats["last_q_margin"] = delta
            elif q == 3:
                feats["q3_delta"] = delta
                feats["last_q_margin"] = delta
            prev_h_q += hq
            prev_a_q += aq

        if len(q_deltas) >= 2:
            feats["qtr_margin_var"] = float(np.var(q_deltas))
            feats["qtr_margin_mean"] = float(np.mean(q_deltas))
        elif q_deltas:
            feats["qtr_margin_mean"] = float(q_deltas[0])
    else:
        # Fallback: approximate from cumulative margin
        feats["q1_delta"] = score_margin
        feats["last_q_margin"] = score_margin

    return feats


# ---------------------------------------------------------------------------
# ECE computation
# ---------------------------------------------------------------------------

def _compute_ece(preds: List[float], labels: List[int],
                 n_bins: int = N_BINS) -> Tuple[float, List[Dict[str, Any]]]:
    """Compute ECE + reliability table for a set of (pred, label) pairs.

    Returns (ece, reliability_table) where:
      ece = sum_b (|bin_n|/N) * |mean_pred - observed_freq|
      reliability_table = list of dicts with keys:
        bin_lower, bin_upper, bin_n, mean_predicted_p, observed_freq, gap
    """
    preds_arr = np.array(preds, dtype=float)
    labels_arr = np.array(labels, dtype=int)
    n_total = len(preds_arr)
    if n_total == 0:
        return 0.0, []

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    table = []
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        # include upper edge in the last bin
        if i == n_bins - 1:
            mask = (preds_arr >= lo) & (preds_arr <= hi)
        else:
            mask = (preds_arr >= lo) & (preds_arr < hi)
        n_bin = int(mask.sum())
        if n_bin == 0:
            table.append({
                "bin_lower": float(lo), "bin_upper": float(hi),
                "bin_n": 0,
                "mean_predicted_p": None,
                "observed_freq": None,
                "gap": None,
            })
            continue
        mean_pred = float(preds_arr[mask].mean())
        obs_freq = float(labels_arr[mask].mean())
        gap = abs(mean_pred - obs_freq)
        ece += (n_bin / n_total) * gap
        table.append({
            "bin_lower": float(lo), "bin_upper": float(hi),
            "bin_n": n_bin,
            "mean_predicted_p": round(mean_pred, 4),
            "observed_freq": round(obs_freq, 4),
            "gap": round(gap, 4),
        })
    return float(ece), table


# ---------------------------------------------------------------------------
# Brier score
# ---------------------------------------------------------------------------

def _brier(p: float, y: int) -> float:
    return float((p - y) ** 2)


# ---------------------------------------------------------------------------
# Main eval loop
# ---------------------------------------------------------------------------

def run(max_games: int, folds: int, min_train: int) -> Dict[str, Any]:
    season_games = load_season_games()
    store = GamelogStore()

    all_ids = [g for g in discover_game_ids() if g in season_games]
    all_ids = [g for g in all_ids
               if _parse_iso_date(season_games[g].get("game_date") or "")]
    all_ids.sort(key=lambda g: season_games[g]["game_date"])

    n_total = len(all_ids)
    if max_games and n_total > max_games:
        idx = np.linspace(0, n_total - 1, max_games).astype(int)
        sampled = [all_ids[i] for i in sorted(set(idx.tolist()))]
    else:
        sampled = all_ids
    print(f"[wp-ece] {n_total} dated games; using {len(sampled)} "
          f"(chronological-even subsample={max_games})")

    records: List[Dict[str, Any]] = []
    n_fail = 0
    for i, gid in enumerate(sampled):
        try:
            rec = build_game_record(gid, season_games[gid], store)
        except Exception:
            rec = None
            n_fail += 1
        if rec is not None:
            records.append(rec)
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{len(sampled)} ({len(records)} usable)")
    records.sort(key=lambda r: r["game_date"])
    print(f"[wp-ece] {len(records)} usable ({n_fail} failed)")
    if len(records) < min_train + 10:
        raise SystemExit(f"too few usable games ({len(records)})")

    # Walk-forward folds by date.
    dates = [r["game_date"] for r in records]
    uniq = sorted(set(dates))
    chunks = np.array_split(np.array(uniq, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]

    # Accumulators: acc[method][period] -> {"preds": [...], "labels": [...], "brier": [...]}
    # methods: "logistic", "inplay_wp"
    methods = ("logistic", "inplay_wp")
    acc: Dict[str, Dict[str, Dict[str, List]]] = {
        m: {p: {"preds": [], "labels": [], "brier": []} for p in _PERIOD_ORDER}
        for m in methods
    }
    # Also track by grid-bucket for the detailed table.
    acc_bucket: Dict[str, Dict[str, Dict[str, List]]] = {
        m: {} for m in methods
    }
    fold_summaries = []

    for fold_i, test_dates in enumerate(fold_test_dates):
        train_recs = [r for r in records if r["game_date"] < min(test_dates)]
        test_recs = [r for r in records if r["game_date"] in test_dates]
        if len(train_recs) < min_train or not test_recs:
            print(f"[fold {fold_i}] skipped (train={len(train_recs)} test={len(test_recs)})")
            continue
        print(f"[fold {fold_i}] train={len(train_recs)} test={len(test_recs)}")

        for rec in test_recs:
            y = rec["home_win"]
            season = season_games.get(rec["game_id"], {}).get("season")

            # Reconstruct full game_row list for this record (needed for
            # quarter-score reconstruction).  The build_game_record function
            # stores it under "grids"; we access the raw featurizer output
            # via the game_rows which are in the grids dict.
            # Note: build_game_record doesn't expose raw game_rows directly;
            # we can reconstruct quarter scores from the grid snapshots.
            # At endQ1 (t=720): home_score = Q1 total
            # At endQ2 (t=1440): home_score = Q1+Q2 total  -> Q2 = total - Q1
            # At endQ3 (t=2160): home_score = Q1+Q2+Q3 total -> Q3 = total - (Q1+Q2)
            grids = rec["grids"]

            # Helper: cumulative scores at end-of-quarter boundaries
            def _cum_scores(t: int) -> Optional[Tuple[float, float]]:
                gd = grids.get(t)
                if gd is None:
                    return None
                gr = gd["game"]
                return (float(gr.get("home_score", 0) or 0),
                        float(gr.get("away_score", 0) or 0))

            q_cum: Dict[int, Tuple[float, float]] = {}
            for q, sec in ((1, 720), (2, 1440), (3, 2160)):
                cs = _cum_scores(sec)
                if cs is not None:
                    q_cum[q] = cs

            def _q_scores_for_snap(snap_name: str) -> Optional[Dict[str, Any]]:
                """Build per-quarter scores dict for the given snap."""
                n_qtrs = {"endQ1": 1, "endQ2": 2, "endQ3": 3}.get(snap_name, 0)
                if n_qtrs == 0:
                    return None
                result: Dict[str, Any] = {}
                prev_h, prev_a = 0.0, 0.0
                for q in range(1, n_qtrs + 1):
                    if q not in q_cum:
                        return None
                    h_cum_q, a_cum_q = q_cum[q]
                    result[f"home_q{q}"] = h_cum_q - prev_h
                    result[f"away_q{q}"] = a_cum_q - prev_a
                    prev_h, prev_a = h_cum_q, a_cum_q
                return result

            for t, gd in sorted(grids.items()):
                gr = gd["game"]
                bucket_label = GRID_LABELS.get(t)
                if bucket_label is None:
                    continue
                period = _PERIOD_OF_GRID.get(t)
                if period is None:
                    continue

                # --- logistic baseline (parameter-free, works at any t) ---
                p_log = baseline_winprob(gr)
                acc["logistic"][period]["preds"].append(p_log)
                acc["logistic"][period]["labels"].append(y)
                acc["logistic"][period]["brier"].append(_brier(p_log, y))
                # bucket-level
                if bucket_label not in acc_bucket["logistic"]:
                    acc_bucket["logistic"][bucket_label] = {
                        "preds": [], "labels": [], "brier": []}
                acc_bucket["logistic"][bucket_label]["preds"].append(p_log)
                acc_bucket["logistic"][bucket_label]["labels"].append(y)
                acc_bucket["logistic"][bucket_label]["brier"].append(_brier(p_log, y))

                # --- inplay_wp: only at end-of-quarter snapshots ---
                snap_name = _END_OF_QTR_SEC.get(t)
                if snap_name is not None:
                    q_scores = _q_scores_for_snap(snap_name)
                    wp_feats = _wp_features(gr, snap_name, q_scores, season)
                    p_wp: Optional[float] = None
                    if wp_feats:
                        try:
                            p_wp = predict_home_win_prob(wp_feats, snap_name)
                        except Exception:
                            p_wp = None
                    if p_wp is not None:
                        acc["inplay_wp"][period]["preds"].append(p_wp)
                        acc["inplay_wp"][period]["labels"].append(y)
                        acc["inplay_wp"][period]["brier"].append(_brier(p_wp, y))
                        if bucket_label not in acc_bucket["inplay_wp"]:
                            acc_bucket["inplay_wp"][bucket_label] = {
                                "preds": [], "labels": [], "brier": []}
                        acc_bucket["inplay_wp"][bucket_label]["preds"].append(p_wp)
                        acc_bucket["inplay_wp"][bucket_label]["labels"].append(y)
                        acc_bucket["inplay_wp"][bucket_label]["brier"].append(
                            _brier(p_wp, y))

        fold_summaries.append({
            "fold": fold_i, "n_train": len(train_recs), "n_test": len(test_recs),
            "test_date_min": str(min(test_dates)),
            "test_date_max": str(max(test_dates)),
        })

    # Report which artifact stack was loaded.
    wp_stacks = {}
    for snap in SNAPSHOTS:
        try:
            wp_stacks[snap] = active_stack(snap)
        except Exception as exc:
            wp_stacks[snap] = {"error": str(exc)}

    return _summarize(acc, acc_bucket, fold_summaries, len(records),
                      n_total, wp_stacks)


# ---------------------------------------------------------------------------
# Summarise
# ---------------------------------------------------------------------------

def _mean(xs: List[float]) -> Optional[float]:
    return float(np.mean(xs)) if xs else None


def _summarize(
    acc: Dict,
    acc_bucket: Dict,
    fold_summaries: List,
    n_records: int,
    n_total: int,
    wp_stacks: Dict,
) -> Dict[str, Any]:
    # Per-period ECE + Brier + reliability table for each method.
    period_results: Dict[str, Dict[str, Any]] = {}
    for period in _PERIOD_ORDER:
        period_results[period] = {}
        for m in ("logistic", "inplay_wp"):
            preds = acc[m][period]["preds"]
            labels = acc[m][period]["labels"]
            brier_vals = acc[m][period]["brier"]
            n = len(preds)
            if n == 0:
                period_results[period][m] = {
                    "n": 0, "brier": None, "ece": None,
                    "reliability": [],
                }
                continue
            ece, rel_table = _compute_ece(preds, labels)
            period_results[period][m] = {
                "n": n,
                "brier": round(float(np.mean(brier_vals)), 5),
                "ece": round(ece, 5),
                "reliability": rel_table,
            }

    # Per-bucket (more granular) ECE + Brier.
    bucket_results: Dict[str, Dict[str, Any]] = {}
    # build ordered bucket list from GRID_LABELS
    for bucket_label in GRID_LABELS.values():
        bucket_results[bucket_label] = {}
        for m in ("logistic", "inplay_wp"):
            bd = acc_bucket.get(m, {}).get(bucket_label)
            if not bd or not bd["preds"]:
                bucket_results[bucket_label][m] = {
                    "n": 0, "brier": None, "ece": None}
                continue
            preds = bd["preds"]
            labels = bd["labels"]
            brier_vals = bd["brier"]
            ece, _ = _compute_ece(preds, labels)
            bucket_results[bucket_label][m] = {
                "n": len(preds),
                "brier": round(float(np.mean(brier_vals)), 5),
                "ece": round(ece, 5),
            }

    # Overall (all periods pooled) ECE + Brier for each method.
    overall: Dict[str, Any] = {}
    for m in ("logistic", "inplay_wp"):
        all_preds: List[float] = []
        all_labels: List[int] = []
        all_brier: List[float] = []
        for period in _PERIOD_ORDER:
            all_preds.extend(acc[m][period]["preds"])
            all_labels.extend(acc[m][period]["labels"])
            all_brier.extend(acc[m][period]["brier"])
        n = len(all_preds)
        if n == 0:
            overall[m] = {"n": 0, "brier": None, "ece": None}
            continue
        ece, _ = _compute_ece(all_preds, all_labels)
        overall[m] = {
            "n": n,
            "brier": round(float(np.mean(all_brier)), 5),
            "ece": round(ece, 5),
        }

    return {
        "meta": {
            "n_total_dated_pbp_games": n_total,
            "n_usable_records": n_records,
            "folds": fold_summaries,
            "n_ece_bins": N_BINS,
            "grid_labels": GRID_LABELS,
            "period_map": _PERIOD_OF_GRID,
            "end_of_qtr_snapshots": _END_OF_QTR_SEC,
            "inplay_wp_artifact_stacks": wp_stacks,
            "design": (
                "ECE harness (W-034). Bins predicted-P vs observed win-freq per "
                "period-bucket. Methods: (1) logistic = time/score sigmoid "
                "(baseline_winprob, parameter-free, evaluated at all 7 grid "
                "buckets per game); (2) inplay_wp = predict_home_win_prob from "
                "src.prediction.inplay_winprob, evaluated at endQ1/endQ2/endQ3 "
                "where full quarter-score features are available. ECE = "
                "sum_b(|bin_n|/N)*|mean_pred - obs_freq| over 10 equal-width bins. "
                "Brier = mean(pred-y)^2. Walk-forward: chronological-even subsample, "
                "no training (both methods are closed-form / use pre-loaded artifacts). "
                "Read-only: no serve-path files touched."),
        },
        "overall": overall,
        "by_period": period_results,
        "by_bucket": bucket_results,
    }


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------

def _f(x: Any, nd: int = 4) -> str:
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "n/a"


def write_markdown(summary: Dict[str, Any], path: str) -> None:
    m = summary["meta"]
    L = ["# Win-Probability Reliability / ECE (W-034)\n"]
    L.append(f"- usable records: **{m['n_usable_records']}** of "
             f"{m['n_total_dated_pbp_games']} dated games "
             f"({len(m['folds'])} WF folds)")
    L.append(f"- ECE bins: {m['n_ece_bins']} equal-width over [0,1]")
    L.append(f"- inplay_wp evaluated at: endQ1, endQ2, endQ3 (full quarter "
             f"scores required); logistic at all 7 grid buckets\n")

    # Artifact stacks
    L.append("## Win-Prob Artifact Stacks\n")
    for snap, info in m.get("inplay_wp_artifact_stacks", {}).items():
        layer = info.get("layer", "?")
        detail = info.get("detail", "")
        L.append(f"- **{snap}**: {layer} — {detail}")
    L.append("")

    # Overall table
    L.append("## Overall (all periods pooled)\n")
    L.append("| method | n | Brier | ECE |")
    L.append("|---|--:|--:|--:|")
    for met_name in ("logistic", "inplay_wp"):
        d = summary["overall"].get(met_name, {})
        n = d.get("n", 0)
        L.append(f"| {met_name} | {n} | {_f(d.get('brier'))} | "
                 f"{_f(d.get('ece'))} |")
    L.append("")

    # Per-period table
    L.append("## Per-period Brier + ECE\n")
    L.append("| period | method | n | Brier | ECE |")
    L.append("|---|---|--:|--:|--:|")
    for period in _PERIOD_ORDER:
        pd_data = summary["by_period"].get(period, {})
        for met_name in ("logistic", "inplay_wp"):
            d = pd_data.get(met_name, {})
            n = d.get("n", 0)
            if n == 0:
                continue
            L.append(f"| {period} | {met_name} | {n} | "
                     f"{_f(d.get('brier'))} | {_f(d.get('ece'))} |")
    L.append("")

    # Per-bucket table
    L.append("## Per-bucket Brier + ECE\n")
    L.append("| bucket | method | n | Brier | ECE |")
    L.append("|---|---|--:|--:|--:|")
    for bkt in GRID_LABELS.values():
        bd = summary["by_bucket"].get(bkt, {})
        for met_name in ("logistic", "inplay_wp"):
            d = bd.get(met_name, {})
            n = d.get("n", 0)
            if n == 0:
                continue
            L.append(f"| {bkt} | {met_name} | {n} | "
                     f"{_f(d.get('brier'))} | {_f(d.get('ece'))} |")
    L.append("")

    # Reliability tables per (period, method)
    L.append("## Reliability tables (per period, per method)\n")
    for period in _PERIOD_ORDER:
        pd_data = summary["by_period"].get(period, {})
        for met_name in ("logistic", "inplay_wp"):
            d = pd_data.get(met_name, {})
            rel = d.get("reliability", [])
            if not rel or d.get("n", 0) == 0:
                continue
            L.append(f"### {period} — {met_name} "
                     f"(n={d['n']}, Brier={_f(d.get('brier'))}, "
                     f"ECE={_f(d.get('ece'))})\n")
            L.append("| bin | mean_pred_P | obs_freq | gap | bin_n |")
            L.append("|-----|--:|--:|--:|--:|")
            for row in rel:
                if row.get("bin_n", 0) == 0:
                    continue
                blo = _f(row["bin_lower"], 2)
                bhi = _f(row["bin_upper"], 2)
                L.append(f"| [{blo},{bhi}) | "
                         f"{_f(row.get('mean_predicted_p'))} | "
                         f"{_f(row.get('observed_freq'))} | "
                         f"{_f(row.get('gap'))} | "
                         f"{row.get('bin_n', 0)} |")
            L.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-games", type=int, default=220,
                    help="chronological-even subsample size (default 220)")
    ap.add_argument("--folds", type=int, default=3,
                    help="walk-forward folds (default 3)")
    ap.add_argument("--min-train", type=int, default=40,
                    help="minimum games in training window to count a fold")
    args = ap.parse_args()

    summary = run(args.max_games, args.folds, args.min_train)

    jp = os.path.join(PLAN_DIR, "eval_winprob_ece.json")
    mp = os.path.join(PLAN_DIR, "eval_winprob_ece.md")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    write_markdown(summary, mp)
    print(f"\n[wp-ece] wrote {jp}")
    print(f"[wp-ece] wrote {mp}")

    # Print summary table to stdout.
    def _fmt(x: Any) -> str:
        return f"{x:8.4f}" if isinstance(x, float) else f"{'n/a':>8}"

    print("\n=== OVERALL (all periods pooled) ===")
    print(f"{'method':<15} {'n':>6} {'Brier':>8} {'ECE':>8}")
    print("-" * 42)
    for met_name in ("logistic", "inplay_wp"):
        d = summary["overall"].get(met_name, {})
        n = d.get("n", 0)
        print(f"{met_name:<15} {n:>6} "
              f"{_fmt(d.get('brier'))} {_fmt(d.get('ece'))}")

    print("\n=== PER-PERIOD Brier + ECE ===")
    print(f"{'period':<8} {'method':<15} {'n':>6} {'Brier':>8} {'ECE':>8}")
    print("-" * 50)
    for period in _PERIOD_ORDER:
        pd_data = summary["by_period"].get(period, {})
        for met_name in ("logistic", "inplay_wp"):
            d = pd_data.get(met_name, {})
            n = d.get("n", 0)
            if n == 0:
                continue
            print(f"{period:<8} {met_name:<15} {n:>6} "
                  f"{_fmt(d.get('brier'))} {_fmt(d.get('ece'))}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
