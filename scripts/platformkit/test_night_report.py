"""Tests for the local-only overnight tracking morning report."""

import json

from scripts.platformkit.night_report import build_report


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_report_prioritizes_harness_passes_and_human_actions(tmp_path):
    tracking = tmp_path / "track.jsonl"
    bridge = tmp_path / "bridge.jsonl"
    supervisor = tmp_path / "supervisor.json"
    _write_jsonl(tracking, [
        {"game_id": "nba-pass", "sport": "nba", "status": "tracked", "rows": 650,
         "passed": True, "failures": [], "seconds": 10},
        {"game_id": "nba-not-pass", "sport": "nba", "status": "tracked", "rows": 900,
         "passed": False, "failures": ["coordinate_contract missing"], "seconds": 10},
        {"game_id": "wnba-thin", "sport": "wnba", "status": "thin", "rows": 510,
         "passed": False, "failures": ["low coverage"], "seconds": 10},
    ])
    _write_jsonl(bridge, [
        {"game_id": "a", "sport": "nba", "status": "staged"},
        {"game_id": "b", "sport": "nba", "status": "failed: no source"},
        {"game_id": "c", "sport": "nba", "status": "failed: no source"},
        {"game_id": "d", "sport": "wnba", "status": "failed: blocked"},
    ])
    supervisor.write_text(json.dumps({"tracked_games": 2, "lanes": {
        "nba": {"untracked": 3, "alive": True}, "wnba": {"untracked": 5, "alive": False},
    }}), encoding="utf-8")

    report = build_report(tracking, bridge, supervisor)

    assert "HEADLINE: 1 games PASSING the harness." in report
    assert ">=500 rows does NOT mean a game PASSES the harness." in report
    assert "- lane not alive: wnba" in report
    assert "- zero passing games: wnba" in report
    assert "- coordinate_contract: nba-not-pass (coordinate_contract missing)" in report
    assert "nba: tracked=2 thin=0 PASSING=1 best_rows=900" in report
    assert "wnba: tracked=0 thin=1 PASSING=0 best_rows=510" in report
    assert "nba: staged=1 failed=2 top_failures=no source (2)" in report
    assert "tracked_games=2 alive_lanes=nba total_queue_depth=8" in report
    assert report.encode("ascii")


def test_report_gracefully_handles_missing_and_malformed_inputs(tmp_path):
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text("not json\n[]", encoding="utf-8")

    report = build_report(malformed, tmp_path / "missing.jsonl", tmp_path / "missing.json")

    assert "HEADLINE: 0 games PASSING the harness." in report
    assert "TRACKING HARNESS\nno data (empty or malformed)" in report
    assert "FOOTAGE BRIDGE\nno data (file missing)" in report
    assert "BRIDGE SUPERVISOR\nno data (file missing)" in report
    assert "WHAT NEEDS A HUMAN\n-------------------\n- None." in report


def test_preserved_image_corpus_is_reported_separately(tmp_path):
    """A declared image-space game is not a broken run. Reporting it only as
    PASSING=0 makes a working pipeline look dead to whoever reads this first."""
    from scripts.platformkit.night_report import build_report

    ledger = tmp_path / "track_daemon_ledger.jsonl"
    ledger.write_text("\n".join([
        json.dumps({"game_id": "a", "sport": "football", "status": "tracked",
                    "rows": 58652, "passed": False,
                    "failures": ["coordinate_contract: rows declare "
                                 "coordinate_space image_px"]}),
        json.dumps({"game_id": "b", "sport": "tennis", "status": "tracked",
                    "rows": 900, "passed": False,
                    "failures": ["coverage 0.67 < 0.90"]}),
    ]), encoding="utf-8")

    report = build_report(tracking_path=ledger,
                          bridge_path=tmp_path / "absent.jsonl",
                          supervisor_path=tmp_path / "absent.json")

    assert "PRESERVED DETECTION CORPUS" in report
    assert "1 games, 58,652 rows" in report
    assert "NOT broken runs" in report


def test_report_counts_old_and_g15b_rows_and_keeps_escalation(tmp_path):
    tracking = tmp_path / "track.jsonl"
    _write_jsonl(tracking, [
        {"game_id": "old", "sport": "nba", "status": "tracked", "rows": 700,
         "passed": True, "failures": []},
        {"game_id": "new", "sport": "nba", "status": "tracked", "adjudicated": True,
         "rows": 900, "passed": False,
         "failure_heads": ["coordinate_contract missing"]},
    ])

    report = build_report(tracking, tmp_path / "missing.jsonl", tmp_path / "missing.json")

    assert "nba: tracked=2 thin=0 PASSING=1 best_rows=900" in report
    assert "- coordinate_contract: new (coordinate_contract missing)" in report
