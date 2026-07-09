"""domains.basketball_nba.composition.lineup_quality_conditioner -- the FIRST
COMPOSED multi-attribute lineup-quality conditioner. Counters the single-
attribute NULLs (game-level x5, in-game mechanism ladder) whose thesis is that
the QUESTION was too simple: attributes are tested here a DOZEN AT ONCE,
composed into one differential score, at the lineup-matchup-segment atomic unit
(game-clock, leak-free, large-n).

ATOMIC UNIT: a 5-on-5 matchup SEGMENT -- the maximal window where both teams'
lineups are constant. Rebuilt here from stints_<season>.parquet by the SAME
two-pointer interval merge domains/basketball_nba/lineups/lineup_matchups.py
validated, but carrying the segment's abs game-clock + running score (which the
period-SUMMED matchups parquet drops) so game-state H2 is testable.
# ponytail: local ~25-line merge, not an import of intersect_stints -- that
# helper discards abs_start/score, which H2 needs. Same logic, +2 fields.

PREREGISTERED (declared BEFORE running; K=2 hypotheses, Bonferroni alpha=0.05/2
=0.025). NOT extended after seeing results.

  DECLARED 12-ATTRIBUTE BASKET (equal weights, DECLARED signs from basketball
  priors -- NOT fit to outcome; the whole point is composition, not weight
  optimization). sign +1 = higher raw is better for the team's net margin:
    gravity(+), spacing_contribution(+), usage_absorption(+), halfcourt_efg(+),
    transition_efg(+), late_clock_efg(+), clutch_efg(+), zone_efg_rim(+),
    rim_pressure_def(+ better rim deterrence), team_dreb_pct_swing(+ lifts team
    DREB when on), opp_ft_rate_allowed_on(- allows more FTs = worse D),
    stint_minutes_load(+ heavy-minutes coach-trust role).
  Each attr is z-scored across the PRIOR-season player population, signed, and
  summed per player; a lineup's composite = sum of its 5 players' composites; a
  segment's composite_diff = home(team_a) composite - away(team_b) composite.

  AS-OF TEMPORAL CONVENTION (strict, leak-free): a season's stints are
  conditioned ONLY by the PRIOR season's profile window (matching the attribute
  gate's convention). 2025-26 stints <- season_2024_25 profiles; 2024-25 stints
  <- season_2023_24 profiles. A season's OWN profile value NEVER enters its own
  stints. 2023-24 stints are EXCLUDED (no season_2022_23 profiles on disk) --
  documented exclusion, not a silent median-fill. Missing player -> 0 (neutral
  in z-space), coverage logged.

  H1 'composed lineup quality': does composite_diff improve OOS stint-margin
     prediction over baseline [score_margin_at_start + time_remaining +
     as-of team strength diff]? Walk-forward: FIT on 2024-25 segments, TEST on
     2025-26. Reported as OOS weighted-RMSE delta AND the cluster-robust
     composite_diff coefficient p on the test season (Bonferroni K=2), with a
     same-sign replication on the train season.
  H2 'composed quality x game state': composite_diff:close_late interaction
     (close_late := |score_margin_start|<=6 AND time_remaining<=360s, declared
     now) on the test season -- does the composite matter MORE close-and-late?

OUTCOME y = (pts_a - pts_b)/overlap_s * 2880 (net rating per 48), weighted by
overlap_s, cluster-robust SEs by game_id. Floors: overlap_s>=30 (declared);
H2 NOT_TESTABLE if <200 close_late segments.

Descriptive / calibration only. edge_claimed hard-wired False. A NULL is a
SUCCESS. NETWORK: zero. ASCII only.
CLI:  python -m domains.basketball_nba.composition.lineup_quality_conditioner
Test: python -m pytest domains/basketball_nba/composition/test_lineup_quality_conditioner.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
PLAYER_PROFILES = REPO_ROOT / "data" / "cache" / "profiles" / "nba_player_profiles.parquet"
TEAM_PROFILES = REPO_ROOT / "data" / "cache" / "profiles" / "nba_team_profiles.parquet"
LEDGER_PATH = REPO_ROOT / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
REPORT_PATH = REPO_ROOT / "data" / "frontend" / "ops" / "nba_lineup_quality_composition.json"

METHOD = "lineup_quality_composition_v1"
ALPHA = 0.05 / 2                     # K=2 Bonferroni, declared in the brief
MIN_OVERLAP_S = 30.0                 # declared segment floor
CLOSE_LATE_MIN_N = 200               # declared H2 testability floor
TRAIN_TAG, TEST_TAG = "2024_25", "2025_26"
PRIOR_WINDOW = {                     # season stints -> PRIOR season profile window (as-of)
    "2025_26": "season_2024_25",
    "2024_25": "season_2023_24",
    "2023_24": None,                 # no season_2022_23 on disk -> excluded
}
# (attribute, sign): sign is DECLARED from basketball priors, never fit.
BASKET: Tuple[Tuple[str, int], ...] = (
    ("gravity", 1), ("spacing_contribution", 1), ("usage_absorption", 1),
    ("halfcourt_efg", 1), ("transition_efg", 1), ("late_clock_efg", 1),
    ("clutch_efg", 1), ("zone_efg_rim", 1), ("rim_pressure_def", 1),
    ("team_dreb_pct_swing", 1), ("opp_ft_rate_allowed_on", -1),
    ("stint_minutes_load", 1),
)


def _period_len(period: int) -> float:
    return 720.0 if period <= 4 else 300.0  # ponytail: OT=300s, same as pbp_lineups.py


def _abs_offset(period: int) -> float:
    return sum(_period_len(q) for q in range(1, period))


def load_player_composite(prior_window: str, path: Path = PLAYER_PROFILES) -> Tuple[Dict[int, float], float]:
    """Per-player composite = sum of the 12 BASKET attributes, each z-scored
    across THIS prior window's player population and signed. Returns
    {player_id: composite} and mean coverage (fraction of the 12 present).
    Empty window -> empty dict (caller documents the exclusion)."""
    p = pd.read_parquet(path)
    p = p[p["window"] == prior_window]
    if p.empty:
        return {}, 0.0
    wide = p.pivot_table(index="entity_id", columns="attribute", values="raw_value", aggfunc="first")
    z = pd.DataFrame(index=wide.index)
    present = pd.Series(0, index=wide.index, dtype=int)
    for attr, sign in BASKET:
        if attr not in wide.columns:
            continue
        col = wide[attr]
        sd = col.std(ddof=0)
        if sd == 0 or pd.isna(sd):
            continue
        zc = sign * (col - col.mean()) / sd
        z[attr] = zc
        present = present + zc.notna().astype(int)
    if z.empty:
        return {}, 0.0
    comp = z.fillna(0.0).sum(axis=1)
    comp.index = comp.index.astype("int64")  # landmine: negative placeholder ids overflow int32
    coverage = float(present.mean() / len(BASKET))
    return comp.to_dict(), coverage


def load_team_strength(prior_window: str, path: Path = TEAM_PROFILES) -> Dict[int, float]:
    """As-of team strength = prior-season avg of net_rating_home/away, per team."""
    tp = pd.read_parquet(path)
    tp = tp[(tp["window"] == prior_window) & (tp["attribute"].isin(["net_rating_home", "net_rating_away"]))]
    if tp.empty:
        return {}
    s = tp.groupby("entity_id")["raw_value"].mean()
    s.index = s.index.astype("int64")
    return s.to_dict()


def build_segments(stints_df: pd.DataFrame) -> pd.DataFrame:
    """5-on-5 matchup segments with abs game-clock + running score. team_a =
    the smaller team_id (deterministic; y and score_margin share this frame)."""
    rows: List[Dict[str, Any]] = []
    for game_id, g in stints_df.groupby("game_id"):
        teams = sorted(g["team_id"].unique())
        if len(teams) != 2:
            continue  # ponytail: skip non-2-team games rather than guess a pairing
        ta, tb = teams
        game_len = sum(_period_len(p) for p in sorted(g["period"].unique()))
        for period, pg in g.groupby("period"):
            A = pg[(pg["team_id"] == ta) & (pg["n_on_court"] == 5)].sort_values("start_s").to_dict("records")
            B = pg[(pg["team_id"] == tb) & (pg["n_on_court"] == 5)].sort_values("start_s").to_dict("records")
            off, i, j = _abs_offset(period), 0, 0
            while i < len(A) and j < len(B):
                a, b = A[i], B[j]
                s, e = max(a["start_s"], b["start_s"]), min(a["end_s"], b["end_s"])
                if s < e:
                    ov = e - s
                    pa = a["pts_for"] * ov / a["elapsed_s"] if a["elapsed_s"] > 0 else 0.0
                    pb = b["pts_for"] * ov / b["elapsed_s"] if b["elapsed_s"] > 0 else 0.0
                    rows.append({"game_id": game_id, "team_id_a": ta, "team_id_b": tb,
                                 "lineup_key_a": a["lineup_key"], "lineup_key_b": b["lineup_key"],
                                 "overlap_s": ov, "pts_a": pa, "pts_b": pb,
                                 "abs_start": off + s, "game_len": game_len})
                if a["end_s"] < b["end_s"]:
                    i += 1
                elif b["end_s"] < a["end_s"]:
                    j += 1
                else:
                    i += 1
                    j += 1
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["game_id", "abs_start"]).reset_index(drop=True)
    df["net"] = df["pts_a"] - df["pts_b"]
    df["score_margin_start"] = df.groupby("game_id")["net"].cumsum() - df["net"]
    df["time_remaining"] = df["game_len"] - df["abs_start"]
    return df


def _lineup_comp(lineup_key: str, comp: Dict[int, float]) -> float:
    return float(sum(comp.get(int(x), 0.0) for x in str(lineup_key).split(",") if x != ""))


def build_frame(season_tag: str, stints_df: Optional[pd.DataFrame] = None,
                player_path: Path = PLAYER_PROFILES, team_path: Path = TEAM_PROFILES) -> Optional[pd.DataFrame]:
    """Full modeling frame for one season, conditioned strictly by the PRIOR
    season profile window. Returns None for an excluded season (no prior)."""
    prior = PRIOR_WINDOW.get(season_tag)
    if prior is None:
        return None
    if stints_df is None:
        stints_df = pd.read_parquet(_LINEUPS_DIR / f"stints_{season_tag}.parquet")
    comp, coverage = load_player_composite(prior, player_path)
    strength = load_team_strength(prior, team_path)
    seg = build_segments(stints_df)
    if seg.empty:
        return seg
    seg = seg[seg["overlap_s"] >= MIN_OVERLAP_S].copy()
    seg["composite_a"] = seg["lineup_key_a"].map(lambda k: _lineup_comp(k, comp))
    seg["composite_b"] = seg["lineup_key_b"].map(lambda k: _lineup_comp(k, comp))
    seg["composite_diff"] = seg["composite_a"] - seg["composite_b"]
    seg["strength_diff"] = seg["team_id_a"].map(strength) - seg["team_id_b"].map(strength)
    seg["y"] = (seg["pts_a"] - seg["pts_b"]) / seg["overlap_s"] * 2880.0
    seg["close_late"] = ((seg["score_margin_start"].abs() <= 6) & (seg["time_remaining"] <= 360)).astype(int)
    seg.attrs["coverage"] = coverage
    return seg


_MODEL_COLS = ["y", "score_margin_start", "time_remaining", "strength_diff", "composite_diff", "overlap_s", "game_id"]
_BASE = "y ~ score_margin_start + time_remaining + strength_diff"


def fit_term(df: pd.DataFrame, formula: str, term: str) -> Dict[str, Any]:
    """WLS (overlap_s weights) + cluster-robust SEs by game_id; return `term`'s
    effect + p. n=0 guard so an empty frame is NOT_TESTABLE, not a crash."""
    d = df.dropna(subset=[c for c in _MODEL_COLS if c in df.columns] + (["close_late"] if "close_late" in df.columns else []))
    if len(d) == 0:
        return {"effect": None, "p": None, "n": 0}
    res = smf.wls(formula, data=d, weights=d["overlap_s"]).fit(cov_type="cluster", cov_kwds={"groups": d["game_id"]})
    if term not in res.params.index:
        return {"effect": None, "p": None, "n": int(res.nobs)}
    return {"effect": float(res.params[term]), "p": float(res.pvalues[term]), "n": int(res.nobs)}


def oos_delta(train: pd.DataFrame, test: pd.DataFrame) -> Dict[str, Any]:
    """Walk-forward: fit baseline and baseline+composite on TRAIN, predict TEST,
    weighted RMSE. delta>0 => composite improves OOS margin prediction."""
    tr = train.dropna(subset=_MODEL_COLS)
    te = test.dropna(subset=_MODEL_COLS)
    if len(tr) == 0 or len(te) == 0:
        return {"rmse_base": None, "rmse_full": None, "delta_rmse": None, "n_test": len(te)}

    def _wrmse(formula: str) -> float:
        res = smf.wls(formula, data=tr, weights=tr["overlap_s"]).fit()
        pred = res.predict(te)
        w = te["overlap_s"]
        return float(np.sqrt((w * (te["y"] - pred) ** 2).sum() / w.sum()))

    rb, rf = _wrmse(_BASE), _wrmse(_BASE + " + composite_diff")
    return {"rmse_base": rb, "rmse_full": rf, "delta_rmse": rb - rf, "n_test": len(te)}


def _verdict(p: Optional[float], n: int, sign_ref: Optional[int] = None,
             effect: Optional[float] = None, min_n: int = 1) -> str:
    if n < min_n or p is None:
        return "NOT_TESTABLE"
    if sign_ref is not None:
        return "REPLICATED" if (p < ALPHA and (effect > 0) == (sign_ref > 0)) else "FAILED_REPLICATION"
    return "SURVIVES_PREREG" if p < ALPHA else "NULL"


def run() -> Dict[str, Any]:
    train, test = build_frame(TRAIN_TAG), build_frame(TEST_TAG)
    rows: List[Dict[str, Any]] = []
    cov_test = float(test.attrs.get("coverage", 0.0)) if test is not None else 0.0

    # H1 primary on TEST season (2025-26, conditioned by 2024-25 profiles)
    h1 = fit_term(test, _BASE + " + composite_diff", "composite_diff")
    v1 = _verdict(h1["p"], h1["n"])
    oos = oos_delta(train, test)
    # H1 replication on TRAIN season (2024-25, conditioned by 2023-24 profiles)
    h1r = fit_term(train, _BASE + " + composite_diff", "composite_diff")
    sign_ref = None if h1["effect"] is None else (1 if h1["effect"] > 0 else -1)
    v1r = _verdict(h1r["p"], h1r["n"], sign_ref=sign_ref, effect=h1r["effect"])

    # H2 interaction on TEST season
    n_cl = int(test["close_late"].sum()) if test is not None and len(test) else 0
    if n_cl < CLOSE_LATE_MIN_N:
        h2, v2 = {"effect": None, "p": None, "n": n_cl}, "NOT_TESTABLE"
    else:
        h2 = fit_term(test, _BASE + " + composite_diff * close_late", "composite_diff:close_late")
        v2 = _verdict(h2["p"], h2["n"])

    for name, fit, verd, term in [
        ("H1_composed_lineup_quality", h1, v1, "composite_diff"),
        ("H1_composed_lineup_quality_replication_2024_25", h1r, v1r, "composite_diff"),
        ("H2_composed_quality_x_close_late", h2, v2, "composite_diff:close_late"),
    ]:
        rows.append({
            "hypothesis": name, "sport": "nba", "atomic_unit": "lineup_segment_asof", "method": METHOD,
            "season": f"walkforward_train_{TRAIN_TAG}_test_{TEST_TAG}",
            "n": fit["n"], "effect": fit["effect"], "p": fit["p"], "alpha_fwer": ALPHA,
            "term": term, "verdict": verd,
            "note": "PROVISIONAL -- needs independent replication" if verd == "SURVIVES_PREREG" else "",
            "edge_claimed": False,
        })

    report = {
        "method": METHOD, "generated_by": "domains/basketball_nba/composition/lineup_quality_conditioner.py",
        "atomic_unit": "lineup_segment_asof", "alpha_fwer_K2": ALPHA,
        "walkforward": {"train_season": TRAIN_TAG, "train_prior_window": PRIOR_WINDOW[TRAIN_TAG],
                        "test_season": TEST_TAG, "test_prior_window": PRIOR_WINDOW[TEST_TAG],
                        "excluded_season": "2023_24 (no season_2022_23 prior profiles)"},
        "basket": [{"attribute": a, "sign": s} for a, s in BASKET],
        "coverage_mean_test": cov_test,
        "H1": {"verdict": v1, **h1, "oos": oos, "replication_2024_25": {"verdict": v1r, **h1r}},
        "H2": {"verdict": v2, "close_late_n": n_cl, **h2},
        "edge_claimed": False,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="ascii")
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return report


def main() -> int:
    rep = run()
    print(f"K=2 alpha_bonferroni={ALPHA:.4f}  basket={len(BASKET)} attrs  coverage_test={rep['coverage_mean_test']:.3f}")
    h1, oos = rep["H1"], rep["H1"]["oos"]
    print(f"  H1 [{h1['verdict']:>16}] composite_diff: n={h1['n']} effect={h1['effect']} p={h1['p']}")
    print(f"     OOS wRMSE base={oos['rmse_base']} full={oos['rmse_full']} delta={oos['delta_rmse']} (>0 helps)")
    print(f"     replication_2024_25 [{h1['replication_2024_25']['verdict']}]")
    h2 = rep["H2"]
    print(f"  H2 [{h2['verdict']:>16}] composite_diff:close_late: n={h2['n']} close_late_n={h2['close_late_n']} p={h2['p']}")
    print(f"  report -> {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
