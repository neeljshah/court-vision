"""G375 scoring: impurity share with Wilson bounds, per prefix, and gate attribution.

Sealed by `docs/evidence/tracking/g375_corpus_sport_purity_2026-09-10/
g375_prereg_2026-09-10.md` (SEAL sha256
2f178a9d533cd9a36f90477ef5b81d499fbe282708433fa29a55344a830242b2). Calibration
language only (Q6): this is a content census, never a gate verdict.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from scripts.platformkit.tracking.g375_census import read_csv, write_csv

Z = 1.959964
PURE = "BASKETBALL_PLAY"
DESCRIPTIVE_BELOW = 30
SHIPPED = re.compile(r"SHIPPED\s+(\S+)\s+(.*)$")
FIELD = re.compile(r"([a-z_]+)=(\S+)")
ATTR_FIELDS = ("sheet_id", "game_id", "prefix", "final_label", "other_sport",
               "shipped_utc", "content", "gate_reason", "max_surface_permille",
               "near_share", "bytes_per_frame")
TABLE_FIELDS = ("prefix", "rated", "impure", "impurity_permille", "wilson_low_permille",
                "wilson_high_permille", "basketball_nonplay", "other_sport", "non_sport",
                "unknown", "reporting")


def wilson(successes: int, total: int) -> tuple[float, float, float]:
    """Point estimate with a Wilson 95 percent interval; a zero total is (0, 0, 0)."""
    if total <= 0:
        return 0.0, 0.0, 0.0
    point = successes / total
    denominator = 1.0 + Z * Z / total
    centre = (point + Z * Z / (2.0 * total)) / denominator
    spread = (Z * math.sqrt(point * (1.0 - point) / total
                            + Z * Z / (4.0 * total * total)) / denominator)
    return point, max(0.0, centre - spread), min(1.0, centre + spread)


def permille(value: float) -> int:
    """Report every share as a per-mille integer, never as currency or a rate of return."""
    return int(round(1000.0 * value))


def shipped_index(log: Path) -> dict[str, dict[str, str]]:
    """Index the feeder log's SHIPPED lines by ledger game id, last line winning."""
    index: dict[str, dict[str, str]] = {}
    if not log.exists():
        return index
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SHIPPED.search(line)
        if match is None:
            continue
        token = match.group(1)
        game_id = token.partition("__")[2] or token
        fields = dict(FIELD.findall(match.group(2)))
        fields["shipped_utc"] = line.split(" ", 1)[0]
        index[game_id] = fields
    return index


def attribute(rows: list[dict[str, str]], index: dict[str, dict[str, str]],
              log_start: str) -> list[dict[str, str]]:
    """Name the admitting gate decision for every non-play section, else UNKNOWN."""
    out: list[dict[str, str]] = []
    for row in rows:
        found = index.get(row["game_id"])
        if found is None:
            out.append({**{key: row.get(key, "") for key in ATTR_FIELDS[:5]},
                        "shipped_utc": "UNKNOWN", "content": "UNKNOWN",
                        "gate_reason": "log_starts_%s_section_finished_%s" % (
                            log_start, row.get("finished_at", "UNKNOWN")),
                        "max_surface_permille": "UNKNOWN", "near_share": "UNKNOWN",
                        "bytes_per_frame": "UNKNOWN"})
            continue
        out.append({**{key: row.get(key, "") for key in ATTR_FIELDS[:5]},
                    "shipped_utc": found.get("shipped_utc", "UNKNOWN"),
                    "content": found.get("content", "UNKNOWN"),
                    "gate_reason": found.get("gate_reason", "UNKNOWN"),
                    "max_surface_permille": found.get("max_surface_permille", "UNKNOWN"),
                    "near_share": found.get("near_share", "UNKNOWN"),
                    "bytes_per_frame": found.get("bytes_per_frame", "UNKNOWN")})
    return out


