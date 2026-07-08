"""domains.tennis.sackmann_pbp_ingest -- Sackmann point-by-point CSVs -> parquet.

Two independent sources, two independent parquets (schemas are unrelated):
  1. tennis_slam_pointbypoint (Grand Slam point sequences, per tournament-year CSV)
     -> data/cache/sackmann_pbp/slam_points.parquet
  2. tennis_MatchChartingProject (crowdsourced shot-by-shot charting, subset of matches)
     -> data/cache/sackmann_pbp/charting_points.parquet

LICENSE NOTE: both sources are CC BY-NC-SA 4.0. Private research use only.
PRIVATE: outputs are derived from license-restricted data; never git-add data/.

ACQUISITION NOTE (2026-07-08): JeffSackmann/tennis_slam_pointbypoint is GONE from
GitHub (account now shows public_repos=1; only tennis_MatchChartingProject remains).
The slam source here is a third-party mirror (halepmania/tennis_slam_pointbypoint,
last pushed 2015-03-10) covering 2011-2015 only -- real data, but a smaller window
than the original repo once had (which reached into the 2020s per prior manifest
fetches). No mirror with later years was found via keyless GitHub repo search.

Real per-match dates do not exist in this slam matches.csv schema (confirmed: no
date/match_date column in any tournament-year file 2011-2015) -- date falls back to
an approximate tournament-start date, flagged via date_source. Charting matches.csv
DOES carry a real per-match Date column, so charting rows never need the fallback.

NETWORK POLICY: this module is a pure transform over already-cloned repo trees.
It does zero network I/O itself -- cloning is a one-time manual/CLI step (see
_cli --clone). Tests call only the parse_*/build_* functions against fixture dirs.
"""
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Approximate Grand Slam start dates (day/month stable year to year; flagged as
# approximate whenever no real per-match date is available).
# ponytail: fixed nominal month/day per slam, not the real historical start day.
# Upgrade path: hardcode exact start dates per (slam, year) if precision matters.
_SLAM_START_MD = {
    "ausopen": (1, 15), "frenchopen": (5, 25), "wimbledon": (6, 25), "usopen": (8, 25),
}
_DATE_ALIASES = ("date", "match_date", "Date")

SLAM_CORE_COLS = [
    "match_id", "tourney", "year", "date", "date_source",
    "set_no", "game_no", "point_number", "point_server", "point_winner",
    "p1_games_won", "p2_games_won", "p1_score", "p2_score",
    "rally", "p1_ace", "p2_ace", "p1_double_fault", "p2_double_fault", "speed_kmh",
]
CHARTING_CORE_COLS = [
    "match_id", "date", "date_source", "tour", "server",
    "is_second_serve", "point_winner", "rally_length",
    "set1", "set2", "gm1", "gm2", "score_state",
]


def _tourney_start_date(tourney: str, year: int) -> pd.Timestamp:
    month, day = _SLAM_START_MD.get(tourney, (1, 1))
    return pd.Timestamp(year=int(year), month=month, day=day)


def parse_slam_file(points_path: str | Path, matches_path: str | Path) -> pd.DataFrame:
    """Parse one tournament-year's points+matches CSV pair into the core schema.

    Schema-drift tolerant: any missing optional column reads as all-null via .get().
    """
    points_path = Path(points_path)
    stem = points_path.name.removesuffix("-points.csv")
    year_str, tourney = stem.split("-", 1)
    year = int(year_str)

    pts = pd.read_csv(points_path, dtype=str)
    matches = pd.read_csv(matches_path, dtype=str) if Path(matches_path).exists() else pd.DataFrame()

    date_col = next((c for c in _DATE_ALIASES if c in matches.columns), None)
    if date_col is not None and "match_id" in matches.columns:
        m_dedup = matches.drop_duplicates(subset="match_id", keep="first")
        date_map = pd.to_datetime(m_dedup.set_index("match_id")[date_col], errors="coerce")
        date = pts["match_id"].map(date_map)
        date_source = pd.Series("match_date", index=pts.index)
        missing = date.isna()
        date = date.where(~missing, _tourney_start_date(tourney, year))
        date_source = date_source.where(~missing, "tourney_start_approx")
    else:
        date = pd.Series(_tourney_start_date(tourney, year), index=pts.index)
        date_source = pd.Series("tourney_start_approx", index=pts.index)

    def num(col: str) -> pd.Series:
        return pd.to_numeric(pts.get(col, pd.Series(dtype="float64")), errors="coerce")

    out = pd.DataFrame({
        "match_id": pts["match_id"],
        "tourney": tourney,
        "year": year,
        "date": pd.to_datetime(date).dt.date,
        "date_source": date_source,
        "set_no": num("SetNo").astype("Int64"),
        "game_no": num("GameNo").astype("Int64"),
        "point_number": num("PointNumber").astype("Int64"),
        "point_server": num("PointServer").astype("Int64"),
        "point_winner": num("PointWinner").astype("Int64"),
        "p1_games_won": num("P1GamesWon").astype("Int64"),
        "p2_games_won": num("P2GamesWon").astype("Int64"),
        "p1_score": pts.get("P1Score", pd.Series(dtype=str)),
        "p2_score": pts.get("P2Score", pd.Series(dtype=str)),
        "rally": num("Rally").astype("Int64"),
        "p1_ace": num("P1Ace").astype("Int64"),
        "p2_ace": num("P2Ace").astype("Int64"),
        "p1_double_fault": num("P1DoubleFault").astype("Int64"),
        "p2_double_fault": num("P2DoubleFault").astype("Int64"),
        "speed_kmh": num("Speed_KMH").astype("float32"),
    })
    return out[SLAM_CORE_COLS]


def build_slam_points(
    raw_dir: str = "data/domains/tennis/_raw/sackmann_pbp_repos/tennis_slam_pointbypoint",
    out_path: str = "data/cache/sackmann_pbp/slam_points.parquet",
) -> pd.DataFrame:
    frames = []
    for p in sorted(glob.glob(os.path.join(raw_dir, "*-points.csv"))):
        m = Path(p.replace("-points.csv", "-matches.csv"))
        frames.append(parse_slam_file(p, m))
    if not frames:
        raise FileNotFoundError(f"No *-points.csv files found under {raw_dir}")
    out = pd.concat(frames, ignore_index=True)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), out_path)
    return out


