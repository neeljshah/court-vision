"""Deterministic, non-judging G389 task allocation and restart helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


CHECKPOINTS = (30, 120, 240, 360, 506)


def pending_keys(manifest: Iterable[dict[str, str]], completed: Iterable[str]) -> list[dict[str, str]]:
    """Subtract completed stable keys once, rejecting duplicate manifest identities."""
    completed_set = set(completed)
    rows = list(manifest)
    keys = [row["frame_key"] for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate-frame-key manifest")
    return [row for row in rows if row["frame_key"] not in completed_set]


def _sort_key(row: dict[str, str]) -> tuple[str, str, str, int, str]:
    try:
        frame_index = int(row.get("frame_index", "0"))
    except ValueError:
        frame_index = 0
    return (row.get("split", ""), row.get("game", row.get("source", "")),
            row.get("section", ""), frame_index, row["frame_key"])


def bins_and_permutation(rows: Iterable[dict[str, str]], bins: int = 30) -> tuple[list[list[dict[str, str]]], list[dict[str, str]]]:
    """Create contiguous quantile bins then a round-robin order across those bins."""
    ordered = sorted(rows, key=_sort_key)
    if bins <= 0 or len(ordered) < bins:
        raise ValueError("invalid-bin-count")
    groups = [ordered[(index * len(ordered)) // bins:((index + 1) * len(ordered)) // bins]
              for index in range(bins)]
    permutation: list[dict[str, str]] = []
    depth = 0
    while any(depth < len(group) for group in groups):
        for group in groups:
            if depth < len(group):
                permutation.append(group[depth])
        depth += 1
    return groups, permutation


def allocation(rows: Iterable[dict[str, str]], completed: Iterable[str], raters: tuple[str, str]) -> list[dict[str, str]]:
    """Assign only uncompleted keys to disjoint rater lanes in frozen order."""
    if len(set(raters)) != 2:
        raise ValueError("two-distinct-raters-required")
    fresh = pending_keys(rows, completed)
    _, order = bins_and_permutation(fresh)
    return [{**row, "ordinal": str(index + 1), "allocation": raters[index % 2]}
            for index, row in enumerate(order)]


def completion_status(completed: Iterable[str], total: int = 506) -> str:
    """Report PARTIAL until the fixed queue itself, not a box quota, is exhausted."""
    distinct = set(completed)
    if len(distinct) > total:
        raise ValueError("completed-key-count-exceeds-fixed-queue")
    return "DONE" if len(distinct) == total else "PARTIAL"


def append_completed(path: Path, rows: Iterable[dict[str, str]]) -> None:
    """Atomically add newline-delimited decisions only when keys are new and unique."""
    incoming = list(rows)
    keys = [row["frame_key"] for row in incoming]
    old = set()
    prior = ""
    if Path(path).exists():
        prior = Path(path).read_text(encoding="utf-8")
        old = {line.split("\t", 1)[0] for line in prior.splitlines() if line}
    if len(keys) != len(set(keys)) or old.intersection(keys):
        raise ValueError("duplicate-decision-key")
    temporary = Path(path).with_suffix(Path(path).suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(prior)
        for row in incoming:
            handle.write(row["frame_key"] + "\t" + row.get("label", "") + "\n")
    temporary.replace(path)
