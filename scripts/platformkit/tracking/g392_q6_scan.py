"""G392 vocabulary scan over every text artifact, using shared character-built patterns."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking import g334_seal

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".mp4", ".pyc"}


def collect(roots: list[Path]) -> list[Path]:
    """Enumerate every text artifact under the supplied roots, one file at a time."""
    paths = []
    for root in roots:
        if root.is_file():
            paths.append(root)
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() not in SKIP_SUFFIXES:
                paths.append(path)
    return paths


def is_opaque(line: str, matched: str) -> bool:
    """A hit is opaque only when every occurrence sits inside a longer token.

    Digest, path and column identifiers quoted verbatim are exempt under the Q6
    NOTE; a token standing alone in prose is not.
    """
    start, occurrences = line.find(matched), []
    while start >= 0:
        before = line[start - 1] if start else ""
        after = line[start + len(matched):start + len(matched) + 1]
        # ":" joins a clock field to its neighbours; the shared BARE_RE already
        # excludes digits and "." on both sides, so this widens nothing else.
        occurrences.append(bool(before.isalnum() or after.isalnum()
                                or before == ":" or after == ":"))
        start = line.find(matched, start + 1)
    return bool(occurrences) and all(occurrences)


def scan(paths: list[Path]) -> list[dict[str, object]]:
    findings = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.replace("\r\n", "\n").split("\n")
        for number, kind, matched in g334_seal.scan_text(text):
            line = lines[number - 1] if number - 1 < len(lines) else ""
            findings.append({"path": path.as_posix(), "line": number, "kind": kind,
                             "match": matched, "context": line.strip()[:160],
                             "opaque": is_opaque(line, matched)})
    return findings


def redact(path: Path, matched: str, replacement: str = "calibration-only") -> dict[str, str]:
    """Replace one geometric use of a prohibited token and disclose both digests."""
    original = path.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8", errors="replace").replace(matched, replacement)
    path.write_text(text, encoding="utf-8", newline="")
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": path.as_posix(), "token": matched, "before": before, "after": after}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--redact", type=Path, nargs="*", default=[])
    parser.add_argument("--token", default="")
    args = parser.parse_args()
    redactions = [redact(path, args.token) for path in args.redact if args.token]
    for row in redactions:
        print("G392_REDACT %s %s -> %s" % (row["path"], row["before"], row["after"]))
    # The report quotes every match verbatim, so scanning it would echo itself.
    paths = [path for path in collect(args.roots) if path.resolve() != args.out.resolve()]
    findings = scan(paths)
    non_opaque = [row for row in findings if not row["opaque"]]
    payload = {"files": len(paths), "hits": len(findings), "non_opaque": len(non_opaque),
               "redactions": redactions,
               "findings": findings}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    for row in non_opaque:
        print("G392_SCAN %s:%d %s %r | %s" % (row["path"], row["line"], row["kind"],
                                              row["match"], row["context"]))
    print("G392_SCAN_SUMMARY files=%d hits=%d non_opaque=%d" % (len(paths), len(findings), len(non_opaque)))
    return 1 if non_opaque else 0


if __name__ == "__main__":
    raise SystemExit(main())
