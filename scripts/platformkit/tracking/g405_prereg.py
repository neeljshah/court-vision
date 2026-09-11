"""G405 preregistration and evidence-text verification helpers."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

SEAL_PREFIX = "SEAL sha256 "
TEXT_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".log", ".md", ".py", ".txt"})
FORBIDDEN = ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
             (98, 97, 110, 107, 114, 111, 108, 108), (112, 110, 108))


def verify_prereg(path: Path) -> bool:
    """Normalize CRLF and verify the terminal seal against bytes above it."""
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    match = re.search(r"\nSEAL sha256 ([0-9a-f]{64})\n?$", text)
    return bool(match and hashlib.sha256(text[:match.start() + 1].encode("utf-8")).hexdigest() == match.group(1))


def q6_hit_counts(paths: list[Path]) -> dict[str, int]:
    """Count restricted vocabulary without emitting matched source text."""
    words = ["".join(chr(code) for code in item) for item in FORBIDDEN]
    counts = {word: 0 for word in words}
    for path in paths:
        if Path(path).suffix.lower() in TEXT_SUFFIXES:
            text = Path(path).read_text(encoding="utf-8", errors="replace").lower()
            for word in words:
                counts[word] += len(re.findall(r"\b%s\b" % re.escape(word), text))
    return counts
