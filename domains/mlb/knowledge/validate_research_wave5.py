"""domains.mlb.knowledge.validate_research_wave5 -- the 2 MLB literature-
sourced UNTESTED rows seeded 2026-07-10 by the round-5 research-wave commit
(29628281, mechanisms.md rows #53/#54).

Row #53 putaway_whiff_dispersion_exceeds_binomial_noise: mirrors CONFIRMED
#39's identity-free per-game dispersion design exactly, output column
swapped from called-strike to 2-strike whiff. PREMISE CHECK (this session):
`savant_full__2025.parquet` columns game_pk/strikes/description confirmed,
705,391 pitch rows / 2,406 games; strikes==2 subset n=210,696 (matches the
seeded row's premise number exactly). Correction to the seeded row's own
premise text: its cited swinging_strike (73,372) / swinging_strike_blocked
(3,954) counts are the WHOLE-SEASON totals, not the 2-strike subset -- within
strikes==2 the true counts are swinging_strike=25,258 / swinging_strike_
blocked=2,775 (28,033 combined whiffs); this does not change testability
(the row's floor is n>=20 2-strike PITCHES/game, not whiffs, and mean
2-strike pitches/game is ~88, far above floor), only the docstring number.

Row #54 zombie_runner_home_away_scoring_rate: rule-era-aware (automatic
runner permanent since 2023; this local corpus is 2023-2026, entirely
inside the rule-active era). PREMISE CHECK (this session): `inning>=10`
n=8,674 rows/204 games (2025); every sampled inning>=10 half-inning's first
pitch has non-null on_2b (588/588), confirming the rule is active for the
full local window -- matches the seeded row's premise numbers exactly.

Run: python -m domains.mlb.knowledge.validate_research_wave5
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.proportion import proportions_ztest

from domains.mlb.knowledge._data import LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA_53 = 0.01
ALPHA_54 = 0.05  # row's own relaxed alpha, declared given the smaller single-inning-slice n
PHI_THRESHOLD = 1.2  # same bar as #39 -- direct outcome-column swap of that design
MIN_PITCHES_PER_GAME = 20  # same floor as #39
MIN_DIFF_54 = 0.05
WHIFF_DESC = {"swinging_strike", "swinging_strike_blocked"}


# --- row #53: putaway-whiff dispersion -------------------------------------

def per_game_putaway_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One row per game_pk: n (2-strike pitches), whiffs (swinging-strike
    outcomes among them). Games below MIN_PITCHES_PER_GAME dropped."""
    d = df.dropna(subset=["strikes", "description", "game_pk"])
    d = d[d["strikes"] == 2]
    g = d.groupby("game_pk").agg(
        n=("description", "size"),
        whiffs=("description", lambda s: int(s.isin(WHIFF_DESC).sum())))
    return g[g["n"] >= MIN_PITCHES_PER_GAME].reset_index()


def putaway_whiff_dispersion_exceeds_binomial_noise(g: pd.DataFrame, label: str) -> Dict[str, Any]:
    hyp = "putaway_whiff_dispersion_exceeds_binomial_noise__%s" % label
    if len(g) < 3:
        return {"hypothesis": hyp, "verdict": "NOT_TESTABLE", "effect": None, "p": None, "n": int(len(g)),
                "note": "fewer than 3 qualifying games"}
    p_bar = g["whiffs"].sum() / g["n"].sum()
    var_null = g["n"] * p_bar * (1 - p_bar)
    chi2 = float(((g["whiffs"] - g["n"] * p_bar) ** 2 / var_null).sum())
    dof = len(g) - 1
    p = float(stats.chi2.sf(chi2, dof))
    phi = chi2 / dof
    verdict = "CONFIRMED_LOCAL" if (phi >= PHI_THRESHOLD and p < ALPHA_53) else "NULL_LOCAL"
    return {"hypothesis": hyp, "verdict": verdict, "effect": round(float(phi), 4), "p": p, "n": int(len(g)),
            "note": "quasi-binomial dispersion ratio phi=%.3f (chi2=%.1f, df=%d, p=%.3g) vs pure-noise phi=1.0, "
                    "pooled 2-strike putaway-whiff rate=%.4f, n=%d games, %s"
                    % (phi, chi2, dof, p, p_bar, len(g), label)}


