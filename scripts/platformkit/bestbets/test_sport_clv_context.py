"""Per-file tests for scripts.platformkit.bestbets.sport_clv_context (BB-Q7).

Run with:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/bestbets/test_sport_clv_context.py -q

Acceptance criteria:
  1. nba during offseason month -> context string contains "offseason"
  2. unknown sport              -> generic label (not empty, not "offseason")
  3. PROXY provenance (clv_is_proxy=True)  -> surfaced as "proxy", not "edge"
  4. PROXY via Provenance enum (FILLED)    -> surfaced as "proxy", not "edge"
  5. graded true-close                     -> "graded" context
  6. INSUFFICIENT_DATA status              -> "insufficient data" context
  7. nba in-season, no clv dict            -> CLV unavailable (not offseason)
  8. batch helper writes clv_context key to every card
  9. no $ / dollar / roi / profit in any context string
 10. empty / None sport -> generic label
 11. month injection works (deterministic, no real-clock dependency in tests)
 12. pure module: no I/O raised, module imports cleanly
"""
from __future__ import annotations

import importlib
import sys

import pytest

from scripts.platformkit.bestbets.sport_clv_context import (
    _GENERIC_SPORT_CTX,
    _GRADED_CTX,
    _INSUFFICIENT_DATA_CTX,
    _NO_INFO_CTX,
    _PROXY_CTX,
    attach_sport_clv_contexts,
    card_clv_context,
    sport_clv_context,
)

# Provenance import for enum-based tests
from governance.policy import Provenance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# NBA offseason month: July (month 7) is outside (10,11,12,1,2,3,4,5,6)
_NBA_OFFSEASON_MONTH = 7
# NBA in-season month: January
_NBA_INSEASON_MONTH = 1
# MLB in-season month: May
_MLB_INSEASON_MONTH = 5

_GRADED_CLV = {
    "clv_pct": 0.03,
    "beat_close": True,
    "clv_status": "graded",
    "clv_is_proxy": False,
}
_PROXY_CLV = {
    "clv_pct": None,
    "beat_close": None,
    "clv_status": "proxy",
    "clv_is_proxy": True,
}
_INSUFF_CLV = {
    "clv_pct": None,
    "beat_close": None,
    "clv_status": "INSUFFICIENT_DATA",
    "clv_is_proxy": True,
}


# ---------------------------------------------------------------------------
# 1. NBA offseason -> label contains "offseason"
# ---------------------------------------------------------------------------

class TestNbaOffseason:
    def test_nba_offseason_month_contains_offseason(self):
        ctx = sport_clv_context("nba", month=_NBA_OFFSEASON_MONTH)
        assert "offseason" in ctx.lower(), (
            "Expected 'offseason' in context for nba offseason month, got: %r" % ctx
        )

    def test_nba_offseason_contains_sport_slug(self):
        ctx = sport_clv_context("nba", month=_NBA_OFFSEASON_MONTH)
        assert "nba" in ctx.lower(), "Expected 'nba' in offseason context string"

    def test_nba_offseason_not_empty(self):
        ctx = sport_clv_context("nba", month=_NBA_OFFSEASON_MONTH)
        assert ctx and ctx.strip(), "Context string must not be empty"

    def test_nba_offseason_with_clv_still_offseason(self):
        # Even if a CLV dict is passed, offseason takes precedence
        ctx = sport_clv_context("nba", _GRADED_CLV, month=_NBA_OFFSEASON_MONTH)
        assert "offseason" in ctx.lower(), (
            "Offseason check must precede CLV inspection"
        )


# ---------------------------------------------------------------------------
# 2. Unknown / None sport -> generic label
# ---------------------------------------------------------------------------

class TestUnknownSport:
    def test_unknown_sport_returns_generic(self):
        ctx = sport_clv_context("curling", month=_NBA_INSEASON_MONTH)
        assert ctx == _GENERIC_SPORT_CTX, (
            "Unknown sport should return generic label, got: %r" % ctx
        )

    def test_none_sport_returns_generic(self):
        ctx = sport_clv_context(None, month=_NBA_INSEASON_MONTH)
        assert ctx == _GENERIC_SPORT_CTX

    def test_empty_sport_returns_generic(self):
        ctx = sport_clv_context("", month=_NBA_INSEASON_MONTH)
        assert ctx == _GENERIC_SPORT_CTX

    def test_generic_label_not_empty(self):
        ctx = sport_clv_context("xyz_unknown_sport", month=5)
        assert ctx and ctx.strip()

    def test_generic_label_not_offseason(self):
        # Generic label should NOT say offseason (it is simply unrecognised)
        ctx = sport_clv_context("curling", month=_NBA_OFFSEASON_MONTH)
        assert "offseason" not in ctx.lower(), (
            "Unknown sport must return generic label even in offseason month"
        )


