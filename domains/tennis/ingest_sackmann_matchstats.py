"""domains.tennis.ingest_sackmann_matchstats — capture the rich serve/return
stats Sackmann ships but the main ingest discards, into a leak-free sidecar.

WHAT: ``build_match_stats`` re-reads the ALREADY-CACHED raw Sackmann match CSVs
(under ``data/domains/tennis/_raw/sackmann/``) and emits ONE row per match keyed
by the SAME ``event_id`` that ``ingest_sackmann._transform_matches`` produces, so
the output joins 1:1 with ``matches.parquet``.  Winner/loser serve+return stats
are RE-ORIENTED to p1/p2 with the IDENTICAL outcome-blind rule
``p1_is_winner = winner_id <= loser_id`` — the join key and the p1/p2 mapping are
therefore both independent of who won.

NETWORK: ZERO.  This is a pure transform of cached CSVs.  Import is side-effect-free.

⚠️ LEAK NOTE: the captured columns (aces, double-faults, serve points won, break
points, seed, age, rank points, derived per-match rates) are DESCRIPTIVE FACTS OF
THE MATCH ITSELF.  Using a match's own stats to predict that same match is a label
leak.  Downstream feature builders MUST consume these ONLY as PRIOR-match trailing
aggregates (e.g. a player's mean 1st-serve-win% over their previous N matches as of
the match date) — NEVER the current row.  This module only CAPTURES the substrate;
it deliberately builds NO features.  It deepens the data ceiling; no edge is claimed.

LICENSE: Sackmann tennis_atp / tennis_wta is CC BY-NC-SA — private research only;
nothing derived from it goes to the public repo.  ``data/domains/tennis/`` is never tracked.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# The raw per-match stat columns Sackmann ships (winner side; loser is l_*).
# Suffix after the w_/l_ prefix; reused verbatim for the p1_/p2_ output names.
_STAT_COLS: tuple[str, ...] = (
    "ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "SvGms", "bpSaved", "bpFaced",
)

# Output column order (event_id first, then p1 block, p2 block, shared, then rates).
_RATE_SUFFIXES: tuple[str, ...] = (
    "1st_in_pct", "1st_win_pct", "2nd_win_pct", "bp_saved_pct", "ace_rate", "df_rate",
)

OUT_COLS: list[str] = (
    ["event_id"]
    + [f"p1_{c}" for c in _STAT_COLS]
    + [f"p2_{c}" for c in _STAT_COLS]
    + ["p1_seed", "p2_seed", "p1_age", "p2_age", "p1_rank_points", "p2_rank_points", "draw_size"]
    + [f"p1_{c}" for c in _RATE_SUFFIXES]
    + [f"p2_{c}" for c in _RATE_SUFFIXES]
)


def _num(series: pd.Series) -> pd.Series:
    """Coerce to float, NaN on blank/missing (older rows have empty serve stats)."""
    return pd.to_numeric(series, errors="coerce").astype("float64")


def _get(df: pd.DataFrame, col: str) -> pd.Series:
    """Return df[col] as float-NaN series, or an all-NaN series if the col is absent."""
    if col in df.columns:
        return _num(df[col])
    return pd.Series([float("nan")] * len(df), index=df.index, dtype="float64")


def _safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """num/den, NaN where den == 0 or either side is NaN (no divide-by-zero, no crash)."""
    den_safe = den.where(den != 0)  # 0 -> NaN denom -> NaN result
    return num / den_safe


def _orient(p1_is_winner: pd.Series, win_val: pd.Series, lose_val: pd.Series) -> pd.Series:
    """Pick winner value where p1 is the winner, else loser value (outcome-blind p1/p2)."""
    return win_val.where(p1_is_winner, lose_val)


def _read_raw_frames(raw_dir: Path, tours: list[str], start_year: int, end_year: int) -> pd.DataFrame:
    """Concatenate every cached ``{tour}_matches_{yr}.csv`` found under raw_dir/sackmann/."""
    frames: list[pd.DataFrame] = []
    for tour in tours:
        for yr in range(start_year, end_year + 1):
            p = raw_dir / f"sackmann/{tour}_matches_{yr}.csv"
            if not p.exists():
                continue
            try:
                df = pd.read_csv(p, dtype=str, low_memory=False)
            except Exception:
                continue
            df["_tour"] = tour
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No match CSV files found under {raw_dir}/sackmann/")
    return pd.concat(frames, ignore_index=True)


def build_match_stats(
    raw_dir: str = "data/domains/tennis/_raw",
    out_path: Optional[str] = None,
    out_dir: str = "data/domains/tennis",
    tours: Optional[list[str]] = None,
    start_year: int = 1968,
    end_year: int = 2026,
) -> Path:
    """Capture Sackmann per-match serve/return stats into a leak-free sidecar parquet.

    Reads ONLY the cached raw CSVs (zero network).  Emits one row per match, keyed
    by the same ``event_id`` as ``matches.parquet`` with stats re-oriented to p1/p2
    via ``p1_is_winner = winner_id <= loser_id``.  Returns the written Path.
    """
    if tours is None:
        tours = ["atp", "wta"]
    raw = Path(raw_dir)
    df = _read_raw_frames(raw, tours, start_year, end_year)

    tour_col = "_tour" if "_tour" in df.columns else "tour"
    winner_id = _num(df.get("winner_id", pd.Series(dtype="float64")))
    loser_id = _num(df.get("loser_id", pd.Series(dtype="float64")))
    # IDENTICAL orientation rule to ingest_sackmann._transform_matches (line 212).
    p1_is_winner = winner_id <= loser_id

    out = pd.DataFrame(index=df.index)

    # --- event_id (must match _transform_matches exactly) ---
    p1_id = winner_id.where(p1_is_winner, loser_id).astype("Int64")
    p2_id = loser_id.where(p1_is_winner, winner_id).astype("Int64")
    date = pd.to_datetime(df.get("tourney_date", pd.Series(dtype=str)), format="%Y%m%d", errors="coerce").dt.date
    tour = df[tour_col].astype(str)
    tourney_id = df.get("tourney_id", pd.Series(dtype=str)).fillna("").astype(str)
    match_num = pd.to_numeric(df.get("match_num", pd.Series(dtype="float64")), errors="coerce").fillna(0).astype("int32")

    def _eid(i: int) -> str:
        d = date.iloc[i]
        dstr = d.strftime("%Y%m%d") if isinstance(d, dt.date) else "00000000"
        return f"{dstr}-{tour.iloc[i]}-{tourney_id.iloc[i]}-{p1_id.iloc[i]}-{p2_id.iloc[i]}-{match_num.iloc[i]}"

    out["event_id"] = [_eid(i) for i in range(len(df))]

    # --- re-oriented raw stat columns ---
    for c in _STAT_COLS:
        w, l = _get(df, f"w_{c}"), _get(df, f"l_{c}")
        out[f"p1_{c}"] = _orient(p1_is_winner, w, l)
        out[f"p2_{c}"] = _orient(p1_is_winner, l, w)

    # --- re-oriented contextual columns ---
    out["p1_seed"] = _orient(p1_is_winner, _get(df, "winner_seed"), _get(df, "loser_seed"))
    out["p2_seed"] = _orient(p1_is_winner, _get(df, "loser_seed"), _get(df, "winner_seed"))
    out["p1_age"] = _orient(p1_is_winner, _get(df, "winner_age"), _get(df, "loser_age"))
    out["p2_age"] = _orient(p1_is_winner, _get(df, "loser_age"), _get(df, "winner_age"))
    out["p1_rank_points"] = _orient(p1_is_winner, _get(df, "winner_rank_points"), _get(df, "loser_rank_points"))
    out["p2_rank_points"] = _orient(p1_is_winner, _get(df, "loser_rank_points"), _get(df, "winner_rank_points"))
    out["draw_size"] = _get(df, "draw_size")

    # --- derived per-match RATES (safe ratios; NaN when denom 0) ---
    for side in ("p1", "p2"):
        svpt = out[f"{side}_svpt"]
        first_in = out[f"{side}_1stIn"]
        out[f"{side}_1st_in_pct"] = _safe_ratio(first_in, svpt)
        out[f"{side}_1st_win_pct"] = _safe_ratio(out[f"{side}_1stWon"], first_in)
        out[f"{side}_2nd_win_pct"] = _safe_ratio(out[f"{side}_2ndWon"], svpt - first_in)
        out[f"{side}_bp_saved_pct"] = _safe_ratio(out[f"{side}_bpSaved"], out[f"{side}_bpFaced"])
        out[f"{side}_ace_rate"] = _safe_ratio(out[f"{side}_ace"], svpt)
        out[f"{side}_df_rate"] = _safe_ratio(out[f"{side}_df"], svpt)

    out = out[OUT_COLS].copy()

    # Deduplicate event_ids deterministically — IDENTICAL scheme to _transform_matches
    # so the suffixes line up for a clean 1:1 join with matches.parquet.
    if out["event_id"].duplicated().any():
        mask = out["event_id"].duplicated(keep=False)
        out.loc[mask, "event_id"] = (
            out.loc[mask, "event_id"] + "-"
            + out.loc[mask].groupby("event_id").cumcount().astype(str)
        )

    dest = Path(out_path) if out_path is not None else Path(out_dir) / "match_stats.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), dest)
    return dest


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Capture Sackmann per-match serve/return stats")
    parser.add_argument("--raw-dir", default="data/domains/tennis/_raw")
    parser.add_argument("--out-dir", default="data/domains/tennis")
    parser.add_argument("--out-path", default=None)
    parser.add_argument("--tours", default="atp,wta")
    parser.add_argument("--start-year", type=int, default=1968)
    parser.add_argument("--end-year", type=int, default=dt.date.today().year)
    args = parser.parse_args()
    tours = [t.strip() for t in args.tours.split(",")]
    dest = build_match_stats(
        raw_dir=args.raw_dir, out_path=args.out_path, out_dir=args.out_dir,
        tours=tours, start_year=args.start_year, end_year=args.end_year,
    )
    df = pd.read_parquet(dest)
    print(f"match_stats: {len(df)} rows written -> {dest}")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(df.head(3).to_string())


if __name__ == "__main__":
    _cli()
