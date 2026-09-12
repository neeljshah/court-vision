"""Schema-preserving receipts and field-aware vocabulary checks for G409."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable


def preserve_repeat_parent(parent: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    """Add G409 repeat fields while retaining the parent repeat schema verbatim."""
    if "identical" not in parent or "runs" not in parent:
        raise ValueError("parent-repeat-shape-absent")
    result = dict(parent)
    result.update(additions)
    return result


def _terms() -> tuple[str, ...]:
    codes = ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))
    return tuple("".join(chr(code) for code in word) for word in codes)


def _json_fields(value: Any, prefix: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _json_fields(child, prefix + "." + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _json_fields(child, "%s[%d]" % (prefix, index))
    elif isinstance(value, str):
        yield prefix, value


def _fields(path: Path) -> Iterable[tuple[str, str]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            for row_index, row in enumerate(csv.DictReader(handle), start=2):
                for name, value in row.items():
                    yield "row:%d:%s" % (row_index, name), value or ""
        return
    if path.suffix.lower() in {".json", ".jsonl"}:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines if line.strip()] if path.suffix.lower() == ".jsonl" else [json.loads("\n".join(lines))]
        for value in values:
            yield from _json_fields(value)
        return
    for line_index, value in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        yield "line:%d" % line_index, value


def field_scan(path: Path) -> dict[str, Any]:
    """Return field locations for forbidden prose without emitting matched text."""
    hits = []
    terms = _terms()
    for field, value in _fields(path):
        lowered = value.lower()
        for index, term in enumerate(terms):
            if re.search(r"\b" + re.escape(term) + r"\b", lowered):
                hits.append({"field": field, "pattern_index": index})
    return {"path": path.as_posix(), "count": len(hits), "hits": hits}
