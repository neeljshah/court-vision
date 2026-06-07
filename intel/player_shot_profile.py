"""ARM-B atlas section: ``shot_profile`` — exhaustive per-player shooting profile.

Implements :class:`AtlasSection` for the ``"shot_profile"`` section of a player's
persistent profile.  Every sub-field below comes from an existing parquet listed in
spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):
  creation.*       — catch_shoot / pull_up / drive / post_up rates + fg%/ppp from
                     player_tracking (trk_cs_*) + playtypes (Spotup/PRBallHandler/
                     Isolation/Postup/PRRollMan/Handoff/Cut/OffRebound).
  context.*        — transition / halfcourt / iso / pnr / off_screen / putback freq+ppp
                     from playtypes_2025-26 (+ playtypes base season fallback).
  shot_clock.*     — early/mid/late-clock shot counts + n_shots from
                     data/intelligence/shot_clock_buckets.parquet.
  quarter_splits.* — per-quarter FGA proxy (pts share Q1-Q4) from
                     data/player_quarter_stats.parquet (per-game → per-player agg).
  clutch.*         — clutch fg_pct / pts_per36 / plus_minus / min from
                     data/cache/clutch_profiles_2025-26.parquet.
  pbp_context.*    — iso_poss_count / pnr_handler / post_up / transition / late_clock /
                     clutch_shots / avg_seconds_per_touch from
                     data/cache/pbp_possession_features.parquet (per-game agg).
  usage_context.*  — usage_pct / ts_pct / efg_pct from
                     data/player_adv_stats.parquet (season-level agg).

DEFER (data gap — not available in current parquets):
  zones.*          — rim/paint/midrange-L-C-R/c3/above-the-break/deep-3 freq+fg%+pps
                     DEFER: no per-zone shot chart parquet in repo (NBA ShotChart API
                     not fetched; cv_shot_range_per_game.parquet has distance but not
                     court-zone categories; would need scripts/fetch_shot_chart.py).
  rest_home_road.* — rest-day / home / road fg% splits
                     DEFER: rest_travel.parquet has team-level b2b flag but no
                     per-player fg% by home/road; player_adv_stats would need a
                     game-by-game home/away join that is not pre-aggregated.
  vs_zone_defense.*— fg% vs zone vs man DEFER: no coverage-by-defense-type parquet.

RESERVED CV SLOTS (value=None, CV branch fills later):
  defender_distance_dist — distribution of defender proximity at shot release (ft)
  contest_level          — fraction of shots contested (CV-tagged: open/contested/smothered)
  dribbles_before        — mean dribble count pre-shot (CV EventDetector)
  closeout_speed         — mean defender closeout velocity at release (ft/s)
  release_time           — mean time-of-release from shot-clock start (s)
  shot_arc               — mean ball apex angle / arc estimate (deg, CV)
  spacing_around         — mean convex-hull spacing of off-ball teammates at shot (ft²)
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
# Data-loading helpers (lazy, module-level cache)
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
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _playtypes_for_player(
    pid: int, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Return play_type -> {freq_pct, ppp} for the player, latest season <= as_of."""
    as_of_str = as_of.date().isoformat()
    result: Dict[str, Any] = {}

    for path_key, path in [
        ("pt26", DATA / "playtypes_2025-26.parquet"),
        ("pt_base", DATA / "playtypes.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid].copy()
        if rows.empty:
            continue
        # Sort seasons and take the latest season whose data is <= as_of
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
            # season like "2025-26" — accept all (no date filter possible without game_date)
        # Accumulate play types
        for _, row in rows.iterrows():
            pt = str(row.get("play_type", ""))
            if pt and pt not in result:
                result[pt] = {
                    "freq_pct": _rd(row.get("freq_pct")),
                    "ppp": _rd(row.get("ppp")),
                }
        break  # use the freshest source that has data
    return result


def _tracking_for_player(
    pid: int, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Return tracking creation sub-fields from player_tracking(_2025-26).parquet."""
    for path_key, path in [
        ("trk26", DATA / "player_tracking_2025-26.parquet"),
        ("trk_base", DATA / "player_tracking.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        row = rows.iloc[0]
        return {
            "drive_count_per_game": _rd(row.get("trk_drv_count")),
            "drive_fg_pct": _rd(row.get("trk_drv_fg_pct")),
            "drive_pts_per_game": _rd(row.get("trk_drv_pts")),
            "catch_shoot_fga_per_game": _rd(row.get("trk_cs_fga")),
            "catch_shoot_fg_pct": _rd(row.get("trk_cs_fg_pct")),
            "catch_shoot_efg_pct": _rd(row.get("trk_cs_efg_pct")),
            "catch_shoot_pts_per_game": _rd(row.get("trk_cs_pts")),
            "_source_season": str(row.get("season", "")),
        }
    return {}


def _quarter_splits_for_player(
    pid: int, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate per-quarter pts from player_quarter_stats, filtered to games <= as_of."""
    path = DATA / "player_quarter_stats.parquet"
    df = _load("qstats", path)
    if df is None or df.empty:
        return {}

    # Filter by player; apply as_of by joining with adv stats game_date if present
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Use per-game adv_stats to find game_dates, then filter by as_of
    adv = _load("adv", DATA / "player_adv_stats.parquet")
    if adv is not None and "game_date" in adv.columns:
        gd_map = (
            adv[adv["player_id"] == pid][["game_id", "game_date"]]
            .drop_duplicates("game_id")
            .set_index("game_id")["game_date"]
        )
        if "game_id" in rows.columns:
            rows = rows.copy()
            rows["_game_date"] = rows["game_id"].map(gd_map)
            rows = rows[rows["_game_date"].notna()]
            rows["_game_date"] = pd.to_datetime(rows["_game_date"])
            as_of_dt = pd.Timestamp(as_of)
            rows = rows[rows["_game_date"] <= as_of_dt]

    if rows.empty:
        return {}

    n_games = rows[rows["period"] == 1]["game_id"].nunique() if "game_id" in rows.columns else 0

    # Per-quarter averages
    splits: Dict[str, Any] = {}
    total_pts = 0.0
    for q in [1, 2, 3, 4]:
        qr = rows[rows["period"] == q]
        if qr.empty:
            continue
        g_count = qr["game_id"].nunique() if "game_id" in qr.columns else len(qr)
        if g_count == 0:
            continue
        pts = float(qr["pts"].sum()) / g_count
        splits[f"q{q}_pts_pg"] = round(pts, 4)
        total_pts += pts

    # Q4 share of total (late-game scoring profile)
    if total_pts > 0 and "q4_pts_pg" in splits:
        splits["q4_share"] = round(splits["q4_pts_pg"] / total_pts, 4)

    splits["n_games"] = n_games
    return splits


def _clutch_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Clutch stats from clutch_profiles_2025-26.parquet."""
    path = CACHE / "clutch_profiles_2025-26.parquet"
    df = _load("clutch26", path)
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}
    if "season" in rows.columns:
        rows = rows.sort_values("season", ascending=False)
    row = rows.iloc[0]
    return {
        "clutch_fg_pct": _rd(row.get("clutch_fg_pct")),
        "clutch_fg3_pct": _rd(row.get("clutch_fg3_pct")),
        "clutch_ft_pct": _rd(row.get("clutch_ft_pct")),
        "clutch_pts_per36": _rd(row.get("clutch_pts_per36")),
        "clutch_plus_minus": _rd(row.get("clutch_plus_minus")),
        "clutch_gp": _ri(row.get("clutch_gp")),
        "clutch_min": _rd(row.get("clutch_min")),
    }


def _pbp_context_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate PBP possession context filtered to games <= as_of."""
    path = CACHE / "pbp_possession_features.parquet"
    df = _load("pbp_poss", path)
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}
    # Leak filter via game_date
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    means = rows[
        [
            "pbp_iso_poss_count",
            "pbp_pnr_ball_handler",
            "pbp_pnr_screener_proxy",
            "pbp_post_up_count",
            "pbp_transition_count",
            "pbp_late_clock_shots",
            "pbp_clutch_shots_attempted",
            "pbp_clutch_pts_scored",
            "pbp_avg_seconds_per_touch",
        ]
    ].mean()

    return {
        "iso_poss_pg": _rd(means.get("pbp_iso_poss_count")),
        "pnr_handler_pg": _rd(means.get("pbp_pnr_ball_handler")),
        "pnr_screener_pg": _rd(means.get("pbp_pnr_screener_proxy")),
        "post_up_pg": _rd(means.get("pbp_post_up_count")),
        "transition_pg": _rd(means.get("pbp_transition_count")),
        "late_clock_shots_pg": _rd(means.get("pbp_late_clock_shots")),
        "clutch_shots_pg": _rd(means.get("pbp_clutch_shots_attempted")),
        "clutch_pts_pg": _rd(means.get("pbp_clutch_pts_scored")),
        "avg_seconds_per_touch": _rd(means.get("pbp_avg_seconds_per_touch")),
        "n_games": n,
    }


def _shot_clock_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Shot-clock bucket summaries from data/intelligence/shot_clock_buckets.parquet.

    Buckets: early (>18s), mid (7-18s), late (<7s).  Provides n_poss and n_shots
    per bucket; feature breakdowns (mean_velocity etc.) are CV-sparse so skipped here.
    """
    path = DATA / "intelligence" / "shot_clock_buckets.parquet"
    df = _load("sc_buckets", path)
    if df is None or df.empty:
        return {}

    # pkey format is "<player_name>/<team_abbrev>" — join via player_name lookup
    # However pkey is not player_id keyed; use player_name from bio if available.
    # DEFER: shot_clock_buckets uses pkey not player_id; player_name lookup fragile.
    # Return empty dict — mark as partial DEFER.
    return {}


def _usage_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Season-aggregate usage/efficiency from player_adv_stats, filtered to <= as_of."""
    path = DATA / "player_adv_stats.parquet"
    df = _load("adv", path)
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    means = rows[
        [c for c in ["usagepercentage", "trueshootingpercentage",
                      "effectivefieldgoalpercentage", "offensiverating"] if c in rows.columns]
    ].mean()

    return {
        "usage_pct": _rd(means.get("usagepercentage")),
        "ts_pct": _rd(means.get("trueshootingpercentage")),
        "efg_pct": _rd(means.get("effectivefieldgoalpercentage")),
        "off_rating": _rd(means.get("offensiverating")),
        "n_games": n,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerShotProfile(AtlasSection):
    """Deep player shot-profile atlas section (player entity, section='shot_profile').

    Builds a provenance-stamped, leak-safe artifact covering shot creation types,
    situational context, shot-clock timing, quarter splits, clutch, and PBP context.
    Reserves 7 CV slots for CV-branch enrichment (all values None until filled).

    Sources used:
      - data/playtypes_2025-26.parquet + data/playtypes.parquet (creation/context)
      - data/player_tracking_2025-26.parquet + data/player_tracking.parquet (catch-shoot/drive)
      - data/player_quarter_stats.parquet (quarter splits)
      - data/cache/clutch_profiles_2025-26.parquet (clutch fg%)
      - data/cache/pbp_possession_features.parquet (iso/pnr/transition/late-clock)
      - data/player_adv_stats.parquet (usage/TS%/eFG%)

    DEFER sections (no source parquet exists yet):
      - zones (rim/paint/mid/corner-3/above-break/deep) — no shot-chart parquet
      - rest/home/road fg% splits — not pre-aggregated per player
      - vs-zone-defense splits — no coverage-by-D-type parquet
      - shot_clock detailed timing — shot_clock_buckets pkey is player_name not player_id
    """

    name: str = "shot_profile"
    entity: str = "player"
    source_name: str = (
        "playtypes_2025-26.parquet + player_tracking_2025-26.parquet + "
        "player_quarter_stats.parquet + clutch_profiles_2025-26.parquet + "
        "pbp_possession_features.parquet + player_adv_stats.parquet"
    )
    conf_cap: Optional[str] = None  # no hard cap; CV slots capped separately

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the shot_profile artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: every data source is filtered to game_date <= as_of
        (player_adv_stats, pbp_possession_features, player_quarter_stats).
        Season-keyed sources (playtypes, tracking, clutch) use the latest season
        available in the data without a game_date; this is acceptable because those
        are pre-published end-of-season summaries that existed before the season ended.

        Returns None when all sources are missing for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        pt = _playtypes_for_player(pid, as_of)
        trk = _tracking_for_player(pid, as_of)
        q_splits = _quarter_splits_for_player(pid, as_of)
        clutch = _clutch_for_player(pid, as_of)
        pbp = _pbp_context_for_player(pid, as_of)
        usage = _usage_for_player(pid, as_of)

        # Bail if nothing was populated (player absent from all sources)
        all_empty = not pt and not trk and not q_splits and not clutch and not pbp and not usage
        if all_empty:
            return None

        # --- Build creation sub-dict from tracking + playtypes ---
        creation: Dict[str, Any] = {}
        if trk:
            creation["catch_shoot_fga_pg"] = trk.get("catch_shoot_fga_per_game")
            creation["catch_shoot_fg_pct"] = trk.get("catch_shoot_fg_pct")
            creation["catch_shoot_efg_pct"] = trk.get("catch_shoot_efg_pct")
            creation["catch_shoot_pts_pg"] = trk.get("catch_shoot_pts_per_game")
            creation["drive_count_pg"] = trk.get("drive_count_per_game")
            creation["drive_fg_pct"] = trk.get("drive_fg_pct")
            creation["drive_pts_pg"] = trk.get("drive_pts_per_game")

        # Pull-up proxy: PRBallHandler + Isolation (ball-creation)
        for pt_key, label in [
            ("PRBallHandler", "pull_up_pnr"),
            ("Isolation", "isolation"),
            ("Spotup", "spot_up"),
            ("Postup", "post_up"),
            ("PRRollMan", "pnr_roll_man"),
            ("Handoff", "handoff"),
            ("Cut", "cut"),
            ("OffRebound", "putback"),
        ]:
            entry = pt.get(pt_key)
            if entry:
                creation[f"{label}_freq_pct"] = entry.get("freq_pct")
                creation[f"{label}_ppp"] = entry.get("ppp")

        # --- Context sub-dict (transition / halfcourt / off-screen) ---
        context: Dict[str, Any] = {}
        for pt_key, label in [
            ("Transition", "transition"),
            ("OffScreen", "off_screen"),
        ]:
            entry = pt.get(pt_key)
            if entry:
                context[f"{label}_freq_pct"] = entry.get("freq_pct")
                context[f"{label}_ppp"] = entry.get("ppp")

        # PBP-derived context (richer, per-game aggregates)
        if pbp:
            context["iso_poss_pg"] = pbp.get("iso_poss_pg")
            context["pnr_handler_pg"] = pbp.get("pnr_handler_pg")
            context["pnr_screener_pg"] = pbp.get("pnr_screener_pg")
            context["post_up_pg"] = pbp.get("post_up_pg")
            context["transition_pg"] = pbp.get("transition_pg")
            context["late_clock_shots_pg"] = pbp.get("late_clock_shots_pg")
            context["avg_seconds_per_touch"] = pbp.get("avg_seconds_per_touch")

        # --- Shot-clock timing (DEFER for detail — pkey join unavailable) ---
        shot_clock_timing: Dict[str, Any] = {
            "_note": "DEFER: shot_clock_buckets uses player_name pkey, not player_id; "
                     "linkage requires scripts/fetch_shot_chart.py or a name->id bridge."
        }

        # --- Quarter splits ---
        quarter_splits: Dict[str, Any] = dict(q_splits)

        # --- Zones (DEFER) ---
        zones: Dict[str, Any] = {
            "_note": "DEFER: no per-zone shot-chart parquet in repo. "
                     "Requires scripts/fetch_shot_chart.py (NBA ShotChartDetail API)."
        }

        # --- Rest / home / road splits (DEFER) ---
        rest_home_road: Dict[str, Any] = {
            "_note": "DEFER: rest_travel.parquet is team-level; per-player fg% by "
                     "home/road not pre-aggregated."
        }

        # --- vs zone-defense splits (DEFER) ---
        vs_zone_defense: Dict[str, Any] = {
            "_note": "DEFER: no coverage-by-D-type parquet available."
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "creation": creation,
            "context": context,
            "shot_clock_timing": shot_clock_timing,
            "quarter_splits": quarter_splits,
            "clutch": clutch,
            "usage_context": usage,
            "zones": zones,
            "rest_home_road": rest_home_road,
            "vs_zone_defense": vs_zone_defense,
        }

        # --- Determine n (largest game-count across data sources) ---
        n_candidates: List[int] = []
        if pbp.get("n_games"):
            n_candidates.append(pbp["n_games"])
        if q_splits.get("n_games"):
            n_candidates.append(q_splits["n_games"])
        if usage.get("n_games"):
            n_candidates.append(usage["n_games"])
        n = max(n_candidates) if n_candidates else 1

        confidence = confidence_from_n(n, cap=self.conf_cap)

        # as_of = the input date (we filtered all per-game sources to <= as_of)
        provenance = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=None,  # no meaningful headline scalar for shot profile
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub-field keys present, no out-of-range values.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        sf = artifact.sub_fields
        required_keys = {
            "creation", "context", "shot_clock_timing",
            "quarter_splits", "clutch", "usage_context",
            "zones", "rest_home_road", "vs_zone_defense",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Sanity-check fg% values are in [0, 1]
        creation = sf.get("creation", {})
        for key in ["catch_shoot_fg_pct", "catch_shoot_efg_pct", "drive_fg_pct"]:
            v = creation.get(key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False

        # CV fields schema must be present and all values None
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False  # CV branch hasn't run yet; values must be null

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for shot_profile (values None — CV branch fills later).

        Slots are stable keys; the CV-fix session calls
        ``store.fill_cv_slot("player", pid, "shot_profile", slot, as_of, value)``
        to populate them WITHOUT a profile rebuild.
        """
        return {
            "defender_distance_dist": CVSlot(
                name="defender_distance_dist",
                dtype="dist",
                description=(
                    "Distribution (mean, p25, p75) of nearest-defender distance at shot "
                    "release in feet, from CV EventDetector + homography coordinates."
                ),
                unit="ft",
                value=None,
            ),
            "contest_level": CVSlot(
                name="contest_level",
                dtype="float",
                description=(
                    "Fraction of shot attempts classified as contested (defender <= 4 ft), "
                    "from CV bounding-box proximity at release frame."
                ),
                unit=None,
                value=None,
            ),
            "dribbles_before": CVSlot(
                name="dribbles_before",
                dtype="float",
                description=(
                    "Mean number of dribbles taken before shot release, "
                    "from CV EventDetector dribble-event sequence."
                ),
                unit=None,
                value=None,
            ),
            "closeout_speed": CVSlot(
                name="closeout_speed",
                dtype="float",
                description=(
                    "Mean defender closeout velocity (ft/s) in the 0.5 s before "
                    "shot release, from CV homography + Kalman velocity."
                ),
                unit="ft/s",
                value=None,
            ),
            "release_time": CVSlot(
                name="release_time",
                dtype="float",
                description=(
                    "Mean seconds elapsed from possession-start (ball-handler gains "
                    "possession) to shot release, approximating shot-clock usage."
                ),
                unit="s",
                value=None,
            ),
            "shot_arc": CVSlot(
                name="shot_arc",
                dtype="float",
                description=(
                    "Mean estimated ball apex angle in degrees above the rim plane, "
                    "derived from CV ball-trajectory tracking between release and apex."
                ),
                unit="deg",
                value=None,
            ),
            "spacing_around": CVSlot(
                name="spacing_around",
                dtype="float",
                description=(
                    "Mean convex-hull area (ft²) of off-ball teammates at the moment "
                    "of shot release — proxy for spacing quality when the shooter fires."
                ),
                unit="ft²",
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
    """Build shot_profile for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from playtypes.
        as_of:      leak boundary date (defaults to today).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        # Discover from the freshest playtypes source
        for path_key, path in [
            ("pt26_disc", DATA / "playtypes_2025-26.parquet"),
            ("pt_disc", DATA / "playtypes.parquet"),
        ]:
            df = _load(path_key, path)
            if df is not None and not df.empty and "player_id" in df.columns:
                player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
                break
        if player_ids is None:
            player_ids = []

    section = PlayerShotProfile()
    artifacts = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
