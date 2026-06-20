"""scripts.platformkit.ingame.ingame_layer_gate_nba_io -- IO + leak-free Elo prior
for the in-game DETAIL-LAYER gate (companion to ingame_layer_gate_nba.py).

Splits the data-loading + pregame-prior plumbing out of the gate so each file stays
<=300 LOC. Everything here is NON-GATED:
  * reads data/domains/basketball_nba/linescores.parquet (1 NBA season, per-quarter).
  * derives a leak-free PREGAME Elo prior p0 per game via the non-gated
    domains.basketball_nba.ratings.walk_forward_elo -- which snapshots each team's
    Elo STRICTLY before the game, then updates. So p0 for game g never sees g's
    outcome (nor any later game's). This is the per-game prior the gate blends in.

The linescore corpus carries no home_win / season column, so we derive both from the
per-quarter totals (home_win = cumulative home > away) and a single constant season
(the whole corpus is 2025-26). A constant season means season-boundary regression
never fires here -- fine: it is one season.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
"""
from __future__ import annotations

import os
from typing import Dict, List

import numpy as np
import pandas as pd

from domains.basketball_nba.ratings import walk_forward_elo

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LINESCORES = os.path.join(
    _REPO, "data", "domains", "basketball_nba", "linescores.parquet")
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "layer_gate_nba.json")

_REG_SEC = 2880.0
# Seconds REMAINING in regulation at the END of each quarter (leak-free as-of points).
QSEC = {1: 2160.0, 2: 1440.0, 3: 720.0}
_QCOLS = ["home_q1", "home_q2", "home_q3", "home_q4",
          "away_q1", "away_q2", "away_q3", "away_q4"]


def p_live_from_margin(score_diff: float, frac_elapsed: float) -> float:
    """Honest live win-prob from realized as-of margin only (mirrors fit_w_surface).

    Logistic slope grows with elapsed fraction = the freshness lever (more confident
    later, by design). This is the BASE model -- (margin, time) only, NO team prior.
    """
    slope = 0.06 + 0.10 * float(frac_elapsed)
    return float(1.0 / (1.0 + np.exp(-slope * float(score_diff))))


def load_linescores(path: str = LINESCORES) -> pd.DataFrame:
    """Load + clean the per-quarter linescore corpus, sorted by date."""
    df = pd.read_parquet(path).dropna(subset=_QCOLS)
    return df.sort_values("date").reset_index(drop=True)


def leakfree_elo_p0(df: pd.DataFrame) -> Dict[int, float]:
    """Leak-free pregame Elo p0 per game_id (event_id), computed ONCE.

    Builds the games frame walk_forward_elo expects (date/season/home_team/away_team/
    home_win), derives home_win + a constant season from the linescore totals, then
    reads p_home_elo -- the STRICTLY pre-game snapshot for each game (no game sees its
    own or any later outcome). Returns {event_id: p0}.
    """
    h = df[["home_q1", "home_q2", "home_q3", "home_q4"]].to_numpy().sum(axis=1)
    a = df[["away_q1", "away_q2", "away_q3", "away_q4"]].to_numpy().sum(axis=1)
    games = pd.DataFrame({
        "game_id": df["event_id"].to_numpy(),
        "date": df["date"].to_numpy(),
        "season": 2025,  # single-season corpus; boundary regression never fires
        "home_team": df["home_abbr"].astype(str).to_numpy(),
        "away_team": df["away_abbr"].astype(str).to_numpy(),
        "home_win": (h > a).astype(float),
    })
    rated = walk_forward_elo(games)
    return {int(r["game_id"]): float(r["p_home_elo"]) for _, r in rated.iterrows()}


def states_for_games(df: pd.DataFrame, p0_map: Dict[int, float]) -> List[dict]:
    """Reconstruct leak-free as-of in-game states (end-Q1/Q2/Q3) for the given games.

    score_diff = cumulative home-away AFTER that quarter (past only); outcome = realized
    home win; p_live = base (margin,time) prob; p0 = leak-free pregame Elo prior for the
    game. margin_final kept for diagnostics. One game contributes 3 states.
    """
    out: List[dict] = []
    for _, r in df.iterrows():
        gid = int(r["event_id"])
        p0 = float(p0_map[gid])
        hc = np.cumsum([float(r["home_q1"]), float(r["home_q2"]),
                        float(r["home_q3"]), float(r["home_q4"])])
        ac = np.cumsum([float(r["away_q1"]), float(r["away_q2"]),
                        float(r["away_q3"]), float(r["away_q4"])])
        y = int(hc[-1] > ac[-1])
        margin_final = float(hc[-1] - ac[-1])
        for q in (1, 2, 3):
            diff = float(hc[q - 1] - ac[q - 1])
            frac = 1.0 - QSEC[q] / _REG_SEC
            out.append({
                "game_id": gid, "period": q, "seconds_remaining": QSEC[q],
                "score_diff": diff, "p0": p0, "p_live": p_live_from_margin(diff, frac),
                "outcome": y, "margin_final": margin_final,
            })
    return out
