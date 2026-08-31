"""Local-first NBA team-game PBP/boxscore as-of feature builder.

Only fields present in local game-level inputs are used.  It never fills missing
statistics from season aggregates, because that would not be a game as-of value.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

KEYS = ["game_id", "game_date", "team_id", "opponent_id"]
STAT_ALIASES = {
    "game_id": ("game_id", "gameId", "GAME_ID"),
    "game_date": ("game_date", "gameDate", "GAME_DATE", "date"),
    "team_id": ("team_id", "teamId", "TEAM_ID", "team"),
    "opponent_id": ("opponent_id", "opponentId", "OPPONENT_ID", "opponent"),
    "fga": ("fga", "FGA"), "fta": ("fta", "FTA"), "orb": ("orb", "OREB", "oreb"),
    "tov": ("tov", "TOV", "turnovers"), "stl": ("stl", "STL", "steals"),
}


def estimate_possessions(fga: float, fta: float, orb: float, tov: float) -> float:
    """Return the Oliver boxscore possession estimate: FGA + .4*FTA - ORB + TOV."""
    return float(fga) + 0.4 * float(fta) - float(orb) + float(tov)


def _first(record: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in record:
            return record[name]
    return None


def _normalise_records(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for record in records:
        if not isinstance(record, dict):
            continue
        row = {name: _first(record, aliases) for name, aliases in STAT_ALIASES.items()}
        if row["game_id"] is not None and row["team_id"] is not None:
            rows.append(row)
    return pd.DataFrame(rows, columns=list(STAT_ALIASES))


def _json_records(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("team_games", "games", "data", "rows", "resultSets"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [data]
    return []


def discover_team_games(data_root: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Find canonical-like local team-game files without treating aggregates as games."""
    nba_dir = data_root / "nba"
    files = list(nba_dir.rglob("*.parquet")) + list(nba_dir.rglob("*.json")) if nba_dir.exists() else []
    files = [path for path in files if path.name != "team_pbp_features_asof.parquet"]
    counts = {"pbp_files": 0, "parquet_files": 0, "json": 0, "boxscore_json": 0,
              "game_rows": 0, "aggregate_json": 0}
    frames = []
    for path in files:
        lower_name = path.name.lower()
        is_pbp = any(token in lower_name for token in ("pbp", "play_by_play", "play-by-play", "playbyplay"))
        if is_pbp:
            counts["pbp_files"] += 1
        if path.suffix.lower() == ".parquet":
            counts["parquet_files"] += 1
        if path.suffix.lower() == ".json":
            counts["json"] += 1
            counts["boxscore_json"] += int("boxscore" in lower_name or "box_score" in lower_name)
            frame = _normalise_records(_json_records(path))
        else:
            try:
                frame = _normalise_records(pd.read_parquet(path).to_dict("records"))
            except (ImportError, OSError, ValueError):
                frame = pd.DataFrame(columns=list(STAT_ALIASES))
        if frame.empty:
            if path.suffix.lower() == ".json":
                counts["aggregate_json"] += 1
            continue
        counts["game_rows"] += len(frame)
        frames.append(frame)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=list(STAT_ALIASES))), counts


def build_asof_features(team_games: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, bool]]:
    """Build prior-only L5 pace, rest, B2B, and optional steal-rate features."""
    missing = set(KEYS).difference(team_games.columns)
    if missing:
        raise ValueError("Team-game input is missing keys: %s" % ", ".join(sorted(missing)))
    frame = team_games.copy()
    frame["game_date"] = pd.to_datetime(frame["game_date"], errors="coerce")
    frame = frame.dropna(subset=KEYS).sort_values(["game_date", "game_id", "team_id"], kind="mergesort")
    stats = {column: column in frame.columns and frame[column].notna().any()
             for column in ("fga", "fta", "orb", "tov", "stl")}
    available = {"pace_proxy": all(stats[name] for name in ("fga", "fta", "orb", "tov")),
                 "transition_proxy": stats["stl"] and all(stats[name] for name in ("fga", "fta", "orb", "tov")),
                 "rest_days": True, "b2b": True}
    for name in ("fga", "fta", "orb", "tov", "stl"):
        if name in frame:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
    if available["pace_proxy"]:
        frame["pace_proxy"] = frame["fga"] + 0.4 * frame["fta"] - frame["orb"] + frame["tov"]
        frame["pace_l5_asof"] = frame.groupby("team_id", sort=False)["pace_proxy"].transform(
            lambda values: values.shift(1).rolling(5, min_periods=1).mean())
    prior_date = frame.groupby("team_id", sort=False)["game_date"].shift(1)
    frame["rest_days_asof"] = (frame["game_date"] - prior_date).dt.days.astype("float64")
    frame["b2b_asof"] = (frame["rest_days_asof"] == 1).astype("Int64")
    frame.loc[prior_date.isna(), "b2b_asof"] = pd.NA
    if available["transition_proxy"]:
        frame["transition_proxy"] = 100.0 * frame["stl"] / frame["pace_proxy"]
        frame["transition_proxy_l5_asof"] = frame.groupby("team_id", sort=False)["transition_proxy"].transform(
            lambda values: values.shift(1).rolling(5, min_periods=1).mean())
    frame["game_date"] = frame["game_date"].dt.strftime("%Y-%m-%d")
    columns = KEYS + [name for name in ("pace_proxy", "pace_l5_asof", "rest_days_asof", "b2b_asof",
                                        "transition_proxy", "transition_proxy_l5_asof") if name in frame]
    return frame[columns].reset_index(drop=True), available


def render_summary(counts: dict[str, int], available: dict[str, bool], output: Path, rows: int) -> str:
    """Render an ASCII discovery report with explicit unsupported-feature status."""
    lines = ["NBA PBP FEATURE DISCOVERY", "DATA ROOT: %s" % output.parent.parent,
             "PBP_FILES: %d" % counts["pbp_files"],
             "PARQUET_FILES: %d" % counts["parquet_files"],
             "JSON_FILES: %d" % counts["json"], "USABLE_TEAM_GAME_ROWS: %d" % counts["game_rows"]]
    lines.insert(5, "BOXSCORE_JSON_FILES: %d" % counts["boxscore_json"])
    for label, name in (("PACE_PROXY", "pace_proxy"), ("L5_PACE", "pace_proxy"),
                        ("REST_DAYS", "rest_days"), ("B2B", "b2b"),
                        ("TRANSITION_PROXY", "transition_proxy")):
        lines.append("%s: %s" % (label, "AVAILABLE" if available.get(name) else "UNAVAILABLE"))
    lines += ["OUTPUT_ROWS: %d" % rows, "OUTPUT: %s" % output]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build local NBA PBP/boxscore as-of team features.")
    parser.add_argument("--data-root", type=Path, default=Path(os.environ.get("NBA_DATA_ROOT", "data")))
    args = parser.parse_args(argv)
    output = args.data_root / "nba" / "team_pbp_features_asof.parquet"
    games, counts = discover_team_games(args.data_root)
    if games.empty:
        features = pd.DataFrame(columns=KEYS + ["rest_days_asof", "b2b_asof"])
        available = {"pace_proxy": False, "rest_days": False, "b2b": False, "transition_proxy": False}
    else:
        features, available = build_asof_features(games)
    output.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output, index=False)
    print(render_summary(counts, available, output, len(features)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
