"""Per-file, no-network tests for polymarket_scope.py + polymarket_book_row.py +
polymarket_book_capture.py: (a) discovery pagination + clobTokenIds/outcomes
JSON-string parsing on fixture pages, (b) live/pregame/idle classification +
cadence from fixture startDate/endDate/live-flag, (c) snapshot-row construction
(raw /book + /midpoint payloads verbatim, best bid/ask/sizes/depth/mid derived)
from a fixture, (d) archive path selection under the two pod env flags, (e) the
read-only-by-construction grep guard, (f) the 429 exponential-backoff schedule,
both as a pure function and as GovernedClient's own retry behavior. Every HTTP
boundary (the discovery *get* callable, GovernedClient's opener) is a fixture
function -- no socket is ever opened.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_polymarket_book_capture.py -q
"""
from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import scripts.platformkit.ingame as ingame_pkg
from scripts.platformkit.ingame import polymarket_book_capture as capture
from scripts.platformkit.ingame import polymarket_book_row as row
from scripts.platformkit.ingame import polymarket_scope as scope


# --------------------------------------------------------------------------- #
# (a) discovery pagination + clobTokenIds/outcomes parsing                    #
# --------------------------------------------------------------------------- #
def test_discovery_url_carries_the_fixed_query_and_a_bumped_offset():
    url0 = scope.discovery_url(0)
    assert "tag_slug=sports" in url0 and "active=true" in url0 and "closed=false" in url0
    assert "order=volume24hr" in url0 and "ascending=false" in url0
    assert "offset=0" in url0
    assert "offset=100" in scope.discovery_url(100)


def test_fetch_events_paginates_by_offset_until_a_short_page(monkeypatch):
    monkeypatch.setattr(scope, "DISCOVERY_LIMIT", 2)
    page0_url, page1_url = scope.discovery_url(0), scope.discovery_url(2)
    pages = {page0_url: [{"id": "E1"}, {"id": "E2"}], page1_url: [{"id": "E3"}]}
    calls = []

    def get(url):
        calls.append(url)
        return pages.get(url)

    events = scope.fetch_events(get)
    assert [e["id"] for e in events] == ["E1", "E2", "E3"]
    assert calls == [page0_url, page1_url], "pagination stopped once a page came back short"


def test_fetch_events_tolerates_a_failed_page():
    assert scope.fetch_events(lambda _url: None) == []


def test_parse_token_ids_decodes_the_json_encoded_string_and_tolerates_garbage():
    assert scope.parse_token_ids({"clobTokenIds": '["111", "222"]'}) == ["111", "222"]
    assert scope.parse_token_ids({"clobTokenIds": "not json"}) == []
    assert scope.parse_token_ids({}) == []


def test_extract_markets_flattens_events_and_tags_sport_state_and_tokens():
    now = datetime(2026, 9, 14, 20, 0, 0, tzinfo=timezone.utc)
    events = [{
        "id": "EV1", "slug": "nba-lal-bos", "title": "NBA: Lakers vs Celtics",
        "startDate": "2026-09-14T19:00:00Z", "endDate": "2026-09-14T22:00:00Z",
        "markets": [{"conditionId": "C1", "question": "Will Lakers win?",
                     "outcomes": '["Yes", "No"]', "clobTokenIds": '["T1", "T2"]'}],
    }]
    markets = scope.extract_markets(events, now)
    assert len(markets) == 1
    m = markets[0]
    assert m["sport"] == "nba" and m["state"] == "live" and m["token_ids"] == ["T1", "T2"]
    assert m["outcomes"] == ["Yes", "No"] and m["condition_id"] == "C1"


def test_extract_markets_skips_a_market_with_no_parseable_token_ids():
    now = datetime(2026, 9, 14, 20, 0, 0, tzinfo=timezone.utc)
    events = [{"id": "EV1", "title": "x", "markets": [{"conditionId": "C1"}]}]
    assert scope.extract_markets(events, now) == []


