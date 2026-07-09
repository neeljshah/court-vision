"""Per-file tests for nba_checkpoint_benchmark.py -- NBA in-game MODEL-vs-MARKET
checkpoint benchmark. OFFLINE + deterministic: synthetic parquet in tmp_path, no
network, no production data mutation.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_nba_checkpoint_benchmark.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import pytest

import scripts.platformkit.ingame.nba_checkpoint_benchmark as m


def _rows_for_game(gid: int, date: str, n: int, *, home_win: int, start_traded_only: bool = True,
                   trailing_untraded: int = 0) -> List[dict]:
    """One synthetic game: period ramps 1->4, score drifts toward the planted winner."""
    rows = []
    ts0 = 1_700_000_000 + gid * 100_000
    for i in range(n):
        period = 1 + min(3, i // (n // 4 + 1))
        clock = max(0.0, 720.0 - 60.0 * (i % (n // 4 + 1)))
        hs = i if home_win else 0
        as_ = 0 if home_win else i
        margin = hs - as_
        mp = min(0.95, max(0.05, 0.5 + 0.01 * margin))
        rows.append({
            "game_id": gid, "game_date": date, "ts": ts0 + i * 60, "period": period,
            "game_clock_s": clock, "score_home": hs, "score_away": as_, "margin": margin,
            "market_prob": mp, "traded": True,
            "market_ticker": "KXNBAGAME-TEST-%d" % gid, "outcome_home_win": home_win,
        })
    for j in range(trailing_untraded):
        last = dict(rows[-1])
        last.update({"ts": ts0 + (n + j) * 60, "traded": False, "market_prob": 0.5})
        rows.append(last)
    return rows


def _write_parquet(path: Path, n_games: int = 9, rows_per_game: int = 20,
                   trailing_untraded: int = 2) -> None:
    all_rows: List[dict] = []
    for g in range(n_games):
        all_rows += _rows_for_game(1000 + g, "2026-05-%02d" % (1 + g % 28), rows_per_game,
                                   home_win=1 if g % 2 == 0 else 0,
                                   trailing_untraded=trailing_untraded)
    pd.DataFrame(all_rows).to_parquet(path)


# --------------------------------------------------------------------------------------- #
def test_phase_and_margin_bucket() -> None:
    assert m.phase_bucket(1) == "P1-2"
    assert m.phase_bucket(2) == "P1-2"
    assert m.phase_bucket(3) == "P3"
    assert m.phase_bucket(4) == "P4+OT"
    assert m.phase_bucket(6) == "P4+OT"
    assert m.margin_bucket(3) == "close_le4"
    assert m.margin_bucket(-4) == "close_le4"
    assert m.margin_bucket(7) == "mid_5to10"
    assert m.margin_bucket(-10) == "mid_5to10"
    assert m.margin_bucket(15) == "blowout_11plus"


def test_elapsed_minutes_regulation_and_ot() -> None:
    assert m._elapsed_minutes(1, 720.0) == 0.0
    assert m._elapsed_minutes(1, 0.0) == 12.0
    assert m._elapsed_minutes(4, 0.0) == 48.0
    # OT period 5 at tip (300s remaining in a 5-min OT) == 48 elapsed (regulation length).
    assert m._elapsed_minutes(5, 300.0) == 48.0
    assert m._elapsed_minutes(5, 0.0) == 53.0


def test_price_checkpoint_reproduces_p0_at_tip() -> None:
    """Closed-form prior check: at elapsed=0/margin=0 the repriced win_home == p0 exactly."""
    for p0 in (0.2, 0.34, 0.5, 0.66, 0.9):
        got = m.price_checkpoint(p0, 0, 0, period=1, game_clock_s=720.0)
        assert got == pytest.approx(p0, abs=1e-6)


def test_price_checkpoint_leak_free_signature() -> None:
    """price_checkpoint's signature carries no outcome/future field -- it is a pure
    function of (p0, score-as-of-tick, period, clock); identical inputs -> identical
    output regardless of anything else happening in the same game."""
    a = m.price_checkpoint(0.4, 10, 6, period=2, game_clock_s=300.0)
    b = m.price_checkpoint(0.4, 10, 6, period=2, game_clock_s=300.0)
    assert a == b
    import inspect
    assert "outcome" not in inspect.signature(m.price_checkpoint).parameters


def test_load_checkpoints_excludes_untraded(tmp_path: Path) -> None:
    p = tmp_path / "checkpoints.parquet"
    _write_parquet(p, n_games=3, rows_per_game=10, trailing_untraded=4)
    df, counts = m.load_checkpoints(p)
    assert counts["n_rows_total"] == 3 * (10 + 4)
    assert counts["n_rows_traded"] == 3 * 10
    assert (df["traded"] == True).all()  # noqa: E712
    assert counts["n_games"] == 3


def test_load_checkpoints_bucket_assignment(tmp_path: Path) -> None:
    p = tmp_path / "checkpoints.parquet"
    _write_parquet(p, n_games=1, rows_per_game=20, trailing_untraded=0)
    df, _ = m.load_checkpoints(p)
    for _, row in df.iterrows():
        expect = "%s|%s" % (m.phase_bucket(int(row["period"])), m.margin_bucket(row["margin"]))
        assert row["bucket"] == expect


def test_load_checkpoints_pricing_ignores_outcome(tmp_path: Path) -> None:
    """LEAK-FREENESS at the pipeline level: flipping outcome_home_win must not change
    either prior variant's priced model_prob for any row."""
    p_a = tmp_path / "a.parquet"
    p_b = tmp_path / "b.parquet"
    rows = _rows_for_game(2000, "2026-05-01", 15, home_win=1)
    pd.DataFrame(rows).to_parquet(p_a)
    flipped = [dict(r, outcome_home_win=1 - r["outcome_home_win"]) for r in rows]
    pd.DataFrame(flipped).to_parquet(p_b)
    df_a, _ = m.load_checkpoints(p_a)
    df_b, _ = m.load_checkpoints(p_b)
    pd.testing.assert_series_equal(
        df_a["model_prob_neutral_p0_0.5"].reset_index(drop=True),
        df_b["model_prob_neutral_p0_0.5"].reset_index(drop=True))
    pd.testing.assert_series_equal(
        df_a["model_prob_first_traded_pretip"].reset_index(drop=True),
        df_b["model_prob_first_traded_pretip"].reset_index(drop=True))


