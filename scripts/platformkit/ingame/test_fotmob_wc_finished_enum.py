"""Per-file tests for fotmob_wc_finished_enum (LANE 3 item 1: corpus-
extension coverage census).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_fotmob_wc_finished_enum.py -q
"""
from __future__ import annotations

import json
from datetime import date

from scripts.platformkit.ingame import fotmob_wc_finished_enum as E


def _fake_fetch(matches_by_date):
    def _fn(date_str):
        return matches_by_date.get(date_str, [])
    return _fn


def test_date_range_inclusive_both_ends():
    out = E._date_range(date(2026, 6, 11), date(2026, 6, 13))
    assert out == ["20260611", "20260612", "20260613"]


def test_is_finished_true_only_when_finished_not_cancelled():
    assert E._is_finished({"status": {"finished": True}}) is True
    assert E._is_finished({"status": {"finished": True, "cancelled": True}}) is False
    assert E._is_finished({"status": {"finished": False}}) is False
    assert E._is_finished({}) is False


def test_scan_window_collects_only_finished_dedup_by_id():
    fetch = _fake_fetch({
        "20260611": [
            {"id": 1, "home": {"name": "A"}, "away": {"name": "B"},
             "status": {"finished": True}},
            {"id": 2, "home": {"name": "C"}, "away": {"name": "D"},
             "status": {"finished": False}},
        ],
        "20260612": [
            {"id": 1, "home": {"name": "A"}, "away": {"name": "B"},
             "status": {"finished": True}},  # duplicate id, same match re-listed
        ],
    })
    result = E.scan_window(start=date(2026, 6, 11), end=date(2026, 6, 12),
                           fetch_fn=fetch, sleep_s=0.0)
    assert len(result["matches"]) == 1
    assert result["matches"][0]["id"] == 1
    assert result["n_requests"] == 2
    assert result["dates_scanned"] == ["20260611", "20260612"]


def test_scan_window_skips_existing_dates_unless_forced():
    calls = []

    def fetch(ds):
        calls.append(ds)
        return []

    result = E.scan_window(start=date(2026, 6, 11), end=date(2026, 6, 13),
                           fetch_fn=fetch, sleep_s=0.0,
                           existing_dates=["20260611", "20260612"])
    assert calls == ["20260613"]
    assert result["dates_scanned"] == ["20260613"]


def test_scan_window_force_rescans_everything():
    calls = []

    def fetch(ds):
        calls.append(ds)
        return []

    E.scan_window(start=date(2026, 6, 11), end=date(2026, 6, 12), fetch_fn=fetch,
                  sleep_s=0.0, existing_dates=["20260611", "20260612"], force=True)
    assert calls == ["20260611", "20260612"]


def test_scan_window_budget_caps_new_requests():
    fetch = _fake_fetch({})
    result = E.scan_window(start=date(2026, 6, 11), end=date(2026, 6, 20),
                           fetch_fn=fetch, sleep_s=0.0, budget=3)
    assert result["n_requests"] == 3
    assert len(result["dates_scanned"]) == 3


def test_default_wc_leagues_for_date_filters_non_wc_leagues(monkeypatch):
    """Guards against the real-world regression this module fixes: a raw
    matches?date= payload lists EVERY league that day (domestic cups, U20s,
    friendlies) -- only leagues whose name contains 'world cup' must survive."""
    payload = {"leagues": [
        {"name": "World Cup Grp. A", "matches": [
            {"id": 1, "home": {"name": "Mexico"}, "away": {"name": "South Africa"},
             "status": {"finished": True}}]},
        {"name": "Friendlies", "matches": [
            {"id": 2, "home": {"name": "X"}, "away": {"name": "Y"},
             "status": {"finished": True}}]},
        {"name": "Cup", "matches": [
            {"id": 3, "home": {"name": "Z"}, "away": {"name": "W"},
             "status": {"finished": True}}]},
    ]}

    def fake_getter(url):
        return payload

    monkeypatch.setattr("domains.soccer.ingame_fotmob._http_get_json", fake_getter)
    out = E._default_wc_leagues_for_date("20260611")
    ids = {m["id"] for m in out}
    assert ids == {1}


def test_default_wc_leagues_for_date_bad_payload_is_honest_empty(monkeypatch):
    monkeypatch.setattr("domains.soccer.ingame_fotmob._http_get_json", lambda url: None)
    assert E._default_wc_leagues_for_date("20260611") == []


def test_scan_window_fetch_exception_is_honest_error_not_raise():
    def boom(ds):
        raise RuntimeError("network flake")

    result = E.scan_window(start=date(2026, 6, 11), end=date(2026, 6, 11),
                           fetch_fn=boom, sleep_s=0.0)
    assert result["matches"] == []
    assert len(result["errors"]) == 1
    assert "network flake" in result["errors"][0]


def test_build_roster_writes_file_and_merges_across_calls(tmp_path):
    path = tmp_path / "roster.json"
    fetch1 = _fake_fetch({"20260611": [
        {"id": 1, "home": {"name": "A"}, "away": {"name": "B"}, "status": {"finished": True}},
    ]})
    doc1 = E.build_roster(roster_path=path, fetch_fn=fetch1, sleep_s=0.0,
                          budget=1, n_captured=39)
    assert path.is_file()
    assert doc1["n_finished_matches_total"] == 1
    assert doc1["n_finished_matches_captured"] == 39

    fetch2 = _fake_fetch({"20260612": [
        {"id": 2, "home": {"name": "C"}, "away": {"name": "D"}, "status": {"finished": True}},
    ]})
    doc2 = E.build_roster(roster_path=path, fetch_fn=fetch2, sleep_s=0.0, n_captured=39)
    ids = {m["id"] for m in doc2["matches"]}
    assert ids == {1, 2}
    assert doc2["n_finished_matches_total"] == 2


def test_build_roster_dedup_does_not_double_count_on_rescan(tmp_path):
    path = tmp_path / "roster.json"
    fetch = _fake_fetch({"20260611": [
        {"id": 1, "home": {"name": "A"}, "away": {"name": "B"}, "status": {"finished": True}},
    ]})
    E.build_roster(roster_path=path, fetch_fn=fetch, sleep_s=0.0)
    doc2 = E.build_roster(roster_path=path, fetch_fn=fetch, sleep_s=0.0, force=True)
    assert doc2["n_finished_matches_total"] == 1


def test_build_roster_honesty_fields_present(tmp_path):
    path = tmp_path / "roster.json"
    doc = E.build_roster(roster_path=path, fetch_fn=_fake_fetch({}), sleep_s=0.0, budget=1)
    assert "honest_note" in doc
    assert "39 already-captured" in doc["honest_note"]
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["component"] == "fotmob_wc_finished_enum"


def test_build_roster_never_raises_on_corrupt_prior_file(tmp_path):
    path = tmp_path / "roster.json"
    path.write_text("not json{{{", encoding="utf-8")
    doc = E.build_roster(roster_path=path, fetch_fn=_fake_fetch({}), sleep_s=0.0, budget=1)
    assert isinstance(doc, dict)
    assert doc["n_finished_matches_total"] == 0
