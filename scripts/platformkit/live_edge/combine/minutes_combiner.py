"""scripts.platformkit.live_edge.combine.minutes_combiner -- LIVE-EDGE C1
minutes-observable combiner.

STEP 0 (premise check, 2026-07-14): no NBA minutes-prediction MODEL exists in
scripts/platformkit or domains/ (swept both trees: only k_minutes_rescore.py,
a foul-trouble MECHANISM decomposition, not a minutes predictor). Per the
program's pivot clause this lane builds the simplest leak-free baseline
(per-player expanding median minutes, as-of) and combines against it.

Claim-feature discovery (data/omni/claims/claims.parquet, 2026-07-14): only
ONE claim family qualifies as a tier-1/tier-2 minutes feature -- 329c45d92e-
094fba / bcc34013 (high_foul_vs_low_foul -> minutes, 7/8 players accepted
MINUTES_MEDIATED). rest (b2b_vs_rest) and blowout/garbage-time were only ever
mined on the pts stat (never on min) and health.minutes_response is
lifecycle=screened (below the family_pass/replicated tier-2 floor) --
excluded per tiered consumption (L-S2), not fabricated. Using this game's OWN
final pf as a feature would leak (same-game future info predicting the same
game's minutes), so the claim is converted to a pregame-knowable prior: each
player's trailing foul-trouble RATE (share of past games with pf>=4), shifted
so only strictly-prior games are visible.

Target: total minutes this game. Model: baseline (rolling median) vs
baseline+foul_rate_prior via ElasticNet and HistGradientBoostingRegressor,
walk-forward split (discovery train, reserve test -- k_sweep_nba's existing
season cutover, never re-derived). Loss: pinball @ median (= 0.5*MAE), the
spec's stated CRPS-or-pinball alternative. Seeds pinned x2.

INVARIANTS: pandas/sklearn + stdlib only. <=300 LOC. ASCII stdout. Never
writes data/registry/ or the claims journal (pending_ledger.jsonl handoff
only -- B1-GRID owns the journal this cycle). No $/edge claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_minutes_combiner.py -q
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import ElasticNet

from scripts.platformkit.io_atomic import append_jsonl_atomic, write_text_atomic
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_sweep_nba as ksn

_OUT_DIR = pathlib.Path("data/omni/live_edge/combine")
_REPORT_JSON = "minutes_combiner_report.json"
_REPORT_MD = "minutes_combiner_report.md"
_PENDING_LEDGER = "pending_ledger.jsonl"
_LANE = "c1_minutes_combiner"

_FOUL_META_CLAIM_ID = "329c45d92e094fba"
_MARKET_FAMILIES = ["ingame.props.minutes"]

BASELINE_WINDOW_MIN_PERIODS = 3
FOUL_RATE_WINDOW = 10
CORR_SKIP_THRESHOLD = 0.9
SEEDS = (0, 42)


def _add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-player, strictly-prior-only (leak-free) features. Cold-start rows
    (a player's first BASELINE_WINDOW_MIN_PERIODS games) fall back to the
    league-wide expanding value at that date -- still knowable_at that date,
    never the player's own future or current-game value."""
    df = df.sort_values(["player_id", "date"]).reset_index(drop=True)

    g = df.groupby("player_id")["min"]
    player_med = g.apply(lambda s: s.shift(1).expanding(min_periods=BASELINE_WINDOW_MIN_PERIODS).median())
    df["baseline_min"] = player_med.reset_index(level=0, drop=True)
    league_med = df["min"].shift(1).expanding(min_periods=BASELINE_WINDOW_MIN_PERIODS).median()
    df["baseline_min"] = df["baseline_min"].fillna(league_med)

    foul_flag = (df["pf"] >= 4).astype(float)
    gf = foul_flag.groupby(df["player_id"])
    player_rate = gf.apply(lambda s: s.shift(1).rolling(FOUL_RATE_WINDOW, min_periods=BASELINE_WINDOW_MIN_PERIODS).mean())
    df["foul_rate_prior"] = player_rate.reset_index(level=0, drop=True)
    league_rate = foul_flag.shift(1).rolling(FOUL_RATE_WINDOW, min_periods=BASELINE_WINDOW_MIN_PERIODS).mean()
    df["foul_rate_prior"] = df["foul_rate_prior"].fillna(league_rate)
    return df


