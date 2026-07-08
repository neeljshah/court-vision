"""domains.basketball_nba.backfill_pbp_espn -- ESPN-derived NBA play-by-play backfill.

CONTEXT: cdn.nba.com's playbyplay/boxscore endpoints (source of the existing
196-game data/cache/team_system/pbp/*.json corpus) are WAF-BLOCKED from this
box at BOTH the plain and stealth fetch tiers -- re-verified this wave (fresh
403 on a 2025-26 gameId not yet cached, plain urllib AND stealth_fetch),
matching cdn_probe's prior BLOCKED verdict. ESPN's free site.api summary DOES
carry substitution events (``type.text=="Substitution"``, ``text``=
"X enters the game for Y") plus shot coordinates in ``plays[]`` -- unlike the
CDN, usable for lineup reconstruction.

Converts ``plays[]`` into the SAME liveData-shaped JSON
(``{"meta":..., "game":{"gameId":..., "actions":[...]}}``) at the SAME path
so pbp_lineups.py/on_off.py/gravity_spacing.py need ZERO changes. Populated
with real values: actionNumber, clock, period, teamId, teamTricode, personId,
scoreHome/Away, and -- substitution (subType in/out), 2pt/3pt/freethrow
(shotResult + x/y in ESPN's own coordinate scale, fine for on_off's
make/miss counts and gravity_spacing's PAIRWISE-within-corpus distances).
Everything else (rebound/turnover/foul/timeout/period-lifecycle) collapses
to generic ``actionType="other"`` -- lineup reconstruction only branches on
``actionType=="substitution"`` vs not. HONESTLY narrower than the real feed
-- not a drop-in for pbp_mapper.py's full taxonomy; ``meta.source`` says so.

ID MAPPING (all reused, nothing invented): ESPN tricode -> NBA tricode via
espn_nba_bridge._norm_abbr; tricode -> real numeric team_id harvested from
the EXISTING 196-game cache; athlete_id -> NBA person_id via this game's own
boxscore.players block (id->name) then ingest_espn_player_box.load_player_map
(name->id, season-complete player_boxscores.parquet) -- unmapped -> personId
None, never fabricated; game_id <-> event_id via (date, home, away) per-date
scoreboard, same join as ingest_espn_player_box.backfill(); clock parse
reuses ingest_pbp_states._clock_seconds.

Politeness: one shared requests.Session, sleep before every call, retry-once
on failure, on-disk skip (resumable). INVARIANTS: domains/+data/cache only;
<=300 LOC; ASCII; never touches src/kernel/api/intel.
Per-file test: python -m pytest domains/basketball_nba/test_backfill_pbp_espn.py -q
CLI: python -m domains.basketball_nba.backfill_pbp_espn --season 2025-26
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from domains.basketball_nba.espn_nba_bridge import _norm_abbr
from domains.basketball_nba.ingest_espn_player_box import (
    _norm_name, is_stale_resolution, load_activity_windows, load_player_map,
)
from domains.basketball_nba.ingest_pbp_states import _clock_seconds

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PBP_DIR = _REPO_ROOT / "data" / "cache" / "team_system" / "pbp"
_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_SB_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date}"
_SUM_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={eid}"

_SUB_RE = re.compile(r"^(.*) enters the game for (.*)$")


# ---------------------------------------------------------------------------
# Pure helpers (no I/O) -- covered by the per-file test with a mocked payload.
# ---------------------------------------------------------------------------

def _pt_clock(seconds_remaining: float) -> str:
    """seconds-remaining-in-period -> NBA liveData clock string ('PTxMy.yyS')."""
    m = int(seconds_remaining // 60)
    s = seconds_remaining - 60 * m
    return f"PT{m}M{s:.2f}S"


def _real_team_id_map(pbp_dir: Path = _PBP_DIR) -> Dict[str, int]:
    """tricode -> real NBA numeric team_id, harvested from the existing cached
    liveData files (ground truth already on disk; no hardcoded/guessed ids)."""
    mapping: Dict[str, int] = {}
    for fp in sorted(pbp_dir.glob("*.json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 -- a corrupt cache file must not abort the scan
            continue
        for a in d.get("game", {}).get("actions", []):
            tid, tc = a.get("teamId"), a.get("teamTricode")
            if tid and tc and tc not in mapping:
                mapping[tc] = int(tid)
        if len(mapping) >= 30:
            break
    return mapping


def _team_map_from_summary(payload: dict, real_ids: Dict[str, int]) -> Dict[str, dict]:
    """ESPN team_id -> {tricode, team_id} for the two teams in *payload*."""
    comps = ((payload.get("header") or {}).get("competitions") or [{}])[0].get("competitors") or []
    out: Dict[str, dict] = {}
    for ct in comps:
        espn_id = str((ct.get("team") or {}).get("id", ""))
        abbr = _norm_abbr((ct.get("team") or {}).get("abbreviation", ""))
        rid = real_ids.get(abbr)
        if espn_id and rid:
            out[espn_id] = {"tricode": abbr, "team_id": rid}
    return out


def _espn_id_to_name(payload: dict) -> Dict[int, str]:
    """ESPN athlete_id -> displayName, from this game's own boxscore.players block."""
    out: Dict[int, str] = {}
    for team_block in (payload.get("boxscore", {}).get("players") or []):
        for stat_block in team_block.get("statistics") or []:
            for ath in stat_block.get("athletes") or []:
                meta = ath.get("athlete") or {}
                aid = meta.get("id")
                if aid:
                    out[int(aid)] = str(meta.get("displayName", ""))
    return out


