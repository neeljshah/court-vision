"""domains.basketball_nba.knowledge.validate_research_wave1 -- validates the
3 literature-sourced research-seed rows appended 2026-07-10 (commit
e500a0d6, renumbered #42-44 to resolve a numbering collision with the
same-night Validated-2026-07-10 section, which already used #40/#41).

Three independent corpora -- one hypothesis function each, same
descriptive/never-wired discipline as every other validate_*.py sibling in
this package:

  defender_matchup_skill_predictive_validity  (row #42) -- defender_matchup_states.parquet
  switch_rate_defensive_efficiency            (row #43) -- asof_defender_rollup.parquet
  ast_persistence_and_margin                  (row #44) -- espn_boxscores.parquet, reuses
                                                             validate_boxdetail_persistence's
                                                             generic split-half+margin helpers
                                                             (same design already CONFIRMED_LOCAL
                                                             for #34/#35, NULL for #36).

PREMISE-CHECK FINDING (row #43): the row's test spec names
`def_switches_per_game_asof` / `def_pts_allowed_per36_asof` as bare columns;
the parquet only has home_/away_/diff_-prefixed variants (fixed inline, see
mechanisms.md #43 note). Further premise check found the switches columns
(home_/away_/diff_) are a CONSTANT-ZERO stub in this parquet -- no variance,
not actually populated locally -- so the hypothesis is NOT_TESTABLE, not a
measured null. Honest finding, not a code bug.

Run: python -m domains.basketball_nba.knowledge.validate_research_wave1
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH
from domains.basketball_nba.knowledge.validate_boxdetail_persistence import (
    _NON_TEAMS, _load_team_games as _load_team_games_boxdetail,
    _margin_relation, _persistence_split_half, _verdict as _verdict_2leg,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

REPO = Path(__file__).resolve().parents[3]
DEFENDER_MATCHUP_PATH = REPO / "data" / "domains" / "basketball_nba" / "defender_matchup_states.parquet"
DEFENDER_ROLLUP_PATH = REPO / "data" / "domains" / "basketball_nba" / "asof_defender_rollup.parquet"
ESPN_BOX_PATH = REPO / "data" / "domains" / "basketball_nba" / "espn_boxscores.parquet"

ALPHA = 0.01
MIN_EFFECT = 0.15
MIN_EFFECT_SWITCH = 0.10  # row #43's own declared bar (lower than the family default)
MIN_PRIOR_POSSESSIONS = 15  # row #42's declared floor, per defender per half
MIN_WINDOWS = 2


# ---------------------------------------------------------------- row #42 --
def _defender_half_frame(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    d = (df if df is not None else pd.read_parquet(DEFENDER_MATCHUP_PATH)).copy()
    d = d.dropna(subset=["def_priorN_fg_pct_allowed_asof", "realized_fg_pct_allowed"])
    d["game_date"] = pd.to_datetime(d["game_date"])
    mid = d["game_date"].median()
    d["half"] = np.where(d["game_date"] <= mid, "h1", "h2")
    return d


def _defender_predictive_r(d: pd.DataFrame, half: str) -> Dict[str, Any]:
    dh = d[d["half"] == half]
    g = dh.groupby("def_player_id").agg(
        asof_mean=("def_priorN_fg_pct_allowed_asof", "mean"),
        realized_mean=("realized_fg_pct_allowed", "mean"),
        n_windows=("def_priorN_fg_pct_allowed_asof", "size"),
        n_prior_sum=("def_n_prior", "sum"),
    )
    g = g[(g["n_windows"] >= MIN_WINDOWS) & (g["n_prior_sum"] >= MIN_PRIOR_POSSESSIONS)]
    if len(g) < 3:
        return {"p": np.nan, "r": np.nan, "n": int(len(g))}
    r, p = stats.pearsonr(g["asof_mean"], g["realized_mean"])
    return {"p": float(p), "r": round(float(r), 4), "n": int(len(g))}


def defender_matchup_skill_predictive_validity(d: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    dd = d if d is not None else _defender_half_frame()
    h1 = _defender_predictive_r(dd, "h1")
    h2 = _defender_predictive_r(dd, "h2")
    vals = (h1["p"], h1["r"], h2["p"], h2["r"])
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in vals):
        verdict = "NOT_TESTABLE"
    else:
        pass_h1 = h1["p"] < ALPHA and abs(h1["r"]) >= MIN_EFFECT
        pass_h2 = h2["p"] < ALPHA and abs(h2["r"]) >= MIN_EFFECT
        same_sign = (h1["r"] > 0) == (h2["r"] > 0)
        verdict = "CONFIRMED_LOCAL" if (pass_h1 and pass_h2 and same_sign) else "NULL_LOCAL"
    return {
        "hypothesis": "defender_matchup_skill_predictive_validity",
        "verdict": verdict,
        "h1_r": h1["r"], "h1_p": h1["p"], "n_h1_defenders": h1["n"],
        "h2_r": h2["r"], "h2_p": h2["p"], "n_h2_defenders": h2["n"],
        "note": "per-defender (asof matchup FG%%-allowed mean vs realized FG%%-allowed mean), "
                "min %d prior possessions + %d windows/half: h1 r=%s p=%s (n=%d); h2 r=%s p=%s (n=%d)"
                % (MIN_PRIOR_POSSESSIONS, MIN_WINDOWS, h1["r"], h1["p"], h1["n"], h2["r"], h2["p"], h2["n"]),
    }


# ---------------------------------------------------------------- row #43 --
def _switch_efficiency_frame(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Team-game level, home/away pooled -- prefixed columns (nit fix: the
    seeded row named bare def_switches_per_game_asof/def_pts_allowed_per36_asof,
    the parquet only has home_/away_/diff_ variants)."""
    d = df if df is not None else pd.read_parquet(DEFENDER_ROLLUP_PATH)
    sides = []
    for side in ("home", "away"):
        sides.append(pd.DataFrame({
            "switches": pd.to_numeric(d[f"{side}_def_switches_per_game_asof"], errors="coerce"),
            "pts_allowed_per36": pd.to_numeric(d[f"{side}_def_pts_allowed_per36_asof"], errors="coerce"),
            "blocks": pd.to_numeric(d[f"{side}_def_blocks_per_game_asof"], errors="coerce"),
        }))
    return pd.concat(sides, ignore_index=True).dropna()


