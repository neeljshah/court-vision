"""G380 additive position provenance helpers.

The producer files are human-gated, so the proposed diff stays a one-line import
plus one call per position-write site and every decision lives here, where it is
testable.  Nothing in this module feeds back into a tracking decision: it only
records which branch emitted a position, so the emitted row can name its source.

Label contract (closed set, additive columns only):
  DETECTION  a fresh detection was assigned to the slot this tick
  PREDICTION the position was filled by a Kalman/optical-flow projection
  CLAMP      a jump guard replaced the new position with the previous one
  SUBPIXEL   a fresh write whose emitted integer position did not move
  HELD       no branch wrote this tick; the row carries an older position
  UNKNOWN    no provenance is available for the slot (never dropped)
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

POSITION_SOURCES = frozenset(
    {"DETECTION", "PREDICTION", "HELD", "CLAMP", "SUBPIXEL", "UNKNOWN"}
)

_KEEP_TICKS = 300      # mirrors the producer's own position-history prune window
_MAX_STAMPS = 6000     # bounded like p.positions; a long game must not grow this
_SEEN_TICK = -1        # sentinel key marking "this slot has been stamped at least once"
_HELD_BRANCH = "src/tracking/advanced_tracker.py:carried"
_SUBPIXEL_BRANCH = "src/pipeline/unified_pipeline.py:subpixel_hold"


def event_id(timestamp, bbox):
    """Stable identifier of the detection a DETECTION row was matched to."""
    try:
        return "%d_%d_%d_%d_%d" % ((int(timestamp),) + tuple(int(v) for v in bbox[:4]))
    except (TypeError, ValueError, IndexError):
        return ""


def stamp(store, slot, timestamp, label, branch, matched_event=""):
    """Record the branch that wrote one (slot, tick) position."""
    if store is None:
        return
    if label not in POSITION_SOURCES:
        raise ValueError("unknown position_source: %s" % label)
    tick = int(timestamp)
    store[(int(slot), tick)] = (label, branch, matched_event)
    store[(int(slot), _SEEN_TICK)] = ("SEEN", "", "")
    if len(store) > _MAX_STAMPS:
        cutoff = tick - _KEEP_TICKS
        for key in [k for k in store if 0 <= k[1] < cutoff]:
            del store[key]


def drop(store, slot, timestamp):
    """Forget one stamp when its position row is removed (duplicate merge)."""
    if store is not None:
        store.pop((int(slot), int(timestamp)), None)


def note_attempt(store, timestamp):
    """Record ONE producer-evaluated attempt, before any row filtering.

    The run-end receipt is written from this set instead of from the pipeline's
    `predictions` buffer, which the 3000-frame VRAM flush clears: a run longer
    than that interval would otherwise lose evaluated tick ids from its own
    receipt.  A tick is recorded, never a row, so a tick that survives the gate
    and emits no player row is still in the receipt.
    """
    if store is not None:
        store.add(int(timestamp))


def label_for(store, slot, timestamp):
    """Return (label, branch, matched_event). Missing is HELD or UNKNOWN, never dropped."""
    if not store:
        return "UNKNOWN", "", ""
    hit = store.get((int(slot), int(timestamp)))
    if hit is not None:
        return hit
    if (int(slot), _SEEN_TICK) in store:
        return "HELD", _HELD_BRANCH, ""
    return "UNKNOWN", "", ""


def resolve_emitted(label, branch, prev_int, cur_int):
    """Upgrade a fresh write whose emitted integer position did not move to SUBPIXEL.

    This is the branch G368 could not separate: it pooled 0.584961 of held steps
    as CLAMP_OR_SUBPIXEL because no emitted field distinguished a clamp from a
    sub-pixel hold.  The clamp is stamped at its own guard; what is left here is
    the sub-pixel case.
    """
    if prev_int is not None and cur_int == prev_int and label in ("DETECTION", "PREDICTION"):
        return "SUBPIXEL", _SUBPIXEL_BRANCH
    return label, branch


_WEIGHT_DIGEST = None


def weight_digest():
    """Digest of the weight files on this route, computed once per process.

    G372 carry-over: the withdrawn overlay globbed a relative `data/models` path
    on every attempt, which is both wrong from the daemon's cwd and a per-attempt
    filesystem walk.  This resolves from the module and caches the result.
    """
    global _WEIGHT_DIGEST
    if _WEIGHT_DIGEST is None:
        try:
            root = Path(__file__).resolve().parents[3]
            found = sorted(list(root.glob("*.pt")) + list((root / "data" / "models").rglob("*.pt")))
            items = ["%s:%d" % (item.relative_to(root).as_posix(), item.stat().st_size)
                     for item in found]
            _WEIGHT_DIGEST = hashlib.sha256("|".join(items).encode("ascii")).hexdigest() \
                if items else ""
        except Exception:
            _WEIGHT_DIGEST = ""
    return _WEIGHT_DIGEST


def bind_attempt(game_id, video, tracking_dir):
    """Stateless, idempotent per-attempt bind for the completion ledger.

    G372 carry-over, all four defects: the bind holds NO claim state and NO
    _PENDING queue, so a repeat attempt recomputes the same value and can never
    be blocked by another attempt; the weight digest is cached and absolute; and
    every failure is caught broadly and degrades to an empty bind, so a tracking
    attempt is never lost and never left un-claimable.
    """
    try:
        stat = os.stat(video)
        token = "%s:%s:%s:%s:%s" % (game_id, stat.st_dev, stat.st_ino,
                                    stat.st_mtime_ns, stat.st_size)
        return {"attempt_id": hashlib.sha256(token.encode("ascii")).hexdigest(),
                "receipt_path": os.path.join(str(tracking_dir), game_id,
                                             "evaluated_tick_receipt.json"),
                "weight_digest": weight_digest(), "bind_error": ""}
    except Exception as exc:
        return {"attempt_id": "", "receipt_path": "", "weight_digest": "",
                "bind_error": type(exc).__name__}
