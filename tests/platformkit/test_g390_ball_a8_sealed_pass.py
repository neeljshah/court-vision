"""Prepare-only rails for G390's single future native-scale scoring pass."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g390_receipt import (
    advance_token,
    begin_scoring,
    charge_candidate_token,
)
from scripts.platformkit.tracking.g390_render_archived import render_archived
from scripts.platformkit.tracking.g390_sealed_input import load_sealed_input

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/preregistration.md"
RENDERS_INDEX = PREREG.parent / "renders/renders_index.csv"
SEAL = b"SEAL sha256 "


def _tables(tmp_path: Path, scale: str = "1.0", reference: bool = True) -> tuple[Path, Path]:
    frames = tmp_path / "frames.csv"
    refs = tmp_path / "reference.csv"
    frames.write_text("frame_key,split,sheet_scale\nk,heldout," + scale + "\n",
                      encoding="ascii", newline="\n")
    refs.write_text("frame_key,label,review_state\n" +
                    ("k,VISIBLE,REVIEWED\n" if reference else ""),
                    encoding="ascii", newline="\n")
    return frames, refs


def test_half_scale_table_is_refused_before_any_score(tmp_path):
    frames, refs = _tables(tmp_path, scale="0.5")
    with pytest.raises(ValueError, match="sheet-scale-not-native-refused"):
        load_sealed_input(frames, refs, expected_total=None, expected_heldout=None)


def test_unsettled_reference_is_refused_before_any_score(tmp_path):
    frames, refs = _tables(tmp_path, reference=False)
    with pytest.raises(ValueError, match="unsettled-reference-refused"):
        load_sealed_input(frames, refs, expected_total=None, expected_heldout=None)


def test_second_scoring_pass_is_refused(tmp_path):
    token = tmp_path / "candidate_token.json"
    charge_candidate_token(token, source_hashes={"reference": "a"})
    advance_token(token, "CHARGED_BEFORE_INFERENCE", "INFERENCE_COMPLETE")
    begin_scoring(token)
    with pytest.raises(ValueError, match="second-scoring-pass-refused"):
        begin_scoring(token)


def test_prereg_seal_uses_lf_normalized_file_bytes():
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    body, marker, recorded = raw.rpartition(b"\n" + SEAL)
    assert marker and recorded
    assert hashlib.sha256(body + b"\n").hexdigest() == recorded.decode("ascii").strip()


def test_renders_index_keeps_parent_score_columns():
    header = RENDERS_INDEX.read_text(encoding="ascii").splitlines()[0].split(",")
    assert "n_predictions" in header
    assert "distance_720p" in header


def test_archived_renderer_refuses_missing_prediction_files(tmp_path):
    missing = tmp_path / "missing.csv"
    with pytest.raises(FileNotFoundError, match="archived-a0-predictions-required"):
        render_archived(missing, missing, tmp_path, missing, missing, tmp_path / "renders")
