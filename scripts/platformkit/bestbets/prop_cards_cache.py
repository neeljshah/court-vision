"""scripts.platformkit.bestbets.prop_cards_cache -- decoupled prop-card cache.

Decouples the SLOW prop computation (full prop board: thousands of player/stat
model evaluations) from the FAST best-bets board tick. The expensive build runs
ONCE per m13 props daemon cycle (300 s cadence); the result is written here. The
fast m10 board (build_cards) READS this cache with a freshness/SLA gate instead
of recomputing the board inline -- which previously made the m10 tick hang >240s.

DATA FLOW
---------
  m13 props_pred_tick_runner (300 s)
      -> build_bounded_prop_cards()  (slow; capped + ranked)
      -> write(cards, n_more, now)   -> data/frontend/prop_cards_cache.json
  m10 build_cards (120 s)
      -> read(now_epoch=now)         (fast; freshness-gated)
      -> append cards to the unified board

CACHE SCHEMA (data/frontend/prop_cards_cache.json)
--------------------------------------------------
{
  "generated_at": <epoch float>,         # write wall-clock (freshness anchor)
  "overall":      "ok" | "UNAVAILABLE",
  "card_count":   int,                    # number of cards served
  "n_more_model_only": {<sport>: int},    # honest "N more available" per sport
  "cards":        [ <prop BestBetCard>, ... ],
  "honest_note":  str,
}

FRESHNESS (stale-never-green)
-----------------------------
read() returns status fresh|stale|unavailable. When the cache is older than
sla_sec (default 1200 s -- 4x the 300 s m13 cadence so one slow-but-alive tick is
tolerated, yet a genuinely dead m13 still reads stale after ~4 missed cadences),
status is "stale" and cards are []. A cache stamped in the FUTURE beyond a small
skew tolerance (clock skew / corruption -> negative age) is ALSO "stale", never
green (the future half of the rail). A missing/corrupt cache -> "unavailable",
cards []. The fast board therefore NEVER blocks on the slow build and NEVER
serves a stale prop set as live.

HONESTY: model-only cards carry model_only=True / edge_claimed=False / no edge;
priced cards carry edge_vs_market (prob diff, NOT $). No $ / pnl / roi field.

RAILS: stdlib only; no network; injectable clock + path for tests; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List, Optional

_REPO = pathlib.Path(__file__).resolve().parents[3]
_DEFAULT_PATH = _REPO / "data" / "frontend" / "prop_cards_cache.json"

# Short-lived last-good prop-LINE snapshot dir (per sport). Lets the prop builder
# reuse the last successful PrizePicks / Underdog line set when the live feed 429s,
# WITHOUT re-polling (which causes the 429). data/frontend is a sanctioned cache dir
# (NOT data/registry). The TTL caps reuse so a feed outage can't serve a stale priced
# line as live; MODEL-ONLY props (the always-fresh layer) never read this cache.
_LINE_CACHE_DIR = _REPO / "data" / "frontend" / "prop_line_cache"
_LINE_CACHE_TTL_SEC: float = 1800.0  # 30 min

# SLA window for the m10 board reading the m13-written prop cache.
#
# m13 writes on a 300 s cadence, but the write happens AFTER the slow full-board
# compute -- so the effective gap between two successive cache timestamps is
# (cadence + that tick's compute time). When the board is large and the box is
# busy, a single slow tick's compute can run long enough that, combined with the
# 300 s cadence, the cache age crosses an SLA of 600 s right before the next write
# lands -- momentarily flipping the board to stale and ZEROING 600+ live cards even
# though m13 is healthy (just slightly slow). That is a false stale.
#
# Widen the SLA to 1200 s = 4x the 300 s cadence. This comfortably absorbs ONE slow
# tick (300 s cadence + up to ~900 s worst-case compute, or one fully skipped cycle)
# without ever zeroing a healthy board. It still catches a GENUINELY DEAD m13: a
# stalled daemon stops writing entirely, so after ~4 missed cadences (>1200 s with
# no new write) the cache reads STALE and props are correctly omitted -- stale-never-
# green is preserved for a real outage; only a single slow-but-alive tick is tolerated.
DEFAULT_SLA_SEC: float = 1200.0

# Future-skew tolerance (seconds). A generated_at slightly AHEAD of our clock is a
# benign clock offset between the writing box and the reader -- treat it as fresh
# (age ~0). But a cache stamped WILDLY in the future (clock skew / corruption / a
# bad write) has a NEGATIVE age, which would otherwise always satisfy age <= sla and
# read FRESH forever -- the future half of stale-never-green, fail-OPEN. Anything more
# than this tolerance into the future is UNTRUSTED -> read STALE (fail-closed),
# mirroring odds_provider.freshness.FUTURE_SKEW_TOLERANCE_SEC (kept in lockstep).
FUTURE_SKEW_TOLERANCE_SEC: float = 120.0  # 2 minutes of tolerated clock skew

_HONEST_NOTE = (
    "Decoupled prop-card cache. Computed ONCE per m13 props cycle (slow full "
    "prop board), read FAST by the m10 board. Model-only cards carry "
    "model_only=True with NO edge/CLV; priced cards carry edge_vs_market "
    "(a prob diff, NOT $). UNITS not $; stale-never-green; calibration not edge."
)


def default_path() -> pathlib.Path:
    """Return the canonical cache path (data/frontend/prop_cards_cache.json)."""
    return _DEFAULT_PATH


# ---------------------------------------------------------------------------
# Write (m13 side)
# ---------------------------------------------------------------------------

def write(
    cards: List[Dict[str, Any]],
    now: float,
    *,
    n_more_model_only: Optional[Dict[str, int]] = None,
    path: Optional[pathlib.Path] = None,
) -> bool:
    """Atomically write the bounded prop-card set to the cache. Never raises.

    Returns True on success. The envelope is overall=ok when cards exist, else
    UNAVAILABLE (honest: nothing live, not a hang).
    """
    _path = path if path is not None else _DEFAULT_PATH
    safe_cards = [c for c in (cards or []) if isinstance(c, dict)]
    doc = {
        "generated_at": float(now),
        "overall": "ok" if safe_cards else "UNAVAILABLE",
        "card_count": len(safe_cards),
        "n_more_model_only": dict(n_more_model_only or {}),
        "cards": safe_cards,
        "honest_note": _HONEST_NOTE,
    }
    try:
        _path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = _path.with_suffix(_path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(_path))
        return True
    except Exception:  # noqa: BLE001 -- writer must never raise
        return False


# ---------------------------------------------------------------------------
# Read (m10 side)
# ---------------------------------------------------------------------------

def _load_raw(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Read+parse the cache JSON; None when missing/corrupt. Never raises."""
    try:
        doc = json.loads(path.read_text(encoding="ascii", errors="replace"))
        return doc if isinstance(doc, dict) else None
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        return None


