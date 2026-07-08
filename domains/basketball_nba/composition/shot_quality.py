"""Shot-level P(make) model + delta ladder -- what each intelligence layer
buys at the ATOMIC unit (one shot), on the full 213k-shot 2025-26 corpus
(shot_features.build_shot_frame). Plain sklearn LogisticRegression, no deep
nets (ponytail: this is a shot-quality DESCRIPTOR, not a market claim).

SPLIT: temporal 60/40 by GAME (never by shot -- a within-game split would
leak). ponytail: games are ordered by sorting `game_id` as a string, not by
a joined calendar date -- verified 99.3% consistent with the box-score date
column on this corpus (NBA game_ids are assigned sequentially within a
season), so this is a reasonable date-proxy without a second data-source
join. A real calendar-date join is the upgrade if that residual ~0.7% jitter
ever matters.

REPORTED ROWS (Brier + log-loss on the held-out 40%):
  league     -- constant = train mean(make), the spec's baseline (i).
  zone_only  -- zone one-hot ONLY, the spec's baseline (ii), reported
                separately from the ladder below so both named baselines
                exist verbatim.
  zone_full  -- zone + subType class + assisted flag (all THREE are
                directly observed on the shot itself, zero historical
                lookup -- the ladder's true zero-intelligence floor).
  +shooter   -- zone_full + shooter's season zone-eFG baseline.
  +defense   -- +shooter + defense's zone-concession eFG (concession_profiles.py).
  +spacing   -- +defense + the shooter's lineup's season spacing proxy.
Each later row's improvement over the previous IS the delta ladder.

PER-GAME EXPECTED POINTS (shooting-luck measurement): the FINAL (+spacing)
model, fit ONCE on the train split, scores every shot in the corpus
(ponytail: train-split rows are then in-sample, test-split rows are OOS --
fine for a descriptive per-game aggregate, not fine for a predictive claim).
xpts = sum(p_hat * shot_value) per (game_id, team_id); luck = actual - xpts.
OUTPUT: data/cache/team_system/composition/shot_xpts_2025_26.parquet.

NETWORK: zero. CLI: python -m domains.basketball_nba.composition.shot_quality
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

from domains.basketball_nba.composition.shot_features import build_shot_frame

REPO_ROOT = Path(__file__).resolve().parents[3]
_XPTS_OUT = REPO_ROOT / "data" / "cache" / "team_system" / "composition" / "shot_xpts_2025_26.parquet"

TRAIN_FRACTION = 0.60


def temporal_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    games = sorted(df["game_id"].unique())
    cut = int(len(games) * TRAIN_FRACTION)
    train_games, test_games = set(games[:cut]), set(games[cut:])
    return df[df["game_id"].isin(train_games)].copy(), df[df["game_id"].isin(test_games)].copy()


def build_design_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """One-hot zone/subtype ONCE (so train/test share identical columns),
    return (design_df, named feature-group column lists) for rung assembly."""
    zone_dummies = pd.get_dummies(df["zone"], prefix="zone")
    subtype_dummies = pd.get_dummies(df["subtype_class"], prefix="sub")
    design = pd.concat([df.reset_index(drop=True), zone_dummies.reset_index(drop=True), subtype_dummies.reset_index(drop=True)], axis=1)
    groups = {
        "zone": list(zone_dummies.columns),
        "descriptors": list(zone_dummies.columns) + list(subtype_dummies.columns) + ["assisted"],
        "shooter": ["shooter_zone_efg"],
        "defense": ["defense_zone_efg_allowed"],
        "spacing": ["spacing_mean_dist"],
    }
    return design, groups


def fit_rung(train: pd.DataFrame, test: pd.DataFrame, feature_cols: list[str] | None) -> tuple[float, float, "pd.Series"]:
    """feature_cols=None -> the constant 'league' baseline. Returns (brier, log_loss, test_p_hat)."""
    y_train, y_test = train["made"].to_numpy(), test["made"].to_numpy()
    if feature_cols is None:
        p_test = pd.Series(y_train.mean(), index=test.index)
    else:
        clf = LogisticRegression(max_iter=1000)
        clf.fit(train[feature_cols].to_numpy(), y_train)
        p_test = pd.Series(clf.predict_proba(test[feature_cols].to_numpy())[:, 1], index=test.index)
    brier = brier_score_loss(y_test, p_test.to_numpy())
    ll = log_loss(y_test, p_test.to_numpy(), labels=[0, 1])
    return brier, ll, p_test


def fit_final_model(train: pd.DataFrame, feature_cols: list[str]) -> LogisticRegression:
    clf = LogisticRegression(max_iter=1000)
    clf.fit(train[feature_cols].to_numpy(), train["made"].to_numpy())
    return clf


def run_delta_ladder(design: pd.DataFrame, groups: dict[str, list[str]]) -> tuple[pd.DataFrame, LogisticRegression, list[str]]:
    train, test = temporal_split(design)
    rungs: list[tuple[str, list[str] | None]] = [
        ("league", None),
        ("zone_only", groups["zone"]),
        ("zone_full", groups["descriptors"]),
        ("+shooter", groups["descriptors"] + groups["shooter"]),
        ("+defense", groups["descriptors"] + groups["shooter"] + groups["defense"]),
        ("+spacing", groups["descriptors"] + groups["shooter"] + groups["defense"] + groups["spacing"]),
    ]
    rows = []
    final_cols: list[str] = []
    for name, cols in rungs:
        brier, ll, _ = fit_rung(train, test, cols)
        rows.append({"rung": name, "n_features": len(cols) if cols else 0, "brier": round(brier, 5), "log_loss": round(ll, 5)})
        if name == "+spacing":
            final_cols = cols
    return pd.DataFrame(rows), fit_final_model(train, final_cols), final_cols


def build_per_game_xpts(design: pd.DataFrame, clf: LogisticRegression, feature_cols: list[str]) -> pd.DataFrame:
    p_hat = clf.predict_proba(design[feature_cols].to_numpy())[:, 1]
    scored = design.assign(xpts=p_hat * design["points"], actual_pts=design["made"] * design["points"])
    agg = scored.groupby(["game_id", "team_id"]).agg(
        xpts=("xpts", "sum"), actual_pts=("actual_pts", "sum"), n_shots=("made", "size"),
    ).reset_index()
    agg["luck"] = agg["actual_pts"] - agg["xpts"]
    return agg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fit the NBA shot-quality delta ladder + per-game xpts")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=str, default=str(_XPTS_OUT))
    args = parser.parse_args(argv)

    df = build_shot_frame(limit=args.limit)
    design, groups = build_design_matrix(df)
    ladder_df, final_clf, final_cols = run_delta_ladder(design, groups)
    print(ladder_df.to_string(index=False))

    xpts_df = build_per_game_xpts(design, final_clf, final_cols)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    xpts_df.to_parquet(out_path, index=False)
    print(f"games={len(xpts_df)} luck_std={xpts_df['luck'].std():.3f} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
