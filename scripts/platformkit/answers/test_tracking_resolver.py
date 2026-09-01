"""Per-file test for answers.tracking_resolver.

Run: python -m pytest scripts/platformkit/answers/test_tracking_resolver.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.answers import tracking_resolver as tr

# tennis thresholds (tracking_harness.SPORTS): ball_valid_min .20, coverage_min
# .90, oob_max .08, jump_p95_max 8.0.  Medians below are coverage .96,
# ball_valid .10, jump_p95 5.0, oob .01 -> normalized threshold margins
# +0.067 / -0.500 / +0.375 / +0.875, so ball_valid is unambiguously worst.
_TENNIS = [
    ("t1", {"coverage_pct": 0.95, "ball_valid_pct": 0.30, "jump_p95": 4.0,
            "oob_pct": 0.02, "passed": True, "failures": []}),
    ("t2", {"coverage_pct": 0.96, "ball_valid_pct": 0.10, "jump_p95": 5.0,
            "oob_pct": 0.01, "passed": False, "failures": ["ball_valid 0.10 < 0.2"]}),
    ("t3", {"coverage_pct": 0.97, "ball_valid_pct": 0.05, "jump_p95": 6.0,
            "oob_pct": 0.00, "passed": False, "failures": ["ball_valid 0.05 < 0.2"]}),
]


@pytest.fixture()
def reports(tmp_path: Path) -> Path:
    """A miniature data/tracking_reports tree: 3 tennis games, 1 soccer game,
    a 2-run ledger for t2, and one provenance row."""
    (tmp_path / "tennis").mkdir()
    for game_id, body in _TENNIS:
        (tmp_path / "tennis" / f"{game_id}.json").write_text(
            json.dumps({"sport": "tennis", "n_frames": 1000, **body}), encoding="utf-8")
    (tmp_path / "soccer").mkdir()
    (tmp_path / "soccer" / "s1.json").write_text(json.dumps({
        "sport": "soccer", "n_frames": 900, "coverage_pct": 0.99, "ball_valid_pct": 0.90,
        "jump_p95": 1.0, "oob_pct": 0.0, "passed": True, "failures": []}), encoding="utf-8")
    before = dict(_TENNIS[1][1], sport="tennis", n_frames=1000)
    after = dict(before, ball_valid_pct=0.25, passed=True,
                 failures=["jump_p95 9.0 > 8.0"], jump_p95=9.0)
    (tmp_path / "ledger.jsonl").write_text("\n".join([
        json.dumps({"ts": "2026-08-01T00:00:00Z", "game_id": "t2", "sport": "tennis",
                    "adapter_version": "aaa", "report": before}),
        json.dumps({"ts": "2026-08-30T00:00:00Z", "game_id": "t2", "sport": "tennis",
                    "adapter_version": "bbb", "report": after}),
    ]) + "\n", encoding="utf-8")
    (tmp_path / "provenance.jsonl").write_text(json.dumps({
        "game_id": "t2", "sport": "tennis", "source_url": "https://example/clip.mp4",
        "video_path": "C:\\\\Users\\\\x\\\\footage\\\\t2.mp4", "sha256": "deadbeef",
        "size_bytes": 42, "capture_ts": "2026-08-30T01:00:00Z",
        "adapter_module": "domains.tennis.tracking.adapter", "adapter_version": "bbb",
    }) + "\n", encoding="utf-8")
    return tmp_path


def test_scoreboard_math_is_exact(reports: Path) -> None:
    env = tr.scoreboard("tennis", reports)
    assert env["status"] == "ok"
    assert env["games_scored"] == 3
    assert env["pass_rate"] == pytest.approx(1 / 3)
    assert env["metric_medians"] == pytest.approx(
        {"coverage": 0.96, "ball_valid": 0.10, "jump_p95": 5.0, "oob": 0.01})
    assert env["games"] == ["t1", "t2", "t3"]
    assert env["as_of"] is not None


def test_worst_metric_picks_the_largest_threshold_shortfall(reports: Path) -> None:
    env = tr.worst_metric("tennis", reports)
    assert env["status"] == "ok"
    assert env["worst_metric"] == "ball_valid"
    assert env["worst_metric_median"] == pytest.approx(0.10)
    assert env["repair_rule"] == tr.RULES["ball_valid"]
    # soccer clears every threshold, but "worst" is still the smallest margin.
    assert tr.worst_metric("soccer", reports)["worst_metric"] == "coverage"


def test_bar_progress_counts_toward_ten(reports: Path) -> None:
    env = tr.bar_progress("tennis", reports)
    assert (env["games_scored"], env["bar"], env["games_needed"], env["bar_met"]) == (3, 10, 7, False)
    assert tr.bar_progress("tennis", reports, bar=2)["bar_met"] is True


def test_unknown_sport_fails_closed(reports: Path) -> None:
    for env in (tr.scoreboard("cricket", reports), tr.worst_metric("curling", reports),
                tr.bar_progress("cricket", reports)):
        assert env["status"] == "no_data"
        assert "unknown sport" in env["note"]
    # A tracked sport with no reports on file is also no_data, not a zero card.
    assert tr.scoreboard("basketball", reports)["status"] == "no_data"


def test_game_report_and_missing_game(reports: Path) -> None:
    env = tr.game_report("t1", reports_dir=reports)
    assert env["status"] == "ok"
    assert env["report"]["coverage_pct"] == 0.95
    assert env["sport"] == "tennis"
    assert tr.game_report("nope", reports_dir=reports)["status"] == "no_data"


def test_changed_diffs_the_two_most_recent_runs(reports: Path) -> None:
    env = tr.changed("t2", reports)
    assert env["status"] == "ok"
    assert (env["adapter_version_before"], env["adapter_version_after"]) == ("aaa", "bbb")
    assert env["metric_deltas"]["ball_valid_pct"]["delta"] == pytest.approx(0.15)
    assert env["metric_deltas"]["jump_p95"]["delta"] == pytest.approx(4.0)
    assert env["passed_before"] is False and env["passed_after"] is True
    assert env["failures_resolved"] == ["ball_valid 0.10 < 0.2"]
    assert env["failures_new"] == ["jump_p95 9.0 > 8.0"]
    # One run (or none) cannot show a delta.
    assert tr.changed("t1", reports)["status"] == "no_data"


def test_provenance_names_the_footage_without_leaking_a_drive_path(reports: Path) -> None:
    env = tr.provenance("t2", reports)
    assert env["status"] == "ok"
    assert env["source_url"] == "https://example/clip.mp4"
    assert env["sha256"] == "deadbeef"
    assert env["video_name"] == "t2.mp4"
    assert ":\\" not in json.dumps(env) and ":/" not in json.dumps(env).replace("https://", "")
    assert tr.provenance("t1", reports)["status"] == "no_data"


def test_routing(reports: Path) -> None:
    assert tr.resolve("worst metric for tennis", reports_dir=reports)["worst_metric"] == "ball_valid"
    assert tr.resolve("how many games does tennis have?", reports_dir=reports)["games_needed"] == 7
    assert tr.resolve("what footage produced t2", reports_dir=reports)["video_name"] == "t2.mp4"
    assert tr.resolve("what changed for t2 after the adapter fix",
                      reports_dir=reports)["status"] == "ok"
    assert tr.resolve("quality report for t1", reports_dir=reports)["game_id"] == "t1"
    assert tr.resolve("tennis tracking scoreboard", reports_dir=reports)["games_scored"] == 3
    assert tr.resolve("how is tracking going?", reports_dir=reports)["status"] == "no_data"


def test_every_envelope_carries_the_self_consistency_caveat(reports: Path) -> None:
    envelopes = [
        tr.scoreboard("tennis", reports), tr.scoreboard("cricket", reports),
        tr.worst_metric("tennis", reports), tr.bar_progress("tennis", reports),
        tr.game_report("t1", reports_dir=reports), tr.game_report("nope", reports_dir=reports),
        tr.changed("t2", reports), tr.changed("t1", reports),
        tr.provenance("t2", reports), tr.provenance("t1", reports),
        tr.resolve("", reports_dir=reports), tr.resolve("provenance", reports_dir=reports),
        tr.resolve("what changed", reports_dir=reports),
    ]
    for env in envelopes:
        assert env["caveat"] == tr.CAVEAT
        assert "SELF-CONSISTENCY" in env["caveat"] and "not accuracy" in env["caveat"]
        assert env["status"] in {"ok", "no_data", "not_supported", "refused", "ambiguous"}
        assert env["category"] == "tracking_quality"
        assert env["source_artifact"].startswith("data/tracking_reports/")
