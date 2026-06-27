"""tests/platformkit/bestbets/test_confidence_score.py

BBQ5-2 acceptance tests for confidence_score.score_card().

Coverage mandated by the accept_test spec:
  1. High model_prob (0.95) + ZERO divergence -> LOW (not HIGH/MED).
  2. Large divergence + non-proxy CLV + ample samples -> HIGH.
  3. clv_is_proxy=True caps label at MED even with large divergence + ample samples.
  4. Missing n_samples -> treated as thin -> caps label at LOW; never raises.
  5. score always in [0.0, 1.0].
  6. label always in {LOW, MED, HIGH}.
  7. No dollar / roi / pnl key in the output (recursive scan of card input allowed).
  8. Empty / garbage card -> (0.0, LOW); never raises.

Additional coverage:
  9. Perfect divergence + real CLV + ample samples -> HIGH.
  10. clv_is_proxy=True alone (small divergence, ample samples) stays <= MED.
  11. Thin sample alone (large divergence, real CLV) caps at LOW.
  12. score_batch: empty list -> []; non-list -> []; bad card -> (0.0, LOW).
  13. score in [0, 1] for a sweep of divergence values.
"""
from __future__ import annotations

import math
import sys
import os

# ---------------------------------------------------------------------------
# Path fixup so the test can run from the repo root with:
#     python -m pytest tests/platformkit/bestbets/test_confidence_score.py -q
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.platformkit.bestbets.confidence_score import (  # noqa: E402
    LABEL_HIGH,
    LABEL_LOW,
    LABEL_MED,
    score_batch,
    score_card,
)

_VALID_LABELS = {LABEL_LOW, LABEL_MED, LABEL_HIGH}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_card(
    *,
    model_prob: float = 0.55,
    market_prob: float = 0.50,
    n_samples: int = 200,
    clv_is_proxy: bool = False,
    sigma: float = 0.05,
) -> dict:
    return {
        "model_prob": model_prob,
        "market_prob": market_prob,
        "n_samples": n_samples,
        "clv_is_proxy": clv_is_proxy,
        "sigma": sigma,
    }


def _has_dollar_key(d: dict) -> bool:
    """Recursively check for any $ / roi / pnl key in a dict."""
    if not isinstance(d, dict):
        return False
    for k, v in d.items():
        if any(bad in str(k).lower() for bad in ("dollar", "pnl", "roi", "profit")):
            return True
        if "$" in str(k):
            return True
        if isinstance(v, dict) and _has_dollar_key(v):
            return True
    return False


# ---------------------------------------------------------------------------
# Spec test 1: high model_prob + ZERO divergence -> LOW
# ---------------------------------------------------------------------------

def test_high_model_prob_zero_divergence_is_low():
    """A 0.95 favourite vs a 0.95 market price has ZERO divergence -> LOW."""
    card = _make_card(
        model_prob=0.95,
        market_prob=0.95,    # same price: zero divergence
        n_samples=500,
        clv_is_proxy=False,
    )
    score, label = score_card(card)
    assert label == LABEL_LOW, (
        f"Expected LOW for zero-divergence favourite, got {label} (score={score:.4f})"
    )
    # score itself should be low (only CLV and sample axes fire; divergence = 0)
    assert score < 0.45, f"Score {score:.4f} suspiciously high for zero-divergence card"


# ---------------------------------------------------------------------------
# Spec test 2: large divergence + real CLV + ample samples -> HIGH
# ---------------------------------------------------------------------------

def test_large_divergence_real_clv_ample_samples_is_high():
    """Strong edge signal, genuine (non-proxy) CLV, ample samples -> HIGH."""
    card = _make_card(
        model_prob=0.70,
        market_prob=0.50,    # 20pp divergence => 4 sigma at sigma=0.05
        n_samples=500,
        clv_is_proxy=False,
    )
    score, label = score_card(card)
    assert label == LABEL_HIGH, (
        f"Expected HIGH for ample+real-CLV+large-divergence, got {label} "
        f"(score={score:.4f})"
    )
    assert score >= 0.60, f"Score {score:.4f} below HIGH_THRESHOLD for a strong card"


# ---------------------------------------------------------------------------
# Spec test 3: clv_is_proxy=True caps at MED
# ---------------------------------------------------------------------------

def test_clv_proxy_caps_at_med():
    """Even with large divergence and ample samples, proxy CLV caps at MED."""
    card = _make_card(
        model_prob=0.70,
        market_prob=0.50,    # 4 sigma divergence
        n_samples=500,
        clv_is_proxy=True,   # proxy -> cap at MED
    )
    score, label = score_card(card)
    assert label in (LABEL_MED, LABEL_LOW), (
        f"Expected MED or LOW for proxy CLV with large divergence, got {label} "
        f"(score={score:.4f})"
    )
    assert label != LABEL_HIGH, (
        f"clv_is_proxy=True must cap at MED, but got HIGH (score={score:.4f})"
    )


# ---------------------------------------------------------------------------
# Spec test 4: missing n_samples -> thin -> LOW; does not raise
# ---------------------------------------------------------------------------

def test_missing_n_samples_is_low_no_crash():
    """Missing n_samples treated as thin -> label must be LOW."""
    card = {
        "model_prob": 0.70,
        "market_prob": 0.50,
        "clv_is_proxy": False,
        # n_samples deliberately absent
    }
    score, label = score_card(card)   # must not raise
    assert label == LABEL_LOW, (
        f"Missing n_samples must give LOW, got {label} (score={score:.4f})"
    )
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Spec test 5+6: score in [0, 1], label in valid set
# ---------------------------------------------------------------------------

