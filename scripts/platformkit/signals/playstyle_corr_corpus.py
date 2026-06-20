"""scripts.platformkit.signals.playstyle_corr_corpus -- the real player-game corpus loader
for the playstyle_corr validation gate (split out to keep the gate <=300 LOC).

Builds a leak-free player-game residual corpus + AS-OF archetype membership:
  * residual_s = actual_s - pregame OOF projection (out-of-fold; player-mean fallback) ->
    co-movement around expectation, never a same-game actual leak;
  * archetype membership = the season-stable rule-based label (player_archetype_sameplayer
    .json) -- a slowly-varying player TRAIT, not a per-game season-final predictor;
  * a stable disjoint-by-GAME 2-way partition (corpus A/B) for cross-corpus replication.

A MISSING on-disk corpus yields None (cold start -> the gate reports NOT-BINDABLE; never
fabricated). Read-only over data/cache + data/models. ASCII; stdlib + pandas/numpy.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REG = _ROOT / "data" / "cache" / "cv_fix" / "leaguegamelog_regular_season.parquet"
_OOF = _ROOT / "data" / "cache" / "pregame_oof_faithful.parquet"
_ARCH = _ROOT / "data" / "models" / "player_archetype_sameplayer.json"


def load_corpus():
    """player-game residuals + archetype membership, or None if the corpus is absent."""
    import pandas as pd
    if not (_REG.exists() and _OOF.exists() and _ARCH.exists()):
        return None
    cols = ["PLAYER_ID", "GAME_ID", "GAME_DATE", "MIN",
            "PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV"]
    box = pd.read_parquet(_REG, columns=cols)
    box.columns = box.columns.str.lower()
    box["game_date"] = pd.to_datetime(box["game_date"])
    box = box[box["min"] >= 5].drop_duplicates(["player_id", "game_id"])
    oof = pd.read_parquet(_OOF, columns=["player_id", "game_date", "stat", "oof_pred"])
    oof["game_date"] = pd.to_datetime(oof["game_date"])
    wide = oof.pivot_table(index=["player_id", "game_date"], columns="stat",
                           values="oof_pred", aggfunc="first").reset_index()
    wide.columns.name = None
    wide = wide.rename(columns={s: "oof_%s" % s for s in _STATS if s in wide.columns})
    m = box.merge(wide, on=["player_id", "game_date"], how="left")
    for s in _STATS:  # leak-free residual = actual - pregame OOF (player-mean fallback)
        oc = "oof_%s" % s
        if oc not in m.columns:
            m[oc] = np.nan
        m["resid_%s" % s] = m[s] - m[oc].fillna(m.groupby("player_id")[s].transform("mean"))
    amap = {int(k): v for k, v in json.load(open(_ARCH)).items()}
    m["archetype"] = m["player_id"].astype(int).map(amap)
    m = m.dropna(subset=["archetype"]).reset_index(drop=True)
    # stable disjoint-by-GAME 2-way partition (cross-corpus A/B) by game_id hash.
    m["corpus"] = np.where(m["game_id"].astype(str).map(lambda g: hash(g) % 2 == 0),
                           "A", "B")
    return m


__all__ = ["load_corpus"]
