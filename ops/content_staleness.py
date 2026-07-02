"""ops.content_staleness -- a CONSERVATIVE stuck-empty soft signal.

The liveness / freshness health path (ops.health_aggregator) answers "is the
daemon alive and beating?". It does NOT look at output CONTENT, so a producer
that is alive + beating but stuck emitting an empty board forever still reads
GREEN. This module adds the missing content check WITHOUT touching the rollup
that gates READY -- it is a pure, opt-in SOFT signal that only emits NOTES.

HONEST-EMPTY vs STUCK
---------------------
An empty surface is OFTEN correct: offseason / no games / all games in-progress
means there is genuinely no pregame card to produce, and GREEN is right. The
ONLY dangerous case is a STUCK surface: its INPUT clearly exists yet its OUTPUT
stays empty. We distinguish the two using the surface's OWN published contract:

  * Each predict_service surface writes a per-sport ``status`` field. The
    producer sets ``status == "unavailable"`` (with a human ``note``) when it
    has NO usable input -- that is the producer's OWN honest-empty declaration.
    We NEVER flag an "unavailable" surface: honest-empty stays green.

  * ``status == "ok"`` is the producer asserting it consumed a usable input /
    snapshot. If output is STILL empty there (no predictions AND no markets),
    AND that empty state has persisted (the surface's ``generated_at`` is older
    than a generous grace window so a single mid-write blip cannot trip it),
    that is the genuine STUCK case -> a DEGRADED-level NOTE.

This rule is structurally false-red-proof for honest-empty: an offseason /
no-games surface declares ``status != "ok"`` and is skipped. Only an
input-present-yet-empty surface is ever named.

CONTRACT
--------
content_signals(*, now=None, surfaces_dir=None, grace_sec=None) -> dict
    {
      "checked":  [<sport>...],         # surfaces inspected
      "stuck":    [{sport, status, age_sec, reason}...],   # input-present-empty
      "honest_empty": [<sport>...],     # empty + status unavailable (NOT flagged)
      "notes":    [<str>...],           # one DEGRADED-level note per stuck surface
    }
    NEVER raises, NEVER reads data/registry/, makes NO network call, and does
    NOT feed the supervisor liveness/readiness rollup. A surface it cannot read
    is simply skipped (it makes no stuck claim about an unreadable file).

INVARIANTS: <=300 LOC; ASCII only; stdlib only; never raises; injectable clock +
paths; never writes anything; never gates READY. Build only under ops/.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Sports whose predict_service surface we inspect. Derived to mirror the live
# producer output tree; an absent sport directory is simply skipped.
_SPORTS = ("nba", "mlb", "soccer", "tennis")

# A surface must have been quietly empty for at least this long before we call
# it STUCK -- a generous grace so a single mid-write / between-cycle read can
# never trip a false note. The slowest producer cadence (soccer scheduler) is
# ~1200s; this window sits comfortably past two of those.
_DEFAULT_GRACE_SEC: float = 3600.0  # 1 hour


def _find_repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(8):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[1]


_REPO_ROOT = _find_repo_root()
_DEFAULT_SURFACES_DIR = _REPO_ROOT / "data" / "frontend" / "predict_service"


def _parse_iso(ts: Any) -> Optional[float]:
    """Parse an ISO-8601 (or epoch) timestamp to epoch seconds. None on failure."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        s = str(ts).strip().replace("Z", "+00:00")
        if not s:
            return None
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001 -- an unparseable stamp makes no claim
        return None


def _surface_age_sec(surface: Dict[str, Any], path: Path, now: float) -> Optional[float]:
    """Age of the surface: prefer its published generated_at, else file mtime."""
    age = _parse_iso(surface.get("generated_at"))
    if age is not None:
        return now - age
    try:
        import os
        return now - float(os.path.getmtime(str(path)))
    except OSError:
        return None


def _is_empty(surface: Dict[str, Any]) -> bool:
    """A surface is empty when it carries no predictions AND no markets."""
    preds = surface.get("predictions")
    markets = surface.get("markets")
    n_pred = len(preds) if isinstance(preds, list) else 0
    n_mkt = len(markets) if isinstance(markets, list) else 0
    return n_pred == 0 and n_mkt == 0


def _classify(
    sport: str,
    path: Path,
    now: float,
    grace_sec: float,
) -> Optional[Dict[str, Any]]:
    """Classify one surface. Returns a row tagged ``kind``.

    kind in {stuck, honest_empty, healthy}; None when the surface cannot be read
    (missing / corrupt) so it makes NO claim and is NOT counted as checked.
    """
    try:
        if not path.exists():
            return None
        surface = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(surface, dict):
            return None
    except Exception:  # noqa: BLE001 -- an unreadable surface makes no stuck claim
        return None

    if not _is_empty(surface):
        return {"kind": "healthy", "sport": sport}  # has output -> nothing to say

    status = str(surface.get("status", "")).lower()
    age_sec = _surface_age_sec(surface, path, now)

    # status != "ok" -> the producer's OWN honest-empty declaration. Never flag.
    if status != "ok":
        return {"kind": "honest_empty", "sport": sport, "status": status or "unknown"}

    # status == "ok" -> input present per the producer, yet output is empty.
    # Require the empty state to have PERSISTED past the grace window so a single
    # mid-write read cannot trip a false note.
    if age_sec is None or age_sec < grace_sec:
        return None  # too fresh to call stuck -- conservative

    return {
        "kind": "stuck",
        "sport": sport,
        "status": status,
        "age_sec": round(age_sec, 1),
        "reason": (
            "surface status=ok (input present) but output empty for %.0fs "
            "(>= grace %.0fs) -- producer may be stuck" % (age_sec, grace_sec)
        ),
    }


def content_signals(
    *,
    now: Optional[float] = None,
    surfaces_dir: Optional[Union[str, Path]] = None,
    grace_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Inspect predict_service surfaces for the STUCK-empty content state.

    A pure, opt-in soft signal. Honest-empty surfaces (status != "ok") are
    listed but NEVER flagged. Only input-present-yet-empty surfaces that have
    persisted past *grace_sec* yield a DEGRADED-level note. Never raises.
    """
    import time

    _now = float(now) if now is not None else time.time()
    base = Path(surfaces_dir) if surfaces_dir is not None else _DEFAULT_SURFACES_DIR
    grace = float(grace_sec) if grace_sec is not None else _DEFAULT_GRACE_SEC

    checked: List[str] = []
    stuck: List[Dict[str, Any]] = []
    honest_empty: List[str] = []
    notes: List[str] = []

    for sport in _SPORTS:
        path = base / sport / "latest.json"
        row = _classify(sport, path, _now, grace)
        if row is None:
            continue  # missing / corrupt -> no claim, not counted as checked
        checked.append(sport)
        if row.get("kind") == "honest_empty":
            honest_empty.append(sport)
        elif row.get("kind") == "stuck":
            stuck.append({k: v for k, v in row.items() if k != "kind"})
            notes.append(
                "content-staleness: %s surface is DEGRADED -- %s"
                % (sport, row.get("reason"))
            )

    return {
        "checked": checked,
        "stuck": stuck,
        "honest_empty": honest_empty,
        "notes": notes,
    }


__all__ = ["content_signals"]
