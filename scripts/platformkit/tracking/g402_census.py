"""G402 retained-source census, per-kind even draw and window receipts.

Censuses every retained native object tree on the pod (never the live feeder
working directory), classifies each by ACTUAL probed kind, and seals the even
30-per-kind draw plus the 10 s window the sealed rule names for each ordinal.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.platformkit.tracking.g402_prepare import DRAW_SIZE, even_draw, window_start

TREES = (
    ("footage_corpus", "/workspace/data/footage_corpus"),
    ("footage_bridge", "/workspace/data/footage_bridge"),
    ("g364_scratch_val", "/workspace/g364_scratch/val"),
)
EXCLUDED_TREES = {"/workspace/feeder/work": "LIVE_FEEDER_WORKING_DIR_NEVER_TOUCHED"}
CENSUS_FIELDS = ("kind", "competition", "game", "section_id", "source_tree", "source_path",
                 "source_bytes", "source_sha256", "width", "height", "avg_fps", "r_fps",
                 "codec_name", "duration_s", "usable_start_s", "usable_span_s",
                 "frame_cap", "eligible", "reason")
DRAW_FIELDS = CENSUS_FIELDS + ("draw_kind", "draw_order", "population",
                               "window_start_s", "start_frame", "frames", "window_end_s")
KINDS = ("1080p30", "720p60")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,codec_name",
         "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True)
    try:
        data = json.loads(out.stdout)
        stream = data["streams"][0]
    except (ValueError, KeyError, IndexError):
        return {}
    return {"width": int(stream.get("width") or 0), "height": int(stream.get("height") or 0),
            "avg_frame_rate": stream.get("avg_frame_rate", ""),
            "r_frame_rate": stream.get("r_frame_rate", ""),
            "codec_name": stream.get("codec_name", ""),
            "duration": float(data.get("format", {}).get("duration") or 0.0)}


def rate(value: str) -> float:
    try:
        num, den = value.split("/")
        return float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def classify(width: int, height: int, fps: float) -> str:
    if (width, height) == (1920, 1080) and 29.0 <= fps < 31.0:
        return "1080p30"
    if (width, height) == (1280, 720) and 59.0 <= fps < 61.0:
        return "720p60"
    return "OTHER_%dx%d_%.2f" % (width, height, fps)


def identity_of(name: str) -> tuple:
    stem = name[:-4] if name.endswith(".mp4") else name
    competition, section_id = stem.split("__", 1) if "__" in stem else ("UNDECLARED", stem)
    return competition, section_id.split("_s")[0], section_id


def census_rows(digest: bool) -> list[dict]:
    rows: list[dict] = []
    for tree_name, tree in TREES:
        for path in sorted(Path(tree).glob("*.mp4")):
            competition, game, section_id = identity_of(path.name)
            try:
                size = path.stat().st_size
            except OSError:
                rows.append({"kind": "VANISHED", "competition": competition, "game": game,
                             "section_id": section_id, "source_tree": tree_name,
                             "source_path": str(path), "source_bytes": 0, "eligible": "",
                             "reason": "ROTATED_AWAY_DURING_CENSUS"})
                continue
            info = probe(path)
            fps = rate(info.get("avg_frame_rate", "")) if info else 0.0
            kind = classify(info.get("width", 0), info.get("height", 0), fps) if info else "UNPROBEABLE"
            span = float(info.get("duration", 0.0))
            reason = ""
            if kind not in KINDS:
                reason = "KIND_NOT_TARGETED"
            elif size <= 0:
                reason = "SOURCE_BYTES_ZERO"
            elif span < 10.0:
                reason = "USABLE_SPAN_UNDER_10S"
            rows.append({
                "kind": kind, "competition": competition, "game": game,
                "section_id": section_id, "source_tree": tree_name,
                "source_path": str(path), "source_bytes": size,
                "source_sha256": sha256_file(path) if digest else "",
                "width": info.get("width", 0), "height": info.get("height", 0),
                "avg_fps": round(fps, 6), "r_fps": round(rate(info.get("r_frame_rate", "")), 6),
                "codec_name": info.get("codec_name", ""), "duration_s": round(span, 6),
                "usable_start_s": 0.0, "usable_span_s": round(span, 6),
                "frame_cap": 600 if kind == "720p60" else 300,
                "eligible": "" if reason else "YES", "reason": reason})
    seen: dict[str, str] = {}
    for row in rows:
        key = row["section_id"]
        if key in seen and not row["reason"]:
            row["eligible"], row["reason"] = "", "SECTION_ID_DUPLICATE_OF_%s" % seen[key]
        else:
            seen.setdefault(key, row["source_tree"])
    return rows


def draw_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    drawn: list[dict] = []
    supply: dict = {"excluded_trees": EXCLUDED_TREES}
    for kind in KINDS:
        pool = [row for row in rows if row["kind"] == kind and row["eligible"] == "YES"]
        supply[kind] = {"eligible_sections": len(pool),
                        "distinct_games": len({row["game"] for row in pool}),
                        "distinct_competitions": len({row["competition"] for row in pool}),
                        "trees": sorted({row["source_tree"] for row in pool}),
                        "required": DRAW_SIZE}
        if len(pool) < DRAW_SIZE:
            supply[kind]["supply"] = "PARTIAL"
            continue
        supply[kind]["supply"] = "COMPLETE"
        for row in even_draw(pool):
            ordinal = row["draw_order"]
            fps = row["avg_fps"]
            start = window_start(row["usable_start_s"], row["usable_span_s"], ordinal)
            drawn.append({**row, "draw_kind": kind, "window_start_s": round(start, 6),
                          "start_frame": int(round(start * fps)),
                          "frames": row["frame_cap"],
                          "window_end_s": round(start + 10.0, 6)})
    return drawn, supply


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-digest", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = census_rows(not args.no_digest)
    with (out / "census.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CENSUS_FIELDS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    drawn, supply = draw_rows(rows)
    with (out / "draw.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DRAW_FIELDS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(drawn)
    supply["census_rows"] = len(rows)
    supply["drawn"] = len(drawn)
    (out / "supply.json").write_text(json.dumps(supply, indent=2, sort_keys=True) + "\n",
                                     encoding="ascii")
    print(json.dumps(supply, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
