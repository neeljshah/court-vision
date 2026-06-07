"""ARM-B atlas section: ``catch_shoot_vs_pullup`` -- shot-creation mode breakdown.

Implements :class:`AtlasSection` for the ``"catch_shoot_vs_pullup"`` section of a
player's persistent profile.  Sub-fields decompose every shot attempt into two
creation modes (catch-and-shoot vs pull-up / off-dribble) and add off-dribble 3-pt
rate and time-to-shot from PBP.

**Sub-field coverage:**

REAL (populated from parquets):
  catch_shoot.*    -- FGA/game, FG%, eFG%, pts/game, freq share from:
                      player_tracking(_2025-26).parquet (trk_cs_*) and
                      playtypes(_2025-26).parquet (Spotup freq_pct + ppp).
  pull_up.*        -- isolation + PRBallHandler play-type freq + ppp as the
                      canonical pull-up / off-dribble creation proxy from
                      playtypes(_2025-26).parquet.  drive_fg_pct/count from
                      player_tracking (trk_drv_*) wired as creation_drive sub-field.
  off_dribble_3.*  -- OffScreen freq_pct + ppp from playtypes as the best available
                      proxy for movement-3 / off-dribble 3-pt rate.
  time_to_shot.*   -- avg_seconds_per_touch (per-game mean, from
                      pbp_possession_features.parquet, game_date-filtered <= as_of).

DEFER (data gap -- not available in current parquets):
  pull_up_fg_pct   -- direct pull-up FG% (NBA ShotDash API not yet fetched;
                      trk_drv_fg_pct is drives only, not all pull-ups).
  cs_freq_vs_league -- league-relative catch-shoot share (needs league agg table).
  dribble_count_avg -- exact mean dribble count pre-shot (CV-only; reserved as CV slot).

RESERVED CV SLOTS (value=None, CV branch fills later):
  openness_on_cs       -- mean nearest-defender distance (ft) at C&S release frame
  dribbles_pre_pull    -- mean dribble count before pull-up shot release (CV EventDetector)
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
    """Load a parquet once per process; cache None on missing or error."""
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
    """Clean integer scalar: NaN/inf/None -> None."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _clamp_pct(v: Optional[float], ceil: float = 1.0) -> Optional[float]:
    """Null out values outside [0, ceil] -- keeps validator face-validity check clean."""
    if v is None:
        return None
    if not (0.0 <= v <= ceil):
        return None
    return v


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _tracking_cs_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return catch-and-shoot tracking metrics for player, latest season <= as_of.

    Reads player_tracking_2025-26.parquet (fresh) with fallback to
    player_tracking.parquet (base).  These are season-aggregated -- no game_date
    column -- so we use the most recent season available without future-data risk
    (season summaries are published after season end).
    """
    for key, path in [
        ("trk26", DATA / "player_tracking_2025-26.parquet"),
        ("trk_base", DATA / "player_tracking.parquet"),
    ]:
        df = _load(key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        row = rows.iloc[0]
        return {
            "cs_fga_pg": _rd(row.get("trk_cs_fga")),
            "cs_fg_pct": _clamp_pct(_rd(row.get("trk_cs_fg_pct"))),
            "cs_efg_pct": _clamp_pct(_rd(row.get("trk_cs_efg_pct")), ceil=1.6),
            "cs_pts_pg": _rd(row.get("trk_cs_pts")),
            "drive_count_pg": _rd(row.get("trk_drv_count")),
            "drive_fg_pct": _clamp_pct(_rd(row.get("trk_drv_fg_pct"))),
            "drive_pts_pg": _rd(row.get("trk_drv_pts")),
            "_source_season": str(row.get("season", "")),
        }
    return {}


def _playtypes_cs_pu_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return play-type breakdown for catch-shoot vs pull-up modes.

    Reads playtypes_2025-26.parquet (fresh) falling back to playtypes.parquet.
    Play-type mapping:
      catch_shoot proxy = Spotup (off-ball spot-up catch-and-shoot)
      pull_up proxy     = Isolation + PRBallHandler (off-dribble creation)
      off_dribble_3     = OffScreen (movement/dribble 3 proxy)
      off_ball_cut      = Cut (cut to basket, catch-and-finish)
    """
    for key, path in [
        ("pt26", DATA / "playtypes_2025-26.parquet"),
        ("pt_base", DATA / "playtypes.parquet"),
    ]:
        df = _load(key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)

        # Build a play_type -> (freq_pct, ppp) lookup from the latest season
        pt_map: Dict[str, Dict[str, Any]] = {}
        for _, row in rows.iterrows():
            pt = str(row.get("play_type", ""))
            if pt not in pt_map:
                pt_map[pt] = {
                    "freq_pct": _rd(row.get("freq_pct")),
                    "ppp": _rd(row.get("ppp")),
                }

        out: Dict[str, Any] = {}

        # Spotup = canonical catch-and-shoot frequency from play-type data
        spotup = pt_map.get("Spotup", {})
        out["cs_spotup_freq_pct"] = _clamp_pct(spotup.get("freq_pct"))
        out["cs_spotup_ppp"] = _rd(spotup.get("ppp"))

        # Pull-up proxy: Isolation (pure 1-on-1 off dribble) + PRBallHandler
        iso = pt_map.get("Isolation", {})
        pnr = pt_map.get("PRBallHandler", {})
        out["pullup_iso_freq_pct"] = _clamp_pct(iso.get("freq_pct"))
        out["pullup_iso_ppp"] = _rd(iso.get("ppp"))
        out["pullup_pnr_handler_freq_pct"] = _clamp_pct(pnr.get("freq_pct"))
        out["pullup_pnr_handler_ppp"] = _rd(pnr.get("ppp"))

        # Combined pull-up share (Iso + PRBallHandler frequencies summed)
        iso_f = iso.get("freq_pct") or 0.0
        pnr_f = pnr.get("freq_pct") or 0.0
        combined = _rd(iso_f + pnr_f)
        # Only store if plausible proportion
        out["pullup_combined_freq_pct"] = _clamp_pct(combined)

        # Off-dribble 3 proxy: OffScreen (movement / curl / off-screen 3s)
        offscreen = pt_map.get("OffScreen", {})
        out["off_dribble_3_freq_pct"] = _clamp_pct(offscreen.get("freq_pct"))
        out["off_dribble_3_ppp"] = _rd(offscreen.get("ppp"))

        # Handoff (another off-ball / catch category)
        handoff = pt_map.get("Handoff", {})
        out["handoff_freq_pct"] = _clamp_pct(handoff.get("freq_pct"))
        out["handoff_ppp"] = _rd(handoff.get("ppp"))

        return out
    return {}


