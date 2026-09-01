from __future__ import annotations

import json

from scripts.platformkit import tracking_regression


def _baseline(path, metrics):
    path.write_text(json.dumps({"schema_version": 1, "sports": {"tennis": metrics}}),
                    encoding="utf-8")


def _reference_clip(tmp_path):
    clip = tmp_path / "reference" / "tennis" / "clip.mp4"
    clip.parent.mkdir(parents=True)
    clip.touch()
    return clip


def test_seeded_degradation_is_reported(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    _baseline(baseline, {"coverage_pct": 0.9, "jump_p95": 2.0})
    _reference_clip(tmp_path)
    monkeypatch.setattr(tracking_regression, "_track_clip", lambda *args: {
        "coverage_pct": 0.7, "jump_p95": 3.0,
    })

    result = tracking_regression.run_reference_regression(baseline, tmp_path / "reference")

    assert result["tennis"]["coverage_pct"] == (0.9, 0.7, "regressed")
    assert result["tennis"]["jump_p95"] == (2.0, 3.0, "regressed")


def test_improvement_is_not_reported_as_regression(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    _baseline(baseline, {"coverage_pct": 0.7, "jump_p95": 3.0})
    _reference_clip(tmp_path)
    monkeypatch.setattr(tracking_regression, "_track_clip", lambda *args: {
        "coverage_pct": 0.9, "jump_p95": 2.0,
    })

    result = tracking_regression.run_reference_regression(baseline, tmp_path / "reference")

    assert all(verdict != "regressed" for _, _, verdict in result["tennis"].values())
    assert result["tennis"]["jump_p95"][2] == "improved"
