"""tests/test_retro_inplay_mae_v2.py — cycle 94d (loop 5).

Three offline tests for scripts/retro_inplay_mae_v2.py — the prod-pergame
baseline variant of cycle 93c. Each test fakes the heavy data sources so
the suite runs in a few hundred ms.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae_v2 as ri2  # noqa: E402


STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _fake_qstats() -> pd.DataFrame:
    """One game, two players, 4 quarters."""
    rows = []
    for q in (1, 2, 3, 4):
        rows.append({
            "game_id": "0099999999", "player_id": 1001, "period": q,
            "min": 10.0, "pts": 5.0, "reb": 2.0, "ast": 1.0,
            "fg3m": 0.0, "stl": 0.0, "blk": 0.0, "tov": 0.0,
            "pf": 1.0, "plus_minus": 0.0,
        })
        rows.append({
            "game_id": "0099999999", "player_id": 2002, "period": q,
            "min": 10.0, "pts": 8.0, "reb": 3.0, "ast": 2.0,
            "fg3m": 0.0, "stl": 0.0, "blk": 0.0, "tov": 0.0,
            "pf": 1.0, "plus_minus": 0.0,
        })
    return pd.DataFrame(rows)


# ── 1. prod_pergame prediction produced for a fixture game (dispatch path) ────

def test_prod_pergame_prediction_dispatch_for_fixture(monkeypatch):
    """prod_pergame_predictions ties (game_id, pid, stat) → predicted float
    using the cycle-48 dispatch (predict_pergame returns a non-None number)."""
    df = _fake_qstats()
    game_dates = {"0099999999": "2024-12-15"}

    # Stub the gamelog index — give the players a 10-game prior history so
    # _row_features has enough data to compute non-zero rolling stats.
    fake_history = []
    for i in range(10):
        fake_history.append((
            datetime(2024, 12, i + 1),
            {"GAME_DATE": f"Dec {i+1}, 2024", "MIN": 30.0,
             "PTS": 15.0, "REB": 5.0, "AST": 3.0, "FG3M": 1.0,
             "STL": 1.0, "BLK": 0.5, "TOV": 1.5,
             "MATCHUP": "HOM vs. AWY"},
            "2024-25",
        ))
    fake_history.append((
        datetime(2024, 12, 15),
        {"GAME_DATE": "Dec 15, 2024", "MIN": 0.0,  # target game placeholder
         "PTS": 0.0, "REB": 0.0, "AST": 0.0, "FG3M": 0.0,
         "STL": 0.0, "BLK": 0.0, "TOV": 0.0,
         "MATCHUP": "HOM vs. AWY"},
        "2024-25",
    ))

    def _fake_index():
        return {1001: list(fake_history), 2002: list(fake_history)}

    monkeypatch.setattr(ri2, "_build_pid_gamelog_index", _fake_index)

    # Stub predict_pergame to a deterministic fake so the test is independent
    # of model artifacts on disk (which may or may not exist on CI).
    import src.prediction.prop_pergame as pp_mod

    def _fake_predict(stat, row, model_dir=None):
        # Return a stat-specific deterministic value so we can assert shape.
        defaults = {"pts": 15.5, "reb": 5.1, "ast": 3.0, "fg3m": 1.0,
                    "stl": 1.0, "blk": 0.5, "tov": 1.5}
        return defaults.get(stat, 0.0)

    monkeypatch.setattr(pp_mod, "predict_pergame", _fake_predict)

    out = ri2.prod_pergame_predictions(game_dates, df)

    # One prediction per (game, player, stat) — 1 game × 2 players × 7 stats.
    assert len(out) == 2 * len(STATS), f"expected 14 preds, got {len(out)}"
    for pid in (1001, 2002):
        for stat in STATS:
            key = ("0099999999", pid, stat)
            assert key in out, f"missing pred for {key}"
            assert isinstance(out[key], float)
            assert out[key] >= 0.0


# ── 2. per-stat MAE computed across 3 systems on shared triples ───────────────

def test_aggregate_mae_v2_pairs_three_systems():
    """aggregate_mae_v2 emits MAE for prod_pergame + endQ1/Q2/Q3 on shared
    (game, pid, stat) triples — and the math is correct."""
    snaps = {
        "G1": {
            "endQ1": {(101, "pts"): 22.0, (101, "ast"): 4.0},
            "endQ2": {(101, "pts"): 21.0, (101, "ast"): 4.5},
            "endQ3": {(101, "pts"): 20.0, (101, "ast"): 5.0},
        },
    }
    actuals = {
        "G1": {(101, "pts"): 19.0, (101, "ast"): 6.0,
                # reb has actuals but no prod prediction → must drop.
                (101, "reb"): 8.0},
    }
    prod = {
        ("G1", 101, "pts"): 17.0,  # |17-19|=2.0
        ("G1", 101, "ast"): 5.5,   # |5.5-6|=0.5
        # No reb pred — triple drops entirely from the table.
    }

    table = ri2.aggregate_mae_v2(snaps, actuals, prod)

    # PTS bucket should have all 4 systems on n=1.
    pts = table["pts"]
    assert pts["prod_pergame"] == (1, 2.0)
    assert pts["endQ1"] == (1, abs(22 - 19))
    assert pts["endQ2"] == (1, abs(21 - 19))
    assert pts["endQ3"] == (1, abs(20 - 19))

    # AST bucket likewise.
    ast = table["ast"]
    assert ast["prod_pergame"] == (1, 0.5)
    assert ast["endQ3"] == (1, abs(5.0 - 6.0))

    # REB bucket should be empty (no prod pred → dropped).
    assert table.get("reb", {}) == {}


# ── 3. output report includes all 3 system columns + headline verdict ─────────

def test_build_report_v2_format_has_three_systems():
    """The markdown report header lists all 3 system columns, and the verdict
    section renders one of the three branches."""
    mae_table = {
        "pts": {"prod_pergame": (100, 4.6210),
                "endQ1": (90, 7.0100),
                "endQ2": (95, 3.9866),
                "endQ3": (100, 2.4469)},
        "reb": {"prod_pergame": (100, 1.9023),
                "endQ1": (90, 3.0341),
                "endQ2": (95, 1.6805),
                "endQ3": (100, 0.9664)},
    }
    report = ri2.build_report_v2(mae_table, n_games=50)

    # The header table must reference all 4 systems including PROD.
    assert "prod_pergame_mae" in report
    assert "endQ1_mae" in report
    assert "endQ2_mae" in report
    assert "endQ3_mae" in report
    # Per-stat rows include both pts and reb.
    assert "| pts |" in report
    assert "| reb |" in report
    # Verdict section is present and is one of the 3 branches.
    assert "## Verdict" in report
    assert ("VALIDATED" in report or "PARTIALLY" in report
            or "NOT competitive" in report or "Inconclusive" in report)