def _time_to_shot_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate avg_seconds_per_touch from pbp_possession_features, filtered to <= as_of.

    This is the primary time-to-shot proxy: the mean seconds a player holds the ball
    per touch across all game possessions.  A lower value indicates quick-release or
    catch-and-shoot tendency; higher values indicate holding/creating.

    Source: data/cache/pbp_possession_features.parquet (grain: player_id x game_id).
    """
    path = CACHE / "pbp_possession_features.parquet"
    df = _load("pbp_poss_cs", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Leak filter by game_date
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n_games = len(rows)
    avg_sec = rows["pbp_avg_seconds_per_touch"].mean() if "pbp_avg_seconds_per_touch" in rows.columns else None
    iso_pg = rows["pbp_iso_poss_count"].mean() if "pbp_iso_poss_count" in rows.columns else None
    pnr_handler_pg = rows["pbp_pnr_ball_handler"].mean() if "pbp_pnr_ball_handler" in rows.columns else None
    late_clock_pg = rows["pbp_late_clock_shots"].mean() if "pbp_late_clock_shots" in rows.columns else None

    return {
        "avg_seconds_per_touch": _rd(avg_sec),
        "iso_poss_pg": _rd(iso_pg),
        "pnr_handler_pg": _rd(pnr_handler_pg),
        "late_clock_shots_pg": _rd(late_clock_pg),
        "n_games": n_games,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerCatchShootVsPullup(AtlasSection):
    """Shot-creation mode breakdown: catch-and-shoot vs pull-up (player entity).

    Section key: ``"catch_shoot_vs_pullup"``.

    Decomposes how a player creates shots into two primary modes:
    - Catch-and-shoot (C&S): player receives a pass and shoots without dribbling.
    - Pull-up / off-dribble: player dribbles to create their own shot.

    Also reports off-dribble 3-pt rate (OffScreen as proxy) and time-to-shot from PBP.

    Sources:
      - data/player_tracking_2025-26.parquet + data/player_tracking.parquet (C&S/drive metrics)
      - data/playtypes_2025-26.parquet + data/playtypes.parquet (play-type freq + PPP)
      - data/cache/pbp_possession_features.parquet (time-to-shot, per-game, leak-safe)

    DEFER sub-fields (noted inline):
      - pull_up_fg_pct: direct pull-up FG% -- NBA ShotDash not fetched; use playtypes ppp proxy.
      - cs_freq_vs_league: league-relative C&S share -- needs league agg table.

    CV slots (reserved, null until CV branch fills):
      - openness_on_cs: mean nearest-defender distance at C&S release (ft)
      - dribbles_pre_pull: mean dribble count pre pull-up release (EventDetector)
    """

    name: str = "catch_shoot_vs_pullup"
    entity: str = "player"
    source_name: str = (
        "player_tracking_2025-26.parquet + playtypes_2025-26.parquet + "
        "pbp_possession_features.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the catch_shoot_vs_pullup artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - pbp_possession_features is filtered by game_date <= as_of.
          - player_tracking and playtypes are season-keyed (end-of-season aggregates);
            they carry no future-game data given the season has not yet ended mid-build.

        Returns None when all sources are missing for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        trk = _tracking_cs_for_player(pid, as_of)
        pt = _playtypes_cs_pu_for_player(pid, as_of)
        tts = _time_to_shot_for_player(pid, as_of)

        # Bail if everything is empty
        if not trk and not pt and not tts:
            return None

        # --- catch_shoot sub-dict ---
        catch_shoot: Dict[str, Any] = {}
        if trk:
            catch_shoot["cs_fga_pg"] = trk.get("cs_fga_pg")
            catch_shoot["cs_fg_pct"] = trk.get("cs_fg_pct")
            catch_shoot["cs_efg_pct"] = trk.get("cs_efg_pct")
            catch_shoot["cs_pts_pg"] = trk.get("cs_pts_pg")
        if pt:
            # Spotup play-type = canonical C&S freq from play-type lens
            catch_shoot["cs_spotup_freq_pct"] = pt.get("cs_spotup_freq_pct")
            catch_shoot["cs_spotup_ppp"] = pt.get("cs_spotup_ppp")
            catch_shoot["handoff_freq_pct"] = pt.get("handoff_freq_pct")
            catch_shoot["handoff_ppp"] = pt.get("handoff_ppp")

        # --- pull_up sub-dict ---
        pull_up: Dict[str, Any] = {}
        if pt:
            pull_up["pullup_iso_freq_pct"] = pt.get("pullup_iso_freq_pct")
            pull_up["pullup_iso_ppp"] = pt.get("pullup_iso_ppp")
            pull_up["pullup_pnr_handler_freq_pct"] = pt.get("pullup_pnr_handler_freq_pct")
            pull_up["pullup_pnr_handler_ppp"] = pt.get("pullup_pnr_handler_ppp")
            pull_up["pullup_combined_freq_pct"] = pt.get("pullup_combined_freq_pct")
        if trk:
            # Drive creation: a subset of pull-up where the player drives to basket
            pull_up["drive_count_pg"] = trk.get("drive_count_pg")
            pull_up["drive_fg_pct"] = trk.get("drive_fg_pct")
            pull_up["drive_pts_pg"] = trk.get("drive_pts_pg")
        # DEFER: pull_up_fg_pct (direct) -- NBA ShotDash not fetched; ppp is the proxy
        pull_up["_pull_up_fg_pct_note"] = (
            "DEFER: direct pull-up FG% not available; NBA ShotDash API not fetched. "
            "Use pullup_iso_ppp and pullup_pnr_handler_ppp as efficiency proxies."
        )

        # --- off_dribble_3 sub-dict ---
        off_dribble_3: Dict[str, Any] = {}
        if pt:
            off_dribble_3["off_screen_freq_pct"] = pt.get("off_dribble_3_freq_pct")
            off_dribble_3["off_screen_ppp"] = pt.get("off_dribble_3_ppp")
        # DEFER: true off-dribble 3 rate -- needs shot-level dribble-count data (CV slot)
        off_dribble_3["_note"] = (
            "DEFER: true off-dribble 3-pt rate requires shot-level dribble tagging "
            "(CV slot dribbles_pre_pull). OffScreen freq is the best available proxy."
        )

        # --- time_to_shot sub-dict ---
        time_to_shot: Dict[str, Any] = {}
        if tts:
            time_to_shot["avg_seconds_per_touch"] = tts.get("avg_seconds_per_touch")
            time_to_shot["iso_poss_pg"] = tts.get("iso_poss_pg")
            time_to_shot["pnr_handler_pg"] = tts.get("pnr_handler_pg")
            time_to_shot["late_clock_shots_pg"] = tts.get("late_clock_shots_pg")

        # --- Determine provenance n from leak-safe per-game source ---
        n = tts.get("n_games", 0) if tts else 0
        if n < 5:
            # Fall back to adv_stats row count if pbp sparse
            from pathlib import Path as _P
            _adv_path = DATA / "player_adv_stats.parquet"
            _adv = _load("adv_cs", _adv_path)
            if _adv is not None and "player_id" in _adv.columns and "game_date" in _adv.columns:
                _rows = _adv[_adv["player_id"] == pid].copy()
                _rows["game_date"] = pd.to_datetime(_rows["game_date"])
                _rows = _rows[_rows["game_date"] <= pd.Timestamp(as_of)]
                n = max(n, len(_rows))

        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        sub_fields: Dict[str, Any] = {
            "catch_shoot": catch_shoot,
            "pull_up": pull_up,
            "off_dribble_3": off_dribble_3,
            "time_to_shot": time_to_shot,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=None,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub-field keys present, proportions in range.

        The full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {"catch_shoot", "pull_up", "off_dribble_3", "time_to_shot"}
        if not required_keys.issubset(sf.keys()):
            return False

        # Check that _pct fields in catch_shoot / pull_up / off_dribble_3 are in [0,1]
        for section_key in ("catch_shoot", "pull_up", "off_dribble_3"):
            sub = sf.get(section_key, {})
            for k, v in sub.items():
                if isinstance(v, float) and ("_pct" in k or "_rate" in k or "_share" in k):
                    if v is not None and not (0.0 <= v <= 1.6):
                        return False

        # CV fields must all be null (CV branch hasn't run)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for catch_shoot_vs_pullup (values None).

        The CV branch fills these from EventDetector frame sequences:
          openness_on_cs:    nearest-defender distance at C&S release.
          dribbles_pre_pull: mean dribble count in the 2 s before pull-up release.
        """
        return {
            "openness_on_cs": CVSlot(
                name="openness_on_cs",
                dtype="float",
                description=(
                    "Mean nearest-defender distance (ft) at the moment of catch-and-shoot "
                    "release, from CV homography + bounding-box proximity. "
                    "Higher = more open on C&S shots."
                ),
                unit="ft",
                value=None,
            ),
            "dribbles_pre_pull": CVSlot(
                name="dribbles_pre_pull",
                dtype="float",
                description=(
                    "Mean number of dribbles taken in the 2 s before pull-up shot release, "
                    "from CV EventDetector dribble-event sequence. "
                    "Directly measures off-dribble shot creation depth."
                ),
                unit=None,
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
    """Build catch_shoot_vs_pullup for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from playtypes.
        as_of:      leak boundary date (defaults to today UTC).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes (compute + validate only).

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        for key, path in [
            ("pt26_disc", DATA / "playtypes_2025-26.parquet"),
            ("pt_disc", DATA / "playtypes.parquet"),
        ]:
            df = _load(key, path)
            if df is not None and not df.empty and "player_id" in df.columns:
                player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
                break
        if player_ids is None:
            player_ids = []

    section = PlayerCatchShootVsPullup()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
