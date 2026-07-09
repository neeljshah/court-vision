"""scripts/backfill_ot_q0.py -- ESPN full-game q0 backfill for OT-truncated games.

ROOT CAUSE (task 39 follow-up, commit d136a1c6): player_boxscores.parquet is
regulation-only (q1-q4 cache) for every OT game fetched before the
fetch_per_quarter_boxscores.py OT fix -- 68 games (60 x 2024-25, 7 x 2025-26,
1 x 2023-24) where is_ot & was_truncated in game_finals_corrected.parquet.
NBA stats API hosts are WAF-blocked from this box, so the OT periods cannot
be filled via that fetcher's new period-5..8 support. This script reuses the
ALREADY-WORKING ESPN full-game q0 route (domains.basketball_nba.
ingest_espn_player_box, which backfilled the 2025-26 "missing entirely"
games) but targets the OT-truncated list specifically -- that module's own
``_missing_games`` skips any game with an existing q-file, so it never
touched these (they already have q1-q4).

The per-player quarter aggregator (ingest_boxscores._aggregate_game) SUMS
every ``{game_id}_q*.json`` file it finds -- if both q0 (full-game, OT
included) and q1-q4 (regulation-only) existed together it would double-count
every regulation stat. So once q0 is written for a target game, this script
renames the now-superseded q1-q4 files to ``.json.bak`` (excluded from the
builder's glob, kept on disk for audit) -- the same q0-only shape already
verified correct for the 2025-26 backfill games.

Politeness: reuses ingest_espn_player_box's shared-session GET (>=1.5s sleep
before every call, exponential backoff). Resume-safe: games already holding
a q0 file are skipped.

Usage
-----
    python scripts/backfill_ot_q0.py                 # fetch all missing q0
    python scripts/backfill_ot_q0.py --limit 5        # smoke test
    python -m domains.basketball_nba.ingest_boxscores  # then rebuild parquet

Per-file test (network mocked):
    cd /c/Users/neelj/nba-ai-system &&
    python -m pytest scripts/test_backfill_ot_q0.py -q
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.basketball_nba.espn_nba_bridge import _norm_abbr
from domains.basketball_nba.ingest_espn_player_box import (
    _CACHE_DIR,
    _GAMES_PARQUET,
    _SB_URL,
    _SUM_URL,
    _UA,
    _get_json,
    load_activity_windows,
    load_player_map,
    parse_summary_players,
)

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FINALS_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "game_finals_corrected.parquet"


def target_games() -> pd.DataFrame:
    """OT-truncated game_ids (is_ot & was_truncated) still missing a q0 file,
    joined with games.parquet for date/home/away (needed to find the ESPN
    event). Empty frame if the finals table has no such rows."""
    finals = pd.read_parquet(_FINALS_PARQUET)
    ot = finals.loc[finals["is_ot"] & finals["was_truncated"], ["game_id", "season"]].copy()
    ot["game_id"] = ot["game_id"].astype(str).str.zfill(10)
    games = pd.read_parquet(_GAMES_PARQUET)[["game_id", "date", "home_team", "away_team"]].copy()
    games["game_id"] = games["game_id"].astype(str).str.zfill(10)
    merged = ot.merge(games, on="game_id", how="left")
    have_q0 = {p.stem.rsplit("_q0", 1)[0] for p in _CACHE_DIR.glob("*_q0.json")}
    return merged[~merged["game_id"].isin(have_q0)].sort_values("date").reset_index(drop=True)


def replace_regulation_files(game_id: str, cache_dir: Path = _CACHE_DIR) -> int:
    """Rename {game_id}_q1..q8.json to .json.bak (excluded from the builder's
    glob) now that q0 supersedes them. Returns count moved."""
    moved = 0
    for p in cache_dir.glob(f"{game_id}_q[1-8].json"):
        p.rename(p.with_name(p.name + ".bak"))
        moved += 1
    return moved


def run(sleep: float = 1.5, limit: int = 0) -> dict:
    """Fetch ESPN q0 full-game boxscores for every OT-truncated game missing
    one. Returns counters. Resume-safe; never raises per-game."""
    todo = target_games()
    if limit > 0:
        todo = todo.head(limit)
    log.info("target OT-truncated games missing q0: %d", len(todo))

    player_map = load_player_map()
    activity = load_activity_windows()
    sess = requests.Session()
    sess.headers["User-Agent"] = _UA
    c = {"written": 0, "no_event_match": 0, "not_final": 0, "empty": 0,
         "skipped": 0, "quarters_replaced": 0}

    dates = sorted({d.strftime("%Y%m%d") for d in pd.to_datetime(todo["date"])})
    for date in dates:
        sb = _get_json(sess, _SB_URL.format(date=date), sleep)
        ev_by_teams: Dict[tuple, str] = {}
        for ev in sb.get("events") or []:
            comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
            sides = {ct.get("homeAway"): ct.get("team", {}).get("abbreviation", "") for ct in comps}
            key = (_norm_abbr(sides.get("home", "")), _norm_abbr(sides.get("away", "")))
            ev_by_teams[key] = str(ev["id"])

        day = todo[pd.to_datetime(todo["date"]).dt.strftime("%Y%m%d") == date]
        for row in day.itertuples():
            gid = row.game_id
            out = _CACHE_DIR / f"{gid}_q0.json"
            if out.exists():
                c["skipped"] += 1
                continue
            eid = ev_by_teams.get((row.home_team, row.away_team))
            if eid is None:
                c["no_event_match"] += 1
                log.warning("no ESPN event for gid=%s %s %s@%s", gid, date, row.away_team, row.home_team)
                continue
            payload = _get_json(sess, _SUM_URL.format(eid=eid), sleep)
            status = ((payload.get("header") or {}).get("competitions") or [{}])[0] \
                .get("status", {}).get("type", {}).get("name", "")
            if not str(status).upper().endswith("FINAL"):
                c["not_final"] += 1
                log.warning("gid=%s eid=%s status=%r not FINAL -- skipped", gid, eid, status)
                continue
            players = parse_summary_players(payload, player_map, season=row.season, activity=activity)
            if not players:
                c["empty"] += 1
                log.warning("gid=%s eid=%s: empty player parse -- skipped", gid, eid)
                continue
            out.write_text(json.dumps({
                "game_id": gid, "period": 0, "source": "espn_fullgame_ot_backfill",
                "espn_event_id": eid, "players": players, "teams": [],
            }, ensure_ascii=False), encoding="utf-8")
            c["quarters_replaced"] += replace_regulation_files(gid, cache_dir=_CACHE_DIR)
            c["written"] += 1
            log.info("wrote q0 gid=%s (%d players) [%d/%d]", gid, len(players), c["written"], len(todo))
    log.info("DONE %s", c)
    return c


def _main() -> None:
    ap = argparse.ArgumentParser(description="ESPN full-game q0 backfill for OT-truncated games")
    ap.add_argument("--limit", type=int, default=0, help="max games this run (0 = all missing)")
    ap.add_argument("--sleep", type=float, default=1.5)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    c = run(sleep=args.sleep, limit=args.limit)
    print(f"RESULT {c}")
    print("RUNBOOK next: python -m domains.basketball_nba.ingest_boxscores")


if __name__ == "__main__":
    _main()
