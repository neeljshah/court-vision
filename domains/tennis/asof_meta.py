"""domains.tennis.asof_meta -- leak-free tennis MATCH-META covariates (ONDISK #9).

Reclaims match-meta dims already sitting in the raw Sackmann CSVs but discarded at
matches.parquet ingest (docs/research/ceiling/ONDISK_RECLAIM_TARGETS.md row #9):
height, ATP rank-points, seed, draw_size (all pre-game FACTS, leak-free directly --
recorded at match entry, not derived from the match outcome) plus a TRAILING prior-
minutes fatigue load (must never touch the match's own minutes; a match's duration is
an outcome-adjacent fact of the match itself).

ORIENTATION: mirrors ingest_sackmann._transform_matches EXACTLY -- p1 = the side with
the smaller numeric id (outcome-blind; kills ex-post label leak), independent of who
won. Every winner_*/loser_* column is re-oriented onto p1_*/p2_* via the same
winner_id <= loser_id comparison matches.parquet already used to build p1_id/p2_id,
so a merge on event_id lands each stat on the correct side.

LEAK DISCIPLINE:
  - height / rank_points / seed / draw_size: pre-game facts AS RECORDED for that
    match row (known before the match is played) -- safe to use directly, no
    trailing window needed.
  - minutes_prior_asof: TRAILING mean of the player's PRIOR matches' minutes only;
    the match's OWN minutes is dropped before joining (own-row-exclusion) and never
    contributes to that row's asof value -- validated by assert_no_future_leak().

SCOPE: ATP only (matches.parquet's spine is 100% tour=="atp"; the WTA gate keeps a
separate corpus). NETWORK: zero -- reads only cached raw CSVs + matches.parquet.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_RAW_DIR_DEFAULT = "data/domains/tennis/_raw/sackmann"
_MATCHES_DEFAULT = "data/domains/tennis/matches.parquet"
_OUT_DEFAULT = "data/domains/tennis/asof_meta.parquet"

_ROUND_ORDER: dict[str, int] = {
    "ER": 0, "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
    "RR": 5, "R128": 6, "R64": 7, "R32": 8, "R16": 9,
    "QF": 10, "SF": 11, "BR": 12, "F": 13,
}

OUT_COLS: list[str] = [
    "event_id",
    "p1_ht", "p2_ht", "diff_ht",
    "p1_rank_points", "p2_rank_points", "diff_rank_points",
    "p1_seed", "p2_seed",
    "draw_size",
    "p1_minutes_prior_asof", "p2_minutes_prior_asof", "diff_minutes_prior_asof",
    "p1_n_prior", "p2_n_prior",
]


_PATTERN_DEFAULT = "atp_matches_*.csv"


def _read_raw_year_csvs(raw_dir: str, pattern: str = _PATTERN_DEFAULT) -> pd.DataFrame:
    """Concat every cached year CSV matching ``pattern``.

    Default is the ATP glob (matches.parquet's spine is ATP-only). S111 passes the WTA
    glob with the WTA spine to build the asof_meta_wta sibling; the raw schema is the
    same Sackmann one, so the orientation and the trailing-minutes walk are unchanged.
    """
    raw = Path(raw_dir)
    frames = [pd.read_csv(p, dtype=str, low_memory=False) for p in sorted(raw.glob(pattern))]
    if not frames:
        raise FileNotFoundError(f"No {pattern} found under {raw_dir}/")
    return pd.concat(frames, ignore_index=True)


def _orient_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """Re-orient winner_*/loser_* raw columns onto p1_*/p2_* (mirrors ingest_sackmann)."""
    df = raw.copy()
    winner_id = pd.to_numeric(df["winner_id"], errors="coerce")
    loser_id = pd.to_numeric(df["loser_id"], errors="coerce")
    p1_is_winner = winner_id <= loser_id

    def _side(col_w: str, col_l: str, dtype: str) -> pd.Series:
        w = pd.to_numeric(df.get(col_w), errors="coerce")
        l = pd.to_numeric(df.get(col_l), errors="coerce")
        return w.where(p1_is_winner, l).astype(dtype)

    out = pd.DataFrame({
        "tourney_id": df["tourney_id"].astype(str),
        "match_num": pd.to_numeric(df["match_num"], errors="coerce").fillna(0).astype("int32"),
        "p1_id": winner_id.where(p1_is_winner, loser_id).astype("Int64"),
        "p2_id": loser_id.where(p1_is_winner, winner_id).astype("Int64"),
        "p1_ht": _side("winner_ht", "loser_ht", "float32"),
        "p2_ht": _side("loser_ht", "winner_ht", "float32"),
        "p1_rank_points": _side("winner_rank_points", "loser_rank_points", "float32"),
        "p2_rank_points": _side("loser_rank_points", "winner_rank_points", "float32"),
        "p1_seed": _side("winner_seed", "loser_seed", "float32"),
        "p2_seed": _side("loser_seed", "winner_seed", "float32"),
        "draw_size": pd.to_numeric(df.get("draw_size"), errors="coerce").astype("float32"),
        "minutes": pd.to_numeric(df.get("minutes"), errors="coerce").astype("float32"),
    })
    return out


def _stable_chrono_sort(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)

    def _col(name: str, default: object) -> pd.Series:
        return df[name] if name in df.columns else pd.Series([default] * n, index=df.index)

    key_df = pd.DataFrame({
        "k0": pd.to_datetime(_col("date", None)).values,
        "k1": _col("tour", "").astype(str).values,
        "k2": _col("tourney_id", "").astype(str).values,
        "k3": _col("round", "").map(_ROUND_ORDER).fillna(6).astype(int).values,
        "k4": pd.to_numeric(_col("match_num", 0), errors="coerce").fillna(0).astype("int64").values,
    }, index=df.index)
    order = key_df.sort_values(["k0", "k1", "k2", "k3", "k4"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


def assert_no_future_leak(df: pd.DataFrame) -> None:
    """Raise AssertionError if debut rows have non-NaN trailing-minutes asof."""
    bad_p1 = df.loc[df["p1_n_prior"] == 0, "p1_minutes_prior_asof"].notna().sum()
    bad_p2 = df.loc[df["p2_n_prior"] == 0, "p2_minutes_prior_asof"].notna().sum()
    if bad_p1 > 0 or bad_p2 > 0:
        raise AssertionError(
            f"Future-leak: {bad_p1} p1 / {bad_p2} p2 debut rows have non-NaN "
            "minutes_prior_asof (own-match minutes leaked into its own row)."
        )


def build_asof_meta(
    raw_dir: Optional[str] = None,
    matches: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
    pattern: str = _PATTERN_DEFAULT,
) -> Path:
    """Build leak-free tennis match-meta covariates keyed by ``event_id``.

    Pre-game facts (ht/rank_points/seed/draw_size) join directly -- they are known
    facts of the match row itself, not trailing aggregates. minutes_prior_asof is a
    strict snapshot-before-update walk forward (own-row minutes excluded). Writes
    parquet and raises AssertionError on future-leak detection. Returns written Path.
    """
    if matches is None:
        matches = pd.read_parquet(_MATCHES_DEFAULT)
    raw = _read_raw_year_csvs(raw_dir or _RAW_DIR_DEFAULT, pattern)
    oriented = _orient_raw(raw)

    spine = matches[["event_id", "date", "tour", "tourney_id", "round", "match_num",
                      "p1_id", "p2_id"]].copy()
    spine["match_num"] = pd.to_numeric(spine["match_num"], errors="coerce").fillna(0).astype("int32")
    spine["p1_id"] = pd.to_numeric(spine["p1_id"], errors="coerce").astype("Int64")
    spine["p2_id"] = pd.to_numeric(spine["p2_id"], errors="coerce").astype("Int64")

    joined = spine.merge(
        oriented, on=["tourney_id", "match_num", "p1_id", "p2_id"], how="left",
        suffixes=("", "_raw"),
    ).drop_duplicates("event_id", keep="first")
    joined = _stable_chrono_sort(joined)

    # Pre-game facts: usable directly (leak-free -- known before the match is played).
    joined["diff_ht"] = joined["p1_ht"] - joined["p2_ht"]
    joined["diff_rank_points"] = joined["p1_rank_points"] - joined["p2_rank_points"]

    # Trailing minutes fatigue: strict snapshot-before-update walk forward.
    n = len(joined)
    p1_ids = joined["p1_id"].to_numpy()
    p2_ids = joined["p2_id"].to_numpy()
    minutes = joined["minutes"].to_numpy(dtype="float64")

    sums: dict[float, float] = {}
    counts: dict[float, int] = {}
    p1_prior = np.full(n, np.nan)
    p2_prior = np.full(n, np.nan)
    p1_n = np.zeros(n, dtype="int64")
    p2_n = np.zeros(n, dtype="int64")

    for i in range(n):
        p1 = float(p1_ids[i]) if p1_ids[i] is not None and not pd.isna(p1_ids[i]) else np.nan
        p2 = float(p2_ids[i]) if p2_ids[i] is not None and not pd.isna(p2_ids[i]) else np.nan

        c1 = counts.get(p1, 0)
        p1_n[i] = c1
        if c1 > 0:
            p1_prior[i] = sums.get(p1, 0.0) / c1

        c2 = counts.get(p2, 0)
        p2_n[i] = c2
        if c2 > 0:
            p2_prior[i] = sums.get(p2, 0.0) / c2

        m = minutes[i]
        if not np.isnan(m):
            sums[p1] = sums.get(p1, 0.0) + m
            counts[p1] = c1 + 1
            sums[p2] = sums.get(p2, 0.0) + m
            counts[p2] = c2 + 1

    joined["p1_minutes_prior_asof"] = p1_prior
    joined["p2_minutes_prior_asof"] = p2_prior
    joined["diff_minutes_prior_asof"] = p1_prior - p2_prior
    joined["p1_n_prior"] = p1_n
    joined["p2_n_prior"] = p2_n

    result = joined[OUT_COLS].copy()
    assert_no_future_leak(result)

    dest = Path(out_path) if out_path is not None else Path(_OUT_DEFAULT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(result, preserve_index=False), dest)
    return dest


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build leak-free tennis match-meta as-of features")
    parser.add_argument("--raw-dir", default=_RAW_DIR_DEFAULT)
    parser.add_argument("--matches", default=_MATCHES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    parser.add_argument("--pattern", default=_PATTERN_DEFAULT)
    args = parser.parse_args()
    dest = build_asof_meta(raw_dir=args.raw_dir, out_path=args.out_path, pattern=args.pattern)
    df = pd.read_parquet(dest)
    print(f"asof_meta: {len(df)} rows -> {dest}")
    print(f"  ht coverage: {df['diff_ht'].notna().mean():.1%}")
    print(f"  rank_points coverage: {df['diff_rank_points'].notna().mean():.1%}")
    print(f"  seed coverage (either side): {(df['p1_seed'].notna() | df['p2_seed'].notna()).mean():.1%}")
    print(f"  minutes_prior_asof coverage: {df['diff_minutes_prior_asof'].notna().mean():.1%}")


if __name__ == "__main__":
    _cli()