def test_build_benchmark_insufficient_data_below_min_games(tmp_path: Path) -> None:
    p = tmp_path / "checkpoints.parquet"
    _write_parquet(p, n_games=3, rows_per_game=10, trailing_untraded=0)
    doc = m.build_benchmark(p)
    assert doc["n_games"] == 3
    assert doc["variants"]["neutral_p0_0.5"]["pooled"]["verdict"] == "INSUFFICIENT_DATA"
    assert doc["edge_claimed"] is False


def test_build_benchmark_enough_games_gets_a_real_verdict(tmp_path: Path) -> None:
    p = tmp_path / "checkpoints.parquet"
    _write_parquet(p, n_games=9, rows_per_game=20, trailing_untraded=1)
    doc = m.build_benchmark(p)
    assert doc["n_games"] == 9
    pooled = doc["variants"]["neutral_p0_0.5"]["pooled"]
    assert pooled["verdict"] in ("MATCH", "MODEL_AHEAD", "MODEL_BEHIND")
    assert pooled["n_ticks"] == 9 * 20
    assert doc["n_rows_untraded_excluded"] == 9


def test_write_benchmark_writes_and_dedupes_history(tmp_path: Path) -> None:
    data_path = tmp_path / "checkpoints.parquet"
    _write_parquet(data_path, n_games=3, rows_per_game=8, trailing_untraded=0)
    out_path = tmp_path / "out.json"
    hist_path = tmp_path / "history.jsonl"
    m.write_benchmark(out_path=out_path, data_path=data_path, history_path=hist_path)
    assert out_path.exists()
    n_lines_1 = len(hist_path.read_text(encoding="utf-8").splitlines())
    assert n_lines_1 == len(m.PRIOR_VARIANTS)
    m.write_benchmark(out_path=out_path, data_path=data_path, history_path=hist_path)
    n_lines_2 = len(hist_path.read_text(encoding="utf-8").splitlines())
    assert n_lines_2 == n_lines_1  # stable generated_at -> rerun dedupes, no growth
