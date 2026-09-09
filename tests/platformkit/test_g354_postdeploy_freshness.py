"""G354 fix 1b: the post-deploy checker must judge freshness by START time.

A clip that STARTED before the producer deploy imported the old module even when
it FINISHED after it, so the finish-time rule swept such clips in and the sealed
checker reported 0.  The ledger has no start field; START is reconstructed as
`finished_at - seconds` (`scripts/platformkit/track_daemon.py:302-303,384`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[2] / "scripts" / "platformkit" / "tracking" / "g354_postdeploy_check.py"
EPOCH = 1000000

# One clip started 300 s BEFORE the epoch and finished 600 s after it; one started
# 500 s after it.  Only the second ran the deployed producer.
LEDGER = [
    {"game_id": "started_before", "sport": "basketball", "finished_at": EPOCH + 600, "seconds": 900},
    {"game_id": "started_after", "sport": "basketball", "finished_at": EPOCH + 800, "seconds": 300},
]


def _clip_store(root: Path, game_id: str, ball_rows: str | None = None) -> None:
    directory = root / game_id
    directory.mkdir(parents=True)
    (directory / "tracking_data.csv").write_text(
        "frame,bbox_x1,bbox_y1,bbox_x2,bbox_y2\n"
        + "".join(f"{f},100,100,200,300\n" for f in range(1, 6)),
        encoding="utf-8")
    (directory / "ball_tracking.csv").write_text(
        ball_rows if ball_rows is not None else
        "frame,timestamp,ball_x2d,ball_y2d,detected,live,ball_inferred,ball_x2d_px,ball_y2d_px\n"
        + "".join(f"{f},0.0,50,60,1,1,0,150,200\n" for f in range(1, 6)),
        encoding="utf-8")


def _run(tmp_path: Path, *extra: str) -> tuple[str, list[dict[str, str]]]:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in LEDGER), encoding="utf-8")
    root = tmp_path / "tracking"
    for row in LEDGER:
        _clip_store(root, str(row["game_id"]))
    postdeploy, rejoin = tmp_path / "postdeploy.csv", tmp_path / "rejoin.csv"
    completed = subprocess.run(
        [sys.executable, str(CHECKER), "--ledger", str(ledger), "--tracking-root", str(root),
         "--after-epoch", str(EPOCH), "--postdeploy", str(postdeploy), "--rejoin", str(rejoin), *extra],
        capture_output=True, text=True)
    import csv
    with postdeploy.open(encoding="utf-8", newline="") as handle:
        return completed.stdout, list(csv.DictReader(handle))


def test_start_time_is_the_default_freshness_rule(tmp_path):
    stdout, rows = _run(tmp_path)
    assert "FRESH_ENTRIES 000001" in stdout, stdout
    assert "EXCLUDED_STARTED_BEFORE_EPOCH 000001" in stdout, stdout
    # Only one fresh clip, so the >= 3 bar keeps the run from claiming a pass.
    assert "POSTDEPLOY_PASS 0" in stdout, stdout
    assert [row["game_id"] for row in rows] == ["started_before", "started_after"]


def test_finish_key_restores_the_weaker_rule(tmp_path):
    stdout, _ = _run(tmp_path, "--freshness-key", "finish")
    assert "FRESH_ENTRIES 000002" in stdout, stdout
    assert "EXCLUDED_STARTED_BEFORE_EPOCH 000000" in stdout, stdout


def _run_ledger(tmp_path: Path, ledger_rows: list[dict], skip_stores: frozenset = frozenset(),
                 ball_rows_by_game: dict | None = None) -> tuple[str, list[dict[str, str]]]:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in ledger_rows), encoding="utf-8")
    root = tmp_path / "tracking"
    for row in ledger_rows:
        game = str(row["game_id"])
        if game not in skip_stores:
            _clip_store(root, game, (ball_rows_by_game or {}).get(game))
    postdeploy, rejoin = tmp_path / "postdeploy.csv", tmp_path / "rejoin.csv"
    completed = subprocess.run(
        [sys.executable, str(CHECKER), "--ledger", str(ledger), "--tracking-root", str(root),
         "--after-epoch", str(EPOCH), "--postdeploy", str(postdeploy), "--rejoin", str(rejoin)],
        capture_output=True, text=True)
    import csv
    with postdeploy.open(encoding="utf-8", newline="") as handle:
        return completed.stdout, list(csv.DictReader(handle))


def test_missing_stores_excluded_from_judged_set(tmp_path):
    # 3 readable, passing clips + 2 clips whose store never landed (absent evidence,
    # not a bad result) must still clear the >= 3 / ratio bar.
    rows = [{"game_id": f"ok_{i}", "sport": "basketball", "finished_at": EPOCH + 700, "seconds": 200}
            for i in range(3)]
    rows += [{"game_id": f"missing_{i}", "sport": "basketball", "finished_at": EPOCH + 700, "seconds": 200}
             for i in range(2)]
    stdout, csv_rows = _run_ledger(tmp_path, rows, skip_stores=frozenset({"missing_0", "missing_1"}))
    assert "FRESH_ENTRIES 000005" in stdout, stdout
    assert "EXCLUDED_MISSING_STORE 000002" in stdout, stdout
    assert "POSTDEPLOY_PASS 1" in stdout, stdout
    by_game = {r["game_id"]: r for r in csv_rows}
    assert by_game["missing_0"]["status"] == "MISSING_TABLE"
    assert by_game["missing_0"]["excluded_reason"] == "MISSING_STORE"
    assert by_game["ok_0"]["status"] == "OK" and by_game["ok_0"]["ratio_pass"] == "1"
    assert by_game["ok_0"]["excluded_reason"] == ""


def test_ratio_above_limit_still_fails_with_missing_excluded(tmp_path):
    # A readable clip whose ball-pixel span blows the 1.5 ratio must still fail the
    # gate even once missing stores are filtered out of the judged set.
    bad_ball = ("frame,timestamp,ball_x2d,ball_y2d,detected,live,ball_inferred,ball_x2d_px,ball_y2d_px\n"
                + "".join(f"{f},0.0,50,60,1,1,0,{0 if f % 2 else 500},200\n" for f in range(1, 6)))
    rows = [{"game_id": f"ok_{i}", "sport": "basketball", "finished_at": EPOCH + 700, "seconds": 200}
            for i in range(2)]
    rows += [{"game_id": "bad_ratio", "sport": "basketball", "finished_at": EPOCH + 700, "seconds": 200}]
    stdout, csv_rows = _run_ledger(tmp_path, rows, ball_rows_by_game={"bad_ratio": bad_ball})
    assert "FRESH_ENTRIES 000003" in stdout, stdout
    assert "EXCLUDED_MISSING_STORE 000000" in stdout, stdout
    assert "POSTDEPLOY_PASS 0" in stdout, stdout
    by_game = {r["game_id"]: r for r in csv_rows}
    assert by_game["bad_ratio"]["status"] == "OK" and by_game["bad_ratio"]["ratio_pass"] == "0"


def test_every_row_carries_start_finish_and_duration(tmp_path):
    _, rows = _run(tmp_path)
    by_game = {row["game_id"]: row for row in rows}
    assert int(by_game["started_before"]["start_epoch"]) == EPOCH + 600 - 900
    assert int(by_game["started_after"]["start_epoch"]) == EPOCH + 800 - 300
    for row in rows:
        started = datetime.strptime(row["started_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        finished = datetime.strptime(row["finished_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert int(started.timestamp()) == int(row["start_epoch"])
        assert int(finished.timestamp()) - int(started.timestamp()) == int(row["duration_s"]) > 0
        # the pre-existing columns survive untouched
        assert row["status"] == "OK" and row["ratio_pass"] == "1"
