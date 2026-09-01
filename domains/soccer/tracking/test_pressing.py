"""Tests for the near-ball pressing proxy.

Run: python -m pytest domains/soccer/tracking/test_pressing.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.soccer.tracking.pressing import (
    PRESSURE_COLUMNS,
    aggregate_pressing,
    carrier_frames,
    pressure_index,
)

CARRIER = (30.0, 34.0)


def _rows(records: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=["frame", "track_id", "cls", "x", "y"])


def _frame_rows(frame: int, defenders: list[tuple[float, float]], with_ball: bool) -> list[dict[str, object]]:
    records = [{"frame": frame, "track_id": 1, "cls": "player", "x": CARRIER[0], "y": CARRIER[1]}]
    for offset, (x, y) in enumerate(defenders):
        records.append({"frame": frame, "track_id": 2 + offset, "cls": "player", "x": x, "y": y})
    if with_ball:
        records.append({"frame": frame, "track_id": 0, "cls": "ball", "x": CARRIER[0], "y": CARRIER[1]})
    return records


APPROACHES = ((1.0, 0.0), (0.8, 0.6))


def _converging(n_frames: int = 40, with_ball: bool = True) -> pd.DataFrame:
    """Two defenders closing radially on a static carrier at 0.4 m per frame."""
    records: list[dict[str, object]] = []
    for frame in range(n_frames):
        distance = 25.0 - 0.4 * frame
        defenders = [(CARRIER[0] + u * distance, CARRIER[1] + v * distance) for u, v in APPROACHES]
        records += _frame_rows(frame, defenders, with_ball)
    return _rows(records)


def _static(n_frames: int = 20) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for frame in range(n_frames):
        records += _frame_rows(frame, [(40.0, 34.0), (36.0, 42.0)], True)
    return _rows(records)


def test_carrier_is_the_player_nearest_the_ball() -> None:
    carriers = carrier_frames(_converging())
    assert len(carriers) == 40
    assert set(carriers["track_id"]) == {1.0}
    assert carriers["ball_dist"].max() == 0.0


def test_loose_ball_yields_no_carrier() -> None:
    rows = _converging(n_frames=3)
    rows.loc[rows["cls"] == "ball", ["x", "y"]] = [95.0, 5.0]
    assert carrier_frames(rows).empty


def test_converging_defenders_raise_pressure_monotonically() -> None:
    index = pressure_index(_converging()).sort_values("frame")
    pressure = index["pressure"].to_numpy()
    assert pressure[0] == 0.0
    assert np.all(np.diff(pressure) >= -1e-9)
    assert np.all(np.diff(pressure[-5:]) > 0.0)
    assert pressure[-1] > pressure[0]
    assert index["n_opponents"].iloc[-1] == 2.0


def test_static_defenders_hold_pressure_flat() -> None:
    index = pressure_index(_static())
    pressure = index["pressure"].to_numpy()
    assert index["n_opponents"].unique().tolist() == [2.0]
    assert pressure[0] > 0.0
    assert float(np.std(pressure)) < 1e-9


def test_no_ball_rows_returns_empty_unless_proxy_is_requested() -> None:
    rows = _converging(with_ball=False)
    assert carrier_frames(rows).empty
    empty = pressure_index(rows)
    assert empty.empty and tuple(empty.columns) == PRESSURE_COLUMNS
    assert aggregate_pressing(rows).empty
    assert not carrier_frames(rows, ball_proxy=True).empty
    assert not pressure_index(rows, ball_proxy=True).empty


def test_aggregate_reports_window_distribution() -> None:
    summary = aggregate_pressing(_converging(), window_s=0.4, fps=25.0)
    assert summary["window"].tolist() == [0, 1, 2, 3]
    assert summary["n_frames"].tolist() == [10.0] * 4
    assert summary["mean"].is_monotonic_increasing
    assert (summary["p90"] >= summary["p50"]).all()
    assert (summary["max"] >= summary["p90"]).all()
    assert float(np.std(aggregate_pressing(_static(), window_s=0.4)["std"])) < 1e-9
