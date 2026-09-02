"""S102 -- the frozen NBA in-game grammar: count, dedupe, and tick-time invariance.

Run ONLY this file: python -m pytest tests/platformkit/foundry/test_ingame_grammar_nba.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.foundry import ingame_grammar_nba as G
from scripts.platformkit.foundry.grammar import semantic_hash
from scripts.platformkit.foundry.ingame_screen import TickTimeLeak, assert_tick_asof

S86_CSV = Path("data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv")
PROBES = 8


def synthetic(n_games: int = 6, n_ticks: int = 40) -> pd.DataFrame:
    """Deterministic multi-game tick frame with the columns the grammar requires."""
    rng = np.random.default_rng(20260903)
    frames = []
    for game in range(n_games):
        home = np.cumsum(rng.integers(0, 4, n_ticks)).astype(float)
        away = np.cumsum(rng.integers(0, 4, n_ticks)).astype(float)
        elapsed = np.linspace(0.5, 47.5, n_ticks)
        frames.append(pd.DataFrame({
            "game": "g%d" % game, "ts": 1_700_000_000 + game * 100_000 + np.arange(n_ticks) * 60.0,
            "period": np.clip((elapsed // 12 + 1).astype(int), 1, 4),
            "score_home": home, "score_away": away, "margin": home - away,
            "elapsed": elapsed, "rem": 48.0 - elapsed}))
    return pd.concat(frames, ignore_index=True).sort_values(
        ["ts", "game"], kind="stable").reset_index(drop=True)


def real_slice(n_games: int = 24) -> pd.DataFrame:
    if not S86_CSV.exists():
        pytest.skip("the S86 screen archive is local-only and absent here")
    frame = pd.read_csv(S86_CSV, usecols=["game_id", "ts", "period", "score_home",
                                          "score_away", "margin", "elapsed", "rem"])
    keep = sorted(frame["game_id"].unique())[:n_games]
    frame = frame[frame["game_id"].isin(keep)].rename(columns={"game_id": "game"})
    frame["game"] = frame["game"].astype(str)
    return frame.sort_values(["ts", "game"], kind="stable").reset_index(drop=True)


def test_the_grid_enumerates_576_hypotheses_and_dedupes_by_semantic_hash():
    """16 base x 6 transforms x 6 conditionings, every one a distinct semantic hash."""
    hypotheses = G.enumerate_hypotheses()
    assert len(G.BASE) == 16 and len(G.TRANSFORMS) == 6 and len(G.PHASES) == 5
    assert len(hypotheses) == 16 * 6 * 6 == 576
    hashes = [semantic_hash(h) for h in hypotheses]
    assert len(set(hashes)) == len(hashes), "the grammar enumerated a duplicate form"
    assert len({G.hypothesis_label(h) for h in hypotheses}) == len(hypotheses)
    assert all(h.horizon == "live_tick" and h.market == "inplay" for h in hypotheses)
    assert all(h.family == G.FAMILY for h in hypotheses)
    assert G.grid_summary()["n_hypotheses"] == 576
    # every hypothesis reads a column the grid actually builds
    columns = set(G.build_grid(synthetic()).columns)
    assert len(columns) == 96
    assert {G.hypothesis_column(h) for h in hypotheses} == columns


def test_every_base_column_is_tick_time_causal_on_the_real_corpus():
    """Truncation invariance at 8 EVENLY spaced probes (A3: never a head slice)."""
    src = real_slice()
    probes = assert_tick_asof(src, G.build_grid, probes=PROBES)
    assert len(probes) == PROBES
    step = max(1, len(src) // (PROBES + 1))
    assert probes == [step * i for i in range(1, PROBES + 1)]
    assert probes[-1] > len(src) // 2, "the probes must reach past the middle of the corpus"


def test_a_planted_future_read_is_caught_by_the_same_guard():
    """The guard is enforcement, not decoration: a next-tick peek must raise."""
    src = synthetic()

    def leaky(frame: pd.DataFrame) -> pd.DataFrame:
        out = G.build_grid(frame)
        out["margin|raw"] = frame.groupby("game")["margin"].shift(-1).to_numpy()
        return out

    with pytest.raises(TickTimeLeak):
        assert_tick_asof(src, leaky, probes=4)


def test_run_length_lead_changes_and_time_decay_read_only_the_past():
    """Hand-checked values on one game, so the scan is not trusted on its own say-so."""
    frame = pd.DataFrame({
        "game": ["g"] * 6, "ts": [0.0, 60.0, 120.0, 180.0, 240.0, 300.0],
        "period": [1, 1, 1, 1, 1, 1],
        "score_home": [0.0, 2.0, 4.0, 6.0, 6.0, 6.0],
        "score_away": [0.0, 0.0, 0.0, 0.0, 5.0, 10.0],
        "margin": [0.0, 2.0, 4.0, 6.0, 1.0, -4.0],
        "elapsed": [0.5, 1.0, 2.0, 3.0, 4.0, 5.0], "rem": [47.5, 47.0, 46.0, 45.0, 44.0, 43.0]})
    state = G.build_state(frame)
    assert list(state["margin"]) == [0.0, 2.0, 4.0, 6.0, 1.0, -4.0]
    # three rises then two falls; the run resets sign, it does not keep counting
    assert list(state["run_len_signed"]) == [0.0, 1.0, 2.0, 3.0, -1.0, -2.0]
    # the lead flips exactly once, on the last tick
    assert list(state["lead_changes"]) == [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    # a 60 s halflife tracks the margin closely; a 600 s halflife lags behind it
    assert state["tdm_h60"].iloc[3] > state["tdm_h600"].iloc[3]
    assert np.isnan(state["pace_ratio_p1"]).all(), "period-1 ticks have no earlier P1 pace"
    assert state.index.equals(frame.index)


def test_phase_conditioning_masks_only_its_own_phase_and_folds_overtime_into_five():
    src = synthetic()
    src.loc[src.index[-5:], "period"] = 5
    values = G.build_grid(src)["margin|raw"]
    for phase in G.PHASES:
        masked = G.conditioned(values, src["period"], phase)
        expected = (src["period"] >= 5) if phase == "5" else (src["period"] == int(phase))
        assert masked.notna().equals(values.notna() & expected)
    assert G.conditioned(values, src["period"], "5").notna().sum() == 5
