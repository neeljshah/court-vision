"""conditional_gate -- per checkpoint, does the composed PREGAME prior improve
in-game win probability BEYOND score+time+Elo? Walk-forward, leak-free, DM-gated.

Same comparability discipline as compose.challenger / intel_weighting.relevance_gate
and it REUSES their fit/score/DM helpers -- base and candidate differ ONLY by the
composed-prior terms (same games, same temporal split, same optimizer):

  base offset = Elo PREGAME home-win logit (fixed coef 1, recalibrated by a
                fitted intercept -- reuse challenger._base_logit_nba).
  base design = [intercept, score_diff_z].
  candidate   = base design + composed prior diffs [off, conc, net, rest]_z
                (reuse challenger._feature_diffs / _standardize / team_form).

TIME NOTE (honest deviation from the literal {score_diff x sqrt(time_remaining)}
base spec): each checkpoint is scored in its OWN regression, so the
time-remaining fraction is a CONSTANT within a checkpoint and score_diff*sqrt(trf)
is exactly collinear with score_diff. The score_diff coefficient therefore
already absorbs the time weighting; we report that coefficient per checkpoint as
the score-information curve (it should rise Q1->Q4) rather than carry a redundant
collinear column. Time still enters across checkpoints via that changing coef.

Walk-forward: games with the checkpoint, date-ordered; train prefix (_TRAIN_FRAC)
fits everything, test suffix scored. Truncation: delta recomputed after dropping
the last 20% of the test window. "Beyond noise" = cluster-robust DM (by game_id).

Verdicts (relevance_gate names): MATTERS_PROVISIONAL / NULL / UNTESTABLE.
Single-fold within one season across 4 checkpoints x adding a 4-feature block ->
strongest verdict stays PROVISIONAL. NO dollar/edge language; Brier deltas only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.compose.challenger import (
    _base_logit_nba,
    _feature_diffs,
    _standardize,
)
from scripts.platformkit.compose.team_form import build_team_form
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.ingame_compose.checkpoints import (
    CHECKPOINTS,
    extract_checkpoints,
    final_home_margin,
)
from scripts.platformkit.intel_weighting.relevance_gate import (
    _DM_ALPHA,
    _MIN_TEST,
    _TRAIN_FRAC,
    _brier,
    _fit,
    _sigmoid,
)

_PRIOR_COLS = ["off", "conc", "net", "rest"]
METHOD = "ingame_compose_v1_walkforward"


@dataclass
class IngameGateResult:
    checkpoint: str
    trf: float                       # time-remaining fraction at the checkpoint
    n_games: int
    n_test: int
    brier_base: float
    brier_cond: float
    delta: float                     # base - cond (>0 => prior still helps)
    delta_trunc80: float
    dm_p: float
    verdict: str
    score_beta: float                # coef on score_diff_z (score-info weight)
    prior_beta_l2: float             # L2 norm of the 4 prior-diff betas
    prior_betas: Dict[str, float] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)


def score_checkpoint(checkpoint: str, trf: float, elo_logit: np.ndarray,
                     score_diff: np.ndarray, prior_diffs: pd.DataFrame,
                     y: np.ndarray, gid: np.ndarray) -> IngameGateResult:
    """Core scorer over ALREADY date-ordered arrays (data-free unit-testable).

    prior_diffs: DataFrame with _PRIOR_COLS raw home-away diffs, same order as
    the other arrays. Standardisation params come from the TRAIN prefix only."""
    n = len(y)
    n_tr = int(n * _TRAIN_FRAC)
    n_te = n - n_tr
    if n_te < _MIN_TEST:
        return IngameGateResult(checkpoint, trf, n, n_te, 0.0, 0.0, 0.0, 0.0, 1.0,
                                "UNTESTABLE", 0.0, 0.0, {},
                                [f"only {n_te} OOS games"])
    tr, te = slice(0, n_tr), slice(n_tr, n)

    feats = prior_diffs.copy()
    feats.insert(0, "score", score_diff)
    z = _standardize(feats, tr)                       # z-score on train prefix
    ones_tr, ones_te = np.ones((n_tr, 1)), np.ones((n_te, 1))
    yb = y[te]

    # base: Elo offset + intercept + score_diff. candidate: + prior diffs.
    base_tr = np.column_stack([ones_tr, z["score"].to_numpy()[tr]])
    base_te = np.column_stack([ones_te, z["score"].to_numpy()[te]])
    th_base = _fit(elo_logit[tr], base_tr, y[tr])
    p_base = _sigmoid(elo_logit[te] + base_te @ th_base)

    cand_tr = np.column_stack([base_tr] + [z[c].to_numpy()[tr] for c in _PRIOR_COLS])
    cand_te = np.column_stack([base_te] + [z[c].to_numpy()[te] for c in _PRIOR_COLS])
    th_cand = _fit(elo_logit[tr], cand_tr, y[tr])
    p_cond = _sigmoid(elo_logit[te] + cand_te @ th_cand)

    brier_base, brier_cond = _brier(p_base, yb), _brier(p_cond, yb)
    delta = brier_base - brier_cond
    d = (p_base - yb) ** 2 - (p_cond - yb) ** 2       # >0 => cond better
    dm_p = diebold_mariano(d, gid[te]).p_value
    cut = int(n_te * 0.8)
    delta_t80 = _brier(p_base[:cut], yb[:cut]) - _brier(p_cond[:cut], yb[:cut])

    prior_betas = {c: float(b) for c, b in zip(_PRIOR_COLS, th_cand[2:])}
    prior_l2 = float(np.linalg.norm(th_cand[2:]))
    if delta > 0 and dm_p < _DM_ALPHA and delta_t80 > 0:
        verdict = "MATTERS_PROVISIONAL"
        caveats = ["single-fold, one season, 4 checkpoints x a 4-feature block: "
                   "expected chance hits ~0.05*tests; stays PROVISIONAL until "
                   "replicated on an independent season/corpus"]
    else:
        verdict = "NULL"
        caveats = []
    return IngameGateResult(
        checkpoint, trf, n, n_te, round(brier_base, 6), round(brier_cond, 6),
        round(delta, 6), round(delta_t80, 6), round(dm_p, 4), verdict,
        round(float(th_base[1]), 4), round(prior_l2, 4),
        {k: round(v, 4) for k, v in prior_betas.items()}, caveats)


def _load_states(season: str = "2025-26"):
    """team_form (prior diffs + label + date + Elo logit) joined to per-game
    checkpoint states. Returns (tf_indexed, states_by_game, elo_by_game, skips).

    Games whose feed home/away orientation disagrees with games.parquet home_win
    (final-margin sign) are dropped and counted -- a flipped feed would corrupt
    score_diff, so we refuse it rather than trust it."""
    import json
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    pbp_dir = repo / "data" / "cache" / "team_system" / "pbp"

    tf = build_team_form(season)
    diffs = _feature_diffs(tf)
    tf = tf.assign(**{c: diffs[c] for c in _PRIOR_COLS})

    games_all, base_logit_all = _base_logit_nba()
    idx = games_all.reset_index().set_index("game_id")["index"]
    elo_by_game: Dict[str, float] = {}
    for g in tf["game_id"].astype(str):
        if g in idx.index:
            elo_by_game[g] = float(base_logit_all[int(idx[g])])

    states_by_game: Dict[str, Dict] = {}
    skips = {"no_pbp": 0, "orientation_flip": 0, "no_elo": 0}
    for g in tf["game_id"].astype(str):
        fp = pbp_dir / f"{g}.json"
        if not fp.exists():
            skips["no_pbp"] += 1
            continue
        if g not in elo_by_game:
            skips["no_elo"] += 1
            continue
        gj = json.loads(fp.read_text(encoding="utf-8"))
        hw = float(tf.loc[tf["game_id"].astype(str) == g, "home_win"].iloc[0])
        fm = final_home_margin(gj)
        if fm is not None and fm != 0 and (fm > 0) != (hw > 0.5):
            skips["orientation_flip"] += 1
            continue
        states_by_game[g] = extract_checkpoints(gj)
    return tf, states_by_game, elo_by_game, skips


def run_all_checkpoints(season: str = "2025-26"
                        ) -> tuple[List[IngameGateResult], Dict[str, int], Dict[str, int]]:
    """Score every checkpoint. Returns (results, per-checkpoint skip counts,
    global skip counts)."""
    tf, states, elo, glob_skips = _load_states(season)
    tf = tf.sort_values("date").reset_index(drop=True)
    gids = tf["game_id"].astype(str).to_numpy()

    results: List[IngameGateResult] = []
    cp_skips: Dict[str, int] = {}
    for cid, _t, trf in CHECKPOINTS:
        rows = []
        skipped = 0
        for i, g in enumerate(gids):
            if g not in states:      # orientation-flip / no-pbp -> in glob_skips
                continue
            st = states[g].get(cid)
            if st is None:           # genuine checkpoint-absence (never imputed)
                skipped += 1
                continue
            r = tf.iloc[i]
            rows.append((r["date"], g, float(r["home_win"]), elo[g], st.score_diff,
                         *[float(r[c]) for c in _PRIOR_COLS]))
        cp_skips[cid] = skipped
        if not rows:
            results.append(IngameGateResult(cid, trf, 0, 0, 0.0, 0.0, 0.0, 0.0, 1.0,
                                            "UNTESTABLE", 0.0, 0.0, {}, ["no games"]))
            continue
        rows.sort(key=lambda x: x[0])                 # date order (walk-forward)
        y = np.array([r[2] for r in rows], dtype=float)
        gid = np.array([r[1] for r in rows])
        elo_l = np.array([r[3] for r in rows], dtype=float)
        sdiff = np.array([r[4] for r in rows], dtype=float)
        pdf = pd.DataFrame([r[5:] for r in rows], columns=_PRIOR_COLS)
        results.append(score_checkpoint(cid, trf, elo_l, sdiff, pdf, y, gid))
    return results, cp_skips, glob_skips


if __name__ == "__main__":  # pragma: no cover - smoke
    res, cps, gs = run_all_checkpoints()
    for r in res:
        print(f"{r.checkpoint:8s} n={r.n_games:4d} te={r.n_test:4d} "
              f"base {r.brier_base:.5f} cond {r.brier_cond:.5f} "
              f"d {r.delta:+.5f} dm {r.dm_p:.4f} prior_l2 {r.prior_beta_l2:.3f} "
              f"score_b {r.score_beta:.3f} {r.verdict}")
    print("checkpoint skips", cps, "global skips", gs)
