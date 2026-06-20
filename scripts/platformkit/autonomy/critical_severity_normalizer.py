"""scripts.platformkit.autonomy.critical_severity_normalizer -- status-severity
normalizer for CRITICAL services.

ROOT CAUSE (QA iters 27/165/283/307):
  ops/status and ops/doctor disagree on CRITICAL services (m1_producer, m1_api_paper)
  when live=None and fresh=null (port-probed servers).  ops.health_aggregator._row_severity
  returns OK for any row where live is not False, breaker != OPEN, and fresh is not
  'stale'/'down'.  This means a CRITICAL service that has never emitted a freshness
  reading (fresh=null) can silently appear green on /api/ops/status while /api/ops/doctor
  (which applies its own null-coercion) shows DEGRADED.

ROOT CAUSE #2 (REVIEW iter4 P1 -- stale-age gap):
  m7_ingame_refresh (and any heartbeat-only service) reads live=True at 44min stale
  because the live boolean comes from heartbeat-file PRESENCE, not heartbeat RECENCY.
  A heartbeat file written 44 minutes ago keeps the service live=True even though the
  daemon is effectively dead.  The health_aggregator never sees age_sec vs fresh_sec,
  so the overall status flips back to 'ok' on a dead-but-present feed.

FIX -- degrade-only normalizer (two rules):

  RULE 1 (critical-null-fresh):
    IF   the service is marked critical=True
    AND  fresh is None (not measured)
    AND  the row would otherwise be OK
    THEN demote to DEGRADED.

  RULE 2 (stale-age coercion -- NEW, closes iter4 P1):
    IF   live is True (or truthy)
    AND  age_sec is present on the row
    AND  age_sec > fresh_sec  (falling back to _DEFAULT_MAX_STALE_SEC when
         fresh_sec is absent from the row)
    THEN coerce live off (treat as NOT live) and demote to DEGRADED.

  Degrade-only: once a row is DEGRADED or DOWN, neither rule ever lifts it to OK.
  The stale-age rule applies regardless of critical flag because a stale heartbeat
  is a lie about liveness on ANY service -- not only critical ones.

GUARANTEE CONTRACT (degrade-only -- stale-never-green):
  * live=True with age_sec > fresh_sec  -> live coerced False + severity >= DEGRADED.
  * live=True with age_sec <= fresh_sec -> unchanged (row is genuinely fresh).
  * Row missing fresh_sec               -> falls back to _DEFAULT_MAX_STALE_SEC (300s)
    and still degrades on gross staleness.
  * Degrade-only: never lifts a stale row to OK.
  * A critical row with live=None/fresh=null -> DEGRADED (never OK) [Rule 1].
  * A critical row with live=False          -> DOWN (already forced by _row_severity).
  * A critical row with fresh='fresh'       -> OK (healthy, not degraded).
  * A non-critical row with fresh=null      -> unchanged [Rule 1 exempt; Rule 2 still
    applies if age_sec present and stale].
  * Any row already at DEGRADED or DOWN     -> unchanged (monotone-down only, never
    upgrades).
  * normalize_services(rows) applies normalize_row to every row and returns a new list
    (never mutates the input).

READ-ONLY: never mutates heartbeat files, spec files, or the ops/ source.
INVARIANTS: <=300 LOC; ASCII only; stdlib only; no I/O at import; NEVER raises;
calibration not edge; no $ field; stale_never_green = True (passive).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_RANK: Dict[str, int] = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK: Dict[int, str] = {0: OK, 1: DEGRADED, 2: DOWN}

# Safe fallback: 5 minutes, matching ops_consensus_reconciler DEFAULT_SLA_SEC.
# A row with no explicit fresh_sec still degrades at this threshold.
_DEFAULT_MAX_STALE_SEC: float = 300.0

HONEST_NOTE = (
    "critical_severity_normalizer: degrade-only; stale-never-green. "
    "Rule 1: CRITICAL service with live=None/fresh=null reads DEGRADED (not OK). "
    "Rule 2: any service with live=True and age_sec > fresh_sec (or >300s default) "
    "has live coerced off and severity forced to >= DEGRADED -- a stale heartbeat "
    "can never read running. "
    "Non-critical port-probed rows without age_sec are unchanged by Rule 1. "
    "Calibration not edge; no $ field."
)


# ---------------------------------------------------------------------------
# Internal helpers -- NEVER raise.
# ---------------------------------------------------------------------------

def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two severities.  Monotone-DOWN -- never upgrades.

    Unknown labels are treated as DEGRADED (conservative, never green).
    """
    cur = _RANK.get(current, _RANK[DEGRADED])
    cand = _RANK.get(candidate, _RANK[DEGRADED])
    return _BY_RANK[max(cur, cand)]


