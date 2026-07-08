"""domains.mlb.matchup.pa_outcome_v2b_pregame -- follow-up to pa_outcome_v2.py's
SHIP_PROVISIONAL_RETROSPECTIVE. v2's winning column, count_leverage_mix_share,
is computed from the PA's OWN realized pitch sequence -- known only in
hindsight once the PA unfolds, not at first pitch. This module tests the
genuinely PREGAME analogue: does the PITCHER'S OWN HISTORICAL TENDENCY (not
this PA's outcome) carry any of that signal?

REPLACEMENT FEATURE -- pitcher_ahead_breaking_share_asof: per pitcher, the
EXPANDING, STRICTLY-PRIOR share of pitches thrown while pitcher-ahead
(strikes>balls pre-pitch, same convention as v2/mlb_hypotheses.build_h5) that
were breaking/offspeed (not in FASTBALL_TYPES), walked forward BY GAME_DATE
across the WHOLE statcast_fuller__2022+2023 corpus -- a 2023 PA can draw on
2022 history, but never on same-date-or-later pitches. This is a season-
spanning pitcher PROFILE (like pitcher_k_rate), not a PA-scoped summary: it
uses every pitch the pitcher threw (terminal or not), on every prior
game_date, not just this PA's own non-terminal pitches.

The two platoon_breaking_* columns from v2 are kept UNCHANGED (they were
already profile-based -- 2022-only, not PA-hindsight -- so nothing to convert
there); only count_leverage_mix_share is replaced.

REUSE (no reinvention): dataset loader (load_pa_dataset/build_features from
pa_outcome_model), the platoon_breaking_* lookup, HistGB+isotonic fit,
verdict rule, and PROFILE_FEATURES baseline columns -- all imported directly
from pa_outcome_v2.py, not re-implemented. Same walk-forward split
(train=2022, test=2023), same probability-floor/renormalize + sklearn
label-order fix inside the reused _fit_calibrated_histgb.

BASELINES (unchanged from v2): league_marginal (v1's zero-feature layer) and
profiles_only (candidate's marginal columns without the two interaction
features) -- both required for the SAME verdict rule.

VERDICT (declared before running, identical rule to v2): SHIP_PROVISIONAL iff
candidate log_loss < BOTH baselines AND its IN_PLAY_OUT Brier doesn't degrade
vs profiles_only. Else NULL -- expected here, since a hindsight-derived
feature usually does not survive conversion to an as-of profile.

RESULT (2026-07-08 real run, statcast_fuller 2022 train / 2023 test,
n_train=182022 n_test=184058): league=1.40231, profiles_only=1.42268,
candidate=1.41297, brier[IN_PLAY_OUT] 0.24671->0.24697. Candidate beats
profiles_only but NOT league_marginal (the declared rule requires beating
BOTH) -- HONEST NULL. pitcher_ahead_breaking_share_asof recovers roughly a
third of profiles_only's gap to league (1.42268->1.41297 of a 0.02037 gap)
but not enough to clear the bar, and IN_PLAY_OUT Brier is marginally worse,
not better. Consistent with v2's own SCOPING NOTE: most of that model's lift
was concentrated in the PA's-own-realized-sequence hindsight feature, not a
deployable pregame pitcher tendency -- this as-of conversion keeps a sliver
of signal but not the win.

Descriptive/research model only. NETWORK: zero. NO MARKET/$ EDGE CLAIMED.
CLI: python -m domains.mlb.matchup.pa_outcome_v2b_pregame
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from domains.mlb.matchup.pa_outcome_model import (
    BUCKETS, _STATCAST, build_features, fit_eval_layer, load_pa_dataset,
)
from domains.mlb.matchup.pa_outcome_v2 import (
    CALIB_TAIL_FRAC, PROFILE_FEATURES, TEST_SEASON, TRAIN_SEASON,
    _fit_calibrated_histgb, build_platoon_breaking_lookup, verdict_rule,
)
from domains.mlb.matchup.pitch_mix_profiles import (
    SEASONS, build_batter_profile, build_pitcher_profile, load_pitch_rows,
)
from domains.mlb.prereg.mlb_hypotheses import FASTBALL_TYPES
from domains.mlb.prereg.stats_common import LEDGER_PATH, append_ledger

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPORT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "matchup" / "pa_outcome_v2b_report.json"
_METHOD = "pa_outcome_v2b_pregame_walkforward"

V2B_INTERACTION_FEATURES = [
    "platoon_breaking_on_base_rate", "platoon_breaking_k_rate", "pitcher_ahead_breaking_share_asof",
]
CANDIDATE_FEATURES = PROFILE_FEATURES + V2B_INTERACTION_FEATURES


def _load_ahead_count_pitch_days(seasons: tuple = SEASONS) -> pd.DataFrame:
    """Per (pitcher, game_date): n_ahead pitches (strikes>balls pre-pitch, ANY
    pitch -- this is a calendar-spanning PROFILE, not PA-scoped) and how many
    were breaking. Every game_date the pitcher threw AT ALL appears (0/0 on
    days with zero ahead-count pitches) so the expanding walk below covers the
    pitcher's full calendar, not just ahead-count days."""
    cols = ["pitcher", "game_date", "pitch_type", "balls", "strikes"]
    frames = []
    for season in seasons:
        df = pd.read_parquet(_STATCAST[season], columns=cols)
        df = df[df["pitch_type"].notna() & (df["pitch_type"] != "None")]
        frames.append(df)
    rows = pd.concat(frames, ignore_index=True)
    all_days = rows.groupby(["pitcher", "game_date"]).size().reset_index()[["pitcher", "game_date"]]

    ahead = rows[rows["strikes"] > rows["balls"]].copy()
    ahead["is_breaking"] = (~ahead["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    ahead_daily = ahead.groupby(["pitcher", "game_date"]).agg(
        n_ahead=("is_breaking", "size"), n_breaking_ahead=("is_breaking", "sum"),
    ).reset_index()

    daily = all_days.merge(ahead_daily, on=["pitcher", "game_date"], how="left")
    daily[["n_ahead", "n_breaking_ahead"]] = daily[["n_ahead", "n_breaking_ahead"]].fillna(0)
    return daily


def _expanding_asof_share(daily: pd.DataFrame) -> pd.DataFrame:
    """Pure function, no IO: given per (pitcher, game_date) n_ahead /
    n_breaking_ahead counts, return the STRICTLY-PRIOR expanding share --
    each row's value uses only that pitcher's earlier game_dates. A
    pitcher's first game_date has no prior history -> NaN (imputed by the
    caller, not here)."""
    daily = daily.sort_values(["pitcher", "game_date"]).reset_index(drop=True)
    grp = daily.groupby("pitcher")
    prior_ahead = grp["n_ahead"].cumsum() - daily["n_ahead"]
    prior_breaking = grp["n_breaking_ahead"].cumsum() - daily["n_breaking_ahead"]
    daily["pitcher_ahead_breaking_share_asof"] = prior_breaking / prior_ahead.replace(0, np.nan)
    return daily[["pitcher", "game_date", "pitcher_ahead_breaking_share_asof"]]


def build_pitcher_ahead_breaking_asof(seasons: tuple = SEASONS) -> pd.DataFrame:
    """Walk-forward BY DATE across the whole corpus (not by season) -- a 2023
    PA may draw on 2022+prior-2023 history, per the module docstring."""
    return _expanding_asof_share(_load_ahead_count_pitch_days(seasons))


def add_v2b_features(feats: pd.DataFrame, train_season: int = TRAIN_SEASON) -> pd.DataFrame:
    """Join platoon_breaking_* (unchanged from v2, TRAIN-season-only lookup)
    and the new as-of pitcher profile onto v1's feature frame. Missing cells
    (incl. a pitcher's first-ever appearance, with no prior history) imputed
    with the TRAIN-ONLY column mean, applied to both splits."""
    df = feats.copy()
    df["is_breaking_terminal"] = (~df["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    platoon_lookup = build_platoon_breaking_lookup(train_season)
    df = df.merge(
        platoon_lookup, how="left",
        left_on=["batter", "p_throws", "is_breaking_terminal"],
        right_on=["batter", "p_throws", "is_breaking"],
    ).drop(columns=["is_breaking"], errors="ignore")

    asof = build_pitcher_ahead_breaking_asof(SEASONS)
    df = df.merge(asof, on=["pitcher", "game_date"], how="left")

    train_mask = df["season"] == train_season
    for col in V2B_INTERACTION_FEATURES:
        train_mean = df.loc[train_mask, col].mean()
        df[col] = df[col].fillna(train_mean)
    return df


def run() -> dict:
    pa = load_pa_dataset(SEASONS)
    pitch_rows = load_pitch_rows(seasons=SEASONS)
    pitcher_profile = build_pitcher_profile(pitch_rows)
    batter_profile = build_batter_profile(pitch_rows)
    pitcher_2022 = pitcher_profile[pitcher_profile["season"] == TRAIN_SEASON]
    batter_2022 = batter_profile[batter_profile["season"] == TRAIN_SEASON]

    feats = build_features(pa, pitcher_2022, batter_2022)
    feats = add_v2b_features(feats, TRAIN_SEASON)
    train = feats[feats["season"] == TRAIN_SEASON]
    test = feats[feats["season"] == TEST_SEASON]

    league = {"log_loss": round(fit_eval_layer(train, test, []), 5)}
    profiles = _fit_calibrated_histgb(train, test, PROFILE_FEATURES, CALIB_TAIL_FRAC)
    candidate = _fit_calibrated_histgb(train, test, CANDIDATE_FEATURES, CALIB_TAIL_FRAC)
    verdict = verdict_rule(league["log_loss"], profiles["log_loss"], candidate["log_loss"],
                            profiles["brier"]["IN_PLAY_OUT"], candidate["brier"]["IN_PLAY_OUT"])

    report = {
        "component": "pa_outcome_v2b_pregame",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_train": int(len(train)), "n_test": int(len(test)),
        "train_date_range": [str(train["game_date"].min()), str(train["game_date"].max())],
        "test_date_range": [str(test["game_date"].min()), str(test["game_date"].max())],
        "buckets": BUCKETS,
        "league_marginal": league,
        "profiles_only": profiles,
        "candidate_v2b": candidate,
        "verdict": verdict,
        "descriptive_only": True,
        "edge_claimed": False,
    }
    return report


def _append_ledger_row(report: dict) -> None:
    row = {
        "hypothesis": "pa_outcome_v2b_pregame(platoon_x_pitchtype + pitcher_ahead_breaking_share_asof)",
        "sport": "mlb", "atomic_unit": "PA",
        "n": report["n_test"],
        "effect": round(report["profiles_only"]["log_loss"] - report["candidate_v2b"]["log_loss"], 5),
        "p": None, "alpha_fwer": None,
        "verdict": report["verdict"],
        "term": "candidate_log_loss_minus_profiles_only_log_loss",
        "note": f"league={report['league_marginal']['log_loss']} "
                f"profiles_only={report['profiles_only']['log_loss']} "
                f"candidate={report['candidate_v2b']['log_loss']}",
        "edge_claimed": False, "method": _METHOD,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    append_ledger([row])


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MLB PA-outcome v2b pregame-analogue model")
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
    print(f"  candidate_v2b:    log_loss={report['candidate_v2b']['log_loss']} "
          f"brier[IN_PLAY_OUT]={report['candidate_v2b']['brier']['IN_PLAY_OUT']}")
    print(f"VERDICT: {report['verdict']}")
    print(f"wrote -> {_REPORT_OUT}")
    print(f"appended ledger row -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
