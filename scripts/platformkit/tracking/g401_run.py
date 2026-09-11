"""G401 driver: cache decoded PTS, then build the two tables from that cache.

Usage:
  python -m scripts.platformkit.tracking.g401_run decode   <receiver>
  python -m scripts.platformkit.tracking.g401_run tables   <receiver> <evidence>
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from scripts.platformkit.tracking.g401_census import (
    even_draw, load_digests, load_probe, shadow_population)
from scripts.platformkit.tracking.g401_measure import (
    decode_pts, paired_caps, policy_row, policy_totals, pts_summary)


def _cache_path(receiver: Path, name: str) -> Path:
    return receiver / "pts_cache" / (name + ".json")


def decode_all(receiver: Path) -> int:
    """Decode every retained source once; the cache is the immutable input."""
    (receiver / "pts_cache").mkdir(exist_ok=True)
    done = 0
    for video in sorted((receiver / "sources").iterdir()):
        target = _cache_path(receiver, video.name)
        if target.exists():
            continue
        pts = decode_pts(video)
        target.write_text(json.dumps(pts), encoding="utf-8")
        done += 1
        print("decoded %s frames=%d" % (video.name, len(pts)), flush=True)
    return done


def load_cached(receiver: Path, name: str) -> list[float] | None:
    path = _cache_path(receiver, name)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_tables(receiver: Path, evidence: Path) -> dict:
    """Policy table, draw, paired arms and per-source PTS identity."""
    probe = {r["name"]: r for r in load_probe(receiver / "corpus_probe.txt")}
    digests = load_digests(receiver / "corpus_digests.txt")
    population = shadow_population(list(probe.values()), digests)
    drawn = even_draw(population)

    pts_rows, summaries = [], {}
    for name in sorted({d["name"] for d in drawn} |
                       {p.name for p in (receiver / "sources").iterdir()}):
        pts = load_cached(receiver, name)
        entry = probe.get(name, {})
        fps = entry.get("validated_fps")
        summary = pts_summary(pts, fps) if pts is not None else None
        summaries[name] = summary
        pts_rows.append({"source_name": name, "validated_fps": fps,
                         "fps_basis": entry.get("fps_basis"),
                         "avg_frame_rate": entry.get("avg_frame_rate"),
                         "r_frame_rate": entry.get("r_frame_rate"),
                         "retained": pts is not None,
                         **(summary or {"pts_count": None, "first_pts": None,
                                        "last_pts": None, "available_span_s": None,
                                        "monotonic": None, "rate_validated": None,
                                        "uniform_steps": None,
                                        "off_grid_steps": None,
                                        "duplicate_pts_steps": None,
                                        "dropped_frames": None,
                                        "max_interval_error_s": None})})

    window = [json.loads(line) for line in
              (receiver / "window_ledger.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]
    policy_rows = []
    for entry in window:
        name = entry.get("_source_name", "") + ".mp4"
        record = probe.get(name, {})
        fps = record.get("validated_fps") or entry.get("source_fps")
        policy_rows.append(policy_row(entry, summaries.get(name), fps))
    totals = policy_totals(policy_rows)

    paired_rows = []
    for item in drawn:
        pts = load_cached(receiver, item["name"])
        summary = summaries.get(item["name"])
        row = paired_caps(item["name"], pts or [], item["validated_fps"],
                          bool(summary and summary["rate_validated"]))
        row["draw_j"] = item["draw_j"]
        row["draw_index"] = item["draw_index"]
        row["competition"] = item["competition"]
        row["game"] = item["game"]
        row["section"] = item["section"]
        row["digest"] = item["digest"]
        paired_rows.append(row)

    draw_rows = [{"draw_j": d["draw_j"], "draw_index": d["draw_index"],
                  "source_name": d["name"], "competition": d["competition"],
                  "game": d["game"], "section": d["section"],
                  "validated_fps": d["validated_fps"], "fps_basis": d["fps_basis"],
                  "stream_duration_s": d["stream_duration_s"],
                  "height": d["height"], "bytes": d["bytes"], "digest": d["digest"]}
                 for d in drawn]
    census_rows = [{"source_name": r["name"], "competition": r["competition"],
                    "game": r["game"], "section": r["section"],
                    "avg_frame_rate": r["avg_frame_rate"],
                    "r_frame_rate": r["r_frame_rate"],
                    "validated_fps": r["validated_fps"], "fps_basis": r["fps_basis"],
                    "stream_duration_s": r["stream_duration_s"], "height": r["height"],
                    "nb_frames": r["nb_frames"], "bytes": r["bytes"],
                    "in_shadow_population": r["name"] in {p["name"] for p in population},
                    "in_draw": r["name"] in {d["name"] for d in drawn}}
                   for r in probe.values()]

    evidence.mkdir(parents=True, exist_ok=True)
    _write_csv(evidence / "census.csv", census_rows)
    _write_csv(evidence / "draw.csv", draw_rows)
    _write_csv(evidence / "pts.csv", pts_rows)
    _write_csv(evidence / "policy_per_section.csv", policy_rows)
    _write_csv(evidence / "paired_caps.csv", paired_rows)
    reach = [r for r in paired_rows if r["cap_basis"] == "VALIDATED_FPS"]
    return {"population_n": len(population), "draw_n": len(drawn),
            "census_n": len(census_rows), "policy": totals,
            "paired_valid_n": len(reach),
            "paired_reaching_target_n": sum(1 for r in reach
                                            if r["arm_b_reaches_target"]),
            "paired_arm_a_reaching_target_n": sum(1 for r in paired_rows
                                                  if abs((r["arm_a_span_s"] or 0) - 100.0)
                                                  <= (r["native_frame_interval_s"] or 1e9))}


def main(argv: list[str]) -> int:
    action, receiver = argv[1], Path(argv[2])
    if action == "decode":
        print("newly decoded", decode_all(receiver))
        return 0
    if action == "tables":
        result = build_tables(receiver, Path(argv[3]))
        print(json.dumps(result, indent=1, sort_keys=True))
        return 0
    raise SystemExit("unknown action %s" % action)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
