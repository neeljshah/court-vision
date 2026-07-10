"""domains.basketball_nba.knowledge.validate_boxdetail_persistence -- 4
mechanisms on the newly-unlocked espn_boxscores.parquet box-DETAIL family
(fast_break_pts, paint_pts, tov_pts, largest_lead). The leak-free walk-forward AS-OF reader
for this family already exists (domains/basketball_nba/boxdetail_asof.py,
built same session) -- this module is the DESCRIPTIVE mechanism check that
sits alongside it, same style as every other validate_*.py in this package
(validate_rotation_pace.py etc): same-game raw values, cross-sectional /
split-half only, never wired as a live per-game feature.

Each hypothesis is ONE stat, testing TWO legs together:
  1. persistence   -- is a team's average of this stat a stable team trait
                       (split-half Pearson r: first half of the corpus's
                       date range vs second half)?
  2. margin-relation -- does this stat correlate with that same game's
                       scoring margin (team_pts - opp_pts, same-game,
                       descriptive only -- not a prediction input)?
CONFIRMED_LOCAL requires BOTH legs to clear ALPHA + a minimum effect size;
otherwise NULL_LOCAL. 4 hypotheses (one per stat), not 8 separate rows.

largest_lead extends the "blowout-tendency" angle (garbage-time bench
inflation, mechanisms.md #17 CONFIRMED) to a team-level trait: does a team's
own largest_lead persist game-to-game, and does it relate to that same
game's scoring margin (obviously correlated with margin by construction for
winning teams -- the real question is the PERSISTENCE leg).

OT CAUTION (same caveat boxdetail_asof.py documents): home_score/away_score
in espn_boxscores.parquet are TRUNCATED for OT games (regulation tie
recorded, not final). Margin here is therefore slightly noisy for OT games
-- acceptable for a descriptive mechanism check; this module produces no
production feature so the caveat does not propagate downstream.

Excludes 3 non-team rows (STARS/STRIPES/WORLD -- All-Star exhibition labels
present in the raw abbr columns, not real teams with a season history).

PRIVATE: data/ never committed. No src.*/kernel.*/other-domain imports (F5).
No edge claimed -- calibration/mechanism knowledge only.

Run: python -m domains.basketball_nba.knowledge.validate_boxdetail_persistence
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from scripts.platformkit.io_atomic import append_jsonl_atomic

REPO = Path(__file__).resolve().parents[3]
ESPN_BOX_PATH = REPO / "data" / "domains" / "basketball_nba" / "espn_boxscores.parquet"
LEDGER_PATH = Path(__file__).resolve().parent / "validation_ledger.jsonl"

ALPHA = 0.01
MIN_EFFECT = 0.15
_NON_TEAMS = {"STARS", "STRIPES", "WORLD"}
STATS = ("fast_break_pts", "paint_pts", "tov_pts", "largest_lead")


def _load_team_games(espn_box: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """espn_boxscores.parquet (one row/game, home_/away_ prefixed) -> one row
    per team-game: date, team, margin, {stat}. Descriptive same-game values
    only -- never wired anywhere as a live feature."""
    df = espn_box if espn_box is not None else pd.read_parquet(ESPN_BOX_PATH)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    sides = []
    for side, opp in (("home", "away"), ("away", "home")):
        d = pd.DataFrame({
            "date": df["date"],
            "team": df[f"{side}_abbr"],
            "margin": pd.to_numeric(df[f"{side}_score"], errors="coerce")
            - pd.to_numeric(df[f"{opp}_score"], errors="coerce"),
        })
        for s in STATS:
            d[s] = pd.to_numeric(df[f"{side}_{s}"], errors="coerce")
        sides.append(d)
    tg = pd.concat(sides, ignore_index=True)
    return tg[~tg["team"].isin(_NON_TEAMS)].reset_index(drop=True)


def _verdict(p_persist: float, eff_persist: float, p_margin: float, eff_margin: float) -> str:
    vals = (p_persist, eff_persist, p_margin, eff_margin)
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in vals):
        return "NOT_TESTABLE"
    persist_real = p_persist < ALPHA and abs(eff_persist) >= MIN_EFFECT
    margin_real = p_margin < ALPHA and abs(eff_margin) >= MIN_EFFECT
    return "CONFIRMED_LOCAL" if (persist_real and margin_real) else "NULL_LOCAL"


def _persistence_split_half(tg: pd.DataFrame, stat: str) -> Dict[str, Any]:
    d = tg.dropna(subset=[stat]).copy()
    if len(d) == 0:
        return {"p": np.nan, "r": np.nan, "n": 0}
    mid = d["date"].median()
    d["half"] = np.where(d["date"] <= mid, "h1", "h2")
    team_half = d.groupby(["team", "half"])[stat].mean().unstack("half").dropna()
    if len(team_half) < 3:
        return {"p": np.nan, "r": np.nan, "n": int(len(team_half))}
    r, p = stats.pearsonr(team_half["h1"], team_half["h2"])
    return {"p": float(p), "r": round(float(r), 4), "n": int(len(team_half))}


def _margin_relation(tg: pd.DataFrame, stat: str) -> Dict[str, Any]:
    d = tg.dropna(subset=[stat, "margin"])
    if len(d) < 3:
        return {"p": np.nan, "r": np.nan, "n": int(len(d))}
    r, p = stats.pearsonr(d[stat], d["margin"])
    return {"p": float(p), "r": round(float(r), 4), "n": int(len(d))}


def hypothesis(tg: pd.DataFrame, stat: str) -> Dict[str, Any]:
    persist = _persistence_split_half(tg, stat)
    margin = _margin_relation(tg, stat)
    verdict = _verdict(persist["p"], persist["r"], margin["p"], margin["r"])
    p_str = "nan" if (persist["p"] is None or np.isnan(persist["p"])) else "%.4g" % persist["p"]
    m_str = "nan" if (margin["p"] is None or np.isnan(margin["p"])) else "%.4g" % margin["p"]
    return {
        "hypothesis": f"boxdetail_{stat}_persistence_and_margin",
        "verdict": verdict,
        "persist_r": persist["r"], "persist_p": persist["p"], "n_persist_teams": persist["n"],
        "margin_r": margin["r"], "margin_p": margin["p"], "n_margin": margin["n"],
        "note": f"split-half team persistence r={persist['r']} p={p_str} (n={persist['n']} teams); "
                f"same-game margin relation r={margin['r']} p={m_str} (n={margin['n']} team-games)",
    }


def run() -> List[Dict[str, Any]]:
    tg = _load_team_games()
    rows = [hypothesis(tg, s) for s in STATS]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "espn_boxscores_boxdetail_2026_01_20_onward"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.3, 0.001, 0.3) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.3, 0.001, 0.3) == "NULL_LOCAL"
    assert _verdict(np.nan, np.nan, 0.001, 0.3) == "NOT_TESTABLE"
    print("self-check OK")
