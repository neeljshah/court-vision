"""Build and guard G384's native-scale frames table for the inherited scorer."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from scripts.platformkit.tracking.g363_ball_coverage import FRAME_FIELDS, read_csv, write_csv

EXTRA_FIELDS = ("source", "format_id")


def native_rows(sealed: list[dict], extra: list[dict]) -> list[dict]:
    """Preserve G363 identity fields while setting the new native reference scale."""
    rows: list[dict] = []
    for source, items in (("sealed", sealed), ("extra", extra)):
        for row in items:
            item = {field: row.get(field, "") for field in FRAME_FIELDS}
            item.update({"source": source, "format_id": row.get("format_id", ""),
                         "sheet_scale": "1.0"})
            rows.append(item)
    keys = [row["frame_key"] for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate-frame-key native-frames")
    return rows


def require_native_scale(frames: Sequence[dict]) -> None:
    """Refuse a scaled sheet table before it can reach the G363 scorer."""
    bad = [row["frame_key"] for row in frames if float(row["sheet_scale"]) != 1.0]
    if bad:
        raise ValueError("REFUSED sheet_scale != 1.0 keys=" + ",".join(bad[:3]))


def score_native_arm(arm: str, split: str, frames: Sequence[dict], refs: dict[str, dict],
                     predictions: Sequence[dict]) -> tuple[dict, list[dict]]:
    """Call the inherited scorer only after the native-scale assertion succeeds."""
    require_native_scale(frames)
    from scripts.platformkit.tracking.g363_score import score_arm
    return score_arm(arm, split, frames, refs, predictions)


def run(args) -> int:
    """Create the additive full-schema frames_v2 table without scoring."""
    rows = native_rows(read_csv(Path(args.sealed_frames)), read_csv(Path(args.extra_frames)))
    require_native_scale(rows)
    write_csv(Path(args.out), FRAME_FIELDS + EXTRA_FIELDS, rows)
    print("NATIVE-FRAMES rows=%d sheet_scale=1.0" % len(rows))
    return 0
