"""Per-file tests for the NBA GRU seq model: leak-free date split, padding/masking,
monotone-time + as-of (leak-free) feature construction. CPU-only, synthetic, tiny."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import nba_gru_dataset as ds  # noqa: E402


def test_split_is_leak_free_by_date():
    df = pd.DataFrame({
        "game_id": ["A", "A", "B", "B", "CK", "CK"],
        "date": pd.to_datetime(["2025-01-01", "2025-01-01", "2026-04-01",
                                 "2026-04-01", "2026-02-01", "2026-02-01"]),
    })
    train, val = ds.split_states(df, drop_ids={"CK"}, cutoff="2026-03-01")
    assert set(train["game_id"]) == {"A"}, "train must be pre-cutoff, checkpoint dropped"
    assert set(val["game_id"]) == {"B"}, "val must be post-cutoff, checkpoint dropped"
    assert "CK" not in set(train["game_id"]) | set(val["game_id"]), "checkpoint leaked"
    assert set(train["game_id"]).isdisjoint(set(val["game_id"]))


def test_elapsed_monotone_and_ot():
    # period 1->4 with clock winding down should give strictly increasing elapsed
    period = np.array([1, 1, 2, 3, 4, 4])
    clock = np.array([720., 60., 360., 200., 400., 0.])
    e = ds._elapsed_from_period_clock(period, clock)
    assert np.all(np.diff(e) > 0), f"elapsed not monotone: {e}"
    # OT (period 5) must exceed end of regulation
    e_ot = ds._elapsed_from_period_clock(np.array([5]), np.array([120.]))
    assert e_ot[0] > ds.REG_SECONDS, "OT elapsed must exceed regulation"


def test_run_feature_is_asof_and_leakfree():
    g = pd.DataFrame({
        "game_id": ["G"] * 4,
        "elapsed": [60., 120., 300., 480.],
        "margin": [2., 4., 10., 10.],
    })
    out = ds._add_run_feature(g).sort_values("elapsed").reset_index(drop=True)
    run = out["margin_run_180"].tolist()
    # e=60 -> ref before start (0) -> 2 ; e=120 -> ref before start -> 4
    # e=300 -> ref as-of 120 (=4) -> 6 ; e=480 -> ref as-of 300 (=10) -> 0
    assert run == [2., 4., 6., 0.], f"as-of run wrong: {run}"
    # leak check: run at row i must not depend on any FUTURE margin
    g2 = g.copy(); g2.loc[3, "margin"] = 999.
    run2 = ds._add_run_feature(g2).sort_values("elapsed")["margin_run_180"].tolist()
    assert run2[:3] == run[:3], "future margin changed a past run value -> LEAK"


def test_to_sequences_shapes_and_norm():
    df = pd.DataFrame({
        "game_id": ["G", "G", "G"],
        "elapsed": [60., 180., 300.],
        "margin": [15., 30., -15.],
        "period": [1, 1, 2],
        "home_win": [1, 1, 1],
        "frac_elapsed": [0.02, 0.06, 0.1],
        "margin_run_180": [15., 0., 0.],
    })
    seqs = ds.to_sequences(df)
    gid, feat, label, meta = seqs[0]
    assert feat.shape == (3, 4) and label == 1.0
    # normalization: margin 15 / 15 == 1.0 in first column
    assert abs(feat[0, 0] - 1.0) < 1e-6, "margin normalization off"
    assert feat.dtype == np.float32


def test_pad_batch_masks_padding():
    try:
        import torch
    except Exception:
        print("torch missing -> skip pad test (BLOCKED-lane behavior is fine)")
        return
    from nba_gru_winprob import pad_batch
    a = np.ones((2, 4), dtype=np.float32)
    b = np.ones((5, 4), dtype=np.float32) * 2
    x, y, mask = pad_batch([(a, 1.0), (b, 0.0)], torch)
    assert x.shape == (2, 5, 4)
    assert mask[0].tolist() == [1, 1, 0, 0, 0], "short seq not masked correctly"
    assert mask[1].tolist() == [1, 1, 1, 1, 1]
    # padded region of x is zero
    assert float(x[0, 2:].abs().sum()) == 0.0, "padding not zeroed"


if __name__ == "__main__":
    for fn in [test_split_is_leak_free_by_date, test_elapsed_monotone_and_ot,
               test_run_feature_is_asof_and_leakfree, test_to_sequences_shapes_and_norm,
               test_pad_batch_masks_padding]:
        fn(); print(f"PASS {fn.__name__}")
    print("ALL PASS")
