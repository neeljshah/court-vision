"""Signal: usage_seesaw — teammate-OUT usage redistribution bump for PTS.

**Hypothesis**
When one or more teammates are OUT (DNP / ruled-out), the possessions they
would have consumed must be absorbed by the active roster. A player with an
above-average usage baseline captures a disproportionate share, producing a
pre-game PTS projection boost that the prop model cannot see (it trains each
player in isolation from same-game DNP counts).

Concretely: ``seesaw_score`` = (dnp_count_in_game - dnp_count_l5_avg) *
usage_baseline * SCALE. Positive scores indicate more-than-usual teammates
are absent today, implying extra possessions flow to this player.

**Data sources — REAL (no DEFER on primary)**
- ``data/cache/dnp_features_team.parquet``
    Grain ``(game_id, team_abbreviation, game_date)``.
    Cols used: ``dnp_count_in_game`` (known from injury report pre-game),
    ``dnp_count_l5_avg`` (rolling prior-game baseline — leak-safe).
    Built by ``scripts/build_dnp_features.py``; identical wrapper pattern
    used in ``prop_pergame.build_dnp_team_features``.

- ``data/cache/adv_stats_splits.parquet``
    Grain ``(player_id, game_id, game_date)``.
    Col used: ``adv_usage_season_to_date`` — expanding-window usage%
    computed from prior games only (pre-built, walk-forward safe).
    Falls back to 0.18 (league mean) when the player has no prior-game data.

**Atlas consumed (reinforcement loop)**
``player:<id>`` / section ``absence_impact`` — if a prior atlas build (e.g.
``intel/player_absence_impact.py``) has stored a player-specific
``usage_lift_per_dnp`` coefficient, it is blended in as a Bayesian prior to
shrink the generic seesaw calculation toward the observed per-player lift.
Graceful no-op when the store is empty (first build).

**Emits**
Dict signal with three sub-features:
  * ``dnp_excess``       — dnp_count_in_game minus the L5 rolling average
                           (signed; positive = unusual absences today).
  * ``usage_baseline``   — player's season-to-date usage% (float in [0, 1]).
  * ``seesaw_score``     — composite = clip(dnp_excess, 0, 4) * usage_baseline;
                           zero when the team has no unusual absences today.

**Gate expectations**
  - Expected verdict: SHIP for PTS (usage redistribution is well-established;
    the dnp_count_in_game is observable pre-game; prop markets underreact to
    multi-man injuries). May also SHIP for AST / REB as secondary targets.
  - Walk-forward: all 4 folds expected to improve — teammate absence events
    are distributed across all seasons in the parquet (2021-26).
  - NULL-SHUFFLE control: dnp_excess is event-driven (real signal) so it
    clears the null bar even when many rows are zero.
  - Ablation: orthogonal to L5/EWMA form (those average over DNP and non-DNP
    games equally). Also orthogonal to rest_b2b_fatigue.
  - Calibration: positive direction for PTS on positive dnp_excess days.
  - CLV: books shade injury-impacted lines, but with a lag for last-minute
    news; our pre-game model update may have a window advantage.

**DEFER notes**
None for the primary features — both parquets are present and populated.
The atlas read of ``absence_impact.usage_lift_per_dnp`` is opportunistic:
if the absence_impact atlas section (ARM-B) has not yet been built, the
signal degrades gracefully to the raw parquet calculation. This constitutes
a soft DEFER only on the reinforcement-blend sub-path; the base signal is
fully implemented.
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
_DNP_TEAM_PATH = _ROOT / "data" / "cache" / "dnp_features_team.parquet"
_ADV_SPLITS_PATH = _ROOT / "data" / "cache" / "adv_stats_splits.parquet"

# Fallback league-mean usage when no player-specific prior is available.
_LEAGUE_MEAN_USAGE: float = 0.18

# Cap on the DNP excess fed into the composite: more than 4 unusual absences
# in one game is pathological and we don't want to amplify unreliable math.
_MAX_DNP_EXCESS: float = 4.0

# Scale factor: chosen so a typical extra-DNP (dnp_excess=1) game for a
# 20%-usage player produces seesaw_score ≈ 0.20 (interpretable as "absorbs
# ~20% of 1 absent player's load"). No tuning at build time — the gate decides.
# (The gate sees this as a raw feature; XGB will learn the correct coefficient.)
_SCALE: float = 1.0

# Blend weight for the atlas prior (when present). 0.25 keeps the raw
# parquet calculation dominant while allowing the learned per-player lift
# to pull the estimate modestly toward the historical mean.
_ATLAS_BLEND: float = 0.25


# ---------------------------------------------------------------------------
# Module-level caches (loaded once per process)
# ---------------------------------------------------------------------------
_DnpLookup = Dict[Tuple[str, str], Dict[str, float]]
_AdvLookup = Dict[Tuple[int, str], float]   # (player_id, game_date_iso) -> usage

_DNP_LOOKUP_CACHE: Optional[_DnpLookup] = None
_ADV_LOOKUP_CACHE: Optional[_AdvLookup] = None


def _load_dnp_lookup(path: Path) -> _DnpLookup:
    """Load dnp_features_team.parquet into a (date_iso, team) -> dict map.

    Mirrors the ``_DnpTeamFeatures`` wrapper in ``prop_pergame.py`` but is
    self-contained so the signal runs without the full model stack.
    Returns an empty dict when the parquet is absent.
    """
    lookup: _DnpLookup = {}
    if not path.exists():
        return lookup
    try:
        import pandas as pd  # noqa: PLC0415

        df = pd.read_parquet(str(path))
        for _, row in df.iterrows():
            raw_date = row.get("game_date")
            date_iso = (
                raw_date.date().isoformat()
                if hasattr(raw_date, "date")
                else str(raw_date)[:10]
            )
            team = str(row.get("team_abbreviation", ""))
            if not date_iso or not team:
                continue

            def _f(col: str) -> float:
                v = row.get(col)
                try:
                    fv = float(v)
                    return fv if fv == fv else 0.0  # NaN check
                except (TypeError, ValueError):
                    return 0.0

            lookup[(date_iso, team)] = {
                "dnp_count_in_game": _f("dnp_count_in_game"),
                "dnp_count_l5_avg":  _f("dnp_count_l5_avg"),
            }
    except Exception:  # noqa: BLE001 — degrade to empty, neutral defaults used
        pass
    return lookup


def _load_adv_lookup(path: Path) -> _AdvLookup:
    """Load adv_stats_splits.parquet into a (player_id, date_iso) -> usage map.

    Only reads ``adv_usage_season_to_date`` (expanding window from prior games —
    pre-built walk-forward safe). Returns {} when the parquet is absent.
    """
    lookup: _AdvLookup = {}
    if not path.exists():
        return lookup
    try:
        import pandas as pd  # noqa: PLC0415

        df = pd.read_parquet(str(path), columns=["player_id", "game_date",
                                                  "adv_usage_season_to_date"])
        for _, row in df.iterrows():
            raw_date = row.get("game_date")
            date_iso = (
                raw_date.date().isoformat()
                if hasattr(raw_date, "date")
                else str(raw_date)[:10]
            )
            pid = row.get("player_id")
            val = row.get("adv_usage_season_to_date")
            if pid is None or not date_iso:
                continue
            try:
                fval = float(val)
                if fval != fval:  # NaN
                    continue
                lookup[(int(pid), date_iso)] = fval
            except (TypeError, ValueError):
                continue
    except Exception:  # noqa: BLE001
        pass
    return lookup


def _get_dnp_lookup() -> _DnpLookup:
    """Return the process-cached DNP lookup, loading once on first call."""
    global _DNP_LOOKUP_CACHE
    if _DNP_LOOKUP_CACHE is None:
        _DNP_LOOKUP_CACHE = _load_dnp_lookup(_DNP_TEAM_PATH)
    return _DNP_LOOKUP_CACHE


def _get_adv_lookup() -> _AdvLookup:
    """Return the process-cached advanced-splits lookup, loading once on first call."""
    global _ADV_LOOKUP_CACHE
    if _ADV_LOOKUP_CACHE is None:
        _ADV_LOOKUP_CACHE = _load_adv_lookup(_ADV_SPLITS_PATH)
    return _ADV_LOOKUP_CACHE


# ---------------------------------------------------------------------------
# The Signal class
# ---------------------------------------------------------------------------

class UsageSeesawSignal(Signal):
    """Usage-seesaw signal: teammate-OUT possession redistribution for PTS.

    Reads ``data/cache/dnp_features_team.parquet`` and
    ``data/cache/adv_stats_splits.parquet`` at build time (O(1) in-memory
    lookup after module-level warm-up).  Optionally blends in a per-player
    ``absence_impact.usage_lift_per_dnp`` coefficient from the store for
    Bayesian shrinkage (reinforcement loop).

    Returns ``None`` when the context lacks ``team``, ``player_id``, or
    ``game_date`` (neutral row — no redistribution info available).
    """

    name: str = "usage_seesaw"
    target: str = "pts"
    scope: str = "pregame"
    reads_atlas: List[str] = ["absence_impact"]
    emits: List[str] = ["dnp_excess", "usage_baseline", "seesaw_score"]

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute the leak-safe seesaw feature dict for one decision row.

        All reads are filtered to ``<= ctx.decision_time``:
        - The DNP parquet is keyed by ``game_date`` (same-day injury-report
          info, available pre-tipoff and therefore valid at pregame scope).
        - ``adv_usage_season_to_date`` is an expanding-window prior computed
          from games BEFORE this one (pre-built in the parquet).
        - The atlas read uses ``ctx.decision_time`` as the as-of bound so the
          store enforces no-leak on the reinforcement sub-path.

        Args:
            ctx: the :class:`AsOfContext` pinning the decision timestamp.

        Returns:
            Dict with keys ``dnp_excess, usage_baseline, seesaw_score``,
            or ``None`` if the required context fields are absent.
        """
        # Require team, player_id, and game_date to form all lookup keys.
        if not ctx.team or ctx.player_id is None or not ctx.game_date:
            return None

        date_iso = ctx.game_date  # already YYYY-MM-DD from AsOfContext

        # ---- 1. DNP team lookup (pre-game injury-report count) ---------------
        dnp_lk = _get_dnp_lookup()
        dnp_row = dnp_lk.get((date_iso, ctx.team), {})
        dnp_count = float(dnp_row.get("dnp_count_in_game", 0.0))
        dnp_l5 = float(dnp_row.get("dnp_count_l5_avg", 0.0))

        # dnp_excess: how many MORE teammates are out today vs the rolling norm.
        # Positive → unusual absences; negative → business as usual (≤ typical).
        dnp_excess = dnp_count - dnp_l5

        # ---- 2. Player usage baseline (season-to-date, leak-safe) ------------
        adv_lk = _get_adv_lookup()
        usage_baseline = adv_lk.get((ctx.player_id, date_iso),
                                    _LEAGUE_MEAN_USAGE)

        # ---- 3. Optional atlas blend (reinforcement loop) --------------------
        # If the absence_impact atlas section has a learned per-player
        # usage_lift_per_dnp coefficient, blend it toward that estimate.
        # Positive lift means this player historically absorbs extra possessions
        # when teammates are out; a zero or missing value is a no-op.
        atlas_lift_per_dnp: float = 0.0
        if self.store is not None:
            entity = f"player:{ctx.player_id}"
            atlas = self.store.read_atlas(
                "player", ctx.player_id, "absence_impact", ctx.decision_time
            )
            if isinstance(atlas, dict):
                raw_lift = atlas.get("usage_lift_per_dnp")
                if raw_lift is not None:
                    try:
                        atlas_lift_per_dnp = float(raw_lift)
                    except (TypeError, ValueError):
                        atlas_lift_per_dnp = 0.0

        # Blended baseline: mix raw parquet usage with the learned per-player lift.
        # blended_baseline ≈ (1 - α) * usage_baseline + α * atlas_lift_per_dnp
        # where α = _ATLAS_BLEND. When atlas_lift_per_dnp is 0.0, this is a no-op.
        blended_usage = (
            (1.0 - _ATLAS_BLEND) * usage_baseline
            + _ATLAS_BLEND * atlas_lift_per_dnp
        ) if atlas_lift_per_dnp != 0.0 else usage_baseline

        # ---- 4. Composite seesaw score ---------------------------------------
        # clip dnp_excess to [0, MAX] so negative excess (fewer absences than
        # usual) does not push the score negative — the downside case (teammates
        # BACK from injury) is a separate signal (not modelled here).
        clipped_excess = max(0.0, min(dnp_excess, _MAX_DNP_EXCESS))
        seesaw_score = clipped_excess * blended_usage * _SCALE

        return {
            "dnp_excess":    round(dnp_excess, 4),
            "usage_baseline": round(usage_baseline, 4),
            "seesaw_score":  round(seesaw_score, 4),
        }

    def hypothesis(self) -> Hypothesis:
        """Return the basketball hypothesis this signal tests."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "When one or more teammates are ruled OUT before tipoff, a "
                "player's expected PTS output increases in proportion to the "
                "number of unusual absences (dnp_count_in_game minus L5 "
                "rolling baseline) and their own usage% baseline. The "
                "seesaw_score feature captures this redistribution and "
                "improves PTS MAE in walk-forward evaluation against the "
                "full model."
            ),
            rationale=(
                "The prop model trains each player in isolation — it has no "
                "same-game DNP feature. When a high-usage teammate (e.g. a "
                "star on a minutes restriction or ruled-out with injury) is "
                "absent, the vacant possessions are absorbed by active "
                "roster members; historically this is proportional to each "
                "active player's prior usage rate. "
                "data/cache/dnp_features_team.parquet (12,156 team-game rows, "
                "2021-26) provides the in-game DNP count pre-game; "
                "adv_stats_splits.adv_usage_season_to_date provides the "
                "player-specific usage baseline from prior games only (no "
                "leak). The dnp_count_l5_avg rolling column lets us compute "
                "excess absences vs the team's typical injury burden, avoiding "
                "flagging chronic-DNP teams as unusual. "
                "Reinforcement: on SHIP, wiring writes a per-player learned "
                "coefficient back as absence_impact.usage_lift_per_dnp so "
                "future builds can shrink toward the observed per-player "
                "redistribution tendency."
            ),
            source="seed",
            atlas_fields=["absence_impact"],
            expected_verdict="SHIP",
            priority="P2",
        )
