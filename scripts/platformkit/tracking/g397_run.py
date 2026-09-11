"""G397 pod driver: frozen census, sealed even draw, and source capture receipts."""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g397_census import (classify_format, even_draw,
                                                      earliest_terminal_original, sha256_file)
from scripts.platformkit.tracking.g397_probe import (decoded_pts_census, probe_directory,
                                                     probe_object, source_filename)

CORPUS = Path("/workspace/data/footage_corpus")
BRIDGE = Path("/workspace/deploy/nba-ai-system/data/footage_bridge")
TRACKING = Path("/workspace/data/tracking")
BUNDLE = ("tracking_data.csv", "ball_tracking.csv", "evaluated_frame_count.json",
          "harness_verdict.json")

__all__ = ["split_section", "declared_kind", "load_ledger", "census_rows", "main"]


def split_section(game_id: str) -> tuple[str, str]:
    """Split a section id into its video id and zero-padded source-start offset."""
    head, sep, tail = str(game_id).rpartition("_s")
    if not sep or not tail.isdigit():
        return str(game_id), "".zfill(9)
    return head, tail.zfill(9)


def declared_kind(record: dict[str, Any]) -> str:
    """Classify a ledger attempt from the producer's own recorded source fields."""
    resolution = str(record.get("source_resolution") or "")
    width, _, height = resolution.partition("x")
    return classify_format({"width": width, "height": height, "fps": record.get("source_fps")})


def load_ledger(path: Path) -> list[dict[str, Any]]:
    """Read the frozen ledger snapshot and stamp one stable attempt identity per line."""
    records = []
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        record["attempt_id"] = "L%05d:%s" % (index, record.get("game_id", ""))
        record["ledger_line"] = index
        record["route_identity"] = "ORIGINAL"
        record["terminal"] = str(record.get("status", "")) in ("tracked", "thin", "timeout")
        record["started_at"] = str(record.get("finished_at", ""))
        records.append(record)
    return records


