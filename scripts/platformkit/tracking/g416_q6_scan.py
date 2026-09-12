"""Field-aware restricted-claim scan for G416 preparation artifacts."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


def patterns() -> tuple[str, ...]:
    """Build scan patterns from character codes and never print the terms."""
    codes = ((100, 111, 108, 108, 97, 114), (114, 111, 105),
             (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))
    return tuple("".join(chr(value) for value in group) for group in codes)


def scan_text(text: str) -> dict[int, int]:
    """Return pattern indices and counts, never matched token strings."""
    lowered = text.lower()
    return {index: len(re.findall(r"\b" + re.escape(pattern) + r"\b", lowered))
            for index, pattern in enumerate(patterns())}


def scan_paths(paths: Iterable[Path]) -> dict[str, dict[int, int]]:
    """Scan supplied text paths without emitting their contents."""
    return {path.as_posix(): scan_text(path.read_text(encoding="utf-8", errors="replace"))
            for path in paths}
