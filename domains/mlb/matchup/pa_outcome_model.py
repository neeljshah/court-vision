"""domains.mlb.matchup.pa_outcome_model -- multinomial PA-outcome model
testing whether a PITCHER-MIX x BATTER-RESPONSE INTERACTION beats
batter-only / pitcher-only / league-rate baselines at predicting the PA
outcome bucket.

BUCKETS (from statcast `events`, PA-terminal rows only):
  K            strikeout, strikeout_double_play
  BB           walk, intent_walk, hit_by_pitch (HBP folded into the "free
               base" bucket -- documented choice, not a hidden merge)
  IN_PLAY_OUT  field_out, force_out, grounded_into_double_play, double_play,
               fielders_choice(_out), sac_fly, sac_bunt, field_error
               (reached on a defensive miscue, bucketed with the outs as an
               approximation -- small n)
  SINGLE_PLUS  single ONLY -- XBH is split out below, matching the 5-bucket
               spec's naming (not "any hit")
  XBH          double, triple, home_run
  (dropped: catcher_interf, truncated_pa -- not resolvable to a clean bucket)

FEATURES (2022-ESTABLISHED, PROJECTED FORWARD -- walk-forward, not
same-season): every feature is read from the 2022 (train-season-only)
pitcher/batter pitch-type profiles from pitch_mix_profiles.py. The SAME 2022
profile table builds features for both 2022 train rows and 2023 test rows,
so no 2023 label ever touches a 2023 feature -- the reported TEST log-loss
is genuinely out-of-season (2022 in-sample fit is not itself leak-free; only
the 2023 held-out evaluation is the walk-forward claim).
  batter_k_rate / batter_slug / batter_bb_rate -- batter's usage-weighted
    overall 2022 profile.
  pitcher_k_rate / pitcher_zone_rate -- pitcher's usage-weighted overall
    2022 profile.
  platoon_match -- 1 if batter.stand == pitcher.p_throws else 0.
  outs_when_up, score_diff -- in-game context (outs_when_up is statcast-
    native; score_diff = batting team's score - fielding team's score, a
    leverage PROXY). TRUE base-out state (runners on base) is CORPUS_ABSENT:
    statcast_fuller has no on_1b/on_2b/on_3b columns, and the separate
    data/cache/ingame/mlb_pitch_states parquets that DO carry base/out state
    have NO pitcher/batter identity column (verified live this session) --
    not joinable at the player level this task needs. Honest null, per the
    brief's own "if joinable" framing.
  expected_k_interaction = sum over pitch types pt of
    pitcher_usage_2022[pitcher, pt] * batter_k_rate_2022[batter, pt] -- what
    K rate this batter's own per-pitch-type tendencies would predict,
    weighted by how often THIS pitcher actually throws each pitch type.
    THE interaction term the task calls for.
  expected_slug_interaction -- identical construction with slug_proxy.
Batters/pitchers absent from the 2022 profile fall back to the column-mean
of that feature (never silently zero-filled -- fixed bug: nansum() over an
all-NaN reindexed row used to return 0.0 for the interaction terms; now
re-nulled + column-mean-imputed like the other projected features).

SPLIT: train = 2022 PA rows, test = 2023 PA rows (temporal, not random).
MODEL: sklearn LogisticRegression, one fit per LAYER (additive feature
sets), scored by log_loss on the SAME held-out 2023 rows.
HONEST NULL: if the interaction layer does not beat batter-only+pitcher-only
on held-out log-loss, that is reported as a NULL result, not hidden.

CLOSED-CLASS GUARD: a PA-outcome classifier, not an in-game SP-fatigue/
velocity model -- no pitch-count/fatigue feature anywhere in this module;
that CLOSED class is untouched.

NETWORK: zero. DESCRIPTIVE/RESEARCH MODEL ONLY -- NO MARKET/$ EDGE CLAIMED.
CLI: python -m domains.mlb.matchup.pa_outcome_model
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

from domains.mlb.matchup.pitch_mix_profiles import (
    SEASONS, build_batter_profile, build_pitcher_profile, load_pitch_rows,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATCAST = {
    2022: _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet",
    2023: _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet",
}
_REPORT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "matchup" / "pa_outcome_model_report.json"

_K_EVENTS = {"strikeout", "strikeout_double_play"}
_BB_EVENTS = {"walk", "intent_walk", "hit_by_pitch"}
_IN_PLAY_OUT_EVENTS = {
    "field_out", "force_out", "grounded_into_double_play", "double_play",
    "fielders_choice", "fielders_choice_out", "sac_fly", "sac_bunt", "field_error",
}
_SINGLE_EVENTS = {"single"}
_XBH_EVENTS = {"double", "triple", "home_run"}
BUCKETS = ["K", "BB", "IN_PLAY_OUT", "SINGLE_PLUS", "XBH"]
_BUCKET_MAP = {}
for _e in _K_EVENTS: _BUCKET_MAP[_e] = "K"
for _e in _BB_EVENTS: _BUCKET_MAP[_e] = "BB"
for _e in _IN_PLAY_OUT_EVENTS: _BUCKET_MAP[_e] = "IN_PLAY_OUT"
for _e in _SINGLE_EVENTS: _BUCKET_MAP[_e] = "SINGLE_PLUS"
for _e in _XBH_EVENTS: _BUCKET_MAP[_e] = "XBH"

_PITCH_TYPE_VOCAB = ["FF", "SL", "SI", "CH", "FC", "CU", "ST", "KC", "FS"]
_PA_COLS = [
    "pitcher", "batter", "pitch_type", "events", "stand", "p_throws",
    "outs_when_up", "bat_score", "home_score", "away_score",
]

FEATURE_LAYERS = {
    "league_rate": [],
    "batter_only": ["batter_k_rate", "batter_slug", "batter_bb_rate"],
    "pitcher_only": ["pitcher_k_rate", "pitcher_zone_rate"],
    "interaction": [
        "batter_k_rate", "batter_slug", "batter_bb_rate",
        "pitcher_k_rate", "pitcher_zone_rate", "platoon_match",
        "outs_when_up", "score_diff",
        "expected_k_interaction", "expected_slug_interaction",
    ],
}


def load_pa_dataset(seasons: tuple = SEASONS) -> pd.DataFrame:
    """PA-terminal rows (events notna) with pitcher/batter/pitch_type/
    platoon/in-game-context columns all read in ONE pass per season -- a
    single self-contained frame, not a reload-and-realign of pitch_rows (a
    separate reload filtered differently can silently misalign row counts,
    e.g. intentional-walk PAs that carry no pitch_type)."""
    frames = []
    for season in seasons:
        df = pd.read_parquet(_STATCAST[season], columns=_PA_COLS)
        df = df[df["events"].notna()].copy()
        df["season"] = season
        frames.append(df)
    pa = pd.concat(frames, ignore_index=True)
    pa["bucket"] = pa["events"].map(_BUCKET_MAP)
    return pa[pa["bucket"].notna()].copy()


def _pitcher_overall(pitcher_profile: pd.DataFrame) -> pd.DataFrame:
    df = pitcher_profile.copy()
    df["w_zone"] = df["in_zone_rate"].fillna(0) * df["usage_share"]
    df["w_k"] = np.where(df["n_pitches"] > 0, df["n_k"] / df["n_pitches"], 0.0) * df["usage_share"]
    return df.groupby(["pitcher", "season"]).agg(
        pitcher_zone_rate=("w_zone", "sum"), pitcher_k_rate=("w_k", "sum"),
    ).reset_index()


def _batter_overall(batter_profile: pd.DataFrame) -> pd.DataFrame:
    df = batter_profile.copy()
    total = df.groupby(["batter", "season"])["n_pa"].transform("sum")
    w = df["n_pa"] / total.replace(0, np.nan)
    df["w_k"] = df["k_rate"] * w
    df["w_slug"] = df["slug_proxy"] * w
    df["w_bb"] = df["bb_rate"] * w
    return df.groupby(["batter", "season"]).agg(
        batter_k_rate=("w_k", "sum"), batter_slug=("w_slug", "sum"), batter_bb_rate=("w_bb", "sum"),
    ).reset_index()


def _wide_matrix(profile: pd.DataFrame, id_col: str, value_col: str, league_avg: pd.Series) -> pd.DataFrame:
    sub = profile[profile["pitch_type"].isin(_PITCH_TYPE_VOCAB)]
    wide = sub.pivot_table(index=id_col, columns="pitch_type", values=value_col, aggfunc="mean")
    wide = wide.reindex(columns=_PITCH_TYPE_VOCAB)
    for pt in _PITCH_TYPE_VOCAB:
        wide[pt] = wide[pt].fillna(league_avg.get(pt, 0.0))
    return wide


def build_features(pa: pd.DataFrame, pitcher_profile_2022: pd.DataFrame,
                    batter_profile_2022: pd.DataFrame) -> pd.DataFrame:
    """Build features for `pa` (any season) using ONLY the 2022 profile
    tables -- see module docstring's walk-forward rationale."""
    pitcher_overall = _pitcher_overall(pitcher_profile_2022)
    batter_overall = _batter_overall(batter_profile_2022)
    df = pa.merge(pitcher_overall.drop(columns="season"), on="pitcher", how="left")
    df = df.merge(batter_overall.drop(columns="season"), on="batter", how="left")
    # coverage flags: does this PA's pitcher/batter have a REAL 2022 profile,
    # or is every projected feature below about to be an imputed placeholder?
    df["has_pitcher_profile"] = df["pitcher"].isin(pitcher_overall["pitcher"])
    df["has_batter_profile"] = df["batter"].isin(batter_overall["batter"])

    league_usage = pitcher_profile_2022.groupby("pitch_type")["usage_share"].mean()
    league_k = batter_profile_2022.groupby("pitch_type")["k_rate"].mean()
    league_slug = batter_profile_2022.groupby("pitch_type")["slug_proxy"].mean()

    for col in ("batter_k_rate", "batter_slug", "batter_bb_rate", "pitcher_zone_rate", "pitcher_k_rate"):
        df[col] = df[col].fillna(df[col].mean())

    df["platoon_match"] = (df["stand"] == df["p_throws"]).astype(int)
    df["score_diff"] = df["bat_score"] - (df["home_score"] + df["away_score"] - df["bat_score"])
    df["outs_when_up"] = df["outs_when_up"].fillna(0)

    usage_wide = _wide_matrix(pitcher_profile_2022, "pitcher", "usage_share", league_usage)
    batter_k_wide = _wide_matrix(batter_profile_2022, "batter", "k_rate", league_k)
    batter_slug_wide = _wide_matrix(batter_profile_2022, "batter", "slug_proxy", league_slug)
    u = usage_wide.reindex(df["pitcher"]).to_numpy()
    bk = batter_k_wide.reindex(df["batter"]).to_numpy()
    bs = batter_slug_wide.reindex(df["batter"]).to_numpy()
    df["expected_k_interaction"] = np.nansum(u * bk, axis=1)
    df["expected_slug_interaction"] = np.nansum(u * bs, axis=1)
    # nansum() silently zeroes all-NaN reindexed rows (bug) -- re-null + impute
    # like the other projected features instead.
    uncovered = ~(df["has_pitcher_profile"] & df["has_batter_profile"])
    df.loc[uncovered, "expected_k_interaction"] = np.nan
    df.loc[uncovered, "expected_slug_interaction"] = np.nan
    for col in ("expected_k_interaction", "expected_slug_interaction"):
        df[col] = df[col].fillna(df[col].mean())
    return df


