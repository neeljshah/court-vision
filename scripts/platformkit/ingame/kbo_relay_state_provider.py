"""scripts.platformkit.ingame.kbo_relay_state_provider -- KBO capture-only state provider
(kbo-live-confirm-wire lane, wave-55).

LIVE-CONFIRMED THIS WAVE: kbo_naver_relay.py's relay route (wave-22) was probed against
game 20260705OBWO02026 while genuinely mid-game (2 polls 66s apart) -- currentGameState's
score/base/pitcher/batter fields AND the top-level `inn`/`no` (relay sequence) fields all
PROGRESSED between polls (awayScore 5->6, base1/base2 changed, pitcher/batter both
rotated, inn stable at 8 but relay seq no 79->80). See
data/domains/kbo/naver_relay_live_sample_2026-07-05.json for both raw payloads with as-of
fetch timestamps. This confirms the relay is a genuine in-game feed, not a cached/stale
snapshot -- closing the "UNCONFIRMED mid-game" gap kbo_naver_relay.py's docstring flagged.

SCOPE (capture-only, binding): this module maps a relay payload -> an as-of STATE ROW for
observability/corpus-building ONLY. It carries NO model probability (the KBO base fit is
HONEST_NEGATIVE and unwired -- see kbo_live_model.py) and triggers NO dispatch branch, NO
bet decision, NO live_board change. It is the same class of addition as
ingame_id_resolver_mlb.make_tick_deep_fn: a fail-open (gid)->dict enricher the capture
loop can optionally merge onto its resolved state.

FAIL-OPEN CONTRACT: relay_state_for_game() and make_kbo_state_fn()'s returned closure
NEVER raise -- any exception (network, bad shape, missing fields) yields None, which the
capture loop's existing None-safe merge (`if isinstance(deep, dict) and deep: state =
{**state, **deep}`) treats as "nothing to add this tick", identical to a dead MLB
resolver. No exception here can ever reach or alter the host poll cycle.

STATE ROW SHAPE: {inning, half, outs, base_state, score_home, score_away, count, fetch_ts}.
  * inning     = relay's top-level `inn` (int) or None.
  * half       = "top" if homeOrAway=="0" else "bottom" if =="1" else None (Naver's
                 convention: homeOrAway is WHO IS BATTING; 0=away batting=top of inning).
  * outs       = currentGameState.out (int) or None.
  * base_state = "1_2_3" style compact label built from base1/2/3 occupancy (kbo_naver_
                 relay.extract_base_out_state's booleans), e.g. "1--" / "-2-" / "123".
                 "---" if bases empty, None if currentGameState itself is missing.
  * score_home / score_away = ints or None.
  * count      = "B-S" (balls-strikes) string, e.g. "1-0", or None if either is absent.
  * fetch_ts   = UTC ISO8601 as-of timestamp for this row (when THIS module fetched it,
                 not the venue's own event time -- the feed carries no such timestamp).

STATE-STORE CONVENTION: rows append to data/cache/kbo_relay_state/<game_id>.jsonl (one
JSON object per line, atomic .tmp+os.replace -- same discipline as live_grade._append_atomic),
mirroring the existing data/cache/ingame_grade/<sport>/<game_id>.jsonl and data/cache/
inplay_history/<sport>/<date>.jsonl per-game/per-sport jsonl conventions already in this
package. This module writes ONLY this new tree -- never ingame_grade, never inplay_history.

INVARIANTS: <=300 LOC; ASCII only; no $/edge fields; never writes data/registry/; never
touches src/ kernel/ api/; network only via the injected/default kbo_naver_relay fetchers
(already stealth-capable through resilient_get_json).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_relay_state_provider.py -q
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.ingame.kbo_naver_relay import extract_base_out_state, fetch_relay

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/kbo_relay_state_provider.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_DIR = _REPO_ROOT / "data" / "cache" / "kbo_relay_state"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _half_from_home_or_away(raw: Dict[str, Any]) -> Optional[str]:
    """Naver's homeOrAway = who is CURRENTLY BATTING: "0" = away batting = top of inning,
    "1" = home batting = bottom. None if the field is absent/unrecognized (never guessed)."""
    v = raw.get("homeOrAway")
    if v is None:
        return None
    s = str(v)
    if s == "0":
        return "top"
    if s == "1":
        return "bottom"
    return None


def _base_state_label(bos: Dict[str, Any]) -> Optional[str]:
    """Compact 3-char base-occupancy label from extract_base_out_state's booleans, e.g.
    "1--" (runner on 1st only), "-2-", "123" (bases loaded), "---" (empty). None if the
    booleans themselves are absent (bos is None upstream)."""
    if not isinstance(bos, dict):
        return None
    b1 = "1" if bos.get("base1") else "-"
    b2 = "2" if bos.get("base2") else "-"
    b3 = "3" if bos.get("base3") else "-"
    return b1 + b2 + b3


def relay_state_for_game(game_id: str,
                         http_get: Optional[Callable] = None,
                         relay: Optional[Dict[str, Any]] = None
                         ) -> Optional[Dict[str, Any]]:
    """Map ONE game's relay payload to an as-of state row. None on any failure/absence
    (never raises). *relay* injects a pre-fetched raw payload (test path / avoids a
    duplicate fetch if the caller already has one); otherwise fetches fresh via
    kbo_naver_relay.fetch_relay(game_id, http_get)."""
    try:
        raw = relay if relay is not None else fetch_relay(game_id, http_get=http_get)
        if not isinstance(raw, dict):
            return None
        cgs = raw.get("currentGameState")
        bos = extract_base_out_state(raw) if isinstance(cgs, dict) else None
        balls = _int_or_none(cgs.get("ball")) if isinstance(cgs, dict) else None
        strikes = _int_or_none(cgs.get("strike")) if isinstance(cgs, dict) else None
        count = "%d-%d" % (balls, strikes) if balls is not None and strikes is not None else None
        row = {
            "game_id": str(game_id),
            "inning": _int_or_none(raw.get("inn")),
            "half": _half_from_home_or_away(raw),
            "outs": (bos or {}).get("outs"),
            "base_state": _base_state_label(bos) if bos is not None else None,
            "score_home": (bos or {}).get("home_score"),
            "score_away": (bos or {}).get("away_score"),
            "count": count,
            "fetch_ts": _utc_iso(),
        }
        # A row with EVERY field None carries no signal -- treat as absence, not a row.
        if all(v is None for k, v in row.items() if k not in ("game_id", "fetch_ts")):
            return None
        return row
    except Exception as exc:  # noqa: BLE001 -- capture-only enrichment must never raise
        logger.debug("kbo_relay_state_provider relay_state_for_game(%s) failed: %s", game_id, exc)
        return None


def _state_path(game_id: str, out_dir: Optional[Path] = None) -> Path:
    base = Path(out_dir) if out_dir is not None else DEFAULT_STATE_DIR
    return base / ("%s.jsonl" % str(game_id))


def append_state_row(game_id: str, row: Dict[str, Any],
                     out_dir: Optional[Path] = None) -> bool:
    """Append *row* to data/cache/kbo_relay_state/<game_id>.jsonl (atomic .tmp+os.replace,
    same discipline as live_grade._append_atomic). True iff the write landed. Never raises."""
    try:
        path = _state_path(game_id, out_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if path.is_file():
            with path.open("r", encoding="utf-8") as fh:
                existing = fh.read()
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(existing)
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:  # noqa: BLE001 -- a write failure is measurement loss, not a crash
        logger.warning("kbo_relay_state_provider append_state_row(%s) failed: %s", game_id, exc)
        return False


def make_kbo_state_fn(*, http_get: Optional[Callable] = None,
                      out_dir: Optional[Path] = None,
                      capture: bool = True
                      ) -> Callable[[str], Optional[Dict[str, Any]]]:
    """Build a (gid)->dict|None closure mirroring ingame_id_resolver_mlb.make_tick_deep_fn's
    per-tick enricher shape, for injection as inplay_capture_loop's kbo_state_fn param.

    *capture* (default True): also append the resolved row to disk via append_state_row
    (data/cache/kbo_relay_state/<game_id>.jsonl) as a SIDE EFFECT of the lookup, mirroring
    how the capture loop itself persists ticks. capture=False returns the mapped row without
    writing (pure lookup, used by tests that check the mapping without touching disk).
    The closure NEVER raises (relay_state_for_game and append_state_row are both already
    exception-safe); any failure degrades to None, which the capture loop's fail-open merge
    treats as "no enrichment this tick" -- identical to the MLB deep-state precedent.
    """
    def _fn(gid: str) -> Optional[Dict[str, Any]]:
        row = relay_state_for_game(gid, http_get=http_get)
        if row is None:
            return None
        if capture:
            append_state_row(gid, row, out_dir=out_dir)
        return row
    return _fn


__all__ = [
    "DEFAULT_STATE_DIR", "relay_state_for_game", "append_state_row", "make_kbo_state_fn",
]
