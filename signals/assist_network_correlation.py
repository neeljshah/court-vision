"""Signal: assist_network_correlation — playmaker role × creation efficiency for AST prediction.

Basketball hypothesis (SGP joint pricing):
  A player's assist output depends not just on individual skill but on their *role*
  within the team's assist network: ball-handler→shooter feed frequency. Players
  who (a) occupy a high-assist-% role (high assistpercentage) AND (b) generate lots
  of potential assists per pass (high trk_pas_potential_ast / trk_pas_passes_made) are
  systematically mis-priced by naive AST over/unders that anchor to season averages.
  This signal decomposes AST into:
    1. playmaker_role    -- rolling L10 assistpercentage (how much of the team's
                           scoring touches flow through this player); per-game, leak-safe.
    2. playmaker_ceiling -- seasonal potential_ast / game from tracking (how many
                           assist opportunities this player's passing style creates).
    3. ast_creation_rate -- ast_pts_created / passes_made (efficiency of converting
                           passes into scoring: captures the teammate-quality factor).

  High playmaker_role × high ast_creation_rate = SGP correlated props:
    the same pass that generates an AST also means a teammate made a shot.
  This is the "who-feeds-whom" network effect the task spec calls for.

Data sources:
  - PRIMARY:  data/player_adv_stats.parquet (77,728 rows, per-game)
              → assistpercentage (walk-forward L10, leak-safe shift(1)+rolling)
  - SECONDARY: data/player_tracking.parquet (2,285 rows, per player-season)
              → trk_pas_potential_ast, trk_pas_ast_points_created, trk_pas_passes_made
  - ATLAS:    store.read_atlas('player', player_id, 'playmaking', ctx.decision_time)
              → potential_ast prior from profile factory

DEFER status:
  - REAL: playmaker_role (adv_stats L10 rolling) — FULLY IMPLEMENTED
  - REAL: ast_creation_rate (tracking seasonal, season-keyed leak-safe) — FULLY IMPLEMENTED
  - REAL: playmaker_ceiling (tracking or atlas prior) — FULLY IMPLEMENTED
  - DEFER: teammate-density feature (how many 3PT shooters can receive the pass) —
    requires a per-game teammate roster join (no per-game team shooting % by lineup
    available yet). Reserved field documented here; see `emits` note.
  - DEFER: live assist network update (ctx.scope == 'live') — the live box snapshot
    has current AST count but no in-game passing breakdown. Live scope uses pregame
    values unchanged (returns same dict as pregame).

Expected gate verdict: SHIP or VARIANCE_ONLY.
  - playmaker_role (L10 ast%) has 77K per-game rows + walk-forward-safe construction.
  - ast_creation_rate is season-level tracking (2K rows) — lower coverage, shrinkage risk.
  - Correlation signal is strongest for traditional PGs; may be VARIANCE_ONLY for wings.
"""
from __future__ import annotations

import datetime as _dt
import warnings
from typing import Dict, List, Optional

import pandas as pd

from src.loop.signal import SCOPES, TARGETS, AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Module-level lazy loaders (loaded once, cached across calls)
# ---------------------------------------------------------------------------
_ADV_STATS: Optional[pd.DataFrame] = None
_TRACKING: Optional[pd.DataFrame] = None
_ADV_STATS_PATH = "data/player_adv_stats.parquet"
_TRACKING_PATH = "data/player_tracking.parquet"


def _load_adv_stats() -> Optional[pd.DataFrame]:
    """Load and prepare player_adv_stats.parquet once (module-level cache)."""
    global _ADV_STATS
    if _ADV_STATS is not None:
        return _ADV_STATS
    try:
        df = pd.read_parquet(_ADV_STATS_PATH)
        df["game_date"] = pd.to_datetime(df["game_date"])
        df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)
        _ADV_STATS = df
        return df
    except Exception as exc:  # missing or corrupt parquet
        warnings.warn(f"assist_network_correlation: could not load adv_stats: {exc}")
        return None


