"""G407 pod-side read-only census of the ORIGINAL live producer under the changed mix.

Reads the daemon ledger, the feeder fetched-format receipts and each completed section's
own tables. Writes only under the caller-supplied output directory. Nothing in
`/workspace/data`, `/workspace/feeder` or the deploy tree is modified.

Schedule reconstruction is the landed G376 definition (ball_tracking.csv `live`), imported
from scripts.platformkit.tracking.g376_schedule and never re-implemented here.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g376_schedule import (
    integral, reconstructed_schedule, route_cap,
)
from scripts.platformkit.tracking.g397_census import sha256_file

FETCH = re.compile(
    r"^(?P<at>\S+Z) FETCH start sport=(?P<sport>\S+) tag=(?P<tag>\S+) (?P<vid>\S+) "
    r"fmt=(?P<fmt>\S+) dur=(?P<dur>\d+)s sections=(?P<n>\d+) offs=(?P<offs>[0-9,]+)")
LEDGER_KEEP = ("game_id", "sport", "status", "rows", "passed", "coverage_pct",
               "harness_coverage_pct", "coordinate_space", "rung", "evaluated_at",
               "seconds", "finished_at", "source_fps", "source_height",
               "source_duration", "decoded_frames", "evaluated_frames", "stride",
               "probe_status", "source_resolution", "degenerate", "resumed_partial")


def fetch_receipts(log_path: Path) -> dict[str, dict[str, Any]]:
    """Map section identity -> the feeder line that fetched it (requested format only)."""
    out: dict[str, dict[str, Any]] = {}
    with Path(log_path).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = FETCH.match(line.strip())
            if not match:
                continue
            tag = match.group("tag")
            stem = ("" if tag == "." else tag + "-") + match.group("vid")
            for off in match.group("offs").split(","):
                out["%s_s%s" % (stem, off)] = {
                    "fetch_utc": match.group("at"), "requested_format_id": match.group("fmt"),
                    "video": match.group("vid"), "feeder_tag": tag,
                    "feeder_sport": match.group("sport"),
                    "video_duration_s": int(match.group("dur")),
                    "section_offset_s": int(off)}
    return out


def corpus_index(corpus: Path) -> dict[str, Path]:
    """Map section identity -> retained source path, stripping the sport prefix."""
    out: dict[str, Path] = {}
    for path in sorted(Path(corpus).glob("*.mp4")):
        out[re.sub(r"^[a-z]+__", "", path.stem)] = path
    return out


def ledger_window(ledger: Path, start_epoch: int, stop_epoch: int) -> tuple[list[dict], dict]:
    """Earliest terminal ORIGINAL attempt per section inside the sealed epoch window."""
    attempts: dict[str, list[dict[str, Any]]] = {}
    total = 0
    with Path(ledger).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                row = json.loads(line)
            except ValueError:
                continue
            done = integral(row.get("finished_at"))
            if done is None or not start_epoch <= done < stop_epoch:
                continue
            attempts.setdefault(str(row.get("game_id", "")), []).append(row)
    kept = []
    repeats = 0
    for identity in sorted(attempts):
        ordered = sorted(attempts[identity], key=lambda row: (integral(row.get("finished_at")) or 0,
                                                              json.dumps(row, sort_keys=True)))
        repeats += len(ordered) - 1
        row = {name: ordered[0].get(name) for name in LEDGER_KEEP}
        row["section_identity"] = identity
        row["attempt_kind"] = "ORIGINAL"
        row["terminal"] = True
        row["terminal_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime(integral(ordered[0].get("finished_at"))))
        row["attempt_id"] = "%s@%s" % (identity, ordered[0].get("finished_at"))
        row["repeat_attempts_in_window"] = len(ordered) - 1
        kept.append(row)
    return kept, {"ledger_lines_total": total, "sections_in_window": len(kept),
                  "repeat_attempts_suppressed": repeats}


def _coordinate_rows(path: Path, wanted: set[int]) -> tuple[list[dict[str, Any]], int, str]:
    """Player coordinate strings for the wanted source frames, byte-equal as written."""
    import csv
    if not path.exists():
        return [], 0, "tracking_table_absent"
    rows: list[dict[str, Any]] = []
    total = 0
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        names = reader.fieldnames or []
        for column in ("frame", "player_id", "x_position", "y_position"):
            if column not in names:
                return [], 0, "tracking_column_absent:" + column
        for row in reader:
            total += 1
            frame = integral(row.get("frame"))
            if frame is None or frame not in wanted:
                continue
            rows.append({"source_frame": frame, "track_id": str(row.get("player_id", "")),
                         "x": str(row.get("x_position", "")), "y": str(row.get("y_position", ""))})
    return rows, total, ""


def section_trace(section_dir: Path, record: dict[str, Any],
                  sealed_frames: set[int] | None = None) -> dict[str, Any]:
    """One section's complete read-only trace; every absence is a named reason."""
    schedule = reconstructed_schedule(section_dir / "ball_tracking.csv")
    evaluated = sorted(schedule["evaluated"])
    suspended = sorted(schedule["suspended"])
    wanted = set(evaluated) if sealed_frames is None else set(evaluated) & set(sealed_frames)
    rows, tracking_rows, tracking_reason = _coordinate_rows(
        section_dir / "tracking_data.csv", wanted)
    verdict: dict[str, Any] = {}
    try:
        verdict = json.loads((section_dir / "harness_verdict.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        verdict = {}
    return {
        "section_identity": record["section_identity"],
        "section_dir_present": section_dir.is_dir(),
        "evaluated_tick_ids": evaluated, "suspended_tick_ids": suspended,
        "evaluated_ticks": len(evaluated), "suspended_ticks": len(suspended),
        "producer_read_frames": schedule["ball_rows"],
        "observed_stride": schedule["observed_stride"],
        "schedule_reason": schedule["reason"] or "",
        "tracking_rows": tracking_rows, "tracking_reason": tracking_reason,
        "coordinate_rows": rows,
        "route_max_frames": route_cap(section_dir),
        "verdict_evaluated_frames": integral(verdict.get("evaluated_frames")),
        "verdict_stride": integral(verdict.get("stride")),
        "verdict_attempted_frames_capped": integral(verdict.get("attempted_frames_capped")),
        "verdict_decoded_frames": integral(verdict.get("decoded_frames")),
        "tracking_sha256": sha256_file(section_dir / "tracking_data.csv")
        if (section_dir / "tracking_data.csv").exists() else "ABSENT",
        "ball_sha256": sha256_file(section_dir / "ball_tracking.csv")
        if (section_dir / "ball_tracking.csv").exists() else "ABSENT",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="G407 read-only live census")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--feeder-log", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--tracking-root", required=True)
    parser.add_argument("--start-epoch", type=int, required=True)
    parser.add_argument("--stop-epoch", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    (out / "raw_traces").mkdir(parents=True, exist_ok=True)
    population, counts = ledger_window(Path(args.ledger), args.start_epoch, args.stop_epoch)
    receipts = fetch_receipts(Path(args.feeder_log))
    retained = corpus_index(Path(args.corpus))
    for row in population:
        identity = row["section_identity"]
        receipt = receipts.get(identity)
        row["fetch_receipt_status"] = "BOUND" if receipt else "UNRESOLVED"
        row.update(receipt or {"requested_format_id": "", "fetch_utc": "", "video": "",
                               "feeder_tag": "", "feeder_sport": "", "video_duration_s": "",
                               "section_offset_s": ""})
        source = retained.get(identity)
        row["retained_pod_path"] = str(source) if source else ""
        row["retained"] = int(bool(source))
        row["source_bytes"] = source.stat().st_size if source else ""
        row["pod_source_sha256"] = sha256_file(source) if source else "PRUNED"
        trace = section_trace(Path(args.tracking_root) / identity, row)
        row["evaluated_ticks"] = trace["evaluated_ticks"]
        row["producer_read_frames"] = trace["producer_read_frames"]
        row["schedule_reason"] = trace["schedule_reason"]
        (out / "raw_traces" / (identity + ".json")).write_text(
            json.dumps(trace, sort_keys=True), encoding="utf-8", newline="\n")
    payload = {"counts": counts, "population": population,
               "fetch_receipt_lines": len(receipts), "retained_corpus_files": len(retained),
               "census_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "population.json").write_text(json.dumps(payload, indent=1, sort_keys=True),
                                         encoding="utf-8", newline="\n")
    print("SECTIONS %d RETAINED %d BOUND_FETCH %d" % (
        len(population), sum(row["retained"] for row in population),
        sum(row["fetch_receipt_status"] == "BOUND" for row in population)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
