"""Re-run G370's binding premise from G359/G366 records and table headers."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

from scripts.platformkit.tracking.g366_confirm import rejection

ARTIFACT_GATES = ("zero_step_share", "distinct_position_ratio")
PROVENANCE_FIELDS = ("position_source", "producer_branch_file_line", "attribution_evidence_sha256")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def provenance_share(section_rows: Iterable[dict[str, str]], sections_dir: Path) -> dict[str, object]:
    """Inspect one player-table header at a time; never load a tracking store."""
    total = stamped = 0
    for row in section_rows:
        name = row["section_name"]
        path = sections_dir / name / "tracking_data.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            fields = set((csv.DictReader(handle).fieldnames or ()))
        total += 1
        stamped += int(any(field in fields for field in PROVENANCE_FIELDS))
    return {"sections_n": total, "explicit_provenance_sections_n": stamped,
            "share": stamped / total if total else 0.0}


def binding_metrics(g359_arms: Path, g366_gates: Path, g366_ticks: Path) -> dict[str, object]:
    """Recompute named premise quantities from the sealed per-section evaluator records."""
    sealed, fresh = read_csv(g359_arms), read_csv(g366_gates)
    combined = sealed + fresh
    artifact = {gate: rejection(combined, "A0", gate, "M1") for gate in ARTIFACT_GATES}
    stationary = rejection(fresh, "A0", "stationary_track_share", "M1")
    ratios = [float(row["ratio_vs_evaluated"]) for row in read_csv(g366_ticks)
              if row.get("ratio_vs_evaluated")]
    ratios.sort()
    median = ratios[len(ratios) // 2] if len(ratios) % 2 else (ratios[len(ratios) // 2 - 1] + ratios[len(ratios) // 2]) / 2
    return {"artifact_gate_a0_m1_rejection": artifact,
            "stationary_a0_m1_rejection_fresh": stationary,
            "tick_ratio_median_fresh": median, "tick_ratio_n": len(ratios)}


def main() -> None:
    parser = argparse.ArgumentParser(description="G370 binding premise")
    parser.add_argument("--g359-arms", required=True, type=Path)
    parser.add_argument("--g366-gates", required=True, type=Path)
    parser.add_argument("--g366-ticks", required=True, type=Path)
    parser.add_argument("--g358-sections", required=True, type=Path)
    parser.add_argument("--fresh-sections", required=True, type=Path)
    parser.add_argument("--sections-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = binding_metrics(args.g359_arms, args.g366_gates, args.g366_ticks)
    sections = read_csv(args.g358_sections) + [row for row in read_csv(args.fresh_sections)
                                                 if row.get("selected") == "1"]
    payload["provenance"] = provenance_share(sections, args.sections_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