# ---------------------------------------------------------------------------
# 3. PROXY provenance via clv_is_proxy flag
# ---------------------------------------------------------------------------

class TestProxyClvIsProxy:
    def test_proxy_flag_returns_proxy_context(self):
        ctx = sport_clv_context("nba", _PROXY_CLV, month=_NBA_INSEASON_MONTH)
        assert "proxy" in ctx.lower(), (
            "clv_is_proxy=True must surface as proxy context, got: %r" % ctx
        )

    def test_proxy_context_does_not_say_edge(self):
        ctx = sport_clv_context("nba", _PROXY_CLV, month=_NBA_INSEASON_MONTH)
        assert "edge" not in ctx.lower(), (
            "Proxy context must NEVER say 'edge', got: %r" % ctx
        )

    def test_proxy_context_not_empty(self):
        ctx = sport_clv_context("mlb", _PROXY_CLV, month=_MLB_INSEASON_MONTH)
        assert ctx and ctx.strip()


# ---------------------------------------------------------------------------
# 4. PROXY via Provenance enum (FILLED / UNAVAILABLE / UNKNOWN)
# ---------------------------------------------------------------------------

class TestProxyProvenance:
    @pytest.mark.parametrize("prov", [
        Provenance.FILLED,
        Provenance.UNAVAILABLE,
        Provenance.UNKNOWN,
    ])
    def test_flagged_provenance_surfaces_as_proxy(self, prov):
        clv_with_prov = {
            "clv_pct": 0.05,
            "beat_close": True,
            "clv_status": "graded",
            "clv_is_proxy": False,
            "provenance": prov,
        }
        ctx = sport_clv_context("nba", clv_with_prov, month=_NBA_INSEASON_MONTH)
        assert "proxy" in ctx.lower(), (
            "Provenance %s must surface as proxy context, got: %r" % (prov, ctx)
        )

    @pytest.mark.parametrize("prov", [
        Provenance.FILLED,
        Provenance.UNAVAILABLE,
        Provenance.UNKNOWN,
    ])
    def test_flagged_provenance_never_says_edge(self, prov):
        clv_with_prov = {
            "clv_pct": 0.05,
            "beat_close": True,
            "clv_status": "graded",
            "clv_is_proxy": False,
            "provenance": prov,
        }
        ctx = sport_clv_context("nba", clv_with_prov, month=_NBA_INSEASON_MONTH)
        assert "edge" not in ctx.lower(), (
            "Proxy context must never say 'edge', got: %r" % ctx
        )

    @pytest.mark.parametrize("prov_str", [
        "FILLED", "UNAVAILABLE", "UNKNOWN",
    ])
    def test_provenance_string_form_surfaces_as_proxy(self, prov_str):
        """Provenance passed as a raw string should also be treated correctly."""
        clv_with_prov = {
            "clv_pct": 0.03,
            "clv_status": "graded",
            "clv_is_proxy": False,
            "provenance": prov_str,
        }
        ctx = sport_clv_context("nba", clv_with_prov, month=_NBA_INSEASON_MONTH)
        assert "proxy" in ctx.lower(), (
            "String provenance %r must map to proxy context, got: %r" % (prov_str, ctx)
        )

    def test_real_model_provenance_does_not_surface_as_proxy(self):
        clv_real = {
            "clv_pct": 0.04,
            "beat_close": True,
            "clv_status": "graded",
            "clv_is_proxy": False,
            "provenance": Provenance.REAL_MODEL,
        }
        ctx = sport_clv_context("nba", clv_real, month=_NBA_INSEASON_MONTH)
        assert "proxy" not in ctx.lower(), (
            "REAL_MODEL provenance should NOT surface as proxy, got: %r" % ctx
        )


# ---------------------------------------------------------------------------
# 5. Graded true close
# ---------------------------------------------------------------------------

class TestGradedClose:
    def test_graded_clv_returns_graded_context(self):
        ctx = sport_clv_context("nba", _GRADED_CLV, month=_NBA_INSEASON_MONTH)
        assert "graded" in ctx.lower(), (
            "Graded CLV must return graded context, got: %r" % ctx
        )

    def test_graded_context_not_empty(self):
        ctx = sport_clv_context("mlb", _GRADED_CLV, month=_MLB_INSEASON_MONTH)
        assert ctx and ctx.strip()


