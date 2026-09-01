"""Leak-safe next-game-minutes A/B on the tracking corpus.

Points A/B is deliberately deferred until the local boxscore backfill: current
points boxscores cover only 34 of 972 tracked 2024-25 games.  This pivot uses
the ``minutes`` string in ``player_tracking_features_asof.parquet`` as the
single-corpus target, so the target has no boxscore join loss.  Run with
``NBA_DATA_ROOT`` or ``./data``; the evidence-only JSON is written to
``data/ab_reports/teacher_student_minutes.json`` under that root.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.platformkit.tracking_features import _game_key
from scripts.platformkit.leak_boundary import embargo_indices


BASE_FEATURES = ("minutes_expanding", "minutes_l5")
LOAD_FEATURES = (
    "cum_distance_7d", "cum_distance_14d", "minutes_7d", "days_rest",
    "speed_decline_ratio", "b2b",
)
EMBARGO_BLOCKS = 1


def _minutes_value(value: object) -> float:
    """Return numeric or ``MM:SS`` minutes as fractional minutes."""
    text = str(value).strip()
    if ":" in text:
        minutes, seconds = text.split(":", 1)
        return float(minutes) + float(seconds) / 60.0
    return float(text)


def _normalise_join_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy whose NBA player-game keys use one canonical dtype."""
    result = frame.copy()
    result["gameId"] = result["gameId"].map(_game_key)
    result["personId"] = pd.to_numeric(result["personId"], errors="raise").astype("int64")
    return result


def _asof_columns(frame: pd.DataFrame, names: Sequence[str]) -> pd.DataFrame:
    columns = ["gameId", "personId", *[name for name in names if name in frame]]
    result = _normalise_join_keys(frame.loc[:, columns])
    if result.duplicated(["gameId", "personId"]).any():
        raise ValueError("Duplicate tracking join keys")
    return result


def diagnose(targets: pd.DataFrame, tracking: pd.DataFrame) -> dict[str, object]:
    """Measure exact target-to-tracking player-game key coverage and misses."""
    target_keys = _normalise_join_keys(targets)
    tracking_keys = _normalise_join_keys(tracking.loc[:, ["gameId", "personId"]])
    tracking_pairs = set(map(tuple, tracking_keys.loc[:, ["gameId", "personId"]].to_numpy()))
    tracking_people = set(tracking_keys["personId"])
    tracking_games = set(tracking_keys["gameId"])
    pair_keys = list(map(tuple, target_keys.loc[:, ["gameId", "personId"]].to_numpy()))
    matched = np.fromiter((key in tracking_pairs for key in pair_keys), dtype=bool, count=len(pair_keys))
    misses = target_keys.loc[~matched].copy()
    different_game = misses["personId"].isin(tracking_people)
    never_person = ~different_game
    never_game = ~misses["gameId"].isin(tracking_games)
    samples = misses.loc[:, [name for name in ("gameId", "personId", "playerName", "minutes") if name in misses]].head(5)
    total = len(target_keys)
    return {
        "target_pairs": int(total),
        "tracking_pairs": int(len(tracking_pairs)),
        "matched_pairs": int(matched.sum()),
        "pair_coverage_pct": 100.0 * float(matched.mean()) if total else 0.0,
        "misses": {
            "count": int(len(misses)),
            "person_present_different_game": int(different_game.sum()),
            "person_never_in_tracking": int(never_person.sum()),
            "game_never_in_tracking": int(never_game.sum()),
        },
        "miss_samples": samples.to_dict(orient="records"),
    }


def _parse_minutes(value: object) -> float:
    try:
        return _minutes_value(value)
    except (TypeError, ValueError):
        return float("nan")


def tracking_targets(tracking: pd.DataFrame) -> pd.DataFrame:
    """Build same-game minutes outcomes directly from the tracking corpus."""
    targets = _asof_columns(tracking, ["gameDate", "minutes"])
    if "minutes" not in targets:
        raise ValueError("Tracking corpus has no minutes column")
    targets["minutes"] = targets["minutes"].map(_parse_minutes)
    targets["gameDate"] = pd.to_datetime(targets["gameDate"], errors="coerce")
    return targets.dropna(subset=["gameDate", "minutes"]).copy()


