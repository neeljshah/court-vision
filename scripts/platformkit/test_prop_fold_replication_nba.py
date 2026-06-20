"""Per-file test for prop_fold_replication_nba.

Acceptance criteria (from BACKLOG PE-X2):
  - synthetic 5-fold OOF -> per-stat dict has per_fold_bss + n_folds_positive
  - stat passing only 1-of-5 folds -> REPLICATION_PENDING (not SHIP)
  - stat passing >= 3-of-5 folds -> REPLICATED
  - all-fold-negative BSS -> REJECT
  - thin fold (n < MIN_FOLD_N) -> INSUFFICIENT_DATA fold excluded from count
  - no $ key in output

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_fold_replication_nba.py -q
"""
from __future__ import annotations

import math
import random
import string

import pytest

from scripts.platformkit.prop_fold_replication_nba import (
    INSUFFICIENT_DATA,
    MIN_FOLD_N,
    REJECT,
    REPLICATED,
    REPLICATION_PENDING,
    load_and_run,
    run_fold_replication,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RNG_SEED = 42


def _make_df(rows):
    """Build a minimal pandas DataFrame from a list of dicts."""
    import pandas as pd
    return pd.DataFrame(rows)


def _gaussian_rows(stat, fold, n, mu_pred=15.0, mu_actual=15.0, noise=4.0, seed=_RNG_SEED):
    """Synthetic rows for a stat/fold: well-calibrated Gaussian predictions."""
    rng = random.Random(seed + fold * 1000 + n)
    out = []
    for _ in range(n):
        pred = rng.gauss(mu_pred, noise)
        actual = rng.gauss(mu_actual, noise)
        out.append({"stat": stat, "fold": fold, "oof_pred": pred, "actual": actual})
    return out


def _skilled_rows(stat, fold, n, skill=0.6, seed=_RNG_SEED):
    """Rows where predictions correlate with outcomes (BSS > 0 expected)."""
    rng = random.Random(seed + fold * 100 + n)
    out = []
    for _ in range(n):
        true_val = rng.gauss(15.0, 4.0)
        noise = rng.gauss(0.0, 1.5)
        pred = true_val * skill + (1 - skill) * 15.0 + noise
        out.append({"stat": stat, "fold": fold, "oof_pred": pred, "actual": true_val})
    return out


def _unskilled_rows(stat, fold, n, seed=_RNG_SEED):
    """Rows where predictions are random noise (BSS <= 0 expected)."""
    rng = random.Random(seed + fold * 777 + n)
    out = []
    for _ in range(n):
        # pred is just a constant; BSS will be ~0 or negative
        pred = 5.0 + rng.uniform(-0.01, 0.01)  # near-constant => bad calibration
        actual = rng.gauss(15.0, 4.0)
        out.append({"stat": stat, "fold": fold, "oof_pred": pred, "actual": actual})
    return out


# ---------------------------------------------------------------------------
# Tests: output structure
# ---------------------------------------------------------------------------

def test_output_has_required_keys():
    """Result always has stats, per_stat, note keys."""
    df = _make_df(_skilled_rows("pts", 1, 50))
    res = run_fold_replication(df, stats=["pts"])
    assert "stats" in res
    assert "per_stat" in res
    assert "note" in res


def test_no_dollar_key_in_output():
    """No $ key anywhere in top-level or per_stat entries."""
    rows = []
    for fold in range(1, 6):
        rows += _skilled_rows("pts", fold, 60)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["pts"])
    for key in res:
        assert "$" not in str(key), f"dollar key found: {key}"
    stat_entry = res["per_stat"].get("pts")
    if isinstance(stat_entry, dict):
        for key in stat_entry:
            assert "$" not in str(key), f"dollar key in stat entry: {key}"


def test_per_stat_has_fold_bss_and_n_folds_positive():
    """Each scored stat entry has per_fold_bss and n_folds_positive."""
    rows = []
    for fold in range(1, 6):
        rows += _skilled_rows("ast", fold, 100)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["ast"])
    entry = res["per_stat"]["ast"]
    assert isinstance(entry, dict), f"expected dict, got {entry}"
    assert "per_fold_bss" in entry, "missing per_fold_bss"
    assert "n_folds_positive" in entry, "missing n_folds_positive"
    assert "n_folds_evaluated" in entry, "missing n_folds_evaluated"
    assert "verdict" in entry, "missing verdict"


# ---------------------------------------------------------------------------
# Tests: verdicts
# ---------------------------------------------------------------------------

def test_replicated_when_three_plus_folds_positive():
    """Stat with skilled preds in all 5 folds -> REPLICATED."""
    rows = []
    for fold in range(1, 6):
        rows += _skilled_rows("pts", fold, 200, skill=0.8, seed=fold * 7)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["pts"])
    entry = res["per_stat"]["pts"]
    assert isinstance(entry, dict)
    assert entry["n_folds_positive"] >= 3, (
        f"expected >=3 folds positive, got {entry['n_folds_positive']}"
    )
    assert entry["verdict"] == REPLICATED, f"expected REPLICATED, got {entry['verdict']}"


def test_replication_pending_when_one_fold_positive():
    """Stat with only 1 positive fold -> REPLICATION_PENDING."""
    import pandas as pd
    rows = []
    # fold 1: skilled (BSS > 0)
    rows += _skilled_rows("reb", 1, 200, skill=0.9, seed=1)
    # folds 2-5: unskilled (BSS <= 0)
    for fold in range(2, 6):
        rows += _unskilled_rows("reb", fold, 200, seed=fold * 13)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["reb"])
    entry = res["per_stat"]["reb"]
    assert isinstance(entry, dict)
    assert entry["n_folds_positive"] == 1, (
        f"expected exactly 1 fold positive, got {entry['n_folds_positive']}"
    )
    assert entry["verdict"] == REPLICATION_PENDING, (
        f"expected REPLICATION_PENDING, got {entry['verdict']}"
    )


