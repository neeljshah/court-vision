"""domains.mlb.knowledge.validate_called_strike_dispersion -- 2 UNTESTED
game-level called-strike-dispersion mechanisms (MLB mechanisms.md #31
umpire-zone-call-consistency companion: NO umpire identity column exists
locally, so this tests the GAME-LEVEL environmental signal only -- does the
called-strike rate on borderline pitches vary MORE across games than pure
binomial sampling noise would predict, and does that per-game deviation
relate to that game's total runs. No per-umpire claim is made anywhere here;
that separate gate (#31) stays NOT_TESTABLE.

"Borderline" = Statcast shadow-zone corners {11,12,13,14} (same EDGE_ZONES
convention as validate_count_zone.py's edge_zone_widens_with_two_strikes),
restricted to TAKEN pitches only (description in {ball, called_strike} --
excludes blocked_ball/automatic_ball/hit_by_pitch, which are not a live
ball/strike judgment call).

Overdispersion test: per game, calls_g ~ Binomial(n_g, p_bar) under the null
of one shared true rate. chi2 = sum((calls_g - n_g*p_bar)^2 / (n_g*p_bar*(1-
p_bar))) ~ chi2(n_games-1) under that null; phi = chi2/df is the standard
quasi-binomial dispersion ratio (phi=1 -> pure sampling noise, phi>1 -> real
extra game-to-game variation). p alone is not trusted here (n_games in the
thousands makes any p tiny) -- CONFIRMED_LOCAL requires phi >= PHI_THRESHOLD
AND p < ALPHA together.

Run: python -m domains.mlb.knowledge.validate_called_strike_dispersion
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
EDGE_ZONES = {11, 12, 13, 14}
TAKEN_DESC = {"ball", "called_strike"}
MIN_PITCHES_PER_GAME = 20
PHI_THRESHOLD = 1.2  # dispersion ratio above pure-binomial-noise
MIN_CORR_EFFECT = 0.1


def per_game_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One row per game_pk: n (taken borderline pitches), calls (called-
    strike count), rate, total_runs (final home+away score). Games with
    fewer than MIN_PITCHES_PER_GAME taken borderline pitches are dropped --
    too few to estimate a stable per-game rate."""
    d = df.dropna(subset=["zone", "description", "game_pk"])
    d = d[d["zone"].isin(EDGE_ZONES) & d["description"].isin(TAKEN_DESC)]
    g = d.groupby("game_pk").agg(
        n=("description", "size"),
        calls=("description", lambda s: int((s == "called_strike").sum())))
    g = g[g["n"] >= MIN_PITCHES_PER_GAME]
    runs = df.groupby("game_pk").agg(hr=("post_home_score", "max"), ar=("post_away_score", "max"))
    g = g.join((runs["hr"] + runs["ar"]).rename("total_runs"), how="left")
    g["rate"] = g["calls"] / g["n"]
    return g.reset_index()


def called_strike_dispersion_exceeds_binomial_noise(g: pd.DataFrame) -> Dict[str, Any]:
    if len(g) < 3:
        return {"hypothesis": "called_strike_dispersion_exceeds_binomial_noise", "verdict": "NOT_TESTABLE",
                "phi": None, "p": None, "n": int(len(g)), "note": "fewer than 3 qualifying games"}
    p_bar = g["calls"].sum() / g["n"].sum()
    var_null = g["n"] * p_bar * (1 - p_bar)
    chi2 = float(((g["calls"] - g["n"] * p_bar) ** 2 / var_null).sum())
    dof = len(g) - 1
    p = float(stats.chi2.sf(chi2, dof))
    phi = chi2 / dof
    verdict = "CONFIRMED_LOCAL" if (phi >= PHI_THRESHOLD and p < ALPHA) else "NULL_LOCAL"
    return {"hypothesis": "called_strike_dispersion_exceeds_binomial_noise", "verdict": verdict,
            "phi": round(float(phi), 4), "p": p, "n": int(len(g)), "pbar": round(float(p_bar), 4),
            "note": "quasi-binomial dispersion ratio phi=%.3f (chi2=%.1f, df=%d, p=%.3g) vs pure-noise phi=1.0, "
                    "pooled called-strike rate on taken borderline(zone 11-14) pitches=%.4f, n=%d games"
                    % (phi, chi2, dof, p, p_bar, len(g))}


def called_strike_deviation_relates_to_total_runs(g: pd.DataFrame) -> Dict[str, Any]:
    d = g.dropna(subset=["total_runs"]).copy()
    if len(d) < 3:
        return {"hypothesis": "called_strike_deviation_relates_to_total_runs", "verdict": "NOT_TESTABLE",
                "effect": None, "p": None, "n": int(len(d)), "note": "fewer than 3 qualifying games"}
    p_bar = d["calls"].sum() / d["n"].sum()
    z = (d["calls"] - d["n"] * p_bar) / np.sqrt(d["n"] * p_bar * (1 - p_bar))
    r, p = stats.pearsonr(z, d["total_runs"])
    verdict = "CONFIRMED_LOCAL" if (p < ALPHA and abs(r) >= MIN_CORR_EFFECT) else "NULL_LOCAL"
    return {"hypothesis": "called_strike_deviation_relates_to_total_runs", "verdict": verdict,
            "effect": round(float(r), 4), "p": float(p), "n": int(len(d)),
            "note": "pearson r(per-game called-strike-rate z-deviation on borderline pitches, game total runs), "
                    "n=%d games, r=%.4f p=%.3g" % (len(d), r, p)}


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    g = per_game_frame(df)
    rows = [called_strike_dispersion_exceeds_binomial_noise(g),
            called_strike_deviation_relates_to_total_runs(g)]
    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-46s %-16s %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    fake = pd.DataFrame({
        "n": [50, 50, 50, 50, 50], "calls": [2, 3, 2, 20, 3],
        "total_runs": [4, 5, 3, 4, 6]})
    r = called_strike_dispersion_exceeds_binomial_noise(fake)
    assert r["verdict"] == "CONFIRMED_LOCAL"  # game index 3 is a huge outlier -> real dispersion
    even = pd.DataFrame({"n": [50] * 20, "calls": [3] * 20, "total_runs": list(range(20))})
    r2 = called_strike_dispersion_exceeds_binomial_noise(even)
    assert r2["verdict"] == "NULL_LOCAL"  # identical rate every game -> phi ~ 0, no dispersion
    print("self-check OK")
