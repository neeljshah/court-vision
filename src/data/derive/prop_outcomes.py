"""
prop_outcomes.py — Pure derivation logic: join a prop_lines row to a box_scores row
and return the actual stat value plus over/under result.

Supported market keys (prop_lines.market):
    pts, reb, ast, stl, blk, threes_made, fg_made, ft_made
    pra  (pts + reb + ast)
    pr   (pts + reb)
    pa   (pts + ast)
    ra   (reb + ast)

Result values: "over" | "under" | "push" | "void"
"void" is returned when the player did not play (box_scores row missing or minutes == 0).
"""
from __future__ import annotations

from typing import Optional

# ── Stat extraction ───────────────────────────────────────────────────────────

# Map market key → list of box_scores column names to sum
_MARKET_COLUMNS: dict[str, list[str]] = {
    "pts":         ["points"],
    "reb":         ["rebounds"],
    "ast":         ["assists"],
    "stl":         ["steals"],
    "blk":         ["blocks"],
    "threes_made": ["fg3_made"],
    "fg_made":     ["fg_made"],
    "ft_made":     ["ft_made"],
    # compound markets
    "pra":         ["points", "rebounds", "assists"],
    "pr":          ["points", "rebounds"],
    "pa":          ["points", "assists"],
    "ra":          ["rebounds", "assists"],
}

# Tolerance for push detection (floating-point equality guard)
_PUSH_TOL = 1e-9


def _extract_stat(box: dict, columns: list[str]) -> Optional[float]:
    """
    Sum one or more box_scores column values.

    Args:
        box:     dict-like row from box_scores (keys = column names).
        columns: list of column names to sum.

    Returns:
        Summed value, or None if any required column is None.
    """
    total = 0.0
    for col in columns:
        val = box.get(col)
        if val is None:
            return None
        total += float(val)
    return total


def _is_dnp(box: Optional[dict]) -> bool:
    """Return True when the player did not play (row absent or minutes == 0)."""
    if box is None:
        return True
    minutes = box.get("minutes")
    if minutes is None:
        return True
    try:
        return float(minutes) == 0.0
    except (TypeError, ValueError):
        return True


# ── Public API ────────────────────────────────────────────────────────────────

def compute_outcome(
    prop_line: dict,
    box_score: Optional[dict],
) -> tuple[Optional[float], str]:
    """
    Derive the actual stat and over/under result for a single prop bet.

    Args:
        prop_line:  Row from prop_lines. Must have keys:
                    - ``market`` (str): one of the keys in _MARKET_COLUMNS.
                    - ``line``   (float): the prop line value (e.g. 24.5).
        box_score:  Row from box_scores for the same (game_id, player_id), or None
                    when the player did not appear in the box score.

    Returns:
        (actual_stat, result) where:
            actual_stat — float stat value, or None on void/missing data.
            result      — one of "over", "under", "push", "void".

    Raises:
        KeyError: if prop_line is missing 'market' or 'line'.
        ValueError: if market is not a recognised key.
    """
    market: str = prop_line["market"]
    line: float = float(prop_line["line"])

    if market not in _MARKET_COLUMNS:
        raise ValueError(f"Unknown market: {market!r}. Known: {sorted(_MARKET_COLUMNS)}")

    if _is_dnp(box_score):
        return None, "void"

    columns = _MARKET_COLUMNS[market]
    actual = _extract_stat(box_score, columns)  # type: ignore[arg-type]

    if actual is None:
        return None, "void"

    if abs(actual - line) <= _PUSH_TOL:
        return actual, "push"
    return actual, ("over" if actual > line else "under")


def resolve_result(
    market: str,
    line: float,
    box_score: Optional[dict],
) -> tuple[Optional[float], str]:
    """
    Convenience wrapper that accepts raw fields instead of a prop_lines dict.

    Args:
        market:    Market key string.
        line:      Prop line value.
        box_score: box_scores row dict, or None.

    Returns:
        (actual_stat, result) — same semantics as compute_outcome.
    """
    return compute_outcome({"market": market, "line": line}, box_score)
