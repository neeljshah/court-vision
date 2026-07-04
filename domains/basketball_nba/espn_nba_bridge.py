"""domains.basketball_nba.espn_nba_bridge -- deterministic, outcome-free id
bridge between ESPN linescores (ESPN event_id + ESPN tricodes) and NBA-stats
player_boxscores (NBA game_id + NBA-stats tricodes), GENERALIZED across ALL
overlapping seasons on disk (lane nba-bridge-expand, wave-33+).

WHY THIS MODULE EXISTS
-----------------------
The wave-33 in-game gate (scripts/platformkit/ingame/
ingame_shooterprofile_gate_nba_io.py::bridge_games) hardcoded a SINGLE
linescores file (linescores.parquet) joined against a SINGLE box-score season
slice (player_boxscores season == "2025-26"), capping the bridged corpus at
74 games -- the entire 2025-26 overlap window and nothing else. This was a
CEILING BUG, not a data ceiling: a second linescores file already sits on
disk (linescores_2024_25.parquet, 1321 ESPN event rows, 2024-10-22 ..
2025-06-22) that the gate never read. Pairing it with
player_boxscores[season=="2024-25"] (1225 unique game_id, same date window)
bridges 1225 additional games with the IDENTICAL deterministic join logic --
raising the honest on-disk ceiling from 74 to 1299 (74 + 1225).

JOIN KEY (unchanged from wave-33, verified outcome-free): (home tricode,
away tricode, calendar date) after normalizing the 6 divergent ESPN<->NBA-
stats abbreviations (GS/NO/NY/SA/UTAH/WSH -> GSW/NOP/NYK/SAS/UTA/WAS). No
score/outcome field participates in the join -- it is a pure schedule-key
match, safe to build ahead of any walk-forward split.

SEASON PAIRING (the fix): each on-disk linescores file only overlaps ONE
player_boxscores season (verified: zero event_id overlap between the two
linescores files). bridge_all_seasons() tries every (linescores_file,
box_season) pair and keeps whichever pairing actually produces matches,
so a newly-dropped linescores file for a new season is picked up without
editing this module's season list.

MATCH CONFIDENCE: this join has exactly one confidence tier in practice --
"exact" (same-day tricode match). A "date_shifted" tier is included in the
schema for future timezone-boundary cases (ESPN's `date` field is sometimes
the tip-off date in a different local convention than the box corpus) but is
NOT currently populated since the wave-33 exact-date join already recovers
the full player_boxscores-scoped ceiling (verified: the 96 unmatched
linescores_2024_25 rows are legitimately OUT of player_boxscores' regular-
season-only scope -- playoffs/play-in dates after 2025-04-13 -- not join
failures). Unmatched rows are excluded, never fabricated.

INVARIANTS: <=300 LOC; ASCII only; pandas + stdlib only; no network; never
mutates linescores.parquet or player_boxscores.parquet (read-only inputs);
outcome-free (only tricode+date participate in the join, no score fields).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_espn_nba_bridge.py -q
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ""))
_DATA_DIR = os.path.join(_REPO, "data", "domains", "basketball_nba")

# All on-disk linescores files as of this lane; add new files here as they land.
LINESCORES_FILES = [
    os.path.join(_DATA_DIR, "linescores.parquet"),
    os.path.join(_DATA_DIR, "linescores_2024_25.parquet"),
]
BOXSCORES_FILE = os.path.join(_DATA_DIR, "player_boxscores.parquet")
OUT_PATH = os.path.join(_DATA_DIR, "espn_nba_game_bridge.parquet")
CORPUS_ID = "espn_nba_bridge_v1"

# ESPN -> NBA-stats tricode normalization (only the divergent ones need mapping;
# identical to wave-33's ingame_shooterprofile_gate_nba_io._ESPN_TO_NBA).
_ESPN_TO_NBA = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
                "UTAH": "UTA", "WSH": "WAS"}

_QCOLS = ["home_q1", "home_q2", "home_q3", "home_q4",
          "away_q1", "away_q2", "away_q3", "away_q4"]


def _norm_abbr(a: str) -> str:
    a = str(a).strip().upper()
    return _ESPN_TO_NBA.get(a, a)


def load_linescores(path: str) -> pd.DataFrame:
    """Load one ESPN linescores parquet, dropping rows missing quarter scores
    (same filter wave-33 applied). Read-only; never mutates the source file."""
    df = pd.read_parquet(path).dropna(subset=_QCOLS)
    return df.sort_values("date").reset_index(drop=True)


def load_boxscores(path: str = BOXSCORES_FILE) -> pd.DataFrame:
    return pd.read_parquet(path)


def _box_games(box: pd.DataFrame) -> pd.DataFrame:
    """One row per NBA game_id: (game_id, home_nba, away_nba, _date)."""
    home_box = (box[box["is_home"] == True]  # noqa: E712
                [["game_id", "date", "team"]].drop_duplicates()
                .rename(columns={"team": "home_nba"}))
    away_box = (box[box["is_home"] == False]  # noqa: E712
                [["game_id", "date", "team"]].drop_duplicates()
                .rename(columns={"team": "away_nba"}))
    home_box["_date"] = pd.to_datetime(home_box["date"]).dt.normalize()
    away_box["_date"] = pd.to_datetime(away_box["date"]).dt.normalize()
    return home_box.merge(away_box[["game_id", "away_nba"]], on="game_id")


def bridge_one(lines: pd.DataFrame, box: pd.DataFrame) -> pd.DataFrame:
    """Deterministic, outcome-free join of one linescores slice to one
    player_boxscores slice on (home tricode, away tricode, date). Identical
    logic to wave-33's bridge_games; generalized to accept any pair of
    corpus slices rather than hardcoding a single season. Returns one row
    per matched game with match_confidence == 'exact' (only tier populated
    today; see module docstring)."""
    lines = lines.copy()
    lines["home_nba"] = lines["home_abbr"].map(_norm_abbr)
    lines["away_nba"] = lines["away_abbr"].map(_norm_abbr)
    lines["_date"] = pd.to_datetime(lines["date"]).dt.normalize()

    box_games = _box_games(box)
    merged = lines.merge(
        box_games[["game_id", "home_nba", "away_nba", "_date"]],
        on=["home_nba", "away_nba", "_date"], how="inner")
    merged = merged.drop_duplicates(subset=["event_id"]).reset_index(drop=True)
    merged["match_confidence"] = "exact"
    return merged


def bridge_all_seasons(
    linescores_paths: Optional[List[str]] = None,
    box: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, int]]]:
    """Try every (linescores_file x player_boxscores season) pairing and keep
    only pairings that actually produce matches -- so a linescores file for a
    season not yet in player_boxscores is silently skipped (reported in the
    stats dict, not silently dropped from the report) rather than crashing.
    Returns (concatenated bridge dataframe, per-pairing match-count stats)."""
    linescores_paths = linescores_paths or LINESCORES_FILES
    box_all = box if box is not None else load_boxscores()
    seasons = sorted(box_all["season"].dropna().unique().tolist())

    frames: List[pd.DataFrame] = []
    stats: Dict[str, Dict[str, int]] = {}
    for lpath in linescores_paths:
        if not os.path.exists(lpath):
            continue
        lname = os.path.basename(lpath)
        lines = load_linescores(lpath)
        best_season, best_df, best_n = None, None, -1
        for season in seasons:
            box_s = box_all[box_all["season"] == season]
            m = bridge_one(lines, box_s)
            if len(m) > best_n:
                best_season, best_df, best_n = season, m, len(m)
        stats[lname] = {
            "linescores_rows": int(lines["event_id"].nunique()),
            "best_season": best_season,
            "bridged": int(best_n),
        }
        if best_df is not None and best_n > 0:
            best_df = best_df.copy()
            best_df["season"] = best_season
            best_df["source_linescores_file"] = lname
            frames.append(best_df)

    out = (pd.concat(frames, ignore_index=True) if frames
           else pd.DataFrame(columns=["event_id", "season", "match_confidence"]))
    return out, stats


def build_and_write(out_path: str = OUT_PATH) -> Tuple[pd.DataFrame, Dict]:
    """Build the full-corpus bridge (all overlapping seasons) and persist it
    with as_of + corpus_id provenance columns, per lane spec. Returns
    (dataframe as written, summary dict) for the caller to report/print."""
    bridge, stats = bridge_all_seasons()
    as_of = datetime.now(timezone.utc).isoformat()
    bridge = bridge.copy()
    bridge["as_of"] = as_of
    bridge["corpus_id"] = CORPUS_ID
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bridge.to_parquet(out_path, index=False)
    summary = {
        "as_of": as_of, "corpus_id": CORPUS_ID,
        "total_bridged": int(len(bridge)),
        "by_season": bridge.groupby("season")["event_id"].nunique().to_dict()
        if len(bridge) else {},
        "per_file_stats": stats,
    }
    return bridge, summary


if __name__ == "__main__":
    df, summary = build_and_write()
    print("=" * 72)
    print("ESPN<->NBA game bridge (all overlapping seasons)")
    print("=" * 72)
    print(f"total bridged games : {summary['total_bridged']}")
    print(f"by season           : {summary['by_season']}")
    print(f"per-file stats       : {summary['per_file_stats']}")
    print(f"wrote                : {OUT_PATH}")
