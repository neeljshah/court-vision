"""signals/clutch_regime.py — ARM-A signal: clutch regime usage concentrator.

Basketball hypothesis
---------------------
Close-and-late situations (Q4 with margin <= 5 pts, <= 5 min remaining, or any
overtime period) concentrate playing-time and ball-usage on the team's top players.
Stars who already have high clutch-usage rates (from the ``clutch`` atlas section)
receive even larger usage bumps; bench players see their usage/minutes collapse.
This makes ``usagepercentage`` (and, transitively, PTS/AST) predictable in the
close-and-late regime beyond what the pregame projection captures.

Feature emitted (dict signal, 2 sub-features)
----------------------------------------------
``clutch_regime__clutch_prob``
    Float [0, 1].  Probability that the current game context is a clutch situation:
    * Live scope: derived from the live snapshot (period, clock, score margin).
    * Pregame scope: expected clutch probability derived from the pregame win-prob
      (close game → toss-up → higher expected clutch-time fraction).
    * Training (no live context): derived from inplay_midquarter_features.parquet
      end-of-Q3 margin (abs(score_margin) <= 5) or PBP clutch-shots-L5 history.

``clutch_regime__clutch_usage_prior``
    Float [0, 1].  The player's historical clutch usage rate, read from the
    ``clutch`` atlas section (``clutch_pts_per36 / 36`` → usage proxy) OR derived
    from ``pbp_clutch_shots_l5_avg`` as a direct clutch shot-rate prior.
    Represents HOW MUCH the player's usage concentrates in clutch situations.

Target
------
``usage`` — usagepercentage from the per-game advanced stats.  Clutch regime is a
direct driver of in-game usage for star players; bench players have near-zero clutch
usage.  This signal also correlates with PTS and AST as secondary effects, but
``usage`` is the cleanest and most direct causal surface.

Scope
-----
``live`` — clutch regime requires game context (period, score margin, time remaining).
At pregame time the clutch-prob is low-information (bounded by win-probability
divergence); the signal's primary value is in-game when the regime is known.

Data sources (REAL, no DEFER for primary path)
----------------------------------------------
PRIMARY — pbp_possession_features_l5.parquet
    Grain (player_id, game_id, game_date).
    Cols: pbp_clutch_shots_l5_avg — rolling L5 walk-forward average of clutch
    shots attempted.  Used as the clutch engagement prior.
    Path: data/cache/pbp_possession_features_l5.parquet  (41,827 rows, real).

SECONDARY — player_adv_stats.parquet
    Grain (player_id, game_id, game_date).
    Cols: usagepercentage, minutes.
    Path: data/player_adv_stats.parquet  (77,728 rows, real).
    Used to join game_date onto quarter_stats when building training features.

TERTIARY — data/cache/inplay_midquarter_features.parquet
    Grain (game_id, game_date, season).
    Cols: score_margin, q4_lead_changes_so_far, pregame_win_prob.
    Used for end-of-Q3 score margin as a clutch-prob signal in training rows.
    2,505 rows (real, endQ3 grain).

ATLAS — ``clutch`` section (profile factory, player)
    Keys: clutch_pts_per36, clutch_fg_pct, clutch_gp, clutch_plus_minus.
    Read via self.read_atlas("player:<pid>", "clutch", ctx.decision_time).
    Provides the player's historical clutch engagement prior.

LIVE — ctx.live snapshot dict (src.data.live schema)
    Keys: period (int), clock ("M:SS"), home_score, away_score,
    home_team, away_team, players[*].{team, min}.
    Preferred source at inference time; never read at train time.

DEFER notice
------------
* player_quarter_stats.parquet lacks a game_date column; joining through
  player_adv_stats (game_id -> game_date) is feasible but adds a join step that
  the gate's walk-forward splitter handles via game_date in the training matrix.
  For now, the Q4 usage uplift (per-quarter slice of usagepercentage) is DEFERRED
  — the signal uses the per-game usagepercentage as its target and the clutch_prob
  as a feature, not a post-hoc Q4 filter.
* pbp_clutch_shots_l5_avg L5 coverage is ~41,827/77,728 rows (~54 % of adv_stats
  rows).  Missing rows default to a league-average clutch rate of 0.9 shots/game.
* Clutch atlas section populated for 1,249 players; any un-profiled player receives
  a neutral clutch_usage_prior of 0.18 (league-average usagepercentage).
* Historical clutch-prob from inplay_midquarter_features covers ~2,505 games (endQ3
  snapshots only, not per-player).  Coverage grows as the store accumulates.
"""
from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue, Verdict

# ---------------------------------------------------------------------------
# Repo root — script-relative; never hardcode the Windows path (RunPod compat)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent

