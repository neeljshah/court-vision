"""Focused tests for the data-fingerprint retraining loop."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.platformkit import retrain_loop


def _data_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "data"
    path = root / "tracking" / "game-1" / "tracking_data.csv"
    path.parent.mkdir(parents=True)
    path.write_text("frame,x\n1,2\n", encoding="utf-8")
    (root / "cache" / "ingame_grade_joined").mkdir(parents=True)
    parquet = root / "nba" / "player_tracking_games.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"fixture")
    monkeypatch.setattr(retrain_loop.pd, "read_parquet", lambda _: pd.DataFrame({"x": [1, 2]}))
    return root


def _write_reports(root: Path) -> None:
    reports = root / "ab_reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "teacher_student_minutes.json").write_text(
        json.dumps({"pooled": {"verdict": "IMPROVED", "delta": -0.25}}), encoding="utf-8"
    )
    (reports / "wp_oos_fixture.json").write_text(
        json.dumps({"pooled": {"delta": 0.015}}), encoding="utf-8"
    )


def _patch_stages(monkeypatch, calls: list[str], root: Path, failing: str | None = None) -> None:
    for name, module in (
        ("tracking_features", retrain_loop.tracking_features),
        ("tracking_load_state", retrain_loop.tracking_load_state),
        ("player_embeddings", retrain_loop.player_embeddings),
        ("teacher_student_ab", retrain_loop.teacher_student_ab),
        ("wp_diag_oos", retrain_loop.wp_diag_oos),
    ):
        def stage(name=name) -> None:
            calls.append(name)
            if name == "teacher_student_ab":
                _write_reports(root)
            if name == failing:
                raise RuntimeError("fixture failure")
        monkeypatch.setattr(module, "main", stage)


def test_changed_fingerprint_runs_stages_once_and_unchanged_skips(tmp_path, monkeypatch) -> None:
    root = _data_root(tmp_path, monkeypatch)
    calls: list[str] = []
    _patch_stages(monkeypatch, calls, root)

    retrain_loop.run_loop(max_passes=1, data_root=root, sleep_seconds=0)
    retrain_loop.run_loop(max_passes=1, data_root=root, sleep_seconds=0)
    changed = root / "tracking" / "game-2" / "tracking_data.csv"
    changed.parent.mkdir(parents=True)
    changed.write_text("frame,x\n1,3\n", encoding="utf-8")
    retrain_loop.run_loop(max_passes=1, data_root=root, sleep_seconds=0)

    assert calls == [
        "tracking_features", "tracking_load_state", "player_embeddings", "teacher_student_ab", "wp_diag_oos",
        "tracking_features", "tracking_load_state", "player_embeddings", "teacher_student_ab", "wp_diag_oos",
    ]
    ledger = (root / "ab_reports" / "retrain_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 2
    row = json.loads(ledger[-1])
    assert row["fingerprint"]["tracking_csv_count"] == 2
    assert row["ab_verdict"] == "IMPROVED"
    assert row["ab_delta"] == -0.25
    assert row["oos_pooled_delta"] == 0.015


def test_raising_stage_is_logged_and_does_not_kill_the_pass(tmp_path, monkeypatch, caplog) -> None:
    root = _data_root(tmp_path, monkeypatch)
    calls: list[str] = []
    _patch_stages(monkeypatch, calls, root, failing="tracking_load_state")

    retrain_loop.run_loop(max_passes=1, data_root=root, sleep_seconds=0)

    assert calls == ["tracking_features", "tracking_load_state", "player_embeddings", "teacher_student_ab", "wp_diag_oos"]
    assert "Retrain stage failed: tracking_load_state" in caplog.text
    assert (root / "ab_reports" / "retrain_ledger.jsonl").exists()