def _base_severity(row: Dict[str, Any]) -> str:
    """Derive the base severity from a services[] row (mirrors health_aggregator).

    DOWN     -- live is False, breaker is OPEN, or fresh='down'.
    DEGRADED -- fresh='stale'.
    OK       -- otherwise (including fresh=None, live=None for port-probed rows).

    This mirrors ops.health_aggregator._row_severity so the normalizer starts
    from the SAME baseline; it then applies the CRITICAL null-fresh rule on top.
    """
    if row.get("live") is False:
        return DOWN
    if row.get("breaker") == "OPEN":
        return DOWN
    fresh = row.get("fresh")
    if fresh == "down":
        return DOWN
    if fresh == "stale":
        return DEGRADED
    return OK


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _stale_age_coerce(row: Dict[str, Any]) -> bool:
    """Return True if the row carries a stale age (age_sec > fresh_sec).

    Used by Rule 2: when live=True but the heartbeat is older than the freshness
    window the service is lying about liveness -- the heartbeat file exists but the
    daemon has not written a new one in time.  This function does NOT mutate the row.

    Returns False (safe/no-coercion) on any type error or missing fields.
    """
    try:
        age_raw = row.get("age_sec") or row.get("age_seconds")
        if age_raw is None:
            return False
        age = float(age_raw)
        if age < 0:
            # Negative age (clock skew / future stamp) -> treat as stale to prevent
            # a constant-future heartbeat from reading live=True forever.
            return True
        # Prefer the row's own fresh_sec; fall back to the safe default.
        fs_raw = row.get("fresh_sec") or row.get("freshness_sec")
        fresh_sec = float(fs_raw) if fs_raw is not None else _DEFAULT_MAX_STALE_SEC
        return age > fresh_sec
    except Exception:  # noqa: BLE001
        return False


def normalize_row(row: Dict[str, Any]) -> str:
    """Return the normalised severity for one services[] row.  NEVER raises.

    Applies two degrade-only rules on top of the base health_aggregator logic:

    RULE 1 (critical-null-fresh):
      IF   critical=True  AND  fresh is None  AND  base severity == OK
      THEN return DEGRADED.
      A CRITICAL service with unmeasured freshness is UNKNOWN, not healthy.

    RULE 2 (stale-age coercion):
      IF   live is True (or truthy)
      AND  age_sec > fresh_sec  (or > _DEFAULT_MAX_STALE_SEC when fresh_sec absent)
      THEN coerce live to False, demote severity to >= DEGRADED.
      A stale heartbeat can NEVER read 'running' (live=True) -- this closes the
      heartbeat-presence-vs-recency gap (iter4 P1: m7_ingame_refresh 44min stale).

    Non-critical rows without age_sec are unchanged by Rule 1; Rule 2 applies to
    ALL services when age_sec is present and stale.
    Any row already at DEGRADED/DOWN is left at that severity (monotone-down).

    Parameters
    ----------
    row :
        A services[] dict from ops.health_aggregator.aggregate() or any compatible
        status document.  The dict is never mutated.

    Returns
    -------
    str
        One of 'ok', 'degraded', 'down'.
    """
    try:
        # Rule 2 -- stale-age coercion: if age_sec > fresh_sec, treat live as False.
        # We compute this BEFORE _base_severity so the base computation sees the
        # coerced liveness state.  We do NOT mutate the original row; instead we
        # shadow the live field in a local overlay.
        if bool(row.get("live")) and _stale_age_coerce(row):
            # Build a shallow overlay that forces live=False for _base_severity.
            row = dict(row)
            row["live"] = False  # local shadow only; original never mutated

        base = _base_severity(row)

        # Carry forward any pre-existing severity annotation (monotone-down).
        existing = str(row.get("severity") or "").lower()
        if existing in _RANK:
            base = _degrade(base, existing)

        # Rule 1 -- critical-null-fresh: unknown freshness on a critical service is
        # DEGRADED.  We apply this AFTER carrying the existing severity so a row
        # already at DEGRADED/DOWN is never accidentally upgraded.
        if (
            base == OK
            and bool(row.get("critical"))
            and row.get("fresh") is None
        ):
            base = DEGRADED

        return base
    except Exception:  # noqa: BLE001 -- must never crash callers
        return DEGRADED


def normalize_services(
    rows: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Apply normalize_row to every row in *rows*.  NEVER raises.

    Returns a NEW list of dicts; each dict is a shallow copy of the original
    with 'severity' updated to the normalised value.  The input list and its
    dicts are never mutated (degrade-only guarantee is per-row and additive).

    An empty or None input list returns [] (never errors).
    """
    try:
        out: List[Dict[str, Any]] = []
        for row in (rows or []):
            if not isinstance(row, dict):
                # Non-dict items are dropped (consistent with other composers).
                continue
            sev = normalize_row(row)
            item = dict(row)
            item["severity"] = sev
            out.append(item)
        return out
    except Exception:  # noqa: BLE001
        return []


def worst_severity(
    rows: Optional[List[Dict[str, Any]]],
) -> str:
    """Return the WORST normalised severity across all rows.  NEVER raises.

    An empty or None list returns DEGRADED (absent data is never asserted green).
    """
    try:
        result = OK
        for row in (rows or []):
            if not isinstance(row, dict):
                result = _degrade(result, DEGRADED)
                continue
            result = _degrade(result, normalize_row(row))
        if not (rows or []):
            # No rows: unknown state -- conservative DEGRADED.
            return DEGRADED
        return result
    except Exception:  # noqa: BLE001
        return DEGRADED


__all__ = [
    "OK", "DEGRADED", "DOWN",
    "_DEFAULT_MAX_STALE_SEC",
    "HONEST_NOTE",
    "normalize_row",
    "normalize_services",
    "worst_severity",
]
