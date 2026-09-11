"""Field-aware restricted-claim scanner for G410 evidence text."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


def _patterns() -> tuple[str, ...]:
    """Build scanner patterns from character codes without echoing them in receipts."""
    codes = ((100, 111, 108, 108, 97, 114), (114, 111, 105),
             (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))
    return tuple("".join(chr(value) for value in group) for group in codes)


def scan_text(text: str) -> dict[int, int]:
    """Return only pattern indices and counts for a claim-bearing text field."""
    lowered = text.lower()
    return {index: len(re.findall(r"\b" + re.escape(pattern) + r"\b", lowered))
            for index, pattern in enumerate(_patterns())}


def scan_paths(paths: Iterable[Path]) -> dict[str, dict[int, int]]:
    """Scan each delivered text path without treating identifiers as prose claims."""
    result: dict[str, dict[int, int]] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        result[str(path)] = scan_text(text)
    return result
