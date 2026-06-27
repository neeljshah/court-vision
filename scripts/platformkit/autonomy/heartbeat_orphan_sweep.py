"""scripts.platformkit.autonomy.heartbeat_orphan_sweep -- prune stale ORPHAN stems.

The orphan_hb_check (IOP-06) SURFACES heartbeat .txt stems under
data/cache/daemon_heartbeats/ that no supervised spec owns. Those leftover beats
from old/dead daemons (scrapers, prior supervisors, retired m14-m18) never go
away on their own, so the orphan note -- and the cosmetic "degraded" it implies --
persists forever even when every CURRENT service is healthy.

This module PRUNES such files, but ONLY when ALL of these are true (fail-CLOSED):
  (a) the stem is NOT owned by any current manifest ProcSpec NOR a known live
      self-beating daemon (m5_autonomy_monitor / m9_supervisor); AND
  (b) the file is STALE -- its mtime is older than ``stale_sec`` (default 2h); AND
  (c) it is a plain ``*.txt`` directly inside daemon_heartbeats/.

NEVER deleted: a stem owned by a live daemon (manifest or known-self-beat); a FRESH
unowned stem (mtime within the window -- it may be a brand-new daemon not yet wired
into the manifest, so we keep it and let the orphan note flag it instead of racing
its owner); anything outside data/cache/daemon_heartbeats/; anything that is not a
regular ``.txt`` file. data/registry/ is NEVER touched.

If the manifest cannot be loaded the owned set is UNKNOWN -> the sweep prunes
NOTHING (it must never delete a stem it cannot prove is unowned). Idempotent: a
second run with nothing stale-and-unowned is a no-op. dry_run=True reports the
plan without deleting. NEVER raises. ASCII; stdlib + repo-internal; <=300 LOC.
Calibration not edge; no $ field.
"""
from __future__ import annotations

import os
import pathlib
import time
from typing import Any, Dict, List, Optional

from scripts.platformkit.autonomy.orphan_hb_check import (
    _KNOWN_AUTONOMY_STEMS,
    _manifest_owned_stems,
)

_REPO = pathlib.Path(__file__).resolve().parents[3]
_HB_DIR = _REPO / "data" / "cache" / "daemon_heartbeats"

# Default staleness threshold: a stem must be older than this (and unowned) to be
# pruned. 2h comfortably exceeds every CURRENT daemon's freshness window (the
# widest is m7_ingame_refresh at 7800s ~= 2.2h -> we floor a bit higher so even a
# slow-but-alive owned daemon could never be reaped if it somehow slipped the
# owned set). Unowned + stale-past-this = clearly a dead leftover.
DEFAULT_STALE_SEC = 2.0 * 3600.0


def _age_sec(path: pathlib.Path, now: float) -> Optional[float]:
    """Age (seconds) from the file mtime, or None if it cannot be stat'd."""
    try:
        return now - os.path.getmtime(str(path))
    except OSError:
        return None


def _candidate_files(hb_dir: pathlib.Path) -> List[pathlib.Path]:
    """Regular ``*.txt`` files directly under *hb_dir*. [] on any error.

    Guards: only *.txt, only regular files (never dirs/symlinks-to-dirs), only the
    immediate directory (glob, not rglob) so nothing nested is ever swept.
    """
    try:
        if not hb_dir.is_dir():
            return []
        out: List[pathlib.Path] = []
        for p in hb_dir.glob("*.txt"):
            try:
                if p.is_file():
                    out.append(p)
            except OSError:
                continue
        return sorted(out)
    except Exception:  # noqa: BLE001
        return []


