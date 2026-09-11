"""Field-aware Q6 vocabulary scan for the G408 evidence directory.

Every pattern and every positive fixture is built from character codes, so this
file never contains a banned token literally.  Receipts carry pattern INDICES
and counts, never matched text.

Two boundary rules make the scan field-aware instead of blanket-exempting file
types.  Alphabetic patterns match only at word boundaries, so a word that
merely contains one (a record-keeping noun, for instance) is not a hit.
Numeric patterns match only when neither neighbour is a digit or a decimal
point, so an appropriately typed measurement that happens to contain the digits
is not a hit while the bare retracted figure still is.
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
ALPHA_LAST = 5  # indices <= this are prose tokens
SKIP_SUFFIXES = (".mp4", ".jpg", ".png", ".pyc")
SKIP_NAMES = ("SHA256SUMS",)
_DIGIT = set("0123456789.")


def _alpha_hits(text: str, pattern: str) -> int:
    return len(re.findall(r"(?<![a-z])" + re.escape(pattern) + r"(?![a-z])",
                          text))


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


def scan_text(text: str) -> list[tuple[int, int]]:
    """Return (pattern_index, count) for every pattern that hits ``text``."""
    lowered = text.lower()
    out = []
    for index, pattern in enumerate(PATTERNS):
        count = (_alpha_hits(lowered, pattern) if index <= ALPHA_LAST
                 else _numeric_hits(lowered, pattern))
        if count:
            out.append((index, count))
    return out


def positive_fixtures() -> list[dict]:
    """Each pattern must fire on a constructed positive and not on a near miss."""
    rows = []
    for index, pattern in enumerate(PATTERNS):
        if index <= ALPHA_LAST:
            positive = " " + pattern + " "
            negative = "x" + pattern + "x"
        else:
            positive = " " + pattern + " "
            negative = "9" + pattern + "9"
        rows.append({"pattern_index": index,
                     "fires_on_positive": bool(scan_text(positive)),
                     "silent_on_near_miss": not scan_text(negative)})
    return rows


def scan_directory(root: Path) -> dict:
    """Scan every text artifact under ``root`` and return the Q6 receipt."""
    scanned, hits = [], []
    for path in sorted(root.rglob("*")):
        if (not path.is_file() or path.suffix in SKIP_SUFFIXES
                or path.name in SKIP_NAMES):
            continue
        rel = path.relative_to(root).as_posix()
        scanned.append(rel)
        for index, count in scan_text(
                path.read_bytes().decode("utf-8", "replace")):
            hits.append({"path": rel, "pattern_index": index, "count": count})
    fixtures = positive_fixtures()
    return {"scanned_paths": scanned, "scanned_count": len(scanned),
            "pattern_count": len(PATTERNS),
            "positive_fixtures": fixtures,
            "all_fixtures_pass": all(row["fires_on_positive"]
                                     and row["silent_on_near_miss"]
                                     for row in fixtures),
            "hits": hits, "non_opaque_hit_count": len(hits),
            "boundary_rules": {
                "alphabetic": "word boundary on both sides",
                "numeric": "neither neighbour is a digit or a decimal point"},
            "note": "patterns and fixtures are built from character codes; "
                    "receipts carry pattern indices and counts, never text"}
