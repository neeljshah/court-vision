"""Construct tests for G350's blind-sheet and confusion scorer contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.platformkit.tracking.g350_wide_cue_score import cohen_kappa, score
from scripts.platformkit.tracking.g350_wide_cue_sheets import _sheet

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g350_prereg_2026-09-08.md"


def _primary(unit_id: str, terra: str, sol: str) -> list[dict[str, str]]:
    return [{"unit_id": unit_id, "rater": "terra", "label": terra},
            {"unit_id": unit_id, "rater": "sol", "label": sol}]


def test_hand_pinned_twelve_shot_confusion_kappa_and_intervals():
    predictions = ["WIDE"] * 5 + ["CLOSEUP"] * 2 + ["CROWD"] * 2 + ["UNKNOWN"] * 3
    references = ["USABLE_WIDE", "USABLE_WIDE", "USABLE_WIDE", "USABLE_WIDE", "CLOSEUP",
                  "USABLE_WIDE", "CLOSEUP", "CROWD_GRAPHICS", "CROWD_GRAPHICS", "UNKNOWN",
                  "CLOSEUP", "USABLE_WIDE"]
    selected = [{"unit_id": "u%02d" % index, "predicted_class": prediction}
                for index, prediction in enumerate(predictions)]
    ratings: list[dict[str, str]] = []
    for index, label in enumerate(references):
        ratings.extend(_primary("u%02d" % index, label, label))
    rows, summary = score(selected, ratings, [])
    counts = {(row["router_class"], row["reference_label"]): row["count"] for row in rows}
    assert counts[("WIDE", "USABLE_WIDE")] == "000004"
    assert counts[("WIDE", "CLOSEUP")] == "000001"
    assert summary["n"] == 12
    assert summary["kappa"] == pytest.approx(1.0)
    assert summary["precision"] == pytest.approx(0.8)
    assert summary["recall"] == pytest.approx(4 / 6)
    assert summary["abstention_share"] == pytest.approx(3 / 12)
    assert summary["precision_wilson"] == pytest.approx((0.3755346298, 0.9637758914))
    assert cohen_kappa(["USABLE_WIDE", "USABLE_WIDE", "CLOSEUP", "CLOSEUP"],
                       ["USABLE_WIDE", "CLOSEUP", "CLOSEUP", "CLOSEUP"]) == pytest.approx(0.5)


def test_blind_sheet_draws_only_unit_identity_not_router_class(tmp_path: Path, monkeypatch):
    drawn: list[str] = []
    original = cv2.putText

    def capture(image, text, *args, **kwargs):
        drawn.append(text)
        return original(image, text, *args, **kwargs)

    monkeypatch.setattr(cv2, "putText", capture)
    frame_map = {index: np.full((180, 320, 3), index * 20, dtype=np.uint8) for index in range(4)}
    row = {"unit_id": "a" * 64 + ":000001", "representative_frame": "2",
           "strip_first_frame": "0", "strip_middle_frame": "2", "strip_last_frame": "3"}
    target = tmp_path / "sheet.jpg"
    _sheet(frame_map, row, target)
    assert target.stat().st_size <= 200_000
    assert drawn == ["SHOT " + row["unit_id"][-13:]]
    assert not any(label in drawn[0] for label in ("WIDE", "CLOSEUP", "CROWD", "UNKNOWN"))


def test_preregistration_seal_normalizes_crlf_without_git_history():
    text = PREREG.read_text(encoding="utf-8").replace("\r\n", "\n")
    prefix, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert hashlib.sha256((prefix + "\n").encode("utf-8")).hexdigest() == seal.strip()
