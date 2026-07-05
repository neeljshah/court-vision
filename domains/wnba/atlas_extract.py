"""domains.wnba.atlas_extract -- WNBA descriptive-depth WIDENING (lane
wnba-atlas). Derives NEW standalone per-player/per-team ranking-ready
parquets from the atlas tables domains/basketball_wnba's own extractors
already materialized to data/cache/ (atlas_wnba_player_box_profile.parquet,
atlas_wnba_player_shooting_profile.parquet, atlas_wnba_team_pace_shooting.
parquet) -- ZERO re-walk of the raw cdn_backfill JSON corpus, PONYTAIL rung
2 (reuse-search-first): those three source parquets already carry every raw
counting-stat column this module needs (assists_per_game, steals_per_game,
blocks_per_game, fga_per_game, fta_per_game, ft_pct_season,
opp_fg3_pct_allowed, opp_paint_pts_allowed_per_game), just not yet split
into their OWN dedicated ranking dimension.

scout_gaps said "20+ dims computable from cdn_backfill but unextracted" --
this module closes 5 of those: assist/playmaking rate, defensive-activity
(stocks: steals+blocks), shot-volume/usage, FT profile (rate+reliability),
and a team-level defense-allowed composite. It does NOT rebuild
atlas_wnba_player_shooting_profile.parquet or atlas_wnba_player_box_profile.
parquet (those already exist and are used verbatim by wnba_claims.py).

FIVE NEW DIMENSIONS, each written to data/cache/atlas_wnba_<name>.parquet:

  player_playmaking        -- assists_per_game (from box_profile)
  player_defense_activity   -- steals_per_game + blocks_per_game = stocks_per_game
                               (from box_profile)
  player_usage_volume       -- fga_per_game shot-attempt volume (from
                               shooting_profile)
  player_ft_profile         -- fta_per_game (FT-drawing rate) + ft_pct_season
                               (FT reliability) (from shooting_profile)
  team_defense_allowed       -- opp_fg3_pct_allowed + opp_paint_pts_allowed_
                               per_game combined into one descriptive
                               defense-environment composite (from
                               team_pace_shooting)

Every output row keeps the SAME provenance columns the source atlas already
carries (n/n_games(_played)/confidence/as_of/corpus_id) plus a fresh 'value'
column set to the new dimension's own headline metric -- so
scripts/platformkit/intel_validation/wnba_claims.py's existing
_full_population_ranking() helper (min_n floor + full-population, no top-N
cap) works UNCHANGED against these new parquets, exactly as it does against
the pre-existing three.

HARD RAIL (ratified power audit, same as wnba_claims.py): WNBA is
DESCRIPTIVE-ONLY at current sample sizes -- no gate, no predictive claim,
no calibration claim. This module and its downstream claims are plain
box-score/officiating-style descriptive aggregates with provenance + floor,
never a hypothesis test.

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; zero
network access; never raises (a missing/malformed source parquet degrades
to an empty output table, never a fabricated row).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/wnba/test_atlas_extract.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _REPO_ROOT / "data" / "cache"

# Source atlas parquets (already materialized by domains/basketball_wnba's
# own extractors -- read-only consumption here, never rebuilt).
_BOX_PROFILE_SRC = _CACHE_DIR / "atlas_wnba_player_box_profile.parquet"
_SHOOTING_PROFILE_SRC = _CACHE_DIR / "atlas_wnba_player_shooting_profile.parquet"
_TEAM_PACE_SRC = _CACHE_DIR / "atlas_wnba_team_pace_shooting.parquet"

CORPUS_ID = "wnba_cdn_backfill_2026"  # same single-season corpus as basketball_wnba
SEASON = "2026"


def _out_path(name: str) -> Path:
    """data/cache/atlas_wnba_<name>.parquet -- same naming convention as
    domains/basketball_wnba's atlas_write_path, distinct dimension names so
    the two builders never collide on disk."""
    return _CACHE_DIR / f"atlas_wnba_{name}.parquet"


def _read_source(path: Path) -> pd.DataFrame:
    """Read one source atlas parquet. Never raises -- a missing/corrupt
    source degrades to an empty frame (downstream builders then emit an
    empty output table, not a fabricated one)."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001 -- fail closed to empty, never crash the run
        return pd.DataFrame()


def build_player_playmaking(box: pd.DataFrame) -> pd.DataFrame:
    """Closes: assist/playmaking rate. One row per player, assists_per_game
    as the headline 'value'. Pure passthrough-plus-rename of a column
    already present in box_profile -- no new aggregation needed."""
    if box.empty or "assists_per_game" not in box.columns:
        return pd.DataFrame()
    out = box[["player_id", "player_name", "n_games_played", "assists_per_game"]].copy()
    out["value"] = out["assists_per_game"]
    out["n"] = out["n_games_played"]
    out["confidence"] = box["confidence"] if "confidence" in box.columns else None
    out["as_of"] = SEASON
    out["corpus_id"] = CORPUS_ID
    return out


