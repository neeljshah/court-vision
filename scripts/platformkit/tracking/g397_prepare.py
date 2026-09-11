"""G397 preparation-only artifact inventory and calibration-language scan."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

TEXT_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".md", ".txt"})
REQUIRED_ARTIFACTS = ("policy_receipt.json", "census.csv", "draw.csv", "source_probes.csv",
                      "source_receipts.csv", "ledger_snapshot.jsonl", "enriched_ledger.jsonl",
                      "per_section.csv", "evaluated_ticks.csv", "held_pairs.csv", "snapshots/",
                      "eye_index.csv", "summary.json", "repeats.json", "common_receipts/")

__all__ = ["REQUIRED_ARTIFACTS", "q6_scan", "prepared_artifact_paths"]


def prepared_artifact_paths(evidence: Path) -> list[Path]:
    """Return the sealed G397 artifact destinations without creating measurements."""
    return [Path(evidence) / item for item in REQUIRED_ARTIFACTS]


def q6_scan(paths: Iterable[Path]) -> None:
    """Reject prohibited calibration-language vocabulary without printing matched text."""
    forbidden = ["".join(chr(code) for code in codes) for codes in
                 ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))]
    hits = 0
    for path in paths:
        path = Path(path)
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            hits += sum(bool(re.search(r"\b" + re.escape(word) + r"\b", text)) for word in forbidden)
    if hits:
        raise ValueError("q6-vocabulary-count:%d" % hits)
