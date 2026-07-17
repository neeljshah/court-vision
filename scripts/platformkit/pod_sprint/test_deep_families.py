"""Tests for scripts.platformkit.pod_sprint.deep_families."""

import numpy as np
import pandas as pd

from scripts.platformkit.models import gbm_nba_ml as g
from scripts.platformkit.pod_sprint import deep_families as df


def _box_row(date, home, away, hp, ap, fg3=(10.0, 25.0, 8.0, 24.0)):
    h3m, h3a, a3m, a3a = fg3
    return {
        "date": pd.Timestamp(date), "home_abbr": home, "away_abbr": away,
        "home_pts": float(hp), "away_pts": float(ap),
        "home_fg_attempted": 85.0, "home_ft_attempted": 20.0, "home_oreb": 10.0, "home_tov": 13.0,
        "away_fg_attempted": 85.0, "away_ft_attempted": 20.0, "away_oreb": 10.0, "away_tov": 13.0,
        "home_fg3m": h3m, "home_fg3a": h3a, "away_fg3m": a3m, "away_fg3a": a3a,
    }


def _season_box(n_per_team=20, seed=0):
    """A season with all 15 East teams round-robin-ish so an 8th seed always exists."""
    rng = np.random.default_rng(seed)
    east = [t for t, c in df._CONFERENCE.items() if c == "E"]
    rows, date = [], pd.Timestamp("2025-10-21")
    for _ in range(n_per_team):
        order = rng.permutation(east)
        for i in range(0, len(order) - 1, 2):
            hp, ap = rng.integers(95, 130), rng.integers(95, 130)
            rows.append(_box_row(date, order[i], order[i + 1], hp, ap))
        date += pd.Timedelta(days=1)  # one slate of games per day, like a real NBA night
    return pd.DataFrame(rows)


def test_tank_gradient_zero_before_70pct_of_season():
    box = _season_box(n_per_team=90)
    feat = df.build_features_deep(box)
    early = feat[feat["m3_season_phase"] <= 0.7]
    assert len(early) > 0
    assert (early["m1_tank_gradient_home"] == 0.0).all()
    assert (early["m1_tank_gradient_away"] == 0.0).all()
    late = feat[feat["m3_season_phase"] > 0.7]
    assert len(late) > 0
    assert (late["m1_tank_gradient_home"] >= 0.0).all()


def test_three_in_four_counting():
    """AAA plays on day 0, 1, 2, 3 (vs 4 different opponents) -- day 3's count must be 4
    (3 prior games within the trailing-4-day window + this one); day 10 (isolated) must be 1."""
    rows = [
        _box_row("2025-10-21", "AAA", "BBB", 100, 90),
        _box_row("2025-10-22", "CCC", "AAA", 90, 100),
        _box_row("2025-10-23", "AAA", "DDD", 100, 90),
        _box_row("2025-10-24", "AAA", "BBB", 100, 90),
        _box_row("2025-11-03", "AAA", "CCC", 100, 90),  # isolated, 10 days later
    ]
    box = pd.DataFrame(rows)
    feat = df.build_features_deep(box)
    assert feat.loc[3, "s1_three_in_four_home"] == 4.0
    assert feat.loc[4, "s1_three_in_four_home"] == 1.0


def test_pythag_gap_hand_check():
    """v2_pythag_gap = l10_wpct - PF^13.91/(PF^13.91+PA^13.91); hand-computed for a
    known 2-game PF/PA history, checked against the module's output on game 3."""
    rows = [
        _box_row("2025-10-21", "AAA", "BBB", 120, 100),
        _box_row("2025-10-23", "AAA", "CCC", 110, 90),
        _box_row("2025-10-25", "AAA", "DDD", 100, 100),  # game 3: read pregame state here
    ]
    box = pd.DataFrame(rows)
    feat = df.build_features_deep(box)
    base = g.build_features(box)
    pf, pa = 120.0 + 110.0, 100.0 + 90.0
    expected_pythag = pf ** 13.91 / (pf ** 13.91 + pa ** 13.91)
    expected_gap = float(base.loc[2, "l10_wpct_home"]) - expected_pythag
    assert abs(feat.loc[2, "v2_pythag_gap_home"] - expected_gap) < 1e-9


