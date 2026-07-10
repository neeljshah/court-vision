"""Per-file test for knowledge.validate_research_wave2. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_research_wave2.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.knowledge import validate_research_wave2 as vrw2


def test_verdict_rule_uses_per_hypothesis_min_effect():
    assert vrw2._verdict(0.001, 0.10, "platoon_split_persistence") == "NULL_LOCAL"  # below 0.15 bar
    assert vrw2._verdict(0.001, 0.20, "platoon_split_persistence") == "CONFIRMED_LOCAL"
    assert vrw2._verdict(0.5, 0.20, "platoon_split_persistence") == "NULL_LOCAL"
    assert vrw2._verdict(None, 0.20, "tto_x_platoon_interaction") == "NOT_TESTABLE"


def test_framing_rate_by_catcher_applies_edge_zone_and_min_n_floor():
    rows = []
    for i in range(600):  # catcher 1: clears the 500 floor
        rows.append({"fielder_2": 1, "zone": 12, "description": "called_strike" if i % 2 == 0 else "ball"})
    for i in range(10):  # catcher 2: below the floor, dropped
        rows.append({"fielder_2": 2, "zone": 12, "description": "ball"})
    df = pd.DataFrame(rows)
    r = vrw2._framing_rate_by_catcher(df, min_n=500)
    assert list(r.index) == [1]
    assert abs(r.loc[1] - 0.5) < 1e-9


def test_catcher_framing_multiseason_trend_paired_ttest_on_synthetic_seasons():
    def season(rate: float, n: int = 600):
        return pd.DataFrame({"fielder_2": [1] * n, "zone": [12] * n,
                              "description": ["called_strike" if i < int(n * rate) else "ball" for i in range(n)]})
    s23, s24, s25 = season(0.30), season(0.30), season(0.30)
    r = vrw2.catcher_framing_multiseason_trend(s23, s24, s25)
    assert r["n"] == 1  # only catcher 1 clears the floor in all 3 seasons
    assert r["hypothesis"] == "catcher_framing_multiseason_trend"
    assert r["corpus"] == "savant_full__2023+2024+2025"


def test_tto_x_platoon_interaction_not_testable_below_n_floor():
    fake_pa = pd.DataFrame({
        "game_pk": [1, 1, 1, 1], "pitcher": [10, 10, 10, 10], "batter": [20, 20, 20, 20],
        "at_bat_number": [1, 2, 3, 4], "stand": ["R", "R", "R", "R"], "p_throws": ["R", "R", "R", "R"],
        "estimated_woba_using_speedangle": [0.3, 0.3, 0.3, 0.3],
    })
    r = vrw2.tto_x_platoon_interaction(fake_pa, "h1")
    assert r["verdict"] == "NOT_TESTABLE" and r["n"] == 4


def test_tto_x_platoon_interaction_caps_trip_number_at_4():
    n = 60
    df = pd.DataFrame({
        "game_pk": [1] * n, "pitcher": [10] * n, "batter": [20] * n,
        "at_bat_number": list(range(1, n + 1)), "stand": ["R"] * n, "p_throws": ["R"] * n,
        "estimated_woba_using_speedangle": [0.3] * n,
    })
    r = vrw2.tto_x_platoon_interaction(df, "h1")
    assert r["n"] <= 4  # only trip_number<=4 rows survive from one repeating batter/pitcher pair


def test_combine_requires_both_halves_confirmed_same_direction():
    a = {"hypothesis": "x__h1", "n": 100, "effect": 0.01, "p": 0.0001, "verdict": "CONFIRMED_LOCAL"}
    b = {"hypothesis": "x__h2", "n": 100, "effect": 0.01, "p": 0.0001, "verdict": "CONFIRMED_LOCAL"}
    assert vrw2._combine("x", [a, b])["verdict"] == "CONFIRMED_LOCAL"
    c = {"hypothesis": "x__h2", "n": 100, "effect": 0.001, "p": 0.5, "verdict": "NULL_LOCAL"}
    assert vrw2._combine("x", [a, c])["verdict"] == "PROVISIONAL"
    d = {"hypothesis": "x__h2", "n": 100, "effect": -0.01, "p": 0.0001, "verdict": "CONFIRMED_LOCAL"}
    assert vrw2._combine("x", [a, d])["verdict"] == "NULL_LOCAL"  # opposite direction, not both-confirmed-same-way


def test_platoon_delta_by_hand_computes_l_minus_r_on_base_rate():
    fake = pd.DataFrame({
        "batter": [1] * 30 + [2] * 30, "p_throws": (["L"] * 15 + ["R"] * 15) * 2,
        "events": (["walk"] * 6 + ["field_out"] * 9) * 4,
        "game_date": pd.to_datetime("2025-04-01"),
    })
    d = vrw2._platoon_delta_by_hand(fake, min_pa=15)
    assert set(d.index) == {1, 2}
    assert abs(d.loc[1] - 0.0) < 1e-9  # same rate vs L and vs R by construction


def test_platoon_split_persistence_not_testable_below_batter_floor():
    n = 40
    df = pd.DataFrame({
        "batter": list(range(n)), "p_throws": ["L", "R"] * (n // 2),
        "events": ["walk"] * n,
        "game_date": pd.to_datetime("2025-04-01") + pd.to_timedelta(list(range(n)), unit="D"),
    })
    r = vrw2.platoon_split_persistence(df)
    assert r["verdict"] == "NOT_TESTABLE"


def test_run_writes_five_rows_one_framing_two_tto_halves_plus_combined_plus_persistence(monkeypatch):
    rng = np.random.default_rng(3)
    n = 700

    def fake_load_season(season):
        return pd.DataFrame({
            "fielder_2": rng.integers(1, 4, n), "zone": [12] * n,
            "description": rng.choice(["ball", "called_strike"], n),
            "game_pk": rng.integers(1, 20, n), "pitcher": rng.integers(1, 5, n),
            "batter": rng.integers(1, 5, n), "at_bat_number": rng.integers(1, 10, n),
            "pitch_number": rng.integers(1, 5, n),
            "stand": rng.choice(["L", "R"], n), "p_throws": rng.choice(["L", "R"], n),
            "estimated_woba_using_speedangle": rng.random(n),
            "events": rng.choice(["walk", "field_out"], n),
            "game_date": pd.to_datetime("2025-04-01") + pd.to_timedelta(rng.integers(0, 150, n), unit="D"),
        })

    written = []
    monkeypatch.setattr(vrw2, "append_jsonl_atomic", lambda path, row: written.append(row))
    monkeypatch.setattr(vrw2, "load_season", fake_load_season)

    rows = vrw2.run()
    assert len(rows) == 5  # framing + tto(h1,h2,combined) + persistence
    assert len(written) == 5
    assert all(r["edge_claimed"] is False and r["sport"] == "mlb" for r in rows)
    assert rows[0]["hypothesis"] == "catcher_framing_multiseason_trend"
    combined = [r for r in rows if r["hypothesis"].endswith("__combined")]
    assert len(combined) == 1
    assert all(r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "PROVISIONAL", "NOT_TESTABLE"} for r in rows)