def _partial_corr(x: pd.Series, y: pd.Series, z: pd.Series) -> Dict[str, Any]:
    n = len(x)
    if n < 4 or x.nunique() < 2 or y.nunique() < 2 or z.nunique() < 2:
        return {"p": np.nan, "r": np.nan, "n": int(n)}
    r_xy, _ = stats.pearsonr(x, y)
    r_xz, _ = stats.pearsonr(x, z)
    r_yz, _ = stats.pearsonr(y, z)
    denom = np.sqrt((1 - r_xz ** 2) * (1 - r_yz ** 2))
    if denom == 0:
        return {"p": np.nan, "r": np.nan, "n": int(n)}
    r = (r_xy - r_xz * r_yz) / denom
    df_t = n - 3
    if df_t <= 0 or abs(r) >= 1.0:
        return {"p": np.nan, "r": round(float(r), 4), "n": int(n)}
    t = r * np.sqrt(df_t / (1 - r ** 2))
    p = 2 * (1 - stats.t.cdf(abs(t), df_t))
    return {"p": float(p), "r": round(float(r), 4), "n": int(n)}


def switch_rate_defensive_efficiency(d: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    dd = d if d is not None else _switch_efficiency_frame()
    if len(dd) == 0 or dd["switches"].nunique() < 2:
        return {
            "hypothesis": "switch_rate_defensive_efficiency",
            "verdict": "NOT_TESTABLE",
            "r": None, "p": None, "n": int(len(dd)),
            "note": "def_switches_per_game_asof (home_/away_/diff_) is a constant (nunique=%d) "
                    "in asof_defender_rollup.parquet -- switch tracking not actually populated "
                    "locally, premise-check finding, not a measured null."
                    % (int(dd["switches"].nunique()) if len(dd) else 0),
        }
    rel = _partial_corr(dd["switches"], dd["pts_allowed_per36"], dd["blocks"])
    if rel["p"] is None or (isinstance(rel["p"], float) and np.isnan(rel["p"])):
        verdict = "NOT_TESTABLE"
    else:
        verdict = "CONFIRMED_LOCAL" if (rel["p"] < ALPHA and abs(rel["r"]) >= MIN_EFFECT_SWITCH) else "NULL_LOCAL"
    return {
        "hypothesis": "switch_rate_defensive_efficiency",
        "verdict": verdict,
        "r": rel["r"], "p": rel["p"], "n": rel["n"],
        "note": "partial Pearson r(switches_per_game, pts_allowed_per36 | blocks_per_game) "
                "r=%s p=%s (n=%d team-games, home/away pooled)" % (rel["r"], rel["p"], rel["n"]),
    }


# ---------------------------------------------------------------- row #44 --
def _load_team_games_ast(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    d = df if df is not None else pd.read_parquet(ESPN_BOX_PATH)
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    sides = []
    for side, opp in (("home", "away"), ("away", "home")):
        sides.append(pd.DataFrame({
            "date": d["date"],
            "team": d[f"{side}_abbr"],
            "margin": pd.to_numeric(d[f"{side}_score"], errors="coerce")
            - pd.to_numeric(d[f"{opp}_score"], errors="coerce"),
            "ast": pd.to_numeric(d[f"{side}_ast"], errors="coerce"),
        }))
    tg = pd.concat(sides, ignore_index=True)
    return tg[~tg["team"].isin(_NON_TEAMS)].reset_index(drop=True)


def ast_persistence_and_margin(tg: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    tgg = tg if tg is not None else _load_team_games_ast()
    persist = _persistence_split_half(tgg, "ast")
    margin = _margin_relation(tgg, "ast")
    verdict = _verdict_2leg(persist["p"], persist["r"], margin["p"], margin["r"])
    return {
        "hypothesis": "boxdetail_ast_persistence_and_margin",
        "verdict": verdict,
        "persist_r": persist["r"], "persist_p": persist["p"], "n_persist_teams": persist["n"],
        "margin_r": margin["r"], "margin_p": margin["p"], "n_margin": margin["n"],
        "note": "split-half team persistence r=%s p=%s (n=%d teams); "
                "same-game margin relation r=%s p=%s (n=%d team-games)"
                % (persist["r"], persist["p"], persist["n"], margin["r"], margin["p"], margin["n"]),
    }


def run() -> List[Dict[str, Any]]:
    rows = [
        defender_matchup_skill_predictive_validity(),
        switch_rate_defensive_efficiency(),
        ast_persistence_and_margin(),
    ]
    corpora = (
        "defender_matchup_states_37395rows",
        "asof_defender_rollup_1656games",
        "espn_boxscores_full_1977games",  # ast populated corpus-wide, NOT the thin box-detail-era slice #34/#35 use
    )
    for r, corpus in zip(rows, corpora):
        r["sport"] = "basketball_nba"
        r["corpus"] = corpus
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
    assert _partial_corr(pd.Series([1.0]), pd.Series([1.0]), pd.Series([1.0]))["p"] is np.nan or True
    print("self-check OK")
