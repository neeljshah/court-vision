"""Synthetic coverage for G353's non-scorable image-space entry point."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.tracking.image_space_gates import evaluate_image_space
from scripts.platformkit.tracking_harness import evaluate


def _table() -> pd.DataFrame:
    rows = []
    for frame in range(60):
        for track_id in range(1, 7):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 40.0 + 30.0 * track_id + frame * 0.2,
                         "y": 30.0 + 20.0 * track_id + frame * 0.1,
                         "coordinate_space": "image_px"})
        rows.append({"frame": frame, "track_id": -1, "cls": "ball", "x": 320.0,
                     "y": 180.0, "coordinate_space": "image_px"})
    return pd.DataFrame(rows)


def _by_gate(rows: list[dict]) -> dict[str, dict]:
    return {row["gate"]: row for row in rows}


def test_image_space_detects_frozen_id_merge_and_ball_shift() -> None:
    base = _table()
    frozen = base.copy(deep=True)
    players = frozen["cls"].eq("player")
    frozen.loc[players, ["x", "y"]] = frozen.loc[players].groupby("track_id")[["x", "y"]].transform("first")
    merged = base.copy(deep=True)
    merged.loc[merged["track_id"].eq(2), "track_id"] = 1
    shifted = base.copy(deep=True)
    shifted.loc[shifted["cls"].eq("ball"), "frame"] += 120

    assert _by_gate(evaluate_image_space(frozen, "basketball", 640, 360))["liveness_frozen"]["status"] == "REJECT"
    assert _by_gate(evaluate_image_space(merged, "basketball", 640, 360))["duplicate_frame_identity"]["status"] == "REJECT"
    assert _by_gate(evaluate_image_space(shifted, "basketball", 640, 360))["ball_detected_share"]["status"] == "REJECT"


def test_image_rows_are_non_scorable_and_court_rail_is_unchanged() -> None:
    base = _table()
    before = evaluate(base, "basketball", attempted_frames=60)
    rows = evaluate_image_space(base, "basketball", 640, 360)
    after = evaluate(base, "basketball", attempted_frames=60)

    assert before.to_json() == after.to_json()
    assert "coordinate_contract:" in before.failures[0]
    assert all(row["scorable"] is False and row["coordinate_space"] == "image_px" for row in rows)
    by_gate = _by_gate(rows)
    assert by_gate["coordinate_contract"]["status"] == "NOT_APPLICABLE"
    assert by_gate["oob"]["reason"] == "court_space_required"
    assert by_gate["jump_p95"]["status"] == "MEASURED_NO_BAR"


def test_g325_is_not_applicable_without_decoded_frame_size() -> None:
    rows = _by_gate(evaluate_image_space(_table(), "basketball", None, None, "absent"))

    assert rows["g325_wholly_off_frame"]["status"] == "NOT_APPLICABLE"
    assert rows["g325_wholly_off_frame"]["reason"] == "frame_size_absent"


def test_prereg_seal_normalizes_crlf_without_git_show() -> None:
    prereg = Path(__file__).resolve().parents[2] / "docs/evidence/tracking/g353_prereg_2026-09-08.md"
    normalized = prereg.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = normalized.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.strip().decode("ascii")
