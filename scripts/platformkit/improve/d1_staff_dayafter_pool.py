"""D1 (WEEKEND_WATCHBOARD.md section 4): staff_dayafter_fatigue_chain (C18) is
PROVISIONAL -- significant in only 1 of 3 seasons (2024, p=0.0043; 2023
p=0.58, 2025 p=0.023, both NULL_LOCAL at alpha=0.01 but same +direction).
Question: is the per-season split simply underpowered? Pools the 3 original
seasons + Fisher-combines their p-values (two different questions -- pooled
effect size vs combined evidence), then runs 2026 (partial season, in disk
cache) as a genuinely out-of-sample 4th check, labelled separately.

Reuses domains.mlb.knowledge.validate_staff_dayafter_chain's team_day_table /
build_dayafter_pairs / _compare unchanged (same leak audit: predictor is
final at close of day d, outcome unfolds on day d+1; gap_days==1 restricts to
true back-to-backs) -- this script only adds pooling + Fisher combination on
top, it does not re-derive the mechanism.

Run: python -m scripts.platformkit.improve.d1_staff_dayafter_pool
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge import validate_staff_dayafter_chain as vdc
from domains.mlb.knowledge._data import LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
CI_ALPHA = 0.05  # 95% CI on the pooled effect (reporting convention; test itself uses ALPHA=0.01)
ORIGINAL_SEASONS = [2023, 2024, 2025]
OOS_SEASON = 2026


def _welch_ci(high: pd.Series, low: pd.Series, alpha: float = CI_ALPHA) -> Dict[str, float]:
    n1, n2 = len(high), len(low)
    v1, v2 = high.var(ddof=1), low.var(ddof=1)
    se = float(np.sqrt(v1 / n1 + v2 / n2))
    df = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    t_crit = float(stats.t.ppf(1 - alpha / 2, df))
    eff = float(high.mean() - low.mean())
    return {"effect": round(eff, 4), "ci_lo": round(eff - t_crit * se, 4), "ci_hi": round(eff + t_crit * se, 4),
            "se": round(se, 4), "df": round(float(df), 1)}


def _season_pairs(season: int) -> pd.DataFrame:
    return vdc.build_dayafter_pairs(vdc.team_day_table(load_season(season)))


def _pooled_test(seasons: List[int]) -> Dict[str, Any]:
    pooled = pd.concat([_season_pairs(s) for s in seasons], ignore_index=True)
    q_hi, q_lo = pooled["prior_day_pitches"].quantile(vdc.HIGH_Q), pooled["prior_day_pitches"].quantile(vdc.LOW_Q)
    high = pooled[pooled["prior_day_pitches"] >= q_hi]["next_runs_allowed"]
    low = pooled[pooled["prior_day_pitches"] <= q_lo]["next_runs_allowed"]
    t, p = stats.ttest_ind(high, low, equal_var=False)
    ci = _welch_ci(high, low)
    return {"hypothesis": "staff_dayafter_fatigue_chain__pooled_%s" % "_".join(str(s) for s in seasons),
            "n": int(len(high) + len(low)), "p": float(p), "seasons": seasons, **ci}


def main() -> int:
    # per-season p-values, recomputed fresh (reuses vdc._compare, no re-derivation)
    per_season = [vdc._compare(_season_pairs(s), s) for s in ORIGINAL_SEASONS]
    p3 = [r["p"] for r in per_season]
    fisher3_stat, fisher3_p = stats.combine_pvalues(p3, method="fisher")

    pooled3 = _pooled_test(ORIGINAL_SEASONS)
    sign_consistent_3 = sum(1 for r in per_season if r["effect"] > 0) >= 2

    if fisher3_p < ALPHA and pooled3["ci_lo"] > 0 and sign_consistent_3:
        label3 = "CONFIRMED_LOCAL"
    elif pooled3["ci_lo"] <= 0 <= pooled3["ci_hi"]:
        label3 = "NULL_UNDERPOWERED"
    else:
        label3 = "NULL_LOCAL"

    # OOS 4th season (2026, partial) -- answers a different question (does the
    # effect generalize to a season not in the original test), kept separate.
    oos_row = vdc._compare(_season_pairs(OOS_SEASON), OOS_SEASON)
    p4 = p3 + [oos_row["p"]]
    fisher4_stat, fisher4_p = stats.combine_pvalues(p4, method="fisher")
    pooled4 = _pooled_test(ORIGINAL_SEASONS + [OOS_SEASON])
    sign_consistent_4 = sum(1 for r in per_season + [oos_row] if r["effect"] > 0) >= 2
    if fisher4_p < ALPHA and pooled4["ci_lo"] > 0 and sign_consistent_4:
        label4 = "CONFIRMED_LOCAL_incl_2026_OOS"
    elif pooled4["ci_lo"] <= 0 <= pooled4["ci_hi"]:
        label4 = "NULL_UNDERPOWERED_incl_2026_OOS"
    else:
        label4 = "NULL_LOCAL_incl_2026_OOS"

    rows = [
        {"hypothesis": "staff_dayafter_fatigue_chain__fisher3", "n": sum(r["n"] for r in per_season),
         "p": float(fisher3_p), "effect": None, "verdict": label3,
         "note": "Fisher combine of 3 original-season p-values %s -> X2=%.3f, p=%.4g; pooled-3 effect=%.4f "
                 "CI95[%.4f,%.4f] n=%d, sign-consistent=%s"
                 % (["%.4g" % x for x in p3], fisher3_stat, fisher3_p, pooled3["effect"], pooled3["ci_lo"],
                    pooled3["ci_hi"], pooled3["n"], sign_consistent_3)},
        {"hypothesis": "staff_dayafter_fatigue_chain__oos_2026", "n": oos_row["n"], "p": oos_row["p"],
         "effect": oos_row["effect"], "verdict": oos_row["verdict"],
         "note": "2026 partial-season (through data-cache cutoff) OOS check, NOT part of the original 3-season "
                 "test: %s" % oos_row["note"]},
        {"hypothesis": "staff_dayafter_fatigue_chain__fisher4_incl_2026oos", "n": sum(r["n"] for r in per_season) + oos_row["n"],
         "p": float(fisher4_p), "effect": None, "verdict": label4,
         "note": "Fisher combine of all 4 seasons (2023-2025 + 2026 OOS) %s -> X2=%.3f, p=%.4g; pooled-4 "
                 "effect=%.4f CI95[%.4f,%.4f] n=%d, sign-consistent=%s"
                 % (["%.4g" % x for x in p4], fisher4_stat, fisher4_p, pooled4["effect"], pooled4["ci_lo"],
                    pooled4["ci_hi"], pooled4["n"], sign_consistent_4)},
    ]
    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__2023-2026_team_day_pitchcount_pooled"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
        print("%-52s %-30s n=%-6s p=%s -- %s" % (r["hypothesis"], r["verdict"], r["n"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
