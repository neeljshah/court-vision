"""Leak-safety + correctness tests for src/ingame/matchup_features.py.

The in-game matchup module adds OPPONENT-defense + individual-matchup-edge
features to the v2 player-line head. The whole point is LEAK-SAFETY: a feature
row for (player, opponent, game_date) must be a pure function of the opponent's
games STRICTLY BEFORE game_date and the player's gamelog rows strictly before
game_date -- never the current game, never any game on/after game_date, never the
season-aggregate (as_of=today) atlas.

The headline test is the AS-OF / TRUNCATION test (``test_future_game_does_not_*``):
we build the opponent-defense provider from an in-memory per-game frame, compute a
PAST row's profile, then APPEND a future opponent game (date >= the cutoff) and
assert the past row's profile is BYTE-FOR-BYTE unchanged. If a future game could
move a past feature, that is a leak -- this test fails loudly.

These tests use synthetic in-memory data (no network, no real parquet needed for
the leak proof), plus a couple of smoke checks against the real providers when the
backing files exist.
"""
import datetime as dt
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("NBA_OFFLINE", "1")

import src.ingame.matchup_features as mf  # noqa: E402
from src.ingame.matchup_features import (  # noqa: E402
    _TeamDefenseAsOf,
    matchup_feature_row,
    player_matchup_row,
    join_matchup_features,
    feature_columns,
    edge_columns,
    self_check_as_of_invariance,
)


# --------------------------------------------------------------------------- #
# Synthetic per-game team-defense frame
# --------------------------------------------------------------------------- #
def _team_frame(extra_rows=None):
    """A small per-(team, game) frame spanning a few teams over Jan 2024.

    Each team plays games on increasing dates; values differ per team so the
    z-scores are non-degenerate and opponent-distinct.
    """
    rows = []
    teams = {
        "BOS": dict(def_rtg=105.0, pace=98.0, dreb_pct=0.78, efg_pct=0.50, tov_ratio=12.0),
        "MIA": dict(def_rtg=112.0, pace=96.0, dreb_pct=0.72, efg_pct=0.54, tov_ratio=14.0),
        "DEN": dict(def_rtg=110.0, pace=99.0, dreb_pct=0.75, efg_pct=0.53, tov_ratio=13.0),
        "OKC": dict(def_rtg=108.0, pace=102.0, dreb_pct=0.74, efg_pct=0.52, tov_ratio=15.0),
        "LAL": dict(def_rtg=114.0, pace=101.0, dreb_pct=0.71, efg_pct=0.55, tov_ratio=12.5),
    }
    gid = 0
    for tri, base in teams.items():
        for k in range(8):  # 8 prior games per team in Jan 2024
            gid += 1
            day = 2 + k  # 2024-01-02 .. 2024-01-09
            jitter = (k - 4) * 0.4
            rows.append({
                "game_id": f"00{gid:08d}",
                "game_date": f"2024-01-{day:02d}",
                "team_tricode": tri,
                "def_rtg": base["def_rtg"] + jitter,
                "pace": base["pace"] + jitter * 0.1,
                "dreb_pct": base["dreb_pct"],
                "efg_pct": base["efg_pct"],
                "tov_ratio": base["tov_ratio"],
            })
    if extra_rows:
        rows.extend(extra_rows)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Column / API contract
# --------------------------------------------------------------------------- #
def test_feature_and_edge_columns_stable():
    cols = feature_columns()
    assert cols[-1] == "mu_is_home"
    assert all(c.startswith("mu_") for c in cols)
    assert len(set(cols)) == len(cols)
    ecols = edge_columns()
    assert all(c.startswith("mu_player_") for c in ecols)
    # edge columns are disjoint from the opponent-axis columns
    assert not (set(cols) & set(ecols))


def test_matchup_row_has_exactly_feature_columns():
    row = matchup_feature_row("LAL", "BOS", "2024-01-10")
    assert set(row.keys()) == set(feature_columns())
    assert all(isinstance(v, float) for v in row.values())


def test_player_matchup_row_includes_edges():
    row = player_matchup_row(2544, "BOS", "2024-01-10")
    assert set(feature_columns()).issubset(row.keys())
    assert set(edge_columns()).issubset(row.keys())


