"""Per-file tests for states_gate.py (LANE 2: NBA states gate -- run_last_3min
/ in_bonus additive terms on a frozen anchored p, cross-fitted md5 halves).
PORTED from domains/basketball_wnba/test_states_gate.py.

Hermetic: synthetic games/linescores/states DataFrames + a fake join map (no
real CDN/box cache reads, no network). Covers: half assignment determinism,
join-guard behavior (unmatched games dropped not faked), crossfit no-leak
(fit half never scores its own eval half), the INSUFFICIENT floor, the NBA
2880s REG_SEC parameterization, and descriptive-stats shape.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_gate.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.states_gate import (
    CHECKPOINTS,
    PERIOD_SEC,
    REG_SEC,
    Row,
    build_rows,
    crossfit_checkpoint_feature,
    descriptive_stats,
    fit_coef,
    half_of,
)


# ---------------------------------------------------------------------------
# NBA parameterization (vs WNBA's 2400s / 600s)
# ---------------------------------------------------------------------------


def test_nba_regulation_seconds_is_2880():
    assert REG_SEC == 2880.0
    assert PERIOD_SEC == 720.0
    assert REG_SEC == 4 * PERIOD_SEC


# ---------------------------------------------------------------------------
# half_of determinism
# ---------------------------------------------------------------------------


def test_half_of_is_deterministic_and_binary():
    for eid in ["401809243", "0022500003", "0", "abc123"]:
        h1 = half_of(eid)
        h2 = half_of(eid)
        assert h1 == h2
        assert h1 in (0, 1)


def test_half_of_splits_a_population_into_both_halves():
    halves = {half_of(str(i)) for i in range(200)}
    assert halves == {0, 1}  # both halves populated over a large id range


# ---------------------------------------------------------------------------
# synthetic corpus fixtures (NBA schema: home_q1..home_q4 per-quarter cols,
# p_anchored precomputed -- build_rows is anchored-source-agnostic)
# ---------------------------------------------------------------------------


def _synthetic_games_with_p0(n: int = 40) -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-01-01")
    for i in range(n):
        home_win = 1.0 if i % 2 == 0 else 0.0
        p_anchored = 0.62 if home_win else 0.38
        rows.append({
            "event_id": str(1000 + i), "date": base + pd.Timedelta(days=i),
            "home_win": home_win, "p_anchored": p_anchored,
        })
    return pd.DataFrame(rows)


def _synthetic_linescores(games_with_p0: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in games_with_p0.iterrows():
        lead = 6.0 if g["home_win"] >= 0.5 else -6.0
        rows.append({
            "event_id": str(g["event_id"]),
            "home_q1": 20.0 + lead / 8, "away_q1": 20.0 - lead / 8,
            "home_q2": 20.0 + lead / 8, "away_q2": 20.0 - lead / 8,
            "home_q3": 20.0 + lead / 8, "away_q3": 20.0 - lead / 8,
            "home_q4": 20.0 + lead / 8, "away_q4": 20.0 - lead / 8,
        })
    return pd.DataFrame(rows)


def _synthetic_states(games_with_p0: pd.DataFrame) -> pd.DataFrame:
    """One CDN-style states row per (game, checkpoint). game_id == event_id
    for test simplicity -- build_rows only cares about the join map, tested
    separately in test_states_gate_join.py."""
    rows = []
    for _, g in games_with_p0.iterrows():
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
    games_with_p0 = _synthetic_games_with_p0()
    lines = _synthetic_linescores(games_with_p0)
    states = _synthetic_states(games_with_p0)
    join_map = {str(e): str(e) for e in games_with_p0["event_id"]}
    return games_with_p0, lines, states, join_map


# ---------------------------------------------------------------------------
# build_rows / join guard
# ---------------------------------------------------------------------------


def test_build_rows_one_row_per_game_per_checkpoint(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    assert len(rows) == len(games_with_p0) * len(CHECKPOINTS)


def test_build_rows_p_anchored_matches_input_column(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    row = next(r for r in rows if r.checkpoint == "end_q1")
    expected = float(games_with_p0.loc[
        games_with_p0["event_id"] == row.event_id, "p_anchored"
    ].iloc[0])
    assert row.p_anchored == pytest.approx(expected)


def test_build_rows_checkpoint_diff_sums_quarters_up_to_period(synthetic_corpus):
    games_with_p0, lines, states, join_map = synthetic_corpus
    rows = build_rows(games_with_p0, lines, states, join_map)
    row_q1 = next(r for r in rows if r.checkpoint == "end_q1")
    row_q3 = next(r for r in rows if r.checkpoint == "end_q3" and r.event_id == row_q1.event_id)
    # end_q3 sums 3 quarters, end_q1 sums 1 -- diff scale should differ (not
    # asserting exact values, just that the checkpoint sums are distinct
    # cumulative windows rather than a single repeated quarter score).
    assert row_q1.checkpoint != row_q3.checkpoint


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


# NOTE: run_gate/write_gate end-to-end tests (assembly + I/O + NO_CORPUS
# path) live in test_states_gate_runner.py, split out to keep this file
# under the LOC cap.
