"""Load settled in-game ticks once and reject cloned tick-store directories."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from scripts.platformkit.ingame_replay_scoreboard import _OUTCOME_KEYS, _normalise, _value


def _file_set(directory: Path) -> Tuple[Tuple[str, int], ...]:
    """Return a stable recursive file-name and size fingerprint."""
    files = []
    for path in directory.rglob("*"):
        if path.is_file():
            try:
                files.append((path.relative_to(directory).as_posix(), path.stat().st_size))
            except OSError:
                continue
    return tuple(sorted(files))


def assert_no_duplicate_stores(root: Path) -> None:
    """Raise when distinct non-empty subdirectories have identical file layouts."""
    if not root.is_dir():
        return
    seen: Dict[Tuple[Tuple[str, int], ...], Path] = {}
    for directory in sorted((path for path in root.rglob("*") if path.is_dir()),
                            key=lambda path: str(path).lower()):
        fingerprint = _file_set(directory)
        if not fingerprint:
            continue
        original = seen.get(fingerprint)
        if original is not None:
            raise ValueError("duplicate tick stores: %s and %s" % (original, directory))
        seen[fingerprint] = directory


def _record(raw: Dict[str, Any]) -> Dict[str, Any] | None:
    tick = _normalise(raw)
    if tick is None:
        return None
    return {**tick, "outcome": float(_value(raw, _OUTCOME_KEYS)),
            "state_summary": raw.get("state_summary"), "raw": raw}


def load_ticks_deduped(store_root: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Load normalized ticks, rejecting cloned stores and deduping their natural key."""
    assert_no_duplicate_stores(store_root)
    records: List[Dict[str, Any]] = []
    keys: Set[Tuple[str, str, float, float | None, float]] = set()
    stores: Set[str] = set()
    raw_count = 0
    for path in sorted(store_root.rglob("*.jsonl"), key=lambda item: str(item).lower()):
        try:
            store = path.parent.relative_to(store_root).as_posix() or "."
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(raw, dict) or (record := _record(raw)) is None:
                        continue
                    raw_count += 1
                    stores.add(store)
                    key = (record["game"], record["timestamp"], record["model_prob"],
                           record["market_prob"], record["outcome"])
                    if key not in keys:
                        keys.add(key)
                        records.append(record)
        except OSError:
            continue
    deduped_count = len(records)
    return records, {"raw_count": raw_count, "deduped_count": deduped_count,
                     "duplicate_pct": ((raw_count - deduped_count) * 100.0 / raw_count
                                       if raw_count else 0.0),
                     "stores_seen": sorted(stores)}
