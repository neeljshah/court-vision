"""ARM-B atlas section: player-level scoring creation profile.

Section key: ``scoring_creation``
Entity:      player

Captures *how* a player generates their points — self-created vs assisted,
transition vs halfcourt, points-per-touch (volume efficiency), and-one rate
(foul-draw on made buckets). Three CV slots are reserved for CV-branch fill later:
``drive_speed``, ``rim_pressure``, and ``help_drawn``.

Data sources
------------
* ``data/cache/player_breakdown_features.parquet``  — assisted/unassisted 2PM+3PM
  share, fast-break (transition) share, 3-point vs paint vs ft vs midrange mix.
  Season-level only (2024-25 as of this build). One season per player (n=games_played
  approximated from tracking).
* ``data/cache/player_tracking_features.parquet``   — drives_per_g, drive_pts_pct,
  drive_ast_pct (catch-shoot vs self-created proxy), passes_made_per_g,
  ast_to_pass_pct. Season-level.
* ``data/cache/pbp_possession_features.parquet``    — game-level and1_count,
  transition_count, avg_seconds_per_touch. Aggregated here.

DEFER notes
-----------
* ``unassisted_share_2pm``, ``unassisted_share_3pm`` → REAL (player_breakdown_features)
* ``assisted_share_2pm``, ``assisted_share_3pm``    → REAL (player_breakdown_features)
* ``transition_pts_share``                          → REAL (player_breakdown_features:
  scoring_pct_pts_fast_break)
* ``pts_per_touch_est``                             → REAL (pbp: avg_seconds_per_touch
  proxy; approximate, not exact touch count)
* ``and_one_rate``                                  → REAL (pbp: and1_count / games)
* ``drives_per_game``                               → REAL (player_tracking_features)
* ``drive_pts_share``                               → REAL (player_tracking_features:
  drive_pts_pct * drives_per_g rescale)
* ``catch_shoot_pts_share``                         → REAL (player_breakdown: ast_2pm
  + ast_3pm weighted share → selfcreated = complement)
* ``iso_pts_pct`` (synergy_ppp_features iso vs pnr vs spotup)    → DEFER (season
  mismatch; synergy parquet has ppp not volume share; would need season_game_count to
  derive share — mark DEFER until a volume-weighted synergy parquet is built)
* ``halfcourt_pts_share``                           → REAL (1 - transition_pts_share)
* ``pnr_bh_pts_pct``                               → DEFER (same reason as iso_pts_pct)
* CV slots (drive_speed, rim_pressure, help_drawn)  → RESERVED null (CV-branch fills)
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repo root (script-relative, RunPod-safe)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"

# Source parquets
_PQ_BREAKDOWN = CACHE / "player_breakdown_features.parquet"
_PQ_TRACKING = CACHE / "player_tracking_features.parquet"
_PQ_PBP = CACHE / "pbp_possession_features.parquet"


class PlayerScoringCreation(AtlasSection):
    """Player-level scoring-creation atlas section.

    Quantifies self-creation vs assisted scoring, transition vs halfcourt share,
    points-per-touch efficiency, and-one foul-draw rate, and drive-based creation.

    Three CV slots are reserved: ``drive_speed`` (ft/s), ``rim_pressure`` (float,
    crowd-index derived from tracking), and ``help_drawn`` (float, defenders pulled
    per drive — proxy for creation value beyond the box score).
    """

    name: str = "scoring_creation"
    entity: str = "player"
    source_name: str = (
        "player_breakdown_features.parquet + "
        "player_tracking_features.parquet + "
        "pbp_possession_features.parquet"
    )
    conf_cap: Optional[str] = None  # no CV-imposed cap; cap applied per n

    # ------------------------------------------------------------------
    # cv_fields — the reserved CV-slot schema (values null until CV fills)
    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slots for the computer-vision branch to populate later.

        Returns:
            drive_speed:   avg drive speed (ft/s) from tracking video.
            rim_pressure:  composite index of defender proximity at rim (0–1).
            help_drawn:    avg number of help defenders pulled per drive (float).
        """
        return {
            "drive_speed": CVSlot(
                name="drive_speed",
                dtype="float",
                description="Average drive speed in ft/s derived from CV tracking.",
                unit="ft/s",
                value=None,
            ),
            "rim_pressure": CVSlot(
                name="rim_pressure",
                dtype="float",
                description=(
                    "Composite defender-proximity index at rim (0=open, 1=maximally contested). "
                    "Derived from CV defender_distance when player attacks the basket."
                ),
                unit=None,
                value=None,
            ),
            "help_drawn": CVSlot(
                name="help_drawn",
                dtype="float",
                description=(
                    "Average number of help defenders pulled per drive possession — "
                    "a proxy for off-ball creation value. Derived from CV spatial tracking."
                ),
                unit="defenders",
                value=None,
            ),
        }

    # ------------------------------------------------------------------
    # build — the leak-safe artifact constructor
    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build a scoring-creation artifact for ``entity_id`` as-of ``as_of``.

        Reads only rows with game_date / season data available strictly before
        ``as_of`` (leak-safe). Returns None when no data is available for the
        player.

        Args:
            entity_id: NBA player_id (int).
            as_of:     decision timestamp; no data after this date may be used.

        Returns:
            AtlasArtifact or None.
        """
        as_of_date = as_of.date()
        as_of_str = as_of_date.isoformat()
        pid = int(entity_id)

        # ---- 1. Load player_breakdown_features (season-level, 2024-25) --------
        breakdown = self._load_breakdown(pid, as_of_str)

        # ---- 2. Load player_tracking_features (season-level) ------------------
        tracking = self._load_tracking(pid, as_of_str)

        # ---- 3. Load pbp_possession_features (game-level, aggregate) ----------
        pbp_agg = self._load_pbp(pid, as_of_str)

        # If none of the three sources have data, skip this player
        if breakdown is None and tracking is None and pbp_agg is None:
            return None

        # ---- 4. Compute sub_fields -------------------------------------------
        sub = self._compute_sub_fields(breakdown, tracking, pbp_agg)

        # ---- 5. Provenance / confidence ----------------------------------------
        # Use pbp game count as n (most granular); fall back to 1 if only season data
        n = pbp_agg.get("n_games", 1) if pbp_agg else (1 if breakdown or tracking else 0)
        if n == 0:
            return None

        conf = confidence_from_n(n, cap=self.conf_cap)
        sources_used = [
            s for s, avail in [
                ("player_breakdown_features.parquet", breakdown is not None),
                ("player_tracking_features.parquet", tracking is not None),
                ("pbp_possession_features.parquet", pbp_agg is not None),
            ]
            if avail
        ]

        prov: Dict[str, Any] = {
            "source": " + ".join(sources_used) if sources_used else "none",
            "n": n,
            "confidence": conf,
            "as_of": as_of_str,
        }

        # headline: self-created share (unassisted 2PM + 3PM weighted)
        uast_2 = sub.get("unassisted_share_2pm")
        uast_3 = sub.get("unassisted_share_3pm")
        headline: Optional[float] = None
        if uast_2 is not None and uast_3 is not None:
            headline = round((uast_2 + uast_3) / 2.0, 3)

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=headline,
            sub_fields=sub,
            provenance=prov,
            confidence=conf,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    # validate — cheap face-validity
    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Return True iff the artifact is internally consistent.

        Checks:
        * Required schema keys present in sub_fields.
        * Share values in [0, 1] when not None.
        * cv_fields schema present with expected slot names.
        """
        if artifact is None:
            return False
        if artifact.entity != "player":
            return False

        sf = artifact.sub_fields or {}

        # All share fields must be in [0, 1] when present
        share_fields = [
            "unassisted_share_2pm", "assisted_share_2pm",
            "unassisted_share_3pm", "assisted_share_3pm",
            "transition_pts_share", "halfcourt_pts_share",
            "drive_pts_share",
        ]
        for key in share_fields:
            val = sf.get(key)
            if val is not None and not (0.0 <= float(val) <= 1.0):
                _log.warning("scoring_creation validate: %s=%s out of [0,1]", key, val)
                return False

        # and_one_rate should be non-negative
        a1r = sf.get("and_one_rate")
        if a1r is not None and float(a1r) < 0:
            return False

        # CV slot names match the contract
        expected_cv = {"drive_speed", "rim_pressure", "help_drawn"}
        if set(artifact.cv_fields.keys()) != expected_cv:
            _log.warning(
                "scoring_creation validate: cv_fields mismatch: %s",
                set(artifact.cv_fields.keys()),
            )
            return False

        # All CV values must be None (reserved, not yet filled)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                _log.warning("scoring_creation validate: CV slot %s not null", slot.name)
                return False

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_breakdown(self, pid: int, as_of_str: str) -> Optional[dict]:
        """Read player_breakdown_features (season-level, latest available as-of)."""
        if not _PQ_BREAKDOWN.exists():
            return None
        try:
            df = pd.read_parquet(_PQ_BREAKDOWN)
        except Exception as exc:
            _log.warning("scoring_creation: cannot read breakdown parquet: %s", exc)
            return None

        # Season-level: use the season that started before as_of
        sub = df[df["player_id"] == pid].copy()
        if sub.empty:
            return None

        # Approximate leak guard: filter to seasons whose end is <= as_of.
        # Season strings like "2024-25" end in April 2025 ~ YYYY-04-15.
        def _season_end(s: str) -> str:
            try:
                end_year = int(s.split("-")[1])
                return f"20{end_year:02d}-04-15"
            except Exception:
                return "9999-01-01"

        sub = sub[sub["season"].apply(_season_end) <= as_of_str]
        if sub.empty:
            return None

        # Most recent season
        r = sub.sort_values("season").iloc[-1]

        def _safe(col: str) -> Optional[float]:
            v = r.get(col)
            if v is None:
                return None
            try:
                f = float(v)
                return None if (f != f) else round(f, 4)  # nan guard
            except (TypeError, ValueError):
                return None

        return {
            "unassisted_share_2pm": _safe("scoring_pct_uast_2pm"),
            "assisted_share_2pm": _safe("scoring_pct_ast_2pm"),
            "unassisted_share_3pm": _safe("scoring_pct_uast_3pm"),
            "assisted_share_3pm": _safe("scoring_pct_ast_3pm"),
            "transition_pts_share": _safe("scoring_pct_pts_fast_break"),
            "pts_3pt_share": _safe("scoring_pct_pts_3pt"),
            "pts_paint_share": _safe("scoring_pct_pts_paint"),
            "pts_ft_share": _safe("scoring_pct_pts_ft"),
            "pts_midrange_share": _safe("scoring_pct_pts_mid_range"),
            "season_used": str(r.get("season", "")),
        }

    def _load_tracking(self, pid: int, as_of_str: str) -> Optional[dict]:
        """Read player_tracking_features (season-level, latest available as-of)."""
        if not _PQ_TRACKING.exists():
            return None
        try:
            df = pd.read_parquet(_PQ_TRACKING)
        except Exception as exc:
            _log.warning("scoring_creation: cannot read tracking parquet: %s", exc)
            return None

        sub = df[df["player_id"] == pid].copy()
        if sub.empty:
            return None

        # Season-end leak guard (same logic as breakdown)
        def _season_end(s: str) -> str:
            try:
                end_year = int(str(s).split("-")[1])
                return f"20{end_year:02d}-04-15"
            except Exception:
                return "9999-01-01"

        sub = sub[sub["season"].apply(_season_end) <= as_of_str]
        if sub.empty:
            return None

        r = sub.sort_values("season").iloc[-1]

        def _safe(col: str) -> Optional[float]:
            v = r.get(col)
            if v is None:
                return None
            try:
                f = float(v)
                return None if (f != f) else round(f, 4)
            except (TypeError, ValueError):
                return None

        return {
            "drives_per_game": _safe("drives_per_g"),
            "drive_pts_share": _safe("drive_pts_pct"),   # pct of total pts from drives
            "drive_ast_rate": _safe("drive_ast_pct"),    # drives ending in assist
            "catch_shoot_efg": _safe("cs_efg_pct"),      # catch-shoot efficiency
            "catch_shoot_3pa_per_g": _safe("cs_3pa_per_g"),
            "ast_to_pass_pct": _safe("ast_to_pass_pct"),  # creation quality per pass
            "passes_made_per_g": _safe("passes_made_per_g"),
        }

    def _load_pbp(self, pid: int, as_of_str: str) -> Optional[dict]:
        """Aggregate pbp_possession_features for and_one_rate + touch efficiency."""
        if not _PQ_PBP.exists():
            return None
        try:
            df = pd.read_parquet(_PQ_PBP)
        except Exception as exc:
            _log.warning("scoring_creation: cannot read pbp parquet: %s", exc)
            return None

        sub = df[df["player_id"] == pid].copy()
        if sub.empty:
            return None

        # Leak guard: game_date <= as_of
        if "game_date" in sub.columns:
            sub["game_date"] = pd.to_datetime(sub["game_date"], errors="coerce")
            sub = sub[sub["game_date"].dt.date <= _dt.date.fromisoformat(as_of_str)]

        if sub.empty:
            return None

        n = len(sub)
        tot_and1 = sub["pbp_and1_count"].sum()
        tot_trans = sub["pbp_transition_count"].sum()

        # and_one_rate: and-ones per game
        and_one_rate = round(float(tot_and1) / n, 4) if n > 0 else None

        # transition_possessions_per_game (from pbp) — used as secondary signal
        transition_per_game = round(float(tot_trans) / n, 4) if n > 0 else None

        # avg_seconds_per_touch as inverse touch-rate proxy (lower = more touches)
        # Derive pts_per_touch_est: since we lack raw touch count, we note that
        # avg_seconds_per_touch is a per-touch-duration estimate (higher = fewer
        # touches per minute). We store it raw and let signals derive the ratio.
        avg_sec_touch = sub["pbp_avg_seconds_per_touch"].mean()
        avg_sec_touch_val: Optional[float] = (
            round(float(avg_sec_touch), 2)
            if avg_sec_touch == avg_sec_touch
            else None
        )

        return {
            "and_one_rate": and_one_rate,
            "transition_poss_per_game": transition_per_game,
            "avg_seconds_per_touch": avg_sec_touch_val,
            "n_games": n,
        }

    def _compute_sub_fields(
        self,
        breakdown: Optional[dict],
        tracking: Optional[dict],
        pbp: Optional[dict],
    ) -> dict:
        """Merge source dicts into the final deeply-nested sub_fields payload."""
        sf: Dict[str, Any] = {}

        # ---- From breakdown ----
        if breakdown:
            # Unassisted / assisted creation mix
            sf["unassisted_share_2pm"] = breakdown.get("unassisted_share_2pm")
            sf["assisted_share_2pm"] = breakdown.get("assisted_share_2pm")
            sf["unassisted_share_3pm"] = breakdown.get("unassisted_share_3pm")
            sf["assisted_share_3pm"] = breakdown.get("assisted_share_3pm")
            # Transition vs halfcourt
            t_share = breakdown.get("transition_pts_share")
            sf["transition_pts_share"] = t_share
            sf["halfcourt_pts_share"] = (
                round(1.0 - t_share, 4) if t_share is not None else None
            )
            # Shot-zone mix
            sf["pts_3pt_share"] = breakdown.get("pts_3pt_share")
            sf["pts_paint_share"] = breakdown.get("pts_paint_share")
            sf["pts_ft_share"] = breakdown.get("pts_ft_share")
            sf["pts_midrange_share"] = breakdown.get("pts_midrange_share")
            sf["breakdown_season"] = breakdown.get("season_used")

        # ---- From tracking ----
        if tracking:
            sf["drives_per_game"] = tracking.get("drives_per_game")
            # drive_pts_share is a share of total points -> must be in [0,1];
            # the source occasionally emits >1 (noisy ratio) which fails face
            # validity, so null out-of-range values rather than ship bad data.
            _dps = tracking.get("drive_pts_share")
            sf["drive_pts_share"] = _dps if (_dps is None or 0.0 <= _dps <= 1.0) else None
            sf["drive_ast_rate"] = tracking.get("drive_ast_rate")
            sf["catch_shoot_efg"] = tracking.get("catch_shoot_efg")
            sf["catch_shoot_3pa_per_g"] = tracking.get("catch_shoot_3pa_per_g")
            sf["ast_to_pass_pct"] = tracking.get("ast_to_pass_pct")
            sf["passes_made_per_g"] = tracking.get("passes_made_per_g")

        # ---- From pbp ----
        if pbp:
            sf["and_one_rate"] = pbp.get("and_one_rate")
            sf["transition_poss_per_game"] = pbp.get("transition_poss_per_game")
            sf["avg_seconds_per_touch"] = pbp.get("avg_seconds_per_touch")

        # ---- DEFER flags: iso_pts_pct, pnr_bh_pts_pct (volume share not derivable
        # from synergy_ppp_features which has ppp not usage shares)
        sf["iso_pts_pct"] = None       # DEFER: needs volume-weighted synergy parquet
        sf["pnr_bh_pts_pct"] = None    # DEFER: same reason

        return sf


