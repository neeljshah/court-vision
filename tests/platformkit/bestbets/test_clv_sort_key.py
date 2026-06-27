"""test_clv_sort_key.py -- per-file acceptance tests for BB-Q6 clv_sort_key.

Acceptance criteria (from BACKLOG BB-Q6):
  1. True-close CLV outranks proxy CLV at equal divergence (clv_sort_key is higher).
  2. Proxy CLV -> 0.0 (never inflates rank above a no-CLV card).
  3. Null / INSUFFICIENT_DATA -> 0.0.
  4. Divergence remains primary key: a higher-divergence card wins even if it has
     lower (or zero) clv_sort_key than a lower-divergence card.
  5. No dollar / roi / pnl / profit key in any output.
  6. Never raises on any input shape (None, dict, dataclass-like, garbage).
  7. attach_clv_sort_keys batch helper works correctly (writes output_key, no I/O).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_clv_sort_key.py -q
"""
from __future__ import annotations

import math
import sys
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from scripts.platformkit.bestbets.clv_sort_key import (
    clv_sort_key,
    attach_clv_sort_keys,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEYS = {"dollar", "roi", "pnl", "profit", "return", "revenue", "usd"}


def _has_banned_key(obj: Any) -> Optional[str]:
    """Recursively scan for a banned key. Returns the first hit or None."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _BANNED_KEYS:
                return str(k)
            hit = _has_banned_key(v)
            if hit:
                return hit
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            hit = _has_banned_key(item)
            if hit:
                return hit
    return None


@dataclass(frozen=True)
class _FakeClvAudit:
    """Minimal duck-type of quant.clv_core.ClvAudit for tests (no real imports)."""
    clv_pct: Optional[float]
    clv_prob: Optional[float]
    sign: int
    is_true_close: bool
    proxy: bool


# ---------------------------------------------------------------------------
# 1. True-close CLV outranks proxy CLV at equal divergence
# ---------------------------------------------------------------------------

def test_true_close_outranks_proxy_at_equal_divergence():
    """KEY ACCEPTANCE: true-close clv_sort_key > proxy clv_sort_key at same divergence.

    Same clv_pct value: a true-close reading contributes it to rank; a proxy reads 0.0.
    This means at equal divergence, the true-close card wins on the secondary key.
    """
    true_close_clv = {"clv_pct": 0.05, "is_true_close": True, "clv_status": "graded"}
    proxy_clv = {"clv_pct": 0.05, "is_true_close": False, "clv_status": "graded"}

    key_true = clv_sort_key(true_close_clv)
    key_proxy = clv_sort_key(proxy_clv)

    assert key_true == 0.05, f"True-close clv_sort_key should be 0.05; got {key_true}"
    assert key_proxy == 0.0, f"Proxy clv_sort_key should be 0.0; got {key_proxy}"
    assert key_true > key_proxy, (
        f"True-close ({key_true}) must outrank proxy ({key_proxy}) at equal divergence"
    )


def test_true_close_clv_is_proxy_flag():
    """clv_is_proxy=False means true-close (clv_index shape)."""
    true_close = {"clv_pct": 0.03, "clv_is_proxy": False, "clv_status": "graded"}
    proxy = {"clv_pct": 0.03, "clv_is_proxy": True, "clv_status": "graded"}

    assert clv_sort_key(true_close) == 0.03
    assert clv_sort_key(proxy) == 0.0


# ---------------------------------------------------------------------------
# 2. Proxy CLV -> 0.0 (never inflates rank)
# ---------------------------------------------------------------------------

def test_proxy_returns_zero():
    """Proxy CLV must always return exactly 0.0 regardless of clv_pct value."""
    cases = [
        {"clv_pct": 0.10, "is_true_close": False, "clv_status": "graded"},
        {"clv_pct": -0.05, "is_true_close": False, "clv_status": "graded"},
        {"clv_pct": 99.9, "clv_is_proxy": True, "clv_status": "graded"},
        {"clv_pct": 0.0, "is_true_close": False, "clv_status": "graded"},
    ]
    for case in cases:
        result = clv_sort_key(case)
        assert result == 0.0, f"Expected 0.0 for proxy {case}, got {result}"


def test_proxy_does_not_outrank_no_clv():
    """Proxy (0.0) must not outrank a card with no CLV at all (also 0.0)."""
    proxy_key = clv_sort_key({"clv_pct": 0.20, "is_true_close": False, "clv_status": "graded"})
    null_key = clv_sort_key(None)

    assert proxy_key == 0.0
    assert null_key == 0.0
    assert proxy_key == null_key, "Proxy and null must tie (both 0.0); neither inflates"


# ---------------------------------------------------------------------------
# 3. Null / INSUFFICIENT_DATA -> 0.0
# ---------------------------------------------------------------------------

def test_none_input_returns_zero():
    """None input must return 0.0."""
    assert clv_sort_key(None) == 0.0


def test_insufficient_data_status_returns_zero():
    """INSUFFICIENT_DATA clv_status -> 0.0 even if is_true_close=True (defensive)."""
    clv = {"clv_pct": 0.05, "is_true_close": True, "clv_status": "INSUFFICIENT_DATA"}
    assert clv_sort_key(clv) == 0.0, "INSUFFICIENT_DATA must be treated as null"


def test_insufficient_data_with_null_clv_pct():
    """INSUFFICIENT_DATA with clv_pct=None -> 0.0."""
    clv = {"clv_pct": None, "clv_is_proxy": True, "clv_status": "INSUFFICIENT_DATA"}
    assert clv_sort_key(clv) == 0.0


def test_true_close_with_none_clv_pct_returns_zero():
    """True-close but clv_pct=None means no usable value -> 0.0."""
    clv = {"clv_pct": None, "is_true_close": True, "clv_status": "graded"}
    result = clv_sort_key(clv)
    assert result == 0.0, f"True-close with None clv_pct must return 0.0; got {result}"


# ---------------------------------------------------------------------------
# 4. Divergence remains primary key
# ---------------------------------------------------------------------------

def test_divergence_primary_sorting():
    """Higher divergence wins over higher clv_sort_key at lower divergence.

    This validates the sort ORDER expected by the caller when using both keys.
    A card with divergence=10.0 but clv_sort_key=0.0 (proxy) should rank BEFORE
    a card with divergence=1.0 but clv_sort_key=0.05 (true-close) because
    divergence is the primary key.

    We simulate by building the combined sort tuple callers should use:
      (-divergence_score, -clv_sort_key)  ascending -> best card first
    """
    card_high_div_proxy = {
        "id": "high_div_proxy",
        "divergence_score": 10.0,
        "clv": {"clv_pct": 0.05, "is_true_close": False, "clv_status": "graded"},
    }
    card_low_div_true = {
        "id": "low_div_true",
        "divergence_score": 1.0,
        "clv": {"clv_pct": 0.05, "is_true_close": True, "clv_status": "graded"},
    }

    def _sort_key(card: dict) -> tuple:
        div = card.get("divergence_score", 0.0)
        clv_k = clv_sort_key(card.get("clv"))
        return (-div, -clv_k)

    ranked = sorted([card_low_div_true, card_high_div_proxy], key=_sort_key)
    assert ranked[0]["id"] == "high_div_proxy", (
        "Higher divergence must win even with proxy CLV; "
        f"got {[c['id'] for c in ranked]}"
    )


def test_clv_breaks_equal_divergence_tie():
    """At equal divergence, true-close CLV breaks the tie over proxy."""
    card_true = {
        "id": "true_close",
        "divergence_score": 5.0,
        "clv": {"clv_pct": 0.05, "is_true_close": True, "clv_status": "graded"},
    }
    card_proxy = {
        "id": "proxy",
        "divergence_score": 5.0,
        "clv": {"clv_pct": 0.05, "is_true_close": False, "clv_status": "graded"},
    }

    def _sort_key(card: dict) -> tuple:
        div = card.get("divergence_score", 0.0)
        clv_k = clv_sort_key(card.get("clv"))
        return (-div, -clv_k)

    ranked = sorted([card_proxy, card_true], key=_sort_key)
    assert ranked[0]["id"] == "true_close", (
        "True-close must win tiebreak over proxy at equal divergence; "
        f"got {[c['id'] for c in ranked]}"
    )


# ---------------------------------------------------------------------------
# 5. No dollar / roi / pnl / profit key
# ---------------------------------------------------------------------------

def test_no_banned_keys_in_output():
    """attach_clv_sort_keys must not write any banned key to cards."""
    cards = [
        {"id": "a", "clv": {"clv_pct": 0.05, "is_true_close": True, "clv_status": "graded"}},
        {"id": "b", "clv": {"clv_pct": 0.05, "is_true_close": False, "clv_status": "graded"}},
        {"id": "c"},
    ]
    attach_clv_sort_keys(cards)
    for card in cards:
        hit = _has_banned_key(card)
        assert hit is None, f"Banned key '{hit}' found in card {card}"


def test_clv_sort_key_no_banned_output():
    """clv_sort_key returns a plain float; no dict/pnl field possible."""
    result = clv_sort_key({"clv_pct": 0.10, "is_true_close": True, "clv_status": "graded"})
    # result is a float; this test mainly documents intent and passes trivially
    assert isinstance(result, float)
    hit = _has_banned_key({"clv_sort_key": result})
    assert hit is None


# ---------------------------------------------------------------------------
# 6. Never raises on any input
# ---------------------------------------------------------------------------

def test_never_raises_on_none():
    assert clv_sort_key(None) == 0.0


def test_never_raises_on_empty_dict():
    assert clv_sort_key({}) == 0.0


def test_never_raises_on_garbage_dict():
    garbage = {"clv_pct": "not_a_number", "is_true_close": "yes", "clv_status": 42}
    result = clv_sort_key(garbage)
    assert isinstance(result, float)
    assert math.isfinite(result)


def test_never_raises_on_nonfinite_clv_pct():
    """Non-finite clv_pct values (inf / nan) must return 0.0, not raise."""
    for bad_val in [float("inf"), float("-inf"), float("nan")]:
        clv = {"clv_pct": bad_val, "is_true_close": True, "clv_status": "graded"}
        result = clv_sort_key(clv)
        assert result == 0.0, f"Non-finite clv_pct={bad_val} must return 0.0; got {result}"


def test_never_raises_on_integer_input():
    """Passing an int instead of a dict/None should silently return 0.0."""
    assert clv_sort_key(42) == 0.0
    assert clv_sort_key(0) == 0.0


def test_never_raises_on_string_input():
    assert clv_sort_key("some_string") == 0.0


# ---------------------------------------------------------------------------
# 6a. ClvAudit duck-type path
# ---------------------------------------------------------------------------

def test_duck_type_clv_audit_true_close():
    """ClvAudit-like object with is_true_close=True uses clv_pct."""
    audit = _FakeClvAudit(clv_pct=0.07, clv_prob=0.02, sign=1,
                          is_true_close=True, proxy=False)
    result = clv_sort_key(audit)
    assert result == 0.07, f"Expected 0.07; got {result}"


def test_duck_type_clv_audit_proxy():
    """ClvAudit-like object with is_true_close=False -> 0.0."""
    audit = _FakeClvAudit(clv_pct=0.07, clv_prob=0.02, sign=1,
                          is_true_close=False, proxy=True)
    result = clv_sort_key(audit)
    assert result == 0.0, f"Expected 0.0 for proxy audit; got {result}"


def test_duck_type_clv_audit_none_pct():
    """ClvAudit-like with is_true_close=True but clv_pct=None -> 0.0."""
    audit = _FakeClvAudit(clv_pct=None, clv_prob=None, sign=0,
                          is_true_close=True, proxy=False)
    result = clv_sort_key(audit)
    assert result == 0.0


# ---------------------------------------------------------------------------
# 7. attach_clv_sort_keys batch helper
# ---------------------------------------------------------------------------

def test_attach_clv_sort_keys_empty():
    """Empty list returns [] without raising."""
    result = attach_clv_sort_keys([])
    assert result == []


def test_attach_clv_sort_keys_writes_output_key():
    """Batch helper writes 'clv_sort_key' to each card."""
    cards = [
        {"id": "tc", "clv": {"clv_pct": 0.04, "is_true_close": True, "clv_status": "graded"}},
        {"id": "pr", "clv": {"clv_pct": 0.04, "is_true_close": False, "clv_status": "graded"}},
        {"id": "no_clv"},
    ]
    result = attach_clv_sort_keys(cards)

    assert result is cards, "Should return the same list (in-place mutation)"
    assert cards[0]["clv_sort_key"] == 0.04, f"True-close: {cards[0]['clv_sort_key']}"
    assert cards[1]["clv_sort_key"] == 0.0, f"Proxy: {cards[1]['clv_sort_key']}"
    assert cards[2]["clv_sort_key"] == 0.0, f"No CLV: {cards[2]['clv_sort_key']}"


def test_attach_clv_sort_keys_custom_keys():
    """Custom clv_key and output_key are respected."""
    cards = [
        {"id": "x", "my_clv": {"clv_pct": 0.09, "is_true_close": True, "clv_status": "graded"}},
    ]
    attach_clv_sort_keys(cards, clv_key="my_clv", output_key="my_sort_key")
    assert cards[0]["my_sort_key"] == 0.09, f"Custom key: {cards[0].get('my_sort_key')}"
    assert "clv_sort_key" not in cards[0], "Default key must not appear when custom key used"


def test_attach_clv_sort_keys_non_dict_items_skipped():
    """Non-dict items in the list are skipped without raising."""
    cards = [None, "string", 42, {"id": "ok", "clv": None}]
    result = attach_clv_sort_keys(cards)
    # Only the dict item gets the output key
    assert result[-1]["clv_sort_key"] == 0.0


def test_attach_clv_sort_keys_no_banned_keys():
    """Batch helper must not write any banned key."""
    cards = [
        {"id": "a", "clv": {"clv_pct": 0.05, "is_true_close": True, "clv_status": "graded"}},
    ]
    attach_clv_sort_keys(cards)
    assert _has_banned_key(cards) is None


# ---------------------------------------------------------------------------
# End-to-end: full ranking scenario
# ---------------------------------------------------------------------------

def test_full_ranking_scenario():
    """Verify the complete intended usage: divergence primary, CLV secondary.

    Three cards at the same tier and divergence:
      card_tc:    true-close clv_pct=0.05  -> clv_sort_key=0.05
      card_proxy: proxy clv_pct=0.05       -> clv_sort_key=0.0
      card_null:  no CLV at all            -> clv_sort_key=0.0

    Expected ranking (all have equal divergence):
      1. card_tc (highest clv_sort_key=0.05)
      2. card_proxy / card_null (both 0.0, tie on CLV -- broken by secondary criteria)
    """
    cards = [
        {
            "id": "null",
            "divergence_score": 2.0,
            "clv": None,
        },
        {
            "id": "proxy",
            "divergence_score": 2.0,
            "clv": {"clv_pct": 0.05, "is_true_close": False, "clv_status": "graded"},
        },
        {
            "id": "tc",
            "divergence_score": 2.0,
            "clv": {"clv_pct": 0.05, "is_true_close": True, "clv_status": "graded"},
        },
    ]

    attach_clv_sort_keys(cards)

    # Check individual keys
    assert cards[0]["clv_sort_key"] == 0.0   # null
    assert cards[1]["clv_sort_key"] == 0.0   # proxy
    assert cards[2]["clv_sort_key"] == 0.05  # true-close

    # Sort: primary=-divergence, secondary=-clv_sort_key (ascending)
    def _key(c: dict) -> tuple:
        return (-c["divergence_score"], -c["clv_sort_key"])

    ranked = sorted(cards, key=_key)
    ids = [c["id"] for c in ranked]

    assert ids[0] == "tc", f"True-close must rank first; got {ids}"
    # proxy and null both 0.0 -- both behind tc; their relative order is stable but not tested
    assert "proxy" in ids[1:] and "null" in ids[1:], f"proxy/null must be in tail; got {ids}"
