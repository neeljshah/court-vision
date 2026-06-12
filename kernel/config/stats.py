"""kernel.config.stats — StatSpec and SportStatRegistry.

Replaces the hardcoded 7-stat tuple scattered across 30+ modules (AUDIT gap #1).
Zero heavy imports: stdlib + typing + dataclasses only.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

StatKind = Literal["count", "continuous", "binary", "interval"]

_VALID_KINDS: frozenset[str] = frozenset({"count", "continuous", "binary", "interval"})

#: Additional meta-targets appended to stat names in loop_targets.
#: These are the non-stat targets the gate/orchestrator reason over.
_META_TARGETS: Tuple[str, ...] = ("minutes", "total", "winprob", "usage", "sigma")


# ---------------------------------------------------------------------------
# StatSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StatSpec:
    """Specification for a single trackable statistic.

    This is the kernel's authoritative descriptor for a stat.  All
    sport-specific numeric constants (sigma, calibration slope, …) live here
    so downstream kernel modules never embed a hardcoded dict.

    Parameters
    ----------
    name:
        Canonical key used everywhere (e.g. ``"pts"``, ``"passing_yards"``).
    kind:
        One of ``"count"``, ``"continuous"``, ``"binary"``, ``"interval"``.
        Routes the honest gate's scoring path:
        - ``count`` / ``continuous`` → MAE-family + RMSE+bias guard.
        - ``binary`` → Brier/log-loss path.
        - ``interval`` → VARIANCE_ONLY path (sigma/coverage, not point-estimate).
    display:
        Human-readable label (e.g. ``"Points"``, ``"Passing Yards"``).
    sigma_default:
        Fallback sigma for the decision engine when per-entity calibration is
        unavailable.  Was ``_STAT_SIGMA`` in ``decision_engine.py``.
    priced:
        Whether the stat appears in prop markets.  Drives ``priced_order()``.
    higher_is_better:
        Direction semantics for display and ranking.
    settle:
        Settlement source: ``"final"`` (post-OT official), ``"official_box"``,
        or ``"scoring_plays"`` (running sum of play-by-play scoring events).
    correlated_with:
        Tuple of other stat names to treat as correlated in the joint sim.
        Used as a hint only — the correlation matrix is domain-measured.
    calibration_fallback_slope:
        Per-stat fallback isotonic slope used when in-sample calibration is
        unavailable.  Was ``edge_calibration.FALLBACK_SLOPES``.
    """

    name: str
    kind: StatKind
    display: str
    sigma_default: float
    priced: bool = True
    higher_is_better: bool = True
    settle: Literal["final", "official_box", "scoring_plays"] = "official_box"
    correlated_with: Tuple[str, ...] = ()
    calibration_fallback_slope: Optional[float] = None

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"StatSpec.kind must be one of {sorted(_VALID_KINDS)!r}; "
                f"got {self.kind!r} for stat {self.name!r}"
            )


# ---------------------------------------------------------------------------
# SportStatRegistry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SportStatRegistry:
    """Ordered registry of all trackable stats for a sport.

    Replaces the hardcoded 7-stat tuple in 30+ modules (AUDIT gap #1).

    The insertion order of ``stats`` is load-bearing: array-positional code
    (routed-ensemble heads, correlation matrices, model pickle feature order)
    depends on it.  The NBA adapter declares stats in the historical tuple
    order ``(pts, reb, ast, fg3m, stl, blk, tov)`` and the byte-identical
    conformance test catches any drift.

    Parameters
    ----------
    sport_id:
        Canonical sport identifier, e.g. ``"nba"``, ``"nfl"``, ``"mlb"``.
    stats:
        Ordered ``{name: StatSpec}`` dict.  Python 3.7+ dicts preserve
        insertion order; the kernel relies on this contract.
    box_score_mapping:
        Source column → canonical name, e.g. ``{"PTS": "pts"}``.
    score_stat:
        Which stat IS the scoreboard (``"pts"`` for NBA/NFL,
        ``"runs"`` for MLB, ``"goals"`` for soccer).
    minutes_equiv:
        Name of the exposure-unit stat, or ``None`` if not tracked.
        NBA: ``"minutes"``; MLB: ``"plate_appearances"``; NFL: ``"snaps"``.
    """

    sport_id: str
    stats: Dict[str, StatSpec]
    box_score_mapping: Dict[str, str]
    score_stat: str
    minutes_equiv: Optional[str] = "minutes"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def target_names(self) -> Tuple[str, ...]:
        """Ordered tuple of stat names in insertion order.

        This is the stat-only portion of the loop's TARGETS constant.
        Example for NBA: ``("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")``.
        """
        return tuple(self.stats.keys())

    def priced_order(self) -> Tuple[str, ...]:
        """Ordered tuple of stat names where ``priced=True``.

        Was ``betting_portfolio._PROP_STATS_ORDER``.  Order is insertion order
        within ``stats``, filtered to priced stats only.
        """
        return tuple(s.name for s in self.stats.values() if s.priced)

    def spec(self, name: str) -> StatSpec:
        """Return the ``StatSpec`` for *name*.

        Raises ``KeyError`` if the stat is not registered.
        """
        return self.stats[name]

    @property
    def loop_targets(self) -> Tuple[str, ...]:
        """Full ordered target tuple consumed by the loop's gate and orchestrator.

        Equals ``target_names()`` concatenated with the fixed meta-targets
        ``("minutes", "total", "winprob", "usage", "sigma")``.

        For the NBA 7-stat registry this produces exactly::

            ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov",
             "minutes", "total", "winprob", "usage", "sigma")

        which is byte-identical to ``TARGETS`` at ``src/loop/signal.py:29-30``.
        """
        return self.target_names() + _META_TARGETS
