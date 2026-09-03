"""S119: the supply probe's stop rule, and the corrected-cluster re-quote.

Run: python -m pytest tests/platformkit/foundry/test_ingame_supply_mlb.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.foundry import ingame_supply_mlb as S

LEDGER = S.ROOT / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"
_SUM = "home_score={h} away_score={a} inning={i}"


def _ticks() -> pd.DataFrame:
    """One game_id holding TWO real games: inning 1..4 on day 1, inning 1..4 on day 2."""
    rows = []
    for day in (5, 6):
        for inning in range(1, 5):
            rows.append({"game_id": "T", "ts": "2026-07-0%dT0%d:00:00Z" % (day, inning),
                         "state_summary": _SUM.format(h=inning - 1, a=0, i=inning),
                         "mlb_pitcher_id": None, "mlb_batter_id": None})
    return pd.DataFrame(rows)


def _series(ticks: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """An archived S82-shaped differential: the candidate helps in segment 1, hurts in 2."""
    rng = np.random.default_rng(seed)
    rows = []
    for i, (_, tick) in enumerate(ticks.iterrows()):
        helped = i < len(ticks) // 2
        rows.append({"feature": "f", "tick_index": i, "game": tick["game_id"],
                     "timestamp": tick["ts"], "y": float(i % 2),
                     "p_e4": 0.5, "p_null": 0.5,
                     "p_candidate": 0.5 + (0.1 if helped else -0.1) * (1 if i % 2 else -1),
                     "market": 0.5 + rng.normal(0, 0.01), "x": float(i)})
    return pd.DataFrame(rows)


def test_real_game_map_splits_one_ticker_into_two_real_games():
    mapping = S.real_game_map(_ticks())
    summary = mapping.pop("_summary")
    assert summary["n_game_ids"] == 1 and summary["n_real_games"] == 2, summary
    assert mapping[("T", "2026-07-05T01:00:00Z")] == 1
    assert mapping[("T", "2026-07-06T01:00:00Z")] == 2


def test_requote_keeps_the_point_estimate_and_only_moves_the_interval():
    ticks = _ticks()
    mapping = S.real_game_map(ticks)
    mapping.pop("_summary")
    series = _series(ticks)
    rows = S.requote(series, mapping)
    assert len(rows) == 1
    row = rows[0]
    y = series["y"].to_numpy(float)
    expected = float((((series["p_null"] - y) ** 2) - ((series["p_candidate"] - y) ** 2)).mean())
    assert row["improvement_vs_null"] == pytest.approx(expected, abs=1e-12)
    assert row["n_game_ids"] == 1 and row["n_real_games"] == 2
    # one game_id cannot carry a clustered interval; two real games can.
    assert row["by_game_id"]["ci95"] is None and row["by_game_id"]["n_clusters"] == 1
    assert row["by_real_game"]["ci95"] is not None
    lo, hi = row["by_real_game"]["ci95"]
    assert row["by_real_game"]["half_width"] == pytest.approx((hi - lo) / 2.0, abs=1e-12)
    assert row["bar"] == 0.004, "the in-game bar was moved"
    assert "tick_informative" in row and row["tick_informative"]["n"] == len(series)


def test_requote_refuses_an_archived_tick_the_store_does_not_carry():
    ticks = _ticks()
    mapping = S.real_game_map(ticks)
    mapping.pop("_summary")
    series = _series(ticks)
    series.loc[0, "timestamp"] = "2099-01-01T00:00:00Z"
    with pytest.raises(AssertionError):
        S.requote(series, mapping)


def test_supply_probe_stop_rule_and_no_ledger_contact():
    before = LEDGER.read_bytes() if LEDGER.exists() else b""
    probe = S.supply_probe(_ticks())
    assert probe["n_suppliable"] < probe["min_members_to_build"]
    assert probe["verdict"].startswith("STOP AFTER PREMISE")
    assert sum(1 for m in probe["members"].values() if m["suppliable_on_screen_side"]) == 1
    for member in probe["members"].values():          # every refusal names its own reason
        assert member["why"] and member["source"]
    source = (S.ROOT / "scripts" / "platformkit" / "foundry" / "ingame_supply_mlb.py").read_text("ascii")
    for banned in ("_charge_ledger", "backtest_runner", "backtest_fwer", "charge_tier",
                   "prereg_sha256", "PREREG"):
        assert banned not in source, banned
    assert (LEDGER.read_bytes() if LEDGER.exists() else b"") == before
