"""G404 gate audit: the sealed even draw of admitted and excluded candidates.

Draws 30 gate-admitted and 30 gate-excluded rows evenly within each FULL stratum,
renders one native full-resolution card per drawn row and freezes a blind dispatch
order derived from the sealed preregistration seal. No gate output, no ball
coordinate and no stratum name ever reaches a card or a card name.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g404_gate import read_csv, write_csv

AUDIT_N = 30
DRAW_FIELDS = ("card_id", "dispatch_position", "stratum", "stratum_index", "frame_key",
               "video_id", "canonical_game", "competition", "pts", "frame_index",
               "width", "height", "pixel_sha256", "card_path", "card_bytes",
               "card_sha256")


def even_indices(size: int, count: int) -> list[int]:
    """The sealed whole-stratum even draw: floor(j*(N-1)/(count-1)+0.5)."""
    if count < 1 or size < count:
        raise ValueError("impossible even draw: %d from %d" % (count, size))
    if count == 1:
        return [0]
    return [int((index * (size - 1) / (count - 1)) + 0.5) for index in range(count)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def stratum_rows(rows: list[dict], admitted: bool) -> list[dict]:
    wanted = "1" if admitted else "0"
    return sorted((row for row in rows if row["gate_admitted"] == wanted),
                  key=lambda row: (row["canonical_game"], float(row["pts"]),
                                   row["pixel_sha256"]))


def render_native(container: Path, index: int, card: Path) -> int:
    """One native full-resolution card; nothing is resized, cropped or annotated."""
    capture = cv2.VideoCapture(str(container))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise ValueError("unreadable native frame %d in %s" % (index, container))
    card.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(card), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    return card.stat().st_size


def run(args) -> int:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(1)
    rows = [row for row in read_csv(Path(args.gate_outputs))
            if row["status"] == "DECODED" and row["gate_admitted"] in ("0", "1")]
    sources = {row["video_id"]: Path(args.sources) / Path(row["median_section_path"]).name
               for row in read_csv(Path(args.census))}
    drawn: list[dict] = []
    for admitted in (True, False):
        stratum = stratum_rows(rows, admitted)
        name = "ADMITTED" if admitted else "EXCLUDED"
        if len(stratum) < AUDIT_N:
            raise ValueError("stratum %s holds %d rows, below the sealed %d"
                             % (name, len(stratum), AUDIT_N))
        for position, index in enumerate(even_indices(len(stratum), AUDIT_N)):
            row = stratum[index]
            drawn.append({"stratum": name, "stratum_index": index, "frame_key": row["frame_key"],
                          "video_id": row["video_id"], "canonical_game": row["canonical_game"],
                          "competition": row["competition"], "pts": row["pts"],
                          "frame_index": row["frame_index"], "width": row["width"],
                          "height": row["height"], "pixel_sha256": row["pixel_sha256"],
                          "stratum_position": position})
    order = list(range(len(drawn)))
    random.Random(args.seed).shuffle(order)
    cards = out / "cards"
    records: list[dict] = []
    for dispatch, source_index in enumerate(order):
        row = drawn[source_index]
        card_id = "card_%02d" % dispatch
        card = cards / (card_id + ".jpg")
        size = render_native(sources[row["video_id"]], int(row["frame_index"]), card)
        records.append({**row, "card_id": card_id, "dispatch_position": dispatch,
                        "card_path": str(card).replace("\\", "/"), "card_bytes": size,
                        "card_sha256": sha256_file(card)})
    records.sort(key=lambda row: row["dispatch_position"])
    write_csv(out / "gate_audit_draw.csv", DRAW_FIELDS, records)
    seal = {"seed": args.seed, "cards": len(records),
            "admitted_cards": sum(1 for row in records if row["stratum"] == "ADMITTED"),
            "excluded_cards": sum(1 for row in records if row["stratum"] == "EXCLUDED"),
            "admitted_stratum": len(stratum_rows(rows, True)),
            "excluded_stratum": len(stratum_rows(rows, False)),
            "draw_sha256": hashlib.sha256(
                "".join(row["frame_key"] for row in records).encode("ascii")).hexdigest(),
            "dispatch_sha256": hashlib.sha256(
                "".join(row["card_id"] + row["card_sha256"]
                        for row in records).encode("ascii")).hexdigest()}
    (out / "gate_audit_seal.json").write_text(json.dumps(seal, indent=1, sort_keys=True)
                                              + "\n", encoding="ascii")
    print(json.dumps(seal, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g404_audit")
    for flag in ("--gate-outputs", "--census", "--sources", "--out-dir", "--seed"):
        parser.add_argument(flag, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
