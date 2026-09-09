"""G361 source/table identity map -- census, sources, links, sample, align, summary.
Builder-prepared (Q1): each subcommand writes an artifact, none scores a verdict. Offline
and deterministic; archived tables reach 92 MB and are streamed, never read whole.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

UNKNOWN = "UNKNOWN"
BAR_FRAMES = 1.0
LANDMARKS = 30
TAKE_ALL_AT = 40
STAMP = "%Y-%m-%dT%H:%M:%SZ"
BINDING = ("source_sha256", "source_first_pts", "source_fps", "source_width",
           "source_height", "source_topcut_px")
LEDGER_FIELDS = ("game_id", "finished_at", "seconds", "rows", "decoded_frames",
                 "evaluated_frames", "stride", "source_duration", "probe_status")
MARKERS = ("deploy_manifest.json", "code_identity.json")
SOURCE_FIELDS = ("game_id", "video_id", "requested_start_s", "requested_end_s",
                 "actual_first_pts", "fps", "width", "height", "topcut_px",
                 "source_sha256", "bytes", "fetch_utc", "format_id", "path")
LINK_FIELDS = ("game_id", "video_id", "requested_start_s", "run_start_utc", "table_sha256",
               "ball_table_sha256", "deploy_manifest_sha256", "source_sha256",
               "join_class", "reason")
SECTION_KEYS = ("game_id", "video_id", "requested_start_s", "join_class")
GID = re.compile(r"^(?:(?P<tag>[A-Za-z0-9]+)-)?(?P<ytid>[A-Za-z0-9_-]{11})_s(?P<off>\d+)$")
SECTION = re.compile(r"\*(\d+)-(\d+)")
FORMAT_ID = re.compile(r"-f\s+(\S+)")
TOPCUT = re.compile(r"^TOPCUT\s*=\s*(\d+)", re.M)

def parse_gid(stem: str) -> dict | None:
    rest = stem.rpartition("__")[2]
    match = GID.match(rest)
    return None if match is None else {"game_id": rest, "ytid": match["ytid"],
                                       "offset": int(match["off"])}

def sha256_file(path) -> str:
    """Streamed digest, UNKNOWN when unreadable -- absence is not a defect (B3)."""
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return UNKNOWN

def read_ledger(path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                rows.append({"game_id": None, "unparsed": True})
    return rows

def read_csv(path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))

def write_csv(path: Path, rows: list[dict], fields, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = append and path.exists()
    with path.open("a" if append else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else list(fields))
        if not existed:
            writer.writeheader()
        writer.writerows(rows)


def even_sample(items: list, minimum: int = LANDMARKS, take_all_at: int = TAKE_ALL_AT) -> list:
    """All when n <= take_all_at, else every k-th with k = floor(n/minimum): stepping
    spans first to last, so this is never a head slice (B7), never truncated back."""
    n = len(items)
    return list(items) if n <= take_all_at else list(items[::max(1, n // minimum)])


def probe(path, first_only: bool = False) -> dict:
    """Stream geometry, rate and presentation stamps; UNKNOWN cells when unreadable."""
    command = (["ffprobe", "-v", "error", "-select_streams", "v:0"]
               + (["-read_intervals", "%+#1"] if first_only else [])
               + ["-show_entries", "stream=width,height,avg_frame_rate:frame=pts_time",
                  "-of", "json", str(path)])
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=900)
        data = json.loads(done.stdout) if done.returncode == 0 else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        data = {}
    stream = (data.get("streams") or [{}])[0]
    stamps = []
    for frame in data.get("frames") or []:
        try:
            stamps.append(float(frame["pts_time"]))
        except (KeyError, TypeError, ValueError):
            continue
    num, _, den = str(stream.get("avg_frame_rate", "")).partition("/")
    fps = float(num) / float(den) if num.isdigit() and den.isdigit() and int(den) else 0.0
    return {"width": stream.get("width", UNKNOWN), "height": stream.get("height", UNKNOWN),
            "fps": fps, "first_pts": stamps[0] if stamps else UNKNOWN, "pts": stamps}


def archived_ticks(table, count: int = LANDMARKS) -> list:
    seen: dict[int, float] = {}
    try:
        with Path(table).open("r", encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                try:
                    seen.setdefault(int(row["frame"]), float(row.get("timestamp") or 0.0))
                except (KeyError, TypeError, ValueError):
                    continue
    except OSError:
        return []
    return even_sample(sorted(seen.items()), count, count + 10)


def aligned_games(path) -> set:
    by_game: dict[str, list] = {}
    for row in read_csv(path) if path and Path(path).exists() else []:
        by_game.setdefault(row["game_id"], []).append(row)
    return {g for g, rows in by_game.items()
            if len({r["landmark"] for r in rows}) >= LANDMARKS
            and all(r["within_bar"] == "1" for r in rows)}


def cmd_census(args) -> None:
    ledger = read_ledger(args.ledger)
    counts = {"ledger_rows": len(ledger), "distinct_game_ids":
              len({r.get("game_id") for r in ledger if r.get("game_id")})}
    counts.update({"ledger_present_" + f: sum(1 for r in ledger if r.get(f) is not None)
                   for f in LEDGER_FIELDS})
    root, heads = Path(args.tracking), []
    for game in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        try:  # header line only: an archived table reaches 92 MB and is never read whole
            with (game / "tracking_data.csv").open(encoding="utf-8", errors="replace") as handle:
                heads.append(next(csv.reader(handle), []))
        except OSError:
            heads.append([])
    tables = [h for h in heads if h]
    counts.update({"table_header_" + f: sum(1 for h in tables if f in h) for f in BINDING})
    complete = sum(1 for h in tables if all(f in h for f in BINDING))
    counts.update(tables_readable=len(tables), tables_unreadable=len(heads) - len(tables),
                  tables_complete_binding=complete)
    write_csv(Path(args.out) / "census.csv", [{"field": k, "count": v, "denominator":
              counts["ledger_rows"] if k.startswith(("ledger", "distinct")) else len(tables)}
              for k, v in sorted(counts.items())], ["field", "count", "denominator"])
    share = complete / len(tables) if tables else 0.0
    print("ledger_rows=%d tables_readable=%d tables_unreadable=%d complete_binding=%d share=%.4f"
          % (len(ledger), len(tables), len(heads) - len(tables), complete, share))
    print("PREMISE FALSE" if share >= 0.95 else "PREMISE HOLDS (share below 0.95)")


def cmd_sources(args) -> None:
    route = Path(args.repo or ".") / "src/tracking/video_handler.py"
    found = TOPCUT.search(route.read_text("utf-8", "replace")) if route.exists() else None
    cut, rows = found.group(1) if found else UNKNOWN, []
    for directory in args.dirs:
        folder = Path(directory)
        for video in sorted(folder.glob("*.mp4")) if folder.is_dir() else []:
            parsed = parse_gid(video.stem)
            if parsed is None:
                continue
            log = video.with_suffix(".log")
            text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            span, fmt, stat = SECTION.search(text), FORMAT_ID.search(text), video.stat()
            meta = probe(video, first_only=True)
            rows.append(dict(zip(SOURCE_FIELDS, (
                parsed["game_id"], parsed["ytid"], span.group(1) if span else parsed["offset"],
                span.group(2) if span else UNKNOWN, meta["first_pts"], meta["fps"] or UNKNOWN,
                meta["width"], meta["height"], cut, sha256_file(video), stat.st_size,
                datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime(STAMP),
                fmt.group(1) if fmt else UNKNOWN, str(video)))))
    rows.sort(key=lambda r: (r["game_id"], r["path"]))
    write_csv(Path(args.out) / "sources.csv", rows, SOURCE_FIELDS)
    print("sources=%d" % len(rows))


def cmd_links(args) -> None:
    sources = {r["game_id"]: r for r in read_csv(args.sources)} \
        if args.sources and Path(args.sources).exists() else {}
    aligned, root, rows = aligned_games(args.alignment), Path(args.tracking), []
    for game_id, entry in sorted({e["game_id"]: e for e in read_ledger(args.ledger)
                                  if e.get("game_id")}.items()):
        folder = root / game_id
        table_sha = sha256_file(folder / "tracking_data.csv")
        parsed = parse_gid(game_id) or {"ytid": UNKNOWN, "offset": UNKNOWN}
        source = sources.get(game_id)
        if table_sha == UNKNOWN:
            join, reason = UNKNOWN, "table_unreadable"
        elif source and len(str(source.get("source_sha256", ""))) == 64:
            join, reason = "EXACT", "source_bytes_present_and_hash_bound"
        elif game_id in aligned:
            join, reason = "ALIGNED", "landmarks_within_bar"
        else:
            join, reason = UNKNOWN, "no_source_bytes_and_no_alignment"
        try:
            start = datetime.fromtimestamp(int(entry["finished_at"]) - int(entry["seconds"]),
                                           timezone.utc).strftime(STAMP)
        except (KeyError, TypeError, ValueError):
            start = UNKNOWN
        rows.append(dict(zip(LINK_FIELDS, (
            game_id, parsed["ytid"], parsed["offset"], start, table_sha,
            sha256_file(folder / "ball_tracking.csv"),
            next((sha256_file(folder / m) for m in MARKERS if (folder / m).exists()), UNKNOWN),
            (source or {}).get("source_sha256", UNKNOWN), join, reason))))
    write_csv(Path(args.out) / "ledger_links.csv", rows, LINK_FIELDS)
    print("links=%d" % len(rows))


def cmd_sample(args) -> None:
    census, eligible = [], []
    for row in sorted(read_csv(args.links), key=lambda r: r["game_id"]):
        checks = {"table_readable": int(row["table_sha256"] != UNKNOWN),
                  "video_id_parsed": int(row["video_id"] != UNKNOWN),
                  "run_start_known": int(row["run_start_utc"] != UNKNOWN)}
        census.append(dict(game_id=row["game_id"], eligible=int(all(checks.values())), **checks))
        if all(checks.values()):
            eligible.append(row)
    picked = even_sample(eligible)
    write_csv(Path(args.out) / "sample_census.csv", census, ["game_id"])
    write_csv(Path(args.out) / "sections.csv",
              [{k: r[k] for k in SECTION_KEYS} for r in picked], SECTION_KEYS)
    print("eligible=%d sampled=%d distinct_video_ids=%d"
          % (len(eligible), len(picked), len({r["video_id"] for r in picked})))


def cmd_align(args) -> None:
    refetched = Path(args.refetched)
    ticks = archived_ticks(Path(args.tracking) / args.game_id / "tracking_data.csv")
    meta, digest, rows = probe(refetched), sha256_file(refetched), []
    fps, stamps = meta["fps"], meta["pts"]
    for index, (frame, timestamp) in enumerate(ticks):
        stamp = stamps[frame] if 0 <= frame < len(stamps) else None
        error = (stamp - timestamp) * fps if stamp is not None and fps else None
        rows.append({"game_id": args.game_id, "landmark": index, "archived_frame": frame,
                     "archived_timestamp": "%.6f" % timestamp,
                     "refetched_pts": UNKNOWN if stamp is None else "%.6f" % stamp,
                     "fps": fps or UNKNOWN, "refetched_sha256": digest,
                     "error_frames": UNKNOWN if error is None else "%.4f" % error,
                     "within_bar": 0 if error is None else int(abs(error) <= BAR_FRAMES)})
    write_csv(Path(args.out) / "alignment.csv", rows, ["game_id"], append=True)
    print("landmarks=%d within_bar=%d" % (len(rows), sum(r["within_bar"] for r in rows)))


def cmd_summary(args) -> None:
    links, claims, classes = read_csv(args.links), {}, {}
    for row in links:
        classes[row["join_class"]] = classes.get(row["join_class"], 0) + 1
        if row["video_id"] != UNKNOWN:
            claims.setdefault((row["video_id"], row["requested_start_s"]), set()).add(row["game_id"])
    unparseable = sum(1 for r in links if r["video_id"] == UNKNOWN)
    ledger = len({r.get("game_id") for r in read_ledger(args.ledger) if r.get("game_id")}) \
        if args.ledger else len(links)
    aligned = sorted(aligned_games(args.alignment))
    summary = {"ledger_links": len(links), "ledger_game_ids": ledger,
               "join_class_counts": classes, "bar_native_frames": BAR_FRAMES,
               "classified_share_of_ledger": round(len(links) / ledger, 6) if ledger else 0.0,
               "collisions": {"%s@%s" % key: sorted(ids) for key, ids in sorted(claims.items())
                              if len(ids) > 1},
               "unreadable_tables": sum(1 for r in links if r["table_sha256"] == UNKNOWN),
               "aligned_sections": aligned, "aligned_section_count": len(aligned),
               "aligned_video_ids": len({(parse_gid(g) or {}).get("ytid") for g in aligned}),
               "unparseable_ids": unparseable}
    summary["collision_count"] = len(summary["collisions"])
    out = Path(args.out) / "summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("ledger_links", "join_class_counts",
                                              "collision_count")}, sort_keys=True))


SPECS = {"census": "!ledger !tracking !out", "sources": "!dirs repo !out",
         "links": "!ledger !tracking sources alignment !out", "sample": "!links !out",
         "align": "!game-id !refetched !tracking !out",
         "summary": "!links alignment ledger !out"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G361 source/table identity map")
    subs = parser.add_subparsers(dest="cmd", required=True)
    for name, flags in SPECS.items():
        sub = subs.add_parser(name)
        for flag in flags.split():
            sub.add_argument("--" + flag.lstrip("!"), required=flag.startswith("!"),
                             default=None, **({"nargs": "+"} if flag == "!dirs" else {}))
        sub.set_defaults(func=globals()["cmd_" + name])
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
