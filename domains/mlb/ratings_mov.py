"""domains.mlb.ratings_mov -- leak-free walk-forward Elo with optional
margin-of-victory (MOV) multiplier.

This is a STRICT generalization of domains.mlb.ratings.walk_forward_elo:
  * mov_scale == 0.0  -> identical update to the pitcher-blind baseline Elo
    (delta = K * (s_home - p)), so the baseline is recoverable for honest A/B.
  * mov_scale  > 0.0  -> the per-game Elo delta is multiplied by a damped
    log-margin factor

        mult = log(|run_diff| + 1) * mov_scale / (mov_offset + |elo_diff_hfa| * 0.001)

    i.e. a bigger run-margin moves the rating more, with the classic
    autocorrelation-damping term (favorite blowouts move ratings less) borrowed
    from the 538 MOV-Elo design.  The MULTIPLIER USES ONLY THE FINAL SCORE OF
    THE CURRENT GAME, which is applied STRICTLY AFTER the pre-game snapshot is
    recorded -- so it can never leak into that game's own features.

Snapshot-before-update leak contract (identical to ratings.py).  Outputs per
game are STRICTLY pre-game: elo_home, elo_away, elo_diff_hfa, p_home_elo.

PURE pandas/numpy + config constants.  No src.* / kernel.* / other-domain imports.
PRIVATE: never tracked on the public repo.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import pandas as pd

from domains.mlb.config import ELO_K, ELO_MEAN, ELO_HFA, SEASON_REGRESS


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Pinned chronological order: (date, home_team, away_team, game_seq)."""
    sort_df = pd.DataFrame(
        {
            "k0": df["date"].astype(str).values,
            "k1": df["home_team"].astype(str).values,
            "k2": df["away_team"].astype(str).values,
            "k3": (df["game_seq"].astype(str).values
                   if "game_seq" in df.columns else ["0"] * len(df)),
        },
        index=df.index,
    )
    order = sort_df.sort_values(["k0", "k1", "k2", "k3"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


def _mov_mult(run_diff: float, elo_diff_hfa: float, mov_scale: float,
              mov_offset: float) -> float:
    """Damped log-margin multiplier (538-style). Returns 1.0 when mov_scale==0."""
    if mov_scale <= 0.0:
        return 1.0
    margin = abs(float(run_diff))
    damp = mov_offset + abs(float(elo_diff_hfa)) * 0.001
    if damp <= 0.0:
        damp = mov_offset
    return math.log(margin + 1.0) * mov_scale / damp


def walk_forward_elo_mov(
    games_df: pd.DataFrame,
    mov_scale: float = 0.0,
    mov_offset: float = 2.2,
    elo_k: float = ELO_K,
    elo_hfa: float = ELO_HFA,
    season_regress: float = SEASON_REGRESS,
) -> pd.DataFrame:
    """Leak-free per-game pre-game Elo with an optional MOV multiplier.

    mov_scale == 0.0 reproduces the pitcher-blind baseline EXACTLY.
    All knobs (elo_k, elo_hfa, season_regress) are exposed so a gate can FIT
    them on a train corpus and test on a held-out corpus.

    Returns the input rows in chronological order plus the columns
    elo_home, elo_away, elo_diff_hfa, p_home_elo (all strictly pre-game).
    """
    df = _sorted(games_df)
    elo: Dict[str, float] = {}
    last_season: Dict[str, int] = {}

    eh_list, ea_list, diff_list, p_list = [], [], [], []

    home_arr = df["home_team"].astype(str).values
    away_arr = df["away_team"].astype(str).values
    season_arr = df["season"].astype(int).values
    hr_arr = df["home_runs"].astype(float).values
    ar_arr = df["away_runs"].astype(float).values

    for i in range(len(df)):
        home, away = home_arr[i], away_arr[i]
        season = int(season_arr[i])

        # season-boundary regression (before snapshot)
        for team in (home, away):
            if team not in elo:
                elo[team] = ELO_MEAN
                last_season[team] = season
            else:
                prev = last_season.get(team)
                if prev is not None and prev != season:
                    elo[team] += season_regress * (ELO_MEAN - elo[team])
                    last_season[team] = season

        eh = elo[home]
        ea = elo[away]
        diff = (eh + elo_hfa) - ea
        p = 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))

        eh_list.append(eh)
        ea_list.append(ea)
        diff_list.append(diff)
        p_list.append(p)

        # --- update (post-snapshot; MOV multiplier uses ONLY this game's final) ---
        hr, ar = hr_arr[i], ar_arr[i]
        s_home = 1.0 if hr > ar else 0.0
        mult = _mov_mult(hr - ar, diff, mov_scale, mov_offset)
        delta = elo_k * mult * (s_home - p)
        elo[home] += delta
        elo[away] -= delta

    out = df.copy()
    out["elo_home"] = eh_list
    out["elo_away"] = ea_list
    out["elo_diff_hfa"] = diff_list
    out["p_home_elo"] = p_list
    return out


__all__ = ["walk_forward_elo_mov", "_mov_mult"]
