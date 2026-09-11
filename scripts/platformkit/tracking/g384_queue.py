"""G384's read-only queue reconciliation and deterministic allocation helper."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Iterable

from scripts.platformkit.tracking.g363_ball_coverage import read_csv, write_csv

QUEUE_FIELDS = ("ordinal", "frame_key", "split", "source", "why", "allocation")


def _unique(rows: list[dict], name: str) -> dict[str, dict]:
    """Index a keyed table, refusing duplicate identities rather than guessing."""
    indexed = {row["frame_key"]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("duplicate-frame-key " + name)
    return indexed


def cache_keys(paths: Iterable[Path], known: set[str]) -> set[str]:
    """Read cache files one at a time; never copy or materialize a cache store."""
    completed: set[str] = set()
    prefixes = {key[:12]: key for key in known}
    for path in paths:
        with Path(path).open(encoding="utf-8", errors="replace", newline="") as handle:
            first = handle.readline()
            if first.startswith("frame_key,"):
                handle.seek(0)
                for row in csv.DictReader(handle):
                    if row.get("frame_key") in known:
                        completed.add(row["frame_key"])
                continue
            for line in [first, *handle]:
                key = prefixes.get(line.split(",", 1)[0].strip())
                if key:
                    completed.add(key)
    return completed


def reconcile(manifest: list[dict], reference: list[dict], adjudications: list[dict],
              queue: list[dict]) -> dict:
    """Reconcile the whole G373 queue against settled tables and the manifest."""
    manifests = _unique(manifest, "manifest")
    refs = _unique(reference, "reference")
    adjs = _unique(adjudications, "adjudications")
    queued = _unique(queue, "queue")
    absent = sorted(set(queued) - set(manifests))
    settled_reference = sorted(set(queued) & set(refs))
    settled_adjudication = sorted(set(queued) & set(adjs))
    if absent or settled_reference or settled_adjudication:
        raise ValueError("queue-reconciliation-failed absent=%d reference=%d adjudication=%d" %
                         (len(absent), len(settled_reference), len(settled_adjudication)))
    splits = Counter(manifests[key]["split"] for key in queued)
    return {"queued": len(queued), "development": splits["development"],
            "heldout": splits["heldout"], "manifest": len(manifests),
            "reference": len(refs), "adjudications": len(adjs), "unresolved": len(queued)}


def interleaved_queue(manifest: list[dict], queue: list[dict], already_rated: set[str]) -> list[dict]:
    """Stable split-interleaving, excluding a key previously completed for this pass."""
    manifests, queued = _unique(manifest, "manifest"), _unique(queue, "queue")
    pools = {split: sorted(key for key in queued if manifests[key]["split"] == split
                           and key not in already_rated)
             for split in ("development", "heldout")}
    rows: list[dict] = []
    while pools["development"] or pools["heldout"]:
        for split in ("development", "heldout"):
            if not pools[split]:
                continue
            key = pools[split].pop(0)
            item = manifests[key]
            rows.append({"ordinal": len(rows) + 1, "frame_key": key, "split": split,
                         "source": item.get("source", ""), "why": queued[key].get("why", ""),
                         "allocation": "PENDING"})
    return rows


def run(args) -> int:
    """Write only an additive allocation file from landed G373 artifacts."""
    manifest, reference, adjudications, queue = (read_csv(Path(value)) for value in
        (args.manifest, args.reference, args.adjudications, args.queue))
    summary = reconcile(manifest, reference, adjudications, queue)
    known = {row["frame_key"] for row in manifest}
    rated = cache_keys((Path(path) for path in args.rater_cache), known)
    rows = interleaved_queue(manifest, queue, rated)
    write_csv(Path(args.out), QUEUE_FIELDS, rows)
    print("QUEUE unresolved=%d allocated=%d cache_completed=%d" %
          (summary["unresolved"], len(rows), len(rated)))
    return 0
