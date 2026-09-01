"""Event-first soccer expected threat (xT), with an honest ball-tracking bridge.

The solver independently implements Karun Singh's 2019 xT recurrence:
https://karun.in/blog/expected-threat.html .  The 12x8 fallback is the
published public xT grid convention; fit() on our captured event corpus is
preferred because its rates and transitions represent our data, not a claim
about a current league.  No external repository code is used.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROWS, COLS, PITCH_X, PITCH_Y = 8, 12, 105.0, 68.0

# Public 12x8 xT fallback values, y rows from one touchline to the other.
# Source/method: Karun Singh, "Introducing Expected Threat" (2019), above.
PUBLISHED_XT_GRID = np.array([
    [.006383, .007796, .008448, .009776, .011262, .012483, .014735, .017450, .021221, .027563, .034851, .037926],
    [.005799, .007131, .008225, .009912, .012233, .015010, .019201, .025144, .032187, .041592, .052673, .055812],
    [.004942, .006349, .007748, .010109, .013067, .016651, .022116, .029811, .040539, .054212, .070654, .078547],
    [.004243, .005871, .008402, .011827, .016348, .022100, .030930, .043131, .059521, .082251, .118634, .162971],
    [.004243, .005871, .008402, .011827, .016348, .022100, .030930, .043131, .059521, .082251, .118634, .162971],
    [.004942, .006349, .007748, .010109, .013067, .016651, .022116, .029811, .040539, .054212, .070654, .078547],
    [.005799, .007131, .008225, .009912, .012233, .015010, .019201, .025144, .032187, .041592, .052673, .055812],
    [.006383, .007796, .008448, .009776, .011262, .012483, .014735, .017450, .021221, .027563, .034851, .037926],
], dtype=float)


def _zone(x: float, y: float, rows: int = ROWS, cols: int = COLS) -> int:
    """Map 105x68 coordinates to a flattened y-major grid zone."""
    col = min(cols - 1, max(0, int(float(x) / PITCH_X * cols)))
    row = min(rows - 1, max(0, int(float(y) / PITCH_Y * rows)))
    return row * cols + col


def solve_xt(shot_prob: np.ndarray, goal_prob: np.ndarray, move_prob: np.ndarray,
             transitions: np.ndarray, tol: float = 1e-10,
             max_iter: int = 200) -> np.ndarray:
    """Solve V = s*g + m*T*V by fixed-point iteration."""
    value = np.zeros_like(shot_prob, dtype=float)
    reward = np.asarray(shot_prob, float) * np.asarray(goal_prob, float)
    for _ in range(max_iter):
        updated = reward + np.asarray(move_prob, float) * (transitions @ value)
        if np.max(np.abs(updated - value)) < tol:
            return updated
        value = updated
    return value


class SoccerXT:
    """A 12x8 xT surface fitted on supplied events or using the fallback."""

    def __init__(self, grid: np.ndarray | None = None) -> None:
        self.grid = np.asarray(PUBLISHED_XT_GRID if grid is None else grid, dtype=float)
        if self.grid.shape != (ROWS, COLS):
            raise ValueError("xT grid must be 8x12")

    @classmethod
    def fit(cls, events_df: pd.DataFrame) -> "SoccerXT":
        """Fit movement/shot/goal rates and transitions from captured events."""
        required = {"x", "y", "next_x", "next_y", "is_shot", "is_goal"}
        if events_df.empty or not required.issubset(events_df.columns):
            return cls()
        n = ROWS * COLS
        total = np.zeros(n); shots = np.zeros(n); goals = np.zeros(n)
        moves = np.zeros(n); transitions = np.zeros((n, n))
        for row in events_df.itertuples(index=False):
            start = _zone(row.x, row.y)
            total[start] += 1
            if bool(row.is_shot):
                shots[start] += 1; goals[start] += float(bool(row.is_goal))
            elif pd.notna(row.next_x) and pd.notna(row.next_y):
                end = _zone(row.next_x, row.next_y)
                moves[start] += 1; transitions[start, end] += 1
        active = total > 0
        shot_prob = np.divide(shots, total, out=np.zeros(n), where=active)
        move_prob = np.divide(moves, total, out=np.zeros(n), where=active)
        goal_prob = np.divide(goals, shots, out=np.zeros(n), where=shots > 0)
        transitions = np.divide(transitions, moves[:, None], out=np.zeros_like(transitions), where=moves[:, None] > 0)
        return cls(solve_xt(shot_prob, goal_prob, move_prob, transitions).reshape(ROWS, COLS))

    def apply(self, events_df: pd.DataFrame, window_seconds: int = 300) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return per-action deltas and team/window xT sums for 105x68 events."""
        actions = events_df.copy()
        empty_sums = pd.DataFrame(columns=["team", "window", "xt_delta"])
        if actions.empty:
            return actions.assign(xt_delta=pd.Series(dtype=float)), empty_sums
        starts = [_zone(x, y) for x, y in zip(actions.x, actions.y)]
        ends = [_zone(x, y) for x, y in zip(actions.next_x, actions.next_y)]
        flat = self.grid.ravel()
        actions["xt_start"] = flat[starts]; actions["xt_end"] = flat[ends]
        actions["xt_delta"] = actions.xt_end - actions.xt_start
        actions["team"] = actions.get("team", "UNKNOWN")
        if "window" not in actions:
            clock = actions.get("timestamp", actions.get("frame", pd.Series(0, index=actions.index)))
            actions["window"] = (pd.to_numeric(clock, errors="coerce").fillna(0) // window_seconds).astype(int)
        return actions, actions.groupby(["team", "window"], as_index=False).xt_delta.sum()


def ball_proxy_events(tracking: pd.DataFrame, max_frame_gap: int = 1) -> pd.DataFrame:
    """Convert consecutive `cls == ball` tracking rows into proxy move events."""
    columns = ["x", "y", "next_x", "next_y", "is_shot", "is_goal", "team", "frame"]
    if "cls" not in tracking or not tracking.cls.astype(str).str.lower().eq("ball").any():
        print("PENDING BALL TRACKING")
        return pd.DataFrame(columns=columns)
    ball = tracking.loc[tracking.cls.astype(str).str.lower().eq("ball")].copy()
    order = "frame" if "frame" in ball else "timestamp" if "timestamp" in ball else None
    if order is None:
        ball["_row_order"] = np.arange(len(ball))
        order = "_row_order"
    ball = ball.sort_values(order).reset_index(drop=True)
    next_ball = ball.shift(-1)
    gap = pd.to_numeric(next_ball[order], errors="coerce") - pd.to_numeric(ball[order], errors="coerce")
    valid = gap.le(max_frame_gap) if order in {"frame", "_row_order"} else gap.ge(0)
    out = pd.DataFrame({"x": ball.x, "y": ball.y, "next_x": next_ball.x,
                        "next_y": next_ball.y, "is_shot": False, "is_goal": False,
                        "team": ball.get("team", "UNKNOWN"), "frame": ball.get("frame", 0)})
    return out.loc[valid.fillna(False)].reset_index(drop=True)


def events_from_tracking_csv(path: str | Path) -> pd.DataFrame:
    """Adapter hook for captured soccer tracking CSV files."""
    return ball_proxy_events(pd.read_csv(path))
