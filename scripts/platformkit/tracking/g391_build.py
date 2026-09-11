"""G391: premise re-measurement, native census, and the sealed blind packet build.

Every input is rehashed with LF normalisation before any count is taken: this
checkout is CRLF, so a raw byte hash of the working tree disagrees with the LF
digest the spec quotes for exactly the same landed bytes.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g391_prepare as prep

EV = "docs/evidence/tracking"
OUT_NAME = "g391_ball_false_call_audit_2026-09-11"
INPUTS = {
    "dev_boxes_v3": EV + "/g389_ball_reference_completion_2026-09-11/dev_boxes_v3.csv",
    "reference_v3": EV + "/g389_ball_reference_completion_2026-09-11/reference_v3.csv",
    "frames_v3": EV + "/g389_ball_reference_completion_2026-09-11/frames_v3.csv",
    "predictions_A8": EV + "/g390_ball_a8_sealed_pass_2026-09-11/predictions_A8.csv",
    "paired_frame_scores":
        EV + "/g390_ball_a8_sealed_pass_2026-09-11/paired_frame_scores.csv",
}
SPEC_HASHES = {
    "dev_boxes_v3": "e151f932c3b4bffe84c89aa8fde18f08c346a1e3a6e65d27ed4b36f095b7b4fa",
    "reference_v3": "ad00670c3601706d5d817de734fc85d82e8fdc379ea03b21bbe1a46e272ad09e",
    "predictions_A8": "58a315bdb63020dce401517fe048a072e6a142e08d18eb54832f3068c1bee1b6",
    "paired_frame_scores": "afc203e7346e94af875fb101049b94b98e5905e922f52b31af9b15cffbbede0b",
}
SHEETS = EV + "/g373_ball_detector_v2_2026-09-10/sheets"
CROP_NATIVE = 448
CROP_ZOOM = 2
CONTEXT_W = 1024
MARKER_NATIVE = 132
CAUSAL_S = 0.2
FPS_ASSUMED = 30.0


def lf_sha256(path: Path) -> str:
    """Digest LF-normalised bytes so a CRLF checkout reproduces the landed hash."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_csv(root: Path, name: str) -> list[dict]:
    with (root / INPUTS[name]).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def premise(root: Path) -> dict:
    """Step 0: rehash, join, and reproduce 549 / 259 / 90 / 169 and 100-50-19."""
    hashes = {name: lf_sha256(root / path) for name, path in INPUTS.items()}
    raw = {name: hashlib.sha256((root / path).read_bytes()).hexdigest()
           for name, path in INPUTS.items()}
    mismatch = [name for name, want in SPEC_HASHES.items() if hashes[name] != want]
    scores = [r for r in read_csv(root, "paired_frame_scores") if r["arm"] == "A8"]
    preds = read_csv(root, "predictions_A8")
    ref = {r["frame_key"]: r for r in read_csv(root, "reference_v3")
           if r["split"] == "heldout"}
    calls = [r for r in preds if r["rank"] == "0" and r["tick_history"] == "OBSERVED"]
    tp_keys = {r["frame_key"] for r in scores if int(r["tp"]) == 1}
    fp_keys = {r["frame_key"] for r in scores if int(r["fp"]) == 1}
    fp_split = collections.Counter(ref[k]["label"] for k in fp_keys)
    out = {
        "lf_sha256": hashes, "raw_crlf_sha256": raw,
        "spec_hash_mismatch_after_lf_normalisation": mismatch,
        "crlf_checkout_explains_prepare_mismatch": not mismatch,
        "n_states": len(scores),
        "n_unique_states": len({r["frame_key"] for r in scores}),
        "n_calls_rank0_observed": len(calls),
        "n_unique_call_keys": len({r["frame_key"] for r in calls}),
        "tp": len(tp_keys), "fp": len(fp_keys),
        "fn_visible_without_tp": sum(1 for r in scores
                                     if r["label"] == "VISIBLE" and int(r["tp"]) == 0),
        "fp_partition": dict(fp_split),
        "label_partition": dict(collections.Counter(r["label"] for r in scores)),
        "n_dev_boxes": len(read_csv(root, "dev_boxes_v3")),
        "a11_handoff_evidenced": False,
    }
    out["premise_true"] = bool(
        out["n_states"] == 549 and out["n_unique_states"] == 549
        and out["n_calls_rank0_observed"] == 259 and out["n_unique_call_keys"] == 259
        and out["tp"] == 90 and out["fp"] == 169 and not mismatch
        and fp_split.get("VISIBLE") == 100 and fp_split.get("ABSENT") == 50
        and fp_split.get("UNKNOWN") == 19)
    return out


