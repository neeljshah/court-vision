"""S450 FIX 1f/1g: every scored HOLDOUT row comes from its own cpcv_splits
path (AMENDMENT 6(a)), scored against RAW gamelog history (AMENDMENT 7(a)).

FIX 1f built the per-path train set out of MANIFEST rows (one row per start,
carrying "y" and no relief/batter appearances) and fed that straight to the
served forecaster, which reads the missing `pitch_strikeOuts`/`battersFaced`
columns as absent -> a corrupted, silently-zeroed forecast. This module now
resolves each path to a SET OF SAFE GAME_PKs (from the manifest-level cpcv
structure) and builds the actual training dataframe from the RAW gamelogs
rows for those games (every appearance -- starts, relief, batting -- every
column the served reader expects), restricted to strictly before the row's
own date. Never manifest rows as a stand-in for raw history.

Split out under the 300 LOC rail (a 6th helper module, AMENDMENT 6(f)).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from scripts.platformkit.eval_gate import cpcv_engine
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_fit import (
    purge_fit_rows, score_row_all_arms,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_manifest import (
    league_k_rate_as_of, opp_k_rate_as_of,
)


def cpcv_paths_for_holdout(fit_rows: List[dict], holdout_rows: List[dict],
                          n_groups: Optional[int] = None, n_test_groups: int = 1,
                          embargo_blocks: int = 1) -> List[Tuple[Set[object], Optional[int]]]:
    """For each row in ``holdout_rows`` (manifest-shaped, one per start): the
    (train_game_pks, path_id) of the cpcv_splits path whose test block holds
    it, after symmetric team/matchup blocking (purge_fit_rows) of that path's
    FIT-bucket rows against just that one row. ``train_game_pks`` names the
    games safe to train on -- callers resolve these against the RAW gamelogs
    (AMENDMENT 7(a)), never the manifest. A row cpcv_splits could not place on
    any path falls back to symmetric-blocking-only games with path_id=None."""
    if not fit_rows or not holdout_rows:
        return [({r["game_pk"] for r in purge_fit_rows(fit_rows, [row])[0]}, None)
                for row in holdout_rows]
    combined = fit_rows + holdout_rows
    dates = [r["date"] for r in combined]
    n_unique = pd.Series(pd.to_datetime(dates, errors="coerce")).nunique()
    n_fit = len(fit_rows)
    row_to_path: Dict[int, int] = {}
    path_train: Dict[int, List[int]] = {}
    if n_unique >= 2:
        groups = n_groups or max(2, min(8, n_unique))
        for path_id, (train_idx, test_idx) in enumerate(
                cpcv_engine.cpcv_splits(dates, n_groups=groups, n_test_groups=n_test_groups,
                                        embargo_blocks=embargo_blocks)):
            path_train[path_id] = [int(i) for i in train_idx]
            for i in test_idx:
                pos = int(i)
                if pos >= n_fit and pos not in row_to_path:
                    row_to_path[pos] = path_id
    out: List[Tuple[Set[object], Optional[int]]] = []
    for offset, row in enumerate(holdout_rows):
        path_id = row_to_path.get(n_fit + offset)
        if path_id is None:
            train_rows, _ = purge_fit_rows(fit_rows, [row])
        else:
            # AMENDMENT 10(a): keep EVERY combined[i] the CPCV train path
            # selected, not just the FIT-bucket ones -- an earlier HOLDOUT
            # row on the same path is valid as-of history too (the 2024 rows
            # belong to the 2025-26 CPCV universe). raw_train_df's own
            # strict `< as_of` filter is what keeps this leak-free, not a
            # fit-only prefilter here.
            train_candidates = [combined[i] for i in path_train[path_id]]
            train_rows, _ = purge_fit_rows(train_candidates, [row])
        out.append(({r["game_pk"] for r in train_rows}, path_id))
    return out


def raw_train_df(gamelogs_df: pd.DataFrame, train_game_pks: Set[object], as_of) -> pd.DataFrame:
    """AMENDMENT 7(a): the actual per-path training state is RAW gamelog rows
    -- every appearance (starts, relief, batting), every column the served
    reader expects (`pitch_strikeOuts`, `battersFaced`, `atBats`,
    `strikeOuts`, ...) -- restricted to the path's safe games AND to dates
    strictly before ``as_of``. Never manifest rows (they carry "y", not
    "pitch_strikeOuts", and omit relief/batter history)."""
    if not train_game_pks:
        return gamelogs_df.iloc[0:0]
    dates = pd.to_datetime(gamelogs_df["date"], errors="coerce")
    mask = (gamelogs_df["game_pk"].isin(train_game_pks) & dates.notna()
           & (dates < pd.Timestamp(as_of)))
    return gamelogs_df.loc[mask]


def score_holdout_via_cpcv(gamelogs_df: pd.DataFrame, fit_rows: List[dict], holdout_rows: List[dict],
                          r: float, beta: float) -> List[Tuple[dict, Optional[int], pd.DataFrame, dict]]:
    """Scores every holdout row through its own cpcv path's RAW train-only
    dataframe (AMENDMENT 7(a)) -- never manifest rows, never the full
    unrestricted corpus. AMENDMENT 8(a): opp_k_rate/league_k_rate are ALSO
    path-restricted -- ``row`` arrives pre-enriched from the UNRESTRICTED
    gamelogs_df (enrich_manifest runs once, before any fold split), so both
    rates are recomputed here from this row's own train_df before scoring;
    the row that gets scored (and returned) is this path-enriched copy, never
    the unrestricted one. Returns (score_result, path_id, train_df,
    path_enriched_row) per row, same order as holdout_rows; the caller must
    retain path_enriched_row (not the original row) for the null
    recomputation (AMENDMENT 7(b)/8(a)) so it reuses the IDENTICAL path
    state, rates included."""
    paths = cpcv_paths_for_holdout(fit_rows, holdout_rows)
    out = []
    for row, (train_game_pks, path_id) in zip(holdout_rows, paths):
        train_df = raw_train_df(gamelogs_df, train_game_pks, row["date"])
        path_row = dict(row)
        path_row["opp_k_rate"] = opp_k_rate_as_of(train_df, row.get("opp_team"), row["date"])
        path_row["league_k_rate"] = league_k_rate_as_of(train_df, row["date"])
        result = score_row_all_arms(train_df, path_row, r, beta)
        out.append((result, path_id, train_df, path_row))
    return out
