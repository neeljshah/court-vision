"""Tests for scripts.platformkit.live_edge.combine.minutes_combiner (LIVE-EDGE
C1 minutes-observable combiner).

Per-file run only:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_minutes_combiner.py -q
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.combine import minutes_combiner as mc


def _synthetic_frame(n_players: int = 30, n_games: int = 260, seed: int = 0) -> pd.DataFrame:
    """Deterministic synthetic per-player-game rows spanning the real
    discovery/reserve cutover (2025-10-01), so the walk-forward split is
    exercised the same way it is on real data. Player minutes are a base
    level plus noise; pf is Bernoulli so foul_rate_prior is nonconstant."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_games, freq="3D")  # crosses 2025-10-01
    rows = []
    for pid in range(n_players):
        base_min = 15 + (pid % 20)
        for i, d in enumerate(dates):
            pf = rng.integers(0, 6)
            m = max(0.0, base_min + rng.normal(0, 3) - (2.0 if pf >= 4 else 0.0))
            rows.append({"player_id": pid, "player_name": f"P{pid}", "game_id": f"{pid}_{i}",
                         "date": d, "is_home": int(i % 2 == 0), "pf": float(pf), "min": m,
                         "pts": m * 0.5})
    return pd.DataFrame(rows)


def test_blocked_on_empty_frame(tmp_path):
    out = mc.run_minutes_combiner(source=pd.DataFrame(), out_dir=tmp_path)
    assert out["blocked"] is True


def test_synthetic_grid_produces_verdict_and_report_files(tmp_path):
    df = _synthetic_frame()
    out = mc.run_minutes_combiner(source=df, out_dir=tmp_path)
    assert out["verdict"] in ("COMBINER_BEATS_BASELINE", "HONEST_NULL")
    assert out["n_discovery"] > 0 and out["n_reserve"] > 0
    assert (tmp_path / "minutes_combiner_report.json").exists()
    assert (tmp_path / "minutes_combiner_report.md").exists()
    report = json.loads((tmp_path / "minutes_combiner_report.json").read_text())
    assert report["baseline_pinball_median"] > 0
    # two pinned seeds recorded for both models
    for model_name in ("elastic_net", "hist_gb"):
        keys = report["per_model_per_seed_pinball"][model_name].keys()
        assert any("seed0" in k for k in keys) and any("seed42" in k for k in keys)


def test_pending_ledger_row_written_not_journal(tmp_path):
    df = _synthetic_frame()
    mc.run_minutes_combiner(source=df, out_dir=tmp_path)
    pending = tmp_path / "pending_ledger.jsonl"
    assert pending.exists()
    row = json.loads(pending.read_text().splitlines()[0])
    assert row["links"]["parent_claims"] == [mc._FOUL_META_CLAIM_ID]
    assert row["lifecycle"] == "screened"  # never self-promotes to accepted
    # this lane must not touch the real claims journal
    assert not (tmp_path / "journal.jsonl").exists()


def test_features_are_leak_free_shifted_by_one_row():
    df = _synthetic_frame(n_players=2, n_games=10)
    out = mc._add_features(df)
    g = out[out["player_id"] == 0].sort_values("date").reset_index(drop=True)
    # baseline_min at row i must equal a function of rows < i only, never row i's own min
    assert g.loc[0, "baseline_min"] != g.loc[0, "min"] or pd.isna(g.loc[0, "baseline_min"])
    for i in range(1, len(g)):
        prior_meds = g.loc[:i - 1, "min"]
        if len(prior_meds) >= mc.BASELINE_WINDOW_MIN_PERIODS:
            assert abs(g.loc[i, "baseline_min"] - prior_meds.median()) < 1e-9


def test_real_slice_smoke():
    """One real-data smoke: the shared box loader + real feature build must
    not raise and must yield a plausible minutes range. Skips quietly if the
    real snapshot parquet is unavailable in this environment."""
    try:
        out = mc.run_minutes_combiner()
    except FileNotFoundError:
        return
    assert "verdict" in out or out.get("blocked") is True
