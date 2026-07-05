"""Companion module for replay_shipped_indices.py (wave-45 lane: reprocess-
register). Holds rows_source loaders and custom comparators for the newly
registered REJECT/NOT_TESTABLE clients, split out to keep the registry file
under the 300-LOC cap. Never imports producer code -- only reads the already-
persisted rows parquet + committed verdict JSON, matching the harness's
no-producer-import invariant.

Policy (Fable-ratified, this task): REJECT/NOT_TESTABLE verdicts get replay
clients too, same as ADOPT/SHIP -- replaying a REJECT verifies the honest
negative stays reproducible as the harness/code evolves. A schema or
verdict-shape mismatch is recorded as an honest UNAVAILABLE with a reason;
it is NEVER coerced into a shape the harness or committed verdict don't have.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.platformkit.reprocess.reprocess_harness import (
    SchemaError,
    run_harness,
    verdict_to_dict,
)

_REPO = Path(__file__).resolve().parents[4]


def load_rows(rel_path: str) -> pd.DataFrame:
    return pd.read_parquet(_REPO / rel_path)


# ---------------------------------------------------------------------------
# positional_weight (NBA, rho, per-fold comparison)
# ---------------------------------------------------------------------------

def positional_weight_rows() -> pd.DataFrame:
    return load_rows("data/domains/basketball_nba/positional_weight_rows.parquet")


def compare_positional_weight(client, committed: dict) -> dict:
    """Per-fold rho delta comparison: the committed verdict's top-level
    scalar (bootstrap_delta_ci_overall.mean_delta) is a BOOTSTRAP MEAN, not
    the harness's fold-pooled rho delta -- not the same statistic, so it is
    NOT used as the comparison target (would be a coercion). Instead this
    compares each per_fold[i].overall.delta (an exact rho(p_variant,y) -
    rho(p_base,y) on that fold's rows) against the harness's own
    per_fold_signs_vs_base for the same fold_id -- both are the identical
    statistic computed two ways, so a 1e-6 match is a meaningful replay
    proof, not a shape-coercion."""
    df = client.rows_source()
    try:
        verdict = run_harness(df, metric=client.metric, cluster_col="cluster_id")
    except SchemaError as e:
        return {"status": "UNAVAILABLE", "reason": f"SchemaError: {e}"}
    replayed = verdict_to_dict(verdict)
    corpus_id = df["corpus_id"].iloc[0]
    replayed_folds = {
        f["fold_id"]: f["mean_delta"]
        for f in replayed["per_corpus"][str(corpus_id)]["per_fold_signs_vs_base"]
    }
    committed_folds = {f["cutoff"]: f["overall"]["delta"] for f in committed["per_fold"]}
    if set(replayed_folds) != set(committed_folds):
        return {
            "status": "UNAVAILABLE",
            "reason": f"fold_id set mismatch: replayed={sorted(replayed_folds)} "
                      f"committed={sorted(committed_folds)}",
        }
    diffs = {k: abs(replayed_folds[k] - committed_folds[k]) for k in replayed_folds}
    max_abs_diff = max(diffs.values())
    return {
        "status": "RAN",
        "matched": max_abs_diff <= client.tolerance,
        "max_abs_diff": max_abs_diff,
        "tolerance": client.tolerance,
        "per_fold_diffs": diffs,
    }


# ---------------------------------------------------------------------------
# elo_refresh (WNBA, brier, per-corpus comparison across 3 candidates)
# ---------------------------------------------------------------------------

def elo_refresh_rows() -> pd.DataFrame:
    return load_rows("data/domains/wnba/elo_refresh_harness_rows.parquet")


def _committed_candidate_delta(committed: dict, candidate: str) -> float:
    """n-weighted mean of per-season brier_delta for one candidate -- the
    committed JSON only stores per-season fold dicts (brier_delta per
    season), never a single pooled-per-candidate scalar, so this derives
    the same n-weighted pooled statistic the harness computes internally
    (mean over ALL rows in that corpus) directly from those fold rows."""
    folds = committed["candidate_folds"][candidate]
    n_tot = sum(f["n_test"] for f in folds)
    return sum(f["brier_delta"] * f["n_test"] for f in folds) / n_tot


def compare_elo_refresh(client, committed: dict) -> dict:
    df = client.rows_source()
    try:
        verdict = run_harness(df, metric=client.metric)
    except SchemaError as e:
        return {"status": "UNAVAILABLE", "reason": f"SchemaError: {e}"}
    replayed = verdict_to_dict(verdict)
    candidates = list(committed.get("candidate_folds", {}).keys())
    if not candidates:
        return {"status": "UNAVAILABLE", "reason": "committed verdict has no candidate_folds"}
    diffs: dict[str, float] = {}
    for cand in candidates:
        corpus_id = f"wnba_elo_refresh_{cand}"
        if corpus_id not in replayed["per_corpus"]:
            return {
                "status": "UNAVAILABLE",
                "reason": f"replayed rows missing corpus_id={corpus_id!r} for candidate {cand!r}",
            }
        replayed_delta = replayed["per_corpus"][corpus_id]["vs_base"]["delta"]
        committed_delta = _committed_candidate_delta(committed, cand)
        diffs[cand] = abs(replayed_delta - committed_delta)
    max_abs_diff = max(diffs.values())
    return {
        "status": "RAN",
        "matched": max_abs_diff <= client.tolerance,
        "max_abs_diff": max_abs_diff,
        "tolerance": client.tolerance,
        "per_candidate_diffs": diffs,
    }


# ---------------------------------------------------------------------------
# umpire_totals_gate (MLB, rmse, relabeled columns -- wave-47 gap closure)
# ---------------------------------------------------------------------------

_UMPIRE_BURN_IN = 300   # must match domains.mlb.umpire_totals_gate.BURN_IN exactly
_UMPIRE_N_FOLDS = 3     # must match domains.mlb.umpire_totals_gate.N_FOLDS exactly


def umpire_totals_rows() -> pd.DataFrame:
    """Relabels umpire_totals_gate_rows.parquet's own columns into the
    harness's rmse contract -- a column RENAME plus a fold_id derived with
    the IDENTICAL construction the gate itself uses: BURN_IN=300 is applied
    as a POSITIONAL cutoff on the RAW row order FIRST (matching
    umpire_totals_gate._score_corpus's arange(BURN_IN, n_total) on the
    as-persisted row order), THEN rows with a NaN prediction are dropped --
    dropping NaNs before slicing would shift the burn-in boundary by however
    many NaN rows preceded it, which is NOT what the gate computes (verified:
    doing dropna-then-slice mismatches the committed fold sizes by 1 row).
    N_FOLDS=3 chronological np.array_split follows, on the post-burn-in,
    post-dropna scorable rows -- both constants copied verbatim from
    domains.mlb.umpire_totals_gate, not re-derived or guessed. No re-scoring:
    candidate_pred/baseline_pred are the gate's own persisted predictions,
    untouched."""
    df = load_rows("data/domains/mlb/umpire_totals_gate_rows.parquet")
    n_total = len(df)
    scorable = df.iloc[_UMPIRE_BURN_IN:n_total].dropna(
        subset=["baseline_pred", "candidate_pred"]).reset_index(drop=True)
    n_scorable = len(scorable)
    fold_bounds = np.array_split(np.arange(n_scorable), _UMPIRE_N_FOLDS)
    fold_id = np.empty(n_scorable, dtype=object)
    for i, b in enumerate(fold_bounds):
        fold_id[b] = f"fold{i}"
    return pd.DataFrame({
        "corpus_id": "mlb_umpire_totals_gate",
        "fold_id": fold_id,
        "event_id": scorable["game_pk"].astype(str),
        "p_variant": scorable["candidate_pred"].astype(float),
        "p_base": scorable["baseline_pred"].astype(float),
        "outcome": scorable["total_runs"].astype(float),
        "hp_umpire_id": scorable["hp_umpire_id"],
    })


def umpire_totals_committed_fold_deltas() -> dict:
    """committed verdict's real_result.folds[i].rmse_delta, keyed to match
    the harness's own fold{i} naming -- rmse_delta is NEGATIVE when the
    candidate improves (cand_rmse - base_rmse), the OPPOSITE sign convention
    from the harness's rmse delta (rmse_base - rmse_variant, positive =>
    variant improves); this returns the value SIGN-FLIPPED so it is directly
    comparable to the harness's per-fold mean_delta without the caller
    needing to know the committed JSON's own sign convention."""
    verdict = json.loads(
        (_REPO / "data" / "domains" / "mlb" / "umpire_totals_gate_verdict.json").read_text(encoding="ascii")
    )
    folds = verdict["real_result"]["folds"]
    return {f"fold{i}": -float(f["rmse_delta"]) for i, f in enumerate(folds)}


