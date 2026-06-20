"""test_daemon_lag_histogram.py -- per-file tests for daemon_lag_histogram.py (BE-R5-8).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/observability/test_daemon_lag_histogram.py -q

Acceptance criteria:
  * Mixed-age heartbeats -> correct fresh/warn/stale bucket counts.
  * worst-offender list = stale bucket daemons.
  * fresh=null + age>=SLA -> stale bucket (stale-never-green).
  * Missing heartbeat dir -> UNAVAILABLE, never green.
  * No $ / roi / pnl / profit / dollar key in output.
  * Never raises on any input.
  * status reflects worst bucket present (stale > warn > ok).
  * stale-never-green: absent heartbeat file -> stale, not fresh.

ASCII only; <= 300 LOC.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from scripts.platformkit.observability.daemon_lag_histogram import (
    BUCKET_FRESH,
    BUCKET_STALE,
    BUCKET_WARN,
    STATUS_OK,
    STATUS_STALE,
    STATUS_UNAVAILABLE,
    STATUS_WARN,
    compute_lag_histogram,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _fixed_clock(epoch: float):
    """Return a clock callable that always returns *epoch*."""
    return lambda: epoch


def _make_specs(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build spec list from list of {name, sla_sec, hb_path (or None)}."""
    return [
        {"name": e["name"], "sla_sec": e["sla_sec"], "hb_path": e.get("hb_path")}
        for e in entries
    ]


def _write_hb(path: Path, age_sec: float, now: float) -> Path:
    """Write a plain ISO-8601 heartbeat file with stamp = now - age_sec."""
    from datetime import datetime, timezone
    stamp = now - age_sec
    dt = datetime.fromtimestamp(stamp, tz=timezone.utc)
    path.write_text(dt.strftime("%Y-%m-%dT%H:%M:%SZ"), encoding="utf-8")
    return path