def build_player_defense_activity(box: pd.DataFrame) -> pd.DataFrame:
    """Closes: defensive-activity ('stocks' = steals+blocks per game).
    Derived sum of two existing box_profile columns -- a real, if simple,
    new descriptive composite (not present as its own column upstream).

    NOT rounded here (unlike every other builder's stored column): the
    downstream claim's criteria.formula is the SAME raw expression
    ('steals_per_game + blocks_per_game'), independently re-evaluated by
    claims_validator's safe_formula.evaluate_formula (which also does not
    round). Storing a pre-rounded value here would drift by IEEE754 noise
    from that live recompute (e.g. stored 1.2667 vs recomputed
    0.8667+0.4000==1.2667000000000002) and could flip a sort-order tie
    between two entities at rank boundary -- caught by this module's own
    test_wnba_claims_ext.py real-corpus VERIFIED check. wnba_claims's
    _full_population_ranking() still rounds the DISPLAYED 'value' to 4dp,
    exactly like every other dimension; only the column used for SORTING
    stays unrounded."""
    if box.empty or not {"steals_per_game", "blocks_per_game"}.issubset(box.columns):
        return pd.DataFrame()
    out = box[["player_id", "player_name", "n_games_played",
               "steals_per_game", "blocks_per_game"]].copy()
    out["stocks_per_game"] = out["steals_per_game"].fillna(0) + out["blocks_per_game"].fillna(0)
    out["value"] = out["stocks_per_game"]
    out["n"] = out["n_games_played"]
    out["confidence"] = box["confidence"] if "confidence" in box.columns else None
    out["as_of"] = SEASON
    out["corpus_id"] = CORPUS_ID
    return out


def build_player_usage_volume(shooting: pd.DataFrame) -> pd.DataFrame:
    """Closes: shot-attempt usage/volume. fga_per_game already present in
    shooting_profile, split into its own ranking dimension (usage volume is
    a distinct descriptive question from shot QUALITY/ts_pct, which
    wnba_claims.py already ranks separately)."""
    if shooting.empty or "fga_per_game" not in shooting.columns:
        return pd.DataFrame()
    out = shooting[["player_id", "player_name", "n_games_played", "fga_per_game"]].copy()
    out["value"] = out["fga_per_game"]
    out["n"] = out["n_games_played"]
    out["confidence"] = shooting["confidence"] if "confidence" in shooting.columns else None
    out["as_of"] = SEASON
    out["corpus_id"] = CORPUS_ID
    return out


def build_player_ft_profile(shooting: pd.DataFrame) -> pd.DataFrame:
    """Closes: free-throw profile (drawing rate + reliability). Two
    existing shooting_profile columns (fta_per_game, ft_pct_season) kept
    side by side as one dimension's provenance; headline 'value' is
    ft_pct_season (reliability), matching the ts_pct-style precedent of
    ranking by the QUALITY metric with volume as a companion column."""
    if shooting.empty or not {"fta_per_game", "ft_pct_season"}.issubset(shooting.columns):
        return pd.DataFrame()
    out = shooting[["player_id", "player_name", "n_games_played",
                     "fta_per_game", "ft_pct_season"]].copy()
    out["value"] = out["ft_pct_season"]
    out["n"] = out["n_games_played"]
    out["confidence"] = shooting["confidence"] if "confidence" in shooting.columns else None
    out["as_of"] = SEASON
    out["corpus_id"] = CORPUS_ID
    return out


def build_team_defense_allowed(team_pace: pd.DataFrame) -> pd.DataFrame:
    """Closes: team-level defense-allowed composite. team_pace_shooting
    already carries opp_fg3_pct_allowed + opp_paint_pts_allowed_per_game as
    raw un-adjusted allowed rates (documented PARTIAL upstream, same
    caveat inherited here) -- this builder just gives that pair its OWN
    ranking-ready table/dimension name rather than living only inside the
    pace_shooting table. Headline 'value' = opp_paint_pts_allowed_per_game
    (points allowed is the more directly interpretable single number)."""
    if team_pace.empty or not {
        "opp_fg3_pct_allowed", "opp_paint_pts_allowed_per_game", "n_games",
    }.issubset(team_pace.columns):
        return pd.DataFrame()
    cols = ["team_id", "n_games", "opp_fg3_pct_allowed", "opp_paint_pts_allowed_per_game"]
    if "team_tricode" in team_pace.columns:
        cols.insert(1, "team_tricode")
    out = team_pace[cols].copy()
    out["value"] = out["opp_paint_pts_allowed_per_game"]
    out["n"] = out["n_games"]
    out["confidence"] = team_pace["confidence"] if "confidence" in team_pace.columns else None
    out["as_of"] = SEASON
    out["corpus_id"] = CORPUS_ID
    return out


def run_extract_atlas() -> Dict[str, int]:
    """Build + write all five new descriptive-widening parquets. Returns
    {dimension_name: n_rows}. Never raises -- an absent/malformed source
    atlas degrades that one dimension to 0 rows (no file written), the
    others proceed independently."""
    box = _read_source(_BOX_PROFILE_SRC)
    shooting = _read_source(_SHOOTING_PROFILE_SRC)
    team_pace = _read_source(_TEAM_PACE_SRC)

    builders = {
        "player_playmaking": lambda: build_player_playmaking(box),
        "player_defense_activity": lambda: build_player_defense_activity(box),
        "player_usage_volume": lambda: build_player_usage_volume(shooting),
        "player_ft_profile": lambda: build_player_ft_profile(shooting),
        "team_defense_allowed": lambda: build_team_defense_allowed(team_pace),
    }
    out: Dict[str, int] = {}
    for name, fn in builders.items():
        df = fn()
        out[name] = len(df)
        if not df.empty:
            path = _out_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".parquet.tmp")
            df.to_parquet(tmp, index=False)
            tmp.replace(path)
    return out


def _main() -> int:
    import json
    print(json.dumps(run_extract_atlas(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "build_player_playmaking", "build_player_defense_activity",
    "build_player_usage_volume", "build_player_ft_profile",
    "build_team_defense_allowed", "run_extract_atlas",
]
