"""domains.tennis.knowledge.validate_match_population -- 7 UNTESTED
match-level mechanisms (mechanisms.md #17 prior-match-duration fatigue, #18
clay/grass specialization persistence, #21 upset-rate by round, #22
retirement-rate by round/surface, #24 H2H recency bias, #25 height x surface
interaction, #27 best-of-5 vs best-of-3 upset rate) against the 2015-2025
ATP+WTA match corpus. Leak audit: every as-of lookup (prior match, prior H2H)
uses only matches strictly BEFORE the target event_id's date, sorted per
player/pair; height/hand are static attributes. `players.parquet` is
ATP-only (confirmed landmine, see reference memory) -- height-dependent test
#25 silently restricts to ATP via the same NaN-filter pattern already used
by `validate_match_outcomes.py::lefty_advantage_on_return`.

Run: python -m domains.tennis.knowledge.validate_match_population
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, load_matches, load_players
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _long_format(m: pd.DataFrame) -> pd.DataFrame:
    """One row per (event_id, player) perspective: player_id, opp_id, date,
    win, minutes, surface, round, best_of."""
    d = m.dropna(subset=["winner", "date"]).copy()
    d["date"] = pd.to_datetime(d["date"])
    a = d.rename(columns={"p1_id": "player_id", "p2_id": "opp_id"}).assign(win=(d["winner"] == 1).astype(int))
    b = d.rename(columns={"p2_id": "player_id", "p1_id": "opp_id"}).assign(win=(d["winner"] == 2).astype(int))
    cols = ["event_id", "date", "player_id", "opp_id", "win", "minutes", "surface", "round", "best_of"]
    return pd.concat([a[cols], b[cols]], ignore_index=True).sort_values(["player_id", "date"])


def prior_match_duration_fatigue(m: pd.DataFrame) -> Dict[str, Any]:
    long = _long_format(m).dropna(subset=["minutes"])
    long["prior_minutes"] = long.groupby("player_id")["minutes"].shift(1)
    d = long.dropna(subset=["prior_minutes"])
    long_prior = d[d["prior_minutes"] >= 150]["win"]
    short_prior = d[d["prior_minutes"] < 150]["win"]
    t, p = stats.ttest_ind(long_prior, short_prior, equal_var=False)
    eff = float(long_prior.mean() - short_prior.mean())
    return {"hypothesis": "prior_match_duration_fatigue", "n": int(len(long_prior) + len(short_prior)),
            "effect": round(eff, 4), "p": float(p), "verdict": _verdict(p, 0.01, eff),
            "note": "win-rate after a >=150min prior match (%.4f, n=%d) vs <150min (%.4f, n=%d)"
                    % (long_prior.mean(), len(long_prior), short_prior.mean(), len(short_prior))}


def clay_grass_specialization_persistence(m: pd.DataFrame) -> Dict[str, Any]:
    long = _long_format(m)
    mid = long["date"].median()
    long["half"] = np.where(long["date"] < mid, "A", "B")
    diffs = {}
    for half in ("A", "B"):
        h = long[long["half"] == half]
        cnt = h.groupby(["player_id", "surface"])["win"].agg(["mean", "size"]).unstack("surface")
        clay_ok = cnt[("size", "Clay")] >= 5 if ("size", "Clay") in cnt.columns else pd.Series(dtype=bool)
        hard_ok = cnt[("size", "Hard")] >= 5 if ("size", "Hard") in cnt.columns else pd.Series(dtype=bool)
        ok = (clay_ok & hard_ok).fillna(False)
        diff = (cnt[("mean", "Clay")] - cnt[("mean", "Hard")])[ok]
        diffs[half] = diff
    piv = pd.concat([diffs["A"].rename("A"), diffs["B"].rename("B")], axis=1).dropna()
    if len(piv) < 15:
        return {"hypothesis": "clay_grass_specialization_persistence", "n": int(len(piv)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 15 players with >=5 Clay AND >=5 Hard matches in BOTH date-halves"}
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "clay_grass_specialization_persistence", "n": int(len(piv)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.1, r),
            "note": "split-half pearson r, player Clay-minus-Hard win-rate, n=%d players" % len(piv)}


def _upset_frame(m: pd.DataFrame) -> pd.DataFrame:
    d = m.dropna(subset=["p1_rank", "p2_rank", "winner"]).copy()
    d["rank_diff"] = d["p2_rank"] - d["p1_rank"]  # positive => p1 favored
    d = d[d["rank_diff"] != 0]
    d["upset"] = np.where(d["rank_diff"] > 0, d["winner"] == 2, d["winner"] == 1).astype(int)
    return d


def upset_rate_by_round(m: pd.DataFrame) -> Dict[str, Any]:
    d = _upset_frame(m)
    tab = pd.crosstab(d["round"], d["upset"])
    tab = tab[tab.sum(axis=1) >= 30]
    chi2, p, dof, _ = stats.chi2_contingency(tab)
    rates = (tab[1] / tab.sum(axis=1)).sort_values()
    eff = float(rates.max() - rates.min())
    return {"hypothesis": "upset_rate_by_round", "n": int(tab.values.sum()), "effect": round(eff, 4),
            "p": float(p), "verdict": _verdict(p, 0.03, eff),
            "note": "upset rate by round: %s" % rates.round(4).to_dict()}


def retirement_rate_by_round_and_surface(m: pd.DataFrame) -> Dict[str, Any]:
    d = m.dropna(subset=["retirement"]).copy()
    tab_r = pd.crosstab(d["round"], d["retirement"])
    tab_r = tab_r[tab_r.sum(axis=1) >= 30]
    chi2_r, p_r, _, _ = stats.chi2_contingency(tab_r)
    tab_s = pd.crosstab(d["surface"], d["retirement"])
    tab_s = tab_s[tab_s.sum(axis=1) >= 30]
    chi2_s, p_s, _, _ = stats.chi2_contingency(tab_s)
    rates_s = (tab_s[True] / tab_s.sum(axis=1)) if True in tab_s.columns else pd.Series(dtype=float)
    eff = float(rates_s.max() - rates_s.min()) if len(rates_s) else 0.0
    p_min = min(p_r, p_s)
    return {"hypothesis": "retirement_rate_by_round_and_surface", "n": int(len(d)), "effect": round(eff, 4),
            "p": float(p_min), "verdict": _verdict(p_min, 0.01, eff),
            "note": "retirement-rate chi2 by round p=%.4g; by surface p=%.4g, surface rates: %s"
                    % (p_r, p_s, rates_s.round(4).to_dict())}


def h2h_recency_vs_ranking(m: pd.DataFrame) -> Dict[str, Any]:
    """As-of prior head-to-head win-rate for p1 against THIS SPECIFIC p2,
    from matches strictly before the current date only. `history[(p, o)]`
    holds p's own past results vs o, updated symmetrically after each match
    so both players' logs stay consistent -- no canonical-pair-order bookkeeping
    needed."""
    d = _with_rank_diff_local(m).sort_values("date")
    history: Dict[tuple, List[int]] = {}
    prior_rate, n_prior = [], []
    for _, row in d.iterrows():
        key = (row["p1_id"], row["p2_id"])
        hist = history.get(key, [])
        n_prior.append(len(hist))
        prior_rate.append(float(np.mean(hist)) if hist else np.nan)
        history.setdefault((row["p1_id"], row["p2_id"]), []).append(int(row["p1_win"]))
        history.setdefault((row["p2_id"], row["p1_id"]), []).append(1 - int(row["p1_win"]))
    d["n_prior_meetings"] = n_prior
    d["prior_h2h_rate_p1"] = prior_rate
    dd = d[d["n_prior_meetings"] >= 3].dropna(subset=["prior_h2h_rate_p1"])
    if len(dd) < 30:
        return {"hypothesis": "h2h_recency_vs_ranking", "n": int(len(dd)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "fewer than 30 matches with >=3 prior meetings between "
                                                    "the same pair -- corpus is too sparse for repeat matchups"}
    res = smf.logit("p1_win ~ prior_h2h_rate_p1 + rank_diff", data=dd).fit(disp=0)
    eff = float(res.params["prior_h2h_rate_p1"])
    p = float(res.pvalues["prior_h2h_rate_p1"])
    return {"hypothesis": "h2h_recency_vs_ranking", "n": int(len(dd)), "effect": round(eff, 4), "p": p,
            "verdict": _verdict(p, 0.1, eff),
            "note": "logit p1_win ~ prior_h2h_rate_p1 + rank_diff, prior-H2H coef=%.4f, n=%d (>=3 prior "
                    "meetings floor)" % (eff, len(dd))}


def _with_rank_diff_local(m: pd.DataFrame) -> pd.DataFrame:
    d = m.dropna(subset=["p1_rank", "p2_rank", "winner", "date"]).copy()
    d["date"] = pd.to_datetime(d["date"])
    d["rank_diff"] = d["p2_rank"] - d["p1_rank"]
    d["p1_win"] = (d["winner"] == 1).astype(int)
    return d


def height_x_surface_interaction(m: pd.DataFrame, players: pd.DataFrame) -> Dict[str, Any]:
    d = _with_rank_diff_local(m)
    ht = players.set_index("player_id")["height"]
    d["h1"], d["h2"] = d["p1_id"].map(ht), d["p2_id"].map(ht)
    d = d.dropna(subset=["h1", "h2"])
    d["height_diff"] = d["h1"] - d["h2"]
    d = d[d["surface"].isin(["Grass", "Clay"])].copy()
    d["is_grass"] = (d["surface"] == "Grass").astype(int)
    res = smf.logit("p1_win ~ height_diff * is_grass", data=d).fit(disp=0)
    term = "height_diff:is_grass"
    eff = float(res.params[term])
    p = float(res.pvalues[term])
    return {"hypothesis": "height_x_surface_interaction", "n": int(len(d)), "effect": round(eff, 5), "p": p,
            "verdict": _verdict(p, 0.005, eff),
            "note": "logit p1_win ~ height_diff*is_grass (ATP-only, height join), interaction coef=%.5f, "
                    "n=%d (Grass+Clay matches only)" % (eff, len(d))}


def best_of_5_vs_3_upset_rate(m: pd.DataFrame) -> Dict[str, Any]:
    d = _upset_frame(m)
    d["abs_rank_diff"] = d["rank_diff"].abs()
    d["bo5"] = (d["best_of"] == 5).astype(int)
    res = smf.logit("upset ~ bo5 + abs_rank_diff", data=d).fit(disp=0)
    eff = float(res.params["bo5"])
    p = float(res.pvalues["bo5"])
    return {"hypothesis": "best_of_5_vs_3_upset_rate", "n": int(len(d)), "effect": round(eff, 4), "p": p,
            "verdict": _verdict(p, 0.05, eff),
            "note": "logit upset ~ best_of==5 + |rank_diff|, bo5 coef=%.4f, n=%d" % (eff, len(d))}


def run() -> List[Dict[str, Any]]:
    m = load_matches()
    players = load_players()
    rows = [prior_match_duration_fatigue(m), clay_grass_specialization_persistence(m),
            upset_rate_by_round(m), retirement_rate_by_round_and_surface(m),
            h2h_recency_vs_ranking(m), height_x_surface_interaction(m, players),
            best_of_5_vs_3_upset_rate(m)]
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = "matches_atp_wta_2015_2025"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-34s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    print("self-check OK")
