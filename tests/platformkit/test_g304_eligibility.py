"""Validate G304 eligibility annotations by MODEL annotator gpt-5.6-sol."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "docs/evidence/tracking/g304_eligibility_sol_2026-09-07.csv"
MEMO_PATH = ROOT / "docs/evidence/tracking/g304_eligibility_sol_2026-09-07.md"
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


def _memo_counts(memo: str, source_id: str) -> tuple[int, ...]:
    pattern = rf"^\| {source_id} \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|"
    match = re.search(pattern, memo, flags=re.MULTILINE)
    assert match, f"missing memo count row for {source_id}"
    return tuple(int(value) for value in match.groups())


def test_g304_eligibility_artifacts() -> None:
    raw = CSV_PATH.read_bytes()
    text = raw.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    rows = list(reader)
    memo = MEMO_PATH.read_text(encoding="utf-8")

    assert reader.fieldnames == SCHEMA
    assert len(rows) == 60
    assert len({row["row_id"] for row in rows}) == 60
    assert Counter(row["source_id"] for row in rows) == {"wnba_01": 30, "wnba_04": 30}
    assert {row["classification"] for row in rows} <= CLASSES
    assert all("gpt-5.6-sol" in row["note"] for row in rows)
    assert "gpt-5.6-sol (declared MODEL annotator)" in memo

    for row in rows:
        if row["classification"] == "NEGATIVE":
            assert row["negative_category"] in NEGATIVE_CATEGORIES
        else:
            assert row["negative_category"] == ""
        if row["classification"] == "ELIGIBLE":
            assert len(row["visible_structures"].split(";")) >= 3
        if row["classification"] == "UNRESOLVABLE":
            assert row["note"].strip()

    for source_id in ("wnba_01", "wnba_04"):
        source_rows = [row for row in rows if row["source_id"] == source_id]
        classes = Counter(row["classification"] for row in source_rows)
        categories = Counter(
            row["negative_category"]
            for row in source_rows
            if row["classification"] == "NEGATIVE"
        )
        expected = (
            classes["ELIGIBLE"],
            classes["NEGATIVE"],
            classes["UNRESOLVABLE"],
            categories["close-up"],
            categories["graphics/transition"],
            categories["replay/alternate-camera"],
        )
        assert _memo_counts(memo, source_id) == expected

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    digest = hashlib.sha256(normalized).hexdigest()
    assert f"LF-normalized CSV SHA-256: `{digest}`" in memo
