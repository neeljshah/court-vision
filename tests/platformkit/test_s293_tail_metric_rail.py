"""Focused S293 tail metric rail checks; run this file only."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate.cpcv_tail_metrics import (
    attach_log_losses, log_loss_values, refuse_mixed_grain, reliability_table, trailing_side,
)
from scripts.platformkit.ingame.s293_tail_metric_replay import _comeback

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/harness/S293_tail_metric_rail_prereg_attempt2_2026-09-07.md"
ARCHIVE = ROOT / "docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv"


def test_s293_prereg_and_one_archived_game_tail_log_losses_are_finite() -> None:
    data = PREREG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = data.split(b"S293_PREREG_SEAL_SHA256=", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.splitlines()[0].decode("ascii")
    rows = []
    with ARCHIVE.open(encoding="ascii", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["record_type"] == "tail_tick":
                if rows and row["game_id"] != rows[0]["game_id"]:
                    break
                rows.append(row)
    assert rows
    for key in ("candidate", "incumbent"):
        losses, audit = log_loss_values([float(row[key]) for row in rows], [float(row["outcome_home_win"]) for row in rows])
        assert np.isfinite(losses).all() and audit["excluded_rows"] == 0


def test_s293_direct_endpoints_mixed_grain_and_trailing_ot_fixture() -> None:
    losses, audit = log_loss_values([0.0, 1.0, 0.25], [0.0, 1.0, 1.0])
    assert np.isfinite(losses).all() and audit == {"n": 3, "zero_probability_rows": 1, "one_probability_rows": 1, "clipped_rows": 2, "excluded_rows": 0}
    assert losses[2] == pytest.approx(-np.log(0.25))
    with pytest.raises(ValueError, match="mixed-grain"):
        refuse_mixed_grain([{"record_type": "all_game"}, {"record_type": "tail_tick"}])
    records = attach_log_losses([{"p_model": 0.2, "p_close": 0.3, "y": 0, "split_id": 0, "n_train": 1}], tail_selector=lambda _: True)
    assert records[0]["log_loss"] == records[0]["tail_log_loss"]


def test_s293_trailing_side_uses_the_trailing_team_frame() -> None:
    # Home frame in; trailing frame out. Row 0: home trails by 14 and wins -- its own
    # p/y carry over. Row 1: away trails by 16 and wins -- the complement is taken.
    # Row 2: an OT row where the trailing side lost, which must survive as a 0 outcome.
    p, y, home_trailing = trailing_side([0.8, 0.3, 0.05], [1, 0, 0], [-14, 16, -20])
    assert home_trailing.tolist() == [True, False, True]
    assert p.tolist() == pytest.approx([0.8, 0.7, 0.05])
    assert y.tolist() == [1.0, 1.0, 0.0]
    with pytest.raises(ValueError, match="margin"):
        trailing_side([0.5, 0.5], [1, 0], [np.nan, 3.0])


def test_s293_comeback_excludes_ot_period_from_n_ticks_but_counts_it_separately() -> None:
    # Periods 1-3 always fail remaining_s <= 720 regardless of margin/clock (each has
    # >= 2160s of regulation left), so only the period-4 row can enter the comeback
    # mask and only a period > 4 (OT) row can enter the period-cap exclusion count.
    rows = pd.DataFrame({
        "game_id": ["g1", "g2", "g3", "g4", "g5"],
        "period": [1, 2, 3, 4, 5],
        "game_clock_s": [300.0, 300.0, 300.0, 100.0, 100.0],
        "margin": [-20.0, -20.0, -20.0, -14.0, 14.0],
        "y": [0, 0, 0, 1, 0],
        "market_prob": [0.5, 0.5, 0.5, 0.3, 0.6],
        "p_close": [0.5, 0.5, 0.5, 0.35, 0.55],
    })
    result = _comeback(rows)
    assert result["n_ticks"] == 1
    assert result["ot_ticks_excluded_by_period_cap"] == 1
    assert result["ot_games_excluded_by_period_cap"] == 1
    assert result["ot_excluded_outcome_home_win_ticks"] == 0


def test_s293_reliability_cells_below_thirty_publish_n_but_no_score() -> None:
    probabilities = [0.05] * 40 + [0.95] * 6
    outcomes = [0] * 40 + [1] * 6
    table = reliability_table(probabilities, outcomes, (0.0, 0.5, 1.0))
    assert [(row["bin"], row["n"]) for row in table] == [("[0.00,0.50)", 40), ("[0.50,1.00]", 6)]
    assert table[0]["suppressed_below_min_n"] is False and table[0]["log_loss"] is not None
    small = table[1]
    assert small["suppressed_below_min_n"] is True
    assert all(small[key] is None for key in ("mean_probability", "empirical_rate", "reliability_gap", "log_loss"))
    empty = reliability_table([0.05], [0], (0.0, 0.5, 1.0))[1]
    assert empty["n"] == 0 and empty["suppressed_below_min_n"] is False
