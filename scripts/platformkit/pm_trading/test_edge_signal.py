"""Per-file tests for edge_signal.py (devig + edge mapping).

Run: python -m pytest scripts/platformkit/pm_trading/test_edge_signal.py -q
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import edge_signal as S  # noqa: E402
from venues.base import Side  # noqa: E402


def test_american_conversion():
    assert abs(S.implied_from_american(-110) - 110.0 / 210.0) < 1e-9
    assert abs(S.implied_from_american(+150) - 100.0 / 250.0) < 1e-9
    assert abs(S.implied_from_american(+100) - 0.5) < 1e-9


def test_decimal_conversion():
    assert abs(S.implied_from_decimal(2.0) - 0.5) < 1e-9
    assert abs(S.implied_from_decimal(4.0) - 0.25) < 1e-9


def test_multiplicative_devig_sums_to_one():
    p = S.devig([0.55, 0.52])  # overround 1.07
    assert abs(sum(p) - 1.0) < 1e-12
    assert abs(p[0] - 0.55 / 1.07) < 1e-9


def test_shin_devig_sums_to_one_and_bounded():
    p = S.devig([0.55, 0.52], method="shin")
    assert abs(sum(p) - 1.0) < 1e-9
    assert all(0.0 < x < 1.0 for x in p)


def test_shin_balanced_book_is_symmetric():
    p = S.devig([0.53, 0.53], method="shin")
    assert abs(p[0] - 0.5) < 1e-6 and abs(p[1] - 0.5) < 1e-6


def test_shin_multiway_sums_to_one():
    p = S.devig([0.40, 0.36, 0.34], method="shin")  # 3-way, overround
    assert abs(sum(p) - 1.0) < 1e-9
    assert all(0.0 < x < 1.0 for x in p)


def test_devig_two_way_american():
    # -110 / -110 -> 0.5 after devig
    assert abs(S.devig_two_way_american(-110, -110) - 0.5) < 1e-9


def test_devig_rejects_bad_input():
    for bad in ([0.5], [0.5, 0.0], [0.5, -0.1]):
        try:
            S.devig(bad)
            assert False, "should reject %r" % (bad,)
        except ValueError:
            pass


def test_build_signal_buy_side_positive_edge():
    sig = S.build_signal("M", fair_prob=0.62, market_price=0.55)
    assert sig.side == Side.BUY
    assert sig.edge == 0.07
    assert sig.edge_bps == 700.0


def test_build_signal_sell_side_negative_edge():
    sig = S.build_signal("M", fair_prob=0.40, market_price=0.55)
    assert sig.side == Side.SELL
    assert sig.edge_bps == -1500.0


def test_consensus_edge_and_agreement():
    # model and book both above price -> agree
    sig = S.build_signal("M", fair_prob=0.62, market_price=0.55, devig_prob=0.58)
    assert sig.consensus_edge_bps == 300.0
    assert sig.agrees_with_consensus() is True
    # model above, book below price -> disagree (yellow flag)
    sig2 = S.build_signal("M", fair_prob=0.62, market_price=0.55, devig_prob=0.50)
    assert sig2.agrees_with_consensus() is False
    # no book supplied -> trivially agrees
    assert S.build_signal("M", 0.62, 0.55).agrees_with_consensus() is True


def test_build_signal_rejects_out_of_range():
    for fp, mp in ((1.2, 0.5), (0.5, -0.1), (-0.1, 0.5)):
        try:
            S.build_signal("M", fp, mp)
            assert False
        except ValueError:
            pass


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