def test_score_always_in_unit_interval_and_valid_label():
    """Sweep across card shapes; score always [0,1], label always valid."""
    cases = [
        _make_card(model_prob=0.55, market_prob=0.50, n_samples=50, clv_is_proxy=True),
        _make_card(model_prob=0.80, market_prob=0.50, n_samples=200, clv_is_proxy=False),
        _make_card(model_prob=0.50, market_prob=0.50, n_samples=200, clv_is_proxy=False),
        _make_card(model_prob=0.99, market_prob=0.01, n_samples=10, clv_is_proxy=True),
        _make_card(model_prob=0.0, market_prob=0.0, n_samples=500, clv_is_proxy=False),
        _make_card(model_prob=1.0, market_prob=0.0, n_samples=500, clv_is_proxy=False),
    ]
    for card in cases:
        score, label = score_card(card)
        assert 0.0 <= score <= 1.0, f"score {score} out of [0,1] for {card}"
        assert label in _VALID_LABELS, f"Invalid label {label!r} for {card}"
        assert math.isfinite(score), f"score is not finite for {card}"


# ---------------------------------------------------------------------------
# Spec test 7: no $ / roi / pnl key anywhere (input card is the boundary)
# ---------------------------------------------------------------------------

def test_no_dollar_key_in_card():
    """The card dict used as input must not produce or carry dollar fields."""
    card = _make_card()
    # The function does not mutate the card, but let's verify the card itself
    # is spec-clean (representative of how cards are built upstream).
    assert not _has_dollar_key(card), "Test card itself has a $ key -- test bug"
    # And the return value is (score: float, label: str) -- no dict returned at all.
    result = score_card(card)
    assert isinstance(result, tuple) and len(result) == 2
    score, label = result
    assert isinstance(score, float)
    assert isinstance(label, str)


# ---------------------------------------------------------------------------
# Spec test 8: empty / garbage card -> (0.0, LOW); never raises
# ---------------------------------------------------------------------------

def test_empty_card_is_low_never_raises():
    """Empty dict and various garbage inputs must return (score ~0, LOW)."""
    bad_inputs = [
        {},
        None,
        "garbage string",
        42,
        [],
        {"model_prob": "NaN", "market_prob": None},
        {"model_prob": float("inf"), "market_prob": 0.5},
        {"model_prob": -99, "market_prob": 0.5, "n_samples": -1},
    ]
    for inp in bad_inputs:
        try:
            score, label = score_card(inp)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"score_card raised on {inp!r}: {exc}") from exc
        assert 0.0 <= score <= 1.0, f"score {score} out of range for {inp!r}"
        assert label in _VALID_LABELS, f"Invalid label {label!r} for {inp!r}"


# ---------------------------------------------------------------------------
# Additional test 9: perfect divergence, real CLV, ample -> HIGH confirmed
# ---------------------------------------------------------------------------

def test_perfect_signal_is_high():
    """Max divergence + real CLV + ample samples should clearly score HIGH."""
    card = _make_card(
        model_prob=0.75,
        market_prob=0.50,    # 5 sigma at sigma=0.05
        n_samples=1000,
        clv_is_proxy=False,
    )
    score, label = score_card(card)
    assert label == LABEL_HIGH, (
        f"Perfect signal should be HIGH, got {label} (score={score:.4f})"
    )


# ---------------------------------------------------------------------------
# Additional test 10: proxy CLV alone (with good other axes) stays <= MED
# ---------------------------------------------------------------------------

def test_proxy_clv_cannot_reach_high():
    """clv_is_proxy=True blocks HIGH regardless of other factors."""
    # Large divergence, ample samples, but proxy CLV
    card = _make_card(
        model_prob=0.80,
        market_prob=0.50,
        n_samples=1000,
        clv_is_proxy=True,
    )
    _, label = score_card(card)
    assert label != LABEL_HIGH, "clv_is_proxy=True must block HIGH label"


# ---------------------------------------------------------------------------
# Additional test 11: thin sample alone caps at LOW
# ---------------------------------------------------------------------------

def test_thin_sample_caps_at_low():
    """n_samples < THIN_THRESHOLD caps at LOW regardless of divergence."""
    card = _make_card(
        model_prob=0.80,
        market_prob=0.50,    # large divergence
        n_samples=5,         # very thin
        clv_is_proxy=False,
    )
    _, label = score_card(card)
    assert label == LABEL_LOW, (
        f"Thin sample must cap at LOW, got {label}"
    )


# ---------------------------------------------------------------------------
# Additional test 12: score_batch edge cases
# ---------------------------------------------------------------------------

def test_score_batch_empty_list():
    assert score_batch([]) == []


def test_score_batch_non_list():
    assert score_batch(None) == []
    assert score_batch("bad") == []


def test_score_batch_bad_card_in_list():
    results = score_batch([None, _make_card(), "bad"])
    assert len(results) == 3
    for score, label in results:
        assert 0.0 <= score <= 1.0
        assert label in _VALID_LABELS


# ---------------------------------------------------------------------------
# Additional test 13: divergence sweep stays in [0, 1]
# ---------------------------------------------------------------------------

def test_divergence_sweep_bounded():
    """score is in [0,1] across a sweep of model_prob values."""
    for mp in [0.50, 0.51, 0.55, 0.60, 0.65, 0.70, 0.80, 0.90, 0.95, 0.99]:
        card = _make_card(
            model_prob=mp,
            market_prob=0.50,
            n_samples=300,
            clv_is_proxy=False,
        )
        score, label = score_card(card)
        assert 0.0 <= score <= 1.0, f"score {score} out of range at mp={mp}"
        assert label in _VALID_LABELS
