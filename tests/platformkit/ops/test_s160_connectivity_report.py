"""Structural contract for the S160 connectivity evidence memo."""

from pathlib import Path
import re


REPORT = Path("docs/evidence/CONNECTIVITY_2026-09-04.md")
VERDICTS = {"PASS", "FAIL", "NOT TESTABLE HERE"}


def test_connectivity_report_has_all_construct_links_and_verdicts() -> None:
    text = REPORT.read_text(encoding="utf-8")
    rows = re.findall(r"^\| (L(?:[1-9]|10|11)) \|.*?\| (PASS|FAIL|NOT TESTABLE HERE) \|", text, re.M)
    assert [link for link, _ in rows] == [f"L{i}" for i in range(1, 12)]
    assert all(verdict in VERDICTS for _, verdict in rows)
