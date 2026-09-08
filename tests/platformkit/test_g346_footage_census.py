import csv
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.platformkit import g346_footage_census as census_mod


class _Capture:
    """Synthetic VideoCapture: `frame_count` frames, `fail_index` always misses."""

    def __init__(self, frame_count: int, fail_index: int | None = None):
        self.frame_count = frame_count
        self.fail_index = fail_index
        self.position = 0

    def isOpened(self) -> bool:
        return True

    def get(self, property_id: int) -> float:
        if property_id == cv2.CAP_PROP_FRAME_COUNT:
            return float(self.frame_count)
        if property_id == cv2.CAP_PROP_FRAME_WIDTH:
            return 160.0
        if property_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return 90.0
        return 0.0

    def set(self, property_id: int, value: float) -> bool:
        if property_id == cv2.CAP_PROP_POS_FRAMES:
            self.position = int(value)
        return True

    def read(self):
        if self.position == self.fail_index:
            return False, None
        return True, np.full((90, 160, 3), 96, dtype=np.uint8)

    def release(self) -> None:
        pass


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_absent_ledger_is_a_hard_error(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    with pytest.raises(FileNotFoundError):
        census_mod.census(corpus, tmp_path / "no_such_ledger.jsonl", tmp_path / "out")


def test_valid_frames_below_requested_is_recorded(tmp_path: Path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    video = corpus / "basketball__game1_s10.mp4"
    video.write_bytes(b"0" * 1024)
    _write_ledger(tmp_path / "ledger.jsonl", [])
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: _Capture(frame_count=10, fail_index=0))

    census_mod.census(corpus, tmp_path / "ledger.jsonl", tmp_path / "out")

    with (tmp_path / "out" / "sealed_sections.csv").open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert int(row["valid_frames"]) < footage_liveness_sample_count()
    assert row["liveness"] in ("LIVE", "FROZEN")


def footage_liveness_sample_count() -> int:
    from scripts.platformkit import footage_liveness
    return footage_liveness.SAMPLE_COUNT


def test_rows_below_50_ledger_only_source_appears_as_absent_file(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()  # no matching file for the ledger-only key below
    _write_ledger(tmp_path / "ledger.jsonl", [
        {"game_id": "ghost_game_s5", "sport": "basketball", "rows": 3},
    ])

    census_mod.census(corpus, tmp_path / "ledger.jsonl", tmp_path / "out")

    with (tmp_path / "out" / "sealed_sections.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    absent = [row for row in rows if row["liveness"] == "ABSENT_FILE"]
    assert len(absent) == 1
    assert absent[0]["game_id"] == "ghost_game"
    assert absent[0]["ledger_rows"] == "%06d" % 3
    assert absent[0]["ledger_entry_present"] == "True"
