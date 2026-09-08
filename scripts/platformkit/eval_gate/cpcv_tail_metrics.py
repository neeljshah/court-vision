"""Additive tail-loss diagnostics beside the protected evaluator records."""
from __future__ import annotations

import math
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np

# Deliberate read-only route imports. S293 adds metrics beside these evaluators.
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.walkforward import walk_forward

EPSILON = 1e-15


def _arrays(probabilities: Sequence[float], outcomes: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if p.ndim != 1 or y.ndim != 1 or len(p) != len(y) or not len(p):
        raise ValueError("probabilities and outcomes must be non-empty one-dimensional equal-length arrays")
    if not np.isfinite(p).all() or not np.isfinite(y).all():
        raise ValueError("non-finite probability or outcome")
    if ((p < 0.0) | (p > 1.0)).any() or not np.isin(y, (0.0, 1.0)).all():
        raise ValueError("probabilities must be in [0,1] and outcomes must be binary")
    return p, y


def log_loss_values(probabilities: Sequence[float], outcomes: Sequence[float],
                    epsilon: float = EPSILON) -> tuple[np.ndarray, dict[str, int]]:
    """Return finite per-row log losses and explicit endpoint accounting."""
    if not 0.0 < epsilon < 0.5:
        raise ValueError("epsilon must be between zero and one half")
    p, y = _arrays(probabilities, outcomes)
    audit = {
        "n": int(len(p)), "zero_probability_rows": int((p == 0.0).sum()),
        "one_probability_rows": int((p == 1.0).sum()),
        "clipped_rows": int(((p < epsilon) | (p > 1.0 - epsilon)).sum()),
        "excluded_rows": 0,
    }
    clipped = np.clip(p, epsilon, 1.0 - epsilon)
    values = -(y * np.log(clipped) + (1.0 - y) * np.log1p(-clipped))
    if not np.isfinite(values).all():
        raise AssertionError("log-loss clipping failed to produce finite values")
    return values, audit


def attach_log_losses(records: Iterable[Mapping[str, object]], *, probability_key: str = "p_model",
                      outcome_key: str = "y", tail_selector: Callable[[Mapping[str, object]], bool]) -> list[dict]:
    """Copy evaluator records and add only ``log_loss`` and ``tail_log_loss``."""
    copied = [dict(record) for record in records]
    if any("log_loss" in row or "tail_log_loss" in row for row in copied):
        raise ValueError("log-loss fields already exist; refusing to overwrite evaluator fields")
    values, _ = log_loss_values([float(row[probability_key]) for row in copied],
                                [float(row[outcome_key]) for row in copied])
    for row, value in zip(copied, values):
        row["log_loss"] = float(value)
        row["tail_log_loss"] = float(value) if tail_selector(row) else None
    return copied


def refuse_mixed_grain(records: Iterable[Mapping[str, object]], grain_key: str = "record_type") -> str:
    """Require one declared grain before a loss aggregation."""
    grains = {str(record[grain_key]) for record in records}
    if len(grains) != 1:
        raise ValueError("mixed-grain records are not valid for a single loss aggregation")
    return next(iter(grains))


def reliability_table(probabilities: Sequence[float], outcomes: Sequence[float],
                      edges: Sequence[float], min_n: int = 30) -> list[dict[str, float | int | str | bool | None]]:
    """Return every declared probability bin; a cell below ``min_n`` publishes n only (Q7)."""
    p, y = _arrays(probabilities, outcomes)
    if len(edges) < 2 or any(right <= left for left, right in zip(edges, edges[1:])):
        raise ValueError("edges must be strictly increasing")
    result = []
    for index, (left, right) in enumerate(zip(edges, edges[1:])):
        final = index == len(edges) - 2
        mask = (p >= left) & ((p <= right) if final else (p < right))
        count = int(mask.sum())
        label = "[%0.2f,%0.2f%s" % (left, right, "]" if final else ")")
        if count < min_n:
            # Q7: only n >= 30 may carry a scored cell. The declared bin is still published
            # with its count -- suppressed, never dropped and never merged into a neighbour.
            result.append({"bin": label, "n": count, "mean_probability": None,
                           "empirical_rate": None, "reliability_gap": None, "log_loss": None,
                           "suppressed_below_min_n": bool(count)})
            continue
        losses, _ = log_loss_values(p[mask], y[mask])
        mean_p, mean_y = float(p[mask].mean()), float(y[mask].mean())
        result.append({"bin": label, "n": count, "mean_probability": mean_p,
                       "empirical_rate": mean_y, "reliability_gap": abs(mean_y - mean_p),
                       "log_loss": float(losses.mean()), "suppressed_below_min_n": False})
    return result


def trailing_side(probabilities: Sequence[float], outcomes: Sequence[float],
                  home_margin: Sequence[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Express forecasts and outcomes from the trailing side when one exists.

    ``p``/``y`` arrive in the home frame. A negative home margin means the HOME team is
    the trailing team, so its own forecast and outcome carry over unchanged; otherwise
    the away team trails and the complement is taken. Callers mask to abs(margin) >= 12,
    so a tied row -- which has no trailing side -- never reaches here.
    """
    p, y = _arrays(probabilities, outcomes)
    margin = np.asarray(home_margin, dtype=float)
    if margin.shape != p.shape or not np.isfinite(margin).all():
        raise ValueError("margin must be finite and aligned with probabilities")
    home_trailing = margin < 0.0
    return np.where(home_trailing, p, 1.0 - p), np.where(home_trailing, y, 1.0 - y), home_trailing


__all__ = [
    "EPSILON", "attach_log_losses", "cpcv_evaluate", "log_loss_values", "refuse_mixed_grain",
    "reliability_table", "trailing_side", "walk_forward",
]
