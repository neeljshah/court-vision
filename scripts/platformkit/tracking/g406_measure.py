"""Premise reproduction and native decoding for the G406 pixel diagnostic."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.platformkit.tracking.g406_prepare import CARDS_PER_KIND, KINDS, join_bounds

ROOT = Path(__file__).resolve().parents[3]
G402 = ROOT / "docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11"
OUT = ROOT / "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11"
FRAMES = Path("C:/Users/neelj/g406_frames")
EXPECTED = {"target_mask.csv": "c2c4f57a56330afbc9a7772b61743864aa04d746d9715e0374743e724a79dc71",
            "eye_index.csv": "d0019a5b0460cca99fe5afade3e414173c104eba5997fc1683f43d1de2bcd436"}
SEALED_CLASS = {"CLAMP": 9354, "PREDICTION": 5259, "SUBPIXEL": 1399, "DETECTION": 3075}
INPUTS = ["draw.csv", "evaluated_ticks.csv", "coverage_per_section.csv", "eye_index.csv",
          "target_mask.csv", "window_pts.csv", "source_receipts.csv", "summary.json"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[Mapping[str, Any]], fields: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in writer.fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def tick_universe() -> dict[str, list[dict[str, Any]]]:
    """Order every bounded evaluated tick by draw_order then source-frame index."""
    ticks = {row["draw_kind"] + "/" + row["section_id"]: row
             for row in read_csv(G402 / "evaluated_ticks.csv")}
    universe: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
    for draw in sorted(read_csv(G402 / "draw.csv"), key=lambda row: (row["draw_kind"], int(row["draw_order"]))):
        kind, section = draw["draw_kind"], draw["section_id"]
        bounds = ticks.get(kind + "/" + section)
        if bounds is None:
            continue
        low, high = int(bounds["sealed_start_frame"]), int(bounds["sealed_end_frame_exclusive"])
        receipt = json.loads((G402 / "raw_tables" / kind / section / "evaluated_tick_receipt.json").read_text())
        for frame in sorted(value for value in receipt["evaluated_tick_ids"] if low <= value < high):
            universe[kind].append({"draw_kind": kind, "draw_order": int(draw["draw_order"]),
                                   "section_id": section, "sealed_start_frame": low,
                                   "sealed_end_frame_exclusive": high, "frame": frame})
    return universe


def sealed_draw() -> list[dict[str, Any]]:
    """Reproduce the sealed 30-per-kind exact-even card draw."""
    universe, cards = tick_universe(), []
    for kind in KINDS:
        pool = universe[kind]
        size = len(pool)
        for position in range(CARDS_PER_KIND):
            ordinal = int(position * (size - 1) / (CARDS_PER_KIND - 1) + 0.5)
            cards.append(dict(pool[ordinal], card_id="%s_%02d" % (kind, position),
                              sealed_ordinal=ordinal, universe_n=size,
                              draw_formula="int(j*(N-1)/29+0.5) over draw_order then bounded receipt ticks"))
    return cards


def _hashes() -> list[dict[str, Any]]:
    rows = []
    for name in INPUTS:
        path = G402 / name
        digest = sha256(path)
        rows.append({"path": "docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11/" + name,
                     "bytes": path.stat().st_size, "sha256": digest,
                     "expected_sha256": EXPECTED.get(name, ""),
                     "expected_match": "" if name not in EXPECTED else int(digest == EXPECTED[name])})
    return rows


def _accounting(coverage: list[dict[str, str]], evaluated: dict[str, dict[str, str]],
                cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = ("draw_kind", "section_id", "coverage_status", "sealed_start_frame", "sealed_end_frame_exclusive",
            "bounded_rows", "excluded_overrun_rows", "sealed_window_source_frames", "all_decoded_frames",
            "all_evaluated_ticks", "zero_output_evaluated_ticks", "candidate_rows")
    carry = ("producer_attempted_ticks", "receipt_evaluated_ticks", "trace_attempt_ticks",
             "bounded_evaluated_ticks", "schedule")
    rows = []
    for row in coverage:
        ticks = evaluated.get(row["draw_kind"] + "/" + row["section_id"], {})
        rows.append({**{field: row[field] for field in keep},
                     **{field: ticks.get(field, "UNKNOWN") for field in carry},
                     "zero_candidate_evaluated_ticks": row["zero_output_evaluated_ticks"],
                     "receipt_zero_output_evaluated_ticks":
                         ticks.get("zero_output_evaluated_ticks", "UNKNOWN"),
                     "g406_selected_ticks": sum(1 for card in cards if card["section_id"] == row["section_id"]
                                                and card["draw_kind"] == row["draw_kind"])})
    return rows


def stage_premise() -> dict[str, Any]:
    mask = read_csv(G402 / "target_mask.csv")
    coverage = read_csv(G402 / "coverage_per_section.csv")
    evaluated = {row["draw_kind"] + "/" + row["section_id"]: row
                 for row in read_csv(G402 / "evaluated_ticks.csv")}
    eye = read_csv(G402 / "eye_index.csv")
    cards = sealed_draw()
    write_csv(OUT / "input_hashes.csv", _hashes(),
              ["path", "bytes", "sha256", "expected_sha256", "expected_match"])
    write_csv(OUT / "draw.csv", cards,
              ["card_id", "draw_kind", "draw_order", "section_id", "sealed_start_frame",
               "sealed_end_frame_exclusive", "frame", "sealed_ordinal", "universe_n", "draw_formula"])
    selected = {(row["draw_kind"], row["section_id"], row["frame"]): row for row in cards}
    bounded = join_bounds([row for row in mask
                           if (row["draw_kind"], row["section_id"], int(row["frame"])) in selected],
                          read_csv(G402 / "draw.csv"), list(evaluated.values()))
    dims = {row["card_id"]: (row["native_width"], row["native_height"]) for row in eye}
    per_card: dict[str, int] = {}
    rows_out = []
    for row in bounded:
        card = selected[(row["draw_kind"], row["section_id"], int(row["frame"]))]["card_id"]
        per_card[card] = per_card.get(card, 0) + 1
        rows_out.append(dict(row, card_id=card, box_id="%s_r%02d" % (card, per_card[card] - 1),
                             native_width=dims[card][0], native_height=dims[card][1]))
    rows_out.sort(key=lambda row: row["box_id"])
    write_csv(OUT / "all_masked_rows.csv", rows_out,
              ["box_id", "card_id", "draw_kind", "section_id", "sealed_start_frame",
               "sealed_end_frame_exclusive", "frame", "player_id", "position_source", "source_branch",
               "matched_event_id", "matched_event_valid", "repeated_coordinate", "x_position", "y_position",
               "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "target_weight", "mask_reason",
               "native_width", "native_height"])
    accounting = _accounting(coverage, evaluated, cards)
    write_csv(OUT / "window_accounting.csv", accounting, list(accounting[0]))
    used = {row["section_id"] for row in cards}
    out_receipts = []
    for row in read_csv(G402 / "source_receipts.csv"):
        path = Path(row["receiver_path"])
        present = path.is_file()
        digest = sha256(path) if present else ""
        out_receipts.append(dict(row, g406_selected=int(row["section_id"] in used),
                                 g406_receiver_present=int(present),
                                 g406_receiver_bytes=path.stat().st_size if present else "",
                                 g406_rehash_sha256=digest,
                                 g406_rehash_equal=int(present and digest == row["source_sha256"])))
    write_csv(OUT / "source_receipts.csv", out_receipts, list(out_receipts[0]))
    classes = {name: sum(1 for row in mask if row["position_source"] == name) for name in SEALED_CLASS}
    return {"sealed_rows": len(mask), "class_table": classes,
            "repeated_coordinate": {name: sum(1 for row in mask if row["position_source"] == name
                                              and row["repeated_coordinate"] == "1") for name in SEALED_CLASS},
            "class_table_matches_sealed": int(classes == SEALED_CLASS),
            "candidate_rows": sum(1 for row in mask if row["target_weight"] == "1"),
            "held_rows": sum(1 for row in mask if row["position_source"] == "HELD"),
            "forbidden_admissions": sum(1 for row in mask if row["target_weight"] == "1"
                                        and row["position_source"] != "DETECTION"),
            "windows_total": len(coverage),
            "windows_complete": sum(1 for row in coverage if row["coverage_status"] == "COMPLETE"),
            "windows_unknown": [row["draw_kind"] + "/" + row["section_id"] for row in coverage
                                if row["coverage_status"] != "COMPLETE"],
            "universe_n": {kind: len(tick_universe()[kind]) for kind in KINDS},
            "draw_matches_g402_eye_index": int(
                [(row["card_id"], row["section_id"], row["frame"], row["sealed_ordinal"]) for row in cards] ==
                [(row["card_id"], row["section_id"], int(row["frame"]), int(row["sealed_ordinal"])) for row in eye]),
            "distinct_ticks": len({(row["draw_kind"], row["section_id"], row["frame"]) for row in cards}),
            "source_windows_supplying_ticks": len({(row["draw_kind"], row["section_id"]) for row in cards}),
            "selected_rows": len(rows_out),
            "retained_off_pod": sum(row["g406_rehash_equal"] for row in out_receipts),
            "retained_selected": sum(row["g406_rehash_equal"] for row in out_receipts if row["g406_selected"])}


def _decode_one(card: Mapping[str, Any], source: Mapping[str, str]) -> dict[str, Any]:
    import cv2
    target = FRAMES / (str(card["card_id"]) + ".png")
    command = ["ffmpeg", "-v", "info", "-nostdin", "-y", "-i", source["receiver_path"],
               "-vf", "select=eq(n\\,%d),showinfo" % card["frame"], "-fps_mode", "passthrough",
               "-frames:v", "1", "-pix_fmt", "rgb24", str(target)]
    done = subprocess.run(command, capture_output=True, text=True)
    pts = ""
    for line in done.stderr.splitlines():
        if "pts_time:" in line:
            pts = line.split("pts_time:")[1].split()[0]
    ok = done.returncode == 0 and target.is_file()
    image = cv2.imread(str(target)) if ok else None
    return {"card_id": card["card_id"], "draw_kind": card["draw_kind"], "section_id": card["section_id"],
            "frame": card["frame"], "source_path": source["source_path"],
            "receiver_path": source["receiver_path"], "receiver_sha256": source["g406_rehash_sha256"],
            "decoded_path": str(target).replace("\\", "/"),
            "decoded_bytes": target.stat().st_size if ok else "",
            "decoded_sha256": sha256(target) if ok else "",
            "decoded_width": "" if image is None else image.shape[1],
            "decoded_height": "" if image is None else image.shape[0],
            "declared_width": source["width"], "declared_height": source["height"],
            "actual_pts_s": pts, "returncode": done.returncode,
            "status": "OK" if image is not None else "UNKNOWN"}


def stage_decode() -> dict[str, Any]:
    FRAMES.mkdir(parents=True, exist_ok=True)
    receipts = {row["section_id"]: row for row in read_csv(OUT / "source_receipts.csv")}
    rows = []
    for card in sealed_draw():
        rows.append(_decode_one(card, receipts[card["section_id"]]))
        print(rows[-1]["card_id"], rows[-1]["status"], rows[-1]["actual_pts_s"], flush=True)
    write_csv(OUT / "frame_receipts.csv", rows, list(rows[0]))
    return {"planned": len(rows), "decoded": sum(1 for row in rows if row["status"] == "OK"),
            "unknown": [row["card_id"] for row in rows if row["status"] != "OK"],
            "dimension_match": sum(1 for row in rows if str(row["decoded_width"]) == row["declared_width"]
                                   and str(row["decoded_height"]) == row["declared_height"])}


if __name__ == "__main__":
    name = sys.argv[1]
    outcome = {"premise": stage_premise, "decode": stage_decode}[name]()
    write_json(OUT / "runtime_receipts" / ("stage_" + name + ".json"), outcome)
    print(json.dumps(outcome, indent=1, sort_keys=True))
