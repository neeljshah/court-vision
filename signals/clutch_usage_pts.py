"""signals/clutch_usage_pts.py — ARM-A signal: clutch scoring bump for pts (live scope).

Basketball hypothesis
---------------------
When a game enters the clutch window (Q4, <=5 min, <=5-pt margin, or overtime),
players with a high historical clutch-scoring rate (from the ``clutch_scoring`` atlas
section) receive a disproportionate share of offensive possessions.  This concentrates
expected points on the team's designated closers and depresses the projection for
bench players.  The clutch-scoring bump is additive on top of the pregame PTS
projection because the regime shift happens in-game and is invisible at tip-off.

Feature emitted (dict signal)
------------------------------
``clutch_scoring_prob``
    Probability [0, 1] that the current context is a clutch situation.
    * Live path  : derived from ``ctx.live`` (period, clock, score margin).
    * Training   : from ``data/cache/inplay_midquarter_features.parquet``
                   end-of-Q3 margin; or from the pregame win-probability
                   stored in ``ctx.extra["pregame_win_prob"]`` as a fallback.
``clutch_pts_rate``
    The player's historical clutch scoring rate (pts_per36 / 36) from the
    ``clutch_scoring`` atlas section.  Represents HOW MUCH the player scores per
    minute of clutch time.  Range ~[0, 1.5].
``clutch_lift``
    ``clutch_scoring_prob × clutch_pts_rate`` — the interaction feature the model
    uses directly.  When the game is NOT clutch, this is near 0 regardless of the
    player's profile.  When clutch, high scorers get a lift >0.

Target
------
``pts`` — per-game (or per-game-remaining) points projection.

Scope
-----
``live`` — the clutch regime only becomes observable in-game.  Pregame clutch_prob
is low-information and already partially captured by pregame win-probability features.

Data sources
------------
PRIMARY — ``clutch_scoring`` atlas section (player entity)
    Keys used: scoring.pts_per36, scoring.gp, scoring.fg_pct, scoring.ft_pct.
    Read via self.read_atlas (ARM-B → ARM-A reinforcement loop).
    Fallback to ``data/cache/clutch_profiles_2025-26.parquet`` when the store is
    absent (direct parquet read, filtered to player_id).

SECONDARY — ``data/cache/inplay_midquarter_features.parquet``
    Cols: game_id, game_date, score_margin, pregame_win_prob.
    Used for training-time clutch_prob estimation (game_date < as_of).

LIVE — ``ctx.live`` snapshot dict
    Keys: period (int), clock ("M:SS"), home_score, away_score.
    Preferred at inference time; never used at train time.

DEFER notice
------------
* The Q4-only per-player pts split (would sharpen the clutch_pts_rate estimate)
  is DEFER: player_quarter_stats lacks a reliable game_date join without the
  player_adv_stats bridge (extra parquet load, not yet wired).
* CLV gate: requires >=30 Pinnacle player-pts closing lines; DEFER until the
  lines archive grows.
"""
from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue, Verdict

