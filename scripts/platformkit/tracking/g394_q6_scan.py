"""G394 text-artifact vocabulary scan using character-code patterns."""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path


PATTERNS = tuple("".join(chr(code) for code in codes) for codes in (
    (114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
    (43, 49, 56, 46, 51, 56), (48, 46, 49, 49, 57), (43, 53, 52),
    (55, 56, 46, 49, 49), (56, 46, 57, 52), (53, 52, 46, 53, 55),
))


def scan(paths: Iterable[Path]) -> dict[str, list[str]]:
    """Return vocabulary matches outside opaque file-name identifiers."""
    findings: dict[str, list[str]] = {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace").lower()
        matches = [pattern for pattern in PATTERNS
                   if re.search((r"(?<![0-9a-z.])" if pattern[0].isdigit() or pattern[0] == "+"
                                 else r"(?<![a-z])") + re.escape(pattern)
                                + (r"(?![0-9a-z.])" if pattern[-1].isdigit()
                                   else r"(?![a-z])"), text)]
        if matches:
            findings[Path(path).as_posix()] = matches
    return findings
