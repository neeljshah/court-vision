"""scripts.platformkit.pod_sprint.crew_fatigue_r1 -- Family R (referee crew condition),
descriptive claim family. See DEEP_FEATURES_PREREG.md R1 (lines 62-72), BINDING, frozen
2026-07-17: "crews on zero days rest call fewer marginal fouls."

DATA-AVAILABILITY DEVIATION (declared, not silent): the prereg names split-half
"2021-22+2022-23 vs 2023-24+2024-25". On disk: data/domains/basketball_nba/games.parquet
has NO 2021-22 rows at all (starts 2022-23), so officials_2021-22.json has no date source
anywhere locally and is dropped entirely -- this only costs a NaN crew_rest_days for an
official's first 2022-23 appearance (season-opener-safe, same convention as
domains/basketball_nba/knowledge/_data.team_game_frame's own rest_days). The PF/FTA
outcome source, player_boxscores.parquet, starts 2023-24 -- 2022-23 has ZERO outcome
rows, so it contributes ONLY prior-game dates for rest-day continuity into 2023-24,
never an outcome row. The split-half actually run is season A=2023-24 (n=1230 games,
full season) vs season B=2024-25+2025-26 pooled -- the only seasons with BOTH officials
AND outcome data -- reported below as h1/h2, not the prereg's literal season pairs.

Team-baseline adjustment: mechanism #54 (domains/basketball_nba/knowledge/mechanisms.md
line 606; code domains/basketball_nba/knowledge/validate_research_wave4.py::build_dataset)
-- leave-one-out SEASON mean of each team's own stat per team-game (excludes the target
game itself), floor MIN_GAMES_PER_TEAM_SEASON games same season (constant imported, not
re-declared). adjusted_g = observed_g - lambda_g, lambda_g = home LOO-mean + away LOO-mean,
observed_g = home actual + away actual. The formula is #54's exactly; _build_adjusted below
generalizes it from PF-only to an arbitrary column (PF and FTA) since #54's own function is
hardcoded to "pf" and is left untouched (mechanism validator, not this prereg's to edit).

crew_b2b: per-official rest_days = calendar days since that SAME NAME's own previous
listed game (any season). Known limitation: officials are joined by exact name string
(no ref-id column exists locally) -- a landmine if a name is spelled inconsistently across
season files, uncorrected here. crew_b2b_any = 1 if ANY listed official (2-4 per game; one
2024-25 game lists 4) has rest_days==0. crew_b2b_all = 1 iff EVERY listed official has
rest_days==0. NaN rest (no prior game on record) counts as "not confirmed 0" for both
variants -- conservative, never inflates b2b. Games with an EMPTY crew list (35 in 2024-25,
1203 of 2025-26's 1230) are dropped -- nothing to condition on.

Confound proxy (prereg point 5, declared here): weekend_flag = date.dayofweek in {Sat,Sun}.
marquee_flag = home_team or away_team in _MARQUEE, a declared 6-team list (largest-market /
most-nationally-televised franchises): LAL, BOS, GSW, NYK, CHI, MIA.

Verdict (per outcome, pf primary / fta secondary): REPLICATED_LOCAL only if crew_b2b_any's
sign matches AND p<0.05 in BOTH h1 and h2 (uncontrolled model), AND the pooled model with
weekend_flag+marquee_flag controls added keeps p<0.05 same sign. CONFOUNDED if it replicates
uncontrolled but the controlled pooled coefficient loses significance or flips sign.
NULL_LOCAL otherwise. edge_claimed=False always -- descriptive claim family, no bet action.

CLI: python -m scripts.platformkit.pod_sprint.crew_fatigue_r1
     writes data/domains/basketball_nba/crew_fatigue_r1.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats as _st

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.basketball_nba.knowledge._data import load_player_boxscores  # noqa: E402
from domains.basketball_nba.knowledge.validate_research_wave4 import (  # noqa: E402
    MIN_GAMES_PER_TEAM_SEASON)
from scripts.platformkit.io_atomic import write_json_atomic  # noqa: E402

_OFFICIALS_DIR = _REPO / "data" / "nba" / "officials"
_GAMES_PATH = _REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
_OUT = _REPO / "data" / "domains" / "basketball_nba" / "crew_fatigue_r1.json"

_DATED_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]  # games.parquet coverage
_OUTCOME_SEASONS = {"2023-24", "2024-25", "2025-26"}           # player_boxscores coverage
_MARQUEE = {"LAL", "BOS", "GSW", "NYK", "CHI", "MIA"}


def load_crew_long(games: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, official) across _DATED_SEASONS, joined to games.parquet
    dates (inner -- drops any officials game_id games.parquet doesn't have). Empty
    crew lists are skipped."""
    rows = []
    for season in _DATED_SEASONS:
        with open(_OFFICIALS_DIR / f"officials_{season}.json", encoding="utf-8") as f:
            crews = json.load(f)
        for game_id, names in crews.items():
            for name in names:
                rows.append({"game_id": game_id, "official": name})
    crew = pd.DataFrame(rows)
    return crew.merge(games[["game_id", "date"]], on="game_id", how="inner")


