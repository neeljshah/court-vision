"""Tests for scripts/health_check.py (cycle 105e, loop 5)."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "health_check.py"

# Load the script as a module (it lives outside the importable package tree).
_spec = importlib.util.spec_from_file_location("health_check", SCRIPT)
hc = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(hc)  # type: ignore[union-attr]


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = hc.main(argv)
    return code, buf.getvalue()


def test_all_categories_run_without_crash():
    results = hc.run_all(skip_network=True)
    # 6 categories run; each contributes >=1 record. API contributes one stub
    # per endpoint when skipped.
    assert len(results) >= 10
    statuses = {r["status"] for r in results}
    assert statuses.issubset({hc.OK, hc.WARN, hc.ERROR})


def test_error_when_model_artifact_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "DATA", tmp_path)
    (tmp_path / "models").mkdir()
    results = []
    hc.check_model_artifacts(results)
    assert any(r["status"] == hc.ERROR and "missing" in r["detail"]
               for r in results)


def test_warn_when_predictions_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "DATA", tmp_path)
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()
    from datetime import date
    f = pred_dir / f"{date.today().isoformat()}.csv"
    f.write_text("a,b\n1,2\n")
    # set mtime to 10h ago
    old = time.time() - 10 * 3600
    os.utime(f, (old, old))
    results = []
    hc.check_data_freshness(results)
    pred_recs = [r for r in results if "predictions/" in r["name"]]
    assert pred_recs and pred_recs[0]["status"] == hc.WARN


def test_api_timeout_is_warn_not_error(monkeypatch):
    def fake_ping(url, timeout=5.0):
        return False, "timeout", timeout
    monkeypatch.setattr(hc, "_ping", fake_ping)
    results = []
    hc.check_api_endpoints(results)
    api_recs = [r for r in results if "timeout" in r["detail"].lower()]
    assert api_recs
    assert all(r["status"] == hc.WARN for r in api_recs)


def test_json_output_is_parseable():
    code, out = _run(["--json", "--skip-network"])
    payload = json.loads(out)
    assert "summary" in payload and "checks" in payload
    assert {"ok", "warn", "error"} <= set(payload["summary"])
    assert isinstance(payload["checks"], list) and payload["checks"]


def test_strict_exits_nonzero_on_warn(monkeypatch):
    # Force at least one WARN by skipping network (each endpoint becomes OK
    # under skip), so inject a fake category that records a WARN.
    real_run_all = hc.run_all

    def fake_run_all(skip_network=False):
        return [{"status": hc.WARN, "name": "x", "detail": "y", "fix": ""}]

    monkeypatch.setattr(hc, "run_all", fake_run_all)
    code, _ = _run(["--strict", "--skip-network"])
    assert code == 1

    monkeypatch.setattr(hc, "run_all",
                        lambda skip_network=False:
                        [{"status": hc.OK, "name": "x",
                          "detail": "y", "fix": ""}])
    code, _ = _run(["--strict", "--skip-network"])
    assert code == 0

    monkeypatch.setattr(hc, "run_all", real_run_all)
