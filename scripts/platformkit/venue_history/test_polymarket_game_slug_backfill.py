"""Tests for scripts.platformkit.venue_history.polymarket_game_slug_backfill.
Offline, canned HTTP only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.venue_history import polymarket_game_slug_backfill as gsb


def _market(slug: str, outcomes: List[str], token0: str, token1: str,
           outcome_prices: List[str], closed: bool = True) -> Dict[str, Any]:
    return {
        "slug": slug,
        "outcomes": json.dumps(outcomes),
        "outcomePrices": json.dumps(outcome_prices),
        "clobTokenIds": json.dumps([token0, token1]),
        "closed": closed,
    }


def _fake_http(pages: Dict[str, List[Dict[str, Any]]],
              events_by_slug: Dict[str, Any],
              history_by_token: Dict[str, List[Dict[str, Any]]]):
    def http(url: str) -> Any:
        if "/prices-history" in url:
            token = url.split("market=")[1].split("&")[0]
            return {"history": history_by_token.get(token, [])}
        if "/events?slug=" in url:
            slug = url.split("slug=")[1]
            return events_by_slug.get(slug, [])
        if "/events?" in url and "tag_slug" in url:
            start_min = url.split("start_date_min=")[1].split("&")[0]
            return pages.get(start_min, [])
        raise AssertionError("unexpected url: %s" % url)
    return http


def test_game_slug_pattern_matches_base_and_skips_postseason() -> None:
    pat = gsb.game_slug_pattern("nba")
    assert pat.match("nba-sas-lal-2025-12-10")
    assert pat.match("nba-nop-lac-2025-04-02-v2")  # v2 variant allowed
    assert not pat.match("nba-playoffs-timberwolves-vs-warriors-to-advance")
    assert not pat.match("world-series-champion-2024")
    assert not pat.match("nba-sas-lal-2025-12-10-spread-home-3pt5")  # aux market


def test_list_game_events_page_filters_non_game_slugs() -> None:
    events = [
        {"slug": "nba-sas-lal-2025-12-10", "startDate": "2025-12-04T00:00:00Z"},
        {"slug": "lebron-james-re-signs-with-lakers", "startDate": "2025-12-04T00:00:00Z"},
        {"slug": "nba-lal-hou-2026-04-26", "startDate": "2025-12-05T00:00:00Z"},
    ]
    http = _fake_http({"2025-12-01": events}, {}, {})
    page = gsb.list_game_events_page("nba", "2025-12-01", http=http)
    assert [e["slug"] for e in page] == ["nba-sas-lal-2025-12-10", "nba-lal-hou-2026-04-26"]


def test_base_moneyline_market_selected_not_aux() -> None:
    slug = "nba-sas-lal-2025-12-10"
    event = {
        "markets": [
            _market(slug + "-spread-home-3pt5", ["Lakers", "Spurs"], "TA", "TB", ["0", "1"]),
            _market(slug, ["Spurs", "Lakers"], "T0", "T1", ["1", "0"]),
        ]
    }
    http = _fake_http({}, {}, {"T0": [{"t": 1764860587, "p": 0.41}]})
    doc = gsb.build_game_doc("nba", slug, event, http=http)
    assert doc is not None
    assert doc["market_slug"] == slug  # base market, not the aux spread market
    assert doc["home"] == "Spurs" and doc["away"] == "Lakers"
    assert doc["outcome_home_win"] == 1
    assert doc["n_prices"] == 1
    assert doc["window"] == "2024plus"


def test_build_game_doc_none_when_no_base_market() -> None:
    slug = "nba-sas-lal-2025-12-10"
    event = {"markets": [_market(slug + "-spread-home-3pt5", ["A", "B"], "TA", "TB", ["0", "1"])]}
    assert gsb.build_game_doc("nba", slug, event, http=_fake_http({}, {}, {})) is None


def test_run_backfill_pages_and_writes_docs(tmp_path: Path) -> None:
    slug1, slug2 = "nba-sas-lal-2025-12-10", "nba-lal-hou-2025-12-11"
    pages = {
        "2025-12-01": [
            {"slug": slug1, "startDate": "2025-12-04T00:00:00Z"},
            {"slug": slug2, "startDate": "2025-12-05T00:00:00Z"},
        ],
        "2025-12-12": [],  # next page: empty -> exhausted
    }
    events = {
        slug1: [{"markets": [_market(slug1, ["Spurs", "Lakers"], "T0", "T1", ["1", "0"])]}],
        slug2: [{"markets": [_market(slug2, ["Lakers", "Rockets"], "T2", "T3", ["0", "1"])]}],
    }
    history = {"T0": [{"t": 1764860587, "p": 0.41}], "T2": [{"t": 1765430400, "p": 0.55}]}
    http = _fake_http(pages, events, history)
    out_dir = tmp_path / "nba_2024plus"
    result = gsb.run_backfill("nba", "2025-12-01", out_dir=out_dir, http=http,
                              sleep_sec=0, sleep_fn=lambda s: None, max_requests=50)
    assert result["n_games"] == 2
    assert result["exhausted"] is True
    assert (out_dir / "2025-12-10_nba-games.jsonl").is_file()
    assert (out_dir / "2025-12-11_nba-games.jsonl").is_file()
    doc = json.loads((out_dir / "2025-12-10_nba-games.jsonl").read_text(encoding="utf-8").strip())
    assert doc["outcome_home_win"] == 1


def test_run_backfill_resumable_skips_seen_slugs(tmp_path: Path) -> None:
    slug1 = "nba-sas-lal-2025-12-10"
    pages = {"2025-12-01": [{"slug": slug1, "startDate": "2025-12-04T00:00:00Z"}], "2025-12-11": []}
    events = {slug1: [{"markets": [_market(slug1, ["Spurs", "Lakers"], "T0", "T1", ["1", "0"])]}]}
    http = _fake_http(pages, events, {"T0": [{"t": 1764860587, "p": 0.41}]})
    out_dir = tmp_path / "nba_2024plus"
    result1 = gsb.run_backfill("nba", "2025-12-01", out_dir=out_dir, http=http,
                               sleep_sec=0, sleep_fn=lambda s: None, max_requests=50)
    assert result1["n_games"] == 1

    def http_should_not_refetch(url: str) -> Any:
        if "/events?slug=" in url:
            raise AssertionError("should not re-fetch an already-seen slug")
        return http(url)

    # Re-run from the same start: the tag-listing page still returns slug1
    # (it doesn't know about our progress), but the seen_dates set from the
    # resumed progress file must skip re-fetching its event detail.
    result2 = gsb.run_backfill("nba", "2025-12-01", out_dir=out_dir, http=http,
                               sleep_sec=0, sleep_fn=lambda s: None, max_requests=50,
                               progress_path=out_dir / "_progress.json")
    assert result2["n_games"] == 1  # cumulative, not re-added
    assert result2["cursor_start_date_min"] >= "2025-12-11"


def test_default_start_dates_reflect_probe_findings() -> None:
    assert gsb.DEFAULT_NBA_START == "2024-10-20"
    assert gsb.DEFAULT_MLB_START == "2024-09-25"
