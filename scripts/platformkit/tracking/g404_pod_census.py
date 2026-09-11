"""G404 pod-side census of the ENTIRE retained native source pool.

Enumerates every retained basketball-family section under the pod corpus and the
deploy bridge, ffprobes each for actual width/height/fps/duration, resolves the
feeder discovery title per video id and hashes one median-offset section per id.
Reads only; writes solely into the row scratch directory it is given.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

NAME = re.compile(r"^(?P<sport>[a-z_]+)__(?P<tag>[a-z0-9_]+)-(?P<vid>[A-Za-z0-9_-]+)_s(?P<off>\d+)\.mp4$")
NEW = re.compile(r"^NEW\s+(?P<sport>\S+)\s+(?P<tag>\S+)\s+(?P<vid>\S+)\s+(?P<dur>\S+)\s+"
                 r"fmt=\S+\s+fps=\S+\s+probe=\S+\s*(?P<title>.*)$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def titles(log: Path) -> dict[str, str]:
    """Video id -> discovery title; the last discovery line for an id wins."""
    found: dict[str, str] = {}
    if not log.exists():
        return found
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = NEW.match(line.strip())
        if match:
            found[match.group("vid")] = match.group("title").strip()
    return found


def probe(path: Path) -> dict:
    """Actual container probe; a failure is recorded, never guessed."""
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,avg_frame_rate:format=duration", "-of", "json", str(path)]
    try:
        raw = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except Exception as error:  # noqa: BLE001 - recorded, never raised away
        return {"probe_status": "probe_failed:" + type(error).__name__}
    if raw.returncode != 0:
        return {"probe_status": "probe_rc_%d" % raw.returncode}
    try:
        payload = json.loads(raw.stdout)
        stream = payload["streams"][0]
        numerator, _, denominator = str(stream.get("avg_frame_rate", "0/1")).partition("/")
        fps = float(numerator) / float(denominator) if float(denominator or 0) else 0.0
        return {"width": int(stream.get("width") or 0), "height": int(stream.get("height") or 0),
                "fps": fps, "duration_s": float(payload["format"]["duration"]),
                "probe_status": "ok"}
    except Exception as error:  # noqa: BLE001
        return {"probe_status": "probe_parse:" + type(error).__name__}


def scan(directories: list[Path], title_map: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.mp4")):
            match = NAME.match(path.name)
            if not match:
                rows.append({"parse": "unparsed_name", "file": path.name, "path": str(path),
                             "bytes": path.stat().st_size})
                continue
            row = {"parse": "ok", "file": path.name, "path": str(path),
                   "bytes": path.stat().st_size, "sport_tag": match.group("sport"),
                   "league_tag": match.group("tag"), "video_id": match.group("vid"),
                   "offset_s": int(match.group("off")),
                   "title": title_map.get(match.group("vid"), "")}
            row.update(probe(path))
            rows.append(row)
    return rows


def median_sections(rows: list[dict]) -> list[dict]:
    """The sealed median rule: offset-ordered sections, index (n-1)//2."""
    by_game: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("parse") == "ok":
            by_game.setdefault(row["video_id"], []).append(row)
    chosen = []
    for _, group in sorted(by_game.items()):
        ordered = sorted(group, key=lambda item: (item["offset_s"], item["file"]))
        chosen.append(ordered[(len(ordered) - 1) // 2])
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(prog="g404_pod_census")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--bridge", required=True)
    parser.add_argument("--discover-log", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = scan([Path(args.corpus), Path(args.bridge)], titles(Path(args.discover_log)))
    with (out / "census.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    lines = []
    for row in median_sections(rows):
        lines.append(sha256_file(Path(row["path"])) + "  " + row["path"])
    (out / "digests.txt").write_text("\n".join(lines) + "\n", encoding="ascii")
    print("SECTIONS", len(rows), "GAMES", len(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
