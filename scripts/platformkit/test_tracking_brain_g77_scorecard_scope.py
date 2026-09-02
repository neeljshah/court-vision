"""G77: scorecard aggregates coordinate profiles independently.

Run: python -m pytest scripts/platformkit/test_tracking_brain_g77_scorecard_scope.py -q
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from scripts.platformkit.tracking_brain import scorecard


_ROOT = Path(__file__).resolve().parents[2]
_INPUTS = _ROOT / "docs/evidence/tracking/g77_scorecard_scope/constructed_inputs.json"
_OUTPUTS = _ROOT / "docs/evidence/tracking/g77_scorecard_scope/constructed_outputs.json"
_REPLAY = _ROOT / "docs/evidence/tracking/g77_scorecard_scope/court_feet_replay.json"
_G72 = _ROOT / "docs/evidence/tracking/g72_metric_local_profile/court_feet_before_reports.json"


def _write_case(root: Path, reports: list[dict[str, object]], sport: str = "baseball") -> Path:
    folder = root / sport
    folder.mkdir(parents=True, exist_ok=True)
    for index, report in enumerate(reports):
        (folder / f"report_{index}.json").write_text(json.dumps(report), encoding="utf-8")
    return root


def _sha256(value: dict[str, object]) -> str:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_g77_scorecard_scopes_profiles_and_preserves_court_feet(tmp_path: Path) -> None:
    """All four constructed cases retain profile-specific counts and metrics."""
    cases = json.loads(_INPUTS.read_text(encoding="utf-8"))
    expected = json.loads(_OUTPUTS.read_text(encoding="utf-8"))
    court = scorecard("baseball", _write_case(tmp_path / "court", cases["court_feet_only"]))
    local = scorecard("baseball", _write_case(tmp_path / "local", cases["metric_local_only"]))
    mixed = scorecard("baseball", _write_case(tmp_path / "mixed", cases["mixed"]))
    empty = scorecard("baseball", _write_case(tmp_path / "empty", cases["empty"]))

    assert court["games_scored"] == 1 and court["pass_rate"] == 1.0
    assert local["coordinate_profiles"]["metric_local"]["games_scored"] == 1
    assert local["coordinate_profiles"]["metric_local"]["pass_rate"] == 0.0
    assert set(local["coordinate_profiles"]["metric_local"]["metric_medians"]) == {
        "coverage", "ball_valid"
    }
    mixed_court = mixed["coordinate_profiles"]["court_feet"]
    assert mixed["coordinate_profile"] == "court_feet"
    assert mixed_court["games_scored"] == court["games_scored"]
    assert mixed_court["pass_rate"] == court["pass_rate"]
    assert mixed_court["metric_medians"] == court["metric_medians"]
    assert mixed["coordinate_profiles"]["metric_local"]["games_scored"] == 1
    assert empty["games_scored"] == 0 and empty["pass_rate"] == 0.0
    for name, actual in {"court_feet_only": court, "metric_local_only": local,
                         "mixed": mixed, "empty": empty}.items():
        assert _sha256(actual) == expected[name]["sha256"]

    reports = {entry["name"]: entry for entry in json.loads(_G72.read_text(encoding="utf-8"))["reports"]}
    for expected_replay in json.loads(_REPLAY.read_text(encoding="utf-8")):
        source = reports[expected_replay["name"]]
        actual = scorecard(source["sport"], _write_case(
            tmp_path / "replay" / source["name"], [source["fields"]], source["sport"]
        ))
        assert _sha256(actual) == expected_replay["before_sha256"]
        assert expected_replay["before_sha256"] == expected_replay["after_sha256"]
