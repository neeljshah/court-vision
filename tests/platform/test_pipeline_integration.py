"""tests/platform/test_pipeline_integration.py — Unit tests for pipeline_integration.py.

Assertions:
  1. banner present, contains "NO edge" (case-insensitive).
  2. edge_claimed is False.
  3. surface has moneyline/totals/spreads/score_means with numeric [0,1] probs.
  4. sgp_lifts entries carry data-BLOCKED note and a numeric lift.
  5. No key/value asserts positive ROI or edge.

Run: PYTHONPATH=<repo-root>
  python -m pytest tests/platform/test_pipeline_integration.py -q
"""
from __future__ import annotations
import math, sys
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.sim_framework import JointDistribution
from scripts.platformkit.sgp_pricer import leg_over_total, leg_side_win
from scripts.platformkit.pipeline_integration import assemble_read, build_default_market_specs

_H, _A, _SEED, _N = 0, 1, 99, 2000


@pytest.fixture(scope="module")
def nba_jd() -> JointDistribution:
    rng = np.random.default_rng(_SEED)
    home = np.clip(rng.normal(112.0, 12.0, _N), 0, None)
    away = np.clip(rng.normal(109.0, 12.0, _N), 0, None)
    return JointDistribution(np.stack([home, away], axis=1), joint_quality="simulated")


@pytest.fixture(scope="module")
def nba_sgp_legs():
    return [leg_side_win(_H, _A, "a"), leg_over_total(_H, _A, 220.5)]


@pytest.fixture(scope="module")
def nba_read(nba_jd, nba_sgp_legs) -> dict:
    return assemble_read("nba", nba_jd,
                         total_lines=[210.5, 215.5, 220.5, 225.5],
                         spread_lines=[-4.5, -1.5, 1.5, 4.5],
                         sgp_legs=nba_sgp_legs, calibration=None)


# ---------------------------------------------------------------------------
# 1. Banner: present, string, contains "NO edge"
# ---------------------------------------------------------------------------
class TestBanner:
    def test_banner_key_present(self, nba_read):
        assert "banner" in nba_read

    def test_banner_is_nonempty_string(self, nba_read):
        assert isinstance(nba_read["banner"], str) and len(nba_read["banner"]) > 0

    def test_banner_contains_no_edge(self, nba_read):
        assert "no edge" in nba_read["banner"].lower(), (
            f"banner must contain 'NO edge' (case-insensitive); got: {nba_read['banner']!r}"
        )


# ---------------------------------------------------------------------------
# 2. edge_claimed is always False
# ---------------------------------------------------------------------------
class TestEdgeClaimed:
    def test_edge_claimed_is_false(self, nba_read):
        assert nba_read["edge_claimed"] is False

    def test_edge_claimed_not_truthy(self, nba_read):
        assert not nba_read["edge_claimed"]


# ---------------------------------------------------------------------------
# 3. Surface: required keys, numeric [0,1] probabilities
# ---------------------------------------------------------------------------
class TestSurface:
    def test_surface_has_required_keys(self, nba_read):
        surf = nba_read["surface"]
        for key in ("moneyline", "totals", "spreads", "score_means", "intervals"):
            assert key in surf

    def test_moneyline_home_away_present(self, nba_read):
        ml = nba_read["surface"]["moneyline"]
        assert "home" in ml and "away" in ml

    def test_moneyline_probs_in_unit_interval(self, nba_read):
        for side, val in nba_read["surface"]["moneyline"].items():
            assert isinstance(val, float) and 0.0 <= val <= 1.0, (
                f"moneyline[{side}]={val!r} outside [0,1]"
            )

    def test_moneyline_sums_to_one(self, nba_read):
        total = sum(nba_read["surface"]["moneyline"].values())
        assert abs(total - 1.0) < 1e-6, f"moneyline sum={total}"

    def test_totals_nonempty_with_valid_probs(self, nba_read):
        tots = nba_read["surface"]["totals"]
        assert len(tots) > 0
        for t in tots:
            assert 0.0 <= t["over"] <= 1.0 and 0.0 <= t["under"] <= 1.0
            assert abs(t["over"] + t["under"] - 1.0) < 1e-6

    def test_spreads_nonempty_with_valid_probs(self, nba_read):
        sprs = nba_read["surface"]["spreads"]
        assert len(sprs) > 0
        for sp in sprs:
            assert 0.0 <= sp["cover_home"] <= 1.0

    def test_score_means_numeric_and_plausible(self, nba_read):
        means = nba_read["surface"]["score_means"]
        assert math.isfinite(means["home"]) and math.isfinite(means["away"])
        assert 80.0 <= means["home"] <= 150.0
        assert 80.0 <= means["away"] <= 150.0

    def test_intervals_lo_lt_hi(self, nba_read):
        ivs = nba_read["surface"]["intervals"]
        for side in ("home", "away"):
            lo, hi = ivs[side]
            assert math.isfinite(lo) and math.isfinite(hi) and lo < hi


