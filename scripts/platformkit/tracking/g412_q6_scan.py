"""Field-aware vocabulary scanner used by the later G412 evidence assembly."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping

_CODES = ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))
_FIELDS = ("claim", "verdict", "summary", "memo", "label", "notes")


def _word(codes: tuple[int, ...]) -> str:
    return "".join(chr(value) for value in codes)


def scan_text(text: str) -> list[int]:
    """Return restricted-pattern indices in prose fields, never the pattern text."""
    lowered = text.lower()
    return [index for index, codes in enumerate(_CODES)
            if re.search(r"\b" + re.escape(_word(codes)) + r"\b", lowered)]


def scan_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Scan only claim-like fields while preserving typed numeric data."""
    counts = [0] * len(_CODES)
    rows_seen = 0
    for row in rows:
        rows_seen += 1
        for field in _FIELDS:
            value = row.get(field)
            if isinstance(value, str):
                for index in scan_text(value):
                    counts[index] += 1
    return {"rows": rows_seen, "pattern_indices": [i for i, count in enumerate(counts) if count],
            "counts": counts}


def scan_paths(paths: Iterable[Path]) -> dict[str, object]:
    """Emit a complete path manifest and index-only counts for text artifacts."""
    manifest = []
    counts = [0] * len(_CODES)
    for path in paths:
        text = path.read_text(encoding="utf-8")
        found = scan_text(text)
        for index in found:
            counts[index] += 1
        manifest.append({"path": path.as_posix(), "pattern_indices": sorted(set(found)),
                         "counts": [found.count(i) for i in range(len(_CODES))]})
    return {"path_manifest": manifest, "pattern_indices": [i for i, count in enumerate(counts) if count],
            "counts": counts}
