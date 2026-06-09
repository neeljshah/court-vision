"""nba_api_v3_patch.py — robust v3 endpoint wrappers for Live Engine v2.

Three endpoints, three guarantees:

* fetch_pbp_v3(game_id)     — playbyplayv3 → list of plays
* fetch_matchups_v3(game_id) — boxscorematchupsv3 → list of defender pairs
* fetch_box_v3(game_id)      — boxscoretraditionalv3 + boxscoreadvancedv3
                                merged per (game_id, player_id)

Each wrapper:
  1. Imports `src.data.nba_api_headers_patch` BEFORE any endpoint call.
  2. Catches 403 / 429 / timeout / connection errors and retries with
     exponential backoff (1s → 2s → 4s, capped at 3 attempts by default).
  3. Honors the project-wide 0.6s NBA API rate limit between successive
     calls — see `RATE_LIMIT_S` module constant.
  4. Returns a list of plain dicts. Errors after exhausted retries
     surface as an empty list with a warning log (callers loop again
     on the next poll).

PBP specifically prefers cdn.nba.com over stats.nba.com because:
  * the CDN feed is unauthenticated, far less likely to rate-limit cloud
    egress IPs (where stats.nba.com regularly times out)
  * it returns the same per-action schema downstream consumers expect
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

# ── header patch MUST happen before any nba_api endpoint import ──────
import src.data.nba_api_headers_patch  # noqa: F401

log = logging.getLogger(__name__)

# Silence urllib3's auto-retry chatter for stats.nba.com — those WARNING
# lines flood the logs whenever the host is unreachable (Railway egress IP
# is rate-limited by stats.nba.com); we already handle retries ourselves.
# Root + both vendored paths covers every nba_api-shipped urllib3 build.
for _noisy in ("urllib3", "urllib3.connectionpool", "urllib3.util.retry",
               "requests.packages.urllib3.connectionpool"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

# Project-wide rate limit between successive API calls — matches the
# convention used elsewhere in the codebase (e.g. live_game_poll).
RATE_LIMIT_S = 0.6

# Backoff sequence (seconds) for 403/429/timeout/network errors.
_BACKOFF_SCHEDULE = (1.0, 2.0, 4.0)

# Tracks the last time any wrapper called the API so we self-throttle.
_LAST_CALL_TS: float = 0.0


def _respect_rate_limit() -> None:
    """Sleep just long enough so successive calls are >= RATE_LIMIT_S apart."""
    global _LAST_CALL_TS
    now = time.time()
    delta = now - _LAST_CALL_TS
    if delta < RATE_LIMIT_S:
        time.sleep(RATE_LIMIT_S - delta)
    _LAST_CALL_TS = time.time()


def _is_retryable(exc: Exception) -> bool:
    """Decide whether ``exc`` warrants a backoff retry vs immediate raise."""
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return True
    if "429" in msg or "rate limit" in msg or "too many" in msg:
        return True
    if "403" in msg or "forbidden" in msg:
        return True
    if "503" in msg or "502" in msg or "504" in msg:
        return True
    if "connection" in msg and ("reset" in msg or "aborted" in msg or
                                "refused" in msg):
        return True
    return False


def _with_retries(fn, *, label: str, retries: int = 2,
                  timeout: float = 10.0, quiet: bool = False) -> Any:
    """Run ``fn()`` with exponential-backoff retries on transient errors.

    Returns whatever ``fn()`` returns on success. Returns ``None``
    after all attempts fail (the caller decides whether to surface
    an empty list or escalate). When ``quiet=True``, failures log at
    DEBUG instead of WARNING — used for endpoints we know are
    unreachable from cloud egress (e.g. matchups from Railway).
    """
    last_exc: Optional[Exception] = None
    attempts = max(1, 1 + retries)
    final_level = logging.DEBUG if quiet else logging.WARNING
    for i in range(attempts):
        _respect_rate_limit()
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if not _is_retryable(exc) or i == attempts - 1:
                log.log(final_level, "%s failed (attempt %d/%d): %s",
                        label, i + 1, attempts, exc)
                break
            backoff = _BACKOFF_SCHEDULE[min(i, len(_BACKOFF_SCHEDULE) - 1)]
            log.log(logging.DEBUG if quiet else logging.INFO,
                    "%s transient failure (%s); backing off %.1fs",
                    label, exc, backoff)
            time.sleep(backoff)
    if last_exc is not None:
        log.log(final_level, "%s exhausted retries: %s", label, last_exc)
    return None


# ── 1. play-by-play v3 ──────────────────────────────────────────────────
_CDN_PBP_URL = (
    "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{gid}.json"
)


# CDN actionType → stats.nba.com playbyplayv3 actionType. The pbp_poller's
# _classify expects the v3 spelling, so we normalize here once.
_CDN_TO_V3_ACTION = {
    "foul": "Foul",
    "substitution": "Substitution",
    "turnover": "Turnover",
    "timeout": "Timeout",
}


def _normalize_cdn_action(a: Dict[str, Any]) -> Dict[str, Any]:
    """Make a CDN action look like a stats.nba.com playbyplayv3 row.

    Only the fields the rest of the live pipeline reads — leaves everything
    else (x/y/qualifiers/shotResult) intact for any downstream consumer
    that wants the richer CDN schema.
    """
    atype = (a.get("actionType") or "").strip()
    shot_result = (a.get("shotResult") or "").strip()
    sub_type = (a.get("subType") or "").strip()

    if atype in {"2pt", "3pt", "freethrow"}:
        # The poller's _classify keys on actionType=="Made Shot" OR
        # isFieldGoalMade is True; we set both so either path matches.
        if shot_result.lower() == "made":
            a["actionType"] = "Made Shot"
            a["isFieldGoalMade"] = True
        else:
            a["actionType"] = "Missed Shot"
            a["isFieldGoalMade"] = False
    elif atype == "period" and sub_type.lower() == "end":
        a["actionType"] = "End Period"
    elif atype in _CDN_TO_V3_ACTION:
        a["actionType"] = _CDN_TO_V3_ACTION[atype]

    # CDN sometimes only sends playerNameI (initial form). Existing
    # consumers expect playerName, so default it.
    if not a.get("playerName"):
        a["playerName"] = a.get("playerNameI") or a.get("playerNameI ") or ""
    return a


def _fetch_pbp_cdn(game_id: str, *, timeout: float) -> List[Dict[str, Any]]:
    """Hit the public CDN PBP feed and return v3-shaped actions.

    Normalizes the CDN per-action schema to what pbp_poller._classify and
    _event_from_play expect (Made Shot, Foul, Substitution, etc.).
    """
    url = _CDN_PBP_URL.format(gid=game_id)
    req = urllib.request.Request(url, headers={
        # Akamai gate on cdn.nba.com rejects requests without a matching
        # Referer/Origin pair — these mimic what nba.com itself sends.
        "User-Agent": "Mozilla/5.0 (CourtVision Live)",
        "Accept": "application/json",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    actions = ((payload or {}).get("game") or {}).get("actions") or []
    return [_normalize_cdn_action(a) for a in actions]


def fetch_pbp_v3(game_id: str, *, timeout: float = 10.0,
                 retries: int = 2) -> List[Dict[str, Any]]:
    """Return the list of all plays for ``game_id``.

    Tries the public cdn.nba.com live PBP feed first (unauthenticated,
    reliable from cloud egress) and falls back to the stats.nba.com
    playbyplayv3 endpoint only if the CDN call fails. Each play is a
    dict with keys (varies by play type):
        actionNumber, period, clock, teamId, teamTricode,
        personId, playerName, actionType, subType, description,
        scoreHome, scoreAway, x, y
    """
    def _call_cdn():
        return _fetch_pbp_cdn(game_id, timeout=timeout)

    cdn_result = _with_retries(_call_cdn,
                               label=f"fetch_pbp_cdn({game_id})",
                               retries=retries, timeout=timeout)
    if cdn_result:
        return cdn_result

    log.info("fetch_pbp_v3(%s) CDN empty/failed, falling back to stats.nba.com",
             game_id)

    def _call_stats():
        from nba_api.stats.endpoints import playbyplayv3 as _pbp
        ep = _pbp.PlayByPlayV3(game_id=game_id, timeout=timeout)
        data = ep.get_normalized_dict()
        return data.get("PlayByPlay") or []

    result = _with_retries(_call_stats, label=f"fetch_pbp_v3({game_id})",
                           retries=retries, timeout=timeout)
    return result or []


# ── 2. boxscore matchups v3 ─────────────────────────────────────────────
def fetch_matchups_v3(game_id: str, *, period: Optional[int] = None,
                      timeout: float = 10.0,
                      retries: int = 2) -> List[Dict[str, Any]]:
    """Return per-offense/defender matchup rows from BoxScoreMatchupsV3.

    Each row has (keys may vary by season):
        personId (offensive), personIdOff, defensivePersonId,
        teamId, teamTricode, matchupMinutes, partialPossessions,
        playerPoints, assists, turnovers, blocks, ...

    When ``period`` is given (1..4 + OT), the response is filtered
    to that period's matchups. None (default) → full game.
    """
    def _call():
        from nba_api.stats.endpoints import boxscorematchupsv3 as _bm
        kwargs: Dict[str, Any] = {"game_id": game_id, "timeout": timeout}
        ep = _bm.BoxScoreMatchupsV3(**kwargs)
        data = ep.get_normalized_dict()
        # endpoint returns nested team→player→matchups; flatten to a
        # uniform list of dicts for downstream consumers.
        rows: List[Dict[str, Any]] = []
        for key, payload in data.items():
            if isinstance(payload, list):
                rows.extend(payload)
        if period is not None:
            rows = [r for r in rows if r.get("period") == period]
        return rows

    # quiet=True: stats.nba.com matchups is unreachable from cloud egress
    # (Railway/Fly) and there's no CDN equivalent — every call fails and
    # warning-level chatter just floods logs. Failure is the expected state.
    result = _with_retries(_call, label=f"fetch_matchups_v3({game_id})",
                           retries=retries, timeout=timeout, quiet=True)
    return result or []


# ── 3. boxscore traditional + advanced v3 ───────────────────────────────
def fetch_box_v3(game_id: str, *, timeout: float = 10.0,
                 retries: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """Return ``{"traditional": [...], "advanced": [...]}`` for ``game_id``.

    Each list is one row per (team, player). Schemas differ between
    the two endpoints — callers usually want both for per-player
    fatigue + efficiency overlays.

    On failure of either endpoint, the corresponding key has an
    empty list — callers should treat missing keys as transient.
    """
    out: Dict[str, List[Dict[str, Any]]] = {"traditional": [], "advanced": []}

    def _trad():
        from nba_api.stats.endpoints import boxscoretraditionalv3 as _bt
        ep = _bt.BoxScoreTraditionalV3(game_id=game_id, timeout=timeout)
        data = ep.get_normalized_dict()
        rows: List[Dict[str, Any]] = []
        # Each endpoint returns 2 datasets (one per team) keyed by
        # "PlayerStats" et al; merge any list-typed values.
        for key, payload in data.items():
            if isinstance(payload, list) and "player" in key.lower():
                rows.extend(payload)
        return rows

    def _adv():
        from nba_api.stats.endpoints import boxscoreadvancedv3 as _ba
        ep = _ba.BoxScoreAdvancedV3(game_id=game_id, timeout=timeout)
        data = ep.get_normalized_dict()
        rows: List[Dict[str, Any]] = []
        for key, payload in data.items():
            if isinstance(payload, list) and "player" in key.lower():
                rows.extend(payload)
        return rows

    trad = _with_retries(_trad, label=f"fetch_box_v3.trad({game_id})",
                         retries=retries, timeout=timeout)
    adv = _with_retries(_adv, label=f"fetch_box_v3.adv({game_id})",
                        retries=retries, timeout=timeout)
    out["traditional"] = trad or []
    out["advanced"] = adv or []
    return out


# ── connectivity self-test ──────────────────────────────────────────────
def verify_v3_endpoints(game_id: str = "0042400315") -> Tuple[bool, Dict[str, int]]:
    """Quick sanity check that all three v3 endpoints are reachable.

    Returns ``(all_ok, counts_per_endpoint)``. Useful from operator
    setup scripts and the daemon-watchdog health probe.
    """
    plays = fetch_pbp_v3(game_id, retries=1)
    matchups = fetch_matchups_v3(game_id, retries=1)
    box = fetch_box_v3(game_id, retries=1)
    counts = {
        "pbp_v3": len(plays),
        "matchups_v3": len(matchups),
        "box_v3_traditional": len(box.get("traditional", [])),
        "box_v3_advanced": len(box.get("advanced", [])),
    }
    all_ok = all(c > 0 for c in counts.values())
    return all_ok, counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    import sys
    gid = sys.argv[1] if len(sys.argv) > 1 else "0042400315"
    ok, counts = verify_v3_endpoints(gid)
    print(f"all_ok={ok}  counts={counts}")
    sys.exit(0 if ok else 1)
