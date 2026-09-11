"""G412 step-0 binding condition: rehash every input and reproduce the sealed counts."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g412_contract import file_digests, write_csv_lf

ROOT = Path(__file__).resolve().parents[3]
G406 = ROOT / "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11"
G402 = ROOT / "docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11"
G380 = ROOT / "docs/evidence/tracking/g380_producer_provenance_2026-09-10"
OUT = ROOT / "docs/evidence/tracking/g412_box_frame_contract_2026-09-12"
FRAMES = Path("C:/Users/neelj/g406_frames")

EXPECTED = {
    G402 / "target_mask.csv":
        "c2c4f57a56330afbc9a7772b61743864aa04d746d9715e0374743e724a79dc71",
    G380 / "summary.json":
        "2155b6f861fd2a611e61488f6ce7bb42af7d231c1860bfde324bee7b7c47dba9",
}
ROUTE_FILES = (
    "src/tracking/video_handler.py", "src/tracking/player_detection.py",
    "src/tracking/advanced_tracker.py", "src/pipeline/unified_pipeline.py",
)
G406_TABLES = (
    "draw.csv", "per_tick.csv", "associations.csv", "frame_receipts.csv",
    "source_receipts.csv", "input_hashes.csv", "window_accounting.csv",
    "all_masked_rows.csv", "comparator_detections.csv", "summary.json", "prereg.md",
)
RECEIPT_FIELDS = ("box_frame", "box_crop_origin_y_px", "box_padding_px")


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read one CSV table with its full column set retained."""
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _hash_row(path: Path, role: str) -> dict[str, Any]:
    if not path.exists():
        return {"path": path.as_posix(), "role": role, "bytes": "", "sha256_on_disk": "",
                "sha256_lf": "", "expected_sha256": EXPECTED.get(path, ""),
                "expected_match": "ABSENT", "status": "ABSENT"}
    size, disk, lf = file_digests(path)
    expected = EXPECTED.get(path, "")
    match = "" if not expected else ("1" if expected in (disk, lf) else "0")
    return {"path": path.as_posix(), "role": role, "bytes": size, "sha256_on_disk": disk,
            "sha256_lf": lf, "expected_sha256": expected, "expected_match": match,
            "status": "PRESENT"}


def collect_input_hashes() -> list[dict[str, Any]]:
    """Hash every landed table, archived route file and sealed prereg used here."""
    rows = [_hash_row(path, "expected_digest") for path in EXPECTED]
    rows += [_hash_row(G406 / name, "g406_table") for name in G406_TABLES]
    rows += [_hash_row(G402 / name, "g402_table")
             for name in ("draw.csv", "route_hashes.json", "evaluated_ticks.csv",
                          "window_pts.csv", "summary.json")]
    rows += [_hash_row(G380 / name, "g380_table") for name in ("trace.csv", "reader_survey.csv")]
    rows += [_hash_row(ROOT / name, "archived_route") for name in ROUTE_FILES]
    rows.append(_hash_row(OUT / "prereg.md", "g412_prereg"))
    return rows


def collect_source_receipts() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rehash every retained original and decoded frame bound to the 60 sealed ticks."""
    receipts = read_csv(G406 / "frame_receipts.csv")
    cache: dict[str, tuple[int, str, str]] = {}
    rows, failures = [], 0
    for rec in receipts:
        recv = Path(rec["receiver_path"])
        key = recv.as_posix()
        if key not in cache:
            cache[key] = file_digests(recv) if recv.exists() else (0, "", "")
        size, disk, _ = cache[key]
        png = FRAMES / (rec["card_id"] + ".png")
        p_size, p_disk, _ = file_digests(png) if png.exists() else (0, "", "")
        ok = (disk == rec["receiver_sha256"]) and (p_disk == rec["decoded_sha256"])
        failures += 0 if ok else 1
        rows.append({
            "card_id": rec["card_id"], "draw_kind": rec["draw_kind"],
            "section_id": rec["section_id"], "frame": rec["frame"],
            "source_path": rec["source_path"], "receiver_path": key,
            "receiver_bytes": size, "receiver_sha256_rehash": disk,
            "receiver_sha256_landed": rec["receiver_sha256"],
            "receiver_rehash_equal": int(disk == rec["receiver_sha256"]),
            "decoded_path": png.as_posix(), "decoded_bytes": p_size,
            "decoded_sha256_rehash": p_disk, "decoded_sha256_landed": rec["decoded_sha256"],
            "decoded_rehash_equal": int(p_disk == rec["decoded_sha256"]),
            "native_width": rec["decoded_width"], "native_height": rec["decoded_height"],
            "actual_pts_s": rec["actual_pts_s"], "landed_status": rec["status"],
            "status": "REHASH_EQUAL" if ok else "REHASH_MISMATCH",
        })
    return rows, {"receipts": len(rows), "failures": failures,
                  "distinct_receiver_files": len(cache)}


def writer_receipt_absence() -> dict[str, Any]:
    """Confirm the production writer and every landed raw table carry no box receipt."""
    src_hits = []
    for name in ROUTE_FILES:
        text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
        src_hits += [name + ":" + field for field in RECEIPT_FIELDS if field in text]
    tables = sorted((G402 / "raw_tables").rglob("tracking_data.csv"))
    header_hits, headers = [], set()
    for table in tables:
        with table.open(newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        headers.add(tuple(header))
        header_hits += [table.as_posix() + ":" + f for f in RECEIPT_FIELDS if f in header]
    neighbour = sorted({"coordinate_space" for h in headers if "coordinate_space" in h})
    return {"route_files_scanned": len(ROUTE_FILES), "route_receipt_hits": src_hits,
            "raw_tables_scanned": len(tables), "distinct_headers": len(headers),
            "table_receipt_hits": header_hits, "neighbour_fields_present": neighbour,
            "neighbour_equivalent_receipt": False,
            "absence_reproduced": not src_hits and not header_hits}


def run() -> dict[str, Any]:
    """Execute the whole binding condition and write its two evidence tables."""
    hashes = collect_input_hashes()
    receipts, receipt_summary = collect_source_receipts()
    draw = read_csv(G406 / "draw.csv")
    per_tick = read_csv(G406 / "per_tick.csv")
    masked = read_csv(G406 / "all_masked_rows.csv")
    silent = [r["card_id"] for r in per_tick if r["producer_silence"] == "1"]
    absence = writer_receipt_absence()
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv_lf(OUT / "input_hashes.csv", list(hashes[0]), hashes)
    write_csv_lf(OUT / "source_receipts.csv", list(receipts[0]), receipts)
    premise = {
        "distinct_ticks": len({(r["section_id"], r["frame"]) for r in draw}),
        "draw_cards": len(draw), "per_tick_cards": len(per_tick),
        "stored_rows": len(masked), "silent_ticks": len(silent), "silent_card_ids": silent,
        "nonsilent_ticks": len(per_tick) - len(silent),
        "expected_digest_mismatches": [r["path"] for r in hashes if r["expected_match"] == "0"],
        "absent_inputs": [r["path"] for r in hashes if r["status"] == "ABSENT"],
        "source_rehash": receipt_summary, "writer_receipt_absence": absence,
    }
    premise["reproduced"] = bool(
        premise["distinct_ticks"] == 60 and premise["stored_rows"] == 206
        and premise["silent_ticks"] == 5 and not premise["expected_digest_mismatches"]
        and not premise["absent_inputs"] and receipt_summary["failures"] == 0
        and absence["absence_reproduced"])
    return premise


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, sort_keys=True))
