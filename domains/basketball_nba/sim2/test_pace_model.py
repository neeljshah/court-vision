"""Per-file tests: duration model normalization + backoff."""
import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.pace_model import PaceModel, DMAX, N_DCELLS


def test_dur_model_normalized():
    rng = np.random.default_rng(1)
    n = 6000
    df = pd.DataFrame({
        "time_b": rng.integers(0, 6, n), "margin_b": rng.integers(0, 7, n),
        "duration": np.clip(rng.normal(14, 6, n), 1, DMAX),
    })
    m = PaceModel.fit(df)
    cdf = m.dur_cdf_matrix()
    assert cdf.shape == (N_DCELLS, DMAX)
    assert np.allclose(cdf[:, -1], 1.0)
    assert np.all(np.diff(cdf, axis=1) >= -1e-9)
    # mean possession duration in a plausible NBA range
    assert 8.0 < m.mean_duration() < 20.0


def test_thin_cell_backoff():
    # only time_b=0,margin_b=0 populated; other cells fall back to global -> still valid CDFs
    df = pd.DataFrame({"time_b": [0] * 100, "margin_b": [0] * 100,
                       "duration": [12.0] * 100})
    m = PaceModel.fit(df)
    cdf = m.dur_cdf_matrix()
    assert np.allclose(cdf[:, -1], 1.0)   # every (incl. empty) cell is normalized
