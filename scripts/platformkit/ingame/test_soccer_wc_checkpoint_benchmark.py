"""Per-file tests for soccer_wc_checkpoint_benchmark.py -- soccer_intl WC in-game
MODEL-vs-MARKET checkpoint benchmark. OFFLINE + deterministic: synthetic parquets in
tmp_path, no network, no production data mutation.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_soccer_wc_checkpoint_benchmark.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import pytest

import scripts.platformkit.ingame.soccer_wc_checkpoint_benchmark as m


def _base_results_rows() -> List[dict]:
    """Prior (pre-2026) matches so Alpha/Beta have a non-degenerate asof strength state."""
    rows = []
    for i in range(20):
        rows.append({"date": "2024-01-%02d" % (1 + i % 28), "home_team": "Alpha",
                     "away_team": "Gamma", "home_score": 2, "away_score": 0,
                     "tournament": "Friendly", "neutral": "TRUE"})
        rows.append({"date": "2024-02-%02d" % (1 + i % 28), "home_team": "Beta",
                     "away_team": "Gamma", "home_score": 1, "away_score": 1,
                     "tournament": "Friendly", "neutral": "TRUE"})
    return rows


def _checkpoint_rows(gid: str, date: str, n: int, home_win: bool) -> List[dict]:
    rows = []
    for i in range(n):
        hs = 1 if (home_win and i >= n // 2) else 0
        as_ = 0 if home_win else (1 if i >= n // 2 else 0)
        rows.append({
            "game_id": gid, "game_date": date, "home_team": "Alpha", "away_team": "Beta",
            "ts": 1_800_000_000 + i * 60, "minute": float(i * 4), "score_home": hs,
            "score_away": as_, "margin": hs - as_,
            "market_ticker": "KXWCGAME-TEST-%s-ALP" % gid,
            "market_prob": min(0.95, max(0.05, 0.5 + 0.05 * (hs - as_))),
            "tie_prob": 0.2, "traded": True,
            "outcome": "home_win" if home_win else "away_win",
        })
    return rows


def _write(tmp_path: Path, n_games: int = 9, rows_per_game: int = 10,
          extra_results: List[dict] = None) -> tuple[Path, Path]:
    ck_rows: List[dict] = []
    for g in range(n_games):
        ck_rows += _checkpoint_rows("g%d" % g, "2026-06-%02d" % (11 + g % 15),
                                    rows_per_game, home_win=(g % 2 == 0))
    ck_path = tmp_path / "checkpoints.parquet"
    pd.DataFrame(ck_rows).to_parquet(ck_path)

    res_rows = _base_results_rows() + (extra_results or [])
    res_path = tmp_path / "results.parquet"
    pd.DataFrame(res_rows).to_parquet(res_path)
    return ck_path, res_path


# --------------------------------------------------------------------------------------- #
def test_phase_and_margin_bucket() -> None:
    assert m.phase_bucket(0) == "early_0to30"
    assert m.phase_bucket(29.9) == "early_0to30"
    assert m.phase_bucket(30) == "mid_30to70"
    assert m.phase_bucket(69.9) == "mid_30to70"
    assert m.phase_bucket(70) == "late_70plus"
    assert m.phase_bucket(120) == "late_70plus"
    assert m.margin_bucket(1) == "leading"
    assert m.margin_bucket(-1) == "trailing"
    assert m.margin_bucket(0) == "tied"


def test_resolve_alias() -> None:
    assert m.resolve_alias("Czechia") == "Czech Republic"
    assert m.resolve_alias("Congo DR") == "DR Congo"
    assert m.resolve_alias("Unmapped Team") == "Unmapped Team"


def test_asof_ignores_future_results_static_does_not(tmp_path: Path) -> None:
    """Core leak-free proof: a match AFTER the target game_date must not move the asof
    reading, but DOES move the static (no-cutoff) reading -- reproducing the audited leak."""
    ck_path, res_path_a = _write(tmp_path, n_games=1, rows_per_game=6)
    future_blowout = [{"date": "2026-06-25", "home_team": "Alpha", "away_team": "Beta",
                       "home_score": 9, "away_score": 0, "tournament": "FIFA World Cup",
                       "neutral": "TRUE"}]
    res_path_b = tmp_path / "results_with_future.parquet"
    pd.DataFrame(_base_results_rows() + future_blowout).to_parquet(res_path_b)

    df_a, _ = m.load_checkpoints(ck_path, res_path_a)
    df_b, _ = m.load_checkpoints(ck_path, res_path_b)

    pd.testing.assert_series_equal(
        df_a["model_prob_asof_leakfree"].reset_index(drop=True),
        df_b["model_prob_asof_leakfree"].reset_index(drop=True))
    assert not df_a["model_prob_static_in_sample"].reset_index(drop=True).equals(
        df_b["model_prob_static_in_sample"].reset_index(drop=True))


def test_load_checkpoints_excludes_untraded_and_unresolved(tmp_path: Path) -> None:
    ck_path, res_path = _write(tmp_path, n_games=2, rows_per_game=5)
    raw = pd.read_parquet(ck_path)
    raw.loc[0, "traded"] = False
    raw.loc[1, "home_team"] = "Nonexistent Team"
    raw.to_parquet(ck_path)

    df, counts = m.load_checkpoints(ck_path, res_path)
    assert counts["n_rows_total"] == 10
    assert counts["n_rows_traded"] == 9
    assert counts["n_rows_team_unresolved"] == 1
    assert len(df) == 8


def test_build_benchmark_insufficient_data_below_min_games(tmp_path: Path) -> None:
    ck_path, res_path = _write(tmp_path, n_games=3, rows_per_game=5)
    doc = m.build_benchmark(ck_path, res_path)
    assert doc["n_games"] == 3
    assert doc["asof_leakfree"]["pooled"]["verdict"] == "INSUFFICIENT_DATA"
    assert doc["edge_claimed"] is False


def test_build_benchmark_enough_games_gets_a_real_verdict(tmp_path: Path) -> None:
    ck_path, res_path = _write(tmp_path, n_games=9, rows_per_game=8)
    doc = m.build_benchmark(ck_path, res_path)
    assert doc["n_games"] == 9
    pooled = doc["asof_leakfree"]["pooled"]
    assert pooled["verdict"] in ("MATCH", "MODEL_AHEAD", "MODEL_BEHIND")
    assert pooled["n_ticks"] == 9 * 8
    assert "static_in_sample_reference" in doc


def test_write_benchmark_writes_and_dedupes_history(tmp_path: Path) -> None:
    ck_path, res_path = _write(tmp_path, n_games=3, rows_per_game=4)
    out_path = tmp_path / "out.json"
    hist_path = tmp_path / "history.jsonl"
    m.write_benchmark(out_path=out_path, data_path=ck_path, results_path=res_path,
                      history_path=hist_path)
    assert out_path.exists()
    n_lines_1 = len(hist_path.read_text(encoding="utf-8").splitlines())
    assert n_lines_1 == 1
    m.write_benchmark(out_path=out_path, data_path=ck_path, results_path=res_path,
                      history_path=hist_path)
    n_lines_2 = len(hist_path.read_text(encoding="utf-8").splitlines())
    assert n_lines_2 == n_lines_1  # stable generated_at -> rerun dedupes, no growth