# ---------------------------------------------------------------------------
# 4. SGP lifts: data-BLOCKED note and numeric lift
# ---------------------------------------------------------------------------
class TestSgpLifts:
    def test_sgp_lifts_nonempty_when_legs_given(self, nba_read):
        assert len(nba_read["sgp_lifts"]) > 0

    def test_sgp_lifts_carry_data_blocked_note(self, nba_read):
        for entry in nba_read["sgp_lifts"]:
            note_low = entry.get("note", "").lower()
            assert "data-blocked" in note_low or "data_blocked" in note_low, (
                f"note must mention data-BLOCKED; got: {entry.get('note')!r}"
            )

    def test_sgp_lifts_lift_is_finite_float(self, nba_read):
        for entry in nba_read["sgp_lifts"]:
            if "error" in entry:
                continue
            lift = entry.get("lift")
            assert lift is not None and isinstance(lift, float) and math.isfinite(lift)

    def test_sgp_lifts_joint_in_unit_interval(self, nba_read):
        for entry in nba_read["sgp_lifts"]:
            if "error" in entry:
                continue
            assert 0.0 <= entry["joint"] <= 1.0

    def test_sgp_lifts_empty_when_no_legs(self, nba_jd):
        read = assemble_read("nba", nba_jd, sgp_legs=None)
        assert read["sgp_lifts"] == []


# ---------------------------------------------------------------------------
# 5. No positive ROI/edge claims in any returned value
# ---------------------------------------------------------------------------
class TestNoEdgeClaims:
    _BANNED = {"profit", "guaranteed", "beat the market", "positive roi"}
    _EDGE_DENIAL_PHRASES = (
        "no edge", "not an edge", "data-blocked", "data_blocked",
        "no model edge", "no claimed", "efficient",
    )

    def _scan(self, obj, path: str = "") -> None:
        if isinstance(obj, str):
            low = obj.lower()
            for word in self._BANNED:
                if word in low:
                    raise AssertionError(
                        f"Banned term {word!r} at path={path!r}: {obj!r}"
                    )
            if "edge" in low:
                is_denial = any(p in low for p in self._EDGE_DENIAL_PHRASES)
                if not is_denial:
                    raise AssertionError(
                        f"Positive 'edge' claim at path={path!r}: {obj!r}"
                    )
        elif isinstance(obj, dict):
            for k, v in obj.items():
                self._scan(v, path=f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._scan(item, path=f"{path}[{i}]")

    def test_no_roi_or_profit_claim_in_output(self, nba_read):
        self._scan(nba_read)

    def test_edge_claimed_false_sentinel(self, nba_read):
        assert nba_read["edge_claimed"] is False


# ---------------------------------------------------------------------------
# 6. Multi-sport structural integrity
# ---------------------------------------------------------------------------
class TestMultiSportIntegrity:
    @pytest.mark.parametrize("sport", ["nba", "soccer", "mlb", "tennis"])
    def test_assemble_read_returns_valid_dict(self, sport):
        rng = np.random.default_rng(7)
        home = np.clip(rng.normal(10.0, 5.0, 1000), 0, None)
        away = np.clip(rng.normal(9.0, 5.0, 1000), 0, None)
        jd = JointDistribution(np.stack([home, away], axis=1), joint_quality="simulated")
        read = assemble_read(sport, jd)
        assert read["sport"] == sport
        assert read["edge_claimed"] is False
        assert "no edge" in read["banner"].lower()

    @pytest.mark.parametrize("sport", ["nba", "soccer", "mlb", "tennis"])
    def test_default_market_specs_nonempty(self, sport):
        specs = build_default_market_specs(sport)
        assert len(specs["total_lines"]) > 0 and len(specs["spread_lines"]) > 0

    def test_unknown_sport_gets_fallback_specs(self):
        specs = build_default_market_specs("curling")
        assert len(specs["total_lines"]) > 0


# ---------------------------------------------------------------------------
# 7. Calibration block
# ---------------------------------------------------------------------------
class TestCalibration:
    def test_calibration_pending_when_no_labels(self, nba_read):
        assert nba_read["calibration"]["status"] == "pending"

    def test_calibration_measured_when_supplied(self, nba_jd):
        cal = {"status": "measured", "raw_ece": 0.04, "recal_ece": 0.03, "n": 500}
        read = assemble_read("nba", nba_jd, calibration=cal)
        assert read["calibration"]["status"] == "measured"
        assert read["calibration"]["raw_ece"] == 0.04


# ---------------------------------------------------------------------------
# 8. Provenance list
# ---------------------------------------------------------------------------
class TestProvenance:
    def test_provenance_is_nonempty_list(self, nba_read):
        pv = nba_read["provenance"]
        assert isinstance(pv, list) and len(pv) > 0

    def test_provenance_references_sim_framework(self, nba_read):
        combined = " ".join(nba_read["provenance"]).lower()
        assert "sim_framework" in combined or "jointdistribution" in combined
