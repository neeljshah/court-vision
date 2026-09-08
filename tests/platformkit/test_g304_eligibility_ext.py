"""Validate G304 extension annotations by MODEL annotator gpt-5.6-sol."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "docs/evidence/tracking/g304_eligibility_ext_sol_2026-09-07.csv"
MEMO_PATH = ROOT / "docs/evidence/tracking/g304_eligibility_ext_sol_2026-09-07.md"
SCHEMA = [
    "row_id",
    "source_id",
    "arena",
    "classification",
    "negative_category",
    "visible_structures",
    "court_end",
    "confidence",
    "note",
]
CLASSES = {"ELIGIBLE", "NEGATIVE", "UNRESOLVABLE"}
NEGATIVE_CATEGORIES = {
    "close-up",
    "graphics/transition",
    "replay/alternate-camera",
}
COURT_ENDS = {
    "LEFT_BASKET",
    "RIGHT_BASKET",
    "BASKET_END_CENTERED",
    "NOT_IDENTIFIABLE",
}
ARENAS = {
    "wnba_01": "Gateway Center Arena",
    "wnba_04": "Climate Pledge Arena",
}
FIRST_PASS = {
    "wnba_01": ((14, 16, 0), (10, 1, 5)),
    "wnba_04": ((9, 19, 2), (7, 0, 12)),
}


def _memo_cells(memo: str, source_id: str) -> list[str]:
    prefix = f"| {source_id} / "
    lines = [line for line in memo.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, f"expected one memo count row for {source_id}"
    return [cell.strip() for cell in lines[0].strip("|").split("|")]


def _triplet(value: str) -> tuple[int, int, int]:
    return tuple(int(item) for item in value.split("/"))  # type: ignore[return-value]


def test_g304_extension_eligibility_artifacts() -> None:
    raw = CSV_PATH.read_bytes()
    text = raw.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    rows = list(reader)
    memo = MEMO_PATH.read_text(encoding="utf-8")

    assert reader.fieldnames == SCHEMA
    assert len(rows) == 75
    assert len({row["row_id"] for row in rows}) == 75
    assert Counter(row["source_id"] for row in rows) == {"wnba_01": 30, "wnba_04": 45}
    assert {row["row_id"] for row in rows} == {
        *(f"wnba_01_e{index:02d}" for index in range(1, 31)),
        *(f"wnba_04_e{index:02d}" for index in range(1, 46)),
    }
    assert {row["classification"] for row in rows} <= CLASSES
    assert {row["court_end"] for row in rows} <= COURT_ENDS
    assert {row["confidence"] for row in rows} <= {"HIGH", "MEDIUM", "LOW"}
    assert all(row["arena"] == ARENAS[row["source_id"]] for row in rows)
    assert all("gpt-5.6-sol MODEL:" in row["note"] for row in rows)
    assert "gpt-5.6-sol (declared MODEL annotator)" in memo
    assert len(memo.splitlines()) <= 40
    assert raw.isascii() and memo.isascii()

    for row in rows:
        if row["classification"] == "NEGATIVE":
            assert row["negative_category"] in NEGATIVE_CATEGORIES
        else:
            assert row["negative_category"] == ""
        if row["classification"] == "ELIGIBLE":
            assert len(row["visible_structures"].split(";")) >= 3
        if row["classification"] == "UNRESOLVABLE":
            assert row["note"].strip()

    category_order = tuple(sorted(NEGATIVE_CATEGORIES))
    assert category_order == ("close-up", "graphics/transition", "replay/alternate-camera")
    for source_id in ARENAS:
        source_rows = [row for row in rows if row["source_id"] == source_id]
        classes = Counter(row["classification"] for row in source_rows)
        categories = Counter(
            row["negative_category"]
            for row in source_rows
            if row["classification"] == "NEGATIVE"
        )
        extension = (
            classes["ELIGIBLE"],
            classes["NEGATIVE"],
            classes["UNRESOLVABLE"],
        )
        extension_categories = tuple(categories[name] for name in category_order)
        first, first_categories = FIRST_PASS[source_id]
        combined = tuple(left + right for left, right in zip(extension, first))
        combined_categories = tuple(
            left + right for left, right in zip(extension_categories, first_categories)
        )
        cells = _memo_cells(memo, source_id)
        assert _triplet(cells[1]) == extension
        assert _triplet(cells[2]) == extension_categories
        assert _triplet(cells[3]) == first
        assert _triplet(cells[4]) == combined
        assert _triplet(cells[5]) == combined_categories

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    digest = hashlib.sha256(normalized).hexdigest()
    assert f"LF-normalized CSV SHA-256: `{digest}`" in memo
