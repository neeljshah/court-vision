"""Seed only S232 GLOB-reachable candidates into an isolated queue database."""
from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from scripts.platformkit.foundry import catalogue, results_db, seed_queue

CANONICAL_QUEUE = Path("data/cache/eval_gate/hypotheses.sqlite")
GLOB_REACHABLE = "GLOB-REACHABLE"
NEEDS_NAMED = "NEEDS-ONE-NAMED-LINE"
NOT_ENUMERABLE = "NOT-ENUMERABLE"
CLASSIFICATIONS = frozenset((GLOB_REACHABLE, NEEDS_NAMED, NOT_ENUMERABLE))


@dataclass(frozen=True)
class DryRun:
    """A no-write enumeration result for the declared queue manifest."""

    entries: tuple[catalogue.Entry, ...]
    hypotheses: int


def _relative(path: str) -> str:
    return Path(path).as_posix()


def _matches_glob(path: str) -> bool:
    return any(fnmatch.fnmatchcase(_relative(path), pattern) for pattern in catalogue.GLOBS)


def load_manifest(path: Path) -> tuple[dict, ...]:
    """Load and validate the S232 declared candidate list without opening a store."""
    payload = json.loads(path.read_text(encoding="ascii"))
    if payload.get("canonical_queue") != CANONICAL_QUEUE.as_posix():
        raise ValueError("manifest canonical_queue differs from the protected canonical path")
    stores = tuple(payload.get("stores", ()))
    identifiers = [str(row.get("id", "")) for row in stores]
    if not stores or len(identifiers) != len(set(identifiers)) or any(not value for value in identifiers):
        raise ValueError("manifest needs unique non-empty store ids")
    for row in stores:
        classification, path_value = row.get("classification"), row.get("path")
        if classification not in CLASSIFICATIONS or not isinstance(path_value, str):
            raise ValueError("manifest row has an invalid classification or path")
        matches = _matches_glob(path_value)
        if classification == GLOB_REACHABLE and not matches:
            raise ValueError("GLOB-REACHABLE row does not match catalogue.GLOBS: {0}".format(path_value))
        if classification == NEEDS_NAMED and matches:
            raise ValueError("NEEDS-ONE-NAMED-LINE row already matches catalogue.GLOBS: {0}".format(path_value))
    return stores


def reachable_entries(stores: Iterable[dict], root: Path = Path(".")) -> tuple[catalogue.Entry, ...]:
    """Return only present, manifest-declared GLOB paths; absent paths are named explicitly."""
    entries = []
    for row in stores:
        if row["classification"] != GLOB_REACHABLE:
            continue
        path = root / row["path"]
        if not path.is_file():
            raise FileNotFoundError("declared GLOB path is absent: {0}".format(path.as_posix()))
        entries.append(catalogue.Entry(path, catalogue.sport_of(path)))
    return tuple(entries)


def dry_run(manifest_path: Path, scratch_path: Path, root: Path = Path(".")) -> DryRun:
    """Count the closed grammar exactly, without creating or opening a SQLite database."""
    _assert_separate_scratch(scratch_path, root)
    entries = reachable_entries(load_manifest(manifest_path), root)
    count = sum(1 for _ in seed_queue.hypotheses(entries=entries))
    return DryRun(entries, count)


def enqueue_scratch(manifest_path: Path, scratch_path: Path, root: Path = Path(".")) -> DryRun:
    """Opt in to enqueueing the declared list at a non-canonical scratch database path."""
    result = dry_run(manifest_path, scratch_path, root)
    with results_db.ResultsDB(scratch_path) as db:
        hashes = [db.upsert_hypothesis(hypothesis, family=hypothesis.family,
                                      runtime_available=hypothesis.runtime_available)
                  for hypothesis in seed_queue.hypotheses(entries=result.entries)]
        db.enqueue(hashes, "T0")
        queued = len(hashes)
    if queued != result.hypotheses:
        raise AssertionError("queue count differs from grammar enumeration")
    return result


def _assert_separate_scratch(scratch_path: Path, root: Path) -> None:
    canonical = (root / CANONICAL_QUEUE).resolve()
    if scratch_path.resolve() == canonical:
        raise ValueError("scratch path must never be the canonical hypotheses.sqlite")


def main() -> None:
    """Print a dry-run count by default; `--apply` is isolated and explicit."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    action = enqueue_scratch if args.apply else dry_run
    result = action(args.manifest, args.scratch)
    print("mode={0} reachable_stores={1} hypotheses={2} scratch={3}".format(
        "apply" if args.apply else "dry-run", len(result.entries), result.hypotheses,
        args.scratch.as_posix()))


if __name__ == "__main__":
    main()
