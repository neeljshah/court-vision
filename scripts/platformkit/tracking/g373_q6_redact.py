"""Redact the prohibited spatial token from G373 free-text rater notes only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path


NOTE_NAMES = {"note", "notes", "reason", "comment", "comments", "free_text"}
_WORD = "".join(chr(c) for c in (101, 100, 103, 101))  # the reserved token, never spelled in source (Q6)
TOKEN = re.compile(r"\b" + _WORD + r"\b", re.IGNORECASE)
REPLACEMENT = "border"
MANIFEST_FIELDS = ("path", "line", "column", "before_sha256", "after_sha256", "replacements")


def sha256(data: bytes) -> str:
    """Return the digest of exact on-disk bytes."""
    return hashlib.sha256(data).hexdigest()


def split_line(line: bytes, delimiter: bytes, column: int) -> tuple[bytes, bytes, bytes]:
    """Split one unquoted delimited line at its requested zero-based column."""
    start = 0
    for _ in range(column):
        found = line.find(delimiter, start)
        if found < 0:
            raise ValueError("row has fewer columns than its header")
        start = found + 1
    end = line.find(delimiter, start)
    if end < 0:
        return line[:start], line[start:], b""
    return line[:start], line[start:end], line[end:]


def file_shape(path: Path, lines: list[bytes]) -> tuple[int, str, int] | None:
    """Return note-column metadata, or None when a file has no eligible note field."""
    if path.suffix == ".txt" and path.parent.name == "raters_v2":
        return (-1, "note", 0)
    if path.suffix != ".csv" or not lines:
        return None
    header = lines[0].rstrip(b"\r\n").decode("ascii")
    names = header.split(",")
    matches = [index for index, name in enumerate(names) if name.lower() in NOTE_NAMES]
    if len(matches) != 1:
        return None
    return (matches[0], names[matches[0]], len(names))


def redact_file(path: Path, root: Path) -> list[dict]:
    """Edit only the declared note field, returning manifest records for changed rows."""
    before = path.read_bytes()
    lines = before.splitlines(keepends=True)
    shape = file_shape(path, lines)
    if shape is None:
        return []
    column, column_name, expected = shape
    changed: list[tuple[int, int]] = []
    output = list(lines)
    first = 0 if path.suffix == ".txt" else 1
    for index in range(first, len(lines)):
        raw = lines[index]
        content = raw.rstrip(b"\r\n")
        ending = raw[len(content):]
        if not content:
            continue
        if column >= 0 and content.count(b",") != expected - 1:
            raise ValueError(f"{path}: line {index + 1} delimiter count changed or unsupported")
        if column < 0:
            prefix, separator, note = content.rpartition(b",")
            if not separator:
                raise ValueError(f"{path}: line {index + 1} has no note delimiter")
            prefix += separator
            suffix = b""
        else:
            prefix, note, suffix = split_line(content, b",", column)
        text = note.decode("utf-8")
        redacted, count = TOKEN.subn(REPLACEMENT, text)
        if count:
            output[index] = prefix + redacted.encode("utf-8") + suffix + ending
            changed.append((index + 1, count))
    if not changed:
        return []
    after = b"".join(output)
    if len(lines) != len(after.splitlines(keepends=True)):
        raise AssertionError("redaction changed row count")
    path.write_bytes(after)
    relative = path.relative_to(root.parent).as_posix()
    return [{"path": relative, "line": line, "column": column_name,
             "before_sha256": sha256(before), "after_sha256": sha256(after),
             "replacements": count} for line, count in changed]


def redact(evidence: Path, manifest: Path) -> list[dict]:
    """Redact every eligible batch/derived note field and write a stable digest manifest."""
    rows: list[dict] = []
    for path in sorted(item for item in evidence.rglob("*") if item.is_file()):
        if path == manifest or path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            continue
        rows.extend(redact_file(path, evidence))
    if rows:
        with manifest.open("w", encoding="ascii", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="g373_q6_redact")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--manifest", default="")
    args = parser.parse_args(argv)
    evidence = Path(args.evidence)
    manifest = Path(args.manifest) if args.manifest else evidence / "q6_redaction_manifest.csv"
    rows = redact(evidence, manifest)
    print("Q6-REDACT rows=" + str(len(rows)) + " replacements=" + str(sum(int(r["replacements"]) for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
