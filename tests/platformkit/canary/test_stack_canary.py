"""tests.platformkit.canary.test_stack_canary -- per-file tests for IOX-2 canary.

Acceptance criteria (from BACKLOG.md IOX-2):
  * All probes pass -> {status: READY, failing_stage: null}
  * envelope-fetch probe raises -> {status: DOWN, failing_stage: 'predict_envelope'}
  * one non-critical probe stale -> DEGRADED (failing_stage remains null)
  * offseason (no predictions in envelope) -> READY-with-note not DOWN
  * never raises
  * all injectable (no live network, no real store)
  * no $ field anywhere in output

INVARIANTS: per-file only (never full pytest); ASCII only; stdlib + repo imports;
never mutates data/registry/; no flag flip; no real money.
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import time

import pytest

from scripts.platformkit.canary.stack_canary import (
    DEGRADED,
    DOWN,
    READY,
    CanaryResult,
    run_canary,
    _probe_calibration_note,
    _probe_envelope_schema,
    _probe_ops_status,
    _probe_predict_envelope,
    _probe_prediction_fresh,
)


# ---------------------------------------------------------------------------
# Helpers -- fake envelopes and stub read_fn factories
# ---------------------------------------------------------------------------

class _FakeEnvelope:
    """Minimal fake SnapshotEnvelope sufficient for canary probes."""

    def __init__(self, *, sport="nba", status="ok", predictions=None,
                 honest_note="Calibrated decision-support only. No $ edge.",
                 schema_version="1.1.0"):
        self.sport = sport
        self.status = status
        self.predictions = predictions or []
        self._honest_note = honest_note
        self._schema_version = schema_version

    def to_dict(self):
        return {
            "sport": self.sport,
            "status": self.status,
            "schema_version": self._schema_version,
            "honest_note": self._honest_note,
            "predictions": [p if isinstance(p, dict) else vars(p)
                            for p in self.predictions],
        }


class _FakePred:
    """Minimal fake PredictionRecord."""
    def __init__(self, game_id="G1", produced_at=None):
        self.game_id = game_id
        self.produced_at = produced_at or "2026-06-20T06:00:00+00:00"


def _make_read_fn(env):
    """Return a stub read_fn that returns *env*."""
    def _fn():
        return env
    return _fn


def _make_raising_read_fn(exc=None):
    """Return a stub read_fn that raises."""
    def _fn():
        raise (exc or RuntimeError("network down"))
    return _fn


def _write_ops_status(tmp_dir, overall="ok", age_sec=10.0):
    """Write a fake ops status.json into *tmp_dir* with controlled mtime."""
    path = pathlib.Path(tmp_dir) / "status.json"
    doc = {"overall": overall, "services": [], "notes": []}
    path.write_text(json.dumps(doc), encoding="utf-8")
    # Adjust mtime to simulate age
    mtime = time.time() - age_sec
    import os
    os.utime(str(path), (mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# Test: happy path -> READY
# ---------------------------------------------------------------------------

def test_all_probes_pass_returns_ready():
    """All probes pass -> status=READY, failing_stage=None."""
    env = _FakeEnvelope(predictions=[_FakePred()])
    read_fn = _make_read_fn(env)
    with tempfile.TemporaryDirectory() as td:
        ops_path = _write_ops_status(td, overall="ok", age_sec=10.0)
        result = run_canary(
            read_fn=read_fn,
            ops_path=ops_path,
            now=time.time(),
        )
    assert isinstance(result, CanaryResult)
    assert result.status == READY
    assert result.failing_stage is None
    # No $ field in the dict output
    d = result.to_dict()
    for key in d:
        assert "$" not in key.lower(), "$ field found in canary output"


# ---------------------------------------------------------------------------
# Test: predict_envelope probe raises -> DOWN with stage named
# ---------------------------------------------------------------------------

def test_envelope_fetch_raises_returns_down():
    """envelope-fetch raises -> status=DOWN, failing_stage='predict_envelope'."""
    read_fn = _make_raising_read_fn(RuntimeError("store unreachable"))
    with tempfile.TemporaryDirectory() as td:
        ops_path = _write_ops_status(td, overall="ok", age_sec=10.0)
        result = run_canary(
            read_fn=read_fn,
            ops_path=ops_path,
            now=time.time(),
        )
    assert result.status == DOWN
    assert result.failing_stage == "predict_envelope"
    # Never green on failure
    assert result.status != READY


# ---------------------------------------------------------------------------
# Test: one non-critical stale -> DEGRADED
# ---------------------------------------------------------------------------

def test_non_critical_stale_ops_returns_degraded():
    """ops_status stale (non-critical) -> DEGRADED, failing_stage is None."""
    env = _FakeEnvelope(predictions=[_FakePred()])
    read_fn = _make_read_fn(env)
    with tempfile.TemporaryDirectory() as td:
        # Write an ops status file that is very old
        ops_path = _write_ops_status(td, overall="degraded", age_sec=9999.0)
        result = run_canary(
            read_fn=read_fn,
            ops_path=ops_path,
            now=time.time(),
            ops_stale_sec=300.0,
        )
    assert result.status == DEGRADED
    # failing_stage is None for non-critical DEGRADED
    assert result.failing_stage is None
    # At least one probe is not ok
    failed = [p for p in result.probes if not p.ok]
    assert failed, "expected at least one failed probe"
    assert all(not p.critical for p in failed), "failed probe should be non-critical"


# ---------------------------------------------------------------------------
# Test: offseason (no predictions) -> READY with note
# ---------------------------------------------------------------------------

def test_offseason_no_predictions_is_ready():
    """No predictions in envelope (offseason) -> READY-with-note, not DOWN."""
    env = _FakeEnvelope(predictions=[])  # empty
    read_fn = _make_read_fn(env)
    with tempfile.TemporaryDirectory() as td:
        ops_path = _write_ops_status(td, overall="ok", age_sec=5.0)
        result = run_canary(
            read_fn=read_fn,
            ops_path=ops_path,
            now=time.time(),
        )
    assert result.status == READY, (
        "offseason (no predictions) must be READY, got %s" % result.status)
    assert result.failing_stage is None
    # A note about offseason should be present
    all_text = " ".join(result.notes + [p.note for p in result.probes])
    assert "offseason" in all_text.lower() or "no predictions" in all_text.lower()


# ---------------------------------------------------------------------------
# Test: envelope missing required key -> DOWN on envelope_schema
# ---------------------------------------------------------------------------

def test_envelope_missing_key_returns_down():
    """Envelope dict missing 'honest_note' key -> DOWN on envelope_schema."""
    class _BadEnv:
        def to_dict(self):
            # Missing honest_note intentionally
            return {"sport": "nba", "status": "ok", "schema_version": "1.1.0"}
        @property
        def predictions(self):
            return []
        @property
        def status(self):
            return "ok"

    read_fn = _make_read_fn(_BadEnv())
    with tempfile.TemporaryDirectory() as td:
        ops_path = _write_ops_status(td, overall="ok", age_sec=5.0)
        result = run_canary(
            read_fn=read_fn,
            ops_path=ops_path,
            now=time.time(),
        )
    assert result.status == DOWN
    assert result.failing_stage in ("envelope_schema", "calibration_note")


# ---------------------------------------------------------------------------
# Test: empty honest_note -> DOWN on calibration_note
# ---------------------------------------------------------------------------

def test_empty_honest_note_returns_down():
    """honest_note empty string -> DOWN on calibration_note stage."""
    env = _FakeEnvelope(honest_note="", predictions=[_FakePred()])
    read_fn = _make_read_fn(env)
    with tempfile.TemporaryDirectory() as td:
        ops_path = _write_ops_status(td, overall="ok", age_sec=5.0)
        result = run_canary(
            read_fn=read_fn,
            ops_path=ops_path,
            now=time.time(),
        )
    assert result.status == DOWN
    assert result.failing_stage == "calibration_note"


# ---------------------------------------------------------------------------
# Test: ops status file absent -> DEGRADED (non-critical)
# ---------------------------------------------------------------------------

def test_ops_status_absent_returns_degraded():
    """Missing ops status.json -> DEGRADED (non-critical), not DOWN."""
    env = _FakeEnvelope(predictions=[_FakePred()])
    read_fn = _make_read_fn(env)
    nonexistent = pathlib.Path("/tmp/canary_test_nonexistent_12345/status.json")
    result = run_canary(
        read_fn=read_fn,
        ops_path=nonexistent,
        now=time.time(),
    )
    assert result.status == DEGRADED
    assert result.failing_stage is None


# ---------------------------------------------------------------------------
# Test: stale prediction -> DEGRADED (non-critical)
# ---------------------------------------------------------------------------

def test_stale_prediction_returns_degraded():
    """produced_at very old -> prediction_fresh DEGRADED, not DOWN."""
    old_ts = "2020-01-01T00:00:00+00:00"  # clearly too old
    env = _FakeEnvelope(predictions=[_FakePred(produced_at=old_ts)])
    read_fn = _make_read_fn(env)
    with tempfile.TemporaryDirectory() as td:
        ops_path = _write_ops_status(td, overall="ok", age_sec=5.0)
        result = run_canary(
            read_fn=read_fn,
            ops_path=ops_path,
            now=time.time(),
            pred_stale_sec=3600.0,
        )
    # prediction_fresh is non-critical; critical probes pass -> at most DEGRADED
    assert result.status in (DEGRADED, READY)
    if result.status == DEGRADED:
        assert result.failing_stage is None


# ---------------------------------------------------------------------------
# Test: never raises (chaos: all probes break)
# ---------------------------------------------------------------------------

def test_run_canary_never_raises():
    """run_canary() must never propagate exceptions regardless of probe behavior."""
    def _bad_read():
        raise ValueError("unexpected chaos")

    try:
        result = run_canary(
            read_fn=_bad_read,
            ops_path=pathlib.Path("/dev/null/nonexistent"),
            now=time.time(),
        )
    except Exception as exc:
        pytest.fail("run_canary raised: %s" % exc)

    assert result.status in (READY, DEGRADED, DOWN)


# ---------------------------------------------------------------------------
# Test: to_dict has no $ key
# ---------------------------------------------------------------------------

def test_to_dict_no_dollar_field():
    """CanaryResult.to_dict() must not contain any $ key."""
    env = _FakeEnvelope(predictions=[_FakePred()])
    with tempfile.TemporaryDirectory() as td:
        ops_path = _write_ops_status(td, overall="ok", age_sec=5.0)
        result = run_canary(
            read_fn=_make_read_fn(env),
            ops_path=ops_path,
            now=time.time(),
        )
    d = result.to_dict()
    flat = json.dumps(d)
    assert "$" not in flat, "$ character found in canary output: %s" % flat


# ---------------------------------------------------------------------------
# Individual probe unit tests
# ---------------------------------------------------------------------------

def test_probe_predict_envelope_ok():
    env = _FakeEnvelope()
    p = _probe_predict_envelope(_make_read_fn(env))
    assert p.ok is True
    assert p.critical is True


def test_probe_predict_envelope_raises():
    p = _probe_predict_envelope(_make_raising_read_fn())
    assert p.ok is False
    assert p.stage == "predict_envelope"


def test_probe_envelope_schema_missing_key():
    class _Env:
        def to_dict(self):
            return {"sport": "nba"}
        @property
        def status(self):
            return "ok"
        @property
        def predictions(self):
            return []
    p = _probe_envelope_schema(_make_read_fn(_Env()))
    assert p.ok is False
    assert "missing" in p.note.lower()


def test_probe_calibration_note_empty():
    env = _FakeEnvelope(honest_note="  ")
    p = _probe_calibration_note(_make_read_fn(env))
    assert p.ok is False
    assert p.stage == "calibration_note"


def test_probe_ops_status_fresh():
    with tempfile.TemporaryDirectory() as td:
        path = _write_ops_status(td, age_sec=10.0)
        p = _probe_ops_status(ops_path=path, now=time.time(), stale_sec=300.0)
    assert p.ok is True
    assert p.critical is False


def test_probe_ops_status_stale():
    with tempfile.TemporaryDirectory() as td:
        path = _write_ops_status(td, age_sec=9999.0)
        p = _probe_ops_status(ops_path=path, now=time.time(), stale_sec=300.0)
    assert p.ok is False
    assert "stale" in p.note.lower()


def test_probe_prediction_fresh_no_preds():
    """No predictions -> ok=True (offseason, not DOWN)."""
    env = _FakeEnvelope(predictions=[])
    p = _probe_prediction_fresh(_make_read_fn(env), now=time.time())
    assert p.ok is True
    assert "offseason" in p.note.lower() or "no predictions" in p.note.lower()


def test_probe_prediction_fresh_old():
    env = _FakeEnvelope(predictions=[_FakePred(produced_at="2020-01-01T00:00:00+00:00")])
    p = _probe_prediction_fresh(_make_read_fn(env), now=time.time(), stale_sec=3600.0)
    assert p.ok is False
    assert p.critical is False


# ---------------------------------------------------------------------------
# Live integration: the REAL store should produce READY (if data/ present)
# ---------------------------------------------------------------------------

def test_real_store_integration():
    """With real data/ on disk the canary should reach READY or DEGRADED (not DOWN)."""
    import pathlib as _p
    store_path = _p.Path(__file__).resolve().parents[3] / "data" / "frontend" / "predict_service" / "nba"
    if not (store_path / "latest.json").exists():
        pytest.skip("data/frontend/predict_service/nba/latest.json absent -- offsite")
    # Use real store read; pass a recent now so prediction_fresh fires correctly
    result = run_canary(now=time.time())
    assert result.status in (READY, DEGRADED), (
        "real store produced DOWN: %s" % result.to_dict())