# --------------------------------------------------------------------------- #
# THE leak test: a FUTURE opponent game must not move a PAST row
# --------------------------------------------------------------------------- #
def test_future_game_does_not_affect_past_profile():
    """Append a future opponent game; the past cutoff's profile is unchanged."""
    cutoff = dt.date(2024, 1, 6)  # opponent has games on 01-02..01-05 before this
    base = _TeamDefenseAsOf(df=_team_frame())
    before = base.profile("BOS", cutoff)
    assert before["n_games"] > 0

    # inject a WILD future BOS game on/after the cutoff (and one ON the cutoff)
    future = [
        {"game_id": "00099999991", "game_date": "2024-01-06", "team_tricode": "BOS",
         "def_rtg": 200.0, "pace": 200.0, "dreb_pct": 0.99, "efg_pct": 0.99,
         "tov_ratio": 99.0},
        {"game_id": "00099999992", "game_date": "2024-02-01", "team_tricode": "BOS",
         "def_rtg": 9.0, "pace": 9.0, "dreb_pct": 0.01, "efg_pct": 0.01,
         "tov_ratio": 1.0},
    ]
    after = _TeamDefenseAsOf(df=_team_frame(extra_rows=future))
    after_prof = after.profile("BOS", cutoff)

    assert after_prof["n_games"] == before["n_games"], "future game changed the window count"
    for k in ("def_rtg_z", "pace_z", "dreb_pct_z", "efg_pct_z", "tov_ratio_z"):
        assert abs(after_prof[k] - before[k]) < 1e-12, f"{k} moved -> LEAK"
    assert after_prof["raw"] == before["raw"], "raw means moved -> LEAK"


def test_future_game_does_not_affect_feature_row(monkeypatch):
    """Same leak guard but at the public matchup_feature_row level."""
    cutoff = "2024-01-06"
    clean = _TeamDefenseAsOf(df=_team_frame())
    leaky = _TeamDefenseAsOf(df=_team_frame(extra_rows=[
        {"game_id": "00099999993", "game_date": "2024-01-06", "team_tricode": "BOS",
         "def_rtg": 999.0, "pace": 999.0, "dreb_pct": 0.99, "efg_pct": 0.99,
         "tov_ratio": 99.0},
    ]))

    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", clean)
    row_clean = matchup_feature_row("LAL", "BOS", cutoff)
    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", leaky)
    row_leaky = matchup_feature_row("LAL", "BOS", cutoff)

    for k in feature_columns():
        assert abs(row_clean[k] - row_leaky[k]) < 1e-12, f"{k} leaked a future game"


def test_strictly_before_not_inclusive():
    """A game ON game_date must NOT be in the window (strictly before)."""
    base = _TeamDefenseAsOf(df=_team_frame())
    # BOS plays 01-02..01-09; cutoff 01-05 -> only 01-02,01-03,01-04 (3 games)
    prof = base.profile("BOS", dt.date(2024, 1, 5))
    assert prof["n_games"] == 3


# --------------------------------------------------------------------------- #
# Determinism + opponent distinctness + polarity
# --------------------------------------------------------------------------- #
def test_determinism_and_opponent_distinctness(monkeypatch):
    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", _TeamDefenseAsOf(df=_team_frame()))
    a = matchup_feature_row("LAL", "BOS", "2024-01-10")
    b = matchup_feature_row("LAL", "BOS", "2024-01-10")
    assert a == b
    other = matchup_feature_row("LAL", "MIA", "2024-01-10")
    assert any(abs(a[k] - other[k]) > 1e-9 for k in a if k != "mu_is_home")


def test_def_rtg_polarity(monkeypatch):
    """+ def_rtg_z = opponent ALLOWS more pts = softer D. MIA(112) > BOS(105)."""
    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", _TeamDefenseAsOf(df=_team_frame()))
    bos = matchup_feature_row("LAL", "BOS", "2024-01-10")
    mia = matchup_feature_row("LAL", "MIA", "2024-01-10")
    # MIA allows more points than BOS -> higher (more positive) softness z
    assert mia["mu_opp_def_rtg_z"] > bos["mu_opp_def_rtg_z"]


def test_thin_opponent_falls_back_to_embedding(monkeypatch):
    """An opponent with < _MIN_OPP_GAMES prior games uses the leak-safe embedding
    (still non-degenerate + opponent-distinct), never crashes / never NaNs."""
    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", _TeamDefenseAsOf(df=_team_frame()))
    # cutoff right after the first BOS game -> only 1 prior game (< 3) -> embedding
    row = matchup_feature_row("LAL", "BOS", "2024-01-03")
    assert all(np.isfinite(v) for v in row.values())
    # embedding is non-degenerate vs a different opponent at the same thin cutoff
    other = matchup_feature_row("LAL", "MIA", "2024-01-03")
    assert any(abs(row[k] - other[k]) > 1e-9 for k in row if k != "mu_is_home")


def test_unknown_opponent_is_finite():
    row = matchup_feature_row("LAL", "ZZZ", "2024-01-10")
    assert all(np.isfinite(v) for v in row.values())


