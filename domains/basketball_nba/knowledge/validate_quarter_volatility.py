"""domains.basketball_nba.knowledge.validate_quarter_volatility -- 2 UNTESTED
quarter-shape persistence mechanisms (NBA mechanisms.md quarter-volatility /
Q1-slow-start seed) against the leak-free linescores corpus. Reuses the
realized per-team-game quarter-shape derivation already built by
domains/basketball_nba/asof_quarter_shape.py::_derive_realized (read-only
import -- this module does not modify that builder) so "quarter_volatility"
and "q1_margin" mean exactly what the production as-of feature means:

  q1_margin           = own_q1 - opp_q1 (positive = fast starter)
  quarter_volatility  = stdev of a team's own q1..q4 points that game

Descriptive only: split-half persistence (first-half-of-corpus-dates vs
second) + a cross-sectional relation to a team's full-game margin variance
(std of margin across its games). Neither leg is a live per-game feature --
same discipline as validate_boxdetail_persistence.py / validate_rotation_pace.py.

Run: python -m domains.basketball_nba.knowledge.validate_quarter_volatility
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.asof_quarter_shape import _derive_realized, _LINESCORES_DEFAULT
from domains.basketball_nba.knowledge._data import LEDGER_PATH
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_EFFECT = 0.15


def team_game_frame(linescores: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """One row per team-game: date, team, quarter_volatility, q1_margin,
    margin (full-game = first_half_margin + second_half_margin, derived from
    the SAME 4 quarter columns as quarter_volatility -- no separate score
    field, so no OT-truncation ambiguity)."""
    ls = linescores if linescores is not None else pd.read_parquet(_LINESCORES_DEFAULT)
    spine = _derive_realized(ls)
    sides = []
    for side in ("home", "away"):
        d = pd.DataFrame({
            "date": pd.to_datetime(spine["date"]),
            "team": spine[f"{side}_key"],
            "quarter_volatility": spine[f"{side}_quarter_volatility"],
            "q1_margin": spine[f"{side}_q1_margin"],
            "margin": spine[f"{side}_first_half_margin"] + spine[f"{side}_second_half_margin"],
        })
        sides.append(d)
    return pd.concat(sides, ignore_index=True)


def _split_half_persist(tg: pd.DataFrame, stat: str) -> Dict[str, Any]:
    d = tg.dropna(subset=[stat]).copy()
    if len(d) == 0:
        return {"p": np.nan, "r": np.nan, "n": 0}
    mid = d["date"].median()
    d["half"] = np.where(d["date"] <= mid, "h1", "h2")
    th = d.groupby(["team", "half"])[stat].mean().unstack("half").dropna()
    if len(th) < 3:
        return {"p": np.nan, "r": np.nan, "n": int(len(th))}
    r, p = stats.pearsonr(th["h1"], th["h2"])
    return {"p": float(p), "r": round(float(r), 4), "n": int(len(th))}


def _fmt_p(p: Optional[float]) -> str:
    return "nan" if (p is None or (isinstance(p, float) and np.isnan(p))) else "%.4g" % p


def _verdict_1leg(p: Optional[float], effect: Optional[float]) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= MIN_EFFECT) else "NULL_LOCAL"


def _verdict_2leg(p1, e1, p2, e2) -> str:
    vals = (p1, e1, p2, e2)
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in vals):
        return "NOT_TESTABLE"
    leg1 = p1 < ALPHA and abs(e1) >= MIN_EFFECT
    leg2 = p2 < ALPHA and abs(e2) >= MIN_EFFECT
    return "CONFIRMED_LOCAL" if (leg1 and leg2) else "NULL_LOCAL"


def quarter_volatility_persists_and_relates_to_margin_variance(tg: pd.DataFrame) -> Dict[str, Any]:
    persist = _split_half_persist(tg, "quarter_volatility")
    team_vol = tg.dropna(subset=["quarter_volatility"]).groupby("team")["quarter_volatility"].mean()
    team_margin_std = tg.dropna(subset=["margin"]).groupby("team")["margin"].std()
    m = pd.concat([team_vol.rename("vol"), team_margin_std.rename("margin_std")], axis=1).dropna()
    if len(m) < 3:
        rel_p, rel_r, rel_n = np.nan, np.nan, int(len(m))
    else:
        rr, pp = stats.pearsonr(m["vol"], m["margin_std"])
        rel_r, rel_p, rel_n = round(float(rr), 4), float(pp), int(len(m))
    verdict = _verdict_2leg(persist["p"], persist["r"], rel_p, rel_r)
    return {
        "hypothesis": "quarter_volatility_persists_and_relates_to_margin_variance",
        "verdict": verdict,
        "persist_r": persist["r"], "persist_p": persist["p"], "n_persist_teams": persist["n"],
        "relate_r": rel_r, "relate_p": rel_p, "n_relate_teams": rel_n,
        "note": "split-half team persistence of quarter_volatility r=%s p=%s (n=%d teams); "
                "cross-sectional r(team avg quarter_volatility, team full-game margin std) r=%s p=%s (n=%d teams)"
                % (persist["r"], _fmt_p(persist["p"]), persist["n"], rel_r, _fmt_p(rel_p), rel_n),
    }


def q1_slow_start_persists(tg: pd.DataFrame) -> Dict[str, Any]:
    persist = _split_half_persist(tg, "q1_margin")
    verdict = _verdict_1leg(persist["p"], persist["r"])
    return {
        "hypothesis": "q1_slow_start_persists_split_half",
        "verdict": verdict,
        "effect": persist["r"], "p": persist["p"], "n": persist["n"],
        "note": "split-half team persistence of q1_margin (own_q1-opp_q1 avg) r=%s p=%s (n=%d teams); "
                "positive=fast starter, negative=slow starter" % (persist["r"], _fmt_p(persist["p"]), persist["n"]),
    }


def run() -> List[Dict[str, Any]]:
    tg = team_game_frame()
    rows = [quarter_volatility_persists_and_relates_to_margin_variance(tg), q1_slow_start_persists(tg)]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "linescores_derive_realized_team_games"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-58s %-16s %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict_1leg(0.001, 0.3) == "CONFIRMED_LOCAL"
    assert _verdict_1leg(0.5, 0.3) == "NULL_LOCAL"
    assert _verdict_2leg(0.001, 0.3, 0.001, 0.3) == "CONFIRMED_LOCAL"
    assert _verdict_2leg(0.5, 0.3, 0.001, 0.3) == "NULL_LOCAL"
    print("self-check OK")