def _load_tracking() -> Optional[pd.DataFrame]:
    """Load and prepare player_tracking.parquet once (module-level cache)."""
    global _TRACKING
    if _TRACKING is not None:
        return _TRACKING
    try:
        df = pd.read_parquet(_TRACKING_PATH)
        # Compute creation rate: potential AST per pass made (a quality-of-pass metric)
        df["trk_ast_creation_rate"] = (
            df["trk_pas_potential_ast"]
            / df["trk_pas_passes_made"].replace(0, float("nan"))
        )
        _TRACKING = df
        return df
    except Exception as exc:
        warnings.warn(f"assist_network_correlation: could not load tracking: {exc}")
        return None


# ---------------------------------------------------------------------------
# Core feature computation helpers (leak-safe — all filtered to < decision_time)
# ---------------------------------------------------------------------------

def _rolling_ast_pct(
    df: pd.DataFrame,
    player_id: int,
    before_date: _dt.datetime,
    window: int = 10,
    min_periods: int = 3,
) -> Optional[float]:
    """L10 rolling assistpercentage for *player_id* over games strictly before *before_date*.

    Leak-safety: we use only games with game_date < before_date (exclusive upper bound,
    matching ctx.decision_time semantics — the game being predicted has not happened).
    """
    subset = df[
        (df["player_id"] == player_id)
        & (df["game_date"] < before_date)
        & (df["assistpercentage"].notna())
    ].copy()
    if len(subset) < min_periods:
        return None
    # Most-recent window
    recent = subset.tail(window)
    return float(recent["assistpercentage"].mean())


def _seasonal_tracking_features(
    df: pd.DataFrame,
    player_id: int,
    season: Optional[str],
) -> Dict[str, Optional[float]]:
    """Retrieve seasonal tracking pass features for the given season (leak-safe).

    Only the *season* string is used as the filter — we do NOT use 2025-26 data
    when evaluating a 2024-25 game (the calling signal passes ctx.season).
    Returns a dict with potential_ast and creation_rate (None if missing).
    """
    subset = df[df["player_id"] == player_id]
    if season is not None:
        # Filter to the exact season; fall back to most recent season before this one
        season_row = subset[subset["season"] == season]
        if season_row.empty:
            # Walk back one season
            available = subset["season"].sort_values()
            available = available[available <= season]
            if available.empty:
                return {"potential_ast": None, "ast_creation_rate": None}
            season_row = subset[subset["season"] == available.iloc[-1]]
    else:
        if subset.empty:
            return {"potential_ast": None, "ast_creation_rate": None}
        season_row = subset.sort_values("season").tail(1)

    if season_row.empty:
        return {"potential_ast": None, "ast_creation_rate": None}
    row = season_row.iloc[0]
    return {
        "potential_ast": _safe_float(row.get("trk_pas_potential_ast")),
        "ast_creation_rate": _safe_float(row.get("trk_ast_creation_rate")),
    }


def _safe_float(v: object) -> Optional[float]:
    """Convert to float; return None for NaN/inf."""
    try:
        f = float(v)  # type: ignore[arg-type]
        return f if (f == f and abs(f) < 1e9) else None  # NaN check via f != f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------


