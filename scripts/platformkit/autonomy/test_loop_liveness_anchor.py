"""Per-file test: status_composer loop-liveness anchors on m4_selfimprove.

Acceptance criteria:
  (A) When m4_selfimprove is present + OK in services[], the loop block reads live
      (liveness_missing=False, liveness_severity=ok) -- a genuinely-alive loop is
      NOT degraded for the cosmetic name-mismatch reason.
  (B) When m4_selfimprove is present but DEGRADED (dead/hung loop), the loop block
      degrades (liveness_severity != ok) -- a real failure is NOT masked.
  (C) When NO loop service is present at all, liveness_missing=True (degraded) --
      absence is still honestly degraded (we never assume ok).
  (D) overall is the WORST of services + loop liveness (monotone-down preserved):
      a dead m4 still drives overall to degraded.

Run (per-file only -- never full pytest):
    cd /c/Users/neelj/nba-ai-system && \
      python -m pytest scripts/platformkit/autonomy/test_loop_liveness_anchor.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.autonomy import status_composer as sc


def _health_doc(overall: str, services):
    return {"overall": overall, "services": services, "notes": [],
            "generated_at": "2026-06-21T00:00:00Z"}


def _svc(name, *, live=True, fresh="fresh", fresh_sec=300.0, age_sec=1.0,
         critical=False):
    return {"name": name, "live": live, "fresh": fresh, "fresh_sec": fresh_sec,
            "age_sec": age_sec, "critical": critical, "breaker": None,
            "last_seen": "2026-06-21T00:00:00Z", "port": None, "reason": None}


def _compose_with(services, overall="ok"):
    """Compose using a stubbed health_aggregator.aggregate."""
    def _fake_aggregate(**_kw):
        return _health_doc(overall, services)
    orig = sc._health.aggregate
    sc._health.aggregate = _fake_aggregate  # type: ignore[assignment]
    try:
        return sc.compose(now=1_750_000_000.0)
    finally:
        sc._health.aggregate = orig  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# (A) alive m4 -> loop live
# --------------------------------------------------------------------------- #

def test_alive_m4_loop_reads_live():
    doc = _compose_with([_svc("m1_producer"), _svc("m4_selfimprove", live=True)])
    loop = doc["loop"]
    assert loop["liveness_missing"] is False, (
        "m4_selfimprove present+ok must make the loop NOT missing")
    assert loop["liveness_severity"] == sc.OK
    assert doc["overall"] == sc.OK


# --------------------------------------------------------------------------- #
# (B) dead/hung m4 -> loop degraded (real failure not masked)
# --------------------------------------------------------------------------- #

def test_dead_m4_loop_degrades():
    # A stale/absent heartbeat shows as live=False / fresh="stale" in the row;
    # health_aggregator._row_severity (inherited by the composer) degrades it.
    dead = _svc("m4_selfimprove", live=False, fresh="stale", age_sec=99999.0)
    doc = _compose_with([_svc("m1_producer"), dead])
    loop = doc["loop"]
    assert loop["liveness_missing"] is False
    assert loop["liveness_severity"] != sc.OK, (
        "a dead m4 loop must degrade liveness -- real failure not masked")
    assert doc["overall"] != sc.OK, "overall must degrade when the loop is dead"


# --------------------------------------------------------------------------- #
# (C) no loop service at all -> still missing/degraded
# --------------------------------------------------------------------------- #

def test_no_loop_service_still_degraded():
    doc = _compose_with([_svc("m1_producer"), _svc("m1_api_paper")])
    loop = doc["loop"]
    assert loop["liveness_missing"] is True
    assert loop["liveness_severity"] != sc.OK
    assert doc["overall"] != sc.OK