def build_features(tracking: pd.DataFrame, load: pd.DataFrame,
                   embeddings: pd.DataFrame) -> pd.DataFrame:
    """Join as-of inputs and add strictly-prior player history features."""
    tracking_columns = [name for name in tracking if name.endswith(("_per36_l5", "_per36_l10"))]
    embedding_columns = [name for name in embeddings if name.startswith("style_embedding_")]
    result = tracking_targets(tracking)
    tracking_features = _asof_columns(tracking, tracking_columns)
    result = result.merge(tracking_features, on=["gameId", "personId"], how="left", validate="one_to_one")
    result = result.merge(_asof_columns(load, LOAD_FEATURES), on=["gameId", "personId"], how="left", validate="one_to_one")
    result = result.merge(_asof_columns(embeddings, embedding_columns), on=["gameId", "personId"], how="left", validate="one_to_one")
    result["gameDate"] = pd.to_datetime(result["gameDate"], errors="coerce")
    result = result.sort_values(["personId", "gameDate", "gameId"], kind="mergesort").reset_index(drop=True)
    grouped = result.groupby("personId", sort=False)
    prior = grouped["minutes"].shift(1)
    result["minutes_expanding"] = prior.groupby(result["personId"], sort=False).transform(
        lambda values: values.expanding().mean()
    )
    result["minutes_l5"] = prior.groupby(result["personId"], sort=False).transform(
        lambda values: values.rolling(5, min_periods=1).mean()
    )
    return result.sort_values(["gameDate", "gameId", "personId"], kind="mergesort").reset_index(drop=True)


