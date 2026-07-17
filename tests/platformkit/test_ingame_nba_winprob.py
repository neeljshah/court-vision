"""Per-file smoke tests for scripts/platformkit/benchmarks/crps_market/
ingame_nba_winprob -- ticker decode, checkpoint anchoring LEAK TRAP, verdict
labels, and fixed-seed bootstrap determinism. Synthetic frames only, no real
corpus reads (those are exercised by the CLI itself, not by this test file).

Run: python -m pytest tests/platformkit/test_ingame_nba_winprob.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.benchmarks.crps_market.ingame_nba_winprob import (
    CHECKPOINTS, checkpoint_row, parse_away_home, _verdict_token,
)


def test_checkpoints_are_a_moat_shape_scan():
    labels = [c[0] for c in CHECKPOINTS]
    assert labels == ["end_q1", "halftime", "end_q3", "q4_under5"]
    minutes = [c[1] for c in CHECKPOINTS]
    assert minutes == sorted(minutes)  # early -> late, monotonic


def test_parse_away_home_real_tricodes():
    assert parse_away_home("nba-nyk-bos-2024-10-22") == ("NYK", "BOS")
    assert parse_away_home("nba-min-lal-2024-10-22") == ("MIN", "LAL")


def test_parse_away_home_unparseable_returns_none():
    assert parse_away_home("not-a-ticker") is None
    assert parse_away_home("") is None


def _game(rows):
    """rows: [(elapsed_minutes, market_prob)] -> a minimal df_game frame."""
    return pd.DataFrame({
        "elapsed_minutes": [r[0] for r in rows],
        "market_prob": [r[1] for r in rows],
    })


def test_checkpoint_row_leak_trap_never_uses_a_tick_after_the_anchor():
    # row at 13min has an extreme market_prob (0.001) -- if the leak trap
    # failed, anchor=12 would wrongly pick it over the 11min row (0.5).
    g = _game([(10.0, 0.4), (11.0, 0.5), (13.0, 0.001)])
    row = checkpoint_row(g, anchor_minutes=12.0)
    assert row["elapsed_minutes"] == 11.0
    assert row["market_prob"] == 0.5


def test_checkpoint_row_picks_last_at_or_before_anchor():
    g = _game([(5.0, 0.3), (12.0, 0.6), (12.0, 0.65)])
    row = checkpoint_row(g, anchor_minutes=12.0)
    assert row["elapsed_minutes"] == 12.0  # exact match is "at" -> included


def test_checkpoint_row_none_when_anchor_never_reached():
    # every row is AFTER the anchor (e.g. a feed that only starts mid-Q2) --
    # never falls back to a future tick, so the checkpoint is honestly absent.
    g = _game([(15.0, 0.5), (20.0, 0.5)])
    assert checkpoint_row(g, anchor_minutes=12.0) is None


def test_checkpoint_row_empty_game():
    assert checkpoint_row(_game([]), anchor_minutes=12.0) is None


def test_verdict_underpowered_below_min_n():
    delta = np.array([0.01, -0.02, 0.03])  # n=3 < 30
    token, provisional, ci = _verdict_token(delta)
    assert token == "UNDERPOWERED"
    assert provisional is False


def test_verdict_model_sharper_provisional():
    rng = np.random.default_rng(1)
    delta = 0.05 + rng.normal(0, 0.01, size=200)  # consistently positive
    token, provisional, ci = _verdict_token(delta)
    assert token == "MODEL_SHARPER_PROVISIONAL"
    assert provisional is True
    assert ci[0] > 0


def test_verdict_market_sharper_provisional():
    rng = np.random.default_rng(2)
    delta = -0.05 + rng.normal(0, 0.01, size=200)  # consistently negative
    token, provisional, ci = _verdict_token(delta)
    assert token == "MARKET_SHARPER_PROVISIONAL"
    assert provisional is True
    assert ci[1] < 0


def test_bootstrap_ci_is_deterministic_fixed_seed():
    delta = np.array([0.01, -0.02, 0.03, 0.01, -0.01] * 10)
    _, _, ci_a = _verdict_token(delta)
    _, _, ci_b = _verdict_token(delta)
    assert ci_a == ci_b
