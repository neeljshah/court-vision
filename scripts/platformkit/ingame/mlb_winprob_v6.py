"""scripts.platformkit.ingame.mlb_winprob_v6 -- RUNG 6 of the MLB in-game win-prob
ladder: the LITERAL named-batter-vs-pitcher composition (task 44). Rung 5 (2cb54695)
tested a TEAM-level pitch-mix composite and the VAL w-grid picked w=0 (added NOTHING
beyond state). Rung 6 swaps in the sharper hypothesis and NOTHING else: a per-GAME win
prob built from the ACTUAL nine named batters vs the opposing starter's as-of profile,
chained through the pitch_engine game Monte-Carlo (domains.mlb.pitch_engine.
rung6_composite). Player IDENTITY -- the diagnosed missing ingredient.

BINDING MATCHED-OOS PROTOCOL (identical to rung 5, differs ONLY by the composite):
  BASE      = mlb_winprob_v2 state HGB, TRAIN_SEASONS=(2022,2023,2024) ONLY in .fit(),
              isotonic on VAL_SEASON=2025. NO composite. (== rung 5 spec-b baseline.)
  CANDIDATE = the SAME state model + scalar logit-offset of the named-lineup composite:
              p_adj = sigmoid(logit(p_state) + w*pa_composite). w on the declared grid
              {0,.05,..,.5} chosen by VAL_SEASON GAME-level Brier (a calibration param,
              never a training row). Rows with no composite carry pa_composite=0.0 so
              the offset is a no-op there -- never a fabricated lean.
Only SPEC-B is run (not rung 5's spec-a feature form): the composite needs per-game
lineups, and mlb_lineups/savant give them for 2025/2026 but NOT the 2022-2024 TRAIN
band, so a train-side feature would be all-missing on the fit seasons. Spec-b selects w
on VAL 2025 (which HAS lineups) and never feeds the composite to the classifier -- so
it is exactly comparable to BASE and needs no train-season lineups.

VERDICT (honest): best_w==0 -> REJECT (composition adds nothing even on the selection
season). best_w>0 -> the real test is the EVAL(2026) grade corpus: a PAIRED,
GAME-CLUSTERED bootstrap of (base_brier - candidate_brier); AHEAD only if the 95% CI
lower bound > 0. Anything else is MATCH/NULL -- an honest REJECT, a real finding about
where MLB in-game intelligence must enter. Scored vs the LIVE market price; no devig,
no $/ROI, edge_claimed=False. NO LIVE WIRING regardless of verdict.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; OMP/BLAS<=4; never writes
data/registry/; never flips a flag; never edits src/kernel/api/intel/team_system or the
v2-v5 modules/live_grade.py/state_bucket_benchmark.py; parquets/jsonl READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v6.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

import scripts.platformkit.ingame.mlb_winprob_v2 as wp
import scripts.platformkit.ingame.mlb_winprob_v2_features as feat
import scripts.platformkit.ingame.mlb_winprob_v5_composite as comp
import scripts.platformkit.ingame.state_bucket_benchmark as sb
from domains.mlb.pitch_engine import rung6_composite as r6
from scripts.platformkit.ingame.mlb_winprob_v3_prior import _logit
from scripts.platformkit.ingame.mlb_winprob_v4_blend import game_level_brier

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "mlb_winprob_v6_benchmark.json"

TRAIN_SEASONS: Tuple[int, ...] = (2022, 2023, 2024)
VAL_SEASON = 2025
W_GRID: Tuple[float, ...] = tuple(round(i * 0.05, 2) for i in range(11))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def _aligned(df: Any) -> Any:
    """Same row mask feat.train_xy applies internally, so pa_composite stays aligned."""
    if df.empty:
        return df
    half = df["half_inning_label"].astype(str).str.extract(r"^(top|bottom)(\d+)$")
    return df.loc[half[1].notna()].reset_index(drop=True)


def paired_game_bootstrap(base_p: np.ndarray, cand_p: np.ndarray, y: np.ndarray,
                          gids: Sequence[str], n_boot: int = 2000, seed: int = 13
                          ) -> Dict[str, Any]:
    """Game-clustered paired bootstrap of (base_brier - cand_brier). Positive => the
    candidate is BETTER (lower Brier). Verdict AHEAD iff CI95 low > 0."""
    y = np.asarray(y, float)
    bb = (base_p - y) ** 2
    cb = (cand_p - y) ** 2
    gids = np.asarray([str(g) for g in gids])
    uniq = np.unique(gids)
    idx_by_g = {g: np.nonzero(gids == g)[0] for g in uniq}
    point = float(bb.mean() - cb.mean())
    if len(uniq) < sb.MIN_GAMES:
        return {"verdict": "INSUFFICIENT", "delta_brier": point, "ci95": None,
                "n_games": int(len(uniq))}
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for k in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        rows = np.concatenate([idx_by_g[g] for g in pick])
        diffs[k] = bb[rows].mean() - cb[rows].mean()
    lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
    verdict = "AHEAD" if lo > 0 else ("BEHIND" if hi < 0 else "MATCH")
    return {"verdict": verdict, "delta_brier": point, "ci95": [lo, hi],
            "n_games": int(len(uniq))}


def train(data_dir: Optional[Path] = None, cache_path: Optional[Path] = None,
          n_sims: int = 1200) -> Dict[str, Any]:
    """Fit BASE state model (2022-2024, iso 2025); select w on VAL 2025 game Brier."""
    assert set(TRAIN_SEASONS) <= {2022, 2023, 2024}, "v6 protocol: TRAIN must stay <=2024"
    table = r6.load_or_build(cache_path, n_sims=n_sims)
    clf_state, iso_state, meta_state = wp.train_model(TRAIN_SEASONS, VAL_SEASON, data_dir)
    val_df, missing_val = feat.load_training_seasons((VAL_SEASON,), data_dir)
    val_a = _aligned(r6.attach_composite_train(val_df, table))
    X8val, yval, _ = feat.train_xy(val_a)
    gid_val = val_a["game_id"].astype(str).to_numpy() if len(val_a) else np.zeros(0)
    pa_val = val_a["pa_composite"].astype(float).to_numpy() if len(val_a) else np.zeros(0)
    n_val_cov = int(val_a["has_composite"].sum()) if len(val_a) else 0
    p_state_val = wp.predict_proba(clf_state, iso_state, X8val)
    state_alone = game_level_brier(p_state_val, yval, gid_val) if len(X8val) else float("nan")
    best_w, best_b = 0.0, state_alone
    for w in W_GRID:
        pb = _sigmoid(_logit(p_state_val) + w * pa_val) if len(p_state_val) else np.zeros(0)
        b = game_level_brier(pb, yval, gid_val) if len(pb) else float("nan")
        if not math.isnan(b) and b < best_b:
            best_b, best_w = b, w
    return {"clf_state": clf_state, "iso_state": iso_state, "table": table,
            "best_w": best_w, "val_game_brier_candidate": best_b,
            "val_game_brier_state_alone": state_alone,
            "meta": {"train_seasons": list(TRAIN_SEASONS), "val_season": VAL_SEASON,
                     "w_grid": list(W_GRID), "n_val_rows": int(len(X8val)),
                     "n_val_games_composite_covered": n_val_cov,
                     "missing_val_season": missing_val}}


def build_benchmark(bundle: Dict[str, Any], grade_dir: Optional[Path] = None,
                    resolver: Any = None) -> Dict[str, Any]:
    from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
    res = resolver if resolver is not None else MlbOutcomeResolver()
    ticks, counts = wp.build_eval_ticks(grade_dir, res)
    ticks = r6.attach_composite_eval(ticks, bundle["table"])
    base_probs = wp.score_new_model(bundle["clf_state"], bundle["iso_state"], ticks)
    pa_e = np.array([t["pa_composite"] for t in ticks], dtype=float) if ticks else np.zeros(0)
    cand_probs = (_sigmoid(_logit(base_probs) + bundle["best_w"] * pa_e)
                  if len(base_probs) else np.zeros(0))
    y = np.array([t["outcome"] for t in ticks], dtype=float) if ticks else np.zeros(0)
    gids = [t["game_id"] for t in ticks]
    n_cov = int(sum(1 for t in ticks if t.get("has_composite")))

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
    bucket_rows = [comp.combine_row3(name, sb._score_bucket(nb[name]), sb._score_bucket(ob[name]),
                                     sb._score_bucket(vb[name])) for name in sorted(nb)]
    pooled = comp.combine_row3("pooled", sb._score_bucket(new_ticks), sb._score_bucket(old_ticks),
                               sb._score_bucket(base_ticks))
    paired = paired_game_bootstrap(base_probs, cand_probs, y, gids)
    # per-phase (early/mid/late) candidate-vs-base paired CI + worst-bucket naming
    phase_paired: Dict[str, Any] = {}
    for name in sorted(nb):
        idx = [i for i, t in enumerate(ticks) if t["bucket"] == name]
        if not idx:
            continue
        phase_paired[name] = paired_game_bootstrap(
            base_probs[idx], cand_probs[idx], y[idx], [gids[i] for i in idx])
    worst = None
    scored = {k: v for k, v in phase_paired.items() if v.get("ci95")}
    if scored:
        worst = min(scored, key=lambda k: scored[k]["delta_brier"])

    val_helps = bundle["best_w"] > 0 and (
        bundle["val_game_brier_candidate"] < bundle["val_game_brier_state_alone"])
    verdict = "REJECT"
    if val_helps and paired["verdict"] == "AHEAD":
        verdict = "AHEAD"
    elif val_helps and paired["verdict"] == "MATCH":
        verdict = "MATCH"
    doc: Dict[str, Any] = {
        "sport": "mlb", "rung": 6, "benchmark": "live_kalshi_market_price",
        "model": "mlb_winprob_v6 (state HGB + named-lineup PA-chain composite offset, w=%.2f)"
                 % bundle["best_w"],
        "hypothesis": "literal named-batter-vs-pitcher composition (pitch_engine game MC)",
        "verdict": verdict,
        "candidate_vs_base_paired": paired,
        "candidate_vs_base_per_phase": phase_paired,
        "worst_phase_bucket": worst,
        "selection": {"best_w": bundle["best_w"], "w_grid": list(W_GRID),
                      "val_game_brier_candidate": bundle["val_game_brier_candidate"],
                      "val_game_brier_state_alone": bundle["val_game_brier_state_alone"],
                      "composition_beat_state_on_val": val_helps},
        "n_grade_files_mlb": counts["n_files"], "n_games_resolved": counts["n_games_resolved"],
        "n_ticks_used": counts["n_ticks_used"], "n_ticks_composite_covered": n_cov,
        "min_games_for_verdict": sb.MIN_GAMES, "buckets": bucket_rows, "pooled": pooled,
        "units": "probability (Brier/log-loss/ECE; no dollars)", "edge_claimed": False,
        "meta": bundle["meta"],
        "honest_note": (
            "Calibration measurement only vs the LIVE market price (not a devig close). "
            "Matched-OOS: state HGB fit 2022-2024, isotonic 2025; the named-lineup "
            "composite differs from rung 5 ONLY in using literal batter identity, and w "
            "is selected on VAL 2025 game-level Brier, never on 2026. AHEAD requires the "
            "PAIRED game-clustered EVAL CI lower bound > 0. No $/ROI/edge claim."),
    }
    return doc


def write_benchmark(out_path: Optional[Path] = None, grade_dir: Optional[Path] = None,
                    resolver: Any = None, data_dir: Optional[Path] = None,
                    cache_path: Optional[Path] = None, n_sims: int = 1200) -> Dict[str, Any]:
    bundle = train(data_dir, cache_path, n_sims=n_sims)
    doc = build_benchmark(bundle, grade_dir, resolver)
    out = out_path or DEFAULT_OUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out))
    return doc


if __name__ == "__main__":
    result = write_benchmark()
    print(json.dumps({"verdict": result["verdict"], "selection": result["selection"],
                      "candidate_vs_base_paired": result["candidate_vs_base_paired"],
                      "worst_phase_bucket": result["worst_phase_bucket"],
                      "pooled_new_vs_market": result["pooled"]["new_vs_market"],
                      "pooled_base_vs_market": result["pooled"]["v2_state_vs_market"],
                      "n_ticks_used": result["n_ticks_used"],
                      "n_ticks_composite_covered": result["n_ticks_composite_covered"]},
                     indent=2, ensure_ascii=True))

__all__ = ["DEFAULT_OUT_PATH", "TRAIN_SEASONS", "VAL_SEASON", "W_GRID",
           "paired_game_bootstrap", "train", "build_benchmark", "write_benchmark"]
