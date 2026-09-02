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


def test_implied_prob_above_one_is_rejected_not_devigged():
    # pi > 1 is not a price. It used to solve to a plausible-looking z and return
    # fair probabilities that summed to 1 and were silently wrong
    # (measured: p=[0.81745, 0.18255], z=0.734047, no error).
    try:
        shin_devig([1.1111, 0.4762])
        raise AssertionError("an implied prob > 1 must not be devigged")
    except ValueError:
        pass


def test_price_guards_are_raises_that_survive_python_O():
    # `python -O` strips asserts; the guard must be a raise or a corrupted book
    # devigs silently (measured under -O: shin_devig_decimal([0.9, 2.1]) returned
    # p=[0.81746, 0.18254], z=0.734065).
    import subprocess
    code = """import sys
sys.path.insert(0, %r)
from shin import shin_devig_decimal
try:
    shin_devig_decimal([0.9, 2.1])
except ValueError:
    print("GUARDED")
""" % _os.path.dirname(_os.path.abspath(__file__))
    out = subprocess.run([_sys.executable, "-O", "-c", code],
                         capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "GUARDED", (out.stdout, out.stderr)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} shin devig tests passed.")
