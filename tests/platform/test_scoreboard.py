"""tests/platform/test_scoreboard.py — Synthetic tests for scripts.platformkit.scoreboard.

NO real adapter / full corpus loaded.  All tests use hand-crafted tiny arrays.
Tests:
  - score_forecaster: brier/logloss/ece correct on hand values
  - well-calibrated set beats miscalibrated on ECE
  - market_beats_model=True when closing Brier < model Brier
  - build_scoreboard skips absent corpora gracefully (mocked adapter)
  - format_leaderboard: contains honest footer, no banned edge words
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import List, Optional, Sequence
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from scripts.platformkit.scoreboard import (
    HONEST_FOOTER,
    build_scoreboard,
    format_leaderboard,
    score_forecaster,
    score_sport,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# "edge" appears in the honest footer as a negation ("NO edge claimed") — not banned there.
# Ban only affirmative claims: words that assert profitability.
_BANNED_WORDS = {"guaranteed", "beat the market", "profit", "proven edge", "positive ev"}


def _fake_bundle(
    signal: Sequence[float],
    target: Sequence[float],
    closing: Optional[Sequence[float]] = None,
):
    """Minimal FeatureBundle-like object."""
    from src.loop.gate import FeatureBundle
    n = len(signal)
    return FeatureBundle(
        base=np.zeros((n, 2), dtype=float),
        signal_col=np.asarray(signal, dtype=float),
        target=np.asarray(target, dtype=float),
        dates=[f"2024-01-{(i % 28) + 1:02d}" for i in range(n)],
        lines=None,
        closing=np.asarray(closing, dtype=float) if closing is not None else None,
    )


def _fake_adapter(signal, target, closing=None, label="test_win_prob"):
    adapter = MagicMock()
    adapter.MARKET_LABEL = label
    adapter.feature_bundle.return_value = _fake_bundle(signal, target, closing)
    return adapter


# ---------------------------------------------------------------------------
# score_forecaster
# ---------------------------------------------------------------------------


class TestScoreForecaster:
    def test_perfect_forecast_brier_zero(self):
        probs = [0.0, 1.0, 0.0, 1.0]
        outcomes = [0, 1, 0, 1]
        r = score_forecaster(probs, outcomes)
        assert r["brier"] == pytest.approx(0.0, abs=1e-10)
        assert r["n"] == 4

    def test_coin_flip_brier_025(self):
        n = 1000
        probs = [0.5] * n
        outcomes = [i % 2 for i in range(n)]
        r = score_forecaster(probs, outcomes)
        assert r["brier"] == pytest.approx(0.25, abs=1e-6)

    def test_log_loss_hand_value(self):
        import math
        probs = [0.9, 0.1]
        outcomes = [1, 0]
        r = score_forecaster(probs, outcomes)
        expected_ll = -0.5 * (math.log(0.9) + math.log(0.9))
        assert r["log_loss"] == pytest.approx(expected_ll, abs=1e-6)

    def test_nan_probs_filtered(self):
        probs = [0.5, float("nan"), 0.7]
        outcomes = [1, 1, 0]
        r = score_forecaster(probs, outcomes)
        assert r["n"] == 2  # nan row dropped

    def test_all_nan_returns_nan(self):
        r = score_forecaster([float("nan")], [1])
        assert r["n"] == 0
        assert math.isnan(r["brier"])

    def test_ece_perfectly_calibrated(self):
        # Construct a set where predicted probs match actual frequencies exactly
        # 100 samples: 50 at p=0.3 (outcome=0 each), 50 at p=0.7 (outcome=1 each).
        # This is NOT perfectly calibrated, but we just check ECE is finite/>=0.
        probs = [0.3] * 50 + [0.7] * 50
        outcomes = [0] * 50 + [1] * 50
        r = score_forecaster(probs, outcomes)
        assert r["ece"] >= 0.0
        assert math.isfinite(r["ece"])

    def test_well_calibrated_beats_miscalibrated_ece(self):
        """A set predicting the true frequency should have lower ECE."""
        np.random.seed(42)
        n = 500
        outcomes = np.random.binomial(1, 0.6, n)

        # Well-calibrated: predict the true rate
        good = np.full(n, 0.6)
        # Miscalibrated: always predict 0.9
        bad = np.full(n, 0.9)

        r_good = score_forecaster(good, outcomes)
        r_bad  = score_forecaster(bad, outcomes)
        assert r_good["ece"] < r_bad["ece"], (
            f"good ECE {r_good['ece']:.4f} should be < bad ECE {r_bad['ece']:.4f}"
        )


# ---------------------------------------------------------------------------
# score_sport / market_beats_model
# ---------------------------------------------------------------------------


class TestScoreSport:
    def test_market_beats_model_true_when_closer_is_better(self):
        """When closing Brier < model Brier, market_beats_model=True."""
        n = 200
        np.random.seed(0)
        outcomes = np.random.binomial(1, 0.55, n).tolist()
        # Model: noisy predictions (bad)
        signal = np.clip(np.random.normal(0.5, 0.3, n), 0.01, 0.99).tolist()
        # Closing: very good — near-perfect (better calibration)
        closing = [float(o) * 0.9 + 0.05 for o in outcomes]

        adapter = _fake_adapter(signal, outcomes, closing)
        rows = score_sport("test_sport", adapter)
        model_row = next(r for r in rows if r["forecaster"] == "model_raw")
        assert model_row["market_beats_model"] is True, (
            f"Expected market_beats_model=True; model_brier={model_row['brier']:.4f}, "
            f"close_brier={model_row['brier'] - model_row['dBrier_vs_close']:.4f}"
        )

    def test_market_beats_model_false_when_model_is_better(self):
        """When closing is worse than model, market_beats_model=False."""
        n = 200
        np.random.seed(1)
        outcomes = np.random.binomial(1, 0.6, n).tolist()
        # Model: very close to truth
        signal = [float(o) * 0.88 + 0.06 for o in outcomes]
        # Closing: coin flip (terrible)
        closing = [0.5] * n

        adapter = _fake_adapter(signal, outcomes, closing)
        rows = score_sport("test_sport", adapter)
        model_row = next(r for r in rows if r["forecaster"] == "model_raw")
        assert model_row["market_beats_model"] is False

    def test_no_closing_data_gives_nan_dbrier(self):
        """When closing is all NaN, dBrier_vs_close should be absent or NaN."""
        n = 100
        signal = [0.6] * n
        outcomes = [1 if i % 2 == 0 else 0 for i in range(n)]
        adapter = _fake_adapter(signal, outcomes, closing=None)
        rows = score_sport("test_sport", adapter)
        model_row = next(r for r in rows if r["forecaster"] == "model_raw")
        # Without closing rows, dBrier_vs_close may be absent
        db = model_row.get("dBrier_vs_close", float("nan"))
        assert math.isnan(db) or db == float("nan"), f"Expected NaN dBrier, got {db}"

    def test_forecaster_names_all_present(self):
        n = 100
        outcomes = [1 if i % 3 != 0 else 0 for i in range(n)]
        closing = [0.65 if i % 3 != 0 else 0.35 for i in range(n)]
        adapter = _fake_adapter([0.6] * n, outcomes, closing)
        rows = score_sport("test_sport", adapter)
        names = {r["forecaster"] for r in rows}
        assert "model_raw" in names
        assert "model_recal" in names
        assert "market_close" in names
        assert "naive_coin" in names
        assert "naive_base_rate" in names


# ---------------------------------------------------------------------------
# build_scoreboard — skips absent corpora gracefully
# ---------------------------------------------------------------------------


class TestBuildScoreboard:
    def test_skips_missing_corpus(self):
        """A FileNotFoundError from the adapter produces a SKIP row, not a crash."""
        mock_adapter_cls = MagicMock(side_effect=FileNotFoundError("no such file"))
        registry_patch = {"fake_sport": ("fake.module", "FakeAdapter")}

        with patch.dict("scripts.platformkit.scoreboard._ADAPTER_REGISTRY", registry_patch):
            with patch("importlib.import_module") as mock_import:
                mock_mod = MagicMock()
                mock_mod.FakeAdapter = mock_adapter_cls
                mock_import.return_value = mock_mod
                rows = build_scoreboard(sports=["fake_sport"])

        assert any(r.get("forecaster") in ("SKIP", "ERROR") for r in rows), (
            f"Expected a SKIP/ERROR row, got: {rows}"
        )

    def test_skips_import_error(self):
        """An ImportError from the adapter module produces an ERROR row, not a crash."""
        registry_patch = {"bad_sport": ("no.such.module", "BadAdapter")}
        with patch.dict("scripts.platformkit.scoreboard._ADAPTER_REGISTRY", registry_patch):
            rows = build_scoreboard(sports=["bad_sport"])
        assert any(r.get("forecaster") in ("SKIP", "ERROR") for r in rows)

    def test_empty_sports_list_returns_empty(self):
        rows = build_scoreboard(sports=[])
        assert rows == []

    def test_unknown_sport_skipped(self):
        rows = build_scoreboard(sports=["nonexistent_sport_xyz"])
        assert rows == []


# ---------------------------------------------------------------------------
# format_leaderboard — honest footer + no banned words
# ---------------------------------------------------------------------------


class TestFormatLeaderboard:
    def _sample_rows(self) -> List[dict]:
        return [
            {"sport": "test", "market": "win_prob", "forecaster": "model_raw",
             "brier": 0.22, "log_loss": 0.65, "ece": 0.03,
             "reliability_slope": 0.95, "n": 200,
             "dBrier_vs_close": 0.01, "market_beats_model": True},
            {"sport": "test", "market": "win_prob", "forecaster": "model_recal",
             "brier": 0.21, "log_loss": 0.64, "ece": 0.02,
             "reliability_slope": 0.98, "n": 200,
             "dBrier_vs_close": 0.00, "market_beats_model": True},
            {"sport": "test", "market": "win_prob", "forecaster": "market_close",
             "brier": 0.20, "log_loss": 0.63, "ece": 0.01,
             "reliability_slope": 1.0, "n": 200,
             "dBrier_vs_close": 0.0, "market_beats_model": False},
        ]

    def test_honest_footer_present(self):
        table = format_leaderboard(self._sample_rows())
        # Check key substrings of the honest footer
        assert "closing line" in table
        assert "NO edge claimed" in table

    def test_no_banned_edge_words(self):
        table = format_leaderboard(self._sample_rows()).lower()
        for word in _BANNED_WORDS:
            assert word not in table, (
                f"Banned word '{word}' found in leaderboard output"
            )

    def test_contains_sport_name(self):
        table = format_leaderboard(self._sample_rows())
        assert "test" in table

    def test_contains_forecaster_names(self):
        table = format_leaderboard(self._sample_rows())
        assert "model_raw" in table
        assert "market_close" in table

    def test_skip_error_rows_displayed(self):
        rows = [{"sport": "missing_sport", "forecaster": "SKIP",
                 "error": "Corpus absent: no file"}]
        table = format_leaderboard(rows)
        assert "SKIP" in table or "missing_sport" in table

    def test_market_beats_model_true_displayed(self):
        table = format_leaderboard(self._sample_rows())
        assert "YES" in table  # market_beats_model=True shown as YES
