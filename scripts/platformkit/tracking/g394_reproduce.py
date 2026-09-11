"""G394 reproduction: recount every arm in a fresh process from saved predictions only.

This is a scorer replay over archived CSVs. It loads no detector and runs no
inference, so it can never stand in for the one charged candidate pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace/wt/a7")

from scripts.platformkit.tracking.g363_score import score_arm  # noqa: E402
from scripts.platformkit.tracking.g390_sealed_input import load_sealed_input  # noqa: E402
from scripts.platformkit.tracking.g394_finish import ARMS, EVIDENCE  # noqa: E402
from scripts.platformkit.tracking.g394_run import G389, rows  # noqa: E402


def main() -> None:
    """Print the reproduced per-arm counts for one fresh process."""
    sealed = load_sealed_input(G389 / "frames_v3.csv", G389 / "reference_v3.csv")
    refs = {key: {"label": row["label"], "cx": row["cx"], "cy": row["cy"],
                  "diameter": row["diameter"]} for key, row in sealed.reference.items()}
    predictions = rows(EVIDENCE / "predictions.csv")
    out = {}
    for arm in ARMS:
        summary, _ = score_arm(arm, "heldout", sealed.frames, refs, predictions)
        out[arm] = {"tp": summary["tp"], "fp": summary["fp"],
                    "fn": summary["n_visible"] - summary["tp"],
                    "coverage": summary["coverage"],
                    "precision_wilson_lo": summary["precision_wilson_lo"],
                    "fp_per_absent": summary["fp_per_absent"],
                    "n_frames": summary["n_frames"], "n_visible": summary["n_visible"],
                    "n_absent": summary["n_absent"], "n_unknown": summary["n_unknown"]}
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    if path:
        path.write_text(text, encoding="ascii", newline="\n")
    print("G394 REPRODUCE " + json.dumps(out, sort_keys=True), flush=True)


if __name__ == "__main__":
    sys.exit(main())
