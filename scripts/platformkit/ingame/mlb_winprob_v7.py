"""scripts.platformkit.ingame.mlb_winprob_v7 -- RUNG 7 of the MLB in-game win-prob
ladder: EVOLVING-STATE conditioning. Rungs 1-6 all REJECT/NULL and taught that NO
pregame/static composite (recalibration, HGB state v2, market-prior blend, team- or
named-batter composition) closes the model~.2295 vs market~.1898 Brier gap. Rung 7
tests the only thing left: features that EVOLVE during a game, unavailable pregame.

WHAT IS TESTED (declared before running): within-game SCORE-MARGIN TRAJECTORY --
[lead_changes, recent_swing, path_vol] (domains.mlb.ingame_trajectory). Path-
dependence the static state model cannot see, and a cheap leak-free proxy for the
diagnosed situational-scoring-intensity lever (pitch-engine v2, db4ba267).

WHAT IS *NOT* TESTED, and WHY (honest -- "say so rather than proxy silently"):
  * live bullpen usage/availability -- the 2026 grade ticks carry NO bullpen field
    (n_bullpen=0 across all 68,525 ticks), so it is not derivable on the EVAL side.
  * current-pitcher pitch_count / times-through-order -- present on the EVAL ticks,
    but NOT derivable leak-free on the 2022-2024 TRAIN parquets: those have no
    pitcher_id (cannot detect pitching changes -> no cumulative count / tto) and
    their game_id scheme (2025-03-18-CUB-LAD-1) has ZERO overlap with savant game_pk
    (numeric), so it would need a fragile date+team-abbrev bridge. Not proxied.
Trajectory is the ONE evolving-state class computable IDENTICALLY on both corpora
with no id bridge and no external join, so it is the only leak-free rung-7 test.

MATCHED-OOS PROTOCOL (gate_baseline_comparability): BASE and CANDIDATE differ ONLY by
the 3 trajectory features -- both HGB, both fit on the SAME seasons (2022-2024), both
isotonic-calibrated on the SAME VAL 2025, both scored on the SAME 2026 grade ticks.
  BASE      = HGB on the 8 v2 state features.
  CANDIDATE = HGB on the same 8 + 3 trajectory features (spec-a: the classifier learns
              the path effect directly -- no hand-crafted composite, no w-grid).
2026 NEVER enters fit/val. Trajectory is causal (margins[0..now] only) and truncation-
invariant. AHEAD only if the PAIRED game-clustered EVAL Brier-delta CI lower bound > 0;
anything else is an honest REJECT. Scored vs the LIVE market price; no devig, no $/ROI,
edge_claimed=False. NO LIVE WIRING regardless of verdict.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; OMP/BLAS<=4; never writes
data/registry/; never flips a flag; never edits src/kernel/api/intel/team_system or the
v2-v6 modules/live_grade.py/state_bucket_benchmark.py; parquets/jsonl READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v7.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

import scripts.platformkit.ingame.mlb_winprob_v2 as wp
import scripts.platformkit.ingame.mlb_winprob_v2_features as feat
import scripts.platformkit.ingame.mlb_winprob_v5_composite as comp
import scripts.platformkit.ingame.state_bucket_benchmark as sb
from domains.mlb.ingame_trajectory import DEFAULT_WINDOW, per_game_trajectory
from scripts.platformkit.ingame.mlb_winprob_v6 import paired_game_bootstrap

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "mlb_winprob_v7_benchmark.json"
TRAIN_SEASONS: Tuple[int, ...] = (2022, 2023, 2024)
VAL_SEASON = 2025
WINDOW = DEFAULT_WINDOW
FEATURE_NAMES = feat.FEATURE_NAMES


def _aligned_sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Sort within-game by asof_idx (temporal), then keep only rows with a parseable
    half label -- the SAME mask feat.train_xy applies, so X8 and trajectory align."""
    if df.empty:
        return df
    d = df.sort_values(["game_id", "asof_idx"], kind="stable").reset_index(drop=True)
    half = d["half_inning_label"].astype(str).str.extract(r"^(top|bottom)(\d+)$")
    return d.loc[half[1].notna()].reset_index(drop=True)


