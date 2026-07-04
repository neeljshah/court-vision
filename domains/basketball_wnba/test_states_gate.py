"""Per-file tests for states_gate.py (LANE 5: WNBA states gate -- run_last_3min
/ in_bonus additive terms on the frozen ANCHORED blend, cross-fitted md5
halves).

Hermetic: synthetic games/linescores/states DataFrames + a fake join map (no
real cdn_backfill/ boxscore reads, no network). Covers: half assignment
determinism, join-guard behavior (unmatched games dropped not faked),
crossfit no-leak (fit half never scores its own eval half), the INSUFFICIENT
floor, and descriptive-stats shape.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_states_gate.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_wnba.ingame_blend import LiveState, blend_prob
from domains.basketball_wnba.ingame_blend_families import build_corpus_with_p0
from domains.basketball_wnba.states_gate import (
    CHECKPOINTS,
    Row,
    build_rows,
    crossfit_checkpoint_feature,
    descriptive_stats,
    fit_coef,
    half_of,
)


# ---------------------------------------------------------------------------
# half_of determinism
# ---------------------------------------------------------------------------


def test_half_of_is_deterministic_and_binary():
    for eid in ["401649378", "1012600001", "0", "abc123"]:
        h1 = half_of(eid)
        h2 = half_of(eid)
        assert h1 == h2
        assert h1 in (0, 1)


def test_half_of_splits_a_population_into_both_halves():
    halves = {half_of(str(i)) for i in range(200)}
    assert halves == {0, 1}  # both halves populated over a large id range


# ---------------------------------------------------------------------------
# synthetic corpus fixtures
# ---------------------------------------------------------------------------


def _synthetic_games(n: int = 40) -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-05-01")
    for i in range(n):
        home_win = 1.0 if i % 2 == 0 else 0.0
        hs, as_ = (85.0, 78.0) if home_win else (78.0, 85.0)
        rows.append({
            "event_id": str(1000 + i), "date": base + pd.Timedelta(days=i),
            "season": "2026", "home_team": "Aces", "away_team": "Fever",
            "home_score": hs, "away_score": as_, "home_win": home_win,
            "neutral_site": False, "status_name": "STATUS_FINAL",
        })
    return pd.DataFrame(rows)


def _synthetic_linescores(games_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in games_df.iterrows():
        lead = 6.0 if g["home_win"] >= 0.5 else -6.0
        rows.append({
            "event_id": str(g["event_id"]),
            "home_end_q1": 20.0 + lead / 4, "away_end_q1": 20.0 - lead / 4,
            "home_half": 40.0 + lead / 2, "away_half": 40.0 - lead / 2,
            "home_end_q3": 60.0 + lead * 0.75, "away_end_q3": 60.0 - lead * 0.75,
        })
    return pd.DataFrame(rows)


def _synthetic_states(games_df: pd.DataFrame) -> pd.DataFrame:
    """One CDN-style states row per (game, checkpoint). game_id == event_id
    for test simplicity -- build_rows only cares about the join map, tested
    separately in test_states_gate_join.py."""
    rows = []
    for _, g in games_df.iterrows():
        run_sign = 1.0 if g["home_win"] >= 0.5 else -1.0
        for cp in CHECKPOINTS:
            rows.append({
                "game_id": str(g["event_id"]), "checkpoint": cp,
                "run_last_3min": run_sign * 4.0,
                "in_bonus_home": True, "in_bonus_away": False,
            })
    return pd.DataFrame(rows)


@pytest.fixture()
def synthetic_corpus():
    games = _synthetic_games()
    lines = _synthetic_linescores(games)
    states = _synthetic_states(games)
    join_map = {str(e): str(e) for e in games["event_id"]}
    games_with_p0 = build_corpus_with_p0(games, "2026")
    return games_with_p0, lines, states, join_map


# ---------------------------------------------------------------------------
# build_rows / join guard
# ---------------------------------------------------------------------------


def test_build_rows_one_row_per_game_per_checkpoint(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    assert len(rows) == len(games_with_p0) * len(CHECKPOINTS)


def test_build_rows_p_anchored_matches_frozen_blend(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    row = next(r for r in rows if r.checkpoint == "end_q1")
    p0 = float(games_with_p0.loc[games_with_p0["event_id"] == row.event_id, "p_home_elo"].iloc[0])
    ls = lines[lines["event_id"] == row.event_id].iloc[0]
    diff = float(ls["home_end_q1"]) - float(ls["away_end_q1"])
    expected = blend_prob(p0, LiveState(period=1, clock_s=0.0, home_score=diff, away_score=0.0))
    assert row.p_anchored == pytest.approx(expected)


def test_build_rows_drops_unjoined_games_never_fabricates(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    partial_map = {k: v for i, (k, v) in enumerate(join_map.items()) if i < 5}
    rows = build_rows(games_with_p0, lines, states, partial_map)
    assert len(rows) == 5 * len(CHECKPOINTS)


def test_build_rows_empty_join_map_yields_no_rows(synthetic_corpus):
    games_with_p0, lines, states, _ = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, {})
    assert rows == []


# ---------------------------------------------------------------------------
# fit_coef determinism + grid always contains 0.0
# ---------------------------------------------------------------------------


def test_fit_coef_is_deterministic(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    cp_rows = [r for r in rows if r.checkpoint == "end_q1"]
    c1 = fit_coef(cp_rows, "run_last_3min")
    c2 = fit_coef(cp_rows, "run_last_3min")
    assert c1 == c2


def test_fit_coef_unknown_feature_raises(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    with pytest.raises(ValueError):
        fit_coef(rows, "nonexistent_feature")


# ---------------------------------------------------------------------------
# crossfit: no-leak + floor
# ---------------------------------------------------------------------------


def test_crossfit_insufficient_below_floor(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    # synthetic corpus has ~20 games/half -- well under the 40-floor default.
    result = crossfit_checkpoint_feature(rows, "end_q1", "run_last_3min")
    assert result.verdict == "INSUFFICIENT"
    assert result.brier_anchored_h1 is None
    assert result.brier_with_term_h1 is None


def test_crossfit_below_custom_lower_floor_runs_both_directions(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    result = crossfit_checkpoint_feature(rows, "end_q1", "run_last_3min", min_n_per_half=5)
    assert result.verdict != "INSUFFICIENT"
    assert result.brier_anchored_h1 is not None
    assert result.brier_with_term_h1 is not None
    assert result.brier_anchored_h0 is not None
    assert result.brier_with_term_h0 is not None


def test_crossfit_fit_half_never_equals_eval_half(synthetic_corpus):
    """No-leak guard: the h0-fit coefficient must be computed ONLY from h0
    rows (never touching h1 outcomes), verified by refitting directly."""
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    cp_rows = [r for r in rows if r.checkpoint == "end_q1"]
    h0 = [r for r in cp_rows if r.half == 0]
    h1 = [r for r in cp_rows if r.half == 1]
    assert h0 and h1
    assert set(r.event_id for r in h0).isdisjoint(set(r.event_id for r in h1))

    result = crossfit_checkpoint_feature(rows, "end_q1", "run_last_3min", min_n_per_half=1)
    direct_coef_h0 = fit_coef(h0, "run_last_3min")
    direct_coef_h1 = fit_coef(h1, "run_last_3min")
    assert result.coef_fit_on_h0 == direct_coef_h0
    assert result.coef_fit_on_h1 == direct_coef_h1


def test_crossfit_zero_coef_reproduces_anchored_brier_when_feature_has_no_signal():
    """If a feature is pure noise (independent of outcome), the fit coefficient
    should stay near 0 and with-term Brier should not diverge wildly from the
    anchored baseline (sanity bound, not an exact-improvement claim)."""
    rows = []
    for i in range(30):
        outcome = float(i % 2 == 0)
        p_anchored = 0.5
        rows.append(Row(
            event_id=str(i), checkpoint="end_q1", p_anchored=p_anchored,
            outcome=outcome, run_last_3min=0.0, in_bonus_diff=0.0,
            half=(i % 2),
        ))
    result = crossfit_checkpoint_feature(rows, "end_q1", "run_last_3min", min_n_per_half=1)
    assert result.brier_with_term_h1 == pytest.approx(result.brier_anchored_h1)
    assert result.brier_with_term_h0 == pytest.approx(result.brier_anchored_h0)


# ---------------------------------------------------------------------------
# descriptive stats
# ---------------------------------------------------------------------------


def test_descriptive_stats_shape(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    stats = descriptive_stats(rows)
    assert set(stats.keys()) == set(CHECKPOINTS)
    for cp in CHECKPOINTS:
        assert stats[cp]["n"] == len(games_with_p0)
        assert 0.0 <= stats[cp]["frac_either_team_in_bonus"] <= 1.0


def test_descriptive_stats_empty_rows_reports_zero_n():
    stats = descriptive_stats([])
    for cp in CHECKPOINTS:
        assert stats[cp]["n"] == 0


# NOTE: run_gate/write_gate end-to-end tests (assembly + I/O) live in
# test_states_gate_runner.py, split out to keep this file under the LOC cap.
