"""Variant-aware staged-video selection for the tracking daemon."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path

from scripts.platformkit.tracking.source_timebase import probe_source


_RESOLUTION_SUFFIX = re.compile(r"_(?:[1-9][0-9]{2,3})p$")


def parse_name(path: Path) -> tuple[str | None, str | None]:
    """Split a staged ``<sport>__<game_id>.mp4`` filename."""
    sport, separator, game_id = path.stem.partition("__")
    if not separator or not sport or not game_id:
        return None, None
    return sport, game_id


def _variant_root(game_id: str) -> str:
    return _RESOLUTION_SUFFIX.sub("", game_id)


def _staged_groups(stage: Path) -> dict[tuple[str, str], list[Path]]:
    """Build explicit group keys, retaining singleton source identities."""
    candidates: dict[tuple[str, str], list[Path]] = {}
    identities: dict[Path, tuple[str, str]] = {}
    for path in sorted(stage.glob("*.mp4")):
        sport, game_id = parse_name(path)
        if sport and game_id:
            candidates.setdefault((sport, _variant_root(game_id)), []).append(path)
            identities[path] = (sport, game_id)
    groups: dict[tuple[str, str], list[Path]] = {}
    for root, paths in candidates.items():
        if len(paths) > 1:
            groups[root] = paths
        else:
            groups[identities[paths[0]]] = paths
    return groups


def sibling_paths(stage: Path, sport: str, game_id: str) -> list[Path]:
    """Return the explicit staged group for an enqueued source identity."""
    return _staged_groups(stage).get((sport, game_id), [])


def _active_roots(active: dict) -> set[tuple[str, str]]:
    roots: set[tuple[str, str]] = set()
    for name in active:
        sport, game_id = parse_name(Path(name))
        if sport and game_id:
            roots.add((sport, _variant_root(game_id)))
    return roots


def _ranking(source: dict[str, float | int | None], path: Path) -> tuple:
    duration = source.get("source_duration")
    height = source.get("source_height")
    known_duration = isinstance(duration, (float, int)) and duration >= 0
    return (known_duration, duration if known_duration else -1,
            height if isinstance(height, int) else -1, path.name)


def claimable(stage: Path, active: dict, minimum_bytes: int, quarantine: Path,
              retainer: Callable[..., bool], record: Callable[[dict], None],
              corrupt_entry: Callable[[str, str, int, bool], dict]) -> list[tuple[Path, str, str]]:
    """Select one valid longest source per explicit staged variant group."""
    ready: list[tuple[Path, str, str]] = []
    active_roots = _active_roots(active)
    for (sport, game_id), paths in _staged_groups(stage).items():
        root = (sport, _variant_root(game_id))
        if any(path.name in active for path in paths) or (len(paths) > 1 and root in active_roots):
            continue
        valid: list[Path] = []
        for path in paths:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size >= minimum_bytes:
                valid.append(path)
                continue
            print("%s is %d bytes -- not a video, quarantining" % (game_id, size), flush=True)
            retained = retainer(path, quarantine, lambda message: print(message, flush=True))
            record(corrupt_entry(game_id, sport, size, retained))
        if valid:
            sources = {path: probe_source(path) for path in valid}
            ready.append((max(valid, key=lambda path: _ranking(sources[path], path)), sport, game_id))
    return ready


def reap_orphans(runner: Callable[..., object], killer: Callable[[int, int], None]) -> int:
    """Kill unowned adapter/run-clip children after a daemon crash."""
    try:
        listing = runner(["ps", "-eo", "ppid,pid,args"], capture_output=True,
                         text=True, timeout=60).stdout
    except (OSError, Exception):
        return 0
    killed = 0
    for line in listing.splitlines():
        fields = line.split(None, 2)
        if len(fields) < 3 or fields[0] != "1":
            continue
        if "adapter_run" not in fields[2] and "run_clip" not in fields[2]:
            continue
        try:
            killer(int(fields[1]), 9)
            killed += 1
        except (OSError, ValueError):
            pass
    return killed
