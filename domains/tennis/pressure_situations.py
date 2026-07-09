"""domains.tennis.pressure_situations -- point-level situation detectors for
the pressure-point claim family (extends prereg_point_mechanisms.py's H1
break-point mechanism to game/set/tiebreak/deuce situations).

charting_points ONLY -- player identity and is_second_serve only exist there
(slam_points.parquet has no player-identity column and no serve-in flag; see
prereg_point_mechanisms.py's verified-schema notes). Real ace/double-fault
rate deltas on slam_points are a documented follow-up, not built here.

Situation definitions (all derived from score_state/gm1/gm2/set1/set2 --
verified against real rows this session, see the mechanism module's own
schema notes for score_state's "server-returner PRE-point" semantics):
  break_point   : returner one point from breaking (reused from
                  prereg_point_mechanisms._break_point).
  game_point    : server one point from winning the CURRENT game -- the
                  mirror of break_point (same function, args swapped).
  set_point     : game_point (either side) AND that side's games-won would
                  CLINCH the set under standard ad-scoring (first to 6, win
                  by 2, breaker at 6-6, i.e. 7-6). Because game_point/
                  break_point are computed from the 0/15/30/40/AD score
                  vocabulary, they are naturally False on tiebreak rows (raw
                  integer scores never match that vocabulary) -- tiebreak
                  set-enders are covered by tiebreak_point instead, never
                  double-counted here.
  tiebreak_point: gm1==6 and gm2==6 and BOTH score_state halves are plain
                  integers (verified: real tiebreak rows carry raw integer
                  scores, not 0/15/30/40/AD, exactly when games are 6-6).
  deuce_battle  : point occurs in a game that has ALREADY reached deuce
                  (40-40) three or more times before this point (own-game
                  running count, keyed on match_id+set1+set2+gm1+gm2 which
                  resets whenever a new game starts) -- a "protracted
                  battle" proxy, not a literal single-deuce-point flag.

CAVEAT: set_point's clinch rule assumes standard ad-scoring; it does not
model no-ad deciding sets or short-set formats (both real but rare in this
corpus's slam/tour coverage) -- a defensible approximation, not exact for
every match format.

edge_claimed hard-wired False (this module computes no claims itself).
NETWORK: zero.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from domains.tennis.prereg_point_mechanisms import _break_point

STANDARD = {"0", "15", "30", "40", "AD"}
SITUATIONS = ("break_point", "game_point", "set_point", "tiebreak_point", "deuce_battle")


def _clinches_set(games_after_win: np.ndarray, opp_games: np.ndarray) -> np.ndarray:
    """Would winning the current game (games_after_win vs opp_games) end the set,
    under standard ad-scoring (first to 6, win by 2, breaker at 6-6 -> 7-6)?"""
    games_after_win = np.asarray(games_after_win, dtype=float)
    opp_games = np.asarray(opp_games, dtype=float)
    reg = (games_after_win >= 6) & ((games_after_win - opp_games) >= 2)
    tb = (games_after_win == 7) & (opp_games == 6)
    return reg | tb


def charting_situation_state(df: pd.DataFrame, year_min: Optional[int] = None) -> pd.DataFrame:
    """One row per usable point: match_id, date, server slot, server_won,
    is_second_serve, and every situation flag in SITUATIONS. Standard-scoring
    rows and tiebreak rows are both kept -- tiebreak rows only ever set
    tiebreak_point=True, every ad-scoring situation is False for them."""
    d = df[(df["date_source"] != "missing") & df["server"].isin((1, 2))
           & df["point_winner"].isin((1, 2))].copy()
    if year_min is not None:
        d = d[pd.to_datetime(d["date"]).dt.year >= year_min]
    parts = d["score_state"].astype(str).str.split("-", n=1, expand=True)
    before_srv, before_ret = parts[0], parts[1]
    is_std = before_srv.isin(STANDARD) & before_ret.isin(STANDARD)
    is_num = before_srv.str.match(r"^\d+$") & before_ret.str.match(r"^\d+$")
    gm1 = pd.to_numeric(d["gm1"], errors="coerce")
    gm2 = pd.to_numeric(d["gm2"], errors="coerce")
    is_tb = is_num & (gm1 == 6) & (gm2 == 6)
    keep = (is_std | is_tb).to_numpy()
    d = d[keep]
    before_srv, before_ret = before_srv[keep], before_ret[keep]
    is_tb = is_tb[keep]
    gm1, gm2 = gm1[keep].to_numpy(), gm2[keep].to_numpy()

    server = d["server"].astype(int)
    is_p1_server = server.to_numpy() == 1
    server_gm = np.where(is_p1_server, gm1, gm2)
    ret_gm = np.where(is_p1_server, gm2, gm1)

    bp = _break_point(before_srv, before_ret)   # returner at break point
    gp = _break_point(before_ret, before_srv)   # server at game point (mirror)
    sp_server = gp.to_numpy() & _clinches_set(server_gm + 1, ret_gm)
    sp_return = bp.to_numpy() & _clinches_set(ret_gm + 1, server_gm)
    set_point = sp_server | sp_return

    is_deuce = (before_srv == "40") & (before_ret == "40")
    game_key = (d["match_id"].astype(str) + "|" + d["set1"].astype(str) + "|" + d["set2"].astype(str)
                + "|" + d["gm1"].astype(str) + "|" + d["gm2"].astype(str))
    deuce_int = is_deuce.astype(int)
    prior_deuces = deuce_int.groupby(game_key).cumsum().to_numpy() - deuce_int.to_numpy()
    deuce_battle = prior_deuces >= 3

    return pd.DataFrame({
        "match_id": d["match_id"].to_numpy(),
        "date": pd.to_datetime(d["date"]).to_numpy(),
        "server": server.to_numpy(),
        "server_won": (d["point_winner"].astype(int).to_numpy() == server.to_numpy()).astype(int),
        "is_second_serve": d["is_second_serve"].fillna(False).to_numpy(),
        "break_point": bp.to_numpy(),
        "game_point": gp.to_numpy(),
        "set_point": set_point,
        "tiebreak_point": is_tb.to_numpy(),
        "deuce_battle": deuce_battle,
    })
