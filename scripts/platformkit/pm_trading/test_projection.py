"""Per-file tests for projection.py (summer P&L scenario Monte Carlo).

Run: python -m pytest scripts/platformkit/pm_trading/test_projection.py -q
"""
import pathlib
import sys

import numpy as np

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import projection as P  # noqa: E402


def test_simulate_shape_and_sane_magnitude():
    rng = np.random.default_rng(1)
    pnl = P.simulate(P.SCENARIOS[1], 20_000, rng)  # BASE
    assert pnl.shape == (20_000,)
    # most-likely summer P&L is small in $ -- a few hundred, not 5 figures
    assert -5_000 < pnl.mean() < 5_000


def test_pnl_is_independent_of_bankroll_size():
    # The honesty thesis: capacity (not bankroll) caps dollars. simulate()
    # must NOT scale with BANKROLL -- $100k and $1M give the same P&L.
    rng1 = np.random.default_rng(7)
    a = P.simulate(P.SCENARIOS[2], 10_000, rng1)
    saved = P.BANKROLL
    try:
        P.BANKROLL = 1_000_000.0
        rng2 = np.random.default_rng(7)
        b = P.simulate(P.SCENARIOS[2], 10_000, rng2)
    finally:
        P.BANKROLL = saved
    assert np.allclose(a, b)


def test_bear_worse_than_bull():
    rng = np.random.default_rng(3)
    bear = P.simulate(P.SCENARIOS[0], 30_000, rng).mean()
    bull = P.simulate(P.SCENARIOS[2], 30_000, rng).mean()
    assert bear < bull


def test_run_returns_scenarios():
    out = P.run(n_sims=5_000)
    assert len(out) == 3
    for d in out.values():
        assert 0.0 <= d["p_profit"] <= 1.0
        assert "p_beat_rf" in d


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
