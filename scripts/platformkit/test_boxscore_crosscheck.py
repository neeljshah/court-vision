import csv
import json
from pathlib import Path

from scripts.platformkit.boxscore_crosscheck import crosscheck


def _write_fixture(directory: Path, rows: list[dict[str, object]]) -> tuple[Path, Path]:
    tracking = directory / "tracking.csv"
    with tracking.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["frame", "track_id", "jersey_number", "event"])
        writer.writeheader()
        writer.writerows(rows)
    boxscore = directory / "boxscore_123.json"
    boxscore.write_text(json.dumps({"game_id": "123", "players": [
        {"jersey_num": "1", "min": 30, "fga": 3},
        {"jersey_num": "2", "min": 20, "fga": 2},
        {"jersey_num": "3", "min": 10, "fga": 1},
        {"jersey_num": "99", "min": 0, "fga": 0},
    ]}), encoding="utf-8")
    return tracking, boxscore


def test_crosscheck_matches_official_participation_and_shots(tmp_path: Path) -> None:
    rows = []
    for jersey, frames in (("1", 30), ("2", 20), ("3", 10)):
        rows.extend(
            {
                "frame": frame,
                "track_id": jersey,
                "jersey_number": jersey,
                "event": "shot" if frame < int(jersey) else "",
            }
            for frame in range(frames)
        )
    tracking, boxscore = _write_fixture(tmp_path, rows)

    result = crosscheck(tracking, boxscore)

    assert result["game_id"] == "123"
    assert result["jersey_match_pct"] == 1.0
    assert result["minutes_spearman"] == 1.0
    assert result["verdict"] == "OK"
    assert result["shots"]["box_fga"] == 6
    assert result["shots"]["tracking_count"] == 6
    assert result["shots"]["within_tolerance"] is True


def test_crosscheck_is_weak_at_the_jersey_threshold(tmp_path: Path) -> None:
    tracking, boxscore = _write_fixture(tmp_path, [
        {"frame": frame, "track_id": "one", "jersey_number": "1", "event": ""}
        for frame in range(30)
    ])

    result = crosscheck(tracking, boxscore)

    assert result["jersey_match_pct"] == 0.3333
    assert result["minutes_spearman"] is None
    assert result["verdict"] == "WEAK"


def test_crosscheck_fails_when_tracking_has_no_official_jerseys(tmp_path: Path) -> None:
    tracking, boxscore = _write_fixture(tmp_path, [
        {"frame": 1, "track_id": "x", "jersey_number": "88", "event": ""},
        {"frame": 2, "track_id": "y", "jersey_number": "77", "event": ""},
    ])

    result = crosscheck(tracking, boxscore)

    assert result["jersey_match_pct"] == 0.0
    assert result["minutes_spearman"] is None
    assert result["verdict"] == "FAIL"
