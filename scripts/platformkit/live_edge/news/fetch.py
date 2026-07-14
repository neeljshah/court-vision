"""scripts.platformkit.live_edge.news.fetch -- A2 raw capture (point-in-time discipline).

Captures the two sources probe.py found REACHABLE (ESPN NBA injuries + news
JSON APIs) to data/omni/live_edge/news/raw/<date>.jsonl. Every row is stamped
with report_ts = CAPTURE time (never the article's own published/date field)
-- that is the whole point of the knowability framing (L-S2): a scraper
that back-dates its rows to event time silently leaks the future.

Reuses odds_provider.transport.resilient_get_json (import only, never
edited) so this inherits the shared stealth-escalation + politeness/backoff
behavior for free.

<=300 LOC. ASCII stdout. Per-file test not required for this module alone
(covered indirectly via parser golden-set test); a __main__ smoke run is the
runnable check per the ponytail non-trivial-logic rule.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.io_atomic import append_jsonl_atomic
from scripts.platformkit.odds_provider.transport import resilient_get_json

_RAW_DIR = Path("data/omni/live_edge/news/raw")

_ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
_ESPN_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raw_path(base_dir=None, *, date: str | None = None) -> Path:
    d = date or datetime.now(timezone.utc).date().isoformat()
    return (Path(base_dir) if base_dir is not None else _RAW_DIR) / f"{d}.jsonl"


def _injury_texts(payload: Dict[str, Any], report_ts: str) -> List[Dict[str, Any]]:
    """One raw text item per player-injury entry (the free-text 'shortComment'/
    'longComment' -- ESPN's own structured status field is NOT copied here on
    purpose: this raw layer feeds the free-text parser, which must work the
    same way it would on an RSS/tweet item with no structured field at all)."""
    items = []
    for team in payload.get("injuries", []) or []:
        for entry in team.get("injuries", []) or []:
            athlete = entry.get("athlete", {}) or {}
            text = str(entry.get("shortComment") or entry.get("longComment") or "").strip()
            if not text:
                continue
            items.append({
                "raw_text": text,
                "player_name": str(athlete.get("displayName", "") or ""),
                "report_ts": report_ts,
                "source": "espn_nba_injuries",
            })
    return items


def _news_texts(payload: Dict[str, Any], report_ts: str) -> List[Dict[str, Any]]:
    items = []
    for a in payload.get("articles", []) or []:
        headline = str(a.get("headline", "") or "").strip()
        if not headline:
            continue
        items.append({
            "raw_text": headline,
            "player_name": "",  # unstructured lead -- parser.extract_player_name_raw handles it
            "report_ts": report_ts,
            "source": "espn_nba_news",
        })
    return items


def capture_once(*, base_dir=None) -> Dict[str, Any]:
    """One capture tick: fetch both reachable sources, append raw items with a
    CAPTURE-time report_ts. Never raises -- one source failing does not sink
    the other (mirrors injury_daemon.tick's per-source isolation)."""
    report_ts = _now_iso()
    path = _raw_path(base_dir)
    n_written = 0
    errors: Dict[str, str] = {}
    for name, url, parse_fn in (
        ("injuries", _ESPN_INJURIES_URL, _injury_texts),
        ("news", _ESPN_NEWS_URL, _news_texts),
    ):
        try:
            payload = resilient_get_json(url, timeout=15.0)
            items = parse_fn(payload, report_ts)
            for item in items:
                append_jsonl_atomic(path, item)
            n_written += len(items)
        except Exception as exc:  # noqa: BLE001 -- one feed failing must not sink the other
            errors[name] = f"{type(exc).__name__}: {exc}"
    return {"report_ts": report_ts, "n_written": n_written, "path": str(path), "errors": errors}


if __name__ == "__main__":
    result = capture_once()
    print(json.dumps(result))
