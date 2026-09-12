"""Read-only G416 binding census and deterministic future-draw helpers."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

MAX_READ_BYTES = 300 * 1024 * 1024
G410 = Path("docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12")


def _read_jsonl(path: Path) -> list[dict]:
    """Read one bounded evidence table and reject a path above the local cap."""
    if not path.exists():
        raise FileNotFoundError("ABSENT-IN-WORKTREE " + path.as_posix())
    if path.stat().st_size > MAX_READ_BYTES:
        raise ValueError("store-over-local-cap " + path.as_posix())
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError("ABSENT-IN-WORKTREE " + path.as_posix())
    if path.stat().st_size > MAX_READ_BYTES:
        raise ValueError("store-over-local-cap " + path.as_posix())
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def exact_even(items: list[object], count: int = 30) -> list[object]:
    """Select exact-even items without replacement or substitution."""
    if len(items) < count or count < 2:
        raise ValueError("exact-even-supply-insufficient")
    return [items[(2 * index * (len(items) - 1) + count - 1) // (2 * (count - 1))]
            for index in range(count)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding_census(root: Path) -> dict[str, object]:
    """Reproduce the G416 premise without conflating original and replay namespaces."""
    base = root / G410
    checks = _read_jsonl(base / "branch_trace.jsonl")
    matrices = _read_jsonl(base / "matrices.jsonl")
    originals = _read_csv(base / "per_row.csv")
    matrix_keys = {(row["section_id"], int(row["frame"])) for row in matrices}
    deficits = []
    for row in checks:
        key = (row["section_id"], int(row["frame"]))
        if key not in matrix_keys:
            deficits.append({"namespace": "replay", "reason": "MISSING_MATRIX", "key": key})
    guard_rows = [row for row in checks if row.get("derived_branch") == "CLAMP_GUARD_REPRODUCED"]
    original_keys = {(row["draw_kind"], row["section_id"], row["frame"], row["player_id"])
                     for row in originals}
    emitted_rows = 0
    emitted_keys: set[tuple[str, str, str]] = set()
    emitted_duplicates = 0
    emitted_dir = base / "runtime_receipts" / "emitted"
    if not emitted_dir.exists():
        raise FileNotFoundError("ABSENT-IN-WORKTREE " + emitted_dir.as_posix())
    for path in sorted(emitted_dir.glob("*.tracking_data.csv")):
        section = path.name.removesuffix(".tracking_data.csv")
        for row in _read_csv(path):
            emitted_rows += 1
            key = (section, row.get("frame", ""), row.get("player_id", ""))
            if key in emitted_keys:
                emitted_duplicates += 1
            emitted_keys.add(key)
    return {
        "checks": len(checks),
        "check_sections": len({row["section_id"] for row in checks}),
        "guard_rows": len(guard_rows),
        "guard_sections": len({row["section_id"] for row in guard_rows}),
        "replay_matrix_rows": len(matrices),
        "replay_matrix_keys": len(matrix_keys),
        "original_rows": len(originals),
        "original_keys": len(original_keys),
        "replay_emitted_files": len(list(emitted_dir.glob("*.tracking_data.csv"))),
        "replay_emitted_rows": emitted_rows,
        "replay_emitted_keys": len(emitted_keys),
        "replay_emitted_duplicate_keys": emitted_duplicates,
        "binding_deficits": deficits,
        "branch_trace_sha256": _sha256(base / "branch_trace.jsonl"),
        "matrices_sha256": _sha256(base / "matrices.jsonl"),
    }


def future_draw(root: Path) -> list[dict[str, object]]:
    """Prepare the sealed 30-section draw from source digest then section id."""
    base = root / G410
    checks = _read_jsonl(base / "branch_trace.jsonl")
    matrices = _read_jsonl(base / "matrices.jsonl")
    receipts = _read_csv(base / "source_receipts.csv")
    digest = {row["section_id"]: row["retained_sha256"] for row in receipts}
    sections = sorted({row["section_id"] for row in checks}, key=lambda item: (digest.get(item, ""), item))
    ticks: dict[str, list[int]] = defaultdict(list)
    for row in matrices:
        ticks[row["section_id"]].append(int(row["frame"]))
    result = []
    for section in exact_even(sections):
        values = sorted(set(ticks.get(section, [])))
        result.append({"section_id": section, "source_digest": digest.get(section, ""),
                       "middle_saved_tick": "UNKNOWN" if not values else values[(len(values) - 1) // 2]})
    return result


def premise_holds(census: dict[str, object]) -> bool:
    """Return only the binding premise specified by G416."""
    return (census["checks"] == 279 and census["check_sections"] == 37 and
            census["guard_rows"] == 7 and census["guard_sections"] == 5 and
            not census["binding_deficits"])


def write_json_lf(path: Path, payload: object) -> None:
    """Write a small preparation receipt using LF endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=1, sort_keys=True) + "\n").encode("utf-8"))
