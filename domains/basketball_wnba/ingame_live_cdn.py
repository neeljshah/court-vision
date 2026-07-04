"""domains.basketball_wnba.ingame_live_cdn -- WNBA CDN live-state extractor.

LANE 4 (this wave): keyless WNBA CDN in-game state, standalone (no shared
capture-loop file touched -- see WIRE SPEC in ingame_live_cdn_poller.py).

ENDPOINTS (keyless GET, Referer https://www.wnba.com/ required -- confirmed
scout spec; verified 2026-07-03 this session found the SAME cdn.wnba.com /
stats.wnba.com hosts unreachable from this box's egress, matching the
existing reference_live_data_routing memory pattern where NBA-brand hosts
(cdn.nba.com family) 403/timeout while ESPN's site.api works):

  boxscore:    https://cdn.wnba.com/static/json/liveData/boxscore/boxscore_{gameId}.json
  playbyplay:  https://cdn.wnba.com/static/json/liveData/playbyplay/playbyplay_{gameId}.json

Discovery of gameIds (scoreboardv3 fetch + ESPN cross-ref mapping) lives in
the companion module ingame_live_cdn_poller.py to keep this file <=300 LOC;
this module is the pure extractor + boxscore/playbyplay fetchers.

SCHEMA (ground-truthed against a real live payload fetched earlier this wave,
gameId 1022600149 CHI@LV 2026-07-03 2nd quarter -- see scratch wnba_cdn_box.txt
/ wnba_scoreboardv3.txt): boxscore.game.{period,gameClock,homeTeam,awayTeam};
each team dict carries {score, inBonus (0/1), timeoutsRemaining, players[]};
each player carries {personId, oncourt ('1'/'0'), statistics.foulsPersonal}.
playbyplay.game.actions[] carries {actionType, clock ("PT08M01.00S" ISO8601,
same format scripts/team_system/pbp_parse.py already parses for the NBA CDN
sibling feed), period, scoreHome, scoreAway} (cumulative on scoring actions)
-- the SAME liveData action shape domains.basketball_nba.pbp_mapper documents
for the NBA CDN sibling. WNBA gameIds are NBA-format (e.g. 1022600149),
CONFIRMED DIFFERENT from ESPN's own event ids (e.g. 401857038 for the SAME
game) -- never conflate the two id spaces (see poller's gameid_map_hint).

HONEST GAP (this wave): cdn.wnba.com / data.wnba.com / stats.wnba.com all
returned a WAF error page ("We are unable to process your request", ref
18.a8a03b17...) or timed out from THIS session's egress on every endpoint
tried, including the gameId-independent todaysScoreboard_00.json root -- a
host-level block/outage, not a bad gameId or wrong path (cdn.nba.com
hard-403'd the same way, matching the existing memory). All extraction logic
below is validated against FIXTURES shaped exactly like the confirmed-real
schema (test_ingame_live_cdn.py), not a fresh live round-trip this wave.

CANDIDATE COVARIATES -- gate discipline (binding): in_bonus_home/away,
timeouts_home/away, foul_trouble_flags, and run_last_3min are STATE/
MEASUREMENT fields only. NONE may enter domains.basketball_wnba.adapter
.WNBAAdapter.predict_live (the anchored blend) or any predict_live path
without its OWN pre-registered, leak-free, walk-forward, >=2-corpus gate
check first (same discipline ingame_blend_families.py used to adopt the
anchored family). Each is a SEPARATE future hypothesis -- e.g. "foul trouble
on an oncourt starter shifts realized net rating" is distinct from "bonus
state raises FT-rate scoring probability". This module ships NONE of that
gating; it only measures and records.

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises
(best-effort None/[] on failure); no $ fields; measurement/sidecar only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingame_live_cdn.py -q
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
SIDECAR_DIR = _REPO_ROOT / "data" / "domains" / "wnba" / "cdn_live"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_REFERER = "https://www.wnba.com/"
_TIMEOUT = 15.0

_BOX_URL = "https://cdn.wnba.com/static/json/liveData/boxscore/boxscore_{gid}.json"
_PBP_URL = "https://cdn.wnba.com/static/json/liveData/playbyplay/playbyplay_{gid}.json"

_CLK = re.compile(r"PT(?:(\d+)M)?(?:([\d.]+)S)?")
FOUL_TROUBLE_THRESHOLD = 4  # >=4 personal fouls = foul-trouble flag (1 shy of fouling out)
RUN_WINDOW_MIN = 3.0


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clock_to_sec(clock: Optional[str]) -> float:
    """ISO8601 'PT08M01.00S' -> seconds REMAINING in the period. '' / None -> 0.0.
    Same regex convention as scripts/team_system/pbp_parse.parse_clock (the NBA
    CDN sibling feed uses the identical clock encoding)."""
    if not clock:
        return 0.0
    m = _CLK.match(str(clock))
    if not m:
        return 0.0
    return float(m.group(1) or 0) * 60.0 + float(m.group(2) or 0)


def _default_http_get(url: str, referer: str = _REFERER) -> Optional[bytes]:
    """Raw bytes or None on any failure (never raises). JSON parsing is the
    caller's job so a WAF HTML error page is distinguishable from a real 404."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": referer})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 -- network flake must never crash a poller
        logger.debug("WNBA CDN fetch failed url=%s err=%s", url, exc)
        return None