def compare_umpire_totals(client, committed: dict) -> dict:
    """Per-fold RMSE delta comparison, mirroring compare_positional_weight's
    fold-by-fold approach: the harness's per_fold_signs_vs_base mean_delta
    (rmse_base - rmse_variant, positive => variant/candidate improves) is
    diffed against the committed verdict's real_result.folds[i].rmse_delta
    (SIGN-FLIPPED by umpire_totals_committed_fold_deltas to the same
    convention) for the SAME fold_id -- both are the identical statistic
    computed two ways (gate's own walk-forward vs harness replay of the
    persisted predictions), so a 1e-6 match is a meaningful replay proof."""
    df = client.rows_source()
    try:
        verdict = run_harness(df, metric=client.metric, cluster_col=None)
    except SchemaError as e:
        return {"status": "UNAVAILABLE", "reason": f"SchemaError: {e}"}
    replayed = verdict_to_dict(verdict)
    corpus_id = df["corpus_id"].iloc[0]
    replayed_folds = {
        f["fold_id"]: f["mean_delta"]
        for f in replayed["per_corpus"][str(corpus_id)]["per_fold_signs_vs_base"]
    }
    committed_folds = umpire_totals_committed_fold_deltas()
    if set(replayed_folds) != set(committed_folds):
        return {
            "status": "UNAVAILABLE",
            "reason": f"fold_id set mismatch: replayed={sorted(replayed_folds)} "
                      f"committed={sorted(committed_folds)}",
        }
    diffs = {k: abs(replayed_folds[k] - committed_folds[k]) for k in replayed_folds}
    max_abs_diff = max(diffs.values())
    return {
        "status": "RAN",
        "matched": max_abs_diff <= client.tolerance,
        "max_abs_diff": max_abs_diff,
        "tolerance": client.tolerance,
        "per_fold_diffs": diffs,
    }