def _combine_dispersion(rows: List[Dict[str, Any]], base_hyp: str) -> Dict[str, Any]:
    """Both seasons required -- dispersion is one-directional, no sign check
    needed (mirrors NBA wave4's foul-dispersion combine rule)."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    confirmed = [r for r in testable if r["verdict"] == "CONFIRMED_LOCAL"]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(confirmed) == 2:
        verdict = "CONFIRMED_LOCAL"
    elif len(confirmed) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": base_hyp + "__combined", "n": int(sum(r["n"] for r in rows)), "effect": None, "p": None,
            "verdict": verdict,
            "note": "two-corpora (2025 vs 2024) replication: %s"
                    % "; ".join("%s(verdict=%s,p=%s,eff=%s)" % (r["hypothesis"], r["verdict"], r["p"], r["effect"])
                                for r in rows)}


# --- row #54: zombie-runner home/away scoring parity ------------------------

def half_inning_scoring(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_pk, inning_topbot) for inning==10: whether the
    batting team scored >=1 run in that half-inning (post-score minus the
    pre-score of its first pitch), restricted to games where BOTH halves of
    the 10th were played (excludes a walkoff-avoided/already-decided top)."""
    d = df[df["inning"] == 10].sort_values(["game_pk", "inning_topbot", "at_bat_number", "pitch_number"])
    grp = d.groupby(["game_pk", "inning_topbot"], sort=False)
    first = grp.head(1).set_index(["game_pk", "inning_topbot"])
    last = grp.tail(1).set_index(["game_pk", "inning_topbot"])
    out = pd.DataFrame(index=first.index)
    out["pre_home"], out["pre_away"] = first["home_score"], first["away_score"]
    out["post_home"], out["post_away"] = last["post_home_score"], last["post_away_score"]
    out = out.reset_index()
    out["scored"] = np.where(out["inning_topbot"] == "Top",
                              (out["post_away"] - out["pre_away"]) >= 1,
                              (out["post_home"] - out["pre_home"]) >= 1)
    both_halves = out.groupby("game_pk")["inning_topbot"].transform("nunique") == 2
    return out[both_halves]


def zombie_runner_home_away_scoring_rate(half: pd.DataFrame) -> Dict[str, Any]:
    home = half[half["inning_topbot"] == "Bot"]["scored"]
    away = half[half["inning_topbot"] == "Top"]["scored"]
    if len(home) < 3 or len(away) < 3:
        return {"hypothesis": "zombie_runner_home_away_scoring_rate", "verdict": "NOT_TESTABLE",
                "effect": None, "p": None, "n": int(len(half)), "note": "fewer than 3 qualifying half-innings/side"}
    _, p = proportions_ztest([int(home.sum()), int(away.sum())], [len(home), len(away)])
    diff = float(home.mean() - away.mean())
    verdict = "CONFIRMED_LOCAL" if (p < ALPHA_54 and abs(diff) >= MIN_DIFF_54) else "NULL_LOCAL"
    return {"hypothesis": "zombie_runner_home_away_scoring_rate", "verdict": verdict, "effect": round(diff, 4),
            "p": float(p), "n": int(len(half)),
            "note": "bottom-10th (home) scoring rate=%.4f (n=%d) vs top-10th (away)=%.4f (n=%d), diff=%+.4f, "
                    "p=%.4g; declared bar |diff|>=0.05 & p<0.05" % (home.mean(), len(home), away.mean(), len(away), diff, p)}


def run() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    disp_legs = []
    for season, label in ((2025, "2025"), (2024, "2024")):
        g = per_game_putaway_frame(load_season(season))
        r = putaway_whiff_dispersion_exceeds_binomial_noise(g, label)
        disp_legs.append(r)
        rows.append(r)
    rows.append(_combine_dispersion(disp_legs, "putaway_whiff_dispersion_exceeds_binomial_noise"))

    half = half_inning_scoring(load_season(2025))
    rows.append(zombie_runner_home_away_scoring_rate(half))

    for r in rows:
        r["sport"] = "mlb"
        r.setdefault("corpus", "savant_full__2025")
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-58s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    fake = pd.DataFrame({"n": [50, 50, 50, 50, 50], "whiffs": [2, 3, 2, 20, 3]})
    r = putaway_whiff_dispersion_exceeds_binomial_noise(fake, "test")
    assert r["verdict"] == "CONFIRMED_LOCAL"  # index 3 is a huge outlier -> real dispersion
    even = pd.DataFrame({"n": [50] * 20, "whiffs": [3] * 20})
    r2 = putaway_whiff_dispersion_exceeds_binomial_noise(even, "test")
    assert r2["verdict"] == "NULL_LOCAL"

    half = pd.DataFrame({
        "game_pk": [1, 1, 2, 2, 3, 3],
        "inning_topbot": ["Top", "Bot", "Top", "Bot", "Top", "Bot"],
        "scored": [True, True, False, True, False, True]})
    out = zombie_runner_home_away_scoring_rate(half)
    assert out["n"] == 6
    assert out["effect"] > 0  # home scored all 3, away scored 1/3

    print("self-check OK")
