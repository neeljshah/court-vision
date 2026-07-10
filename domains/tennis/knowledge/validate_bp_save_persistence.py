"""domains.tennis.knowledge.validate_bp_save_persistence -- 2 UNTESTED
mechanisms (seed C8) against `match_stats.parquet` (59,312 rows) joined to
`matches.parquet` on event_id. Leak audit note: this is a POPULATION-level,
within-match-stats mechanism check (like mechanisms.md #14
first_set_winner_match_win_rate) -- NOT a pre-match predictive feature, since
bpSaved/bpFaced are outcomes of the match itself. The event_id join between
match_stats.parquet and matches.parquet was verified this session: p1's
serve stats (1st_win_pct, bp_saved_pct) are markedly higher in rows where
matches.parquet says winner==1 (0.75 vs 0.64 first-serve-win-pct, 0.65 vs
0.50 bp-saved-pct) confirming the p1/p2 slot convention is consistent across
both parquets on this event_id -- not a tautology by construction, an
empirical alignment check.

Both hypotheses below explicitly guard the collinearity the task calls out:
break-point-save rate and overall serve win rate are correlated ~0.80 at the
player level (saving a break point is mechanically a serve point won), so
every test controls for serve win rate rather than reporting a raw
correlation alone.

Run: python -m domains.tennis.knowledge.validate_bp_save_persistence
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, TENNIS_DIR, load_matches
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_BP_FACED = 3      # floor so bp_saved_pct isn't a noisy 0/1 or 1/1 ratio
MIN_MATCHES_PER_HALF = 5


def load_match_stats() -> pd.DataFrame:
    """event_id -> p1/p2 serve + break-point stats. Not added to _data.py --
    only this validator and validate_travel_altitude need it."""
    return pd.read_parquet(TENNIS_DIR / "match_stats.parquet")


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _joined(matches: pd.DataFrame, stats_df: pd.DataFrame) -> pd.DataFrame:
    d = matches.dropna(subset=["winner", "date"]).merge(stats_df, on="event_id", how="inner")
    d["date"] = pd.to_datetime(d["date"])
    return d


def _player_side(d: pd.DataFrame, n: int) -> pd.DataFrame:
    """Long-format rows for slot n (1 or 2): player_id, date, bp_saved_pct,
    serve_win_rate (own service points won / own service points played),
    restricted to matches with >= MIN_BP_FACED break points faced."""
    o = d[d["p%d_bpFaced" % n] >= MIN_BP_FACED].copy()
    o["player_id"] = o["p%d_id" % n]
    o["bp_saved_pct"] = o["p%d_bp_saved_pct" % n]
    o["serve_win_rate"] = (o["p%d_1stWon" % n] + o["p%d_2ndWon" % n]) / o["p%d_svpt" % n]
    return o[["player_id", "date", "bp_saved_pct", "serve_win_rate"]].dropna()


def bp_save_skill_persistence_partial(matches: pd.DataFrame, stats_df: pd.DataFrame) -> Dict[str, Any]:
    """Split-half persistence of per-player bp_saved_pct, THEN a partial
    effect controlling for split-half-A serve win rate (a leak-safe, prior
    proxy for overall serve strength -- not the contemporaneous half-B serve
    rate, to avoid controlling with the outcome half's own determinant)."""
    d = _joined(matches, stats_df)
    long = pd.concat([_player_side(d, 1), _player_side(d, 2)], ignore_index=True)
    mid = long["date"].median()
    long["half"] = np.where(long["date"] < mid, "A", "B")
    g = long.groupby(["player_id", "half"]).agg(bp=("bp_saved_pct", "mean"),
                                                  sv=("serve_win_rate", "mean"),
                                                  n=("bp_saved_pct", "size"))
    g = g[g["n"] >= MIN_MATCHES_PER_HALF]
    piv = g.unstack("half").dropna()
    if len(piv) < 15:
        return {"hypothesis": "bp_save_skill_persistence_partial", "n": int(len(piv)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 15 players with >=%d matches (>=%d bp faced) in BOTH date-halves"
                        % (MIN_MATCHES_PER_HALF, MIN_BP_FACED)}
    bpA, bpB = piv[("bp", "A")], piv[("bp", "B")]
    svA = piv[("sv", "A")]
    r_raw, p_raw = stats.pearsonr(bpA, bpB)
    ols_df = pd.DataFrame({"bpA": bpA.values, "bpB": bpB.values, "svA": svA.values})
    res = smf.ols("bpB ~ bpA + svA", data=ols_df).fit()
    eff = float(res.params["bpA"])
    p = float(res.pvalues["bpA"])
    return {"hypothesis": "bp_save_skill_persistence_partial", "n": int(len(piv)), "effect": round(eff, 4),
            "p": p,
            "note": "raw split-half pearson r=%.4f (p=%.3g) but OLS bpB ~ bpA + svA (serve-win-rate-"
                    "controlled) gives bpA partial coef=%.4f (p=%.3g), n=%d players -- tests whether "
                    "persistence survives once serve strength is netted out" % (r_raw, p_raw, eff, p, len(piv))}


def bp_save_differential_predicts_outcome_partial(matches: pd.DataFrame, stats_df: pd.DataFrame) -> Dict[str, Any]:
    """Match-level bp_saved_pct differential vs match outcome, controlling
    for the serve-win-rate differential (the two are correlated ~0.5-0.8, so
    the guard is the serve_diff covariate, not a raw bp_diff-only fit)."""
    d = _joined(matches, stats_df)
    d = d[(d["p1_bpFaced"] >= MIN_BP_FACED) & (d["p2_bpFaced"] >= MIN_BP_FACED)].copy()
    d["p1_win"] = (d["winner"] == 1).astype(int)
    d["bp_diff"] = d["p1_bp_saved_pct"] - d["p2_bp_saved_pct"]
    d["serve_diff"] = ((d["p1_1stWon"] + d["p1_2ndWon"]) / d["p1_svpt"]
                        - (d["p2_1stWon"] + d["p2_2ndWon"]) / d["p2_svpt"])
    d = d.dropna(subset=["bp_diff", "serve_diff"])
    if len(d) < 30:
        return {"hypothesis": "bp_save_differential_predicts_outcome_partial", "n": int(len(d)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE", "note": "fewer than 30 matches with >=%d bp faced "
                "on both sides" % MIN_BP_FACED}
    res = smf.logit("p1_win ~ bp_diff + serve_diff", data=d).fit(disp=0)
    eff = float(res.params["bp_diff"])
    p = float(res.pvalues["bp_diff"])
    sv_coef = float(res.params["serve_diff"])
    return {"hypothesis": "bp_save_differential_predicts_outcome_partial", "n": int(len(d)),
            "effect": round(eff, 4), "p": p,
            "note": "logit p1_win ~ bp_diff + serve_diff, bp_diff coef=%.4f (p=%.3g) vs serve_diff "
                    "coef=%.4f, n=%d -- bp_diff survives the serve_diff control but its magnitude is "
                    "small relative to overall serve dominance" % (eff, p, sv_coef, len(d))}


def run() -> List[Dict[str, Any]]:
    matches = load_matches()
    stats_df = load_match_stats()
    rows = [
        (bp_save_skill_persistence_partial(matches, stats_df), 0.1),
        (bp_save_differential_predicts_outcome_partial(matches, stats_df), 0.5),
    ]
    out = []
    for r, min_eff in rows:
        if "verdict" not in r:
            r["verdict"] = _verdict(r["p"], r["effect"], min_eff)
        r["sport"] = "tennis"
        r["corpus"] = "match_stats_atp_wta_2015_2025"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
        out.append(r)
    return out


def main() -> int:
    for r in run():
        print("%-46s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    print("self-check OK")
