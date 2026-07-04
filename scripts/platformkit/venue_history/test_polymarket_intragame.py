"""Tests for scripts.platformkit.venue_history.polymarket_intragame. Offline, canned HTTP only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.venue_history import polymarket_intragame as pi


def _market(slug: str, outcomes: List[str], token0: str, token1: str,
           outcome_prices: List[str], closed: bool = True) -> Dict[str, Any]:
    return {
        "slug": slug,
        "outcomes": json.dumps(outcomes),
        "outcomePrices": json.dumps(outcome_prices),
        "clobTokenIds": json.dumps([token0, token1]),
        "closed": closed,
    }


def _fake_http(events_by_slug: Dict[str, Any], history_by_token: Dict[str, List[Dict[str, Any]]]):
    def http(url: str) -> Any:
        if "/prices-history" in url:
            token = url.split("market=")[1].split("&")[0]
            return {"history": history_by_token.get(token, [])}
        if "/events?slug=" in url:
            slug = url.split("slug=")[1]
            return events_by_slug.get(slug, [])
        raise AssertionError("unexpected url: %s" % url)
    return http


def test_json_string_token_and_outcome_parse() -> None:
    """clobTokenIds/outcomes/outcomePrices are JSON-ENCODED STRINGS -- json.loads them."""
    m = _market("mlb-tb-det-2023-04-02", ["Rays", "Tigers"], "TOK0", "TOK1", ["1", "0"])
    assert pi._as_list(m["outcomes"]) == ["Rays", "Tigers"]
    assert pi._as_list(m["clobTokenIds"]) == ["TOK0", "TOK1"]
    assert pi._resolve_outcome(m) == 1  # outcome[0] (Rays/home) won


def test_resolve_outcome_ambiguous_cases() -> None:
    open_mkt = _market("x", ["A", "B"], "T0", "T1", ["0.6", "0.4"], closed=False)
    assert pi._resolve_outcome(open_mkt) is None  # not closed -> never guessed
    draw_shaped = _market("x", ["A", "B"], "T0", "T1", ["0.5", "0.5"], closed=True)
    assert pi._resolve_outcome(draw_shaped) is None  # not a clean 1/0 settle
    away_won = _market("x", ["A", "B"], "T0", "T1", ["0", "1"], closed=True)
    assert pi._resolve_outcome(away_won) == 0


def test_fetch_dailies_event_exact_slug() -> None:
    events = {
        "mlb-dailies-2023-04-02": [{
            "slug": "mlb-dailies-2023-04-02",
            "markets": [_market("mlb-tb-det-2023-04-02", ["Rays", "Tigers"], "T0", "T1", ["1", "0"])],
        }],
    }
    http = _fake_http(events, {})
    ev = pi.fetch_dailies_event("mlb", "2023-04-02", http=http)
    assert ev is not None
    assert ev["slug"] == "mlb-dailies-2023-04-02"
    # A day with no event -> None, not a fabricated empty doc.
    assert pi.fetch_dailies_event("mlb", "2023-01-01", http=http) is None


def test_fetch_price_history_explicit_ts_shape() -> None:
    history = {"TOK0": [{"t": 1680415202, "p": 0.81}, {"t": 1680415270, "p": 0.79},
                        {"t": "bad", "p": 0.5}, {"t": 1680415300, "p": 1.5}]}
    http = _fake_http({}, history)
    pts = pi.fetch_price_history("TOK0", 1680400000, 1680500000, http=http)
    # Bad ts and out-of-range prob rows are dropped; good rows carry ISO ts.
    assert len(pts) == 2
    assert pts[0]["ts"] == "2023-04-02T06:00:02Z"
    assert pts[0]["prob_home"] == 0.81


def test_build_game_doc_ordering_and_asof() -> None:
    m = _market("mlb-tb-det-2023-04-02", ["Rays", "Tigers"], "T0", "T1", ["1", "0"])
    history = {"T0": [{"t": 1680415202, "p": 0.81}, {"t": 1680415270, "p": 0.85}]}
    http = _fake_http({}, history)
    doc = pi.build_game_doc("2023-04-02", "mlb-dailies-2023-04-02", "mlb", m, http=http)
    assert doc is not None
    assert doc["home"] == "Rays" and doc["away"] == "Tigers"
    assert doc["outcome_home_win"] == 1
    assert doc["n_prices"] == 2
    # Ticks stay in fetch order (already time-ascending from the venue).
    ts_list = [p["ts"] for p in doc["prices"]]
    assert ts_list == sorted(ts_list)


def test_enumerator_resumability(tmp_path: Path) -> None:
    """A run that hits an off-day then a game-day, resumed, does not re-walk the
    already-confirmed day."""
    events = {
        "mlb-dailies-2023-04-01": [],  # off-day: no event
        "mlb-dailies-2023-04-02": [{
            "slug": "mlb-dailies-2023-04-02",
            "markets": [_market("mlb-tb-det-2023-04-02", ["Rays", "Tigers"], "T0", "T1", ["1", "0"])],
        }],
        "mlb-dailies-2023-04-03": [{
            "slug": "mlb-dailies-2023-04-03",
            "markets": [_market("mlb-nyy-bos-2023-04-03", ["Yankees", "Red Sox"], "T2", "T3", ["0", "1"])],
        }],
    }
    history = {"T0": [{"t": 1680415202, "p": 0.81}], "T2": [{"t": 1680501602, "p": 0.55}]}
    http = _fake_http(events, history)
    out_dir = tmp_path / "poly_out"
    result = pi.run_backfill("mlb", "2023-04-01", "2023-04-03", out_dir=out_dir,
                             http=http, sleep_sec=0, sleep_fn=lambda s: None, max_requests=50)
    assert result["n_off_days"] == 1
    assert result["n_game_days"] == 2
    assert result["n_games"] == 2
    assert (out_dir / "2023-04-02_mlb-dailies-2023-04-02.jsonl").is_file()
    assert (out_dir / "2023-04-03_mlb-dailies-2023-04-03.jsonl").is_file()

    # Simulate an interrupted-then-resumed run: seed progress at 04-02 done.
    prog_path = out_dir / "_progress.json"
    prog = json.loads(prog_path.read_text(encoding="utf-8"))
    assert prog["last_date_done"] == "2023-04-03"
    seeded = dict(prog)
    seeded["last_date_done"] = "2023-04-02"
    seeded["n_game_days"] = 1
    seeded["n_games"] = 1
    prog_path.write_text(json.dumps(seeded), encoding="utf-8")
    for f in out_dir.glob("*.jsonl"):
        f.unlink()
    result2 = pi.run_backfill("mlb", "2023-04-01", "2023-04-03", out_dir=out_dir,
                              http=http, sleep_sec=0, sleep_fn=lambda s: None, max_requests=50)
    # Only 04-03 should be (re-)fetched -- 04-01/04-02 are skipped as already done.
    assert not (out_dir / "2023-04-02_mlb-dailies-2023-04-02.jsonl").exists()
    assert (out_dir / "2023-04-03_mlb-dailies-2023-04-03.jsonl").is_file()
    assert result2["n_game_days"] == 2  # cumulative counter carried from progress


def test_budget_stops_run_short_of_end_date(tmp_path: Path) -> None:
    events = {
        "mlb-dailies-2023-04-01": [{
            "slug": "mlb-dailies-2023-04-01",
            "markets": [_market("mlb-a-b-2023-04-01", ["A", "B"], "T0", "T1", ["1", "0"])],
        }],
        "mlb-dailies-2023-04-02": [{
            "slug": "mlb-dailies-2023-04-02",
            "markets": [_market("mlb-c-d-2023-04-02", ["C", "D"], "T2", "T3", ["1", "0"])],
        }],
    }
    http = _fake_http(events, {"T0": [], "T2": []})
    result = pi.run_backfill("mlb", "2023-04-01", "2023-04-05", max_requests=2,
                             out_dir=tmp_path / "poly_out", http=http,
                             sleep_sec=0, sleep_fn=lambda s: None)
    assert result["budget_hit"] is True
    assert result["reached_end_date"] is False
