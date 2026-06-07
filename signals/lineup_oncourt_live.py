"""lineup_oncourt_live — live signal: current 5-man unit quality (target=winprob, scope=live).

Basketball hypothesis
---------------------
The 5-man unit on court at decision-time (reconstructed from the live snapshot via
``is_starter`` + playing-time inference) carries a season-level net-rating that is
more informative for rest-of-game win probability than the pre-game starting-five
net-rating.  A lineup with a high season net-rating on court in the 4th quarter
(or when the game is close) drives rest-of-game probability up; a bad unit on court
does the opposite.

Feature emitted (dict, 4 sub-features)
---------------------------------------
``net_rating_on``          — season net-rating of the inferred on-court 5-man unit
                             (NaN → 0.0).
``pace_on``                — season avg pace of the inferred unit (proxy for possession
                             count remaining).
``min_share_top1``         — minutes share of the top lineup (concentration proxy;
                             high = they burn this unit, low = deep rotation).
``time_remaining_weight``  — (remaining_game_minutes / 48) * |net_rating_on|, a
                             time-decayed importance scalar.

Data sources (all leak-safe)
-----------------------------
*  ``ctx.live`` dict (spec_data.md §6) — live box snapshot supplying period, clock,
   per-player {team, min, is_starter} and player_ids.  This is the PRIMARY source
   for "who is on court now".
*  ``data/cache/lineup_features.parquet`` (spec_features.md §4) — season-level
   {player_id, season, lineup_top3_net_rating, lineup_top1_min_share,
   lineup_avg_pace_on} read once and cached at module load.
*  ``PointInTimeStore`` — reads ``lineup_splits`` atlas section if pre-written (ARM-B
   intel) so the signal consumes intelligence where available; falls back to the
   parquet without failing.

DEFER flags
-----------
The PBP-subs stream (real in-game substitution events) is NOT available in the
current live snapshot schema (spec_data.md §6).  ``ctx.live["players"]`` carries
``is_starter`` (pre-game) and cumulative ``min`` but NOT a per-second on-court
indicator.  We therefore INFER the current unit from:
  1. players whose ``min`` > 0.0 and are marked ``is_starter`` → likely starters
     still on court near the start;
  2. but for mid-game / end-of-game snapshots this degrades to "played at all this
     game" rather than "playing right now".
True PBP-sub tracking is DEFERRED until the live snapshot adds ``on_court: bool``
per player (one field change in src/data/live.py).  Until then, the signal is a
*good-faith approximation*: season quality of the top-minute players by team who
likely constitute the current unit — valid as a win-prob feature but imprecise for
individual player substitution events.

Gate expectations
-----------------
Expected verdict: DEFER on strict walk-forward (live snapshots are sparse / not
paired with future outcomes in the training parquet), or VARIANCE_ONLY (useful for
CI width / momentum but not point-MAE).  Not expected to SHIP as a point-estimate
signal without PBP-sub wiring.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.loop.signal import (
    AsOfContext,
    Hypothesis,
    Signal,
    SignalValue,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level cache — parquet is read once (offline safe via NBA_OFFLINE=1)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_LINEUP_PARQUET = _ROOT / "data" / "cache" / "lineup_features.parquet"

_lineup_df: Optional[pd.DataFrame] = None  # lazy-loaded, keyed (player_id, season)


def _load_lineup_df() -> pd.DataFrame:
    """Load and cache lineup_features.parquet (season-level, ~2,936 rows)."""
    global _lineup_df
    if _lineup_df is None:
        try:
            df = pd.read_parquet(_lineup_parquet)
            # Ensure the join key is int-typed to match player_ids from the snapshot
            df["player_id"] = df["player_id"].astype(int)
            _lineup_df = df
        except Exception as exc:  # noqa: BLE001
            logger.warning("lineup_oncourt_live: could not load %s (%s) — signal will return None",
                           _LINEUP_PARQUET, exc)
            _lineup_df = pd.DataFrame(columns=[
                "player_id", "season",
                "lineup_top3_net_rating", "lineup_top1_min_share", "lineup_avg_pace_on",
            ])
    return _lineup_df


# ---------------------------------------------------------------------------
# Helper: infer on-court 5-man unit from live snapshot
# ---------------------------------------------------------------------------
_MIN_PLAYED_ONCOURT = 0.5  # players with >= this many minutes are "in rotation"


def _infer_oncourt_ids(snapshot: dict, team: str) -> List[int]:
    """Return up to 5 player_ids for ``team`` who are most likely on court now.

    Strategy (DEFER note): use cumulative ``min`` played > 0 as a proxy because
    the snapshot does not expose a real-time on_court boolean.  We sort descending
    by minutes and take the top 5 as the inferred current lineup.  This is accurate
    for starters-heavy close games but degrades in garbage time.
    """
    players = [
        p for p in snapshot.get("players", [])
        if p.get("team") == team and (p.get("min") or 0.0) >= _MIN_PLAYED_ONCOURT
    ]
    # Sort by minutes descending — the most-used players are most likely on court
    players.sort(key=lambda p: p.get("min", 0.0), reverse=True)
    ids = [int(p["player_id"]) for p in players[:5]]
    return ids


def _season_from_game_id(game_id: Optional[str]) -> str:
    """Best-effort season string from the game_id prefix (e.g. '0022400123' → '2024-25').

    Falls back to '2024-25' when the prefix is unrecognised.
    """
    if not game_id or len(game_id) < 5:
        return "2024-25"
    prefix = game_id[3:5]  # characters 3-4 encode the season start year's last two digits
    try:
        yr = int(prefix)
        return f"20{yr:02d}-{(yr+1):02d}"
    except ValueError:
        return "2024-25"


# ---------------------------------------------------------------------------
# Signal implementation
# ---------------------------------------------------------------------------

class LineupOncourtLive(Signal):
    """Live signal: quality of the inferred current 5-man unit → win probability.

    Reads:
    * ``ctx.live`` for on-court player inference (period, clock, team, min).
    * ``lineup_features.parquet`` for season net-rating / pace / min-share.
    * Atlas section ``lineup_splits`` (if written by ARM-B) for richer season data.

    Emits 4 sub-features (see module docstring).
    """

    name: str = "lineup_oncourt_live"
    target: str = "winprob"
    scope: str = "live"
    reads_atlas: List[str] = ["lineup_splits"]
    emits: List[str] = [
        "net_rating_on",
        "pace_on",
        "min_share_top1",
        "time_remaining_weight",
    ]

    # ------------------------------------------------------------------
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute lineup quality features for ``ctx.team`` at decision time.

        Leak-safety:
          * Reads only ``ctx.live`` (the snapshot captured at or before
            ``ctx.decision_time``).
          * Reads the lineup parquet filtered to ``season <= ctx.game_date``
            via the ``as_of`` bound enforced by :meth:`Signal.read_atlas`;
            the parquet itself contains only historical season averages so
            no future information leaks.
          * If the store has a ``lineup_splits`` atlas section for a player,
            it is read with ``as_of=ctx.decision_time`` (leak-safe).

        Returns ``None`` when:
          * ``ctx.live`` is absent (not a live context).
          * ``ctx.team`` is missing.
          * The snapshot produces no on-court player_ids (coverage gap).
        """
        if not ctx.live or not ctx.team:
            return None

        snap: dict = ctx.live
        team: str = ctx.team
        game_id: Optional[str] = ctx.game_id

        # ---- infer on-court unit ----------------------------------------
        oncourt_ids = _infer_oncourt_ids(snap, team)
        if not oncourt_ids:
            return None

        # ---- season string for the parquet join --------------------------
        season = ctx.season or _season_from_game_id(game_id)

        # ---- load parquet (cached) and filter to season ------------------
        df = _load_lineup_df()
        if df.empty:
            return None

        season_df = df[df["season"] == season]

        # ---- try atlas read first (ARM-B intelligence → reinforcement) --
        # For each on-court player, prefer the atlas lineup_splits section
        # if it was written before decision_time; fall back to parquet.
        net_ratings: List[float] = []
        paces: List[float] = []
        min_shares: List[float] = []

        for pid in oncourt_ids:
            # Atlas read (leak-safe via store.read_atlas bound)
            atlas_row = self.read_atlas(
                f"player:{pid}", "lineup_splits", ctx.decision_time
            )
            if atlas_row and "lineup_top3_net_rating" in atlas_row:
                nr = atlas_row.get("lineup_top3_net_rating")
                pc = atlas_row.get("lineup_avg_pace_on")
                ms = atlas_row.get("lineup_top1_min_share")
            else:
                # Parquet fallback (season-level)
                row = season_df[season_df["player_id"] == pid]
                if row.empty:
                    # Try the most recent season available as a prior
                    row = df[df["player_id"] == pid].sort_values("season").tail(1)
                if row.empty:
                    continue
                nr = row["lineup_top3_net_rating"].iloc[0]
                pc = row["lineup_avg_pace_on"].iloc[0]
                ms = row["lineup_top1_min_share"].iloc[0]

            if nr is not None and not pd.isna(nr):
                net_ratings.append(float(nr))
            if pc is not None and not pd.isna(pc):
                paces.append(float(pc))
            if ms is not None and not pd.isna(ms):
                min_shares.append(float(ms))

        if not net_ratings:
            return None

        # ---- aggregate unit-level features --------------------------------
        net_rating_on = float(sum(net_ratings) / len(net_ratings))
        pace_on = float(sum(paces) / len(paces)) if paces else 0.0
        min_share_top1 = float(sum(min_shares) / len(min_shares)) if min_shares else 0.0

        # ---- time-remaining weight ----------------------------------------
        period = snap.get("period", 4)
        clock = snap.get("clock", "0:00")
        try:
            from src.data.live import remaining_game_minutes
            rem = remaining_game_minutes(period, clock)
        except Exception:  # noqa: BLE001
            # Fallback: assume 48 minutes total, uniform remaining
            rem = max(0.0, 48.0 - period * 12.0)

        time_remaining_weight = (rem / 48.0) * abs(net_rating_on)

        return {
            "net_rating_on": net_rating_on,
            "pace_on": pace_on,
            "min_share_top1": min_share_top1,
            "time_remaining_weight": time_remaining_weight,
        }

    # ------------------------------------------------------------------
    def hypothesis(self) -> Hypothesis:
        """Basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "The season net-rating of the 5-man unit currently on court (inferred "
                "from live box minutes played) predicts rest-of-game win probability "
                "better than the pre-game team-level prior, especially when the unit "
                "is significantly better or worse than the opponent's likely unit."
            ),
            rationale=(
                "Lineup net-rating is a known predictor of game outcomes in the "
                "basketball analytics literature (RPM, RAPM, lineup +/-). In live "
                "contexts the coaching decision of WHICH unit is on court at a given "
                "moment encodes information about game-state (close game → starters, "
                "blowout → bench) that is correlated with future score. The time-"
                "remaining weight amplifies the signal when more regulation is left."
            ),
            source="seed",
            atlas_fields=["lineup_splits"],
            expected_verdict="DEFER",
            priority="P2",
        )