def census_rows(records: list[dict[str, Any]], probes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one census row per attempt, keeping declared and measured states apart."""
    rows = []
    for record in records:
        video, start = split_section(record.get("game_id", ""))
        name = source_filename(str(record.get("sport", "")), str(record.get("game_id", "")))
        probe = probes.get(name)
        rows.append({
            "attempt_id": record["attempt_id"], "ledger_line": record["ledger_line"],
            "section_id": record.get("game_id"), "competition": record.get("sport"),
            "video": video, "source_start": start, "status": record.get("status"),
            "terminal": int(bool(record["terminal"])), "route_identity": "ORIGINAL",
            "declared_kind": declared_kind(record),
            "declared_resolution": record.get("source_resolution"),
            "declared_height": record.get("source_height"), "declared_fps": record.get("source_fps"),
            "declared_duration": record.get("source_duration"), "rows": record.get("rows"),
            "decoded_frames": record.get("decoded_frames"),
            "evaluated_frames": record.get("evaluated_frames"), "stride": record.get("stride"),
            "passed": record.get("passed"), "finished_at": record.get("finished_at"),
            "probe_status": "ABSENT" if not probe else probe.get("probe_status"),
            "measured_kind": "UNKNOWN" if not probe else probe.get("format_kind"),
            "measured_width": None if not probe else probe.get("width"),
            "measured_height": None if not probe else probe.get("height"),
            "measured_fps": None if not probe else probe.get("fps"),
            "source_sha256": "" if not probe else probe.get("sha256", ""),
            "source_filename": name,
            "outputs_present": int((TRACKING / str(record.get("game_id"))).is_dir()),
        })
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _unique_sections(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["declared_kind"] != kind:
            continue
        key = str(row["section_id"])
        current = best.get(key)
        if current is None or str(row["finished_at"]) < str(current["finished_at"]):
            best[key] = row
    return list(best.values())


def _capture(section: str, scratch: Path, probes: dict[str, dict[str, Any]],
             attempt: dict[str, Any] | None, sport: str) -> dict[str, Any]:
    """Retain one section's table bundle and source receipt in a single pass."""
    out = scratch / "snapshots" / section
    out.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {"section_id": section, "competition": sport}
    for name in BUNDLE:
        source = TRACKING / section / name
        if not source.is_file():
            receipt[name + "_status"] = "ABSENT"
            continue
        data = source.read_bytes()
        (out / name).write_bytes(data)
        readback = (out / name).read_bytes()
        receipt[name + "_status"] = "OK" if readback == data else "READBACK_MISMATCH"
        receipt[name + "_bytes"] = len(data)
        receipt[name + "_sha256"] = sha256_file(out / name)
        if name.endswith(".csv"):
            receipt[name + "_lines"] = data.count(b"\n")
    name = source_filename(sport, section)
    for directory in (CORPUS, BRIDGE):
        path = directory / name
        if path.is_file():
            probe = probes.get(name) or probe_object(path)
            receipt.update({"source_path": probe.get("path"), "source_status": "PRESENT",
                            "source_sha256": probe.get("sha256"), "source_bytes": probe.get("bytes"),
                            "measured_width": probe.get("width"), "measured_height": probe.get("height"),
                            "measured_avg_fps": probe.get("avg_fps"), "measured_r_fps": probe.get("r_fps"),
                            "time_base": probe.get("time_base"), "codec_name": probe.get("codec_name"),
                            "measured_kind": probe.get("format_kind"),
                            "format_duration": probe.get("format_duration")})
            receipt.update(decoded_pts_census(path))
            break
    else:
        receipt.update({"source_status": "ABSENT", "measured_kind": "UNKNOWN", "pts_status": "ABSENT"})
    receipt["attempt_id"] = None if attempt is None else attempt.get("attempt_id")
    return receipt


def main(argv: list[str]) -> int:
    """Run the frozen census, the sealed draw, and the one-pass capture on the pod."""
    scratch = Path(argv[1] if len(argv) > 1 else "/workspace/g397_scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    records = load_ledger(scratch / "ledger_snapshot.jsonl")
    probes = {}
    for row in probe_directory(CORPUS) + probe_directory(BRIDGE):
        probes.setdefault(row["filename"], row)
    _write_csv(scratch / "source_probes.csv", sorted(probes.values(), key=lambda r: r["filename"]))
    rows = census_rows(records, probes)
    _write_csv(scratch / "census.csv", rows)
    draw: list[dict[str, Any]] = []
    for kind in ("1080p30", "720p60"):
        unique = _unique_sections(rows, kind)
        if len(unique) < 30:
            print("INSUFFICIENT %s %d" % (kind, len(unique)))
            continue
        for order, selected in enumerate(even_draw(unique, 30)):
            draw.append(dict(selected, draw_kind=kind, draw_order=order,
                             population=len(unique)))
    _write_csv(scratch / "draw.csv", draw)
    by_section: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_section.setdefault(str(record.get("game_id")), []).append(record)
    receipts = []
    for selected in draw:
        section = str(selected["section_id"])
        attempts = by_section.get(section, [])
        receipt = _capture(section, scratch, probes,
                           earliest_terminal_original(attempts), str(selected["competition"]))
        receipt.update({"draw_kind": selected["draw_kind"], "draw_order": selected["draw_order"],
                        "declared_kind": selected["declared_kind"], "attempts": len(attempts)})
        receipts.append(receipt)
        print("CAPTURED %s %s %s" % (section, receipt["source_status"], receipt.get("pts_status")))
    _write_csv(scratch / "source_receipts.csv", receipts)
    selected_ids = {str(row["section_id"]) for row in draw}
    with (scratch / "selected_ledger.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            if str(record.get("game_id")) in selected_ids:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
    print("CENSUS rows=%d draw=%d probes=%d" % (len(rows), len(draw), len(probes)))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    sys.exit(main(sys.argv))
