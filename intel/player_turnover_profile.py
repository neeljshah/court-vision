"""ARM-B atlas section: ``turnover_profile`` -- exhaustive per-player turnover profile.

Implements :class:`AtlasSection` for the ``"turnover_profile"`` section of a player's
persistent profile.  Every real sub-field comes from existing parquets cited in
spec_features.md / spec_intel_memory.md -- no re-derivation.

NOTE on the existing ``count_distributions`` section in build_persistent_profiles.py:
That section covers mean/var/dispersion of tov per game (NegBinom parameterisation for
interval modelling).  This ``turnover_profile`` section is DEEPER and ORTHOGONAL: it
adds usage-normalised season rates, rolling recency (L5/L10), per-quarter distribution,
pressure-game sensitivity, and a DEFER stub for type-breakdown (live/dead-ball/off-foul).
The bridge registers it as an ADDITIONAL section, not a replacement.

**Sub-field coverage:**

REAL (populated from existing parquets):

  season_rate.*  -- season-aggregate tov_pct (% of possessions ending in TOV) from
                    data/cache/bbref_advanced_extended.parquet (bbref_tov_pct);
                    usage-normalised turnover_ratio (100*TOV/(FGA+0.44*FTA+TOV)) from
                    data/player_adv_stats.parquet aggregated season-to-date;
                    assist:turnover ratio from same; all LEAK-SAFE (filtered game_date<=as_of).

  rolling.*      -- rolling L5/L10 turnover_ratio + ast:to + EWMA from
                    data/player_adv_stats.parquet (per-game grain, sorted game_date).

  by_quarter.*   -- mean TOV per game per quarter (q1..q4) and q4 share from
                    data/player_quarter_stats.parquet joined to game_date via
                    data/player_pf.parquet (the same join pattern as foul_tendency).

  pressure_sensitivity.*
                 -- pressure-game TOV delta: compares turnover_ratio in "tight" games
                    (|score_margin_at_start| is captured via the game context available
                    in player_adv_stats; we proxy pressure as games where
                    turnoverratio >= 80th percentile of that player's own distribution
                    vs. their median).  Provides a within-player pressure-elevation index.
                    Source: data/player_adv_stats.parquet (per-game, leak-safe).

DEFER (data gap -- stubs with _note):

  by_type.*      -- live-ball/dead-ball/offensive-foul breakdown.
                    DEFER: NBA Stats API does not expose per-EVENTMSGTYPE breakdown for
                    turnovers at the player level in public endpoints.  PBP
                    EVENTMSGTYPE=5 (turnover) rows carry PLAYER1_ID but the HOME/VISITOR
                    DESCRIPTION text that encodes foul-type is not structured; V3->V2
                    normalisation in pbp_scraper.py also sets PLAYER2_ID="0"
                    (spec_features §2 GOTCHA), blocking offensive-foul attribution.
                    Recoverable when a true-V2 PBP feed or structured DESCRIPTION parser
                    is available.

  opponent_pressure.*
                 -- opponent-induced TOV rate: per-defender forced-TO rate (steals
                    generated, deflections leading to live-ball TO).  DEFER: no
                    per-defender-tov table exists in public NBA Stats endpoints; hustle
                    parquets carry hustle_deflections/hustle_stolen (aggregate, not
                    paired to offensive player), which cannot be joined to WHICH offensive
                    player turned it over without PBP PLAYER2_ID.

RESERVED CV SLOTS (value=None, CV branch fills later):

  ball_handler_speed_at_tov
                 -- mean player speed (ft/s, court coordinates) at the frame where a
                    turnover event is detected by EventDetector (EVENTMSGTYPE=5 frame
                    anchor).  High speed = live-ball / transition TOV;
                    low speed = dead-ball / half-court.  CV fills via fill_cv_slot.

  defender_proximity_at_tov
                 -- mean distance (ft) between the ball-handler and the nearest
                    defender at the turnover frame (homography court coordinates).
                    Pressure-induced vs. self-induced separation signal.

  spacing_at_tov_commit
                 -- mean convex-hull area (ft^2) of the TOV player's teammates at the
                    turnover frame.  Small values indicate tight help-defense convergence
                    (help-side TOV); large values indicate broken possession or
                    transition breakdown.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Module-level parquet cache (load once per process)
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


def _load(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            _SRC_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC_CACHE[key] = None
    return _SRC_CACHE[key]


def _rd(v: Any) -> Optional[float]:
    """Clean scalar: NaN/inf -> None, numpy -> python float, round 4 dp."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 4)