def _get_json(url: str, http_get: Optional[Callable[[str], Optional[bytes]]] = None
              ) -> Optional[dict]:
    getter = http_get or _default_http_get
    body = getter(url)
    if not body:
        return None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        logger.debug("WNBA CDN non-JSON response url=%s (WAF/error page?)", url)
        return None
    return data if isinstance(data, dict) else None


def fetch_boxscore(game_id: str,
                    http_get: Optional[Callable[[str], Optional[bytes]]] = None
                    ) -> Optional[dict]:
    """boxscore.game dict, or None on any failure (WAF page, timeout, bad id)."""
    payload = _get_json(_BOX_URL.format(gid=game_id), http_get)
    if payload is None:
        return None
    game = payload.get("game")
    return game if isinstance(game, dict) else None


def fetch_playbyplay(game_id: str,
                      http_get: Optional[Callable[[str], Optional[bytes]]] = None
                      ) -> Optional[dict]:
    """playbyplay.game dict, or None on any failure."""
    payload = _get_json(_PBP_URL.format(gid=game_id), http_get)
    if payload is None:
        return None
    game = payload.get("game")
    return game if isinstance(game, dict) else None


def _oncourt_ids(team: dict) -> Optional[List[str]]:
    """Exactly-5 oncourt personIds for one team dict, or None if the feed does
    not report exactly 5 (never silently truncate/pad -- an honest None beats
    a fabricated 5th player)."""
    ids = [str(p.get("personId")) for p in (team.get("players") or [])
           if isinstance(p, dict) and str(p.get("oncourt")) == "1"]
    return ids if len(ids) == 5 else None


def _foul_trouble(team: dict, side: str) -> List[Dict[str, Any]]:
    """Oncourt players on *side* with >= FOUL_TROUBLE_THRESHOLD personal fouls."""
    out: List[Dict[str, Any]] = []
    for p in (team.get("players") or []):
        if not isinstance(p, dict) or str(p.get("oncourt")) != "1":
            continue
        fouls = ((p.get("statistics") or {}).get("foulsPersonal"))
        try:
            fouls = int(fouls)
        except (TypeError, ValueError):
            continue
        if fouls >= FOUL_TROUBLE_THRESHOLD:
            out.append({"side": side, "person_id": str(p.get("personId")), "fouls": fouls})
    return out


