"""tests.platform.test_research_digest — Tests for the concise research digest.

Verifies that format_digest:
  1. Contains verdict counts (REJECT / SHIP / DEFER / VARIANCE_ONLY).
  2. Contains coverage information.
  3. Contains belief P(ship) mean when belief_summary is populated.
  4. Contains the honest "markets efficient / no edge" framing.
  5. Contains NO edge-claim language.
  6. Is deterministic (same input → same output).
  7. Is graceful on an empty result dict.
  8. Stays under 20 lines.

All tests are offline / no filesystem I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_HARNESS = _ROOT / "scripts" / "research_harness"
if str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))

from research_digest import format_digest  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic result fixtures
# ---------------------------------------------------------------------------

_SYNTHETIC_RESULT: dict = {
    "n_ingested": 4,
    "n_total": 4,
    "out_md": None,
    "coverage_summary": "Coverage: 37.5% of candidates tested across 4 sports.",
    "verdict_summary": {"REJECT": 3, "SHIP": 0, "DEFER": 1, "VARIANCE_ONLY": 0},
    "skipped_no_data": False,
    "beliefs_path": None,
    "belief_summary": {
        "tennis": {"rest_diff": 0.102, "elo_gap": 0.095},
        "soccer": {"over_under": 0.108},
    },
    "top_gaps": [],
}

_EMPTY_RESULT: dict = {}

# Edge-claim phrases that must NOT appear in digest output.
_EDGE_WORDS = (
    "profitable", "profitability", "arbitrage",
    "winning strategy", "guaranteed",
    "positive edge", "betting edge", "proven edge",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _digest(result: dict) -> str:
    """Return lowercase digest for easier assertion."""
    return format_digest(result).lower()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_digest_contains_reject_count() -> None:
    """Digest must show REJECT count from verdict_summary."""
    out = _digest(_SYNTHETIC_RESULT)
    assert "reject" in out
    assert "3" in out  # 3 REJECTs in fixture


def test_digest_contains_ship_count() -> None:
    """Digest must show SHIP count."""
    out = _digest(_SYNTHETIC_RESULT)
    assert "ship" in out
    assert "0" in out  # 0 SHIPs


def test_digest_contains_defer_count() -> None:
    """Digest must show DEFER count."""
    out = _digest(_SYNTHETIC_RESULT)
    assert "defer" in out
    assert "1" in out  # 1 DEFER


def test_digest_contains_variance_only_count() -> None:
    """Digest must show VARIANCE_ONLY count."""
    out = _digest(_SYNTHETIC_RESULT)
    assert "variance_only" in out


def test_digest_contains_coverage() -> None:
    """Digest must surface coverage information."""
    out = _digest(_SYNTHETIC_RESULT)
    # Either the % or the word coverage must appear
    assert "coverage" in out or "%" in out


def test_digest_contains_belief_mean() -> None:
    """When belief_summary is populated digest must show P(ship) mean."""
    out = _digest(_SYNTHETIC_RESULT)
    # belief_summary has 3 posteriors: 0.102, 0.095, 0.108 → mean ≈ 0.102
    assert "p(ship)" in out or "belief" in out


def test_digest_belief_mean_value() -> None:
    """The belief mean shown must be numerically consistent with the fixture."""
    raw = format_digest(_SYNTHETIC_RESULT)
    import re
    # Look for pattern like "mean=0.102" or similar float
    matches = re.findall(r"mean=(\d+\.\d+)", raw, re.IGNORECASE)
    assert matches, f"No 'mean=<float>' found in digest:\n{raw}"
    mean_val = float(matches[0])
    expected = (0.102 + 0.095 + 0.108) / 3
    assert abs(mean_val - expected) < 0.005, (
        f"Belief mean {mean_val:.4f} deviates from expected {expected:.4f}"
    )


def test_digest_contains_honest_framing() -> None:
    """Digest must contain the honest market-efficiency / no-edge framing."""
    out = _digest(_SYNTHETIC_RESULT)
    assert "no edge is claimed" in out
    assert "market" in out and "efficient" in out
    assert "reject" in out  # REJECT = success framing


def test_digest_no_edge_claim_language() -> None:
    """Digest must not contain any positive edge-claim language."""
    out = _digest(_SYNTHETIC_RESULT)
    for phrase in _EDGE_WORDS:
        assert phrase not in out, (
            f"Digest contains forbidden edge-claim phrase: {phrase!r}"
        )


def test_digest_is_deterministic() -> None:
    """Same input must produce byte-identical output."""
    d1 = format_digest(_SYNTHETIC_RESULT)
    d2 = format_digest(_SYNTHETIC_RESULT)
    assert d1 == d2, "format_digest is not deterministic"


def test_digest_graceful_on_empty() -> None:
    """Empty result dict must not raise; output must still contain honest framing."""
    out = _digest(_EMPTY_RESULT)
    assert "no edge is claimed" in out
    assert "market" in out


def test_digest_graceful_on_empty_no_edge_claims() -> None:
    """Empty result digest must also be free of edge-claim language."""
    out = _digest(_EMPTY_RESULT)
    for phrase in _EDGE_WORDS:
        assert phrase not in out, (
            f"Empty-result digest contains forbidden phrase: {phrase!r}"
        )


def test_digest_under_20_lines() -> None:
    """Digest must stay under 20 printed lines (compact terminal summary)."""
    raw = format_digest(_SYNTHETIC_RESULT)
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    assert len(lines) <= 20, (
        f"Digest is {len(lines)} non-empty lines — exceeds 20-line limit:\n{raw}"
    )


def test_digest_with_top_gaps() -> None:
    """When top_gaps are present they must appear in the digest."""
    from dataclasses import dataclass

    @dataclass
    class FakeGap:
        label: str
        score: float

    result_with_gaps = {**_SYNTHETIC_RESULT, "top_gaps": [
        FakeGap(label="tennis_surface_h2h", score=0.87),
        FakeGap(label="soccer_xg_ratio", score=0.74),
        FakeGap(label="mlb_home_rest", score=0.61),
    ]}
    out = _digest(result_with_gaps)
    assert "tennis_surface_h2h" in out
    assert "soccer_xg_ratio" in out
    assert "mlb_home_rest" in out


def test_digest_top_gaps_honest_framing() -> None:
    """Top-gaps section must not imply gaps are opportunities / edges."""
    from dataclasses import dataclass

    @dataclass
    class FakeGap:
        label: str
        score: float

    result_with_gaps = {**_SYNTHETIC_RESULT, "top_gaps": [
        FakeGap(label="tennis_surface_h2h", score=0.87),
    ]}
    out = _digest(result_with_gaps)
    # The honest framing in the gaps section
    assert "untested" in out or "completeness" in out or "opportunity" in out


def test_digest_returns_string() -> None:
    """format_digest must always return a str, never None."""
    result = format_digest(_SYNTHETIC_RESULT)
    assert isinstance(result, str)
    assert len(result) > 0
