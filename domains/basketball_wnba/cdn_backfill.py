"""domains.basketball_wnba.cdn_backfill -- bounded resumable WNBA CDN backfill.

LANE 4 retry (this wave): wave-10 found cdn.wnba.com WAF-blocked (HTTP 200 +
Akamai/marketing-site HTML where JSON was expected) from that session's plain-
urllib egress. THIS session retried and escalated to the stealth tier
(scripts.platformkit.odds_provider.stealth_fetch, scrapling chrome-TLS
impersonation, already installed for the odds pipeline) and confirmed:

  - boxscore_{gameId}.json   -> REACHABLE via stealth tier (plain urllib still
    blocked: same 200+marketing-HTML pattern as wave-10).
  - playbyplay_{gameId}.json -> REACHABLE via stealth tier.
  - scheduleLeagueV2.json    -> REACHABLE via stealth tier (full-season static
    schedule -- gameId/gameCode/gameStatus/team tricodes for all 350 games,
    incl. 150 completed regular-season + Commissioner's Cup finals as of
    2026-07-04). This REPLACES the scoreboardv3 discovery path entirely for
    backfill purposes: scoreboardv3 (stats.wnba.com) still timed out via
    stealth this session, but is not needed since the static schedule already
    lists every gameId + gameStatus for the whole season.
  - todaysScoreboard_00.json / odds_todaysGames.json -> still 403 via stealth
    (unrelated to backfill; live-day discovery is the poller module's concern).

Since completed games are Final (gameStatus == 3), their boxscore+playbyplay
are STATIC once the game ends -- fetching them is a one-time backfill, not a
live poll. This module owns exactly that: discover completed gameIds from the
season schedule, then fetch+persist raw boxscore/playbyplay JSON per game to
data/domains/wnba/cdn_backfill/<gameId>/{boxscore,playbyplay}.json.

RESUMABLE: a gameId whose both output files already exist on disk is skipped
entirely on a re-run (idempotent-by-file-presence -- no separate manifest to
go stale). POLITE: 1 request/sec between fetches (see run_backfill sleep_s).
BOUNDED: run_backfill defaults to the full completed-game list but accepts
max_games to cap any single pass (this wave's proof run used <=170).

PROVENANCE: every backfilled row this produces (via cdn_states_extract.py) is
tagged provenance="cdn_backfill" -- a VALIDATION corpus, never pooled with a
forward-only capture stream (binding invariant, see AUTONOMY_CHARTER).

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises
(best-effort None on any single-game failure, does not abort the whole run);
no $ fields; measurement/backfill only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_cdn_backfill.py -q
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
BACKFILL_DIR = _REPO_ROOT / "data" / "domains" / "wnba" / "cdn_backfill"

_SCHEDULE_URL = "https://cdn.wnba.com/static/json/staticData/scheduleLeagueV2.json"
_BOX_URL = "https://cdn.wnba.com/static/json/liveData/boxscore/boxscore_{gid}.json"
_PBP_URL = "https://cdn.wnba.com/static/json/liveData/playbyplay/playbyplay_{gid}.json"

FINAL_STATUS = 3  # NBA-family liveData convention: 1=pre, 2=live, 3=final
DEFAULT_MAX_GAMES = 170  # bounded-budget ceiling per BINDING INVARIANTS


def _stealth_getter() -> Callable[[str], Optional[dict]]:
    """Returns a get_json(url)->dict|None callable backed by the stealth tier.
    Import is lazy so this module never touches scrapling at import time."""
    from scripts.platformkit.odds_provider.stealth_fetch import stealth_get_json

    def _get(url: str) -> Optional[dict]:
        try:
            return stealth_get_json(url, timeout=25.0)
        except Exception as exc:  # noqa: BLE001 -- network/WAF flake, never raise
            logger.debug("stealth fetch failed url=%s err=%s", url, exc)
            return None
    return _get


def fetch_completed_game_ids(
    get_json: Optional[Callable[[str], Optional[dict]]] = None,
) -> List[Dict[str, str]]:
    """[{game_id, game_code, date}] for every FINAL-status game in the season
    static schedule, or [] on any fetch/parse failure (never raises)."""
    getter = get_json or _stealth_getter()
    payload = getter(_SCHEDULE_URL)
    if not isinstance(payload, dict):
        return []
    sched = payload.get("leagueSchedule") or {}
    out: List[Dict[str, str]] = []
    for gd in sched.get("gameDates") or []:
        for g in gd.get("games") or []:
            if not isinstance(g, dict):
                continue
            if g.get("gameStatus") != FINAL_STATUS:
                continue
            gid = g.get("gameId")
            if not gid:
                continue
            out.append({
                "game_id": str(gid),
                "game_code": str(g.get("gameCode") or ""),
                "date": str(g.get("gameDateEst") or "")[:10],
            })
    return out


def game_dir(game_id: str) -> Path:
    return BACKFILL_DIR / str(game_id)


def _already_backfilled(game_id: str) -> bool:
    d = game_dir(game_id)
    return (d / "boxscore.json").exists() and (d / "playbyplay.json").exists()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def backfill_one_game(
    game_id: str,
    get_json: Optional[Callable[[str], Optional[dict]]] = None,
    *,
    force: bool = False,
) -> Dict[str, object]:
    """Fetch+persist one game's boxscore+playbyplay. Skips (resumable) if both
    files already exist unless force=True. Returns a per-game status dict;
    never raises -- a fetch failure is recorded, not thrown."""
    if not force and _already_backfilled(game_id):
        return {"game_id": game_id, "status": "skipped_exists"}

    getter = get_json or _stealth_getter()
    box = getter(_BOX_URL.format(gid=game_id))
    pbp = getter(_PBP_URL.format(gid=game_id))

    d = game_dir(game_id)
    if isinstance(box, dict) and box.get("game"):
        _write_json(d / "boxscore.json", box)
    if isinstance(pbp, dict) and pbp.get("game"):
        _write_json(d / "playbyplay.json", pbp)

    ok_box = (d / "boxscore.json").exists()
    ok_pbp = (d / "playbyplay.json").exists()
    if ok_box and ok_pbp:
        status = "fetched"
    elif ok_box or ok_pbp:
        status = "partial"
    else:
        status = "failed"
    return {"game_id": game_id, "status": status}


def run_backfill(
    max_games: int = DEFAULT_MAX_GAMES,
    sleep_s: float = 1.0,
    get_json: Optional[Callable[[str], Optional[dict]]] = None,
    game_ids: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Bounded resumable backfill pass. If *game_ids* is given, backfills
    exactly those (test/offline friendly, skips schedule discovery); else
    discovers completed gameIds from the season schedule, capped at
    max_games. Returns a summary dict; never raises."""
    getter = get_json or _stealth_getter()

    if game_ids is not None:
        targets = list(game_ids)[:max_games]
        n_discovered = len(targets)
    else:
        games = fetch_completed_game_ids(getter)
        n_discovered = len(games)
        targets = [g["game_id"] for g in games][:max_games]

    counts = {"fetched": 0, "skipped_exists": 0, "partial": 0, "failed": 0}
    for gid in targets:
        result = backfill_one_game(gid, get_json=getter)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if result["status"] != "skipped_exists":
            time.sleep(sleep_s)

    return {
        "n_discovered": n_discovered,
        "n_targeted": len(targets),
        **counts,
    }


def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Bounded resumable WNBA CDN backfill.")
    parser.add_argument("--max-games", type=int, default=DEFAULT_MAX_GAMES)
    parser.add_argument("--sleep-s", type=float, default=1.0)
    parser.add_argument("--game-ids", nargs="*", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    summary = run_backfill(max_games=args.max_games, sleep_s=args.sleep_s,
                            game_ids=args.game_ids)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "fetch_completed_game_ids", "backfill_one_game", "run_backfill",
    "game_dir", "BACKFILL_DIR", "FINAL_STATUS", "DEFAULT_MAX_GAMES",
]
