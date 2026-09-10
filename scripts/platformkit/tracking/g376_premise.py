"""G376 premise (Q8) -- recompute the G370 before-condition on the immutable lane snapshot.

Two zero-observation shares are printed, because they are not the same quantity:
  RAW  -- declared ticks with no row in `tracking_data.csv`, the class OBSERVED of this row.
  M1   -- declared ticks with no surviving PLAYER row after the G370 route, reproduced by
          importing that route verbatim (`load_merged`, `adapt_production_section`,
          `construct_arm("A0")`, `collapse_held`, `cls == "player"`) exactly as
          `g370_scorer.admission_rows` builds its observation arrays. This is the 0.7014 / 0.7644.
Reads the snapshot only; no `src/`, `data/` or deploy path is written.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from scripts.platformkit.tracking.g358_gate_execution import construct_arm, load_merged
from scripts.platformkit.tracking.g359_held_position import collapse_held
from scripts.platformkit.tracking.g376_schedule import frame_set
from scripts.platformkit.tracking.production_schema_adapter import adapt_production_section

BEFORE = {"SEALED34": "0.7014", "FRESH69": "0.7644"}
_f = "{:.6f}".format


def m1_observed_frames(tracking: Path, ball: Path) -> set[int]:
    """The G370 M1 player-observation frames of one section, via the imported G370 route."""
    adapted = adapt_production_section(load_merged(Path(tracking), Path(ball)))
    m1, _ = collapse_held(construct_arm(adapted.table, "A0"))
    players = m1.loc[m1["cls"].eq("player")]
    return {int(value) for value in players["frame"].dropna().tolist()}


def rows(classification: Path, snapshot: Path) -> list[dict[str, object]]:
    """One row per section: declared ticks, raw observed ticks and M1 observed ticks."""
    out = []
    with Path(classification).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            section = Path(snapshot) / row["section_id"]
            declared = int(row["declared_ticks"])
            stride = int(row["stride"]) if row["stride"] else 0
            declared_set = {index * stride for index in range(declared)} if stride else set()
            raw = frame_set(section / "tracking_data.csv")[0] & declared_set
            m1 = m1_observed_frames(section / "tracking_data.csv",
                                    section / "ball_tracking.csv") & declared_set
            out.append({"section_id": row["section_id"], "set": row["set"],
                        "declared_ticks": declared, "raw_observed_ticks": len(raw),
                        "m1_observed_ticks": len(m1),
                        "raw_zero_observation_ticks": declared - len(raw),
                        "m1_zero_observation_ticks": declared - len(m1),
                        "decoded_frames": row["decoded_frames"],
                        "ledger_evaluated_frames": row["ledger_evaluated_frames"],
                        "non_integral_decoded_over_evaluated": int(
                            bool(row["decoded_frames"]) and bool(row["ledger_evaluated_frames"])
                            and int(row["decoded_frames"]) % int(row["ledger_evaluated_frames"]) != 0)})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    section_rows = rows(out_dir / "classification.csv", Path(args.snapshot))
    with (out_dir / "premise.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(section_rows[0]))
        writer.writeheader()
        writer.writerows(section_rows)
    summary = {}
    for set_name in ("SEALED34", "FRESH69"):
        subset = [row for row in section_rows if row["set"] == set_name]
        declared = sum(row["declared_ticks"] for row in subset)
        raw_zero = sum(row["raw_zero_observation_ticks"] for row in subset)
        m1_zero = sum(row["m1_zero_observation_ticks"] for row in subset)
        summary[set_name] = {
            "sections": len(subset), "declared_ticks": declared,
            "raw_zero_observation_ticks": raw_zero,
            "raw_zero_observation_share": _f(raw_zero / declared),
            "m1_zero_observation_ticks": m1_zero,
            "m1_zero_observation_share": _f(m1_zero / declared),
            "g370_published_m1_zero_observation_share": BEFORE[set_name],
            "sections_non_integral_decoded_over_evaluated": sum(
                row["non_integral_decoded_over_evaluated"] for row in subset),
            "premise_holds_at_0_10": (raw_zero / declared) >= 0.10,
        }
    (out_dir / "premise.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