def _pinball_median(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.where(diff >= 0, 0.5 * diff, 0.5 * -diff)))


def _fit_predict(model_name: str, X_train, y_train, X_test, seed: int):
    if model_name == "elastic_net":
        model = ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=seed, max_iter=5000)
    else:
        model = HistGradientBoostingRegressor(loss="quantile", quantile=0.5, random_state=seed, max_iter=200)
    model.fit(X_train, y_train)
    return model, model.predict(X_test)


def run_minutes_combiner(base_dir=None, source=None, out_dir: pathlib.Path | None = None) -> dict[str, Any]:
    if isinstance(source, pd.DataFrame) and source.empty:
        return {"blocked": True, "reason": "empty sweep frame"}
    df = ksn._load_sweep_frame(source)  # noqa: SLF001 -- reuse the shared loader, never forked
    if df.empty:
        return {"blocked": True, "reason": "empty sweep frame"}
    df = _add_features(df)
    discovery, reserve = ksn.split_discovery_reserve(df)
    discovery = discovery.dropna(subset=["baseline_min", "foul_rate_prior"])
    reserve = reserve.dropna(subset=["baseline_min", "foul_rate_prior"])
    if len(discovery) < 50 or len(reserve) < 50:
        return {"blocked": True, "reason": f"insufficient rows after cold-start drop "
                                            f"(discovery={len(discovery)}, reserve={len(reserve)})"}

    corr = float(np.corrcoef(discovery["baseline_min"], discovery["foul_rate_prior"])[0, 1])
    feature_included = abs(corr) <= CORR_SKIP_THRESHOLD

    y_train, y_test = discovery["min"].to_numpy(), reserve["min"].to_numpy()
    baseline_pinball = _pinball_median(y_test, reserve["baseline_min"].to_numpy())

    feature_sets = {"baseline_only": ["baseline_min"]}
    if feature_included:
        feature_sets["baseline_plus_foul_rate"] = ["baseline_min", "foul_rate_prior"]

    seed_results: dict[str, Any] = {}
    best_model_pinball, best_model_name = None, None
    for model_name in ("elastic_net", "hist_gb"):
        seed_results[model_name] = {}
        for feat_label, cols in feature_sets.items():
            X_train, X_test = discovery[cols].to_numpy(), reserve[cols].to_numpy()
            for seed in SEEDS:
                _, y_pred = _fit_predict(model_name, X_train, y_train, X_test, seed)
                pinball = _pinball_median(y_test, y_pred)
                seed_results[model_name][f"{feat_label}_seed{seed}"] = pinball
                if feat_label != "baseline_only" and (best_model_pinball is None or pinball < best_model_pinball):
                    best_model_pinball, best_model_name = pinball, f"{model_name}:{feat_label}_seed{seed}"

    marginal_delta = None
    permutation_attr = None
    if feature_included:
        base_only_avg = np.mean([seed_results["hist_gb"][f"baseline_only_seed{s}"] for s in SEEDS])
        combo_avg = np.mean([seed_results["hist_gb"][f"baseline_plus_foul_rate_seed{s}"] for s in SEEDS])
        marginal_delta = float(base_only_avg - combo_avg)  # positive = foul_rate_prior helped

        model, _ = _fit_predict("hist_gb", discovery[["baseline_min", "foul_rate_prior"]].to_numpy(),
                                 y_train, reserve[["baseline_min", "foul_rate_prior"]].to_numpy(), SEEDS[0])
        perm = permutation_importance(model, reserve[["baseline_min", "foul_rate_prior"]].to_numpy(), y_test,
                                       n_repeats=10, random_state=SEEDS[0], scoring="neg_mean_absolute_error")
        permutation_attr = {"baseline_min": float(perm.importances_mean[0]),
                             "foul_rate_prior": float(perm.importances_mean[1])}

    beats_baseline = best_model_pinball is not None and best_model_pinball < baseline_pinball
    verdict = "COMBINER_BEATS_BASELINE" if beats_baseline else "HONEST_NULL"
    if verdict == "COMBINER_BEATS_BASELINE":
        blocking_reason = None
    elif feature_included:
        blocking_reason = "only 1 claim-backed feature available (foul_rate_prior); marginal contribution did not beat baseline OOS"
    else:
        blocking_reason = f"foul_rate_prior correlated with baseline (|rho|={corr:.3f} > {CORR_SKIP_THRESHOLD}) -- skipped, no combiner feature to add"

    report = {
        "observable": "minutes", "n_discovery": int(len(discovery)), "n_reserve": int(len(reserve)),
        "baseline": "per-player expanding median minutes, shift(1), min_periods=3, league fallback",
        "baseline_pinball_median": baseline_pinball, "best_combiner_pinball_median": best_model_pinball,
        "best_model": best_model_name, "verdict": verdict, "blocking_reason": blocking_reason,
        "marginal_delta_foul_rate_prior_hist_gb": marginal_delta,
        "permutation_importance_hist_gb": permutation_attr,
        "correlation_baseline_vs_foul_rate": corr, "feature_included": feature_included,
        "seeds": list(SEEDS), "per_model_per_seed_pinball": seed_results,
        "claim_features_considered": [_FOUL_META_CLAIM_ID],
        "claim_features_excluded_no_tier12": [
            "rest (b2b_vs_rest, never mined on min stat)",
            "blowout/garbage-time (no claims exist for minutes)",
            "health.minutes_response (lifecycle=screened, below tier-2 floor)",
        ],
    }
    _write_report(report, out_dir)
    _write_pending_ledger(report, out_dir=out_dir)
    return report


