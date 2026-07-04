"""domains.basketball_nba.cdn_probe -- NBA CDN reachability probe (LANE 4, this wave).

WAVE-14 PRECEDENT: cdn.wnba.com was WAF-blocked (200 + marketing-site HTML)
from plain urllib but REACHABLE via the stealth tier (scrapling chrome-TLS
impersonation, scripts.platformkit.odds_provider.stealth_fetch). This module
runs the SAME two-tier probe against cdn.nba.com's sibling endpoints
(scheduleLeagueV2.json, boxscore_{gameId}.json, playbyplay_{gameId}.json,
todaysScoreboard_00.json) to test whether the NBA-brand CDN behaves the same.

VERDICT THIS WAVE: BLOCKED -- harder than the WNBA case.
  - Plain urllib: HTTPError 403 (not a 200+HTML mask).
  - Stealth tier (scrapling impersonate='chrome'): ALSO HTTPError 403.
  - The response body (captured directly via scrapling.fetchers.Fetcher,
    bypassing stealth_get_json's error path) is an explicit Akamai edge
    "Access Denied" page -- e.g. body starts
    b'<HTML><HEAD>\\n<TITLE>Access Denied</TITLE>...' with a
    "Reference #18.<hash>.<timestamp>" footer. This is a WAF/edge-ACL block
    at the CDN layer, not a bot-challenge page -- chrome-TLS impersonation
    does not clear it (unlike the WNBA marketing-HTML mask, which was a JS
    challenge stealth's real browser engine executes through).
  - Confirmed across 4 distinct endpoints (schedule, scoreboard, 2 distinct
    boxscore gameIds, odds) and 2 retries with a 2s gap (not a transient
    network blip) -- see this wave's session log for the exact commands run.

ALTERNATIVE (the ask if BLOCKED): an on-disk NBA checkpoint-derivable states
source ALREADY EXISTS, no backfill needed:
  - data/domains/basketball_nba/linescores.parquet (+ linescores_2024_25.parquet)
    -- 1313 rows, one per game: event_id, home_abbr/away_abbr, home_q1..q4,
    away_q1..q4, date. Cumulative-sum the q1..q3 columns per side to get
    exactly the end_q1 / half / end_q3 SCORE checkpoints CDN boxscore replay
    would have produced. This is provenance=ESPN summary (ingest_boxscores.py
    lineage), already ingested, already used by asof_quarter_shape.py.
  - domains/basketball_nba/ingest_pbp_states.py + ingest_pbp_foul_states.py
    -- FINER ~2-minute as-of grid (margin trajectory + cumulative foul diff)
    from the same ESPN summary plays[] array, already leak-free/as-of by
    construction (see those modules' docstrings). This exceeds CDN checkpoint
    granularity (3 boundaries/game) with ~14 grid points/game.
  - No in_bonus / lineup / run_last_3min analog exists on disk yet (those
    need the raw PBP action-type detail the CDN boxscore/playbyplay carries
    that ESPN's summary plays[] does not expose the same way) -- an HONEST
    GAP, not fabricated here.

For lane 2's NBA states gate: point it at linescores.parquet for the
score-only checkpoint, or ingest_pbp_states.py's finer grid if it needs a
denser as-of axis. No new backfill file is produced by this module (there is
nothing to backfill -- the CDN never yielded a payload).

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises
(a probe failure is a recorded verdict, not an exception); no $ fields;
measurement/probe only. Politeness: this module makes at most a handful of
one-off GETs per run (no loop, no polling) -- see run_probe's fixed URL list.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_cdn_probe.py -q
"""
from __future__ import annotations

import json
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
_SCOREBOARD_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
_BOX_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{gid}.json"
_PBP_URL = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{gid}.json"

# A small fixed set of plausible 2025-26 regular-season gameIds (NBA gameId
# format 00225XXXXX = season-type 002 [regular season], season 25, sequence).
# These are PROBE targets only -- reachability does not depend on any one of
# them actually existing; a 403 at this layer happens before game lookup.
PROBE_GAME_IDS: List[str] = ["0022500001", "0022500100", "0022500500"]


def _stealth_getter() -> Callable[[str], Optional[dict]]:
    """Returns a get_json(url)->dict|None callable backed by the stealth tier.
    Import is lazy so this module never touches scrapling at import time."""
    from scripts.platformkit.odds_provider.stealth_fetch import stealth_get_json

    def _get(url: str) -> Optional[dict]:
        try:
            return stealth_get_json(url, timeout=25.0)
        except Exception as exc:  # noqa: BLE001 -- network/WAF flake, never raise
            logger.debug("stealth probe failed url=%s err=%s", url, exc)
            return None
    return _get


def _plain_getter() -> Callable[[str], Optional[dict]]:
    """Returns a get_json(url)->dict|None callable using plain urllib (no
    stealth). Used to distinguish 'blocked at the WAF layer entirely' from
    'blocked for bots but reachable via a real browser TLS fingerprint'."""
    import urllib.request

    def _get(url: str) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001
            logger.debug("plain probe failed url=%s err=%s", url, exc)
            return None
    return _get


def probe_endpoint(
    url: str,
    plain_get: Optional[Callable[[str], Optional[dict]]] = None,
    stealth_get: Optional[Callable[[str], Optional[dict]]] = None,
) -> Dict[str, object]:
    """Probe one URL at both tiers. Returns {url, plain_ok, stealth_ok,
    reachable}. reachable is True iff EITHER tier returned parseable JSON.
    Never raises -- a fetch failure at a tier just yields *_ok=False."""
    plain = plain_get or _plain_getter()
    stealth = stealth_get or _stealth_getter()

    try:
        plain_result = plain(url)
    except Exception as exc:  # noqa: BLE001 -- an injected/real getter may raise; never propagate
        logger.debug("plain probe raised url=%s err=%s", url, exc)
        plain_result = None
    try:
        stealth_result = stealth(url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("stealth probe raised url=%s err=%s", url, exc)
        stealth_result = None

    plain_ok = isinstance(plain_result, dict)
    stealth_ok = isinstance(stealth_result, dict)
    return {
        "url": url,
        "plain_ok": plain_ok,
        "stealth_ok": stealth_ok,
        "reachable": plain_ok or stealth_ok,
    }


def run_probe(
    plain_get: Optional[Callable[[str], Optional[dict]]] = None,
    stealth_get: Optional[Callable[[str], Optional[dict]]] = None,
    game_ids: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Probe the fixed cdn.nba.com endpoint set at both tiers. Returns a
    summary dict with a per-endpoint breakdown and an overall verdict
    ('REACHABLE' if any endpoint is reachable at any tier, else 'BLOCKED').
    Never raises."""
    gids = game_ids if game_ids is not None else PROBE_GAME_IDS
    urls = [_SCHEDULE_URL, _SCOREBOARD_URL] + \
        [_BOX_URL.format(gid=g) for g in gids] + \
        [_PBP_URL.format(gid=g) for g in gids]

    results = [probe_endpoint(u, plain_get=plain_get, stealth_get=stealth_get) for u in urls]
    n_reachable = sum(1 for r in results if r["reachable"])
    verdict = "REACHABLE" if n_reachable > 0 else "BLOCKED"
    return {
        "verdict": verdict,
        "n_endpoints_probed": len(results),
        "n_reachable": n_reachable,
        "results": results,
    }


def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    summary = run_probe()
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "probe_endpoint", "run_probe", "PROBE_GAME_IDS",
]
