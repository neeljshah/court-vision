"""The gate must DETECT a planted prior signal and REFUSE pure noise -- the two
failure modes that would make the payoff-arena result meaningless."""
import numpy as np
import pandas as pd

from scripts.platformkit.ingame_compose.conditional_gate import (
    _PRIOR_COLS,
    score_checkpoint,
)


def _sig(z):
    return 1.0 / (1.0 + np.exp(-z))


def _make(n, seed, prior_drives_y):
    """n date-ordered games; y = f(score_diff [+ 'off' prior if prior_drives_y]).
    elo offset neutral (0) so the test isolates score vs prior contribution."""
    rng = np.random.default_rng(seed)
    score_diff = rng.normal(0, 5, n)                 # in-game score info
    off = rng.normal(0, 1, n)                         # candidate prior feature
    prior = pd.DataFrame({c: rng.normal(0, 1, n) for c in _PRIOR_COLS})
    prior["off"] = off                                # plant signal into 'off'
    logit = 0.1 * score_diff + (1.6 * off if prior_drives_y else 0.0)
    y = (rng.uniform(0, 1, n) < _sig(logit)).astype(float)
    elo = np.zeros(n)
    gid = np.array([f"g{i}" for i in range(n)])        # each game its own cluster
    return elo, score_diff, prior, y, gid


def test_planted_prior_signal_is_detected():
    elo, sd, prior, y, gid = _make(500, seed=1, prior_drives_y=True)
    r = score_checkpoint("endQ1", 0.75, elo, sd, prior, y, gid)
    assert r.delta > 0, r
    assert r.dm_p < 0.05, r
    assert r.verdict == "MATTERS_PROVISIONAL", r
    assert r.prior_beta_l2 > 0.3, r                    # 'off' beta is real


def test_pure_noise_is_refused():
    elo, sd, prior, y, gid = _make(500, seed=7, prior_drives_y=False)
    r = score_checkpoint("endQ1", 0.75, elo, sd, prior, y, gid)
    assert r.verdict == "NULL", r


def test_too_few_oos_is_untestable():
    elo, sd, prior, y, gid = _make(80, seed=3, prior_drives_y=True)  # ~32 OOS < 60
    r = score_checkpoint("endQ1", 0.75, elo, sd, prior, y, gid)
    assert r.verdict == "UNTESTABLE", r


if __name__ == "__main__":
    test_planted_prior_signal_is_detected()
    test_pure_noise_is_refused()
    test_too_few_oos_is_untestable()
    print("conditional_gate signal/noise tests PASS")
