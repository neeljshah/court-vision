"""Per-file test: the leak-free as-of expanding-mean guarantee."""
from domains.basketball_nba.sim2.corpus import asof_series


def test_asof_is_leak_free():
    # k=0: each game's as-of == mean of STRICTLY PRIOR games (never sees itself)
    vals = [100.0, 200.0, 300.0]
    out = asof_series(vals, base=150.0, k=0.0)
    assert out[0] == 150.0          # no prior -> base
    assert out[1] == 100.0          # mean([100])
    assert out[2] == 150.0          # mean([100,200]) -- excludes the 300 itself


def test_asof_shrinks_to_base():
    # k large -> as-of pinned near base regardless of observed values
    out = asof_series([500.0, 500.0], base=100.0, k=1000.0)
    assert all(abs(v - 100.0) < 5.0 for v in out)


def test_asof_current_game_never_affects_its_own_value():
    # changing the LAST game's value must not change any earlier as-of value
    a = asof_series([110.0, 120.0, 130.0], base=115.0, k=3.0)
    b = asof_series([110.0, 120.0, 999.0], base=115.0, k=3.0)
    assert a[:2] == b[:2]           # earlier as-of identical; only index 2 could differ
    assert a[2] == b[2]             # index 2 depends only on games 0,1 -> also identical
