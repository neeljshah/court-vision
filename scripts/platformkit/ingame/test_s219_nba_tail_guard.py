"""Focused construct checks for the frozen S219 NBA tail guard."""
import pandas as pd

from scripts.platformkit.ingame import s219_nba_tail_guard as s219


def _rows() -> pd.DataFrame:
    rows = []
    for fold, start in (("F1", 0), ("F2", 3), ("F3", 6), ("F4", 9)):
        for game_no in range(start, start + 3):
            for tick in range(2):
                rows.append({"game": "g%d" % game_no, "game_date": fold,
                             "ts": "2026-01-%02dT00:00:0%dZ" % (game_no + 1, tick),
                             "p_e4": 0.90 if tick == 0 else 0.70,
                             "market": 0.60, "y": float(game_no % 2),
                             "margin": 2.0, "rem": 20.0})
    return pd.DataFrame(rows)


def test_s219_frozen_grid_clamps_and_scores_all_outer_test_ticks(monkeypatch):
    monkeypatch.setattr(s219, "apply_incumbent", lambda rows, kind: rows)
    assert s219.GRID == ((0.05, 0.15), (0.05, 0.25), (0.05, 0.35),
                         (0.10, 0.15), (0.10, 0.25), (0.10, 0.35))
    assert s219.CONFIDENT_CUT == 0.3
    clamped = s219.clamp_probability(pd.Series([0.8, 0.80001, 0.2]), 0.05, 0.35)
    assert clamped.tolist() == [0.8, 0.55, 0.2]
    summary, archive = s219.screen(_rows())
    assert summary["n_qualifying_games"] == 12
    assert summary["n_scored_games"] == 9
    assert summary["n_scored_ticks"] == 18
    assert len(summary["members"]) == 6
    assert {row["member"] for row in summary["members"]} == {
        s219.member_name(*pair) for pair in s219.GRID
    }
    assert {row["n_ticks"] for row in summary["members"]} == {18}
    assert summary["composite"]["n_ticks"] == 18
    assert set(summary["composite"]["selection_by_outer_fold"]) == {"F2", "F3", "F4"}
    assert [summary["selection_tick_counts"][fold]["selected_ticks"] for fold in ("F2", "F3", "F4")] == [4, 10, 16]
    assert [summary["selection_tick_counts"][fold]["embargoed_ticks"] for fold in ("F2", "F3", "F4")] == [2, 2, 2]
    assert len(archive) == 7 * 9
    recomputed = s219.recompute_from_per_game([row for row in archive if row["member"] == "composite"])
    assert recomputed["n_ticks"] == summary["composite"]["n_ticks"]
    assert abs(recomputed["improvement_vs_incumbent"] - summary["composite"]["improvement_vs_incumbent"]) < 1e-12
    assert recomputed["dm_ci95"] == summary["composite"]["dm_ci95"]
    assert all("tail_guard" in row and "max_loser_probability_guard" in row for row in archive)
    assert recomputed["tail_guard"] == summary["composite"]["tail_guard"]
    assert summary["verdict"] == "SCREEN_NULL"
    assert not summary["composite"]["bar_ci_bh_pass"]