def test_capped_mov_elo_differs_only_on_blowouts():
    """Two teams: game 1 is a close game (margin 5, <=cap) -- elo must match the plain
    model exactly afterward. Game 2 is a blowout (margin 40, >cap) -- elo must then
    diverge from the plain model (the whole point of the cap)."""
    rows = [
        _box_row("2025-10-21", "AAA", "BBB", 100, 95),   # margin 5
        _box_row("2025-10-23", "AAA", "BBB", 130, 90),   # margin 40, blowout
    ]
    box = pd.DataFrame(rows)
    plain = g.build_features(box)
    capped = df.build_features_capped_mov(box, cap=20.0)
    # row 1 (before game 1) both start at init elo -- trivially equal; check AFTER game 1
    # by reading row index 1's pregame elo, which reflects game 0's update.
    assert abs(plain.loc[1, "elo_home"] - capped.loc[1, "elo_home"]) < 1e-9
    # a 3rd game would show divergence post-blowout; assert the two Elo TRAJECTORIES
    # differ once the blowout's update has been applied, i.e. compare the final model's
    # internal state by adding one more game and reading its pregame elo.
    rows.append(_box_row("2025-10-25", "AAA", "BBB", 100, 100))
    box3 = pd.DataFrame(rows)
    plain3 = g.build_features(box3)
    capped3 = df.build_features_capped_mov(box3, cap=20.0)
    assert abs(plain3.loc[2, "elo_home"] - capped3.loc[2, "elo_home"]) > 1e-6


def test_fg3_luck_neutral_when_columns_absent():
    """Premise-check: if the box corpus has no fg3m/fg3a columns, V1 must read a neutral
    0.0 everywhere instead of raising."""
    rows = [
        {k: v for k, v in _box_row("2025-10-21", "AAA", "BBB", 100, 95).items()
         if not k.startswith(("home_fg3", "away_fg3"))},
        {k: v for k, v in _box_row("2025-10-23", "AAA", "CCC", 100, 95).items()
         if not k.startswith(("home_fg3", "away_fg3"))},
    ]
    box = pd.DataFrame(rows)
    feat = df.build_features_deep(box)
    assert (feat["v1_fg3_luck_home"] == 0.0).all()
    assert (feat["v1_fg3_luck_away"] == 0.0).all()


def test_leak_trap_deep_pass_ignores_own_game():
    """Row i's deep-pass features must be identical regardless of game i's own score --
    only games strictly BEFORE i may influence row i. A later row for either team must
    shift, proving the state update itself is wired (just not leaking into row i)."""
    box = _season_box(n_per_team=6, seed=2)
    feat_a = df.build_features_deep(box)
    corrupted = box.copy()
    victim = 30
    corrupted.loc[victim, "home_pts"] = 999.0
    corrupted.loc[victim, "away_pts"] = 1.0
    feat_b = df.build_features_deep(corrupted)

    cols = sum(df.FAMILY_COLUMNS.values(), []) + ["x1_pace_product"]
    row_a = feat_a.loc[victim, cols]
    row_b = feat_b.loc[victim, cols]
    pd.testing.assert_series_equal(row_a, row_b)

    ht, at = box.loc[victim, "home_abbr"], box.loc[victim, "away_abbr"]
    later = box.loc[victim + 1:]
    hits = later[(later["home_abbr"].isin([ht, at])) | (later["away_abbr"].isin([ht, at]))]
    assert len(hits) > 0
    nxt = hits.index[0]
    assert not feat_a.loc[nxt, cols].equals(feat_b.loc[nxt, cols])


def test_build_features_deep_shape():
    box = _season_box(n_per_team=10, seed=3)
    feat = df.build_features_deep(box)
    all_cols = sum(df.FAMILY_COLUMNS.values(), [])
    assert set(all_cols) <= set(feat.columns)
    assert not feat[all_cols].isna().any().any()
    assert len(feat) == len(box)