def test_reject_when_all_folds_negative():
    """Stat with no positive BSS in any fold -> REJECT."""
    rows = []
    for fold in range(1, 6):
        rows += _unskilled_rows("blk", fold, 200, seed=fold * 31)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["blk"])
    entry = res["per_stat"]["blk"]
    assert isinstance(entry, dict)
    assert entry["n_folds_positive"] == 0, (
        f"expected 0 folds positive, got {entry['n_folds_positive']}"
    )
    assert entry["verdict"] == REJECT, f"expected REJECT, got {entry['verdict']}"


# ---------------------------------------------------------------------------
# Tests: thin-fold handling
# ---------------------------------------------------------------------------

def test_thin_fold_excluded_not_counted():
    """Thin fold (n < MIN_FOLD_N) -> INSUFFICIENT_DATA in per_fold_bss, not counted."""
    rows = []
    # fold 1: thin (< MIN_FOLD_N)
    rows += _skilled_rows("stl", 1, MIN_FOLD_N - 1, skill=0.9, seed=99)
    # folds 2-5: skilled + thick
    for fold in range(2, 6):
        rows += _skilled_rows("stl", fold, 200, skill=0.5, seed=fold * 3)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["stl"])
    entry = res["per_stat"]["stl"]
    assert isinstance(entry, dict)
    fold_bss = entry["per_fold_bss"]
    # fold 1 key should be INSUFFICIENT_DATA (thin)
    fold1_val = fold_bss.get("1")
    assert fold1_val == INSUFFICIENT_DATA, (
        f"expected INSUFFICIENT_DATA for thin fold 1, got {fold1_val}"
    )
    # n_folds_evaluated should count only thick folds (4 folds)
    assert entry["n_folds_evaluated"] == 4, (
        f"expected 4 evaluated folds, got {entry['n_folds_evaluated']}"
    )


def test_all_folds_thin_gives_insufficient_data():
    """All folds thin -> verdict INSUFFICIENT_DATA."""
    rows = []
    for fold in range(1, 6):
        rows += _skilled_rows("tov", fold, MIN_FOLD_N - 1, skill=0.9, seed=fold * 17)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["tov"])
    entry = res["per_stat"]["tov"]
    assert entry == INSUFFICIENT_DATA or (
        isinstance(entry, dict) and entry.get("verdict") == INSUFFICIENT_DATA
    ), f"expected INSUFFICIENT_DATA, got {entry}"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

def test_empty_df_returns_insufficient_data():
    """Empty DataFrame -> per_stat all INSUFFICIENT_DATA."""
    import pandas as pd
    df = pd.DataFrame(columns=["stat", "fold", "oof_pred", "actual"])
    res = run_fold_replication(df, stats=["pts"])
    assert res["per_stat"]["pts"] == INSUFFICIENT_DATA


def test_missing_fold_column_graceful():
    """Missing fold column -> graceful note, no crash."""
    import pandas as pd
    df = pd.DataFrame([{"stat": "pts", "oof_pred": 10.0, "actual": 12.0}])
    res = run_fold_replication(df, stats=["pts"])
    assert "per_stat" in res
    # Should not raise; all stats -> INSUFFICIENT_DATA or note explains missing col
    assert "note" in res


def test_absent_parquet_returns_insufficient_data():
    """Absent parquet -> all INSUFFICIENT_DATA, no raise."""
    res = load_and_run(oof_path="/tmp/nonexistent_pregame_oof.parquet", stats=["pts"])
    assert res["per_stat"]["pts"] == INSUFFICIENT_DATA
    assert "note" in res


def test_multiple_stats_scored_independently():
    """Two stats in one DataFrame are scored independently."""
    rows = []
    for fold in range(1, 6):
        rows += _skilled_rows("pts", fold, 150, skill=0.8, seed=fold)
        rows += _unskilled_rows("tov", fold, 150, seed=fold * 41)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["pts", "tov"])
    pts_entry = res["per_stat"]["pts"]
    tov_entry = res["per_stat"]["tov"]
    assert isinstance(pts_entry, dict)
    assert isinstance(tov_entry, dict)
    # pts should be REPLICATED, tov should be REJECT
    assert pts_entry["verdict"] == REPLICATED, f"pts: {pts_entry}"
    assert tov_entry["verdict"] == REJECT, f"tov: {tov_entry}"


def test_per_fold_bss_values_are_finite_floats_or_sentinel():
    """per_fold_bss values are finite floats or INSUFFICIENT_DATA string."""
    rows = []
    for fold in range(1, 6):
        rows += _skilled_rows("fg3m", fold, 80, skill=0.7, seed=fold * 5)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["fg3m"])
    entry = res["per_stat"]["fg3m"]
    assert isinstance(entry, dict)
    for fold_key, bss_val in entry["per_fold_bss"].items():
        if bss_val != INSUFFICIENT_DATA:
            assert isinstance(bss_val, float), f"fold {fold_key} bss not float: {bss_val}"
            assert math.isfinite(bss_val), f"fold {fold_key} bss not finite: {bss_val}"


def test_n_folds_positive_is_int():
    """n_folds_positive is always an int."""
    rows = []
    for fold in range(1, 6):
        rows += _skilled_rows("reb", fold, 60, skill=0.6, seed=fold * 11)
    df = _make_df(rows)
    res = run_fold_replication(df, stats=["reb"])
    entry = res["per_stat"]["reb"]
    assert isinstance(entry, dict)
    assert isinstance(entry["n_folds_positive"], int)
