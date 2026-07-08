"""domains.basketball_nba.ingest_espn_player_box -- ESPN full-game PLAYER boxes
-> quarter_box cache (2025-26 backfill).

Backfills the 2025-26 player-box gap (74/1156 games): stats.nba.com is BLOCKED
from this box; ESPN site.api is the documented working route. NOT the same as
ingest_espn_box.py (TEAM-level, own parquet) -- this module emits PER-PLAYER
lines in the exact record shape the existing pure transform
(domains.basketball_nba.ingest_boxscores) already consumes, written as ONE file
``data/cache/quarter_box/{nba_game_id}_q0.json`` per game -- ZERO changes to
the transform. period=0 marks FULL-GAME totals (honest: ESPN has no per-quarter
player box; real quarter files are q1..q4, so quarter-level consumers globbing
q1-q4 never see these).

HONEST GAPS: no quarter split; ESPN minutes are whole-integer strings; players
absent from the existing parquet name/id table (post-Jan-2026 debuts) get a
SYNTHETIC negative id = -espn_id and are logged -- they aggregate fine within
2025-26 but will not join across seasons by id.

ID MAPPING: parquet uses NBA player_ids; ESPN athlete ids differ. Mapped via
accent-stripped lowercase name join against the existing parquet (verified
collision-free on the 627-player table). ESPN events map to NBA game_ids via
(date, home_abbr, away_abbr) against games.parquet, with the bridge module's
tricode normalizer.

Politeness: one shared requests.Session, >=1.5s sleep before EVERY call,
exponential backoff on errors. Resume-safe: a game with ANY existing
{gid}_q*.json is skipped (also protects the 74 real-quarter games from
double counting).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/domains/basketball_nba/test_ingest_espn_player_box.py -q
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests

from domains.basketball_nba.espn_nba_bridge import _norm_abbr

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _REPO_ROOT / "data" / "cache" / "quarter_box"
_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_BOX_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_FLAGS_PATH = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "id_resolution_flags.jsonl"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_SB_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date}"
_SUM_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={eid}"

# ESPN stat key -> output field(s). Dash keys split into (made, att).
_DASH_KEYS = {
    "fieldGoalsMade-fieldGoalsAttempted": ("fgm", "fga"),
    "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("fg3m", "fg3a"),
    "freeThrowsMade-freeThrowsAttempted": ("ftm", "fta"),
}
_SCALAR_KEYS = {
    "points": "pts", "rebounds": "reb", "offensiveRebounds": "oreb",
    "defensiveRebounds": "dreb", "assists": "ast", "steals": "stl",
    "blocks": "blk", "turnovers": "to", "fouls": "pf", "plusMinus": "plus_minus",
}


def _norm_name(s: str) -> str:
    """Accent-stripped lowercase name key; drops Jr/Sr/II-V suffixes."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]", "", s.lower())
    return " ".join(p for p in s.split() if p not in ("jr", "sr", "ii", "iii", "iv", "v"))


def load_player_map(box_parquet: Path = _BOX_PARQUET) -> Dict[str, int]:
    """norm_name -> NBA player_id from the existing parquet (collision-free)."""
    b = pd.read_parquet(box_parquet, columns=["player_id", "player_name"]).drop_duplicates()
    return {_norm_name(n): int(pid) for pid, n in zip(b["player_id"], b["player_name"])}


def _season_start_year(season: object) -> object:
    """Leading 4-digit start year of a season label ('2024-25' -> 2024); None if unparseable."""
    m = re.match(r"(\d{4})", str(season))
    return int(m.group(1)) if m else None


def load_activity_windows(box_parquet: Path = _BOX_PARQUET) -> Dict[int, set]:
    """player_id -> set of season START-YEARS present in the box parquet.

    The self-contained basis for ``is_stale_resolution``: as the box parquet
    accrues seasons, a name-join that lands on a long-retired player's id
    becomes detectable purely from the id's own on-disk activity span.
    """
    b = pd.read_parquet(box_parquet, columns=["player_id", "season"]).drop_duplicates()
    out: Dict[int, set] = {}
    for pid, season in zip(b["player_id"], b["season"]):
        y = _season_start_year(season)
        if y is not None:
            out.setdefault(int(pid), set()).add(y)
    return out


