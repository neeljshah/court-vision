"""Pure helpers for the G357 fix-1b census/reseal: base_game_id, competition label, even sampling.

Mirrors (byte-for-byte logic) the inline pod-side census script that reads the read-only ledger;
duplicated intentionally rather than shipped to the pod (no module scp before ACCEPT, contract B5).
"""
from __future__ import annotations

import re

BASKETBALL_SPORTS = {"nba", "wnba", "ncaa_basketball", "basketball"}
KNOWN_LEAGUE_PREFIXES = {
    "nbl", "euroleague", "gleague", "fiba", "lnb", "eurocup", "ncaaw", "acb", "cba", "bleague", "upco",
}
_SUFFIX = re.compile(r"_s\d+$")
_PREFIX = re.compile(r"^([A-Za-z]+)-")


def base_game_id(game_id: str) -> str:
    """Strip the trailing _s<offset> segment-clip suffix, leaving the base video id."""
    return _SUFFIX.sub("", game_id)


def competition_of(game_id: str, sport: str) -> str:
    """Return the finer league label when game_id carries a known prefix, else the ledger sport."""
    match = _PREFIX.match(game_id)
    if match and match.group(1).lower() in KNOWN_LEAGUE_PREFIXES:
        return match.group(1)
    return sport


def even_sample_indices(n: int, target: int = 30) -> list[int]:
    """Return 0-based indices spread evenly across a ledger-ordered eligible set of size n.

    n <= 40: every index (take ALL). Else step k = n // target starting at (n % target) // 2,
    yielding >= target indices spanning the full set (never a head slice).
    """
    if n <= 0:
        return []
    if n <= 40:
        return list(range(n))
    k = n // target
    start = (n % target) // 2
    return list(range(start, n, k))
