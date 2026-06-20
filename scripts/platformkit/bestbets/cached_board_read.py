"""scripts.platformkit.bestbets.cached_board_read -- freshness-stamped cache reader.

Reads data/frontend/best_bets.json and returns a freshness-gated envelope.
Closes the stale-never-green gap on the CACHE itself: even if the compute
daemon wrote a valid envelope, a consumer calling read() gets an honest
STALE verdict when the file is older than the SLA -- and the overall field
is NEVER 'ok' in that state (stale-never-green).

Defense-in-depth: past-tipoff cards are filtered out on read, even if the
sanitize() step missed them at write time (e.g. a card tip-off occurs while
the file is cached between compute cycles).

Return shape
------------
{
    "status":    "fresh" | "stale" | "unavailable",
    "overall":   str  -- copied from envelope, forced to "stale" when status!=fresh,
    "note":      str  -- human-readable explanation when stale/unavailable,
    "cards":     list -- filtered cards ([] when unavailable/stale with 0 live),
    "generated_at": float | None,
    "card_count": int,
    "stale_note": str  -- non-empty ONLY when status=="stale",
    "honest_note": str -- always the calibration reminder,
}

No $ / ROI / PnL field. CALIBRATION not edge. UNITS not $.

SLA
---
DEFAULT_SLA_SEC = 300.0  -- 5 minutes; tunable at call site.
For NBA in-season this is already generous (daemon cadence is 120s).
A year-old Polymarket card always fails this check.

RAILS: stdlib only; no network; injectable clock + path for tests; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import pathlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

_REPO = pathlib.Path(__file__).resolve().parents[3]
_DEFAULT_PATH = _REPO / "data" / "frontend" / "best_bets.json"

DEFAULT_SLA_SEC: float = 300.0  # 5 minutes

_HONEST_NOTE = (
    "MEASUREMENT-ONLY bestbets daemon. "
    "Cards = ranked calibrated divergence; UNITS not $; "
    "real-money default-DENY; calibration not edge."
)

# Card keys that may carry the event start time (mirrors board_sanitizer).
_TIPOFF_KEYS = ("tipoff_utc", "tipoff", "game_datetime", "commence_time")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_tipoff(raw: Any) -> Optional[datetime]:
    """Parse a tipoff value to an aware datetime; None if unparseable."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(raw, str):
        try:
            s = raw.strip().replace("Z", "+00:00")
            tip = datetime.fromisoformat(s)
            return tip if tip.tzinfo else tip.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return None
    return None


def _tipoff_in_past(card: Dict[str, Any], now: datetime) -> bool:
    """True when the card's event has already started/completed (stale-never-green)."""
    for key in _TIPOFF_KEYS:
        tip = _parse_tipoff(card.get(key))
        if tip is not None and tip <= now:
            return True
    return False


def _filter_past_tipoff(
    cards: List[Dict[str, Any]],
    now: datetime,
) -> List[Dict[str, Any]]:
    """Drop cards whose event start time is at or before *now*."""
    return [c for c in cards if not _tipoff_in_past(c, now)]


def _load_raw(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Read and parse the JSON cache file. Returns None if missing or corrupt."""
    try:
        text = path.read_text(encoding="ascii", errors="replace")
        doc = json.loads(text)
        if not isinstance(doc, dict):
            return None
        return doc
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        return None


def _unavailable(note: str) -> Dict[str, Any]:
    return {
        "status": "unavailable",
        "overall": "unavailable",
        "note": note,
        "cards": [],
        "generated_at": None,
        "card_count": 0,
        "stale_note": "",
        "honest_note": _HONEST_NOTE,
    }


def _stale_envelope(
    doc: Dict[str, Any],
    cards: List[Dict[str, Any]],
    age_sec: float,
    generated_at: float,
) -> Dict[str, Any]:
    stale_note = (
        "Cache is %.0f s old (SLA exceeded). "
        "overall forced to 'stale'; cards filtered for past tipoffs. "
        "Stale-never-green: do not render as live edge." % age_sec
    )
    return {
        "status": "stale",
        # Force away from 'ok' -- stale-never-green invariant.
        "overall": "stale",
        "note": doc.get("note", ""),
        "cards": cards,
        "generated_at": generated_at,
        "card_count": len(cards),
        "stale_note": stale_note,
        "honest_note": _HONEST_NOTE,
    }


def _fresh_envelope(
    doc: Dict[str, Any],
    cards: List[Dict[str, Any]],
    generated_at: float,
) -> Dict[str, Any]:
    return {
        "status": "fresh",
        "overall": doc.get("overall", "ok"),
        "note": doc.get("note", ""),
        "cards": cards,
        "generated_at": generated_at,
        "card_count": len(cards),
        "stale_note": "",
        "honest_note": _HONEST_NOTE,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read(
    *,
    path: Optional[pathlib.Path] = None,
    sla_sec: float = DEFAULT_SLA_SEC,
    now_epoch: Optional[float] = None,
) -> Dict[str, Any]:
    """Read the cached best-bets board with freshness gating.

    Parameters
    ----------
    path:
        Override for the cache file path (default: data/frontend/best_bets.json).
    sla_sec:
        Maximum acceptable age in seconds (default: DEFAULT_SLA_SEC = 300.0).
        Pass a smaller value for stricter SLAs (e.g. in-season NBA = 120).
    now_epoch:
        Injectable wall-clock epoch (float seconds) for deterministic tests.
        Defaults to time.time().

    Returns
    -------
    Dict with keys: status, overall, note, cards, generated_at, card_count,
    stale_note, honest_note.  Never raises. Never contains a $ / ROI / PnL field.
    """
    _path = path if path is not None else _DEFAULT_PATH
    _now_ts = now_epoch if now_epoch is not None else time.time()
    _now_dt = datetime.fromtimestamp(_now_ts, tz=timezone.utc)

    doc = _load_raw(_path)
    if doc is None:
        return _unavailable("Cache file missing or unreadable: %s" % _path)

    # Extract generated_at; treat missing/corrupt as unavailable.
    raw_gen = doc.get("generated_at")
    try:
        generated_at = float(raw_gen)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _unavailable(
            "Cache has no parseable generated_at field -- treating as unavailable."
        )

    age_sec = _now_ts - generated_at

    # Pull raw cards; tolerate missing key.
    raw_cards = doc.get("cards")
    if not isinstance(raw_cards, list):
        raw_cards = []

    # Defense-in-depth: drop past-tipoff cards regardless of freshness verdict.
    live_cards = _filter_past_tipoff(raw_cards, _now_dt)

    if age_sec > sla_sec:
        return _stale_envelope(doc, live_cards, age_sec, generated_at)

    return _fresh_envelope(doc, live_cards, generated_at)


__all__ = ["DEFAULT_SLA_SEC", "read"]