def _season_X(seasons: Sequence[int], data_dir: Optional[Path]
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(X8, traj[N,3], y) for the given seasons, row-aligned. Trajectory = per-game
    causal path features over state_diff ordered by asof_idx."""
    df, _ = feat.load_training_seasons(seasons, data_dir)
    a = _aligned_sorted(df)
    X8, y, _ = feat.train_xy(a)
    if not len(a):
        return X8, np.zeros((0, 3)), y
    traj = per_game_trajectory(a["state_diff"].astype(float).to_numpy(),
                               a["game_id"].astype(str).to_numpy(), WINDOW)
    return X8, traj, y


def _fit(X: np.ndarray, y: np.ndarray, Xval: np.ndarray, yval: np.ndarray
         ) -> Tuple[HistGradientBoostingClassifier, IsotonicRegression]:
    clf = HistGradientBoostingClassifier(random_state=42)
    if len(X):
        clf.fit(X, y)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    if len(Xval):
        iso.fit(clf.predict_proba(Xval)[:, 1], yval)
    else:
        iso.fit([0.0, 1.0], [0.0, 1.0])
    return clf, iso


def train(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fit BASE (8 feat) and CANDIDATE (8+3 traj) HGBs on 2022-2024, iso on VAL 2025.
    Identical everything except the 3 trajectory columns."""
    assert set(TRAIN_SEASONS) <= {2022, 2023, 2024}, "v7: TRAIN must stay <=2024"
    X8, tr, y = _season_X(TRAIN_SEASONS, data_dir)
    X8v, trv, yv = _season_X((VAL_SEASON,), data_dir)
    X11, X11v = np.hstack([X8, tr]), np.hstack([X8v, trv])
    base_clf, base_iso = _fit(X8, y, X8v, yv)
    cand_clf, cand_iso = _fit(X11, y, X11v, yv)
    return {"base_clf": base_clf, "base_iso": base_iso, "cand_clf": cand_clf,
            "cand_iso": cand_iso,
            "meta": {"train_seasons": list(TRAIN_SEASONS), "val_season": VAL_SEASON,
                     "window": WINDOW, "n_train_rows": int(len(X11)),
                     "n_val_rows": int(len(X11v)),
                     "base_features": list(FEATURE_NAMES),
                     "candidate_features": list(FEATURE_NAMES)
                     + ["traj_lead_changes", "traj_recent_swing", "traj_path_vol"]}}


def _eval_X(ticks: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
    """(X8, X11) for eval ticks. Trajectory computed per game over the tick margin
    stream in capture order (grade files are chronological append-logs)."""
    if not ticks:
        return np.zeros((0, 8)), np.zeros((0, 11))
    X8 = np.array([[t[f] for f in FEATURE_NAMES] for t in ticks], dtype=float)
    margins = np.array([t["score_margin"] for t in ticks], dtype=float)
    gids = np.array([str(t["game_id"]) for t in ticks])
    traj = per_game_trajectory(margins, gids, WINDOW)
    return X8, np.hstack([X8, traj])


def build_benchmark(bundle: Dict[str, Any], grade_dir: Optional[Path] = None,
                    resolver: Any = None) -> Dict[str, Any]:
    ticks, counts = wp.build_eval_ticks(grade_dir, resolver)
    X8e, X11e = _eval_X(ticks)
    base_probs = wp.predict_proba(bundle["base_clf"], bundle["base_iso"], X8e)
    cand_probs = wp.predict_proba(bundle["cand_clf"], bundle["cand_iso"], X11e)
    y = np.array([t["outcome"] for t in ticks], dtype=float) if ticks else np.zeros(0)
    gids = [t["game_id"] for t in ticks]

    new_ticks = [dict(t, model_prob=float(p)) for t, p in zip(ticks, cand_probs)]
    old_ticks = [dict(t, model_prob=t["old_model_prob"]) for t in ticks]
    base_ticks = [dict(t, model_prob=float(p)) for t, p in zip(ticks, base_probs)]
    nb: Dict[str, List[Dict[str, Any]]] = {}
    ob: Dict[str, List[Dict[str, Any]]] = {}
    vb: Dict[str, List[Dict[str, Any]]] = {}
    for t in new_ticks:
        nb.setdefault(t["bucket"], []).append(t)
    for t in old_ticks:
        ob.setdefault(t["bucket"], []).append(t)
    for t in base_ticks:
        vb.setdefault(t["bucket"], []).append(t)
    bucket_rows = [comp.combine_row3(name, sb._score_bucket(nb[name]),
                                     sb._score_bucket(ob[name]), sb._score_bucket(vb[name]))
                   for name in sorted(nb)]
    pooled = comp.combine_row3("pooled", sb._score_bucket(new_ticks),
                               sb._score_bucket(old_ticks), sb._score_bucket(base_ticks))
    paired = paired_game_bootstrap(base_probs, cand_probs, y, gids)
    phase_paired: Dict[str, Any] = {}
    for name in sorted(nb):
        idx = [i for i, t in enumerate(ticks) if t["bucket"] == name]
        if idx:
            phase_paired[name] = paired_game_bootstrap(
                base_probs[idx], cand_probs[idx], y[idx], [gids[i] for i in idx])
    scored = {k: v for k, v in phase_paired.items() if v.get("ci95")}
    worst = min(scored, key=lambda k: scored[k]["delta_brier"]) if scored else None
    verdict = "AHEAD" if paired["verdict"] == "AHEAD" else "REJECT"
    return {
        "sport": "mlb", "rung": 7, "benchmark": "live_kalshi_market_price",
        "model": "mlb_winprob_v7 (state HGB + within-game margin trajectory, spec-a)",
        "hypothesis": "evolving-state: within-game score-margin trajectory (path-dependence)",
        "verdict": verdict, "candidate_vs_base_paired": paired,
        "candidate_vs_base_per_phase": phase_paired, "worst_phase_bucket": worst,
        "n_grade_files_mlb": counts["n_files"], "n_games_resolved": counts["n_games_resolved"],
        "n_ticks_used": counts["n_ticks_used"], "min_games_for_verdict": sb.MIN_GAMES,
        "buckets": bucket_rows, "pooled": pooled,
        "units": "probability (Brier/log-loss/ECE; no dollars)", "edge_claimed": False,
        "meta": bundle["meta"],
        "honest_note": (
            "Calibration measurement only vs the LIVE market price (not a devig close). "
            "Matched-OOS: BASE (8 state feats) and CANDIDATE (+3 within-game trajectory "
            "feats) are both HGB fit 2022-2024, isotonic 2025, scored on the 2026 grade "
            "corpus; they differ ONLY by the trajectory columns. Trajectory is causal "
            "(margins[0..now]) and truncation-invariant. Bullpen usage and pitch_count/"
            "tto fatigue were NOT tested: bullpen is absent from the eval ticks, and "
            "pitch_count/tto are not derivable leak-free on the train parquets (no "
            "pitcher_id; game_id<->savant game_pk mismatch). AHEAD requires the PAIRED "
            "game-clustered EVAL CI lower bound > 0. No $/ROI/edge claim."),
    }


def write_benchmark(out_path: Optional[Path] = None, grade_dir: Optional[Path] = None,
                    resolver: Any = None, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    bundle = train(data_dir)
    doc = build_benchmark(bundle, grade_dir, resolver)
    out = out_path or DEFAULT_OUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out))
    return doc


if __name__ == "__main__":
    result = write_benchmark()
    print(json.dumps({"verdict": result["verdict"],
                      "candidate_vs_base_paired": result["candidate_vs_base_paired"],
                      "worst_phase_bucket": result["worst_phase_bucket"],
                      "pooled_cand_vs_market": result["pooled"]["new_vs_market"],
                      "pooled_base_vs_market": result["pooled"]["v2_state_vs_market"],
                      "n_ticks_used": result["n_ticks_used"]}, indent=2, ensure_ascii=True))

__all__ = ["DEFAULT_OUT_PATH", "TRAIN_SEASONS", "VAL_SEASON", "WINDOW",
           "train", "build_benchmark", "write_benchmark"]
