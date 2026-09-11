"""G389 step 0: whole-set premise, native sheet census, sealed deterministic sweep.

Runs on the PC only (the native sheets live in the repo, not on the pod). It makes
no judgment: it reproduces the binding counts, hashes and OPENS every pending sheet,
and freezes the sealed bin/round-robin permutation and the disjoint rater allocation
before any rater is dispatched.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g389_premise as premise
import g389_prepare as prepare

ROOT = Path(__file__).resolve().parents[3]
D373 = ROOT / "docs/evidence/tracking/g373_ball_detector_v2_2026-09-10"
D384 = ROOT / "docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10"
OUT = ROOT / "docs/evidence/tracking/g389_ball_reference_completion_2026-09-11"
AUDIT_N = 30


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    """Write one evidence table with an explicit, additive field order."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def load() -> dict:
    """Read every sealed input table once, keyed by its fixed role."""
    return {
        "manifest": premise.read_rows(D373 / "sheet_manifest_all.csv"),
        "reference": premise.read_rows(D373 / "reference_v2.csv"),
        "adjudications": premise.read_rows(D384 / "adjudications_g384.csv"),
        "dev_boxes": premise.read_rows(D373 / "dev_boxes.csv"),
        "frames": premise.read_rows(D384 / "frames_v2.csv"),
    }


def enrich(manifest: list[dict], frames: list[dict]) -> list[dict]:
    """Attach game/section/frame_index so the sealed sort key is fully defined."""
    index = {row["frame_key"]: row for row in frames}
    out = []
    for row in manifest:
        extra = index.get(row["frame_key"], {})
        out.append({**row, "game": extra.get("game", ""), "section": extra.get("section", ""),
                    "frame_index": extra.get("frame_index", "0"),
                    "sheet_scale": extra.get("sheet_scale", "")})
    return out


def even_indices(total: int, count: int) -> list[int]:
    """Evenly spaced positions over the WHOLE queue -- never a head slice (A3/B7)."""
    return [(index * total) // count + (total // count) // 2 for index in range(count)]


def main() -> int:
    data = load()
    counts = premise.binding_counts(data["manifest"], data["reference"],
                                    data["adjudications"], data["dev_boxes"])
    premise.check_binding(counts)
    settled = {row["frame_key"] for row in data["reference"]} | \
              {row["frame_key"] for row in data["adjudications"]}
    rows = enrich(data["manifest"], data["frames"])
    pending_rows = prepare.pending_keys(rows, settled)
    pending = {row["frame_key"] for row in pending_rows}

    receipts = premise.sheet_receipts(data["manifest"], pending, D373 / "sheets")
    opened = sum(receipt["status"] == "OPENED" for receipt in receipts)
    hash_ok = sum(1 for receipt in receipts
                  if receipt["sha256"] and receipt["sha256"] == next(
                      row["sheet_sha256"] for row in data["manifest"]
                      if row["frame_key"] == receipt["frame_key"]))
    native = sum(1 for receipt in receipts
                 if (receipt["width"], receipt["height"]) == (1920, 1080))
    write_csv(OUT / "pending_sheet_receipts.csv", receipts,
              ["frame_key", "sheet", "exists", "bytes", "sha256", "width", "height", "status"])

    groups, order = prepare.bins_and_permutation(pending_rows)
    audit = {order[index]["frame_key"] for index in even_indices(len(order), AUDIT_N)}
    bin_of = {row["frame_key"]: number for number, group in enumerate(groups, 1)
              for row in group}
    sweep = []
    for ordinal, row in enumerate(order, 1):
        sweep.append({"ordinal": ordinal, "bin": bin_of[row["frame_key"]],
                      "frame_key": row["frame_key"], "split": row["split"],
                      "source": row["source"], "game": row["game"],
                      "section": row["section"], "frame_index": row["frame_index"],
                      "sheet": row["sheet"],
                      "allocation": ("terra", "sol")[(ordinal - 1) % 2],
                      "audit_duplicate": int(row["frame_key"] in audit)})
    write_csv(OUT / "sweep_permutation.csv", sweep,
              ["ordinal", "bin", "frame_key", "split", "source", "game", "section",
               "frame_index", "sheet", "allocation", "audit_duplicate"])
    write_csv(OUT / "sweep_bins.csv",
              [{"bin": number, "n": len(group), "first_key": group[0]["frame_key"],
                "last_key": group[-1]["frame_key"]}
               for number, group in enumerate(groups, 1)],
              ["bin", "n", "first_key", "last_key"])

    census = [{"frame_key": row["frame_key"], "split": row["split"], "source": row["source"],
               "sheet": row["sheet"], "sheet_bytes": row["sheet_bytes"],
               "width": row["width"], "height": row["height"], "game": row["game"],
               "section": row["section"], "frame_index": row["frame_index"],
               "sheet_scale": row["sheet_scale"],
               "queue_state": "PENDING" if row["frame_key"] in pending else "SETTLED",
               "settled_by": ("g384" if any(a["frame_key"] == row["frame_key"]
                                            for a in data["adjudications"])
                              else "g373" if row["frame_key"] not in pending else "")}
              for row in rows]
    write_csv(OUT / "key_sheet_census.csv", census,
              ["frame_key", "split", "source", "sheet", "sheet_bytes", "width", "height",
               "game", "section", "frame_index", "sheet_scale", "queue_state", "settled_by"])

    summary = {"binding_counts": counts, "binding_verdict": "HOLDS",
               "pending_sheets": len(receipts), "sheets_opened": opened,
               "sheets_hash_match": hash_ok, "sheets_native_1920x1080": native,
               "sheets_missing_pixels": len(receipts) - opened,
               "sheet_bytes_total": sum(int(r["bytes"]) for r in receipts),
               "bins": len(groups), "permutation_len": len(order),
               "allocation": {"terra": sum(s["allocation"] == "terra" for s in sweep),
                              "sol": sum(s["allocation"] == "sol" for s in sweep)},
               "audit_duplicate_keys": len(audit),
               "checkpoints": list(prepare.CHECKPOINTS)}
    (OUT / "premise.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
