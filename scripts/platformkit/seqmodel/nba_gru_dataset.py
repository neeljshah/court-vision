"""Dataset builder for the NBA in-game GRU win-prob sequence model (GOAL 5).

LEAK-FREE DESIGN (declared before any training -- see nba_gru_winprob.py docstring
for the full experiment preregistration; this module only builds the tensors):

Sources
-------
- data/cache/ingame/pbp_states_2024_25.parquet, pbp_states_2025_26.parquet
  (game-clock candles at 120s TOTAL-game spacing; ~1,470 games across 2 seasons).
- data/cache/inplay_odds/nba_checkpoints_2025_26_playoffs.parquet
  (53 playoff games; ~60s WITHIN-period candles; market_prob = P(home win); OT to P6).

Parity landmines handled here
-----------------------------
1. 44/53 checkpoint game_ids ALSO appear in the 2025-26 states corpus -> HARD LEAK.
   All 53 checkpoint ids are dropped from train/val (exclude by id AND by date band).
2. states use TOTAL-game clock; checkpoints use WITHIN-period clock + OT. Both are
   mapped to a single monotone `elapsed` seconds axis (0..2880 reg, >2880 OT).
3. `n_plays_seen` exists in states but NOT in checkpoints -> EXCLUDED (a feature must
   be computable in BOTH builders or it silently reads 0 at inference).
4. candle spacing differs (120s train vs 60s test) -> the only sequential feature,
   margin_run_180, is defined over a FIXED 180s of game-time via as-of lookup, so it
   has identical semantics regardless of candle density. No raw per-candle deltas.

v1 feature set (as-of, leak-free, identical information set to the ladder logistic):
    margin, frac_elapsed, period, margin_run_180
Deliberately NO pregame team identity/strength (isolates pure sequence value).
Score-total-as-of and possession are NOT available in both corpora -> omitted (noted).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REG_SECONDS = 2880.0  # 4 x 12min
OT_SECONDS = 300.0
RUN_WINDOW = 180.0    # game-time window for the scoring-run feature
FEATURES = ["margin", "frac_elapsed", "period", "margin_run_180"]
# normalization divisors (fixed, no fitting -> no leak)
NORM = np.array([15.0, 1.0, 4.0, 15.0], dtype=np.float32)

DATA = "data/cache"
STATES = [
    f"{DATA}/ingame/pbp_states_2024_25.parquet",
    f"{DATA}/ingame/pbp_states_2025_26.parquet",
]
CHECKPOINTS = f"{DATA}/inplay_odds/nba_checkpoints_2025_26_playoffs.parquet"
CUTOFF = "2026-03-01"  # train = before; val = on/after (25-26 only), excl. checkpoints


def _elapsed_from_period_clock(period: np.ndarray, clock_s: np.ndarray) -> np.ndarray:
    """Within-period (period, game_clock_s) -> monotone game-time elapsed seconds."""
    period = period.astype(float)
    clock_s = clock_s.astype(float)
    reg = (period - 1) * 720.0 + (720.0 - clock_s)
    ot = REG_SECONDS + (period - 5) * OT_SECONDS + (OT_SECONDS - clock_s)
    return np.where(period <= 4, reg, ot)


def _add_run_feature(df: pd.DataFrame) -> pd.DataFrame:
    """margin_run_180 = margin(now) - margin as-of RUN_WINDOW sec of game-time ago.
    Computed per game via searchsorted (leak-free; ref before start -> 0)."""
    out = []
    for _, g in df.groupby("game_id", sort=False):
        g = g.sort_values("elapsed", kind="mergesort").reset_index(drop=True)
        e = g["elapsed"].to_numpy(dtype=float)
        m = g["margin"].to_numpy(dtype=float)
        ref_idx = np.searchsorted(e, e - RUN_WINDOW, side="right") - 1
        ref = np.where(ref_idx >= 0, m[np.clip(ref_idx, 0, len(m) - 1)], 0.0)
        g["margin_run_180"] = m - ref
        out.append(g)
    return pd.concat(out, ignore_index=True)


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["frac_elapsed"] = np.clip(df["elapsed"] / REG_SECONDS, 0.0, 1.0)
    df = _add_run_feature(df)
    return df


def load_states() -> pd.DataFrame:
    """Long per-candle frame from both states parquets on the unified elapsed axis."""
    frames = []
    for p in STATES:
        s = pd.read_parquet(p)
        f = pd.DataFrame({
            "game_id": s["event_id"].astype(str),
            "date": pd.to_datetime(s["date"]),
            "elapsed": REG_SECONDS - s["seconds_remaining"].astype(float),
            "margin": s["home_margin"].astype(float),
            "home_win": s["home_win"].astype(int),
        })
        # period from total elapsed (regulation only in this corpus)
        f["period"] = np.clip(np.ceil(f["elapsed"] / 720.0), 1, 4).astype(int)
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    return _finalize(df)


def load_checkpoints() -> pd.DataFrame:
    """Checkpoint (market) frame; keeps market_prob aligned to each candle row."""
    ck = pd.read_parquet(CHECKPOINTS)
    f = pd.DataFrame({
        "game_id": ck["game_id"].astype(str),
        "date": pd.to_datetime(ck["game_date"]),
        "elapsed": _elapsed_from_period_clock(ck["period"].to_numpy(), ck["game_clock_s"].to_numpy()),
        "margin": ck["margin"].astype(float),
        "period": np.clip(ck["period"].astype(int), 1, 6),
        "home_win": ck["outcome_home_win"].astype(int),
        "market_prob": ck["market_prob"].astype(float),
    })
    return _finalize(f)


def checkpoint_ids() -> set[str]:
    return set(pd.read_parquet(CHECKPOINTS)["game_id"].astype(str))


def split_states(states: pd.DataFrame, drop_ids: set[str], cutoff: str = CUTOFF):
    """STRICT date split by game. train = <cutoff (all 24-25 + early 25-26);
    val = >=cutoff (25-26 tail). Checkpoint ids removed from BOTH (leak guard)."""
    s = states[~states["game_id"].isin(drop_ids)].copy()
    cut = pd.Timestamp(cutoff)
    train = s[s["date"] < cut]
    val = s[s["date"] >= cut]
    # assert no game spans the boundary and no id overlap
    assert set(train["game_id"]).isdisjoint(set(val["game_id"])), "train/val game overlap"
    assert set(train["game_id"]).isdisjoint(drop_ids), "checkpoint leak in train"
    assert set(val["game_id"]).isdisjoint(drop_ids), "checkpoint leak in val"
    return train, val


def to_sequences(df: pd.DataFrame):
    """Long frame -> per-game list of (feat[T,4] normalized, label float, meta DataFrame).
    Padding/masking is handled by the training collate; here sequences stay ragged."""
    seqs = []
    for gid, g in df.groupby("game_id", sort=False):
        g = g.sort_values("elapsed", kind="mergesort")
        feat = (g[FEATURES].to_numpy(dtype=np.float32) / NORM)
        label = float(g["home_win"].iloc[0])
        seqs.append((gid, feat, label, g.reset_index(drop=True)))
    return seqs


if __name__ == "__main__":  # smoke summary + self-checks (ASCII only)
    ck_ids = checkpoint_ids()
    st = load_states()
    tr, va = split_states(st, ck_ids)
    ck = load_checkpoints()
    print(f"states rows={len(st)} games={st.game_id.nunique()}")
    print(f"train games={tr.game_id.nunique()} rows={len(tr)} dates {tr.date.min().date()}..{tr.date.max().date()}")
    print(f"val   games={va.game_id.nunique()} rows={len(va)} dates {va.date.min().date()}..{va.date.max().date()}")
    print(f"test(checkpoints) games={ck.game_id.nunique()} rows={len(ck)} dates {ck.date.min().date()}..{ck.date.max().date()}")
    # market orientation sanity: prob should rise with home margin
    c = np.corrcoef(ck["market_prob"], ck["margin"])[0, 1]
    print(f"corr(market_prob, margin)={c:.3f} (must be >0 for P(home win) orientation)")
    # monotone elapsed check on one game
    g0 = ck.sort_values(["game_id", "elapsed"]).groupby("game_id").head(1)
    print(f"OT rows in checkpoints (period>4): {(ck.period > 4).sum()}")
