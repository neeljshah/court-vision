"""domains.basketball_nba.knowledge.validate_q2_blowout_state -- mechanism
seeds for sim2's rank-4 worst bucket P2|m6 (period 2, off-relative margin
bucket 6 -- `_MARGIN_EDGES = (-15,-8,-3,3,8,15)` in
domains/basketball_nba/sim2/possession_model.py means bucket 6 is off_margin
>= 15, "home already up 15+ in Q2", n=65). Per
docs/research/sim_heatmap_bucket_sweep_2026-07-10.md's mechanism mapping,
"NO mechanism targets this state" -- this module seeds and tests 3
hypotheses from that sweep note's RESEARCH-LANE TARGET entry:

  (a) q2_lead_extension_beyond_ar -- do teams already up/down >=15 after Q1
      (the sim's own top-bucket edge) extend that lead in Q2 by MORE than a
      naive AR(1) fit on moderate-lead games (|q1_margin|<15) would predict,
      or revert toward it? Tests the sim's own miscalibration hypothesis
      directly: a flat/AR-implied margin transition understates tail
      dynamics. Two independent season corpora (linescores.parquet 2025-26,
      linescores_2024_25.parquet 2024-25), same >=2-corpus discipline as
      validate_q3_state.py (reuses its team_game_quarters/load_all_corpora
      verbatim -- same q1_margin/q2_margin ingredient, no need to rebuild).
  (b) q2_blowout_early_bench_deployment -- does the SAME Q1-lead magnitude
      predict reduced starter minutes THAT game, beyond what mechanism #49
      (CONFIRMED_LOCAL, blowout FINAL margin -> fewer starter minutes,
      season-level proxy) already explains? A positive answer would mean
      Q2's specific miscalibration is partly a rotation-composition effect
      (bench already in by Q2 in extreme-Q1-blowout games) distinct from
      #49's season-aggregate story; a null means final margin already
      captures the coach's substitution response and Q1-timing adds nothing.
      Split-half by date on the joined frame (mirrors #49/#50's own
      split-half discipline in validate_research_wave3.py, whose
      build_dataset() is reused verbatim for the starter_minutes/abs_margin
      ingredient; date+team join uses domains.basketball_nba.team_name_
      resolver to normalize linescores' ESPN abbreviations, e.g. "GS", to
      the box-score corpus key "GSW").
  (c) q2_foul_pace_state_interaction -- premise check only: no quarter-level
      foul or pace ingredient exists anywhere in the local corpus (checked
      fresh this session -- four_factor_env.parquet is a team-SEASON
      aggregate with no foul column at all; player_boxscores.parquet's `pf`
      is a game-TOTAL, not quarter-split; linescores.parquet carries points
      per quarter only). NOT_TESTABLE, closes this sub-question rather than
      leaving it silently untried.

No $/edge claimed. ASCII only. Sharpness/calibration research only.

Run: python -m domains.basketball_nba.knowledge.validate_q2_blowout_state
Test: python -m pytest domains/basketball_nba/knowledge/test_validate_q2_blowout_state.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from domains.basketball_nba import team_name_resolver
from domains.basketball_nba.knowledge._data import BOX_PATH, FOUR_FACTOR_PATH, LEDGER_PATH
from domains.basketball_nba.knowledge.validate_q3_state import (
    _CORPORA as _LS_CORPORA, load_all_corpora, team_game_quarters,
)
from domains.basketball_nba.knowledge.validate_research_wave3 import build_dataset as _wave3_build_dataset
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
LEAD_EDGE = 15.0        # matches sim2's own top margin-bucket edge (_MARGIN_EDGES[-1])
MIN_NORMAL_N = 30
MIN_EXTREME_N = 15
MIN_EFFECT_PTS = 1.0    # (a)'s declared bar: mean |signed AR residual|, points
MIN_ROWS_HALF = 30      # (b)'s declared minimum rows per date-half
MIN_Q1_COEF = 0.05      # (b)'s declared bar: partial coef on q1_blowout, min/margin-pt (signed, story predicts negative)


def _fmt_p(p: Optional[float]) -> str:
    return "nan" if (p is None or (isinstance(p, float) and np.isnan(p))) else "%.4g" % p


def _verdict_replicated(per_group_confirmed: Dict[str, Optional[bool]]) -> str:
    vals = list(per_group_confirmed.values())
    if all(v is None for v in vals):
        return "NOT_TESTABLE"
    if all(v is True for v in vals):
        return "REPLICATED"
    if any(v is True for v in vals):
        return "PARTIAL"
    return "NULL"


# --------------------------------------------------------------- hyp (a) ---
def q2_lead_extension_beyond_ar(tg: pd.DataFrame) -> Dict[str, Any]:
    """AR(1) slope/intercept fit on MODERATE-lead games only (|q1_margin| <
    LEAD_EDGE), applied out-of-subset to the EXTREME-lead games (>= LEAD_EDGE,
    the sim's own m6/m0 edge) to test whether the tail behaves differently
    from the population trend, not just whether q1/q2 margin correlate."""
    per_corpus: Dict[str, Any] = {}
    confirmed: Dict[str, Optional[bool]] = {}
    for corpus, d in tg.groupby("corpus"):
        d2 = d.dropna(subset=["q1_margin", "q2_margin"])
        normal = d2[d2["q1_margin"].abs() < LEAD_EDGE]
        extreme = d2[d2["q1_margin"].abs() >= LEAD_EDGE]
        if len(normal) < MIN_NORMAL_N or len(extreme) < MIN_EXTREME_N:
            per_corpus[corpus] = {"signed_resid_mean": None, "p": None, "n_extreme": int(len(extreme))}
            confirmed[corpus] = None
            continue
        slope, intercept, _, _, _ = stats.linregress(normal["q1_margin"], normal["q2_margin"])
        pred = slope * extreme["q1_margin"] + intercept
        resid = extreme["q2_margin"] - pred
        signed = resid * np.sign(extreme["q1_margin"])
        _, p = stats.ttest_1samp(signed, 0.0)
        per_corpus[corpus] = {"signed_resid_mean": round(float(signed.mean()), 3), "p": float(p),
                               "n_extreme": int(len(extreme)), "ar_slope": round(float(slope), 4)}
        confirmed[corpus] = bool(p < ALPHA and abs(signed.mean()) >= MIN_EFFECT_PTS)
    verdict = _verdict_replicated(confirmed)
    note = "; ".join(
        "%s: n_extreme=%s ar_slope=%s signed_resid_mean=%s p=%s"
        % (c, v["n_extreme"], v.get("ar_slope"), v["signed_resid_mean"], _fmt_p(v["p"]))
        for c, v in sorted(per_corpus.items()))
    return {
        "hypothesis": "q2_lead_extension_beyond_ar", "verdict": verdict, "per_corpus": per_corpus,
        "note": "signed AR(1) residual (fit on |q1_margin|<%.0f, applied to |q1_margin|>=%.0f, sign-"
                "flipped to lead direction: positive=extends beyond naive AR, negative=extra reversion "
                "beyond naive AR) per corpus. " % (LEAD_EDGE, LEAD_EDGE) + note,
    }


# --------------------------------------------------------------- hyp (b) ---
def _q1_lead_join_frame() -> pd.DataFrame:
    """date+team join: linescores-derived q1_margin (both corpora, ESPN abbr
    normalized via team_name_resolver to the box-score 3-letter key) merged
    onto wave3's starter_minutes/abs_margin team-game frame (build_dataset(),
    reused verbatim -- same ingredient row #49 already validated on)."""
    frames = []
    for corpus, path in _LS_CORPORA.items():
        if not path.exists():
            continue
        tg = team_game_quarters(pd.read_parquet(path), corpus)
        tg = tg.copy()
        tg["team_key"] = tg["team"].map(team_name_resolver.resolve)
        frames.append(tg[["date", "team_key", "q1_margin"]].dropna(subset=["team_key"]))
    if not frames:
        return pd.DataFrame(columns=["date", "team", "abs_margin", "starter_minutes", "q1_blowout"])
    q1 = pd.concat(frames, ignore_index=True)
    wave3d = _wave3_build_dataset()
    merged = wave3d.merge(q1, left_on=["date", "team"], right_on=["date", "team_key"], how="inner")
    merged["q1_blowout"] = merged["q1_margin"].abs()
    return merged


def _q1_effect_half(d: pd.DataFrame, half: str) -> Dict[str, Any]:
    hyp = "q2_blowout_early_bench_deployment__%s" % half
    if len(d) < MIN_ROWS_HALF:
        return {"hypothesis": hyp, "n": int(len(d)), "effect": None, "p": None, "verdict": None,
                "note": "insufficient joined rows (n=%d, need >=%d), half=%s" % (len(d), MIN_ROWS_HALF, half)}
    res = smf.ols("starter_minutes ~ abs_margin + q1_blowout", data=d).fit()
    coef, p = float(res.params["q1_blowout"]), float(res.pvalues["q1_blowout"])
    ok = bool(p < ALPHA and coef <= -MIN_Q1_COEF)
    return {"hypothesis": hyp, "n": int(len(d)), "effect": round(coef, 4), "p": p, "verdict": ok,
            "note": "OLS starter_minutes~abs_margin+q1_blowout (partial coef on Q1-lead magnitude, "
                    "controlling for #49's already-CONFIRMED final-margin effect), half=%s coef=%.4f "
                    "p=%.4g n=%d" % (half, coef, p, len(d))}


def q2_blowout_early_bench_deployment(d: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    if d is None:
        d = _q1_lead_join_frame()
    if len(d) < 2 * MIN_ROWS_HALF:
        return {"hypothesis": "q2_blowout_early_bench_deployment", "verdict": "NOT_TESTABLE",
                "per_half": {}, "note": "joined frame too small (n=%d)" % len(d)}
    med = d["date"].median()
    halves = {"h1": _q1_effect_half(d[d["date"] <= med], "h1"),
              "h2": _q1_effect_half(d[d["date"] > med], "h2")}
    verdict = _verdict_replicated({k: v["verdict"] for k, v in halves.items()})
    note = "; ".join("%s: %s" % (k, v["note"]) for k, v in sorted(halves.items()))
    return {"hypothesis": "q2_blowout_early_bench_deployment", "verdict": verdict,
            "per_half": halves, "note": note}


# --------------------------------------------------------------- hyp (c) ---
def q2_foul_pace_state_interaction() -> Dict[str, Any]:
    ff = pd.read_parquet(FOUR_FACTOR_PATH)
    box_cols = list(pd.read_parquet(BOX_PATH).columns)
    foul_cols_ff = [c for c in ff.columns if "foul" in c.lower() or c.lower() == "pf"]
    return {"hypothesis": "q2_foul_pace_state_interaction", "verdict": "NOT_TESTABLE", "n": 0,
            "note": "premise check: four_factor_env.parquet is a team-SEASON aggregate (n=%d rows, one "
                    "per team, foul columns found=%s); player_boxscores.parquet's `pf` (present: %s) is "
                    "a game-TOTAL, not quarter-split; linescores.parquet carries points per quarter only, "
                    "no foul/pace columns. No quarter-level foul or pace ingredient exists in the local "
                    "corpus -- cannot test at Q2 granularity without a new PBP-quarter-foul build (out of "
                    "scope this session)." % (len(ff), foul_cols_ff or "none", "pf" in box_cols)}


def run() -> List[Dict[str, Any]]:
    tg = load_all_corpora()
    rows = [
        q2_lead_extension_beyond_ar(tg),
        q2_blowout_early_bench_deployment(),
        q2_foul_pace_state_interaction(),
    ]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "linescores_2024_25+2025_26+player_boxscores"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-38s %-14s %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict_replicated({"a": True, "b": True}) == "REPLICATED"
    assert _verdict_replicated({"a": True, "b": False}) == "PARTIAL"
    assert _verdict_replicated({"a": False, "b": False}) == "NULL"
    assert _verdict_replicated({"a": None, "b": None}) == "NOT_TESTABLE"
    print("self-check OK")


__all__ = [
    "q2_lead_extension_beyond_ar", "q2_blowout_early_bench_deployment",
    "q2_foul_pace_state_interaction", "run", "main", "ALPHA", "LEAD_EDGE",
    "MIN_EFFECT_PTS", "MIN_Q1_COEF",
]