def sweep(
    *,
    hb_dir: Optional[pathlib.Path] = None,
    stale_sec: float = DEFAULT_STALE_SEC,
    now: Optional[float] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Prune stale, manifest-unowned heartbeat stems. Never raises.

    Parameters
    ----------
    hb_dir :
        Directory to sweep (default: data/cache/daemon_heartbeats/). Injected in
        tests to point at a temp dir.
    stale_sec :
        Minimum age (seconds) before an unowned stem may be pruned. A file younger
        than this is KEPT even if unowned (it may be a not-yet-wired new daemon).
    now :
        Epoch clock (default time.time()). Injected for deterministic tests.
    dry_run :
        When True, compute the plan but delete nothing (``would_prune`` populated,
        ``pruned`` empty).

    Returns
    -------
    dict with keys:
        swept_at        -- epoch float.
        hb_dir          -- directory swept (str).
        manifest_ok     -- bool; False -> owned set UNKNOWN -> nothing pruned.
        stale_sec       -- the threshold used.
        owned_stems     -- the owned set (manifest + known self-beats), sorted.
        kept_owned      -- on-disk stems skipped because owned.
        kept_fresh      -- unowned stems skipped because still fresh (with ages).
        would_prune     -- stale+unowned stems eligible for pruning.
        pruned          -- stems actually deleted (empty when dry_run).
        errors          -- stems whose unlink raised (kept; surfaced honestly).
        notes           -- plain-text notes.
        honest_note     -- disclaimer.
    """
    t = float(now) if now is not None else time.time()
    scan_dir = hb_dir if hb_dir is not None else _HB_DIR
    notes: List[str] = []

    manifest_stems = _manifest_owned_stems()
    manifest_ok = manifest_stems is not None
    if not manifest_ok:
        # Owned set UNKNOWN -> we cannot PROVE any stem is unowned -> prune nothing.
        notes.append(
            "heartbeat_orphan_sweep: manifest import failed; owned set UNKNOWN -> "
            "pruning NOTHING (fail-closed; never delete an unprovable stem)"
        )
        return {
            "swept_at": t, "hb_dir": str(scan_dir), "manifest_ok": False,
            "stale_sec": float(stale_sec), "owned_stems": [],
            "kept_owned": [], "kept_fresh": [], "would_prune": [],
            "pruned": [], "errors": [], "notes": notes,
            "honest_note": _HONEST_NOTE,
        }

    owned = set(manifest_stems) | set(_KNOWN_AUTONOMY_STEMS)
    owned_sorted = sorted(owned)

    kept_owned: List[str] = []
    kept_fresh: List[Dict[str, Any]] = []
    would_prune: List[str] = []
    pruned: List[str] = []
    errors: List[Dict[str, Any]] = []

    for path in _candidate_files(scan_dir):
        stem = path.stem
        if stem in owned:
            kept_owned.append(stem)
            continue
        age = _age_sec(path, t)
        if age is None:
            # Cannot determine age -> conservatively KEEP (never delete blind).
            kept_fresh.append({"stem": stem, "age_sec": None})
            continue
        if age <= float(stale_sec):
            kept_fresh.append({"stem": stem, "age_sec": round(age, 1)})
            continue
        # Unowned AND stale-past-threshold -> eligible.
        would_prune.append(stem)
        if dry_run:
            continue
        try:
            path.unlink()
            pruned.append(stem)
        except Exception as exc:  # noqa: BLE001 -- one bad unlink must not abort
            errors.append({"stem": stem, "error": str(exc)[:160]})

    if would_prune:
        verb = "would prune" if dry_run else "pruned"
        notes.append(
            "heartbeat_orphan_sweep: %s %d stale unowned stem(s): %s"
            % (verb, len(would_prune), ", ".join(sorted(would_prune)))
        )
    else:
        notes.append("heartbeat_orphan_sweep: no stale unowned stems to prune")
    if kept_fresh:
        notes.append(
            "heartbeat_orphan_sweep: kept %d unowned-but-FRESH stem(s) "
            "(may be a not-yet-wired daemon -- flagged, not deleted)"
            % len(kept_fresh)
        )

    return {
        "swept_at": t, "hb_dir": str(scan_dir), "manifest_ok": True,
        "stale_sec": float(stale_sec), "owned_stems": owned_sorted,
        "kept_owned": sorted(kept_owned), "kept_fresh": kept_fresh,
        "would_prune": sorted(would_prune), "pruned": sorted(pruned),
        "errors": errors, "notes": notes, "honest_note": _HONEST_NOTE,
    }


_HONEST_NOTE = (
    "heartbeat_orphan_sweep prunes ONLY stale (mtime older than stale_sec) AND "
    "manifest-unowned daemon_heartbeats/*.txt stems; a live or fresh stem is never "
    "deleted; data/registry/ is never touched. Calibration not edge; no $ field."
)


def _main() -> int:  # pragma: no cover -- thin CLI wrapper
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Prune stale, manifest-unowned heartbeat stems under "
                    "data/cache/daemon_heartbeats/. Fail-closed + idempotent."
    )
    p.add_argument("--hb-dir", default=str(_HB_DIR),
                   help="Heartbeat directory to sweep (default: %(default)s)")
    p.add_argument("--stale-sec", type=float, default=DEFAULT_STALE_SEC,
                   help="Min age (s) before an unowned stem may be pruned.")
    p.add_argument("--dry-run", action="store_true",
                   help="Report the plan without deleting anything.")
    a = p.parse_args()
    doc = sweep(hb_dir=pathlib.Path(a.hb_dir), stale_sec=a.stale_sec,
                dry_run=a.dry_run)
    if not doc["manifest_ok"]:
        print("heartbeat_orphan_sweep: manifest UNKNOWN -> pruned nothing", flush=True)
        return 2
    target = doc["would_prune"] if a.dry_run else doc["pruned"]
    print("heartbeat_orphan_sweep: %s %d stale unowned stem(s)%s"
          % ("would prune" if a.dry_run else "pruned", len(target),
             (" -> " + ", ".join(target)) if target else ""), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["sweep", "DEFAULT_STALE_SEC"]
