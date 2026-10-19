"""S450: per-row scoring + FIT-corpus grid fits for the pitcher-K distribution row.

Splits the manifest-building / arm math (mlb_pitcher_k_distribution_arms.py,
mlb_pitcher_k_distribution_manifest.py) from the fold-level fit/score loop so
neither file needs to grow past the 300 LOC rail.

Every row is scored for ALL THREE arms together or abstained for ALL THREE
together (AMENDMENT 1(c)): a row any single arm cannot forecast is not scored
by the other two either, so the paired denominator across arms never drifts.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import pandas as pd

from scripts.platformkit.eval_gate import cpcv_engine
from scripts.platformkit.eval_gate.cpcv_engine import assert_vintage
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_arms import (
    BETA_GRID, K_LINES, R_GRID, arm_a_forecast, arm_b_forecast, arm_c_forecast,
    brier_at_k_from_pmf, crps_from_pmf, exceedance_prob_from_pmf,
    log_score_from_pmf, pinball_from_pmf, pmf_from_exceedance,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_history import (
    PITCHER_HISTORY_INVALID, pitcher_history_invalid,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_manifest import (
    battersfaced_missing, coerce_count, league_k_rate_as_of, opp_k_rate_as_of,
    opponent_team,
)

EMBARGO_DAYS_BOUNDARY = 1  # calendar-day symmetric embargo used to purge FIT rows


def enrich_row(gamelogs_df: pd.DataFrame, row: Dict[str, object]) -> Dict[str, object]:
    """Attach opponent/league K-rate pools + a strict-int y to one manifest row.
    Pools depend only on (game_pk, team, date), never on r/beta, so this runs
    once per row before either grid fit."""
    out = dict(row)
    opp = opponent_team(gamelogs_df, row["game_pk"], row["team"])
    out["opp_team"] = opp
    out["opp_k_rate"] = opp_k_rate_as_of(gamelogs_df, opp, row["date"])
    out["league_k_rate"] = league_k_rate_as_of(gamelogs_df, row["date"])
    y_val, y_reason = coerce_count(row.get("y"))
    out["y_int"] = y_val
    out["y_reason"] = y_reason
    out["bf_missing"] = battersfaced_missing(row.get("battersFaced"))
    return out


def enrich_manifest(gamelogs_df: pd.DataFrame, manifest_df: pd.DataFrame) -> List[Dict[str, object]]:
    return [enrich_row(gamelogs_df, r) for r in manifest_df.to_dict("records")]


def _vintage_state(row: Dict[str, object]) -> dict:
    """Minimal cpcv_engine-shaped state so assert_vintage (reused unedited) can
    check this row's history cutoff is strictly before its own game day."""
    game_date = pd.Timestamp(row["date"])
    state_ts = (game_date + pd.Timedelta(hours=12)).isoformat()
    avail_ts = (game_date - pd.Timedelta(seconds=1)).isoformat()
    return {
        "game_id": f"{row['game_pk']}:{row['player_id']}",
        "state_ts": state_ts,
        "features": {"pitcher_history": True},
        "feature_avail": {"pitcher_history": avail_ts},
    }


def _purge_state(row: Dict[str, object]) -> dict:
    """Minimal cpcv_engine-shaped state carrying only what ``_blocked_indices``
    needs (home/away) to flag a same-team / same-matchup row near a boundary."""
    opp = row.get("opp_team") or row["team"]
    return {"home": row["team"], "away": opp}


def purge_fit_rows(fit_rows: List[Dict[str, object]], holdout_rows: List[Dict[str, object]],
                   embargo_days: int = EMBARGO_DAYS_BOUNDARY) -> Tuple[List[Dict[str, object]], int]:
    """AMENDMENT 2(c): FIT rows are purged of any row cpcv_engine's OWN
    symmetric purge/embargo machinery (``_blocked_indices``, called for real,
    never a synthetic stand-in) flags as too close in calendar days, same
    team, or same matchup to a holdout row. Returns (kept_fit_rows,
    n_purged). Called via the module object so a raising replacement
    propagates."""
    if not fit_rows or not holdout_rows:
        return list(fit_rows), 0
    combined = list(fit_rows) + list(holdout_rows)
    states = [_purge_state(r) for r in combined]
    stamps = [pd.Timestamp(r["date"]).to_pydatetime() for r in combined]
    test_idx = list(range(len(fit_rows), len(combined)))
    blocked = cpcv_engine._blocked_indices(states, stamps, test_idx, embargo_days)
    kept = [r for i, r in enumerate(fit_rows) if i not in blocked]
    return kept, len(fit_rows) - len(kept)


# cpcv_derive_fit_rows (AMENDMENT 5(b), cpcv_splits + this purge) lives in
# mlb_pitcher_k_distribution_realrun.py to keep this file under the LOC rail.


