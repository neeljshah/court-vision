"""Per-file tests for pitch_engine.selection -- empirical table + backoff."""
import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.selection import SelectionModel, no_context_baseline, MIN_CELL


def _frame(pitcher, pclass, n, cidx=0, pidx=0, bbucket=0, zbucket="IZ"):
    return pd.DataFrame({"pitcher": [pitcher] * n, "pclass": [pclass] * n,
                         "cidx": [cidx] * n, "pidx": [pidx] * n,
                         "bbucket": [bbucket] * n, "zbucket": [zbucket] * n})


def test_pitcher_specific_and_backoff():
    # pitcher 1 throws only FB in count 0-0 (dense); a stray league of BR/OS
    df = pd.concat([
        _frame(1, "FB", MIN_CELL + 5, cidx=0),
        _frame(2, "BR", MIN_CELL + 5, cidx=0),
        _frame(3, "OS", MIN_CELL + 5, cidx=0),
    ], ignore_index=True)
    m = SelectionModel.fit(df)
    # pitcher-specific cell dominates
    p = m.class_probs(1, 0, 0, 0)
    assert p.argmax() == 0 and p[0] > 0.9      # Laplace-smoothed, near 1
    # unknown pitcher -> league cell (mix of FB/BR/OS ~ equal)
    p_unk = m.class_probs(999, 0, 0, 0)
    assert abs(p_unk.sum() - 1.0) < 1e-9
    assert 0.2 < p_unk[0] < 0.5
    # zone probs normalized
    z = m.zone_probs(0, 0)
    assert abs(z.sum() - 1.0) < 1e-9


def test_no_context_baseline_marginal():
    df = pd.concat([_frame(1, "FB", 60), _frame(1, "BR", 40)], ignore_index=True)
    b = no_context_baseline(df)
    assert abs(b.sum() - 1.0) < 1e-9
    assert b.argmax() == 0 and 0.55 < b[0] < 0.62   # 61/103 after Laplace
