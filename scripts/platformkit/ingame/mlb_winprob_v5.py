"""scripts.platformkit.ingame.mlb_winprob_v5 -- rung 5 of the MLB in-game win-prob
ladder. COMPOSITION test: does the REPLICATED PA-outcome machinery (domains/mlb/
matchup/pa_outcome_v2_replicate_2024.py, 31cbd3df -- platoon x pitch-type + as-of mix
features, 6/6 folds DM p=1e-4), composed UPWARD into a GAME-level pregame score, add
anything beyond the state model alone? See mlb_winprob_v5_composite.py's docstring for
why that composition is a TEAM-level fallback (no lineups, no 2025/2026 statcast IDs)
built from the SAME mlb_pitch_states corpus the state model itself trains on.

LADDER SO FAR: pooled model (0eee3708, 0.2292 vs market 0.1898) -> v2 (3aac11e8,
state-only, REJECT: OOD-overconfident) -> v3 (57c1c696, unregularized prior blend,
REJECT) -> v4 (spec-b's state classifier was fit on 2024+2025 POOLED, so its own 2025
selection score was partly in-sample -- a named PROTOCOL FLAW). RUNG 5 fixes the
protocol directly (BINDING PROTOCOL below) rather than re-litigating the blend math.

BINDING PROTOCOL (both specs identically): TRAIN_SEASONS=(2022,2023,2024) ONLY ever
enters a classifier's OWN .fit() (fixed constant, never 2025; feat.FORBIDDEN_
TRAIN_SEASONS already hard-blocks 2026 -- see test_matched_oos_guard). VAL_SEASON=2025
is used ONLY for isotonic calibration + the scalar blend-weight grid search (both
GAME-level, explicitly permitted as calibration params, never as training rows).
EVAL=2026 (live_grade corpus), scored exactly once, by the winner only.

SPECS (K=2): (a) "composite-as-feature" -- v2's 8 state features (mlb_winprob_v2_
features, unchanged) + pa_composite + has_composite (mlb_winprob_v5_composite) as a
fresh 10-feature HistGB, TRAIN_SEASONS-only fit, isotonic on VAL_SEASON. (b)
"composite-as-logit-offset" -- the SAME 8-feature state HistGB (mlb_winprob_v2.
train_model, TRAIN_SEASONS/VAL_SEASON -- ALSO reused as this module's 2nd baseline,
"v2 state model") blended as p_adj = sigmoid(logit(p_state) + w*pa_composite), w on
the declared grid {0,.05,...,.5} chosen by VAL_SEASON GAME-level Brier. Rows with no
composite coverage carry pa_composite=0.0, so the offset is a no-op for them
regardless of w -- never a fabricated lean.

SELECTION: lower VAL_SEASON GAME-level Brier wins (game_level_brier, reused from v4).
The state-alone Brier (w=0/no composite) is ALSO recorded on VAL_SEASON as the
ablation anchor answering "did composition add beyond state" for whichever spec wins.
The losing spec is never scored on 2026.

EVAL (2026, winner only): pooled + per-bucket (state_bucket_benchmark phase|margin)
Brier/log-loss/ECE for NEW(winner) vs OLD(pooled model, 0eee3708) vs V2(state-only,
the SAME clf_state/iso_state fit above) vs MARKET -- three baselines, since the
mission asks whether composition beats state ALONE, not just the old pooled model.

HONESTY: calibration measurement only; edge_claimed always False; no $/ROI field. NO
LIVE WIRING. A NULL (composition adds nothing beyond state) is a real finding about
WHERE MLB intelligence must enter (deeper in-game state, not a pregame team
composite) -- reported plainly.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import; OMP/BLAS
threads capped to 4; never writes data/registry/; never flips a flag; never edits src/
kernel/ api/ intel/ scripts/team_system/ or the v2/v3/v4 modules/live_grade.py/
state_bucket_benchmark.py; parquets/jsonl READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v5.py -q
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
import scripts.platformkit.ingame.mlb_winprob_v5_composite as comp
import scripts.platformkit.ingame.state_bucket_benchmark as sb
from scripts.platformkit.ingame.mlb_winprob_v3_prior import _logit
from scripts.platformkit.ingame.mlb_winprob_v4_blend import game_level_brier

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "mlb_winprob_v5_benchmark.json"
DEFAULT_MODEL_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_winprob_v5.pkl"
DEFAULT_META_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_winprob_v5_meta.json"

TRAIN_SEASONS: Tuple[int, ...] = (2022, 2023, 2024)  # ONLY band any classifier .fit() may see
VAL_SEASON = 2025                                    # calibration/blend-weight selection ONLY
COMPOSITE_SEASONS: Tuple[int, ...] = (2022, 2023, 2024, 2025, 2026)
W_GRID: Tuple[float, ...] = tuple(round(i * 0.05, 2) for i in range(11))  # 0, .05, ..., .5
FEATURE_NAMES_V5: Tuple[str, ...] = tuple(feat.FEATURE_NAMES) + ("pa_composite", "has_composite")


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def _aligned(df: Any) -> Any:
    """Same row mask feat.train_xy applies internally (parseable half_inning_label),
    exposed here so pa_composite/game_id stay row-aligned with feat.train_xy's X/y."""
    if df.empty:
        return df
    half = df["half_inning_label"].astype(str).str.extract(r"^(top|bottom)(\d+)$")
    return df.loc[half[1].notna()].reset_index(drop=True)


