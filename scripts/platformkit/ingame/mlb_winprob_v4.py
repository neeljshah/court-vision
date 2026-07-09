"""scripts.platformkit.ingame.mlb_winprob_v4 -- rung 4 of the MLB in-game win-prob ladder.

LADDER SO FAR: pooled model (0eee3708, Brier 0.2292 vs market 0.1898) -> v2 (3aac11e8,
HistGB no prior, honest REJECT, OOD-overconfident on 2026 blowouts) -> v3 (57c1c696, adds
a market-price prior via an UNREGULARIZED per-tick logit-blend fit on autocorrelated 2025
rows with sparse 2022/2024-only PM train coverage, honest REJECT). Carried forward: state
features + a prior anchor both work -- the FIT was wrong.

DESIGN (K=2, declared before running): TRAIN BAND = 2024+2025 pitch states (the band
where 2024plus Polymarket priors exist) -- feat.load_training_seasons/2026-guard reused
unchanged, 2026 NEVER enters train/val. Prior coverage is reported for 2024 and 2025
SEPARATELY (prior_coverage_2024 / prior_coverage_2025 in the output doc): the mlb_2024plus
Polymarket corpus on disk starts 2025-04-02 -- 2024 has ZERO PM prior rows (same
sparse-2024 gap v3 already flagged), so spec (a)'s 2024 rows fall back to prior_home=0.5.

  spec (a) "prior-as-feature, retrained": v3's 10-feature vector (v2's 8 state features +
  prior_logit + has_prior, v3.train_xy_v3 reused unchanged) as a fresh HistGB, TRAINED ON
  2024 ONLY, isotonic-calibrated on 2025. No blend fit -- the model itself learns how much
  to trust prior_logit via has_prior. Clean OOS: 2025 never enters spec (a)'s own fit.

  spec (b) "regularized per-phase blend": v2's 8-feature state HistGB (wp.train_model
  reused unchanged) trained on 2024+2025 POOLED (more state-only data, no prior feature to
  leak), isotonic-calibrated on 2025 (also inside that pooled train window -- see honest_note
  leak flag below). On top of it, a per-PHASE (early/mid/late, sb.phase_bucket reused) blend
  weight w_phase in [0,1] on logit scale: blended = sigmoid(w*logit(prior) + (1-w)*logit
  (p_state)), w in COARSE GRID {0,.1,...,1.0}, chosen per phase by GAME-LEVEL (not
  tick-level) Brier on 2025 -- grid + game-aggregation is the regularization v3's
  unconstrained per-tick 2-coefficient logistic fit lacked. Rows with has_prior=False are
  NEVER blended toward a fabricated neutral prior -- they pass through p_state unchanged
  regardless of w_phase (never silently guessed).

  Selection: lower 2025 GAME-LEVEL Brier wins (both specs scored the same way); the loser
  is never scored on 2026. Eval prior (2026) = last traded Kalshi candle before the game's
  first captured tick (prior_mod.build_eval_priors, reused unchanged from v3).

LEAK AUDIT (spec b, explicit): the state HistGB backing spec (b) is fit on 2024+2025
POOLED, so its own 2025 predictions (used for isotonic calibration AND the blend-weight
grid search) are IN-SAMPLE for the state component -- unlike spec (a), which trains
cleanly on 2024 only and validates OOS on 2025. A spec-(b) win on the 2025 comparison is
partly attributable to this in-sample optimism, not just the blend regularization --
flagged here so rung 5 has the diagnosis. The 2026 number is untouched by this asymmetry
(pre-registered K=2, only the winner is ever scored there).

EVAL: pooled + per-bucket (state_bucket_benchmark phase|margin) Brier/log-loss/ECE for
NEW(winner) vs OLD(pooled model, commit 0eee3708) vs MARKET, reusing sb._score_bucket's
game-clustered bootstrap verdict and wp._combine_row unchanged.

HONESTY: calibration measurement only; edge_claimed always False; no $/ROI field. NO LIVE
WIRING -- if the CI shows the new model ahead, wiring it in is a follow-up decision.
INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import; OMP/BLAS
threads capped to 4; never writes data/registry/; never flips a flag; never edits src/
kernel/ api/ intel/ scripts/team_system/ or the v2/v3 modules/live_grade.py/
state_bucket_benchmark.py; parquets/jsonl READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v4.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import json
import logging
import math
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

import scripts.platformkit.ingame.mlb_winprob_v2 as wp
import scripts.platformkit.ingame.mlb_winprob_v2_features as feat
import scripts.platformkit.ingame.mlb_winprob_v3 as v3
import scripts.platformkit.ingame.mlb_winprob_v3_prior as prior_mod
import scripts.platformkit.ingame.state_bucket_benchmark as sb
from scripts.platformkit.ingame.mlb_winprob_v4_blend import (
    PHASES, W_GRID, blend as _blend, game_level_brier as _game_level_brier,
    select_phase_weights,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "mlb_winprob_v4_benchmark.json"
DEFAULT_MODEL_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_winprob_v4.pkl"
DEFAULT_META_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_winprob_v4_meta.json"

TRAIN_SEASON_A = 2024
TRAIN_SEASONS_B: Tuple[int, ...] = (2024, 2025)
VAL_SEASON = 2025


def _load_with_prior(season: int, pm_index: Any, data_dir: Optional[Path]) -> Tuple[Any, Dict[str, int]]:
    df, missing = feat.load_training_seasons((season,), data_dir)
    df, counts = prior_mod.attach_priors(df, pm_index)
    counts = dict(counts, missing_files=missing)
    return df, counts


# -- train both specs, select by 2025 GAME-LEVEL Brier -- #
def train_specs(data_dir: Optional[Path] = None,
                pm_dirs: Sequence[Path] = prior_mod.DEFAULT_PM_DIRS) -> Dict[str, Any]:
    pm_index, pm_counts = prior_mod.build_pm_prior_index(pm_dirs)
    df24, cov24 = _load_with_prior(TRAIN_SEASON_A, pm_index, data_dir)
    df25, cov25 = _load_with_prior(VAL_SEASON, pm_index, data_dir)

    # -- spec a: 10-feature HGB (state + prior), train=2024 only, val/iso=2025 -- #
    Xtr_a, ytr_a, _ = v3.train_xy_v3(df24)
    Xval_a, yval_a, _ = v3.train_xy_v3(df25)
    clf_a = HistGradientBoostingClassifier(random_state=42)
    if len(Xtr_a):
        clf_a.fit(Xtr_a, ytr_a)
    iso_a = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    if len(Xval_a):
        iso_a.fit(clf_a.predict_proba(Xval_a)[:, 1], yval_a)
    else:
        iso_a.fit([0.0, 1.0], [0.0, 1.0])
    probs_a_val = wp.predict_proba(clf_a, iso_a, Xval_a)
    game_id_a = df25.loc[v3._valid_rows(df25), "game_id"].astype(str).to_numpy()
    brier_a = _game_level_brier(probs_a_val, yval_a, game_id_a) if len(Xval_a) else float("nan")

    # -- spec b: 8-feature state HGB, train=2024+2025 pooled, + per-phase blend -- #
    clf_state, iso_state, meta_state = wp.train_model(TRAIN_SEASONS_B, VAL_SEASON, data_dir)
    ok_b = v3._valid_rows(df25)
    d25 = df25.loc[ok_b]
    X8v, yv, _ = feat.train_xy(d25)
    game_id_b = d25["game_id"].astype(str).to_numpy()
    phase_b = np.array([sb.phase_bucket(v) for v in X8v[:, 0]])
    prior_b = d25["prior_home"].astype(float).to_numpy()
    has_b = d25["has_prior"].to_numpy()
    p_state_val = wp.predict_proba(clf_state, iso_state, X8v)
    w_by_phase = select_phase_weights(p_state_val, yv, game_id_b, phase_b, prior_b, has_b)
    probs_b_val = _blend(p_state_val, prior_b, has_b, w_by_phase, phase_b)
    brier_b = _game_level_brier(probs_b_val, yv, game_id_b) if len(X8v) else float("nan")

    candidates = [(n, b) for n, b in (("a", brier_a), ("b", brier_b)) if not math.isnan(b)]
    winner = min(candidates, key=lambda kv: kv[1])[0] if candidates else "a"

    return {
        "clf_a": clf_a, "iso_a": iso_a, "clf_state": clf_state, "iso_state": iso_state,
        "w_by_phase": w_by_phase, "winner": winner,
        "val_game_brier_spec_a": brier_a, "val_game_brier_spec_b": brier_b,
        "meta": {
            "train_season_a": TRAIN_SEASON_A, "train_seasons_b": list(TRAIN_SEASONS_B),
            "val_season": VAL_SEASON, "pm_index_counts": pm_counts,
            "prior_coverage_2024": cov24, "prior_coverage_2025": cov25,
        },
    }


# -- eval on the 2026 grade corpus (winner only) -- #
def build_benchmark(bundle: Dict[str, Any], grade_dir: Optional[Path] = None,
                    resolver: Any = None, kalshi_dir: Optional[Path] = None) -> Dict[str, Any]:
    ticks, counts, eval_prior_counts = prior_mod.build_eval_ticks_with_prior(
        wp.build_eval_ticks, grade_dir, resolver, kalshi_dir)
    if bundle["winner"] == "a":
        X10 = np.array([[t[f] for f in feat.FEATURE_NAMES] +
                        [prior_mod._logit(t["prior_home"]).item(), float(t["has_prior"])]
                        for t in ticks], dtype=float) if ticks else np.zeros((0, len(v3.FEATURE_NAMES_V3)))
        winner_probs = wp.predict_proba(bundle["clf_a"], bundle["iso_a"], X10)
    else:
        p_state = wp.score_new_model(bundle["clf_state"], bundle["iso_state"], ticks)
        phase_e = np.array([sb.phase_bucket(t["inning"]) for t in ticks])
        prior_e = np.array([t["prior_home"] for t in ticks], dtype=float)
        has_e = np.array([t["has_prior"] for t in ticks], dtype=bool)
        winner_probs = _blend(p_state, prior_e, has_e, bundle["w_by_phase"], phase_e)

    new_ticks = [dict(t, model_prob=float(p)) for t, p in zip(ticks, winner_probs)]
    old_ticks = [dict(t, model_prob=t["old_model_prob"]) for t in ticks]
    new_by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    old_by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    for t in new_ticks:
        new_by_bucket.setdefault(t["bucket"], []).append(t)
    for t in old_ticks:
        old_by_bucket.setdefault(t["bucket"], []).append(t)

    bucket_rows = [wp._combine_row(name, sb._score_bucket(new_by_bucket[name]),
                                   sb._score_bucket(old_by_bucket[name]))
                  for name in sorted(new_by_bucket)]
    pooled = wp._combine_row("pooled", sb._score_bucket(new_ticks), sb._score_bucket(old_ticks))

    doc: Dict[str, Any] = {
        "sport": "mlb", "benchmark": "live_kalshi_market_price",
        "model": "mlb_winprob_v4 (spec %s: %s)" % (
            bundle["winner"],
            "10-feature HistGB+prior, train=2024 only, isotonic on 2025" if bundle["winner"] == "a"
            else "8-feature state HistGB (train=2024+2025) + regularized per-phase logit-blend"),
        "baseline_model": "pooled in-game model (mlb_state_bucket_benchmark, commit 0eee3708)",
        "spec_selection": {
            "val_game_brier_spec_a": bundle["val_game_brier_spec_a"],
            "val_game_brier_spec_b": bundle["val_game_brier_spec_b"],
            "winner": bundle["winner"], "w_by_phase": bundle["w_by_phase"], "w_grid": list(W_GRID),
        },
        "feature_names": list(v3.FEATURE_NAMES_V3) if bundle["winner"] == "a" else list(feat.FEATURE_NAMES),
        "n_grade_files_mlb": counts["n_files"],
        "n_games_outcome_resolved": counts["n_games_resolved"],
        "n_games_outcome_unresolved": counts["n_games_unresolved"],
        "n_ticks_seen": counts["n_ticks_seen"],
        "n_ticks_missing_state_dropped": counts["n_ticks_missing_state"],
        "n_ticks_used": counts["n_ticks_used"],
        "prior_coverage_eval_2026": eval_prior_counts,
        "prior_coverage_2024": bundle["meta"]["prior_coverage_2024"],
        "prior_coverage_2025": bundle["meta"]["prior_coverage_2025"],
        "min_games_for_verdict": sb.MIN_GAMES,
        "buckets": bucket_rows, "pooled": pooled,
        "units": "probability (Brier/log-loss/ECE; no dollars)",
        "edge_claimed": False,
        "honest_note": (
            "Calibration/benchmark measurement only vs the LIVE market price, not a "
            "devigged close. Train band 2024+2025 (2024 has ZERO Polymarket prior rows on "
            "disk -- mlb_2024plus starts 2025-04-02 -- see prior_coverage_2024/2025). Spec "
            "(a) trains cleanly OOS (2024 train, 2025 val); spec (b)'s state model is fit "
            "on 2024+2025 POOLED so its own 2025 val/blend-selection score is partly "
            "in-sample -- flagged, not hidden, in this module's docstring LEAK AUDIT "
            "section. Selection by 2025 GAME-LEVEL Brier; the losing spec was never scored "
            "on 2026. Blend weight is grid-constrained ({0,.1,...,1.0}) per phase, chosen "
            "on GAME-clustered Brier -- the regularization v3's unconstrained per-tick "
            "2-coefficient fit lacked. No $/ROI/edge claim."),
        "calibration_scoreboard": {"per_sport": [{
            "sport": "mlb", "method": "mlb_winprob_v4_pooled",
            "n": pooled["n_ticks"],
            "baseline_brier": pooled["market"]["brier"] if pooled["market"] else None,
            "improved_brier": pooled["new_model"]["brier"] if pooled["new_model"] else None,
            "baseline_ece": pooled["market"]["ece"] if pooled["market"] else None,
            "improved_ece": pooled["new_model"]["ece"] if pooled["new_model"] else None,
        }]},
    }
    return doc


def save_model(bundle: Dict[str, Any], model_path: Optional[Path] = None,
              meta_path: Optional[Path] = None) -> Tuple[Path, Path]:
    """Save pkl + _meta.json; asserts fitted feature count == declared meta count."""
    p_pkl = Path(model_path) if model_path is not None else DEFAULT_MODEL_PATH
    p_meta = Path(meta_path) if meta_path is not None else DEFAULT_META_PATH
    p_pkl.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(bundle["meta"])
    meta["winner"] = bundle["winner"]
    if bundle["winner"] == "a":
        n_features_fit = int(getattr(bundle["clf_a"], "n_features_in_", len(v3.FEATURE_NAMES_V3)))
        assert n_features_fit == len(v3.FEATURE_NAMES_V3), (
            "mlb_winprob_v4 pkl/meta feature-count drift: fitted=%d meta=%d"
            % (n_features_fit, len(v3.FEATURE_NAMES_V3)))
        meta["n_features"] = len(v3.FEATURE_NAMES_V3)
        payload = {"spec": "a", "clf": bundle["clf_a"], "iso": bundle["iso_a"],
                  "feature_names": list(v3.FEATURE_NAMES_V3)}
    else:
        n_features_fit = int(getattr(bundle["clf_state"], "n_features_in_", len(feat.FEATURE_NAMES)))
        assert n_features_fit == len(feat.FEATURE_NAMES), (
            "mlb_winprob_v4 pkl/meta feature-count drift: fitted=%d meta=%d"
            % (n_features_fit, len(feat.FEATURE_NAMES)))
        meta["n_features"] = len(feat.FEATURE_NAMES)
        payload = {"spec": "b", "clf_state": bundle["clf_state"], "iso_state": bundle["iso_state"],
                  "w_by_phase": bundle["w_by_phase"], "feature_names": list(feat.FEATURE_NAMES)}
    with p_pkl.open("wb") as fh:
        pickle.dump(payload, fh)
    p_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")
    return p_pkl, p_meta


def write_benchmark(out_path: Optional[Path] = None, grade_dir: Optional[Path] = None,
                    resolver: Any = None, history_path: Optional[Path] = None,
                    data_dir: Optional[Path] = None, kalshi_dir: Optional[Path] = None) -> Dict[str, Any]:
    from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
    res = resolver if resolver is not None else MlbOutcomeResolver()
    bundle = train_specs(data_dir)
    doc = build_benchmark(bundle, grade_dir, res, kalshi_dir)
    out = out_path or DEFAULT_OUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out))
    try:
        from scripts.platformkit import scoreboard_history as sh
        sh.append_rows(source_path=out, history_path=history_path)
    except Exception as exc:  # noqa: BLE001 -- history append is best-effort
        logger.debug("write_benchmark: scoreboard_history append skipped: %s", exc)
    save_model(bundle)
    return doc


if __name__ == "__main__":
    result = write_benchmark()
    print(json.dumps({"spec_selection": result["spec_selection"], "pooled": result["pooled"],
                      "prior_coverage_2024": result["prior_coverage_2024"],
                      "prior_coverage_2025": result["prior_coverage_2025"],
                      "n_ticks_used": result["n_ticks_used"],
                      "honest_note": result["honest_note"]}, indent=2, ensure_ascii=True))

__all__ = [
    "DEFAULT_OUT_PATH", "DEFAULT_MODEL_PATH", "DEFAULT_META_PATH",
    "TRAIN_SEASON_A", "TRAIN_SEASONS_B", "VAL_SEASON", "PHASES", "W_GRID",
    "select_phase_weights", "train_specs", "build_benchmark", "save_model", "write_benchmark",
]
