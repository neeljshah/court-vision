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
OUT_RELATIVE_PATH = Path("scripts/platformkit/analytics_showcase/out/market_strength_atlas.json")
SPORTS = ("basketball_nba", "mlb", "soccer", "tennis")
REQUIRED = {"date", "home_team", "away_team", "home_ml", "away_ml"}
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


def odds_format(value: float) -> str:
    """Classify an accepted moneyline using the same rule as decimal_odds."""
    value = float(value)
    if not np.isfinite(value) or value == 0:
        return "invalid"
    if abs(value) >= 100:
        return "american"
    if value > 1.0:
        return "decimal"
    return "invalid"


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


def adapt_source(sport: str, source: pd.DataFrame) -> tuple[pd.DataFrame | None, str | None]:
    """Map explicit two-sided market schemas to the atlas's canonical columns."""
    if REQUIRED.issubset(source.columns):
        return source.copy(), None
    if sport == "mlb":
        pattern = r"^\d{8}-(?P<home_team>[^-]+)-(?P<away_team>[^-]+)-\d+$"
        needed = {"event_id", "date", "ml_close_home_am", "ml_close_away_am"}
        teams = source["event_id"].astype(str).str.extract(pattern) if "event_id" in source else pd.DataFrame()
        if needed.issubset(source.columns) and teams.notna().all().all():
            return pd.DataFrame({
                "date": source["date"], "home_team": teams["home_team"], "away_team": teams["away_team"],
                "home_ml": source["ml_close_home_am"], "away_ml": source["ml_close_away_am"],
            }), None
        return None, "MLB event_id or closing-moneyline mapping is incomplete."
    if sport == "tennis":
        pattern = r"^.+-(?P<home_team>\d+)-(?P<away_team>\d+)-\d+$"
        needed = {"event_id", "date_td", "ps_p1", "ps_p2"}
        players = source["event_id"].astype(str).str.extract(pattern) if "event_id" in source else pd.DataFrame()
        if needed.issubset(source.columns) and players.notna().all().all():
            return pd.DataFrame({
                "date": source["date_td"], "home_team": "player_" + players["home_team"],
                "away_team": "player_" + players["away_team"], "home_ml": source["ps_p1"],
                "away_ml": source["ps_p2"],
            }), None
        return None, "Tennis event_id or paired Pinnacle player-price mapping is incomplete."
    return None, "Soccer source has over/under prices only; no two-sided match-result market is available."


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
        shift = k * (close_p - model_p)
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


def _distribution(records: list[dict], key: str) -> dict[str, float]:
    values = np.array([float(record[key]) for record in records])
    return {"mean": round(float(np.mean(values)), 6), "p10": round(float(np.quantile(values, 0.1)), 6),
            "p90": round(float(np.quantile(values, 0.9)), 6)}


def _moneyline_sample(games: pd.DataFrame) -> list[dict[str, float | str]]:
    sample = []
    for row in games[["home_ml", "away_ml"]].head(5).itertuples(index=False):
        home, away = float(row.home_ml), float(row.away_ml)
        sample.append({"home_ml": home, "away_ml": away, "home_ml_format": odds_format(home),
                       "away_ml_format": odds_format(away)})
    return sample