def parse_charting_file(points_path: str | Path, matches_path: str | Path, tour: str) -> pd.DataFrame:
    """Parse one MatchChartingProject points CSV (+ its matches CSV for dates)."""
    pts = pd.read_csv(points_path, dtype=str, low_memory=False)
    matches = pd.read_csv(matches_path, dtype=str) if Path(matches_path).exists() else pd.DataFrame()

    date_col = next((c for c in _DATE_ALIASES if c in matches.columns), None)
    if date_col is not None and "match_id" in matches.columns:
        # A handful of matches are double-charted (same match_id twice); keep first.
        m_dedup = matches.drop_duplicates(subset="match_id", keep="first")
        date_map = pd.to_datetime(m_dedup.set_index("match_id")[date_col], format="%Y%m%d", errors="coerce")
        date = pts["match_id"].map(date_map)
        date_source = pd.Series("match_date", index=pts.index)
        missing = date.isna()
        date_source = date_source.where(~missing, "missing")
    else:
        date = pd.Series(pd.NaT, index=pts.index)
        date_source = pd.Series("missing", index=pts.index)

    second_serve = pts.get("2nd", pd.Series(dtype=str))
    is_second_serve = second_serve.notna() & (second_serve.astype(str).str.strip() != "")

    out = pd.DataFrame({
        "match_id": pts["match_id"],
        "date": pd.to_datetime(date).dt.date,
        "date_source": date_source,
        "tour": tour,
        "server": pd.to_numeric(pts.get("Svr", pd.Series(dtype="float64")), errors="coerce").astype("Int64"),
        "is_second_serve": is_second_serve,
        "point_winner": pd.to_numeric(pts.get("PtWinner", pd.Series(dtype="float64")), errors="coerce").astype("Int64"),
        # ponytail: "1st"/"2nd" hold full shot notation (e.g. "4b37y1r3n#"); rally
        # length needs parsing that notation, which we deliberately skip here.
        # Upgrade path: tokenize the notation string and count shot codes.
        "rally_length": pd.Series(pd.NA, index=pts.index, dtype="Int64"),
        "set1": pd.to_numeric(pts.get("Set1", pd.Series(dtype="float64")), errors="coerce").astype("Int64"),
        "set2": pd.to_numeric(pts.get("Set2", pd.Series(dtype="float64")), errors="coerce").astype("Int64"),
        "gm1": pd.to_numeric(pts.get("Gm1", pd.Series(dtype="float64")), errors="coerce").astype("Int64"),
        "gm2": pd.to_numeric(pts.get("Gm2", pd.Series(dtype="float64")), errors="coerce").astype("Int64"),
        "score_state": pts.get("Pts", pd.Series(dtype=str)),
    })
    return out[CHARTING_CORE_COLS]


