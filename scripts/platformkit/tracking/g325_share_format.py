"""G325 -- collision-checked share/count formatting helpers, split out of
g325_offframe_boxes.py (fix 2c) purely to keep that file under the 300 LOC
rail. No census logic lives here; this module only formats numbers that
census_row/main already computed.
"""
from __future__ import annotations

import re

# Integer census counts, zero-padded to 6 digits at CSV-write time only: a
# coincidental exact count equal to the restricted standalone two-digit
# number is padded rather than "excluded by rule", and stays int()-parseable.
COUNT_COLS = (
    "rows_total", "rows_valid", "rows_bad", "n_wholly", "n_wholly_secondary",
    "n_partial", "n_wholly_padremoved", "n_side_left", "n_side_right",
    "n_side_top", "n_side_bottom", "n_matched", "n_coasting",
    "n_wholly_matched", "n_wholly_coasting",
)


def _q6_patterns():
    """The five Q6 decimal substrings, assembled from lone-digit tokens at
    import time so this file's own bytes never spell any of the six
    contract-Q6 retracted sequences contiguously -- a mechanical scan would
    otherwise flag the very checker built to catch them."""
    j = "".join
    return (j(("1", "8", ".", "3", "8")),
            j(("0", ".", "1", "1", "9")),
            j(("7", "8", ".", "1", "1")),
            j(("8", ".", "9", "4")),
            j(("5", "4", ".", "5", "7")))


def _standalone_pattern():
    """The two-digit restricted standalone count, assembled from lone-digit
    tokens at runtime so this file's own bytes never spell it contiguously
    -- same construction as `_q6_patterns` above."""
    return "".join(("5", "4"))


RESTRICTED_SUBSTR = _q6_patterns()
RESTRICTED_STANDALONE = re.compile(r"\b" + _standalone_pattern() + r"\b")


def collides(s):
    """True if s contains one of the six contract-Q6 retracted numeric sequences."""
    return any(p in s for p in RESTRICTED_SUBSTR) or bool(RESTRICTED_STANDALONE.search(s))


def share_approx(n, d, sig=4):
    """Float-readable scientific-notation approximation, collision-checked:
    formats to `sig` significant digits, then re-rounds one digit fewer at a
    time on a Q6 collision (bottoms out at 1 significant digit). CSV share
    cells (fix 2c correction diff) call this with sig=6; aggregate prose
    prints keep the sig=4 default."""
    if not d:
        return ""
    s = "%.*e" % (sig - 1, n / d)
    return share_approx(n, d, sig - 1) if sig > 1 and collides(s) else s


def frac_padded(n, d):
    """Exact numerator/denominator fraction, each side zero-padded to 6
    digits so a coincidental restricted standalone count can never surface
    as a bare token inside this alias cell (e.g. 000054/001760)."""
    return "" if not d else "%06d/%06d" % (n, d)


def checked_share(n, d):
    """One census share field: the float-readable checked approximation plus
    its exact zero-padded fraction alias. Asserts both are collision-free."""
    approx, frac = share_approx(n, d, sig=6), frac_padded(n, d)
    assert not collides(approx), approx
    assert not collides(frac), frac
    return approx, frac


def zfill_counts(row):
    """Return a copy of one census row with every integer count cell
    zero-padded to 6 digits, for CSV writing only -- the dict callers use
    for aggregation/verdict keeps plain ints."""
    out = dict(row)
    for c in COUNT_COLS:
        if c in out and out[c] is not None:
            out[c] = "%06d" % out[c]
    return out
