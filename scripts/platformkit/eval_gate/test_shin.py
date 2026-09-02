"""Tests for the Shin devig reference. numpy + stdlib only; runs standalone or via pytest."""
from __future__ import annotations
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # blueprint uses bare sibling imports; make them work under "python -m pytest" from the repo root too
import numpy as np
from shin import shin_devig, shin_devig_decimal, implied_from_decimal


def test_fair_book_unchanged():
    # no overround (B == 1) -> z == 0, probs unchanged
    p, z = shin_devig([0.5, 0.5])
    assert abs(z) < 1e-9
    assert np.allclose(p, [0.5, 0.5], atol=1e-9)


def test_symmetric_vig_splits_evenly():
    # -110/-110 style: implied [0.5238, 0.5238], B ~ 1.0476 -> fair [0.5, 0.5]
    p, z = shin_devig([0.5238, 0.5238])
    assert abs(p.sum() - 1.0) < 1e-9
    assert np.allclose(p, [0.5, 0.5], atol=1e-6)
    assert z > 0.0


def test_normalizes_and_orders_on_lopsided_book():
    # heavy favorite: implied [0.80, 0.30], B = 1.10
    p, z = shin_devig([0.80, 0.30])
    assert abs(p.sum() - 1.0) < 1e-9            # THE property the old formula failed
    assert p[0] > p[1]                          # favorite stays the favorite
    assert 0.0 < z < 1.0
    # Shin differs from naive multiplicative devig (pi/B) on lopsided books (FLB)
    mult = np.array([0.80, 0.30]) / 1.10
    assert not np.allclose(p, mult, atol=1e-3)


def test_three_way_soccer_sums_to_one():
    # home/draw/away implied summing to ~1.08 overround
    p, z = shin_devig([0.50, 0.30, 0.28])
    assert abs(p.sum() - 1.0) < 1e-9
    assert np.all(p > 0)


def test_decimal_helper_matches():
    p_dec, z_dec = shin_devig_decimal([1.91, 1.91])   # -110/-110 in decimal
    assert abs(sum(p_dec) - 1.0) < 1e-9
    assert np.allclose(p_dec, [0.5, 0.5], atol=1e-6)
    # implied_from_decimal sanity
    assert np.allclose(implied_from_decimal([2.0, 4.0]), [0.5, 0.25])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} shin devig tests passed.")
