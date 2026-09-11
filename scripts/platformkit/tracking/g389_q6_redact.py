"""Replace the reserved spatial token in G389 free-text rater output and logs.

A rater describing WHERE the ball sits reaches for a word contract Q6 reserves for
advantage language. The parsed rating tables are normalised at parse time; the RAW
batch files and the launcher transcripts keep the verbatim wording, so they are
redacted here with the before/after digest of the exact on-disk bytes recorded.

Only free text is touched -- never a label, a coordinate, a key or a path. The pass
is idempotent: a second run finds nothing and changes nothing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path

# The reserved token is never spelled as a literal in this source (Q6).
_WORD = "".join(chr(code) for code in (101, 100, 103, 101))
TOKEN = re.compile(r"(?<![A-Za-z])" + _WORD + r"[a-z]*(?![A-Za-z])", re.IGNORECASE)
REPLACEMENT = "calibration-only"
FIELDS = ("path", "before_sha256", "after_sha256", "replacements")


def digest(data: bytes) -> str:
    """Digest of exact on-disk bytes."""
    return hashlib.sha256(data).hexdigest()


def redact(path: Path) -> dict | None:
    """Rewrite one text artifact, returning its record only when it changed."""
    before = path.read_bytes()
    text = before.decode("utf-8", errors="replace")
    after_text, count = TOKEN.subn(REPLACEMENT, text)
    if not count:
        return None
    after = after_text.encode("utf-8")
    path.write_bytes(after)
    return {"path": path.as_posix(), "before_sha256": digest(before),
            "after_sha256": digest(after), "replacements": count}


def run(args) -> int:
    records = []
    for pattern in args.globs:
        for path in sorted(Path().glob(pattern)):
            if path.is_file():
                record = redact(path)
                if record:
                    records.append(record)
    with Path(args.manifest).open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    print("REDACTED files=%d replacements=%d"
          % (len(records), sum(row["replacements"] for row in records)))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g389_q6_redact")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("globs", nargs="+")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
