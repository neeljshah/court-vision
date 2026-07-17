"""Per-file test for the pod sprint driver: run, checkpoint, resume, halt."""
import json
import sys

import pytest

from scripts.platformkit.pod_sprint import driver


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(driver, "LOG_DIR", tmp_path / "logs")
    return tmp_path


def _job(name, code, required=True):
    return {"name": name, "argv": [sys.executable, "-c", code],
            "timeout_s": 60, "required": required}


def test_chain_runs_and_checkpoints(sandbox, monkeypatch):
    monkeypatch.setattr(driver, "JOBS", [
        _job("a", "print('hi')"), _job("b", "print('bye')")])
    assert driver.main([]) == 0
    state = json.loads((sandbox / "state.json").read_text())
    assert state["a"]["status"] == "ok" and state["b"]["status"] == "ok"
    summary = json.loads((sandbox / "logs" / "sprint_summary.json").read_text())
    assert summary["halted_at"] is None


def test_required_failure_halts_optional_does_not(sandbox, monkeypatch):
    monkeypatch.setattr(driver, "JOBS", [
        _job("soft", "raise SystemExit(1)", required=False),
        _job("hard", "raise SystemExit(1)", required=True),
        _job("never", "print('x')")])
    assert driver.main([]) == 1
    state = json.loads((sandbox / "state.json").read_text())
    assert state["soft"]["status"] == "fail"
    assert state["soft"]["attempts"] == driver.MAX_ATTEMPTS
    assert state["hard"]["status"] == "fail"
    assert "never" not in state
    summary = json.loads((sandbox / "logs" / "sprint_summary.json").read_text())
    assert summary["halted_at"] == "hard"


def test_prediction_eval_fails_closed(sandbox, monkeypatch, tmp_path):
    from scripts.platformkit.pod_sprint import prediction_eval as pe
    monkeypatch.setattr(pe, "STATE_PATH", tmp_path / "nope.json")

    def boom():
        raise RuntimeError("no data on this box")
    import scripts.platformkit.platform_scoreboard as ps
    monkeypatch.setattr(ps, "build_scoreboard", boom)
    rep = pe.compose()
    assert rep["status"] == "blocked"
    assert "no data" in rep["blocked_reason"]
    assert rep["eval_gate"]["status"] == "missing"
    assert rep["n_sports_scored"] == 0


def test_resume_skips_done_jobs(sandbox, monkeypatch):
    monkeypatch.setattr(driver, "JOBS", [_job("a", "print('hi')")])
    assert driver.main([]) == 0
    first = json.loads((sandbox / "state.json").read_text())["a"]["ended"]
    assert driver.main([]) == 0  # resume: job already ok, not rerun
    assert json.loads(
        (sandbox / "state.json").read_text())["a"]["ended"] == first


def test_exhausted_job_terminal_on_rerun_until_retry(sandbox, monkeypatch):
    monkeypatch.setattr(driver, "JOBS", [_job("bad", "raise SystemExit(1)")])
    assert driver.main([]) == 1
    assert json.loads(
        (sandbox / "state.json").read_text())["bad"]["attempts"] == 2
    assert driver.main([]) == 1  # rerun must NOT burn another attempt
    assert json.loads(
        (sandbox / "state.json").read_text())["bad"]["attempts"] == 2
    assert driver.main(["--retry", "bad"]) == 1  # re-armed: attempts reset+rerun
    assert json.loads(
        (sandbox / "state.json").read_text())["bad"]["attempts"] == 2
