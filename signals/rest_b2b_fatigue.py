"""Signal: rest_b2b_fatigue — back-to-back / travel fatigue penalty for PTS.

**Hypothesis**
Back-to-back legs and long road trips suppress offensive efficiency, especially
3P%, because cumulative fatigue impairs catch-and-shoot mechanics and reduces
aggressive rim-attack frequency.  A player on a B2B (zero rest days since the
prior game) averages ~1.2 fewer PTS and ~0.3 fewer 3PM vs matched non-B2B
outings after controlling for minutes and opponent.  The effect is larger for
high-volume scorers (usage% > 25%) and for the second leg of a road trip ending
at altitude (>4,000 ft above sea level).

**Data source — REAL (no DEFER)**
``data/rest_travel.parquet`` — grain ``(game_id, team_abbreviation, game_date)``.
Columns: ``is_b2b`` (float 0/1), ``is_b3b`` (float 0/1), ``miles_traveled``
(float, distance from prior game city), ``altitude_ft`` (float, destination
arena altitude in ft). Built by ``src/ingest/rest_travel.py``.  Keyed in memory
as ``(game_date_iso, team_abbreviation)`` for O(1) lookup — identical to the
``_RestTravel`` wrapper already used by ``prop_pergame.py``.

**Atlas consumed (reinforcement loop)**
``team:<tri>`` / section ``fatigue_profile`` — if a prior trained value has been
written back via ``wiring.write_back_atlas_field``, the stored
``b2b_pts_delta`` is blended with the raw parquet flags to Bayesian-shrink
toward the per-team historical B2B penalty.  Graceful no-op when the store is
empty (first build).

**Emits**
Dict signal with five sub-features:

  * ``is_b2b``        — 1.0 if zero-rest-days since prior game, else 0.0
  * ``is_b3b``        — 1.0 if the team played two days in a row before today
  * ``miles_traveled``— straight-line distance from prior game arena (miles)
  * ``altitude_ft``   — destination arena altitude (ft; 0 = sea-level)
  * ``fatigue_score`` — composite [0, 1]: 0.5*is_b2b + 0.2*is_b3b
                        + 0.2*(miles/3000).clip(0,1) + 0.1*(alt/5280).clip(0,1)

**Gate expectations**
  - Expected verdict: SHIP for the composite fatigue_score on PTS (B2B effect
    well-established in NBA literature; the parquet already exists, full coverage).
  - Walk-forward: all 4 folds expected to improve — the B2B suppression is
    consistent across seasons 2021-26.
  - NULL-SHUFFLE control: the binary B2B flag will clear the null bar.
  - Ablation: is_b2b adds independent signal beyond L5/EWMA form features
    (those roll over B2B and non-B2B games equally).
  - Calibration: direction is unambiguous (negative for PTS on B2B days).
  - CLV: sportsbooks shade B2B lines, but not always perfectly; the composite
    fatigue_score including altitude may yield a modest CLV edge.
  - VARIANCE_ONLY possible for the altitude sub-feature alone (small n of
    high-altitude games).

**DEFER note**
None for the primary parquet — all four columns are populated.  The
reinforcement-read of ``fatigue_profile`` from the atlas is opportunistic and
gracefully absent on a cold store.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Paths — script-relative ROOT (portable to RunPod Linux)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_REST_TRAVEL_PATH = _ROOT / "data" / "rest_travel.parquet"

# Composite weight constants (must sum to 1.0)
_W_B2B: float = 0.50
_W_B3B: float = 0.20
_W_MILES: float = 0.20
_W_ALT: float = 0.10

# Normalisation denominators for the continuous sub-features
_MILES_SCALE: float = 3000.0   # ~LAX→BOS (2,983 mi) — caps at 1.0 for max road trip
_ALT_SCALE: float = 5280.0     # 1 mile = 5,280 ft (Denver 5,280 ft → 1.0)

# Neutral / missing defaults (match prop_pergame._REST_TRAVEL_DEFAULTS)
_DEFAULTS: Dict[str, float] = {
    "is_b2b": 0.0,
    "is_b3b": 0.0,
    "miles_traveled": 0.0,
    "altitude_ft": 0.0,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_lookup(path: Path) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Load rest_travel.parquet into a (date_iso, team_abbrev) keyed dict.

    Returns an empty dict if the parquet is absent or cannot be parsed.
    Replicates the pattern in ``prop_pergame.build_rest_travel`` so the
    signal is self-contained and runnable without the full model stack.
    """
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    if not path.exists():
        return lookup
    try:
        import pandas as pd  # noqa: PLC0415 (lazy import — keep import surface minimal)
        df = pd.read_parquet(str(path))
        for _, row in df.iterrows():
            key = (str(row["game_date"]), str(row["team_abbreviation"]))
            lookup[key] = {
                "is_b2b":         float(row.get("is_b2b", 0.0) or 0.0),
                "is_b3b":         float(row.get("is_b3b", 0.0) or 0.0),
                "miles_traveled": float(row.get("miles_traveled", 0.0) or 0.0),
                "altitude_ft":    float(row.get("altitude_ft", 0.0) or 0.0),
            }
    except Exception:  # noqa: BLE001 — degrade silently, neutral defaults used
        pass
    return lookup


def _fatigue_score(is_b2b: float, is_b3b: float,
                   miles: float, alt_ft: float) -> float:
    """Composite fatigue score in [0, 1].

    Weighted sum: 0.5*B2B + 0.2*B3B + 0.2*(miles/3000)↑1 + 0.1*(alt/5280)↑1
    Higher score → more fatigue → expected negative marginal effect on PTS.
    """
    miles_norm = min(miles / _MILES_SCALE, 1.0)
    alt_norm = min(alt_ft / _ALT_SCALE, 1.0)
    return (
        _W_B2B * is_b2b
        + _W_B3B * is_b3b
        + _W_MILES * miles_norm
        + _W_ALT * alt_norm
    )


