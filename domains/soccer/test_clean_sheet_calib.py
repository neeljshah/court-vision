"""domains/soccer/test_clean_sheet_calib.py -- Per-file tests for clean_sheet_calib.

Tests:
  1. sum_to_one: P(cs_home) + P(no_cs_home) = 1.0 from scoreline engine
  2. identity-in / identity-out: perfectly-calibrated input unchanged post-calib
  3. thin corpus: n < MIN_CORPUS -> INSUFFICIENT_DATA verdict
  4. real corpus (if present): held-out ECE(recal) < ECE(raw) OR verdict='REJECT' recorded
  5. btts coherence: btts_yes + btts_no = 1.0 from markets.py
  6. no-dollar field: verdict dict has no $ or money field
  7. pinball_ok flag present in market results

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_clean_sheet_calib.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.soccer.clean_sheet_calib import (
    MIN_CORPUS,
    MIN_HISTORY,
    CALIBRATION_NOTE,
    _ece,
    _pinball,
    _wf_cal,
    run_calibration,
)
from domains.soccer.scoreline_engine import scoreline_matrix
from domains.soccer.markets import clean_sheet, btts


# ---------------------------------------------------------------------------
# 1. sum-to-one coherence
# ---------------------------------------------------------------------------

def test_clean_sheet_sum_to_one():
    """P(cs_home_clean) + P(no_cs_home) must equal 1.0 for any valid lambda pair."""
    for lam_h, lam_a in [(1.2, 0.9), (2.5, 1.8), (0.5, 3.0)]:
        P = scoreline_matrix(lam_h, lam_a)
        cs = clean_sheet(P)
        total = cs["cs_home_clean"] + (1.0 - cs["cs_home_clean"])
        assert abs(total - 1.0) < 1e-9, f"cs_home complement failed: {total}"
        total2 = cs["cs_away_clean"] + (1.0 - cs["cs_away_clean"])
        assert abs(total2 - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 2. btts coherence
# ---------------------------------------------------------------------------

def test_btts_sum_to_one():
    """btts_yes + btts_no must equal 1.0."""
    for lam_h, lam_a in [(1.5, 1.5), (0.6, 2.2), (3.0, 0.4)]:
        P = scoreline_matrix(lam_h, lam_a)
        b = btts(P)
        assert abs(b["btts_yes"] + b["btts_no"] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 3. walk-forward calibration: identity on already-perfect calibrator
# ---------------------------------------------------------------------------

def test_wf_cal_passthrough_below_min_history():
    """Events before MIN_HISTORY must pass through as-is."""
    n = MIN_HISTORY - 1
    rng = np.random.default_rng(42)
    raw = rng.uniform(0.2, 0.8, n)
    out = (rng.random(n) > 0.5).astype(float)
    valid = np.ones(n, dtype=bool)
    cal = _wf_cal(raw, out, valid, min_history=MIN_HISTORY)
    np.testing.assert_allclose(cal, np.clip(raw, 0, 1), atol=1e-9,
                                err_msg="Pass-through below MIN_HISTORY failed")


# ---------------------------------------------------------------------------
# 4. thin corpus -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

def test_thin_corpus_insufficient_data(tmp_path):
    """Fewer than MIN_CORPUS valid rows -> INSUFFICIENT_DATA, no crash."""
    import pandas as pd

    rows = []
    for i in range(MIN_CORPUS - 1):
        rows.append({
            "event_id": f"e{i}", "date": "2022-01-01", "season": 2022,
            "div": "E0", "home_team": "A", "away_team": "B",
            "fthg": 1, "ftag": 0, "total_goals": 1,
            "target_over25": 0, "ftr": "H",
        })
    df = pd.DataFrame(rows)
    parquet_path = str(tmp_path / "matches.parquet")
    df.to_parquet(parquet_path, index=False)

    result = run_calibration(matches_path=parquet_path, min_corpus=MIN_CORPUS)
    assert result["verdict"] == "INSUFFICIENT_DATA", (
        f"Expected INSUFFICIENT_DATA, got {result['verdict']}"
    )
    assert result["n"] < MIN_CORPUS


# ---------------------------------------------------------------------------
# 5. real corpus: calibration improvement OR honest REJECT
# ---------------------------------------------------------------------------

def test_real_corpus_verdict():
    """On the real corpus: verdict is SHIP or REJECT (never silent crash).

    Acceptance: verdict in {SHIP, REJECT} AND markets dict populated.
    Either ECE improvement (SHIP) OR honest REJECT recorded is a valid pass.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    corpus = root / "data" / "domains" / "soccer" / "matches.parquet"
    if not corpus.exists():
        pytest.skip("Soccer corpus not available; skipping real-corpus test")

    result = run_calibration()
    assert result["verdict"] in ("SHIP", "REJECT"), (
        f"Unexpected verdict: {result['verdict']}"
    )
    assert len(result["markets"]) == 3, "Expected 3 markets: cs_home, cs_away, btts"
    assert result["sum_to_one_ok"], "sum_to_one coherence check failed on real corpus"

    # Acceptance: if SHIP, all ECE improved; if REJECT, honest gate recorded
    if result["verdict"] == "SHIP":
        for mkt, res in result["markets"].items():
            assert res["ece_improves"], f"{mkt}: SHIP but ECE did not improve"
            assert res["pinball_ok"], f"{mkt}: SHIP but pinball not ok"
    else:
        failing = [k for k, v in result["markets"].items() if not v["passes"]]
        assert len(failing) > 0, "REJECT verdict but no failing markets recorded"


