"""test_heartbeat_sla_matrix.py -- per-file tests: acceptance, stale-never-green, ordering.

Split from the original 381-line file to satisfy <=300 LOC/file rail (BE8-6).
Companion: test_heartbeat_sla_matrix_io.py covers report writing, schema, never-raises.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/observability/test_heartbeat_sla_matrix.py -q

Acceptance criteria:
  * Two heartbeat files (one at 50% of SLA, one at 120% of SLA) ->
    the 120% row is marked stale=True and sorted first (worst-first).
  * Absent heartbeat file -> stale=True (stale-never-green), never ok.
  * overall="stale" if any row is stale; overall="ok" only when all rows ok.
  * No process started; no $ field; no flag flip; no data/registry/ write.
  * Never raises on any input.

ASCII only; <=300 LOC.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.observability.heartbeat_sla_matrix import (
    compute_sla_matrix,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _fixed_clock(epoch: float):
    """Return a clock callable that always returns *epoch*."""
    return lambda: epoch


def _write_hb(path: Path, age_sec: float, now: float) -> Path:
    """Write a plain ISO-8601 heartbeat at stamp = now - age_sec."""
    stamp = now - age_sec
    dt = datetime.fromtimestamp(stamp, tz=timezone.utc)
    path.write_text(dt.strftime("%Y-%m-%dT%H:%M:%SZ"), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Primary acceptance test: 50% vs 120% of SLA
# ---------------------------------------------------------------------------

class TestPrimaryAcceptance:
    """Key acceptance: 50% of SLA fresh, 120% of SLA stale, stale sorted first."""

    def test_120pct_stale_sorted_first(self, tmp_path):
        """The 120%-of-SLA row must be marked stale=True and appear first."""
        now = time.time()
        sla = 300.0

        # fresh: 50% of SLA (age=150)
        p_fresh = tmp_path / "svc_fresh.txt"
        _write_hb(p_fresh, age_sec=150.0, now=now)

        # stale: 120% of SLA (age=360)
        p_stale = tmp_path / "svc_stale.txt"
        _write_hb(p_stale, age_sec=360.0, now=now)

        specs = [
            # Deliberately list fresh first -- the sort must reorder to stale-first.
            {"name": "svc_fresh", "sla_sec": sla, "hb_path": str(p_fresh)},
            {"name": "svc_stale", "sla_sec": sla, "hb_path": str(p_stale)},
        ]
        result = compute_sla_matrix(
            specs, clock=_fixed_clock(now), write_report=False
        )

        # Stale row is first
        assert result["rows"][0]["name"] == "svc_stale"
        assert result["rows"][0]["stale"] is True
        assert result["rows"][1]["name"] == "svc_fresh"
        assert result["rows"][1]["stale"] is False

        # Overall must be stale because one row is stale
        assert result["overall"] == "stale"
        assert result["n_stale"] == 1
        assert result["n_ok"] == 1
        assert "svc_stale" in result["stale_names"]

    def test_pct_of_sla_values(self, tmp_path):
        """pct_of_sla must match age/sla * 100."""
        now = time.time()
        sla = 300.0

        p_fresh = tmp_path / "fr.txt"
        _write_hb(p_fresh, age_sec=150.0, now=now)
        p_stale = tmp_path / "st.txt"
        _write_hb(p_stale, age_sec=360.0, now=now)

        specs = [
            {"name": "fr", "sla_sec": sla, "hb_path": str(p_fresh)},
            {"name": "st", "sla_sec": sla, "hb_path": str(p_stale)},
        ]
        result = compute_sla_matrix(
            specs, clock=_fixed_clock(now), write_report=False
        )
        rows = {r["name"]: r for r in result["rows"]}

        assert rows["fr"]["pct_of_sla"] == pytest.approx(50.0, abs=2.0)
        assert rows["st"]["pct_of_sla"] == pytest.approx(120.0, abs=2.0)


# ---------------------------------------------------------------------------
# Stale-never-green: absent heartbeat
# ---------------------------------------------------------------------------

class TestStaleNeverGreen:
    """Absent or unreadable heartbeat must be stale, never ok."""

    def test_absent_file_is_stale(self, tmp_path):
        now = time.time()
        p = tmp_path / "ghost.txt"  # NOT written
        specs = [{"name": "ghost", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        row = result["rows"][0]
        assert row["stale"] is True
        assert row["age_sec"] is None
        assert row["pct_of_sla"] is None
        assert result["overall"] == "stale"

    def test_empty_file_is_stale(self, tmp_path):
        now = time.time()
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        specs = [{"name": "d_empty", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        assert result["rows"][0]["stale"] is True

    def test_corrupt_file_is_stale(self, tmp_path):
        now = time.time()
        p = tmp_path / "corrupt.txt"
        p.write_bytes(b"\xff\xfe bad bytes")
        specs = [{"name": "d_corrupt", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        assert result["rows"][0]["stale"] is True

    def test_overall_stale_if_any_stale(self, tmp_path):
        now = time.time()
        sla = 300.0
        # one fresh, one absent
        p_fresh = tmp_path / "ok.txt"
        _write_hb(p_fresh, age_sec=50.0, now=now)
        p_ghost = tmp_path / "ghost.txt"
        specs = [
            {"name": "ok", "sla_sec": sla, "hb_path": str(p_fresh)},
            {"name": "ghost", "sla_sec": sla, "hb_path": str(p_ghost)},
        ]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        assert result["overall"] == "stale"

    def test_overall_ok_only_when_all_fresh(self, tmp_path):
        now = time.time()
        sla = 300.0
        specs = []
        for i in range(3):
            p = tmp_path / ("d%d.txt" % i)
            _write_hb(p, age_sec=50.0, now=now)
            specs.append({"name": "d%d" % i, "sla_sec": sla, "hb_path": str(p)})
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        assert result["overall"] == "ok"
        assert result["n_stale"] == 0


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

class TestOrdering:
    """Worst-first ordering: stale rows before ok rows; within stale,
    highest pct_of_sla sorts first."""

    def test_stale_before_ok(self, tmp_path):
        now = time.time()
        sla = 300.0
        data = [("ok_d", 50.0), ("stale_d", 600.0)]
        specs = []
        for name, age in data:
            p = tmp_path / ("%s.txt" % name)
            _write_hb(p, age_sec=age, now=now)
            specs.append({"name": name, "sla_sec": sla, "hb_path": str(p)})
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        assert result["rows"][0]["name"] == "stale_d"
        assert result["rows"][-1]["name"] == "ok_d"

    def test_absent_sorts_before_stale_with_age(self, tmp_path):
        """Absent heartbeat (pct=inf) sorts before a stale-but-measurable one."""
        now = time.time()
        sla = 300.0
        p_stale = tmp_path / "measured.txt"
        _write_hb(p_stale, age_sec=600.0, now=now)
        p_ghost = tmp_path / "ghost.txt"  # absent
        specs = [
            {"name": "measured", "sla_sec": sla, "hb_path": str(p_stale)},
            {"name": "ghost", "sla_sec": sla, "hb_path": str(p_ghost)},
        ]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        names = [r["name"] for r in result["rows"]]
        # ghost (absent) sorts before measured (stale-with-age)
        assert names.index("ghost") < names.index("measured")

    def test_multiple_stale_sorted_by_pct_desc(self, tmp_path):
        now = time.time()
        sla = 300.0
        entries = [("s_high", 900.0), ("s_low", 400.0)]
        specs = []
        for name, age in entries:
            p = tmp_path / ("%s.txt" % name)
            _write_hb(p, age_sec=age, now=now)
            specs.append({"name": name, "sla_sec": sla, "hb_path": str(p)})
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        names = [r["name"] for r in result["rows"]]
        # s_high (300%) before s_low (133%)
        assert names.index("s_high") < names.index("s_low")
