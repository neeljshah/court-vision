"""Leak-free NFL home-win baseline using free nflverse schedule releases.

The public release pattern is
https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet
(replace ``parquet`` with ``csv`` for the CSV asset).  This utility is an
evaluation baseline only; it makes no betting-edge or ROI claim.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
from sklearn.linear_model import LogisticRegression

NFLVERSE_SCHEDULE_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"
)
FEATURE_COLUMNS = [
    "home_win_pct", "away_win_pct", "home_pf_l5", "away_pf_l5",
    "home_pa_l5", "away_pa_l5", "home_rest_days", "away_rest_days", "home_flag",
]


def _data_root() -> Path:
    return Path(os.environ.get("NBA_DATA_ROOT", "data"))


def _read_schedule(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_parquet(path)


def fetch_schedules(years: Iterable[int], local_path: Optional[Path] = None) -> pd.DataFrame:
    """Load selected NFL seasons, downloading once only when no local file exists."""
    path = Path(local_path) if local_path is not None else _data_root() / "nfl" / "schedules.parquet"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(NFLVERSE_SCHEDULE_URL, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(request, timeout=60) as response, path.open("wb") as target:
            shutil.copyfileobj(response, target)
    frame = _read_schedule(path)
    return frame[frame["season"].isin([int(year) for year in years])].copy()


def _team_snapshot(history: List[Dict[str, Any]], day: pd.Timestamp) -> Dict[str, float]:
    if not history:
        return {"win_pct": 0.5, "pf_l5": 21.0, "pa_l5": 21.0, "rest_days": 7.0}
    recent = history[-5:]
    wins = sum(row["win"] for row in history)
    return {
        "win_pct": wins / len(history),
        "pf_l5": sum(row["pf"] for row in recent) / len(recent),
        "pa_l5": sum(row["pa"] for row in recent) / len(recent),
        "rest_days": float(min(30, max(0, (day - history[-1]["day"]).days))),
    }


def build_features(schedules: pd.DataFrame) -> pd.DataFrame:
    """Create game rows whose team features use games strictly before that gameday."""
    required = {"season", "gameday", "home_team", "away_team", "home_score", "away_score"}
    missing = required.difference(schedules.columns)
    if missing:
        raise ValueError("Schedule is missing columns: %s" % ", ".join(sorted(missing)))
    games = schedules.copy()
    games["gameday"] = pd.to_datetime(games["gameday"], errors="coerce")
    games["home_score"] = pd.to_numeric(games["home_score"], errors="coerce")
    games["away_score"] = pd.to_numeric(games["away_score"], errors="coerce")
    games = games.dropna(subset=list(required)).copy()
    games = games.sort_values(["gameday", "season", "home_team", "away_team"], kind="mergesort")
    histories: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    rows: List[Dict[str, Any]] = []
    for _, slate in games.groupby("gameday", sort=True):
        pending: List[tuple[str, float, float, pd.Timestamp]] = []
        for _, game in slate.iterrows():
            home, away, day = str(game.home_team), str(game.away_team), game.gameday
            home_state, away_state = _team_snapshot(histories[home], day), _team_snapshot(histories[away], day)
            if game.home_score != game.away_score:
                row = {"season": int(game.season), "gameday": day.strftime("%Y-%m-%d"),
                       "game_id": str(game.get("game_id", "%s_%s_%s" % (day.date(), home, away))),
                       "home_team": home, "away_team": away,
                       "home_win": int(game.home_score > game.away_score), "home_flag": 1.0}
                for prefix, state in (("home", home_state), ("away", away_state)):
                    for key, value in state.items():
                        row["%s_%s" % (prefix, key)] = value
                rows.append(row)
            pending.extend([(home, float(game.home_score), float(game.away_score), day),
                            (away, float(game.away_score), float(game.home_score), day)])
        for team, points_for, points_against, day in pending:
            histories[team].append({"win": float(points_for > points_against), "pf": points_for,
                                    "pa": points_against, "day": day})
    return pd.DataFrame(rows, columns=["season", "gameday", "game_id", "home_team", "away_team", "home_win"] + FEATURE_COLUMNS)


def _reliability(probabilities: Iterable[float], outcomes: Iterable[int]) -> List[Dict[str, Any]]:
    paired = list(zip(probabilities, outcomes))
    rows: List[Dict[str, Any]] = []
    for index in range(10):
        group = [(probability, outcome) for probability, outcome in paired
                 if min(9, int(probability * 10)) == index]
        count = len(group)
        rows.append({"bin": "%.1f-%.1f" % (index / 10, (index + 1) / 10), "n": count,
                     "mean_predicted": (sum(pair[0] for pair in group) / count if count else None),
                     "observed": (sum(pair[1] for pair in group) / count if count else None)})
    return rows


def walk_forward(features: pd.DataFrame) -> List[Dict[str, Any]]:
    """Evaluate last four available adjacent-season folds without future seasons in training."""
    seasons = sorted(int(value) for value in features["season"].unique())
    folds = [(season, season + 1) for season in seasons if season + 1 in seasons][-4:]
    reports: List[Dict[str, Any]] = []
    for train_season, test_season in folds:
        train = features[features["season"] <= train_season]
        test = features[features["season"] == test_season]
        if train.empty or test.empty or train["home_win"].nunique() < 2:
            continue
        assert int(train["season"].max()) < int(test["season"].min())
        model = LogisticRegression(max_iter=1000, random_state=0)
        model.fit(train[FEATURE_COLUMNS], train["home_win"])
        probability = model.predict_proba(test[FEATURE_COLUMNS])[:, 1]
        outcome = test["home_win"].astype(int).to_numpy()
        reports.append({"train_through_season": train_season, "test_season": test_season,
                        "max_train_season": int(train["season"].max()), "n": len(test),
                        "accuracy": float(((probability >= 0.5) == outcome).mean()),
                        "brier": float(((probability - outcome) ** 2).mean()),
                        "reliability": _reliability(probability, outcome)})
    return reports


def render(reports: List[Dict[str, Any]]) -> str:
    lines = ["NFL GAME-OUTCOME WALK-FORWARD (EVALUATION ONLY)", "TEST | N | ACCURACY | BRIER",
             "-----|---|----------|------"]
    lines += ["%d | %d | %.4f | %.4f" % (row["test_season"], row["n"], row["accuracy"], row["brier"])
              for row in reports]
    lines.append("NO BETTING EDGE OR ROI IS CLAIMED; THIS IS A LEAK-FREE BASELINE EVALUATION.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a leak-free NFL home-win baseline.")
    parser.add_argument("--years", type=int, nargs="+", default=list(range(2018, 2027)))
    parser.add_argument("--local-path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data") / "ab_reports" / "nfl_game_model.json")
    args = parser.parse_args(argv)
    features = build_features(fetch_schedules(args.years, args.local_path))
    reports = walk_forward(features)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"features": FEATURE_COLUMNS, "folds": reports,
                                       "disclaimer": "Evaluation only; no betting edge or ROI is claimed."}, indent=2) + "\n",
                           encoding="utf-8")
    print(render(reports))
    print("REPORT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