def score_row_all_arms(df: pd.DataFrame, row: Dict[str, object], r: float, beta: float) -> Dict[str, object]:
    """Score one enriched manifest row for arms A/B/C, or abstain all three.

    Never drops a row: every return carries "status" in {"scored", "abstain"}
    and an abstention always names a reason.
    """
    if row["y_reason"] is not None:
        return {"status": "abstain", "reason": f"y_{row['y_reason']}"}
    # AMENDMENT 14(a)/15(a): a bad prior-pitcher-history value would silently
    # zero into player_rates_mlb's rate sum -- common-abstain BEFORE any arm
    # call. The guard mirrors player_rates_mlb's own row selection exactly.
    if pitcher_history_invalid(df, row.get("date"), row.get("player_id")):
        return {"status": "abstain", "reason": PITCHER_HISTORY_INVALID}
    # AMENDMENT 4(b): an unavailable enriched rate is a common abstention BEFORE
    # any arm is invoked -- arm_c_forecast's beta==0 short-circuit must never be
    # allowed to bypass rate validation (a row's rate availability does not
    # depend on which beta the FIT grid happened to choose).
    if row["opp_k_rate"] is None or row["league_k_rate"] is None:
        return {"status": "abstain", "reason": "opp_rate_unavailable"}
    y = row["y_int"]
    dists = {
        "A": arm_a_forecast(df, row["player_id"], row["date"]),
        "B": arm_b_forecast(df, row["player_id"], row["date"], r),
        "C": arm_c_forecast(df, row["player_id"], row["date"], r, beta,
                            row["opp_k_rate"], row["league_k_rate"]),
    }
    pmfs: Dict[str, list] = {}
    for arm, dist in dists.items():
        if dist.get("status") != "ok":
            reason = dist.get("reason")
            return {"status": "abstain", "reason": reason or f"arm_{arm}_unknown"}
        adapted = pmf_from_exceedance(dist["p_over"])
        if adapted["status"] != "ok":
            return {"status": "abstain", "reason": f"arm_{arm}_{adapted['reason']}"}
        pmfs[arm] = adapted["pmf"]

    assert_vintage(_vintage_state(row))  # reused unedited leak-guard sanity check

    metrics: Dict[str, dict] = {}
    for arm, pmf in pmfs.items():
        metrics[arm] = {
            "crps": crps_from_pmf(pmf, y),
            "pinball_q10": pinball_from_pmf(pmf, y, 0.10),
            "pinball_q50": pinball_from_pmf(pmf, y, 0.50),
            "pinball_q90": pinball_from_pmf(pmf, y, 0.90),
            "log_score": log_score_from_pmf(pmf, y),
            "k_line": {
                str(k): {
                    "p_over": exceedance_prob_from_pmf(pmf, k),
                    "outcome": 1.0 if y > k else 0.0,
                    "brier": brier_at_k_from_pmf(pmf, y, k),
                } for k in K_LINES
            },
        }
    return {"status": "scored", "y": y, "date": row["date"], "game_pk": row["game_pk"],
            "player_id": row["player_id"], "metrics": metrics}


def _fit_grid(fit_rows: List[Dict[str, object]], df: pd.DataFrame, grid: Tuple[float, ...],
             forecast_fn, min_n: int = 30) -> Tuple[Optional[float], Dict[float, Optional[float]], dict]:
    """Score every grid value on the SAME common set of FIT rows (AMENDMENT
    2(b)): a row any grid value cannot forecast is dropped for ALL values, so
    rankings are never compared across different sample sets. Returns
    (best_or_None, {value: mean_loss_or_None}, meta) where meta names
    n_considered (non-y-reason FIT rows attempted), n_common (rows every grid
    value could score) and grid_common_abstained (the rows dropped for all
    values). best is None -- no parameter chosen, never the first grid value --
    when fewer than min_n common finite losses exist, including an empty FIT
    corpus; AMENDMENT 3(b): the per-value scores are then None, never inf, so
    a strict json.dumps(allow_nan=False) of the report never raises."""
    per_row_losses: List[Dict[float, float]] = []
    n_considered = 0
    for row in fit_rows:
        if row["y_reason"] is not None:
            continue
        n_considered += 1
        if pitcher_history_invalid(df, row.get("date"), row.get("player_id")):
            continue  # AMENDMENT 14(a)/15(a): common-abstain for ALL grid values
        row_losses: Dict[float, float] = {}
        ok = True
        for value in grid:
            dist = forecast_fn(row, value)
            if dist.get("status") != "ok":
                ok = False
                break
            adapted = pmf_from_exceedance(dist["p_over"])
            if adapted["status"] != "ok":
                ok = False
                break
            loss = crps_from_pmf(adapted["pmf"], row["y_int"])
            if not math.isfinite(loss):
                ok = False
                break
            row_losses[value] = loss
        if ok:
            per_row_losses.append(row_losses)

    n_common = len(per_row_losses)
    meta = {"n_considered": n_considered, "n_common": n_common,
           "grid_common_abstained": n_considered - n_common}
    if n_common < min_n:
        # AMENDMENT 4(a): under-floor is None for EVERY grid value, never a
        # numeric score beside best=None -- n_common>0-but-under-floor must not
        # leak real means into a report whose parameter is unchosen.
        scores = {value: None for value in grid}
        return None, scores, meta
    scores = {value: sum(rl[value] for rl in per_row_losses) / n_common for value in grid}
    best = min(grid, key=lambda v: (scores[v], v))
    return best, scores, meta


