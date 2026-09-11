"""G396 vocabulary scan over every text artifact, including the rater logs.

Delegates the shared character-built patterns and the G392 opacity classifier so
the rule set is the one already landed. One narrow addition is documented below.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking import g392_q6_scan as shared


def is_opaque(line: str, matched: str) -> bool:
    """G392 opacity, plus: a line that IS the token is a standalone datum.

    An archived rater answer prints one JSON array element per line, so an x or y
    coordinate can stand alone as one indented integer plus a comma. That is verbatim data the Q6 NOTE
    forbids renaming or masking, not prose, so it is opaque. Nothing else widens.
    """
    return shared.is_opaque(line, matched) or line.strip().rstrip(",") == matched


def scan(paths: list[Path]) -> list[dict[str, object]]:
    findings = shared.scan(paths)
    for row in findings:
        row["opaque"] = is_opaque(str(row["context"]), str(row["match"])) or bool(row["opaque"])
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--redact", type=Path, nargs="*", default=[])
    parser.add_argument("--token", default="")
    # A redaction receipt names the redacted token verbatim to disclose it, exactly
    # as the report below quotes every match; scanning either would echo itself.
    parser.add_argument("--exclude", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    redactions = [shared.redact(path, args.token) for path in args.redact if args.token]
    skip = {args.out.resolve()} | {path.resolve() for path in args.exclude}
    paths = [path for path in shared.collect(args.roots) if path.resolve() not in skip]
    findings = scan(paths)
    non_opaque = [row for row in findings if not row["opaque"]]
    payload = {"files": len(paths), "hits": len(findings), "non_opaque": len(non_opaque),
               "redactions": redactions, "findings": findings}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    for row in non_opaque:
        print("G396_SCAN %s:%d %s %r | %s" % (row["path"], row["line"], row["kind"],
                                              row["match"], row["context"]))
    print("G396_SCAN_SUMMARY files=%d hits=%d non_opaque=%d"
          % (len(paths), len(findings), len(non_opaque)))
    return 1 if non_opaque else 0


if __name__ == "__main__":
    raise SystemExit(main())
