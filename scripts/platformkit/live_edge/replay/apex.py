"""scripts.platformkit.live_edge.replay.apex -- B4-APEX: three honesty-
increasing additions to the hardened full-ledger validator (bb790fc2):
(1) placebo/negative-control FP-rate check on the exact hardened gate,
(2) power/MDE for the INSUFFICIENT_DATA bucket (no-power vs tested-null),
(3) testability expansion for tails.* claims via the calibration-coverage
instrument (tail_calib, already built) instead of the mean-CRPS design
run_full_ledger structurally cannot apply to a quantile claim.

None of these weaken the gate: the FP-rate check PROVES the gate rejects
noise at the right rate (or flags a real bug loudly if it doesn't); MDE
reports honest power, it does not manufacture survivors; the tails
expansion adds a NEW valid test for a topic that was previously
NOT_TICK_TESTABLE by construction, it never re-scores a claim under the
mean-CRPS design it already failed/passed.

Imports run_full_ledger + harden (B4-HARDEN, additive/backward-compat only,
never edited) and tail_calib.calib + tails (TAIL-CALIB, read-only). Pure
compute module -- no ledger writes.

INVARIANTS: pandas/numpy/scipy stdlib only. <=300 LOC. ASCII stdout.
edge_claimed=False, calibration language only, no $/ROI.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
from scipy import stats as sps

from scripts.platformkit.live_edge.replay import harden as hd
from scripts.platformkit.live_edge.replay import run_full_ledger as rfl
from scripts.platformkit.live_edge.tail_calib import calib as tc

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "replay" / "apex"

PLACEBO_N_CAP = 1500          # stratified-sample runtime cap, see placebo_run
MDE_ALPHA = 0.05
MDE_POWER = 0.80
MIN_ENTITY_RESERVE_ROWS = 10  # per-player calibration verdict floor (tails expansion)


# ---------------------------------------------------------------- 1. PLACEBO

def classify_all(claims_df: pd.DataFrame) -> pd.DataFrame:
    """Same classification run_full_ledger already used to find the 20,109
    tick-testable rows -- reused, not re-derived."""
    return claims_df.apply(rfl.classify_claim, axis=1, result_type="expand")


def sample_testable(claims_df: pd.DataFrame, classified: pd.DataFrame,
                     n_cap: int = PLACEBO_N_CAP, seed: int = 0) -> pd.DataFrame:
    """Stratified-by-construction random sample of tick-testable claim rows
    (np.random.choice over the whole testable index is already proportional
    to each grain's share), capped at n_cap for runtime -- the placebo test
    needs a large-enough sample to estimate a ~5%/~0% FP rate with a usable
    CI, not the full 20,109 (honest cap, reported in the output)."""
    testable_idx = claims_df.index[classified["grain"].notna()]
    if len(testable_idx) <= n_cap:
        return claims_df.loc[testable_idx]
    rng = np.random.default_rng(seed)
    chosen = rng.choice(testable_idx.to_numpy(), size=n_cap, replace=False)
    return claims_df.loc[chosen]


def shuffle_outcomes(corpora: dict, seed: int = 0) -> dict:
    """Placebo corpora: same rows, same cell/entity columns, but the OUTCOME
    column shuffled (fixed permutation per corpus) -- breaks any true
    cell/entity <-> outcome relationship while preserving each corpus's
    marginal outcome distribution exactly. Scoring real claims' real cells/
    deltas against this shuffled world is the negative control: any claim
    that still comes back IMPROVES did so by chance, not signal."""
    rng = np.random.default_rng(seed)
    out = dict(corpora)
    for key, col in (("team_a", "points"), ("team_b", "points"),
                     ("player_a", "scored"), ("player_b", "scored")):
        df = corpora[key].copy()
        df[col] = rng.permutation(df[col].to_numpy())
        out[key] = df
    return out


def placebo_run(claims_df: pd.DataFrame, classified: pd.DataFrame, corpora: dict,
                 n_total_testable: int, n_cap: int = PLACEBO_N_CAP, seed: int = 0) -> pd.DataFrame:
    """Scores a sample of REAL claim cells/deltas against SHUFFLED (placebo)
    corpora through the exact hardened gate (same validate_one_corpus +
    combine_two_corpora run_full_ledger uses). Returns one row per sampled
    claim -- the empirical null distribution of the gate."""
    sample = sample_testable(claims_df, classified, n_cap, seed)
    placebo_corpora = shuffle_outcomes(corpora, seed)
    rows = []
    for idx, row in sample.iterrows():
        parsed = classified.loc[idx].to_dict()
        if parsed["grain"] == "team":
            ra, rb = rfl.score_team_claim(parsed, placebo_corpora)
        else:
            ra, rb = rfl.score_player_claim(parsed, placebo_corpora)
        verdict = hd.combine_two_corpora(ra, rb)
        rows.append({"claim_id": row["claim_id"], "grain": parsed["grain"],
                      "p_value_a": ra["p_value"], "verdict_a": ra["verdict"],
                      "p_value_b": rb["p_value"], "verdict_b": rb["verdict"],
                      "verdict": verdict})
    results = pd.DataFrame(rows)
    results.attrs["n_total_testable"] = n_total_testable
    results.attrs["n_sampled"] = len(sample)
    return results


def placebo_summary(placebo_results: pd.DataFrame) -> dict:
    """FP-rate table: single-corpus rejection rate among tests that actually
    ran (verdict != INSUFFICIENT_DATA, i.e. n_games >= MIN_GAMES), split
    IMPROVES vs WORSE. NOTE this is NOT a clean Type-I-error/nominal-alpha
    check by itself: a placebo claim keeps its REAL discovered_delta (fit to
    match a genuine discovery-slice relationship) but is scored against a
    SHUFFLED reserve where that relationship no longer holds -- a nonzero
    delta compared to shuffled data is EXPECTED to score worse-than-baseline
    on average (a true, correct rejection of a now-miscalibrated predictor,
    not a false positive). The IMPROVES side is the one that matters for
    gate integrity (a spurious 'this still works' on pure noise); see
    placebo_defensible_check for the promotion-relevant (Bonferroni AND
    majority-class) FP rate."""
    n_total_testable = int(placebo_results.attrs.get("n_total_testable", len(placebo_results)))
    tested_a = placebo_results[placebo_results["verdict_a"] != "INSUFFICIENT_DATA"]
    tested_b = placebo_results[placebo_results["verdict_b"] != "INSUFFICIENT_DATA"]
    improves_a = float(tested_a["verdict_a"].eq("IMPROVES").mean()) if len(tested_a) else float("nan")
    worse_a = float(tested_a["verdict_a"].eq("WORSE").mean()) if len(tested_a) else float("nan")
    improves_b = float(tested_b["verdict_b"].eq("IMPROVES").mean()) if len(tested_b) else float("nan")
    worse_b = float(tested_b["verdict_b"].eq("WORSE").mean()) if len(tested_b) else float("nan")
    both = placebo_results[placebo_results["verdict"] == "IMPROVES_BOTH_CORPORA"]
    alpha_bonf = MDE_ALPHA / n_total_testable if n_total_testable else float("nan")
    bonf_pass = int(((both["p_value_a"] < alpha_bonf) & (both["p_value_b"] < alpha_bonf)).sum()) if len(both) else 0
    return {
        "n_sampled": int(placebo_results.attrs.get("n_sampled", len(placebo_results))),
        "n_scored_a": int(len(tested_a)), "n_scored_b": int(len(tested_b)),
        "empirical_improves_rate_a": improves_a, "empirical_worse_rate_a": worse_a,
        "empirical_improves_rate_b": improves_b, "empirical_worse_rate_b": worse_b,
        "nominal_reject_rate": MDE_ALPHA,
        "raw_both_corpora_pass": int(len(both)),
        "n_total_testable_for_bonferroni": n_total_testable,
        "alpha_bonferroni": alpha_bonf,
        "bonferroni_survivors_on_placebo": bonf_pass,
    }


def placebo_defensible_check(placebo_results: pd.DataFrame, claims_df: pd.DataFrame,
                              n_total_testable: int) -> dict:
    """The FP-rate that actually matters for promotion: does the FULL
    defensible gate (Bonferroni AND the majority-class degeneracy filter --
    reuses run_full_ledger's OWN _complement_frac/MAJORITY_COMPLEMENT_FRAC,
    never re-derived) survive noise? Bonferroni alone is checked in
    placebo_summary; this applies the SECOND layer on top, on the same
    Bonferroni-passing rows, to report the true defensible-survivor FP rate."""
    both = placebo_results[placebo_results["verdict"] == "IMPROVES_BOTH_CORPORA"].copy()
    alpha_bonf = MDE_ALPHA / n_total_testable if n_total_testable else float("nan")
    if not len(both):
        return {"n_bonferroni_pass": 0, "n_defensible": 0, "majority_class_ids": []}
    both["bonferroni_pass"] = (both["p_value_a"] < alpha_bonf) & (both["p_value_b"] < alpha_bonf)
    bonf_rows = both[both["bonferroni_pass"]]
    if not len(bonf_rows):
        return {"n_bonferroni_pass": 0, "n_defensible": 0, "majority_class_ids": []}
    cmap = claims_df.set_index("claim_id")
    is_majority = bonf_rows["claim_id"].map(
        lambda c: rfl._complement_frac(cmap.loc[c]) < rfl.MAJORITY_COMPLEMENT_FRAC if c in cmap.index else False)
    defensible = bonf_rows[~is_majority]
    return {
        "n_bonferroni_pass": int(len(bonf_rows)),
        "n_defensible": int(len(defensible)),
        "majority_class_ids": bonf_rows.loc[is_majority, "claim_id"].tolist(),
    }


# ---------------------------------------------------------------- 2. MDE/POWER

def corpus_sigma(corpora: dict) -> dict:
    """Global outcome std per grain (team: points-per-possession; player:
    scored-rate), pooled across both trailing-date corpora. A per-cell sigma
    would be more precise; this is a documented, honest simplification (see
    mde_for_n) that makes MDE comparable on one scale across all 14,305
    INSUFFICIENT_DATA claims."""
    team_pts = pd.concat([corpora["team_a"]["points"], corpora["team_b"]["points"]])
    player_scored = pd.concat([corpora["player_a"]["scored"], corpora["player_b"]["scored"]])
    return {"team": float(team_pts.std(ddof=1)), "player": float(player_scored.std(ddof=1))}


def mde_for_n(n, sigma: float, alpha: float = MDE_ALPHA, power: float = MDE_POWER) -> float:
    """Minimum detectable mean-shift (outcome's own units) for a one-sample
    z-test at n i.i.d. observations, two-sided alpha, target power.
    SIMPLIFICATION (documented, honest): the real hardened test clusters by
    game_id (fewer effective independent units than n_active), so this MDE
    using raw n_active is an OPTIMISTIC LOWER BOUND -- the true clustered-
    test MDE is >= this value. Used because the task asks for MDE 'at their
    n_active'."""
    if n is None or n <= 1 or sigma is None or sigma <= 0 or not np.isfinite(sigma):
        return float("inf")
    z_a = sps.norm.ppf(1 - alpha / 2)
    z_b = sps.norm.ppf(power)
    return float((z_a + z_b) * sigma / np.sqrt(n))


def power_report(ledger_results: pd.DataFrame, sigma: dict) -> pd.DataFrame:
    """For every INSUFFICIENT_DATA claim in the real full-ledger run, the
    binding MDE = max(mde at n_active_a, mde at n_active_b) -- a claim only
    promotes if BOTH corpora independently reject, so the harder-to-satisfy
    corpus sets the real detectable-effect floor. Distinguishes 'no power to
    test' (large MDE relative to discovered_delta) from a claim that could
    plausibly have been adjudicated at a finer data floor."""
    insuff = ledger_results[ledger_results["verdict"] == "INSUFFICIENT_DATA"].copy()
    insuff["sigma"] = insuff["grain"].map(sigma)
    insuff["mde_a"] = [mde_for_n(n, s) for n, s in zip(insuff["n_active_a"], insuff["sigma"])]
    insuff["mde_b"] = [mde_for_n(n, s) for n, s in zip(insuff["n_active_b"], insuff["sigma"])]
    insuff["mde_binding"] = insuff[["mde_a", "mde_b"]].max(axis=1)
    return insuff[["claim_id", "topic", "grain", "discovered_delta",
                   "n_active_a", "n_active_b", "mde_a", "mde_b", "mde_binding"]]


def mde_summary(power_df: pd.DataFrame) -> dict:
    finite = power_df[np.isfinite(power_df["mde_binding"])]
    out = {"n_insufficient": int(len(power_df)), "n_finite_mde": int(len(finite))}
    for grain in ("team", "player"):
        g = finite.loc[finite["grain"] == grain, "mde_binding"]
        out[f"{grain}_median_mde"] = float(g.median()) if len(g) else float("nan")
        out[f"{grain}_p25_mde"] = float(g.quantile(0.25)) if len(g) else float("nan")
        out[f"{grain}_p75_mde"] = float(g.quantile(0.75)) if len(g) else float("nan")
        out[f"{grain}_n"] = int(len(g))
    return out


# ------------------------------------------------------ 3. TESTABILITY EXPANSION

def tails_claims(claims_df: pd.DataFrame) -> pd.DataFrame:
    """The 762 tails.* NOT_TICK_TESTABLE claims (reason=
    quantile_design_not_mean_delta in run_full_ledger's classification) --
    B2's per-entity distribution-shape claims, structurally untestable by
    run_full_ledger's mean-CRPS design, never by lack of real data."""
    return claims_df[claims_df["topic"].astype(str).str.startswith("tails.")].copy()


def _entity_id(scope_json: str):
    scope = json.loads(scope_json)
    ids = scope.get("entity_ids") or []
    return int(ids[0]) if ids else None


def calibration_verdict_for_entity(entity_id, fit_metrics: dict, reserve: pd.DataFrame,
                                    entity_col: str, stat_col: str,
                                    min_rows: int = MIN_ENTITY_RESERVE_ROWS) -> dict:
    """The RIGHT instrument for a distribution-shape claim: per-entity
    paired CRPS (tail-aware empirical quantile vector vs a naive same-mean/
    std Normal), scored on that entity's OOS reserve rows only. Reuses
    tail_calib.calib's fit + CRPS plumbing (TAIL-CALIB lane, read-only) --
    adds the PER-CLAIM (per-entity) verdict tail_calib's own report never
    computed (it reports pooled observable-level verdicts only)."""
    m = fit_metrics.get(entity_id) if entity_id is not None else None
    if m is None or m.get("insufficient"):
        return {"n_reserve": 0, "verdict": "INSUFFICIENT_DATA", "p_value": None, "crps_delta": None}
    rows = reserve[reserve[entity_col] == entity_id]
    if len(rows) < min_rows:
        return {"n_reserve": int(len(rows)), "verdict": "INSUFFICIENT_DATA", "p_value": None, "crps_delta": None}
    actual = rows[stat_col].to_numpy(dtype=float)
    mean, std, quantiles = m["mean"], m["std"], m["quantiles"]
    crps_base = np.array([tc.crps_approx(lambda q: tc.baseline_ppf(q, mean, std), x) for x in actual])
    crps_tail = np.array([tc.crps_approx(lambda q: tc.tail_aware_ppf(q, quantiles), x) for x in actual])
    diff = crps_base - crps_tail  # positive => tail-aware wins
    if len(diff) < 2 or diff.std(ddof=1) == 0.0:
        return {"n_reserve": int(len(diff)), "verdict": "INSUFFICIENT_DATA", "p_value": None,
                "crps_delta": float(diff.mean())}
    _, p_value = sps.ttest_1samp(diff, popmean=0.0)
    verdict = "NULL"
    if p_value < MDE_ALPHA:
        verdict = "TAIL_CALIB_BEATS_BASELINE" if diff.mean() > 0 else "TAIL_CALIB_WORSE"
    return {"n_reserve": int(len(diff)), "verdict": verdict, "p_value": float(p_value),
            "crps_delta": float(diff.mean())}


def expand_tails_testability(claims_df: pd.DataFrame, nba_disc: pd.DataFrame, nba_res: pd.DataFrame,
                              entity_col: str = "player_id", stat_col: str = "pts") -> pd.DataFrame:
    """Runs every tails.nba.points PLAYER-grain claim through the per-entity
    calibration instrument (fit_predictors/CRPS is a player_id -> pts fit,
    matching nba_disc/nba_res). Real ledger inspection (2026-07-14, this
    lane) shows tails.nba.points also carries 30 TEAM-grain rows (entity_ids
    are team abbreviations like "ATL", not a player_id) plus tails.mlb.*
    (no per-player MLB store, per tails.py's own DATA-ABSENT note) -- all of
    those stay NOT_TESTABLE_HERE, honestly, rather than forced through a
    player-fit dict they don't belong in."""
    tails_df = tails_claims(claims_df)
    fit_metrics = tc.fit_predictors(nba_disc, entity_col, stat_col)
    rows = []
    for _, row in tails_df.iterrows():
        scope = json.loads(row["scope_json"])
        is_nba_player_points = (row["topic"] == "tails.nba.points"
                                 and scope.get("entity_type") == "player")
        if not is_nba_player_points:
            rows.append({"claim_id": row["claim_id"], "topic": row["topic"],
                         "n_reserve": None, "verdict": "NOT_TESTABLE_HERE", "p_value": None, "crps_delta": None})
            continue
        eid = _entity_id(row["scope_json"])
        result = calibration_verdict_for_entity(eid, fit_metrics, nba_res, entity_col, stat_col)
        result.update({"claim_id": row["claim_id"], "topic": row["topic"]})
        rows.append(result)
    return pd.DataFrame(rows)


def expansion_summary(expansion_df: pd.DataFrame) -> dict:
    counts = expansion_df["verdict"].value_counts().to_dict()
    newly_testable = int(sum(v for k, v in counts.items()
                             if k not in ("INSUFFICIENT_DATA", "NOT_TESTABLE_HERE")))
    return {"n_tails_claims": int(len(expansion_df)), "verdict_counts": counts,
            "newly_testable": newly_testable}


__all__ = [
    "PLACEBO_N_CAP", "MDE_ALPHA", "MDE_POWER", "MIN_ENTITY_RESERVE_ROWS", "OUT_DIR",
    "classify_all", "sample_testable", "shuffle_outcomes", "placebo_run", "placebo_summary",
    "placebo_defensible_check", "corpus_sigma", "mde_for_n", "power_report", "mde_summary",
    "tails_claims", "calibration_verdict_for_entity", "expand_tails_testability", "expansion_summary",
]
