"""tests/platformkit/sla/test_sla_scoreboard.py -- per-file tests for IOX-1 scoreboard.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/sla/test_sla_scoreboard.py -q

Acceptance tests:
  - (artifact_path, sla_sec) list + now -> rows {name, age_sec, sla_sec, breached, status}
  - missing file -> status=STALE breached=True (never ok/green)
  - age > sla -> breached True, status=STALE
  - age <= sla -> breached False, status=ok
  - writes data/frontend/ops/sla_scoreboard.json atomically (no $ key)
  - empty list -> [] never raises
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from scripts.platformkit.sla.sla_scoreboard import build, write_scoreboard


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_artifact(tmp_path):
    """A real file whose mtime is controlled via writes."""
    p = tmp_path / "snapshot.json"
    p.write_text("{}", encoding="ascii")
    return p


# ---------------------------------------------------------------------------
# build() -- core verdict logic
# ---------------------------------------------------------------------------

class TestBuildEmpty:
    def test_empty_list_returns_empty(self):
        result = build([])
        assert result == []

    def test_never_raises_on_empty(self):
        # must not raise even with no items
        assert build([], now=0.0) == []


class TestBuildMissingFile:
    def test_missing_file_is_stale_breached(self, tmp_path):
        absent = tmp_path / "nonexistent.json"
        now = time.time()
        rows = build([(absent, 300.0)], now=now)
        assert len(rows) == 1
        r = rows[0]
        assert r["name"] == "nonexistent.json"
        assert r["age_sec"] is None
        assert r["breached"] is True
        assert r["status"] == "STALE"

    def test_missing_file_sla_sec_preserved(self, tmp_path):
        absent = tmp_path / "missing.parquet"
        rows = build([(absent, 600.0)], now=time.time())
        assert rows[0]["sla_sec"] == 600.0


class TestBuildFreshFile:
    def test_fresh_within_sla_is_ok(self, tmp_artifact):
        now = time.time()
        # The file was just written (age ~0s), SLA=300s -> should be ok
        rows = build([(tmp_artifact, 300.0)], now=now)
        assert len(rows) == 1
        r = rows[0]
        assert r["breached"] is False
        assert r["status"] == "ok"
        assert r["age_sec"] is not None
        assert r["age_sec"] <= 5.0  # file was just created

    def test_fresh_row_has_required_keys(self, tmp_artifact):
        rows = build([(tmp_artifact, 300.0)], now=time.time())
        r = rows[0]
        assert set(r.keys()) == {"name", "age_sec", "sla_sec", "breached", "status"}

    def test_status_ok_only_when_not_breached(self, tmp_artifact):
        rows = build([(tmp_artifact, 300.0)], now=time.time())
        r = rows[0]
        assert (r["status"] == "ok") == (not r["breached"])


class TestBuildStaleFile:
    def test_age_over_sla_is_stale(self, tmp_artifact):
        # Use a fake 'now' that is 1000s in the future relative to mtime
        mtime = tmp_artifact.stat().st_mtime
        future_now = mtime + 1000.0
        rows = build([(tmp_artifact, 300.0)], now=future_now)
        r = rows[0]
        assert r["breached"] is True
        assert r["status"] == "STALE"
        assert r["age_sec"] > 300.0

    def test_age_exactly_at_sla_is_ok(self, tmp_artifact):
        # age == sla_sec should NOT be breached (age <= sla is ok)
        mtime = tmp_artifact.stat().st_mtime
        exact_now = mtime + 300.0
        rows = build([(tmp_artifact, 300.0)], now=exact_now)
        r = rows[0]
        assert r["breached"] is False
        assert r["status"] == "ok"

    def test_age_one_second_over_sla_breaches(self, tmp_artifact):
        mtime = tmp_artifact.stat().st_mtime
        over_now = mtime + 301.0
        rows = build([(tmp_artifact, 300.0)], now=over_now)
        r = rows[0]
        assert r["breached"] is True
        assert r["status"] == "STALE"


class TestBuildMultipleArtifacts:
    def test_mixed_ok_and_stale(self, tmp_path):
        fresh = tmp_path / "fresh.json"
        fresh.write_text("{}", encoding="ascii")
        absent = tmp_path / "absent.json"

        mtime = fresh.stat().st_mtime
        now = mtime + 100.0  # fresh is 100s old

        artifacts = [
            (fresh, 300.0),   # ok (100s < 300s)
            (absent, 300.0),  # STALE (file missing)
        ]
        rows = build(artifacts, now=now)
        assert len(rows) == 2
        assert rows[0]["status"] == "ok"
        assert rows[0]["breached"] is False
        assert rows[1]["status"] == "STALE"
        assert rows[1]["breached"] is True

    def test_all_fresh_no_breach(self, tmp_path):
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text("{}", encoding="ascii")
        f2.write_text("{}", encoding="ascii")
        now = time.time()
        rows = build([(f1, 3600.0), (f2, 7200.0)], now=now)
        assert all(not r["breached"] for r in rows)

    def test_names_match_basenames(self, tmp_path):
        p = tmp_path / "sla_scoreboard.json"
        p.write_text("{}", encoding="ascii")
        rows = build([(p, 300.0)], now=time.time())
        assert rows[0]["name"] == "sla_scoreboard.json"

    def test_string_path_accepted(self, tmp_artifact):
        rows = build([(str(tmp_artifact), 300.0)], now=time.time())
        assert len(rows) == 1
        assert rows[0]["breached"] is False


class TestBuildNoRaises:
    def test_build_never_raises_on_garbage(self):
        # Malformed entries should not raise -- bad entry is skipped
        result = build([("", -1), (None, 300)])  # type: ignore[list-item]
        # Should return at most 2 rows without raising; empty or partial is fine
        assert isinstance(result, list)

    def test_build_never_raises_no_now(self, tmp_artifact):
        # now defaults to time.time() -- must not raise
        rows = build([(tmp_artifact, 300.0)])
        assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# write_scoreboard() -- atomic JSON write
# ---------------------------------------------------------------------------

class TestWriteScoreboard:
    def test_writes_valid_json(self, tmp_path):
        out = tmp_path / "ops" / "sla_scoreboard.json"
        rows = [{"name": "x.json", "age_sec": 10.0, "sla_sec": 300.0,
                 "breached": False, "status": "ok"}]
        ok = write_scoreboard(rows, out_path=out, generated_at_epoch=0.0)
        assert ok is True
        doc = json.loads(out.read_text(encoding="ascii"))
        assert "rows" in doc
        assert "generated_at" in doc
        assert "any_breached" in doc
        assert "honest_note" in doc

    def test_no_dollar_key(self, tmp_path):
        out = tmp_path / "sla_scoreboard.json"
        write_scoreboard([], out_path=out, generated_at_epoch=0.0)
        doc = json.loads(out.read_text(encoding="ascii"))
        # No dollar-sign JSON keys (keys themselves must not contain $ or be roi/pnl)
        all_keys = set(doc.keys())
        assert not any("$" in k for k in all_keys)
        assert "roi" not in all_keys
        assert "pnl" not in all_keys
        assert "profit" not in all_keys

    def test_any_breached_true_when_any_row_breached(self, tmp_path):
        out = tmp_path / "sla.json"
        rows = [
            {"name": "a.json", "age_sec": None, "sla_sec": 300.0,
             "breached": True, "status": "STALE"},
            {"name": "b.json", "age_sec": 10.0, "sla_sec": 300.0,
             "breached": False, "status": "ok"},
        ]
        write_scoreboard(rows, out_path=out, generated_at_epoch=1.0)
        doc = json.loads(out.read_text(encoding="ascii"))
        assert doc["any_breached"] is True

    def test_any_breached_false_when_all_ok(self, tmp_path):
        out = tmp_path / "sla.json"
        rows = [{"name": "a.json", "age_sec": 5.0, "sla_sec": 300.0,
                 "breached": False, "status": "ok"}]
        write_scoreboard(rows, out_path=out, generated_at_epoch=1.0)
        doc = json.loads(out.read_text(encoding="ascii"))
        assert doc["any_breached"] is False

    def test_empty_rows_write_ok(self, tmp_path):
        out = tmp_path / "sla.json"
        ok = write_scoreboard([], out_path=out, generated_at_epoch=0.0)
        assert ok is True
        doc = json.loads(out.read_text(encoding="ascii"))
        assert doc["rows"] == []
        assert doc["any_breached"] is False

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "sla_scoreboard.json"
        ok = write_scoreboard([], out_path=out, generated_at_epoch=0.0)
        assert ok is True
        assert out.exists()

    def test_output_is_ascii(self, tmp_path):
        out = tmp_path / "sla.json"
        write_scoreboard([], out_path=out, generated_at_epoch=0.0)
        raw = out.read_bytes()
        # All bytes should be in ASCII range
        assert all(b < 128 for b in raw)

    def test_returns_false_on_bad_path(self):
        # write to an invalid path (directory as file)
        bad_path = pathlib.Path("/dev/null/not_possible/sla.json")
        result = write_scoreboard([], out_path=bad_path)
        # Should return False, not raise
        assert result is False

    def test_generated_at_iso_format(self, tmp_path):
        out = tmp_path / "sla.json"
        write_scoreboard([], out_path=out, generated_at_epoch=0.0)
        doc = json.loads(out.read_text(encoding="ascii"))
        ts = doc["generated_at"]
        # Should be ISO-8601 UTC string
        assert ts.endswith("Z")
        assert "T" in ts


# ---------------------------------------------------------------------------
# Integration: build + write round-trip
# ---------------------------------------------------------------------------

class TestBuildWriteRoundTrip:
    def test_roundtrip_fresh_and_absent(self, tmp_path):
        fresh = tmp_path / "fresh.json"
        fresh.write_text("{}", encoding="ascii")
        absent = tmp_path / "ghost.json"
        out = tmp_path / "scoreboard.json"

        mtime = fresh.stat().st_mtime
        now = mtime + 50.0

        rows = build([(fresh, 300.0), (absent, 300.0)], now=now)
        write_scoreboard(rows, out_path=out, generated_at_epoch=now)

        doc = json.loads(out.read_text(encoding="ascii"))
        assert len(doc["rows"]) == 2
        assert doc["rows"][0]["status"] == "ok"
        assert doc["rows"][1]["status"] == "STALE"
        assert doc["any_breached"] is True