def _guard_stale(pid: Optional[int], season: object, activity: Optional[Dict[int, set]]) -> Optional[int]:
    """Reject a name-join to a >=2-season-stale id (retired/wrong athlete) ->
    None (unmapped), mirroring ingest_espn_player_box's box guard. Inert when
    season/activity are None (back-compat: existing tests pass unchanged)."""
    if pid is not None and season is not None and activity is not None \
            and is_stale_resolution(pid, season, activity):
        return None
    return pid


def _resolve_id(espn_id: Optional[object], id_to_name: Dict[int, str], player_map: Dict[str, int],
                season: object = None, activity: Optional[Dict[int, set]] = None) -> Optional[int]:
    if not espn_id:
        return None
    name = id_to_name.get(int(espn_id))
    if not name:
        return None
    return _guard_stale(player_map.get(_norm_name(name)), season, activity)


def _convert_play(play: dict, team_map: Dict[str, dict], id_to_name: Dict[int, str], player_map: Dict[str, int],
                  season: object = None, activity: Optional[Dict[int, set]] = None) -> List[dict]:
    """One ESPN play -> 0, 1, or 2 liveData-shaped actions (2 for a substitution:
    'out' then 'in', matching the real NBA feed's own two-record convention)."""
    team_info = team_map.get(str((play.get("team") or {}).get("id", "")))
    if team_info is None:
        return []
    clock_s = _clock_seconds((play.get("clock") or {}).get("displayValue")) or 0.0
    base = {
        "clock": _pt_clock(clock_s),
        "period": int((play.get("period") or {}).get("number", 1) or 1),
        "teamId": team_info["team_id"],
        "teamTricode": team_info["tricode"],
        "scoreHome": play.get("homeScore"),
        "scoreAway": play.get("awayScore"),
        "description": play.get("text", ""),
        "x": None, "y": None,
    }
    parts = play.get("participants") or []
    type_text = (play.get("type") or {}).get("text", "")
    pts_att = play.get("pointsAttempted") or 0
    if type_text != "Substitution":
        pid = _resolve_id((parts[0].get("athlete") or {}).get("id") if parts else None,
                          id_to_name, player_map, season, activity)
        if play.get("shootingPlay") and pts_att in (1, 2, 3):
            # shot/FT: on_off.py/gravity_spacing.py key off 2pt/3pt + real x/y;
            # ESPN garbage-sentinels a FT's coordinate (~-2.1e9) -> drop out-of-court.
            coord = play.get("coordinate") or {}
            x, y = coord.get("x"), coord.get("y")
            if x is None or y is None or abs(x) > 1000 or abs(y) > 1000:
                x = y = None
            else:
                # ESPN feet (x=width 0-50, y=length-from-baseline) -> CDN percent
                # convention (x=length/94, y=width/50); verified via ~25ft 3pt dists.
                x, y = float(y) / 94.0 * 100.0, float(x) / 50.0 * 100.0
            kind = "freethrow" if pts_att == 1 else ("3pt" if pts_att == 3 else "2pt")
            return [{**base, "actionType": kind, "subType": "", "personId": pid,
                     "shotResult": "Made" if play.get("scoringPlay") else "Missed",
                     "x": x, "y": y}]
        return [{**base, "actionType": "other", "subType": "", "personId": pid}]

    m = _SUB_RE.match(play.get("text", "") or "")
    in_id = _guard_stale(player_map.get(_norm_name(m.group(1).strip())) if m else None, season, activity)
    out_id = _guard_stale(player_map.get(_norm_name(m.group(2).strip())) if m else None, season, activity)
    if in_id is None and len(parts) > 0:
        in_id = _resolve_id((parts[0].get("athlete") or {}).get("id"), id_to_name, player_map, season, activity)
    if out_id is None and len(parts) > 1:
        out_id = _resolve_id((parts[1].get("athlete") or {}).get("id"), id_to_name, player_map, season, activity)
    return [
        {**base, "actionType": "substitution", "subType": "out", "personId": out_id},
        {**base, "actionType": "substitution", "subType": "in", "personId": in_id},
    ]


