"""Per-file tests for the profile-attribute gate (calibration only, no edge)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.profiles import attribute_gate as ag


def test_window_leak_rule():
    # plain full-season windows resolve; partial windows are refused (None).
    assert ag._window_season("season_2025_26", "split") == "2025-26"
    assert ag._window_season("season_2023", "plain") == "2023"
    assert ag._window_season("season_2024_25_home", "split") is None
    assert ag._window_season("clutch_2024", "plain") is None
    assert ag._window_season("season_2024_last20", "split") is None


def test_verdict_bonferroni_bar():
    # dm_p=0.01 clears a K=1 bar (0.05) but NOT a K=10 bar (0.005) -> tightens.
    assert ag._verdict(0.01, 0.01, 0.01, K=1) == "MATTERS_PROVISIONAL"
    assert ag._verdict(0.01, 0.01, 0.01, K=10) == "NULL"
    # every rail is required: non-positive delta or delta_t80 -> NULL.
    assert ag._verdict(-0.01, 0.0001, 0.01, K=1) == "NULL"
    assert ag._verdict(0.01, 0.0001, -0.01, K=1) == "NULL"


def test_same_season_window_skipped(monkeypatch):
    """Only a same-season profile window exists -> SKIPPED_SAME_SEASON_WINDOW
    (no strictly-prior season to condition on, so it is not knowable pregame)."""
    games = pd.DataFrame({"season": ["2025-26"] * 4})
    sub = pd.DataFrame({"entity_id": ["1610612737", "1610612738"],
                        "window": ["season_2025_26", "season_2025_26"],
                        "attribute": ["x", "x"], "raw_value": [0.1, 0.2]})
    monkeypatch.setattr(ag, "_locate", lambda s, a: ("team", sub))
    g, tested = ag.gate_attribute("nba", "x", games, lambda: np.zeros(4))
    assert not tested and g.verdict == "SKIPPED_SAME_SEASON_WINDOW", (g.verdict, g.caveats)


def test_untestable_no_base(monkeypatch):
    """Attribute absent from every profile parquet -> UNTESTABLE_NO_BASE, and
    the (costly) base logit is never requested."""
    games = pd.DataFrame({"season": ["2025-26"] * 4})
    monkeypatch.setattr(ag, "_locate", lambda s, a: (None, None))

    def _boom() -> np.ndarray:
        raise AssertionError("base logit must not be built for an untestable attr")

    g, tested = ag.gate_attribute("nba", "__nope__", games, _boom)
    assert not tested and g.verdict == "UNTESTABLE_NO_BASE"


def test_player_to_team_minutes_weighted_agg(tmp_path, monkeypatch):
    """Prior-season player profile values roll up to team as a minutes-weighted
    mean of that team's prior-season players (design (a))."""
    from scripts.platformkit.intel_weighting import player_team_agg as pta

    box = pd.DataFrame({
        "season": ["2024-25"] * 4,
        "team": ["BOS", "BOS", "DEN", "DEN"],
        "player_id": [1, 2, 3, 4],
        "min": [30.0, 10.0, 5.0, 1.0],
    })
    path = tmp_path / "box.parquet"
    box.to_parquet(path)
    # player 1=10 (30 min), player 2=2 (10 min) -> BOS = (10*30+2*10)/40 = 8.0
    vals = {"1": 10.0, "2": 2.0}
    team_vals, dropped = pta.aggregate_to_team(vals, "2024-25", boxscores=path)
    assert abs(team_vals["BOS"] - 8.0) < 1e-9, team_vals
    assert "DEN" in dropped  # DEN uncovered (players 3,4 carry no value)


if __name__ == "__main__":
    test_window_leak_rule()
    test_verdict_bonferroni_bar()
    print("smoke OK")