def is_stale_resolution(pid: int, season: object, activity: Dict[int, set]) -> bool:
    """CONSERVATIVE guard: True iff a name-join to *pid* looks like a retired /
    wrong athlete rather than a legitimate current or returning player.

    Rule -- derived ENTIRELY from the box parquet's own season coverage
    (``activity`` = player_id -> set of season start-years). Flag TRUE only when
    ALL hold:
      * *pid* has box rows in some season BEFORE ``season`` (a prior history), AND
      * its most-recent prior season is >= 2 FULL seasons stale, i.e.
        ``current_start - last_prior_start >= 3`` (e.g. last 2021-22 vs a
        2024-25 game: 2024 - 2021 = 3), AND
      * *pid* has NO rows in an ADJACENT season (start-year ``current-1`` or
        ``current+1``).

    Deliberately DOES NOT flag: an id with no prior rows (a debut/rookie); a
    player who missed exactly ONE season then returned (``last_prior_start ==
    current-2`` -> gap 2, below the >=3 bar); anyone active in an adjacent
    season. Absent that stale-then-silent signature the join is accepted.
    """
    cur = _season_start_year(season)
    if cur is None:
        return False
    yrs = activity.get(int(pid))
    if not yrs:
        return False
    prior = [y for y in yrs if y < cur]
    if not prior:
        return False
    if any(y in (cur - 1, cur + 1) for y in yrs):
        return False
    return max(prior) <= cur - 3


