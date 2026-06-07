"""Unit tests for src.loop.error_miner (residual mining + intel-scanner).

Self-contained: synthesises a biased residual bucket + a tiny in-memory store, so
the test needs no live data and no network (NBA_OFFLINE-safe).

Run:
    env NBA_OFFLINE=1 python -m pytest tests/test_loop_error_miner.py -q
"""
from __future__ import annotations

import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, ".")

from src.loop.error_miner import (  # noqa: E402
    ResidualBucket, bucket_residuals, intel_scan, mine, load_residuals,
)
from src.loop.signal import Hypothesis  # noqa: E402
from src.loop.store import PointInTimeStore  # noqa: E402


def _synthetic_rows(n_biased: int = 120, n_clean: int = 120):
    """Build residual rows: a BLOWOUT bucket biased high, a NORMAL bucket clean."""
    rows = []
    # biased bucket: model over-predicts pts by ~+3.0 in blowouts (systematic)
    for i in range(n_biased):
        rows.append({
            "stat": "pts", "pred": 20.0, "actual": 17.0 + (i % 3 - 1) * 0.5,
            "resid": 3.0 + (i % 3 - 1) * 0.5, "player_id": str(1000 + i),
            "game_state": "blowout", "game_date": "2026-05-01",
        })
    # clean bucket: ~zero mean residual in normal games
    for i in range(n_clean):
        rows.append({
            "stat": "pts", "pred": 20.0, "actual": 20.0 + (i % 5 - 2) * 0.4,
            "resid": -(i % 5 - 2) * 0.4, "player_id": str(2000 + i),
            "game_state": "normal", "game_date": "2026-05-01",
        })
    return rows


def test_bucket_finds_systematic_bias():
    rows = _synthetic_rows()
    buckets = bucket_residuals(rows, min_n=50)
    by_val = {next(iter(b.dims.values())): b for b in buckets}
    assert "blowout" in by_val and "normal" in by_val
    blow, norm = by_val["blowout"], by_val["normal"]
    # the biased bucket's mean is ~+3, clean bucket ~0
    assert blow.mean_resid > 2.5
    assert abs(norm.mean_resid) < 0.5
    # systematic bias is significant; clean bucket is not flagged systematic
    assert blow.p_value < 0.01
    assert blow.severity() > norm.severity()
    assert blow.n >= 50


def test_min_n_filter_drops_small_buckets():
    rows = _synthetic_rows(n_biased=10, n_clean=10)
    assert bucket_residuals(rows, min_n=50) == []  # both below min_n
    assert len(bucket_residuals(rows, min_n=5)) == 2


def test_mine_emits_hypothesis_for_biased_bucket():
    rows = _synthetic_rows()
    hyps = mine(rows=rows, min_n=50, store=None)
    assert hyps, "expected at least one hypothesis from the biased bucket"
    assert all(isinstance(h, Hypothesis) for h in hyps)
    names = {h.name for h in hyps}
    assert any("blowout" in n for n in names)
    # clean bucket must NOT produce a hypothesis (no systematic bias)
    assert not any("normal" in n for n in names)
    h = next(h for h in hyps if "blowout" in h.name)
    assert h.target == "pts"
    assert h.source == "error_miner"


def test_intel_scan_emits_atlas_signal_when_section_present(tmp_path):
    store = PointInTimeStore(store_dir=tmp_path, autoload=False)
    # the descriptive arm has built an on_off_impact section for one player
    store.write_atlas("player", 1000, "on_off_impact",
                      dt.datetime(2026, 4, 1), {"on_off_net": 5.2},
                      {"source": "test", "n": 30, "confidence": "high"})
    buckets = bucket_residuals(_synthetic_rows(), min_n=50)
    hyps = intel_scan(buckets, store, top_k=10)
    assert hyps, "intel-scan should emit a hypothesis (blowout->on_off_impact present)"
    h = hyps[0]
    assert h.source == "intel_scanner"
    assert "on_off_impact" in h.atlas_fields


def test_intel_scan_skips_when_section_absent(tmp_path):
    store = PointInTimeStore(store_dir=tmp_path, autoload=False)  # empty store
    buckets = bucket_residuals(_synthetic_rows(), min_n=50)
    assert intel_scan(buckets, store, top_k=10) == []


def test_load_residuals_offline_empty(tmp_path):
    # no predictions dir -> graceful empty, never raises
    assert load_residuals(pred_dir=tmp_path / "nope") == []


if __name__ == "__main__":
    test_bucket_finds_systematic_bias()
    test_min_n_filter_drops_small_buckets()
    test_mine_emits_hypothesis_for_biased_bucket()
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_intel_scan_emits_atlas_signal_when_section_present(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_intel_scan_skips_when_section_absent(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_load_residuals_offline_empty(Path(d))
    print("all error_miner tests passed")
