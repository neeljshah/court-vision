"""G392 eligibility decision, row summary and artifact digests.

Fewer than two qualified raters blocks every real-paint dispatch. This module
never lowers a bar and never invents a recovery figure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g392_protocol as protocol

SKIP_SUFFIXES = {".pyc"}


def eligibility(qualification: dict[str, object]) -> dict[str, object]:
    """Name every qualified and excluded rater and the real-dispatch decision."""
    per_rater = qualification["per_rater"]
    qualified = sorted(name for name, row in per_rater.items()
                       if row["passed"] >= protocol.CONTROL_BAR)
    excluded = sorted(name for name in per_rater if name not in qualified)
    allowed = len(qualified) == 2 and qualification["joint"] >= protocol.CONTROL_BAR
    return {"bar": protocol.CONTROL_BAR, "controls": protocol.CONTROL_COUNT,
            "per_rater_passed": {name: per_rater[name]["passed"] for name in sorted(per_rater)},
            "joint": qualification["joint"], "qualified_raters": qualified,
            "excluded_raters": excluded, "real_dispatch_allowed": bool(allowed),
            "real_scored": False if not allowed else None,
            "decision": ("REAL PAINT NOT SCORED -- PROTOCOL NOT QUALIFIED" if not allowed
                         else "REAL PAINT DISPATCH PERMITTED"),
            "retry_or_substitute": "none -- the sealed method forbids both"}


def parent_states(census: Path) -> dict[str, int]:
    """Account for all 60 original states, including the 11 parent decode failures."""
    rows = tiles.read_csv(census)
    retained = [row for row in rows if row.get("retained") == "RETAINED"]
    return {"states": len(rows), "retained": len(retained),
            "parent_failures": len(rows) - len(retained),
            "native_ready": sum(row.get("status") == "READY" for row in retained)}


def digests(roots: list[Path]) -> list[tuple[str, str]]:
    out = []
    for root in roots:
        targets = [root] if root.is_file() else sorted(
            path for path in root.rglob("*") if path.is_file())
        for path in targets:
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            out.append((hashlib.sha256(path.read_bytes()).hexdigest(), path.as_posix()))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--extra", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    practice = json.loads((args.evidence / "practice" / "summary.json").read_text(encoding="utf-8"))
    qualification = json.loads(
        (args.evidence / "qualification" / "summary.json").read_text(encoding="utf-8"))
    decision = eligibility(qualification)
    (args.evidence / "eligibility.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    summary = {"row": "G392", "verdict": "PARTIAL -- PROTOCOL NOT QUALIFIED"
               if not decision["real_dispatch_allowed"] else "QUALIFIED",
               "protocol_qualified": bool(decision["real_dispatch_allowed"]),
               "practice": practice, "qualification": qualification,
               "eligibility": decision, "parent_states": parent_states(args.census),
               "real_paint_scored": False,
               "real_paint_note": ("not scored: fewer than two qualified raters; G388's 0/30 "
                                   "audited and 0/23 visible-conditioned diagnostic stands "
                                   "unrepeated and is not restated as a G392 result")}
    (args.evidence / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    lines = ["%s  %s" % pair for pair in digests([args.evidence] + list(args.extra))]
    (args.evidence / "SHA256SUMS").write_text("\n".join(lines) + "\n",
                                              encoding="ascii", newline="\n")
    print(json.dumps({"eligibility": decision, "parent_states": summary["parent_states"],
                      "artifacts": len(lines)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
