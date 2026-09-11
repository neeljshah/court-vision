"""G398 text scanner with character-code-built claim patterns."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


PATTERNS = tuple("".join(chr(code) for code in codes) for codes in (
    (114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
    (43, 49, 56, 46, 51, 56), (48, 46, 49, 49, 57), (43, 53, 52),
    (55, 56, 46, 49, 49), (56, 46, 57, 52), (53, 52, 46, 53, 55),
))


def expression(pattern: str) -> str:
    """Boundary rule shared with the landed G394 scanner: digit runs stay opaque."""
    head = r"(?<![0-9a-z.])" if pattern[0].isdigit() or pattern[0] == "+" else r"(?<![a-z])"
    tail = r"(?![0-9a-z.])" if pattern[-1].isdigit() else r"(?![a-z])"
    return head + re.escape(pattern) + tail


def scan(paths: Iterable[Path]) -> dict[str, list[str]]:
    """Return matched pattern identifiers without printing artifact text."""
    findings: dict[str, list[str]] = {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace").lower()
        matched = [pattern for pattern in PATTERNS if re.search(expression(pattern), text)]
        if matched:
            findings[Path(path).as_posix()] = matched
    return findings