def _write_report(report: dict, out_dir: pathlib.Path | None) -> None:
    d = out_dir or _OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    write_text_atomic(d / _REPORT_JSON, json.dumps(report, indent=2, default=str))
    lines = [
        "# minutes combiner report (LIVE-EDGE C1)", "",
        f"verdict: **{report['verdict']}**", "",
        f"- n_discovery={report['n_discovery']} n_reserve={report['n_reserve']}",
        f"- baseline pinball@median: {report['baseline_pinball_median']:.4f}",
        f"- best combiner pinball@median: {report['best_combiner_pinball_median']}",
        f"- best model: {report['best_model']}",
        f"- marginal delta (foul_rate_prior, hist_gb): {report['marginal_delta_foul_rate_prior_hist_gb']}",
        f"- blocking reason: {report['blocking_reason']}",
    ]
    write_text_atomic(d / _REPORT_MD, "\n".join(lines) + "\n")


def _write_pending_ledger(report: dict, out_dir: pathlib.Path | None) -> None:
    """Append a claim-shaped row for the orchestrator to batch into the
    journal after B1 finishes (one-writer-at-a-time rule -- this lane never
    calls claims_ledger.add_claim/add_claims_batch itself)."""
    scope = {"sport": "nba", "entity_type": "mechanism_family", "entity_ids": ["minutes_combiner_v1"],
             "context": {"observable": "minutes"}}
    statement = f"LIVE-EDGE C1 minutes combiner v1: {report['verdict']}"
    claim = {
        "statement": statement, "type": "meta", "scope": scope,
        "topic": "composition.minutes_combiner", "lifecycle": "screened",
        "effect": {"verdict": report["verdict"], "baseline_pinball_median": report["baseline_pinball_median"],
                   "best_combiner_pinball_median": report["best_combiner_pinball_median"]},
        "evidence": report, "provenance": {"created_by_lane": _LANE},
        "links": {"parent_claims": [_FOUL_META_CLAIM_ID], "market_families": _MARKET_FAMILIES},
    }
    claim["claim_id"] = cl.make_claim_id(claim["statement"], claim["scope"])
    d = out_dir or _OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    append_jsonl_atomic(d / _PENDING_LEDGER, claim)


if __name__ == "__main__":
    out = run_minutes_combiner()
    for k, v in out.items():
        if k not in ("per_model_per_seed_pinball", "permutation_importance_hist_gb"):
            print(f"[minutes_combiner] {k}: {v}")


__all__ = ["run_minutes_combiner"]
