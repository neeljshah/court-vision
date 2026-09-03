"""S116 corpus half -- the two SCREEN-side in-game tick frames, in one normalised schema.

Kept out of `s116_pooled_ingame` only to hold both modules under the 300-LOC rail (the
same reason `foundry.run_ingame_screen` exists); it adds no fitting and no scoring.

Columns produced: sport, cluster, date, ts_utc, margin, model, market, y, frac_elapsed,
and after `prepare` also logit_market and gap = logit(model) - logit(market).

  nba -- the S86 archived per-tick SCREEN side (verdict side never read); model is
         `price_checkpoint` over the as-of Elo prior; cluster = `nba:<game_id>`;
         frac_elapsed = elapsed / (48 + 5 * overtime periods), OT-aware.
  mlb -- the joined Kalshi tick store on the S82 ISO-week SCREEN side (same seed, so
         `screen_sha256` reproduces; verdict side never read); model is the incumbent
         e4 blend; cluster = REAL game (S106 `real_game_seq`, not the re-used ticker);
         frac_elapsed = (inning - 1 + half) / max(9, inning), extras-aware.

No ledger, no seal, no charge. Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/ingame/test_s116_pooled_ingame.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.s94_nba_early_shrinkage import S86_CSV, logit

REPO = Path(__file__).resolve().parents[3]
NBA_COLS = ["game_id", "game_date", "ts", "period", "elapsed", "margin", "model", "market", "y"]


def load_nba(path: Path = S86_CSV) -> pd.DataFrame:
    """The S86 SCREEN-side per-tick archive (the verdict side is never read)."""
    raw = pd.read_csv(path, usecols=NBA_COLS)
    out = pd.DataFrame({
        "sport": "nba", "cluster": "nba:" + raw["game_id"].astype(str),
        "date": raw["game_date"].astype(str),
        "ts_utc": pd.to_datetime(raw["ts"], unit="s"), "margin": raw["margin"].astype(float),
        "model": raw["model"].astype(float), "market": raw["market"].astype(float),
        "y": raw["y"].astype(float)})
    # OT-aware: regulation is 48 min and each extra period adds 5. Period is known at the tick.
    denom = 48.0 + 5.0 * np.maximum(0, raw["period"].to_numpy(int) - 4)
    out["frac_elapsed"] = np.clip(raw["elapsed"].to_numpy(float) / denom, 0.0, 1.0)
    return out


def _mlb_rows(ticks, e4, first) -> pd.DataFrame:
    """One row per tick that carries a finite model, a finite line, an outcome and state."""
    from scripts.platformkit.mlb_state_features import parse_state

    rows = []
    for i, tick in enumerate(ticks):
        p, mkt, y = e4[i], tick.get("market_prob"), tick.get("outcome")
        if p is None or mkt is None or y is None or not np.isfinite(float(mkt)):
            continue
        summary = tick.get("state_summary") or (tick.get("raw") or {}).get("state_summary")
        state = parse_state(summary)
        if state["inning"] is None or state["home_score"] is None or state["away_score"] is None:
            continue
        rows.append({"game": str(tick["game"]), "ts": str(tick["timestamp"]),
                     "game_date": first[str(tick["game"])], "state_summary": str(summary or ""),
                     "y": float(y), "model": float(p), "market": float(mkt),
                     "margin": float(state["home_score"]) - float(state["away_score"]),
                     "inning": int(state["inning"]),
                     "half": 0.5 if str(state["half"]).lower().startswith("bot") else 0.0})
    return pd.DataFrame(rows)


def load_mlb() -> pd.DataFrame:
    """The S82 SCREEN side of the joined MLB tick store, clustered by REAL game (S106)."""
    from scripts.platformkit import hedge_trial_arms as arms
    from scripts.platformkit.eval_gate.real_game_split import assign_real_game_seq, cluster_ids
    from scripts.platformkit.eval_gate.stacker import _first_dates, e4_gd_series
    from scripts.platformkit.foundry.ingame_screen import partition
    from scripts.platformkit.ingame_replay_scoreboard import discover_store

    ticks, feats = arms.load_corpus(discover_store(REPO / "data" / "cache"), "mlb")
    frame = _mlb_rows(ticks, e4_gd_series(ticks, feats), _first_dates(ticks))
    frame = frame[frame["game"].isin(partition(frame).screen_ids)].reset_index(drop=True)
    frame, _ = assign_real_game_seq(frame.rename(columns={"game": "game_id"}), game_col="game_id",
                                   ts_col="ts", state_col="state_summary")
    inn = frame["inning"].to_numpy(float)
    return pd.DataFrame({
        "sport": "mlb", "cluster": "mlb:" + cluster_ids(frame, game_col="game_id"),
        "date": frame["game_date"].astype(str),
        "ts_utc": pd.to_datetime(frame["ts"], format="ISO8601", utc=True).dt.tz_localize(None),
        "margin": frame["margin"].astype(float), "model": frame["model"].astype(float),
        "market": frame["market"].astype(float), "y": frame["y"].astype(float),
        # extras-aware: regulation is 9 innings; an extra inning extends the denominator.
        "frac_elapsed": np.clip((inn - 1.0 + frame["half"].to_numpy(float))
                                / np.maximum(9.0, inn), 0.0, 1.0)}).reset_index(drop=True)


def prepare(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate the sport frames, add the offset and the prior-minus-market gap.

    A cluster id must not be a bare integer: the archived per-tick CSV is read back with
    default dtypes when a CI is recomputed (Q9), and a numeric id re-types per chunk and
    splits one cluster into two. Sport-prefixed ids make that impossible.
    """
    out = pd.concat(list(frames), ignore_index=True)
    numeric = out["cluster"].astype(str).str.fullmatch(r"[0-9]+")
    if bool(numeric.any()):
        raise ValueError("cluster ids must not be bare integers: %s"
                         % sorted(set(out.loc[numeric, "cluster"].astype(str)))[:3])
    out["logit_market"] = logit(out["market"])
    out["gap"] = logit(out["model"]) - out["logit_market"]
    return out.sort_values(["ts_utc", "sport", "cluster"], kind="stable").reset_index(drop=True)


def census(frame: pd.DataFrame) -> dict:
    """n ticks / n clusters / date span per sport -- the STEP 0 table."""
    return {s: {"n_ticks": int(len(sub)), "n_clusters": int(sub["cluster"].nunique()),
                "date_min": str(sub["date"].min()), "date_max": str(sub["date"].max())}
            for s, sub in frame.groupby("sport", sort=True)}


__all__ = ["load_nba", "load_mlb", "prepare", "census"]
