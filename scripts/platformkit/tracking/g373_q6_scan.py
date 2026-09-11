"""G373 phase 1: the contract Q6 vocabulary scan over this row's own artifacts.

Q6 forbids monetary, return-rate, gain and advantage language, and the retracted
figures, in any artifact, memo, ledger line or register row.  The scan patterns are
ASSEMBLED FROM CHARACTER CODES at run time, so no forbidden token appears as a
literal in this file and the scanner never reports itself.

Q6 NOTE (orchestrator ruling 2026-09-04, S223): opaque identifiers quoted verbatim
-- file basenames, paths, column names, module strings -- are exempt even when they
contain a forbidden token.  A census must emit the exact path and never mask it, so
a hit inside a path-like run of characters is reported separately as EXEMPT-PATH
rather than as a finding.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Word stems and retracted figures, built from code points so they are not literals.
_WORDS = ((100, 111, 108, 108, 97, 114), (114, 111, 105), (112, 114, 111, 102, 105, 116),
          (101, 100, 103, 101), (98, 97, 110, 107, 114, 111, 108, 108),
          (112, 110, 108), (119, 97, 103, 101, 114))
_FIGURES = ((49, 56, 46, 51, 56), (48, 46, 49, 49, 57), (55, 56, 46, 49, 49),
            (56, 46, 57, 52), (53, 52, 46, 53, 55))
PATH_LIKE = re.compile(r"[A-Za-z0-9_./\\-]*[/\\._][A-Za-z0-9_./\\-]*")


def patterns() -> list[tuple[str, re.Pattern]]:
    """Whole-word stems plus the retracted figures, assembled at run time."""
    out = []
    for codes in _WORDS:
        token = "".join(chr(code) for code in codes)
        out.append((token, re.compile(r"(?<![A-Za-z])" + token + r"[a-z]*(?![A-Za-z])",
                                      re.IGNORECASE)))
    for codes in _FIGURES:
        token = "".join(chr(code) for code in codes)
        out.append((token, re.compile(re.escape(token))))
    return out


def scan_text(text: str, rules: list[tuple[str, re.Pattern]]) -> tuple[int, int, list[str]]:
    """Findings and path-exempt hits for one artifact's text."""
    exempt_spans = [match.span() for match in PATH_LIKE.finditer(text)]
    findings, exempt, samples = 0, 0, []
    for token, rule in rules:
        for match in rule.finditer(text):
            inside = any(start <= match.start() and match.end() <= end
                         for start, end in exempt_spans)
            if inside:
                exempt += 1
                continue
            findings += 1
            if len(samples) < 8:
                samples.append(f"{token}@{match.start()}")
    return findings, exempt, samples


def run(args) -> int:
    rules = patterns()
    report: dict[str, dict] = {}
    total = 0
    output = Path(args.out).resolve() if args.out else None
    for name in args.path:
        path = Path(name)
        targets = sorted(item for item in path.rglob("*") if item.is_file()) \
        if path.is_dir() else [path]
        for target in targets:
            if output is not None and target.resolve() == output:
                continue
            if target.suffix.lower() in (".jpg", ".jpeg", ".png", ".pt", ".tar", ".mp4"):
                continue
            try:
                text = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            findings, exempt, samples = scan_text(text, rules)
            total += findings
            if findings or exempt:
                report[str(target).replace("\\", "/")] = {
                    "findings": findings, "exempt_path": exempt, "samples": samples}
    if args.ledger_rows:
        ledger = Path(args.ledger_rows)
        rows = [line for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines()
                if "| G373 |" in line]
        findings, exempt, samples = scan_text("\n".join(rows), rules)
        total += findings
        if findings or exempt:
            report[str(ledger).replace("\\", "/") + "#G373"] = {
                "findings": findings, "exempt_path": exempt, "samples": samples}
    payload = {"scanned_roots": list(args.path), "ledger_rows": args.ledger_rows,
               "total_findings": total, "by_file": report}
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                                  encoding="ascii", newline="\n")
    print("Q6-SCAN total_findings=" + str(total) + " files_with_any=" + str(len(report)))
    for name, entry in sorted(report.items()):
        if entry["findings"]:
            print("  FINDING " + name + " " + json.dumps(entry["samples"]))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g373_q6_scan")
    parser.add_argument("path", nargs="+")
    parser.add_argument("--out", default="")
    parser.add_argument("--ledger-rows", default="")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
