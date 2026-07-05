"""domains.basketball_wnba.atlas_extract_context -- CONTEXT parquets from the
168-game WNBA CDN backfill corpus + espn_scoreboard.parquet (zero new fetch).

LANE: wnba-context-extract (program v2 build rank 4, EXTRACTION ONLY -- no
gate, no adoption, no prediction wiring; the power audit forbids any WNBA
gate this wave). Mirrors the wave-29 atlas_extract_team.py/atlas_extract_
common.py conventions (same raw-JSON walk, same provenance columns) but at a
DIFFERENT grain than atlas_wnba_team_officials_venue: that table aggregates
crew fouls straight off the boxscore team-totals (crew-games only, no floor,
team-level attendance). This module derives crew fouls from the PLAY-BY-PLAY
foul events (per-official attribution via officialId, not just crew-total),
applies an explicit >=10-game claim floor per official, and reports
attendance/arena at GAME grain (one row per game) rather than team-aggregated.
schedule_density is a new grain entirely: per-team games-in-last-7/14-days
from the ESPN scoreboard corpus (770 rows, 2024-2026), pure date arithmetic,
no CDN dependency.

Builds THREE parquets under data/domains/wnba/:
  referee_crew_foul_rate   -- per-official personal-foul rate/game, foul
                              events pulled from playbyplay.json actionType
                              == 'foul'; claim_eligible True only when
                              n_games >= 10 (crew claim floor per lane spec).
  arena_attendance_context -- one row per game: attendance + arena fields
                              straight off boxscore.json (game grain, not
                              team-aggregated).
  schedule_density         -- per-team-game: games in the trailing 7/14 days
                              (strictly before this game's date), computed
                              from espn_scoreboard.parquet date column alone.

ZERO NEW FETCH: every function here is pure/read-only against files already
on disk. No network calls anywhere in this module.

PROVENANCE (storage R5): every row carries as_of/corpus_id/season, written at
creation, per intelligence_program.json's provenance_note.

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises
(a malformed/missing game degrades to a skipped game, not an aborted run).
EXTRACTION ONLY -- no gate, no descriptive-validity claim wired here (the
optional crew-ranking claim, if published, goes through the UNMODIFIED
scripts/platformkit/intel_validation/claims_validator.py contract, never a
new/modified validator).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_context.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from domains.basketball_wnba.atlas_extract_common import (
    CORPUS_ID, SEASON, iter_backfilled_games,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
ESPN_SCOREBOARD_PATH = _REPO_ROOT / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
CONTEXT_OUT_DIR = _REPO_ROOT / "data" / "domains" / "wnba"

CREW_CLAIM_FLOOR = 10  # min games/official before claim_eligible=True (lane spec)


def context_write_path(name: str) -> Path:
    """data/domains/wnba/<name>.parquet -- these three tables live beside the
    corpus (data/domains/wnba/), NOT in data/cache/ like the atlas_wnba_*
    tables, matching the lane spec's 'BUILD 3 parquets under data/domains/wnba/'."""
    return CONTEXT_OUT_DIR / f"{name}.parquet"


# ---------------------------------------------------------------------------
# 1. referee_crew_foul_rate -- per-official foul rate from pbp foul events
# ---------------------------------------------------------------------------

def _foul_events(game_id: str, pbp_game: dict) -> List[Dict[str, Any]]:
    """One row per foul ACTION in *pbp_game*, attributed to the calling
    official (officialId) -- not the crew aggregate. Never raises; a
    malformed action is skipped."""
    rows: List[Dict[str, Any]] = []
    actions = pbp_game.get("actions") or []
    if not isinstance(actions, list):
        return rows
    for a in actions:
        if not isinstance(a, dict):
            continue
        if a.get("actionType") != "foul":
            continue
        official_id = a.get("officialId")
        if official_id is None:
            continue
        rows.append({
            "game_id": str(game_id),
            "official_id": str(official_id),
            "sub_type": a.get("subType"),
        })
    return rows


def _official_names(box_game: dict) -> Dict[str, str]:
    """{official_id (str) -> display name} from boxscore.json's officials
    list for this one game. Merged across games by first-seen (names are
    stable per person)."""
    out: Dict[str, str] = {}
    officials = box_game.get("officials") or []
    if not isinstance(officials, list):
        return out
    for o in officials:
        if not isinstance(o, dict):
            continue
        pid = o.get("personId")
        if pid is None:
            continue
        out[str(pid)] = o.get("name") or o.get("nameI") or str(pid)
    return out


