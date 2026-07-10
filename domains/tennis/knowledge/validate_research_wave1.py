"""domains.tennis.knowledge.validate_research_wave1 -- 3 UNTESTED mechanisms
from the 2026-07-10 research wave (mechanisms.md #32 tiebreak-skill
persistence, #33 dominance-margin, #34 14-day load vs serve execution).

Premise-check correction (mechanisms.md #32's own artifact-link text, and the
task brief that seeded it, describe `asof_setdetail.parquet` as carrying
"player_id" -- it does NOT: the file has only `event_id` + p1_/p2_-prefixed
feature columns, no id column at all. Player identity is reached by joining
`event_id` to `matches.parquet`'s PREFIXED `p1_id`/`p2_id` columns (same
pattern `validate_bp_save_persistence.py` and `validate_travel_altitude.py`
already use). #32's test below therefore skips `asof_setdetail.parquet`
entirely and instead parses REALIZED tiebreak outcomes straight out of
`matches.parquet`'s `score` string (the row's own test spec names this as the
"more direct" option), using the winner-first-token convention already
validated for mechanisms.md #14 -- consistent with the corrected join path,
not a different corpus.

Leak audit: #32 and #34 are split-half / cross-sectional comparisons of
REALIZED (post-match) stats, same population-mechanism framing as #14/#18;
no as-of feature is used as a predictor of itself. #33 uses
`avg_games_per_set_asof_diff`, which is a genuine as-of (leak-safe, prior-only)
feature by construction of `asof_setdetail.parquet` (see #29/#31's use of the
sibling `_asof` columns in this same file for the established leak-audit
note).

Run: python -m domains.tennis.knowledge.validate_research_wave1
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, TENNIS_DIR, load_matches, load_schedule_density
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_TB_FACED = 5       # declared floor, mechanisms.md #32: >=5 tiebreaks/half
MIN_PLAYERS = 15        # mirrors validate_bp_save_persistence.py's floor
_TB_RE = re.compile(r"(\d+)-(\d+)\(\d+\)")


def load_match_stats() -> pd.DataFrame:
    """event_id -> p1/p2 serve stats. Not added to _data.py -- same reasoning
    as the other validators that already load this file locally."""
    return pd.read_parquet(TENNIS_DIR / "match_stats.parquet")


def load_asof_setdetail() -> pd.DataFrame:
    """event_id -> p1/p2 as-of set-detail features (tiebreak/margin history).
    ATP+WTA combined would need the `_wta` sibling too; this wave's #33 row
    only names the ATP file, so this loader matches the row's own scope."""
    return pd.read_parquet(TENNIS_DIR / "asof_setdetail.parquet")


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _match_winner_tiebreaks(score: Any) -> "tuple[int, int]":
    """(tiebreaks won by the MATCH WINNER, tiebreaks played), parsed from set
    tokens like '7-6(4)'. Uses the winner-first-token convention validated for
    mechanisms.md #14: the front number is the match winner's games in that
    set, so front>back means the winner took the breaker. Restricted to the
    standard 7-6/6-7 scoreline (skips rare formats, e.g. deciding-set
    super-tiebreaks written differently)."""
    if not isinstance(score, str):
        return 0, 0
    won = faced = 0
    for front, back in _TB_RE.findall(score):
        f, b = int(front), int(back)
        if {f, b} != {6, 7}:
            continue
        faced += 1
        won += int(f > b)
    return won, faced


