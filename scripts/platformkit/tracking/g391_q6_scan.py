"""G391 text-artifact vocabulary scan with character-code patterns."""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path


PATTERNS = tuple("".join(chr(code) for code in codes) for codes in (
    (114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
    (43, 49, 56, 46, 51, 56), (48, 46, 49, 49, 57), (43, 53, 52),
    (55, 56, 46, 49, 49), (56, 46, 57, 52), (53, 52, 46, 53, 55),
))


def scan(paths: Iterable[Path]) -> dict[str, list[str]]:
    """Return non-identifier vocabulary matches from the supplied text artifacts."""
    findings: dict[str, list[str]] = {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace").lower()
        # A retracted FIGURE is only that figure: a measured pixel coordinate can
        # merely CONTAIN one of the numeric patterns as a substring, so digits and
        # the decimal point guard those patterns as well as letters do.
        matches = [pattern for pattern in PATTERNS
                   if re.search((r"(?<![0-9a-z.])" if pattern[0].isdigit() or pattern[0] == "+"
                                 else r"(?<![a-z])") + re.escape(pattern)
                                + (r"(?![0-9a-z.])" if pattern[-1].isdigit()
                                   else r"(?![a-z])"), text)]
        if matches:
            findings[Path(path).as_posix()] = matches
    return findings


TEXT_SUFFIXES = (".md", ".csv", ".json", ".txt", ".log", ".py")


def main() -> int:
    """Scan every text artifact this row wrote, its rater logs included."""
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="g391_q6_scan")
    parser.add_argument("--root", default=r"C:\Users\neelj\nba-track-a10")
    parser.add_argument("--extra", nargs="*", default=[])
    args = parser.parse_args()
    root = Path(args.root)
    targets = [path for path in
               (root / "docs/evidence/tracking/g391_ball_false_call_audit_2026-09-11").rglob("*")
               if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES]
    targets += [root / "docs/evidence/tracking/g391_ball_false_call_audit_2026-09-11.md"]
    targets += sorted(Path(p) for p in args.extra)
    targets += sorted(root.glob("scripts/platformkit/tracking/g391_*.py"))
    # The report is written by this scan, so scanning it would report the previous
    # run's own quoted findings as fresh hits.
    targets = [path for path in targets
               if path.is_file() and path.name != "q6_scan.json"]
    findings = scan(targets)
    opaque = {path: hits for path, hits in findings.items()
              if all(pattern in Path(path).name.lower() for pattern in hits)}
    report = {"n_scanned": len(targets), "n_files_with_hits": len(findings),
              "non_opaque_hits": {p: h for p, h in findings.items() if p not in opaque},
              "opaque_identifier_hits": opaque}
    out = (root / "docs/evidence/tracking/g391_ball_false_call_audit_2026-09-11"
           / "q6_scan.json")
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    print("Q6 scanned=%d non_opaque=%d opaque=%d"
          % (len(targets), len(report["non_opaque_hits"]), len(opaque)))
    for path, hits in report["non_opaque_hits"].items():
        print("  HIT %s %s" % (path, hits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