def convert_game_actions(payload: dict, real_ids: Dict[str, int], player_map: Dict[str, int],
                         season: object = None, activity: Optional[Dict[int, set]] = None) -> Tuple[List[dict], int]:
    """PURE: ESPN summary payload -> (actions list, n_unmapped_sub_person_ids).

    When ``season``/``activity`` are given, name-joins to a >=2-season-stale id
    are rejected to personId None (the retired/wrong-athlete guard); default
    None keeps the guard inert."""
    team_map = _team_map_from_summary(payload, real_ids)
    id_to_name = _espn_id_to_name(payload)
    actions: List[dict] = []
    unmapped = 0
    for play in payload.get("plays") or []:
        for a in _convert_play(play, team_map, id_to_name, player_map, season, activity):
            if a["actionType"] == "substitution" and a.get("personId") is None:
                unmapped += 1
            actions.append(a)
    for i, a in enumerate(actions, start=1):
        a["actionNumber"] = i
    return actions, unmapped


# ---------------------------------------------------------------------------
# Fetch / backfill layer (network + disk I/O)
# ---------------------------------------------------------------------------

def _missing_games(season: str, games_parquet: Path = _GAMES_PARQUET, pbp_dir: Path = _PBP_DIR) -> pd.DataFrame:
    g = pd.read_parquet(games_parquet)
    g = g[g["season"] == season].copy()
    cached = {fp.stem for fp in pbp_dir.glob("*.json")}
    return g[~g["game_id"].astype(str).isin(cached)].sort_values("date")


