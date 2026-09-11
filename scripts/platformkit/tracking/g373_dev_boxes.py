"""G373 phase 1: the development label set and its per-box provenance.

Only an ADJUDICATED or AGREED VISIBLE box on a DEVELOPMENT frame counts toward the
sealed quota of >= 500 unique boxes from >= 5 development games.  ABSENT and
UNKNOWN outcomes are retained in the census and reported, never discarded, and a
box whose frame is a causal neighbour of another counted box does not count twice.

Every row carries the source identity the amendment requires (contract A9: the full
path, byte size and resolution of the input, never a game id alone), so a box can
be traced back to the exact section bytes and decoded frame index it came from.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import read_csv, write_csv

BOX_FIELDS = ("frame_key", "game", "section", "offset_s", "format_id", "section_path",
              "section_bytes", "section_sha256", "frame_index", "width", "height",
              "sheet", "sheet_sha256", "label", "box_x", "box_y", "box_w", "box_h",
              "cx", "cy", "diameter", "decided_by", "sol_label", "sol_cx", "sol_cy",
              "terra_label", "terra_cx", "terra_cy", "source")


def provenance(frames_csv: Path, extra_csv: Path, sources_csv: Path) -> dict[str, dict]:
    """Source identity per development frame key, sealed frames and extras alike."""
    rung = {row["section"]: ("312" if row["status"].endswith("312") else "270")
            for row in read_csv(sources_csv) if row["status"].startswith("OK")}
    out: dict[str, dict] = {}
    for row in read_csv(frames_csv):
        if row["split"] != "development":
            continue
        out[row["frame_key"]] = {
            "game": row["game"], "section": row["section"], "offset_s": row["offset_s"],
            "format_id": rung.get(row["section"], ""), "section_path": row["section_path"],
            "section_bytes": row["section_bytes"], "section_sha256": row["section_sha256"],
            "frame_index": row["frame_index"], "width": row["width"], "height": row["height"],
            "source": "sealed"}
    if extra_csv and Path(extra_csv).exists():
        for row in read_csv(extra_csv):
            out[row["frame_key"]] = {key: row[key] for key in
                                     ("game", "section", "offset_s", "format_id",
                                      "section_path", "section_bytes", "section_sha256",
                                      "frame_index", "width", "height")}
            out[row["frame_key"]]["source"] = "extra"
    return out


def run(args) -> int:
    sources = provenance(Path(args.frames), Path(args.extra), Path(args.sources))
    sheets = {row["frame_key"]: row for row in read_csv(Path(args.manifest))}
    primaries: dict[str, dict[str, dict]] = {}
    for row in read_csv(Path(args.ratings)):
        if row["rater"] in ("sol", "terra"):
            primaries.setdefault(row["frame_key"], {})[row["rater"]] = row

    rows: list[dict] = []
    labels = {"VISIBLE": 0, "ABSENT": 0, "UNKNOWN": 0}
    claimed: set[tuple[str, int]] = set()
    skipped_neighbour = 0
    for entry in read_csv(Path(args.reference)):
        key = entry["frame_key"]
        origin = sources.get(key)
        if origin is None:
            continue
        labels[entry["label"]] = labels.get(entry["label"], 0) + 1
        if entry["label"] != "VISIBLE":
            continue
        index = int(origin["frame_index"])
        neighbour = next((item for item in claimed
                          if item[0] == origin["section"] and abs(item[1] - index) <= 2), None)
        if neighbour is not None:
            skipped_neighbour += 1
            continue
        claimed.add((origin["section"], index))
        pair = primaries.get(key, {})
        sheet = sheets.get(key, {})
        rows.append({"frame_key": key, "sheet": sheet.get("sheet", ""),
                     "sheet_sha256": sheet.get("sheet_sha256", ""),
                     "label": entry["label"],
                     **{field: entry[field] for field in
                        ("box_x", "box_y", "box_w", "box_h", "cx", "cy", "diameter",
                         "decided_by")},
                     **{f"{rater}_{field}": pair.get(rater, {}).get(field, "")
                        for rater in ("sol", "terra") for field in ("label", "cx", "cy")},
                     **origin})
    write_csv(Path(args.out), BOX_FIELDS, rows)
    games = sorted({row["game"] for row in rows})
    payload = {"boxes": len(rows), "unique_frames": len({row["frame_key"] for row in rows}),
               "games": len(games), "game_ids": games,
               "by_source": {name: sum(1 for row in rows if row["source"] == name)
                             for name in ("sealed", "extra")},
               "development_reference_labels": labels,
               "skipped_causal_neighbour": skipped_neighbour,
               "quota": {"boxes_required": 500, "games_required": 5,
                         "met": bool(len(rows) >= 500 and len(games) >= 5)}}
    Path(args.summary).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                                  encoding="ascii", newline="\n")
    print("DEV-BOXES " + json.dumps({key: payload[key] for key in
                                     ("boxes", "games", "by_source", "quota")}, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g373_dev_boxes")
    for flag in ("--frames", "--sources", "--manifest", "--ratings", "--reference",
                 "--out", "--summary"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--extra", default="")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
