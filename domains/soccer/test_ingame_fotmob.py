"""Per-file test for domains.soccer.ingame_fotmob.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_ingame_fotmob.py -q
"""
from __future__ import annotations

import json

import domains.soccer.ingame_fotmob as fm


def _fake_detail():
    """A small synthetic matchDetails content block: home(id=1) scores an xG
    0.3 shot at minute 10, away(id=2) scores an xG 0.5 shot at minute 60."""
    return {
        "general": {"homeTeam": {"id": 1, "name": "Home FC"},
                    "awayTeam": {"id": 2, "name": "Away FC"}},
        "shotmap": {"shots": [
            {"teamId": 1, "min": 10, "minAdded": None, "expectedGoals": 0.3,
             "expectedGoalsOnTarget": 0.2, "isOnTarget": True},
            {"teamId": 2, "min": 60, "minAdded": None, "expectedGoals": 0.5,
             "expectedGoalsOnTarget": 0.4, "isOnTarget": True},
        ]},
        "momentum": {"main": {"data": [
            {"minute": 5, "value": 10}, {"minute": 8, "value": -5},
            {"minute": 55, "value": 20},
        ]}},
        "matchFacts": {"events": {"events": [
            {"type": "Card", "card": "Red", "time": 70, "isHome": False},
            {"type": "Card", "card": "Yellow", "time": 20, "isHome": True},
        ]}},
    }


def test_asof_no_future_leak():
    """A shot at minute 60 must never appear in a minute-45 cutoff row (and
    must appear once the cutoff passes it) -- the core as-of invariant."""
    detail = _fake_detail()
    state_45 = fm.asof_state_at(detail, 45.0)
    state_60 = fm.asof_state_at(detail, 60.0)
    assert state_45["xg_away"] == 0.0, "away's minute-60 shot leaked into a minute-45 row"
    assert state_60["xg_away"] == 0.5
    # home's minute-10 shot is present at both cutoffs (monotonic non-decreasing).
    assert state_45["xg_home"] == 0.3
    assert state_60["xg_home"] == 0.3


def test_asof_monotonic_cutoffs_never_decrease():
    """xg accumulated must be monotonically non-decreasing as cutoff advances."""
    detail = _fake_detail()
    prev_home = prev_away = 0.0
    for cutoff in (0.0, 9.9, 10.0, 30.0, 59.9, 60.0, 90.0):
        st = fm.asof_state_at(detail, cutoff)
        assert st["xg_home"] >= prev_home - 1e-9
        assert st["xg_away"] >= prev_away - 1e-9
        prev_home, prev_away = st["xg_home"], st["xg_away"]


def test_red_card_state_asof():
    detail = _fake_detail()
    assert fm.asof_state_at(detail, 69.0)["red_card_state"] == (0, 0)
    assert fm.asof_state_at(detail, 70.0)["red_card_state"] == (0, 1)


def test_momentum_last10_window():
    detail = _fake_detail()
    st = fm.asof_state_at(detail, 8.0)
    # points at minute 5 and 8 are within (8-10, 8] = (-2, 8]; mean = (10 + -5)/2 = 2.5
    assert st["momentum_last10"] == 2.5


def test_big_chance_diff_always_none():
    """Honest gap: FotMob shotmap has no per-shot isBigChance flag."""
    detail = _fake_detail()
    st = fm.asof_state_at(detail, 90.0)
    assert st["big_chance_diff"] is None


def test_asof_state_never_raises_on_malformed_detail():
    for bad in (None, {}, {"shotmap": None}, {"shotmap": {"shots": "not-a-list"}},
                {"momentum": {"main": {"data": [{"minute": "x", "value": "y"}]}}}):
        st = fm.asof_state_at(bad or {}, 45.0)
        assert isinstance(st, dict)
        assert st["cutoff_min"] == 45.0


def test_match_to_fixture_substring_both_sides():
    matches = [
        {"id": 111, "home": {"name": "Switzerland"}, "away": {"name": "Algeria"}},
        {"id": 222, "home": {"name": "Argentina"}, "away": {"name": "Cape Verde"}},
    ]
    hit = fm.match_to_fixture(matches, "Switzerland", "Algeria")
    assert hit is not None and hit["id"] == 111