def expanding_folds(frame: pd.DataFrame, folds: int = 4) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield identical chronological expanding-window train/test index pairs."""
    dates = pd.to_datetime(frame["gameDate"], errors="raise")
    assert dates.is_monotonic_increasing, "Rows must be sorted by gameDate before folds"
    unique_dates = dates.drop_duplicates().to_numpy()
    blocks = np.array_split(unique_dates, folds + 1)
    if len(unique_dates) < folds + 1 or any(len(block) == 0 for block in blocks):
        raise ValueError("Need at least {0} distinct game dates".format(folds + 1))
    for fold in range(folds):
        train_dates = np.concatenate(blocks[: fold + 1])
        test_dates = blocks[fold + 1]
        train_index = np.flatnonzero(dates.isin(train_dates))
        test_index = np.flatnonzero(dates.isin(test_dates))
        assert dates.iloc[train_index].max() < dates.iloc[test_index].min(), "Fold leaks future dates"
        yield train_index, test_index


def _matrix(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Return the requested numeric design-matrix columns without imputing."""
    return frame.loc[:, columns].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _median_impute_train_test(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Median-impute each matrix column using values available in train only."""
    medians = train.median(axis=0).fillna(0.0)
    return train.fillna(medians), test.fillna(medians)


def evaluate_ab(frame: pd.DataFrame, tracking_columns: Sequence[str], folds: int = 4,
                coverage_pct: float = 100.0) -> dict[str, object]:
    """Evaluate baseline and tracking arms on exactly the same expanding folds."""
    base = list(BASE_FEATURES)
    report_folds: list[dict[str, object]] = []
    base_errors: list[float] = []
    track_errors: list[float] = []
    features_valid = True
    for number, (train_index, test_index) in enumerate(expanding_folds(frame, folds), start=1):
        safe = embargo_indices(frame["gameDate"], frame.iloc[test_index]["gameDate"], EMBARGO_BLOCKS)
        train_index = np.intersect1d(train_index, safe, assume_unique=True)
        y_train = frame.iloc[train_index]["minutes"]
        y_test = frame.iloc[test_index]["minutes"]
        base_train, base_test = _median_impute_train_test(
            _matrix(frame.iloc[train_index], base), _matrix(frame.iloc[test_index], base)
        )
        tracking_train = _matrix(frame.iloc[train_index], tracking_columns)
        tracking_rates = tracking_train.notna().mean()
        usable_tracking = [name for name in tracking_columns if tracking_rates[name] >= 0.50]
        # This guards against an apparently high key-join rate whose values were
        # dropped or rendered unusable before reaching the tracking design matrix.
        features_valid = features_valid and len(usable_tracking) >= 3
        base_model = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(base_train, y_train)
        base_predictions = base_model.predict(base_test)
        base_errors.extend(np.abs(y_test.to_numpy() - base_predictions))
        base_mae = float(mean_absolute_error(y_test, base_predictions))
        fold_report: dict[str, object] = {
            "fold": number, "mae_base": base_mae, "coverage_pct": coverage_pct,
            "rows": int(len(test_index)), "tracking_train_columns": [*base, *usable_tracking],
            "tracking_non_null_rates": {name: float(tracking_rates[name]) for name in tracking_columns},
            "tracking_usable_columns": usable_tracking,
        }
        if len(usable_tracking) >= 3:
            track_train, track_test = _median_impute_train_test(
                _matrix(frame.iloc[train_index], [*base, *usable_tracking]),
                _matrix(frame.iloc[test_index], [*base, *usable_tracking]),
            )
            track_model = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(track_train, y_train)
            track_predictions = track_model.predict(track_test)
            track_errors.extend(np.abs(y_test.to_numpy() - track_predictions))
            track_mae = float(mean_absolute_error(y_test, track_predictions))
            fold_report.update({"mae_track": track_mae, "delta": track_mae - base_mae})
        report_folds.append(fold_report)
    # The assertion is deliberately adjacent to the verdict path: a future
    # refactor cannot return an A/B conclusion without a live tracking matrix.
    assert all(len(fold["tracking_usable_columns"]) >= 3 for fold in report_folds) == features_valid
    mae_base = float(np.mean(base_errors))
    mae_track = float(np.mean(track_errors)) if features_valid else None
    delta = mae_track - mae_base if mae_track is not None else None
    verdict = "INVALID (join)" if coverage_pct <= 60.0 else "INVALID (features)" if not features_valid else (
        "IMPROVED" if delta < 0 else "WORSE" if delta > 0 else "NO-CHANGE"
    )
    return {"folds": report_folds, "pooled": {"mae_base": mae_base, "mae_track": mae_track,
            "delta": delta, "coverage_pct": coverage_pct, "verdict": verdict}}


def run(data_root: Path, diagnose_only: bool = False) -> dict[str, object]:
    """Assemble the real corpus, run the A/B, and write its JSON evidence report."""
    nba_dir = data_root / "nba"
    tracking = pd.read_parquet(nba_dir / "player_tracking_features_asof.parquet")
    load = pd.read_parquet(nba_dir / "player_load_state_asof.parquet")
    embeddings = pd.read_parquet(nba_dir / "player_embeddings_asof.parquet")
    targets = tracking_targets(tracking)
    diagnosis = {
        "tracking": diagnose(targets, tracking),
        "load": diagnose(targets, load),
        "embeddings": diagnose(targets, embeddings),
    }
    if diagnose_only:
        return diagnosis
    coverage = min(float(item["pair_coverage_pct"]) for item in diagnosis.values())
    features = build_features(tracking, load, embeddings)
    tracking_columns = [name for name in features if name.endswith(("_per36_l5", "_per36_l10"))
                        or name in LOAD_FEATURES or name.startswith("style_embedding_")]
    # HistGradientBoosting handles the genuinely unavailable first-game history
    # values natively. Dropping them would needlessly remove an entire first
    # date and can make the required four chronological folds impossible.
    eligible = features.dropna(subset=["gameDate"]).copy()
    report = evaluate_ab(eligible, tracking_columns, coverage_pct=coverage)
    report["coverage_pct"] = coverage
    report["diagnosis"] = diagnosis
    report["rows_total"] = int(len(features))
    report["rows_evaluated"] = int(len(eligible))
    output = data_root / "ab_reports" / "teacher_student_minutes.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    """Run the offline A/B and print its concise ASCII-only summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnose", action="store_true", help="report minutes-target input key coverage")
    args = parser.parse_args()
    report = run(Path(os.environ.get("NBA_DATA_ROOT", "./data")), diagnose_only=args.diagnose)
    if args.diagnose:
        print(json.dumps(report, indent=2, allow_nan=False))
        return
    for fold in report["folds"]:
        print("fold {0} tracking_train_columns={1}".format(fold["fold"], fold["tracking_train_columns"]))
        for name, rate in fold["tracking_non_null_rates"].items():
            print("fold {0} tracking_non_null {1}={2:.1f}%".format(fold["fold"], name, 100.0 * rate))
        if "mae_track" in fold:
            print("fold {0} MAE_base={1:.3f} MAE_track={2:.3f} delta={3:.3f} coverage={4:.1f}%".format(
                fold["fold"], fold["mae_base"], fold["mae_track"], fold["delta"], fold["coverage_pct"]
            ))
        else:
            print("fold {0} MAE_base={1:.3f} MAE_track=NA delta=NA coverage={2:.1f}%".format(
                fold["fold"], fold["mae_base"], fold["coverage_pct"]
            ))
    pooled = report["pooled"]
    track_mae = "NA" if pooled["mae_track"] is None else "{0:.3f}".format(pooled["mae_track"])
    delta = "NA" if pooled["delta"] is None else "{0:.3f}".format(pooled["delta"])
    print("pooled MAE_base={0:.3f} MAE_track={1} delta={2} coverage={3:.1f}% VERDICT {4}".format(
        pooled["mae_base"], track_mae, delta, pooled["coverage_pct"], pooled["verdict"]
    ))


if __name__ == "__main__":
    main()
