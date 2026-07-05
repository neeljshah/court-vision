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
it is NEVER coerced into a shape the harness or committed verdict don't
actually have.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
# UNAVAILABLE reason builders (schema / missing-verdict mismatches)
# ---------------------------------------------------------------------------

def umpire_totals_unavailable_reason() -> str:
    return (
        "Rows schema mismatch: data/domains/mlb/umpire_totals_gate_rows.parquet "
        "columns are ['game_pk','date','hp_umpire_id','total_runs','baseline_pred',"
        "'candidate_pred'] -- a custom RMSE-comparison shape, not the harness's "
        "required ['corpus_id','fold_id','event_id','p_variant','p_base','outcome']. "
        "The committed verdict (umpire_totals_gate_verdict.json) itself reports "
        "baseline_rmse/candidate_rmse per fold, not Brier/rho -- the harness has no "
        "RMSE metric path. Recorded as an honest UNAVAILABLE rather than renaming "
        "columns or inventing an RMSE metric mode to force a fit."
    )


def ingame_hypothesis_unavailable_reason(layer: str) -> str:
    return (
        f"Rows schema mismatch: data/domains/basketball_nba/ingame_hypothesis_{layer}_"
        "*_rows.parquet columns are ['game_id','period','seconds_remaining','score_diff',"
        "'p_live','outcome','cond_delta'/'cond_val','team','layer','season'] -- an in-game "
        "state shape (no corpus_id/fold_id/p_variant/p_base). The committed verdict "
        f"(ingame_hypothesis_{layer}.json) is split per-season with its own DM-test block "
        "computed directly against p_live/cond_prior, never persisted as p_variant/p_base "
        "rows. Recorded as an honest UNAVAILABLE rather than relabeling columns to fit."
    )


def h3_playstyle_unavailable_reason() -> str:
    return (
        "No committed verdict exists for data/domains/tennis/h3_playstyle_rows.parquet -- "
        "searched data/domains/tennis/**/*.json for an h3/playstyle-named verdict and found "
        "none (only surface_hold_gate_verdict.json, a different gate, is present). Rows are "
        "schema-compatible with the harness (corpus_id/fold_id/event_id/p_variant/p_base/"
        "outcome present, binary outcome), but there is nothing committed to replay against. "
        "Recorded as an honest UNAVAILABLE rather than treating a fresh harness run as its "
        "own ground truth."
    )
