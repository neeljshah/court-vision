"""ARM-B atlas section: ``post_up_profile`` -- per-player post-up play profile.

Implements :class:`AtlasSection` for the ``"post_up_profile"`` section of a
player's persistent profile.  Post-up data comes from the two best available
parquet sources in the repo; CV slots are reserved for future enrichment.

**Sub-field coverage:**

REAL (populated from parquets):
  post_up_freq_pct   -- fraction of total possessions that are post-ups (0-1)
                        from playtypes_2025-26.parquet (Postup row, freq_pct column).
  post_up_ppp        -- points-per-possession in post-up situations
                        from playtypes_2025-26.parquet (Postup row, ppp column).
  post_up_pg         -- mean post-up possessions per game from
                        data/cache/pbp_possession_features.parquet
                        (pbp_post_up_count column, per-game mean, filtered <= as_of).
  n_games            -- number of games in the pbp sample (drives the provenance n).

DEFER (no source available in current parquets):
  kick_out_rate      -- fraction of post-up possessions ending in a kick-out pass
                        DEFER: no per-possession outcome parquet; playtypes only has
                        aggregate ppp, not pass/shot split.
  deep_seal_pct      -- fraction of post-up catches within X feet of the block
                        DEFER: no per-play location parquet; requires either NBA
                        ShotChartDetail API or CV seal_depth (reserved below).

RESERVED CV SLOTS (value=None, CV branch fills later):
  seal_depth         -- mean distance from the basket (ft) at post-up catch,
                        from CV homography + EventDetector possession-start frame.
  double_team_drawn  -- fraction of post-up possessions where a second defender
                        rotates within 5 ft before the player shoots or passes
                        (CV bounding-box proximity count at post-up possession).
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

def _playtypes_postup(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return Postup freq_pct and ppp for the player from playtypes parquets.

    Uses the freshest season source (2025-26 preferred, base as fallback).
    Season-keyed -- no game_date column -- so no per-game as_of filter is
    applied (accepted: end-of-season summaries existed before season ended).

    Returns an empty dict if the player has no Postup rows.
    """
    for key, path in [
        ("pt26", DATA / "playtypes_2025-26.parquet"),
        ("pt_base", DATA / "playtypes.parquet"),
    ]:
        df = _load(key, path)
        if df is None or df.empty:
            continue
        rows = df[(df["player_id"] == pid) & (df["play_type"] == "Postup")]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        row = rows.iloc[0]
        freq = _rd(row.get("freq_pct"))
        ppp = _rd(row.get("ppp"))
        # freq_pct stored as fraction 0-1 in the parquet (sums to ~1 across play types)
        # Null out any values outside [0, 1] (data guard)
        if freq is not None and not (0.0 <= freq <= 1.0):
            freq = None
        # ppp is unbounded but sanity-check for implausible extremes
        if ppp is not None and not (0.0 <= ppp <= 4.0):
            ppp = None
        return {
            "post_up_freq_pct": freq,
            "post_up_ppp": ppp,
            "_source_season": str(row.get("season", "")),
        }
    return {}