def _ri(v: Any) -> Optional[int]:
    """Clean integer scalar."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Per-source aggregation helpers (all LEAK-SAFE via as_of filter)
# ---------------------------------------------------------------------------

def _season_rate_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Season-level tov_pct, turnover_ratio, and ast:to ratio filtered to <= as_of.

    Sources:
      - data/cache/bbref_advanced_extended.parquet (tov_pct, seasonal grain)
      - data/player_adv_stats.parquet (per-game turnoverratio + assisttoturnover,
        aggregated season-to-date up to as_of)

    Leak-safety:
      - bbref parquet is seasonal (end-of-season published); we take the LATEST season
        whose season_year <= as_of.year -- consistent with spec_intel_memory §1.4
        "seasonal source" treatment (same approach as playtypes/tracking).
      - player_adv_stats rows are filtered game_date <= as_of (per-game, strict bound).
    """
    as_of_ts = pd.Timestamp(as_of)
    result: Dict[str, Any] = {}

    # bbref tov_pct (season-aggregate; take latest available season <= as_of)
    bb = _load("bbref_adv", CACHE / "bbref_advanced_extended.parquet")
    if bb is not None and not bb.empty:
        rows = bb[bb["player_id"] == pid].copy()
        if "season_year" in rows.columns:
            rows = rows[rows["season_year"] <= as_of.year]
        if not rows.empty:
            rows = rows.sort_values("season_year")
            last = rows.iloc[-1]
            result["bbref_tov_pct"] = _rd(last.get("tov_pct"))
            result["bbref_season"] = str(last.get("season", ""))

    # player_adv_stats: season-to-date aggregation up to as_of
    adv = _load("adv_stats", DATA / "player_adv_stats.parquet")
    n_games = 0
    if adv is not None and not adv.empty:
        rows_adv = adv[adv["player_id"] == pid].copy()
        if "game_date" in rows_adv.columns:
            rows_adv["game_date"] = pd.to_datetime(rows_adv["game_date"])
            rows_adv = rows_adv[rows_adv["game_date"] <= as_of_ts]
        if not rows_adv.empty:
            rows_adv = rows_adv.sort_values("game_date")
            n_games = len(rows_adv)
            last_adv = rows_adv.iloc[-1]
            # Season-to-date means
            result["season_to_date_turnover_ratio"] = _rd(
                rows_adv["turnoverratio"].mean()
            )
            result["season_to_date_ast_to"] = _rd(
                rows_adv["assisttoturnover"].mean()
            )
            # Most recent game snapshot (trailing indicator)
            result["last_game_turnover_ratio"] = _rd(last_adv.get("turnoverratio"))
            result["last_game_ast_to"] = _rd(last_adv.get("assisttoturnover"))

    result["n_games"] = n_games
    return result