def _get_json(sess: requests.Session, url: str, sleep: float, tries: int = 2) -> dict:
    """Polite GET: sleep BEFORE every call, retry-once with backoff on error."""
    for attempt in range(tries):
        time.sleep(sleep if attempt == 0 else sleep * 2)
        try:
            r = sess.get(url, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("fetch fail (try %d/%d) %s: %s", attempt + 1, tries, url, exc)
    return {}


def backfill(season: str = "2025-26", sleep: float = 0.7, limit: int = 0,
             pbp_dir: Path = _PBP_DIR) -> dict:
    """Fetch ESPN-derived pbp for every uncached *season* game; resumable,
    on-disk skip. Returns a counters dict; never raises per-game.
    *pbp_dir* lets a different season write to a SEPARATE cache dir (team id
    map is still harvested from the original 2025-26 cache -- franchises are
    unchanged season-to-season, no need to duplicate that harvest)."""
    pbp_dir.mkdir(parents=True, exist_ok=True)
    real_ids = _real_team_id_map()
    player_map = load_player_map()
    activity = load_activity_windows()  # feeds the stale-id guard in convert_game_actions
    todo = _missing_games(season, pbp_dir=pbp_dir)
    if limit > 0:
        todo = todo.head(limit)
    dates = sorted({d.strftime("%Y%m%d") for d in pd.to_datetime(todo["date"])})
    log.info("season=%s missing=%d dates=%d", season, len(todo), len(dates))

    sess = requests.Session()
    sess.headers["User-Agent"] = _UA
    c = {"written": 0, "no_event_match": 0, "not_final": 0, "empty": 0, "unmapped_subs": 0}

    for date in dates:
        sb = _get_json(sess, _SB_URL.format(date=date), sleep)
        ev_by_teams: Dict[Tuple[str, str], str] = {}
        for ev in sb.get("events") or []:
            comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
            sides = {ct.get("homeAway"): ct.get("team", {}).get("abbreviation", "") for ct in comps}
            key = (_norm_abbr(sides.get("home", "")), _norm_abbr(sides.get("away", "")))
            ev_by_teams[key] = str(ev["id"])

        day = todo[pd.to_datetime(todo["date"]).dt.strftime("%Y%m%d") == date]
        for row in day.itertuples():
            gid = str(row.game_id)
            out_path = pbp_dir / f"{gid}.json"
            if out_path.exists():
                continue
            eid = ev_by_teams.get((row.home_team, row.away_team))
            if eid is None:
                c["no_event_match"] += 1
                log.warning("no ESPN event for gid=%s %s %s@%s", gid, date, row.away_team, row.home_team)
                continue
            sum_url = _SUM_URL.format(eid=eid)
            payload = _get_json(sess, sum_url, sleep)
            status = ((payload.get("header") or {}).get("competitions") or [{}])[0] \
                .get("status", {}).get("type", {}).get("name", "")
            if not str(status).upper().endswith("FINAL"):
                c["not_final"] += 1
                log.warning("gid=%s eid=%s status=%r not FINAL -- skipped", gid, eid, status)
                continue
            actions, unmapped = convert_game_actions(payload, real_ids, player_map, season, activity)
            if not actions:
                c["empty"] += 1
                log.warning("gid=%s eid=%s: empty action parse -- skipped", gid, eid)
                continue
            c["unmapped_subs"] += unmapped
            out = {
                "meta": {"version": 1, "code": 200, "request": sum_url,
                         "time": pd.Timestamp.utcnow().isoformat(),
                         "source": "espn_derived", "coord": "cdn_pct"},
                "game": {"gameId": gid, "actions": actions},
            }
            out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            c["written"] += 1
            log.info("wrote %s (%d actions) [%d/%d]", out_path.name, len(actions), c["written"], len(todo))
    log.info("DONE %s", c)
    return c


def _main() -> None:
    ap = argparse.ArgumentParser(description="ESPN-derived NBA pbp backfill -> team_system/pbp cache")
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--limit", type=int, default=0, help="max games this run (0 = all missing)")
    ap.add_argument("--sleep", type=float, default=0.7)
    ap.add_argument("--pbp-dir", default=None, help="override output dir (default: team_system/pbp)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pbp_dir = Path(args.pbp_dir) if args.pbp_dir else _PBP_DIR
    c = backfill(season=args.season, limit=args.limit, sleep=args.sleep, pbp_dir=pbp_dir)
    print(f"RESULT {c}")


if __name__ == "__main__":
    _main()