def build_referee_crew_foul_rate() -> pd.DataFrame:
    """Closes: referee_crew_tendencies (per-OFFICIAL grain, pbp-derived).
    One row per official: personal-foul-call rate per game they officiated,
    n_games = distinct games with >=1 attributed foul call, claim_eligible
    True only when n_games >= CREW_CLAIM_FLOOR (10)."""
    foul_rows: List[Dict[str, Any]] = []
    name_map: Dict[str, str] = {}
    n_games = 0
    for gid, pair in iter_backfilled_games():
        events = _foul_events(gid, pair["playbyplay"])
        if events:
            foul_rows.extend(events)
        names = _official_names(pair["boxscore"])
        for pid, nm in names.items():
            name_map.setdefault(pid, nm)
        n_games += 1
    logger.info("atlas_extract_context: %d foul events from %d games", len(foul_rows), n_games)
    if not foul_rows:
        return pd.DataFrame()
    fr = pd.DataFrame(foul_rows)
    rows = []
    for oid, g in fr.groupby("official_id"):
        games_officiated = g["game_id"].nunique()
        total_fouls = len(g)
        rows.append({
            "official_id": oid,
            "official_name": name_map.get(oid, oid),
            "n_games": games_officiated,
            "total_fouls_called": total_fouls,
            "fouls_per_game": round(total_fouls / games_officiated, 4) if games_officiated else None,
            "claim_eligible": games_officiated >= CREW_CLAIM_FLOOR,
            "value": round(total_fouls / games_officiated, 4) if games_officiated else 0.0,
            "n": games_officiated,
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
            "season": SEASON,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. arena_attendance_context -- GAME-grain attendance + arena
# ---------------------------------------------------------------------------

def build_arena_attendance_context() -> pd.DataFrame:
    """Closes: arena_attendance_context, one row PER GAME (not team-
    aggregated) with attendance + arena fields straight off boxscore.json."""
    rows: List[Dict[str, Any]] = []
    for gid, pair in iter_backfilled_games():
        box = pair["boxscore"]
        arena = box.get("arena") or {}
        home = box.get("homeTeam") or {}
        away = box.get("awayTeam") or {}
        rows.append({
            "game_id": str(gid),
            "home_team_tricode": home.get("teamTricode"),
            "away_team_tricode": away.get("teamTricode"),
            "attendance": box.get("attendance"),
            "sellout": box.get("sellout"),
            "arena_name": arena.get("arenaName"),
            "arena_city": arena.get("arenaCity"),
            "arena_state": arena.get("arenaState"),
            "game_et": box.get("gameEt"),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
            "season": SEASON,
        })
    logger.info("atlas_extract_context: %d game-level attendance rows", len(rows))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. schedule_density -- per-team-game games-in-last-7/14-days
# ---------------------------------------------------------------------------

def _team_game_log(scoreboard: pd.DataFrame) -> pd.DataFrame:
    """Long form: one row per (team, game date), from the wide home/away
    espn_scoreboard frame. Pure reshape, no I/O."""
    if scoreboard.empty:
        return pd.DataFrame()
    home = scoreboard[["event_id", "date", "season", "home_team"]].rename(
        columns={"home_team": "team"})
    away = scoreboard[["event_id", "date", "season", "away_team"]].rename(
        columns={"away_team": "team"})
    long = pd.concat([home, away], ignore_index=True)
    return long.dropna(subset=["team", "date"])


def build_schedule_density(scoreboard: pd.DataFrame = None) -> pd.DataFrame:
    """Closes: schedule_density. Per-team-game row: count of that team's
    OTHER games strictly within the trailing 7/14 days (date arithmetic only,
    no CDN join -- pure espn_scoreboard.parquet). One row per (team, game
    date, event_id) so back-to-back sequences are directly queryable."""
    if scoreboard is None:
        if not ESPN_SCOREBOARD_PATH.exists():
            return pd.DataFrame()
        try:
            scoreboard = pd.read_parquet(ESPN_SCOREBOARD_PATH)
        except (OSError, ValueError):
            return pd.DataFrame()
    long = _team_game_log(scoreboard)
    if long.empty:
        return pd.DataFrame()
    long = long.sort_values(["team", "date"]).reset_index(drop=True)
    rows: List[Dict[str, Any]] = []
    for team, g in long.groupby("team"):
        dates = g["date"].tolist()
        event_ids = g["event_id"].tolist()
        seasons = g["season"].tolist()
        for i, (d, eid, seas) in enumerate(zip(dates, event_ids, seasons)):
            window7 = sum(1 for other in dates if other != d and 0 < (d - other).days <= 7)
            window14 = sum(1 for other in dates if other != d and 0 < (d - other).days <= 14)
            rows.append({
                "team": team,
                "event_id": str(eid),
                "date": d,
                "season": seas,
                "games_last_7d": window7,
                "games_last_14d": window14,
                "as_of": SEASON,
                "corpus_id": "wnba_espn_scoreboard",
            })
    logger.info("atlas_extract_context: %d schedule_density rows across %d teams",
                len(rows), long["team"].nunique())
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_extract_context() -> Dict[str, int]:
    """Build + write all three context parquets. Returns {table: n_rows}."""
    tables = {
        "referee_crew_foul_rate": build_referee_crew_foul_rate(),
        "arena_attendance_context": build_arena_attendance_context(),
        "schedule_density": build_schedule_density(),
    }
    out: Dict[str, int] = {}
    for name, df in tables.items():
        out[name] = len(df)
        if not df.empty:
            path = context_write_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".parquet.tmp")
            df.to_parquet(tmp, index=False)
            tmp.replace(path)
    return out


def _main() -> int:
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_extract_context(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "CREW_CLAIM_FLOOR", "context_write_path",
    "build_referee_crew_foul_rate", "build_arena_attendance_context",
    "build_schedule_density", "run_extract_context",
]
