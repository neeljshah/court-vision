"""Adapt production player rows for non-scorable image-space gate evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class ProductionTranslation:
    """Canonical rows and sealed frame-size provenance."""

    table: pd.DataFrame
    frame_width: float | None
    frame_height: float | None
    frame_size_source: str


_REQUIRED = frozenset(("frame", "player_id", "x_position", "y_position",
                       "ball_x2d", "ball_y2d"))


def _positive_pair(values: Mapping[str, object] | None) -> tuple[float, float] | None:
    if values is None:
        return None
    try:
        width = float(values.get("frame_width", values.get("width")))
        height = float(values.get("frame_height", values.get("height")))
    except (TypeError, ValueError):
        return None
    return (width, height) if isfinite(width) and isfinite(height) and width > 0 and height > 0 else None


def _estimated_size(source: pd.DataFrame) -> tuple[float, float] | None:
    if not {"x_norm", "y_norm"}.issubset(source.columns):
        return None
    x = pd.to_numeric(source["x_position"], errors="coerce")
    y = pd.to_numeric(source["y_position"], errors="coerce")
    x_norm = pd.to_numeric(source["x_norm"], errors="coerce")
    y_norm = pd.to_numeric(source["y_norm"], errors="coerce")
    widths = (x / x_norm).replace([float("inf"), float("-inf")], pd.NA).dropna()
    heights = (y / y_norm).replace([float("inf"), float("-inf")], pd.NA).dropna()
    if widths.empty or heights.empty:
        return None
    width, height = float(widths.median()), float(heights.median())
    return (width, height) if width > 0 and height > 0 else None


def _frame_size(source: pd.DataFrame,
                frame_size_sidecar: Mapping[str, object] | None) -> tuple[float | None, float | None, str]:
    sidecar = _positive_pair(frame_size_sidecar)
    if sidecar is not None:
        return sidecar[0], sidecar[1], "sidecar"
    estimated = _estimated_size(source)
    if estimated is not None:
        return estimated[0], estimated[1], "estimated"
    return None, None, "absent"


def _ball_rows(source: pd.DataFrame, size_source: str) -> pd.DataFrame:
    has_px = {"ball_x2d_px", "ball_y2d_px"}.issubset(source.columns)
    x_name, y_name = ("ball_x2d_px", "ball_y2d_px") if has_px else ("ball_x2d", "ball_y2d")
    rows: list[dict[str, object]] = []
    for frame, group in source.groupby("frame", sort=False):
        x = pd.to_numeric(group[x_name], errors="coerce")
        y = pd.to_numeric(group[y_name], errors="coerce")
        usable = group.loc[x.notna() & y.notna()].head(1)
        if usable.empty:
            continue
        record = usable.iloc[0].to_dict()
        record.update({"frame": frame, "track_id": -1, "x": float(x.loc[usable.index[0]]),
                       "y": float(y.loc[usable.index[0]]), "cls": "ball",
                       "ball_source": "embedded_px" if has_px else "embedded_court",
                       "frame_size_source": size_source, "scorable": False})
        rows.append(record)
    return pd.DataFrame(rows)


def adapt_production_section(source: pd.DataFrame,
                             frame_size_sidecar: Mapping[str, object] | None = None) -> ProductionTranslation:
    """Return additive canonical rows without changing a production table."""
    missing = sorted(_REQUIRED.difference(source.columns))
    if missing:
        raise ValueError("production table missing columns: {}".format(", ".join(missing)))
    width, height, size_source = _frame_size(source, frame_size_sidecar)
    players = source.copy(deep=True)
    players["track_id"] = players["player_id"]
    players["x"] = players["x_position"]
    players["y"] = players["y_position"]
    players["cls"] = "player"
    players["ball_source"] = "not_ball"
    players["frame_size_source"] = size_source
    players["scorable"] = False
    if "coordinate_space" not in players.columns:
        players["coordinate_space"] = "image_px"
    balls = _ball_rows(source, size_source)
    if not balls.empty and "coordinate_space" not in balls.columns:
        balls["coordinate_space"] = "image_px"
    table = pd.concat((players, balls), ignore_index=True, sort=False)
    return ProductionTranslation(table, width, height, size_source)
