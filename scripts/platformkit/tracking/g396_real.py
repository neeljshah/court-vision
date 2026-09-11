"""G396 real-paint batches, pairing and per-context accounting for sol and ASTRA.

Reuses the G388 fragment reader and the G396 geometry unchanged. It never
invents a recovery minimum and never drops an UNKNOWN or ABSENT context.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g388_score as g388s
from scripts.platformkit.tracking import g396_protocol as protocol

BATCH_SIZE = 10
SEED = 396
RATERS = ("astra", "sol")


def context_ids(transforms: Path) -> list[str]:
    """Return the unchanged even 30-of-49 selection under an opaque G396 label."""
    keys = sorted({row["opaque_id"] for row in tiles.read_csv(transforms)})
    if len(keys) != protocol.CONTROL_COUNT:
        raise ValueError("expected exactly 30 inherited real contexts")
    return ["G396_" + key.split("_")[1] for key in keys]


def build_batches(transforms: Path, cache: Path, work: Path) -> dict[str, list[str]]:
    """Write one blind per-rater real batch: six fixed tiles per context line."""
    rows = tiles.read_csv(transforms)
    by_context: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_context.setdefault(row["opaque_id"], []).append(row)
    order = context_ids(transforms)
    random.Random(SEED).shuffle(order)
    written: dict[str, list[str]] = {}
    for rater in RATERS:
        directory = work / ("batch_real_%s" % rater)
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for start in range(0, len(order), BATCH_SIZE):
            batch = directory / ("batch_%02d.tsv" % (start // BATCH_SIZE + 1))
            lines = []
            for label in order[start:start + BATCH_SIZE]:
                source = sorted(by_context["G387_" + label.split("_")[1]],
                                key=lambda row: (int(row["y"]), int(row["x"])))
                if len(source) != 6:
                    raise ValueError("a context does not carry its six sealed tiles")
                lines.append(label + "\t" + ",".join(
                    (cache / row["tile"]).as_posix() for row in source))
            batch.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
            paths.append(batch.as_posix())
        written[rater] = paths
    return written


def _symmetric(left: protocol.Fragment, right: protocol.Fragment) -> float:
    """Stable symmetric infinite-line distance used only to order candidates."""
    values = [protocol._line_distance(point, right.line())
              for point in (left.first, left.second, left.third)]
    values += [protocol._line_distance(point, left.line())
               for point in (right.first, right.second, right.third)]
    return sum(values) / len(values)


def pair_contexts(labels: list[str], out_dirs: dict[str, Path]) -> list[dict[str, object]]:
    """Pair both qualified raters' fragments once per context under the sealed rules."""
    results = []
    for label in labels:
        state_a, raw_left = g388s.read_real_response(out_dirs["astra"] / (label + ".json"))
        state_b, raw_right = g388s.read_real_response(out_dirs["sol"] / (label + ".json"))
        left = [protocol.Fragment(f.tile, f.family, f.first, f.second, f.third, f.fragment_id)
                for f in raw_left]
        right = [protocol.Fragment(f.tile, f.family, f.first, f.second, f.third, f.fragment_id)
                 for f in raw_right]
        scored = sorted(((_symmetric(a, b), i, j, a, b)
                         for i, a in enumerate(left) for j, b in enumerate(right)
                         if protocol.pair_compatible(a, b)), key=lambda row: row[:3])
        used_left: set[int] = set()
        used_right: set[int] = set()
        pairs = []
        for _value, i, j, a, b in scored:
            if i not in used_left and j not in used_right:
                used_left.add(i)
                used_right.add(j)
                pairs.append((a, b))
        families = {f.family for f in left} ^ {f.family for f in right}
        results.append({"context_id": label, "astra_state": state_a, "sol_state": state_b,
                        "astra_fragments": left, "sol_fragments": right, "pairs": pairs,
                        "family_disagreement": bool(families)})
    return results


def tables(results: list[dict[str, object]], visibility: dict[str, str],
           audit: dict[str, dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return the pair table and the accounting row for every one of the 30 states."""
    pairs, frames = [], []
    for record in results:
        context = str(record["context_id"])
        audited = 0
        for order, (left, right) in enumerate(record["pairs"], start=1):
            pair_id = "%s_pair%d" % (context, order)
            verdict = audit.get(pair_id, {})
            same = str(verdict.get("same_band", "PENDING")).upper()
            audited += same == "YES"
            pairs.append({"pair_id": pair_id, "context_id": context, "tile": str(left.tile),
                          "family": left.family,
                          "symmetric_line_px": "%.2f" % _symmetric(left, right),
                          "astra_span_px": "%.1f" % left.line().length(),
                          "sol_span_px": "%.1f" % right.line().length(),
                          "passes_sealed_6px_rule": "YES",
                          "claude_audit_same_painted_band": same,
                          "audit_points_within_3px": str(verdict.get("points_within_3px", "")),
                          "audit_note": str(verdict.get("note", "")),
                          "card": "renders/audit_cards/%s.png" % pair_id})
        frames.append({"context_id": context,
                       "claude_visibility": visibility.get(context, "UNKNOWN"),
                       "astra_state": str(record["astra_state"]),
                       "sol_state": str(record["sol_state"]),
                       "astra_fragments": str(len(record["astra_fragments"])),
                       "sol_fragments": str(len(record["sol_fragments"])),
                       "candidate_pairs": str(len(record["pairs"])),
                       "audited_same_band": str(audited),
                       "family_disagreement": "YES" if record["family_disagreement"] else "NO"})
    return pairs, frames


def summarise(frames: list[dict[str, str]]) -> dict[str, object]:
    """Account for all 30 states with both denominators and no invented minimum."""
    visible = [row for row in frames if row["claude_visibility"] == "YES"]
    return {"states_accounted": len(frames),
            "recovered_of_all": {"passed": sum(int(row["audited_same_band"]) > 0 for row in frames),
                                 "denominator": len(frames)},
            "recovered_of_visible": {
                "passed": sum(int(row["audited_same_band"]) > 0 for row in visible),
                "denominator": len(visible)},
            "candidate_pairs": sum(int(row["candidate_pairs"]) for row in frames),
            "family_disagreement": sum(row["family_disagreement"] == "YES" for row in frames),
            "unknown_or_absent": {
                rater: sum(row[rater + "_state"] != "VISIBLE" for row in frames)
                for rater in RATERS},
            "denominator_note": (
                "conditional on the 49 retained native images of the 60-state parent census; "
                "the 11 parent decode failures are in neither denominator")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transforms", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_batches(args.transforms, args.cache, args.work), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
