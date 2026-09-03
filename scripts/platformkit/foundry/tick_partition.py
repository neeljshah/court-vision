"""S121: the in-game screen/verdict partition at TICK grain.

THE DEFECT (S121, exposed by the S106 real-game split and measured in S119):
`ingame_screen.partition` hands `tiers.partition_corpus` ONE state per ticker, stamped with
the ticker's GAME-FIRST DATE, and `run()` then takes every tick of a screen-side ticker. A
Kalshi ticker parks several nights under one key (S105/S106), so a ticker whose first date is
in the screen ISO week keeps ticking into the verdict week: 495 of the 15,702 S82 screen ticks
are dated 2026-07-06/07-07 = 2026-W28, the VERDICT side. Dropping them halves the S82 leader
(+0.003332 -> +0.001628). The leak runs one way only -- `first_dates` is the ticker's own
first tick date, so a tick can never be EARLIER than its ticker's week; measured on the raw
store, the only cross-week ticks are W26->W27 (188) and W27->W28 (495), zero backwards.

THE MODE. `ticker_week` (the DEFAULT) is the frozen S82/S117 rule and is untouched, so both
archives reproduce byte-identically. `tick_week` assigns each TICK by its own timestamp's ISO
week, with each REAL GAME (S106) coalesced to the week of its first tick so a real game is
never split down the middle, and asserts the two sides are disjoint at tick level and that no
real game contributes to both. Select it with `mode="tick_week"` or the environment variable
FOUNDRY_INGAME_PARTITION=tick_week.

No ledger row, no prereg seal, no charge. Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/foundry/test_tick_partition.py -q
"""
from __future__ import annotations

import os
from typing import Any, Optional, Sequence

import pandas as pd

from scripts.platformkit.eval_gate.real_game_split import assign_real_game_seq, cluster_ids
from scripts.platformkit.foundry.tiers import Partition, partition_corpus

ENV_VAR = "FOUNDRY_INGAME_PARTITION"
MODES = ("ticker_week", "tick_week")
DEFAULT_MODE = "ticker_week"


def partition_mode(mode: Optional[str] = None) -> str:
    """Explicit argument beats the environment beats the frozen default."""
    chosen = mode or os.environ.get(ENV_VAR) or DEFAULT_MODE
    if chosen not in MODES:
        raise ValueError("unknown partition mode %r; expected one of %s" % (chosen, list(MODES)))
    return chosen


def _block_stamps(rows: pd.DataFrame, state_summary: Optional[Sequence[Any]]) -> pd.Series:
    """The stamp each tick is BLOCKED by: its own, or its real game's first (S106)."""
    stamps = pd.to_datetime(rows["ts"].astype(str).str.replace("Z", "", regex=False))
    if state_summary is None:
        return stamps
    frame = pd.DataFrame({"game_id": rows["game"].astype(str).to_numpy(),
                          "ts": rows["ts"].astype(str).to_numpy(),
                          "state_summary": list(state_summary)})
    split, _ = assign_real_game_seq(frame)
    cluster = pd.Series(cluster_ids(split).to_numpy(), index=stamps.index)
    return stamps.groupby(cluster).transform("min")


def tick_partition(rows: pd.DataFrame, *, seed: int = 0,
                   state_summary: Optional[Sequence[Any]] = None) -> Partition:
    """SF-1 sides over TICKS: `partition_corpus`'s own ISO-week rule, one state per tick."""
    stamps = _block_stamps(rows, state_summary)
    states = [{"game_id": str(row_id), "state_ts": stamp.strftime("%Y-%m-%dT%H:%M:%S")}
              for row_id, stamp in zip(rows["row_id"], stamps)]
    return partition_corpus(states, seed=seed)


def screen_side(rows: pd.DataFrame, part: Partition, *, mode: Optional[str] = None,
                state_summary: Optional[Sequence[Any]] = None, seed: int = 0) -> tuple:
    """(screen-side rows, meta). `ticker_week` is the frozen rule; `tick_week` is S121's."""
    chosen = partition_mode(mode)
    if chosen == "ticker_week":
        side = rows[rows["game"].isin(part.screen_ids)].reset_index(drop=True)
        return side, {"mode": chosen, "basis": part.basis, "screen_sha256": part.screen_sha256,
                      "verdict_sha256": part.verdict_sha256, "n_screen_ticks": int(len(side)),
                      "real_game_purged": False}
    tick = tick_partition(rows, seed=seed, state_summary=state_summary)
    ids = rows["row_id"].astype(str)
    on_screen, on_verdict = ids.isin(tick.screen_ids), ids.isin(tick.verdict_ids)
    assert not bool((on_screen & on_verdict).any()), "a tick landed on both partition sides"
    assert bool((on_screen | on_verdict).all()), "a tick landed on neither partition side"
    if state_summary is not None:      # no real game may straddle the screen/verdict boundary
        frame = pd.DataFrame({"game_id": rows["game"].astype(str).to_numpy(),
                              "ts": rows["ts"].astype(str).to_numpy(),
                              "state_summary": list(state_summary)})
        split, _ = assign_real_game_seq(frame)
        sides = pd.DataFrame({"cluster": cluster_ids(split).to_numpy(),
                              "screen": on_screen.to_numpy()}).groupby("cluster")["screen"].nunique()
        straddle = sorted(sides.index[sides > 1])
        assert not straddle, "real games on both partition sides: %s" % straddle[:5]
    side = rows[on_screen.to_numpy()].reset_index(drop=True)
    return side, {"mode": chosen, "basis": tick.basis, "screen_sha256": tick.screen_sha256,
                  "verdict_sha256": tick.verdict_sha256, "n_screen_ticks": int(len(side)),
                  "n_verdict_ticks": int(len(rows) - len(side)),
                  "n_dropped_vs_ticker_week": int(rows["game"].isin(part.screen_ids).sum() - len(side)),
                  "real_game_purged": state_summary is not None}
