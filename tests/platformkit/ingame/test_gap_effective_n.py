"""Construct checks for the explicit empty effective-sample-size contract."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.ingame.gap_effective_n import effective_sample_size


def test_empty_input_requires_opt_in_and_returns_the_complete_ess_shape() -> None:
    """n = 2 (CONSTRUCT): default raises; explicit opt-in returns all six fields."""
    rows = pd.DataFrame({"game": pd.Series(dtype=str), "loss_differential": pd.Series(dtype=float)})

    with pytest.raises(ValueError, match="no non-null game/loss rows"):
        effective_sample_size(rows)

    assert effective_sample_size(rows, empty_ok=True) == {
        "n_ticks": 0,
        "n_games": 0,
        "rho": 0.0,
        "design_effect": 1.0,
        "n_eff": 0.0,
        "n_eff_bound_ok": True,
    }