_PBP_L5_PATH = _ROOT / "data" / "cache" / "pbp_possession_features_l5.parquet"
_ADV_STATS_PATH = _ROOT / "data" / "player_adv_stats.parquet"
_MIDQUARTER_PATH = _ROOT / "data" / "cache" / "inplay_midquarter_features.parquet"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Clutch definition: abs margin <= this value with enough time remaining
_CLUTCH_MARGIN_THRESHOLD: float = 5.0
# Q4 minutes remaining that constitute "late" (NBA official clutch = last 5 min)
_CLUTCH_MINUTES_REMAINING: float = 5.0
# League-average usagepercentage (neutral prior for players with no atlas)
_LEAGUE_AVG_USAGE: float = 0.182
# League-average clutch shots per game (PBP L5 prior for unlisted players)
_LEAGUE_AVG_CLUTCH_SHOTS: float = 0.9
# Sigmoid steepness for clutch-prob from pregame win-prob divergence
_WIN_PROB_K: float = 8.0
# Maximum pts_per36 a clutch scorer achieves (normalisation cap for prior)
_MAX_CLUTCH_PTS36: float = 60.0

# ---------------------------------------------------------------------------
# Module-level parquet caches (populated once per process, lazy)
# ---------------------------------------------------------------------------
_pbp_l5_df: Optional[pd.DataFrame] = None
_midquarter_df: Optional[pd.DataFrame] = None


def _load_pbp_l5() -> pd.DataFrame:
    """Lazy-load pbp_possession_features_l5 (clutch shots L5 rolling average)."""
    global _pbp_l5_df
    if _pbp_l5_df is None:
        if _PBP_L5_PATH.exists():
            _pbp_l5_df = pd.read_parquet(
                _PBP_L5_PATH,
                columns=["player_id", "game_id", "game_date", "pbp_clutch_shots_l5_avg"],
            )
            _pbp_l5_df["game_date"] = pd.to_datetime(
                _pbp_l5_df["game_date"], errors="coerce"
            )
        else:
            _pbp_l5_df = pd.DataFrame(
                columns=["player_id", "game_id", "game_date", "pbp_clutch_shots_l5_avg"]
            )
    return _pbp_l5_df


def _load_midquarter() -> pd.DataFrame:
    """Lazy-load inplay_midquarter_features (end-of-Q3 score margin)."""
    global _midquarter_df
    if _midquarter_df is None:
        if _MIDQUARTER_PATH.exists():
            _midquarter_df = pd.read_parquet(
                _MIDQUARTER_PATH,
                columns=["game_id", "game_date", "score_margin", "pregame_win_prob",
                         "q4_lead_changes_so_far"],
            )
            _midquarter_df["game_date"] = pd.to_datetime(
                _midquarter_df["game_date"], errors="coerce"
            )
        else:
            _midquarter_df = pd.DataFrame(
                columns=["game_id", "game_date", "score_margin", "pregame_win_prob",
                         "q4_lead_changes_so_far"]
            )
    return _midquarter_df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _clutch_prob_from_live(live: Dict) -> float:
    """Derive clutch probability [0, 1] from a live snapshot dict.

    Returns 1.0 when clearly in clutch time (Q4/OT, close, late);
    0.0 for non-Q4 or blowouts; intermediate values for borderline cases.
    """
    period = int(live.get("period", 0))
    # Only Q4 and OT are clutch-eligible
    if period < 4:
        return 0.0

    # Overtime is always clutch
    if period > 4:
        return 1.0

    # Q4: check clock and margin
    clock_str = str(live.get("clock", "12:00"))
    min_remaining = _parse_clock_minutes(clock_str)
    if min_remaining is None:
        min_remaining = 6.0  # default: not yet clutch

    # Soft gate on time: sigmoid centred at 5 min remaining
    time_clutch = _sigmoid(2.0 * (_CLUTCH_MINUTES_REMAINING - min_remaining))

    # Score margin gate
    home_score = float(live.get("home_score", 0))
    away_score = float(live.get("away_score", 0))
    margin = abs(home_score - away_score)

    if margin == 0:
        margin_clutch = 1.0
    elif margin <= _CLUTCH_MARGIN_THRESHOLD:
        margin_clutch = 1.0 - (margin / (_CLUTCH_MARGIN_THRESHOLD * 2.0))
        margin_clutch = max(0.5, margin_clutch)
    else:
        # Soft decay: 6→0.4, 10→0.2, 15+→~0.0
        margin_clutch = _sigmoid(-0.4 * (margin - _CLUTCH_MARGIN_THRESHOLD))

    return float(time_clutch * margin_clutch)


