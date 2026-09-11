"""G396 eligibility decision, state accounting and artifact digests.

Fewer than two raters qualified on the FRESH G396 controls blocks every
real-paint dispatch. No bar is lowered and no recovery figure is invented.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking import g392_finish as finish

REAL_NOTE_BLOCKED = ("not scored: fewer than two raters qualified on the fresh G396 controls; "
                     "the paint line PAUSES with no rater substitution, no new control seed and "
                     "no protocol switch inside this row. G388's 0/30 audited diagnostic stands "
                     "unrepeated and is not restated as a G396 result")


def _render_digest(landed_root: Path, candidate_root: Path, landed: list[Path]) -> str:
    """Hash sorted relative path/digest pairs, marking unavailable raw rerenders."""
    pairs = []
    for path in landed:
        relpath = path.relative_to(landed_root).as_posix()
        candidate = candidate_root / relpath
        pairs.append("%s\t%s\n" % (relpath, hashlib.sha256(candidate.read_bytes()).hexdigest()
                                     if candidate.is_file() else "MISSING"))
    return hashlib.sha256("".join(sorted(pairs)).encode("ascii")).hexdigest()


def render_repeat_report(evidence: Path, repeat_one: Path, repeat_two: Path) -> dict[str, object]:
    """Write per-tree and per-file fresh-process render digest evidence."""
    landed_root = evidence / "renders"
    rows, trees = [], {}
    for tree in sorted(path for path in landed_root.iterdir() if path.is_dir()):
        landed = sorted(path for path in tree.rglob("*") if path.is_file())
        named = tree.name
        one_root, two_root = repeat_one / named, repeat_two / named
        for path in landed:
            relpath = path.relative_to(tree).as_posix()
            values = [path, one_root / relpath, two_root / relpath]
            digests = [hashlib.sha256(value.read_bytes()).hexdigest() if value.is_file() else "MISSING"
                       for value in values]
            rows.append({"tree": named, "relpath": relpath, "landed": digests[0],
                         "process_1": digests[1], "process_2": digests[2],
                         "identical": str(digests[0] == digests[1] == digests[2]).lower()})
        trees[named] = {"process_1": _render_digest(tree, one_root, landed),
                        "process_2": _render_digest(tree, two_root, landed),
                        "matches_landed": _render_digest(tree, tree, landed),
                        "identical": all(row["identical"] == "true" for row in rows
                                         if row["tree"] == named), "files": len(landed)}
    target = evidence / "renders_repeat_digests.csv"
    with target.open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=("tree", "relpath", "landed", "process_1",
                                                    "process_2", "identical"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    payload = json.loads((evidence / "repeats.json").read_text(encoding="utf-8"))
    payload["render_trees"] = trees
    payload["render_identity_share"] = "%d/%d" % (sum(row["identical"] == "true" for row in rows),
                                                     len(rows))
    (evidence / "repeats.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                             encoding="utf-8", newline="\n")
    return {"render_trees": trees, "render_identity_share": payload["render_identity_share"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--real", type=Path, default=None)
    parser.add_argument("--extra", type=Path, nargs="*", default=[])
    parser.add_argument("--render-repeats-only", action="store_true")
    parser.add_argument("--refresh-manifest-only", action="store_true")
    parser.add_argument("--repeat-one", type=Path)
    parser.add_argument("--repeat-two", type=Path)
    args = parser.parse_args()
    if args.render_repeats_only:
        if not args.repeat_one or not args.repeat_two:
            parser.error("render repeat report requires repeat-one and repeat-two")
        print(json.dumps(render_repeat_report(args.evidence, args.repeat_one, args.repeat_two),
                         indent=2, sort_keys=True))
        return 0
    if args.refresh_manifest_only:
        lines = ["%s  %s" % pair for pair in finish.digests([args.evidence])
                 if not pair[1].endswith("/SHA256SUMS")]
        (args.evidence / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii",
                                                    newline="\n")
        print("G396_MANIFEST files=%d" % len(lines))
        return 0
    practice = json.loads((args.evidence / "practice" / "summary.json").read_text(encoding="utf-8"))
    qualification = json.loads(
        (args.evidence / "qualification" / "summary.json").read_text(encoding="utf-8"))
    decision = finish.eligibility(qualification)
    real = json.loads(args.real.read_text(encoding="utf-8")) if args.real and args.real.is_file() else None
    decision["real_scored"] = bool(real)
    (args.evidence / "eligibility.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    summary = {"row": "G396",
               "verdict": "PARTIAL -- PROTOCOL NOT QUALIFIED" if not decision["real_dispatch_allowed"]
               else ("DONE" if real else "QUALIFIED -- REAL PAINT PENDING"),
               "protocol_qualified": bool(decision["real_dispatch_allowed"]),
               "practice": practice, "qualification": qualification, "eligibility": decision,
               "parent_states": finish.parent_states(args.census),
               "real_paint_scored": bool(real), "real_paint": real,
               "real_paint_note": REAL_NOTE_BLOCKED if not real else
               "scored on the sealed even 30-of-49 retained contexts; denominator is conditional on retained images"}
    (args.evidence / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    lines = ["%s  %s" % pair for pair in finish.digests([args.evidence] + list(args.extra))
             if not pair[1].endswith("/SHA256SUMS")]
    (args.evidence / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    print(json.dumps({"eligibility": decision, "parent_states": summary["parent_states"],
                      "verdict": summary["verdict"], "artifacts": len(lines)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