# Module-level cache so the parquet is read once per process (not per row)
_LOOKUP_CACHE: Optional[Dict[Tuple[str, str], Dict[str, float]]] = None


def _get_lookup() -> Dict[Tuple[str, str], Dict[str, float]]:
    """Return the process-cached lookup, loading once on first call."""
    global _LOOKUP_CACHE
    if _LOOKUP_CACHE is None:
        _LOOKUP_CACHE = _load_lookup(_REST_TRAVEL_PATH)
    return _LOOKUP_CACHE


# ---------------------------------------------------------------------------
# The Signal class
# ---------------------------------------------------------------------------

class RestB2bFatigueSignal(Signal):
    """Back-to-back / road-trip fatigue penalty signal (target=pts, scope=pregame).

    Reads ``data/rest_travel.parquet`` at build time (O(1) in-memory lookup
    after module-level warm-up).  Optionally blends in a previously learned
    per-team B2B delta from the store for Bayesian shrinkage (reinforcement loop).

    Emits a dict of five sub-features (see module docstring).  Returns ``None``
    when neither ``ctx.team`` nor ``ctx.game_date`` is available (neutral row).
    """

    name: str = "rest_b2b_fatigue"
    target: str = "pts"
    scope: str = "pregame"
    reads_atlas: List[str] = ["fatigue_profile"]
    emits: List[str] = [
        "is_b2b",
        "is_b3b",
        "miles_traveled",
        "altitude_ft",
        "fatigue_score",
    ]

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute the leak-safe rest/travel feature dict for one decision row.

        Only uses rows from ``rest_travel.parquet`` matching ``ctx.game_date``
        and ``ctx.team`` — i.e. the game-day record for the player's team.  The
        parquet itself is point-in-time (built from NBA schedule data available
        before each game).  No ``datetime.utcnow()`` call is made here.

        Args:
            ctx: the :class:`AsOfContext` pinning the decision timestamp + team.

        Returns:
            Dict with keys ``is_b2b, is_b3b, miles_traveled, altitude_ft,
            fatigue_score``, or ``None`` when team/date is not available.
        """
        # Need at least team and game_date to form the lookup key
        if not ctx.team or not ctx.game_date:
            return None

        # ---- 1. Parquet lookup (primary data source) -------------------------
        lookup = _get_lookup()
        raw = dict(lookup.get((ctx.game_date, ctx.team), _DEFAULTS))

        is_b2b = raw["is_b2b"]
        is_b3b = raw["is_b3b"]
        miles = raw["miles_traveled"]
        alt_ft = raw["altitude_ft"]

        # ---- 2. Optional atlas blend (reinforcement loop) --------------------
        # If the store holds a previously learned per-team b2b_pts_delta, we
        # absorb it as a pseudo-observation that adjusts the fatigue_score via
        # a mild Bayesian correction.  The correction is additive and capped
        # so it cannot flip the direction of the signal.
        store_correction: float = 0.0
        if self.store is not None and ctx.team:
            atlas = self.store.read_atlas(
                "team", ctx.team, "fatigue_profile", ctx.decision_time
            )
            if isinstance(atlas, dict):
                b2b_delta = atlas.get("b2b_pts_delta")  # expected negative float
                if b2b_delta is not None:
                    try:
                        # Scale the stored delta to a [−0.1, +0.1] correction
                        # on fatigue_score so the composite stays in [0, 1].
                        delta_f = float(b2b_delta)
                        # Conservative: cap the influence at ±10pp of score
                        store_correction = max(-0.1, min(0.1, -delta_f / 20.0))
                    except (TypeError, ValueError):
                        pass

        # ---- 3. Composite score ----------------------------------------------
        score = _fatigue_score(is_b2b, is_b3b, miles, alt_ft)
        # Clamp after reinforcement correction
        score = max(0.0, min(1.0, score + store_correction))

        return {
            "is_b2b": is_b2b,
            "is_b3b": is_b3b,
            "miles_traveled": miles,
            "altitude_ft": alt_ft,
            "fatigue_score": score,
        }

    def hypothesis(self) -> Hypothesis:
        """Return the basketball hypothesis this signal tests."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "NBA players on back-to-back (zero-rest) nights score ~1.2 fewer "
                "PTS on average vs matched non-B2B outings; the suppression is "
                "amplified by long travel (>1,500 miles) and high-altitude venues "
                "(≥4,000 ft). A composite fatigue_score combining B2B flag, B3B "
                "flag, miles traveled, and venue altitude improves PTS MAE in "
                "walk-forward evaluation against the full model."
            ),
            rationale=(
                "Back-to-back scheduling creates accumulated fatigue that impairs "
                "catch-and-shoot mechanics (reducing 3P%) and discourages aggressive "
                "rim attacks. The rest_travel.parquet (12,156 team-game rows, "
                "2021-26) provides the B2B/B3B flags and travel distance pre-game. "
                "Altitude suppresses VO2 max and reduces FT rate. Current L5/EWMA "
                "form features average over B2B and non-B2B nights equally and "
                "cannot model the scheduling-specific penalty — this signal provides "
                "the missing orthogonal dimension. Reinforcement loop: on SHIP, "
                "wiring writes per-team b2b_pts_delta back to the store so future "
                "builds can shrink toward the learned team-specific estimate."
            ),
            source="seed",
            atlas_fields=["fatigue_profile"],
            expected_verdict="SHIP",
            priority="P2",
        )
