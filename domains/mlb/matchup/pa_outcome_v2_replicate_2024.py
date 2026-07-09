"""domains.mlb.matchup.pa_outcome_v2_replicate_2024 -- STANDING REPLICATION:
adjudicates pa_outcome_v2's SHIP_PROVISIONAL_RETROSPECTIVE ledger row
(pa_outcome_v2.py, ledger rows 45/48) on a genuinely INDEPENDENT corpus:
data/cache/statcast/savant_full__2024.parquet -- different source table than
v2's statcast_fuller__2022/2023, different season, never touched by v2/v2b.

CRITICAL HISTORY: v2's SHIP_PROVISIONAL lift was concentrated in
count_leverage_mix_share, a rollup of the PA's OWN realized pitch sequence --
within-unit hindsight w.r.t. first pitch. The pregame analogue
(pa_outcome_v2b_pregame.py, ledger row 49, replacing that column with
pitcher_ahead_breaking_share_asof) came back NULL (league=1.40231,
profiles_only=1.42268, candidate=1.41297). This module follows v2b's HONEST
AS-OF framing (no within-PA sequence feature) and checks whether v2b's NULL
replicates on 2024. count_leverage_mix_share is never computed here.

FOLD SCHEME (declared before running): monthly EXPANDING walk-forward within
the single 2024 season (no second season here for a v2/v2b-style year split).
One fold per calendar month April-September; TRAIN = every 2024 pitch with
game_date strictly before that month's first day, TEST = PA-terminal rows in
that month. Fold skipped if train pitch-count < MIN_TRAIN_N=5000 (declared,
not results-tuned). Per-fold profile tables (batter/pitcher marginals,
platoon_breaking_* lookup) are rebuilt from ONLY that fold's train rows each
time. n=0 usable folds -> NOT_TESTABLE.

FEATURES (AS-OF ONLY): PROFILE_FEATURES (v2/v2b's 8 marginal columns, via
pa_outcome_model.build_features, rebuilt per-fold since this corpus has no
earlier season to project forward from); platoon_breaking_on_base_rate/
_k_rate (v2's lookup, rebuilt per-fold via platoon_context, reused not
reimplemented); pitcher_ahead_breaking_share_asof (v2b's own feature,
_expanding_asof_share imported verbatim -- already per-row strictly-prior,
no fold-specific rebuild needed).

MODEL: HistGradientBoostingClassifier + isotonic calibration, same fit shape
as pa_outcome_v2's _fit_calibrated_histgb -- reimplemented in _fit_score_rows
ONLY because the imported version doesn't expose per-row detail, needed for
the per-date DM test.

GRADE: candidate (PROFILE + 3 as-of cols) vs baseline (PROFILE alone) --
differ ONLY by the hypothesis features. Pooled multiclass log-loss + IN_
PLAY_OUT Brier. DM test: per-PA log-loss differential (baseline - candidate)
averaged by game_date, HAC (Newey-West) t-test via statsmodels OLS(cov_type="HAC").

VERDICT: REPLICATED iff pooled candidate log_loss < pooled baseline AND DM
p < 0.05. Else FAILED_REPLICATION (matches v2b's own NULL -- KILLS v2's
SHIP_PROVISIONAL_RETROSPECTIVE claim as deployable). n=0 folds -> NOT_TESTABLE.

Descriptive/research model only. NETWORK: zero. NO MARKET/$ EDGE CLAIMED.
Cap HistGB threads: OMP_NUM_THREADS=4 python -m domains.mlb.matchup.pa_outcome_v2_replicate_2024
"""
from __future__ import annotations

