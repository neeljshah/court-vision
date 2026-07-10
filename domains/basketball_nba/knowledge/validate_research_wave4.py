"""domains.basketball_nba.knowledge.validate_research_wave4 -- validates the
1 NBA literature-sourced UNTESTED row appended 2026-07-10 (commit 226391a3,
"research-wave 4", row #54 in mechanisms.md):

  foul_rate_dispersion_exceeds_poisson_noise (row #54) -- team-adjusted
    quasi-Poisson dispersion of per-game total personal fouls, IDENTITY-FREE
    (no referee/crew column exists locally), mirroring MLB #39's called-
    strike-dispersion design exactly: chi2 = sum((observed_g-lambda_g)^2 /
    lambda_g) ~ chi2(n_games-1), phi = chi2/df.

PREMISE CHECK (this session): player_boxscores.parquet 77,744 rows on disk,
columns game_id/team/pf/season/date confirmed, 3,611 distinct games, pf has
zero nulls -- matches the row's stated shape exactly.

lambda_g construction: for each team-game, the "expected" PF contribution is
that team's LEAVE-ONE-OUT mean PF-per-game within its own season (excludes
the target game itself, per the row's own anti-circularity spec). Team-
seasons with fewer than MIN_GAMES_PER_TEAM_SEASON games are dropped (a LOO
mean off too few games is unstable) -- this is the row's own "season-split
subset if leave-one-out season means require a same-season floor" escape
hatch, exercised literally. lambda_g = home LOO-mean + away LOO-mean;
observed_g = home actual PF + away actual PF for that game.

HONESTY: split-half-by-date replication (2 groups) inside this single run,
mirroring wave3's >=2-corpora discipline for an affirmative -- both halves
must independently clear the row's own declared bar (phi>=1.15 AND p<0.01).

Run: python -m domains.basketball_nba.knowledge.validate_research_wave4
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH, load_player_boxscores
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
PHI_THRESHOLD = 1.15  # row #54's declared bar (below MLB #39's 1.2 -- team-baseline-adjusted, not raw pooled)
MIN_GAMES_PER_TEAM_SEASON = 10  # floor for a stable leave-one-out season mean
MIN_GAMES = 3


def _combine_halves(rows: List[Dict[str, Any]], hyp: str) -> Dict[str, Any]:
    """Both halves must independently clear the row's own phi+p bar (i.e.
    verdict==CONFIRMED_LOCAL) -- dispersion is one-directional (phi>=1.15
    already implies effect>0), so no sign check is needed here."""
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
    return {"hypothesis": hyp + "__combined", "n": int(sum(r["n"] for r in rows)), "effect": None, "p": None,
            "verdict": verdict,
            "note": "split-half-by-date replication: %s"
                    % "; ".join("%s(verdict=%s,p=%s,eff=%s)" % (r["hypothesis"], r["verdict"], r["p"], r["effect"])
                                for r in rows)}


def build_dataset(box: pd.DataFrame) -> pd.DataFrame:
    """One row per game: home_team/away_team PF actuals, each team's leave-
    one-out season-mean PF (its own expected contribution), lambda (sum of
    both LOO means), observed (sum of both actual PF), date. Games where
    either team's season has fewer than MIN_GAMES_PER_TEAM_SEASON team-games
    on record are dropped -- LOO mean too unstable."""
    tg = box.groupby(["game_id", "team", "season", "date"], as_index=False)["pf"].sum()
    season_sum = tg.groupby(["team", "season"])["pf"].transform("sum")
    season_n = tg.groupby(["team", "season"])["pf"].transform("size")
    tg["loo_mean"] = (season_sum - tg["pf"]) / (season_n - 1)
    tg = tg[season_n >= MIN_GAMES_PER_TEAM_SEASON].copy()
    ordered = tg.sort_values(["game_id", "team"]).groupby("game_id")
    rows = []
    for game_id, grp in ordered:
        if len(grp) != 2:
            continue  # only fully-populated two-team games qualify
        a, b = grp.iloc[0], grp.iloc[1]
        rows.append({"game_id": game_id, "date": a["date"], "lambda": a["loo_mean"] + b["loo_mean"],
                     "observed": a["pf"] + b["pf"]})
    return pd.DataFrame(rows)


def _dispersion_verdict(d: pd.DataFrame, half: str) -> Dict[str, Any]:
    hyp = "foul_rate_dispersion_exceeds_poisson_noise__%s" % half
    if len(d) < MIN_GAMES:
        return {"hypothesis": hyp, "n": int(len(d)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than %d qualifying games, half=%s" % (MIN_GAMES, half)}
    chi2 = float(((d["observed"] - d["lambda"]) ** 2 / d["lambda"]).sum())
    dof = len(d) - 1
    p = float(stats.chi2.sf(chi2, dof))
    phi = chi2 / dof
    verdict = "CONFIRMED_LOCAL" if (phi >= PHI_THRESHOLD and p < ALPHA) else "NULL_LOCAL"
    return {"hypothesis": hyp, "n": int(len(d)), "effect": round(float(phi), 4), "p": p, "verdict": verdict,
            "note": "quasi-Poisson dispersion ratio phi=%.3f (chi2=%.1f, df=%d, p=%.3g) vs pure-noise phi=1.0, "
                    "team-adjusted (leave-one-out season mean) expected total PF, n=%d games, half=%s"
                    % (phi, chi2, dof, p, len(d), half)}


def foul_rate_dispersion_exceeds_poisson_noise(box: pd.DataFrame = None) -> List[Dict[str, Any]]:
    box = box if box is not None else load_player_boxscores()
    d = build_dataset(box)
    if d.empty:
        return [{"hypothesis": "foul_rate_dispersion_exceeds_poisson_noise__combined", "n": 0, "effect": None,
                  "p": None, "verdict": "NOT_TESTABLE", "note": "no team-seasons clear the LOO-mean game floor"}]
    mid = d["date"].median()
    h1 = _dispersion_verdict(d[d["date"] <= mid], "h1")
    h2 = _dispersion_verdict(d[d["date"] > mid], "h2")
    return [h1, h2, _combine_halves([h1, h2], "foul_rate_dispersion_exceeds_poisson_noise")]


def run() -> List[Dict[str, Any]]:
    box = load_player_boxscores()
    rows = foul_rate_dispersion_exceeds_poisson_noise(box)
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "player_boxscores_team_game_pf_loo_season_mean (split-half by date)"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-56s %-16s n=%-6s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r.get("n"), r.get("effect"), r.get("p"), r.get("note")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: dataset build joins two-team games only, the
    dispersion verdict threshold, and combine-halves logic."""
    box = pd.DataFrame([
        {"game_id": "g1", "team": "BOS", "season": "2025-26", "date": pd.Timestamp("2026-01-01"), "pf": 20.0},
        {"game_id": "g1", "team": "PHI", "season": "2025-26", "date": pd.Timestamp("2026-01-01"), "pf": 18.0},
    ])
    d = build_dataset(box)
    assert d.empty  # each team has only 1 season-game -- below MIN_GAMES_PER_TEAM_SEASON floor

    fake = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=5),
                          "lambda": [40.0] * 5, "observed": [42, 39, 41, 90, 38]})
    r = _dispersion_verdict(fake, "h1")
    assert r["verdict"] == "CONFIRMED_LOCAL"  # game index 3 is a huge outlier -> real dispersion
    even = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=20),
                          "lambda": [40.0] * 20, "observed": [40, 41] * 10})
    r2 = _dispersion_verdict(even, "h1")
    assert r2["verdict"] == "NULL_LOCAL"  # near-identical rate every game -> phi ~ 0, no dispersion

    out = _combine_halves(
        [{"hypothesis": "x__h1", "n": 5, "effect": 1.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"},
         {"hypothesis": "x__h2", "n": 5, "effect": 1.4, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}], "x")
    assert out["verdict"] == "CONFIRMED_LOCAL"
    out2 = _combine_halves(
        [{"hypothesis": "x__h1", "n": 5, "effect": 1.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"},
         {"hypothesis": "x__h2", "n": 5, "effect": 1.0, "p": 0.5, "verdict": "NULL_LOCAL"}], "x")
    assert out2["verdict"] == "PROVISIONAL"
    print("self-check OK")
