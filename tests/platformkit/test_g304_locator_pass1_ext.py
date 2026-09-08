"""Validate the gpt-5.6-sol MODEL locator-pass-1 G304 extension artifact."""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = (
    ROOT
    / "docs"
    / "evidence"
    / "tracking"
    / "g304_locator_pass1_sol_ext_2026-09-07.csv"
)
MEMO_PATH = CSV_PATH.with_suffix(".md")
LOCATOR = "gpt-5.6-sol"
HEADER = [
    "locator_name",
    "row_id",
    "source_id",
    "arena",
    "classification",
    "negative_category",
    "unresolved_reason",
    "court_end",
    "record_type",
    "landmark_name",
    "x",
    "y",
    "visible",
    "confidence",
    "note",
]
VOCABULARY = {
    "CORNER_NEAR_L",
    "CORNER_NEAR_R",
    "CORNER_FAR_L",
    "CORNER_FAR_R",
    "LANE_BASE_L",
    "LANE_BASE_R",
    "FT_LINE_L",
    "FT_LINE_R",
    "KEY_TOP",
    "THREE_PT_BASE_L",
    "THREE_PT_BASE_R",
    "CENTER_SIDELINE_NEAR",
    "CENTER_SIDELINE_FAR",
    "CENTER_CIRCLE_TOP",
    "CENTER_CIRCLE_BOTTOM",
}
NOTE_TOKENS = {
    "clear",
    "player-occlusion",
    "motion-blur",
    "graphic-occlusion",
    "frame-boundary",
    "decode-corruption",
}
STRUCTURES = {
    "CORNER_NEAR_L": "court_boundary",
    "CORNER_NEAR_R": "court_boundary",
    "CORNER_FAR_L": "court_boundary",
    "CORNER_FAR_R": "court_boundary",
    "LANE_BASE_L": "lane_boundary",
    "LANE_BASE_R": "lane_boundary",
    "FT_LINE_L": "free_throw_line",
    "FT_LINE_R": "free_throw_line",
    "KEY_TOP": "free_throw_arc",
    "THREE_PT_BASE_L": "three_point_arc",
    "THREE_PT_BASE_R": "three_point_arc",
    "CENTER_SIDELINE_NEAR": "midcourt_line",
    "CENTER_SIDELINE_FAR": "midcourt_line",
    "CENTER_CIRCLE_TOP": "center_circle",
    "CENTER_CIRCLE_BOTTOM": "center_circle",
}
EXPECTED_IDS = {
    *(f"wnba_01_e{i:02d}" for i in (1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 17, 18, 27)),
    *(f"wnba_04_e{i:02d}" for i in (1, 2, 6, 7, 9, 11, 14, 16, 17, 18, 24, 25, 26, 27, 30, 33, 34, 37, 38, 39, 41, 42, 43, 44, 45)),
}


def _rows() -> tuple[list[str], list[dict[str, str]]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def test_schema_identity_and_extension_coverage() -> None:
    header, rows = _rows()
    assert header == HEADER
    assert rows
    assert {row["locator_name"] for row in rows} == {LOCATOR}
    assert {row["row_id"] for row in rows} == EXPECTED_IDS
    assert {row["classification"] for row in rows} == {"ELIGIBLE"}
    assert all(not row["negative_category"] for row in rows)
    assert all(not row["unresolved_reason"] for row in rows)
    source_counts = Counter(row_id[:7] for row_id in EXPECTED_IDS)
    assert source_counts == {"wnba_01": 15, "wnba_04": 25}


def test_landmark_rows_use_exact_vocabulary_and_original_pixels() -> None:
    _, rows = _rows()
    landmarks = [row for row in rows if row["record_type"] == "LANDMARK"]
    assert len(landmarks) == 109
    seen: set[tuple[str, str]] = set()
    for row in landmarks:
        assert row["landmark_name"] in VOCABULARY
        key = (row["row_id"], row["landmark_name"])
        assert key not in seen
        seen.add(key)
        x, y = int(row["x"]), int(row["y"])
        assert 0 <= x < 1920
        assert 0 <= y < 1080
        assert row["visible"] == "TRUE"
        assert 0.0 <= float(row["confidence"]) <= 1.0
        assert row["note"] in NOTE_TOKENS
        if x <= 1 or x >= 1918 or y <= 1 or y >= 1078:
            assert row["note"] == "frame-boundary"


def test_minimum_and_structure_gate_or_explicit_shortfall() -> None:
    _, rows = _rows()
    by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_id[row["row_id"]].append(row)
    shortfall_ids: set[str] = set()
    for row_id, group in by_id.items():
        landmarks = [row for row in group if row["record_type"] == "LANDMARK"]
        shortfalls = [row for row in group if row["record_type"] == "SHORTFALL"]
        if len(landmarks) >= 6:
            assert not shortfalls
            assert len({STRUCTURES[row["landmark_name"]] for row in landmarks}) >= 3
        else:
            assert len(shortfalls) == 1
            shortfall_ids.add(row_id)
            row = shortfalls[0]
            assert row["visible"] == "FALSE"
            assert not row["landmark_name"]
            assert not row["x"] and not row["y"] and not row["confidence"]
            assert row["note"] == f"visible_named_landmarks={len(landmarks)};required=6"
    assert shortfall_ids == {
        "wnba_01_e08",
        *(f"wnba_04_e{i:02d}" for i in (1, 2, 6, 7, 9, 11, 14, 16, 17, 18, 24, 25, 26, 27, 30, 33, 34, 37, 38, 39, 41, 42, 43, 44, 45)),
    }


def test_expected_arena_counts_and_record_types() -> None:
    _, rows = _rows()
    assert {row["record_type"] for row in rows} == {"LANDMARK", "SHORTFALL"}
    arena_landmarks = Counter(
        row["arena"] for row in rows if row["record_type"] == "LANDMARK"
    )
    arena_shortfalls = Counter(
        row["arena"] for row in rows if row["record_type"] == "SHORTFALL"
    )
    assert arena_landmarks == {
        "Gateway Center Arena": 89,
        "Climate Pledge Arena": 20,
    }
    assert arena_shortfalls == {
        "Gateway Center Arena": 1,
        "Climate Pledge Arena": 25,
    }


def test_memo_is_short_ascii_model_named_and_hash_bound() -> None:
    memo = MEMO_PATH.read_text(encoding="ascii")
    assert len(memo.splitlines()) <= 40
    assert LOCATOR in memo
    assert "NOT VERIFIED" in memo
    match = re.search(r"LF-normalized CSV SHA-256: `([0-9a-f]{64})`", memo)
    assert match
    import hashlib

    normalized = CSV_PATH.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    assert match.group(1) == hashlib.sha256(normalized).hexdigest()
