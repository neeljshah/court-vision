"""predict_service.produce_sla_degrade -- per-sport SLA-degrade evaluator.

BE-R5-6 workstream: closes the ops/status-vs-doctor divergence for the producer
layer.  produce/status used to treat ANY existing snapshot file as ok regardless
of its age, and the scheduler's heartbeat.sports_run gap (a registered sport
silently dropped from rotation) was never surfaced in the status rollup.

TWO degrade rules applied here:

  Rule A -- snapshot age vs SLA:
    A sport whose latest.json is older than its SLA (seconds) scores ok=False.
    Delegates exclusively to normalize_service_severity from the SHARED
    ops_staleness_normalizer so produce/status and doctor/autonomy cannot
    disagree for the same snapshot row.

  Rule B -- scheduler sports_run gap:
    Every sport in the registered active set MUST appear in the heartbeat's
    sports_run list.  An absent sport degrades the rollup with a
    warning["scheduler_gap"] field.  This catches the Iter-2 P1 pattern where
    a sport silently falls out of the scheduler rotation.

PUBLIC API:
  SPORT_SLA_SEC: Dict[str, float]          -- per-sport SLA in seconds
  default_sla_for(sport) -> float          -- SLA lookup (falls back to 1800s)
  evaluate_sport_freshness(sport, age_sec, snapshot_status) -> dict
  evaluate_scheduler_gap(registered_sports, sports_run) -> dict

OUTPUT SHAPE (evaluate_sport_freshness):
  {
    "sport": str,
    "ok": bool,          # False when age>=SLA or snapshot_status != 'ok'
    "severity": str,     # 'ok' | 'degraded' | 'down'
    "honest_note": str,  # calibration not edge; no $
    "edge_claimed": False,
  }

OUTPUT SHAPE (evaluate_scheduler_gap):
  {
    "gap_detected": bool,
    "missing_sports": list[str],   # registered but absent from sports_run
    "warning": str | None,
    "honest_note": str,
    "edge_claimed": False,
  }

INVARIANTS: <=300 LOC; ASCII only; no I/O at import; NEVER raises; no $ field;
  reuses normalize_service_severity from ops_staleness_normalizer exclusively.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from predict_service.ops_staleness_normalizer import (
    DEGRADED,
    DOWN,
    HONEST_NOTE as _SHARED_NOTE,
    OK,
    normalize_service_severity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-sport SLA configuration (seconds). Mirrors scheduler cadences * 2 so a
# single missed cycle does not immediately degrade; a second-missed cycle does.
# ---------------------------------------------------------------------------
SPORT_SLA_SEC: Dict[str, float] = {
    "nba":        1200.0,   # scheduler: 600s cadence  x2
    "mlb":        1800.0,   # scheduler: 900s cadence  x2
    "soccer":     2400.0,   # scheduler: 1200s cadence x2
    "soccer_intl": 3600.0,  # scheduler: 1800s cadence x2
    "tennis":     1800.0,   # scheduler: 900s cadence  x2
}

_DEFAULT_SLA_SEC = 1800.0  # fallback for unknown sports

HONEST_NOTE = (
    "produce_sla_degrade: per-sport SLA evaluator. "
    "ok=False when snapshot age>=SLA OR scheduler omits a registered sport. "
    "Delegates to shared ops_staleness_normalizer (single truth source). "
    "Calibration not edge; no $ field."
)


def default_sla_for(sport: str) -> float:
    """Return the SLA in seconds for *sport* (falls back to _DEFAULT_SLA_SEC).

    NEVER raises.
    """
    try:
        return float(SPORT_SLA_SEC.get(str(sport).lower(), _DEFAULT_SLA_SEC))
    except Exception:  # noqa: BLE001
        return _DEFAULT_SLA_SEC


# ---------------------------------------------------------------------------
# Rule A: per-sport snapshot freshness vs SLA.
# ---------------------------------------------------------------------------

def evaluate_sport_freshness(
    sport: str,
    age_sec: Optional[float],
    snapshot_status: str = "ok",
    sla_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluate one sport's snapshot freshness against its SLA.  NEVER raises.

    Parameters
    ----------
    sport:
        Sport key (e.g. 'nba', 'mlb').
    age_sec:
        Seconds since the snapshot was generated.  None means never written ->
        treated as infinitely stale (DEGRADED).
    snapshot_status:
        The status field from the stored SnapshotEnvelope ('ok', 'unavailable',
        etc.).  A non-'ok' status degrades independently of age.
    sla_sec:
        Override the SLA; defaults to SPORT_SLA_SEC[sport] or _DEFAULT_SLA_SEC.

    Returns a dict with keys: sport, ok (bool), severity (str), honest_note,
    edge_claimed (False).
    """
    try:
        sport_key = str(sport).lower()
        sla = float(sla_sec) if sla_sec is not None else default_sla_for(sport_key)

        # Build a row in the shape normalize_service_severity expects.
        # HEARTBEAT mode: age_sec is the authoritative freshness signal.
        # We resolve 'fresh'/'stale' from age-vs-SLA ourselves before passing to
        # the kernel so the kernel's "fresh=None + critical -> DEGRADED" guard
        # (designed for services that never emit a freshness probe) does not
        # incorrectly degrade a sport whose age is known and within SLA.
        snap_live = snapshot_status == "ok"
        if not snap_live:
            # Unavailable/errored snapshot: always DOWN.
            fresh_val: Optional[str] = "down"
        elif age_sec is None:
            # Never written: treat as stale (no heartbeat yet).
            fresh_val = "stale"
        elif float(age_sec) >= sla:
            fresh_val = "stale"
        else:
            fresh_val = "fresh"

        row: Dict[str, Any] = {
            "critical": True,
            "live": snap_live,
            "fresh": fresh_val,
        }
        if age_sec is not None:
            row["age_sec"] = float(age_sec)

        severity = normalize_service_severity(row, sla_sec=sla, readiness_kind="HEARTBEAT")
        ok = severity == OK

        return {
            "sport": sport_key,
            "ok": ok,
            "severity": severity,
            "sla_sec": sla,
            "age_sec": age_sec,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001 -- never raises
        logger.warning("evaluate_sport_freshness(%s) failed: %s", sport, exc)
        return {
            "sport": str(sport),
            "ok": False,
            "severity": DEGRADED,
            "sla_sec": sla_sec,
            "age_sec": age_sec,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "_error": type(exc).__name__,
        }


# ---------------------------------------------------------------------------
# Rule B: scheduler sports_run gap detector.
# ---------------------------------------------------------------------------

def evaluate_scheduler_gap(
    registered_sports: List[str],
    sports_run: List[str],
) -> Dict[str, Any]:
    """Detect registered sports silently absent from the scheduler sports_run.

    Parameters
    ----------
    registered_sports:
        The canonical set of sports the predict service knows about
        (e.g. from registry.active_sports() or _KNOWN_SPORTS keys).
    sports_run:
        The heartbeat's sports_run list (sports the scheduler actually ran
        in its last cycle).

    Returns
    -------
    dict with keys:
      gap_detected (bool): True when any registered sport is absent.
      missing_sports (list[str]): the absent sports, sorted.
      warning (str | None): human-readable warning when gap_detected.
      honest_note (str)
      edge_claimed (False)

    NEVER raises.
    """
    try:
        reg = {str(s).lower() for s in (registered_sports or [])}
        ran = {str(s).lower() for s in (sports_run or [])}
        missing = sorted(reg - ran)
        gap = len(missing) > 0
        warning: Optional[str] = None
        if gap:
            warning = (
                "scheduler_gap: %d registered sport(s) absent from heartbeat "
                "sports_run -- %s. Producer may have silently dropped them." %
                (len(missing), ", ".join(missing))
            )
            logger.warning(warning)
        return {
            "gap_detected": gap,
            "missing_sports": missing,
            "warning": warning,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001 -- never raises
        logger.warning("evaluate_scheduler_gap failed: %s", exc)
        return {
            "gap_detected": True,
            "missing_sports": [],
            "warning": "evaluate_scheduler_gap failed: %s" % type(exc).__name__,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "_error": type(exc).__name__,
        }


__all__ = [
    "SPORT_SLA_SEC",
    "HONEST_NOTE",
    "default_sla_for",
    "evaluate_sport_freshness",
    "evaluate_scheduler_gap",
]