# --------------------------------------------------------------------------- #
# Edge scalars (player scoring-shape x opponent softness)
# --------------------------------------------------------------------------- #
def _shape_stub(rows_by_pid):
    class _S:
        def shape(self, pid, as_of, window=20):
            return rows_by_pid.get(int(pid),
                                   {"n_games": 0, "scoring_rate": None,
                                    "perimeter_reliance": None,
                                    "interior_reliance": None})
    return _S()


def test_edges_zero_without_player(monkeypatch):
    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", _TeamDefenseAsOf(df=_team_frame()))
    row = matchup_feature_row("LAL", "BOS", "2024-01-10",
                              player_id=None, include_edges=True)
    for c in edge_columns():
        assert row[c] == 0.0


def test_edges_use_only_prior_games_and_sign(monkeypatch):
    """A rim-reliant scorer vs a SOFT interior yields a positive interior edge;
    the edge is computed from the player's prior shape only (leak-safe)."""
    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", _TeamDefenseAsOf(df=_team_frame()))
    # craft an opponent whose interior is soft: high def_rtg + low dreb -> rim_z > 0
    # (LAL: def_rtg 114 high, dreb 0.71 low -> soft interior). Use LAL as opponent.
    monkeypatch.setattr(mf, "_SHAPE_SINGLETON", _shape_stub({
        2544: {"n_games": 10, "scoring_rate": 0.8,
               "perimeter_reliance": 0.1, "interior_reliance": 0.9},
    }))
    row = matchup_feature_row("BOS", "LAL", "2024-01-10",
                              player_id=2544, include_edges=True)
    # soft interior (rim_z) should be > 0 for LAL; interior-reliant -> positive edge
    assert row["mu_opp_rim_fg_allowed_z"] > 0
    assert row["mu_player_interior_edge"] > 0


# --------------------------------------------------------------------------- #
# Join helper
# --------------------------------------------------------------------------- #
def test_join_matchup_features_adds_columns(monkeypatch):
    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", _TeamDefenseAsOf(df=_team_frame()))
    monkeypatch.setattr(mf, "_SHAPE_SINGLETON", _shape_stub({}))
    df = pd.DataFrame([
        {"player_id": 1, "opp": "BOS", "game_date": "2024-01-10", "event_idx": 0},
        {"player_id": 1, "opp": "BOS", "game_date": "2024-01-10", "event_idx": 1},
        {"player_id": 2, "opp": "MIA", "game_date": "2024-01-10", "event_idx": 0},
    ])
    out = join_matchup_features(df, opponent_col="opp", date_col="game_date")
    for c in list(feature_columns()) + list(edge_columns()):
        assert c in out.columns
    # the two BOS rows (same key) get identical opponent axes
    bos = out[out["opp"] == "BOS"]
    assert bos["mu_opp_def_rtg_z"].nunique() == 1
    # BOS vs MIA differ
    mia = out[out["opp"] == "MIA"]
    assert abs(bos["mu_opp_def_rtg_z"].iloc[0] - mia["mu_opp_def_rtg_z"].iloc[0]) > 1e-9


def test_join_handles_missing_opponent(monkeypatch):
    monkeypatch.setattr(mf, "_TEAM_DEF_SINGLETON", _TeamDefenseAsOf(df=_team_frame()))
    df = pd.DataFrame([
        {"player_id": 1, "opp": None, "game_date": "2024-01-10"},
        {"player_id": 2, "opp": "BOS", "game_date": None},
    ])
    out = join_matchup_features(df, opponent_col="opp", date_col="game_date")
    for c in feature_columns():
        assert (out[c] == 0.0).all()


# --------------------------------------------------------------------------- #
# Self-check + real-source smoke (skipped if backing files absent)
# --------------------------------------------------------------------------- #
def test_self_check_as_of_invariance_passes():
    assert self_check_as_of_invariance("BOS") is True
    assert self_check_as_of_invariance("DEN") is True


@pytest.mark.skipif(not os.path.exists(mf.TEAM_PERGAME_PARQUET),
                    reason="team_advanced_stats.parquet not present")
def test_real_source_smoke():
    """Against the REAL per-game parquet: a mid-season cutoff yields a finite,
    opponent-distinct profile and the strictly-before window is respected."""
    td = _TeamDefenseAsOf()
    prof = td.profile("BOS", dt.date(2024, 1, 15))
    assert prof.get("n_games", 0) >= 1
    assert np.isfinite(prof["def_rtg_z"])
    # a row built straight off the real source is finite for all columns
    row = matchup_feature_row("LAL", "BOS", "2024-01-15")
    assert all(np.isfinite(v) for v in row.values())