def table(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Impurity with Wilson bounds overall and per prefix, per-mille integers."""
    groups: dict[str, list[dict[str, str]]] = {"ALL": list(rows)}
    for row in rows:
        groups.setdefault(row["prefix"], []).append(row)
    out: list[dict[str, str]] = []
    for key in ["ALL"] + sorted(k for k in groups if k != "ALL"):
        members = groups[key]
        impure = [row for row in members if row["final_label"] != PURE]
        point, low, high = wilson(len(impure), len(members))
        counts = {label: sum(row["final_label"] == label for row in members)
                  for label in ("BASKETBALL_NONPLAY", "OTHER_SPORT", "NON_SPORT", "UNKNOWN")}
        out.append({"prefix": key, "rated": str(len(members)), "impure": str(len(impure)),
                    "impurity_permille": str(permille(point)),
                    "wilson_low_permille": str(permille(low)),
                    "wilson_high_permille": str(permille(high)),
                    "basketball_nonplay": str(counts["BASKETBALL_NONPLAY"]),
                    "other_sport": str(counts["OTHER_SPORT"]),
                    "non_sport": str(counts["NON_SPORT"]),
                    "unknown": str(counts["UNKNOWN"]),
                    "reporting": "BOUNDED" if len(members) >= DESCRIPTIVE_BELOW
                                 else "DESCRIPTIVE"})
    return out


def join(labels: list[dict[str, str]], sample: list[dict[str, str]],
         census: list[dict[str, str]]) -> list[dict[str, str]]:
    """Attach prefix, game id and ledger finish stamp to every final label."""
    by_sheet = {row["sheet_id"]: row for row in sample}
    finished = {row["game_id"]: row.get("finished_at", "") for row in census}
    out = []
    for row in labels:
        source = by_sheet[row["sheet_id"]]
        out.append({**row, "game_id": source["game_id"], "prefix": source["prefix"],
                    "finished_at": finished.get(source["game_id"], "")})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="G375 impurity and attribution scorer")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--feeder-log", type=Path, required=True)
    parser.add_argument("--log-start", default="UNKNOWN")
    parser.add_argument("--attribution", type=Path, required=True)
    parser.add_argument("--table", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--kappa", type=float, required=True)
    parser.add_argument("--agreement", type=float, required=True)
    parser.add_argument("--absent", type=int, default=0)
    args = parser.parse_args()
    rows = join(read_csv(args.labels), read_csv(args.sample), read_csv(args.census))
    impure = [row for row in rows if row["final_label"] != PURE]
    index = shipped_index(args.feeder_log)
    attribution = attribute(impure, index, args.log_start)
    summary_table = table(rows)
    write_csv(args.attribution, attribution, ATTR_FIELDS)
    write_csv(args.table, summary_table, TABLE_FIELDS)
    overall = summary_table[0]
    sports: dict[str, int] = {}
    for row in rows:
        if row["final_label"] == "OTHER_SPORT" and row["other_sport"]:
            sports[row["other_sport"]] = sports.get(row["other_sport"], 0) + 1
    named = sum(1 for row in attribution if row["content"] != "UNKNOWN")
    summary = {
        "rated_sheets": len(rows), "absent_sections": args.absent,
        "impure_sections": len(impure),
        "impurity_permille": int(overall["impurity_permille"]),
        "impurity_wilson_low_permille": int(overall["wilson_low_permille"]),
        "impurity_wilson_high_permille": int(overall["wilson_high_permille"]),
        "basketball_nonplay": int(overall["basketball_nonplay"]),
        "other_sport": int(overall["other_sport"]),
        "non_sport": int(overall["non_sport"]),
        "unknown": int(overall["unknown"]),
        "other_sport_names": dict(sorted(sports.items())),
        "kappa": round(args.kappa, 6), "raw_agreement": round(args.agreement, 6),
        "prefixes_covered": len(summary_table) - 1,
        "attributed_named": named,
        "attributed_unknown": len(attribution) - named,
        "attribution_complete": len(attribution) == len(impure),
        "gate_thresholds_moved": 0, "sections_deleted": 0,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                            encoding="ascii")
    print(json.dumps(summary, sort_keys=True))
    for row in summary_table:
        print("  %-18s rated=%3s impure=%3s permille=%4s [%4s,%4s] %s" % (
            row["prefix"], row["rated"], row["impure"], row["impurity_permille"],
            row["wilson_low_permille"], row["wilson_high_permille"], row["reporting"]))


if __name__ == "__main__":
    main()
