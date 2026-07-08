"""Per-file test for news_facts: entities from ESPN categories, LLM hook OFF. No network."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.edge_engine import news_facts  # noqa: E402

# Trimmed recording of the real ESPN NBA news payload shape (captured 2026-07-08).
_FIXTURE = {
    "articles": [
        {"headline": "Grades for offseason signings",
         "published": "2026-07-08T16:27:00Z",
         "links": {"web": {"href": "https://espn.com/story/1"}},
         "categories": [
             {"type": "league", "description": "NBA"},
             {"type": "topic", "description": "nba free agency"},
             {"type": "topic", "description": "nba free agency"},  # dup -> collapsed
             {"type": "team", "description": "Phoenix Suns"},
             {"type": "athlete", "description": "Devin Booker"},
         ]},
        {"headline": "", "published": "2026-07-08T10:00:00Z"},  # empty headline -> skipped
    ]
}


def test_rows_from_payload_pulls_structured_entities():
    rows = news_facts.rows_from_payload(_FIXTURE, "nba")
    assert len(rows) == 1, "empty-headline article is skipped"
    r = rows[0]
    assert r["categories"] == ["nba free agency"], "deduped topic descriptions"
    assert r["teams"] == ["Phoenix Suns"]
    assert r["players"] == ["Devin Booker"]
    assert r["url"] == "https://espn.com/story/1"
    assert "llm_notes" not in r, "LLM hook is OFF by default -> identical schema"
    assert r["source"] == "espn_news" and r["sport"] == "nba"


def test_llm_hook_off_without_env(monkeypatch):
    monkeypatch.delenv("CV_EDGE_LLM", raising=False)
    assert news_facts._llm_enabled() is False
    monkeypatch.setenv("CV_EDGE_LLM", "1")  # flag on but no key -> still off
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert news_facts._llm_enabled() is False


def test_store_news_dedupes(tmp_path, monkeypatch):
    from scripts.platformkit.edge_engine import facts_store
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)
    n1, a1 = news_facts.store_news("nba", http_get=lambda url: _FIXTURE)
    assert (n1, a1) == (1, 1)
    n2, a2 = news_facts.store_news("nba", http_get=lambda url: _FIXTURE)
    assert (n2, a2) == (1, 0)
