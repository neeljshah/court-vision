"""Report candidate tracking metrics; no novelty or predictive-value claim is made.

These candidate metrics are pending a prior-art gate and prediction-lift
validation. Run with ``python scripts/platformkit/novel_metrics.py``. Inputs
are read from ``NBA_DATA_ROOT/nba`` (or ``./data/nba``), and the report is
written to ``NBA_DATA_ROOT/ab_reports``.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.tracking_features import _minutes_as_float


MIN_GAMES = 30
METRICS = (
    "load_speed_elasticity",
    "load_touch_elasticity",
    "contest_rest_response",
    "b2b_speed_drop",
)
REPORT_HEADER = (
    "CANDIDATE metrics pending prior-art gate + prediction-lift validation; "
    "no novelty claim yet."
)


def _ols(x: pd.Series, y: pd.Series, standardize_x: bool = False) -> tuple[float, float, int]:
    """Return simple OLS slope, R-squared, and complete-observation count."""
    frame = pd.DataFrame({
        "x": pd.to_numeric(x, errors="coerce"),
        "y": pd.to_numeric(y, errors="coerce"),
    }).dropna()
    n = len(frame)
    if n < 2:
        return np.nan, np.nan, n
    values = frame["x"].to_numpy(dtype=float)
    if standardize_x:
        scale = values.std(ddof=0)
        if scale == 0:
            return np.nan, np.nan, n
        values = (values - values.mean()) / scale
    if np.ptp(values) == 0:
        return np.nan, np.nan, n
    target = frame["y"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(values, target, 1)
    fitted = intercept + slope * values
    total = np.square(target - target.mean()).sum()
    r2 = np.nan if total == 0 else 1.0 - np.square(target - fitted).sum() / total
    return float(slope), float(r2), n


def _prepare_games(tracking: pd.DataFrame, state: pd.DataFrame) -> pd.DataFrame:
    """Join raw tracking outcomes to their as-of load state."""
    keys = ["gameId", "personId"]
    required_tracking = set(keys) | {
        "minutes", "speed", "touches", "contestedFieldGoalsAttempted",
        "uncontestedFieldGoalsAttempted",
    }
    required_state = set(keys) | {"cum_distance_7d", "days_rest", "b2b"}
    missing = sorted(required_tracking.difference(tracking.columns))
    missing += sorted(required_state.difference(state.columns))
    if missing:
        raise ValueError("Missing required columns: %s" % ", ".join(missing))
    state_columns = keys + ["cum_distance_7d", "days_rest", "b2b"]
    games = tracking.merge(state[state_columns], on=keys, how="inner", validate="one_to_one")
    minutes = _minutes_as_float(games["minutes"])
    games["touches_per36"] = pd.to_numeric(games["touches"], errors="coerce").div(
        minutes.replace(0, np.nan)
    ).mul(36.0)
    contested = pd.to_numeric(games["contestedFieldGoalsAttempted"], errors="coerce")
    uncontested = pd.to_numeric(games["uncontestedFieldGoalsAttempted"], errors="coerce")
    games["contested_fga_share"] = contested.div((contested + uncontested).replace(0, np.nan))
    games["speed"] = pd.to_numeric(games["speed"], errors="coerce")
    return games


def compute_novel_metrics(tracking: pd.DataFrame, state: pd.DataFrame) -> pd.DataFrame:
    """Compute candidate per-player tracking metrics for players with 30+ games."""
    games = _prepare_games(tracking, state)
    records: list[dict[str, object]] = []
    for player, player_games in games.groupby("personId", sort=True):
        if len(player_games) < MIN_GAMES:
            continue
        for metric, x, y, standardized in (
            ("load_speed_elasticity", "cum_distance_7d", "speed", True),
            ("load_touch_elasticity", "cum_distance_7d", "touches_per36", True),
            ("contest_rest_response", "days_rest", "contested_fga_share", False),
        ):
            value, r2, n = _ols(player_games[x], player_games[y], standardized)
            records.append({"player": player, "metric": metric, "value": value, "r2": r2, "n": n})
        b2b = player_games.loc[player_games["b2b"].fillna(False).astype(bool), "speed"].dropna()
        rested = player_games.loc[player_games["days_rest"].ge(2), "speed"].dropna()
        value = np.nan if not len(b2b) or not len(rested) else float(b2b.mean() - rested.mean())
        records.append({"player": player, "metric": "b2b_speed_drop", "value": value,
                        "r2": np.nan, "n": int(len(b2b) + len(rested))})
    return pd.DataFrame(records, columns=["player", "metric", "value", "r2", "n"])


def render_report(metrics: pd.DataFrame) -> str:
    """Render ASCII rankings and league summaries for console output."""
    lines = [REPORT_HEADER]
    for metric in METRICS:
        subset = metrics.loc[metrics["metric"].eq(metric)].dropna(subset=["value"])
        lines.append("\n%s" % metric)
        lines.append("BOTTOM 10")
        lines.append(subset.nsmallest(10, "value").to_string(index=False, float_format="%.4f"))
        lines.append("TOP 10")
        lines.append(subset.nlargest(10, "value").to_string(index=False, float_format="%.4f"))
        if metric.startswith("load_"):
            lines.append("SUMMARY negative_share=%.4f median=%.4f" % (
                (subset["value"] < 0).mean() if len(subset) else np.nan,
                subset["value"].median() if len(subset) else np.nan,
            ))
    return "\n".join(lines)


def main() -> None:
    """Write the candidate-metrics parquet and print its ASCII report."""
    data_root = Path(os.environ.get("NBA_DATA_ROOT", "data"))
    nba_dir = data_root / "nba"
    metrics = compute_novel_metrics(
        pd.read_parquet(nba_dir / "player_tracking_games.parquet"),
        pd.read_parquet(nba_dir / "player_load_state_asof.parquet"),
    )
    output = data_root / "ab_reports" / "novel_metrics_players.parquet"
    output.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_parquet(output, index=False)
    print(render_report(metrics))
    print("Wrote %d rows to %s" % (len(metrics), output))


if __name__ == "__main__":
    main()