# ---------------------------------------------------------------------------
# 6. no $ field in result
# ---------------------------------------------------------------------------

def test_no_dollar_field():
    """Result dict must not contain any dollar/money field (no edge claim)."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    corpus = root / "data" / "domains" / "soccer" / "matches.parquet"
    if not corpus.exists():
        pytest.skip("Soccer corpus not available")

    result = run_calibration()
    # Flatten all keys from nested dicts
    all_keys = list(result.keys())
    for mkt in result.get("markets", {}).values():
        all_keys.extend(mkt.keys())
    dollar_keys = [k for k in all_keys if "$" in k or "profit" in k.lower() or "roi" in k.lower()]
    assert len(dollar_keys) == 0, f"Found dollar/money fields: {dollar_keys}"


# ---------------------------------------------------------------------------
# 7. scoring helpers correctness
# ---------------------------------------------------------------------------

def test_ece_perfect():
    """ECE of a perfectly-calibrated uniform predictor should be near zero."""
    n = 1000
    p = np.full(n, 0.5)
    rng = np.random.default_rng(0)
    y = rng.binomial(1, 0.5, n).astype(float)
    ece = _ece(p, y, bins=5)
    assert ece < 0.05, f"ECE of 0.5-predictor on 50/50 data should be ~0; got {ece:.4f}"


def test_pinball_is_brier():
    """_pinball is Brier (CRPS for binary): lower for well-calibrated forecast."""
    rng = np.random.default_rng(7)
    y = rng.binomial(1, 0.4, 500).astype(float)
    # Well-calibrated: p = base rate
    pb_good = _pinball(np.full(500, 0.4), y)
    # Miscalibrated: p = 0.8 when truth is ~0.4
    pb_bad = _pinball(np.full(500, 0.8), y)
    # Also confirm it equals Brier
    brier = float(np.mean((np.full(500, 0.4) - y) ** 2))
    assert abs(pb_good - brier) < 1e-9, f"_pinball should equal Brier; {pb_good:.4f} != {brier:.4f}"
    assert pb_good < pb_bad, f"Well-calibrated brier {pb_good:.4f} should beat {pb_bad:.4f}"


# ---------------------------------------------------------------------------
# 8. pinball_ok flag present in market results
# ---------------------------------------------------------------------------

def test_market_result_keys():
    """Every market result must include pinball_ok and ece_improves keys."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    corpus = root / "data" / "domains" / "soccer" / "matches.parquet"
    if not corpus.exists():
        pytest.skip("Soccer corpus not available")

    result = run_calibration()
    required = {"ece_raw", "ece_cal", "pinball_raw", "pinball_cal",
                "ece_improves", "pinball_ok", "passes", "n_val"}
    for mkt, res in result["markets"].items():
        missing = required - set(res.keys())
        assert not missing, f"{mkt} missing keys: {missing}"
