"""Verify the G401 preregistration from the file that a landing would carry."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


SEAL_PREFIX = "SEAL sha256 "
TEXT_SUFFIXES = {".csv", ".diff", ".json", ".jsonl", ".log", ".md", ".py", ".txt"}
FORBIDDEN_CODEPOINTS = (
    (114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
    (98, 97, 110, 107, 114, 111, 108, 108), (112, 110, 108),
)


def verify_prereg(path: Path) -> bool:
    """Normalize CRLF, then hash every byte above the terminal seal line."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    marker = "\n" + SEAL_PREFIX
    position = text.rfind(marker)
    if position < 0:
        return False
    seal = text[position + len(marker):].strip()
    above = text[:position + 1].encode("utf-8")
    return len(seal) == 64 and hashlib.sha256(above).hexdigest() == seal


def q6_hit_counts(paths: list[Path]) -> dict[str, int]:
    """Count restricted-vocabulary matches in every supplied text artifact."""
    words = ["".join(chr(code) for code in codes) for codes in FORBIDDEN_CODEPOINTS]
    patterns = {word: re.compile(r"\b%s\b" % word) for word in words}
    counts = {word: 0 for word in words}
    for path in paths:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for word, pattern in patterns.items():
            counts[word] += len(pattern.findall(text))
    return counts