def _clutch_prob_from_margin(abs_margin: float, lead_changes: float = 0.0) -> float:
    """Estimate clutch probability from an end-of-Q3 margin (training path).

    Close margin → high clutch probability; blowout → near zero.
    """
    # Sigmoid centred at 0, steep: margin=0 → 0.80, margin=5 → 0.50, margin=10 → 0.15
    base = _sigmoid(-0.35 * abs_margin + 1.5)
    # Lead changes boost: > 3 lead changes in Q4 so far signals contested game
    lead_boost = min(0.15, lead_changes * 0.05)
    return float(min(1.0, base + lead_boost))


def _clutch_prob_from_pregame_win_prob(win_prob: Optional[float]) -> float:
    """Derive expected clutch-time probability from the pregame win probability.

    A toss-up game (win_prob ~0.50) has the highest expected clutch fraction.
    A lopsided game (win_prob near 0 or 1) has lower expected clutch fraction.
    Uses |win_prob - 0.5| as the divergence measure.
    """
    if win_prob is None:
        return 0.25  # moderate prior
    divergence = abs(float(win_prob) - 0.5)
    # divergence=0 → prob=0.50; divergence=0.5 → prob~0.02
    return float(_sigmoid(-_WIN_PROB_K * divergence + 1.5))


def _clutch_usage_prior_from_atlas(atlas_data: Optional[Dict]) -> float:
    """Extract a [0, 1] clutch-usage prior from the player's 'clutch' atlas section.

    Uses clutch_pts_per36 as a proxy for clutch ball-usage concentration,
    normalised against _MAX_CLUTCH_PTS36.  A star with clutch_pts_per36=50
    gets a prior of ~0.83; a bencher with 0 gets 0.0.
    """
    if not atlas_data:
        return _LEAGUE_AVG_USAGE
    pts_per36 = atlas_data.get("clutch_pts_per36")
    if pts_per36 is not None:
        try:
            return float(min(1.0, float(pts_per36) / _MAX_CLUTCH_PTS36))
        except (TypeError, ValueError):
            pass
    return _LEAGUE_AVG_USAGE


def _clutch_shots_l5_prior(player_id: int, game_date: _dt.datetime) -> Optional[float]:
    """Return the rolling L5 clutch-shots-attempted average for a player as-of game_date.

    LEAK-SAFE: only rows with pbp_l5 game_date STRICTLY before the decision date
    are eligible (the L5 average itself is already lag-safe by construction, but
    we add a date guard here so we never use same-game data).
    """
    df = _load_pbp_l5()
    if df.empty:
        return None
    cutoff = pd.Timestamp(game_date.date()) if isinstance(game_date, _dt.datetime) else pd.Timestamp(game_date)
    # Filter to this player, past games only
    mask = (df["player_id"] == player_id) & (df["game_date"] < cutoff)
    sub = df[mask]
    if sub.empty:
        return None
    # Latest row = most recent L5 window before decision
    return float(sub.sort_values("game_date").iloc[-1]["pbp_clutch_shots_l5_avg"])


def _midquarter_clutch_prob(game_id: str, decision_date: _dt.datetime) -> Optional[float]:
    """Look up end-of-Q3 clutch probability from inplay_midquarter_features.

    LEAK-SAFE: only includes games whose game_date < decision_date (we never
    read the *current* game's snapshot during training — the gate enforces
    temporal splitting, but we apply an extra guard here).
    """
    df = _load_midquarter()
    if df.empty:
        return None
    cutoff = pd.Timestamp(decision_date.date())
    mask = (df["game_id"] == str(game_id)) & (df["game_date"] < cutoff)
    row = df[mask]
    if row.empty:
        return None
    r = row.iloc[0]
    abs_margin = abs(float(r.get("score_margin", 10.0) or 10.0))
    lead_changes = float(r.get("q4_lead_changes_so_far", 0.0) or 0.0)
    return _clutch_prob_from_margin(abs_margin, lead_changes)


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------

