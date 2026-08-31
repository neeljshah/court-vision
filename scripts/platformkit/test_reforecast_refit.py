"""Focused synthetic coverage for full-corpus reforecast refitting."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit import reforecast_refit


def _write_corpus(root: Path) -> Path:
    store = root / "ingame_grade_joined"
    store.mkdir(parents=True)
    path = store / "ticks.jsonl"
    rows = []
    for day in range(10):
        for game_index in range(6):
            outcome = float(game_index % 2)
            rows.append({
                "game_id": "NBA_%02d_%02d" % (day, game_index),
                "timestamp": "2026-01-%02dT12:00:00Z" % (day + 1),
                "model_prob": 0.8 if outcome else 0.2,
                "outcome": outcome,
            })
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="ascii")
    return root


def test_full_corpus_writes_monotone_serving_artifact_and_ledger(tmp_path: Path) -> None:
    cache = _write_corpus(tmp_path / "cache")
    result = reforecast_refit.replay_and_refit("v7", cache_root=cache, output_root=tmp_path / "data")

    assert result["status"] == "OK"
    artifact_path = tmp_path / "data" / "models_calib" / "serving_isotonic_nba_v7.json"
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="ascii"))
    assert isinstance(artifact["x_thresholds"], list)
    assert isinstance(artifact["y_thresholds"], list)
    assert all(a <= b for a, b in zip(artifact["y_thresholds"], artifact["y_thresholds"][1:]))
    assert artifact["n_reforecast_ticks"] == 60
    assert artifact["verification"]["raw"]["murphy"]["brier"] is not None

    ledger = tmp_path / "data" / "ab_reports" / "reforecast_ledger.jsonl"
    lines = ledger.read_text(encoding="ascii").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["version_tag"] == "v7"
    assert row["sport"] == "nba"
    assert row["reforecast_ticks"] == 60
    assert row["brier_raw"] is not None
    assert row["murphy_reforecast_calibrated"]["resolution"] is not None