def crew_b2b_flags(crew_long: pd.DataFrame) -> pd.DataFrame:
    """Per-official rest_days (calendar days since that name's own previous listed
    game), then game-level crew_b2b_any / crew_b2b_all."""
    c = crew_long.sort_values(["official", "date"]).copy()
    c["rest_days"] = c.groupby("official")["date"].diff().dt.days - 1
    c["is_b2b"] = c["rest_days"] == 0  # NaN == 0 is False -- no leak, no false b2b
    return c.groupby("game_id").agg(
        crew_b2b_any=("is_b2b", "any"), crew_b2b_all=("is_b2b", "all"),
        n_officials=("official", "size")).reset_index()


def build_adjusted(box: pd.DataFrame, col: str, min_games: int = MIN_GAMES_PER_TEAM_SEASON) -> pd.DataFrame:
    """Mechanism #54's leave-one-out team-baseline adjustment (validate_research_wave4.py
    ::build_dataset), generalized from PF-only to any player_boxscores column."""
    tg = box.groupby(["game_id", "team", "season", "date"], as_index=False)[col].sum()
    season_sum = tg.groupby(["team", "season"])[col].transform("sum")
    season_n = tg.groupby(["team", "season"])[col].transform("size")
    tg["loo_mean"] = (season_sum - tg[col]) / (season_n - 1)
    tg = tg[season_n >= min_games].copy()
    rows = []
    for game_id, grp in tg.sort_values(["game_id", "team"]).groupby("game_id"):
        if len(grp) != 2:
            continue
        a, b = grp.iloc[0], grp.iloc[1]
        rows.append({"game_id": game_id, "date": a["date"], "season": a["season"],
                     f"lambda_{col}": a["loo_mean"] + b["loo_mean"],
                     f"observed_{col}": a[col] + b[col]})
    out = pd.DataFrame(rows, columns=["game_id", "date", "season", f"lambda_{col}", f"observed_{col}"])
    out[f"adjusted_{col}"] = out[f"observed_{col}"] - out[f"lambda_{col}"]
    return out


def _ols(df: pd.DataFrame, y: str, xs: List[str]) -> Dict[str, object]:
    """statsmodels OLS if installed, else numpy lstsq + manual (X'X)^-1 sigma^2 SE."""
    d = df[[y] + xs].dropna()
    n = len(d)
    if n < 5:
        return {"n": n, "coef": {}, "p": {}}
    yv = d[y].to_numpy(dtype=float)
    X = np.column_stack([np.ones(n)] + [d[c].to_numpy(dtype=float) for c in xs])
    names = ["const"] + xs
    try:
        import statsmodels.api as sm
        fit = sm.OLS(yv, X).fit()
        coefs, pvals = fit.params, fit.pvalues
    except ImportError:
        beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
        resid = yv - X @ beta
        dof = n - X.shape[1]
        sigma2 = float(resid @ resid) / dof
        se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
        tvals = beta / se
        coefs, pvals = beta, 2 * _st.t.sf(np.abs(tvals), dof)
    return {"n": n, "coef": {k: float(v) for k, v in zip(names, coefs)},
            "p": {k: float(v) for k, v in zip(names, pvals)}}


def _verdict(rows: List[Dict], controlled: Dict[str, Dict], outcome: str) -> str:
    h1 = next(r for r in rows if r["outcome"] == outcome and r["variant"] == "crew_b2b_any" and r["half"] == "h1")
    h2 = next(r for r in rows if r["outcome"] == outcome and r["variant"] == "crew_b2b_any" and r["half"] == "h2")
    if h1["coef"] is None or h2["coef"] is None or h1["p"] is None or h2["p"] is None:
        return "NOT_TESTABLE"
    same_sign = (h1["coef"] > 0) == (h2["coef"] > 0)
    both_sig = h1["p"] < 0.05 and h2["p"] < 0.05
    if not (same_sign and both_sig):
        return "NULL_LOCAL"
    c = controlled[outcome]
    ctrl_coef, ctrl_p = c["coef"].get("crew_b2b_any"), c["p"].get("crew_b2b_any")
    if ctrl_coef is None or ctrl_p is None:
        return "NULL_LOCAL"
    if ctrl_p < 0.05 and (ctrl_coef > 0) == (h1["coef"] > 0):
        return "REPLICATED_LOCAL"
    return "CONFOUNDED"


