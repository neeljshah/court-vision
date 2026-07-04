"""scripts.platformkit.autonomy.post_restart_enrichment_checks -- LANE 5 (waves
11-13) additive extension to the post-restart verifier: m37_ingame_enrichment's
own data-flow surface (fotmob/gumbo/book-depth pollers) + the enriched tick
fields it feeds into in-play capture rows + the espn_event_id id-bridge field.

Mirrors post_restart_capture_checks.py's pattern EXACTLY (same PASS/FAIL/PENDING
vocabulary, same "no live game -> PENDING, never FAIL" discipline). Split into
its own module so post_restart_checks.py / post_restart_capture_checks.py stay
under the <=300 LOC rail (this lane's charter: additive-only, no edits to
inplay_capture_loop.py / stack_specs.py).

WHAT IT CHECKS (each row independent, one bad row never crashes the rest):
  (h) m37's 3 poller artifact dirs exist + have a fresh mtime: fotmob_live/,
      gumbo_live/, book_depth/ (kalshi + polymarket). PENDING-when-no-live-game
      semantics identical to check_capture_dirs -- these pollers only produce
      fresh rows when a live game of the relevant sport is on; an idle slate
      correctly reads PENDING, never FAIL.
  (i) a fresh in-play tick (any capture sport) carries the enrichment keys
      inplay_capture_loop._enrichment_fields() always emits (xg_home, xg_away,
      xg_asof_min, spread_bp, book_thinness, stale_quote, espn_wp) -- None
      values are fine (that is the honest-absence contract), the check is KEY
      PRESENCE, not non-null. No live game / no tick file -> PENDING.
  (j) a fresh mlb capture tick's state carries a non-null espn_event_id (the
      id-bridge field ingame_live_state._extract() emits) -- PENDING without a
      live mlb game, FAIL if a fresh tick exists but the key is missing/None.

Every external effect (wall clock, live-game lookup) is INJECTABLE; this
module reads ONLY already-written files under data/domains/**, data/cache/**,
data/frontend/ops/** -- never fetches over the network, never touches a PID,
never writes data/registry/, never flips a flag.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_post_restart_enrichment_checks.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.platformkit.autonomy.post_restart_checks import FAIL, PASS, PENDING, row

_REPO = Path(__file__).resolve().parents[3]
_DOMAINS = _REPO / "data" / "domains"
_BOOK_DEPTH = _REPO / "data" / "cache" / "book_depth"
_LINE_HIST = _REPO / "data" / "cache" / "line_history"

# m37's 3 poller artifact dirs (name -> (path, sport gate for the live-game
# lookup, honest label)). fotmob only produces rows for a live soccer_intl
# fixture; gumbo only for a live mlb game; book_depth is cross-sport (mlb +
# wnba per ingame_enrichment_runner._run_book_depth) so it gates on EITHER.
_FOTMOB_DIR = _DOMAINS / "soccer_intl" / "fotmob_live"
_GUMBO_DIR = _DOMAINS / "mlb" / "gumbo_live"

# Enrichment keys inplay_capture_loop._enrichment_fields() ALWAYS emits (dict
# always has all 7 keys; values are None-safe by design -- see that fn's
# module comment). Presence, not non-null, is what proves the wiring is live.
ENRICHMENT_KEYS: List[str] = [
    "xg_home", "xg_away", "xg_asof_min", "spread_bp", "book_thinness",
    "stale_quote", "espn_wp",
]


def _newest_mtime(dir_path: Path, pattern: str = "*.jsonl") -> Any:
    """Newest mtime among *pattern* files in *dir_path*, or None if absent/empty."""
    try:
        if not dir_path.is_dir():
            return None
        files = list(dir_path.glob(pattern))
        if not files:
            return None
        return max(f.stat().st_mtime for f in files)
    except Exception:  # noqa: BLE001
        return None


def check_m37_artifact_dirs(now: float, *, live_game_fn: Callable[[str], bool],
                            fresh_sec: float = 1800.0) -> List[Dict[str, Any]]:
    """(h) m37's 3 poller artifact dirs: fresh mtime when the gating sport has a
    live game right now; PENDING (never FAIL) on a quiet slate."""
    rows: List[Dict[str, Any]] = []

    def _one(name: str, dir_path: Path, gate_sport: str) -> None:
        try:
            live = bool(live_game_fn(gate_sport))
        except Exception as exc:  # noqa: BLE001 -- an unknown live state is NOT a FAIL
            rows.append(row(name, PENDING, "live-game lookup raised %s" % type(exc).__name__))
            return
        if not live:
            rows.append(row(name, PENDING, "no live %s game right now" % gate_sport))
            return
        if not dir_path.is_dir():
            rows.append(row(name, FAIL, "live game but no dir %s" % dir_path))
            return
        newest = _newest_mtime(dir_path)
        if newest is None:
            rows.append(row(name, FAIL, "live game, dir exists, but no jsonl rows yet"))
            return
        age = now - newest
        if age <= fresh_sec:
            rows.append(row(name, PASS, "live game, freshest row %.0fs old (<=%.0fs)"
                            % (age, fresh_sec)))
        else:
            rows.append(row(name, FAIL, "live game but freshest row %.0fs old (>%.0fs)"
                            % (age, fresh_sec)))

    _one("m37_fotmob_live", _FOTMOB_DIR, "soccer_intl")
    _one("m37_gumbo_live", _GUMBO_DIR, "mlb")

    # book_depth is cross-sport (mlb OR wnba per _run_book_depth's sports=[...]);
    # gate on either being live so a genuinely idle slate still reads PENDING.
    try:
        live_mlb = bool(live_game_fn("mlb"))
    except Exception:  # noqa: BLE001
        live_mlb = False
    try:
        live_wnba = bool(live_game_fn("wnba"))
    except Exception:  # noqa: BLE001
        live_wnba = False
    if not (live_mlb or live_wnba):
        rows.append(row("m37_book_depth", PENDING, "no live mlb/wnba game right now"))
    elif not _BOOK_DEPTH.is_dir():
        rows.append(row("m37_book_depth", FAIL, "live game but no dir %s" % _BOOK_DEPTH))
    else:
        newest = None
        try:
            for venue_dir in _BOOK_DEPTH.iterdir():
                if venue_dir.is_dir():
                    vm = _newest_mtime(venue_dir)
                    if vm is not None and (newest is None or vm > newest):
                        newest = vm
        except Exception:  # noqa: BLE001
            newest = None
        if newest is None:
            rows.append(row("m37_book_depth", FAIL,
                            "live game, dir exists, but no venue jsonl rows yet"))
        else:
            age = now - newest
            if age <= fresh_sec:
                rows.append(row("m37_book_depth", PASS,
                                "live game, freshest row %.0fs old (<=%.0fs)"
                                % (age, fresh_sec)))
            else:
                rows.append(row("m37_book_depth", FAIL,
                                "live game but freshest row %.0fs old (>%.0fs)"
                                % (age, fresh_sec)))
    return rows


def _newest_tick_row(sport: str) -> Any:
    """Last JSON line of the freshest capture file for *sport*, or None."""
    sport_dir = _LINE_HIST / sport
    try:
        if not sport_dir.is_dir():
            return None
        files = sorted(sport_dir.glob("*.jsonl")) + sorted(sport_dir.glob("*.json"))
        if not files:
            return None
        newest = max(files, key=lambda f: f.stat().st_mtime)
        last_line = None
        with newest.open("r", encoding="ascii", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last_line = line
        if last_line is None:
            return None
        parsed = json.loads(last_line)
        return parsed if isinstance(parsed, dict) else None
    except Exception:  # noqa: BLE001
        return None


def check_enrichment_tick_fields(now: float, *, live_game_fn: Callable[[str], bool],
                                 sport: str = "mlb") -> Dict[str, Any]:
    """(i) a fresh tick for *sport* carries all 7 enrichment keys (None values
    fine). No live game -> PENDING."""
    name = "enrichment_tick_fields_%s" % sport
    try:
        live = bool(live_game_fn(sport))
    except Exception as exc:  # noqa: BLE001
        return row(name, PENDING, "live-game lookup raised %s" % type(exc).__name__)
    if not live:
        return row(name, PENDING, "no live %s game right now" % sport)
    parsed = _newest_tick_row(sport)
    if parsed is None:
        return row(name, PENDING, "live game but no readable capture tick yet")
    missing = [k for k in ENRICHMENT_KEYS if k not in parsed]
    if missing:
        return row(name, FAIL, "fresh tick missing enrichment keys: %s" % missing,
                    missing=missing)
    return row(name, PASS, "fresh tick carries all %d enrichment keys (values may be None)"
              % len(ENRICHMENT_KEYS))


def check_espn_event_id_mlb(now: float, *, live_game_fn: Callable[[str], bool]) -> Dict[str, Any]:
    """(j) a fresh mlb capture tick carries a non-null espn_event_id."""
    name = "espn_event_id_mlb"
    try:
        live = bool(live_game_fn("mlb"))
    except Exception as exc:  # noqa: BLE001
        return row(name, PENDING, "live-game lookup raised %s" % type(exc).__name__)
    if not live:
        return row(name, PENDING, "no live mlb game right now")
    parsed = _newest_tick_row("mlb")
    if parsed is None:
        return row(name, PENDING, "live game but no readable capture tick yet")
    eid = parsed.get("espn_event_id")
    if eid:
        return row(name, PASS, "fresh mlb tick carries espn_event_id=%r" % eid)
    return row(name, FAIL, "fresh mlb tick present but espn_event_id missing/null")


__all__ = [
    "ENRICHMENT_KEYS",
    "check_m37_artifact_dirs", "check_enrichment_tick_fields", "check_espn_event_id_mlb",
]
