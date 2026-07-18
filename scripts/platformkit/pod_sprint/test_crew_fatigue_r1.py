"""Tests for scripts.platformkit.pod_sprint.crew_fatigue_r1: hand-computed rest days
+ b2b flag (any/all variants), and the mechanism-#54 team-baseline adjustment formula."""

import pandas as pd

from scripts.platformkit.pod_sprint.crew_fatigue_r1 import build_adjusted, crew_b2b_flags


def test_crew_b2b_hand_computed():
    """5 games, officials A-F. g1: all first appearances -> no b2b possible. g2: A
    worked g1 the day before (rest_days=0) but D/E are first appearances -> any=True,
    all=False. g3/g4: 3+ days rest -> no b2b. g5: both D and E have rest_days=0 ->
    any=True AND all=True."""
    crew_long = pd.DataFrame([
        {"game_id": "g1", "official": "A", "date": pd.Timestamp("2024-01-01")},
        {"game_id": "g1", "official": "B", "date": pd.Timestamp("2024-01-01")},
        {"game_id": "g1", "official": "C", "date": pd.Timestamp("2024-01-01")},
        {"game_id": "g2", "official": "A", "date": pd.Timestamp("2024-01-02")},
        {"game_id": "g2", "official": "D", "date": pd.Timestamp("2024-01-02")},
        {"game_id": "g2", "official": "E", "date": pd.Timestamp("2024-01-02")},
        {"game_id": "g3", "official": "B", "date": pd.Timestamp("2024-01-05")},
        {"game_id": "g3", "official": "C", "date": pd.Timestamp("2024-01-05")},
        {"game_id": "g3", "official": "F", "date": pd.Timestamp("2024-01-05")},
        {"game_id": "g4", "official": "D", "date": pd.Timestamp("2024-01-06")},
        {"game_id": "g4", "official": "E", "date": pd.Timestamp("2024-01-06")},
        {"game_id": "g5", "official": "D", "date": pd.Timestamp("2024-01-07")},
        {"game_id": "g5", "official": "E", "date": pd.Timestamp("2024-01-07")},
    ])
    # hand-computed rest_days: A's g2 rest = (01-02 - 01-01).days - 1 = 0
    c = crew_long.sort_values(["official", "date"]).copy()
    c["rest_days"] = c.groupby("official")["date"].diff().dt.days - 1
    a_g2 = c[(c.official == "A") & (c.game_id == "g2")]["rest_days"].iloc[0]
    assert a_g2 == 0
    d_g4 = c[(c.official == "D") & (c.game_id == "g4")]["rest_days"].iloc[0]
    assert d_g4 == 3  # (01-06 - 01-02).days - 1 = 3
    d_g5 = c[(c.official == "D") & (c.game_id == "g5")]["rest_days"].iloc[0]
    assert d_g5 == 0  # (01-07 - 01-06).days - 1 = 0

    flags = crew_b2b_flags(crew_long).set_index("game_id")
    assert flags.loc["g1", "crew_b2b_any"] == False  # noqa: E712 -- all first appearances
    assert flags.loc["g1", "crew_b2b_all"] == False  # noqa: E712
    assert flags.loc["g2", "crew_b2b_any"] == True  # noqa: E712 -- A is confirmed b2b
    assert flags.loc["g2", "crew_b2b_all"] == False  # noqa: E712 -- D/E unconfirmed (NaN)
    assert flags.loc["g3", "crew_b2b_any"] == False  # noqa: E712 -- 3 days rest, no b2b
    assert flags.loc["g4", "crew_b2b_any"] == False  # noqa: E712
    assert flags.loc["g5", "crew_b2b_any"] == True  # noqa: E712
    assert flags.loc["g5", "crew_b2b_all"] == True  # noqa: E712 -- both D and E at 0 rest


def test_build_adjusted_matches_hand_computed_loo():
    """3 games between team X and team Y, PF totals hand-picked so the leave-one-out
    (excluding the target game) season means are simple fractions. floor overridden
    to min_games=2 so the tiny 3-game synthetic season clears it."""
    box = pd.DataFrame([
        {"game_id": "g1", "team": "X", "season": "2099-00", "date": pd.Timestamp("2099-01-01"), "pf": 20.0},
        {"game_id": "g1", "team": "Y", "season": "2099-00", "date": pd.Timestamp("2099-01-01"), "pf": 18.0},
        {"game_id": "g2", "team": "X", "season": "2099-00", "date": pd.Timestamp("2099-01-02"), "pf": 24.0},
        {"game_id": "g2", "team": "Y", "season": "2099-00", "date": pd.Timestamp("2099-01-02"), "pf": 16.0},
        {"game_id": "g3", "team": "X", "season": "2099-00", "date": pd.Timestamp("2099-01-03"), "pf": 22.0},
        {"game_id": "g3", "team": "Y", "season": "2099-00", "date": pd.Timestamp("2099-01-03"), "pf": 20.0},
    ])
    out = build_adjusted(box, "pf", min_games=2).set_index("game_id")
    # g1: X LOO excl g1 = (24+22)/2=23, Y LOO excl g1 = (16+20)/2=18 -> lambda=41, observed=38 -> adj=-3
    assert abs(out.loc["g1", "adjusted_pf"] - (-3.0)) < 1e-9
    # g2: X LOO=(20+22)/2=21, Y LOO=(18+20)/2=19 -> lambda=40, observed=40 -> adj=0
    assert abs(out.loc["g2", "adjusted_pf"] - 0.0) < 1e-9
    # g3: X LOO=(20+24)/2=22, Y LOO=(18+16)/2=17 -> lambda=39, observed=42 -> adj=3
    assert abs(out.loc["g3", "adjusted_pf"] - 3.0) < 1e-9


def test_build_adjusted_drops_thin_seasons():
    """A team-season with fewer games than the floor is dropped entirely (LOO mean
    too unstable off 1 game)."""
    box = pd.DataFrame([
        {"game_id": "g1", "team": "X", "season": "2099-00", "date": pd.Timestamp("2099-01-01"), "pf": 20.0},
        {"game_id": "g1", "team": "Y", "season": "2099-00", "date": pd.Timestamp("2099-01-01"), "pf": 18.0},
    ])
    out = build_adjusted(box, "pf", min_games=2)
    assert out.empty
