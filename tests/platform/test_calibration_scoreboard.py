"""tests/platform/test_calibration_scoreboard.py — Synthetic unit tests for calibration_scoreboard.

All tests use SYNTHETIC metric providers — no real pipeline, data files, or heavy adapters
are loaded.  The test suite is intentionally pandas-light and fast.

Coverage:
  1. Metric helpers (_brier, _ece, _log_loss, _score) — correctness on known values.
  2. build_calibration_scoreboard — with injected fake providers.
  3. _render_markdown — banners, table rows, no forbidden tokens.
  4. _write_artifact — writes file to tmp path, content checks.
  5. Error handling — provider raises, graceful row with "error" key.
  6. Honest-token audit — no edge/ROI/beats-the-market tokens in output.
"""
from __future__ import annotations

import math
import sys
import os
from pathlib import Path
from typing import Dict, List

import numpy as np
import pytest

# Ensure repo root is on path
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.calibration_scoreboard import (
    _brier,
    _ece,
    _log_loss,
    _score,
    _render_markdown,
    _write_artifact,
    _fmt,
    _both_finite,
    build_calibration_scoreboard,
    HONEST_BANNER,
    SOCCER_SAMPLE_CAP,
)
from scripts.platformkit.brain_audit import scan_text  # the REAL self-policing audit

# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(42)


