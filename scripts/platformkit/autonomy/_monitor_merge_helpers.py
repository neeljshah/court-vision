"""scripts.platformkit.autonomy._monitor_merge_helpers -- degrade-merge steps.

Private helpers used by autonomy_monitor_runner.tick(): the three IOP wires that
run after status_composer.compose() and before the atomic write.

  _apply_reaper_merge  -- IOP-08: degrade services[] from reaper snapshot
  _apply_m5fix         -- IOP-07: degrade m5 row when own heartbeat is stale/absent
  _apply_orphan_surface -- IOP-06: surface orphan stems into doc["notes"]

All three functions:
  * Accept and return a dict (shallow copy on mutation).
  * Never raise -- any error leaves the doc unchanged.
  * Never upgrade a severity to a better value (monotone-down invariant).
  * Are READ-ONLY regarding heartbeats, flags, and real-money fields.

SAFETY / INVARIANTS: MEASUREMENT-ONLY. Calibration not edge; no $ field. ASCII.
"""
from __future__ import annotations

import logging
import pathlib
from typing import Any, Dict, List, Optional

from scripts.platformkit.autonomy.reaper_status_bridge import (
    load_reaper_status,
    merge_reaper_into_services,
)

logger = logging.getLogger("autonomy_monitor_runner")

DEGRADED = "degraded"

_RANK: Dict[str, int] = {"ok": 0, "degraded": 1, "down": 2}
_BY_RANK: Dict[int, str] = {0: "ok", 1: "degraded", 2: "down"}


def _degrade_str(a: str, b: str) -> str:
    """Return the worse of two severity strings."""
    ra = _RANK.get(a, _RANK[DEGRADED])
    rb = _RANK.get(b, _RANK[DEGRADED])
    return _BY_RANK[max(ra, rb)]


def _apply_reaper_merge(
    doc: Dict[str, Any],
    *,
    reaper_path: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """IOP-08: degrade-only merge of reaper verdicts into doc["services"]. Never raises.

    Loads the reaper snapshot from *reaper_path* (defaults to the bridge default).
    Missing file -> empty rows -> services unchanged (unknown, never forced green).
    STALE_HUNG / NO_HEARTBEAT rows degrade the matching service; HEALTHY rows and
    unmatched rows are left alone. The overall severity is re-derived as the worst
    of the existing overall and the degraded services.

    Returns a SHALLOW COPY of *doc* with services and overall potentially degraded.
    Never upgrades anything to "ok".
    """
    try:
        reaper_rows = load_reaper_status(path=reaper_path)
        if not reaper_rows:
            return doc
        services: List[Dict[str, Any]] = doc.get("services") or []
        merged = merge_reaper_into_services(services, reaper_rows)
        existing_overall = str(doc.get("overall", DEGRADED))
        new_overall = existing_overall
        for svc in merged:
            if isinstance(svc, dict):
                new_overall = _degrade_str(new_overall, str(svc.get("severity", DEGRADED)))
        out = dict(doc)
        out["services"] = merged
        out["overall"] = new_overall
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("autonomy_monitor reaper merge raised: %s", exc)
        return doc


def _apply_m5fix(
    doc: Dict[str, Any],
    *,
    now: float,
    m5_hb_path: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """IOP-07: degrade m5 row when its own heartbeat is stale/null. Never raises."""
    try:
        from scripts.platformkit.autonomy.status_composer_m5fix import patch_m5_row
        kwargs: Dict[str, Any] = {"now": now}
        if m5_hb_path is not None:
            kwargs["hb_path"] = m5_hb_path
        return patch_m5_row(doc, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.debug("autonomy_monitor m5fix raised: %s", exc)
        return doc


def _apply_orphan_sweep(
    doc: Dict[str, Any],
    *,
    hb_dir: Optional[pathlib.Path] = None,
    now: float,
) -> Dict[str, Any]:
    """Prune STALE + manifest-unowned heartbeat stems (self-healing). Never raises.

    Runs BEFORE _apply_orphan_surface so the surfaced orphan note reflects the
    post-sweep reality (a stale dead-daemon leftover is reaped, not nagged about
    forever). The sweep is fail-CLOSED + conservative: it deletes ONLY *.txt stems
    that are unowned AND older than its stale threshold; a live or fresh stem is
    never touched, and an unloadable manifest prunes nothing (see
    heartbeat_orphan_sweep). It does NOT mutate *doc* -- pruning a dead file does
    not change any severity -- so the doc is returned unchanged. READ-ONLY w.r.t.
    the status envelope; the only side effect is removing clearly-dead cache files.
    """
    try:
        from scripts.platformkit.autonomy.heartbeat_orphan_sweep import sweep
        kwargs: Dict[str, Any] = {"now": now}
        if hb_dir is not None:
            kwargs["hb_dir"] = hb_dir
        sweep(**kwargs)
    except Exception as exc:  # noqa: BLE001 -- sweep must never sink the tick
        logger.debug("autonomy_monitor orphan sweep raised: %s", exc)
    return doc


def _apply_orphan_surface(
    doc: Dict[str, Any],
    *,
    hb_dir: Optional[pathlib.Path] = None,
    orphan_report_path: Optional[pathlib.Path] = None,
    now: float,
) -> Dict[str, Any]:
    """IOP-06: surface orphan stems into doc["notes"]. READ-ONLY; never raises."""
    try:
        from scripts.platformkit.autonomy.orphan_hb_check import run_check
        kwargs: Dict[str, Any] = {"now": now}
        if hb_dir is not None:
            kwargs["hb_dir"] = hb_dir
        if orphan_report_path is not None:
            kwargs["report_path"] = orphan_report_path
        orphan_doc = run_check(**kwargs)
        orphan_stems = orphan_doc.get("orphan_stems")
        if not orphan_stems:
            return doc
        out = dict(doc)
        notes: List[str] = list(out.get("notes") or [])
        notes.append(
            "orphans: %d unowned heartbeat stem(s) found in daemon_heartbeats/"
            % len(orphan_stems)
        )
        for stem in orphan_stems:
            notes.append("  orphan_stem: %s" % stem)
        out["notes"] = notes
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("autonomy_monitor orphan surface raised: %s", exc)
        return doc


__all__ = ["_apply_reaper_merge", "_apply_m5fix", "_apply_orphan_sweep",
           "_apply_orphan_surface"]
