"""scripts.platformkit.data_frontier.statsbomb_open_full -- resumable full-repo pull
of StatsBomb open-data event files (frontier census rank 1, KEYLESS_CONFIRMED).

On-disk baseline: data/cache/statsbomb/events/<match_id>.json, 400 files (the
existing sample pulled by domains/soccer/ingest_statsbomb_events.py). The public
repo publishes 4,235. This module extends the SAME layout/cache dir -- it does not
introduce a new directory -- and is purely additive: existing files are never
re-fetched or overwritten (skip-if-cached), so it composes safely with the sample
puller and can be re-run/interrupted freely.

SOURCE: github.com/statsbomb/open-data (public, keyless, no rate limit stated;
we self-impose 1 req/s per the census's own politeness convention). One git-tree
API call lists every event-file id; each missing id is then fetched from
raw.githubusercontent.com.

CLI: python -m scripts.platformkit.data_frontier.statsbomb_open_full [--max-seconds S] [--limit N] [--delay 1.0]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

from scripts.platformkit.data_frontier._politeness import (
    atomic_write_bytes, atomic_write_text, log_line,
)

_REPO = Path(__file__).resolve().parents[3]
_CACHE = _REPO / "data" / "cache" / "statsbomb"
_EVENTS_DIR = _CACHE / "events"
_TREE_CACHE = _CACHE / "_tree_full.json"
_PROGRESS_FP = _CACHE / "full_pull_progress.json"
_LOG_FP = _REPO / "data" / "cache" / "logs" / "statsbomb_full_pull.log"

_TREE_URL = "https://api.github.com/repos/statsbomb/open-data/git/trees/master?recursive=1"
_RAW_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master"
_HDR = {"User-Agent": "Mozilla/5.0 (research; bounded polite pull, data-frontier lane)"}
_DELAY_S = 1.0
_MAX_CONSECUTIVE_FAILURES = 5


def fetch_event_id_list(fetcher=None) -> List[str]:
    """One API call -> every published data/events/<id>.json id (cached to disk so
    re-runs never re-hit the API, per GitHub's unauthenticated rate limit)."""
    if _TREE_CACHE.exists():
        tree = json.loads(_TREE_CACHE.read_text(encoding="utf-8"))
    else:
        get = fetcher or requests.get
        r = get(_TREE_URL, headers=_HDR, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"git tree fetch failed: HTTP {r.status_code}")
        tree = r.json()
        atomic_write_text(_TREE_CACHE, json.dumps(tree))
    ids = []
    for item in tree.get("tree", []):
        path = item.get("path", "")
        if path.startswith("data/events/") and path.endswith(".json"):
            ids.append(path[len("data/events/"):-len(".json")])
    return sorted(ids, key=lambda s: (len(s), s))


def already_cached() -> set:
    if not _EVENTS_DIR.exists():
        return set()
    return {p.stem for p in _EVENTS_DIR.glob("*.json")}


def _fetch_one(match_id: str, fetcher=None, timeout: float = 60.0):
    get = fetcher or requests.get
    url = f"{_RAW_BASE}/data/events/{match_id}.json"
    return get(url, headers=_HDR, timeout=timeout)


def pull(
    *,
    max_seconds: Optional[float] = None,
    limit: Optional[int] = None,
    delay_s: float = _DELAY_S,
    fetcher=None,
    events_dir: Path = _EVENTS_DIR,
    log_path: Path = _LOG_FP,
    progress_path: Path = _PROGRESS_FP,
) -> Dict[str, object]:
    """Resumable: skips any match_id already on disk, checkpoints progress every
    25 files, stops on wall-clock budget / --limit / _MAX_CONSECUTIVE_FAILURES."""
    all_ids = fetch_event_id_list(fetcher=fetcher)
    existing = {p.stem for p in events_dir.glob("*.json")} if events_dir.exists() else set()
    remaining = [i for i in all_ids if i not in existing]
    if limit is not None:
        remaining = remaining[:limit]

    fetched: List[str] = []
    failed: List[str] = []
    consecutive_failures = 0
    stopped_reason = None
    t0 = time.monotonic()
    log_line(log_path, f"START total_published={len(all_ids)} already_cached={len(existing)} "
                        f"to_fetch={len(remaining)}")

    for n, match_id in enumerate(remaining, start=1):
        if max_seconds is not None and (time.monotonic() - t0) > max_seconds:
            stopped_reason = "max_seconds"
            break
        try:
            r = _fetch_one(match_id, fetcher=fetcher)
        except requests.RequestException as exc:
            log_line(log_path, f"FAIL {match_id} exception={exc}")
            failed.append(match_id)
            consecutive_failures += 1
        else:
            if r.status_code == 200 and len(r.content) > 10:
                atomic_write_bytes(events_dir / f"{match_id}.json", r.content)
                fetched.append(match_id)
                consecutive_failures = 0
            else:
                log_line(log_path, f"FAIL {match_id} HTTP {r.status_code}")
                failed.append(match_id)
                consecutive_failures += 1

        if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            stopped_reason = "consecutive_failures"
            log_line(log_path, f"STOP consecutive_failures={consecutive_failures}")
            break

        if n % 25 == 0 or n == len(remaining):
            atomic_write_text(progress_path, json.dumps({
                "total_published": len(all_ids), "fetched_this_run": len(fetched),
                "failed_this_run": len(failed), "landed_of_remaining": n,
                "remaining_of_run": len(remaining),
            }))
            log_line(log_path, f"PROGRESS {n}/{len(remaining)} fetched={len(fetched)} failed={len(failed)}")

        if n != len(remaining):
            time.sleep(delay_s)

    now_cached = len(existing) + len(fetched)
    result = {
        "total_published": len(all_ids),
        "already_cached_before_run": len(existing),
        "fetched_this_run": len(fetched),
        "failed_this_run": len(failed),
        "now_cached": now_cached,
        "coverage_frac": round(now_cached / len(all_ids), 4) if all_ids else 0.0,
        "stopped_reason": stopped_reason,
    }
    atomic_write_text(progress_path, json.dumps(result))
    log_line(log_path, f"DONE {json.dumps(result)}")
    return result


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Resumable StatsBomb open-data full-repo event pull.")
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--delay", type=float, default=_DELAY_S)
    a = ap.parse_args(argv)
    res = pull(max_seconds=a.max_seconds, limit=a.limit, delay_s=a.delay)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["fetch_event_id_list", "already_cached", "pull", "main"]
