"""L21_lineup_watcher.py — Lineup Announcement Watcher (BUILD L21, v2).

Polls Lineups.com and RotoWire for confirmed NBA starting lineups, diffs them
against expected top-5 fantasy-point starters, and dispatches alerts via L22.

Public API: LineupConfirmation, fetch_confirmed_lineups, diff_against_expected,
            alert_on_surprises

CLI:
    python L21_lineup_watcher.py fetch [--date YYYY-MM-DD]
    python L21_lineup_watcher.py once

Environment Variables
---------------------
None required for core operation.  The following vars affect behaviour when
used in the broader execute-loop stack:

  NBA_LINEUP_DIR    Override the default persistence directory
                    (``<project_root>/data/lineup_announcements``).  Useful
                    for integration tests or RunPod deployments with a separate
                    data volume.  Not read by L21 itself (set _LINEUP_DIR in
                    calling code), but documented here for operator reference.

Paper vs Live Mode (MODE GATING)
---------------------------------
L21 is a read-only watcher: it fetches public lineup information and writes a
local JSON snapshot.  It performs no financial transactions and therefore has
no paper/live distinction of its own.

In *paper* deployments the emitted "lineup.confirmed" events are consumed
downstream (e.g. by L44) which enforces the paper/live gate before any bet
submission.  L21 publishes unconditionally regardless of the value of
SUBMISSION_MODE or any equivalent environment variable.

Event Publication
-----------------
For each newly confirmed lineup (game_id × team first seen, or whose starter
roster has changed since the last fetch), L21 publishes a ``"lineup.confirmed"``
event to the L46 EventBus singleton:

    Event name : "lineup.confirmed"
    source     : "L21"
    payload    : {
        "game_id"          : str   — date-string used as game identifier,
        "team"             : str   — 3-letter NBA team abbreviation,
        "starters"         : list[str] — normalised player names,
        "confirmed_at"     : str   — ISO 8601 UTC timestamp,
        "previously_unknown": bool — True if first time this team appears,
    }

Publication is best-effort: any exception from L46 is caught and logged at
WARNING level so that a broken bus never blocks lineup data delivery.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ── paths ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR  = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))

_LINEUP_DIR = _PROJECT_DIR / "data" / "lineup_announcements"
log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
_LINEUPS_COM_URL = "https://www.lineups.com/nba/lineups"
_ROTOWIRE_URL    = "https://www.rotowire.com/basketball/nba-lineups.php"
_HTTP_TIMEOUT    = 8
_RETRY_BACKOFF   = 2
_EXPECTED_TOP_N  = 5
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

try:
    from scripts.execute_loop.L22_alerting import send_alert
except ImportError:
    try:
        from L22_alerting import send_alert  # type: ignore[no-redef]
    except ImportError:
        send_alert = None  # type: ignore[assignment]

# ── L46 EventBus (soft import — bus unavailable → publish silently skipped) ───
try:
    import scripts.execute_loop.L46_event_bus as _L46
except ImportError:
    try:
        import L46_event_bus as _L46  # type: ignore[no-redef]
    except ImportError:
        _L46 = None  # type: ignore[assignment]


@dataclass
class LineupConfirmation:
    team:               str
    confirmed_starters: list[str]
    surprise_starters:  list[str] = field(default_factory=list)
    benched_expected:   list[str] = field(default_factory=list)
    source:             str       = ""   # lineups.com|rotowire|manual_seed
    timestamp:          str       = ""
    note:               str       = ""


def _normalize_name(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _http_get(url: str) -> str:
    """GET with 8 s timeout + 1 retry (2 s backoff). Returns '' on failure."""
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            if attempt == 0:
                log.debug("[L21] HTTP attempt 1 failed %s: %s — retrying", url, exc)
                time.sleep(_RETRY_BACKOFF)
            else:
                log.warning("[L21] HTTP failed %s after 2 attempts: %s", url, exc)
    return ""


class _LineupParser(HTMLParser):
    """Parse lineup__abbr divs (team) and lineup__player li > a/span (names)."""

    def __init__(self, also_span: bool = False) -> None:
        super().__init__()
        self._teams:     Dict[str, list] = {}
        self._cur_team:  Optional[str]   = None
        self._in_abbr    = False
        self._in_li      = False
        self._in_leaf    = False
        self._leaf_tags  = {"a", "span"} if also_span else {"a"}

    def handle_starttag(self, tag: str, attrs: list) -> None:
        cls = dict(attrs).get("class", "")
        if tag == "div" and "lineup__abbr" in cls:
            self._in_abbr = True
        if tag == "li" and "lineup__player" in cls:
            self._in_li   = True
            self._in_leaf = False
        if self._in_li and tag in self._leaf_tags:
            self._in_leaf = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "div":
            self._in_abbr = False
        if tag == "li":
            self._in_li = self._in_leaf = False
        if tag in self._leaf_tags:
            self._in_leaf = False

    def handle_data(self, data: str) -> None:
        txt = data.strip()
        if not txt:
            return
        if self._in_abbr:
            team = txt.upper()[:3]
            if len(team) == 3 and team.isalpha():
                self._cur_team = team
                self._teams.setdefault(team, [])
            self._in_abbr = False
            return
        if self._in_leaf and self._cur_team:
            self._teams[self._cur_team].append(txt)
            self._in_leaf = False

    def result(self) -> Dict[str, list]:
        return {k: v for k, v in self._teams.items() if v}


def _parse_html(html: str, source: str, also_span: bool = False) -> Dict[str, list]:
    parser = _LineupParser(also_span=also_span)
    try:
        parser.feed(html)
    except Exception as exc:
        log.warning("[L21] %s parse error: %s", source, exc)
    return parser.result()


def _load_seed(date: str) -> Dict[str, list]:
    path = _LINEUP_DIR / f"_seed_{date}.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k.upper(): v for k, v in raw.items() if isinstance(v, list)}
    except Exception as exc:
        log.warning("[L21] seed load failed (%s): %s", path, exc)
    return {}


def _add_confirmation(
    store: Dict[str, LineupConfirmation],
    team: str,
    players: list,
    source: str,
) -> None:
    if len(team) != 3 or not team.isalpha():
        log.warning("[L21] Unknown team abbr '%s' — skipping", team)
        return
    norm = [_normalize_name(p) for p in players if p.strip()]
    note = f"partial: {len(norm)}/{_EXPECTED_TOP_N}" if 0 < len(norm) < _EXPECTED_TOP_N else ""
    store[team] = LineupConfirmation(
        team=team, confirmed_starters=norm, source=source,
        timestamp=_now_iso(), note=note,
    )


def _publish_lineup_event(
    game_id: str,
    team: str,
    starters: list,
    confirmed_at: str,
    previously_unknown: bool,
) -> None:
    """Publish a 'lineup.confirmed' event to the L46 EventBus (best-effort)."""
    if _L46 is None:
        return
    try:
        _L46.publish(
            "lineup.confirmed",
            source="L21",
            payload={
                "game_id": game_id,
                "team": team,
                "starters": starters,
                "confirmed_at": confirmed_at,
                "previously_unknown": previously_unknown,
            },
        )
        log.debug("[L21] Published lineup.confirmed for %s/%s", game_id, team)
    except Exception as exc:
        log.warning("[L21] EventBus publish failed for %s/%s: %s", game_id, team, exc)


def _load_persisted(date: str) -> Dict[str, list]:
    """Return {team: [starters]} from the persisted JSON for *date*, or {}."""
    path = _LINEUP_DIR / f"{date}.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            k.upper(): v.get("confirmed_starters", [])
            for k, v in raw.items()
            if isinstance(v, dict)
        }
    except Exception as exc:
        log.warning("[L21] persisted load failed (%s): %s", path, exc)
    return {}


def fetch_confirmed_lineups(date: Optional[str] = None) -> List[LineupConfirmation]:
    """Fetch confirmed NBA starting lineups for *date* (default: today UTC).

    Sources tried in order per team: lineups.com → rotowire → manual seed.
    Returns [] (with INFO log) if no data available.
    Persists results atomically to data/lineup_announcements/<date>.json.
    Publishes a "lineup.confirmed" event via L46 for each new or changed team.
    """
    if date is None:
        date = _today_str()
    store: Dict[str, LineupConfirmation] = {}

    # Load previously persisted lineups for change detection
    previous: Dict[str, list] = _load_persisted(date)

    # source 1: lineups.com (also_span=True covers their markup variant)
    html = _http_get(_LINEUPS_COM_URL)
    if html:
        for team, players in _parse_html(html, "lineups.com", also_span=True).items():
            if team not in store:
                _add_confirmation(store, team, players, "lineups.com")
    else:
        log.warning("[L21] lineups.com blocked or empty")

    # source 2: rotowire
    html2 = _http_get(_ROTOWIRE_URL)
    if html2:
        for team, players in _parse_html(html2, "rotowire").items():
            if team not in store:
                _add_confirmation(store, team, players, "rotowire")
    else:
        log.warning("[L21] rotowire blocked or empty")

    # source 3: manual seed
    for team, players in _load_seed(date).items():
        if team not in store:
            _add_confirmation(store, team, players, "manual_seed")

    result = list(store.values())
    if not result:
        log.info("[L21] No lineup data for %s — too early or all sources blocked", date)
    else:
        _persist(date, result)
        # Publish events for new or changed lineups
        for conf in result:
            prev_starters = previous.get(conf.team)
            previously_unknown = prev_starters is None
            roster_changed = (not previously_unknown) and (
                set(conf.confirmed_starters) != set(prev_starters)
            )
            if previously_unknown or roster_changed:
                try:
                    _publish_lineup_event(
                        game_id=date,
                        team=conf.team,
                        starters=conf.confirmed_starters,
                        confirmed_at=conf.timestamp,
                        previously_unknown=previously_unknown,
                    )
                except Exception as pub_exc:
                    log.warning("[L21] publish skipped for %s: %s", conf.team, pub_exc)
    return result


def diff_against_expected(
    confirmation: LineupConfirmation,
    fpts_data: Dict[str, dict],
) -> dict:
    """Populate confirmation.surprise_starters / benched_expected vs fpts top-5.

    fpts_data format: {player_name: {"mean": float, "team": str}}
    Returns {"surprise_starters": [...], "benched_expected": [...]}.
    Modifies *confirmation* in-place.
    """
    team_players: Dict[str, float] = {}
    for raw, info in fpts_data.items():
        if not isinstance(info, dict):
            continue
        if info.get("team", "").upper() != confirmation.team:
            continue
        team_players[_normalize_name(raw)] = float(info.get("mean", 0.0))

    top5         = set(sorted(team_players, key=team_players.__getitem__, reverse=True)[:_EXPECTED_TOP_N])
    confirmed    = set(confirmation.confirmed_starters)
    surprise     = sorted(confirmed - top5)
    benched      = sorted(top5 - confirmed)
    confirmation.surprise_starters = surprise
    confirmation.benched_expected  = benched
    return {"surprise_starters": surprise, "benched_expected": benched}


def alert_on_surprises(confirmations: List[LineupConfirmation]) -> int:
    """Send one alert per surprise starter via L22.  Returns alert count sent."""
    if send_alert is None:
        log.info("[L21] Alerting disabled — L22 not available")
        return 0
    count = 0
    for conf in confirmations:
        for player in conf.surprise_starters:
            title = f"Surprise starter: {player} ({conf.team})"
            body  = (
                f"'{player}' confirmed for {conf.team} but NOT in expected top-5. "
                f"Source: {conf.source} | {conf.timestamp}"
            )
            try:
                if send_alert(channel="news", level="warning", title=title, body=body):
                    count += 1
                    log.info("[L21] Alert: surprise starter %s (%s)", player, conf.team)
            except Exception as exc:
                log.error("[L21] alert failed for %s: %s", player, exc)
    return count


def _persist(date: str, confirmations: List[LineupConfirmation]) -> None:
    _LINEUP_DIR.mkdir(parents=True, exist_ok=True)
    out, tmp = _LINEUP_DIR / f"{date}.json", _LINEUP_DIR / f"{date}.tmp"
    try:
        tmp.write_text(json.dumps({c.team: asdict(c) for c in confirmations}, indent=2), encoding="utf-8")
        os.replace(tmp, out)
        log.info("[L21] Persisted %d team(s) → %s", len(confirmations), out)
    except OSError as exc:
        log.error("[L21] persist failed: %s", exc)


def _main(argv: Optional[list] = None) -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s")
    ap  = argparse.ArgumentParser(description="NBA Lineup Watcher (L21)")
    sub = ap.add_subparsers(dest="cmd")
    pf  = sub.add_parser("fetch")
    pf.add_argument("--date", default=None)
    sub.add_parser("once")
    args = ap.parse_args(argv)

    if args.cmd == "fetch":
        print(json.dumps([asdict(c) for c in fetch_confirmed_lineups(date=args.date)], indent=2))
    elif args.cmd == "once":
        confs = fetch_confirmed_lineups()
        n     = alert_on_surprises(confs)
        log.info("[L21] once — %d confirmation(s), %d alert(s)", len(confs), n)
        print(json.dumps([asdict(c) for c in confs], indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    _main()