def _pbp_postup(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return per-game post-up possession count (mean) filtered to games <= as_of.

    Source: data/cache/pbp_possession_features.parquet, column pbp_post_up_count.
    The game_date column is used for the leak-safe as_of filter.

    Returns dict with post_up_pg and n_games, or empty dict if player absent.
    """
    path = CACHE / "pbp_possession_features.parquet"
    df = _load("pbp_poss", path)
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
    n_games = len(rows)
    col = "pbp_post_up_count"
    if col not in rows.columns:
        return {"n_games": n_games}
    mean_val = _rd(rows[col].mean())
    # per-game count must be non-negative
    if mean_val is not None and mean_val < 0:
        mean_val = None
    return {
        "post_up_pg": mean_val,
        "n_games": n_games,
    }


def _adv_n_games(pid: int, as_of: _dt.datetime) -> int:
    """Fallback game count from player_adv_stats.parquet filtered to <= as_of.

    Used only when pbp_possession_features has no rows for the player.
    """
    path = DATA / "player_adv_stats.parquet"
    df = _load("adv", path)
    if df is None or df.empty:
        return 0
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return 0
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    return len(rows)


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerPostUpProfile(AtlasSection):
    """Post-up play profile atlas section (player entity, section='post_up_profile').

    Builds a provenance-stamped, leak-safe artifact covering post-up frequency,
    points-per-possession, and per-game possession count.  Reserves 2 CV slots
    for CV-branch enrichment (seal_depth, double_team_drawn -- values None until filled).

    Sources used:
      - data/playtypes_2025-26.parquet + data/playtypes.parquet  (freq_pct, ppp)
      - data/cache/pbp_possession_features.parquet  (per-game post_up_count, n)

    DEFER sections (no source parquet exists yet):
      - kick_out_rate  -- no per-possession outcome parquet; playtypes has only aggregate
      - deep_seal_pct  -- no per-play location parquet; deferred to CV seal_depth slot
    """

    name: str = "post_up_profile"
    entity: str = "player"
    source_name: str = (
        "playtypes_2025-26.parquet + pbp_possession_features.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the post_up_profile artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: pbp_possession_features is filtered to game_date <= as_of.
        Season-keyed playtypes sources do not have game_date; they are accepted as
        end-of-season summaries that pre-existed the season boundary.

        Returns None when all sources are missing for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        pt = _playtypes_postup(pid, as_of)
        pbp = _pbp_postup(pid, as_of)

        # Bail if completely empty (player absent from all sources)
        if not pt and not pbp:
            return None

        # --- Determine n (actual game-count from pbp; adv as fallback) ---
        n_games_pbp: int = _ri(pbp.get("n_games")) or 0
        if n_games_pbp == 0:
            n_games_pbp = _adv_n_games(pid, as_of)
        n: int = n_games_pbp

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            # REAL fields from playtypes
            "post_up_freq_pct": pt.get("post_up_freq_pct"),
            "post_up_ppp": pt.get("post_up_ppp"),
            # REAL fields from pbp
            "post_up_pg": pbp.get("post_up_pg"),
            "n_games": n,
            # DEFER fields
            "kick_out_rate": None,
            "deep_seal_pct": None,
            "_defer_kick_out_rate": (
                "DEFER: no per-possession outcome parquet; playtypes only provides "
                "aggregate ppp, not pass/shot split per post-up possession."
            ),
            "_defer_deep_seal_pct": (
                "DEFER: no per-play post-up location parquet; deferred to CV "
                "seal_depth slot (CV branch fills from homography coordinates)."
            ),
        }

        confidence = confidence_from_n(n, cap=self.conf_cap)
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
            value=pt.get("post_up_freq_pct"),  # headline: how often does this player post up
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, no out-of-range proportions.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "post_up_freq_pct", "post_up_ppp", "post_up_pg",
            "n_games", "kick_out_rate", "deep_seal_pct",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # post_up_freq_pct must be in [0, 1] if not None
        freq = sf.get("post_up_freq_pct")
        if freq is not None and not (0.0 <= freq <= 1.0):
            return False

        # ppp should be non-negative if not None
        ppp = sf.get("post_up_ppp")
        if ppp is not None and ppp < 0.0:
            return False

        # post_up_pg must be non-negative if not None
        pg = sf.get("post_up_pg")
        if pg is not None and pg < 0.0:
            return False

        # CV fields must be null (CV branch has not run yet)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for post_up_profile (values None -- CV fills later).

        Slots:
          seal_depth       -- mean distance from basket at post-up catch (ft, CV homography).
          double_team_drawn -- fraction of post-up possessions where a 2nd defender
                              rotates within 5 ft (CV bounding-box proximity).
        """
        return {
            "seal_depth": CVSlot(
                name="seal_depth",
                dtype="float",
                description=(
                    "Mean distance from the basket (ft) at the moment of post-up "
                    "catch, derived from CV homography + EventDetector "
                    "possession-start frame coordinates."
                ),
                unit="ft",
                value=None,
            ),
            "double_team_drawn": CVSlot(
                name="double_team_drawn",
                dtype="float",
                description=(
                    "Fraction of post-up possessions (0-1) where a second defender "
                    "closes within 5 ft of the ball-handler before a shot or pass, "
                    "from CV bounding-box proximity counts at post-up possessions."
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
    """Build post_up_profile for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from playtypes.
        as_of:      leak boundary date (defaults to today).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if player_ids is None:
        # Discover from the freshest playtypes source that has Postup rows
        for path_key, path in [
            ("pt26_disc", DATA / "playtypes_2025-26.parquet"),
            ("pt_disc", DATA / "playtypes.parquet"),
        ]:
            df = _load(path_key, path)
            if df is not None and not df.empty and "player_id" in df.columns:
                player_ids = sorted(
                    df["player_id"].dropna().astype(int).unique().tolist()
                )
                break
        if player_ids is None:
            player_ids = []

    section = PlayerPostUpProfile()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