def _period_len_sec(period: int) -> float:
    return 600.0 if period <= 4 else 300.0  # WNBA quarter=10min, OT=5min


def _game_elapsed_sec(period: int, clock_s_remaining: float) -> float:
    before = sum(_period_len_sec(p) for p in range(1, max(1, period)))
    return before + (_period_len_sec(period) - clock_s_remaining)


def _run_last_3min(actions: List[dict], period: int, clock_s: float) -> Optional[float]:
    """Net HOME score over trailing actions within RUN_WINDOW_MIN minutes of
    game-clock time (period/clock-aware, NOT wallclock). None if actions is
    empty/absent or fewer than 2 in-window scoring actions exist (never
    fabricated 0.0 when the feed gave nothing to measure)."""
    if not actions:
        return None
    cur_elapsed = _game_elapsed_sec(period, clock_s)
    window_start = cur_elapsed - RUN_WINDOW_MIN * 60.0
    in_window = []
    for a in actions:
        if not isinstance(a, dict):
            continue
        a_period, a_clock = a.get("period"), a.get("clock")
        if a_period is None or a_clock is None:
            continue
        try:
            a_elapsed = _game_elapsed_sec(int(a_period), clock_to_sec(a_clock))
        except (TypeError, ValueError):
            continue
        if window_start <= a_elapsed <= cur_elapsed:
            in_window.append(a)
    if not in_window:
        return None
    scores = [(a.get("scoreHome"), a.get("scoreAway")) for a in in_window
              if a.get("scoreHome") is not None and a.get("scoreAway") is not None]
    if len(scores) < 2:
        return None
    (h0, a0), (h1, a1) = scores[0], scores[-1]
    try:
        return float(h1) - float(h0) - (float(a1) - float(a0))
    except (TypeError, ValueError):
        return None


def extract_state(game_id: str, box_game: dict, pbp_game: Optional[dict] = None
                   ) -> Dict[str, Any]:
    """boxscore (+ optional playbyplay) game dicts -> one flat state row. Pure
    function, no I/O. Never raises -- a missing/malformed sub-field degrades
    that ONE output field to None rather than aborting the whole row."""
    home = box_game.get("homeTeam") or {}
    away = box_game.get("awayTeam") or {}
    period = int(box_game.get("period") or 0)
    clock_s = clock_to_sec(box_game.get("gameClock"))

    foul_flags = _foul_trouble(home, "home") + _foul_trouble(away, "away")
    actions = (pbp_game or {}).get("actions") or []
    run = _run_last_3min(actions, period, clock_s) if actions else None

    return {
        "game_id": str(game_id),
        "ts": _utc_iso(),
        "period": period,
        "clock_s": clock_s,
        "score_home": home.get("score"),
        "score_away": away.get("score"),
        "in_bonus_home": bool(home.get("inBonus")) if home.get("inBonus") is not None else None,
        "in_bonus_away": bool(away.get("inBonus")) if away.get("inBonus") is not None else None,
        "timeouts_home": home.get("timeoutsRemaining"),
        "timeouts_away": away.get("timeoutsRemaining"),
        "oncourt_home": _oncourt_ids(home),
        "oncourt_away": _oncourt_ids(away),
        "foul_trouble_flags": foul_flags,
        "run_last_3min": run,
    }


def sidecar_path(game_id: str) -> Path:
    return SIDECAR_DIR / f"{game_id}.jsonl"


def append_snapshot(game_id: str, row: Dict[str, Any]) -> None:
    """Append one snapshot line. Best-effort; never raises."""
    try:
        SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
        with sidecar_path(game_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.debug("append_snapshot failed for %s: %s", game_id, exc)


__all__ = [
    "fetch_boxscore", "fetch_playbyplay", "extract_state", "clock_to_sec",
    "sidecar_path", "append_snapshot", "SIDECAR_DIR",
    "FOUL_TROUBLE_THRESHOLD", "RUN_WINDOW_MIN",
]