def _envelope(status: str, cards: List[Dict[str, Any]], gen_at: Optional[float],
              n_more: Dict[str, int], note: str) -> Dict[str, Any]:
    return {
        "status": status,
        # stale-never-green: overall is ok ONLY when status==fresh.
        "overall": "ok" if status == "fresh" and cards else (
            "stale" if status == "stale" else "unavailable"),
        "cards": cards,
        "card_count": len(cards),
        "generated_at": gen_at,
        "n_more_model_only": n_more,
        "stale_note": note if status == "stale" else "",
        "honest_note": _HONEST_NOTE,
    }


def read(
    *,
    path: Optional[pathlib.Path] = None,
    sla_sec: float = DEFAULT_SLA_SEC,
    now_epoch: Optional[float] = None,
) -> Dict[str, Any]:
    """Read the cached bounded prop cards with freshness gating. Never raises.

    Returns an envelope with keys: status (fresh|stale|unavailable), overall,
    cards, card_count, generated_at, n_more_model_only, stale_note, honest_note.

    * Missing / corrupt cache  -> status=unavailable, cards=[].
    * Cache older than sla_sec  -> status=stale,       cards=[] (never green).
    * Otherwise                 -> status=fresh,       cards=<cached cards>.

    This read does NO model computation -- it is a pure JSON read, so the fast
    board tick can call it without ever triggering the slow full-board build.
    """
    _path = path if path is not None else _DEFAULT_PATH
    _now = now_epoch if now_epoch is not None else time.time()

    doc = _load_raw(_path)
    if doc is None:
        return _envelope("unavailable", [], None, {},
                         "cache missing or unreadable")

    try:
        gen_at = float(doc.get("generated_at"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _envelope("unavailable", [], None, {},
                         "cache has no parseable generated_at")

    raw_cards = doc.get("cards")
    cards = [c for c in raw_cards if isinstance(c, dict)] \
        if isinstance(raw_cards, list) else []
    raw_more = doc.get("n_more_model_only")
    n_more = {str(k): int(v) for k, v in raw_more.items()} \
        if isinstance(raw_more, dict) else {}

    age = _now - gen_at
    # Future half of stale-never-green: a cache stamped beyond the skew tolerance
    # AHEAD of our clock (clock skew / corruption) has a negative age that would
    # otherwise read fresh forever. Fail CLOSED -> stale, never green.
    if age < -FUTURE_SKEW_TOLERANCE_SEC:
        note = ("prop cache generated_at is %.0f s in the FUTURE (beyond %.0f s "
                "skew tolerance); untrusted -> props omitted from board -- "
                "stale-never-green." % (-age, FUTURE_SKEW_TOLERANCE_SEC))
        return _envelope("stale", [], gen_at, n_more, note)
    if age > sla_sec:
        note = ("prop cache is %.0f s old (SLA %.0f s exceeded); "
                "props omitted from board -- stale-never-green." % (age, sla_sec))
        return _envelope("stale", [], gen_at, n_more, note)

    return _envelope("fresh", cards, gen_at, n_more, "")


# ---------------------------------------------------------------------------
# Last-good prop-LINE snapshot (429 resilience for the priced layer)
# ---------------------------------------------------------------------------

def _line_cache_path(sport: str) -> pathlib.Path:
    safe = "".join(c for c in str(sport) if c.isalnum() or c in "_-") or "x"
    return _LINE_CACHE_DIR / ("%s.json" % safe)


def line_cache_write(sport: str, lines: List[Any]) -> None:
    """Persist the last-good gathered PropLines for *sport* (atomic). Stores each
    line via its to_dict(); never fabricates. Never raises."""
    try:
        rows = [ln.to_dict() for ln in (lines or []) if hasattr(ln, "to_dict")]
        if not rows:
            return
        path = _line_cache_path(sport)
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"generated_at": time.time(), "rows": rows}
        raw = json.dumps(doc, ensure_ascii=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
    except Exception:  # noqa: BLE001 -- writer must never raise
        return


def line_cache_read(sport: str,
                    ttl_sec: float = _LINE_CACHE_TTL_SEC) -> Optional[List[Any]]:
    """Reload a fresh-enough last-good PropLine snapshot for *sport*. None when
    missing / corrupt / older than ttl_sec (so a feed outage can't serve a stale
    priced line indefinitely). Rehydrates dataclass PropLine rows. Never raises."""
    try:
        path = _line_cache_path(sport)
        doc = json.loads(path.read_text(encoding="ascii", errors="replace"))
        if not isinstance(doc, dict):
            return None
        gen = float(doc.get("generated_at"))
        if time.time() - gen > float(ttl_sec):
            return None
        rows = doc.get("rows")
        if not isinstance(rows, list) or not rows:
            return None
        from scripts.platformkit.odds_provider.prop_base import PropLine  # noqa: PLC0415
        keys = PropLine.__dataclass_fields__.keys()
        out = [PropLine(**{k: r.get(k) for k in keys})
               for r in rows if isinstance(r, dict)]
        return out or None
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        return None


__all__ = ["DEFAULT_SLA_SEC", "FUTURE_SKEW_TOLERANCE_SEC", "default_path",
           "write", "read", "line_cache_write", "line_cache_read"]
