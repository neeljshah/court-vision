"""Per-file pytest for quality_validity_gate.py / quality_validity_stats.py.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_quality_validity_gate.py -q

NEVER run the full suite (freezes the box).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.quality_validity_gate import (
    CUTOFFS_2024_25,
    FORWARD_DAYS,
    MIN_FORWARD_GAMES,
    MIN_PLAYERS_PER_CUTOFF,
    QUALIFY_MIN_FGA,
    QUALIFY_MIN_GAMES,
    _agg_pre_t,
    rank_at_cutoff,
    run_gate,
)
from domains.basketball_nba.quality_validity_stats import (
    paired_bootstrap_delta,
    spearman,
    top_decile_diagnostic,
)


def test_gate_pre_registered_cutoffs_and_floors_frozen():
    """These are pre-registered per the spec -- changing them post-hoc would
    be exactly the narrative-fitting the spec bans."""
    assert CUTOFFS_2024_25 == ["2024-12-01", "2025-01-01", "2025-02-01", "2025-03-01"]
    assert FORWARD_DAYS == 30
    assert MIN_FORWARD_GAMES == 8
    assert MIN_PLAYERS_PER_CUTOFF == 100
    assert QUALIFY_MIN_GAMES == 20
    assert QUALIFY_MIN_FGA == 200


def test_spearman_perfect_and_zero_correlation():
    x = pd.Series([1, 2, 3, 4, 5])
    y_perfect = pd.Series([10, 20, 30, 40, 50])
    y_inverse = pd.Series([50, 40, 30, 20, 10])
    assert spearman(x, y_perfect) == pytest.approx(1.0)
    assert spearman(x, y_inverse) == pytest.approx(-1.0)


def test_top_decile_diagnostic_shape():
    table = pd.DataFrame({
        "shooter_pctile": np.linspace(0, 1, 20),
        "realized_ts_pct": np.linspace(0.4, 0.7, 20),
    })
    diag = top_decile_diagnostic(table, "shooter_pctile")
    assert diag["n_top_decile"] == 2  # 20 // 10
    # top decile (highest pctile) should have the highest realized TS in this
    # perfectly-correlated synthetic table
    assert diag["top_decile_mean_realized_ts"] > diag["field_mean_realized_ts"]


def test_paired_bootstrap_delta_ci_excludes_zero_for_strong_synthetic_signal():
    """If shooter_pctile is a much better predictor of realized_ts_pct than
    naive_pctile in synthetic data, the bootstrap CI should exclude 0 in favor
    -- sanity-checks the bootstrap machinery itself, independent of real NBA data."""
    rng = np.random.default_rng(42)
    n = 150
    truth = rng.uniform(0, 1, n)
    tables = []
    for _ in range(4):
        noise_shooter = rng.normal(0, 0.05, n)
        noise_naive = rng.normal(0, 0.5, n)
        tables.append(pd.DataFrame({
            "player_id": np.arange(n),
            "shooter_pctile": np.clip(truth + noise_shooter, 0, 1),
            "naive_pctile": np.clip(truth + noise_naive, 0, 1),
            "realized_ts_pct": truth,
        }))
    result = paired_bootstrap_delta(tables, n_boot=300, seed=1)
    assert result["ci_lo"] > 0  # shooter (near-truth) beats naive (noisy) with CI excluding 0
    assert result["n_boot_effective"] > 250


def test_paired_bootstrap_delta_ci_includes_zero_for_null_signal():
    """When both rankings are equally (un)informative, the CI should include 0
    -- verifies the bootstrap does not manufacture a spurious win."""
    rng = np.random.default_rng(7)
    n = 150
    truth = rng.uniform(0, 1, n)
    tables = []
    for _ in range(4):
        noise = rng.normal(0, 0.3, n)
        tables.append(pd.DataFrame({
            "player_id": np.arange(n),
            "shooter_pctile": np.clip(truth + rng.normal(0, 0.3, n), 0, 1),
            "naive_pctile": np.clip(truth + rng.normal(0, 0.3, n), 0, 1),
            "realized_ts_pct": truth,
        }))
    result = paired_bootstrap_delta(tables, n_boot=300, seed=2)
    assert result["ci_lo"] < 0 < result["ci_hi"]


def test_rank_at_cutoff_is_leak_free_no_future_rows_used():
    """Construct a synthetic boxscore where a player's pre-T stats and
    post-T stats are wildly different; confirm the pre-T ranking uses ONLY
    pre-T rows (the leak-free invariant)."""
    dates_pre = pd.date_range("2024-10-22", periods=25, freq="D")
    dates_post = pd.date_range("2024-12-05", periods=10, freq="D")
    rows = []
    pid_counter = 1
    # build enough players to clear the >=100-qualifying floor with realistic stat lines
    for p in range(120):
        pid = pid_counter
        pid_counter += 1
        for i, d in enumerate(dates_pre):
            rows.append({
                "game_id": f"pre_{p}_{i}", "date": d, "season": "2024-25",
                "player_id": pid, "player_name": f"Player{p}",
                "fgm": 5, "fga": 10, "fg3m": 1, "fg3a": 3, "ftm": 2, "fta": 2, "pts": 13,
            })
        for i, d in enumerate(dates_post):
            rows.append({
                "game_id": f"post_{p}_{i}", "date": d, "season": "2024-25",
                "player_id": pid, "player_name": f"Player{p}",
                "fgm": 0, "fga": 20, "fg3m": 0, "fg3a": 10, "ftm": 0, "fta": 0, "pts": 0,
            })
    box = pd.DataFrame(rows)
    r = rank_at_cutoff(box, "2024-12-01")
    # if the ranking leaked post-T rows, naive_comp/ts_pct would collapse toward 0
    # for every player (since post-T rows are all 0-pt efficiency disasters);
    # leak-free pre-T aggregation must show the pre-T efficiency instead.
    if r is not None:
        table = r["table"]
        assert (table["naive_comp"] > 0.3).all()


def test_agg_pre_t_dedupes_duplicate_player_id_different_name_spelling():
    """Root-cause regression test (2026-07-18 crash): player_boxscores.parquet
    carries inconsistent name-string spellings for the SAME player_id across
    dates (e.g. "Nikola Jokic" vs the diacritic spelling -- 18 player_ids
    verified live). _agg_pre_t used to group by player_id+player_name, which
    silently split one player's pre-T games/FGA across two rows; once merged
    with the (player_id-only) forward table and set_index("player_id") in
    rank_at_cutoff, that produced a duplicate index label -- the direct cause
    of percentile_rank's ValueError('cannot reindex on an axis with duplicate
    labels'). Must collapse to exactly one row per player_id."""
    rows = pd.DataFrame({
        "game_id": [1, 2, 3],
        "date": pd.to_datetime(["2024-11-01", "2024-11-05", "2024-11-10"]),
        "player_id": [203999, 203999, 203999],
        "player_name": ["Nikola Jokic", "Nikola Jokic", "Nikola Jokic-diacritic"],
        "fgm": [10, 8, 9], "fga": [15, 14, 13], "fg3m": [1, 1, 2], "fg3a": [3, 2, 4],
        "ftm": [4, 3, 5], "fta": [5, 4, 6], "pts": [25, 20, 25],
    })
    agg = _agg_pre_t(rows)
    assert len(agg) == 1
    row = agg.iloc[0]
    assert row["player_id"] == 203999
    assert row["games"] == 3
    assert row["fga"] == 15 + 14 + 13


