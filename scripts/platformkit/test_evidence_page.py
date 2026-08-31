"""Per-file tests for the multi-sport evidence page generator."""
import json

from scripts.platformkit.evidence_page import MARKER, generate


def _report(sport, passed, failures):
    return {"sport": sport, "n_frames": 100, "coverage_pct": 0.75,
            "det_per_frame": 8.0, "median_track_len": 30.0,
            "ball_valid_pct": 0.5, "jump_p95": 2.0, "oob_pct": 0.01,
            "passed": passed, "failures": failures}


def test_generates_marked_scoreboard_sport_pages_and_models(tmp_path):
    reports = tmp_path / "data" / "tracking_reports" / "basketball"
    reports.mkdir(parents=True)
    (reports / "game_a.json").write_text(json.dumps(_report("basketball", True, [])))
    (reports / "game_b.json").write_text(json.dumps(_report("basketball", False, ["coverage 0.20 < 0.60"])))
    ledger = reports.parent / "ledger.jsonl"
    ledger.write_text(json.dumps({"report": "game_a.json", "game_id": "NBA-001"}) + "\n")
    ab = tmp_path / "data" / "ab_reports"
    ab.mkdir(parents=True)
    (ab / "wp_oos_20260831.json").write_text(json.dumps({"walk_forward": {"brier": 0.193}}))
    demo = tmp_path / "docs" / "evidence" / "demos"
    demo.mkdir(parents=True)
    (demo / "NBA-001_demo.gif").write_bytes(b"GIF89a")

    generate(tmp_path)
    readme = (tmp_path / "docs" / "evidence" / "multisport" / "README.md").read_text()
    sport = (tmp_path / "docs" / "evidence" / "multisport" / "basketball.md").read_text()
    assert readme.startswith(MARKER)
    assert "| [basketball](basketball.md) | 2 | 50%" in readme
    assert "coverage 0.20 < 0.60" in readme
    assert "No betting edge or ROI is claimed" in readme
    assert sport.startswith(MARKER)
    assert "| NBA-001 | 100 | PASS" in sport
    assert "[GIF](../demos/NBA-001_demo.gif)" in sport
