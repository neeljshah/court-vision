"""G331 -- harness-side frame-denominator sidecar, and the G310 rows-per-frame recomputation.

The production route writes `evaluated_frame_count.json` with `evaluated_frames` null and the
reason `max_frames_is_detector_dependent_in_this_route` whenever a frame cap is supplied
(`scripts/run_clip.py:191-193`), because the counter that decides the cap is only incremented
after a detector-gated test (`src/pipeline/unified_pipeline.py:1696,2069`). Every rows-per-frame
number in the tracking evidence therefore falls back to EMITTED frames, which counts no frame the
detector emitted nothing for.

This module is ADDITIVE. It never rewrites the route's own sidecar and never invents the route's
count: `evaluated_frames` is carried VERBATIM together with the route's `reason`. The
reconstructions it adds are named `*_reconstructed` so no reader can mistake one for a producer
count. Nothing under `src/` is edited.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCHEMA_VERSION = "g331-v1"
PRODUCER_VERSION = "g331_evaluated_frames_sidecar/1"
SIDECAR_NAME = "g331_frame_denominators.json"
ROUTE_SIDECAR = "evaluated_frame_count.json"
INT_PAD = 6
NOT_KNOWABLE = "NOT KNOWABLE"


def _frame_ids(path) -> list:
    """Sorted distinct integer frame ids in a route table; empty when the table is absent."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return sorted({int(float(r["frame"])) for r in csv.DictReader(handle) if r.get("frame")})


def modal_gap(frames: list):
    """Most common positive difference between consecutive distinct frame ids; None when absent."""
    gaps = Counter(b - a for a, b in zip(frames, frames[1:]) if b > a)
    return gaps.most_common(1)[0][0] if gaps else None


def span_positions(frames: list, stride):
    """Strided positions across the covered span; None unless stride divides EVERY observed gap."""
    if stride is None or stride <= 0 or len(frames) < 2:
        return None
    if any((b - a) % stride for a, b in zip(frames, frames[1:])):
        return None
    return (frames[-1] - frames[0]) // stride + 1


def ffprobe_source_frames(video_path) -> tuple:
    """Container frame count and the method used; never a decode."""
    path = Path(video_path) if video_path else None
    if path is None or not path.exists():
        return None, "source_absent"
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=nb_frames,r_frame_rate,duration", "-of", "json", str(path)]
    try:
        streams = json.loads(subprocess.run(command, check=True, capture_output=True,
                                            text=True).stdout).get("streams", [])
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None, "ffprobe_unavailable"
    if len(streams) != 1:
        return None, "ffprobe_unavailable"
    stream = streams[0]
    try:
        count = int(stream.get("nb_frames"))
    except (TypeError, ValueError):
        count = None
    if count and count > 0:
        return count, "ffprobe_nb_frames"
    try:
        numerator, _, denominator = str(stream.get("r_frame_rate", "")).partition("/")
        rate = float(numerator) / float(denominator) if denominator else float(numerator)
        return round(float(stream["duration"]) * rate), "ffprobe_duration_times_rate"
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        return None, "ffprobe_unavailable"


