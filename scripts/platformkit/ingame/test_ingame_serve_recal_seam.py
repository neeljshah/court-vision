"""Per-file tests for ingame_serve_recal_seam.py.

Acceptance criteria (from BACKLOG.md ig-serve-recal-seam):
  1. With a present recal map, recalibrate_served maps p_home per time-bucket
     matching ingame_recal_apply.apply_recal.
  2. absent/empty surfaces/nba_recal.json -> exact identity passthrough (do-no-harm).
  3. monotone iso map order preserved (non-decreasing output for non-decreasing input).
  4. missing/None frac_elapsed -> identity passthrough.
  5. provenance string records '+recal(applied)' vs '+recal(identity:no-map)'.
  6. no dollar-sign key in any output.
  7. never raises on null payload.

No dollar P&L; calibration not edge; ASCII only; per-file test only.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import pytest

import scripts.platformkit.ingame.ingame_serve_recal_seam as _seam
from scripts.platformkit.ingame.ingame_serve_recal_seam import (
    recalibrate_served,
    reload_map,
)
from scripts.platformkit.ingame.ingame_recal_apply import (
    apply_recal,
    load_recal_map,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recal_json(buckets: Dict, n_buckets: int = 4,
                     verdict: str = "SHIP") -> Dict:
    return {
        "sport": "nba",
        "verdict": verdict,
        "n_buckets": n_buckets,
        "buckets": buckets,
    }


def _identity_bucket() -> Dict:
    return {"x": [0.0, 1.0], "y": [0.0, 1.0]}


def _shift_bucket(shift: float) -> Dict:
    """Monotone map with a midpoint shift for discriminating buckets."""
    y_mid = max(0.0, min(1.0, 0.5 + shift))
    return {"x": [0.0, 0.5, 1.0], "y": [0.0, y_mid, 1.0]}


def _write_recal_json(tmp_dir: str, payload: Dict) -> str:
    path = os.path.join(tmp_dir, "nba_recal.json")
    with open(path, "w", encoding="ascii") as f:
        json.dump(payload, f)
    return path


def _no_dollar_keys(d: Dict) -> bool:
    for k in d:
        if "$" in str(k):
            return False
        v = d[k]
        if isinstance(v, dict) and not _no_dollar_keys(v):
            return False
    return True


def _inject_map(tmp_path, payload: Dict) -> str:
    """Write payload to a tmp nba_recal.json and inject into the seam cache."""
    path = _write_recal_json(str(tmp_path), payload)
    reload_map(path=path)
    return path


def _clear_seam():
    """Reset seam cache to a clean (unloaded) state without a path override."""
    _seam._MAP_CACHE = None
    _seam._MAP_LOADED = False
    _seam._MAP_PATH_OVERRIDE = None


# ---------------------------------------------------------------------------
# 1. With present map: recalibrate_served matches apply_recal directly
# ---------------------------------------------------------------------------

class TestMatchesApplyRecal:
    """Verify the seam delegates correctly to apply_recal for each bucket."""

    def test_maps_p_home_per_bucket(self, tmp_path):
        """recalibrate_served output must equal apply_recal output for same inputs."""
        buckets = {str(b): _shift_bucket(b * 0.04) for b in range(4)}
        payload = _make_recal_json(buckets)
        path = _inject_map(tmp_path, payload)
        recal_map = load_recal_map(path)

        # Sample (remaining_frac, p_home) pairs covering all four buckets
        # bucket b: frac_elapsed in [b/4, (b+1)/4)
        # remaining_frac = 1 - frac_elapsed
        cases = [
            (0.99, 0.55),   # bucket 0
            (0.74, 0.60),   # bucket 1
            (0.49, 0.65),   # bucket 2
            (0.10, 0.70),   # bucket 3
        ]
        for remaining_frac, p_in in cases:
            frac_elapsed = 1.0 - remaining_frac
            seam_out = recalibrate_served(p_home=p_in, frac_elapsed=frac_elapsed)

            blend_stub = {
                "p_home": p_in,
                "p_away": 1.0 - p_in,
                "remaining_frac": remaining_frac,
            }
            direct_out = apply_recal(blend_stub, recal_map)

            assert seam_out["p_home"] == pytest.approx(direct_out["p_home"], abs=1e-9), (
                f"Mismatch at remaining={remaining_frac}, p={p_in}: "
                f"seam={seam_out['p_home']:.6f} direct={direct_out['p_home']:.6f}"
            )
            assert seam_out["recal_applied"] == direct_out["recal_applied"]
            assert seam_out["recal_bucket"] == direct_out["recal_bucket"]

    def test_recal_applied_true_with_valid_map(self, tmp_path):
        """recal_applied must be True when a valid map is present and used."""
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        out = recalibrate_served(p_home=0.6, frac_elapsed=0.5)
        assert out["recal_applied"] is True

    def test_provenance_applied_string(self, tmp_path):
        """Provenance must be '+recal(applied)' when map was used."""
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        out = recalibrate_served(p_home=0.6, frac_elapsed=0.5)
        assert out["recal_provenance"] == "+recal(applied)"


# ---------------------------------------------------------------------------
# 2. Absent/empty map -> exact identity passthrough
# ---------------------------------------------------------------------------

class TestAbsentMapIdentity:
    """Absent or empty nba_recal.json must leave p_home unchanged."""

    def test_absent_file_identity(self, tmp_path):
        nonexistent = os.path.join(str(tmp_path), "nba_recal.json")
        reload_map(path=nonexistent)
        p_in = 0.63
        out = recalibrate_served(p_home=p_in, frac_elapsed=0.5)
        assert out["p_home"] == pytest.approx(p_in)
        assert out["recal_applied"] is False
        assert out["recal_bucket"] is None

    def test_empty_file_identity(self, tmp_path):
        path = os.path.join(str(tmp_path), "nba_recal.json")
        with open(path, "w", encoding="ascii") as f:
            f.write("")
        reload_map(path=path)
        p_in = 0.45
        out = recalibrate_served(p_home=p_in, frac_elapsed=0.3)
        assert out["p_home"] == pytest.approx(p_in)
        assert out["recal_applied"] is False

    def test_malformed_json_identity(self, tmp_path):
        path = os.path.join(str(tmp_path), "nba_recal.json")
        with open(path, "w", encoding="ascii") as f:
            f.write("{bad json}")
        reload_map(path=path)
        p_in = 0.72
        out = recalibrate_served(p_home=p_in, frac_elapsed=0.8)
        assert out["p_home"] == pytest.approx(p_in)
        assert out["recal_applied"] is False

    def test_empty_buckets_identity(self, tmp_path):
        payload = {"sport": "nba", "verdict": "SHIP", "buckets": {}}
        _inject_map(tmp_path, payload)
        p_in = 0.55
        out = recalibrate_served(p_home=p_in, frac_elapsed=0.5)
        assert out["p_home"] == pytest.approx(p_in)
        assert out["recal_applied"] is False

    def test_provenance_no_map_string_on_absent(self, tmp_path):
        nonexistent = os.path.join(str(tmp_path), "missing_nba_recal.json")
        reload_map(path=nonexistent)
        out = recalibrate_served(p_home=0.5, frac_elapsed=0.5)
        assert out["recal_provenance"] == "+recal(identity:no-map)"


# ---------------------------------------------------------------------------
# 3. Monotone iso order preserved
# ---------------------------------------------------------------------------

class TestMonotonePreserved:
    """Output p_home must be monotone non-decreasing in input p_home."""

    def test_monotone_on_identity_map(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        inputs = [i / 20.0 for i in range(21)]
        outputs = [
            recalibrate_served(p_home=p, frac_elapsed=0.5)["p_home"]
            for p in inputs
        ]
        for i in range(1, len(outputs)):
            assert outputs[i] >= outputs[i - 1] - 1e-12, (
                f"Monotone violated at i={i}: {outputs[i-1]:.4f} -> {outputs[i]:.4f}"
            )

    def test_monotone_on_shift_map(self, tmp_path):
        """A shifted isotonic map must still produce monotone output."""
        bucket = {"x": [0.0, 0.2, 0.5, 0.8, 1.0], "y": [0.0, 0.0, 0.5, 1.0, 1.0]}
        payload = _make_recal_json({str(b): bucket for b in range(4)})
        _inject_map(tmp_path, payload)
        inputs = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        outputs = [
            recalibrate_served(p_home=p, frac_elapsed=0.75)["p_home"]
            for p in inputs
        ]
        for i in range(1, len(outputs)):
            assert outputs[i] >= outputs[i - 1] - 1e-12


# ---------------------------------------------------------------------------
# 4. missing/None frac_elapsed -> identity passthrough
# ---------------------------------------------------------------------------

class TestBadFracElapsed:
    """None or non-finite frac_elapsed must trigger identity passthrough."""

    @pytest.mark.parametrize("frac", [None, float("nan"), float("inf"), float("-inf")])
    def test_bad_frac_identity(self, tmp_path, frac):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        p_in = 0.65
        out = recalibrate_served(p_home=p_in, frac_elapsed=frac)
        assert out["p_home"] == pytest.approx(p_in)
        assert out["recal_applied"] is False
        assert out["recal_bucket"] is None

    @pytest.mark.parametrize("frac", [None, float("nan")])
    def test_bad_frac_provenance(self, tmp_path, frac):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        out = recalibrate_served(p_home=0.5, frac_elapsed=frac)
        assert out["recal_provenance"] == "+recal(identity:bad-frac)"


# ---------------------------------------------------------------------------
# 5. provenance strings
# ---------------------------------------------------------------------------

class TestProvenanceStrings:
    """Provenance field must distinguish applied vs identity cases."""

    def test_applied_provenance(self, tmp_path):
        payload = _make_recal_json({str(b): _shift_bucket(0.05) for b in range(4)})
        _inject_map(tmp_path, payload)
        out = recalibrate_served(p_home=0.6, frac_elapsed=0.5)
        assert "+recal(applied)" in out["recal_provenance"]

    def test_no_map_provenance(self, tmp_path):
        absent = os.path.join(str(tmp_path), "not_there.json")
        reload_map(path=absent)
        out = recalibrate_served(p_home=0.6, frac_elapsed=0.5)
        assert "identity" in out["recal_provenance"]
        assert "no-map" in out["recal_provenance"]

    def test_bad_frac_provenance_string(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        out = recalibrate_served(p_home=0.5, frac_elapsed=None)
        assert "bad-frac" in out["recal_provenance"]


# ---------------------------------------------------------------------------
# 6. No dollar key
# ---------------------------------------------------------------------------

class TestNoDollarKey:
    def test_no_dollar_identity(self, tmp_path):
        absent = os.path.join(str(tmp_path), "missing.json")
        reload_map(path=absent)
        out = recalibrate_served(p_home=0.5, frac_elapsed=0.5)
        assert _no_dollar_keys(out), "Dollar key found in identity output"

    def test_no_dollar_applied(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        out = recalibrate_served(p_home=0.6, frac_elapsed=0.5)
        assert _no_dollar_keys(out), "Dollar key found in recalibrated output"

    def test_no_dollar_with_extra(self, tmp_path):
        absent = os.path.join(str(tmp_path), "missing.json")
        reload_map(path=absent)
        out = recalibrate_served(
            p_home=0.55, frac_elapsed=0.5,
            extra={"edge_claimed": False, "provenance": "blend"},
        )
        assert _no_dollar_keys(out)


# ---------------------------------------------------------------------------
# 7. Never raises on null payload
# ---------------------------------------------------------------------------

class TestNeverRaises:
    @pytest.mark.parametrize("p_home,frac", [
        (None, 0.5),
        (None, None),
        (float("nan"), 0.5),
        (float("inf"), 0.3),
        ("not_a_float", 0.5),
        (0.5, "not_a_float"),
        (0.5, None),
    ])
    def test_never_raises(self, p_home, frac):
        _clear_seam()
        try:
            out = recalibrate_served(p_home=p_home, frac_elapsed=frac)
            assert isinstance(out, dict)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"recalibrate_served raised: {exc}")

    def test_null_extra_no_raise(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        try:
            out = recalibrate_served(p_home=0.5, frac_elapsed=0.5, extra=None)
            assert isinstance(out, dict)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"recalibrate_served raised on None extra: {exc}")


# ---------------------------------------------------------------------------
# 8. reload_map / lazy load mechanics
# ---------------------------------------------------------------------------

class TestLazyLoad:
    def test_reload_map_switches_path(self, tmp_path):
        """reload_map with a valid path must cause next call to use new map."""
        shift_bucket = _shift_bucket(0.20)
        payload = _make_recal_json({str(b): shift_bucket for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        reload_map(path=path)
        out = recalibrate_served(p_home=0.50, frac_elapsed=0.5)
        # With the shift map, p=0.5 at midpoint -> y_mid = 0.5+0.20=0.70
        assert out["p_home"] == pytest.approx(0.70, abs=1e-6)

    def test_reload_none_resets_to_default(self, tmp_path):
        """reload_map(path=None) must reset cache; next call reads default path."""
        # Point at a valid map first
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        path = _write_recal_json(str(tmp_path), payload)
        reload_map(path=path)
        out1 = recalibrate_served(p_home=0.6, frac_elapsed=0.5)
        assert out1["recal_applied"] is True

        # Reset to default (which likely has no nba_recal.json in default surfaces/)
        reload_map(path=None)
        # After reset, _MAP_LOADED is False and _MAP_PATH_OVERRIDE is None
        assert _seam._MAP_LOADED is False
        assert _seam._MAP_PATH_OVERRIDE is None


# ---------------------------------------------------------------------------
# 9. Extra keys pass-through
# ---------------------------------------------------------------------------

class TestExtraPassthrough:
    def test_extra_keys_in_output_identity(self, tmp_path):
        absent = os.path.join(str(tmp_path), "missing.json")
        reload_map(path=absent)
        out = recalibrate_served(
            p_home=0.5, frac_elapsed=0.5,
            extra={"edge_claimed": False, "game_id": "G001"},
        )
        assert out.get("game_id") == "G001"
        assert out.get("edge_claimed") is False

    def test_extra_does_not_clobber_p_home(self, tmp_path):
        absent = os.path.join(str(tmp_path), "missing.json")
        reload_map(path=absent)
        out = recalibrate_served(
            p_home=0.6, frac_elapsed=0.5,
            extra={"p_home": 0.99},  # should NOT win over the real p_home
        )
        # recalibrate_served ignores extra['p_home'] (stripped in merge logic)
        assert out["p_home"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# 10. p stays in [0,1]
# ---------------------------------------------------------------------------

class TestProbabilityBounds:
    def test_p_home_in_unit_interval(self, tmp_path):
        extreme_bucket = {"x": [0.0, 1.0], "y": [-0.5, 1.5]}
        payload = _make_recal_json({str(b): extreme_bucket for b in range(4)})
        _inject_map(tmp_path, payload)
        for p in [0.0, 0.1, 0.5, 0.9, 1.0]:
            out = recalibrate_served(p_home=p, frac_elapsed=0.5)
            assert 0.0 <= out["p_home"] <= 1.0
            assert 0.0 <= out["p_away"] <= 1.0

    def test_p_home_plus_p_away_approx_one(self, tmp_path):
        payload = _make_recal_json({str(b): _identity_bucket() for b in range(4)})
        _inject_map(tmp_path, payload)
        for p in [0.2, 0.4, 0.6, 0.8]:
            out = recalibrate_served(p_home=p, frac_elapsed=0.4)
            assert out["p_home"] + out["p_away"] == pytest.approx(1.0, abs=1e-9)