def _num(s: object) -> float:
    try:
        return float(str(s).replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


def parse_summary_players(payload: dict, player_map: Dict[str, int],
                          season: object = None, activity: Dict[int, set] = None,
                          roster_ids: Dict[str, set] = None) -> List[dict]:
    """ESPN summary payload -> quarter_box-shaped player records (pure, no I/O).

    Unmapped names get player_id = -espn_id (synthetic; caller logs via the
    'player_id_mapped' flag). DNP athletes (empty stats) are skipped.

    ID-RESOLUTION GUARD (root cause of the Elfrid-Payton contamination): when
    ``season`` is given, a name-join that resolves to an id is REJECTED to the
    same negative-placeholder convention (and marked with ``resolution_flag`` +
    ``rejected_id`` so the caller can log it) if EITHER
      * ``activity`` is given and ``is_stale_resolution`` fires (the id's box
        activity is >= 2 full seasons stale -- a retired/wrong athlete), OR
      * ``roster_ids`` is given (team_abbr -> set of valid ids from that
        season's PBP personIds) and the id is absent from that team's roster.
    Both default None -> guard inert (back-compat with existing callers/tests).
    """
    out: List[dict] = []
    for team_block in (payload.get("boxscore", {}).get("players") or []):
        nba_abbr = _norm_abbr(team_block.get("team", {}).get("abbreviation", ""))
        for stat_block in team_block.get("statistics") or []:
            keys = stat_block.get("keys") or []
            for ath in stat_block.get("athletes") or []:
                stats = ath.get("stats") or []
                if ath.get("didNotPlay") or not stats:
                    continue
                by_key = dict(zip(keys, stats))
                meta = ath.get("athlete") or {}
                name = str(meta.get("displayName", ""))
                espn_id = int(meta.get("id", 0) or 0)
                resolved = player_map.get(_norm_name(name))
                reason = None
                if resolved is not None and season is not None:
                    if activity is not None and is_stale_resolution(resolved, season, activity):
                        reason = "stale_id_ge2_seasons"
                    elif roster_ids is not None and resolved not in roster_ids.get(nba_abbr, set()):
                        reason = "roster_absent"
                nba_id = None if reason else resolved
                rec = {
                    "player_id": nba_id if nba_id is not None else -espn_id,
                    "player_id_mapped": nba_id is not None,
                    "espn_player_id": espn_id,
                    "player_name": name,
                    "team_abbreviation": nba_abbr,
                    "start_position": "F" if ath.get("starter") else "",
                    "min": str(by_key.get("minutes", "0")),
                }
                if reason:
                    rec["resolution_flag"] = reason
                    rec["rejected_id"] = int(resolved)
                for k, (mf, af) in _DASH_KEYS.items():
                    parts = str(by_key.get(k, "0-0")).split("-")
                    rec[mf] = _num(parts[0])
                    rec[af] = _num(parts[1]) if len(parts) > 1 else 0.0
                for k, f in _SCALAR_KEYS.items():
                    rec[f] = _num(by_key.get(k, 0))
                out.append(rec)
    return out


def _get_json(sess: requests.Session, url: str, sleep: float, tries: int = 4) -> dict:
    """Polite GET: baseline sleep BEFORE every call, exponential backoff on error."""
    for attempt in range(tries):
        time.sleep(sleep if attempt == 0 else sleep * (2 ** attempt))
        try:
            r = sess.get(url, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("fetch fail (try %d/%d) %s: %s", attempt + 1, tries, url, exc)
    return {}


def _missing_games(season: str) -> pd.DataFrame:
    """games.parquet rows for *season* with NO quarter_box cache file at all."""
    g = pd.read_parquet(_GAMES_PARQUET)
    g = g[g["season"] == season].copy()
    cached = {fp.stem.rsplit("_q", 1)[0] for fp in _CACHE_DIR.glob("*_q*.json")}
    return g[~g["game_id"].astype(str).isin(cached)].sort_values("date")


def backfill(season: str = "2025-26", limit: int = 0, sleep: float = 1.5) -> dict:
    """Fetch ESPN player boxes for every uncached game of *season*; write q0 files.

    Returns counters dict. Resume-safe; FINAL-status gate; never raises per-game.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    player_map = load_player_map()
    activity = load_activity_windows()  # as-of snapshot; feeds the stale-id guard
    todo = _missing_games(season)
    if limit > 0:
        todo = todo.head(limit)
    dates = sorted({d.strftime("%Y%m%d") for d in pd.to_datetime(todo["date"])})
    log.info("season=%s missing_games=%d dates=%d", season, len(todo), len(dates))

    sess = requests.Session()
    sess.headers["User-Agent"] = _UA
    c = {"written": 0, "no_event_match": 0, "not_final": 0, "empty": 0,
         "unmapped_players": 0, "id_flagged": 0}

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
            gid = str(row.game_id)
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
            players = parse_summary_players(payload, player_map, season=season, activity=activity)
            if not players:
                c["empty"] += 1
                log.warning("gid=%s eid=%s: empty player parse -- skipped", gid, eid)
                continue
            flagged = [p for p in players if p.get("resolution_flag")]
            if flagged:
                with _FLAGS_PATH.open("a", encoding="utf-8") as fh:
                    for p in flagged:
                        fh.write(json.dumps({
                            "game_id": gid, "season": season, "team": p["team_abbreviation"],
                            "espn_name": p["player_name"], "rejected_id": p["rejected_id"],
                            "reason": p["resolution_flag"],
                        }, ensure_ascii=False) + "\n")
                c["id_flagged"] += len(flagged)
                log.warning("gid=%s rejected %d stale/roster-absent id-joins", gid, len(flagged))
            unmapped = [p["player_name"] for p in players if not p["player_id_mapped"]]
            if unmapped:
                c["unmapped_players"] += len(unmapped)
                log.info("gid=%s unmapped names (synthetic neg ids): %s", gid, unmapped)
            out = _CACHE_DIR / f"{gid}_q0.json"
            out.write_text(json.dumps({
                "game_id": gid, "period": 0, "source": "espn_fullgame",
                "espn_event_id": eid, "players": players, "teams": [],
            }, ensure_ascii=False), encoding="utf-8")
            c["written"] += 1
            log.info("wrote %s (%d players) [%d/%d]", out.name, len(players), c["written"], len(todo))
    log.info("DONE %s", c)
    return c


def _main() -> None:
    ap = argparse.ArgumentParser(description="ESPN NBA full-game PLAYER box backfill -> quarter_box q0 cache")
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--limit", type=int, default=0, help="max games this run (0 = all missing)")
    ap.add_argument("--sleep", type=float, default=1.5)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    c = backfill(season=args.season, limit=args.limit, sleep=args.sleep)
    print(f"RESULT {c}")
    print("RUNBOOK after full backfill completes:")
    print("  1. python -m domains.basketball_nba.ingest_boxscores   # rebuild parquet")
    print("  2. python scripts/platformkit/intel_validation/nba_canonical_shooter_claims.py --season 2025-26")
    print("  3. run the claims validator on the emitted claim")


if __name__ == "__main__":
    _main()