def build_charting_points(
    raw_dir: str = "data/domains/tennis/_raw/sackmann_pbp_repos/tennis_MatchChartingProject",
    out_path: str = "data/cache/sackmann_pbp/charting_points.parquet",
) -> pd.DataFrame:
    frames = []
    for tour, gender in (("m", "m"), ("w", "w")):
        matches_path = Path(raw_dir) / f"charting-{gender}-matches.csv"
        for p in sorted(glob.glob(os.path.join(raw_dir, f"charting-{gender}-points-*.csv"))):
            frames.append(parse_charting_file(p, matches_path, tour))
    if not frames:
        raise FileNotFoundError(f"No charting-*-points-*.csv files found under {raw_dir}")
    out = pd.concat(frames, ignore_index=True)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), out_path)
    return out


def _report(name: str, df: pd.DataFrame, core_cols: list[str]) -> None:
    n_matches = df["match_id"].nunique() if "match_id" in df.columns else 0
    years = pd.to_datetime(df["date"], errors="coerce").dt.year.dropna()
    yr_range = f"{int(years.min())}-{int(years.max())}" if len(years) else "n/a"
    print(f"\n{name}: n_rows={len(df)} n_matches={n_matches} year_range={yr_range}")
    print("  null rates:")
    for c in core_cols:
        rate = df[c].isna().mean() if c in df.columns else 1.0
        print(f"    {c}: {rate:.1%}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Sackmann point-by-point ingest")
    parser.add_argument("--slam-raw-dir", default="data/domains/tennis/_raw/sackmann_pbp_repos/tennis_slam_pointbypoint")
    parser.add_argument("--charting-raw-dir", default="data/domains/tennis/_raw/sackmann_pbp_repos/tennis_MatchChartingProject")
    parser.add_argument("--out-dir", default="data/cache/sackmann_pbp")
    parser.add_argument("--skip-slam", action="store_true")
    parser.add_argument("--skip-charting", action="store_true")
    args = parser.parse_args()

    was_empty = not any(Path(args.out_dir).glob("*.parquet")) if Path(args.out_dir).exists() else True

    if not args.skip_slam:
        slam_out = str(Path(args.out_dir) / "slam_points.parquet")
        slam = build_slam_points(args.slam_raw_dir, slam_out)
        _report("slam_points", slam, SLAM_CORE_COLS)

    if not args.skip_charting:
        chart_out = str(Path(args.out_dir) / "charting_points.parquet")
        chart = build_charting_points(args.charting_raw_dir, chart_out)
        _report("charting_points", chart, CHARTING_CORE_COLS)

    print(f"\ncensus: {args.out_dir} was {'EMPTY' if was_empty else 'non-empty'} before this run")


if __name__ == "__main__":
    _cli()
