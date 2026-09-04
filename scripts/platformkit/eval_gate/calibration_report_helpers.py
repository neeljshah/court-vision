"""Shared unchanged helpers for the calibration evidence report."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.wp_diagnostics import max_loser_wp


def _as_records(records: Any) -> list[dict[str, Any]]:
    if hasattr(records, "to_dict"):
        return [dict(row) for row in records.to_dict("records")]
    return [dict(row) for row in records]


def _prediction_column(rows: Sequence[Mapping[str, Any]]) -> str | None:
    for column in ("model_prob", "pred", "prediction", "p_base"):
        if any(column in row for row in rows):
            return column
    return None


def _finite_binary(value: Any) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) in (0.0, 1.0)
    except (TypeError, ValueError):
        return False


def _bin_table(probs: Sequence[float], outcomes: Sequence[float], bins: int) -> list[dict[str, Any]]:
    """The ONE bin-edge rule -- always `bins` rows, empty bins carried as n = 0."""
    p, y = np.asarray(probs, dtype=float), np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, Any]] = []
    for k in range(bins):
        lo, hi = float(edges[k]), float(edges[k + 1])
        mask = (p >= lo) & (p < hi) if k < bins - 1 else (p >= lo) & (p <= hi)
        n_k = int(mask.sum())
        mean_p = float(p[mask].mean()) if n_k else None
        observed = float(y[mask].mean()) if n_k else None
        rows.append({"bin": "%0.1f-%0.1f" % (lo, hi), "lo": lo, "hi": hi, "n": n_k,
                    "mean_predicted_prob": mean_p, "observed_win_freq": observed,
                    "gap": (observed - mean_p) if n_k else None})
    return rows


def _from_bins(table: Sequence[Mapping[str, Any]], base_rate: float,
               total: int) -> dict[str, float]:
    """Recompute the summary figures FROM the published bins (A2 reproduction)."""
    out = {"ece": 0.0, "reliability": 0.0, "resolution": 0.0}
    for row in table:
        if not row["n"]:
            continue
        weight = row["n"] / total
        out["ece"] += weight * abs(row["gap"])
        out["reliability"] += weight * row["gap"] ** 2
        out["resolution"] += weight * (row["observed_win_freq"] - base_rate) ** 2
    return out


def _ticks(probs: Sequence[float], outcomes: Sequence[float],
           rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"model_prob": float(prob), "outcome": float(outcome),
         "game": str(row.get("event_id", index))}
        for index, (prob, outcome, row) in enumerate(zip(probs, outcomes, rows))
    ]


def _unit_groups(rows: Sequence[Mapping[str, Any]], unit_col: str | None,
                 order_by: str | None) -> tuple[list[tuple[str, list[int]]], bool, bool]:
    """Positions per corpus_unit, sorted within the unit by ``order_by`` (S50).

    Returns (groups, sort_within_unit_is_noop, partition_is_identity) -- both
    flags published so a reader sees whether the walk order actually moved.
    ponytail: the sort key is ``str(value)``; every gate corpus stores one
    ISO-ordered date dtype per column, so lexical order IS date order there.
    """
    units: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        units.setdefault(str(row.get(unit_col)) if unit_col else "ALL", []).append(index)
    groups: list[tuple[str, list[int]]] = []
    sort_noop = True
    for key, positions in units.items():
        ordered = positions
        if order_by and any(order_by in rows[index] for index in positions):
            ordered = sorted(positions, key=lambda index: str(rows[index].get(order_by)))
            sort_noop = sort_noop and ordered == positions
        groups.append((key, ordered))
    walked = [index for _, positions in groups for index in positions]
    return groups, sort_noop, walked == list(range(len(rows)))


def _unit_summary(key: str, positions: list[int], rows: Sequence[Mapping[str, Any]],
                  order_by: str | None, raw: list[float], calibrated: list[float],
                  outcomes: list[float], bins: int) -> dict[str, Any]:
    dates = [str(rows[index].get(order_by)) for index in positions] if order_by else []
    y = [outcomes[index] for index in positions]
    return {
        "corpus_unit": key, "n": len(positions),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "ece_before": ece([raw[index] for index in positions], y, bins=bins),
        "ece_after": ece([calibrated[index] for index in positions], y, bins=bins),
    }


def _max_loser_summary(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep the existing diagnostic's aggregate fields, not its event listing."""
    result = max_loser_wp(ticks)
    return {key: result[key] for key in ("quantiles", "above_0_8", "above_0_9")}
