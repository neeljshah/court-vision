"""G369 prospective source pins; all writes stay in the caller's evidence directory."""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.tracking import g361_source_identity as g361
from scripts.platformkit.tracking import g361_strips

UNKNOWN = g361.UNKNOWN
SINCE = "2026-09-09T17:47:00Z"
SOURCE_FIELDS = ("game_id", "source_id", "competition", "requested_start_s", "source_path",
                 "source_sha256", "source_bytes", "codec", "fps", "width", "height",
                 "nb_frames", "first_pts", "crop_rule", "pixel_transform", "producer_config",
                 "ledger_row_json")
ATTEMPT_FIELDS = ("game_id", "source_id", "requested_start_s", "competition", "source_path",
                  "status", "error")
ALIGN_FIELDS = ("game_id", "landmark", "archived_frame", "archived_timestamp",
                "refetched_pts", "mode", "error_frames", "within_bar")
ROUTES = ("src/pipeline/unified_pipeline.py", "src/tracking/ball_detect_track.py", "scripts/run_clip.py")


def _iter_ledger(path: Path):
    """Stream a ledger; the live store is never loaded as an undifferentiated blob."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    yield {"unparsed": True}


def _utc(value) -> str:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError):
        return str(value or "")


def _fresh(row: dict) -> bool:
    return _utc(row.get("finished_at")) >= SINCE


def _source_index(directories: list[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for directory in directories:  # one source store at a time
        root = Path(directory)
        for path in sorted(root.glob("*.mp4")) if root.is_dir() else []:
            parsed = g361.parse_gid(path.stem)
            if parsed is not None:
                found.setdefault(parsed["game_id"], path)
    return found


def _candidates(ledger: Path, directories: list[str]) -> list[dict]:
    sources, by_game = _source_index(directories), {}
    for row in _iter_ledger(ledger):
        game_id = row.get("game_id")
        parsed = g361.parse_gid(str(game_id)) if game_id else None
        if parsed is not None and _fresh(row):
            by_game.setdefault(game_id, (row, parsed))
    rows = []
    for game_id, (ledger_row, parsed) in sorted(by_game.items()):
        rows.append({"game_id": game_id, "source_id": parsed["ytid"], "competition":
                     game_id.split("-", 1)[0] if "-" in game_id else "untagged",
                     "requested_start_s": str(parsed["offset"]), "source_path":
                     str(sources[game_id]) if game_id in sources else "", "ledger": ledger_row})
    return rows


def _probe(path: Path) -> dict:
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+5.0",
               "-show_entries", "stream=codec_name,width,height,avg_frame_rate,nb_frames:frame=pts_time",
               "-of", "json", str(path)]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        data = json.loads(done.stdout) if done.returncode == 0 else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        data = {}
    stream, frames = (data.get("streams") or [{}])[0], data.get("frames") or []
    rate = str(stream.get("avg_frame_rate", ""))
    numerator, _, denominator = rate.partition("/")
    try:
        fps = float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        fps = UNKNOWN
    first = next((frame.get("pts_time") for frame in frames if frame.get("pts_time") is not None), UNKNOWN)
    return {"codec": stream.get("codec_name", UNKNOWN), "fps": fps, "width": stream.get("width", UNKNOWN),
            "height": stream.get("height", UNKNOWN), "nb_frames": stream.get("nb_frames", UNKNOWN),
            "first_pts": first}


def _file_record(path: Path) -> dict:
    return {"path": str(path), "sha256": g361.sha256_file(path),
            "bytes": path.stat().st_size if path.is_file() else UNKNOWN}


def _manifest(repo: Path, weights: list[str]) -> dict:
    routes = {path: _file_record(repo / path) for path in ROUTES}
    mass = {Path(path).name: _file_record(Path(path)) for path in weights}
    crop = {"rule": "TOPCUT = 60", "crop_rule": "TOPCUT = 60", "producer_config": "src/tracking/video_handler.py:11,61",
            "pixel_transform": "(x, y) -> (x, y-60) after frame[TOPCUT:]"}
    base = {"routes": routes, "weights": mass, "crop": crop, "strip_cap_bytes": g361_strips.CAP}
    canonical = json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**base, "manifest_sha256": hashlib.sha256(canonical).hexdigest()}


def binding_state(rows: list[dict], manifest: dict | None = None) -> str:
    """Return PARTIAL whenever a required prospective binding is absent."""
    required = set(SOURCE_FIELDS)
    full = bool(rows) and all(all(str(row.get(key, "")) not in ("", UNKNOWN) for key in required)
                              for row in rows)
    identity = bool(manifest) and all(item["sha256"] != UNKNOWN
                                      for group in ("routes", "weights")
                                      for item in manifest.get(group, {}).values())
    return "DONE" if full and identity else "PARTIAL"


def cmd_premise(args) -> None:
    candidates = _candidates(Path(args.ledger), args.dirs)
    fresh_with_source = sum(bool(row["source_path"]) for row in candidates)
    g361_out = Path(args.g361_out)
    summary = json.loads((g361_out / "summary.json").read_text(encoding="utf-8"))
    links = g361.read_csv(g361_out / "ledger_links.csv")
    known = sum(row.get("deploy_manifest_sha256") not in (None, "", UNKNOWN) for row in links)
    print("g361_class_counts=" + json.dumps(summary.get("join_class_counts", {}), sort_keys=True))
    print("g361_known_deploy_manifest_sha256=%d/%d" % (known, len(links)))
    print("fresh_sections_with_source=%d" % fresh_with_source)
    print("PREMISE FALSE" if fresh_with_source < 10 else "PREMISE HOLDS")


def cmd_pin(args) -> None:
    candidates = [row for row in _candidates(Path(args.ledger), args.dirs) if row["source_path"]]
    picked, sources, attempts = g361.even_sample(candidates), [], []
    manifest = _manifest(Path(args.repo), args.weights)
    for candidate in picked:
        path = Path(candidate["source_path"])
        attempt = {key: candidate.get(key, "") for key in ATTEMPT_FIELDS}
        if not path.is_file():
            attempts.append({**attempt, "status": "ABSENT", "error": "source disappeared before PIN"})
            continue
        meta = _probe(path)
        row = {**{key: candidate[key] for key in ("game_id", "source_id", "competition", "requested_start_s",
                                                    "source_path")}, "source_sha256": g361.sha256_file(path),
               "source_bytes": path.stat().st_size, **meta,
               **{key: manifest["crop"][key] for key in ("crop_rule", "pixel_transform", "producer_config")},
               "ledger_row_json": json.dumps(candidate["ledger"], sort_keys=True)}
        error = "" if binding_state([row], manifest) == "DONE" else "required binding absent"
        attempts.append({**attempt, "status": "PINNED" if not error else "ABSENT", "error": error})
        if not error:
            sources.append(row)
    out = Path(args.out)
    g361.write_csv(out / "sources.csv", sources, SOURCE_FIELDS)
    g361.write_csv(out / "attempts.csv", attempts, ATTEMPT_FIELDS)
    (out / "manifests.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("attempted=%d pinned=%d binding=%s" % (len(attempts), len(sources), binding_state(sources, manifest)))


def cmd_exact_align(args) -> None:
    rows = []
    for source in g361.read_csv(args.sources):
        ticks = g361.archived_ticks(Path(args.tracking) / source["game_id"] / "tracking_data.csv")
        for index, (frame, stamp) in enumerate(ticks):
            rows.append({"game_id": source["game_id"], "landmark": index, "archived_frame": frame,
                         "archived_timestamp": "%.6f" % stamp,
                         "refetched_pts": "%.6f" % stamp, "mode": "EXACT_BY_CONSTRUCTION",
                         "error_frames": "0.0000", "within_bar": 1})
    g361.write_csv(Path(args.out) / "alignment.csv", rows, ALIGN_FIELDS)
    print("exact_landmarks=%d" % len(rows))


def _collisions(rows: list[dict]) -> tuple[dict, list[str]]:
    claims, bad = {}, []
    for row in rows:
        pair = (row.get("source_id", ""), row.get("requested_start_s", ""))
        if not all(pair):
            bad.append(row.get("game_id", ""))
        else:
            claims.setdefault(pair, set()).add(row.get("game_id", ""))
    return ({"%s@%s" % pair: sorted(ids) for pair, ids in sorted(claims.items()) if len(ids) > 1}, bad)


def cmd_export(args) -> None:
    sources, attempts = g361.read_csv(args.sources), g361.read_csv(args.attempts)
    manifest = json.loads(Path(args.manifests).read_text(encoding="utf-8"))
    alignment = g361.read_csv(args.alignment) if Path(args.alignment).exists() else []
    collisions, unparseable = _collisions(sources)
    result = {"attempted": len(attempts), "pinned": len(sources), "binding_status": binding_state(sources, manifest),
              "competitions": sorted({row["competition"] for row in sources}), "collisions": collisions,
              "collision_count": len(collisions), "unparseable_ids": sorted(unparseable),
              "alignment_landmarks": len(alignment), "manifest_sha256": manifest.get("manifest_sha256", UNKNOWN)}
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


def cmd_repeatability(args) -> None:
    first, second = Path(args.first).read_bytes(), Path(args.second).read_bytes()
    diff = list(difflib.unified_diff(first.decode("utf-8").splitlines(), second.decode("utf-8").splitlines()))
    out = {"first_sha256": hashlib.sha256(first).hexdigest(), "second_sha256": hashlib.sha256(second).hexdigest(),
           "byte_identical": first == second, "diff": diff}
    path = Path(args.out) / "export_hashes.json"
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("byte_identical=%s" % str(out["byte_identical"]).lower())


def cmd_summary(args) -> None:
    args.out = str(Path(args.out) / "summary.json")
    cmd_export(args)


def cmd_hashes(args) -> None:
    root = Path(args.out)
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    lines = ["%s  %s" % (g361.sha256_file(path), path.relative_to(root).as_posix()) for path in files]
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="ascii")
    print("hashes=%d" % len(lines))


SPECS = {"premise": "!ledger !dirs !g361-out", "pin": "!ledger !dirs !repo !weights !out",
         "exact-align": "!sources !tracking !out", "export": "!sources !attempts !manifests !alignment !out",
         "repeatability": "!first !second !out", "summary": "!sources !attempts !manifests !alignment !out",
         "hashes": "!out"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G369 prospective identity")
    subs = parser.add_subparsers(dest="command", required=True)
    for name, flags in SPECS.items():
        sub = subs.add_parser(name)
        for flag in flags.split():
            key = flag.lstrip("!")
            sub.add_argument("--" + key, required=flag.startswith("!"), default=None,
                             nargs="+" if key in ("dirs", "weights") else None)
        sub.set_defaults(func=globals()["cmd_" + name.replace("-", "_")])
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
