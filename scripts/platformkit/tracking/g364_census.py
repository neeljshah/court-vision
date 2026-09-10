"""Census, seeded game-disjoint split, and source pinning for G364 phase 1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import subprocess
from collections import defaultdict
from pathlib import Path

ELIGIBLE_RESOLUTION = "1920x1080"
SEED = 364


def sha256_file(path: Path) -> str:
    """Stream one file to its full SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_unit(game_id: str, sport: str) -> dict[str, str] | None:
    """Split a ledger game id into competition, eleven-character video id, and offset."""
    if "_s" not in game_id:
        return None
    stem, _, offset = game_id.rpartition("_s")
    if not offset.isdigit() or len(stem) < 11:
        return None
    video_id, token = stem[-11:], stem[:-11].rstrip("-_")
    return {"section_id": game_id, "video_id": video_id, "offset_s": offset,
            "competition": sport + "/" + token if token else sport,
            "game_id": sport + ":" + video_id}


def census(ledger: Path) -> list[dict[str, str]]:
    """Enumerate every ledger row as a census line with its eligibility verdict."""
    rows: list[dict[str, str]] = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        unit = parse_unit(entry.get("game_id", ""), entry.get("sport", ""))
        reason = ""
        if unit is None:
            reason = "no_video_id_or_offset"
        elif entry.get("status") != "tracked":
            reason = "status_" + str(entry.get("status"))
        elif entry.get("source_resolution") != ELIGIBLE_RESOLUTION:
            reason = "resolution_" + str(entry.get("source_resolution"))
        elif not entry.get("source_duration"):
            reason = "no_duration"
        base = unit or {"section_id": entry.get("game_id", ""), "video_id": "", "offset_s": "",
                        "competition": entry.get("sport", ""), "game_id": ""}
        rows.append({**base, "sport": entry.get("sport", ""), "status": str(entry.get("status")),
                     "source_resolution": str(entry.get("source_resolution")),
                     "duration_s": "%.3f" % float(entry.get("source_duration") or 0.0),
                     "eligible": "0" if reason else "1", "ineligible_reason": reason})
    return rows


def split(eligible: list[dict[str, str]], dev_games: int, val_games: int,
          per_game: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Draw a seeded game-disjoint development and validation reservation."""
    by_game: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in eligible:
        by_game[row["game_id"]].append(row)
    games = sorted(by_game)
    random.Random(SEED).shuffle(games)
    if len(games) < dev_games + val_games:
        raise ValueError("census has too few distinct games for a disjoint split")
    picked = []
    for group in (games[:dev_games], games[dev_games:dev_games + val_games]):
        side = []
        for game in group:
            sections = sorted(by_game[game], key=lambda row: int(row["offset_s"]))
            step = max(1, len(sections) // per_game)
            side.extend(sections[::step][:per_game])
        picked.append(sorted(side, key=lambda row: (row["game_id"], int(row["offset_s"]))))
    if set(row["game_id"] for row in picked[0]) & set(row["game_id"] for row in picked[1]):
        raise ValueError("seeded split is not game-disjoint")
    return picked[0], picked[1]


def fetch(row: dict[str, str], scratch: Path, timeout: int) -> Path | None:
    """Fetch one pinned section with the recorded yt-dlp recipe, or report it absent."""
    start = int(row["offset_s"])
    end = start + int(math.ceil(float(row["duration_s"]) or 130.0))
    target = scratch / ("%s_s%d.mp4" % (row["video_id"], start))
    target.unlink(missing_ok=True)
    command = ["yt-dlp", "-f", "270/312", "--no-playlist", "--no-warnings",
               "--download-sections", "*%d-%d" % (start, end), "--merge-output-format", "mp4",
               "-o", str(target), "--", "https://www.youtube.com/watch?v=" + row["video_id"]]
    try:
        subprocess.run(command, check=True, timeout=timeout, capture_output=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return target if target.exists() and target.stat().st_size > 0 else None


def probe(path: Path) -> dict[str, str]:
    """Record the container facts every pinned source must carry."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,nb_read_frames,avg_frame_rate,codec_name",
                          "-count_frames", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True, timeout=900)
    stream = json.loads(out.stdout)["streams"][0]
    return {"source_width": str(stream["width"]), "source_height": str(stream["height"]),
            "frame_count": str(stream["nb_read_frames"]),
            "avg_frame_rate": str(stream["avg_frame_rate"]),
            "codec_name": str(stream["codec_name"])}


def pin(candidates: list[dict[str, str]], scratch: Path, quota: int, timeout: int,
        fetched_utc: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Fetch candidates in sealed order until the quota holds and pin every byte used."""
    scratch.mkdir(parents=True, exist_ok=True)
    pinned: list[dict[str, str]] = []
    absent: list[dict[str, str]] = []
    for row in candidates:
        if len(pinned) >= quota:
            break
        path = fetch(row, scratch, timeout)
        if path is None:
            absent.append({**row, "absent_reason": "fetch_failed"})
            print("ABSENT %s" % row["section_id"], flush=True)
            continue
        facts = probe(path)
        if facts["source_width"] != "1920" or int(facts["frame_count"]) < 40:
            absent.append({**row, "absent_reason": "probe_%sx%s_frames_%s" % (
                facts["source_width"], facts["source_height"], facts["frame_count"])})
            path.unlink(missing_ok=True)
            print("ABSENT %s probe" % row["section_id"], flush=True)
            continue
        pinned.append({**row, **facts, "source_path": str(path),
                       "byte_size": str(path.stat().st_size),
                       "source_sha256": sha256_file(path), "fetched_utc": fetched_utc})
        print("PINNED %s frames=%s" % (row["section_id"], facts["frame_count"]), flush=True)
    return pinned, absent


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write one LF manifest; nothing is written when the manifest is empty."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read one bounded manifest CSV in text mode."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _summarise(name: str, rows: list[dict[str, str]]) -> None:
    print("%s sections=%d games=%d competitions=%d" % (
        name, len(rows), len({row["game_id"] for row in rows}),
        len({row["competition"] for row in rows})))


def main() -> None:
    parser = argparse.ArgumentParser(description="G364 census, seeded split, and source pinning")
    parser.add_argument("action", choices=("census", "pin"))
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--out-dev", type=Path)
    parser.add_argument("--out-val", type=Path)
    parser.add_argument("--out-absent", type=Path)
    parser.add_argument("--dev-games", type=int, default=12)
    parser.add_argument("--val-games", type=int, default=16)
    parser.add_argument("--per-game", type=int, default=3)
    parser.add_argument("--quota", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--fetched-utc", default="")
    args = parser.parse_args()
    if args.action == "census":
        rows = census(args.ledger)
        eligible = [row for row in rows if row["eligible"] == "1"]
        write_csv(args.out, rows)
        development, validation = split(eligible, args.dev_games, args.val_games, args.per_game)
        write_csv(args.out_dev, development)
        write_csv(args.out_val, validation)
        print("census=%d eligible=%d" % (len(rows), len(eligible)))
        _summarise("development_candidates", development)
        _summarise("validation_reserved", validation)
        return
    pinned, absent = pin(read_csv(args.candidates), args.scratch, args.quota,
                         args.timeout, args.fetched_utc)
    write_csv(args.out, pinned)
    write_csv(args.out_absent, absent)
    _summarise("pinned", pinned)
    print("absent=%d" % len(absent))


if __name__ == "__main__":
    main()
