"""Conservative NBA ball-screen candidate detection from tracking rows.

This is SCREEN-CANDIDATE detection, not defender coverage classification.
Without full re-ID and defender assignments, better tracking is required to
identify the defender-facing coverage taxonomy described by Atlas.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


EVENT_COLUMNS = ["game_id", "frame", "handler_id", "screener_id", "x", "y"]
_ID_COLUMNS = ("player_id", "track_id")
_X_COLUMNS = ("ft_x", "x")
_Y_COLUMNS = ("ft_y", "y")
_TEAM_COLUMNS = ("team_id", "team", "side")
_POSSESSION_COLUMNS = ("has_possession", "is_possession", "possession_flag",
                       "ball_possession", "ball_possession_flag", "possession", "has_ball")
_HANDLER_COLUMNS = ("ball_handler_id", "possessor_id")


def _column(frame: pd.DataFrame, names: tuple[str, ...], label: str) -> str:
    for name in names:
        if name in frame.columns:
            return name
    raise ValueError("Tracking data requires a %s column; accepted: %s" %
                     (label, ", ".join(names)))


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value) if pd.notna(value) else False


def _ball_position(rows: pd.DataFrame) -> tuple[float, float] | None:
    for x_col, y_col in (("_ball_x", "_ball_y"), ("ball_ft_x", "ball_ft_y"),
                         ("ball_x", "ball_y")):
        if x_col in rows and y_col in rows:
            point = rows[[x_col, y_col]].dropna()
            if not point.empty:
                return float(point.iloc[0][x_col]), float(point.iloc[0][y_col])
    return None


def _handler(rows: pd.DataFrame) -> pd.Series | None:
    for column in _POSSESSION_COLUMNS:
        if column in rows:
            flagged = rows.loc[rows[column].map(_truthy)]
            if not flagged.empty:
                return flagged.iloc[0]
    for column in _HANDLER_COLUMNS:
        if column in rows:
            value = rows[column].dropna()
            if not value.empty:
                match = rows.loc[rows["player_id"].astype(str).eq(str(value.iloc[0]))]
                if not match.empty:
                    return match.iloc[0]
    ball = _ball_position(rows)
    if ball is None or rows.empty:
        return None
    distance = (rows["x"].sub(ball[0]).pow(2) + rows["y"].sub(ball[1]).pow(2))
    return rows.loc[distance.idxmin()]


def _prepare(df: pd.DataFrame, fps: float) -> tuple[pd.DataFrame, str | None, str]:
    if fps <= 0:
        raise ValueError("fps must be positive")
    required = {"frame": "frame", "player_id": _column(df, _ID_COLUMNS, "player ID"),
                "x": _column(df, _X_COLUMNS, "x coordinate"),
                "y": _column(df, _Y_COLUMNS, "y coordinate")}
    team_column = _column(df, _TEAM_COLUMNS, "team ID")
    work = df.rename(columns={source: target for target, source in required.items()
                              if source != target}).copy()
    work["frame"] = pd.to_numeric(work["frame"], errors="raise")
    work["x"] = pd.to_numeric(work["x"], errors="raise")
    work["y"] = pd.to_numeric(work["y"], errors="raise")
    if "cls" in work:
        ball = work.loc[work["cls"].astype(str).str.lower().eq("ball"),
                        ["frame", "x", "y"]].drop_duplicates("frame")
        ball = ball.rename(columns={"x": "_ball_x", "y": "_ball_y"})
        work = work.loc[~work["cls"].astype(str).str.lower().eq("ball")].copy()
        work = work.merge(ball, on="frame", how="left")
    work = work.dropna(subset=["player_id", "x", "y", team_column])
    work = work.sort_values(["player_id", "frame"])
    dt = work.groupby("player_id")["frame"].diff().div(fps)
    dx = work.groupby("player_id")["x"].diff()
    dy = work.groupby("player_id")["y"].diff()
    work["speed"] = (dx.pow(2).add(dy.pow(2)).pow(0.5).div(dt)).fillna(0.0)
    return work, "game_id" if "game_id" in work else None, team_column


def per_game_counts(events: pd.DataFrame) -> pd.DataFrame:
    """Return screen-candidate counts grouped by the input game identifier."""
    if events.empty:
        return pd.DataFrame(columns=["game_id", "screen_candidate_count"])
    return (events.groupby("game_id", dropna=False).size()
            .rename("screen_candidate_count").reset_index())


def detect_screens(df: pd.DataFrame, fps: float = 30.0, min_frames: int = 8) -> pd.DataFrame:
    """Return conservative same-team, stationary screener convergence candidates.

    A candidate requires a possession-flagged (or ball-nearest) handler and a
    same-team teammate within five feet whose speed remains below two feet per
    second for at least ``min_frames`` consecutive source frames.
    """
    if min_frames < 1:
        raise ValueError("min_frames must be at least one")
    work, game_column, team_column = _prepare(df, fps)
    states: dict[tuple[Any, Any], dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for frame, group in work.sort_values("frame").groupby("frame", sort=True):
        handler = _handler(group)
        candidates: dict[tuple[Any, Any], pd.Series] = {}
        if handler is not None:
            teammates = group.loc[(group["player_id"] != handler["player_id"]) &
                                  (group[team_column] == handler[team_column])]
            distance = ((teammates["x"] - handler["x"]).pow(2) +
                        (teammates["y"] - handler["y"]).pow(2)).pow(0.5)
            near = teammates.loc[distance.le(5.0) & teammates["speed"].lt(2.0)]
            candidates = {(handler["player_id"], row["player_id"]): row
                          for _, row in near.iterrows()}
        for pair in set(states).difference(candidates):
            del states[pair]
        for pair, screener in candidates.items():
            previous = states.get(pair)
            contiguous = previous is not None and frame == previous["last_frame"] + 1
            state = previous if contiguous else {
                "start_frame": frame, "x": float(screener["x"]), "y": float(screener["y"]),
                "count": 0, "reported": False,
            }
            state["count"] += 1
            state["last_frame"] = frame
            states[pair] = state
            if state["count"] == min_frames and not state["reported"]:
                events.append({"game_id": group[game_column].iloc[0] if game_column else None,
                               "frame": state["start_frame"], "handler_id": pair[0],
                               "screener_id": pair[1], "x": state["x"], "y": state["y"]})
                state["reported"] = True
    result = pd.DataFrame(events, columns=EVENT_COLUMNS)
    result.attrs["per_game_counts"] = per_game_counts(result)
    return result


def write_events(events: pd.DataFrame, path: str | Path) -> Path:
    """Write screen-candidate events to a CSV or JSON file and return its path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".json":
        events.to_json(target, orient="records", indent=2)
    else:
        events.to_csv(target, index=False)
    return target
