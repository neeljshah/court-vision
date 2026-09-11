"""Reproduce G385's binding G375 counts and make a development exclusion census."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read one bounded CSV manifest."""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def census(labels: list[dict[str, str]], sample: list[dict[str, str]],
           candidates: list[dict[str, str]], development: list[dict[str, str]]) -> tuple[dict[str, int], list[dict[str, str]]]:
    """Validate the exact premise and name every candidate excluded by development video."""
    sample_by_sheet = {row["sheet_id"]: row for row in sample}
    if not {row["sheet_id"] for row in labels} <= set(sample_by_sheet):
        raise ValueError("a rated G375 sheet is absent from the sealed sample")
    counts: dict[str, int] = {}
    for row in labels:
        counts[row["final_label"]] = counts.get(row["final_label"], 0) + 1
    other_videos = {sample_by_sheet[row["sheet_id"]]["video_id"] for row in labels
                    if row["final_label"] == "OTHER_SPORT"}
    if (len(labels), sum(value for key, value in counts.items() if key != "BASKETBALL_PLAY"),
            counts.get("OTHER_SPORT", 0), other_videos) != (281, 127, 6, {"oW8psSa2hf4"}):
        raise ValueError("G385 binding G375 premise did not reproduce")
    g375_dev = {row["video_id"] for row in sample if row.get("video_id")}
    g364_dev = {row["video_id"] for row in development if row.get("video_id")}
    excluded = []
    for row in candidates:
        video = row.get("video_id", "")
        reason = "g375_labelled_video" if video in g375_dev else (
            "g364_development_video" if video in g364_dev else "")
        if reason:
            excluded.append({"game_id": row.get("game_id", ""), "video_id": video, "reason": reason})
    summary = {"g375_rated": len(labels), "g375_nonplay": 127,
               "g375_other_sport": 6, "candidate_rows": len(candidates),
               "g375_development_videos": len(g375_dev), "g364_development_videos": len(g364_dev),
               "excluded_rows": len(excluded)}
    return summary, excluded


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    """Write an LF-only exclusion receipt outside operational storage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("game_id", "video_id", "reason"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="G385 binding premise census")
    parser.add_argument("--g375-labels", type=Path, required=True)
    parser.add_argument("--g375-sample", type=Path, required=True)
    parser.add_argument("--g375-census", type=Path, required=True)
    parser.add_argument("--g364-development", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary, excluded = census(read_rows(args.g375_labels), read_rows(args.g375_sample),
                               read_rows(args.g375_census), read_rows(args.g364_development))
    write_rows(args.out, excluded)
    print("PREMISE TRUE g375_rated=%d g375_nonplay=%d other_sport=%d candidate_rows=%d excluded=%d" % (
        summary["g375_rated"], summary["g375_nonplay"], summary["g375_other_sport"],
        summary["candidate_rows"], summary["excluded_rows"]))


if __name__ == "__main__":
    main()