def context_census(root: Path) -> dict:
    """Causal availability for ALL 549 targets and the disjoint DEV pair supply."""
    frames = read_csv(root, "frames_v3")
    window = CAUSAL_S * FPS_ASSUMED
    rows: list[dict] = []
    dev_pairs = 0
    for split in ("heldout", "development"):
        by_section = collections.defaultdict(list)
        for frame in frames:
            if frame["split"] == split:
                by_section[frame["section"]].append(int(frame["frame_index"]))
        for section, indices in by_section.items():
            indices.sort()
            for position, index in enumerate(indices):
                prior = [index - other for other in indices[:position]]
                near = [gap for gap in prior if 0 < gap <= window]
                if split == "development":
                    dev_pairs += len(near)
                else:
                    rows.append({
                        "section": section, "frame_index": index,
                        "n_prior_keys_in_section": position,
                        "nearest_prior_gap_frames": min(prior) if prior else "",
                        "n_causal_neighbours_within_0p2s": len(near),
                        "availability": "MISSING" if len(near) < 2 else "PRESENT"})
    gaps = [r["nearest_prior_gap_frames"] for r in rows
            if r["nearest_prior_gap_frames"] != ""]
    return {"rows": rows, "dev_pairs_within_0p2s": dev_pairs, "n_targets": len(rows),
            "n_targets_with_two_causal_neighbours":
                sum(1 for r in rows if r["availability"] == "PRESENT"),
            "min_nearest_prior_gap_frames": min(gaps) if gaps else "",
            "fps_assumed": FPS_ASSUMED, "causal_window_s": CAUSAL_S}


def mark(draw: ImageDraw.ImageDraw, cx: float, cy: float, half: float) -> None:
    """A neutral open marker: it points at the candidate without covering it."""
    for offset, colour in ((0, (0, 0, 0)), (1, (255, 255, 255))):
        draw.rectangle((cx - half + offset, cy - half + offset,
                        cx + half - offset, cy + half - offset), outline=colour, width=1)
    tick = max(6.0, half / 3.0)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.line((cx + dx * half, cy + dy * half,
                   cx + dx * (half - tick), cy + dy * (half - tick)),
                  fill=(255, 255, 255), width=2)