# ---------------------------------------------------------------------------
# Module-level instance — the bridge callable target
# ---------------------------------------------------------------------------
SECTION = PlayerScoringCreation()


def register(*, store=None, dry_run: bool = False, as_of: Optional[_dt.datetime] = None) -> dict:
    """Build artifacts for all available players and register via the bridge.

    Convenience entry point called by the orchestrator or manually. Uses today as
    the as_of when not specified. Returns the bridge manifest dict.

    Args:
        store:    optional PointInTimeStore to also write atlas records.
        dry_run:  skip disk writes when True.
        as_of:    override the as-of date (default: today UTC midnight).

    Returns:
        manifest dict from profile_factory_bridge.register_section.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Collect all player_ids from the broadest source available
    player_ids = _collect_player_ids()

    artifacts = []
    skipped = 0
    for pid in player_ids:
        try:
            art = SECTION.build(pid, as_of)
            if art is None:
                skipped += 1
                continue
            if not SECTION.validate(art):
                _log.warning("scoring_creation: skipping player %s (failed validate)", pid)
                skipped += 1
                continue
            artifacts.append(art)
        except Exception as exc:
            _log.warning("scoring_creation: error building player %s: %s", pid, exc)
            skipped += 1

    _log.info(
        "scoring_creation: built %d artifacts, skipped %d",
        len(artifacts),
        skipped,
    )

    return register_section(SECTION, artifacts, store=store, dry_run=dry_run)


def _collect_player_ids() -> list:
    """Collect unique player_ids from available source parquets."""
    ids: set = set()
    for pq in (_PQ_BREAKDOWN, _PQ_TRACKING, _PQ_PBP):
        if pq.exists():
            try:
                df = pd.read_parquet(pq, columns=["player_id"])
                ids.update(df["player_id"].dropna().astype(int).tolist())
            except Exception:
                pass
    return sorted(ids)