# --------------------------------------------------------------------------- #
# (b) live/pregame/idle classification + cadence                              #
# --------------------------------------------------------------------------- #
def test_classify_event_state_live_pregame_idle_and_missing_dates():
    now = datetime(2026, 9, 14, 20, 0, 0, tzinfo=timezone.utc)
    assert scope.classify_event_state(
        {"startDate": "2026-09-14T19:00:00Z", "endDate": "2026-09-14T22:00:00Z"}, now
    ) == ("live", scope.LIVE_CADENCE_SEC)
    assert scope.classify_event_state({"startDate": "2026-09-15T10:00:00Z"}, now) \
        == ("pregame", scope.PREGAME_CADENCE_SEC)
    assert scope.classify_event_state({"startDate": "2026-09-20T10:00:00Z"}, now) \
        == ("idle", scope.IDLE_CADENCE_SEC)
    assert scope.classify_event_state({}, now) == ("idle", scope.IDLE_CADENCE_SEC)


def test_classify_event_state_honors_the_live_flag_even_without_dates():
    now = datetime(2026, 9, 14, 20, 0, 0, tzinfo=timezone.utc)
    assert scope.classify_event_state({"live": True}, now) == ("live", scope.LIVE_CADENCE_SEC)


def test_classify_sport_keyword_heuristic():
    assert scope.classify_sport("NBA: Lakers vs Celtics") == "nba"
    assert scope.classify_sport("Real Madrid vs Barcelona (La Liga)") == "soccer"
    assert scope.classify_sport("ATP Shanghai: Sinner vs Alcaraz") == "tennis"
    assert scope.classify_sport("Totally unrelated market") == "other"


# --------------------------------------------------------------------------- #
# (c) snapshot-row construction: raw verbatim + derived best bid/ask/mid/depth #
# --------------------------------------------------------------------------- #
def _market(**over):
    base = {"sport": "nba", "event_id": "E1", "event_slug": "s", "condition_id": "C1",
            "question": "Will X win?", "outcomes": ["Yes", "No"], "state": "live"}
    base.update(over)
    return base


def test_book_row_stores_raw_payloads_verbatim_and_derives_best_bid_ask_depth():
    book_body = {"bids": [{"price": "0.40", "size": "10"}, {"price": "0.45", "size": "5"}],
                 "asks": [{"price": "0.60", "size": "3"}, {"price": "0.55", "size": "7"}]}
    mid_body = {"mid": "0.52"}
    out = row.book_row(_market(), "TOK1", 0, book_body, mid_body,
                        ts_ms=1700000000000, capture_ts="2026-09-14T20:00:00.000000Z")
    assert out["book"] is book_body and out["midpoint_raw"] is mid_body, "raw payloads, no transformation"
    assert out["venue"] == "polymarket" and out["sport"] == "nba" and out["token_id"] == "TOK1"
    assert out["outcome_label"] == "Yes" and out["capture_version"] == row.CAPTURE_VERSION
    assert out["best_bid"] == 0.45 and out["best_bid_size"] == 5.0, "last entry of the ASC bid ladder"
    assert out["best_ask"] == 0.55 and out["best_ask_size"] == 7.0, "last entry of the DESC ask ladder"
    assert out["depth_bid"] == 15.0 and out["depth_ask"] == 10.0
    assert out["mid"] == 0.52, "the venue's own /midpoint value takes precedence over (bid+ask)/2"


def test_book_row_mid_falls_back_to_bid_ask_average_without_a_midpoint_fetch():
    book_body = {"bids": [{"price": "0.40", "size": "1"}], "asks": [{"price": "0.60", "size": "1"}]}
    out = row.book_row(_market(), "TOK1", 1, book_body, None,
                        ts_ms=1700000001000, capture_ts="2026-09-14T20:00:05.000000Z")
    assert out["outcome_label"] == "No"
    assert out["mid"] == 0.50, "no midpoint payload -> falls back to (0.40+0.60)/2"


def test_book_row_one_sided_book_leaves_the_missing_side_none_and_mid_none():
    book_body = {"bids": [{"price": "0.20", "size": "2"}], "asks": []}
    out = row.book_row(_market(), "TOK1", 0, book_body, None,
                        ts_ms=1700000002000, capture_ts="2026-09-14T20:00:10.000000Z")
    assert out["best_bid"] == 0.20 and out["best_ask"] is None
    assert out["depth_ask"] == 0.0
    assert out["mid"] is None, "no ask side and no midpoint fetch -- nothing to average"


