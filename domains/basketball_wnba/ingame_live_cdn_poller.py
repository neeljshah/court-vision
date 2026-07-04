"""domains.basketball_wnba.ingame_live_cdn_poller -- bounded WNBA CDN poller.

Companion to ingame_live_cdn.py (kept separate to hold that file <=300 LOC).
Discovers live gameIds via stats.wnba.com scoreboardv3 (Referer required --
the non-v3 stats.wnba.com path serves an AngularJS shell, avoided per scout
spec), cross-references them to ESPN event ids (a SEPARATE id space -- see
gameid_map_hint), then calls ingame_live_cdn.fetch_boxscore/fetch_playbyplay
+ extract_state + append_snapshot for each live game.

HONEST GAP: see ingame_live_cdn.py's module docstring -- cdn.wnba.com AND
stats.wnba.com were both unreachable (WAF page / timeout) from this session's
egress this wave, confirmed on the gameId-independent scoreboardv3 endpoint
too. This poller is therefore validated by injecting http_get/game_ids
directly (test_ingame_live_cdn_poller.py), not a live network round-trip.

WIRE SPEC (future lane -- NOT applied this wave; inplay_capture_loop.py is
untouched). Additive lines a future integration lane would add to
inplay_capture_loop._extract's wnba branch:

    if sport == "wnba":
        from domains.basketball_wnba.ingame_live_cdn import (
            fetch_boxscore, fetch_playbyplay, extract_state, append_snapshot)
        box = fetch_boxscore(game_id)
        if box is not None:
            state = extract_state(game_id, box, fetch_playbyplay(game_id))
            append_snapshot(game_id, state)
            out["wnba_in_bonus_home"] = state["in_bonus_home"]
            out["wnba_in_bonus_away"] = state["in_bonus_away"]
            out["wnba_foul_trouble_flags"] = state["foul_trouble_flags"]
            out["wnba_run_last_3min"] = state["run_last_3min"]

CANDIDATE COVARIATES -- gate discipline (binding, restated from
ingame_live_cdn.py): in_bonus_*, timeouts_*, foul_trouble_flags, and
run_last_3min are measurement-only. None may enter WNBAAdapter.predict_live
without its own pre-registered gate. See ingame_live_cdn.py docstring.

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; ~1s pacing
between fetches; never raises; no $ fields; measurement/sidecar only.

Run (bounded, one pass):
  cd /c/Users/neelj/nba-ai-system && python -m domains.basketball_wnba.ingame_live_cdn_poller --once

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingame_live_cdn_poller.py -q
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from .ingame_live_cdn import (
    append_snapshot, extract_state, fetch_boxscore, fetch_playbyplay,
)

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_REFERER = "https://www.wnba.com/"
_TIMEOUT = 15.0
_SCOREBOARDV3_URL = "https://stats.wnba.com/stats/scoreboardv3?GameDate={date}&LeagueID=10"


def _default_http_get(url: str) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": _REFERER})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        logger.debug("scoreboardv3 fetch failed url=%s err=%s", url, exc)
        return None


def fetch_scoreboardv3(date_str: str,
                        http_get: Optional[Callable[[str], Optional[bytes]]] = None
                        ) -> List[dict]:
    """List of scoreboardv3 game dicts for date_str ('YYYY-MM-DD'), or [] on
    failure (timeout, WAF page, malformed JSON -- never raises)."""
    getter = http_get or _default_http_get
    body = getter(_SCOREBOARDV3_URL.format(date=date_str))
    if not body:
        return []
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(payload, dict):
        return []
    games = (payload.get("scoreboard") or {}).get("games")
    return games if isinstance(games, list) else []


def _candidate_splits(tri: str) -> List[tuple]:
    """(away, home) candidate splits of the concatenated gameCode tricode blob.

    HARDENING (this wave): the shipped v1 assumed a fixed 3+3 split (true for
    every WNBA tricode observed in the live 2026 schedule -- CHI/LVA/GSV/NGR
    etc are all exactly 3 chars -- see cdn_backfill.fetch_completed_game_ids's
    season-schedule probe, 350 games checked), but nothing in the CDN contract
    GUARANTEES 3 chars forever (NBA-family
    tricodes have occasionally been non-3-letter historically, e.g. 2-letter
    or 4-letter alternate codes). Rather than hardcode one split point, try
    every plausible away-length in [2,4] and let the ESPN-abbreviation match
    below disambiguate; a length that yields zero or >1 hits is discarded, so
    a wrong split can only ever produce an absent mapping, never a garbage one."""
    out = []
    for away_len in (3, 2, 4):
        if 0 < away_len < len(tri):
            out.append((tri[:away_len], tri[away_len:]))
    return out


def gameid_map_hint(scoreboardv3_games: List[dict], espn_events: List[dict]) -> Dict[str, str]:
    """scoreboardv3 gameId -> ESPN event id, cross-referenced by same-day team
    tricode/displayName substring match (both id spaces are NBA-format vs
    ESPN-format and NEVER positionally identical -- confirmed 2026-07-03:
    gameId 1022600149 vs espn id 401857038 for the same CHI@LV game).
    Unmatched or ambiguous (>1 hit, incl. across split candidates) pairs are
    absent from the result -- never a guessed mapping. Tricode segment is
    NOT assumed to be a fixed 3+3 split (see _candidate_splits)."""
    out: Dict[str, str] = {}
    for sb in scoreboardv3_games:
        code = str(sb.get("gameCode") or "")
        tri = code.split("/")[-1] if "/" in code else ""  # e.g. "MINNYL" -> away+home tricodes
        if len(tri) < 4:
            continue
        all_hits = []
        for away_tri, home_tri in _candidate_splits(tri):
            for ev in espn_events:
                comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
                names = {c.get("homeAway"): str((c.get("team") or {}).get("abbreviation") or "")
                         for c in comps}
                home_abbr, away_abbr = names.get("home", "").upper(), names.get("away", "").upper()
                if home_abbr and away_abbr and \
                   (home_abbr in home_tri.upper() or home_tri.upper() in home_abbr) and \
                   (away_abbr in away_tri.upper() or away_tri.upper() in away_abbr):
                    if ev not in all_hits:
                        all_hits.append(ev)
        if len(all_hits) == 1:
            out[str(sb.get("gameId"))] = str(all_hits[0].get("id"))
    return out


def poll_once(date_str: Optional[str] = None, *, sleep_s: float = 1.0,
              game_ids: Optional[List[str]] = None,
              box_getter: Optional[Callable] = None,
              pbp_getter: Optional[Callable] = None,
              sb_getter: Optional[Callable] = None) -> Dict[str, object]:
    """One bounded poll pass over live WNBA games. If *game_ids* is given,
    polls exactly those (offline/test-friendly, skips scoreboardv3 discovery
    entirely); else discovers live games via scoreboardv3 for date_str
    (default: today UTC). Returns {date, n_games, n_live, n_snapshots}; never
    raises."""
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary: Dict[str, object] = {"date": date_str, "n_games": 0, "n_live": 0, "n_snapshots": 0}

    if game_ids is not None:
        targets = list(game_ids)
        summary["n_games"] = len(targets)
        summary["n_live"] = len(targets)
    else:
        games = fetch_scoreboardv3(date_str, http_get=sb_getter)
        summary["n_games"] = len(games)
        # gameStatus: 1=pre, 2=live, 3=final (NBA-family liveData convention).
        targets = [str(g.get("gameId")) for g in games if g.get("gameStatus") == 2]
        summary["n_live"] = len(targets)

    for gid in targets:
        box = fetch_boxscore(gid, http_get=box_getter)
        if box is None:
            time.sleep(sleep_s)
            continue
        pbp = fetch_playbyplay(gid, http_get=pbp_getter)
        state = extract_state(gid, box, pbp)
        append_snapshot(gid, state)
        summary["n_snapshots"] = int(summary["n_snapshots"]) + 1
        time.sleep(sleep_s)
    return summary


def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Bounded WNBA CDN live-state poll.")
    parser.add_argument("--once", action="store_true", help="Run exactly one bounded pass.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC).")
    parser.add_argument("--game-ids", nargs="*", default=None,
                         help="Explicit gameIds (skips scoreboardv3 discovery).")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    summary = poll_once(date_str=args.date, game_ids=args.game_ids)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["fetch_scoreboardv3", "gameid_map_hint", "poll_once"]