class ClutchRegimeSignal(Signal):
    """Close-and-late regime → usage concentration signal (target=usage, scope=live).

    Emits two sub-features:
      * clutch_prob         — probability the game is in clutch regime [0, 1]
      * clutch_usage_prior  — player's historical clutch usage rate [0, 1]

    At train time: derives clutch_prob from inplay_midquarter (endQ3 margin) and
    clutch_usage_prior from the PBP L5 clutch shots history + atlas clutch section.
    At live inference: clutch_prob from ctx.live snapshot (period, clock, score
    margin); clutch_usage_prior from the atlas (reinforcement read).
    """

    name: str = "clutch_regime"
    target: str = "usage"
    scope: str = "live"
    reads_atlas: List[str] = ["clutch"]
    emits: List[str] = ["clutch_prob", "clutch_usage_prior"]

    # ------------------------------------------------------------------
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return {clutch_prob, clutch_usage_prior} leak-safe at ctx.decision_time.

        Priority:
          1. ctx.live snapshot (real-time inference)
          2. inplay_midquarter_features parquet (training rows with game_id)
          3. pregame win-probability fallback (broadest coverage)

        Returns None when the player is unknown and no context is available.
        """
        player_id: Optional[int] = ctx.player_id
        decision_time: _dt.datetime = ctx.decision_time

        # ---- 1. Clutch usage prior (atlas + PBP L5) --------------------
        clutch_usage_prior = self._build_usage_prior(ctx)

        # ---- 2. Clutch prob: live path ---------------------------------
        if ctx.live is not None:
            clutch_prob = _clutch_prob_from_live(ctx.live)
            return {
                "clutch_prob": clutch_prob,
                "clutch_usage_prior": clutch_usage_prior,
            }

        # ---- 3. Clutch prob: training path (historical game context) ---
        if ctx.game_id is not None:
            cprob = _midquarter_clutch_prob(str(ctx.game_id), decision_time)
            if cprob is not None:
                return {
                    "clutch_prob": cprob,
                    "clutch_usage_prior": clutch_usage_prior,
                }

        # ---- 4. Pregame win-probability fallback -----------------------
        pregame_win_prob: Optional[float] = ctx.extra.get("pregame_win_prob")
        if pregame_win_prob is None:
            # Try atlas-level team win prob if wired
            if self.store is not None and ctx.team is not None:
                team_atlas = self.read_atlas(
                    f"team:{ctx.team}", "ratings", decision_time
                )
                if isinstance(team_atlas, dict):
                    pregame_win_prob = team_atlas.get("home_win_prob")

        cprob = _clutch_prob_from_pregame_win_prob(pregame_win_prob)
        return {
            "clutch_prob": cprob,
            "clutch_usage_prior": clutch_usage_prior,
        }

    # ------------------------------------------------------------------
    def _build_usage_prior(self, ctx: AsOfContext) -> float:
        """Build the clutch-usage prior from the atlas and PBP L5 history.

        Atlas read (reinforcement path) → PBP L5 parquet → neutral default.
        The final value is the average of available sources, clipped to [0, 1].
        """
        player_id = ctx.player_id
        decision_time = ctx.decision_time

        atlas_prior: Optional[float] = None
        pbp_prior: Optional[float] = None

        # Atlas read (clutch section)
        if self.store is not None and player_id is not None:
            atlas_data = self.read_atlas(
                f"player:{player_id}", "clutch", decision_time
            )
            if atlas_data:
                atlas_prior = _clutch_usage_prior_from_atlas(atlas_data)

        # PBP L5 clutch shots prior
        if player_id is not None and ctx.game_date is not None:
            try:
                game_dt = _dt.datetime.strptime(ctx.game_date, "%Y-%m-%d")
            except ValueError:
                game_dt = decision_time
            pbp_shots = _clutch_shots_l5_prior(player_id, game_dt)
            if pbp_shots is not None:
                # Normalise: L5 avg clutch shots → usage proxy
                # 3.0 shots/game ≈ high clutch usage (star); 0 → bench
                pbp_prior = float(min(1.0, pbp_shots / 3.0))

        # Blend available priors
        priors = [p for p in (atlas_prior, pbp_prior) if p is not None]
        if priors:
            return float(min(1.0, sum(priors) / len(priors)))
        return _LEAGUE_AVG_USAGE

    # ------------------------------------------------------------------
    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Close-and-late game situations (Q4 margin <= 5 pts with <= 5 min "
                "remaining, or overtime) concentrate ball-usage on star players; "
                "clutch_prob × clutch_usage_prior predicts usage uplift above the "
                "pregame projection for the identified player."
            ),
            rationale=(
                "NBA possession usage is not constant across game states.  Coaches "
                "deploy their best ball-handlers and closers in clutch situations, "
                "shrinking rotations from 8-9 players to 5-6.  Players with high "
                "historical clutch pts_per36 (atlas clutch section) and high L5 "
                "clutch shots receive a disproportionate usage share.  Bench and "
                "role players see near-zero clutch usage.  The signal captures this "
                "regime shift as a live feature unavailable pre-game, making it a "
                "pure live signal whose predictive value is additive on top of "
                "pregame usagepercentage features."
            ),
            source="seed",
            atlas_fields=["clutch"],
            expected_verdict=Verdict.SHIP,
            priority="P1",
        )
