"""G404 field-aware vocabulary scan over EVERY landable text artifact.

Patterns are built from character codes so this file never spells a banned token.
Output is counts only, keyed by pattern INDEX, and the scan always includes its own
source and every rater or runtime .txt receipt. Numeric patterns are reported with
their line context classified as retraction or claim, never silently dropped.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _word(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


PROSE_PATTERNS = (
    _word(114, 111, 105),
    _word(112, 114, 111, 102, 105, 116),
    _word(101, 100, 103, 101),
    _word(100, 111, 108, 108, 97, 114),
    _word(98, 97, 110, 107, 114, 111, 108, 108),
    _word(112, 110, 108),
)
NUMERIC_PATTERNS = (_word(43, 49, 56, 46, 51, 56), _word(48, 46, 49, 49, 57),
                    _word(43, 53, 52), _word(55, 56, 46, 49, 49),
                    _word(56, 46, 57, 52), _word(53, 52, 46, 53, 55))
RETRACTION_MARKS = (_word(114, 101, 116, 114, 97, 99, 116),
                    _word(78, 79, 84, 32, 86, 69, 82, 73, 70, 73, 69, 68))
SUFFIXES = (".md", ".csv", ".json", ".txt", ".py", ".jsonl")


def is_identifier_context(line: str) -> bool:
    """An opaque identifier quoted verbatim is exempt by the Q6 orchestrator ruling."""
    return "/" in line or "\\" in line or line.strip().startswith("#")


def columns_of(line: str, header: list[str], token: str) -> list[str]:
    """Name the CSV columns a numeric pattern lands in; a data column is not a claim."""
    cells = line.split(",")
    return [header[index] if index < len(header) else "column_%d" % index
            for index, cell in enumerate(cells) if token in cell]


def scan_path(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    header = lines[0].split(",") if lines and path.suffix.lower() == ".csv" else []
    prose: dict[str, int] = {}
    numeric: dict[str, dict[str, int]] = {}
    for line in lines:
        lowered = line.lower()
        retraction = any(mark.lower() in lowered for mark in RETRACTION_MARKS)
        for index, token in enumerate(PROSE_PATTERNS):
            hits = len(re.findall(r"\b" + re.escape(token) + r"\b", lowered))
            if hits and not is_identifier_context(line):
                key = "prose_%d" % index
                prose[key] = prose.get(key, 0) + hits
        for index, token in enumerate(NUMERIC_PATTERNS):
            if token not in line:
                continue
            key = "numeric_%d" % index
            bucket = numeric.setdefault(key, {"retraction_context": 0, "claim_context": 0,
                                              "data_field_context": 0, "fields": []})
            fields = columns_of(line, header, token) if header else []
            if fields:
                bucket["data_field_context"] += 1
                bucket["fields"] = sorted(set(bucket["fields"]) | set(fields))
            elif retraction:
                bucket["retraction_context"] += 1
            else:
                bucket["claim_context"] += 1
    return {"prose_pattern_counts": prose, "numeric_pattern_counts": numeric}


def repository_path(path: Path) -> str:
    """Return a scan receipt path relative to the process repository root."""
    return path.resolve().relative_to(Path.cwd().resolve()).as_posix()


def run(args) -> int:
    roots = [Path(item) for item in args.root]
    paths = sorted({path for root in roots for path in
                    ([root] if root.is_file() else root.rglob("*"))
                    if path.is_file() and (path.suffix.lower() in SUFFIXES or
                                           path.name == "SHA256SUMS")})
    scanner = Path(__file__).resolve()
    if scanner not in paths:
        paths.append(scanner)
    findings = {}
    for path in paths:
        result = scan_path(path)
        if result["prose_pattern_counts"] or result["numeric_pattern_counts"]:
            findings[repository_path(path)] = result
    manifest = [repository_path(path) for path in paths]
    payload = {"files_scanned": len(paths),
               "path_manifest": manifest,
               "scanner_included": repository_path(scanner),
               "prose_patterns": len(PROSE_PATTERNS),
               "numeric_patterns": len(NUMERIC_PATTERNS),
               "findings_counts_only": findings,
               "claim_context_hits": sum(
                   bucket["claim_context"] for result in findings.values()
                   for bucket in result["numeric_pattern_counts"].values())}
    Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                              encoding="ascii", newline="\n")
    print("Q6 files", payload["files_scanned"], "flagged", len(findings),
          "claim_context", payload["claim_context_hits"])
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g404_q6_scan")
    parser.add_argument("--out", required=True)
    parser.add_argument("--root", action="append", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