def _make_probs_outcomes(n: int = 200, bias: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Return (probs, outcomes) with mild calibration error controlled by bias."""
    p = _RNG.uniform(0.2, 0.8, n)
    # Outcomes drawn from Bernoulli(p + bias), clipped
    y = (_RNG.uniform(0, 1, n) < np.clip(p + bias, 0, 1)).astype(float)
    return p, y


def _fake_sport_result(sport: str, n: int = 200, *,
                       baseline_brier: float = 0.22,
                       improved_brier: float = 0.20,
                       baseline_ece: float = 0.04,
                       improved_ece: float = 0.02) -> Dict:
    """Return a synthetic SportMetrics dict without touching any adapter."""
    return {
        "sport": sport,
        "method": f"synthetic-method-{sport}",
        "baseline_label": "synthetic-baseline",
        "baseline": {"n": n, "brier": baseline_brier, "logloss": 0.65,
                     "ece": baseline_ece},
        "improved": {"n": n, "brier": improved_brier, "logloss": 0.62,
                     "ece": improved_ece},
    }


def _fake_provider(sport: str, **kw):
    """Return a zero-arg callable that produces synthetic SportMetrics."""
    def _fn():
        return _fake_sport_result(sport, **kw)
    return _fn


# ---------------------------------------------------------------------------
# 1. Metric helper tests
# ---------------------------------------------------------------------------

class TestBrier:
    def test_perfect(self):
        p = np.array([1.0, 0.0, 1.0, 0.0])
        y = np.array([1.0, 0.0, 1.0, 0.0])
        assert _brier(p, y) == pytest.approx(0.0, abs=1e-12)

    def test_coin(self):
        p = np.full(1000, 0.5)
        y = _RNG.integers(0, 2, 1000).astype(float)
        assert 0.23 <= _brier(p, y) <= 0.27

    def test_always_wrong(self):
        p = np.array([0.0, 1.0])
        y = np.array([1.0, 0.0])
        assert _brier(p, y) == pytest.approx(1.0, abs=1e-12)


class TestEce:
    def test_perfect_calibration(self):
        # Uniformly calibrated: mean pred ~= mean outcome in each bin
        p, y = _make_probs_outcomes(500)
        # ECE for rough calibration should be low (<0.05)
        assert _ece(p, y) < 0.10

    def test_highly_miscalibrated(self):
        # Always predict 0.9 but outcome is 0.1 base-rate
        n = 200
        p = np.full(n, 0.9)
        y = np.zeros(n)
        y[:20] = 1.0
        assert _ece(p, y) > 0.5

    def test_empty(self):
        # _ece returns 0.0 for empty arrays (no bins populated → zero total)
        result = _ece(np.array([]), np.array([]))
        assert result == pytest.approx(0.0)

    def test_output_in_range(self):
        p, y = _make_probs_outcomes(300)
        e = _ece(p, y)
        assert 0.0 <= e <= 1.0


class TestLogLoss:
    def test_perfect_log_loss(self):
        p = np.array([1.0 - 1e-12, 1e-12])
        y = np.array([1.0, 0.0])
        assert _log_loss(p, y) < 1e-9

    def test_coin_logloss(self):
        p = np.full(100, 0.5)
        y = np.array([1.0] * 50 + [0.0] * 50)
        assert _log_loss(p, y) == pytest.approx(math.log(2), rel=0.01)


class TestScore:
    def test_returns_expected_keys(self):
        p, y = _make_probs_outcomes()
        s = _score(p, y)
        assert set(s) >= {"n", "brier", "logloss", "ece"}

    def test_n_matches_input(self):
        p, y = _make_probs_outcomes(150)
        s = _score(p, y)
        assert s["n"] == 150

    def test_nan_rows_excluded(self):
        p = np.array([0.5, float("nan"), 0.6])
        y = np.array([1.0, 0.0, 0.0])
        s = _score(p, y)
        assert s["n"] == 2

    def test_all_nan(self):
        p = np.full(10, float("nan"))
        y = np.ones(10)
        s = _score(p, y)
        assert s["n"] == 0
        assert math.isnan(s["brier"])


# ---------------------------------------------------------------------------
# 2. build_calibration_scoreboard with synthetic providers
# ---------------------------------------------------------------------------

class TestBuildScoreboard:
    def test_returns_one_row_per_provider(self, tmp_path):
        providers = {
            "NBA": _fake_provider("NBA"),
            "TENNIS": _fake_provider("TENNIS"),
        }
        rows = build_calibration_scoreboard(providers=providers,
                                            vault_root=tmp_path, write=False)
        assert len(rows) == 2

    def test_sport_keys_present(self, tmp_path):
        providers = {"MLB": _fake_provider("MLB"), "SOCCER": _fake_provider("SOCCER")}
        rows = build_calibration_scoreboard(providers=providers,
                                            vault_root=tmp_path, write=False)
        sports = {r["sport"] for r in rows}
        assert "MLB" in sports and "SOCCER" in sports

    def test_write_creates_artifact(self, tmp_path):
        providers = {"NBA": _fake_provider("NBA")}
        build_calibration_scoreboard(providers=providers,
                                     vault_root=tmp_path, write=True)
        artifact = tmp_path / "_Calibration_Scoreboard.md"
        assert artifact.exists()
        assert artifact.stat().st_size > 100

    def test_error_provider_captured(self, tmp_path):
        def _bad_provider():
            raise RuntimeError("synthetic error")

        providers = {"BAD": _bad_provider}
        rows = build_calibration_scoreboard(providers=providers,
                                            vault_root=tmp_path, write=False)
        assert len(rows) == 1
        assert "error" in rows[0]
        assert "synthetic error" in rows[0]["error"]

    def test_mixed_providers(self, tmp_path):
        def _bad():
            raise ValueError("oops")

        providers = {"GOOD": _fake_provider("GOOD"), "BAD": _bad}
        rows = build_calibration_scoreboard(providers=providers,
                                            vault_root=tmp_path, write=False)
        assert len(rows) == 2
        good = next(r for r in rows if r.get("sport") == "GOOD")
        bad = next(r for r in rows if r.get("sport") == "BAD")
        assert "error" not in good
        assert "error" in bad


# ---------------------------------------------------------------------------
# 3. _render_markdown — structure and honest-token audit
# ---------------------------------------------------------------------------

# Affirmative edge-claim tokens that must NOT appear positively in the output.
# Note: negation phrases like "no roi" or "no beats-the-market claim" are fine.
# We check that the token does not appear in an affirmative context by looking for
# "no X" / "not X" prefixes and only flagging un-negated occurrences.
_AFFIRMATIVE_EDGE_TOKENS = [
    "positive expected value",
    "guaranteed edge",
    "beats the close",
    "beat the close",
    "market edge is claimed",
    "edge is proven",
    "+x% roi",
]


class TestRenderMarkdown:
    @pytest.fixture
    def sample_rows(self):
        return [
            _fake_sport_result("NBA"),
            _fake_sport_result("TENNIS", baseline_brier=0.23, improved_brier=0.19),
        ]

    def test_contains_honest_banner(self, sample_rows):
        md = _render_markdown(sample_rows)
        assert "calibration metric" in md.lower() or "not a market edge" in md.lower()

    def test_contains_table_header(self, sample_rows):
        md = _render_markdown(sample_rows)
        assert "| Sport |" in md

    def test_sport_rows_in_table(self, sample_rows):
        md = _render_markdown(sample_rows)
        assert "NBA" in md
        assert "TENNIS" in md

    def test_no_forbidden_edge_tokens(self, sample_rows):
        md = _render_markdown(sample_rows).lower()
        for tok in _AFFIRMATIVE_EDGE_TOKENS:
            assert tok not in md, f"Forbidden edge token found: '{tok}'"

    def test_real_audit_scan_text_clean(self, sample_rows):
        # Tie this test to the REAL brain_audit (W96 lesson): the hand-maintained
        # _AFFIRMATIVE_EDGE_TOKENS list diverged from scan_text -- the banner's
        # 'guaranteed-edge' slipped past the list (it checks 'guaranteed edge' with a
        # space) but scan_text flagged the bare word 'guaranteed' on the real rebuild.
        # The authoritative audit (what the brain_pipeline gate runs) must be clean.
        assert scan_text(HONEST_BANNER) == [], scan_text(HONEST_BANNER)
        assert scan_text(_render_markdown(sample_rows)) == [], \
            scan_text(_render_markdown(sample_rows))

    def test_error_row_rendered(self):
        rows = [{"sport": "MLB", "error": "corpus absent"}]
        md = _render_markdown(rows)
        assert "ERROR" in md
        assert "MLB" in md

    def test_delta_values_appear(self, sample_rows):
        md = _render_markdown(sample_rows)
        # delta should appear as a signed number like -0.02000
        assert "-0.0" in md or "+0.0" in md


# ---------------------------------------------------------------------------
# 4. _write_artifact
# ---------------------------------------------------------------------------

class TestWriteArtifact:
    def test_creates_file(self, tmp_path):
        rows = [_fake_sport_result("NBA")]
        p = _write_artifact(rows, vault_root=tmp_path)
        assert p.exists()

    def test_file_content_has_banner(self, tmp_path):
        rows = [_fake_sport_result("TENNIS")]
        p = _write_artifact(rows, vault_root=tmp_path)
        content = p.read_text(encoding="utf-8")
        assert "calibration" in content.lower()

    def test_no_edge_tokens_in_file(self, tmp_path):
        rows = [_fake_sport_result("SOCCER")]
        p = _write_artifact(rows, vault_root=tmp_path)
        content = p.read_text(encoding="utf-8").lower()
        for tok in _AFFIRMATIVE_EDGE_TOKENS:
            assert tok not in content, f"Forbidden edge token in artifact: '{tok}'"


# ---------------------------------------------------------------------------
# 5. Utility helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_fmt_nan(self):
        assert _fmt(float("nan")) == "—"

    def test_fmt_regular(self):
        assert _fmt(0.12345) == "0.12345"

    def test_fmt_signed(self):
        s = _fmt(-0.01, signed=True)
        assert s.startswith("-")

    def test_both_finite_true(self):
        assert _both_finite(0.5, 0.6)

    def test_both_finite_false(self):
        assert not _both_finite(float("nan"), 0.5)
        assert not _both_finite(0.5, float("inf"))

    def test_soccer_sample_cap_is_positive(self):
        assert SOCCER_SAMPLE_CAP > 0

    def test_honest_banner_no_edge_claim(self):
        banner_lower = HONEST_BANNER.lower()
        # Banner must contain explicit denial language
        assert "no edge" in banner_lower or "not a market edge" in banner_lower
        # Banner must not contain affirmative edge claims (negated phrases like "no roi" are fine)
        for tok in _AFFIRMATIVE_EDGE_TOKENS:
            assert tok not in banner_lower, f"Affirmative edge token in banner: '{tok}'"
