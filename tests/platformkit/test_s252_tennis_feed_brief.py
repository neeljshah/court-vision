"""Structure checks for the S252 four-candidate tennis feed decision brief."""
from pathlib import Path


BRIEF = Path("docs/evidence/harness/S252_tennis_point_feed_decision_2026-09-04.md")
HEADERS = [
    "Candidate",
    "Cost",
    "Cadence",
    "Terms/ToS",
    "Minimum viable capture",
    "Sourced-or-unsourced flag",
]
EXPECTED_CANDIDATES = {
    "Sportradar Tennis",
    "Enetpulse",
    "Data Sports Group",
    "Self-serve REST/WebSocket pair: livetennisapi.com + tennis-api.com",
}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _decision_rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    header_index = next(index for index, line in enumerate(lines) if _cells(line) == HEADERS)
    rows: list[list[str]] = []
    for line in lines[header_index + 2:]:
        if not line.startswith("|"):
            break
        rows.append(_cells(line))
    return rows


def test_s252_brief_has_four_complete_candidates_and_one_recommendation() -> None:
    text = BRIEF.read_text(encoding="ascii")
    rows = _decision_rows(text)
    recommendation_lines = [
        line for line in text.splitlines() if line.startswith("Recommendation:")
    ]

    assert len(rows) == 4
    assert all(len(row) == len(HEADERS) for row in rows)
    assert all(all(cell for cell in row) for row in rows)
    assert {row[0] for row in rows} == EXPECTED_CANDIDATES
    assert recommendation_lines == ["Recommendation: no feed recommended."]
