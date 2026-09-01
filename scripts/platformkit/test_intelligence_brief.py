"""Per-file test: python -m pytest scripts/platformkit/test_intelligence_brief.py -q"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from scripts.platformkit.intelligence_brief import (KNOWN, NO_CLAIM, build, canon, collect_signals,
                                                    render_sport, worst_failure, write_briefs)

TENNIS_REPORT = {
    "sport": "tennis", "n_frames": 4224, "coverage_pct": 1.0, "ball_valid_pct": 0.0,
    "jump_p95": 40.17, "passed": False,
    "failures": ["ball_valid 0.00 < 0.2", "jump_p95 40.2 > 8.0"],
}
WNBA_REPORT = {"sport": "basketball", "n_frames": 900, "passed": True, "failures": []}
NBA_AB = {"sport": "NBA", "folds": [{"verdicts": {"vs_market": "TRAIL"}}],
          "screens": {"pace_gap": {"verdict": "INSUFFICIENT"}}}
MLB_AB = {"by_sport": {"mlb": {"note": "ONLY OOS DELTAS COUNT"}}}


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Fixture artifact tree: tennis + wnba tracking, nba + mlb ab_reports, one ledger."""
    tracking, ab_dir, out = tmp_path / "tracking", tmp_path / "ab", tmp_path / "out"
    (tracking / "tennis").mkdir(parents=True)
    (tracking / "wnba").mkdir(parents=True)
    ab_dir.mkdir()
    (tracking / "tennis" / "tennis_03.json").write_text(json.dumps(TENNIS_REPORT), encoding="utf-8")
    (tracking / "wnba" / "wnba_g1.json").write_text(json.dumps(WNBA_REPORT), encoding="utf-8")
    (ab_dir / "walkforward_nba.json").write_text(json.dumps(NBA_AB), encoding="utf-8")
    (ab_dir / "window_replay.json").write_text(json.dumps(MLB_AB), encoding="utf-8")
    (ab_dir / "foundry_ledger.jsonl").write_text(
        json.dumps({"sport": "nba", "signal": "b2b_speed_drop", "grade": "FLAT", "lift": 0.0047}) + "\n",
        encoding="utf-8")
    return tracking, ab_dir, out


def test_canon_maps_aliases_and_rejects_unknown() -> None:
    assert canon("basketball") == "nba" and canon("KXMLBGAME") == "mlb"
    assert canon("soccer_intl") == "soccer" and canon("wnba") == "wnba"
    assert canon("cricket") is None and canon(None) is None


def test_worst_failure_picks_the_largest_relative_miss() -> None:
    assert worst_failure(TENNIS_REPORT["failures"]) == "jump_p95 40.2 > 8.0"
    assert worst_failure([]) is None


def test_tennis_brief_quotes_fixture_values_and_source_filenames(tree) -> None:
    tracking, ab_dir, out = tree
    write_briefs(out, tracking, ab_dir)
    text = (out / "tennis.md").read_text(encoding="utf-8")
    assert "4224" in text and "ball_valid 0.00 < 0.2" in text
    assert "jump_p95 40.2 > 8.0" in text
    assert "tennis/tennis_03.json" in text
    assert "Pass rate: 0/1" in text
    assert "## 4. Known limits" in text and "## 5. Open questions" in text
    assert "10-game bar is not met" in text


def test_model_and_signal_sections_cite_their_files(tree) -> None:
    tracking, ab_dir, out = tree
    write_briefs(out, tracking, ab_dir)
    nba = (out / "nba.md").read_text(encoding="utf-8")
    assert "TRAIL" in nba and "walkforward_nba.json" in nba
    assert "b2b_speed_drop" in nba and "FLAT" in nba and "foundry_ledger.jsonl" in nba
    assert "INSUFFICIENT" in nba.split("## 4. Known limits")[1]
    mlb = (out / "mlb.md").read_text(encoding="utf-8")
    assert "ONLY OOS DELTAS COUNT" in mlb and "window_replay.json" in mlb


