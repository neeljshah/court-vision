"""Character-code-built vocabulary scan for G400 landable text artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _word(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


TOKENS = (
    _word(114, 111, 105),
    _word(112, 114, 111, 102, 105, 116),
    _word(101, 100, 103, 101),
    _word(100, 111, 108, 108, 97, 114),
)


def scan(paths: Iterable[Path]) -> dict[str, list[str]]:
    """Return code-safe findings for every supplied UTF-8 text artifact."""
    findings: dict[str, list[str]] = {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace").lower()
        hits = ["-".join(str(ord(char)) for char in token) for token in TOKENS if token in text]
        if hits:
            findings[str(path)] = hits
    return findings
