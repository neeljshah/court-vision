"""Focused G360 tests for the deterministic cue and blind sheets."""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.court_presence_cue import court_presence
from scripts.platformkit.tracking.g360_court_presence_sheets import _sheet


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g360_prereg_2026-09-08.md"


def test_two_line_family_court_scores_above_synthetic_crowd():
    hsv = np.full((180, 320, 3), (20, 150, 160), dtype=np.uint8)
    court = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    cv2.line(court, (16, 30), (304, 30), (255, 255, 255), 2)
    cv2.line(court, (160, 8), (160, 172), (255, 255, 255), 2)
    crowd = np.full((180, 320, 3), 40, dtype=np.uint8)
    for x in range(12, 320, 24):
        cv2.circle(crowd, (x, 80 + (x % 3) * 12), 6, (90, 90, 90), -1)
    court_score, families, longest, surface = court_presence(court)
    crowd_score, _, _, _ = court_presence(crowd)
    assert families >= 2
    assert longest >= 320 * 0.08
    assert surface > 0.0
    assert court_score > crowd_score


def test_sheet_has_no_cue_or_prediction_value(tmp_path: Path, monkeypatch):
    drawn: list[str] = []
    original = cv2.putText

    def capture(image, text, *args, **kwargs):
        drawn.append(text)
        return original(image, text, *args, **kwargs)

    monkeypatch.setattr(cv2, "putText", capture)
    _sheet([np.full((180, 320, 3), value, dtype=np.uint8) for value in (20, 40, 60)],
           "0123456789abcdef", tmp_path / "sheet.jpg")
    assert (tmp_path / "sheet.jpg").stat().st_size <= 200_000
    assert drawn == ["FRAME 456789abcdef"]
    assert not any(word in drawn[0] for word in ("COURT", "NON_COURT", "ABSTAIN", "score", "surface"))


def test_preregistration_seal_normalizes_crlf_without_git_history():
    text = PREREG.read_text(encoding="utf-8").replace("\r\n", "\n")
    prefix, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert hashlib.sha256((prefix + "\n").encode("utf-8")).hexdigest() == seal.strip()
