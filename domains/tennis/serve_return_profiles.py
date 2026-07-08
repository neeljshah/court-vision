"""domains.tennis.serve_return_profiles -- per player-season serve/return
strength profiles.

Builds one row per (player_id, season, tour) with SERVE and RETURN strength,
from the finest on-disk grain this corpus supports: match_stats.parquet
(59,312 rows: raw per-match p1_/p2_ serve box stats -- ace/df/svpt/1stWon/
2ndWon/SvGms/bpSaved/bpFaced) joined to matches.parquet (ATP, 30,616 rows)
and wta_matches.parquet (WTA, 11,270 rows) via event_id for date/surface/
player-id (both joins are 100% coverage, verified this session).

SERVE/RETURN FORMULAS reused VERBATIM from the existing leak-free as-of
modules (domains.tennis.asof_hold._derive_realized,
domains.tennis.asof_return._derive_realized_return) -- same realized-stat
math, just aggregated per SEASON here (descriptive, not a trailing walk-
forward feature):
  serve_pts_won = (1stWon + 2ndWon) / svpt                (own service line)
  return_won    = 1 - (opp_1stWon + opp_2ndWon) / opp_svpt (against opp serve)

PROFILE (per player-season-tour, floor >= MIN_MATCHES=20 matches):
  serve_strength -- mean serve_pts_won across the player's matches that season
  return_strength -- mean return_won across the player's matches that season
  z_serve_strength / z_return_strength -- within (tour, season) z-scores, for
    serve_return_interaction's tier bucketing.

season = calendar year of the match date (tennis tournaments run roughly
Jan-Nov within one calendar year; unlike soccer there is no Aug-May season
convention on this tour schedule).

NETWORK: zero. DESCRIPTIVE ONLY -- no market/$ edge claimed.

CLI: python -m domains.tennis.serve_return_profiles
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis.asof_hold import _derive_realized  # noqa: E402
from domains.tennis.asof_return import _derive_realized_return  # noqa: E402

_MATCH_STATS = _REPO / "data/domains/tennis/match_stats.parquet"
_ATP_MATCHES = _REPO / "data/domains/tennis/matches.parquet"
_WTA_MATCHES = _REPO / "data/domains/tennis/wta_matches.parquet"
_OUT = _REPO / "data/domains/tennis/serve_return_profiles.parquet"

MIN_MATCHES = 20


def _join_tour(match_stats: pd.DataFrame, matches: pd.DataFrame, tour: str) -> pd.DataFrame:
    cols = ["event_id", "date", "surface", "p1_id", "p2_id", "p1_name", "p2_name"]
    joined = match_stats.merge(matches[cols], on="event_id", how="inner")
    joined = _derive_realized(joined)
    joined = _derive_realized_return(joined)
    joined["tour"] = tour
    joined["season"] = pd.to_datetime(joined["date"]).dt.year
    return joined


def _melt_players(joined: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for me, opp in (("p1", "p2"), ("p2", "p1")):
        rows.append(pd.DataFrame({
            "player_id": pd.to_numeric(joined[f"{me}_id"], errors="coerce"),
            "player_name": joined[f"{me}_name"],
            "season": joined["season"], "tour": joined["tour"], "surface": joined["surface"],
            "serve_pts_won": joined[f"{me}_svpts_won_realized"],
            "return_won": joined[f"{me}_return_won_realized"],
        }))
    long_df = pd.concat(rows, ignore_index=True)
    long_df = long_df.dropna(subset=["player_id"])
    long_df["player_id"] = long_df["player_id"].astype("int64")
    return long_df


def build_profiles(
    match_stats_path: Path = _MATCH_STATS, atp_matches_path: Path = _ATP_MATCHES,
    wta_matches_path: Path = _WTA_MATCHES, min_matches: int = MIN_MATCHES,
) -> pd.DataFrame:
    """Return one row per (player_id, season, tour) qualifying (>=min_matches
    with BOTH serve_pts_won and return_won observed), with raw + z-score
    serve/return strengths and n_matches."""
    match_stats = pd.read_parquet(match_stats_path)
    atp = _join_tour(match_stats, pd.read_parquet(atp_matches_path), "ATP")
    wta = _join_tour(match_stats, pd.read_parquet(wta_matches_path), "WTA")
    long_df = _melt_players(pd.concat([atp, wta], ignore_index=True))
    long_df = long_df.dropna(subset=["serve_pts_won", "return_won"])

    grp = long_df.groupby(["player_id", "season", "tour"])
    n_matches = grp.size().rename("n_matches")
    agg = pd.DataFrame({
        "serve_strength": grp["serve_pts_won"].mean(),
        "return_strength": grp["return_won"].mean(),
    }).join(n_matches).reset_index()
    agg = agg[agg["n_matches"] >= min_matches].reset_index(drop=True)

    for dim in ("serve_strength", "return_strength"):
        grp2 = agg.groupby(["tour", "season"])[dim]
        mean_ = grp2.transform("mean")
        std_ = grp2.transform("std").replace(0.0, pd.NA)
        agg[f"z_{dim}"] = (agg[dim] - mean_) / std_

    names = long_df.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]
    agg["player_name"] = agg["player_id"].map(names).fillna("Unknown")
    return agg


def write_profiles(out_path: Path = _OUT) -> Path:
    df = build_profiles()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out_path)
    return out_path


def main() -> int:
    df = build_profiles()
    print(f"player-season-tour profiles: n_rows={len(df)} floor=n_matches>={MIN_MATCHES}")
    for tour in ("ATP", "WTA"):
        sub = df[df["tour"] == tour]
        print(f"  {tour}: {len(sub)} rows, {sub['season'].nunique()} seasons, "
              f"{sub['player_id'].nunique()} distinct players")
    print(df[["player_name", "tour", "season", "n_matches", "serve_strength", "return_strength"]].head(5).to_string())
    out = write_profiles()
    print(f"wrote -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
