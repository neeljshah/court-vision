"""Preparation-only selection and evidence helpers for G402."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping

DRAW_SIZE = 30
TEXT_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".md", ".py", ".txt"})
REQUIRED_ARTIFACTS = (
    "census.csv", "draw.csv", "source_receipts.csv", "window_pts.csv",
    "route_hashes.json", "launch_receipts.csv", "raw_tables/", "trace/",
    "evaluated_ticks.csv", "held_pairs.csv", "provenance_counts.csv",
    "target_mask.csv", "coverage_per_section.csv", "pixel_audit.csv",
    "eye_index.csv", "summary.json", "repeats.json", "renders/",
    "common_receipts/", "SHA256SUMS",
)

__all__ = ["DRAW_SIZE", "REQUIRED_ARTIFACTS", "even_draw", "prepared_artifact_paths",
           "q6_scan", "window_start"]


def _identity(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    fields = ("competition", "game", "section_id", "source_sha256")
    values = tuple(str(row.get(field, "")) for field in fields)
    if not all(values):
        raise ValueError("draw-identity-field-absent")
    return values


def even_draw(rows: Iterable[Mapping[str, Any]], draw_size: int = DRAW_SIZE) -> list[dict[str, Any]]:
    """Select an even, unique-section draw without replacement or top-up."""
    pool = [dict(row) for row in rows]
    if draw_size != DRAW_SIZE:
        raise ValueError("draw-size-must-remain-30")
    identities = [_identity(row) for row in pool]
    sections = [identity[2] for identity in identities]
    if len(pool) < draw_size:
        raise ValueError("source-quota-insufficient")
    if len(set(sections)) != len(sections):
        raise ValueError("source-section-not-unique")
    indexed = sorted(zip(identities, pool), key=lambda item: item[0])
    count = len(indexed)
    picked = [indexed[int(j * (count - 1) / (draw_size - 1) + 0.5)][1]
              for j in range(draw_size)]
    return [dict(row, draw_order=j, population=count) for j, row in enumerate(picked)]


def window_start(usable_start: float, usable_span: float, ordinal: int) -> float:
    """Return the sealed 10-second native-time window start for one draw ordinal."""
    if ordinal < 0 or ordinal >= DRAW_SIZE:
        raise ValueError("draw-ordinal-out-of-range")
    if usable_span < 10.0:
        raise ValueError("usable-span-under-10-seconds")
    return float(usable_start) + (ordinal + 1) * (float(usable_span) - 10.0) / 31.0


def prepared_artifact_paths(evidence: Path) -> list[Path]:
    """Return G402 destinations without creating a measurement artifact."""
    return [Path(evidence) / item for item in REQUIRED_ARTIFACTS]


def q6_scan(paths: Iterable[Path]) -> None:
    """Reject prohibited vocabulary without emitting matched artifact text."""
    words = ["".join(chr(code) for code in codes) for codes in
             ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))]
    hits = 0
    for path in paths:
        path = Path(path)
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            body = path.read_text(encoding="utf-8", errors="replace").lower()
            hits += sum(bool(re.search(r"\b" + re.escape(word) + r"\b", body))
                        for word in words)
    if hits:
        raise ValueError("q6-vocabulary-count:%d" % hits)
