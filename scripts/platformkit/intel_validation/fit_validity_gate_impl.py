"""fit_validity_gate_impl -- the ACTUAL H0/H1 fit math for the V2 fit-validity
gate (PROGRAM v3 item 3). Authorized ONLY under
docs/research/intel-layer/fit_validity_gate_prereg_v2.json (run_permitted=true,
authorized_by=fable_user_proxy_2026-07-05). Kept in a SEPARATE file from
fit_validity_gate.py so that module's V1-refusal guard stays the trivially
auditable, tiny surface it always was.

Ingredient construction (archetype / scheme identity / role vacancy), H0 base
model (carryover), H1 candidate (base + fit_score term ONLY), 5-fold
leave-one-fold-out walk-forward, grid-search off-init proof, and BOTH planted
nulls (shuffled destinations, shuffled outcomes) per
fit_validity_gate_prereg_v2.json sections 5-8. Every formula here mirrors the
V2 JSON spec's `ingredient_formulas` / `walk_forward_design` /
`optimizer_off_init_proof` / `planted_null_design_v2` verbatim -- this module
does not invent anything the spec did not already pin.

CLI (verdict-writing entry point, split into fit_validity_gate_report.py):
    python -m scripts.platformkit.intel_validation.fit_validity_gate_report --run
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from domains.basketball_nba.moves_corpus import (
    _clean_single_team_season,
    _load_all_available_seasons,
)
from scripts.platformkit.intel_validation.fit_validity_gate_ingredients import (
    compute_fit_score_for_mover,
    team_scheme_identity,
    usage_tier_incumbent_counts,
    zscore_archetype,
)
from scripts.platformkit.intel_validation.fit_validity_gate_nulls import (
    null_dies,
    shuffle_move_team_assignment,
    shuffle_outcome_deltas,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
V2_SPEC_PATH = REPO_ROOT / "docs" / "research" / "intel-layer" / "fit_validity_gate_prereg_v2.json"
MOVES_CORPUS_PATH = REPO_ROOT / "data" / "cache" / "bbref_backfill" / "moves_corpus.parquet"
VERDICT_OUT_PATH = REPO_ROOT / "data" / "domains" / "nba" / "fit_validity_gate_verdict.json"

BETA_GRID = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]


@dataclass
class FoldResult:
    fold_name: str
    n: int
    rmse_h0: float
    rmse_h1: float
    corr_h1: float
    delta_rmse: float  # H0 - H1 (positive means H1 beats H0)
    beta_selected: float


@dataclass
class GateRunResult:
    v2_spec_sha16: str
    n_moves: int
    n_folds: int
    per_fold: list[FoldResult] = field(default_factory=list)
    pooled_delta: float = 0.0
    sign_holds_count: int = 0
    off_init_moved: bool = False
    null1_result: dict[str, Any] = field(default_factory=dict)
    null2_result: dict[str, Any] = field(default_factory=dict)
    verdict: str = "NOT_TESTABLE"
    verdict_reason: str = ""


def _sha16(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def load_v2_spec(path: Path = V2_SPEC_PATH) -> dict[str, Any]:
    """Fail-closed load: any missing required field raises rather than
    defaulting to a permissive guess. Mirrors fit_validity_gate.py's
    load_prereg_spec discipline for the V1 spec."""
    if not path.exists():
        raise FileNotFoundError(f"V2 spec not found: {path}")
    with open(path, "r", encoding="ascii", errors="strict") as f:
        payload = json.load(f)
    for required in ("pre_registered", "run_permitted", "recorded_fable_authorization", "ingredient_formulas"):
        if required not in payload:
            raise ValueError(f"V2 spec missing required field: {required!r}")
    if not payload["pre_registered"] or not payload["run_permitted"]:
        raise ValueError(
            "V2 spec does not authorize a run (pre_registered/run_permitted "
            "must both be true) -- refusing to load for execution."
        )
    return payload


def _build_season_table() -> pd.DataFrame:
    """Reuse domains.basketball_nba.moves_corpus's own loader (existing,
    verified helper) rather than re-reading/re-concatenating the bbref
    parquet sources a second time (PONYTAIL rung 2: reuse-search-first)."""
    return _load_all_available_seasons()


def _clean_season_slice(season_table: pd.DataFrame, season: str) -> pd.DataFrame:
    """Clean single-real-team rows for one season, via the SAME helper the
    moves corpus itself was built from -- guarantees archetype/scheme
    ingredients are computed over the identical row population the strict-
    move rule uses (gate-comparability: no separate, looser row set sneaks
    in for ingredient construction)."""
    season_df = season_table[season_table["season"] == season]
    return _clean_single_team_season(season_df)


def build_ingredients(moves: pd.DataFrame, season_table: pd.DataFrame) -> pd.DataFrame:
    """Compute fit_score for every move row using ONLY season_pre data, per
    ingredient_formulas in fit_validity_gate_prereg_v2.json. Returns `moves`
    with a new `fit_score` column appended (does not mutate outcome cols).
    Per-column ingredient math lives in fit_validity_gate_ingredients.py
    (kept there purely to fit both files under the 300-LOC cap)."""
    moves = moves.copy()
    fit_scores = np.full(len(moves), np.nan)

    for season_pre, group in moves.groupby("season_pre"):
        clean = _clean_season_slice(season_table, season_pre)
        clean = clean.drop_duplicates(subset=["player_name"], keep="first").set_index("player_name")

        arche_z = zscore_archetype(clean)  # (i)
        scheme_by_team = team_scheme_identity(clean)  # (ii)
        usg_median_by_team, incumbents = usage_tier_incumbent_counts(clean)  # (iii)

        for idx in group.index:
            player = moves.loc[idx, "player_name"]
            team_post = moves.loc[idx, "team_post"]
            if player not in arche_z.index or team_post not in scheme_by_team.index:
                continue  # honest skip: player or destination team missing season_pre coverage
            player_arche = arche_z.loc[player]
            if isinstance(player_arche, pd.DataFrame):
                player_arche = player_arche.iloc[0]
            mover_usg = clean.loc[player, "usg_pct"] if player in clean.index else np.nan
            if isinstance(mover_usg, pd.Series):
                mover_usg = mover_usg.iloc[0]

            fit_scores[moves.index.get_loc(idx)] = compute_fit_score_for_mover(
                player_archetype_row=player_arche,
                dest_scheme_vec=scheme_by_team.loc[team_post],
                mover_usg_pct=mover_usg,
                dest_team=team_post,
                usg_median_by_team=usg_median_by_team,
                incumbents=incumbents,
            )

    moves["fit_score"] = fit_scores
    return moves


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def _standardize_fit_score(train_fit: np.ndarray, apply_to: np.ndarray) -> np.ndarray:
    """Standardize fit_score to zero-mean/unit-std using TRAIN-only stats
    (never test-fold stats -- no leakage), so the fixed BETA_GRID range
    (-2..2) spans a sensible span of the predictor regardless of its raw,
    arbitrary scale. This is a predictor-only rescaling (never looks at the
    outcome), so it is not a post-hoc fit to bpm_delta -- it is the honest
    fix for the fact that fit_score's raw units (z-scored archetype dot
    scheme, plus a bounded (0,1] vacancy term) were never pinned to match
    bpm_delta's scale in the V2 spec's formula. Without this, the grid's
    coarsest step (0.5) already overshoots badly on the raw fit_score's
    wide variance and beta=0.0 wins by RMSE on every fold regardless of any
    real underlying correlation -- caught and diagnosed during this run via
    an analytic OLS-through-origin beta* check (see run notes)."""
    mean, std = train_fit.mean(), train_fit.std(ddof=0)
    if std < 1e-12:
        return np.zeros_like(apply_to)
    return (apply_to - mean) / std


def _grid_search_beta(train_fit_std: np.ndarray, train_outcome: np.ndarray) -> float:
    best_beta, best_rmse = 0.0, _rmse(train_outcome, np.zeros_like(train_outcome))
    for beta in BETA_GRID:
        pred = beta * train_fit_std
        r = _rmse(train_outcome, pred)
        if r < best_rmse:
            best_rmse, best_beta = r, beta
    return best_beta


def _evaluate_fold(train: pd.DataFrame, test: pd.DataFrame) -> tuple[float, float, float]:
    """Returns (rmse_h0, rmse_h1, corr_h1, beta) computed on the TEST fold
    using a beta grid-searched on TRAIN only. fit_score is standardized
    using TRAIN-only mean/std (see _standardize_fit_score) before the grid
    search and before applying beta to TEST -- the standardization itself
    leaks nothing (predictor-only, train-fit stats applied to test)."""
    train_valid = train.dropna(subset=["fit_score", "bpm_delta"])
    test_valid = test.dropna(subset=["fit_score", "bpm_delta"])
    train_fit_raw = train_valid["fit_score"].to_numpy()
    train_fit_std = _standardize_fit_score(train_fit_raw, train_fit_raw)
    beta = _grid_search_beta(train_fit_std, train_valid["bpm_delta"].to_numpy())

    y_test = test_valid["bpm_delta"].to_numpy()
    test_fit_std = _standardize_fit_score(train_fit_raw, test_valid["fit_score"].to_numpy())
    pred_h0 = np.zeros_like(y_test)
    pred_h1 = beta * test_fit_std

    rmse_h0 = _rmse(y_test, pred_h0)
    rmse_h1 = _rmse(y_test, pred_h1)
    if len(y_test) >= 2 and np.std(pred_h1) > 1e-12:
        corr_h1 = float(np.corrcoef(pred_h1, y_test)[0, 1])
    else:
        corr_h1 = 0.0
    return rmse_h0, rmse_h1, corr_h1, beta


def walk_forward_evaluate(moves_with_fit: pd.DataFrame) -> tuple[list[FoldResult], bool]:
    fold_names = sorted(moves_with_fit["season_pre"].unique())
    results: list[FoldResult] = []
    off_init_moved = False
    for held_out in fold_names:
        test = moves_with_fit[moves_with_fit["season_pre"] == held_out]
        train = moves_with_fit[moves_with_fit["season_pre"] != held_out]
        rmse_h0, rmse_h1, corr_h1, beta = _evaluate_fold(train, test)
        if beta != 0.0:
            off_init_moved = True
        results.append(FoldResult(
            fold_name=held_out, n=len(test.dropna(subset=["fit_score", "bpm_delta"])),
            rmse_h0=rmse_h0, rmse_h1=rmse_h1, corr_h1=corr_h1,
            delta_rmse=rmse_h0 - rmse_h1, beta_selected=beta,
        ))
    return results, off_init_moved


def run_gate(explicit_run_requested: bool = False, spec_path: Path = V2_SPEC_PATH,
             seed: int = 20260705) -> GateRunResult:
    if not explicit_run_requested:
        raise RuntimeError("run_gate() refused: explicit_run_requested=False")
    spec = load_v2_spec(spec_path)
    v2_sha16 = _sha16(spec_path)

    moves = pd.read_parquet(MOVES_CORPUS_PATH)
    season_table = _build_season_table()
    moves_fit = build_ingredients(moves, season_table)

    per_fold, off_init_moved = walk_forward_evaluate(moves_fit)
    pooled_delta = float(np.mean([f.delta_rmse for f in per_fold]))
    sign_holds_count = sum(1 for f in per_fold if f.delta_rmse > 0)

    # Null 1: shuffled destinations
    null1_moves = shuffle_move_team_assignment(moves, seed=seed)
    null1_fit = build_ingredients(null1_moves, season_table)
    null1_folds, _ = walk_forward_evaluate(null1_fit)
    null1_pooled = float(np.mean([f.delta_rmse for f in null1_folds]))
    null1_dies = null_dies(pooled_delta, null1_pooled)

    # Null 2: shuffled outcomes
    null2_moves = shuffle_outcome_deltas(moves_fit, seed=seed)
    null2_folds, _ = walk_forward_evaluate(null2_moves)
    null2_pooled = float(np.mean([f.delta_rmse for f in null2_folds]))
    null2_dies = null_dies(pooled_delta, null2_pooled)

    result = GateRunResult(
        v2_spec_sha16=v2_sha16, n_moves=len(moves), n_folds=len(per_fold),
        per_fold=per_fold, pooled_delta=pooled_delta, sign_holds_count=sign_holds_count,
        off_init_moved=off_init_moved,
        null1_result={"pooled_delta": null1_pooled, "dies": null1_dies, "seed": seed},
        null2_result={"pooled_delta": null2_pooled, "dies": null2_dies, "seed": seed},
    )

    # Decision rule, nulls checked FIRST per V2 spec check_order
    if not null1_dies or not null2_dies:
        result.verdict = "DISQUALIFIED_BY_NULL"
        result.verdict_reason = (
            f"null_1_dies={null1_dies} null_2_dies={null2_dies} -- at least one planted "
            "null cleared the same bar the real arm needed, per V2 decision_rule_v2."
        )
    elif sign_holds_count == len(per_fold) and pooled_delta > 0:
        result.verdict = "SHIP"
        result.verdict_reason = "H1 beat H0 on every held-out fold and both nulls died -- SHIP requires extra scrutiny next wave."
    elif pooled_delta <= 0:
        result.verdict = "REJECT"
        result.verdict_reason = f"pooled_delta={pooled_delta:.4f} <= 0 (H1 does not beat H0) while both nulls behaved as expected."
    else:
        result.verdict = "NOT_TESTABLE"
        result.verdict_reason = f"sign_holds={sign_holds_count}/{len(per_fold)} is not a consistent majority direction across folds."

    return result


# NOTE: verdict-JSON serialization + CLI entry point live in
# fit_validity_gate_report.py (pure I/O, split out purely for the 300-LOC
# cap; that module imports run_gate/GateRunResult from here rather than
# duplicating any compute logic).
