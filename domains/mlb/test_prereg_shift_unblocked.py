"""Per-file test for prereg_shift_unblocked.py -- spray-angle/pull classification
on hand-computed coordinates, the as-of leak guard end-to-end through
build_gb_frame, and the test/replicate verdict rules (BLOCKED, NOT_TESTABLE,
same-sign-and-p<alpha REPLICATED/FAILED_REPLICATION).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_prereg_shift_unblocked.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb import prereg_shift_unblocked as psu

_HOME_X, _HOME_Y = psu._HOME_X, psu._HOME_Y


def test_spray_angle_and_pull_classification_hand_computed():
    # denominator (198.27-hc_y)=100 for all rows; hc_x chosen for a clean +-30deg spray
    hc_x = pd.Series([_HOME_X - 100 * np.tan(np.radians(30)),   # spray = -30deg (3B/LF side)
                      _HOME_X + 100 * np.tan(np.radians(30)),   # spray = +30deg (1B/RF side)
                      _HOME_X])                                  # spray = 0deg (dead center)
    hc_y = pd.Series([_HOME_Y - 100, _HOME_Y - 100, _HOME_Y - 100])
    spray = psu.spray_angle_deg(hc_x, hc_y)
    assert np.allclose(spray.to_numpy(), [-30.0, 30.0, 0.0], atol=1e-6)

    stand = pd.Series(["R", "R", "R"])
    # RHB: pulled to the -30deg (3B/LF) side, NOT the +30deg (1B/RF) side or dead center
    assert psu.classify_pulled(spray, stand).tolist() == [True, False, False]

    stand_l = pd.Series(["L", "L", "L"])
    # LHB: pulled to the +30deg (1B/RF) side, NOT the -30deg (3B/LF) side or dead center
    assert psu.classify_pulled(spray, stand_l).tolist() == [False, True, False]


def _gb_row(batter, game_date, hc_x, hc_y, stand="R", events="field_out",
            alignment="Standard"):
    return {"batter": batter, "game_date": game_date, "hc_x": hc_x, "hc_y": hc_y,
            "stand": stand, "bb_type": "ground_ball", "events": events,
            "if_fielding_alignment": alignment}


def test_build_gb_frame_leak_guard_drops_first_date():
    pull_x, pull_y = _HOME_X - 60, _HOME_Y - 100  # spray well past -15deg -> RHB pull
    df = pd.DataFrame([
        _gb_row(1, "2023-04-01", pull_x, pull_y),
        _gb_row(1, "2023-04-02", pull_x, pull_y),
        _gb_row(1, "2023-04-03", pull_x, pull_y),
    ])
    frame = psu.build_gb_frame(df)
    # first game_date has no prior data -> pull_share_asof NaN -> dropped (leak guard)
    assert set(frame["game_date"]) == {"2023-04-02", "2023-04-03"}
    assert (frame["pull_share_asof"] == 1.0).all()  # every prior grounder was a pull


def test_build_gb_frame_empty_when_no_ground_balls():
    df = pd.DataFrame([{"batter": 1, "game_date": "2023-04-01", "hc_x": 100.0, "hc_y": 100.0,
                         "stand": "R", "bb_type": "fly_ball", "events": "field_out",
                         "if_fielding_alignment": "Standard"}])
    assert psu.build_gb_frame(df).empty


def test_run_h1_test_blocked_when_hit_coords_absent():
    df = pd.DataFrame({"bb_type": ["ground_ball"], "events": ["single"],
                        "if_fielding_alignment": ["Standard"]})
    row = psu.run_h1_test(df)
    assert row["verdict"] == "BLOCKED"


def test_run_h1_test_not_testable_when_zero_scoreable_rows():
    df = pd.DataFrame([{"batter": 1, "game_date": "2023-04-01", "hc_x": 100.0, "hc_y": 100.0,
                         "stand": "R", "bb_type": "fly_ball", "events": "field_out",
                         "if_fielding_alignment": "Standard"}])
    row = psu.run_h1_test(df)
    assert row["verdict"] == "NOT_TESTABLE"
    assert row["n"] == 0


def _synthetic_gb_df(n_dates=20, n_batters=6, per_date=20, seed=3, planted_sign=1.0):
    """6 batters with distinct TRUE pull rates spread 0.10..0.90 (spread via
    the pull/no-pull hc_x choice), is_shifted alternating by date (same across
    batters so it is not confounded with batter identity), and a planted
    interaction: hit prob shifts with true_pull_rate * is_shifted * planted_sign."""
    rng = np.random.default_rng(seed)
    rows = []
    dates = [f"2023-04-{d:02d}" for d in range(1, n_dates + 1)]
    pull_x, pull_y = _HOME_X - 60, _HOME_Y - 100     # clean RHB pull coords
    oppo_x, oppo_y = _HOME_X + 60, _HOME_Y - 100      # clean RHB opposite-field coords
    for b in range(n_batters):
        true_pull_rate = 0.1 + 0.16 * b
        for d_idx, d in enumerate(dates):
            is_shifted = d_idx % 2
            for _ in range(per_date):
                pulled = rng.random() < true_pull_rate
                hc_x, hc_y = (pull_x, pull_y) if pulled else (oppo_x, oppo_y)
                hit_p = 0.30 + planted_sign * 0.35 * true_pull_rate * is_shifted
                hit_p = min(max(hit_p, 0.02), 0.98)
                events = "single" if rng.random() < hit_p else "field_out"
                rows.append(_gb_row(1000 + b, d, hc_x, hc_y, stand="R", events=events,
                                     alignment="Infield shade" if is_shifted else "Standard"))
    return pd.DataFrame(rows)


def test_run_h1_test_detects_planted_positive_interaction():
    df23 = _synthetic_gb_df(seed=1, planted_sign=1.0)
    row = psu.run_h1_test(df23)
    assert row["verdict"] == "SURVIVES_PREREG"
    assert row["effect"] > 0


def test_run_h1_replicate_failed_when_sign_flips():
    fake_test_row = {"verdict": "SURVIVES_PREREG", "effect": 2.0}
    df24 = _synthetic_gb_df(seed=2, planted_sign=-1.0)  # opposite-sign planted effect
    row = psu.run_h1_replicate(df24, fake_test_row)
    assert row["verdict"] == "FAILED_REPLICATION"
    assert row["effect"] < 0


def test_run_h1_replicate_short_circuits_when_test_row_not_survives():
    fake_test_row = {"verdict": "NULL", "effect": 0.1}
    df24 = _synthetic_gb_df(seed=4, planted_sign=1.0)
    row = psu.run_h1_replicate(df24, fake_test_row)
    assert row["verdict"] == "FAILED_REPLICATION"
    assert "not attempted on the merits" in row["note"]


def test_run_h1_replicate_blocked_when_hit_coords_absent():
    df24 = pd.DataFrame({"bb_type": ["ground_ball"], "events": ["single"],
                          "if_fielding_alignment": ["Standard"]})
    fake_test_row = {"verdict": "SURVIVES_PREREG", "effect": 1.0}
    row = psu.run_h1_replicate(df24, fake_test_row)
    assert row["verdict"] == "BLOCKED"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
