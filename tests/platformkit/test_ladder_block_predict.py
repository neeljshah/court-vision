"""Batched block predictions must equal the reference per-tick path to 1e-12."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate import ladder_block_predict as ladder
from scripts.platformkit.eval_gate import s265_incumbent_conformal_band_sample as s265
from scripts.platformkit.eval_gate import s86_nba_every_tick as s86
from scripts.platformkit.foundry import ingame_incumbent_nba as incumbent

SAMPLE, TOLERANCE = 2500, 1e-12


def _ticks() -> pd.DataFrame:
    """Real S86 tick features when the corpus is present, else a synthetic stand-in."""
    if s86.CHECKPOINTS.exists():
        rows = s265._rows(s86.load_ticks(s86.CHECKPOINTS)).head(4 * SAMPLE)
        return rows.join(incumbent.ladder_base_columns(rows))
    generator = np.random.default_rng(308)
    size = 4 * SAMPLE
    return pd.DataFrame({"source_row": np.arange(size),
                         "y": generator.integers(0, 2, size).astype(float),
                         "logit_p0": generator.normal(size=size),
                         "margin_s": generator.normal(0.0, 9.0, size),
                         "z": generator.normal(0.0, 12.0, size)})


def test_batched_block_predictions_equal_the_per_tick_path() -> None:
    frame = _ticks()
    assert len(frame) == 4 * SAMPLE
    states = [{"s86_block": 0, "outcome": int(row.y),
               "features": {"state_key": "k%07d" % int(row.source_row),
                            "logit_p0": float(row.logit_p0), "margin_s": float(row.margin_s),
                            "z": float(row.z)}}
              for row in frame.itertuples(index=False)]
    test, train = states[:SAMPLE], states[SAMPLE:]
    assert len({state["outcome"] for state in train}) == 2
    fit = ladder.fit_block(train)
    one = np.array([ladder.predict_one(fit, state["features"]) for state in test])
    many = ladder.predict_many(fit, [state["features"] for state in test])
    assert len(one) == SAMPLE and float(np.max(np.abs(one - many))) <= TOLERANCE
    predictor = ladder.BlockPredictor(test)
    served = np.array([predictor(train, state, True) for state in test])
    assert float(np.max(np.abs(served - one))) <= TOLERANCE