# ---------------------------------------------------------------------------
# 6. INSUFFICIENT_DATA status
# ---------------------------------------------------------------------------

class TestInsufficientData:
    def test_insufficient_data_status(self):
        ctx = sport_clv_context("nba", _INSUFF_CLV, month=_NBA_INSEASON_MONTH)
        # INSUFFICIENT_DATA with clv_is_proxy=True will hit proxy path first
        # Both are honest -- either "proxy" or "insufficient" is acceptable.
        assert "proxy" in ctx.lower() or "insufficient" in ctx.lower(), (
            "INSUFFICIENT_DATA/proxy CLV must return proxy or insufficient context, got: %r" % ctx
        )

    def test_insufficient_data_status_only(self):
        """INSUFFICIENT_DATA without is_proxy flag -> 'insufficient data' context."""
        clv = {
            "clv_pct": None,
            "beat_close": None,
            "clv_status": "INSUFFICIENT_DATA",
            "clv_is_proxy": False,  # no proxy flag; only status drives it
        }
        ctx = sport_clv_context("nba", clv, month=_NBA_INSEASON_MONTH)
        assert "insufficient" in ctx.lower(), (
            "INSUFFICIENT_DATA without proxy flag -> insufficient context, got: %r" % ctx
        )


# ---------------------------------------------------------------------------
# 7. NBA in-season, no CLV dict -> CLV unavailable (not offseason)
# ---------------------------------------------------------------------------

class TestNbaInSeasonNoClv:
    def test_inseason_no_clv_dict(self):
        ctx = sport_clv_context("nba", None, month=_NBA_INSEASON_MONTH)
        assert "offseason" not in ctx.lower(), (
            "In-season nba with no CLV should NOT say offseason, got: %r" % ctx
        )
        assert ctx and ctx.strip()

    def test_inseason_empty_clv_dict(self):
        ctx = sport_clv_context("nba", {}, month=_NBA_INSEASON_MONTH)
        # Empty dict: no useful CLV info
        assert ctx and ctx.strip()


# ---------------------------------------------------------------------------
# 8. Batch helper writes clv_context to every card
# ---------------------------------------------------------------------------

class TestBatchHelper:
    def test_attach_adds_clv_context_key(self):
        cards = [
            {"sport": "nba", "clv": _GRADED_CLV},
            {"sport": "mlb", "clv": _PROXY_CLV},
            {"sport": "nba"},  # no clv key
        ]
        result = attach_sport_clv_contexts(cards, month=_NBA_INSEASON_MONTH)
        assert result is cards, "Should return the same list"
        for card in cards:
            assert "clv_context" in card, "Every card must have clv_context key"
            assert isinstance(card["clv_context"], str)
            assert card["clv_context"].strip()

    def test_batch_offseason_nba(self):
        cards = [
            {"sport": "nba", "clv": _GRADED_CLV},
            {"sport": "nba", "clv": _PROXY_CLV},
        ]
        attach_sport_clv_contexts(cards, month=_NBA_OFFSEASON_MONTH)
        for card in cards:
            assert "offseason" in card["clv_context"].lower(), (
                "Offseason NBA cards must carry offseason context, got: %r" % card["clv_context"]
            )

    def test_batch_non_dict_items_skipped(self):
        cards = [None, "not-a-card", {"sport": "nba"}, 42]
        # Should not raise
        result = attach_sport_clv_contexts(cards, month=_NBA_INSEASON_MONTH)  # type: ignore[arg-type]
        # Only the dict gets annotated
        assert result[2].get("clv_context")  # type: ignore[union-attr]

    def test_batch_custom_output_key(self):
        cards = [{"sport": "nba", "clv": _GRADED_CLV}]
        attach_sport_clv_contexts(cards, output_key="my_ctx", month=_NBA_INSEASON_MONTH)
        assert "my_ctx" in cards[0]


# ---------------------------------------------------------------------------
# 9. No $ / dollar / roi / profit in any context string
# ---------------------------------------------------------------------------

class TestNoBannedFields:
    _ALL_CONTEXTS = [
        _GENERIC_SPORT_CTX,
        _PROXY_CTX,
        _INSUFFICIENT_DATA_CTX,
        _GRADED_CTX,
        _NO_INFO_CTX,
        "nba offseason -- CLV unavailable",  # representative offseason string
    ]

    @pytest.mark.parametrize("ctx", _ALL_CONTEXTS)
    def test_no_dollar_sign(self, ctx):
        assert "$" not in ctx, "Context string must not contain '$': %r" % ctx

    @pytest.mark.parametrize("ctx", _ALL_CONTEXTS)
    def test_no_roi(self, ctx):
        assert "roi" not in ctx.lower(), "Context string must not mention ROI: %r" % ctx

    @pytest.mark.parametrize("ctx", _ALL_CONTEXTS)
    def test_no_profit(self, ctx):
        assert "profit" not in ctx.lower(), "Context must not mention profit: %r" % ctx