def test_wnba_directory_beats_the_in_file_sport_token(tree) -> None:
    tracking, ab_dir, out = tree
    write_briefs(out, tracking, ab_dir)
    text = (out / "wnba.md").read_text(encoding="utf-8")
    assert "wnba/wnba_g1.json" in text and "Pass rate: 1/1" in text
    assert "the file's `sport` field says" in text


def test_sport_with_no_data_gets_an_honest_empty_brief(tree) -> None:
    tracking, ab_dir, out = tree
    write_briefs(out, tracking, ab_dir)
    text = (out / "nfl.md").read_text(encoding="utf-8")
    assert text.count("UNKNOWN") >= 3
    assert "No report under `data/tracking_reports/` maps to nfl." in text
    assert "No failing metric and no INSUFFICIENT/INVALID verdict" in text


def test_index_lists_every_known_sport(tree) -> None:
    tracking, ab_dir, out = tree
    write_briefs(out, tracking, ab_dir)
    index = (out / "index.md").read_text(encoding="utf-8")
    for sport in KNOWN:
        assert f"[{sport}]({sport}.md)" in index


def test_regeneration_is_byte_stable_and_leaves_mtimes_alone(tree) -> None:
    tracking, ab_dir, out = tree
    first = {path: path.read_bytes() for path in write_briefs(out, tracking, ab_dir)}
    stamps = {path: path.stat().st_mtime_ns for path in first}
    time.sleep(0.01)
    second = {path: path.read_bytes() for path in write_briefs(out, tracking, ab_dir)}
    assert first == second
    assert stamps == {path: path.stat().st_mtime_ns for path in second}


def test_stale_artifact_becomes_an_open_question(tree) -> None:
    tracking, ab_dir, out = tree
    old = tracking / "tennis" / "tennis_03.json"
    stale = time.time() - 30 * 86400
    os.utime(old, (stale, stale))
    write_briefs(out, tracking, ab_dir)
    text = (out / "tennis.md").read_text(encoding="utf-8")
    assert "days older than the newest artifact" in text


def test_empty_tree_still_renders_every_brief(tmp_path: Path) -> None:
    out = tmp_path / "out"
    written = write_briefs(out, tmp_path / "missing", tmp_path / "gone")
    assert len(written) == len(KNOWN) + 1
    assert "no artifacts" in (out / "index.md").read_text(encoding="utf-8")


def test_signals_keep_only_the_last_row_per_sport_signal(tmp_path: Path) -> None:
    ab_dir = tmp_path / "ab"
    ab_dir.mkdir()
    (ab_dir / "foundry_ledger.jsonl").write_text(
        json.dumps({"sport": "nba", "signal": "s1", "grade": "FLAT"}) + "\n"
        + "not json\n"
        + json.dumps({"sport": "nba", "signal": "s1", "grade": "SHIP"}) + "\n", encoding="utf-8")
    rows = collect_signals(ab_dir)["nba"]
    assert len(rows) == 1 and rows[0]["state"] == "SHIP"


def test_no_edge_language_in_any_generated_brief(tree) -> None:
    tracking, ab_dir, out = tree
    banned = ("roi", "profit", "bankroll", "edge ", "+18.38", "78.11", "0.119", "54.57")
    for path in write_briefs(out, tracking, ab_dir):
        # The NO_CLAIM disclaimer names those words in order to disclaim them.
        body = "\n".join(line for line in path.read_text(encoding="utf-8").lower().splitlines()
                         if NO_CLAIM.lower() not in line)
        for token in banned:
            assert token not in body, f"{path.name} contains {token!r}"


def test_build_reads_the_real_repo_tree_without_error() -> None:
    bundle = build()
    assert set(bundle) == {"tracking", "models", "signals", "mtimes", "as_of"}
    assert all(canon(sport) == sport for sport in bundle["tracking"])
    assert render_sport("tennis", bundle).startswith("# Intelligence brief -- tennis")