def fit_eval_layer(train_df: pd.DataFrame, test_df: pd.DataFrame, feature_cols: list) -> float:
    y_train, y_test = train_df["bucket"], test_df["bucket"]
    if not feature_cols:
        rates = y_train.value_counts(normalize=True).reindex(BUCKETS).fillna(1e-6)
        probs = np.tile(rates.to_numpy(), (len(y_test), 1))
        return float(log_loss(y_test, probs, labels=BUCKETS))
    scaler = StandardScaler().fit(train_df[feature_cols])
    X_train = scaler.transform(train_df[feature_cols])
    X_test = scaler.transform(test_df[feature_cols])
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_train, y_train)
    prob_df = pd.DataFrame(clf.predict_proba(X_test), columns=clf.classes_)
    for b in BUCKETS:
        if b not in prob_df.columns:
            prob_df[b] = 1e-6
    return float(log_loss(y_test, prob_df[BUCKETS].to_numpy(), labels=BUCKETS))


def run_ladder() -> dict:
    pitch_rows = load_pitch_rows(seasons=SEASONS)
    pa = load_pa_dataset(SEASONS)

    pitcher_profile = build_pitcher_profile(pitch_rows)
    batter_profile = build_batter_profile(pitch_rows)
    pitcher_2022 = pitcher_profile[pitcher_profile["season"] == 2022]
    batter_2022 = batter_profile[batter_profile["season"] == 2022]

    feats = build_features(pa, pitcher_2022, batter_2022)
    train = feats[feats["season"] == 2022]
    test = feats[feats["season"] == 2023]
    # report the ladder on the full test set AND the both-covered subset, so
    # a coverage artifact (imputed-placeholder rows) can't hide the verdict.
    covered = test["has_pitcher_profile"] & test["has_batter_profile"]
    test_covered = test[covered]

    def _ladder(train_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:
        out = {}
        for name, cols in FEATURE_LAYERS.items():
            out[name] = {"log_loss": round(fit_eval_layer(train_df, test_df, cols), 5), "n_features": len(cols)}
        base = out["league_rate"]["log_loss"]
        for name in out:
            out[name]["delta_vs_league"] = round(base - out[name]["log_loss"], 5)
        return out

    return {
        "component": "pa_outcome_model",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "test_coverage": {
            "both_profile_covered_n": int(covered.sum()),
            "both_profile_covered_frac": round(float(covered.mean()), 4),
        },
        "buckets": BUCKETS,
        "layers": _ladder(train, test),
        "layers_covered_subset": _ladder(train, test_covered),
        "descriptive_only": True,
        "edge_claimed": False,
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MLB PA-outcome interaction-model ladder")
    parser.parse_args(argv)

    report = run_ladder()
    _REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_OUT, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)

    cov = report["test_coverage"]
    print(f"n_train={report['n_train']} n_test={report['n_test']} "
          f"both_profile_covered={cov['both_profile_covered_n']} ({cov['both_profile_covered_frac']:.2%})")
    print("layers (full test set):")
    for name, r in report["layers"].items():
        print(f"  {name}: log_loss={r['log_loss']} delta_vs_league={r['delta_vs_league']} "
              f"n_features={r['n_features']}")
    print("layers (both-profile-covered subset):")
    for name, r in report["layers_covered_subset"].items():
        print(f"  {name}: log_loss={r['log_loss']} delta_vs_league={r['delta_vs_league']} "
              f"n_features={r['n_features']}")
    print(f"wrote -> {_REPORT_OUT}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
