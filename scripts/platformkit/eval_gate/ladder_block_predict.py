"""Block-batched ladder_base predictions for the S294 / S308 CPCV callbacks.

The CPCV engine calls its predictor once per test tick. The fitted model was
already cached per frozen block, but the PREDICTION was not: every tick built a
one-row DataFrame and called ``predict_proba`` (measured on the pod at 1.301 ms
of CPU per callback, 2,791,497 callbacks for the S308 nested design).

``predict_many`` uses the SAME fitted model, the SAME standardising mean/std and
the SAME ``LADDER_BASE_COLS`` order as ``predict_one``, so it reproduces the
per-tick path to floating-point tolerance. ``predict_one`` is retained as the
reference path and ``tests/platformkit/test_ladder_block_predict.py`` asserts
the two agree to 1e-12 on real S86 ticks. Calibration tooling only.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.foundry import ingame_incumbent_nba as incumbent

Fit = tuple[pd.Series, pd.Series, LogisticRegression]


def fit_block(train: list[dict], outcome_key: str = "outcome") -> Fit:
    """Fit the shared ladder_base logistic model on one purged train path."""
    cols = incumbent.LADDER_BASE_COLS
    frame = pd.DataFrame([state["features"] for state in train])
    mean, std = frame[cols].mean(), frame[cols].std(ddof=0).replace(0.0, 1.0)
    model = LogisticRegression(C=1e6, max_iter=2000).fit(
        frame[cols].sub(mean).div(std).to_numpy(),
        np.asarray([state[outcome_key] for state in train]))
    return mean, std, model


def predict_one(fit: Fit, features: dict) -> float:
    """Reference per-tick path: one one-row frame, one predict_proba call."""
    mean, std, model = fit
    return float(model.predict_proba(pd.DataFrame([features])[incumbent.LADDER_BASE_COLS]
                                     .sub(mean).div(std).to_numpy())[0, 1])


def predict_many(fit: Fit, features: Iterable[dict]) -> np.ndarray:
    """Batched path: one predict_proba call over every tick of a block."""
    mean, std, model = fit
    frame = pd.DataFrame(list(features))
    return model.predict_proba(frame[incumbent.LADDER_BASE_COLS]
                               .sub(mean).div(std).to_numpy())[:, 1]


class BlockPredictor:
    """Fit once per frozen block, then serve that block's ticks from one batch.

    The callback signature is the CPCV engine's predictor contract, so the
    per-tick record path, the purge, the redaction and the vintage assertion are
    all unchanged; only the arithmetic is batched. Every served tick is checked
    against its own source features, so a redacted view that had diverged from
    the state it was built from would raise rather than be served a stale value.
    """

    def __init__(self, states: list[dict], group_key: str = "s86_block") -> None:
        self.group_key = group_key
        self.source: dict[str, dict] = {}
        self.blocks: dict[int, list[dict]] = {}
        for state in states:
            features = state["features"]
            self.source[features["state_key"]] = features
            self.blocks.setdefault(int(state[group_key]), []).append(features)
        self.cache: dict[int, tuple[Fit, dict[str, float]]] = {}

    def __call__(self, train: list[dict], test: dict, _: bool = True) -> float:
        block = int(test[self.group_key])
        if block not in self.cache:
            fit = fit_block(train)
            rows = self.blocks[block]
            self.cache[block] = fit, dict(zip([row["state_key"] for row in rows],
                                              map(float, predict_many(fit, rows))))
        features = test["features"]
        source = self.source[features["state_key"]]
        assert all(source[col] == features[col] for col in incumbent.LADDER_BASE_COLS), (
            "redacted test view diverged from its source ladder_base features")
        return self.cache[block][1][features["state_key"]]
