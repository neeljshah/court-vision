"""edge_engine -- ESPN news feed -> headline fact rows with entities from ESPN's OWN categories.

ESPN tags every article with a structured `categories[]` array (type in {league, topic, team,
athlete, ...}, each with a `description`). So player/team entities come from that structured
field by RULE -- no free-text NLP. That is the ponytail win: the market's own tagging is the
extractor. No LLM, no secret, no network in tests.

  GET https://site.api.espn.com/apis/site/v2/sports/<path>/news
  payload.articles[] -> {headline, published (ISO), categories[], links.web.href, type}

Fact row (append-only JSONL, dedupe key = headline|published):
  {sport, source, headline, published, categories[], players[], teams[], url}

OPTIONAL LLM enricher: OFF by default (model-independence is a binding rule). When CV_EDGE_LLM=1
AND an Anthropic key is present it delegates to the extract.py LLM-in-one-box seam to pull extra
entities from the free-text headline; the seam is a STUB today so it returns [] and the rule path
stands alone. When off, no `llm_notes` key is added -- the row schema is identical either way.

Stdlib only. <=300 LOC. Per-file test: test_news_facts.py.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:  # package import
    from scripts.platformkit.edge_engine.facts_store import (  # type: ignore
        HttpGet, append_new, http_json, path_for,
    )
except ImportError:  # direct-script / per-file-test fallback
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.edge_engine.facts_store import (  # type: ignore
        HttpGet, append_new, http_json, path_for,
    )

_SOURCE = "espn_news"
_BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/news"

_SPORT_PATHS: Dict[str, str] = {
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
}


def _entities(categories: List[Dict[str, Any]], want: str) -> List[str]:
    """Deduped, order-preserving descriptions of categories whose type == want."""
    out: List[str] = []
    for c in categories or []:
        if c.get("type") == want:
            desc = c.get("description")
            if desc and desc not in out:
                out.append(str(desc))
    return out


def _llm_enabled() -> bool:
    """OFF unless explicitly opted in AND a key is present (model-independence default)."""
    return os.environ.get("CV_EDGE_LLM") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _maybe_llm_enrich(headline: str, published: str, sport: str) -> List[str]:
    """OPTIONAL free-text enricher, gated. Returns [] when off or when the seam is a stub.

    Delegates to extract.extract_llm (the LLM-in-one-box). Today that raises NotImplementedError
    (human-run wiring), so this returns [] and the rule path is unaffected. Any exception is
    swallowed -- an enricher failure must never break the deterministic fact row.
    """
    if not _llm_enabled():
        return []
    try:  # pragma: no cover - off by default, seam is a stub
        from scripts.platformkit.edge_engine import extract  # type: ignore
        from scripts.platformkit.edge_engine.schema_source import SourceDoc  # type: ignore
        doc = SourceDoc(doc_id=f"news:{sport}", sport=sport, published_ts=published,
                        text=headline, source=_SOURCE)
        return [f.value_text for f in extract.extract_llm(doc)]
    except Exception:
        return []


def rows_from_payload(payload: Dict[str, Any], sport: str) -> List[Dict[str, Any]]:
    """Parse an ESPN news payload into fact rows. Pure -- no network, used by the test."""
    rows: List[Dict[str, Any]] = []
    for a in payload.get("articles", []) or []:
        headline = str(a.get("headline", "") or "")
        if not headline:
            continue
        published = str(a.get("published", "") or "")
        cats = a.get("categories", []) or []
        url = str(((a.get("links") or {}).get("web") or {}).get("href", "") or "")
        row: Dict[str, Any] = {
            "sport": sport,
            "source": _SOURCE,
            "headline": headline,
            "published": published,
            "categories": _entities(cats, "topic"),
            "players": _entities(cats, "athlete"),
            "teams": _entities(cats, "team"),
            "url": url,
        }
        notes = _maybe_llm_enrich(headline, published, sport)
        if notes:
            row["llm_notes"] = notes
        rows.append(row)
    return rows


def _dedupe_key(r: Dict[str, Any]) -> Tuple[str, str]:
    return (r["headline"], r["published"])


def fetch_news(sport: str, http_get: Optional[HttpGet] = None) -> List[Dict[str, Any]]:
    """Fetch + normalize the ESPN news feed for one sport. http_get injectable for tests."""
    if sport not in _SPORT_PATHS:
        raise ValueError(f"news not wired for sport {sport!r}; wired={list(_SPORT_PATHS)}")
    get = http_get or http_json
    payload = get(_BASE.format(path=_SPORT_PATHS[sport]))
    return rows_from_payload(payload, sport)


def store_news(sport: str, http_get: Optional[HttpGet] = None) -> Tuple[int, int]:
    """Fetch, then append only new rows. Returns (n_fetched, n_added). Idempotent on re-run."""
    rows = fetch_news(sport, http_get=http_get)
    # published is the freshness field for news; store_summary reads it. Copy into fetched_at
    # is unnecessary -- store_summary already falls back to `published`.
    added = append_new(path_for("news", sport), rows, _dedupe_key)
    return len(rows), added


WIRED_SPORTS: Tuple[str, ...] = tuple(_SPORT_PATHS)
