"""G404 step 0 input hashing: every handoff, gate asset and sealed document.

Each manifest entry is `path::role::expected`, where `expected` is either a full
64-hex SHA-256 the row must reproduce or `-` when no sealed digest exists. A
missing path is recorded as ABSENT, never substituted and never silently skipped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

FIELDS = ("role", "path", "accessibility", "bytes", "sha256", "sha256_lf",
          "expected_sha256", "match")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_tree(path: Path) -> tuple[str, int]:
    """Digest a directory as the sorted list of member name plus member digest."""
    parts, total = [], 0
    for item in sorted(path.rglob("*")):
        if item.is_file():
            total += item.stat().st_size
            parts.append(item.relative_to(path).as_posix() + "  " + sha256_file(item))
    return hashlib.sha256(("\n".join(parts) + "\n").encode("ascii")).hexdigest(), total


def describe(entry: str, accessibility: str) -> dict[str, str]:
    """One manifest row; a checkout-newline difference is named, never hidden."""
    raw_path, role, expected = entry.split("::", 2)
    path = Path(raw_path)
    if not path.exists():
        return {"role": role, "path": raw_path, "accessibility": "ABSENT", "bytes": "0",
                "sha256": "", "sha256_lf": "", "expected_sha256": expected,
                "match": "ABSENT"}
    if path.is_dir():
        digest, size = sha256_tree(path)
        normalized = ""
    else:
        digest, size = sha256_file(path), path.stat().st_size
        normalized = hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if expected == "-":
        match = "NO_SEALED_DIGEST"
    elif digest == expected:
        match = "MATCH"
    elif normalized and normalized == expected:
        match = "MATCH_AFTER_LF_NORMALIZATION"
    else:
        match = "MISMATCH"
    return {"role": role, "path": raw_path, "accessibility": accessibility,
            "bytes": str(size), "sha256": digest, "sha256_lf": normalized,
            "expected_sha256": expected, "match": match}


def run(args) -> int:
    rows = [describe(entry, args.accessibility) for entry in args.entry]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write = out.exists() and args.append
    with out.open("a" if write else "w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
        if not write:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: str(value).encode("ascii", "replace").decode("ascii")
                             for key, value in row.items()})
    bad = [row for row in rows if row["match"] in ("MISMATCH", "ABSENT")]
    for row in rows:
        print(row["match"], row["role"], row["sha256"][:16])
    return 1 if bad else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g404_inputs")
    parser.add_argument("--out", required=True)
    parser.add_argument("--accessibility", required=True)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--entry", action="append", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
