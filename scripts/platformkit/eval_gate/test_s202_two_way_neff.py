"""Focused construct tests for S202's additive crossed-n_eff diagnostic."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.s202_two_way_neff import crossed_bootstrap_neff


def test_crossed_bootstrap_is_deterministic_and_keeps_the_full_denominator() -> None:
    rows = pd.DataFrame({"loss": [0.01, 0.08, 0.03, 0.12, 0.04, 0.17, 0.06, 0.20],
                         "home": ["A", "A", "B", "B", "C", "C", "D", "D"],
                         "away": ["W", "X", "W", "X", "W", "X", "W", "X"]})
    first = crossed_bootstrap_neff(rows, "loss", "home", "away", iterations=1000, seed=20260904)
    second = crossed_bootstrap_neff(rows, "loss", "home", "away", iterations=1000, seed=20260904)
    assert first == second
    assert first["n_rows"] == len(rows)
    assert first["first_clusters"] == 4
    assert first["second_clusters"] == 2
    assert first["iterations"] == 1000
    assert first["n_eff"] > 0.0
