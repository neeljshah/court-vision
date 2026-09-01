"""Tests for offline tracking-corpus re-scoring."""
import json
from pathlib import Path

import pandas as pd

from scripts.platformkit.corpus_rescore import _depth_probe, rescore_all


def _good_rows() -> list[dict[str, object]]:
    """Court-feet rows that also move: a frozen tracker is a liveness failure."""
    rows = []
    for frame in range(10):
        for track_id in range(6):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10 + 2 * track_id + 0.5 * frame, "y": 20 + track_id})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball",
                     "x": 47 + 0.5 * frame, "y": 25})
    return rows


def test_rescore_writes_deltas_detects_new_pass_and_appends_ledger(tmp_path: Path):
    tracking = tmp_path / "tracking"
    reports = tmp_path / "reports"
    game = tracking / "game-1"
    game.mkdir(parents=True)
    pd.DataFrame(_good_rows()).to_csv(game / "tracking_data.csv", index=False)
    previous = {"sport": "basketball", "config_version": "old", "passed": False,
                "coverage_pct": 0.5, "ball_valid_pct": 0.5, "oob_pct": 0.1}
    prior_path = reports / "basketball" / "game-1.json"
    prior_path.parent.mkdir(parents=True)
    prior_path.write_text(json.dumps(previous), encoding="utf-8")

    result = rescore_all(tracking, reports, {})

    assert result == {"games_rescored": 1, "newly_passing": 1, "newly_failing": 0}
    current = json.loads(prior_path.read_text(encoding="utf-8"))
    assert current["passed"] is True and current["config_version"] != "old"
    line = json.loads((reports / "rescore_ledger.jsonl").read_text(encoding="utf-8"))
    assert line["passed_before"] is False and line["passed_after"] is True
    assert line["metric_deltas"]["coverage_pct"] == 0.5
    assert line["metric_deltas"]["oob_pct"] == -0.1


def test_missing_depth_probe_is_skipped_cleanly(monkeypatch, tmp_path: Path):
    import scripts.platformkit.corpus_rescore as rescore

    def missing_module(_: str):
        raise ModuleNotFoundError("optional probe absent")

    monkeypatch.setattr(rescore.importlib, "import_module", missing_module)
    csv_path = tmp_path / "tracking_data.csv"
    pd.DataFrame(_good_rows()).to_csv(csv_path, index=False)
    assert _depth_probe(csv_path, "unavailable", {}) is None