# --------------------------------------------------------------------------- #
# (d) archive path selection under the two pod env flags                      #
# --------------------------------------------------------------------------- #
def test_archive_path_is_live_only_with_both_flags_set():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    scratch = row.SCRATCH_ARCHIVE_ROOT / "nba" / "2026-09-14.jsonl"
    live = row.LIVE_ARCHIVE_ROOT / "nba" / "2026-09-14.jsonl"
    assert row.archive_path("nba", now, {}) == scratch
    assert row.archive_path("nba", now, {"CV_CAPTURE_POD": "1"}) == scratch
    assert row.archive_path("nba", now, {"CV_POLYMARKET_BOOK_ARCHIVE_LIVE": "1"}) == scratch
    both = {"CV_CAPTURE_POD": "1", "CV_POLYMARKET_BOOK_ARCHIVE_LIVE": "1"}
    assert row.archive_path("nba", now, both) == live
    assert row.live_archive_enabled(both)
    assert not row.live_archive_enabled({"CV_CAPTURE_POD": "1"})
    # capture.py re-exports the same helpers -- prove they resolve identically
    assert capture.archive_path("nba", now, both) == live


# --------------------------------------------------------------------------- #
# (e) read-only by construction: no order-placement endpoint anywhere         #
# --------------------------------------------------------------------------- #
def test_polymarket_modules_never_reference_order_placement_endpoints():
    # Assembled at runtime so this guard never contains the literal fragments
    # it is checking for.
    forbidden = ["/" + "order", "post" + "_" + "order"]
    ingame_dir = Path(ingame_pkg.__file__).resolve().parent
    modules = sorted(ingame_dir.glob("polymarket_*.py"))
    assert modules, "expected polymarket_*.py modules to exist under ingame/"
    for path in modules:
        text = path.read_text(encoding="utf-8")
        for frag in forbidden:
            assert frag not in text, "%s references a forbidden order-placement fragment %r" % (path.name, frag)


# --------------------------------------------------------------------------- #
# (f) 429 exponential backoff: pure schedule + GovernedClient's own retries   #
# --------------------------------------------------------------------------- #
def test_backoff_seconds_doubles_and_caps():
    assert [capture.backoff_seconds(n) for n in range(1, 7)] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
    assert capture.backoff_seconds(0) == 0.0


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self):
        return self._payload


def _flaky_opener(fail_times, payload):
    calls = {"n": 0}

    def opener(request, timeout=15.0):
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
        return _FakeResponse(payload)

    return opener, calls


def test_governed_client_retries_with_the_backoff_schedule_then_succeeds():
    opener, calls = _flaky_opener(fail_times=2, payload={"ok": True})
    sleeps = []
    client = capture.GovernedClient(opener=opener, sleep_fn=sleeps.append, clock=lambda: 100.0)
    body, ts_ms = client.get("https://clob.polymarket.com/book?token_id=T1")
    assert body == {"ok": True} and isinstance(ts_ms, int)
    assert client.n_429 == 2 and client.n_errors == 2 and calls["n"] == 3
    assert sleeps == [capture.backoff_seconds(1), capture.backoff_seconds(2)], \
        "constant clock keeps the token bucket at wait=0 for these 3 acquires -- only 429 backoff sleeps"


def test_governed_client_gives_up_after_max_retries_and_returns_none():
    opener, calls = _flaky_opener(fail_times=999, payload={})
    sleeps = []
    client = capture.GovernedClient(opener=opener, sleep_fn=sleeps.append, clock=lambda: 100.0, max_retries=2)
    body, ts_ms = client.get("https://clob.polymarket.com/book?token_id=T1")
    assert body is None and isinstance(ts_ms, int)
    assert client.n_429 == 3 and calls["n"] == 3, "initial attempt + 2 retries, all 429"
    assert sleeps == [capture.backoff_seconds(1), capture.backoff_seconds(2)]


def test_governed_client_non_429_http_error_never_retries():
    def opener(request, timeout=15.0):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", {}, None)
    sleeps = []
    client = capture.GovernedClient(opener=opener, sleep_fn=sleeps.append, clock=lambda: 100.0)
    body, ts_ms = client.get("https://clob.polymarket.com/book?token_id=T1")
    assert body is None and client.n_429 == 0 and client.n_errors == 1
    assert sleeps == [], "a non-429 error never sleeps for backoff"
