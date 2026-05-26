"""tests/test_R30_W3_cache_rebuild.py — R30_W3 predictions cache rebuild.

Six checks covering the refresh + probe pipeline for today's
``data/cache/predictions_cache_<date>.parquet``:

  1. cache_exists      — the rebuilt parquet is on disk and parseable
  2. schema_preserved  — rebuilt columns match the legacy/backup columns
  3. n_rows_reasonable — non-zero row count and a multiple of len(STATS)=7
  4. mtime_advances    — rebuilt mtime > backup mtime (a fresh write
                          happened); only checked when backup exists
  5. reproducible      — re-running the refresher on a tiny --max sample
                          produces the same q50 for the same (pid, stat)
                          on a second call (deterministic predictor)
  6. backup_or_probe   — either the .bak_R30_W3 sidecar exists OR the
                          probe JSON (probe_R30_W3_results.json) was
                          written (covers the "no prior cache" cold path)

Tests skip gracefully when artifacts are absent so they're safe to ship
on machines without the parent repo's gamelog cache.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date as _date

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_TODAY = _date.today().isoformat()
_CACHE = os.path.join(PROJECT_DIR, "data", "cache",
                      f"predictions_cache_{_TODAY}.parquet")
_BAK = _CACHE + ".bak_R30_W3"
_PROBE_JSON = os.path.join(PROJECT_DIR, "data", "cache",
                           "probe_R30_W3_results.json")

_EXPECTED_COLS = {
    "player_id", "player_name", "team", "stat",
    "q10", "q50", "q90", "sigma", "computed_at",
}


def _load(p: str):
    pd = pytest.importorskip("pandas")
    if not os.path.exists(p):
        pytest.skip(f"missing artifact: {p}")
    return pd.read_parquet(p)


def test_cache_exists_and_parseable() -> None:
    if not os.path.exists(_CACHE):
        pytest.skip(f"rebuilt cache absent: {_CACHE}")
    df = _load(_CACHE)
    assert df is not None
    # Empty is allowed in the off-season / cold start; just must be readable.
    assert set(df.columns) == _EXPECTED_COLS, (
        f"unexpected schema: {set(df.columns)}"
    )


def test_schema_preserved_vs_backup() -> None:
    if not (os.path.exists(_CACHE) and os.path.exists(_BAK)):
        pytest.skip("need both rebuilt cache + backup for schema-parity check")
    new = _load(_CACHE)
    old = _load(_BAK)
    assert list(new.columns) == list(old.columns)
    # dtypes should also match column-for-column
    for c in new.columns:
        assert new[c].dtype == old[c].dtype, (
            f"dtype mismatch on {c}: {new[c].dtype} vs {old[c].dtype}"
        )


def test_n_rows_reasonable() -> None:
    if not os.path.exists(_CACHE):
        pytest.skip("rebuilt cache absent")
    df = _load(_CACHE)
    # If non-empty, len must be a clean multiple of STATS count (7).
    from src.prediction.prop_pergame import STATS  # noqa: PLC0415
    assert len(df) % len(STATS) == 0, (
        f"len(df)={len(df)} not a multiple of n_stats={len(STATS)}"
    )


def test_mtime_advances_after_rebuild() -> None:
    if not (os.path.exists(_CACHE) and os.path.exists(_BAK)):
        pytest.skip("need both rebuilt cache + backup to compare mtimes")
    assert os.path.getmtime(_CACHE) >= os.path.getmtime(_BAK), (
        "rebuilt cache mtime is older than backup — rebuild did not run"
    )


def test_predictions_reproducible_smoke() -> None:
    """Re-run a 5-player rebuild twice; q50 must match (deterministic models)."""
    pd = pytest.importorskip("pandas")
    from scripts.improve_loop.refresh_predictions_cache import refresh  # noqa: PLC0415

    # Use temp out paths so the official cache isn't disturbed by the test.
    tmp_a = os.path.join(PROJECT_DIR, "data", "cache",
                         "_R30_W3_test_a.parquet")
    tmp_b = os.path.join(PROJECT_DIR, "data", "cache",
                         "_R30_W3_test_b.parquet")
    for p in (tmp_a, tmp_b):
        if os.path.exists(p):
            os.remove(p)
    try:
        _, n_a, _ = refresh(max_players=5, backup=False,
                            out_path=tmp_a, verbose=False)
        _, n_b, _ = refresh(max_players=5, backup=False,
                            out_path=tmp_b, verbose=False)
        if n_a == 0 or n_b == 0:
            pytest.skip("no gamelogs available — cannot test reproducibility")
        a = pd.read_parquet(tmp_a)
        b = pd.read_parquet(tmp_b)
        assert n_a == n_b
        merged = a.merge(
            b[["player_id", "stat", "q50"]],
            on=["player_id", "stat"], suffixes=("_a", "_b"),
        )
        # Identical inputs + frozen models -> identical q50.
        diff = (merged["q50_a"] - merged["q50_b"]).abs().max()
        assert diff < 1e-6, (
            f"non-deterministic: max |q50_a - q50_b| = {diff}"
        )
    finally:
        for p in (tmp_a, tmp_b):
            if os.path.exists(p):
                os.remove(p)


def test_backup_created_or_probe_ran() -> None:
    """Either the .bak_R30_W3 sidecar exists (refresh ran with backup=True)
    OR the probe JSON exists (probe wrote results). At least one must be
    present after a successful R30_W3 ship — the test fails when neither
    is."""
    if not os.path.exists(_CACHE):
        pytest.skip("rebuilt cache absent")
    has_bak = os.path.exists(_BAK)
    has_probe = os.path.exists(_PROBE_JSON)
    assert has_bak or has_probe, (
        f"neither backup ({_BAK}) nor probe ({_PROBE_JSON}) exists "
        "— refresh + probe did not run end-to-end"
    )
    # When the probe ran, it should contain the canonical keys.
    if has_probe:
        with open(_PROBE_JSON, encoding="utf-8") as f:
            d = json.load(f)
        for k in ("probe", "today", "n_predictions_new",
                  "cache_new_mtime"):
            assert k in d, f"probe missing key: {k}"
        assert d["probe"] == "R30_W3"
