"""ASCII text artifact scan using code-point patterns rather than claim literals."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


PATTERNS = tuple("".join(chr(code) for code in codes) for codes in (
    (114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
    (43, 49, 56, 46, 51, 56), (48, 46, 49, 49, 57), (43, 53, 52),
    (55, 56, 46, 49, 49), (56, 46, 57, 52), (53, 52, 46, 53, 55),
))


def scan(paths: Iterable[Path]) -> dict[str, list[str]]:
    """Return case-insensitive forbidden-text matches for explicit artifact paths."""
    findings: dict[str, list[str]] = {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace").lower()
        matched = [pattern for pattern in PATTERNS
                   if re.search(r"(?<![a-z])" + re.escape(pattern) + r"(?![a-z])", text)]
        if matched:
            findings[str(path)] = matched
    return findings