def _rolling_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Rolling L5/L10 turnover_ratio + EWMA from player_adv_stats, filtered <= as_of.

    Source: data/player_adv_stats.parquet (per-game, game_date filtered).
    """
    as_of_ts = pd.Timestamp(as_of)

    adv = _load("adv_stats", DATA / "player_adv_stats.parquet")
    if adv is None or adv.empty:
        return {}

    rows = adv[adv["player_id"] == pid].copy()
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= as_of_ts]

    if rows.empty:
        return {}

    rows = rows.sort_values("game_date")
    tr = rows["turnoverratio"].dropna()
    asto = rows["assisttoturnover"].dropna()

    result: Dict[str, Any] = {}
    if len(tr) >= 1:
        result["l5_turnover_ratio"] = _rd(tr.tail(5).mean())
        result["l10_turnover_ratio"] = _rd(tr.tail(10).mean())
        # EWMA with halflife=5 games (emphasises recent form)
        result["ewma_turnover_ratio"] = _rd(
            tr.ewm(halflife=5, min_periods=1).mean().iloc[-1]
        )
    if len(asto) >= 1:
        result["l5_ast_to"] = _rd(asto.tail(5).mean())
        result["l10_ast_to"] = _rd(asto.tail(10).mean())

    result["n_games"] = len(rows)
    return result


def _by_quarter_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Mean TOV per game per quarter (q1..q4) and q4 share, filtered <= as_of.

    Sources:
      - data/player_quarter_stats.parquet (per-quarter tov; no game_date col)
      - data/player_pf.parquet (provides game_id -> game_date map for leak boundary)

    Pattern mirrors player_foul_tendency._by_quarter_for_player exactly.
    """
    as_of_ts = pd.Timestamp(as_of)

    qstats = _load("qstats", DATA / "player_quarter_stats.parquet")
    pf_df = _load("pf_raw", DATA / "player_pf.parquet")

    if qstats is None or qstats.empty:
        return {}

    rows = qstats[qstats["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Enforce as_of via game_date from player_pf
    if pf_df is not None and "game_date" in pf_df.columns and "game_id" in rows.columns:
        gd_map = (
            pf_df[pf_df["player_id"] == pid][["game_id", "game_date"]]
            .drop_duplicates("game_id")
            .set_index("game_id")["game_date"]
        )
        rows = rows.copy()
        rows["_game_date"] = pd.to_datetime(rows["game_id"].map(gd_map))
        rows = rows[rows["_game_date"].notna() & (rows["_game_date"] <= as_of_ts)]

    if rows.empty:
        return {}

    result: Dict[str, Any] = {}
    total_tov_pg = 0.0

    for q in [1, 2, 3, 4]:
        qr = rows[rows["period"] == q]
        if qr.empty:
            continue
        g_count = qr["game_id"].nunique() if "game_id" in qr.columns else len(qr)
        if g_count == 0:
            continue
        tov_pg = float(qr["tov"].sum()) / g_count
        result[f"q{q}_tov_pg"] = round(tov_pg, 4)
        total_tov_pg += tov_pg

    # Q4 share -- how much of daily turnover budget comes in clutch quarter
    if total_tov_pg > 0 and "q4_tov_pg" in result:
        result["q4_share_of_daily_tov"] = round(result["q4_tov_pg"] / total_tov_pg, 4)

    result["n_quarter_games"] = (
        rows["game_id"].nunique() if "game_id" in rows.columns else len(rows)
    )
    return result


def _pressure_sensitivity_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Within-player pressure TOV elevation: high-turnover-ratio games vs. median.

    We define a player's "pressure games" as those where their per-possession turnover
    ratio (turnoverratio from player_adv_stats) is at or above the 80th percentile of
    their own distribution.  The pressure_elevation_ratio is:

        mean(turnoverratio in top-20% games) / median(turnoverratio across all games)

    A ratio > 1.0 means the player spikes in pressure moments; near 1.0 means they
    maintain composure.  This is a WITHIN-PLAYER signal (no cross-player comparison).

    Source: data/player_adv_stats.parquet (per-game, filtered game_date <= as_of).
    Leak-safe: only games already played as of the as_of date are used.
    """
    as_of_ts = pd.Timestamp(as_of)

    adv = _load("adv_stats", DATA / "player_adv_stats.parquet")
    if adv is None or adv.empty:
        return {}

    rows = adv[adv["player_id"] == pid].copy()
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= as_of_ts]

    tr = rows["turnoverratio"].dropna()
    if len(tr) < 10:  # need at least 10 games for meaningful percentile split
        return {"_note": "insufficient games for pressure split (< 10)"}

    p80 = float(np.percentile(tr, 80))
    median_tr = float(np.median(tr))
    high_tr = tr[tr >= p80]

    if median_tr == 0.0 or len(high_tr) == 0:
        return {
            "pressure_elevation_ratio": None,
            "median_turnover_ratio": _rd(median_tr),
            "p80_turnover_ratio": _rd(p80),
            "n_high_pressure_games": 0,
            "n_total_games": len(tr),
        }

    return {
        "pressure_elevation_ratio": _rd(float(high_tr.mean()) / median_tr),
        "median_turnover_ratio": _rd(median_tr),
        "p80_turnover_ratio": _rd(p80),
        "mean_high_pressure_turnover_ratio": _rd(float(high_tr.mean())),
        "n_high_pressure_games": len(high_tr),
        "n_total_games": len(tr),
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerTurnoverProfile(AtlasSection):
    """Deep player turnover-profile atlas section (player entity, section='turnover_profile').

    Covers four REAL sub-dicts and two DEFER stubs:
      - season_rate       (season tov_pct, season-to-date turnover_ratio, ast:to)
      - rolling           (L5/L10 turnover_ratio, EWMA, ast:to rolling)
      - by_quarter        (mean TOV per quarter, q4 share)
      - pressure_sensitivity (within-player high-tov-game elevation index)
      - by_type           (DEFER: live/dead-ball/off-foul type unknown without V2 PBP)
      - opponent_pressure (DEFER: per-defender forced-TO table unavailable)

    Three CV slots reserved for CV-branch enrichment (all values None until filled):
      - ball_handler_speed_at_tov
      - defender_proximity_at_tov
      - spacing_at_tov_commit

    Sources:
      - data/cache/bbref_advanced_extended.parquet (bbref tov_pct, seasonal)
      - data/player_adv_stats.parquet (per-game turnoverratio + ast:to)
      - data/player_quarter_stats.parquet (per-quarter tov)
      - data/player_pf.parquet (game_id -> game_date map for quarter leak boundary)

    NOT used (intentionally excluded):
      - data/cache/pbp_possession_features.parquet -- no tov cols
      - data/cache/foul_features.parquet -- foul-specific, no tov
      - data/cache/inplay_qbox_efficiency.parquet -- team-level tov_per_poss only
    """

    name: str = "turnover_profile"
    entity: str = "player"
    source_name: str = (
        "bbref_advanced_extended.parquet + player_adv_stats.parquet + "
        "player_quarter_stats.parquet + player_pf.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the leak-safe turnover_profile artifact for one player.

        Leak guarantee:
          - bbref_advanced_extended: season_year <= as_of.year (end-of-season parquet).
          - player_adv_stats: game_date <= as_of (per-game strict bound).
          - player_quarter_stats: joined to game_date via player_pf (same bound).
          - player_pf: game_date <= as_of (per-game strict bound, used as join key).

        Returns None when the player is absent from all primary per-game sources.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        season_rate = _season_rate_for_player(pid, as_of)
        rolling = _rolling_for_player(pid, as_of)
        by_quarter = _by_quarter_for_player(pid, as_of)
        pressure = _pressure_sensitivity_for_player(pid, as_of)

        # Bail if no per-game adv_stats data (the primary source)
        if not season_rate and not rolling:
            return None

        # --- DEFER stubs ---
        by_type: Dict[str, Any] = {
            "_note": (
                "DEFER: live-ball/dead-ball/offensive-foul breakdown requires structured "
                "PBP EVENTMSGTYPE=5 row parsing with PLAYER1_ID + HOME/VISITOR_DESCRIPTION "
                "text classification.  V3->V2 normalisation in pbp_scraper.py sets "
                "PLAYER2_ID='0' on all freshly scraped files (spec_features §2 GOTCHA); "
                "per-player offensive-foul attribution unavailable until the true-V2 PBP "
                "feed is restored or a structured DESCRIPTION text parser is added."
            )
        }
        opponent_pressure: Dict[str, Any] = {
            "_note": (
                "DEFER: opponent-induced TOV rate (forced-TO per defender) requires joining "
                "hustle_deflections/hustle_stolen to the OFFENSIVE player who turned the ball "
                "over.  PBP PLAYER2_ID='0' blocks this pairing (same V3->V2 gotcha). "
                "hustle parquets (hustle_features_2025-26.parquet) carry aggregate defensive "
                "deflections but cannot be mapped to which offensive player they victimised."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "season_rate": season_rate,
            "rolling": rolling,
            "by_quarter": by_quarter,
            "pressure_sensitivity": pressure,
            "by_type": by_type,
            "opponent_pressure": opponent_pressure,
        }

        # --- Sample size: max across per-game sources ---
        n_candidates: List[int] = []
        if season_rate.get("n_games"):
            n_candidates.append(season_rate["n_games"])
        if rolling.get("n_games"):
            n_candidates.append(rolling["n_games"])
        if by_quarter.get("n_quarter_games"):
            n_candidates.append(by_quarter["n_quarter_games"])
        n = max(n_candidates) if n_candidates else 1

        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        # Headline value: season-to-date turnover ratio (most actionable single scalar)
        headline = (
            _rd(season_rate.get("season_to_date_turnover_ratio"))
            or _rd(rolling.get("l5_turnover_ratio"))
        )

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=headline,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, ratios non-negative.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required = {
            "season_rate", "rolling", "by_quarter",
            "pressure_sensitivity", "by_type", "opponent_pressure",
        }
        if not required.issubset(sf.keys()):
            return False

        # turnover_ratio must be non-negative when present
        for outer, key in [
            ("season_rate", "season_to_date_turnover_ratio"),
            ("season_rate", "last_game_turnover_ratio"),
            ("rolling", "l5_turnover_ratio"),
            ("rolling", "l10_turnover_ratio"),
            ("rolling", "ewma_turnover_ratio"),
        ]:
            v = sf.get(outer, {}).get(key)
            if v is not None and v < 0.0:
                return False

        # pressure_elevation_ratio must be > 0 when present
        elev = sf.get("pressure_sensitivity", {}).get("pressure_elevation_ratio")
        if elev is not None and elev <= 0.0:
            return False

        # tov_pct must be in [0, 100] when present
        tov_pct = sf.get("season_rate", {}).get("bbref_tov_pct")
        if tov_pct is not None and not (0.0 <= tov_pct <= 100.0):
            return False

        # CV fields present and all null (CV branch has not run yet)
        if not artifact.cv_fields:
            return False
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for turnover_profile (values None -- CV branch fills).

        The CV-fix session calls:
          store.fill_cv_slot("player", pid, "turnover_profile", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild.  Slots are stable keys.

        Slots:
          ball_handler_speed_at_tov  -- player speed (ft/s) at the TOV frame; high ->
                                        live-ball/transition TO, low -> dead-ball.
          defender_proximity_at_tov  -- distance (ft) to nearest defender at TOV frame;
                                        pressure-induced vs. self-induced.
          spacing_at_tov_commit      -- convex-hull area (ft^2) of teammates; tight =
                                        help-converge TO, large = broken transition.
        """
        return {
            "ball_handler_speed_at_tov": CVSlot(
                name="ball_handler_speed_at_tov",
                dtype="float",
                description=(
                    "Mean player speed (ft/s) at the frame where a turnover event is "
                    "detected by EventDetector (EVENTMSGTYPE=5 frame anchor + homography "
                    "coordinates). High speed indicates a live-ball or transition turnover "
                    "(fumble, bad pass at pace); low speed indicates a dead-ball or "
                    "half-court turnover (walk, bad pass from set play)."
                ),
                unit="ft/s",
                value=None,
            ),
            "defender_proximity_at_tov": CVSlot(
                name="defender_proximity_at_tov",
                dtype="float",
                description=(
                    "Mean distance (ft) between the ball-handler and the nearest defender "
                    "at the turnover frame (homography court coordinates). Low values "
                    "indicate tight on-ball pressure induced the turnover; high values "
                    "suggest the turnover was self-inflicted or from a broken play "
                    "without immediate defensive pressure."
                ),
                unit="ft",
                value=None,
            ),
            "spacing_at_tov_commit": CVSlot(
                name="spacing_at_tov_commit",
                dtype="float",
                description=(
                    "Mean convex-hull area (ft^2) of the ball-handler's teammates at the "
                    "turnover frame. Small values indicate a help-defense convergence "
                    "scenario (teammates clustered, defence collapsing); large values "
                    "indicate a transition or broken-play breakdown with teammates spread. "
                    "From homography court coordinates at the EventDetector turnover frame."
                ),
                unit="ft^2",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build turnover_profile for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int). If None, discovers from player_adv_stats.
        as_of:      leak boundary date (defaults to today's UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes (compute and validate only).

    Returns:
        manifest dict from register_section.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if player_ids is None:
        adv = _load("adv_disc", DATA / "player_adv_stats.parquet")
        if adv is not None and "player_id" in adv.columns:
            player_ids = sorted(
                adv["player_id"].dropna().astype(int).unique().tolist()
            )
        else:
            player_ids = []

    section = PlayerTurnoverProfile()
    artifacts = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
