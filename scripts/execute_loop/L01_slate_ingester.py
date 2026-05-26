"""
L01_slate_ingester.py — DraftKings / FanDuel DFS slate ingester.

Three-tier fallback: HTTP → cache (.cache/<book>_<date>.json, <6 h) → seed (seed_<book>_<date>.json)

Public API
----------
    SlateContest          dataclass
    get_dfs_slate(book, date, paper) -> list[SlateContest] | None
    parse_dk_contest(group_json, draftables_json) -> SlateContest
    parse_fd_contest(fd_json) -> SlateContest
    save_slate(slate, out_dir) -> str
    main()   CLI --book {dk,fd,both} --date YYYY-MM-DD --out --paper

Paper vs Live Mode
------------------
When PAPER_MODE is True (the default), the module skips all live HTTP
requests to DraftKings and FanDuel endpoints and falls back immediately
to the local cache or seed file.  No network calls are made in paper mode.
When PAPER_MODE is False (SUBMISSION_MODE=live), live HTTP is attempted
first, then cache, then seed.

    PAPER_MODE = (SUBMISSION_MODE != "live")   # module-level constant

Environment Variables:
    SUBMISSION_MODE   "paper" (default) → skip HTTP; "live" → attempt HTTP first.
                      Any value other than "live" is treated as paper mode.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Paper vs live mode gate — default is paper (no HTTP calls).
PAPER_MODE: bool = os.environ.get("SUBMISSION_MODE", "paper").lower() != "live"

_SCRIPT_DIR  = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

import src.data.nba_api_headers_patch  # noqa: F401  MUST be first nba_api-adjacent import

log = logging.getLogger(__name__)

_CACHE_TTL_SECS   = 6 * 3600
_DK_CONTESTS_URL  = "https://www.draftkings.com/lobby/getcontests?sport=NBA"
_DK_DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{group_id}/draftables"
_FD_FIXTURE_URL   = "https://api.fanduel.com/fixture-lists?sport=nba"
_DK_SPORT_ID      = 4
_MIN_PLAYERS      = 8

_DK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.draftkings.com",
    "Referer": "https://www.draftkings.com/",
}
_FD_HEADERS = {**_DK_HEADERS, "Origin": "https://www.fanduel.com", "Referer": "https://www.fanduel.com/"}

_DK_CONTEST_TYPE_MAP = {21: "classic", 96: "showdown", 195: "main"}
_DK_SLOT_MAP = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "FLEX", 6: "C", 7: "UTIL", 8: "CPT"}


@dataclass
class SlateContest:
    contest_id: str
    book: str           # "dk" | "fd"
    sport: str          # "NBA"
    slate_type: str     # "classic" | "showdown" | "main" | "single"
    salary_cap: int
    roster_slots: list  # ["PG","SG","SF","PF","C","FLEX","UTIL","UTIL"]
    lock_time: str      # ISO-8601 UTC
    game_ids: list
    players: list = field(default_factory=list)  # {name, team, position, salary, status, player_id}


# ── path / IO helpers ─────────────────────────────────────────────────────────

def _cache_path(book: str, date: str, out_dir: str) -> Path:
    p = Path(out_dir) / ".cache"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{book}_{date}.json"


def _seed_path(book: str, date: str, out_dir: str) -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    return Path(out_dir) / f"seed_{book}_{date}.json"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> Optional[datetime]:
    """Parse ISO-8601 aware datetime; handles DK's 7-digit fractional seconds."""
    if not ts:
        return None
    s = re.sub(r"(\.\d{6})\d+([\+\-Z])", r"\1\2", ts.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _is_cache_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < _CACHE_TTL_SECS


def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to load %s: %s", path, exc)
        return None


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _http_get(url: str, headers: dict) -> Optional[dict]:
    """GET url → parsed JSON, or None on any error (including 403)."""
    try:
        import requests
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s from %s", resp.status_code, url)
            return None
        return resp.json()
    except Exception as exc:
        log.warning("HTTP fetch failed (%s): %s", url, exc)
        return None


# ── DK parsing ────────────────────────────────────────────────────────────────

def _build_dk_roster_slots(contest_type_id: int) -> List[str]:
    if contest_type_id == 96:  # showdown
        return ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
    return ["PG", "SG", "SF", "PF", "C", "FLEX", "UTIL", "UTIL"]


def parse_dk_contest(group_json: dict, draftables_json: dict) -> SlateContest:
    """
    Build SlateContest from DK draftgroup + draftables responses.

    group_json may be a raw lobby DraftGroup dict or the normalized 'group' sub-dict.
    draftables_json must contain key 'draftables' (list of player objects).
    """
    g = group_json.get("group", group_json)
    contest_type_id = int(g.get("contestTypeId", 21))
    players: List[dict] = []
    seen: dict = {}

    for raw in draftables_json.get("draftables", []):
        salary = int(raw.get("salary", 0) or 0)
        if salary <= 0:
            log.warning("Skipping player '%s' — salary=%s", raw.get("displayName", "?"), salary)
            continue
        player_id  = str(raw.get("playerDkId", raw.get("draftableId", "")))
        status_raw = str(raw.get("status", "None") or "None")
        entry = {
            "name":      str(raw.get("displayName", "")),
            "team":      str(raw.get("teamAbbreviation", "")),
            "position":  _DK_SLOT_MAP.get(int(raw.get("rosterSlotId", 5)), raw.get("position", "FLEX")),
            "salary":    salary,
            "status":    "" if status_raw.upper() == "NONE" else status_raw,
            "player_id": player_id,
        }
        if player_id in seen:
            players[seen[player_id]] = entry  # last entry wins on trade
        else:
            seen[player_id] = len(players)
            players.append(entry)

    contest_id = str(g.get("draftGroupId", ""))
    if len(players) < _MIN_PLAYERS:
        log.warning("DK contest %s has only %d players — pool too small", contest_id, len(players))

    return SlateContest(
        contest_id=contest_id,
        book="dk",
        sport=str(g.get("sport", "NBA")),
        slate_type=_DK_CONTEST_TYPE_MAP.get(contest_type_id, "classic"),
        salary_cap=int(g.get("salaryCap", 50000)),
        roster_slots=_build_dk_roster_slots(contest_type_id),
        lock_time=g.get("startDate", "") or _now_utc().isoformat(),
        game_ids=[str(gm.get("gameId") or gm.get("game_id", "")) for gm in g.get("games", []) if gm.get("gameId") or gm.get("game_id")],
        players=players,
    )


# ── FD parsing ────────────────────────────────────────────────────────────────

def parse_fd_contest(fd_json: dict) -> SlateContest:
    """
    Build SlateContest from FanDuel fixture-list payload.

    Expects: {"fixture_lists": [{"id":..., "salary_cap":..., "roster_slots_count":{},
              "start_date":..., "slate_type_name":..., "fixtures":[...], "players":[...]}]}
    """
    fl = (fd_json.get("fixture_lists") or [fd_json])[0]
    slate_name = str(fl.get("slate_type_name", "classic") or "classic").lower()
    slot_counts = fl.get("roster_slots_count", {})
    roster_slots: List[str] = []
    for pos, cnt in slot_counts.items():
        roster_slots.extend([pos] * int(cnt or 0))

    players: List[dict] = []
    seen: dict = {}
    for raw in fl.get("players", []):
        salary = int(raw.get("salary", 0) or 0)
        if salary <= 0:
            log.warning("Skipping FD player '%s' — salary=%s", raw.get("full_name", "?"), salary)
            continue
        player_id = str(raw.get("id", ""))
        entry = {
            "name":      str(raw.get("full_name", raw.get("name", ""))),
            "team":      str(raw.get("team", raw.get("team_abbr", ""))),
            "position":  str(raw.get("position", "UTIL")),
            "salary":    salary,
            "status":    str(raw.get("injury_status", raw.get("status", "")) or ""),
            "player_id": player_id,
        }
        if player_id in seen:
            players[seen[player_id]] = entry
        else:
            seen[player_id] = len(players)
            players.append(entry)

    contest_id = str(fl.get("id", "fd_unknown"))
    if len(players) < _MIN_PLAYERS:
        log.warning("FD contest %s has only %d players — pool too small", contest_id, len(players))

    return SlateContest(
        contest_id=contest_id,
        book="fd",
        sport="NBA",
        slate_type=slate_name if slate_name in ("classic", "showdown", "main", "single") else "classic",
        salary_cap=int(fl.get("salary_cap", 60000) or 60000),
        roster_slots=roster_slots or ["PG", "SG", "SF", "PF", "C", "UTIL", "UTIL", "UTIL"],
        lock_time=fl.get("start_date", "") or _now_utc().isoformat(),
        game_ids=[str(fx["id"]) for fx in fl.get("fixtures", []) if fx.get("id")],
        players=players,
    )


# ── save ──────────────────────────────────────────────────────────────────────

def save_slate(slate: SlateContest, out_dir: str = "data/dfs_slates") -> str:
    """Write SlateContest to <out_dir>/<book>_<date>_<slate_type>.json; return path."""
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    lock_dt = _parse_iso(slate.lock_time)
    date_str = lock_dt.strftime("%Y-%m-%d") if lock_dt else _now_utc().strftime("%Y-%m-%d")
    out_path = base / f"{slate.book}_{date_str}_{slate.slate_type}.json"
    out_path.write_text(json.dumps(asdict(slate), indent=2), encoding="utf-8")
    log.info("Saved slate → %s", out_path)
    return str(out_path)


# ── live fetch helpers ────────────────────────────────────────────────────────

def _fetch_dk_groups(date: str) -> List[dict]:
    data = _http_get(_DK_CONTESTS_URL, _DK_HEADERS)
    if not data:
        return []
    groups = [
        dg for dg in data.get("DraftGroups", [])
        if int(dg.get("SportId", 0)) == _DK_SPORT_ID
        and date in str(dg.get("StartDateEst", dg.get("StartDate", "")))
    ]
    log.info("DK: found %d draft groups for %s", len(groups), date)
    return groups


def _try_dk_http(date: str, cache_p: Path) -> Optional[dict]:
    groups = _fetch_dk_groups(date)
    if not groups:
        return None
    items = []
    for dg in groups:
        gid = int(dg.get("DraftGroupId", dg.get("draftGroupId", 0)))
        if not gid:
            continue
        url = _DK_DRAFTABLES_URL.format(group_id=gid)
        draftables = _http_get(url, _DK_HEADERS)
        if draftables:
            items.append({"group": dg, "draftables": draftables})
        time.sleep(0.5)
    if not items:
        return None
    payload = {"groups": items}
    _save_json(cache_p, payload)
    return payload


def _try_fd_http(date: str, cache_p: Path) -> Optional[dict]:
    data = _http_get(_FD_FIXTURE_URL, _FD_HEADERS)
    if data is None:
        return None
    _save_json(cache_p, data)
    return data


# ── payload parsers ───────────────────────────────────────────────────────────

def _parse_dk_payload(payload: dict) -> List[SlateContest]:
    slates: List[SlateContest] = []
    if "groups" in payload:
        for item in payload["groups"]:
            dg = item.get("group", {})
            draftables = item.get("draftables", {})
            if not draftables:
                continue
            group_norm = {
                "draftGroupId":  dg.get("DraftGroupId",      dg.get("draftGroupId", "")),
                "contestTypeId": dg.get("ContestTypeId",     dg.get("contestTypeId", 21)),
                "salaryCap":     dg.get("DraftGroupSalaryCap", dg.get("salaryCap", 50000)),
                "sport": "NBA",
                "startDate":     dg.get("StartDateEst",      dg.get("startDate", "")),
                "games": [{"gameId": str(gm.get("GameId", gm.get("gameId", "")))}
                          for gm in dg.get("Games", dg.get("games", []))],
            }
            if "draftables" not in draftables:
                draftables = {"draftables": draftables.get("draftables", [])}
            slate = parse_dk_contest(group_norm, draftables)
            if len(slate.players) >= _MIN_PLAYERS:
                slates.append(slate)
            else:
                log.warning("DK contest %s discarded — %d players", slate.contest_id, len(slate.players))
        return slates

    group_raw  = payload.get("group", payload)
    draftables = {"draftables": payload.get("draftables", [])}
    slate = parse_dk_contest(group_raw, draftables)
    if len(slate.players) >= _MIN_PLAYERS:
        slates.append(slate)
    else:
        log.warning("DK contest %s discarded — %d players", slate.contest_id, len(slate.players))
    return slates


def _parse_fd_payload(payload: dict) -> List[SlateContest]:
    slate = parse_fd_contest(payload)
    if len(slate.players) < _MIN_PLAYERS:
        log.warning("FD contest %s discarded — %d players", slate.contest_id, len(slate.players))
        return []
    return [slate]


# ── main ingest ───────────────────────────────────────────────────────────────

def get_dfs_slate(
    book: str,
    date: str,
    paper: Optional[bool] = None,
    out_dir: str = "data/dfs_slates",
) -> Optional[List[SlateContest]]:
    """
    Fetch/parse DFS slate(s) for book on date. Three-tier fallback: HTTP → cache → seed.

    Args:
        book:   "dk" | "fd"
        date:   "YYYY-MM-DD"
        paper:  skip HTTP; use seed/cache only, never write to live paths.
    Returns:
        List[SlateContest] (may be empty if all locked), or None if all tiers fail.
    """
    # Resolve paper flag: explicit caller override → else module-level PAPER_MODE.
    if paper is None:
        paper = PAPER_MODE
    book = book.lower()
    cache_p = _cache_path(book, date, out_dir)
    seed_p  = _seed_path(book, date, out_dir)
    raw: Optional[dict] = None

    if not paper:
        raw = _try_dk_http(date, cache_p) if book == "dk" else _try_fd_http(date, cache_p) if book == "fd" else None
        if raw is None and book not in ("dk", "fd"):
            log.warning("Unknown book '%s'", book)
            return None

    if raw is None and _is_cache_fresh(cache_p):
        log.info("Using fresh cache: %s", cache_p)
        raw = _load_json(cache_p)

    if raw is None and seed_p.exists():
        log.warning("Using seed file (HTTP + cache both failed): %s", seed_p)
        raw = _load_json(seed_p)

    if raw is None:
        log.warning(
            "No data for book=%s date=%s (tried HTTP, cache, seed). Create seed at %s",
            book, date, seed_p,
        )
        return None

    now    = _now_utc()
    slates = _parse_dk_payload(raw) if book == "dk" else _parse_fd_payload(raw)

    unlocked = []
    for s in slates:
        lock_dt = _parse_iso(s.lock_time)
        if lock_dt is not None and lock_dt <= now:
            log.info("Dropping locked contest %s (lock=%s)", s.contest_id, s.lock_time)
            continue
        unlocked.append(s)

    log.info("book=%s date=%s → %d unlocked slates", book, date, len(unlocked))
    return unlocked


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="DFS slate ingester")
    parser.add_argument("--book",  default="dk", choices=["dk", "fd", "both"])
    parser.add_argument("--date",  default=_now_utc().strftime("%Y-%m-%d"))
    parser.add_argument("--out",   default="data/dfs_slates")
    parser.add_argument("--paper", action="store_true",
                        help="Skip HTTP — load seed/cache only")
    args = parser.parse_args(argv)

    books = ["dk", "fd"] if args.book == "both" else [args.book]
    total = 0
    for book in books:
        slates = get_dfs_slate(book=book, date=args.date, paper=args.paper, out_dir=args.out)
        if not slates:
            log.info("book=%s: no slates returned", book)
            continue
        for slate in slates:
            if args.paper:
                log.info("[paper] book=%s contest=%s type=%s players=%d",
                         slate.book, slate.contest_id, slate.slate_type, len(slate.players))
            else:
                log.info("Wrote %s", save_slate(slate, out_dir=args.out))
            total += 1
    log.info("Done — %d slate(s) processed", total)


if __name__ == "__main__":
    main()
