"""clv_tracker.py — Pure CLV math: closing line value + EV delta.

Supports American odds, decimal odds, and implied-prob inputs.

Public API
----------
    american_to_prob(odds)                          -> float
    decimal_to_prob(decimal_odds)                   -> float
    vig_strip(prob_a, prob_b)                       -> tuple[float, float]
    compute_clv(taken_odds, closing_odds, stake,
                fmt)                                -> CLVResult
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple


OddsFormat = Literal["american", "decimal", "prob"]


# ── helpers ──────────────────────────────────────────────────────────────────

def american_to_prob(odds: float) -> float:
    """Convert American moneyline odds to raw implied probability (with vig).

    Parameters
    ----------
    odds:
        Positive (e.g. +150) or negative (e.g. -110) American odds.

    Returns
    -------
    float
        Implied probability in [0, 1].
    """
    if odds >= 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def decimal_to_prob(decimal_odds: float) -> float:
    """Convert decimal odds (European) to implied probability.

    Parameters
    ----------
    decimal_odds:
        Decimal representation, e.g. 1.909 for -110 American.

    Returns
    -------
    float
        Implied probability in (0, 1).
    """
    if decimal_odds <= 0:
        raise ValueError(f"decimal_odds must be positive, got {decimal_odds}")
    return 1.0 / decimal_odds


def vig_strip(prob_a: float, prob_b: float) -> Tuple[float, float]:
    """Remove vig from a two-sided market.

    Parameters
    ----------
    prob_a, prob_b:
        Raw implied probabilities for each side (sum > 1.0 due to vig).

    Returns
    -------
    tuple[float, float]
        Vig-free (no-vig) probabilities that sum to 1.0.
    """
    total = prob_a + prob_b
    if total <= 0:
        raise ValueError("prob_a + prob_b must be positive")
    return prob_a / total, prob_b / total


def _to_prob(value: float, fmt: OddsFormat) -> float:
    """Dispatch odds conversion."""
    if fmt == "american":
        return american_to_prob(value)
    if fmt == "decimal":
        return decimal_to_prob(value)
    # fmt == "prob" — already a probability
    if not (0.0 < value < 1.0):
        raise ValueError(f"Probability must be in (0, 1), got {value}")
    return value


# ── result dataclass ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CLVResult:
    """CLV computation output.

    Attributes
    ----------
    taken_prob:
        Implied probability at bet-take time (vig-inclusive raw).
    closing_prob:
        Implied probability at closing time (vig-inclusive raw).
    clv_pct:
        CLV percentage = (closing_prob - taken_prob) / taken_prob * 100.
        Positive = bet taken at better price than close (value).
    ev_delta_usd:
        Dollar EV improvement vs closing line = clv_pct/100 * stake.
    stake:
        Wager amount in USD.
    """
    taken_prob: float
    closing_prob: float
    clv_pct: float
    ev_delta_usd: float
    stake: float


# ── main function ─────────────────────────────────────────────────────────────

def compute_clv(
    taken_odds: float,
    closing_odds: float,
    stake: float,
    fmt: OddsFormat = "american",
) -> CLVResult:
    """Compute closing line value for a single bet.

    CLV % = (closing_prob - taken_prob) / taken_prob * 100.
    A positive CLV means the bet was taken at a better price than where the
    market settled, indicating edge vs the closing number.

    Parameters
    ----------
    taken_odds:
        The odds at which the bet was placed.
    closing_odds:
        The final closing-line odds for the same side.
    stake:
        Wager amount in USD.
    fmt:
        Odds format: "american" (default), "decimal", or "prob".

    Returns
    -------
    CLVResult
        taken_prob, closing_prob, clv_pct, ev_delta_usd, stake.

    Examples
    --------
    >>> r = compute_clv(-110, -120, 100.0)
    >>> r.clv_pct > 0          # bet taken at better price than close
    True
    >>> r = compute_clv(-110, -110, 50.0)
    >>> r.clv_pct              # zero CLV — closing == taken
    0.0
    """
    if stake <= 0:
        raise ValueError(f"stake must be positive, got {stake}")

    taken_prob = _to_prob(taken_odds, fmt)
    closing_prob = _to_prob(closing_odds, fmt)

    if taken_prob <= 0:
        raise ValueError("taken_prob computed as zero — check odds input")

    clv_pct = (closing_prob - taken_prob) / taken_prob * 100.0
    ev_delta_usd = (clv_pct / 100.0) * stake

    return CLVResult(
        taken_prob=taken_prob,
        closing_prob=closing_prob,
        clv_pct=round(clv_pct, 6),
        ev_delta_usd=round(ev_delta_usd, 4),
        stake=stake,
    )


def compute_clv_novig(
    taken_odds: float,
    closing_odds_a: float,
    closing_odds_b: float,
    stake: float,
    fmt: OddsFormat = "american",
) -> CLVResult:
    """Compute CLV against a vig-stripped closing line.

    Strips vig from the closing two-sided market before computing CLV,
    giving a fairer comparison against the true market probability.

    Parameters
    ----------
    taken_odds:
        Odds at bet placement.
    closing_odds_a:
        Closing odds for the side that was bet.
    closing_odds_b:
        Closing odds for the opposite side.
    stake:
        Wager amount in USD.
    fmt:
        Odds format: "american", "decimal", or "prob".

    Returns
    -------
    CLVResult
        CLV computed against vig-free closing probability.
    """
    taken_prob = _to_prob(taken_odds, fmt)
    raw_a = _to_prob(closing_odds_a, fmt)
    raw_b = _to_prob(closing_odds_b, fmt)
    novig_a, _ = vig_strip(raw_a, raw_b)

    if taken_prob <= 0:
        raise ValueError("taken_prob computed as zero")

    clv_pct = (novig_a - taken_prob) / taken_prob * 100.0
    ev_delta_usd = (clv_pct / 100.0) * stake

    return CLVResult(
        taken_prob=taken_prob,
        closing_prob=novig_a,
        clv_pct=round(clv_pct, 6),
        ev_delta_usd=round(ev_delta_usd, 4),
        stake=stake,
    )
