"""Small I/O helpers shared by the G401 finish and repeat processes."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

FLOAT_KEYS = ('arm_a_span_s', 'arm_b_span_s', 'arm_a_loss_s', 'arm_b_loss_s', 'native_frame_interval_s', 'validated_fps', 'arm_a_last_admitted_pts', 'arm_a_first_excluded_pts', 'arm_b_last_admitted_pts', 'arm_b_first_excluded_pts')
INT_KEYS = ('draw_j', 'arm_a_frame_cap', 'arm_b_frame_cap', 'arm_a_read_frames', 'arm_b_read_frames', 'source_frame_count', 'declared_stride_opportunities')


def sha256_file(path: Path) -> str:
    """SHA-256 over one file's exact bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="ascii", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def retype(row: dict) -> dict:
    """CSV text back to the numbers the renderer needs."""
    item = dict(row)
    for key in FLOAT_KEYS:
        item[key] = float(row[key]) if row.get(key) not in ("", "None", None) else None
    for key in INT_KEYS:
        item[key] = int(row[key]) if row.get(key) not in ("", "None", None) else None
    item["arm_b_reaches_target"] = row["arm_b_reaches_target"] == "True"
    return item
