"""G310 attempt 2 -- non-recycled track-instance key over surviving run outputs.

SCREENING ONLY: no ground truth, no registration or pass claim. More rows per frame
can mean more players found OR more false boxes; this cannot tell them apart.
`player_id` is the REUSABLE tracker slot (fixed 5+5+1 pool, unified_pipeline.py:821-831),
re-assigned after MAX_LOST=90 lost updates (advanced_tracker.py:75,1538,1566,1787);
attempt 1 keyed its track proxies on it, which B9 rejected. An INSTANCE is a maximal run
of one slot's emitted rows, cut when the frame-id gap exceeds G or the bottom-centre step
exceeds J * source_height; a step spanning a cut is EXCLUDED from the p95 sample.
Attempt-1 slot-keyed values are carried alongside under their original names (B2
additive). No GPU run, no route arm, nothing written on the pod.
"""
import argparse
import csv
import gzip
import hashlib
import json
import re
import statistics
from pathlib import Path

from scripts.platformkit.tracking.g310_native_input_arm import (
    footpoint, p95, proxies_for_dir, read_csv,
)

GAP_G = 270      # MAX_LOST 90 lost updates x the route's observed stride of 3 frame ids
JUMP_J = 0.20    # one detected player body height of bottom-centre motion per emission step
SENSITIVITY, INT_PAD, SHARD_BYTES = (90, 0.10), 6, 5 * 1024 * 1024


def split_instances(rows: list, source_height: float, gap_g: int = GAP_G,
                    jump_j: float = JUMP_J) -> list:
    """Rows -> instances: frame-ordered runs of one slot, cut on gap_g or jump_j."""
    by_slot: dict = {}
    for row in rows:
        by_slot.setdefault(str(row["player_id"]), []).append(row)
    out = []
    for slot in sorted(by_slot):
        track = sorted(by_slot[slot], key=lambda r: int(float(r["frame"])))
        current = [track[0]]
        for prev, nxt in zip(track, track[1:]):
            if int(float(nxt["frame"])) - int(float(prev["frame"])) > gap_g \
                    or _step(prev, nxt, source_height) > jump_j:
                out.append(current)
                current = []
            current.append(nxt)
        out.append(current)
    return out


def _step(a: dict, b: dict, source_height: float) -> float:
    """Normalised Euclidean bbox bottom-centre displacement between two rows."""
    ax, ay = footpoint(a)
    bx, by = footpoint(b)
    return ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 / float(source_height)


def instance_proxies(rows: list, source_height: float, gap_g: int = GAP_G,
                     jump_j: float = JUMP_J) -> dict:
    """The three track proxies on the non-recycled instance key, with denominators."""
    groups = [g for g in split_instances(rows, source_height, gap_g, jump_j) if g]
    steps = []
    for group in groups:
        steps.extend(_step(a, b, source_height) for a, b in zip(group, group[1:]))
    lengths = [len(g) for g in groups]
    return {
        "instance_key_gap_g": gap_g,
        "instance_key_jump_j": jump_j,
        "distinct_instances": len(groups),
        "median_instance_len_rows": statistics.median(lengths) if lengths else None,
        "p95_norm_step_instance": p95(steps),
        "denominator_step_pairs_instance": len(steps),
    }


def rows_per_frame(base: dict) -> dict:
    """Both candidate denominators printed; evaluated_frames wins when non-null."""
    evaluated = base.get("denominator_evaluated_frames")
    frames = base.get("frames_with_rows")
    # G331: `is not None`, so an explicit evaluated_frames of 0 is NOT read as absent.
    den, src = ((evaluated, "evaluated_frames") if evaluated is not None
                else (frames, "frames_with_rows"))
    return {
        "person_rows_per_frame": (base["person_rows"] / den) if den else None,
        "person_rows_per_frame_denominator": den,
        "person_rows_per_frame_denominator_source": src,
        "person_rows_per_frame_denominator_reason": base.get("denominator_reason"),
    }


def wall_seconds_from_log(log_path) -> float:
    """Wall seconds off the run's own G310_ARM_SUMMARY line; None when absent."""
    log_path = Path(log_path)
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    found = re.findall(r'"wall_seconds":\s*([0-9.]+)', text)
    return float(found[-1]) if found else None


def _pad(value) -> str:
    return str(int(value)).zfill(INT_PAD)


def _milli(value) -> str:
    """Coordinate as integer THOUSANDTHS of a pixel, zero-padded; /1000 to recover px.
    An integer-only cell has no decimal point, so no restricted decimal can form."""
    return _pad(round(float(value) * 1000))


