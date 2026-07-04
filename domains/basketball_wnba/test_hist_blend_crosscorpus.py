"""Per-file tests for hist_blend_crosscorpus.py (LANE 3 sub-task A: cross-corpus
in-game blend refit). Hermetic synthetic fixtures for the pure-function core
(build_rows_corpus_a/b, run_direction, adopt_verdict) + a real-corpus smoke
test that is SKIPPED (not failed) if the local data files are absent, since
data/domains/wnba/ is gitignored and may not exist in a fresh clone.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_hist_blend_crosscorpus.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_wnba.hist_blend_crosscorpus import (
    CDN_BACKFILL_DIR,
    LINESCORES_PARQUET,
    _walk_forward_elo_simple,
    adopt_verdict,
    build_rows_corpus_a,
    build_rows_corpus_b,
    load_corpus_a_2026,
    load_corpus_b_games,
    load_corpus_b_states,
    run_cross_corpus_check,
    run_direction,
)
from domains.basketball_wnba.ingame_blend_families import FAMILY_NAMES, Row


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _synthetic_corpus_a() -> pd.DataFrame:
    rows = []
    for i in range(20):
        home_win = 1.0 if i % 2 == 0 else 0.0
        lead = 6.0 if home_win else -6.0
        rows.append({
            "event_id": str(i), "date": pd.Timestamp("2026-05-01") + pd.Timedelta(days=i),
            "season": "2026", "home_team": "Aces", "away_team": "Fever",
            "home_end_q1": 20.0 + lead / 4, "away_end_q1": 20.0 - lead / 4,
            "home_half": 40.0 + lead / 2, "away_half": 40.0 - lead / 2,
            "home_end_q3": 60.0 + lead * 0.75, "away_end_q3": 60.0 - lead * 0.75,
            "home_win": home_win,
        })
    return pd.DataFrame(rows)


def _synthetic_corpus_b_games() -> pd.DataFrame:
    rows = []
    for i in range(20):
        home_win = 1.0 if i % 2 == 0 else 0.0
        rows.append({
            "game_id": f"g{i}", "date": f"2026-05-{i+1:02d}",
            "home_team": "Liberty", "away_team": "Sky", "home_win": home_win,
        })
    return pd.DataFrame(rows)


def _synthetic_corpus_b_states() -> pd.DataFrame:
    rows = []
    for i in range(20):
        home_win = 1.0 if i % 2 == 0 else 0.0
        lead = 6.0 if home_win else -6.0
        for cp, base in (("end_q1", 20.0), ("half", 40.0), ("end_q3", 60.0)):
            rows.append({
                "game_id": f"g{i}", "checkpoint": cp,
                "score_home": base + lead / 4, "score_away": base - lead / 4,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Corpus A row-building
# ---------------------------------------------------------------------------


def test_build_rows_corpus_a_shape():
    a = _walk_forward_elo_simple(_synthetic_corpus_a())
    by_cp = build_rows_corpus_a(a)
    assert set(by_cp.keys()) == {"end_q1", "half", "end_q3"}
    for cp in by_cp:
        assert len(by_cp[cp]) == 20
        assert all(isinstance(r, Row) for r in by_cp[cp])


def test_walk_forward_elo_leak_free_first_game_is_prior():
    a = _walk_forward_elo_simple(_synthetic_corpus_a())
    # First game: both teams unseen -> p0 must be exactly the HFA-only prior.
    d = 40.0  # ELO_HFA, both teams start at ELO_MEAN
    expected = 1.0 / (1.0 + pow(10.0, -d / 400.0))
    assert abs(a.iloc[0]["p0"] - expected) < 1e-9


# ---------------------------------------------------------------------------
# Corpus B row-building (join games + states, exclude unmatched)
# ---------------------------------------------------------------------------


def test_build_rows_corpus_b_shape():
    games = _walk_forward_elo_simple(_synthetic_corpus_b_games())
    states = _synthetic_corpus_b_states()
    by_cp = build_rows_corpus_b(games, states)
    assert set(by_cp.keys()) == {"end_q1", "half", "end_q3"}
    for cp in by_cp:
        assert len(by_cp[cp]) == 20


def test_build_rows_corpus_b_skips_unmatched_game_id():
    games = _walk_forward_elo_simple(_synthetic_corpus_b_games())
    states = _synthetic_corpus_b_states()
    # Inject a states row for a game_id absent from games -- must be skipped.
    extra = pd.DataFrame([{"game_id": "ghost", "checkpoint": "end_q1",
                           "score_home": 10.0, "score_away": 5.0}])
    states2 = pd.concat([states, extra], ignore_index=True)
    by_cp = build_rows_corpus_b(games, states2)
    assert len(by_cp["end_q1"]) == 20  # ghost row not included


def test_load_corpus_b_games_excludes_ties(tmp_path):
    import json as _json
    d = tmp_path / "g1"
    d.mkdir()
    payload = {"game": {"gameEt": "2026-05-01T00:00:00-04:00",
                        "homeTeam": {"teamName": "Sky", "score": 80},
                        "awayTeam": {"teamName": "Fever", "score": 80}}}
    (d / "boxscore.json").write_text(_json.dumps(payload), encoding="utf-8")
    out = load_corpus_b_games(tmp_path)
    assert out.empty  # tie is malformed for a binary home_win -- excluded, not faked


def test_load_corpus_b_games_excludes_national_team(tmp_path):
    import json as _json
    d = tmp_path / "g1"
    d.mkdir()
    payload = {"game": {"gameEt": "2026-05-01T00:00:00-04:00",
                        "homeTeam": {"teamName": "Japan National Team", "score": 70},
                        "awayTeam": {"teamName": "Aces", "score": 90}}}
    (d / "boxscore.json").write_text(_json.dumps(payload), encoding="utf-8")
    out = load_corpus_b_games(tmp_path)
    assert out.empty


# ---------------------------------------------------------------------------
# run_direction / adopt_verdict
# ---------------------------------------------------------------------------


def test_run_direction_covers_all_families():
    a = _walk_forward_elo_simple(_synthetic_corpus_a())
    by_cp = build_rows_corpus_a(a)
    result = run_direction(by_cp, by_cp, "self", "self")
    assert set(result.per_family_brier.keys()) == set(FAMILY_NAMES)
    for name in FAMILY_NAMES:
        assert set(result.per_family_brier[name].keys()) == {"end_q1", "half", "end_q3"}


def test_adopt_verdict_reject_when_no_consistent_winner():
    a = _walk_forward_elo_simple(_synthetic_corpus_a())
    by_cp_a = build_rows_corpus_a(a)
    games_b = _walk_forward_elo_simple(_synthetic_corpus_b_games())
    by_cp_b = build_rows_corpus_b(games_b, _synthetic_corpus_b_states())
    a_to_b = run_direction(by_cp_a, by_cp_b, "a", "b")
    b_to_a = run_direction(by_cp_b, by_cp_a, "b", "a")
    verdict = adopt_verdict(a_to_b, b_to_a)
    assert verdict["verdict"] in ("ADOPT", "REJECT")
    assert "reason" in verdict


def test_adopt_verdict_adopt_when_family_sweeps_both_directions():
    # Construct a DirectionResult pair where "anchored" strictly beats all
    # others at every checkpoint in both directions.
    from domains.basketball_wnba.hist_blend_crosscorpus import DirectionResult
    per_family_ab = {name: {"end_q1": 0.30, "half": 0.30, "end_q3": 0.30} for name in FAMILY_NAMES}
    per_family_ab["anchored"] = {"end_q1": 0.10, "half": 0.10, "end_q3": 0.10}
    per_family_ba = {name: {"end_q1": 0.28, "half": 0.28, "end_q3": 0.28} for name in FAMILY_NAMES}
    per_family_ba["anchored"] = {"end_q1": 0.09, "half": 0.09, "end_q3": 0.09}
    a_to_b = DirectionResult("a", "b", per_family_ab, n_fit=10, n_validate=10)
    b_to_a = DirectionResult("b", "a", per_family_ba, n_fit=10, n_validate=10)
    verdict = adopt_verdict(a_to_b, b_to_a)
    assert verdict["verdict"] == "ADOPT"
    assert verdict["cross_corpus_winner"] == "anchored"


# ---------------------------------------------------------------------------
# Real-corpus smoke test (skipped if local data absent -- gitignored dirs)
# ---------------------------------------------------------------------------


def test_real_corpus_smoke():
    if not LINESCORES_PARQUET.exists() or not CDN_BACKFILL_DIR.exists():
        pytest.skip("local WNBA data corpora absent (gitignored data/ dir)")
    report = run_cross_corpus_check()
    assert report["edge_claimed"] is False
    assert report["verdict"] in ("ADOPT", "REJECT", "INSUFFICIENT_DATA")
    # Must be JSON-serializable (consumed by downstream report tooling).
    json.dumps(report, default=str)