# ---------------------------------------------------------------------------
# 10. Case insensitivity of sport slug
# ---------------------------------------------------------------------------

class TestCaseInsensitivity:
    def test_uppercase_nba(self):
        ctx_lower = sport_clv_context("nba", month=_NBA_OFFSEASON_MONTH)
        ctx_upper = sport_clv_context("NBA", month=_NBA_OFFSEASON_MONTH)
        assert ctx_lower == ctx_upper, (
            "Sport slug must be case-insensitive: %r vs %r" % (ctx_lower, ctx_upper)
        )

    def test_mixed_case_mlb(self):
        ctx = sport_clv_context("MLB", _GRADED_CLV, month=_MLB_INSEASON_MONTH)
        assert "graded" in ctx.lower()


# ---------------------------------------------------------------------------
# 11. Month injection (deterministic, no real-clock dependency)
# ---------------------------------------------------------------------------

class TestMonthInjection:
    def test_month_7_is_nba_offseason(self):
        ctx = sport_clv_context("nba", month=7)
        assert "offseason" in ctx.lower()

    def test_month_1_is_nba_inseason(self):
        ctx = sport_clv_context("nba", None, month=1)
        assert "offseason" not in ctx.lower()

    def test_month_8_is_mlb_inseason(self):
        ctx = sport_clv_context("mlb", _GRADED_CLV, month=8)
        assert "graded" in ctx.lower()

    def test_month_12_is_mlb_offseason(self):
        ctx = sport_clv_context("mlb", month=12)
        assert "offseason" in ctx.lower()


# ---------------------------------------------------------------------------
# 12. Pure module: imports cleanly, no I/O side effects
# ---------------------------------------------------------------------------

class TestModulePurity:
    def test_module_importable(self):
        mod = importlib.import_module(
            "scripts.platformkit.bestbets.sport_clv_context"
        )
        assert hasattr(mod, "sport_clv_context")
        assert hasattr(mod, "attach_sport_clv_contexts")

    def test_no_side_effects_on_import(self):
        # Re-import should not fail or produce output
        if "scripts.platformkit.bestbets.sport_clv_context" in sys.modules:
            mod = sys.modules["scripts.platformkit.bestbets.sport_clv_context"]
            importlib.reload(mod)

    def test_result_is_str(self):
        ctx = sport_clv_context("nba", month=_NBA_OFFSEASON_MONTH)
        assert isinstance(ctx, str)

    def test_result_is_ascii(self):
        for sport in ("nba", "mlb", "soccer", "tennis", "unknown"):
            ctx = sport_clv_context(sport, month=7)
            ctx.encode("ascii")  # raises if non-ASCII

    def test_never_raises_on_garbage_input(self):
        """sport_clv_context must not raise on any input."""
        garbage_inputs = [
            (None, None),
            (42, {}),
            ("nba", "not_a_dict"),
            ("nba", {"clv_pct": float("inf")}),
            ("nba", {"clv_is_proxy": "yes", "clv_status": None}),
        ]
        for sport, clv in garbage_inputs:
            try:
                ctx = sport_clv_context(sport, clv, month=1)  # type: ignore[arg-type]
                assert isinstance(ctx, str) and ctx.strip()
            except Exception as exc:
                pytest.fail(
                    "sport_clv_context raised on input (%r, %r): %s" % (sport, clv, exc)
                )


# ---------------------------------------------------------------------------
# 13. card_clv_context helper
# ---------------------------------------------------------------------------

class TestCardClvContext:
    def test_card_dict_works(self):
        card = {"sport": "nba", "clv": _GRADED_CLV}
        ctx = card_clv_context(card, month=_NBA_INSEASON_MONTH)
        assert "graded" in ctx.lower()

    def test_card_with_no_clv(self):
        card = {"sport": "nba"}
        ctx = card_clv_context(card, month=_NBA_INSEASON_MONTH)
        assert isinstance(ctx, str) and ctx.strip()

    def test_non_dict_card_returns_unavailable(self):
        ctx = card_clv_context("bad_input")  # type: ignore[arg-type]
        assert ctx == _NO_INFO_CTX
