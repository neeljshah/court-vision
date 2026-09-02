"""Deterministic construct tests for the teacher-to-student calibration gate."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.eval_gate import student_gate
from scripts.platformkit.eval_gate.scoring import brier as core_brier
from scripts.platformkit.eval_gate.walkforward import LeakError


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def _states(kind: str, n: int = 1000, seed: int = 20260903) -> list[dict]:
    rng = np.random.default_rng(seed)
    player_ids = rng.integers(0, 100, size=n)
    if kind == "identity":
        latent = np.linspace(-2.0, 2.0, 100)
        probabilities = _sigmoid(latent[player_ids])
        teacher = _sigmoid(rng.normal(size=n))
    elif kind == "teacher":
        teacher_raw = rng.normal(size=n)
        probabilities = _sigmoid(teacher_raw)
        teacher = probabilities
    else:
        raise ValueError(kind)
    outcomes = rng.binomial(1, probabilities)
    start = datetime(2023, 1, 1, 12)
    states = []
    for index in range(n):
        state_ts = start + timedelta(days=index)
        states.append({
            "game_id": f"g{index}", "state_ts": state_ts.isoformat(), "sport": "all",
            "home": f"H{index}", "away": f"A{index}", "player_id": int(player_ids[index]),
            "features": {"teacher": float(teacher[index])},
            "feature_avail": {"teacher": (state_ts - timedelta(hours=1)).isoformat()},
            "outcome": int(outcomes[index]),
        })
    return states


def _teacher(_train: list[dict], test: dict, _inside: bool) -> float:
    return float(test["features"]["teacher"])


def _run(kind: str, tmp_path: Path, monkeypatch) -> tuple[student_gate.StudentVerdict, dict]:
    ledger = tmp_path / f"{kind}_ledger.jsonl"
    output = tmp_path / "output"
    observed = []
    def checking_brier(probabilities, outcomes):
        rows = [json.loads(line) for line in ledger.read_text(encoding="ascii").splitlines() if line]
        payload = json.loads((output / f"student_gate_{kind}.json").read_text(encoding="ascii"))
        observed.append((len(rows), payload["k_cumulative"]))
        return core_brier(probabilities, outcomes)

    monkeypatch.setattr(student_gate, "brier", checking_brier)
    result = student_gate.run_student_gate(
        _states(kind), _teacher, ledger_path=ledger, charge_spec=f"synthetic:{kind}", name=kind, output_dir=output
    )
    assert observed and observed[0] == (1, result.k_cumulative)
    payload = json.loads((output / f"student_gate_{kind}.json").read_text(encoding="ascii"))
    rows = [json.loads(line) for line in ledger.read_text(encoding="ascii").splitlines() if line]
    assert len(rows) == 1
    assert rows[0]["k_cumulative"] == payload["k_cumulative"] == result.k_cumulative
    assert payload["ledger_row"] == rows[0]
    assert payload["prereg_sha256"] == student_gate._PREREG_SHA256
    assert payload["arm_briers"] == payload["detail"]["arm_briers"]
    return result, payload


def test_two_construct_corpora_and_preregistered_ledger_order(tmp_path: Path, monkeypatch):
    null_result, null_payload = _run("identity", tmp_path, monkeypatch)
    teaches_result, teaches_payload = _run("teacher", tmp_path, monkeypatch)
    assert null_result.verdict == "NULL"
    assert teaches_result.verdict == "TEACHES"
    assert null_payload["detail"]["n_rows"] >= 1000
    assert teaches_payload["detail"]["n_rows"] >= 1000


def test_empty_feature_availability_propagates_leak_error(tmp_path: Path):
    states = _states("teacher")
    states[17]["feature_avail"] = {}
    ledger = tmp_path / "ledger.jsonl"
    with pytest.raises(LeakError, match="empty feature_avail"):
        student_gate.run_student_gate(
            states, _teacher, ledger_path=ledger, charge_spec="leak", name="leak", output_dir=tmp_path
        )
    assert not ledger.exists()


def test_runtime_unavailable_registered_input_is_refused(tmp_path: Path):
    def unsafe(_train: list[dict], test: dict, _inside: bool) -> float:
        return float(test["features"]["teacher"])

    unsafe.registered_inputs = {"tracking_feature": {"runtime_available": False}}
    with pytest.raises(ValueError, match="runtime_available=False"):
        student_gate.run_student_gate(
            _states("teacher"), unsafe, ledger_path=tmp_path / "ledger.jsonl", charge_spec="unsafe", name="unsafe", output_dir=tmp_path
        )
