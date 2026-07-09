"""domains.tennis.composition.pressure_composite -- COMPOSED pressure profile
(the composition directive at the point level, n=728k charting_points).

DECLARED BASKET (8 signals, equal-weight z-composite, preregistered before
running): bp_serve_delta, gp_serve_delta, sp_serve_delta, tb_delta,
deuce_delta, bp_return_delta, pressure_serve, set3plus_stamina.
  - The first 6 + bp_return_delta are (situation win-rate - that role's own
    whole-window win-rate) deltas, one per (situation, role) in
    pressure_situations.SITUATIONS x {serve,return} -- same delta convention
    as pressure_point_claims.py's descriptive family (baseline is over ALL
    of that role's points, situational points included).
  - pressure_serve is IDENTICAL to bp_serve_delta by construction (same
    formula the task's basket independently names as attribute_registry.py's
    VALIDATED_MECHANISM ingredient) -- kept as its own basket slot per the
    task spec; this makes it fully colinear with slot 1, a declared caveat,
    not a bug.
  - set3plus_stamina is a raw rate (not a delta): server win rate on points
    played in set 3+ (attribute_registry.py's stamina-proxy formula), same
    as-of/prior-years-only construction as the deltas.

AS-OF (walk-forward): for a player-year (player, Y), every basket ingredient
uses ONLY points from years < Y -- per-player cumulative sums, sorted
ascending, current-year row's own contribution excluded before dividing.
Z-scoring is done ONCE across the full population of ELIGIBLE (floor-
clearing) player-year rows -- inputs are already prior-only per row, so
standardizing against the contemporaneous population scale carries no
outcome leak (it only rescales already-leak-free numbers).

MIN COVERAGE FLOOR: a player-year needs >=200 prior high-leverage points
(break_point OR set_point OR tiebreak_point, either role, summed) to get a
composite; below-floor player-years are EXCLUDED with counts reported (see
build_composite_table + add_composite).

PREREGISTERED TEST (K=2, Bonferroni alpha=0.025, same ALPHA as
prereg_point_mechanisms.py):
  H1 composed pressure profile: on HIGH-LEVERAGE points (break_point,
    set_point, or tiebreak_point) in test years >= TEST_YEAR_MIN, does
    (server_composite - returner_composite) predict server_won beyond a
    baseline of server's as-of overall serve-win-rate + returner's as-of
    overall return-win-rate + surface? Logistic, cluster-robust SE by
    match_id. The baseline strengths reuse prereg_point_mechanisms.py's own
    date-batched as-of walk-forward machinery (_match_level_agg +
    asof_walkforward) over the FULL point corpus -- same leak discipline,
    same MIN_PRIOR_PTS floor. "Walk-forward by year" is baked into how every
    per-point feature (composite AND baseline strengths) is built -- one
    pooled cluster-robust fit over all qualifying test-year points, matching
    prereg_point_mechanisms.py's H2 precedent (not a separate refit per
    year).
  H2 pressure x situation severity: same regression frame, does the
    pressure_diff:severe interaction matter, where severe=1 on
    set_point/tiebreak_point rows (declared MORE severe than a garden-
    variety break_point) and severe=0 on plain break_point rows?

edge_claimed hard-wired False everywhere. NETWORK: zero. Corpora READ-ONLY.
CLI: python -m domains.tennis.composition.pressure_composite
Per-file test: python -m pytest domains/tennis/composition/test_pressure_composite.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from domains.tennis.prereg_point_mechanisms import (
    ALPHA, MIN_PRIOR_PTS, REPO_ROOT, _CHART_PATH, _charting_match_ids,
    _corpus_row, _id_frame, _match_level_agg, append_ledger, asof_walkforward,
    charting_point_state,
)
from domains.tennis.pressure_point_claims import build_long_table
from domains.tennis.pressure_situations import charting_situation_state
from domains.tennis.profiles.ingredients import _charting_surfaces

OUT_PATH = REPO_ROOT / "data/frontend/ops/tennis_pressure_composition.json"

HL_FLOOR = 200          # prior high-leverage points needed for a composite
TEST_YEAR_MIN = 2018    # walk-forward test window (task-declared "2018+")

# (basket_slot -> (situation, role)); pressure_serve is copied from bp_serve_delta below.
INGREDIENT_SPEC: Dict[str, Tuple[str, str]] = {
    "bp_serve_delta": ("break_point", "serve"),
    "gp_serve_delta": ("game_point", "serve"),
    "sp_serve_delta": ("set_point", "serve"),
    "tb_delta": ("tiebreak_point", "serve"),
    "deuce_delta": ("deuce_battle", "serve"),
    "bp_return_delta": ("break_point", "return"),
}
BASKET = tuple(INGREDIENT_SPEC) + ("pressure_serve", "set3plus_stamina")


def _asof_prior(df: pd.DataFrame, sum_cols: List[str]) -> pd.DataFrame:
    """Adds `<col>_prior` = cumulative sum over STRICTLY EARLIER years for the
    same player_name (one row per (player_name, year), sorted ascending)."""
    d = df.sort_values(["player_name", "year"]).reset_index(drop=True)
    g = d.groupby("player_name")
    for c in sum_cols:
        d[f"{c}_prior"] = g[c].cumsum() - d[c]
    return d


def _delta_yearly(long_df: pd.DataFrame, situation: str, role: str) -> pd.DataFrame:
    """Per (player_name, year): as-of (prior-years-only) situational delta =
    situ_win_rate - role's own whole-window win_rate (same baseline
    convention as pressure_point_claims.py)."""
    scoped = long_df[long_df["role"] == role]
    base = scoped.groupby(["player_name", "year"])["won"].agg(base_won="sum", base_n="count")
    situ = scoped[scoped[situation]].groupby(["player_name", "year"])["won"].agg(situ_won="sum", situ_n="count")
    yearly = base.join(situ, how="left").fillna(0.0).reset_index()
    yearly = _asof_prior(yearly, ["base_won", "base_n", "situ_won", "situ_n"])
    situ_rate = yearly["situ_won_prior"] / yearly["situ_n_prior"].replace(0, np.nan)
    base_rate = yearly["base_won_prior"] / yearly["base_n_prior"].replace(0, np.nan)
    yearly["value"] = situ_rate - base_rate
    return yearly[["player_name", "year", "value"]]


def _high_leverage_yearly(long_df: pd.DataFrame) -> pd.DataFrame:
    """Per (player_name, year): as-of prior count of high-leverage point
    involvement (break_point OR set_point OR tiebreak_point, either role)."""
    hl = long_df.assign(hl=(long_df["break_point"] | long_df["set_point"] | long_df["tiebreak_point"]).astype(int))
    yearly = hl.groupby(["player_name", "year"])["hl"].sum().reset_index(name="hl_n")
    yearly = _asof_prior(yearly, ["hl_n"])
    return yearly[["player_name", "year", "hl_n_prior"]]


def _set3plus_yearly(chart_raw: pd.DataFrame, id_map: Dict[str, tuple], player_years: pd.DataFrame) -> pd.DataFrame:
    """Per (player_name, year): as-of prior server win rate on points played
    in set 3+ (attribute_registry.py's stamina-proxy formula), continuous
    over `player_years` (0-fill years with no set3+ activity, so the prior
    cumsum still carries forward correctly)."""
    d = chart_raw[(chart_raw["date_source"] != "missing") & chart_raw["server"].isin((1, 2))
                  & chart_raw["point_winner"].isin((1, 2))].copy()
    d["year"] = pd.to_datetime(d["date"]).dt.year
    set1 = pd.to_numeric(d["set1"], errors="coerce")
    set2 = pd.to_numeric(d["set2"], errors="coerce")
    d["set3plus"] = ((set1 + set2 + 1) >= 3).fillna(False)
    d["won"] = (d["point_winner"].astype(int) == d["server"].astype(int)).astype(int)
    d = d.merge(_id_frame(id_map), on="match_id", how="left")
    d["player_name"] = np.where(d["server"].astype(int) == 1, d["p1_id"], d["p2_id"])

    n3_won = d[d["set3plus"]].groupby(["player_name", "year"])["won"].sum().rename("n3_won")
    n3_n = d.groupby(["player_name", "year"])["set3plus"].sum().rename("n3_n")
    yearly = player_years.merge(n3_won, on=["player_name", "year"], how="left") \
                          .merge(n3_n, on=["player_name", "year"], how="left").fillna(0.0)
    yearly = _asof_prior(yearly, ["n3_won", "n3_n"])
    yearly["value"] = yearly["n3_won_prior"] / yearly["n3_n_prior"].replace(0, np.nan)
    return yearly[["player_name", "year", "value"]]


def build_composite_table(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """One row per (player_name, year) with the 8 as-of basket ingredients
    + hl_n_prior (the eligibility floor input). No z-scoring/filtering here
    (see add_composite) -- this is the raw, unfiltered ingredient table."""
    long_df = build_long_table(chart_raw)
    long_df["year"] = pd.to_datetime(long_df["date"]).dt.year

    ing = _high_leverage_yearly(long_df)
    for name, (situation, role) in INGREDIENT_SPEC.items():
        yearly = _delta_yearly(long_df, situation, role).rename(columns={"value": name})
        ing = ing.merge(yearly, on=["player_name", "year"], how="left")
    ing["pressure_serve"] = ing["bp_serve_delta"]

    id_map = _charting_match_ids(chart_raw["match_id"])
    s3 = _set3plus_yearly(chart_raw, id_map, ing[["player_name", "year"]])
    ing = ing.merge(s3.rename(columns={"value": "set3plus_stamina"}), on=["player_name", "year"], how="left")
    return ing


def add_composite(ing: pd.DataFrame, floor: int = HL_FLOOR) -> Tuple[pd.DataFrame, int, int]:
    """Filters to floor-eligible player-years, z-scores each basket column
    across that eligible population, composite = row mean of available z's.
    Returns (eligible_with_composite, n_considered, n_excluded_below_floor)."""
    n_considered = len(ing)
    elig = ing[ing["hl_n_prior"] >= floor].copy()
    n_excluded = n_considered - len(elig)
    z = pd.DataFrame(index=elig.index)
    for col in BASKET:
        mu, sd = elig[col].mean(), elig[col].std(ddof=0)
        z[col] = (elig[col] - mu) / sd if pd.notna(sd) and sd > 0 else np.nan
    elig["pressure_composite"] = z.mean(axis=1, skipna=True)
    return elig, n_considered, n_excluded


def build_regression_frame(chart_raw: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """High-leverage points (test years only) joined to: as-of baseline serve/
    return strength (prereg_point_mechanisms' own walk-forward machinery, full
    corpus), the as-of pressure composite (server & returner), and surface."""
    id_map = _charting_match_ids(chart_raw["match_id"])
    state = charting_situation_state(chart_raw).merge(_id_frame(id_map), on="match_id", how="left")
    is_p1_server = state["server"].to_numpy() == 1
    state["server_name"] = np.where(is_p1_server, state["p1_id"], state["p2_id"])
    state["returner_name"] = np.where(is_p1_server, state["p2_id"], state["p1_id"])
    state["year"] = pd.to_datetime(state["date"]).dt.year
    hl_mask = state["break_point"] | state["set_point"] | state["tiebreak_point"]
    pts = state[hl_mask & (state["year"] >= TEST_YEAR_MIN)].copy()
    pts["severe"] = (pts["set_point"] | pts["tiebreak_point"]).astype(int)

    full_state = charting_point_state(chart_raw)
    snap = asof_walkforward(_match_level_agg(full_state, id_map)).set_index(["match_id", "player_id"])
    snap_s = snap.reindex(list(zip(pts["match_id"], pts["server_name"])))
    snap_r = snap.reindex(list(zip(pts["match_id"], pts["returner_name"])))
    pts = pts.assign(serve_str=snap_s["serve_str"].to_numpy(), serve_n_prior=snap_s["serve_n_prior"].to_numpy(),
                      return_str=snap_r["return_str"].to_numpy(), return_n_prior=snap_r["return_n_prior"].to_numpy())
    pts = pts[(pts["serve_n_prior"] >= MIN_PRIOR_PTS) & (pts["return_n_prior"] >= MIN_PRIOR_PTS)]
    pts = pts.dropna(subset=["serve_str", "return_str"])

    ing = build_composite_table(chart_raw)
    elig, n_considered, n_excluded = add_composite(ing)
    comp = elig.set_index(["player_name", "year"])["pressure_composite"]
    pts = pts.assign(server_composite=comp.reindex(list(zip(pts["server_name"], pts["year"]))).to_numpy(),
                      returner_composite=comp.reindex(list(zip(pts["returner_name"], pts["year"]))).to_numpy())
    pts = pts.dropna(subset=["server_composite", "returner_composite"])
    pts["pressure_diff"] = pts["server_composite"] - pts["returner_composite"]

    pts = pts.merge(_charting_surfaces(), on="match_id", how="inner")
    meta = {"n_considered_player_years": n_considered, "n_excluded_below_floor": n_excluded, "hl_floor": HL_FLOOR}
    return pts, meta


def h1_fit(pts: pd.DataFrame) -> Dict[str, Any]:
    if pts.empty:
        return {"n": 0, "effect": None, "p": None, "term": "pressure_diff"}
    res = smf.logit("server_won ~ serve_str + return_str + C(surface) + pressure_diff", data=pts) \
             .fit(disp=0, cov_type="cluster", cov_kwds={"groups": pts["match_id"]})
    return {"n": int(res.nobs), "effect": float(res.params["pressure_diff"]),
            "p": float(res.pvalues["pressure_diff"]), "term": "pressure_diff"}


def h2_fit(pts: pd.DataFrame) -> Dict[str, Any]:
    term = "pressure_diff:severe"
    if pts.empty or pts["severe"].nunique() < 2:
        return {"n": 0, "effect": None, "p": None, "term": term}
    res = smf.logit("server_won ~ serve_str + return_str + C(surface) + pressure_diff*severe", data=pts) \
             .fit(disp=0, cov_type="cluster", cov_kwds={"groups": pts["match_id"]})
    return {"n": int(res.nobs), "effect": float(res.params[term]), "p": float(res.pvalues[term]), "term": term}


def run() -> Dict[str, Any]:
    chart_raw = pd.read_parquet(_CHART_PATH)
    pts, meta = build_regression_frame(chart_raw)
    fit1, fit2 = h1_fit(pts), h2_fit(pts)
    rows = [
        _corpus_row("H1 composed pressure profile", "charting_points_2018plus_highleverage", "point", fit1),
        _corpus_row("H2 pressure x situation severity", "charting_points_2018plus_highleverage", "point", fit2),
    ]
    append_ledger(rows)
    out = {
        "basket": list(BASKET), "hl_floor": HL_FLOOR, "test_year_min": TEST_YEAR_MIN,
        "alpha_fwer": ALPHA, "n_regression_points": len(pts), **meta,
        "h1": rows[0], "h2": rows[1], "edge_claimed": False,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="ascii", errors="strict")
    return out


def main() -> int:
    result = run()
    print(f"K=2 alpha_bonferroni={ALPHA} -- tennis composed pressure profile")
    print(f"  basket={result['basket']}")
    print(f"  player-years: considered={result['n_considered_player_years']} "
          f"excluded_below_floor={result['n_excluded_below_floor']} (floor={HL_FLOOR})")
    for key in ("h1", "h2"):
        r = result[key]
        print(f"  [{r['verdict']:>18}] {r['hypothesis']}: n={r['n']} effect={r['effect']} p={r['p']}")
    print(f"wrote -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
