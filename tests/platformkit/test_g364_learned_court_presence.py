"""Focused construct tests for the prepared G364 learned court-presence lane."""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.platformkit.tracking.g364_sampler import (assert_game_disjoint, evenly_pick,
                                                        interior_indices, sample_sections)
from scripts.platformkit.tracking.g364_sheets import sheet
from scripts.platformkit.tracking.g364_train import decisions, fit_head


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g364_prereg_2026-09-10.md"


def test_separable_synthetic_embeddings_train_a_linear_head():
    features = np.vstack((np.tile((3.0, 0.0), (8, 1)), np.tile((-3.0, 0.0), (8, 1))))
    labels = ["USABLE_COURT"] * 8 + ["CLOSEUP"] * 8
    model = fit_head(features, labels)
    assert decisions(model, features, 0.05).count("COURT") == 8
    assert decisions(model, features, 0.05).count("NON_COURT") == 8


def test_sampler_is_interior_and_never_a_head_slice():
    indices = interior_indices(101, 12)
    assert len(indices) == 12 and indices[0] > 0 and indices[-1] < 100
    rows = [{"section_id": "s", "frame_index": str(index)} for index in range(100)]
    selected = evenly_pick(rows, 12)
    assert int(selected[0]["frame_index"]) > 0
    assert int(selected[-1]["frame_index"]) < 99
    expanded = sample_sections([{"source_sha256": "a" * 64, "source_path": "video.mp4",
                                 "section_id": "s", "game_id": "g", "competition": "nba",
                                 "frame_count": "101"}])
    assert len(expanded) == 12 and int(expanded[0]["frame_index"]) > 0


def test_sheet_writes_no_score_or_prediction(tmp_path: Path, monkeypatch):
    drawn: list[str] = []
    original = cv2.putText

    def capture(image, text, *args, **kwargs):
        drawn.append(text)
        return original(image, text, *args, **kwargs)

    monkeypatch.setattr(cv2, "putText", capture)
    sheet([np.full((180, 320, 3), value, dtype=np.uint8) for value in (20, 40, 60)],
          "a" * 64 + ":section:000100", tmp_path / "sheet.jpg")
    assert (tmp_path / "sheet.jpg").stat().st_size <= 200_000
    assert drawn == ["FRAME ction:000100"]
    assert not any(word in drawn[0].lower() for word in ("score", "court", "non_court", "abstain"))


def test_validation_games_are_disjoint_from_development():
    development = [{"game_id": "dev-1"}, {"game_id": "dev-2"}]
    assert_game_disjoint(development, [{"game_id": "val-1"}])
    with pytest.raises(ValueError, match="overlap"):
        assert_game_disjoint(development, [{"game_id": "dev-2"}])


def test_preregistration_seal_normalizes_crlf_without_git_history():
    text = PREREG.read_text(encoding="utf-8").replace("\r\n", "\n")
    prefix, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert hashlib.sha256((prefix + "\n").encode("utf-8")).hexdigest() == seal.strip()


def test_census_split_is_seeded_and_game_disjoint():
    from scripts.platformkit.tracking.g364_census import parse_unit, split

    unit = parse_unit("gleague-_fl2i6vToTM_s3699", "basketball")
    assert unit["video_id"] == "_fl2i6vToTM" and unit["offset_s"] == "3699"
    assert unit["competition"] == "basketball/gleague"
    assert parse_unit("wnba_01_1080p", "wnba") is None
    eligible = [{"game_id": "g%d" % game, "offset_s": str(90 + 1200 * index),
                 "competition": "c%d" % (game % 3), "section_id": "g%d_s%d" % (game, index)}
                for game in range(6) for index in range(4)]
    development, validation = split(eligible, 3, 3, 2)
    assert_game_disjoint(development, validation)
    assert len(development) == 6 and len(validation) == 6
    assert split(eligible, 3, 3, 2)[0] == development