def frame_denominators(route_dir, video_path=None) -> dict:
    """Every denominator the harness can record beside one route output directory."""
    route_dir = Path(route_dir)
    route = {}
    route_path = route_dir / ROUTE_SIDECAR
    if route_path.exists():
        route = json.loads(route_path.read_text(encoding="utf-8"))
    person = _frame_ids(route_dir / "tracking_data.csv")
    ball = _frame_ids(route_dir / "ball_tracking.csv")
    stride, stride_source = route.get("stride"), "route_sidecar.stride"
    if stride is None:
        stride, stride_source = modal_gap(ball), "reconstructed_from_ball_table"
    if video_path is None and route.get("source_path"):
        video_path = route["source_path"]
    source_frames, source_method = ffprobe_source_frames(video_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "producer_version": PRODUCER_VERSION,
        "route_sidecar_present": route_path.exists(),
        "decoded_frames": route.get("decoded_frames"),
        "evaluated_frames": route.get("evaluated_frames"),
        "evaluated_frames_reason": route.get("reason"),
        "frame_cap": route.get("max_frames"),
        "stride": stride,
        "emitted_frames": len(person),
        "processed_frames_reconstructed": len(ball),
        "delivered_frames_in_span_reconstructed": span_positions(sorted(set(person + ball)), stride),
        "source_frames": source_frames,
        "source_frames_method": source_method,
        "field_sources": {
            "decoded_frames": "route_sidecar.decoded_frames",
            "evaluated_frames": "route_sidecar.evaluated_frames",
            "evaluated_frames_reason": "route_sidecar.reason",
            "frame_cap": "route_sidecar.max_frames",
            "stride": stride_source,
            "emitted_frames": "tracking_data.csv distinct frame",
            "processed_frames_reconstructed": "ball_tracking.csv distinct frame",
            "delivered_frames_in_span_reconstructed": "both tables plus stride",
            "source_frames": source_method,
        },
    }


