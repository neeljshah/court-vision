"""Leak-safe NBA crew and MLB plate-umpire officiating priors.

This module deliberately requires a timestamped assignment snapshot. A post-game
officials table cannot be used at runtime, even when it can support training.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


OUTPUT_COLUMNS = (
    "crew_foul_rate_prior",
    "umpire_strike_zone_prior",
    "runtime_available",
)
DEFAULT_PATHS = {
    "games": Path("data/cache/officials/games.csv"),
    "nba_assignments": Path("data/cache/officials/nba_crew_assignments.csv"),
    "nba_logs": Path("data/cache/officials/nba_crew_game_logs.csv"),
    "mlb_assignments": Path("data/cache/statcast/mlb_umpire_assignments.csv"),
    "pitches": Path("data/cache/statcast/called_strikes.csv"),
}


def _time_column(frame: pd.DataFrame, choices: tuple[str, ...]) -> str:
    for name in choices:
        if name in frame:
            return name
    raise ValueError("missing one of: {}".format(", ".join(choices)))


def _require(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [name for name in columns if name not in frame]
    if missing:
        raise ValueError("missing columns: {}".format(", ".join(missing)))


def _eligible_assignments(
    games: pd.DataFrame, assignments: pd.DataFrame, official_column: str
) -> pd.DataFrame:
    """Select the latest assignment snapshot at or before each decision horizon."""
    _require(games, ("game_id", "sport"))
    _require(assignments, ("game_id", official_column, "captured_at"))
    horizon = _time_column(games, ("decision_horizon", "as_of_time", "prediction_time"))
    left = games[["game_id", "sport", horizon]].copy()
    left["_horizon"] = pd.to_datetime(left[horizon], errors="coerce", utc=True)
    right = assignments[["game_id", official_column, "captured_at"]].copy()
    right["_captured"] = pd.to_datetime(right["captured_at"], errors="coerce", utc=True)
    joined = left.merge(right, on="game_id", how="left")
    eligible = joined[joined["_captured"].notna() & (joined["_captured"] < joined["_horizon"])]
    eligible = eligible.sort_values(["game_id", "_captured"], kind="mergesort")
    selected = eligible.drop_duplicates("game_id", keep="last")
    return selected[["game_id", official_column]].assign(runtime_available=True)


def _prior_by_official(
    games: pd.DataFrame, history: pd.DataFrame, official_column: str, value_column: str
) -> pd.Series:
    """Return strict-prior expanding means, excluding same-date games too."""
    _require(games, ("game_id", "game_date"))
    _require(history, ("game_id", "game_date", official_column, value_column))
    target_dates = pd.to_datetime(games["game_date"], errors="coerce")
    records: list[float] = []
    for official, game_date, game_id in games[[official_column, "game_date", "game_id"]].itertuples(index=False):
        date = pd.to_datetime(game_date, errors="coerce")
        prior = history[
            (history[official_column] == official)
            & (pd.to_datetime(history["game_date"], errors="coerce") < date)
            & (history["game_id"] != game_id)
        ][value_column]
        records.append(float(prior.mean()) if len(prior) else float("nan"))
    return pd.Series(records, index=games.index, dtype="float64")


def fit_expected_called_strike(pitches: pd.DataFrame) -> pd.DataFrame:
    """Score pitches with an expectation fitted exclusively on earlier seasons."""
    _require(pitches, ("game_id", "pitch_date", "season", "umpire_id", "called_strike"))
    scored = pitches.copy()
    scored["pitch_date"] = pd.to_datetime(scored["pitch_date"], errors="coerce")
    scored["season"] = pd.to_numeric(scored["season"], errors="coerce")
    scored["called_strike"] = pd.to_numeric(scored["called_strike"], errors="coerce")
    keys = [name for name in ("balls", "strikes", "zone") if name in scored]
    scored["expected_called_strike"] = np.nan
    scored["fit_window_date"] = pd.NaT
    for season in sorted(scored["season"].dropna().unique()):
        mask = scored["season"] == season
        fit = scored[scored["season"] < season].dropna(subset=["called_strike", "pitch_date"])
        if fit.empty:
            continue
        scored_dates = scored.loc[mask, "pitch_date"].dropna()
        if not scored_dates.empty and not (fit["pitch_date"].max() < scored_dates.min()):
            raise AssertionError("expectation fit window is not strictly prior to scored season")
        fallback = float(fit["called_strike"].mean())
        if keys:
            rates = fit.groupby(keys, dropna=False)["called_strike"].mean()
            index = pd.MultiIndex.from_frame(scored.loc[mask, keys])
            expected = rates.reindex(index).to_numpy(dtype="float64")
            expected = np.where(np.isnan(expected), fallback, expected)
        else:
            expected = np.full(int(mask.sum()), fallback)
        scored.loc[mask, "expected_called_strike"] = expected
        scored.loc[mask, "fit_window_date"] = fit["pitch_date"].max()
    return scored


def build_officiating_priors(
    games: pd.DataFrame,
    nba_assignments: pd.DataFrame,
    nba_logs: pd.DataFrame,
    mlb_assignments: pd.DataFrame,
    pitches: pd.DataFrame,
) -> pd.DataFrame:
    """Build the three declared columns from timestamped snapshots and prior logs."""
    _require(games, ("game_id", "game_date", "sport"))
    out = games[["game_id"]].copy()
    out["crew_foul_rate_prior"] = np.nan
    out["umpire_strike_zone_prior"] = np.nan
    out["runtime_available"] = False

    nba = games[games["sport"].str.upper().eq("NBA")].copy()
    if not nba.empty:
        nba["_row_index"] = nba.index
        selected = _eligible_assignments(nba, nba_assignments, "crew_id")
        nba = nba.merge(selected, on="game_id", how="left")
        _require(nba_logs, ("game_id", "game_date", "crew_id", "fouls", "free_throw_attempts"))
        logs = nba_logs.copy()
        minutes = pd.to_numeric(logs.get("minutes", 48.0), errors="coerce")
        logs["_crew_rate"] = 48.0 * (
            pd.to_numeric(logs["fouls"], errors="coerce")
            + pd.to_numeric(logs["free_throw_attempts"], errors="coerce")
        ) / minutes
        nba["crew_foul_rate_prior"] = _prior_by_official(nba, logs, "crew_id", "_crew_rate")
        indices = nba["_row_index"].to_numpy()
        out.loc[indices, "crew_foul_rate_prior"] = nba["crew_foul_rate_prior"].to_numpy()
        out.loc[indices, "runtime_available"] = nba["runtime_available"].eq(True).to_numpy()

    mlb = games[games["sport"].str.upper().eq("MLB")].copy()
    if not mlb.empty:
        mlb["_row_index"] = mlb.index
        selected = _eligible_assignments(mlb, mlb_assignments, "umpire_id")
        mlb = mlb.merge(selected, on="game_id", how="left")
        scored = fit_expected_called_strike(pitches)
        scored["_residual"] = scored["called_strike"] - scored["expected_called_strike"]
        game_residual = scored.groupby(["game_id", "umpire_id"], as_index=False).agg(
            game_date=("pitch_date", "min"), _residual=("_residual", "mean")
        )
        mlb["umpire_strike_zone_prior"] = _prior_by_official(
            mlb, game_residual, "umpire_id", "_residual"
        )
        indices = mlb["_row_index"].to_numpy()
        out.loc[indices, "umpire_strike_zone_prior"] = mlb["umpire_strike_zone_prior"].to_numpy()
        out.loc[indices, "runtime_available"] = mlb["runtime_available"].eq(True).to_numpy()
    return out[list(OUTPUT_COLUMNS)]


def report_runtime_availability(frame: pd.DataFrame) -> str:
    """Return the ASCII runtime availability report required by the queue."""
    fraction = float(frame["runtime_available"].mean()) if len(frame) else 0.0
    return "runtime_available_fraction={:.6f}".format(fraction)


def main() -> int:
    """Load local files, or fail closed without attempting a network fetch."""
    parser = argparse.ArgumentParser()
    for name, path in DEFAULT_PATHS.items():
        parser.add_argument("--{}".format(name.replace("_", "-")), default=str(path))
    args = parser.parse_args()
    paths = {name: Path(getattr(args, name)) for name in DEFAULT_PATHS}
    missing = [path for path in paths.values() if not path.is_file()]
    if missing:
        for path in missing:
            print("UNAVAILABLE missing_path={}".format(path))
        return 0
    frame = build_officiating_priors(*(pd.read_csv(paths[name]) for name in DEFAULT_PATHS))
    print(report_runtime_availability(frame))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