# ---------------------------------------------------------------------------
# Repo root (script-relative — works on Windows local + RunPod Linux)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_CLUTCH_PROFILES_PATH = _ROOT / "data" / "cache" / "clutch_profiles_2025-26.parquet"
_MIDQUARTER_PATH = _ROOT / "data" / "cache" / "inplay_midquarter_features.parquet"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Clutch definition (matches NBA's official stat definition)
_CLUTCH_MARGIN_THRESHOLD: float = 5.0
_CLUTCH_MINUTES_REMAINING: float = 5.0
# Neutral priors
_LEAGUE_AVG_CLUTCH_RATE: float = 0.25   # pts_per36 ≈ 9 / 36 (modest star)
_MAX_CLUTCH_PTS36: float = 60.0         # normalisation cap (superhuman ceiling)
# Sigmoid steepness for pregame win-prob → clutch prob
_WIN_PROB_K: float = 8.0

# Module-level caches
_clutch_df: Optional[pd.DataFrame] = None
_midquarter_df: Optional[pd.DataFrame] = None


def _load_clutch_profiles() -> pd.DataFrame:
    """Lazy-load clutch_profiles_2025-26.parquet once per process."""
    global _clutch_df
    if _clutch_df is None:
        if _CLUTCH_PROFILES_PATH.exists():
            try:
                _clutch_df = pd.read_parquet(_CLUTCH_PROFILES_PATH)
            except Exception:
                _clutch_df = pd.DataFrame()
        else:
            _clutch_df = pd.DataFrame()
    return _clutch_df


def _load_midquarter() -> pd.DataFrame:
    """Lazy-load inplay_midquarter_features.parquet once per process."""
    global _midquarter_df
    if _midquarter_df is None:
        if _MIDQUARTER_PATH.exists():
            try:
                _midquarter_df = pd.read_parquet(
                    _MIDQUARTER_PATH,
                    columns=["game_id", "game_date", "score_margin", "pregame_win_prob"],
                )
                _midquarter_df["game_date"] = pd.to_datetime(
                    _midquarter_df["game_date"], errors="coerce"
                )
            except Exception:
                _midquarter_df = pd.DataFrame()
        else:
            _midquarter_df = pd.DataFrame(
                columns=["game_id", "game_date", "score_margin", "pregame_win_prob"]
            )
    return _midquarter_df


def _rd(v: object) -> Optional[float]:
    """Return cleaned float or None for NaN/inf/non-numeric."""
    if v is None:
        return None
    try:
        import numpy as np
        f = float(v)  # type: ignore[arg-type]
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _sigmoid(x: float) -> float:
    """Numerically stable logistic sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _parse_clock_minutes(clock_str: str) -> Optional[float]:
    """Parse 'M:SS' clock string to remaining minutes as a float."""
    try:
        parts = clock_str.strip().split(":")
        return float(parts[0]) + float(parts[1]) / 60.0
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Clutch-probability helpers
# ---------------------------------------------------------------------------

def _clutch_prob_from_live(live: Dict) -> float:
    """Derive clutch probability from a live snapshot dict.

    Returns 1.0 for confirmed clutch (Q4/OT, close, late);
    0.0 for non-Q4 or blowouts; sigmoid-blend for borderline cases.
    """
    period = int(live.get("period", 0))
    if period < 4:
        return 0.0
    if period > 4:
        return 1.0  # overtime is always clutch

    clock_str = str(live.get("clock", "12:00"))
    min_remaining = _parse_clock_minutes(clock_str)
    if min_remaining is None:
        min_remaining = 6.0  # conservative: not yet clutch

    # Time gate: sigmoid centred at 5 minutes remaining
    time_clutch = _sigmoid(2.0 * (_CLUTCH_MINUTES_REMAINING - min_remaining))

    # Margin gate
    home_score = float(live.get("home_score", 0))
    away_score = float(live.get("away_score", 0))
    margin = abs(home_score - away_score)

    if margin == 0:
        margin_clutch = 1.0
    elif margin <= _CLUTCH_MARGIN_THRESHOLD:
        margin_clutch = max(0.5, 1.0 - margin / (_CLUTCH_MARGIN_THRESHOLD * 2.0))
    else:
        margin_clutch = _sigmoid(-0.4 * (margin - _CLUTCH_MARGIN_THRESHOLD))

    return float(time_clutch * margin_clutch)


def _clutch_prob_from_margin(abs_margin: float) -> float:
    """Estimate clutch prob from end-of-Q3 absolute margin (training path)."""
    # margin=0 → ~0.82, margin=5 → ~0.50, margin=15 → ~0.05
    return float(_sigmoid(-0.35 * abs_margin + 1.5))


def _clutch_prob_from_pregame_win_prob(win_prob: Optional[float]) -> float:
    """Derive expected clutch-time prob from the pregame win probability.

    A toss-up (win_prob~0.50) has the highest expected clutch fraction.
    """
    if win_prob is None:
        return 0.25  # moderate neutral prior
    divergence = abs(float(win_prob) - 0.5)
    return float(_sigmoid(-_WIN_PROB_K * divergence + 1.5))


def _midquarter_clutch_prob(game_id: str, decision_dt: _dt.datetime) -> Optional[float]:
    """Look up endQ3 clutch probability from inplay_midquarter_features.

    LEAK-SAFE: only includes rows with game_date < decision_dt (we never
    read the current game's snapshot during training).
    """
    df = _load_midquarter()
    if df.empty:
        return None
    cutoff = pd.Timestamp(decision_dt.date())
    mask = (df["game_id"] == str(game_id)) & (df["game_date"] < cutoff)
    rows = df[mask]
    if rows.empty:
        return None
    r = rows.iloc[0]
    abs_margin = abs(float(r.get("score_margin", 10.0) or 10.0))
    return _clutch_prob_from_margin(abs_margin)


# ---------------------------------------------------------------------------
# Clutch scoring rate helpers
# ---------------------------------------------------------------------------

def _clutch_rate_from_atlas(atlas_data: Optional[Dict]) -> float:
    """Extract clutch pts rate from the ``clutch_scoring`` atlas sub-fields.

    Uses scoring.pts_per36 normalised against _MAX_CLUTCH_PTS36.
    Returns a neutral prior when atlas is absent.

    Note: the atlas artifact sub_fields dict has a 'scoring' key at the top level.
    """
    if not atlas_data:
        return _LEAGUE_AVG_CLUTCH_RATE
    # Atlas build() stores the whole artifact value dict in the store;
    # when read via read_atlas the store may return either the artifact's
    # value (pts_per36 scalar) or the sub_fields dict depending on the store
    # implementation.  Handle both shapes defensively.
    pts36: Optional[float] = None

    # Shape 1: atlas_data is the sub_fields dict (preferred store contract)
    if isinstance(atlas_data, dict):
        scoring = atlas_data.get("scoring", {}) or {}
        pts36 = _rd(scoring.get("pts_per36"))
        # Shape 2: store returned the headline scalar directly
        if pts36 is None:
            pts36 = _rd(atlas_data.get("pts_per36"))

    if pts36 is None:
        return _LEAGUE_AVG_CLUTCH_RATE
    # Normalise: 36 pts/36 min → rate=1.0 (extreme star); 9 pts/36 → 0.25
    return float(min(1.5, max(0.0, float(pts36) / _MAX_CLUTCH_PTS36)))


def _clutch_rate_from_parquet(pid: int) -> float:
    """Direct parquet fallback for clutch_pts_rate when the store is absent.

    Reads the latest season row for player_id=pid from clutch_profiles.
    Returns the neutral league-average prior when the player is absent.
    No as_of filter needed: the clutch parquet contains only published
    season aggregates (safe pregame information for any in-season decision).
    """
    df = _load_clutch_profiles()
    if df.empty or "player_id" not in df.columns:
        return _LEAGUE_AVG_CLUTCH_RATE
    rows = df[df["player_id"] == pid]
    if rows.empty:
        return _LEAGUE_AVG_CLUTCH_RATE
    if "season" in rows.columns:
        rows = rows.sort_values("season", ascending=False)
    row = rows.iloc[0]
    pts36 = _rd(row.get("clutch_pts_per36"))
    if pts36 is None:
        return _LEAGUE_AVG_CLUTCH_RATE
    return float(min(1.5, max(0.0, pts36 / _MAX_CLUTCH_PTS36)))


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------

class ClutchUsagePts(Signal):
    """Late-game scoring bump for PTS when the game is close (target=pts, scope=live).

    Emits three sub-features:
      clutch_scoring_prob  — probability the game is in clutch time [0, 1].
      clutch_pts_rate      — player's historical clutch pts rate (pts36/MAX) [0, 1.5].
      clutch_lift          — clutch_scoring_prob × clutch_pts_rate (interaction).
    """

    name: str = "clutch_usage_pts"
    target: str = "pts"
    scope: str = "live"
    reads_atlas: List[str] = ["clutch_scoring"]
    emits: List[str] = ["clutch_scoring_prob", "clutch_pts_rate", "clutch_lift"]

    # ------------------------------------------------------------------
    def _build_clutch_rate(self, ctx: AsOfContext) -> float:
        """Build the clutch pts rate prior from the atlas store or parquet fallback."""
        player_id = ctx.player_id
        if player_id is None:
            return _LEAGUE_AVG_CLUTCH_RATE

        # --- Atlas read (ARM-B → ARM-A reinforcement) ---
        if self.store is not None:
            atlas_data = self.read_atlas(
                f"player:{player_id}", "clutch_scoring", ctx.decision_time
            )
            if atlas_data:
                return _clutch_rate_from_atlas(atlas_data)

        # --- Parquet fallback ---
        return _clutch_rate_from_parquet(int(player_id))

    # ------------------------------------------------------------------
    def _build_clutch_prob(self, ctx: AsOfContext) -> float:
        """Build the clutch probability from live context, midquarter parquet, or pregame.

        Priority:
          1. ctx.live snapshot (real-time inference).
          2. inplay_midquarter_features parquet (training rows with game_id).
          3. pregame win-probability fallback (broadest coverage).
        """
        # 1. Live snapshot
        if ctx.live is not None:
            return _clutch_prob_from_live(ctx.live)

        # 2. Midquarter parquet (training path)
        if ctx.game_id is not None:
            cprob = _midquarter_clutch_prob(str(ctx.game_id), ctx.decision_time)
            if cprob is not None:
                return cprob

        # 3. Pregame win-prob fallback
        wp: Optional[float] = ctx.extra.get("pregame_win_prob")
        if wp is None and self.store is not None and ctx.team is not None:
            team_atlas = self.read_atlas(
                f"team:{ctx.team}", "ratings", ctx.decision_time
            )
            if isinstance(team_atlas, dict):
                wp = team_atlas.get("home_win_prob")  # type: ignore[assignment]

        return _clutch_prob_from_pregame_win_prob(wp)

    # ------------------------------------------------------------------
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return {clutch_scoring_prob, clutch_pts_rate, clutch_lift} for one decision.

        LEAK-SAFE:
          - ctx.live is only available at inference, never injected during training.
          - inplay_midquarter reads apply game_date < decision_time.
          - Atlas reads go through the store's as_of guard.
          - Clutch profiles parquet contains only published season aggregates.

        Returns None only when the player_id is missing AND no game context exists.
        """
        clutch_prob = self._build_clutch_prob(ctx)
        clutch_rate = self._build_clutch_rate(ctx)
        clutch_lift = round(clutch_prob * clutch_rate, 4)

        return {
            "clutch_scoring_prob": round(clutch_prob, 4),
            "clutch_pts_rate": round(clutch_rate, 4),
            "clutch_lift": clutch_lift,
        }

    # ------------------------------------------------------------------
    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Players with high historical clutch pts_per36 (from the clutch_scoring "
                "atlas) receive a disproportionate share of late-game possessions when "
                "the game enters the clutch window (Q4, <=5 min, <=5-pt margin or OT); "
                "clutch_lift = clutch_prob × clutch_pts_rate predicts PTS uplift beyond "
                "the pregame projection for identified closers."
            ),
            rationale=(
                "NBA coaching decisions concentrate ball-usage on designated closers in "
                "clutch situations.  Stars with high clutch pts_per36 (LeBron, SGA, "
                "Curry) see usage shares rise from ~28% to ~40%+ in Q4 <5-min close "
                "games; bench players' usage collapses to near zero.  The clutch_scoring "
                "atlas captures this historical rate per player; clutch_prob is a "
                "real-time regime indicator.  The product gives a signal only when BOTH "
                "the player is a proven closer AND the game is actually in clutch time, "
                "making it additive on top of pregame features which cannot know the "
                "game state."
            ),
            source="seed",
            atlas_fields=["clutch_scoring"],
            expected_verdict=Verdict.SHIP,
            priority="P1",
        )