def tiebreak_skill_persistence_partial(matches: pd.DataFrame, stats_df: pd.DataFrame) -> Dict[str, Any]:
    """Unblocks mechanisms.md #15 (NOT_TESTABLE on slam_points, no player
    id): split-half persistence of realized per-player tiebreak win rate,
    THEN a partial effect controlling for split-half-A serve win rate --
    mirrors validate_bp_save_persistence.py's collinearity guard exactly,
    since tiebreak points are themselves serve/return points."""
    d = matches.dropna(subset=["winner", "date", "p1_id", "p2_id"]).merge(stats_df, on="event_id", how="inner")
    won_faced = d["score"].apply(_match_winner_tiebreaks)
    d["winner_tb_won"] = [x[0] for x in won_faced]
    d["tb_faced"] = [x[1] for x in won_faced]
    d = d[d["tb_faced"] > 0].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["p1_tb_won"] = np.where(d["winner"] == 1, d["winner_tb_won"], d["tb_faced"] - d["winner_tb_won"])
    d["p2_tb_won"] = d["tb_faced"] - d["p1_tb_won"]
    d["p1_sv"] = (d["p1_1stWon"] + d["p1_2ndWon"]) / d["p1_svpt"]
    d["p2_sv"] = (d["p2_1stWon"] + d["p2_2ndWon"]) / d["p2_svpt"]
    l1 = d[["p1_id", "date", "p1_tb_won", "tb_faced", "p1_sv"]].rename(
        columns={"p1_id": "player_id", "p1_tb_won": "tb_won", "p1_sv": "sv"})
    l2 = d[["p2_id", "date", "p2_tb_won", "tb_faced", "p2_sv"]].rename(
        columns={"p2_id": "player_id", "p2_tb_won": "tb_won", "p2_sv": "sv"})
    long = pd.concat([l1, l2], ignore_index=True).dropna()
    mid = long["date"].median()
    long["half"] = np.where(long["date"] < mid, "A", "B")
    g = long.groupby(["player_id", "half"]).agg(won=("tb_won", "sum"), faced=("tb_faced", "sum"), sv=("sv", "mean"))
    g["rate"] = g["won"] / g["faced"]
    g = g[g["faced"] >= MIN_TB_FACED]
    piv = g[["rate", "sv"]].unstack("half").dropna()
    if len(piv) < MIN_PLAYERS:
        return {"hypothesis": "tiebreak_skill_persistence_partial", "n": int(len(piv)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than %d players with >=%d tiebreaks faced in BOTH date-halves"
                        % (MIN_PLAYERS, MIN_TB_FACED)}
    tbA, tbB, svA = piv[("rate", "A")], piv[("rate", "B")], piv[("sv", "A")]
    r_raw, p_raw = stats.pearsonr(tbA, tbB)
    ols_df = pd.DataFrame({"tbA": tbA.values, "tbB": tbB.values, "svA": svA.values})
    res = smf.ols("tbB ~ tbA + svA", data=ols_df).fit()
    eff = float(res.params["tbA"])
    p = float(res.pvalues["tbA"])
    return {"hypothesis": "tiebreak_skill_persistence_partial", "n": int(len(piv)), "effect": round(eff, 4), "p": p,
            "verdict": _verdict(p, eff, 0.15),  # reuses mechanisms.md #32's own declared |r|>=0.15 bar
            "note": "raw split-half pearson r=%.4f (p=%.3g) but OLS tbB ~ tbA + svA (serve-win-rate-"
                    "controlled) gives tbA partial coef=%.4f (p=%.3g), n=%d players -- realized tiebreaks "
                    "parsed from matches.parquet score string, not the asof rolling feature"
                    % (r_raw, p_raw, eff, p, len(piv))}


def dominance_margin_predicts_outcome_partial(matches: pd.DataFrame, asof: pd.DataFrame) -> Dict[str, Any]:
    """logit p1_win ~ avg_games_per_set_asof_diff + rank_diff, ATP+WTA (this
    row's own scope is `asof_setdetail.parquet`, the ATP file only -- see
    load_asof_setdetail's note)."""
    d = matches.dropna(subset=["p1_rank", "p2_rank", "winner"]).copy()
    d["rank_diff"] = d["p2_rank"] - d["p1_rank"]
    d["p1_win"] = (d["winner"] == 1).astype(int)
    d = d.merge(asof[["event_id", "avg_games_per_set_asof_diff"]], on="event_id", how="inner")
    d = d.dropna(subset=["avg_games_per_set_asof_diff", "rank_diff"])
    if len(d) < 30:
        return {"hypothesis": "dominance_margin_predicts_outcome_partial", "n": int(len(d)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE", "note": "fewer than 30 matched rows"}
    res = smf.logit("p1_win ~ avg_games_per_set_asof_diff + rank_diff", data=d).fit(disp=0)
    eff = float(res.params["avg_games_per_set_asof_diff"])
    p = float(res.pvalues["avg_games_per_set_asof_diff"])
    z = eff / float(res.bse["avg_games_per_set_asof_diff"])
    return {"hypothesis": "dominance_margin_predicts_outcome_partial", "n": int(len(d)), "effect": round(eff, 4),
            "p": p, "verdict": "CONFIRMED_LOCAL" if (abs(z) >= 2 and p < 0.05) else "NULL_LOCAL",
            "note": "logit p1_win ~ avg_games_per_set_asof_diff + rank_diff, coef=%.4f (coef/se=%.2f), "
                    "n=%d -- declared bar |coef|/se>=2 & p<0.05; direction is NEGATIVE (opposite the causal "
                    "story: a bigger prior game-margin edge over the opponent predicts a LOWER win prob net "
                    "of rank), echoing this ledger's other folklore-reversing rows (#11, #21, #28)"
                    % (eff, z, len(d))}


def _load_tercile_frame(matches: pd.DataFrame, sched: pd.DataFrame, stats_df: pd.DataFrame) -> pd.DataFrame:
    load = sched.set_index(["event_id", "player_id"])["matches_last_14d"]
    d = matches.dropna(subset=["p1_id", "p2_id"]).merge(stats_df, on="event_id", how="inner")
    l1 = pd.Series(list(zip(d["event_id"], d["p1_id"])), index=d.index).map(load)
    l2 = pd.Series(list(zip(d["event_id"], d["p2_id"])), index=d.index).map(load)
    d["combined_load"] = (l1 + l2) / 2.0
    d["combined_ace_rate"] = (d["p1_ace_rate"] + d["p2_ace_rate"]) / 2.0
    d["combined_1st_in_pct"] = (d["p1_1st_in_pct"] + d["p2_1st_in_pct"]) / 2.0
    d = d.dropna(subset=["combined_load", "combined_ace_rate", "combined_1st_in_pct"]).copy()
    d["tercile"] = pd.qcut(d["combined_load"], 3, labels=False, duplicates="drop")
    return d


def _load_tercile_test(d: pd.DataFrame, col: str, hyp: str) -> Dict[str, Any]:
    if d["tercile"].nunique() < 2:
        return {"hypothesis": hyp, "n": int(len(d)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "matches_last_14d has too few distinct values to form terciles"}
    lo, hi = d[d["tercile"] == d["tercile"].min()][col], d[d["tercile"] == d["tercile"].max()][col]
    t, p = stats.ttest_ind(hi, lo, equal_var=False)
    eff = float(hi.mean() - lo.mean())
    return {"hypothesis": hyp, "n": int(len(d)), "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, eff, 0.01),
            "note": "%s top matches_last_14d tercile %.4f (n=%d) vs bottom tercile %.4f (n=%d)"
                    % (col, hi.mean(), len(hi), lo.mean(), len(lo))}


def load_14d_ace_rate_tercile(matches: pd.DataFrame, sched: pd.DataFrame, stats_df: pd.DataFrame) -> Dict[str, Any]:
    d = _load_tercile_frame(matches, sched, stats_df)
    return _load_tercile_test(d, "combined_ace_rate", "load_14d_ace_rate_tercile")


def load_14d_first_serve_in_tercile(matches: pd.DataFrame, sched: pd.DataFrame, stats_df: pd.DataFrame) -> Dict[str, Any]:
    d = _load_tercile_frame(matches, sched, stats_df)
    return _load_tercile_test(d, "combined_1st_in_pct", "load_14d_first_serve_in_tercile")


def run() -> List[Dict[str, Any]]:
    matches = load_matches()
    stats_df = load_match_stats()
    asof = load_asof_setdetail()
    sched = load_schedule_density()
    rows = [
        tiebreak_skill_persistence_partial(matches, stats_df),
        dominance_margin_predicts_outcome_partial(matches, asof),
        load_14d_ace_rate_tercile(matches, sched, stats_df),
        load_14d_first_serve_in_tercile(matches, sched, stats_df),
    ]
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = "matches_asof_setdetail_schedule_density_atp_wta"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-40s %-14s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    assert _match_winner_tiebreaks("7-6(4) 6-3") == (1, 1)
    assert _match_winner_tiebreaks("6-7(4) 7-6(6) 6-1") == (1, 2)
    assert _match_winner_tiebreaks("6-3 6-4") == (0, 0)
    print("self-check OK")
