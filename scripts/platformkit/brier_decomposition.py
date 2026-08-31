"""Murphy Brier-score decomposition and conservative forecaster comparisons."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Sequence

import numpy as np


def _pairs(pred_probs: Iterable[float], outcomes: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
    """Validate binary outcomes and return finite forecast arrays."""
    probs = np.asarray(list(pred_probs), dtype=float)
    actual = np.asarray(list(outcomes), dtype=float)
    if probs.ndim != 1 or actual.ndim != 1 or len(probs) != len(actual) or not len(probs):
        raise ValueError("pred_probs and outcomes must be non-empty equal-length vectors")
    if not np.isfinite(probs).all() or not np.isfinite(actual).all() or np.any((probs < 0) | (probs > 1)):
        raise ValueError("probabilities and outcomes must be finite; probabilities must be in [0, 1]")
    if not np.isin(actual, (0.0, 1.0)).all():
        raise ValueError("outcomes must be binary")
    return probs, actual


def decompose(pred_probs: Iterable[float], outcomes: Iterable[float], n_bins: int = 10) -> dict[str, object]:
    """Return exact Murphy components plus fixed-width reliability-panel bins.

    Components group on each distinct forecast value, which preserves the Brier
    identity exactly; ``n_bins`` controls only the human-readable panel.
    """
    if n_bins < 1:
        raise ValueError("n_bins must be positive")
    probs, actual = _pairs(pred_probs, outcomes)
    base_rate = float(actual.mean())
    reliability = resolution = 0.0
    for value in np.unique(probs):
        group = actual[probs == value]
        weight = len(group) / len(actual)
        observed = float(group.mean())
        reliability += weight * (float(value) - observed) ** 2
        resolution += weight * (observed - base_rate) ** 2
    uncertainty = base_rate * (1.0 - base_rate)
    brier = float(np.mean((probs - actual) ** 2))
    assert abs(brier - (reliability - resolution + uncertainty)) <= 1e-9
    groups: list[list[int]] = [[] for _ in range(n_bins)]
    for index, value in enumerate(probs):
        groups[min(n_bins - 1, int(value * n_bins))].append(index)
    bins = []
    for number, indices in enumerate(groups):
        if indices:
            subset = np.asarray(indices)
            bins.append({"bin": "%0.2f-%0.2f" % (number / n_bins, (number + 1) / n_bins),
                         "n": len(indices), "mean_pred": float(probs[subset].mean()),
                         "obs_freq": float(actual[subset].mean())})
        else:
            bins.append({"bin": "%0.2f-%0.2f" % (number / n_bins, (number + 1) / n_bins),
                         "n": 0, "mean_pred": None, "obs_freq": None})
    return {"brier": float(brier), "reliability": float(reliability),
            "resolution": float(resolution), "uncertainty": float(uncertainty), "bins": bins}


def _source_pairs(value: object) -> tuple[Sequence[float], Sequence[float]]:
    if isinstance(value, Mapping):
        return value["pred_probs"], value["outcomes"]  # type: ignore[index]
    if isinstance(value, tuple) and len(value) == 2:
        return value[0], value[1]
    raise ValueError("each source must be (pred_probs, outcomes) or a mapping with those keys")


def panel(preds_by_source: Mapping[str, object], n_bins: int = 10) -> str:
    """Render an ASCII comparison panel and shrink-to-base-rate warnings."""
    results = {name: decompose(*_source_pairs(value), n_bins=n_bins)
               for name, value in sorted(preds_by_source.items())}
    flags: dict[str, list[str]] = defaultdict(list)
    for name, result in results.items():
        for other, baseline in results.items():
            if name == other:
                continue
            if (result["brier"] < baseline["brier"] and result["resolution"] < baseline["resolution"]
                    and result["reliability"] < baseline["reliability"]):
                flags[name].append(other)
    lines = ["SOURCE | BRIER | RELIABILITY | RESOLUTION | UNCERTAINTY | MARKET-FOLLOW FLAG"]
    for name, result in results.items():
        warning = ("improvement may be shrink-to-base-rate -- verify resolution"
                   if name in flags else "-")
        lines.append("%s | %.6f | %.6f | %.6f | %.6f | %s" %
                     (name, result["brier"], result["reliability"], result["resolution"],
                      result["uncertainty"], warning))
    return "\n".join(lines)
