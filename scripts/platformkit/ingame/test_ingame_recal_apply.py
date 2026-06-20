"""Per-file tests for ingame_recal_apply.py.

Acceptance criteria (from BACKLOG.md ig-recal-apply):
  1. loads nba_recal.json and recalibrates p_home per time-bucket.
  2. absent/empty file -> exact identity passthrough (p_home unchanged, recal_applied=False).
  3. monotone isotonic map preserved: output is monotone non-decreasing in input p_home.
  4. never raises on malformed/missing keys.
  5. p stays in [0,1].
  6. no $ key in any output dict.

No dollar P&L; calibration not edge; ASCII only; per-file test only.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List

import pytest

from scripts.platformkit.ingame.ingame_recal_apply import (
    apply_recal,
    load_recal_map,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recal_json(buckets: Dict, n_buckets: int = 4,
                     verdict: str = "SHIP") -> Dict:
    """Build a minimal valid nba_recal.json payload."""
    return {
        "sport": "nba",
        "verdict": verdict,
        "n_buckets": n_buckets,
        "buckets": buckets,
    }


def _identity_bucket() -> Dict:
    """A bucket map that is the identity: x=[0,1], y=[0,1]."""
    return {"x": [0.0, 1.0], "y": [0.0, 1.0]}


def _shrink_bucket(lo: float = 0.2, hi: float = 0.8) -> Dict:
    """A bucket map that de-shrinks probabilities toward 0/1 (un-shrink).

    Input [0,0.5,1] -> output [0, 0.5, 1], but anything in (0,0.5) is pushed lower
    and (0.5,1) higher. We use a simple piecewise map: x=[0,lo,0.5,hi,1], y=[0,0,0.5,1,1].
    This is monotone non-decreasing, mimicking what IsotonicRegression would learn.
    """
    x = [0.0, lo, 0.5, hi, 1.0]
    y = [0.0, 0.0, 0.5, 1.0, 1.0]
    return {"x": x, "y": y}


def _make_blend_result(p_home: float = 0.6,
                       remaining_frac: float = 0.25,
                       **extra) -> Dict[str, Any]:
    """Minimal blend_apply.apply_surface-compatible result dict."""
    r: Dict[str, Any] = {
        "p_home": p_home,
        "p_away": 1.0 - p_home,
        "w": 0.5,
        "remaining_frac": remaining_frac,
        "variance": 0.05,
        "p_live": p_home,
        "basis": "blend",
        "edge_claimed": False,
    }
    r.update(extra)
    return r


def _write_recal_json(tmp_dir: str, payload: Dict) -> str:
    path = os.path.join(tmp_dir, "nba_recal.json")
    with open(path, "w", encoding="ascii") as f:
        json.dump(payload, f)
    return path


def _no_dollar_keys(d: Dict) -> bool:
    """Assert no key contains '$' anywhere in the output."""
    for k in d:
        if "$" in str(k):
            return False
        v = d[k]
        if isinstance(v, dict) and not _no_dollar_keys(v):
            return False
    return True


# ---------------------------------------------------------------------------
# 1. load_recal_map -- file-level tests
# ---------------------------------------------------------------------------

class TestLoadRecalMap:
    def test_absent_file_returns_none(self):
        result = load_recal_map("/nonexistent/path/nba_recal.json")
        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        p = tmp_path / "nba_recal.json"
        p.write_text("", encoding="ascii")
        assert load_recal_map(str(p)) is None

    def test_invalid_json_returns_none(self, tmp_path):
        p = tmp_path / "nba_recal.json"
        p.write_text("{not valid json", encoding="ascii")
        assert load_recal_map(str(p)) is None

    def test_valid_map_loads(self, tmp_path):
        payload = _make_recal_json({"0": _identity_bucket(),
                                    "1": _identity_bucket(),
                                    "2": _identity_bucket(),
                                    "3": _identity_bucket()})
        path = _write_recal_json(str(tmp_path), payload)
        result = load_recal_map(path)
        assert result is not None
        assert result["verdict"] == "SHIP"
        assert "buckets" in result

    def test_missing_buckets_key_returns_none(self, tmp_path):
        payload = {"sport": "nba", "verdict": "SHIP", "n_buckets": 4}
        path = _write_recal_json(str(tmp_path), payload)
        assert load_recal_map(path) is None

    def test_empty_buckets_returns_none(self, tmp_path):
        payload = _make_recal_json({})
        path = _write_recal_json(str(tmp_path), payload)
        assert load_recal_map(path) is None

    def test_bucket_with_mismatched_xy_is_invalid(self, tmp_path):
        # A bucket where len(x) != len(y)
        bad_bucket = {"x": [0.0, 1.0], "y": [0.0]}
        payload = _make_recal_json({"0": bad_bucket})
        path = _write_recal_json(str(tmp_path), payload)
        # Only one bucket, which is invalid -> should return None
        assert load_recal_map(path) is None

    def test_one_valid_bucket_among_bad_is_accepted(self, tmp_path):
        bad_bucket = {"x": [0.0, 1.0], "y": [0.0]}  # mismatched
        good_bucket = _identity_bucket()
        payload = _make_recal_json({"0": bad_bucket, "1": good_bucket})
        path = _write_recal_json(str(tmp_path), payload)
        # At least one valid bucket -> load should succeed
        result = load_recal_map(path)
        assert result is not None


# ---------------------------------------------------------------------------
# 2. apply_recal -- identity passthrough when no map
# ---------------------------------------------------------------------------

class TestIdentityPassthrough:
    def test_none_map_identity(self):
        br = _make_blend_result(p_home=0.65, remaining_frac=0.30)
        out = apply_recal(br, None)
        assert out["p_home"] == pytest.approx(0.65)
        assert out["recal_applied"] is False
        assert out["recal_bucket"] is None

    def test_none_map_preserves_all_keys(self):
        br = _make_blend_result(p_home=0.70, remaining_frac=0.50)
        out = apply_recal(br, None)
        for k in br:
            assert k in out

    def test_absent_file_identity(self):
        recal = load_recal_map("/nonexistent/nba_recal.json")
        br = _make_blend_result(p_home=0.55)
        out = apply_recal(br, recal)
        assert out["p_home"] == pytest.approx(0.55)
        assert out["recal_applied"] is False

    def test_identity_map_passthrough(self, tmp_path):
        """An identity (x=[0,1],y=[0,1]) bucket must not change p_home."""
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            br = _make_blend_result(p_home=p, remaining_frac=0.25)
            out = apply_recal(br, recal)
            assert out["p_home"] == pytest.approx(p, abs=1e-9)


# ---------------------------------------------------------------------------
# 3. apply_recal -- correct time-bucket routing
# ---------------------------------------------------------------------------

class TestTimeBucketRouting:
    """Verify each frac_elapsed routes to the correct bucket (Q1..Q4)."""

    def _build_marked_recal(self, tmp_path) -> tuple:
        """Build a recal with distinct y-shifts per bucket so we can detect which fired."""
        # bucket b: x=[0,1], y=[b*0.05, b*0.05+1] clipped; use simple offsets
        # Actually make each bucket push p_home toward a distinct target range:
        # bucket 0: x=[0.5], y=[0.1] (collapses to 0.1 for any input -- extreme)
        # We just use distinct identity-like maps with a small constant lift per bucket.
        def _bucket_with_lift(lift: float) -> Dict:
            # x = [0, 0.5, 1], y clipped to [0,1] with a known shift
            y_lo = max(0.0, 0.0 + lift)
            y_mid = max(0.0, min(1.0, 0.5 + lift))
            y_hi = min(1.0, 1.0 + lift)
            return {"x": [0.0, 0.5, 1.0], "y": [y_lo, y_mid, y_hi]}

        buckets = {str(b): _bucket_with_lift(b * 0.02) for b in range(4)}
        payload = _make_recal_json(buckets)
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)
        return recal, buckets

    def test_early_routes_to_bucket0(self, tmp_path):
        recal, _ = self._build_marked_recal(tmp_path)
        # remaining_frac=0.99 -> frac_elapsed=0.01 -> bucket 0
        br = _make_blend_result(p_home=0.50, remaining_frac=0.99)
        out = apply_recal(br, recal)
        assert out["recal_bucket"] == 0

    def test_late_routes_to_bucket3(self, tmp_path):
        recal, _ = self._build_marked_recal(tmp_path)
        # remaining_frac=0.01 -> frac_elapsed=0.99 -> bucket 3
        br = _make_blend_result(p_home=0.50, remaining_frac=0.01)
        out = apply_recal(br, recal)
        assert out["recal_bucket"] == 3

    def test_midgame_routes_to_bucket2(self, tmp_path):
        recal, _ = self._build_marked_recal(tmp_path)
        # remaining_frac=0.30 -> frac_elapsed=0.70 -> bucket min(3, floor(0.70*4))=2
        br = _make_blend_result(p_home=0.50, remaining_frac=0.30)
        out = apply_recal(br, recal)
        assert out["recal_bucket"] == 2


# ---------------------------------------------------------------------------
# 4. monotone isotonic map preserved in output
# ---------------------------------------------------------------------------

class TestMonotonePreserved:
    """output p_home must be monotone non-decreasing in input p_home."""

    def test_monotone_output_on_shrink_bucket(self, tmp_path):
        bucket = _shrink_bucket(lo=0.2, hi=0.8)
        payload = _make_recal_json({str(b): bucket for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)
        inputs = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        outputs = []
        for p in inputs:
            br = _make_blend_result(p_home=p, remaining_frac=0.25)
            out = apply_recal(br, recal)
            outputs.append(out["p_home"])
        # Monotone non-decreasing
        for i in range(1, len(outputs)):
            assert outputs[i] >= outputs[i - 1] - 1e-12, (
                f"Monotone violated at i={i}: {outputs[i-1]:.4f} -> {outputs[i]:.4f}"
            )

    def test_monotone_identity_map(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)
        inputs = [i / 20.0 for i in range(21)]
        outputs = [apply_recal(_make_blend_result(p_home=p, remaining_frac=0.5),
                               recal)["p_home"] for p in inputs]
        for i in range(1, len(outputs)):
            assert outputs[i] >= outputs[i - 1] - 1e-12


# ---------------------------------------------------------------------------
# 5. never raises on malformed / missing keys
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """apply_recal + load_recal_map must never raise under adversarial inputs."""

    @pytest.mark.parametrize("bad_result", [
        {},
        {"p_home": "not_a_float"},
        {"p_home": None},
        {"p_home": float("nan")},
        {"p_home": float("inf")},
        {"remaining_frac": -99.0},
    ])
    def test_bad_blend_result_no_raise(self, bad_result):
        try:
            out = apply_recal(bad_result, None)
            assert isinstance(out, dict)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"apply_recal raised unexpectedly: {exc}")

    @pytest.mark.parametrize("bad_recal", [
        {},
        {"buckets": None},
        {"buckets": {"0": {}}},
        {"buckets": {"0": {"x": [], "y": []}}},
        {"buckets": {"0": {"x": [0.5], "y": [0.5, 0.8]}}},
        {"sport": "nba"},  # missing buckets
        None,
    ])
    def test_bad_recal_map_no_raise(self, bad_recal):
        br = _make_blend_result()
        try:
            out = apply_recal(br, bad_recal)
            assert isinstance(out, dict)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"apply_recal raised unexpectedly: {exc}")

    def test_missing_remaining_frac_defaults_to_identity_bucket(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)
        # No remaining_frac -> defaults to 1.0 -> frac_elapsed=0.0 -> bucket 0
        br = {"p_home": 0.65, "p_away": 0.35}
        out = apply_recal(br, recal)
        assert isinstance(out, dict)
        assert 0.0 <= out["p_home"] <= 1.0


# ---------------------------------------------------------------------------
# 6. p stays in [0, 1]
# ---------------------------------------------------------------------------

class TestProbabilityBounds:
    def test_p_home_in_unit_interval(self, tmp_path):
        # Use a bucket map that tries to push outside [0,1]
        extreme_bucket = {"x": [0.0, 1.0], "y": [-0.5, 1.5]}
        payload = _make_recal_json({str(b): extreme_bucket for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)

        for p in [0.0, 0.1, 0.5, 0.9, 1.0]:
            br = _make_blend_result(p_home=p, remaining_frac=0.25)
            out = apply_recal(br, recal)
            assert 0.0 <= out["p_home"] <= 1.0, (
                f"p_home={out['p_home']} out of [0,1] for input {p}"
            )
            assert 0.0 <= out["p_away"] <= 1.0

    def test_p_home_plus_p_away_approx_one(self, tmp_path):
        payload = _make_recal_json({str(b): _shrink_bucket() for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)
        for p in [0.2, 0.4, 0.6, 0.8]:
            br = _make_blend_result(p_home=p, remaining_frac=0.5)
            out = apply_recal(br, recal)
            assert out["p_home"] + out["p_away"] == pytest.approx(1.0, abs=1e-9)

    def test_extreme_pregame_probabilities_clamped(self):
        """Inputs already at 0 or 1 must stay in [0,1]."""
        for p_extreme in [-0.1, 0.0, 1.0, 1.1]:
            br = _make_blend_result(p_home=p_extreme, remaining_frac=0.5)
            out = apply_recal(br, None)
            assert 0.0 <= out["p_home"] <= 1.0


# ---------------------------------------------------------------------------
# 7. no $ key anywhere
# ---------------------------------------------------------------------------

class TestNoDollarKey:
    def test_no_dollar_key_identity(self):
        br = _make_blend_result(p_home=0.60)
        out = apply_recal(br, None)
        assert _no_dollar_keys(out), "Dollar key found in identity output"

    def test_no_dollar_key_with_map(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)
        br = _make_blend_result(p_home=0.70, remaining_frac=0.20)
        out = apply_recal(br, recal)
        assert _no_dollar_keys(out), "Dollar key found in recalibrated output"

    def test_no_dollar_key_in_loaded_map(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)
        assert _no_dollar_keys(recal or {}), "Dollar key found in loaded recal map"


# ---------------------------------------------------------------------------
# 8. full integration: load from disk and recalibrate (canonical acceptance test)
# ---------------------------------------------------------------------------

class TestFullIntegration:
    """Simulate the ig-recal-persist -> ig-recal-apply pipeline end to end."""

    def test_recalibrate_per_time_bucket(self, tmp_path):
        """Load a valid nba_recal.json and recalibrate p_home per bucket.

        Each time bucket gets a distinct monotone map. Verify that the correct
        bucket map is applied in each region and that all outputs are valid.
        """
        # Build per-bucket maps with known transforms
        def _shift_map(shift: float) -> Dict:
            # x=[0,0.5,1], y clamped with shift applied at midpoint only
            return {
                "x": [0.0, 0.5, 1.0],
                "y": [max(0.0, 0.0), max(0.0, min(1.0, 0.5 + shift)), 1.0],
            }

        buckets = {
            "0": _shift_map(0.00),   # Q1: identity-like
            "1": _shift_map(0.05),   # Q2: slight upward push at midpoint
            "2": _shift_map(0.10),   # Q3: moderate push
            "3": _shift_map(0.15),   # Q4: largest push
        }
        payload = _make_recal_json(buckets)
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)

        assert recal is not None, "Failed to load valid recal map"
        assert recal["n_buckets"] == 4

        # Test one state per bucket
        # bucket 0: remaining_frac=0.99 -> frac_elapsed~0.01
        # bucket 1: remaining_frac=0.75 -> frac_elapsed~0.25
        # bucket 2: remaining_frac=0.50 -> frac_elapsed~0.50
        # bucket 3: remaining_frac=0.10 -> frac_elapsed~0.90
        cases = [
            (0.99, 0, 0.50),
            (0.75, 1, 0.50),
            (0.50, 2, 0.50),
            (0.10, 3, 0.50),
        ]
        for remaining, expected_bucket, p_in in cases:
            br = _make_blend_result(p_home=p_in, remaining_frac=remaining)
            out = apply_recal(br, recal)
            assert out["recal_applied"] is True
            assert out["recal_bucket"] == expected_bucket
            assert 0.0 <= out["p_home"] <= 1.0
            assert 0.0 <= out["p_away"] <= 1.0
            assert abs(out["p_home"] + out["p_away"] - 1.0) < 1e-9
            assert _no_dollar_keys(out)

    def test_roundtrip_identity_unchanged(self, tmp_path):
        """A recal map of pure identity knots leaves p_home unchanged."""
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        recal = load_recal_map(path)

        test_ps = [0.1, 0.3, 0.5, 0.7, 0.9]
        for p in test_ps:
            br = _make_blend_result(p_home=p, remaining_frac=0.40)
            out = apply_recal(br, recal)
            assert out["p_home"] == pytest.approx(p, abs=1e-9), (
                f"Identity map changed p_home from {p} to {out['p_home']}"
            )
