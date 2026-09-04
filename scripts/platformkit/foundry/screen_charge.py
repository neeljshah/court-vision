"""Screen-width accounting for one charged foundry verdict."""
from __future__ import annotations

import math


def k_increment(screened_n: int, charged_at_once: int = 1) -> int:
    """Return this charge's share of new screened hypotheses, floored at one.

    A screen width belongs to the family even if no candidate is promoted. When
    several verdicts are charged together, their ceiling-divided shares retain
    the full screen width rather than pricing each verdict as one hypothesis.
    """
    if isinstance(screened_n, bool) or isinstance(charged_at_once, bool):
        raise TypeError("screened_n and charged_at_once must be integers")
    if not isinstance(screened_n, int) or not isinstance(charged_at_once, int):
        raise TypeError("screened_n and charged_at_once must be integers")
    if charged_at_once < 1:
        raise ValueError("charged_at_once must be at least one")
    return max(1, int(math.ceil(max(0, screened_n) / charged_at_once)))
