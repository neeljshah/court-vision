"""domains.mlb.knowledge.validate_reliever_b2b_fatigue -- mechanism #35:
does a reliever pitching on back-to-back days (is_b2b), or with 2+
appearances in the trailing 3 days (appearances_last_3d), show degraded
same-outing run-prevention (higher xwOBA allowed) vs pitching on >=1 day
rest? NOT the blocklisted velo-decline class -- outcome tested here is
contact quality allowed (estimated_woba_using_speedangle), never
release_speed.

Leak audit: is_b2b / appearances_last_3d in bullpen_relief_chains.parquet
are derived from appearances STRICTLY BEFORE the outing being scored (prior
rest-day history, known before the outing starts). The outcome (mean xwOBA
allowed during that same outing) is observed only as the outing unfolds, so
predictor -> outcome ordering is leak-free.

Corpora: 2023/2024/2025 seasons are treated as independent replication
corpora (2022 has no local pitch-level parquet; 2026 is a partial
in-progress season and is excluded). Per HONESTY discipline, an affirmative
requires the same-direction effect to clear p<ALPHA in >=2 of 3 seasons,
else the combined verdict is PROVISIONAL (1 season) or NULL_LOCAL (0).

Run: python -m domains.mlb.knowledge.validate_reliever_b2b_fatigue
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import LEDGER_PATH, load_season, pa_final_pitch
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
SEASONS = [2023, 2024, 2025]
CHAINS_PATH = Path(__file__).resolve().parents[3] / "data" / "domains" / "mlb" / "bullpen_relief_chains.parquet"
MIN_GROUP_N = 20


def _verdict(p, min_abs_effect: float, effect) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def load_chains() -> pd.DataFrame:
    return pd.read_parquet(CHAINS_PATH)


def appearance_outcome(pitch: pd.DataFrame) -> pd.Series:
    """Mean xwOBA allowed per (game_pk, pitcher) -- the appearance-level
    run-prevention outcome, computed from the SAME outing being scored."""
    pa = pa_final_pitch(pitch).dropna(subset=["estimated_woba_using_speedangle"])
    return pa.groupby(["game_pk", "pitcher"])["estimated_woba_using_speedangle"].mean()


def _compare(chains: pd.DataFrame, outcome: pd.Series, flag_col: str, threshold: int,
             season: int, hyp: str) -> Dict[str, Any]:
    d = chains.merge(outcome.rename("xwoba_allowed"), left_on=["game_pk", "player_id"],
                      right_index=True, how="inner")
    d = d.dropna(subset=[flag_col])
    fatigued = d[d[flag_col] >= threshold]["xwoba_allowed"]
    rested = d[d[flag_col] == 0]["xwoba_allowed"]
    if len(fatigued) < MIN_GROUP_N or len(rested) < MIN_GROUP_N:
        return {"hypothesis": hyp, "n": int(len(fatigued) + len(rested)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE",
                "note": "insufficient n after merge (%d fatigued / %d rested), season=%d"
                        % (len(fatigued), len(rested), season)}
    t, p = stats.ttest_ind(fatigued, rested, equal_var=False)
    eff = float(fatigued.mean() - rested.mean())
    return {"hypothesis": hyp, "n": int(len(fatigued) + len(rested)), "effect": round(eff, 5), "p": float(p),
            "verdict": _verdict(p, 0.003, eff),
            "note": "mean xwOBA allowed, %s>=%d (%.4f, n=%d) vs %s==0 (%.4f, n=%d), season=%d"
                    % (flag_col, threshold, fatigued.mean(), len(fatigued), flag_col, rested.mean(),
                       len(rested), season)}


def _combine(rows: List[Dict[str, Any]], hyp: str) -> Dict[str, Any]:
    """Combine per-season rows. Only a POSITIVE significant effect (fatigued
    group allows MORE xwOBA = worse run prevention) counts as support for the
    fatigue-degrades-performance hypothesis. A significant NEGATIVE effect is
    the opposite direction (fatigued group allows LESS xwOBA) -- reported but
    never counted as confirming support, since it more plausibly reflects a
    selection confound (managers deploy their most-trusted/best relievers on
    heavy-usage stretches) than fatigue."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    sig_support = [r for r in testable if r["p"] < ALPHA and r["effect"] > 0]
    sig_reverse = [r for r in testable if r["p"] < ALPHA and r["effect"] < 0]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(sig_support) >= 2:
        verdict = "CONFIRMED_LOCAL"
    elif len(sig_support) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    seasons_note = "; ".join("%d:%s(p=%s,eff=%s)" % (s, r["verdict"], r["p"], r["effect"])
                              for s, r in zip(SEASONS, rows))
    reverse_note = (" -- %d season(s) significant in the REVERSE direction (fatigued group allowed LESS "
                     "xwOBA, likely a selection confound, not counted as support)" % len(sig_reverse)
                     if sig_reverse else "")
    return {"hypothesis": hyp + "__combined", "n": int(sum(r["n"] for r in rows)), "effect": None, "p": None,
            "verdict": verdict,
            "note": "cross-season replication (%d independent season corpora): %s%s"
                     % (len(SEASONS), seasons_note, reverse_note)}


def run() -> List[Dict[str, Any]]:
    chains = load_chains()
    b2b_rows: List[Dict[str, Any]] = []
    apps_rows: List[Dict[str, Any]] = []
    for season in SEASONS:
        pitch = load_season(season)
        outcome = appearance_outcome(pitch)
        season_chains = chains[chains["year"] == season]
        b2b_rows.append(_compare(season_chains, outcome, "is_b2b", 1, season, "reliever_b2b_fatigue"))
        apps_rows.append(_compare(season_chains, outcome, "appearances_last_3d", 2, season,
                                   "reliever_3in3d_fatigue"))
    rows = b2b_rows + [_combine(b2b_rows, "reliever_b2b_fatigue")] + \
        apps_rows + [_combine(apps_rows, "reliever_3in3d_fatigue")]
    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "bullpen_relief_chains+savant_full__2023-2025"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-32s %-16s n=%-8d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