def test_match_to_fixture_no_ambiguous_guess():
    """Two matches sharing a home-name-substring collision -> None, never a guess."""
    matches = [
        {"id": 1, "home": {"name": "Korea Republic"}, "away": {"name": "Ghana"}},
        {"id": 2, "home": {"name": "Korea Republic"}, "away": {"name": "Poland"}},
    ]
    # away side disambiguates correctly to exactly one match.
    assert fm.match_to_fixture(matches, "Korea Republic", "Ghana")["id"] == 1
    # a home-only query with no away info given still requires the away side to
    # align -- an empty/garbage away string aligns with neither, so None.
    assert fm.match_to_fixture(matches, "Korea Republic", "zzz-no-such-team") is None


def test_match_to_fixture_none_when_no_match():
    matches = [{"id": 1, "home": {"name": "Brazil"}, "away": {"name": "Serbia"}}]
    assert fm.match_to_fixture(matches, "France", "England") is None


def test_fetch_matches_for_date_flattens_leagues(monkeypatch=None):
    payload = {"leagues": [
        {"matches": [{"id": 1}, {"id": 2}]},
        {"matches": [{"id": 3}]},
        "not-a-dict-league",
    ]}
    out = fm.fetch_matches_for_date("20260703", getter=lambda url: payload)
    assert [m["id"] for m in out] == [1, 2, 3]


def test_fetch_matches_for_date_empty_on_bad_payload():
    assert fm.fetch_matches_for_date("20260703", getter=lambda url: None) == []
    assert fm.fetch_matches_for_date("20260703", getter=lambda url: "oops") == []


def test_fetch_match_detail_merges_general_into_content():
    """FotMob puts homeTeam/awayTeam under top-level `general`, not inside
    `content` -- fetch_match_detail must merge it in so asof_state_at can
    find content['general']['homeTeam']['id']."""
    payload = {
        "general": {"homeTeam": {"id": 9, "name": "H"}, "awayTeam": {"id": 8, "name": "A"}},
        "content": {"shotmap": {"shots": []}},
    }
    detail = fm.fetch_match_detail(123, getter=lambda url: payload)
    assert detail is not None
    assert detail["general"]["homeTeam"]["id"] == 9
    assert detail["shotmap"] == {"shots": []}


def test_fetch_match_detail_none_on_bad_payload():
    assert fm.fetch_match_detail(1, getter=lambda url: None) is None
    assert fm.fetch_match_detail(1, getter=lambda url: {"no_content_key": True}) is None


def test_sidecar_path_shape():
    p = fm.sidecar_path(4653717)
    assert p.name == "4653717.jsonl"
    assert p.parent == fm.SIDECAR_DIR
    assert p.parent.parts[-3:] == ("data", "domains", "soccer_intl") or \
        p.parent.parts[-2:] == ("soccer_intl", "fotmob_live")


def test_append_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(fm, "SIDECAR_DIR", tmp_path)
    fm.append_snapshot("test123", {"xg_home": 1.2, "xg_away": 0.4})
    lines = (tmp_path / "test123.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["xg_home"] == 1.2 and "fetch_ts" in row

    # a second append does not overwrite the first (append-only).
    fm.append_snapshot("test123", {"xg_home": 2.0, "xg_away": 1.0})
    lines2 = (tmp_path / "test123.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == 2


def test_poll_once_offline_summary_shape(monkeypatch):
    """poll_once with an injected offline matches list -- no network."""
    live_match = {
        "id": 555,
        "home": {"name": "Home FC"}, "away": {"name": "Away FC"},
        "status": {"started": True, "finished": False, "cancelled": False},
    }
    monkeypatch.setattr(fm, "fetch_matches_for_date", lambda d, getter=None: [live_match])
    monkeypatch.setattr(fm, "fetch_match_detail", lambda mid, getter=None: _fake_detail())
    monkeypatch.setattr(fm, "append_snapshot", lambda mid, row: None)
    summary = fm.poll_once("20260703", sleep_s=0.0)
    assert summary["n_matches"] == 1
    assert summary["n_matched"] == 1
    assert summary["n_snapshots"] == 1