# -- train both specs on TRAIN_SEASONS only, select by VAL_SEASON GAME-level Brier -- #
def train_specs(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    assert set(TRAIN_SEASONS) <= {2022, 2023, 2024}, (
        "mlb_winprob_v5 protocol violation: TRAIN_SEASONS must stay <=2024")
    daily = comp.build_team_daily_asof(COMPOSITE_SEASONS, data_dir)
    train_df, missing_train = feat.load_training_seasons(TRAIN_SEASONS, data_dir)
    val_df, missing_val = feat.load_training_seasons((VAL_SEASON,), data_dir)
    train_a = _aligned(comp.attach_composite_train(train_df, daily))
    val_a = _aligned(comp.attach_composite_train(val_df, daily))
    X8tr, ytr, _ = feat.train_xy(train_a)
    X8val, yval, _ = feat.train_xy(val_a)
    gid_val = val_a["game_id"].astype(str).to_numpy() if len(val_a) else np.zeros(0)

    # -- spec a: 10-feature HGB (state + composite), fit TRAIN_SEASONS only -- #
    extra_tr = train_a[["pa_composite", "has_composite"]].astype(float).to_numpy() if len(train_a) else np.zeros((0, 2))
    extra_val = val_a[["pa_composite", "has_composite"]].astype(float).to_numpy() if len(val_a) else np.zeros((0, 2))
    X9tr = np.column_stack([X8tr, extra_tr]) if len(X8tr) else np.zeros((0, len(FEATURE_NAMES_V5)))
    X9val = np.column_stack([X8val, extra_val]) if len(X8val) else np.zeros((0, len(FEATURE_NAMES_V5)))
    clf_a = HistGradientBoostingClassifier(random_state=42)
    if len(X9tr):
        clf_a.fit(X9tr, ytr)
    iso_a = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    if len(X9val):
        iso_a.fit(clf_a.predict_proba(X9val)[:, 1], yval)
    else:
        iso_a.fit([0.0, 1.0], [0.0, 1.0])
    probs_a_val = wp.predict_proba(clf_a, iso_a, X9val)
    brier_a = game_level_brier(probs_a_val, yval, gid_val) if len(X9val) else float("nan")

    # -- spec b (+ this module's 2nd baseline): shared 8-feature state HGB, TRAIN_SEASONS only -- #
    clf_state, iso_state, meta_state = wp.train_model(TRAIN_SEASONS, VAL_SEASON, data_dir)
    p_state_val = wp.predict_proba(clf_state, iso_state, X8val)
    pa_val = val_a["pa_composite"].astype(float).to_numpy() if len(val_a) else np.zeros(0)
    state_alone_brier = game_level_brier(p_state_val, yval, gid_val) if len(X8val) else float("nan")
    best_w, best_b = 0.0, state_alone_brier
    for w in W_GRID:
        probs_b = _sigmoid(_logit(p_state_val) + w * pa_val) if len(p_state_val) else np.zeros(0)
        b = game_level_brier(probs_b, yval, gid_val) if len(probs_b) else float("nan")
        if not math.isnan(b) and b < best_b:
            best_b, best_w = b, w
    brier_b = best_b
    candidates = [(n, b) for n, b in (("a", brier_a), ("b", brier_b)) if not math.isnan(b)]
    winner = min(candidates, key=lambda kv: kv[1])[0] if candidates else "a"

    return {
        "clf_a": clf_a, "iso_a": iso_a, "clf_state": clf_state, "iso_state": iso_state,
        "best_w": best_w, "winner": winner, "daily": daily,
        "val_game_brier_spec_a": brier_a, "val_game_brier_spec_b": brier_b,
        "val_game_brier_state_alone": state_alone_brier,
        "meta": {"train_seasons": list(TRAIN_SEASONS), "val_season": VAL_SEASON,
                 "missing_train_seasons": missing_train, "missing_val_season": missing_val,
                 "composite_seasons": list(COMPOSITE_SEASONS), "w_grid": list(W_GRID)},
    }

# -- eval on the 2026 grade corpus (winner only, + v2-state as a 2nd baseline) -- #
def build_benchmark(bundle: Dict[str, Any], grade_dir: Optional[Path] = None,
                    resolver: Any = None) -> Dict[str, Any]:
    ticks, counts = wp.build_eval_ticks(grade_dir, resolver)
    ticks = comp.attach_composite_eval(ticks, bundle["daily"])
    v2_probs = wp.score_new_model(bundle["clf_state"], bundle["iso_state"], ticks)
    if bundle["winner"] == "a":
        X9 = np.array([[t[f] for f in feat.FEATURE_NAMES] + [t["pa_composite"], float(t["has_composite"])]
                       for t in ticks], dtype=float) if ticks else np.zeros((0, len(FEATURE_NAMES_V5)))
        winner_probs = wp.predict_proba(bundle["clf_a"], bundle["iso_a"], X9)
    else:
        pa_e = np.array([t["pa_composite"] for t in ticks], dtype=float)
        winner_probs = _sigmoid(_logit(v2_probs) + bundle["best_w"] * pa_e) if len(v2_probs) else np.zeros(0)

    new_ticks = [dict(t, model_prob=float(p)) for t, p in zip(ticks, winner_probs)]
    old_ticks = [dict(t, model_prob=t["old_model_prob"]) for t in ticks]
    v2_ticks = [dict(t, model_prob=float(p)) for t, p in zip(ticks, v2_probs)]
    new_bb: Dict[str, List[Dict[str, Any]]] = {}
    old_bb: Dict[str, List[Dict[str, Any]]] = {}
    v2_bb: Dict[str, List[Dict[str, Any]]] = {}
    for t in new_ticks:
        new_bb.setdefault(t["bucket"], []).append(t)
    for t in old_ticks:
        old_bb.setdefault(t["bucket"], []).append(t)
    for t in v2_ticks:
        v2_bb.setdefault(t["bucket"], []).append(t)
    bucket_rows = [comp.combine_row3(name, sb._score_bucket(new_bb[name]), sb._score_bucket(old_bb[name]),
                                     sb._score_bucket(v2_bb[name])) for name in sorted(new_bb)]
    pooled = comp.combine_row3("pooled", sb._score_bucket(new_ticks), sb._score_bucket(old_ticks),
                               sb._score_bucket(v2_ticks))
    spec_key = "val_game_brier_spec_a" if bundle["winner"] == "a" else "val_game_brier_spec_b"
    composition_beyond_state = bundle[spec_key] < bundle["val_game_brier_state_alone"]
    doc: Dict[str, Any] = {
        "sport": "mlb", "benchmark": "live_kalshi_market_price",
        "model": "mlb_winprob_v5 (spec %s: %s)" % (
            bundle["winner"],
            "10-feature HistGB (state+composite), TRAIN_SEASONS-only fit, isotonic on VAL_SEASON"
            if bundle["winner"] == "a" else
            "8-feature state HGB + scalar logit-offset composite blend (w=%.2f)" % bundle["best_w"]),
        "baseline_model_pooled": "pooled in-game model (mlb_state_bucket_benchmark, commit 0eee3708)",
        "baseline_model_v2_state": "mlb_winprob_v2 state-only model (SAME clf_state/iso_state used here)",
        "spec_selection": {
            "val_game_brier_spec_a": bundle["val_game_brier_spec_a"],
            "val_game_brier_spec_b": bundle["val_game_brier_spec_b"],
            "val_game_brier_state_alone": bundle["val_game_brier_state_alone"],
            "winner": bundle["winner"], "best_w": bundle["best_w"], "w_grid": list(W_GRID),
            "composition_beat_state_alone_on_val": composition_beyond_state,
        },
        "feature_names": list(FEATURE_NAMES_V5) if bundle["winner"] == "a" else list(feat.FEATURE_NAMES),
        "n_grade_files_mlb": counts["n_files"], "n_games_outcome_resolved": counts["n_games_resolved"],
        "n_games_outcome_unresolved": counts["n_games_unresolved"], "n_ticks_seen": counts["n_ticks_seen"],
        "n_ticks_missing_state_dropped": counts["n_ticks_missing_state"], "n_ticks_used": counts["n_ticks_used"],
        "min_games_for_verdict": sb.MIN_GAMES, "buckets": bucket_rows, "pooled": pooled,
        "units": "probability (Brier/log-loss/ECE; no dollars)", "edge_claimed": False,
        "honest_note": (
            "Calibration/benchmark measurement only vs the LIVE market price, not a devigged "
            "close. TRAIN_SEASONS=2022-2024 ONLY entered any classifier's own .fit(); VAL_SEASON "
            "2025 used only for isotonic calibration + the w grid search (both GAME-level), never "
            "for training -- fixes v4's named protocol flaw. pa_composite is a TEAM-level fallback "
            "(no lineups/no 2025-2026 statcast IDs on disk; see mlb_winprob_v5_composite.py), not "
            "the literal batter-vs-pitcher REPLICATED machinery. "
            "composition_beat_state_alone_on_val=%s -- %s. No $/ROI/edge claim." % (
                composition_beyond_state,
                "the composite feature/offset improved on VAL_SEASON GAME-level Brier vs the "
                "state model alone" if composition_beyond_state else
                "composition added NOTHING beyond the state model on VAL_SEASON -- an honest NULL: "
                "MLB intelligence needs to enter deeper in-game state, not a pregame team "
                "composite")),
        "calibration_scoreboard": {"per_sport": [{
            "sport": "mlb", "method": "mlb_winprob_v5_pooled", "n": pooled["n_ticks"],
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
        n_fit = int(getattr(bundle["clf_a"], "n_features_in_", len(FEATURE_NAMES_V5)))
        assert n_fit == len(FEATURE_NAMES_V5), (
            "mlb_winprob_v5 pkl/meta feature-count drift: fitted=%d meta=%d" % (n_fit, len(FEATURE_NAMES_V5)))
        meta["n_features"] = len(FEATURE_NAMES_V5)
        payload = {"spec": "a", "clf": bundle["clf_a"], "iso": bundle["iso_a"],
                  "feature_names": list(FEATURE_NAMES_V5)}
    else:
        n_fit = int(getattr(bundle["clf_state"], "n_features_in_", len(feat.FEATURE_NAMES)))
        assert n_fit == len(feat.FEATURE_NAMES), (
            "mlb_winprob_v5 pkl/meta feature-count drift: fitted=%d meta=%d" % (n_fit, len(feat.FEATURE_NAMES)))
        meta["n_features"] = len(feat.FEATURE_NAMES)
        payload = {"spec": "b", "clf_state": bundle["clf_state"], "iso_state": bundle["iso_state"],
                  "best_w": bundle["best_w"], "feature_names": list(feat.FEATURE_NAMES)}
    with p_pkl.open("wb") as fh:
        pickle.dump(payload, fh)
    p_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")
    return p_pkl, p_meta


def write_benchmark(out_path: Optional[Path] = None, grade_dir: Optional[Path] = None,
                    resolver: Any = None, history_path: Optional[Path] = None,
                    data_dir: Optional[Path] = None) -> Dict[str, Any]:
    from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
    res = resolver if resolver is not None else MlbOutcomeResolver()
    bundle = train_specs(data_dir)
    doc = build_benchmark(bundle, grade_dir, res)
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
                      "n_ticks_used": result["n_ticks_used"], "honest_note": result["honest_note"]},
                     indent=2, ensure_ascii=True))

__all__ = [
    "DEFAULT_OUT_PATH", "DEFAULT_MODEL_PATH", "DEFAULT_META_PATH", "TRAIN_SEASONS",
    "VAL_SEASON", "COMPOSITE_SEASONS", "W_GRID", "FEATURE_NAMES_V5",
    "train_specs", "build_benchmark", "save_model", "write_benchmark",
]