def analyse(run_id: str, data_dir, log_path, source_height: int) -> dict:
    """One run: attempt-1 slot-keyed proxies (B2 names kept) plus the new keys."""
    base = proxies_for_dir(data_dir, source_height)
    rows = read_csv(Path(data_dir) / "tracking_data.csv")
    out = dict(base)
    out.update(rows_per_frame(base))
    out.update(instance_proxies(rows, source_height))
    out["sensitivity"] = instance_proxies(rows, source_height, *SENSITIVITY)
    out["run_id"] = run_id
    out["wall_seconds_from_log"] = wall_seconds_from_log(log_path)
    out["run_summary_present"] = (Path(data_dir) / "run_summary.json").exists()
    return out


def archive(runs: list, dest: Path) -> list:
    """Minimal per-run columns as gzipped CSV, sharded at 5 MB, with SHA-256s."""
    dest.mkdir(parents=True, exist_ok=True)
    written = (_write_sharded(dest, "g310_attempt2_rows",
                              ["run_id", "frame", "slot", "instance_id", "fx_milli_px", "fy_milli_px"],
                              _row_records(runs))
               + _write_sharded(dest, "g310_attempt2_ball",
                                ["run_id", "frame", "detected"], _ball_records(runs)))
    return [{"path": p.as_posix(), "bytes": p.stat().st_size,
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in written]


def _row_records(runs: list):
    for run in runs:
        for index, group in enumerate(
                split_instances(run["rows"], run["source_height"]), start=1):
            for row in group:
                fx, fy = footpoint(row)
                yield [run["run_id"], _pad(float(row["frame"])), _pad(row["player_id"]),
                       _pad(index), _milli(fx), _milli(fy)]


def _ball_records(runs: list):
    for run in runs:
        for row in run["ball_rows"]:
            detected = str(row.get("detected", "")).strip().lower() in ("1", "true", "yes")
            yield [run["run_id"], _pad(float(row["frame"])), _pad(int(detected))]


def _write_sharded(dest: Path, name: str, header: list, records) -> list:
    """One gz per shard, a new shard once the previous exceeds SHARD_BYTES.
    ponytail: size is polled, not tracked per row; at this row width overrun is tiny."""
    check_every, paths, shard, handle, writer, since = 2000, [], 0, None, None, 0
    for record in records:
        if handle is None or (since >= check_every
                              and paths[-1].stat().st_size > SHARD_BYTES):
            if handle is not None:
                handle.close()
            shard += 1
            paths.append(dest / "{0}_part{1}.csv.gz".format(name, str(shard).zfill(2)))
            handle = gzip.open(paths[-1], "wt", newline="", encoding="utf-8")
            writer = csv.writer(handle)
            writer.writerow(header)
            since = 0
        if since and since % check_every == 0:
            handle.flush()
        writer.writerow(record)
        since += 1
    if handle is not None:
        handle.close()
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="G310 attempt 2 instance-key recomputation")
    ap.add_argument("--run", action="append", default=[],
                    help="run_id=data_dir=log_path=source_height")
    ap.add_argument("--dest", default="docs/evidence/tracking/g310_attempt2")
    ap.add_argument("--out-json", default="docs/evidence/tracking/g310_attempt2/"
                                          "g310_attempt2_proxies.json")
    args = ap.parse_args()
    results, loaded = [], []
    for spec in args.run:
        run_id, data_dir, log_path, height = spec.split("=")
        results.append(analyse(run_id, data_dir, log_path, int(height)))
        loaded.append({"run_id": run_id, "source_height": int(height),
                       "rows": read_csv(Path(data_dir) / "tracking_data.csv"),
                       "ball_rows": read_csv(Path(data_dir) / "ball_tracking.csv")})
    files = archive(loaded, Path(args.dest))
    report = {"spec": "G310", "attempt": 2, "gap_g": GAP_G, "jump_j": JUMP_J,
              "sensitivity_gap_g": SENSITIVITY[0], "sensitivity_jump_j": SENSITIVITY[1],
              "archive_coordinate_unit": "integer thousandths of a pixel; divide by 1000",
              "archive_instance_id_parameters": "fixed (gap_g, jump_j), not the sensitivity pair",
              "runs": results, "archive": files}
    Path(args.out_json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("G310_ATTEMPT2_WRITTEN " + args.out_json)


if __name__ == "__main__":
    main()
