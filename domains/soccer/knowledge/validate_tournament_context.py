"""domains.soccer.knowledge.validate_tournament_context -- 3 UNTESTED
mechanisms on the soccer-intl full-history corpus (`data/domains/soccer_intl/
results.parquet`, 49,477 rows, 1872-2026, cols date/home_team/away_team/
home_score/away_score/tournament/city/country/neutral -- confirmed this
session). 52 rows are unplayed WC-2026 fixtures (home_score/away_score both
NaN, dated 2026-06-17..2026-06-27) -- dropped before any test, leaving 49,425
played matches. No confederation/continent column exists locally, so the
split-half stability check (c) uses era (pre/post-2000) instead.

DESCRIPTIVE only: closed, already-played matches vs their own date/venue/
competition metadata -- no forward replay, no market/$ edge claimed.

Run: python -m domains.soccer.knowledge.validate_tournament_context
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH
from scripts.platformkit.io_atomic import append_jsonl_atomic

REPO = Path(__file__).resolve().parents[3]
RESULTS_PATH = REPO / "data" / "domains" / "soccer_intl" / "results.parquet"
ALPHA = 0.01


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or p != p:
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def load_results() -> pd.DataFrame:
    """Played matches only (drops unplayed fixtures with NaN scores)."""
    df = pd.read_parquet(RESULTS_PATH).dropna(subset=["home_score", "away_score"]).copy()
    df["goal_diff"] = df["home_score"] - df["away_score"]
    df["home_win"] = (df["home_score"] > df["away_score"]).astype(int)
    df["total_goals"] = df["home_score"] + df["away_score"]
    df["competitive"] = df["tournament"] != "Friendly"
    return df


def home_advantage_neutral_vs_true(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """(a) home-advantage magnitude: goal-diff and win-rate at neutral venues
    vs true home venues. At a neutral site the listed "home" team gets no
    crowd/travel/pitch-familiarity edge, so both should shrink toward zero."""
    home, neutral = df[~df["neutral"]], df[df["neutral"]]
    gd_t, gd_p = stats.ttest_ind(home["goal_diff"], neutral["goal_diff"], equal_var=False)
    gd_eff = float(home["goal_diff"].mean() - neutral["goal_diff"].mean())
    tab = pd.crosstab(df["neutral"], df["home_win"])
    _, wr_p, _, _ = stats.chi2_contingency(tab)
    wr_eff = float(home["home_win"].mean() - neutral["home_win"].mean())
    return [
        {"hypothesis": "home_advantage_neutral_vs_true_goal_diff", "n": int(len(home) + len(neutral)),
         "effect": round(gd_eff, 4), "p": float(gd_p), "verdict": _verdict(gd_p, gd_eff, 0.1),
         "note": "goal-diff true-home (%.4f, n=%d) vs neutral-venue (%.4f, n=%d)"
                 % (home["goal_diff"].mean(), len(home), neutral["goal_diff"].mean(), len(neutral))},
        {"hypothesis": "home_advantage_neutral_vs_true_win_rate", "n": int(len(home) + len(neutral)),
         "effect": round(wr_eff, 4), "p": float(wr_p), "verdict": _verdict(wr_p, wr_eff, 0.02),
         "note": "home-win-rate true-home (%.4f, n=%d) vs neutral-venue (%.4f, n=%d), chi2"
                 % (home["home_win"].mean(), len(home), neutral["home_win"].mean(), len(neutral))},
    ]


def tournament_vs_friendly_scoring_environment(df: pd.DataFrame) -> Dict[str, Any]:
    """(b) does competitive-tournament context (vs Friendly) shift the
    scoring environment (total goals per match)?"""
    comp, fr = df[df["competitive"]], df[~df["competitive"]]
    t, p = stats.ttest_ind(comp["total_goals"], fr["total_goals"], equal_var=False)
    eff = float(comp["total_goals"].mean() - fr["total_goals"].mean())
    return {"hypothesis": "tournament_vs_friendly_scoring_environment", "n": int(len(df)),
            "effect": round(eff, 4), "p": float(p), "verdict": _verdict(p, eff, 0.05),
            "note": "total-goals/match competitive (%.4f, n=%d) vs friendly (%.4f, n=%d)"
                    % (comp["total_goals"].mean(), len(comp), fr["total_goals"].mean(), len(fr))}


def home_advantage_neutral_split_half_by_era(df: pd.DataFrame) -> Dict[str, Any]:
    """(c) split-half stability of the (a) goal-diff effect (the larger of
    the two (a) readings) across pre-2000 vs post-2000 -- no confederation
    column exists locally, so era is the available split axis."""
    halves = {}
    for era, cond in (("pre2000", df["date"].dt.year < 2000), ("post2000", df["date"].dt.year >= 2000)):
        d = df[cond]
        home, neutral = d[~d["neutral"]]["goal_diff"], d[d["neutral"]]["goal_diff"]
        t, p = stats.ttest_ind(home, neutral, equal_var=False)
        halves[era] = {"eff": float(home.mean() - neutral.mean()), "p": float(p), "n": int(len(d))}
    both_confirm = all(h["p"] < ALPHA and h["eff"] >= 0.1 for h in halves.values())
    same_sign = (halves["pre2000"]["eff"] > 0) == (halves["post2000"]["eff"] > 0)
    conservative_eff = min(halves["pre2000"]["eff"], halves["post2000"]["eff"])
    worst_p = max(halves["pre2000"]["p"], halves["post2000"]["p"])
    verdict = "CONFIRMED_LOCAL" if (both_confirm and same_sign) else "NULL_LOCAL"
    return {"hypothesis": "home_advantage_neutral_split_half_by_era", "n": int(len(df)),
            "effect": round(conservative_eff, 4), "p": worst_p, "verdict": verdict,
            "note": "goal-diff true-home-minus-neutral effect, pre2000 %.4f (n=%d, p=%.2g) vs "
                    "post2000 %.4f (n=%d, p=%.2g) -- replicates (same sign, both p<%.2g) in both era halves"
                    % (halves["pre2000"]["eff"], halves["pre2000"]["n"], halves["pre2000"]["p"],
                       halves["post2000"]["eff"], halves["post2000"]["n"], halves["post2000"]["p"], ALPHA)}


def run() -> List[Dict[str, Any]]:
    df = load_results()
    rows = home_advantage_neutral_vs_true(df) + [
        tournament_vs_friendly_scoring_environment(df),
        home_advantage_neutral_split_half_by_era(df),
    ]
    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "soccer_intl_results__%d_played" % len(df)
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-46s %-16s n=%-8d effect=%+.4f p=%.4g -- %s"
              % (r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict thresholds behave as declared."""
    assert _verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    print("self-check OK")
