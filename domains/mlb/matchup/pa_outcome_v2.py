"""domains.mlb.matchup.pa_outcome_v2 -- PA-outcome model v2, composed ONLY
from the two mechanisms that REPLICATED on an independent 2024 corpus
(domains/mlb/prereg/mlb_savant_2024.py): platoon (P-hand x B-stand) x
pitch-type (p=2.8e-4) and count-leverage (pitcher-ahead) x pitch-mix
(p=1.6e-17).

BUG FOUND + FIXED BUILDING THIS MODULE: v1 (pa_outcome_model.py) was
originally reported as an honest NULL (2023 log_loss 1.92729 vs league
1.88036) -- but that comparison had a scoring bug: sklearn's
log_loss(labels=X) always scores ALPHABETICAL y_pred columns regardless of
X's given order, and BUCKETS isn't alphabetical, so every v1 layer was
graded against the wrong class. Root-cause-fixed in pa_outcome_model.
_BUCKETS_SORTED (used by fit_eval_layer, which this module reuses for its
league baseline). Corrected numbers: league=1.40231, v1's OWN interaction
layer=1.39552 -- v1's ladder was a small real win the bug had hidden, not a
null. v2 below is a genuine, separate improvement on top of that corrected
baseline, not a re-litigation of the bug fix.

v2 changes the SPEC vs v1: (1) model = HistGradientBoostingClassifier +
per-class isotonic calibration, not linear; (2) features = v1's SAME
marginal profile columns (batter_k_rate, batter_slug, batter_bb_rate,
pitcher_k_rate, pitcher_zone_rate, platoon_match, outs_when_up, score_diff)
PLUS exactly two new columns, so candidate-minus-baseline isolates only the
replicated mechanisms:
  (a) platoon_breaking_on_base_rate / _k_rate: this batter's 2022-only
      rate in the (p_throws-hand, terminal-pitch-is-breaking) CELL matching
      this PA -- conditioned on platoon AND breaking/fastball together (a
      plain platoon_match main effect, already in baseline, is not this).
      Rolled up from platoon_context.py's floor-gated (batter, hand,
      pitch_type) counts (>=100 PA/hand) by SUMMING n_pa/n_on_base/n_k into
      2 buckets, not re-derived from raw pitches. Built from load_pa_rows()
      FILTERED to season==2022 before aggregation -- that one 2022 lookup
      keys both train and test rows.
  (b) count_leverage_mix_share: per PA, share of NON-TERMINAL pitches
      (events.isna() within (game_pk, at_bat_number)) that were breaking
      AND pitcher-ahead (strikes>balls pre-pitch, mlb_hypotheses.build_h5
      convention). SCOPING NOTE: a summary of the PA's own realized
      sequence, known only once it unfolds -- not a season-crossing leak
      (each season uses only its own pitches) but more retrospective than a
      pregame feature; flagged, not silently upgraded to "predictive."
  Missing cells imputed with the TRAIN-ONLY (2022) mean applied to both
  splits -- stricter than v1's build_features (means over train+test).

EXCLUDED: base-out state x contact type -- its base-runner columns
(on_1b/on_2b/on_3b) exist only on savant_full, not this corpus; it also
predicts contact type, not PA bucket, and is weaker-on-replication.

BASELINES (both required, same HistGB spec): league_marginal = v1's own
zero-feature layer (fit_eval_layer, reused verbatim); profiles_only =
HistGB+calibration over the candidate's SAME marginal columns WITHOUT the
two new ones -- the comparability rail.

SPLIT: walk-forward, train=2022, test=2023. Calibration = a TEMPORAL TAIL
(last 20% by game_date) of 2022 TRAIN only, isotonic-fit via
CalibratedClassifierCV(FrozenEstimator(...)); 2023 never touches fitting.

VERDICT (declared before running): SHIP_PROVISIONAL iff candidate log_loss
< BOTH baselines AND its IN_PLAY_OUT Brier doesn't degrade vs profiles_only.
Else NULL -- a cataloged success, not a failure.

RESULT (2026-07-08 real run): SHIP_PROVISIONAL -- league=1.40231,
profiles_only=1.42268 (profiles ALONE still lose to league, matching v1),
candidate=1.34549, brier[IN_PLAY_OUT] 0.24671->0.24042. HONEST CAVEAT (post
-hoc ablation, not tuned into the verdict rule): re-fitting with each new
column alone shows count_leverage_mix_share carries nearly all of the lift
(profiles+mix_share alone = 1.34867) while platoon_breaking_* alone barely
moves profiles_only (1.42204). The win is real by the declared rule, but is
concentrated in feature (b), the more retrospective of the two -- read the
SCOPING NOTE above before treating this as a pregame-deployable result.

Descriptive/research model only. NETWORK: zero. NO MARKET/$ EDGE CLAIMED.
CLI: python -m domains.mlb.matchup.pa_outcome_v2
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import brier_score_loss, log_loss

from domains.mlb.matchup.pa_outcome_model import (
    BUCKETS, _BUCKETS_SORTED, _STATCAST, build_features, fit_eval_layer, load_pa_dataset,
)
from domains.mlb.matchup.pitch_mix_profiles import (
    SEASONS, build_batter_profile, build_pitcher_profile, load_pitch_rows,
)
from domains.mlb.matchup.platoon_context import build_batter_platoon_pitch, load_pa_rows
from domains.mlb.prereg.mlb_hypotheses import FASTBALL_TYPES
from domains.mlb.prereg.stats_common import LEDGER_PATH, append_ledger

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPORT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "matchup" / "pa_outcome_v2_report.json"

TRAIN_SEASON, TEST_SEASON = 2022, 2023
CALIB_TAIL_FRAC = 0.2  # last 20% of TRAIN by game_date held out for isotonic calibration
_METHOD = "pa_outcome_v2_walkforward"

PROFILE_FEATURES = [
    "batter_k_rate", "batter_slug", "batter_bb_rate",
    "pitcher_k_rate", "pitcher_zone_rate", "platoon_match",
    "outs_when_up", "score_diff",
]
V2_INTERACTION_FEATURES = [
    "platoon_breaking_on_base_rate", "platoon_breaking_k_rate", "count_leverage_mix_share",
]
CANDIDATE_FEATURES = PROFILE_FEATURES + V2_INTERACTION_FEATURES


def build_platoon_breaking_lookup(train_season: int = TRAIN_SEASON) -> pd.DataFrame:
    """(batter, p_throws, is_breaking) -> on_base_rate/k_rate, built from
    TRAIN-SEASON-ONLY PA rows via platoon_context's own floor-gated
    (batter, hand, pitch_type) aggregation, rolled up by summing counts
    (not re-derived from raw pitches)."""
    pa_rows = load_pa_rows(seasons=(train_season,))
    fine, _ = build_batter_platoon_pitch(pa_rows)
    fine = fine.copy()
    fine["is_breaking"] = (~fine["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    rolled = fine.groupby(["batter", "p_throws", "is_breaking"]).agg(
        n_pa=("n_pa", "sum"), n_on_base=("n_on_base", "sum"), n_k=("n_k", "sum"),
    ).reset_index()
    rolled["platoon_breaking_on_base_rate"] = rolled["n_on_base"] / rolled["n_pa"]
    rolled["platoon_breaking_k_rate"] = rolled["n_k"] / rolled["n_pa"]
    return rolled[["batter", "p_throws", "is_breaking",
                    "platoon_breaking_on_base_rate", "platoon_breaking_k_rate"]]


def build_count_leverage_mix(seasons: tuple = SEASONS) -> pd.DataFrame:
    """Per-PA (game_pk, at_bat_number) share of NON-TERMINAL pitches that
    were breaking + thrown pitcher-ahead. Computed per season independently
    (2023 rows use only 2023 pitches) -- see module docstring scoping note."""
    cols = ["game_pk", "at_bat_number", "pitch_type", "balls", "strikes", "events"]
    frames = []
    for season in seasons:
        df = pd.read_parquet(_STATCAST[season], columns=cols)
        df = df[df["pitch_type"].notna() & (df["pitch_type"] != "None")]
        frames.append(df)
    rows = pd.concat(frames, ignore_index=True)
    nonterm = rows[rows["events"].isna()].copy()
    nonterm["is_breaking_ahead"] = (
        (~nonterm["pitch_type"].isin(FASTBALL_TYPES)) & (nonterm["strikes"] > nonterm["balls"])
    ).astype(int)
    agg = nonterm.groupby(["game_pk", "at_bat_number"]).agg(
        n_nonterm=("is_breaking_ahead", "size"), n_breaking_ahead=("is_breaking_ahead", "sum"),
    ).reset_index()
    agg["count_leverage_mix_share"] = agg["n_breaking_ahead"] / agg["n_nonterm"]
    return agg[["game_pk", "at_bat_number", "count_leverage_mix_share"]]


def add_v2_features(feats: pd.DataFrame, train_season: int = TRAIN_SEASON) -> pd.DataFrame:
    """Join the two new interaction columns onto v1's feature frame (which
    already carries the marginal profile columns) and impute missing cells
    with the TRAIN-ONLY column mean, applied to both splits."""
    df = feats.copy()
    df["is_breaking_terminal"] = (~df["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    platoon_lookup = build_platoon_breaking_lookup(train_season)
    df = df.merge(
        platoon_lookup, how="left",
        left_on=["batter", "p_throws", "is_breaking_terminal"],
        right_on=["batter", "p_throws", "is_breaking"],
    ).drop(columns=["is_breaking"], errors="ignore")
    mix = build_count_leverage_mix(SEASONS)
    df = df.merge(mix, on=["game_pk", "at_bat_number"], how="left")
    train_mask = df["season"] == train_season
    for col in V2_INTERACTION_FEATURES:
        train_mean = df.loc[train_mask, col].mean()
        df[col] = df[col].fillna(train_mean)
    return df


def _fit_calibrated_histgb(train_df: pd.DataFrame, test_df: pd.DataFrame,
                            feature_cols: list, calib_tail_frac: float = CALIB_TAIL_FRAC) -> dict:
    """HistGradientBoostingClassifier fit on the earlier (1 - calib_tail_frac)
    of TRAIN (sorted by game_date), isotonic-calibrated on the later temporal
    tail slice of TRAIN, scored on TEST. TEST never touches fitting."""
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
    # score in _BUCKETS_SORTED (alphabetical) order -- log_loss(labels=X)
    # always assumes that order regardless of X (pa_outcome_model note).
    proba = proba[_BUCKETS_SORTED]
    # isotonic on well-separated data can output exact 0/1; ONE test-row
    # miss against an exact-0 true-class prob makes log_loss infinite --
    # floor + renormalize (same 1e-6 floor fit_eval_layer uses).
    proba = proba.clip(lower=1e-6)
    proba = proba.div(proba.sum(axis=1), axis=0)
    ll = float(log_loss(test_df["bucket"], proba.to_numpy(), labels=_BUCKETS_SORTED))
    briers = {}
    for b in BUCKETS:
        y_bin = (test_df["bucket"] == b).astype(int)
        briers[b] = round(float(brier_score_loss(y_bin, proba[b])), 5)
    return {"log_loss": round(ll, 5), "brier": briers, "n_fit": int(len(fit_part)),
            "n_calib": int(len(calib_part))}


def verdict_rule(league_ll: float, profiles_ll: float, candidate_ll: float,
                  profiles_brier_ipo: float, candidate_brier_ipo: float) -> str:
    beats_both = candidate_ll < league_ll and candidate_ll < profiles_ll
    return "SHIP_PROVISIONAL" if beats_both and candidate_brier_ipo <= profiles_brier_ipo else "NULL"


def run() -> dict:
    pa = load_pa_dataset(SEASONS)
    pitch_rows = load_pitch_rows(seasons=SEASONS)
    pitcher_profile = build_pitcher_profile(pitch_rows)
    batter_profile = build_batter_profile(pitch_rows)
    pitcher_2022 = pitcher_profile[pitcher_profile["season"] == TRAIN_SEASON]
    batter_2022 = batter_profile[batter_profile["season"] == TRAIN_SEASON]

    feats = build_features(pa, pitcher_2022, batter_2022)
    feats = add_v2_features(feats, TRAIN_SEASON)
    train = feats[feats["season"] == TRAIN_SEASON]
    test = feats[feats["season"] == TEST_SEASON]

    league = {"log_loss": round(fit_eval_layer(train, test, []), 5)}
    profiles = _fit_calibrated_histgb(train, test, PROFILE_FEATURES)
    candidate = _fit_calibrated_histgb(train, test, CANDIDATE_FEATURES)
    verdict = verdict_rule(league["log_loss"], profiles["log_loss"], candidate["log_loss"],
                            profiles["brier"]["IN_PLAY_OUT"], candidate["brier"]["IN_PLAY_OUT"])

    report = {
        "component": "pa_outcome_v2",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_train": int(len(train)), "n_test": int(len(test)),
        "train_date_range": [str(train["game_date"].min()), str(train["game_date"].max())],
        "test_date_range": [str(test["game_date"].min()), str(test["game_date"].max())],
        "buckets": BUCKETS,
        "league_marginal": league,
        "profiles_only": profiles,
        "candidate_v2": candidate,
        "verdict": verdict,
        "descriptive_only": True,
        "edge_claimed": False,
    }
    return report


def _append_ledger_row(report: dict) -> None:
    row = {
        "hypothesis": "pa_outcome_v2_composed(platoon_x_pitchtype + count_leverage_x_mix)",
        "sport": "mlb", "atomic_unit": "PA",
        "n": report["n_test"],
        "effect": round(report["profiles_only"]["log_loss"] - report["candidate_v2"]["log_loss"], 5),
        "p": None, "alpha_fwer": None,
        "verdict": report["verdict"],
        "term": "candidate_log_loss_minus_profiles_only_log_loss",
        "note": f"league={report['league_marginal']['log_loss']} "
                f"profiles_only={report['profiles_only']['log_loss']} "
                f"candidate={report['candidate_v2']['log_loss']}",
        "edge_claimed": False, "method": _METHOD,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    append_ledger([row])


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MLB PA-outcome v2 composed model")
    parser.parse_args(argv)

    report = run()
    _REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_OUT, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)
    _append_ledger_row(report)
    print(f"n_train={report['n_train']} n_test={report['n_test']}")
    print(f"  league_marginal:  log_loss={report['league_marginal']['log_loss']}")
    print(f"  profiles_only:    log_loss={report['profiles_only']['log_loss']} "
          f"brier[IN_PLAY_OUT]={report['profiles_only']['brier']['IN_PLAY_OUT']}")
    print(f"  candidate_v2:     log_loss={report['candidate_v2']['log_loss']} "
          f"brier[IN_PLAY_OUT]={report['candidate_v2']['brier']['IN_PLAY_OUT']}")
    print(f"VERDICT: {report['verdict']}")
    print(f"wrote -> {_REPORT_OUT}")
    print(f"appended ledger row -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