def render_packet(sheet: Path, cx: float, cy: float, out: Path) -> None:
    """One blind card: full native context above a candidate-centred native crop."""
    frame = Image.open(sheet).convert("RGB")
    width, height = frame.size
    context = frame.resize((CONTEXT_W, round(CONTEXT_W * height / width)), Image.LANCZOS)
    scale = CONTEXT_W / width
    mark(ImageDraw.Draw(context), cx * scale, cy * scale, MARKER_NATIVE * scale / 2.0)
    half = CROP_NATIVE // 2
    left = max(0, min(width - CROP_NATIVE, round(cx) - half))
    top = max(0, min(height - CROP_NATIVE, round(cy) - half))
    crop = frame.crop((left, top, left + CROP_NATIVE, top + CROP_NATIVE))
    crop = crop.resize((CROP_NATIVE * CROP_ZOOM, CROP_NATIVE * CROP_ZOOM), Image.LANCZOS)
    mark(ImageDraw.Draw(crop), (cx - left) * CROP_ZOOM, (cy - top) * CROP_ZOOM,
         MARKER_NATIVE * CROP_ZOOM / 2.0)
    card = Image.new("RGB", (CONTEXT_W, context.height + crop.height + 8), (32, 32, 32))
    card.paste(context, (0, 0))
    card.paste(crop, ((CONTEXT_W - crop.width) // 2, context.height + 8))
    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(out, quality=84, optimize=True)


def _packet_keys(universe: list[dict], packets: list[dict]) -> list[str]:
    """Recover each packet's key from its opaque id, never from the input order."""
    digest = {hashlib.sha256(row["frame_key"].encode("ascii")).hexdigest()[:16]:
              row["frame_key"] for row in universe}
    return [digest[packet["packet_id"].split("-")[-1]] for packet in packets]


def build(root: Path) -> dict:
    """Freeze the 259 called keys into blind packets with native cards."""
    frames = {r["frame_key"]: r for r in read_csv(root, "frames_v3")}
    preds = [r for r in read_csv(root, "predictions_A8")
             if r["rank"] == "0" and r["tick_history"] == "OBSERVED"]
    manifest, universe = [], []
    for pred in preds:
        key = pred["frame_key"]
        frame = frames[key]
        rel = SHEETS + "/" + key[:12] + ".jpg"
        sheet = root / rel
        manifest.append({
            "frame_key": key, "game": frame["game"], "section": frame["section"],
            "frame_index": frame["frame_index"], "width": frame["width"],
            "height": frame["height"], "sheet_scale": frame["sheet_scale"],
            "native_sheet": rel, "sheet_present": int(sheet.exists()),
            "sheet_bytes": sheet.stat().st_size if sheet.exists() else 0,
            "sheet_sha256": lf_sha256(sheet) if sheet.exists() else "",
            "cand_cx": pred["x"], "cand_cy": pred["y"],
            "cand_w": pred["w"], "cand_h": pred["h"]})
        universe.append({"frame_key": key, "game": frame["game"],
                         "section": frame["section"],
                         "frame_index": frame["frame_index"],
                         "native_path": "", "crop_path": ""})
    packets = prep.freeze_packets(universe)
    ordered = _packet_keys(universe, packets)
    by_key = {row["frame_key"]: row for row in manifest}
    cards = root / EV / OUT_NAME / "cards"
    for packet, key in zip(packets, ordered):
        record = by_key[key]
        packet["native_path"] = record["native_sheet"]
        packet["crop_path"] = EV + "/" + OUT_NAME + "/cards/" + packet["packet_id"] + ".jpg"
        render_packet(root / record["native_sheet"], float(record["cand_cx"]),
                      float(record["cand_cy"]), cards / (packet["packet_id"] + ".jpg"))
    prep.assert_packets_blind(packets)
    return {"manifest": manifest, "packets": packets,
            "packet_to_key": list(zip([p["packet_id"] for p in packets], ordered))}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(prog="g391_build")
    parser.add_argument("--root", default=r"C:\Users\neelj\nba-track-a10")
    args = parser.parse_args()
    root = Path(args.root)
    out_dir = root / EV / OUT_NAME
    seal = prep.verify_preregistration(out_dir / "preregistration.md")
    facts = premise(root)
    facts["preregistration_seal"] = seal
    print("PREMISE " + json.dumps({k: facts[k] for k in (
        "n_states", "n_calls_rank0_observed", "tp", "fp", "fn_visible_without_tp",
        "fp_partition", "premise_true",
        "crlf_checkout_explains_prepare_mismatch")}, sort_keys=True))
    if not facts["premise_true"]:
        (out_dir / "premise.json").write_text(json.dumps(facts, indent=2), encoding="ascii")
        print("PREMISE FALSE -- stopping")
        return 1
    census = context_census(root)
    built = build(root)
    facts["context_census"] = {k: v for k, v in census.items() if k != "rows"}
    (out_dir / "premise.json").write_text(json.dumps(facts, indent=2), encoding="ascii")
    write_csv(out_dir / "native_manifest.csv", built["manifest"],
              list(built["manifest"][0].keys()))
    write_csv(out_dir / "packets.csv", built["packets"], list(built["packets"][0].keys()))
    write_csv(out_dir / "context_census.csv", census["rows"],
              list(census["rows"][0].keys()))
    write_csv(out_dir / "packet_key_map_SEALED.csv",
              [{"packet_id": p, "frame_key": k} for p, k in built["packet_to_key"]],
              ["packet_id", "frame_key"])
    print("BUILD packets=%d census_rows=%d causal_present=%d dev_pairs=%d min_gap=%s"
          % (len(built["packets"]), len(census["rows"]),
             census["n_targets_with_two_causal_neighbours"],
             census["dev_pairs_within_0p2s"], census["min_nearest_prior_gap_frames"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
