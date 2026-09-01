"""Leak-free NFL run/pass prediction from pre-snap nflverse PBP fields only.

Only `play_type` run/pass rows without a penalty are retained; special teams,
no-plays, punts, field goals, kickoffs, spikes, and penalty rows are excluded.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss

PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{}.parquet"
FEATURE_COLUMNS = [
    "down", "ydstogo", "yardline_100", "quarter", "half_seconds_remaining",
    "game_seconds_remaining", "score_differential", "posteam_timeouts_remaining",
    "defteam_timeouts_remaining", "shotgun", "no_huddle", "team_asof_pass_rate",
]
PUBLISHED_ACCURACY = 0.753


def _data_root() -> Path:
    return Path(os.environ.get("NBA_DATA_ROOT", "data"))


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_parquet(path)


def fetch_pbp(years: Optional[Iterable[int]] = None, data_root: Optional[Path] = None) -> pd.DataFrame:
    """Load up to five local-first nflverse PBP seasons, downloading missing files."""
    root = Path(data_root) if data_root is not None else _data_root()
    candidates = list(years) if years is not None else range(datetime.now().year, datetime.now().year - 8, -1)
    frames = []
    for year in candidates:
        path = root / "nfl" / "pbp_{}.parquet".format(int(year))
        try:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                request = urllib.request.Request(PBP_URL.format(int(year)), headers={"User-Agent": "curl/8.0"})
                with urllib.request.urlopen(request, timeout=90) as response, path.open("wb") as target:
                    shutil.copyfileobj(response, target)
            frames.append(_read(path))
        except (OSError, urllib.error.URLError, ValueError):
            if path.exists() and path.stat().st_size == 0:
                path.unlink()
            continue
        if len(frames) == 5:
            break
    if not frames:
        raise RuntimeError("No nflverse PBP seasons were available locally or from the release URL.")
    return pd.concat(frames, ignore_index=True)


def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").fillna(default) if column in frame else pd.Series(default, index=frame.index)


def build_features(pbp: pd.DataFrame) -> pd.DataFrame:
    """Build play rows with an offense pass rate strictly from prior games."""
    required = {"season", "game_id", "posteam", "play_type", "down", "ydstogo", "yardline_100"}
    missing = required.difference(pbp.columns)
    if missing:
        raise ValueError("PBP is missing columns: {}".format(", ".join(sorted(missing))))
    plays = pbp.copy()
    penalty = _numeric(plays, "penalty")
    plays = plays[plays["play_type"].isin(["run", "pass"]) & (penalty == 0)].copy()
    plays = plays.dropna(subset=["season", "game_id", "posteam", "down", "ydstogo", "yardline_100"])
    if plays.empty:
        return pd.DataFrame(columns=["season", "game_id", "offense_team", "target"] + FEATURE_COLUMNS)
    plays["season"] = pd.to_numeric(plays["season"], errors="coerce").astype(int)
    plays["offense_team"] = plays["posteam"].astype(str)
    plays["target"] = (plays["play_type"] == "pass").astype(int)
    plays["game_day"] = pd.to_datetime(plays.get("game_date"), errors="coerce")
    plays["game_day"] = plays["game_day"].fillna(pd.to_datetime(plays["season"].astype(str) + "-01-01"))
    plays["down"] = _numeric(plays, "down")
    plays["ydstogo"] = _numeric(plays, "ydstogo")
    plays["yardline_100"] = _numeric(plays, "yardline_100")
    plays["quarter"] = _numeric(plays, "qtr")
    plays["half_seconds_remaining"] = _numeric(plays, "half_seconds_remaining")
    plays["game_seconds_remaining"] = _numeric(plays, "game_seconds_remaining")
    plays["score_differential"] = _numeric(plays, "posteam_score") - _numeric(plays, "defteam_score")
    for name in ("posteam_timeouts_remaining", "defteam_timeouts_remaining", "shotgun", "no_huddle"):
        plays[name] = _numeric(plays, name)
    games = (plays.groupby(["season", "game_day", "game_id", "offense_team"], as_index=False)["target"]
             .agg(pass_plays="sum", total_plays="count"))
    games["rate"] = games["pass_plays"] / games["total_plays"]
    games = games.sort_values(["game_day", "season", "game_id", "offense_team"], kind="mergesort")
    prior = {}
    game_rates = {}
    for day, slate in games.groupby("game_day", sort=True):
        pending = []
        for row in slate.itertuples(index=False):
            total, passed = prior.get(row.offense_team, (0, 0))
            game_rates[row.game_id, row.offense_team] = passed / total if total else 0.5
            pending.append((row.offense_team, int(row.total_plays), int(row.pass_plays)))
        for team, count, passed in pending:
            old_total, old_passed = prior.get(team, (0, 0))
            prior[team] = old_total + count, old_passed + passed
    plays["team_asof_pass_rate"] = [game_rates[(game, team)] for game, team in zip(plays.game_id, plays.offense_team)]
    return plays[["season", "game_id", "offense_team", "target"] + FEATURE_COLUMNS].reset_index(drop=True)


def walk_forward(features: pd.DataFrame) -> dict[str, Any]:
    """Evaluate adjacent season folds, retaining the latest three test seasons."""
    seasons = sorted(int(year) for year in features["season"].unique())
    folds = [(year, year + 1) for year in seasons if year + 1 in seasons][-3:]
    reports, pooled = [], {"logistic_regression": [], "hist_gradient_boosting": []}
    for train_season, test_season in folds:
        train, test = features[features.season <= train_season], features[features.season == test_season]
        if train.empty or test.empty or train.target.nunique() < 2:
            continue
        assert int(train.season.max()) < int(test.season.min())
        median = train[FEATURE_COLUMNS].median().fillna(0.0)
        x_train, x_test = train[FEATURE_COLUMNS].fillna(median), test[FEATURE_COLUMNS].fillna(median)
        result: dict[str, Any] = {"train_through_season": train_season, "test_season": test_season, "n": len(test)}
        for name, model in (("logistic_regression", LogisticRegression(max_iter=1000, random_state=0)),
                            ("hist_gradient_boosting", HistGradientBoostingClassifier(random_state=0))):
            model.fit(x_train, train.target)
            probability = model.predict_proba(x_test)[:, 1]
            metrics = {"accuracy": float(accuracy_score(test.target, probability >= 0.5)),
                       "log_loss": float(log_loss(test.target, probability, labels=[0, 1]))}
            result[name] = metrics
            pooled[name].append((test.target.to_numpy(), probability))
        reports.append(result)
    summary = {}
    for name, values in pooled.items():
        if values:
            target, probability = np.concatenate([item[0] for item in values]), np.concatenate([item[1] for item in values])
            accuracy = float(accuracy_score(target, probability >= 0.5))
            summary[name] = {"n": len(target), "accuracy": accuracy, "log_loss": float(log_loss(target, probability, labels=[0, 1])),
                             "published_verdict": "AT/ABOVE" if accuracy >= PUBLISHED_ACCURACY else "BELOW"}
    return {"folds": reports, "pooled": summary}


def render(report: dict[str, Any]) -> str:
    lines = ["NFL RUN/PASS WALK-FORWARD (SITUATION ONLY)", "MODEL | TEST | N | ACCURACY | LOG LOSS", "------|------|---|----------|---------"]
    for fold in report["folds"]:
        for model in ("logistic_regression", "hist_gradient_boosting"):
            metric = fold[model]
            lines.append("{} | {} | {} | {:.4f} | {:.4f}".format(model, fold["test_season"], fold["n"], metric["accuracy"], metric["log_loss"]))
    lines.append("PUBLISHED: Fernandes JQAS 2020 neural net 75.3 pct (team 64.7-82.5); Teich arXiv:1601.00574 about 74-75 pct.")
    for model, metric in report["pooled"].items():
        lines.append("POOLED {}: {:.4f} accuracy, {:.4f} log loss, {} PUBLISHED.".format(model, metric["accuracy"], metric["log_loss"], metric["published_verdict"]))
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate situation-only NFL run/pass prediction.")
    parser.add_argument("--years", type=int, nargs="+")
    parser.add_argument("--output", type=Path, default=Path("data") / "ab_reports" / "nfl_run_pass.json")
    args = parser.parse_args(argv)
    report = walk_forward(build_features(fetch_pbp(args.years)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"features": FEATURE_COLUMNS, "filter": "play_type in {run, pass} and penalty == 0; specials and no-plays excluded.", "published_benchmark": PUBLISHED_ACCURACY, **report}, indent=2) + "\n", encoding="utf-8")
    print(render(report))
    print("REPORT: {}".format(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