def run() -> Dict[str, object]:
    games = pd.read_parquet(_GAMES_PATH)
    box = load_player_boxscores()
    box = box[box["season"].isin(_OUTCOME_SEASONS)]

    crew_long = load_crew_long(games)
    flags = crew_b2b_flags(crew_long)

    adj_pf = build_adjusted(box, "pf")
    adj_fta = build_adjusted(box, "fta")
    analysis = adj_pf.merge(
        adj_fta[["game_id", "lambda_fta", "observed_fta", "adjusted_fta"]], on="game_id", how="inner")
    analysis = analysis.merge(flags, on="game_id", how="inner")
    analysis = analysis.merge(games[["game_id", "home_team", "away_team"]], on="game_id", how="left")
    analysis["weekend_flag"] = analysis["date"].dt.dayofweek.isin([5, 6]).astype(int)
    analysis["marquee_flag"] = (
        analysis["home_team"].isin(_MARQUEE) | analysis["away_team"].isin(_MARQUEE)).astype(int)
    analysis["crew_b2b_any"] = analysis["crew_b2b_any"].astype(int)
    analysis["crew_b2b_all"] = analysis["crew_b2b_all"].astype(int)
    analysis["half"] = np.where(analysis["season"] == "2023-24", "h1", "h2")

    halves = {"h1": analysis[analysis["half"] == "h1"], "h2": analysis[analysis["half"] == "h2"],
              "pooled": analysis}
    ols_rows = []
    for outcome in ("pf", "fta"):
        ycol = f"adjusted_{outcome}"
        for variant in ("crew_b2b_any", "crew_b2b_all"):
            for half_name, sub in halves.items():
                res = _ols(sub, ycol, [variant])
                ols_rows.append({"outcome": outcome, "variant": variant, "half": half_name,
                                  "n": res["n"], "coef": res["coef"].get(variant),
                                  "p": res["p"].get(variant)})

    controlled = {}
    for outcome in ("pf", "fta"):
        controlled[outcome] = _ols(analysis, f"adjusted_{outcome}", ["crew_b2b_any", "weekend_flag", "marquee_flag"])

    strata = analysis.groupby(["weekend_flag", "marquee_flag"])["crew_b2b_any"].mean().reset_index()
    strata_rows = [{"weekend_flag": int(r.weekend_flag), "marquee_flag": int(r.marquee_flag),
                     "crew_b2b_any_rate": float(r.crew_b2b_any)} for r in strata.itertuples()]

    verdict_pf = _verdict(ols_rows, controlled, "pf")
    verdict_fta = _verdict(ols_rows, controlled, "fta")

    return {
        "family": "R", "hypothesis": "crew_b2b_fatigue",
        "n_games_analyzed": int(len(analysis)), "n_h1": int(len(halves["h1"])), "n_h2": int(len(halves["h2"])),
        "deviation_from_prereg": "split-half run as 2023-24(h1) vs 2024-25+2025-26(h2), not "
                                  "2021-22+2022-23 vs 2023-24+2024-25 -- no PF/FTA outcome data "
                                  "exists locally before season 2023-24 (player_boxscores.parquet); "
                                  "see module docstring.",
        "marquee_teams": sorted(_MARQUEE),
        "ols_uncontrolled": ols_rows,
        "ols_controlled_pooled": {k: v for k, v in controlled.items()},
        "confound_strata_crew_b2b_any_rate": strata_rows,
        "verdict": {"pf": verdict_pf, "fta": verdict_fta},
        "edge_claimed": False,
    }


def _print_table(result: Dict[str, object]) -> None:
    print("Family R -- crew_b2b_fatigue (n_games=%d, h1=%d, h2=%d)" % (
        result["n_games_analyzed"], result["n_h1"], result["n_h2"]))
    print(result["deviation_from_prereg"])
    print("marquee teams: %s" % ", ".join(result["marquee_teams"]))
    print()
    print("%-6s %-14s %-8s %6s %12s %10s" % ("outcome", "variant", "half", "n", "coef", "p"))
    for r in result["ols_uncontrolled"]:
        coef = "%.4f" % r["coef"] if r["coef"] is not None else "NA"
        p = "%.4g" % r["p"] if r["p"] is not None else "NA"
        print("%-6s %-14s %-8s %6d %12s %10s" % (r["outcome"], r["variant"], r["half"], r["n"], coef, p))
    print()
    print("controlled pooled (crew_b2b_any + weekend_flag + marquee_flag):")
    for outcome, c in result["ols_controlled_pooled"].items():
        coef = c["coef"].get("crew_b2b_any")
        p = c["p"].get("crew_b2b_any")
        print("  %-4s n=%-6d crew_b2b_any coef=%s p=%s" % (
            outcome, c["n"], "%.4f" % coef if coef is not None else "NA",
            "%.4g" % p if p is not None else "NA"))
    print()
    print("crew_b2b_any rate by (weekend_flag, marquee_flag):")
    for r in result["confound_strata_crew_b2b_any_rate"]:
        print("  weekend=%d marquee=%d rate=%.4f" % (r["weekend_flag"], r["marquee_flag"], r["crew_b2b_any_rate"]))
    print()
    print("VERDICT pf=%s fta=%s (edge_claimed=%s)" % (
        result["verdict"]["pf"], result["verdict"]["fta"], result["edge_claimed"]))


def main() -> int:
    result = run()
    _print_table(result)
    write_json_atomic(_OUT, result, indent=2)
    print("\nwrote %s" % _OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