def fit_r_grid(fit_rows: List[Dict[str, object]], df: pd.DataFrame,
              grid: Tuple[float, ...] = R_GRID) -> Tuple[Optional[float], Dict[float, Optional[float]], dict]:
    """Grid-fit r by min mean CRPS on FIT-corpus rows only (AMENDMENT 1(e))."""
    return _fit_grid(fit_rows, df, grid, lambda row, r: arm_b_forecast(df, row["player_id"], row["date"], r))


def fit_beta_grid(fit_rows: List[Dict[str, object]], df: pd.DataFrame, r: float,
                  grid: Tuple[float, ...] = BETA_GRID) -> Tuple[Optional[float], Dict[float, Optional[float]], dict]:
    """Grid-fit beta (r frozen) by min mean CRPS on FIT-corpus rows only."""
    return _fit_grid(fit_rows, df, grid, lambda row, beta: arm_c_forecast(
        df, row["player_id"], row["date"], r, beta, row["opp_k_rate"], row["league_k_rate"]))


def permute_opp_k_rate_null(rows: List[Dict[str, object]], seed: int = 13) -> List[Dict[str, object]]:
    """AMENDMENT 1(f)/2(f): Arm C's predictive null -- permute opp_k_rate across
    same-date starts with shared, predeclared draws. Order-independent: rows are
    assigned to date-groups (and ordered within each group) by the STABLE
    identity (date, game_pk, player_id), never by input row position, and dates
    are visited in sorted order, so reversed or reordered input consumes the
    seeded RNG stream identically and yields IDENTICAL null assignments.
    Returns copies; does not mutate ``rows``."""
    order = sorted(range(len(rows)), key=lambda i: (
        str(rows[i]["date"]), str(rows[i]["game_pk"]), str(rows[i]["player_id"])))
    by_date: Dict[object, List[int]] = {}
    for i in order:
        by_date.setdefault(rows[i]["date"], []).append(i)
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    for date in sorted(by_date.keys(), key=str):
        idxs = by_date[date]
        shuffled = [rows[i]["opp_k_rate"] for i in idxs]
        rng.shuffle(shuffled)
        for i, rate in zip(idxs, shuffled):
            out[i]["opp_k_rate"] = rate
    return out


def compute_null_losses(train_dfs: List[pd.DataFrame], enriched_rows: List[Dict[str, object]],
                        scored_results: List[Dict[str, object]], r: float, beta: float,
                        seed: int = 13) -> Tuple[List[dict], List[float]]:
    """AMENDMENT 5(c)/6(b)/7(b): re-score Arm C for real under
    permute_opp_k_rate_null's same-date permutation (called as a bare
    module-global, so a raising replacement of it propagates), using EACH
    ROW'S OWN path-specific raw training dataframe (``train_dfs[i]``, the
    IDENTICAL state ``score_holdout_via_cpcv`` used for that row's real
    score) -- never one shared unrestricted ``gamelogs_df``.
    ``train_dfs``/``enriched_rows``/``scored_results`` are 1:1, same order
    (the scored subset of one fold). Each archived identity carries its OWN
    null_crps_c, null_delta AND split_id (copied from the real result, so the
    caller can validate identity+split-id equality, not merely counts) --
    AMENDMENT 6(b)/7(b). A row the null itself cannot forecast is omitted,
    never fabricated -- completeness is checked by the caller, never assumed
    here. Returns (assignments, null_deltas) where null_deltas[i] =
    null_CRPS_C - real_CRPS_B."""
    permuted = permute_opp_k_rate_null(enriched_rows, seed=seed)
    assignments: List[dict] = []
    null_deltas: List[float] = []
    for train_df, orig, perm, result in zip(train_dfs, enriched_rows, permuted, scored_results):
        # AMENDMENT 16(a): the guard runs BEFORE arm_c_forecast here too --
        # invalid history omits the assignment (never scores a null off a
        # poisoned pool), so completeness (the caller's coverage check)
        # forces INSUFFICIENT rather than a partial/contaminated null.
        if pitcher_history_invalid(train_df, orig["date"], orig["player_id"]):
            continue
        dist = arm_c_forecast(train_df, orig["player_id"], orig["date"], r, beta,
                              perm["opp_k_rate"], orig["league_k_rate"])
        if dist.get("status") != "ok":
            continue
        adapted = pmf_from_exceedance(dist["p_over"])
        if adapted["status"] != "ok":
            continue
        crps_null = crps_from_pmf(adapted["pmf"], result["y"])
        delta = crps_null - result["metrics"]["B"]["crps"]
        null_deltas.append(delta)
        assignments.append({"game_pk": orig["game_pk"], "player_id": orig["player_id"],
                            "date": orig["date"], "null_opp_k_rate": perm["opp_k_rate"],
                            "null_crps_c": crps_null, "null_delta": delta,
                            "split_id": result.get("split_id")})
    return assignments, null_deltas