def analyze_games(games: pd.DataFrame, sport: str) -> dict:
    train, evaluation = _split_by_date(games)
    k, hfa = choose_grid(train)
    _, train_ratings, _ = walk_forward(train, k, hfa)
    records, final_ratings, bands = walk_forward(evaluation, k, hfa, train_ratings)
    error = float(np.mean([abs(r["p_model"] - r["p_close"]) for r in records]))
    teams = sorted(final_ratings, key=final_ratings.get, reverse=True)
    training_spread = max(train_ratings.values()) - min(train_ratings.values())

    def entry(team: str) -> dict:
        return {"team": team, "rating": round(final_ratings[team], 3),
                "uncertainty_band_exploratory": round(bands.get(team, 0.0), 4)}

    latest_ratings = {"top_5": [entry(t) for t in teams[:5]], "bottom_5": [entry(t) for t in teams[-5:][::-1]]}
    distributions = {"p_model": _distribution(records, "p_model"), "p_close": _distribution(records, "p_close")}
    print(f"TRAINING_RATING_SPREAD {sport}: {training_spread:.3f}")
    print(f"EVAL_DISTRIBUTION {sport}: " + json.dumps(distributions, ensure_ascii=True))
    return {
        "as_of": evaluation["date"].max().date().isoformat(),
        "n_train": int(len(train)), "n_eval": int(len(evaluation)),
        "chosen_k": k, "chosen_hfa": hfa,
        "training_rating_spread": round(float(training_spread), 3),
        "latest_ratings": latest_ratings,
        "top_5": latest_ratings["top_5"], "bottom_5": latest_ratings["bottom_5"],
        "eval_scores": {
            "mean_absolute_tracking_error": round(error, 6),
            "probability_distribution": distributions,
            "outcome_join": "NONE",
            "outcome_note": "Existing showcase joins are incompatible with this two-sided home-moneyline grain; tracking-to-close only.",
        },
        "cross_book_context": "SKIPPED: no cheap schema-stable multi-book join was used.",
        "verdict": "Descriptive close-tracking summary only; no outcome or edge inference is made.",
    }


def analyze_sport(sport: str, repo: Path) -> dict:
    path = repo / "data" / "domains" / sport / "odds.parquet"
    if not path.exists():
        print(f"SKIP {sport}: missing {path.relative_to(repo)}")
        return {"status": "skipped", "as_of": None, "note": "odds parquet is absent",
                "verdict": "SKIPPED: required odds parquet is absent."}
    source = pd.read_parquet(path)
    source_columns = list(map(str, source.columns))
    print(f"SCHEMA {sport}: {', '.join(source_columns)}")
    adapted, note = adapt_source(sport, source)
    if adapted is None:
        print(f"SKIP {sport}: {note}")
        return {"status": "skipped", "as_of": None, "note": note, "source_columns": source_columns,
                "verdict": "SKIPPED: no unambiguous two-sided market mapping is available."}
    sample = _moneyline_sample(adapted)
    print(f"ODDS_SAMPLE {sport}: " + json.dumps(sample, ensure_ascii=True))
    try:
        result = analyze_games(prepare_games(adapted), sport)
    except ValueError as exc:
        print(f"SKIP {sport}: {exc}")
        return {"status": "skipped", "as_of": None, "note": str(exc),
                "verdict": "SKIPPED: no usable first-half and evaluation-half split."}
    result.update(status="ok", source=str(path.relative_to(repo)).replace("\\", "/"),
                  source_columns=source_columns, moneyline_sample=sample)
    return result


def build(repo: Path | None = None) -> dict:
    """Build the artifact without consuming any realized game result."""
    return {
        "label": "DESCRIPTIVE_ONLY", "descriptive_only": True, "edge_claimed": False,
        "as_of": "latest accepted game date per sport",
        "method": "Devig two-sided closing moneylines, fit ratings to close probability, select K/HFA on first half, then freeze for second-half walk-forward scoring.",
        "rating_update": "R_home += K*(p_close-p_model); R_away -= K*(p_close-p_model); no result enters rating updates.",
        "uncertainty": "EXPLORATORY: team band is rolling standard deviation of its last ten absolute close-tracking residuals.",
        "sports": {sport: analyze_sport(sport, repo or REPO) for sport in SPORTS},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> dict:
    repo = Path.cwd()
    result = build(repo)
    out_json = repo / OUT_RELATIVE_PATH
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    return result


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = main()
    print(f"wrote {Path.cwd() / OUT_RELATIVE_PATH}")
    print(json.dumps({s: r["status"] for s, r in result["sports"].items()}, ensure_ascii=True))
