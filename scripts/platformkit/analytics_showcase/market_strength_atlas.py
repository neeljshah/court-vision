"""Descriptive market-implied team-strength atlas; no outcome-rating update."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
REPO = HERE.parents[2]
OUT_JSON = HERE / "out" / "market_strength_atlas.json"
SPORTS = ("basketball_nba", "mlb", "soccer", "tennis")
REQUIRED = {"date", "home_team", "away_team", "home_ml", "away_ml", "total", "spread"}
GRID = tuple((k, hfa) for k in (8, 16, 32) for hfa in (0, 40, 80))


def decimal_odds(value: float) -> float:
    """Convert either American or decimal odds into decimal odds."""
    value = float(value)
    if not np.isfinite(value) or value == 0:
        raise ValueError("odds must be finite and nonzero")
    if abs(value) >= 100:
        return 1.0 + (value / 100.0 if value > 0 else 100.0 / abs(value))
    if value <= 1.0:
        raise ValueError("decimal odds must exceed one")
    return value


def devig(home_odds: float, away_odds: float) -> tuple[float, float]:
    """Return proportional-devigged home and away probabilities."""
    home_raw, away_raw = 1.0 / decimal_odds(home_odds), 1.0 / decimal_odds(away_odds)
    total = home_raw + away_raw
    return home_raw / total, away_raw / total


def elo_probability(home_rating: float, away_rating: float, hfa: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-((home_rating - away_rating + hfa) / 400.0)))


def prepare_games(df: pd.DataFrame) -> pd.DataFrame:
    """Validate an expected two-sided moneyline schema and add p_close."""
    needed = REQUIRED - set(df.columns)
    if needed:
        raise ValueError("missing columns: " + ", ".join(sorted(needed)))
    games = df.copy()
    games["date"] = pd.to_datetime(games["date"], errors="coerce", utc=True)
    games = games.dropna(subset=["date", "home_team", "away_team", "home_ml", "away_ml"])
    rows = []
    for home, away in games[["home_ml", "away_ml"]].itertuples(index=False, name=None):
        try:
            rows.append(devig(home, away)[0])
        except (TypeError, ValueError):
            rows.append(np.nan)
    games["p_close"] = rows
    games = games.dropna(subset=["p_close"])
    return games.sort_values(["date", "home_team", "away_team"], kind="mergesort").reset_index(drop=True)


def walk_forward(games: pd.DataFrame, k: int, hfa: int, ratings: dict[str, float] | None = None) -> tuple[list[dict], dict[str, float], dict[str, float]]:
    """Predict before each market-line update, then update ratings toward p_close."""
    ratings = dict(ratings or {})
    residuals: dict[str, list[float]] = defaultdict(list)
    records = []
    for row in games.itertuples(index=False):
        home, away = str(row.home_team), str(row.away_team)
        rh, ra = ratings.get(home, 1500.0), ratings.get(away, 1500.0)
        model_p = elo_probability(rh, ra, hfa)
        close_p = float(row.p_close)
        residual = abs(close_p - model_p)
        records.append({"date": row.date, "home": home, "away": away, "p_model": model_p, "p_close": close_p})
        shift = k * 400.0 * (close_p - model_p)
        ratings[home], ratings[away] = rh + shift, ra - shift
        residuals[home].append(residual)
        residuals[away].append(residual)
    bands = {team: float(np.std(values[-10:])) for team, values in residuals.items()}
    return records, ratings, bands


def choose_grid(train: pd.DataFrame) -> tuple[int, int]:
    """Use only first-half games to minimize in-window close tracking error."""
    scored = []
    for k, hfa in GRID:
        records, _, _ = walk_forward(train, k, hfa)
        error = float(np.mean([abs(r["p_model"] - r["p_close"]) for r in records]))
        scored.append((error, k, hfa))
    _, k, hfa = min(scored)
    return k, hfa


def _split_by_date(games: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(games["date"].unique())
    if len(dates) < 2:
        raise ValueError("fewer than two distinct game dates")
    train_dates = set(dates[: len(dates) // 2])
    return games[games["date"].isin(train_dates)], games[~games["date"].isin(train_dates)]


def analyze_games(games: pd.DataFrame) -> dict:
    train, evaluation = _split_by_date(games)
    k, hfa = choose_grid(train)
    _, train_ratings, _ = walk_forward(train, k, hfa)
    records, final_ratings, bands = walk_forward(evaluation, k, hfa, train_ratings)
    error = float(np.mean([abs(r["p_model"] - r["p_close"]) for r in records]))
    teams = sorted(final_ratings, key=final_ratings.get, reverse=True)

    def entry(team: str) -> dict:
        return {"team": team, "rating": round(final_ratings[team], 3),
                "uncertainty_band_exploratory": round(bands.get(team, 0.0), 4)}

    return {
        "as_of": evaluation["date"].max().date().isoformat(),
        "n_train": int(len(train)), "n_eval": int(len(evaluation)),
        "chosen_k": k, "chosen_hfa": hfa,
        "top_5": [entry(t) for t in teams[:5]], "bottom_5": [entry(t) for t in teams[-5:][::-1]],
        "eval_scores": {
            "mean_absolute_tracking_error": round(error, 6),
            "outcome_join": "NONE",
            "outcome_note": "Existing showcase joins are incompatible with this two-sided home-moneyline grain; tracking-to-close only.",
        },
        "cross_book_context": "SKIPPED: no cheap schema-stable multi-book join was used.",
        "verdict": "The compressed rating state tracks the devigged close imperfectly and is expected to trail or match it.",
    }


def analyze_sport(sport: str) -> dict:
    path = REPO / "data" / "domains" / sport / "odds.parquet"
    if not path.exists():
        print(f"SKIP {sport}: missing {path.relative_to(REPO)}")
        return {"status": "skipped", "as_of": None, "note": "odds parquet is absent",
                "verdict": "SKIPPED: required odds parquet is absent."}
    source = pd.read_parquet(path)
    missing = sorted(REQUIRED - set(source.columns))
    if missing:
        print(f"SKIP {sport}: schema differs; missing {', '.join(missing)}")
        return {"status": "skipped", "as_of": None, "note": "schema differs", "missing_columns": missing,
                "verdict": "SKIPPED: required two-sided moneyline schema differs."}
    try:
        result = analyze_games(prepare_games(source))
    except ValueError as exc:
        print(f"SKIP {sport}: {exc}")
        return {"status": "skipped", "as_of": None, "note": str(exc),
                "verdict": "SKIPPED: no usable first-half and evaluation-half split."}
    result.update(status="ok", source=str(path.relative_to(REPO)).replace("\\", "/"))
    return result


def build() -> dict:
    """Build the artifact without consuming any realized game result."""
    return {
        "label": "DESCRIPTIVE_ONLY", "descriptive_only": True, "edge_claimed": False,
        "as_of": "latest accepted game date per sport",
        "method": "Devig two-sided closing moneylines, fit ratings to close probability, select K/HFA on first half, then freeze for second-half walk-forward scoring.",
        "rating_update": "R_home += K*400*(p_close-p_model); R_away -= K*400*(p_close-p_model); no result enters rating updates.",
        "uncertainty": "EXPLORATORY: team band is rolling standard deviation of its last ten absolute close-tracking residuals.",
        "sports": {sport: analyze_sport(sport) for sport in SPORTS},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> dict:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    return result


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = main()
    print(f"wrote {OUT_JSON}")
    print(json.dumps({s: r["status"] for s, r in result["sports"].items()}, ensure_ascii=True))