import argparse
import json
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")  # ponytail: box also runs other lanes; cap before sklearn import
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from domains.mlb.matchup.pa_outcome_model import _BUCKET_MAP, _BUCKETS_SORTED, build_features
from domains.mlb.matchup.pa_outcome_v2 import CALIB_TAIL_FRAC, PROFILE_FEATURES
from domains.mlb.matchup.pa_outcome_v2b_pregame import _expanding_asof_share
from domains.mlb.matchup.pitch_mix_profiles import build_batter_profile, build_pitcher_profile
from domains.mlb.matchup.platoon_context import _K_EVENTS, _ON_BASE_EVENTS, build_batter_platoon_pitch
from domains.mlb.prereg.mlb_hypotheses import FASTBALL_TYPES
from domains.mlb.prereg.stats_common import LEDGER_PATH, append_ledger

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAVANT_2024 = _REPO_ROOT / "data" / "cache" / "statcast" / "savant_full__2024.parquet"
_REPORT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "matchup" / "pa_outcome_v2_replicate_2024_report.json"
_METHOD = "pa_outcome_v2_replicate_2024_monthly_walkforward"

MIN_TRAIN_N = 5000
TEST_MONTHS = ["2024-04", "2024-05", "2024-06", "2024-07", "2024-08", "2024-09"]
INTERACTION_FEATURES = ["platoon_breaking_on_base_rate", "platoon_breaking_k_rate",
                         "pitcher_ahead_breaking_share_asof"]
CANDIDATE_FEATURES = PROFILE_FEATURES + INTERACTION_FEATURES
_PITCH_COLS = ["pitcher", "batter", "pitch_type", "zone", "type", "des", "events", "game_date",
               "stand", "p_throws", "outs_when_up", "bat_score", "home_score", "away_score",
               "game_pk", "at_bat_number", "balls", "strikes"]

def load_2024_rows() -> pd.DataFrame:
    df = pd.read_parquet(_SAVANT_2024, columns=_PITCH_COLS)
    df = df[df["pitch_type"].notna() & (df["pitch_type"] != "None")].copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df

def build_folds(dates: pd.Series, min_train_n: int = MIN_TRAIN_N) -> list:
    """Pure function of a date series (no IO): for each TEST_MONTHS entry,
    return (month, cutoff, train_mask, test_mask). Skips a month if its
    train_n < floor. Directly testable for leakage: max(train dates) must
    be < min(test dates) for every fold kept."""
    folds = []
    for month in TEST_MONTHS:
        cutoff = pd.Timestamp(month + "-01")
        next_month = cutoff + pd.offsets.MonthBegin(1)
        train_mask = dates < cutoff
        test_mask = (dates >= cutoff) & (dates < next_month)
        if train_mask.sum() < min_train_n or test_mask.sum() == 0:
            continue
        folds.append((month, cutoff, train_mask, test_mask))
    return folds