def test_rank_at_cutoff_dedupes_duplicate_player_id_no_crash():
    """End-to-end regression for the exact reported crash: a player_id whose
    pre-T boxscore rows carry two independently-qualifying name spellings
    (mirrors the real Nikola Jokic 203999 case, where both the ASCII and
    diacritic spellings individually clear the >=20-games/>=200-FGA floor)
    used to survive into `qual` as two rows, and after the merge + set_index
    ("player_id") in rank_at_cutoff left a duplicate index label that crashed
    percentile_rank. Confirms the _agg_pre_t fix collapses both spellings to
    one row before that indexing ever happens, exercised through the real
    rank_at_cutoff merge/percentile path (not just the helper in isolation)."""
    dup_dates = pd.date_range("2024-09-01", periods=50, freq="D")
    other_dates_pre = pd.date_range("2024-10-22", periods=25, freq="D")
    dates_post = pd.date_range("2024-12-05", periods=10, freq="D")
    dup_pid = 999999
    rows = []
    for i, d in enumerate(dup_dates):
        name = "Nikola Jokic" if i < 25 else "Nikola Jokic-diacritic"
        rows.append({
            "game_id": f"dup_{i}", "date": d, "season": "2024-25",
            "player_id": dup_pid, "player_name": name,
            "fgm": 5, "fga": 10, "fg3m": 1, "fg3a": 3, "ftm": 2, "fta": 2, "pts": 13,
        })
    for i, d in enumerate(dates_post):
        rows.append({
            "game_id": f"dup_post_{i}", "date": d, "season": "2024-25",
            "player_id": dup_pid, "player_name": "Nikola Jokic-diacritic",
            "fgm": 5, "fga": 10, "fg3m": 1, "fg3a": 3, "ftm": 2, "fta": 2, "pts": 13,
        })
    for p in range(120):
        pid = p + 1
        for i, d in enumerate(other_dates_pre):
            rows.append({
                "game_id": f"pre_{p}_{i}", "date": d, "season": "2024-25",
                "player_id": pid, "player_name": f"Player{p}",
                "fgm": 5, "fga": 10, "fg3m": 1, "fg3a": 3, "ftm": 2, "fta": 2, "pts": 13,
            })
        for i, d in enumerate(dates_post):
            rows.append({
                "game_id": f"post_{p}_{i}", "date": d, "season": "2024-25",
                "player_id": pid, "player_name": f"Player{p}",
                "fgm": 5, "fga": 10, "fg3m": 1, "fg3a": 3, "ftm": 2, "fta": 2, "pts": 13,
            })
    box = pd.DataFrame(rows)
    r = rank_at_cutoff(box, "2024-12-01")  # must not raise ValueError
    assert r is not None
    table = r["table"]
    assert (table["player_id"] == dup_pid).sum() <= 1


def test_run_gate_returns_honest_reject_or_ship_never_raises():
    """Smoke test against real on-disk data: the gate must terminate with one
    of the two pre-registered verdicts (never silently succeed/crash)."""
    gate = run_gate()
    assert gate.verdict in ("SHIP_RICHER_INDEX", "REJECT_NAIVE_STAYS_CANONICAL")
    assert gate.n_folds >= 1  # at least one of the 4 monthly cutoffs must clear the floor
    assert not np.isnan(gate.mean_rho_shooter)
    assert not np.isnan(gate.mean_rho_naive)


def test_honest_null_clause_binding_naive_wins_or_ci_includes_zero_rejects():
    """Binding per spec: SHIP only if CI excludes 0 in favor AND sign holds
    >=3/4 folds AND replicates. Verify the verdict logic actually enforces
    this (not a softer rule) using the real gate result."""
    gate = run_gate()
    if gate.verdict == "SHIP_RICHER_INDEX":
        assert gate.bootstrap and gate.bootstrap["ci_lo"] > 0
        assert gate.sign_holds_folds >= 3
        assert gate.replication and gate.replication.get("delta", -1) > 0
    else:
        assert gate.verdict == "REJECT_NAIVE_STAYS_CANONICAL"
