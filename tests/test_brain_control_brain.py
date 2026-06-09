"""Tests for P2.3 B8 closure: equal-weight as the validated default.

Asserts:
1. control_brain.engine_weights returns 1/n for each engine (sum=1).
2. regime_skill_weights raises NotImplementedError('DATA_BLOCKED_UNTIL_SEASON_2').
3. B8_brain_equalweight.json exists, parses cleanly, and records beats_equal_weight=False
   with an honest rationale.

All tests are additive (no live-path mutation) and default-OFF (no CV_ flag set).
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Path setup: ensure src/ is on sys.path (mirrors pytest conftest pattern)
# ---------------------------------------------------------------------------
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ---------------------------------------------------------------------------
# Lazy import helpers
# ---------------------------------------------------------------------------

def _load_cb():
    """Import src.brain.control_brain freshly (no cache side-effects in flags)."""
    import importlib
    import src.brain.control_brain as cb  # noqa: E402
    return cb


def _make_preds(n: int, *, margin_offset: float = 0.0) -> List[Dict[str, Any]]:
    """Create a synthetic list of n EnginePred dicts for testing."""
    return [
        {
            "engine": f"engine_{i}",
            "win_prob_home": 0.5,
            "margin_home": float(i) + margin_offset,
            "total": 220.0,
            "home_pts": 110.0,
            "away_pts": 110.0,
            "margin_sd": 10.0,
            "n_models": 1,
            "n_signals": 0,
            "notes": "",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1. engine_weights: equal weights 1/n, sum=1, byte-identical to margins.mean()
# ---------------------------------------------------------------------------

class TestEngineWeightsEqualWeight:
    """engine_weights must return 1/n uniform vector (Rung 0) for all flags OFF."""

    @pytest.mark.parametrize("n", [1, 3, 7, 16])
    def test_uniform_value(self, n: int) -> None:
        """Every weight is exactly 1/n when all CV_ flags are OFF."""
        import numpy as np
        cb = _load_cb()
        # Ensure flags are OFF
        for flag in ("CV_BRAIN_REGIME", "CV_BRAIN_GLS"):
            os.environ.pop(flag, None)

        preds = _make_preds(n)
        w = cb.engine_weights(preds)
        assert w.shape == (n,), f"expected shape ({n},), got {w.shape}"
        expected = float(1.0 / n)
        for i in range(n):
            assert abs(float(w[i]) - expected) < 1e-12, (
                f"weight[{i}]={w[i]:.15f} != {expected:.15f} (delta={abs(float(w[i])-expected):.2e})"
            )

    @pytest.mark.parametrize("n", [2, 5, 7, 16])
    def test_sum_to_one(self, n: int) -> None:
        """Sum of weights is exactly 1.0 (simplex invariant, D03 §2.3)."""
        import numpy as np
        cb = _load_cb()
        for flag in ("CV_BRAIN_REGIME", "CV_BRAIN_GLS"):
            os.environ.pop(flag, None)

        preds = _make_preds(n)
        w = cb.engine_weights(preds)
        total = float(w.sum())
        assert abs(total - 1.0) < 1e-9, f"weights sum to {total:.15f}, expected 1.0"

    @pytest.mark.parametrize("n", [3, 7, 16])
    def test_byte_identical_to_margins_mean(self, n: int) -> None:
        """dot(w, margins) == margins.mean() to within 1e-12 (D03 §8 B1 byte-identity proof)."""
        import numpy as np
        cb = _load_cb()
        for flag in ("CV_BRAIN_REGIME", "CV_BRAIN_GLS"):
            os.environ.pop(flag, None)

        preds = _make_preds(n, margin_offset=1.5)
        w = cb.engine_weights(preds)
        margins = np.array([float(p["margin_home"]) for p in preds])
        weighted = float(np.dot(w, margins))
        mean_val = float(margins.mean())
        assert abs(weighted - mean_val) < 1e-12, (
            f"dot(w, margins)={weighted:.15f} != margins.mean()={mean_val:.15f} "
            f"(delta={abs(weighted - mean_val):.2e})"
        )

    def test_empty_preds_raises_valueerror(self) -> None:
        """engine_weights([]) must raise ValueError (D03 §2.3 precondition)."""
        cb = _load_cb()
        with pytest.raises(ValueError):
            cb.engine_weights([])

    @pytest.mark.parametrize("n", [4, 8])
    def test_all_positive(self, n: int) -> None:
        """All weights are strictly positive (no engine silenced in Rung 0)."""
        import numpy as np
        cb = _load_cb()
        for flag in ("CV_BRAIN_REGIME", "CV_BRAIN_GLS"):
            os.environ.pop(flag, None)

        preds = _make_preds(n)
        w = cb.engine_weights(preds)
        assert float(w.min()) > 0.0, f"minimum weight {float(w.min())} is not positive"


# ---------------------------------------------------------------------------
# 2. regime_skill_weights raises NotImplementedError('DATA_BLOCKED_UNTIL_SEASON_2')
# ---------------------------------------------------------------------------

class TestRegimeSkillWeightsBlocked:
    """Rung 2 must be permanently blocked until the 5-criterion 2-season gate clears (D03 §4.4)."""

    def test_raises_not_implemented_error(self) -> None:
        """regime_skill_weights must raise NotImplementedError on any call."""
        cb = _load_cb()
        regime = cb.RegimeVector(
            is_playoff=False,
            pace_tier=1,
            margin_bucket=1,
            disagree_tier=0,
            coverage_flags=0,
            n_engines=7,
        )
        with pytest.raises(NotImplementedError):
            cb.regime_skill_weights(["e0", "e1", "e2"], regime)

    def test_error_message_contains_data_blocked(self) -> None:
        """The NotImplementedError message must contain 'DATA_BLOCKED_UNTIL_SEASON_2'."""
        cb = _load_cb()
        regime = cb.RegimeVector(
            is_playoff=False,
            pace_tier=1,
            margin_bucket=0,
            disagree_tier=1,
            coverage_flags=0,
            n_engines=3,
        )
        with pytest.raises(NotImplementedError) as exc_info:
            cb.regime_skill_weights(["a", "b", "c"], regime)
        assert "DATA_BLOCKED_UNTIL_SEASON_2" in str(exc_info.value), (
            f"Expected 'DATA_BLOCKED_UNTIL_SEASON_2' in error message, got: {exc_info.value}"
        )

    def test_blocked_regardless_of_engine_list_length(self) -> None:
        """regime_skill_weights is blocked for any engine list (even single engine)."""
        cb = _load_cb()
        regime = cb.RegimeVector(
            is_playoff=True,
            pace_tier=2,
            margin_bucket=3,
            disagree_tier=2,
            coverage_flags=7,
            n_engines=1,
        )
        with pytest.raises(NotImplementedError) as exc_info:
            cb.regime_skill_weights(["only_engine"], regime)
        assert "DATA_BLOCKED_UNTIL_SEASON_2" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. B8_brain_equalweight.json: exists, parses, records beats_equal_weight=false
# ---------------------------------------------------------------------------

_MARKER_PATH = os.path.join(
    _ROOT, "data", "registry", "build_checks", "B8_brain_equalweight.json"
)


class TestB8MarkerJson:
    """B8_brain_equalweight.json must exist, parse, and honestly record the backtest outcome."""

    def test_marker_file_exists(self) -> None:
        """The B8 marker JSON file must exist on disk."""
        assert os.path.exists(_MARKER_PATH), (
            f"B8_brain_equalweight.json not found at {_MARKER_PATH}"
        )

    def test_marker_is_valid_json(self) -> None:
        """The B8 marker must parse as valid JSON."""
        with open(_MARKER_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, dict), "B8 marker must be a JSON object"

    def _load_marker(self) -> Dict[str, Any]:
        with open(_MARKER_PATH, encoding="utf-8") as fh:
            return json.load(fh)

    def test_beats_equal_weight_is_false(self) -> None:
        """beats_equal_weight must be False (the honest backtest outcome)."""
        data = self._load_marker()
        assert "beats_equal_weight" in data, "marker missing 'beats_equal_weight' key"
        assert data["beats_equal_weight"] is False, (
            f"beats_equal_weight={data['beats_equal_weight']!r}, expected False. "
            "The 5-fold CV-std gate rejected learned weights on 1 season / N_eff~1.636."
        )

    def test_beats_equal_weight_rationale_present(self) -> None:
        """A non-empty rationale string must accompany the false result."""
        data = self._load_marker()
        rationale = data.get("beats_equal_weight_rationale", "")
        assert isinstance(rationale, str) and len(rationale) > 20, (
            "beats_equal_weight_rationale must be a non-empty explanation string"
        )

    def test_honesty_class_is_research(self) -> None:
        """honesty_class must be 'research' (not 'proven' or 'proven-capable')."""
        data = self._load_marker()
        assert data.get("honesty_class") == "research", (
            f"honesty_class={data.get('honesty_class')!r}, expected 'research'"
        )

    def test_rung_2_deferred_data_blocked(self) -> None:
        """The marker must record that Rung-2 is DATA_BLOCKED_UNTIL_SEASON_2."""
        data = self._load_marker()
        gate_field = data.get("rung_2_gate", "")
        assert "DATA_BLOCKED_UNTIL_SEASON_2" in str(gate_field), (
            f"rung_2_gate={gate_field!r} must contain 'DATA_BLOCKED_UNTIL_SEASON_2'"
        )

    def test_asof_present(self) -> None:
        """marker must have an 'asof' date field."""
        data = self._load_marker()
        assert "asof" in data, "marker missing 'asof' date"
        assert data["asof"] == "2026-06-08", f"asof={data['asof']!r}"

    def test_seasons_from_live_json(self) -> None:
        """The marker's seasons list must match what engine_reliability_weights.json records."""
        data = self._load_marker()
        # Load the live source of truth
        rw_path = os.path.join(
            _ROOT, "data", "cache", "team_system", "engine_reliability_weights.json"
        )
        if not os.path.exists(rw_path):
            pytest.skip("engine_reliability_weights.json absent; skip cross-check")
        with open(rw_path, encoding="utf-8") as fh:
            rw = json.load(fh)
        live_seasons = rw.get("seasons", [])
        marker_seasons = data.get("seasons", [])
        assert set(marker_seasons) == set(live_seasons), (
            f"marker seasons {marker_seasons} != live json seasons {live_seasons}"
        )

    def test_n_graded_matches_live_json(self) -> None:
        """The marker's n_graded must match engine_reliability_weights.json."""
        data = self._load_marker()
        rw_path = os.path.join(
            _ROOT, "data", "cache", "team_system", "engine_reliability_weights.json"
        )
        if not os.path.exists(rw_path):
            pytest.skip("engine_reliability_weights.json absent; skip cross-check")
        with open(rw_path, encoding="utf-8") as fh:
            rw = json.load(fh)
        live_n = rw.get("n_graded")
        marker_n = data.get("n_graded")
        assert marker_n == live_n, (
            f"marker n_graded={marker_n} != live json n_graded={live_n}"
        )

    def test_architecture_reference_present(self) -> None:
        """The marker must contain a reference to the ARCHITECTURE.md file."""
        data = self._load_marker()
        ref = data.get("reference", "")
        assert "ARCHITECTURE" in str(ref), (
            f"'reference' field should cite ARCHITECTURE.md, got: {ref!r}"
        )

    def test_rung_active_is_zero(self) -> None:
        """rung_active must be 0 (equal-weight rung, not a learned weight)."""
        data = self._load_marker()
        assert "rung_active" in data, "marker missing 'rung_active'"
        assert data["rung_active"] == 0, (
            f"rung_active={data['rung_active']!r}, expected 0 (Rung 0 = equal-weight default)"
        )