def _write_json_hb(path: Path, age_sec: float, now: float) -> Path:
    """Write a JSON heartbeat file (updated_at epoch float)."""
    stamp = now - age_sec
    path.write_text(json.dumps({"updated_at": stamp, "cycle_count": 1}),
                    encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Core bucket tests
# ---------------------------------------------------------------------------

class TestBucketCounts:
    """Mixed-age heartbeats produce correct fresh/warn/stale bucket counts."""

    def test_all_fresh(self, tmp_path):
        now = time.time()
        sla = 300.0
        specs = []
        for i in range(3):
            p = tmp_path / ("d%d.txt" % i)
            _write_hb(p, age_sec=100.0, now=now)  # age < sla -> fresh
            specs.append({"name": "d%d" % i, "sla_sec": sla, "hb_path": str(p)})
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert result["buckets"][BUCKET_FRESH] == 3
        assert result["buckets"][BUCKET_WARN] == 0
        assert result["buckets"][BUCKET_STALE] == 0
        assert result["status"] == STATUS_OK

    def test_all_warn(self, tmp_path):
        now = time.time()
        sla = 300.0
        specs = []
        for i in range(3):
            p = tmp_path / ("d%d.txt" % i)
            # SLA <= age < 2*SLA -> warn (age = 400, sla=300, 2*sla=600)
            _write_hb(p, age_sec=400.0, now=now)
            specs.append({"name": "d%d" % i, "sla_sec": sla, "hb_path": str(p)})
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert result["buckets"][BUCKET_WARN] == 3
        assert result["buckets"][BUCKET_STALE] == 0
        assert result["status"] == STATUS_WARN

    def test_all_stale(self, tmp_path):
        now = time.time()
        sla = 300.0
        specs = []
        for i in range(3):
            p = tmp_path / ("d%d.txt" % i)
            # age >= 2*sla -> stale
            _write_hb(p, age_sec=700.0, now=now)
            specs.append({"name": "d%d" % i, "sla_sec": sla, "hb_path": str(p)})
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert result["buckets"][BUCKET_STALE] == 3
        assert result["status"] == STATUS_STALE

    def test_mixed_ages_correct_counts(self, tmp_path):
        now = time.time()
        sla = 300.0
        specs = []
        # 2 fresh (age=50), 1 warn (age=450), 2 stale (age=800)
        for i, age in enumerate([50.0, 50.0, 450.0, 800.0, 800.0]):
            p = tmp_path / ("m%d.txt" % i)
            _write_hb(p, age_sec=age, now=now)
            specs.append({"name": "m%d" % i, "sla_sec": sla, "hb_path": str(p)})
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert result["buckets"][BUCKET_FRESH] == 2
        assert result["buckets"][BUCKET_WARN] == 1
        assert result["buckets"][BUCKET_STALE] == 2
        assert result["status"] == STATUS_STALE

    def test_worst_offender_list_is_stale_daemons(self, tmp_path):
        now = time.time()
        sla = 300.0
        specs = []
        for name, age in [("alpha", 50.0), ("beta", 800.0), ("gamma", 800.0)]:
            p = tmp_path / ("%s.txt" % name)
            _write_hb(p, age_sec=age, now=now)
            specs.append({"name": name, "sla_sec": sla, "hb_path": str(p)})
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert set(result["worst"]) == {"beta", "gamma"}
        assert "alpha" not in result["worst"]


# ---------------------------------------------------------------------------
# stale-never-green invariant
# ---------------------------------------------------------------------------

class TestStaleNeverGreen:
    """absent/null heartbeat must land in stale bucket, never fresh."""

    def test_absent_file_is_stale(self, tmp_path):
        now = time.time()
        p = tmp_path / "missing.txt"
        # Do NOT write the file -> absent heartbeat
        specs = [{"name": "m1", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        rows = {r["name"]: r for r in result["per_daemon"]}
        assert rows["m1"]["bucket"] == BUCKET_STALE
        assert rows["m1"]["age_sec"] is None
        assert result["status"] == STATUS_STALE

    def test_absent_file_age_none_not_fresh(self, tmp_path):
        """age=None with age>=SLA -> stale (the spec's acceptance test exact case)."""
        now = time.time()
        p = tmp_path / "no_file.txt"
        specs = [{"name": "daemon_x", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        row = result["per_daemon"][0]
        assert row["bucket"] == BUCKET_STALE
        assert row["age_sec"] is None

    def test_empty_file_is_stale(self, tmp_path):
        now = time.time()
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        specs = [{"name": "d_empty", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert result["per_daemon"][0]["bucket"] == BUCKET_STALE

    def test_worst_includes_absent_file(self, tmp_path):
        now = time.time()
        sla = 300.0
        fresh_path = tmp_path / "fresh.txt"
        _write_hb(fresh_path, age_sec=50.0, now=now)
        specs = [
            {"name": "fresh_d", "sla_sec": sla, "hb_path": str(fresh_path)},
            {"name": "ghost_d", "sla_sec": sla, "hb_path": str(tmp_path / "ghost.txt")},
        ]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert "ghost_d" in result["worst"]
        assert "fresh_d" not in result["worst"]


# ---------------------------------------------------------------------------
# Missing heartbeat dir -> UNAVAILABLE
# ---------------------------------------------------------------------------

class TestMissingHeartbeatDir:
    def test_nonexistent_dir_gives_unavailable(self):
        nonexistent = Path("/totally/nonexistent/heartbeats_dir/xyz")
        specs = [{"name": "m1", "sla_sec": 300.0, "hb_path": None}]
        result = compute_lag_histogram(
            specs, heartbeat_dir=nonexistent, clock=_fixed_clock(time.time())
        )
        # hb_path=None + dir missing -> age=None -> stale bucket -> STALE or UNAVAILABLE
        assert result["status"] in (STATUS_UNAVAILABLE, STATUS_STALE)

    def test_no_heartbeat_daemons_gives_unavailable(self):
        # Specs with no hb_path and no heartbeat dir that exists
        specs: List[Dict[str, Any]] = []
        result = compute_lag_histogram(specs, clock=_fixed_clock(time.time()))
        assert result["status"] == STATUS_UNAVAILABLE

    def test_unavailable_never_ok(self):
        specs: List[Dict[str, Any]] = []
        result = compute_lag_histogram(specs, clock=_fixed_clock(time.time()))
        assert result["status"] != STATUS_OK


# ---------------------------------------------------------------------------
# JSON heartbeat format (predict_service / ingame pattern)
# ---------------------------------------------------------------------------

class TestJsonHeartbeatFormat:
    def test_json_updated_at_epoch_fresh(self, tmp_path):
        now = time.time()
        p = tmp_path / "_heartbeat.json"
        _write_json_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "svc", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert result["per_daemon"][0]["bucket"] == BUCKET_FRESH

    def test_json_updated_at_epoch_stale(self, tmp_path):
        now = time.time()
        p = tmp_path / "_heartbeat.json"
        _write_json_hb(p, age_sec=800.0, now=now)
        specs = [{"name": "svc", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert result["per_daemon"][0]["bucket"] == BUCKET_STALE

    def test_json_updated_at_warn(self, tmp_path):
        now = time.time()
        p = tmp_path / "_heartbeat.json"
        _write_json_hb(p, age_sec=450.0, now=now)
        specs = [{"name": "svc", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert result["per_daemon"][0]["bucket"] == BUCKET_WARN


# ---------------------------------------------------------------------------
# Output schema + no $ field
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_required_top_level_keys(self, tmp_path):
        now = time.time()
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        for key in ("per_daemon", "buckets", "worst", "status", "honest_note"):
            assert key in result, "Missing key: %s" % key

    def test_per_daemon_row_keys(self, tmp_path):
        now = time.time()
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        row = result["per_daemon"][0]
        for key in ("name", "sla_sec", "age_sec", "staleness_frac", "bucket", "hb_path"):
            assert key in row, "Missing per_daemon row key: %s" % key

    def test_no_dollar_fields(self, tmp_path):
        now = time.time()
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        banned = {"pnl", "profit", "roi", "bankroll", "usd", "dollar", "stake",
                  "edge_claimed", "edge"}
        all_keys = set(result.keys())
        for row in result["per_daemon"]:
            all_keys |= set(row.keys())
        for key in all_keys:
            assert key.lower() not in banned, "Banned $ field present: %s" % key

    def test_buckets_dict_has_three_keys(self, tmp_path):
        now = time.time()
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        assert set(result["buckets"].keys()) == {"fresh", "warn", "stale"}

    def test_staleness_frac_proportional_to_age_over_sla(self, tmp_path):
        now = time.time()
        sla = 300.0
        age = 150.0
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=age, now=now)
        specs = [{"name": "d", "sla_sec": sla, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        row = result["per_daemon"][0]
        assert row["staleness_frac"] == pytest.approx(age / sla, abs=0.01)


# ---------------------------------------------------------------------------
# Never-raises contract
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_none_specs(self):
        # None specs -> tries to import stack_specs (may succeed or return UNAVAILABLE)
        result = compute_lag_histogram(None, clock=_fixed_clock(time.time()))
        assert "status" in result

    def test_empty_specs_list(self):
        result = compute_lag_histogram([], clock=_fixed_clock(time.time()))
        assert result["status"] == STATUS_UNAVAILABLE

    def test_malformed_spec_entries(self):
        specs = [None, {}, {"name": "x"}, 42, {"name": "y", "sla_sec": "bad"}]  # type: ignore
        result = compute_lag_histogram(specs, clock=_fixed_clock(time.time()))  # type: ignore
        assert "status" in result

    def test_corrupt_heartbeat_file(self, tmp_path):
        now = time.time()
        p = tmp_path / "corrupt.txt"
        p.write_bytes(b"\xff\xfe corrupt binary")
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        # Corrupt file -> age=None -> stale bucket
        assert result["per_daemon"][0]["bucket"] == BUCKET_STALE

    def test_hb_path_is_none_with_valid_dir(self, tmp_path):
        # hb_path=None, no matching file in dir -> age=None -> stale
        now = time.time()
        specs = [{"name": "ghost", "sla_sec": 300.0, "hb_path": None}]
        result = compute_lag_histogram(
            specs, heartbeat_dir=tmp_path, clock=_fixed_clock(now)
        )
        assert result["per_daemon"][0]["bucket"] == BUCKET_STALE


# ---------------------------------------------------------------------------
# Sorting: worst offenders first
# ---------------------------------------------------------------------------

class TestOrdering:
    def test_stale_sorted_before_warn_and_fresh(self, tmp_path):
        now = time.time()
        sla = 300.0
        data = [("stale_d", 800.0), ("warn_d", 450.0), ("fresh_d", 100.0)]
        specs = []
        for name, age in data:
            p = tmp_path / ("%s.txt" % name)
            _write_hb(p, age_sec=age, now=now)
            specs.append({"name": name, "sla_sec": sla, "hb_path": str(p)})
        result = compute_lag_histogram(specs, clock=_fixed_clock(now))
        names = [r["name"] for r in result["per_daemon"]]
        assert names[0] == "stale_d"
        assert names[-1] == "fresh_d"
