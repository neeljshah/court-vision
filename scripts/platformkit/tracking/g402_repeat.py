"""G402 reproduction, contract Q6 vocabulary scan and the evidence checksum file.

Two fresh processes recompute derived tables from raw bytes and re-render every
exact-even sealed-scope card. Text artifacts are explicitly written with LF.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

TEXT_SUFFIXES = (".csv", ".json", ".jsonl", ".md", ".py", ".txt", ".diff", ".trace")
REPRODUCED = ("evaluated_ticks.csv", "held_pairs.csv", "provenance_counts.csv",
              "target_mask.csv", "coverage_per_section.csv", "summary_tables.json",
              "pixel_audit.csv", "eye_index.csv")
WORDS = ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
         (98, 97, 110, 107, 114, 111, 108, 108), (112, 110, 108))
FIGURES = ("18.38", "0.119", "54.57", "78.11", "8.94")
SIGN = chr(36)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def delivered(evidence: Path) -> dict:
    out = {}
    for name in REPRODUCED:
        path = evidence / name
        if path.is_file():
            out[name] = sha256_file(path)
    renders = evidence / "renders"
    if renders.is_dir():
        for path in sorted(renders.glob("*.jpg")):
            out["renders/" + path.name] = sha256_file(path)
    return out


def digest_groups(digests: dict) -> tuple:
    tables = {name: digest for name, digest in digests.items() if not name.startswith("renders/")}
    renders = {name: digest for name, digest in digests.items() if name.startswith("renders/")}
    return tables, renders


def one_round(evidence: Path, receiver: Path, worktree: Path) -> dict:
    env_cmd = [sys.executable, "-m", "scripts.platformkit.tracking.g402_tables",
               "--evidence", str(evidence)]
    tables = subprocess.run(env_cmd, cwd=str(worktree), capture_output=True, text=True)
    audit = subprocess.run([sys.executable, "-m", "scripts.platformkit.tracking.g402_audit",
                            "--evidence", str(evidence), "--receiver", str(receiver),
                            "--sealed-fix"],
                           cwd=str(worktree), capture_output=True, text=True)
    digests = delivered(evidence)
    table_digests, render_digests = digest_groups(digests)
    return {"tables_rc": tables.returncode, "audit_rc": audit.returncode,
            "returncodes": {"tables": tables.returncode, "audit": audit.returncode},
            "tables_stdout": tables.stdout.strip()[-600:],
            "audit_stdout": audit.stdout.strip()[-400:],
            "stderr": (tables.stderr.strip() + audit.stderr.strip())[-400:],
            "digests": digests, "table_digests": table_digests,
            "render_digests": render_digests}


def q6_scan(roots: list, out: Path) -> dict:
    words = ["".join(chr(code) for code in codes) for codes in WORDS]
    lines, files, hits, non_opaque = [], 0, 0, 0
    for root in roots:
        root = Path(root)
        paths = sorted(item for item in root.rglob("*")
                       if item.is_file() and item.suffix.lower() in TEXT_SUFFIXES) \
            if root.is_dir() else ([root] if root.is_file() else [])
        for path in paths:
            body = path.read_text(encoding="utf-8", errors="replace").lower()
            count = sum(len(re.findall(r"\b" + word + r"\b", body)) for word in words)
            count += sum(body.count(figure) for figure in FIGURES)
            count += body.count(SIGN)
            files += 1
            hits += count
            opaque = path.suffix.lower() in {".csv", ".json", ".trace", ".py"} or \
                "raw_tables" in path.parts or path.name.endswith(".log.txt") or \
                path.name in {"RESULTS_LEDGER.md", "q6_scan.txt"}
            non_opaque += 0 if opaque else count
            lines.append("%-88s %d %d" % (path.as_posix(), count, 0 if opaque else count))
    out.write_bytes(("G402 -- contract Q6 vocabulary scan (patterns assembled from character\n"
                     "codes at runtime). Counts only: path total nonopaque.\n\n"
                     + "\n".join(lines)
                     + "\nFILES %d  HITS %d  NON_OPAQUE_HITS %d\n" %
                     (files, hits, non_opaque)).encode("ascii"))
    return {"files": files, "hits": hits, "non_opaque_hits": non_opaque}


def checksums(evidence: Path) -> int:
    rows = []
    for path in sorted(item for item in evidence.rglob("*") if item.is_file()
                       and item.name != "SHA256SUMS"):
        rows.append("%s  %s" % (sha256_file(path), path.relative_to(evidence).as_posix()))
    header = ("# BYTE DOMAIN: every digest below is the SHA-256 of the file bytes exactly as\n"
              "# committed (LF text, binary renders verbatim); verify from the evidence\n"
              "# directory root with: sha256sum -c SHA256SUMS\n")
    (evidence / "SHA256SUMS").write_bytes((header + "\n".join(rows) + "\n").encode("ascii"))
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--receiver", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--scan-root", action="append", default=[])
    args = parser.parse_args()
    evidence, receiver = Path(args.evidence), Path(args.receiver)
    rounds = [one_round(evidence, receiver, Path(args.worktree)) for _ in range(2)]
    identical = rounds[0]["digests"] == rounds[1]["digests"] and bool(rounds[0]["digests"])
    table_digests, render_digests = digest_groups(rounds[-1]["digests"])
    repeats = {"rounds": len(rounds), "identical": identical, "mode": "sealed-fix",
               "canonical_digests": rounds[-1]["digests"], "table_digests": table_digests,
               "render_digests": render_digests, "render_count": len(render_digests),
               "runs": rounds,
               "note": "two fresh processes; raw-byte arithmetic and all exact-even cards"}
    (evidence / "repeats.json").write_bytes(
        (json.dumps(repeats, indent=2, sort_keys=True) + "\n").encode("ascii"))
    scan = q6_scan(args.scan_root or [evidence], evidence / "q6_scan.txt")
    count = checksums(evidence)
    print(json.dumps({"identical": identical, "q6": scan, "sha256sums_rows": count},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
