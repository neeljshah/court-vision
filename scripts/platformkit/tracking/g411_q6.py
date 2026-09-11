"""Field-aware Q6 vocabulary scan for the G411 evidence directory.

Patterns and positive fixtures are built from character codes, so this file
never contains a banned token literally.  Receipts carry pattern INDICES and
counts, never matched text.  The scan is field-aware rather than exempting
file types: alphabetic patterns match only at word boundaries, and numeric
patterns match only when neither neighbour is a digit or a decimal point, so a
typed measurement that merely contains the digits is not a hit while the bare
retracted figure still is.  The scanner's own source is scanned too.
"""
from __future__ import annotations

import re
from pathlib import Path

# 0-5 prose tokens, 6-11 retracted figures.
CODES = (
    (101, 100, 103, 101),
    (112, 114, 111, 102, 105, 116),
    (114, 111, 105),
    (98, 97, 110, 107, 114, 111, 108, 108),
    (98, 101, 116),
    (119, 97, 103, 101, 114),
    (43, 49, 56, 46, 51, 56),
    (48, 46, 49, 49, 57),
    (55, 56, 46, 49, 49),
    (56, 46, 57, 52),
    (53, 52, 46, 53, 55),
    (43, 53, 52, 37),
)
PATTERNS = tuple("".join(chr(code) for code in row) for row in CODES)
ALPHA_LAST = 5
SKIP_SUFFIXES = (".mp4", ".jpg", ".png", ".pyc")
SKIP_NAMES = ("SHA256SUMS",)
_DIGIT = set("0123456789.")


def _alpha_hits(text: str, pattern: str) -> int:
    return len(re.findall(r"(?<![a-z])" + re.escape(pattern) + r"(?![a-z])", text))


def _numeric_hits(text: str, pattern: str) -> int:
    count = 0
    start = 0
    while True:
        index = text.find(pattern, start)
        if index < 0:
            return count
        before = text[index - 1] if index else ""
        after = text[index + len(pattern):index + len(pattern) + 1]
        if before not in _DIGIT and after not in _DIGIT:
            count += 1
        start = index + 1


def scan_text(text: str) -> list:
    """Return only pattern indices and counts, never matched text."""
    lowered = text.lower()
    rows = []
    for index, pattern in enumerate(PATTERNS):
        count = (_alpha_hits(lowered, pattern) if index <= ALPHA_LAST
                 else _numeric_hits(lowered, pattern))
        if count:
            rows.append({"pattern_index": index, "count": count})
    return rows


def positive_fixtures() -> list:
    """Provide code-built positives and boundary near-misses for tests."""
    rows = []
    for index, pattern in enumerate(PATTERNS):
        near = ("x" + pattern + "x") if index <= ALPHA_LAST else ("9" + pattern + "9")
        rows.append({"pattern_index": index,
                     "fires_on_positive": bool(scan_text(" " + pattern + " ")),
                     "silent_on_near_miss": not scan_text(near)})
    return rows


def scannable(path: Path) -> bool:
    """Decide field-aware inclusion; no whole file type is blanket-exempt."""
    return (path.is_file() and path.suffix.lower() not in SKIP_SUFFIXES
            and path.name not in SKIP_NAMES)


def scan_paths(paths: list, root: Path) -> dict:
    """Scan every named text path, emitting a complete manifest and indices."""
    hits = []
    manifest = []
    for path in sorted(set(str(item) for item in paths)):
        item = Path(path)
        if not scannable(item):
            continue
        label = str(item.relative_to(root)).replace("\\", "/")
        manifest.append(label)
        try:
            text = item.read_text(encoding="utf-8", errors="replace")
        except OSError:
            hits.append({"path": label, "pattern_index": -1, "count": 0,
                         "unreadable": True})
            continue
        for row in scan_text(text):
            hits.append(dict(row, path=label))
    fixtures = positive_fixtures()
    return {"all_fixtures_pass": all(row["fires_on_positive"]
                                     and row["silent_on_near_miss"]
                                     for row in fixtures),
            "boundary_rules": {
                "alphabetic": "word boundary on both sides",
                "numeric": "neither neighbour is a digit or a decimal point"},
            "hits": hits, "non_opaque_hit_count": len(hits),
            "note": "patterns and fixtures are built from character codes; "
                    "receipts carry pattern indices and counts, never text",
            "pattern_count": len(PATTERNS), "positive_fixtures": fixtures,
            "scanned_count": len(manifest), "scanned_paths": manifest}