def build_platoon_breaking_lookup_fold(train_pa: pd.DataFrame) -> pd.DataFrame:
    """Fold-scoped v2.build_platoon_breaking_lookup: same rollup via
    platoon_context's floor-gated aggregation, built from TRAIN-only rows."""
    train_pa = train_pa.copy()
    train_pa["on_base"] = train_pa["events"].isin(_ON_BASE_EVENTS).astype(int)
    train_pa["is_k"] = train_pa["events"].isin(_K_EVENTS).astype(int)
    fine, _ = build_batter_platoon_pitch(train_pa)
    fine = fine.copy()
    fine["is_breaking"] = (~fine["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    rolled = fine.groupby(["batter", "p_throws", "is_breaking"]).agg(
        n_pa=("n_pa", "sum"), n_on_base=("n_on_base", "sum"), n_k=("n_k", "sum"),
    ).reset_index()
    rolled["platoon_breaking_on_base_rate"] = rolled["n_on_base"] / rolled["n_pa"]
    rolled["platoon_breaking_k_rate"] = rolled["n_k"] / rolled["n_pa"]
    return rolled[["batter", "p_throws", "is_breaking",
                    "platoon_breaking_on_base_rate", "platoon_breaking_k_rate"]]

def build_pitcher_ahead_asof_2024(pitch_rows: pd.DataFrame) -> pd.DataFrame:
    """2024 analogue of v2b's build_pitcher_ahead_breaking_asof, built from
    the already-loaded frame. _expanding_asof_share (imported verbatim) is
    genuinely per-row strictly-prior -- correct for any fold, no rebuild."""
    all_days = pitch_rows.groupby(["pitcher", "game_date"]).size().reset_index()[["pitcher", "game_date"]]
    ahead = pitch_rows[pitch_rows["strikes"] > pitch_rows["balls"]].copy()
    ahead["is_breaking"] = (~ahead["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    ahead_daily = ahead.groupby(["pitcher", "game_date"]).agg(
        n_ahead=("is_breaking", "size"), n_breaking_ahead=("is_breaking", "sum"),
    ).reset_index()
    daily = all_days.merge(ahead_daily, on=["pitcher", "game_date"], how="left")
    daily[["n_ahead", "n_breaking_ahead"]] = daily[["n_ahead", "n_breaking_ahead"]].fillna(0)
    return _expanding_asof_share(daily)

def _fit_score_rows(train_df: pd.DataFrame, test_df: pd.DataFrame, feature_cols: list,
                     calib_tail_frac: float = CALIB_TAIL_FRAC) -> dict:
    """Same fit shape as pa_outcome_v2's _fit_calibrated_histgb -- reimplemented
    (not imported) ONLY to expose per-row log-loss/IN_PLAY_OUT-SE arrays for
    the per-date DM test below (the aggregate-only import can't)."""
    train_sorted = train_df.sort_values("game_date").reset_index(drop=True)
    cutoff = int(len(train_sorted) * (1 - calib_tail_frac))
    fit_part, calib_part = train_sorted.iloc[:cutoff], train_sorted.iloc[cutoff:]
    clf = HistGradientBoostingClassifier(random_state=0)
    clf.fit(fit_part[feature_cols], fit_part["bucket"])
    calibrated = CalibratedClassifierCV(FrozenEstimator(clf), method="isotonic")
    calibrated.fit(calib_part[feature_cols], calib_part["bucket"])

    proba = pd.DataFrame(calibrated.predict_proba(test_df[feature_cols]), columns=calibrated.classes_)
    for b in _BUCKETS_SORTED:
        if b not in proba.columns:
            proba[b] = 1e-6
    proba = proba[_BUCKETS_SORTED].clip(lower=1e-6)
    proba = proba.div(proba.sum(axis=1), axis=0)

    y_true = test_df["bucket"].to_numpy()
    col_idx = np.array([_BUCKETS_SORTED.index(b) for b in y_true])
    p_true = proba.to_numpy()[np.arange(len(y_true)), col_idx]
    row_ll = -np.log(p_true)
    y_ipo = (test_df["bucket"] == "IN_PLAY_OUT").astype(int).to_numpy()
    row_se_ipo = (y_ipo - proba["IN_PLAY_OUT"].to_numpy()) ** 2
    return {"row_ll": row_ll, "row_se_ipo": row_se_ipo,
            "log_loss": float(row_ll.mean()), "brier_ipo": float(row_se_ipo.mean())}

def run() -> dict:
    pitch_rows = load_2024_rows()
    pa_all = pitch_rows[pitch_rows["events"].notna()].copy()
    pa_all["bucket"] = pa_all["events"].map(_BUCKET_MAP)
    pa_all = pa_all[pa_all["bucket"].notna()].copy()
    asof = build_pitcher_ahead_asof_2024(pitch_rows)

    folds = build_folds(pitch_rows["game_date"])
    if not folds:
        return {"component": "pa_outcome_v2_replicate_2024", "verdict": "NOT_TESTABLE",
                "n_folds": 0, "note": "no fold cleared MIN_TRAIN_N", "edge_claimed": False}

    per_fold, ll_b, ll_c, se_b, se_c, dates = [], [], [], [], [], []
    for month, cutoff, train_mask_pitch, test_mask_pitch in folds:
        train_pitch = pitch_rows[train_mask_pitch].assign(season=0)
        pitcher_profile = build_pitcher_profile(train_pitch)
        batter_profile = build_batter_profile(train_pitch)
        pa_train_mask = pa_all["game_date"] < cutoff
        next_month = cutoff + pd.offsets.MonthBegin(1)
        pa_test_mask = (pa_all["game_date"] >= cutoff) & (pa_all["game_date"] < next_month)
        pa_fold = pa_all[pa_train_mask | pa_test_mask].copy()
        feats = build_features(pa_fold, pitcher_profile, batter_profile)
        feats["is_breaking_terminal"] = (~feats["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
        platoon_lookup = build_platoon_breaking_lookup_fold(pa_all[pa_train_mask])
        feats = feats.merge(platoon_lookup, how="left",
                             left_on=["batter", "p_throws", "is_breaking_terminal"],
                             right_on=["batter", "p_throws", "is_breaking"]
                             ).drop(columns=["is_breaking"], errors="ignore")
        feats = feats.merge(asof, on=["pitcher", "game_date"], how="left")
        fold_train_mask = feats["game_date"] < cutoff
        for col in INTERACTION_FEATURES:
            feats[col] = feats[col].fillna(feats.loc[fold_train_mask, col].mean())
        fold_train, fold_test = feats[fold_train_mask], feats[~fold_train_mask]
        if len(fold_test) == 0:
            continue
        baseline = _fit_score_rows(fold_train, fold_test, PROFILE_FEATURES)
        candidate = _fit_score_rows(fold_train, fold_test, CANDIDATE_FEATURES)
        per_fold.append({
            "month": month, "n_train": int(len(fold_train)), "n_test": int(len(fold_test)),
            "baseline_log_loss": round(baseline["log_loss"], 5),
            "candidate_log_loss": round(candidate["log_loss"], 5),
            "baseline_brier_ipo": round(baseline["brier_ipo"], 5),
            "candidate_brier_ipo": round(candidate["brier_ipo"], 5),
        })
        ll_b.append(baseline["row_ll"]); ll_c.append(candidate["row_ll"])
        se_b.append(baseline["row_se_ipo"]); se_c.append(candidate["row_se_ipo"])
        dates.append(fold_test["game_date"].to_numpy())

    if not per_fold:
        return {"component": "pa_outcome_v2_replicate_2024", "verdict": "NOT_TESTABLE",
                "n_folds": 0, "note": "every fold had 0 test rows", "edge_claimed": False}

    baseline_ll, candidate_ll = np.concatenate(ll_b), np.concatenate(ll_c)
    baseline_se, candidate_se = np.concatenate(se_b), np.concatenate(se_c)
    diff = pd.DataFrame({"date": np.concatenate(dates), "d": baseline_ll - candidate_ll})
    per_date = diff.groupby("date")["d"].mean().sort_index()
    n_dates = len(per_date)
    maxlags = max(1, int(4 * (n_dates / 100) ** (2 / 9)))
    dm_fit = sm.OLS(per_date.to_numpy(), np.ones(n_dates)).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    dm_stat, dm_p = float(dm_fit.tvalues[0]), float(dm_fit.pvalues[0])
    pooled_baseline_ll, pooled_candidate_ll = float(baseline_ll.mean()), float(candidate_ll.mean())
    verdict = ("REPLICATED" if (pooled_candidate_ll < pooled_baseline_ll and dm_p < 0.05)
               else "FAILED_REPLICATION")
    return {
        "component": "pa_outcome_v2_replicate_2024",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "corpus": "savant_full__2024.parquet (independent of v2/v2b's statcast_fuller 2022/2023)",
        "fold_scheme": "monthly expanding walk-forward, MIN_TRAIN_N=5000",
        "n_folds": len(per_fold), "n_test_total": int(len(baseline_ll)), "n_dates": n_dates,
        "per_fold": per_fold,
        "pooled_baseline_log_loss": round(pooled_baseline_ll, 5),
        "pooled_candidate_log_loss": round(pooled_candidate_ll, 5),
        "pooled_baseline_brier_ipo": round(float(baseline_se.mean()), 5),
        "pooled_candidate_brier_ipo": round(float(candidate_se.mean()), 5),
        "dm_stat": round(dm_stat, 4), "dm_p": round(dm_p, 6), "dm_maxlags": maxlags,
        "verdict": verdict,
        "descriptive_only": True, "edge_claimed": False,
    }

_HYPOTHESIS = "pa_outcome_v2b_pregame(platoon_x_pitchtype + pitcher_ahead_breaking_share_asof)"

def _append_ledger_row(report: dict) -> None:
    verdict = report["verdict"]
    not_testable = verdict == "NOT_TESTABLE"
    if not_testable:
        n, effect, p, alpha, term = 0, None, None, None, None
        note = f"INDEPENDENT-CORPUS (savant_full 2024) replication attempt: {report.get('note', '')}"
    else:
        n = report["n_test_total"]
        effect = round(report["pooled_baseline_log_loss"] - report["pooled_candidate_log_loss"], 5)
        p, alpha = report["dm_p"], 0.05
        term = "dm_test_baseline_row_ll_minus_candidate_row_ll_by_date"
        verdict_note = ("KILLED_ON_REPLICATION as a deployable pregame model -- v2's SHIP_PROVISIONAL "
                         "claim does not hold on an independent corpus, matching v2b's own NULL."
                         if verdict == "FAILED_REPLICATION" else
                         "as-of signal REPLICATES on an independent corpus, contradicting v2b's NULL -- "
                         "reopen the pregame-deployable line.")
        note = (f"INDEPENDENT-CORPUS replication of pa_outcome_v2's SHIP_PROVISIONAL_RETROSPECTIVE "
                f"claim (ledger rows 45/48), following v2b's honest as-of framing (ledger row 49, "
                f"itself NULL on statcast_fuller): savant_full 2024, monthly walk-forward, "
                f"n_folds={report['n_folds']}, baseline={report['pooled_baseline_log_loss']} "
                f"candidate={report['pooled_candidate_log_loss']} dm_stat={report['dm_stat']} "
                f"dm_p={report['dm_p']}. {verdict_note}")
    row = {"hypothesis": _HYPOTHESIS, "sport": "mlb", "atomic_unit": "PA", "n": n, "effect": effect,
           "p": p, "alpha_fwer": alpha, "verdict": verdict, "term": term, "note": note,
           "edge_claimed": False, "method": _METHOD, "computed_at": datetime.now(timezone.utc).isoformat()}
    append_ledger([row])

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Independent-corpus (2024) replication of PA-outcome v2/v2b")
    parser.parse_args(argv)

    report = run()
    _REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_OUT, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)
    _append_ledger_row(report)

    if report["verdict"] == "NOT_TESTABLE":
        print(f"VERDICT: NOT_TESTABLE -- {report.get('note', '')}")
    else:
        print(f"n_folds={report['n_folds']} n_test_total={report['n_test_total']} n_dates={report['n_dates']}")
        print(f"  baseline  log_loss={report['pooled_baseline_log_loss']} brier_ipo={report['pooled_baseline_brier_ipo']}")
        print(f"  candidate log_loss={report['pooled_candidate_log_loss']} brier_ipo={report['pooled_candidate_brier_ipo']}")
        print(f"  DM stat={report['dm_stat']} p={report['dm_p']} (maxlags={report['dm_maxlags']})")
        print(f"VERDICT: {report['verdict']}")
    print(f"wrote -> {_REPORT_OUT}  |  appended ledger row -> {LEDGER_PATH}")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