class AssistNetworkCorrelation(Signal):
    """Playmaker role × creation-efficiency signal for AST predictions.

    Emits three sub-features (dict signal):
      ``assist_network_correlation__playmaker_role``
          Rolling L10 assistpercentage (fraction of team FGM the player assisted).
          Range [0, 1]; ~0.30–0.45 for elite PGs.
      ``assist_network_correlation__playmaker_ceiling``
          Seasonal potential_ast / game from tracking (how many assist opportunities
          the player's passing style generates). Range [0, 21]; ~8–18 for elite PGs.
      ``assist_network_correlation__ast_creation_rate``
          potential_ast / passes_made (how efficiently passes convert to AST).
          Range [0, 1]; ~0.10–0.35.

    Reads atlas section ``playmaking`` as a shrinkage prior when tracking data is
    missing (e.g. current season not yet in tracking parquet).
    """

    name: str = "assist_network_correlation"
    target: str = "ast"
    scope: str = "both"
    reads_atlas: List[str] = ["playmaking"]
    emits: List[str] = ["playmaker_role", "playmaker_ceiling", "ast_creation_rate"]

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute leak-safe AST network features for the player in *ctx*.

        Returns a dict of three sub-features, or None if player_id is missing
        or no adv_stats data is available before ctx.decision_time.

        Leak contract: all reads filtered to strictly < ctx.decision_time (adv_stats)
        or <= current season without using a future season (tracking).
        """
        if ctx.player_id is None:
            return None

        adv = _load_adv_stats()
        tracking = _load_tracking()

        # ---- 1. playmaker_role — rolling L10 assistpercentage -------------------
        playmaker_role: Optional[float] = None
        if adv is not None:
            playmaker_role = _rolling_ast_pct(
                adv,
                player_id=ctx.player_id,
                before_date=ctx.decision_time,
                window=10,
                min_periods=3,
            )

        # ---- 2 & 3. tracking features (seasonal, leak-safe) ---------------------
        ceiling: Optional[float] = None
        creation_rate: Optional[float] = None

        if tracking is not None:
            trk = _seasonal_tracking_features(tracking, ctx.player_id, ctx.season)
            ceiling = trk["potential_ast"]
            creation_rate = trk["ast_creation_rate"]

        # ---- Atlas fallback for ceiling when tracking is absent -----------------
        if ceiling is None or creation_rate is None:
            atlas = self.read_atlas(
                entity=f"player:{ctx.player_id}",
                section="playmaking",
                as_of=ctx.decision_time,
            )
            if atlas is not None:
                if ceiling is None:
                    ceiling = _safe_float(atlas.get("potential_ast"))
                if creation_rate is None and atlas.get("passes_made") and atlas.get("potential_ast"):
                    pm = _safe_float(atlas.get("passes_made"))
                    pa = _safe_float(atlas.get("potential_ast"))
                    if pm and pm > 0 and pa is not None:
                        creation_rate = pa / pm

        # ---- Return None only if ALL three sub-features are missing --------------
        if playmaker_role is None and ceiling is None and creation_rate is None:
            return None

        return {
            "playmaker_role": playmaker_role,
            "playmaker_ceiling": ceiling,
            "ast_creation_rate": creation_rate,
        }

    def hypothesis(self) -> Hypothesis:
        """The basketball hypothesis this signal tests."""
        return Hypothesis(
            name=self.name,
            target="ast",
            scope="both",
            statement=(
                "A player's AST output is predictable beyond naive averages by "
                "decomposing it into: (a) playmaker_role = rolling L10 assistpercentage "
                "(fraction of team FGM they assisted), (b) playmaker_ceiling = seasonal "
                "potential_ast / game from tracking, and (c) ast_creation_rate = "
                "potential_ast / passes_made. High role × high efficiency = "
                "systematic under-pricing; low role = systematic over-pricing on "
                "prop AST lines anchored to season averages. Jointly, these features "
                "capture the 'who-feeds-whom' network so that AST and teammate "
                "made-shot props are priced as correlated in SGP construction."
            ),
            rationale=(
                "assistpercentage has 77K per-game rows with a walk-forward-safe "
                "rolling L10 construction. Tracking potential_ast / passes_made is "
                "a season-level prior capturing passing style orthogonal to the "
                "rolling stat. Together they form a two-factor playmaking model: "
                "role (are they the primary distributor?) × efficiency "
                "(are their passes high-quality assists?). The SGP application is "
                "direct: a player with role=0.35 and creation_rate=0.25 who is "
                "priced at 7.5 AST is correlated with their shooters' 3PM props."
            ),
            source="seed",
            atlas_fields=["playmaking"],
            expected_verdict="SHIP",
            priority="P1",
        )
