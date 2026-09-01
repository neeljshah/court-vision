"""Measure liveness and identity discontinuities in tracking CSVs.

This is a read-only corpus audit.  It intentionally uses the raw pixel-space
``x_position``/``y_position`` columns because those are the fields written by
the production tracking pipeline.

Run from the repository root, for example:
``python -m scripts.platformkit.audit_nba_tracking_liveness --root C:/.../data/tracking``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


KNOWN_GAMES = ("0022500047", "0022500002", "0022401185", "0022400923", "0022500068")
USE_COLUMNS = (
    "frame", "timestamp", "player_id", "team", "x_position", "y_position",
    "player_name", "team_abbrev", "possession_id", "scoreboard_period",
)
TELEPORT_DISTANCE = 50.0


def _columns(path: Path) -> list[str]:
    header = pd.read_csv(path, nrows=0).columns
    return [name for name in USE_COLUMNS if name in header]


def _pct(values: pd.Series) -> float | None:
    values = values.dropna()
    return None if len(values) == 0 else float(values.mean())


def _number(value: float) -> float | None:
    return float(value) if pd.notna(value) else None


def audit_game(path: Path) -> dict[str, object]:
    """Return raw-position liveness and discontinuity measures for one game."""
    data = pd.read_csv(path, usecols=_columns(path), low_memory=False)
    required = {"frame", "player_id", "x_position", "y_position"}
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError("%s missing %s" % (path, ", ".join(missing)))
    input_rows = len(data)
    for name in ("frame", "player_id", "x_position", "y_position"):
        data[name] = pd.to_numeric(data[name], errors="coerce")
    data = data.dropna(subset=list(required)).copy()
    data = data.sort_values(["player_id", "frame"], kind="mergesort").reset_index(drop=True)
    grouped = data.groupby("player_id", sort=False)
    previous = grouped[["x_position", "y_position", "frame"]].shift()
    data["step"] = np.hypot(data["x_position"] - previous["x_position"],
                             data["y_position"] - previous["y_position"])
    data["frame_gap"] = data["frame"] - previous["frame"]
    steps = data.loc[data["step"].notna()].copy()
    identity_columns = [name for name in ("player_name", "team", "team_abbrev") if name in data]
    identity_change = pd.Series(False, index=data.index)
    for name in identity_columns:
        prior = grouped[name].shift()
        identity_change |= data[name].notna() & prior.notna() & data[name].ne(prior)
    steps["identity_change"] = identity_change.loc[steps.index]
    boundary = pd.Series(False, index=data.index)
    for name in ("possession_id", "scoreboard_period"):
        if name in data:
            prior = grouped[name].shift()
            boundary |= data[name].notna() & prior.notna() & data[name].ne(prior)
    steps["boundary"] = boundary.loc[steps.index]
    teleports = steps.loc[steps["step"] >= TELEPORT_DISTANCE]
    per_player = data.groupby("player_id", sort=False).size().sort_values(ascending=False)
    top_id = per_player.index[0]
    top = steps.loc[steps["player_id"].eq(top_id), "step"]
    fractions = (data[["x_position", "y_position"]] % 1.0).abs().lt(1e-9)
    return {
        "game_id": path.parent.name,
        "input_rows": int(input_rows),
        "malformed_required_row_count": int(input_rows - len(data)),
        "rows": int(len(data)),
        "step_count": int(len(steps)),
        "zero_step_share": _pct(steps["step"].eq(0.0)),
        "distinct_position_ratio": float(len(data.drop_duplicates(["x_position", "y_position"])) / len(data)),
        "median_step_distance": _number(steps["step"].median()),
        "nonzero_step_median": _number(steps.loc[steps["step"] > 0, "step"].median()),
        "same_frame_player_duplicate_share": _pct(data.duplicated(["frame", "player_id"])),
        "integer_coordinate_pair_share": _pct(fractions.all(axis=1)),
        "teleports_ge_50": int(len(teleports)),
        "teleport_identity_change_share": _pct(teleports["identity_change"]),
        "teleport_boundary_share": _pct(teleports["boundary"]),
        "teleport_gap_gt_3_share": _pct(teleports["frame_gap"] > 3),
        "all_step_identity_change_share": _pct(steps["identity_change"]),
        "top_player": {
            "player_id": int(top_id), "rows": int(per_player.iloc[0]),
            "zero_step_share": _pct(top.eq(0.0)),
            "median_nonzero_step": _number(top.loc[top > 0].median()),
        },
    }


def _summary(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    fields = ("zero_step_share", "distinct_position_ratio", "median_step_distance",
              "nonzero_step_median", "same_frame_player_duplicate_share",
              "integer_coordinate_pair_share", "teleport_identity_change_share",
              "teleport_boundary_share", "teleport_gap_gt_3_share")
    result: dict[str, dict[str, float]] = {}
    for name in fields:
        values = pd.Series([row[name] for row in rows], dtype="float64").dropna()
        result[name] = {"min": float(values.min()), "p25": float(values.quantile(.25)),
                        "median": float(values.median()), "p75": float(values.quantile(.75)),
                        "max": float(values.max()), "mean": float(values.mean())}
    return result


def choose_games(root: Path, count: int) -> list[Path]:
    """Choose a deterministic spread plus the five supplied reproduction games."""
    available = {
        path.parent.name: path for path in root.glob("*/tracking_data.csv")
        if path.parent.name.isdigit() and len(path.parent.name) == 10
    }
    chosen = [available[game] for game in KNOWN_GAMES if game in available]
    remaining = [path for game, path in sorted(available.items()) if game not in KNOWN_GAMES]
    needed = max(0, count - len(chosen))
    if needed:
        indexes = np.linspace(0, len(remaining) - 1, min(needed, len(remaining)), dtype=int)
        chosen.extend(remaining[index] for index in indexes)
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/tracking"))
    parser.add_argument("--games", type=int, default=25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = choose_games(args.root, args.games)
    if len(paths) < args.games:
        raise FileNotFoundError("Only %d tracking CSVs found below %s" % (len(paths), args.root))
    games = [audit_game(path) for path in paths]
    report = {"root": str(args.root), "games_requested": args.games, "games_measured": len(games),
              "teleport_distance": TELEPORT_DISTANCE, "games": games, "distribution": _summary(games)}
    rendered = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="ascii")
    print(rendered)


if __name__ == "__main__":
    main()
