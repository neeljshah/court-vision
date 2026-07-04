"""domains.tennis.atlas_persist -- persistence layer for the in-memory tennis atlases.

atlas_playstyles.build_playstyles() and atlas_h2h.build_h2h() compute real
per-player / per-pair statistics in memory but only ever emit rendered
Obsidian prose -- the row-level DataFrames never reach disk. This module
imports and calls the SAME compute helpers (no re-derivation of the
clustering / aggregation logic) and writes the row-level results to
parquet with as_of/corpus_id/season provenance columns stamped at
creation time. Unblocks tennis H3 (deferred-watchlist), which needs the
atlas rows to exist on disk, not just as vault markdown.

Public API:
    persist_playstyles(out_path, corpus_dir=None, as_of=None) -> PersistResult
    persist_h2h(out_path, corpus_dir=None, as_of=None) -> PersistResult

F5-clean: stdlib + numpy + pandas + domains.tennis.* only.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib
from typing import Optional

import pandas as pd

from domains.tennis.atlas_playstyles import DEFAULT_CORPUS, _compute_stats, _load_corpus
from domains.tennis.atlas_h2h import _compute_pair_stats, _load_matches
from domains.tennis.atlas_h2h import DEFAULT_CORPUS as H2H_DEFAULT_CORPUS

CORPUS_ID = "sackmann_atp_matches_parquet"


@dataclasses.dataclass
class PersistResult:
    out_path: pathlib.Path
    row_count: int
    columns: list


def _stamp_provenance(df: pd.DataFrame, as_of: str, corpus_id: str, season_col_source: pd.Series) -> pd.DataFrame:
    """Add as_of/corpus_id/season columns. season derived from a date-like series (year)."""
    df = df.copy()
    df["as_of"] = as_of
    df["corpus_id"] = corpus_id
    seasons = pd.to_datetime(season_col_source, errors="coerce").dt.year
    # season_col_source is per-row-aligned with df already (same index/order).
    df["season"] = seasons.values if len(seasons) == len(df) else None
    return df


def persist_playstyles(
    out_path: pathlib.Path,
    corpus_dir: Optional[pathlib.Path] = None,
    as_of: Optional[str] = None,
) -> PersistResult:
    """Compute per-player playstyle stats (via atlas_playstyles._compute_stats)
    and persist to parquet with provenance columns.

    Season here is corpus-level (min..max match year), NOT per-player, since
    _compute_stats aggregates across a player's whole career in the corpus --
    stamped as a single row-level column for schema uniformity with atlas_h2h.
    """
    if corpus_dir is None:
        corpus_dir = DEFAULT_CORPUS
    corpus_dir = pathlib.Path(corpus_dir)
    matches, players = _load_corpus(corpus_dir)

    stats = _compute_stats(matches, players)
    as_of = as_of or dt.date.today().isoformat()

    stats = stats.copy()
    stats["as_of"] = as_of
    stats["corpus_id"] = CORPUS_ID
    # Corpus-level season span (single int if matches span one year, else the max year
    # observed -- recorded honestly as corpus_season_max alongside corpus_season_min).
    match_years = pd.to_datetime(matches["date"], errors="coerce").dt.year
    stats["corpus_season_min"] = int(match_years.min()) if len(match_years) else None
    stats["corpus_season_max"] = int(match_years.max()) if len(match_years) else None

    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stats.to_parquet(out_path, index=False)

    return PersistResult(out_path=out_path, row_count=len(stats), columns=list(stats.columns))


def persist_h2h(
    out_path: pathlib.Path,
    corpus_dir: Optional[pathlib.Path] = None,
    as_of: Optional[str] = None,
) -> PersistResult:
    """Compute per-match pair-keyed H2H rows (via atlas_h2h._compute_pair_stats)
    and persist to parquet with provenance columns, preserving p1_id/p2_id
    (the pair-entity key the claims-contract extension will use later).

    _compute_pair_stats() only carries p1_name/p2_name internally -- this
    function re-joins p1_id/p2_id from the same matches DataFrame by row
    position (both derived from the identical df, same row order, no filter
    applied before this join) so the persisted rows are PAIR-KEYED by id,
    not just by name.
    """
    if corpus_dir is None:
        corpus_dir = H2H_DEFAULT_CORPUS
    corpus_dir = pathlib.Path(corpus_dir)
    df = _load_matches(corpus_dir)
    df["date"] = df["date"].astype(str)

    pair_df = _compute_pair_stats(df)

    # _compute_pair_stats iterates df.iterrows() in order and appends one record
    # per input row with no filtering/reordering -- row i of pair_df corresponds
    # to row i of df. Assert this invariant before trusting the positional join.
    if len(pair_df) != len(df):
        raise ValueError(
            f"atlas_h2h._compute_pair_stats row count {len(pair_df)} != "
            f"input matches row count {len(df)}; positional id join would be unsafe"
        )

    pair_df = pair_df.copy()
    pair_df["p1_id"] = df["p1_id"].values
    pair_df["p2_id"] = df["p2_id"].values

    as_of = as_of or dt.date.today().isoformat()
    pair_df["as_of"] = as_of
    pair_df["corpus_id"] = CORPUS_ID
    pair_df["season"] = pd.to_datetime(pair_df["date"], errors="coerce").dt.year

    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pair_df.to_parquet(out_path, index=False)

    return PersistResult(out_path=out_path, row_count=len(pair_df), columns=list(pair_df.columns))


if __name__ == "__main__":
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    out_dir = repo_root / "data" / "domains" / "tennis"

    r1 = persist_playstyles(out_dir / "atlas_playstyles.parquet")
    print(f"atlas_playstyles.parquet: {r1.row_count} rows, {len(r1.columns)} cols -> {r1.out_path}")

    r2 = persist_h2h(out_dir / "atlas_h2h.parquet")
    print(f"atlas_h2h.parquet: {r2.row_count} rows, {len(r2.columns)} cols -> {r2.out_path}")