def write_sidecar(route_dir, video_path=None) -> Path:
    """Persist the harness sidecar beside the route output; the route's own file is untouched."""
    path = Path(route_dir) / SIDECAR_NAME
    payload = json.dumps(frame_denominators(route_dir, video_path), indent=2, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def p95_nearest_rank(values: list):
    """True nearest-rank p95: the ceil(0.95 n)-th smallest value. None on an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[-(-95 * len(ordered) // 100) - 1]


def read_archive(path) -> dict:
    """Archived G310 rows grouped by run_id, preserving every run; no head slice."""
    grouped: dict = defaultdict(list)
    with gzip.open(Path(path), "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped[row["run_id"]].append(row)
    return grouped


def _instance_steps(rows: list, source_height: float) -> list:
    """Normalised footpoint steps within each archived instance; cut-spanning pairs excluded."""
    by_instance: dict = defaultdict(list)
    for row in rows:
        by_instance[row["instance_id"]].append(row)
    steps = []
    for group in by_instance.values():
        group.sort(key=lambda r: int(r["frame"]))
        for a, b in zip(group, group[1:]):
            dx = (int(b["fx_milli_px"]) - int(a["fx_milli_px"])) / 1000.0
            dy = (int(b["fy_milli_px"]) - int(a["fy_milli_px"])) / 1000.0
            steps.append((dx * dx + dy * dy) ** 0.5 / source_height)
    return steps


def _source_frames_by_game(pilot_summary: dict) -> dict:
    """ffprobe nb_frames per game id from the committed corpus probe."""
    out = {}
    for probe in pilot_summary.get("corpus_probed", []):
        stem = Path(probe["path"]).stem
        game = stem.split("__", 1)[1] if "__" in stem else stem
        try:
            out[game] = int(probe.get("nb_frames"))
        except (TypeError, ValueError):
            out[game] = None
    return out


def game_id(run_id: str) -> str:
    """Strip the pass prefix and the arm suffix from an archived run id."""
    core = run_id.split("__", 1)[1] if "__" in run_id else run_id
    for suffix in ("_armP_repeat", "_armN", "_armP"):
        if core.endswith(suffix):
            return core[: -len(suffix)]
    return core


def _ratio(numerator: int, denominator):
    return numerator / denominator if denominator else None


def recompute(proxies: dict, rows_archive: dict, ball_archive: dict, sources: dict) -> list:
    """One record per committed run: every denominator, its n, or NOT KNOWABLE."""
    out = []
    for run in proxies["runs"]:
        run_id = run["run_id"]
        rows, ball = rows_archive.get(run_id, []), ball_archive.get(run_id, [])
        person_frames = sorted({int(r["frame"]) for r in rows})
        ball_frames = sorted({int(r["frame"]) for r in ball})
        emitted = len(person_frames) or None
        processed = len(ball_frames) or None
        if processed is not None and processed != run["ball_rows_total"]:
            processed = None
        stride = modal_gap(ball_frames) or modal_gap(person_frames)
        steps = _instance_steps(rows, float(run["source_height"]))
        out.append({
            "run_id": run_id,
            "person_rows": run["person_rows"],
            "archive_rows": len(rows),
            "stride": stride,
            "emitted_frames": emitted,
            "processed_frames_recon": processed,
            "delivered_in_span_recon": span_positions(sorted(set(person_frames + ball_frames)),
                                                      stride),
            "evaluated_frames_route": run["denominator_evaluated_frames"],
            "decoded_frames_route": None,
            "source_frames": sources.get(game_id(run_id)),
            "rows_per_emitted": _ratio(run["person_rows"], emitted),
            "rows_per_processed_recon": _ratio(run["person_rows"], processed),
            "rows_per_delivered_recon": _ratio(
                run["person_rows"],
                span_positions(sorted(set(person_frames + ball_frames)), stride)),
            "step_pairs": len(steps),
            "p95_committed": run["p95_norm_step_instance"],
            "p95_nearest_rank": p95_nearest_rank(steps),
        })
    return out


def _cell(value) -> str:
    return NOT_KNOWABLE if value is None else str(int(value)).zfill(INT_PAD)


def _rate(value) -> str:
    return NOT_KNOWABLE if value is None else "%.6f" % value


FIELDS = ["run_id", "person_rows", "stride", "denominator_EMITTED", "rows_per_frame_EMITTED",
          "denominator_PROCESSED_RECON", "rows_per_frame_PROCESSED_RECON",
          "denominator_DELIVERED_IN_SPAN_RECON", "rows_per_frame_DELIVERED_IN_SPAN_RECON",
          "denominator_EVALUATED_route", "denominator_DECODED_route", "denominator_SOURCE",
          "inflation_EMITTED_over_PROCESSED_RECON", "step_pairs_n"]


def to_csv_rows(records: list) -> list:
    """The committed table: integer cells zero-padded, ratios to six places, else NOT KNOWABLE."""
    out = []
    for rec in records:
        inflation = None
        if rec["rows_per_emitted"] and rec["rows_per_processed_recon"]:
            inflation = rec["rows_per_emitted"] / rec["rows_per_processed_recon"]
        out.append(dict(zip(FIELDS, [
            rec["run_id"], _cell(rec["person_rows"]), _cell(rec["stride"]),
            _cell(rec["emitted_frames"]), _rate(rec["rows_per_emitted"]),
            _cell(rec["processed_frames_recon"]), _rate(rec["rows_per_processed_recon"]),
            _cell(rec["delivered_in_span_recon"]), _rate(rec["rows_per_delivered_recon"]),
            _cell(rec["evaluated_frames_route"]), _cell(rec["decoded_frames_route"]),
            _cell(rec["source_frames"]), _rate(inflation), _cell(rec["step_pairs"]),
        ])))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default="docs/evidence/tracking/g310_attempt2")
    parser.add_argument("--pilot", default="docs/evidence/tracking/g310_pilot_pre_prereg")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    archive, pilot = REPO / args.archive, REPO / args.pilot
    proxies = json.loads((archive / "g310_attempt2_proxies.json").read_text(encoding="utf-8"))
    sources = _source_frames_by_game(
        json.loads((pilot / "pilot_summary.json").read_text(encoding="utf-8")))
    records = recompute(proxies,
                        read_archive(archive / "g310_attempt2_rows_part01.csv.gz"),
                        read_archive(archive / "g310_attempt2_ball_part01.csv.gz"), sources)
    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(to_csv_rows(records))
    print(json.dumps(records, indent=2, sort_keys=True))
    print("wrote %s (%d runs)" % (out_path, len(records)))


if __name__ == "__main__":
    main()
