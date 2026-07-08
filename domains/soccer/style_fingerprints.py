"""domains.soccer.style_fingerprints -- per team-season style vectors.

Builds one row per (team, season) with a normalized STYLE vector from the
finest on-disk grain this corpus supports: match_stats.parquet (shots/SOT/
fouls/corners/cards per match) joined to matches.parquet (season, via
event_id -- both parquets share the exact same event_id format, verified
this session: 25,834/25,834 match_stats rows join).

HONEST SUBSTITUTION: the task brief asks for "possession share", but this
corpus (football-data.co.uk derived) carries NO possession column at all
(census-verified this session -- match_stats.parquet's 25 columns are shots/
SOT/corners/fouls/cards only). shot_share (team shots / total match shots)
is used as the closest on-disk proxy for territorial/tempo dominance and is
labelled as a proxy everywhere it appears, never silently renamed to
"possession".

STYLE DIMENSIONS (per team-season, floor >= MIN_MATCHES=15 matches):
  shot_share          -- proxy for territorial dominance (NOT true possession)
  sot_ratio           -- shots-on-target / shots (finishing-attempt quality)
  fouls_committed_pm  -- fouls given away per match
  fouls_drawn_pm      -- fouls won (opponent's fouls against this team) per match
  corners_pm          -- corners per match
  cards_pm            -- yellow+red cards committed per match (unweighted)
Each is also emitted as a within-season z-score (z_<dim>) so style_interaction
can bucket teams into tiers without re-deriving the season population.

ppg (points per game, 3/1/0) is carried alongside as a STRENGTH reference
column -- not a style dimension, used later to control for "beyond strength".

NETWORK: zero. Pure pandas over already-materialized parquets.
DESCRIPTIVE ONLY -- no market/$ edge claimed.

CLI: python -m domains.soccer.style_fingerprints
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

_MATCH_STATS = _REPO / "data/domains/soccer/match_stats.parquet"
_MATCHES = _REPO / "data/domains/soccer/matches.parquet"
_OUT = _REPO / "data/domains/soccer/style_fingerprints.parquet"

MIN_MATCHES = 15
STYLE_DIMS = (
    "shot_share", "sot_ratio", "fouls_committed_pm", "fouls_drawn_pm",
    "corners_pm", "cards_pm",
)


def _melt_team_matches(match_stats: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Join match_stats (shots/fouls/corners/cards) to matches (season, ftr),
    then melt home/away into one row per (team, match) -- team, opponent,
    season, shots_for/against, sot_for, fouls_for/against, corners_for,
    cards_for, points (3/1/0 from this team's perspective)."""
    joined = match_stats.merge(
        matches[["event_id", "season", "ftr"]], on="event_id", how="inner")

    def _side(prefix: str, opp_prefix: str, team_col: str, opp_col: str, win_code: str) -> pd.DataFrame:
        out = pd.DataFrame({
            "team": joined[team_col],
            "opponent": joined[opp_col],
            "season": joined["season"],
            "shots_for": joined[f"{prefix}_shots"],
            "shots_against": joined[f"{opp_prefix}_shots"],
            "sot_for": joined[f"{prefix}_sot"],
            "fouls_for": joined[f"{prefix}_fouls"],
            "fouls_against": joined[f"{opp_prefix}_fouls"],
            "corners_for": joined[f"{prefix}_corners"],
            "cards_for": joined[f"{prefix}_yellow"] + joined[f"{prefix}_red"],
        })
        out["points"] = joined["ftr"].map(
            {win_code: 3, "D": 1}).fillna(0.0)
        return out

    home = _side("home", "away", "home_team", "away_team", "H")
    away = _side("away", "home", "away_team", "home_team", "A")
    return pd.concat([home, away], ignore_index=True)


def build_fingerprints(
    match_stats_path: Path = _MATCH_STATS, matches_path: Path = _MATCHES,
    min_matches: int = MIN_MATCHES,
) -> pd.DataFrame:
    """Return one row per (team, season) qualifying (>=min_matches), with
    raw style metrics, z_<dim> within-season z-scores, ppg, and n_matches."""
    match_stats = pd.read_parquet(match_stats_path)
    matches = pd.read_parquet(matches_path)
    long_df = _melt_team_matches(match_stats, matches)

    grp = long_df.groupby(["team", "season"])
    n_matches = grp.size().rename("n_matches")
    agg = pd.DataFrame({
        "shot_share": grp["shots_for"].sum() / (grp["shots_for"].sum() + grp["shots_against"].sum()),
        "sot_ratio": grp["sot_for"].sum() / grp["shots_for"].sum(),
        "fouls_committed_pm": grp["fouls_for"].mean(),
        "fouls_drawn_pm": grp["fouls_against"].mean(),
        "corners_pm": grp["corners_for"].mean(),
        "cards_pm": grp["cards_for"].mean(),
        "ppg": grp["points"].mean(),
    }).join(n_matches)
    agg = agg[agg["n_matches"] >= min_matches].reset_index()

    for dim in STYLE_DIMS:
        season_mean = agg.groupby("season")[dim].transform("mean")
        season_std = agg.groupby("season")[dim].transform("std").replace(0.0, pd.NA)
        agg[f"z_{dim}"] = (agg[dim] - season_mean) / season_std

    return agg


def write_fingerprints(out_path: Path = _OUT) -> Path:
    df = build_fingerprints()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out_path)
    return out_path


def main() -> int:
    df = build_fingerprints()
    n_seasons = df["season"].nunique()
    print(f"team-season fingerprints: n_rows={len(df)} n_seasons={n_seasons} "
          f"floor=n_matches>={MIN_MATCHES}")
    print(df[["team", "season", "n_matches"] + list(STYLE_DIMS) + ["ppg"]].head(5).to_string())
    out = write_fingerprints()
    print(f"wrote -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
