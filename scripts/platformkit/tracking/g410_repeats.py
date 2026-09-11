"""Two fresh-process reproductions of every delivered G410 table and card."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.platformkit.tracking.g410_finalize import digests

PARENT = "docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11"
DELIVERED = "docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12"


def steps(out: str, traces: str) -> list:
    """Return the ordered regenerating commands for one reproduction round."""
    run = [sys.executable, "-m"]
    return [
        run + ["scripts.platformkit.tracking.g410_measure", PARENT, out],
        run + ["scripts.platformkit.tracking.g410_sources", PARENT,
               out + "/replay_queue.tsv", out + "/source_receipts.csv"],
        run + ["scripts.platformkit.tracking.g410_bound_trace", traces,
                      out + "/per_row.csv", out + "/runtime_receipts/traces"],
        run + ["scripts.platformkit.tracking.g410_report",
                      out + "/runtime_receipts/traces", out + "/per_row.csv", out],
        run + ["scripts.platformkit.tracking.g410_render",
                      out + "/per_row.csv", PARENT + "/source_receipts.csv", out],
        run + ["scripts.platformkit.tracking.g410_finalize", out],
    ]


def one_round(traces: str) -> dict:
    """Run one full regeneration in a fresh temporary tree and digest it."""
    tmp = tempfile.mkdtemp(prefix="g410_round_")
    (Path(tmp) / "runtime_receipts").mkdir(parents=True, exist_ok=True)
    receipt = Path(traces).parent / "launch_receipts.tsv"
    if receipt.exists():
        shutil.copyfile(receipt, Path(tmp) / "runtime_receipts" / receipt.name)
    runs = []
    for command in steps(tmp, traces):
        done = subprocess.run(command, capture_output=True, text=True)
        runs.append({"command": " ".join(command[2:]),
                     "returncode": done.returncode,
                     "stdout": done.stdout.strip()[-400:]})
        if done.returncode != 0:
            runs[-1]["stderr_tail"] = done.stderr.strip()[-400:]
            break
    table = digests(Path(tmp))
    table.pop("q6_scan.json", None)
    return {"runs": runs, "digests": table, "tmp": tmp}


def main(out: str, traces: str = DELIVERED + "/runtime_receipts/traces") -> None:
    """Write repeats.json in the parent receipt shape."""
    rounds = [one_round(traces), one_round(traces)]
    delivered = digests(Path(DELIVERED))
    delivered.pop("q6_scan.json", None)
    delivered.pop("repeats.json", None)
    shared = sorted(set(rounds[0]["digests"]) & set(delivered))
    identical = (rounds[0]["digests"] == rounds[1]["digests"]
                 and all(rounds[0]["digests"][k] == delivered[k] for k in shared))
    tables = {k: v for k, v in rounds[0]["digests"].items()
              if k.endswith(".csv") or k.endswith(".json") or k.endswith(".jsonl")}
    renders = {k: v for k, v in rounds[0]["digests"].items()
               if k.startswith("renders/")}
    payload = {
        "identical": bool(identical),
        "rounds": 2,
        "mode": "fresh-process-regeneration-from-delivered-bytes",
        "note": ("two fresh processes rebuild every table and card from the "
                 "landed parent bytes and the delivered bounded traces; this "
                 "does not prove producer-run repeatability"),
        "runs": [r["runs"] for r in rounds],
        "round_digest_match": rounds[0]["digests"] == rounds[1]["digests"],
        "delivered_keys_compared": len(shared),
        "delivered_mismatches": [k for k in shared
                                 if rounds[0]["digests"][k] != delivered[k]],
        "table_digests": tables,
        "render_digests": renders,
        "render_count": len(renders),
        "canonical_digests": rounds[0]["digests"],
    }
    Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                         encoding="ascii", newline="")
    print("identical=%s compared=%d mismatches=%d"
          % (payload["identical"], len(shared), len(payload["delivered_mismatches"])))


if __name__ == "__main__":
    main(*sys.argv[1:])
