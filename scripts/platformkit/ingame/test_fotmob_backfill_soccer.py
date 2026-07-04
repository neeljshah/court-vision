"""Per-file tests for fotmob_backfill_soccer (LANE 2: FotMob xG backfill).

OFFLINE + deterministic: injected fetch_matches/fetch_detail/match_to_fixture
/asof_fn + an in-memory SoccerOutcomeResolver -- no real network, no real
disk data touched (tmp_path only).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_fotmob_backfill_soccer.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.ingame import fotmob_backfill_soccer as B
from scripts.platformkit.ingame.soccer_outcome import SoccerOutcomeResolver


def _finals_df():
    return pd.DataFrame([
        {"event_id": "1", "date": "2026-06-22", "home_team": "Argentina",
         "away_team": "Austria", "home_score": 2.0, "away_score": 0.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
    ])


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _fake_detail():
    return {
        "general": {"homeTeam": {"id": 1, "name": "Argentina"},
                    "awayTeam": {"id": 2, "name": "Austria"}},
        "shotmap": {"shots": [
            {"teamId": 1, "min": 9, "expectedGoals": 0.79, "expectedGoalsOnTarget": 0.0,
             "isOnTarget": False},
            {"teamId": 1, "min": 70, "expectedGoals": 0.3, "expectedGoalsOnTarget": 0.2,
             "isOnTarget": True},
        ]},
    }


def _fake_asof(detail, cutoff):
    shots = (detail.get("shotmap") or {}).get("shots") or []
    xg_home = sum(s["expectedGoals"] for s in shots if s["min"] <= cutoff and s["teamId"] == 1)
    return {"cutoff_min": cutoff, "xg_home": round(xg_home, 4), "xg_away": 0.0,
            "sot_diff": 0, "big_chance_diff": None, "momentum_last10": None,
            "red_card_state": (0, 0)}


def test_find_finished_match_resolves_via_date_and_names():
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    calls = []

    def fetch_matches(date_str):
        calls.append(date_str)
        if date_str == "20260622":
            return [{"id": 4667815, "home": {"name": "Argentina"}, "away": {"name": "Austria"}}]
        return []

    def mtf(matches, home, away):
        for m in matches:
            if m["home"]["name"] == home and m["away"]["name"] == away:
                return m
        return None

    fx = B.find_finished_match("KXWCGAME-26JUN22ARGAUT", res, fetch_matches=fetch_matches,
                               match_to_fixture_fn=mtf)
    assert fx is not None and fx["id"] == 4667815
    assert "20260622" in calls


def test_find_finished_match_unresolvable_ticker_returns_none():
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    fx = B.find_finished_match("760500", res, fetch_matches=lambda d: [],
                               match_to_fixture_fn=lambda m, h, a: None)
    assert fx is None


def test_find_finished_match_no_match_returns_none():
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    fx = B.find_finished_match("KXWCGAME-26JUN22ARGAUT", res, fetch_matches=lambda d: [],
                               match_to_fixture_fn=lambda m, h, a: None)
    assert fx is None


def test_reconstruct_snapshots_asof_no_future_leak():
    detail = _fake_detail()
    rows = B.reconstruct_snapshots(detail, 4667815, "Argentina", "Austria",
                                   ["2026-06-22T17:10:00Z", "2026-06-22T18:40:00Z"],
                                   asof_fn=_fake_asof)
    assert len(rows) == len(B._CHECKPOINT_MINUTES)
    # checkpoint 15 must NOT see the minute-70 shot; checkpoint 75+ must.
    by_cutoff = {r["cutoff_min"]: r for r in rows}
    assert by_cutoff[15.0]["xg_home"] == 0.79
    assert by_cutoff[75.0]["xg_home"] == 1.09
    for r in rows:
        assert r["provenance"] == B.PROVENANCE_SIDECAR
        assert r["match_id"] == 4667815
        assert r["home"] == "Argentina" and r["away"] == "Austria"


def test_reconstruct_snapshots_fetch_ts_within_tick_span():
    detail = _fake_detail()
    ticks = ["2026-06-22T17:00:00Z", "2026-06-22T17:30:00Z", "2026-06-22T18:50:00Z"]
    rows = B.reconstruct_snapshots(detail, 1, "H", "A", ticks, asof_fn=_fake_asof)
    fts = [r["fetch_ts"] for r in rows]
    assert min(fts) >= min(ticks)
    assert max(fts) <= max(ticks)


def test_reconstruct_snapshots_empty_ticks_never_raises():
    detail = _fake_detail()
    rows = B.reconstruct_snapshots(detail, 1, "H", "A", [], asof_fn=_fake_asof)
    assert len(rows) == len(B._CHECKPOINT_MINUTES)


def test_write_sidecar_and_path_roundtrip(tmp_path):
    rows = [{"cutoff_min": 15.0, "xg_home": 0.1}]
    B.write_sidecar(123, rows, out_dir=tmp_path)
    p = B.backfill_sidecar_path(123, out_dir=tmp_path)
    assert p.is_file()
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["xg_home"] == 0.1


def test_backfill_all_resumable_skips_existing_sidecar(tmp_path):
    grade_dir = tmp_path / "grade"
    _write_jsonl(grade_dir / "KXWCGAME-26JUN22ARGAUT.jsonl", [
        {"ts": "2026-06-22T17:10:00Z", "model_prob": 0.5, "market_prob": 0.5},
    ])
    out_dir = tmp_path / "backfill"
    res = SoccerOutcomeResolver(finals_df=_finals_df())

    def fetch_matches(date_str):
        if date_str == "20260622":
            return [{"id": 4667815, "home": {"name": "Argentina"}, "away": {"name": "Austria"}}]
        return []

    def mtf(matches, home, away):
        for m in matches:
            if m["home"]["name"] == home and m["away"]["name"] == away:
                return m
        return None

    fetch_calls = {"n": 0}

    def fetch_detail(mid):
        fetch_calls["n"] += 1
        return _fake_detail()

    summary1 = B.backfill_all(grade_dir=grade_dir, out_dir=out_dir, resolver=res,
                              sleep_s=0.0, fetch_matches=fetch_matches, fetch_detail=fetch_detail,
                              match_to_fixture_fn=mtf, asof_fn=_fake_asof)
    assert summary1["n_fetched"] == 1
    assert summary1["n_written"] == 1
    assert fetch_calls["n"] == 1

    # Second pass: sidecar already exists -> resumable skip, NO new fetch.
    summary2 = B.backfill_all(grade_dir=grade_dir, out_dir=out_dir, resolver=res,
                              sleep_s=0.0, fetch_matches=fetch_matches, fetch_detail=fetch_detail,
                              match_to_fixture_fn=mtf, asof_fn=_fake_asof)
    assert summary2["n_skipped_existing"] == 1
    assert summary2["n_fetched"] == 0
    assert fetch_calls["n"] == 1


def test_backfill_all_force_refetches(tmp_path):
    grade_dir = tmp_path / "grade"
    _write_jsonl(grade_dir / "KXWCGAME-26JUN22ARGAUT.jsonl", [
        {"ts": "2026-06-22T17:10:00Z", "model_prob": 0.5, "market_prob": 0.5},
    ])
    out_dir = tmp_path / "backfill"
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    fetch_calls = {"n": 0}

    def fetch_detail(mid):
        fetch_calls["n"] += 1
        return _fake_detail()

    kwargs = dict(
        grade_dir=grade_dir, out_dir=out_dir, resolver=res, sleep_s=0.0,
        fetch_matches=lambda d: [{"id": 1, "home": {"name": "Argentina"}, "away": {"name": "Austria"}}]
        if d == "20260622" else [],
        fetch_detail=fetch_detail,
        match_to_fixture_fn=lambda matches, h, a: next(
            (m for m in matches if m["home"]["name"] == h and m["away"]["name"] == a), None),
        asof_fn=_fake_asof,
    )
    B.backfill_all(**kwargs)
    assert fetch_calls["n"] == 1
    B.backfill_all(**kwargs, force=True)
    assert fetch_calls["n"] == 2


def test_backfill_all_budget_caps_new_fetches(tmp_path):
    grade_dir = tmp_path / "grade"
    _write_jsonl(grade_dir / "KXWCGAME-26JUN22ARGAUT.jsonl", [{"ts": "2026-06-22T17:00:00Z"}])
    _write_jsonl(grade_dir / "KXWCGAME-26JUN23ENGGHA.jsonl", [{"ts": "2026-06-23T12:00:00Z"}])
    finals = pd.DataFrame([
        {"event_id": "1", "date": "2026-06-22", "home_team": "Argentina", "away_team": "Austria",
         "home_score": 2.0, "away_score": 0.0, "status_name": "STATUS_FULL_TIME", "completed": True},
        {"event_id": "2", "date": "2026-06-23", "home_team": "England", "away_team": "Ghana",
         "home_score": 1.0, "away_score": 0.0, "status_name": "STATUS_FULL_TIME", "completed": True},
    ])
    res = SoccerOutcomeResolver(finals_df=finals)
    fetch_calls = {"n": 0}

    def fetch_matches(date_str):
        if date_str == "20260622":
            return [{"id": 1, "home": {"name": "Argentina"}, "away": {"name": "Austria"}}]
        if date_str == "20260623":
            return [{"id": 2, "home": {"name": "England"}, "away": {"name": "Ghana"}}]
        return []

    def fetch_detail(mid):
        fetch_calls["n"] += 1
        return _fake_detail()

    summary = B.backfill_all(
        grade_dir=grade_dir, out_dir=tmp_path / "backfill", resolver=res, sleep_s=0.0, budget=1,
        fetch_matches=fetch_matches, fetch_detail=fetch_detail,
        match_to_fixture_fn=lambda matches, h, a: next(
            (m for m in matches if m["home"]["name"] == h and m["away"]["name"] == a), None),
        asof_fn=_fake_asof,
    )
    assert summary["n_fetched"] == 1
    assert fetch_calls["n"] == 1


def test_backfill_all_no_grade_dir_is_honest_empty(tmp_path):
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    summary = B.backfill_all(grade_dir=tmp_path / "absent", out_dir=tmp_path / "out", resolver=res,
                             sleep_s=0.0)
    assert summary["n_tickers"] == 0
    assert summary["errors"] == []


def test_backfill_all_never_raises_on_detail_fetch_exception(tmp_path):
    grade_dir = tmp_path / "grade"
    _write_jsonl(grade_dir / "KXWCGAME-26JUN22ARGAUT.jsonl", [{"ts": "2026-06-22T17:00:00Z"}])
    res = SoccerOutcomeResolver(finals_df=_finals_df())

    def boom(mid):
        raise RuntimeError("network flake")

    summary = B.backfill_all(
        grade_dir=grade_dir, out_dir=tmp_path / "out", resolver=res, sleep_s=0.0,
        fetch_matches=lambda d: [{"id": 1, "home": {"name": "Argentina"}, "away": {"name": "Austria"}}]
        if d == "20260622" else [],
        fetch_detail=boom,
        match_to_fixture_fn=lambda matches, h, a: next(
            (m for m in matches if m["home"]["name"] == h and m["away"]["name"] == a), None),
        asof_fn=_fake_asof,
    )
    assert summary["n_written"] == 0
    assert len(summary["errors"]) == 1
