"""G389 whole-set premise checks for the native ball-reference completion pass."""
from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

from PIL import Image


EXPECTED = {
    "manifest": 1620, "settled": 1114, "pending": 506,
    "pending_development": 301, "pending_heldout": 205, "dev_boxes": 312,
    "heldout_absent": 161, "heldout_visible": 157, "heldout_unknown": 26,
    "candidate_executions": 0,
}


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read one CSV table with stable, explicit text values."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _index(rows: list[dict[str, str]], name: str) -> dict[str, dict[str, str]]:
    indexed = {row["frame_key"]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("duplicate-frame-key " + name)
    return indexed


def binding_counts(manifest: list[dict[str, str]], reference: list[dict[str, str]],
                   adjudications: list[dict[str, str]], dev_boxes: list[dict[str, str]]) -> dict[str, int]:
    """Reproduce the G389 binding counts from all manifest and settled rows."""
    man, ref, adj = (_index(rows, name) for rows, name in
                     ((manifest, "manifest"), (reference, "reference"),
                      (adjudications, "adjudications")))
    if (set(ref) | set(adj)) - set(man) or set(ref) & set(adj):
        raise ValueError("settled-keys-not-a-disjoint-manifest-subset")
    settled = set(ref) | set(adj)
    pending = set(man) - settled
    rows = list(ref.values()) + list(adj.values())
    heldout = Counter(row["label"] for row in rows if man[row["frame_key"]]["split"] == "heldout")
    base_boxes = {row["frame_key"] for row in dev_boxes}
    added_boxes = {row["frame_key"] for row in adj.values()
                   if man[row["frame_key"]]["split"] == "development"
                   and row["label"] == "VISIBLE" and row.get("box_w")}
    if not base_boxes.issubset(set(man)) or base_boxes.intersection(set(adj)):
        raise ValueError("development-box-identity-mismatch")
    return {
        "manifest": len(man), "settled": len(settled), "pending": len(pending),
        "pending_development": sum(man[key]["split"] == "development" for key in pending),
        "pending_heldout": sum(man[key]["split"] == "heldout" for key in pending),
        "dev_boxes": len(base_boxes | added_boxes), "heldout_absent": heldout["ABSENT"],
        "heldout_visible": heldout["VISIBLE"], "heldout_unknown": heldout["UNKNOWN"],
        "candidate_executions": 0,
    }


def check_binding(counts: dict[str, int]) -> None:
    """Reject a stale dispatch before allocation or judgment begins."""
    changed = {key: (EXPECTED[key], counts.get(key)) for key in EXPECTED
               if EXPECTED[key] != counts.get(key)}
    if changed:
        raise ValueError("binding-counts-changed " + repr(changed))


def sheet_receipts(manifest: list[dict[str, str]], pending: set[str], sheets: Path) -> list[dict[str, object]]:
    """Hash and open each pending native sheet separately, preserving missing pixels."""
    receipts: list[dict[str, object]] = []
    for row in manifest:
        if row["frame_key"] not in pending:
            continue
        path = Path(sheets) / row["sheet"]
        receipt: dict[str, object] = {"frame_key": row["frame_key"], "sheet": row["sheet"],
                                      "exists": path.is_file(), "bytes": 0, "sha256": "",
                                      "width": "", "height": "", "status": "MISSING-PIXELS"}
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            with Image.open(path) as image:
                receipt.update(bytes=path.stat().st_size, sha256=digest.hexdigest(),
                               width=image.width, height=image.height, status="OPENED")
        receipts.append(receipt)
    return receipts