# ---------------------------------------------------------------------------
# UNAVAILABLE reason builders (schema / verdict-shape mismatches)
# ---------------------------------------------------------------------------


def ingame_hypothesis_unavailable_reason(layer: str) -> str:
    return (
        f"Rows schema mismatch: data/domains/basketball_nba/ingame_hypothesis_{layer}_"
        "*_rows.parquet columns are ['game_id','period','seconds_remaining','score_diff',"
        "'p_live','outcome','cond_delta'/'cond_val','team','layer','season'] -- an in-game "
        "state shape (no corpus_id/fold_id/p_variant/p_base). RE-CHECKED wave-47 for a "
        "field_paths mapping fix (task asked): NOT a simple rename -- the committed verdict's "
        f"(ingame_hypothesis_{layer}.json) per-fold brier_base/brier_prior score a TRAIN-only-"
        "fit conditioning-prior surface (fit_weight_surface) gated to a TRAIN-derived threshold; "
        "neither the fitted surface, the gate threshold, nor the gated_on mask were persisted "
        "per-row -- only the plain p_live/cond_prior columns were exported. Reproducing "
        "brier_prior would require RE-FITTING the fold's prior surface (model re-run), not a "
        "column rename. Recorded as an honest UNAVAILABLE rather than relabeling columns to fit."
    )


def h3_playstyle_unavailable_reason() -> str:
    """RETIRED wave-h3-h0-export: p_base now exports H0's own detail pred
    (r0["p_variant"]), not the plain sigmoid base -- REGISTERED (RAN) below
    via h3_playstyle_rows()/compare_h3_playstyle(), not UNAVAILABLE."""
    return "RETIRED (pre h3-h0-export fix) -- see compare_h3_playstyle."


# ---------------------------------------------------------------------------
# tennis_h3_playstyle (ATP, brier, per-fold comparison; h3-h0-export lane)
# ---------------------------------------------------------------------------

def h3_playstyle_rows() -> pd.DataFrame:
    return load_rows("data/domains/tennis/h3_playstyle_rows.parquet")


def compare_h3_playstyle(client, committed: dict) -> dict:
    """Per-fold Brier delta comparison (mirrors compare_umpire_totals): harness
    mean_delta (brier_base - brier_variant, positive => H1 improves) vs
    committed atp.real.folds[i].brier_delta_h1_minus_h0 (SIGN-FLIPPED: committed
    is brier_h1 - brier_h0, negative => H1 improves), same fold_id -- identical
    statistic computed two ways, so a 1e-6 match is a real replay proof."""
    df = client.rows_source()
    try:
        verdict = run_harness(df, metric=client.metric, cluster_col=None)
    except SchemaError as e:
        return {"status": "UNAVAILABLE", "reason": f"SchemaError: {e}"}
    replayed = verdict_to_dict(verdict)
    corpus_id = df["corpus_id"].iloc[0]
    replayed_folds = {
        f["fold_id"]: f["mean_delta"]
        for f in replayed["per_corpus"][str(corpus_id)]["per_fold_signs_vs_base"]
    }
    committed_folds = {
        f"fold{f['fold']}": -float(f["brier_delta_h1_minus_h0"])
        for f in committed["atp"]["real"]["folds"]
    }
    if set(replayed_folds) != set(committed_folds):
        return {
            "status": "UNAVAILABLE",
            "reason": f"fold_id set mismatch: replayed={sorted(replayed_folds)} "
                      f"committed={sorted(committed_folds)}",
        }
    diffs = {k: abs(replayed_folds[k] - committed_folds[k]) for k in replayed_folds}
    max_abs_diff = max(diffs.values())
    return {
        "status": "RAN",
        "matched": max_abs_diff <= client.tolerance,
        "max_abs_diff": max_abs_diff,
        "tolerance": client.tolerance,
        "per_fold_diffs": diffs,
    }
