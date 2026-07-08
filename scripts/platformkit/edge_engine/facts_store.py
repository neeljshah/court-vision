"""edge_engine -- shared HTTP getter + append-only JSONL fact store (stdlib only).

Three consumers share this: injury_facts.py, news_facts.py, and cli.py. It owns the two
mechanical concerns those modules would otherwise duplicate:

  - http_json(url): the default network getter (urllib + browser UA + timeout). INJECTABLE --
    tests pass their own http_get and never touch the network (identical pattern to
    frontend/feed_espn._http_json).
  - append_new(path, rows, keyfn): read the existing JSONL, drop rows whose dedupe key is
    already present, and write the file back once atomically. Append-only + idempotent, so a
    re-run of the CLI adds 0 rows. ASCII-safe (ensure_ascii) for the cp1252 console.

No LLM, no secret, no prediction number -- this is plumbing. <=300 LOC. Test: test_facts_store.py.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:  # package import
    from scripts.platformkit.io_atomic import write_text_atomic  # type: ignore
except ImportError:  # direct-script / per-file-test fallback
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.io_atomic import write_text_atomic  # type: ignore

_REPO_ROOT = Path(__file__).resolve().parents[3]
FACTS_DIR = _REPO_ROOT / "data" / "cache" / "edge_engine"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 15

HttpGet = Callable[[str], Dict[str, Any]]


def utc_now_iso() -> str:
    """UTC capture stamp (seconds precision, tz-aware) -- the fetched_at vintage floor."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def http_json(url: str) -> Dict[str, Any]:
    """Default network getter (urllib + browser UA + timeout). Returns {} on any error.

    Never used in tests -- injury_facts/news_facts accept an injected http_get so the whole
    parse path runs hermetically off a recorded fixture.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec - GET only
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # pragma: no cover - network guard (offline / rate-limited / 5xx)
        return {}


def path_for(kind: str, sport: str) -> Path:
    """data/cache/edge_engine/<kind>_facts_<sport>.jsonl (e.g. injury_facts_nba.jsonl)."""
    return FACTS_DIR / f"{kind}_facts_{sport}.jsonl"


def read_rows(path: Path) -> List[Dict[str, Any]]:
    """Parse an existing JSONL store into a list of row dicts (empty if the file is absent)."""
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_new(path: Path, rows: Iterable[Dict[str, Any]],
               keyfn: Callable[[Dict[str, Any]], tuple]) -> int:
    """Append only rows whose dedupe key is not already stored. Returns the count added.

    Reads existing keys once, filters, then writes the whole file back in ONE atomic replace
    (O(n) per call, not O(n^2)). Idempotent: re-running with the same feed adds 0.
    """
    existing = read_rows(path)
    seen = {keyfn(r) for r in existing}
    fresh: List[Dict[str, Any]] = []
    for r in rows:
        k = keyfn(r)
        if k in seen:
            continue
        seen.add(k)
        fresh.append(r)
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    all_rows = existing + fresh
    body = "\n".join(json.dumps(r, ensure_ascii=True, sort_keys=True) for r in all_rows)
    write_text_atomic(path, body + "\n", encoding="ascii")
    return len(fresh)


def store_summary(kind: str, sport: str) -> Dict[str, Any]:
    """One freshness/count row for the CLI: total rows + newest fetched_at seen in the store."""
    rows = read_rows(path_for(kind, sport))
    latest: Optional[str] = None
    for r in rows:
        ts = r.get("fetched_at") or r.get("published")
        if ts and (latest is None or ts > latest):
            latest = ts
    return {"kind": kind, "sport": sport, "rows": len(rows), "latest": latest or "-"}
