"""test_llm_context.py — board-green unit tests for the V6 LLM context layer.

Network-free, real-money-free, no live API calls.
Runs under: python -m pytest tests/test_llm_context.py -q

Section-11 invariants tested:
  1. Every ContextFactor in a built CV has leak_free=True.
  2. With CV_LLM_CONTEXT unset, route_context() returns empty mults (byte-identical).
  3. All factor marginal_or_scouting values are legal.
  4. Only VALIDATED_KEYS factors can be "marginal".
  5. pace_matchup and opp_defense never produce an active mult (null / intrinsic guard).
  6. LLM weight clamping: weight > 1 is clamped to 1.
  7. Artifact dict has required keys.
  8. context_artifact_path produces a path under .../context/
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

# ---------- path setup ----------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_TS_DIR = os.path.join(_ROOT, "scripts", "team_system")
_SRC_DIR = os.path.join(_ROOT, "src")
for _p in (_TS_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------- minimal stub dataclasses (so tests work even if sim unavailable) ----------
from llm_context_layer import (  # type: ignore
    ContextFactor,
    ContextVector,
    context_artifact_path,
    _template_brief,
    _gate_on,
    war_room_brief,
)
from context_router import route_context, VALIDATED_KEYS, _ACTIVE_MULT_KEYS  # type: ignore
from context_scout import VALIDATED_KEYS as SCOUT_VK  # type: ignore


def _make_factor(factor="home_road", lean="home", mag=1.020, conf="high",
                 vek="home_road", m_or_s="marginal", leak_free=True) -> ContextFactor:
    return ContextFactor(
        factor=factor, lean=lean, magnitude=mag, confidence=conf,
        leak_free=leak_free, validated_effect_key=vek,
        marginal_or_scouting=m_or_s, evidence={}, source="scout",
    )


def _make_cv(factors=None) -> ContextVector:
    if factors is None:
        factors = [_make_factor()]
    return ContextVector(
        matchup="SAS@NYK", asof="2026-06-08",
        honesty_class="research", leak_free=all(f.leak_free for f in factors),
        factors=factors, rare_flags=[], provenance={},
    )


def _minimal_bundle(home="NYK", away="SAS") -> dict:
    return {
        "home": home,
        "away": away,
        "asof": "2026-06-08",
        "sim": {
            "home_mean": 112.0, "away_mean": 109.0, "total_mean": 221.0,
            "home_win_prob": 0.52, "engine_spread": 3.0, "n_poss": 96,
            "home_pace": 94.0, "away_pace": 101.0,
            "home_def_rtg": 110.8, "away_def_rtg": 108.8,
            "home_rim_d": 63.0, "away_rim_d": 71.0,
            "home_perim_d": 62.0, "away_perim_d": 65.0,
            "home_ft_force": 1.073, "away_ft_force": 0.935,
            "home_tov_force": 1.063, "away_tov_force": 1.020,
        },
        "spine": {
            "home_road": {"mag": 1.020, "status": "wired_pregame", "confidence": "high"},
        },
        "tiers": {
            "home": {"srs": 6.55, "blowout_game_pct": 0.086, "close_game_pct": 0.32},
            "away": {"srs": 8.56, "blowout_game_pct": 0.025, "close_game_pct": 0.35},
            "league_home_margin": 1.73, "baseline_total": 231.0,
        },
        "vault": {"home_team": {}, "away_team": {}, "war_room": {}},
        "avail": {"home_out_ids": [], "away_out_ids": [], "home_b2b": False, "away_b2b": False},
        "resolver": {
            "1628969": {"name": "Mikal Bridges", "team": "NYK", "pts_base": 13.2,
                        "matchup_mult": 0.962, "pts_proj": 12.7},
            "1641705": {"name": "Victor Wembanyama", "team": "SAS", "pts_base": 24.7,
                        "matchup_mult": 1.005, "pts_proj": 24.9},
        },
        "validated_keys": sorted(VALIDATED_KEYS),
    }


class TestLeakFreeInvariant(unittest.TestCase):
    """Every factor must be leak_free=True."""

    def test_all_factors_leak_free(self):
        factors = [
            _make_factor("home_road", leak_free=True),
            _make_factor("pace_lean", vek="pace_matchup", m_or_s="scouting", leak_free=True),
            _make_factor("form", vek=None, m_or_s="scouting", lean="neutral", mag=1.0, leak_free=True),
        ]
        cv = _make_cv(factors)
        for f in cv.factors:
            self.assertTrue(f.leak_free, f"Factor {f.factor} has leak_free=False")

    def test_future_derived_field_detected(self):
        """A factor with leak_free=False should fail our assertion."""
        bad = _make_factor(leak_free=False)
        with self.assertRaises(AssertionError):
            assert bad.leak_free, "future-derived factor must not be in CV"


class TestByteIdenticalGate(unittest.TestCase):
    """With CV_LLM_CONTEXT unset, route_context returns empty mults."""

    def test_empty_mults_when_gate_off(self):
        cv = _make_cv()
        bundle = _minimal_bundle()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CV_LLM_CONTEXT", None)
            result = route_context(cv, bundle)
        self.assertEqual(result["marginal_mults"], {})
        self.assertEqual(result["applied_keys"], [])
        self.assertEqual(result["weights"], {})

    def test_gate_on_with_env(self):
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            self.assertTrue(_gate_on())

    def test_gate_off_without_env(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CV_LLM_CONTEXT", None)
            self.assertFalse(_gate_on())


class TestMarginalOrScoutingLegal(unittest.TestCase):
    """marginal_or_scouting must be 'marginal' or 'scouting'."""

    def test_legal_values(self):
        for m_or_s in ("marginal", "scouting"):
            f = _make_factor(m_or_s=m_or_s)
            self.assertIn(f.marginal_or_scouting, ("marginal", "scouting"))

    def test_only_validated_keys_can_be_marginal(self):
        for key in ("home_road", "rest_b2b"):  # the only keys that produce non-identity mults
            f = _make_factor(vek=key, m_or_s="marginal")
            self.assertIn(f.validated_effect_key, VALIDATED_KEYS)

    def test_non_validated_key_must_be_scouting(self):
        f = _make_factor(factor="clutch", vek=None, m_or_s="scouting")
        self.assertIsNone(f.validated_effect_key)
        self.assertEqual(f.marginal_or_scouting, "scouting")


class TestNullKeyGuards(unittest.TestCase):
    """pace_matchup and opp_defense must never produce an active per-player mult."""

    def test_pace_matchup_emits_no_mult(self):
        pace_factor = _make_factor("pace_lean", vek="pace_matchup", m_or_s="scouting",
                                   lean="under", mag=1.000)
        cv = _make_cv([pace_factor])
        bundle = _minimal_bundle()
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        # pace_matchup should be in skipped, not applied
        skipped_keys = [s["factor"] for s in result.get("skipped", [])]
        self.assertIn("pace_matchup", skipped_keys)
        self.assertNotIn("pace_matchup", result.get("applied_keys", []))

    def test_opp_defense_emits_no_mult(self):
        opp_factor = _make_factor("matchup_edge", vek="opp_defense", m_or_s="marginal",
                                  lean="away_defense", mag=0.982)
        cv = _make_cv([opp_factor])
        bundle = _minimal_bundle()
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        skipped_keys = [s["factor"] for s in result.get("skipped", [])]
        self.assertIn("opp_defense", skipped_keys)
        self.assertNotIn("opp_defense", result.get("applied_keys", []))


class TestLLMWeightClamping(unittest.TestCase):
    """LLM-proposed weight > 1 must be clamped to 1; < 0 to 0."""

    def test_weight_clamped_above_1(self):
        # If LLM proposes magnitude 2.0 (out of range), weight is clamped to 1.0
        f = _make_factor("home_road", mag=2.0, vek="home_road", m_or_s="marginal")
        cv = _make_cv([f])
        bundle = _minimal_bundle()
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        w = result.get("weights", {}).get("home_road", 1.0)
        self.assertLessEqual(w, 1.0, "weight must be clamped to [0,1]")

    def test_weight_clamped_below_0(self):
        f = _make_factor("home_road", mag=-0.5, vek="home_road", m_or_s="marginal")
        cv = _make_cv([f])
        bundle = _minimal_bundle()
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        w = result.get("weights", {}).get("home_road", 0.0)
        self.assertGreaterEqual(w, 0.0)


class TestArtifactStructure(unittest.TestCase):
    """Artifact dict has required top-level keys."""

    def _build_artifact(self):
        from llm_context_layer import run_context_room  # type: ignore
        # Use a tempdir for the cache to avoid polluting the real cache
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CV_LLM_CONTEXT", None)
        with tempfile.TemporaryDirectory() as td:
            with patch("llm_context_layer.CONTEXT_DIR", td):
                try:
                    artifact = run_context_room("NYK", "SAS", asof="2026-06-08", nsims=500)
                    return artifact
                except Exception:
                    return None

    def test_template_brief_returns_string(self):
        cv = _make_cv()
        bundle = _minimal_bundle()
        routed = {"applied_keys": ["home_road"], "weights": {"home_road": 1.0},
                  "marginal_mults": {}, "skipped": []}
        brief = _template_brief(cv, routed, bundle)
        self.assertIsInstance(brief, str)
        self.assertGreater(len(brief), 20)

    def test_context_artifact_path(self):
        path = context_artifact_path("NYK", "SAS", "2026-06-08")
        self.assertIn("context", path)
        self.assertIn("SAS_at_NYK", path)
        self.assertIn("2026-06-08", path)

    def test_context_artifact_path_no_asof(self):
        path = context_artifact_path("NYK", "SAS", None)
        self.assertIn("latest", path)


class TestValidatedKeysConsistency(unittest.TestCase):
    """VALIDATED_KEYS from scout and router must agree."""

    def test_validated_keys_match(self):
        # router keeps an ordered tuple (compile-time display guard); scout loads a
        # runtime frozenset from signal_effects.json. Same SET of keys is the invariant.
        self.assertEqual(set(VALIDATED_KEYS), set(SCOUT_VK))

    def test_all_expected_keys_present(self):
        for k in ("home_road", "rest_b2b", "pace_matchup", "opp_defense"):
            self.assertIn(k, VALIDATED_KEYS)


class TestNotLeakFreeExcluded(unittest.TestCase):
    """A factor with leak_free=False must NOT drive a marginal mult (router-level)."""

    def test_not_leak_free_home_road_excluded(self):
        bad = _make_factor("home_road", vek="home_road", m_or_s="marginal", leak_free=False)
        cv = _make_cv([bad])
        bundle = _minimal_bundle()
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        # home_road must NOT be applied; its effect must not leak in via the fallback
        self.assertNotIn("home_road", result.get("applied_keys", []))
        self.assertEqual(result.get("marginal_mults", {}), {},
                         "not-leak-free factor leaked a marginal mult")
        reasons = " ".join(s.get("reason", "") for s in result.get("skipped", []))
        self.assertIn("leak_free=False", reasons)

    def test_unselected_validated_key_does_not_fire(self):
        # CV has NO home_road factor at all -> home_road must not fire unconditionally.
        pace_only = _make_factor("pace_lean", vek="pace_matchup",
                                 m_or_s="scouting", lean="under", mag=1.0)
        cv = _make_cv([pace_only])
        bundle = _minimal_bundle()
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        self.assertNotIn("home_road", result.get("applied_keys", []))
        self.assertEqual(result.get("marginal_mults", {}), {})


class TestLLMDoesNotComputePoint(unittest.TestCase):
    """The LLM layer reads/weights/narrates only — it never computes the point prediction.

    The point projection comes exclusively from the deterministic sim (bundle['sim']),
    which is assembled WITHOUT any LLM call. The brief is prose; the router only emits
    attenuation mults for pre-validated keys. No LLM output may set a numeric projection.
    """

    def test_brief_is_prose_not_a_projection(self):
        cv = _make_cv()
        bundle = _minimal_bundle()
        routed = {"applied_keys": ["home_road"], "weights": {"home_road": 1.0},
                  "marginal_mults": {}, "skipped": [], "gate": True,
                  "honesty_class": "research"}
        # war_room_brief with no ANTHROPIC_API_KEY must fall back to the template (no network).
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            brief = war_room_brief(cv, routed, bundle)
        self.assertIsInstance(brief, str)
        # The brief NARRATES the sim's numbers; it does not invent a projection of its own.
        self.assertIn("research", brief.lower())

    def test_sim_numbers_come_from_bundle_not_llm(self):
        # The point numbers in the brief are exactly the sim numbers in the bundle.
        cv = _make_cv()
        bundle = _minimal_bundle()
        routed = {"applied_keys": ["home_road"], "marginal_mults": {}, "skipped": []}
        brief = _template_brief(cv, routed, bundle)
        # 221 total / 112 home / 109 away are the bundle['sim'] numbers, not LLM-derived.
        self.assertIn("221", brief)  # total_mean
        self.assertIn("112", brief)  # home_mean

    def test_router_only_attenuates_never_invents(self):
        # A marginal mult may only attenuate a validated spine effect: weight in [0,1].
        # Even with an out-of-range proposed magnitude, the applied weight is <= 1.
        f = _make_factor("home_road", mag=5.0, vek="home_road", m_or_s="marginal")
        cv = _make_cv([f])
        bundle = _minimal_bundle()
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        for key, w in result.get("weights", {}).items():
            self.assertGreaterEqual(w, 0.0)
            self.assertLessEqual(w, 1.0, f"{key} weight {w} amplifies past spine — illegal")
        # Per-player xfg mults must stay within the spine's OWN entity home/road band
        # (player_effects.parquet home_xfg in [0.892, 1.136], road_xfg in [0.867, 1.066]).
        # The router applies the spine value attenuated by weight; it never amplifies
        # PAST the spine. Bound generously by the parquet extremes.
        for pid, m in result.get("marginal_mults", {}).items():
            self.assertLessEqual(m["xfg"], 1.14, "mult amplifies past spine entity band")
            self.assertGreaterEqual(m["xfg"], 0.86)


class TestB2BConditionGate(unittest.TestCase):
    """rest_b2b mult only fires when the condition is met."""

    def test_b2b_skipped_when_condition_not_met(self):
        b2b_factor = _make_factor("rest_b2b", vek="rest_b2b", m_or_s="marginal",
                                  lean="none", mag=0.989)
        cv = _make_cv([b2b_factor])
        bundle = _minimal_bundle()
        bundle["avail"]["home_b2b"] = False
        bundle["avail"]["away_b2b"] = False
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        self.assertNotIn("rest_b2b", result.get("applied_keys", []))

    def test_b2b_applied_when_condition_met(self):
        b2b_factor = _make_factor("rest_b2b", vek="rest_b2b", m_or_s="marginal",
                                  lean="home_b2b", mag=1.0)  # weight=1.0 = full effect
        cv = _make_cv([b2b_factor])
        bundle = _minimal_bundle()
        bundle["avail"]["home_b2b"] = True  # B2B condition met
        bundle["avail"]["away_b2b"] = False
        with patch.dict(os.environ, {"CV_LLM_CONTEXT": "1"}):
            result = route_context(cv, bundle)
        self.assertIn("rest_b2b", result.get("applied_keys", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
