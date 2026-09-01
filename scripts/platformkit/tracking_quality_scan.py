"""Cross-sport tracking-quality scan: what is wrong with the tracks themselves.

The harness answers "does this game pass". It does not answer "why is the
tracking bad", and every diagnosis so far has needed a bespoke probe
(baseball_funnel_probe, tennis_metric_probe, tennis_coverage_probe). This
reports the same defect signatures for every sport so they can be compared.

Signals, chosen because each maps to a distinct real failure:
  tracks_per_frame      -- detector yield. A tennis rally has 2 players; 8 means
                           crowd or officials are being tracked.
  median_track_frames   -- identity continuity. A tracker that reassigns ids
                           every few frames produces thousands of stubs and
                           makes any per-player feature meaningless.
  singleton_share       -- share of ids seen in exactly ONE frame. High values
                           mean the tracker is not tracking at all, it is
                           re-detecting.
  stationary_share      -- share of ids whose total displacement is tiny. These
                           are officials, benches, logos and scoreboard
                           furniture, not players.
  churn_ratio           -- distinct ids divided by the busiest frame's track
                           count. 1.0 is perfect identity; 50 means ids are
                           being minted constantly.
  dup_frame_track       -- one id appearing twice in a frame. Always a bug.

Run:  python -m scripts.platformkit.tracking_quality_scan <csv> [<csv> ...]
      python -m scripts.platformkit.tracking_quality_scan --sport-best
"""
from __future__ import annotations

import argparse
import collections
import csv
import math
import sys
from pathlib import Path

STATIONARY_SPAN = 2.0  # units of whatever space the rows declare


def _rows(path: Path) -> list:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        print("unreadable %s: %s" % (path, exc))
        return []


def _number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def scan(path: Path) -> dict:
    """Return the defect signature for one tracking CSV."""
    rows = _rows(path)
    if not rows:
        return {"path": str(path), "rows": 0}
    players = [r for r in rows if (r.get("cls") or "player") == "player"]
    frames = {r.get("frame") for r in players}
    by_track: dict = collections.defaultdict(list)
    per_frame: dict = collections.Counter()
    seen_pairs: set = set()
    duplicates = 0
    for row in players:
        track, frame = row.get("track_id"), row.get("frame")
        by_track[track].append((_number(row.get("x")), _number(row.get("y"))))
        per_frame[frame] += 1
        if (frame, track) in seen_pairs:
            duplicates += 1
        seen_pairs.add((frame, track))

    lengths = sorted(len(v) for v in by_track.values())
    spans = []
    for points in by_track.values():
        xs = [p[0] for p in points if not math.isnan(p[0])]
        ys = [p[1] for p in points if not math.isnan(p[1])]
        if xs and ys:
            spans.append(max(max(xs) - min(xs), max(ys) - min(ys)))
    busiest = max(per_frame.values()) if per_frame else 0
    tracks = len(by_track)
    return {
        "path": str(path),
        "rows": len(players),
        "frames": len(frames),
        "tracks": tracks,
        "tracks_per_frame": round(len(players) / len(frames), 2) if frames else 0.0,
        "median_track_frames": lengths[len(lengths) // 2] if lengths else 0,
        "singleton_share": round(sum(1 for n in lengths if n == 1) / tracks, 4) if tracks else 0.0,
        "stationary_share": round(sum(1 for s in spans if s < STATIONARY_SPAN) / len(spans), 4) if spans else 0.0,
        "churn_ratio": round(tracks / busiest, 1) if busiest else 0.0,
        "dup_frame_track": duplicates,
        "space": (rows[0].get("coordinate_space") or "undeclared"),
    }


def render(reports: list) -> str:
    header = ("%-11s %-8s %-7s %-7s %-6s %-7s %-8s %-7s %-6s %s"
              % ("GAME", "rows", "frames", "tracks", "t/frm", "medlen",
                 "single", "static", "churn", "space"))
    lines = [header, "-" * len(header)]
    for r in reports:
        if not r.get("rows"):
            lines.append("%-11s EMPTY" % Path(r["path"]).parent.name[:11])
            continue
        lines.append("%-11s %-8s %-7s %-7s %-6s %-7s %-8s %-7s %-6s %s" % (
            Path(r["path"]).parent.name[:11], r["rows"], r["frames"], r["tracks"],
            r["tracks_per_frame"], r["median_track_frames"],
            r["singleton_share"], r["stationary_share"], r["churn_ratio"],
            r["space"]))
    return "\n".join(lines)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="*", type=Path)
    args = parser.parse_args(argv[1:])
    if not args.csvs:
        print("usage: tracking_quality_scan.py <tracking_data.csv> [...]")
        return 2
    print(render([scan(p) for p in args.csvs]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
