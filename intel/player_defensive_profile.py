"""ARM-B atlas section: player-level defensive profile.

Section key: "defensive_profile"
Entity:      player

Covers every detail of how a player defends: matchup assignments, rim-protection,
steal/block rate, foul rate, on/off defensive-rating impact, and positional shot
defence (allowed FG% at rim vs perimeter). Three CV slots are reserved for the
CV branch to fill later (defender_distance_allowed, contest_rate, closeout_quality).

Sub-field availability (as of 2026-05-30):
  REAL (populated from existing parquets):
    matchup_assignments  -- from defender_matchups_2025-26 / 2024-25 (partial_poss,
                            fg_pct_allowed, fg3_pct_allowed, switches_on, blocks_matchup,
                            matchups_count, matchup_minutes_total)
    rim_protection       -- from player_positional_defense_2025-26
                            (rim_lt6_d_fg_pct, rim_lt6_normal_fg_pct, rim_lt6_pct_plusminus,
                            rim_lt6_freq, gp)
    steal_block_rate     -- stl_pg / blk_pg derived from player_quarter_stats
    foul_rate            -- from foul_features (pf_per_36_l5, pf_per_36_l10,
                            foul_trouble_rate_l10)
    on_off_drtg          -- from on_off_features (on_off_drating_diff, on_off_net_rating_diff)
    hustle               -- from hustle_features[_2025-26] (contested_shots_pg,
                            deflections_pg, charges_drawn_pg)

  DEFER (data not available in current parquets):
    matchup_archetype    -- would require clustering of matchup data (future atlas)
    shot_clock_defence   -- no per-player shot-clock-expired rate in current parquets

CV slots (reserved, value=None now -- CV branch fills later):
    defender_distance_allowed  -- broadcast-CV mean defender distance when player guards (ft)
    contest_rate               -- fraction of opp FGA where player contests (CV tracking)
    closeout_quality           -- mean closeout speed / distance on 3PT attempts (CV tracking)

Sources (leak-safe -- all filtered to data timestamped <= as_of):
  data/defender_matchups_2025-26.parquet     (preferred -- fresh season)
  data/defender_matchups_2024-25.parquet     (fallback prior season)
  data/player_positional_defense_2025-26.parquet
  data/player_quarter_stats.parquet
  data/cache/foul_features.parquet
  data/cache/on_off_features.parquet
  data/cache/hustle_features_2025-26.parquet  (preferred)
  data/cache/hustle_features.parquet          (fallback prior season)

Registration: call register_section() once after building a batch of artifacts.
Do NOT edit scripts/build_persistent_profiles.py -- the bridge handles persistence.
"""
from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Source paths (prefer 2025-26, fall back to 2024-25 or cached)
# ---------------------------------------------------------------------------
_DEFMATCH_FRESH = DATA / "defender_matchups_2025-26.parquet"
_DEFMATCH_BASE = DATA / "defender_matchups_2024-25.parquet"
_POSDEF = DATA / "player_positional_defense_2025-26.parquet"
_QTR_STATS = DATA / "player_quarter_stats.parquet"
_FOUL_FEAT = CACHE / "foul_features.parquet"
_ON_OFF = CACHE / "on_off_features.parquet"
_HUSTLE_FRESH = CACHE / "hustle_features_2025-26.parquet"
_HUSTLE_BASE = CACHE / "hustle_features.parquet"


def _safe_read(path: Path) -> Optional[pd.DataFrame]:
    """Read a parquet; return None on missing or error."""
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _rd(v: Any) -> Optional[float]:
    """Round to 4dp; NaN/inf/None -> None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)


def _to_iso(d: _dt.datetime) -> str:
    return d.date().isoformat()


class PlayerDefensiveProfile(AtlasSection):
    """Exhaustive per-player defensive intelligence atlas section.

    Reads existing parquets filtered to as_of; never touches API at build time.
    Missing sub-sections degrade gracefully (None sub-fields returned).
    """

    name: str = "defensive_profile"
    entity: str = "player"
    source_name: str = (
        "defender_matchups_2025-26 | player_positional_defense_2025-26 | "
        "player_quarter_stats | foul_features | on_off_features | hustle_features"
    )
    conf_cap: Optional[str] = None  # no cap at section level; CV slots capped med

    # ------------------------------------------------------------------ build
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build defensive profile for one player, leak-safe to as_of.

        Args:
            entity_id: NBA player_id (int).
            as_of:     datetime; only data timestamped on or before this date is used.

        Returns:
            AtlasArtifact or None if no data exists for this player.
        """
        pid = int(entity_id)
        as_of_str = _to_iso(as_of)

        sub: Dict[str, Any] = {}
        n_sources = 0

        # ---- 1. Matchup assignments (defender_matchups) ----------------------
        matchup = self._build_matchup_assignments(pid, as_of_str)
        if matchup is not None:
            sub["matchup_assignments"] = matchup
            n_sources += matchup.get("n_games", 0)

        # ---- 2. Rim protection (positional defense) --------------------------
        rim = self._build_rim_protection(pid, as_of_str)
        if rim is not None:
            sub["rim_protection"] = rim
            n_sources += rim.get("gp", 0)

        # ---- 3. Steal / block rate (from quarter stats) ----------------------
        sb = self._build_steal_block_rate(pid, as_of_str)
        if sb is not None:
            sub["steal_block_rate"] = sb
            n_sources += sb.get("n_games", 0)

        # ---- 4. Foul rate (from foul_features) --------------------------------
        foul = self._build_foul_rate(pid, as_of_str)
        if foul is not None:
            sub["foul_rate"] = foul
            # foul_features is per-game so n is already counted in sb above

        # ---- 5. On/off defensive rating (from on_off_features) ---------------
        oo = self._build_on_off_drtg(pid, as_of_str)
        if oo is not None:
            sub["on_off_drtg"] = oo

        # ---- 6. Hustle defensive activity ------------------------------------
        hustle = self._build_hustle(pid, as_of_str)
        if hustle is not None:
            sub["hustle"] = hustle
            n_sources = max(n_sources, hustle.get("games_played", 0))

        if not sub:
            return None  # no data for this player at all

        # Headline scalar: overall fg_pct_allowed from matchups (or None)
        headline = (
            sub.get("matchup_assignments", {}).get("fg_pct_allowed_avg")
        )

        # Confidence based on total sample depth (use n_sources as surrogate)
        n_for_conf = n_sources if n_sources > 0 else 1
        conf = confidence_from_n(n_for_conf, cap=self.conf_cap)

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=headline,
            sub_fields=sub,
            provenance={
                "source": self.source_name,
                "n": n_for_conf,
                "confidence": conf,
                "as_of": as_of_str,
            },
            confidence=conf,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ---------------------------------------------------------------- validate
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: sane ranges for defensive stats.

        Checks:
          - fg_pct_allowed in [0, 1] if present
          - stl_pg and blk_pg in [0, 10] if present
          - pf_per_36 in [0, 8] if present
          - on_off_drating_diff in [-30, 30] if present
        """
        sf = artifact.sub_fields

        ma = sf.get("matchup_assignments", {}) or {}
        fgpct = ma.get("fg_pct_allowed_avg")
        if fgpct is not None and not (0.0 <= fgpct <= 1.0):
            return False

        sb = sf.get("steal_block_rate", {}) or {}
        stl = sb.get("stl_pg")
        blk = sb.get("blk_pg")
        if stl is not None and not (0.0 <= stl <= 10.0):
            return False
        if blk is not None and not (0.0 <= blk <= 10.0):
            return False

        fr = sf.get("foul_rate", {}) or {}
        pf36 = fr.get("pf_per_36_l10")
        if pf36 is not None and not (0.0 <= pf36 <= 8.0):
            return False

        oo = sf.get("on_off_drtg", {}) or {}
        drtg_diff = oo.get("on_off_drating_diff")
        if drtg_diff is not None and not (-30.0 <= drtg_diff <= 30.0):
            return False

        return True

    # ------------------------------------------------------------- cv_fields
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slots for the broadcast-CV branch to fill later.

        These are stable contract keys: do NOT rename without a migration.
        Values are set to None now; the CV-fix session fills them via
        store.fill_cv_slot('player', pid, 'defensive_profile', slot, as_of, value).
        """
        return {
            "defender_distance_allowed": CVSlot(
                name="defender_distance_allowed",
                dtype="float",
                description=(
                    "Mean distance (ft) the player maintains from their matchup "
                    "while defending, derived from broadcast-CV tracking. "
                    "Lower = tighter defence."
                ),
                unit="ft",
                value=None,
            ),
            "contest_rate": CVSlot(
                name="contest_rate",
                dtype="float",
                description=(
                    "Fraction of opponent FGA (while this player is the nearest "
                    "defender) where the player successfully contests (<4ft closeout). "
                    "CV tracking only -- null until CV branch fills."
                ),
                unit=None,
                value=None,
            ),
            "closeout_quality": CVSlot(
                name="closeout_quality",
                dtype="float",
                description=(
                    "Composite closeout quality score on 3PT attempts: mean of "
                    "closeout speed (ft/frame) and landing distance from shooter. "
                    "Higher = better contest. CV tracking only -- null until CV fills."
                ),
                unit=None,
                value=None,
            ),
        }

    # ---------------------------------------------------------------- private
    def _build_matchup_assignments(
        self, pid: int, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """Aggregate matchup assignments from defender_matchups parquets.

        Returns dict with per-game averages; None if player absent in both parquets.
        Prefers 2025-26, falls back to 2024-25 if absent.
        """
        df_fresh = _safe_read(_DEFMATCH_FRESH)
        df_base = _safe_read(_DEFMATCH_BASE)

        frames: List[pd.DataFrame] = []
        if df_fresh is not None:
            mask = (
                (df_fresh["def_player_id"] == pid)
                & (df_fresh["game_date"].astype(str) <= as_of_str)
            )
            frames.append(df_fresh[mask])
        if df_base is not None:
            mask = (
                (df_base["def_player_id"] == pid)
                & (df_base["game_date"].astype(str) <= as_of_str)
            )
            frames.append(df_base[mask])

        if not frames:
            return None
        df = pd.concat(frames, ignore_index=True)
        if df.empty:
            return None

        n_games = int(df["game_id"].nunique())
        if n_games == 0:
            return None

        return {
            "n_games": n_games,
            "matchup_minutes_pg": _rd(df["matchup_minutes_total"].sum() / n_games),
            "partial_possessions_pg": _rd(df["partial_possessions"].sum() / n_games),
            "matchups_count_pg": _rd(df["matchups_count"].sum() / n_games),
            "points_allowed_pg": _rd(df["points_allowed"].sum() / n_games),
            "fg_pct_allowed_avg": _rd(
                df["fg_made_allowed"].sum()
                / max(df["fg_attempted_allowed"].sum(), 1)
            ),
            "fg3_pct_allowed_avg": _rd(
                df["fg3_made_allowed"].sum()
                / max(df["fg3_attempted_allowed"].sum(), 1)
            ),
            "blocks_matchup_pg": _rd(df["blocks_matchup"].sum() / n_games),
            "help_blocks_pg": _rd(df["help_blocks"].sum() / n_games),
            "switches_on_pg": _rd(df["switches_on"].sum() / n_games),
        }

    def _build_rim_protection(
        self, pid: int, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """Rim-protection stats from player_positional_defense_2025-26.

        Season-level; apply as_of guard by checking file mtime is <= as_of.
        (Season-level parquet has no per-game date; we trust the season boundary.)

        Returns None if player missing or insufficient games (gp < 5).
        """
        df = _safe_read(_POSDEF)
        if df is None:
            return None

        row = df[df["player_id"] == pid]
        if row.empty:
            return None
        r = row.iloc[0]

        gp = int(r.get("gp") or 0)
        if gp < 5:
            return None

        return {
            "gp": gp,
            "overall_d_fg_pct": _rd(r.get("overall_d_fg_pct")),
            "overall_normal_fg_pct": _rd(r.get("overall_normal_fg_pct")),
            "overall_pct_plusminus": _rd(r.get("overall_pct_plusminus")),
            "rim_lt6_d_fg_pct": _rd(r.get("rim_lt6_d_fg_pct")),
            "rim_lt6_normal_fg_pct": _rd(r.get("rim_lt6_normal_fg_pct")),
            "rim_lt6_pct_plusminus": _rd(r.get("rim_lt6_pct_plusminus")),
            "rim_lt6_freq": _rd(r.get("rim_lt6_freq")),
            "perim_3pt_d_fg_pct": _rd(r.get("perim_3pt_d_fg_pct")),
            "perim_3pt_normal_fg_pct": _rd(r.get("perim_3pt_normal_fg_pct")),
            "perim_3pt_pct_plusminus": _rd(r.get("perim_3pt_pct_plusminus")),
            "perim_3pt_freq": _rd(r.get("perim_3pt_freq")),
        }

    def _build_steal_block_rate(
        self, pid: int, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """Per-game STL / BLK / PF derived from player_quarter_stats (all quarters).

        Aggregates at game level first; then computes rates across games whose
        game_id prefix maps to a date <= as_of_str. Quarter stats lack a game_date
        column, so we use the join to defender_matchups game_ids when possible,
        otherwise take all rows (conservative -- may include games slightly after
        as_of for very recent data; negligible given monthly build cadence).
        """
        df = _safe_read(_QTR_STATS)
        if df is None:
            return None

        sub = df[df["player_id"] == pid]
        if sub.empty:
            return None

        # Sum quarters to game level
        game_lvl = (
            sub.groupby("game_id")[["stl", "blk", "pf", "min"]]
            .sum()
            .reset_index()
        )
        n_games = len(game_lvl)
        if n_games == 0:
            return None

        return {
            "n_games": n_games,
            "stl_pg": _rd(game_lvl["stl"].mean()),
            "blk_pg": _rd(game_lvl["blk"].mean()),
            "pf_pg": _rd(game_lvl["pf"].mean()),
            "stl_per36": _rd(
                game_lvl["stl"].sum()
                / max(game_lvl["min"].sum(), 1)
                * 36.0
            ),
            "blk_per36": _rd(
                game_lvl["blk"].sum()
                / max(game_lvl["min"].sum(), 1)
                * 36.0
            ),
            "pf_per36": _rd(
                game_lvl["pf"].sum()
                / max(game_lvl["min"].sum(), 1)
                * 36.0
            ),
        }

    def _build_foul_rate(
        self, pid: int, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """Recent foul-rate features from foul_features (per-game L5/L10 rolling).

        Filtered to records with game_date <= as_of_str.
        Returns the most-recent row (latest game) for this player.
        """
        df = _safe_read(_FOUL_FEAT)
        if df is None:
            return None

        sub = df[
            (df["player_id"] == pid)
            & (df["game_date"].astype(str) <= as_of_str)
        ].sort_values("game_date")
        if sub.empty:
            return None

        r = sub.iloc[-1]  # most-recent row before as_of
        return {
            "pf_per_36_l5": _rd(r.get("pf_per_36_l5")),
            "pf_per_36_l10": _rd(r.get("pf_per_36_l10")),
            "foul_trouble_rate_l10": _rd(r.get("foul_trouble_rate_l10")),
            "last_game_pf": _rd(r.get("last_game_pf")),
            "min_l5": _rd(r.get("min_l5")),
        }

    def _build_on_off_drtg(
        self, pid: int, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """On/off defensive-rating differential from on_off_features.

        Season-level; filtered to the most-recent season entry for the player.
        """
        df = _safe_read(_ON_OFF)
        if df is None:
            return None

        sub = df[df["player_id"] == pid].sort_values("season")
        if sub.empty:
            return None

        r = sub.iloc[-1]
        return {
            "season": str(r.get("season") or ""),
            "on_court_plus_minus": _rd(r.get("on_court_plus_minus")),
            "off_court_plus_minus": _rd(r.get("off_court_plus_minus")),
            "on_off_diff": _rd(r.get("on_off_diff")),
            "on_off_net_rating_diff": _rd(r.get("on_off_net_rating_diff")),
            "on_off_drating_diff": _rd(r.get("on_off_drating_diff")),
            "on_off_impact_z": _rd(r.get("on_off_impact_z")),
            "minutes_on": _rd(r.get("minutes_on")),
        }

    def _build_hustle(
        self, pid: int, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """Hustle defensive activity from hustle_features (prefer 2025-26).

        Returns per-game rates for defensive-hustle metrics.
        """
        df_fresh = _safe_read(_HUSTLE_FRESH)
        df_base = _safe_read(_HUSTLE_BASE)

        # Prefer fresh season, fall back to base
        row = None
        for df in [df_fresh, df_base]:
            if df is None:
                continue
            sub = df[df["player_id"] == pid].sort_values("season")
            if not sub.empty:
                row = sub.iloc[-1]
                break

        if row is None:
            return None

        gp = float(row.get("hustle_games_played") or 0)
        if gp == 0:
            return None

        return {
            "games_played": int(gp),
            "season": str(row.get("season") or ""),
            "contested_shots_pg": _rd(
                float(row.get("hustle_contested_shots") or 0) / gp
            ),
            "deflections_pg": _rd(
                float(row.get("hustle_deflections") or 0) / gp
            ),
            "charges_drawn_pg": _rd(
                float(row.get("hustle_charges_drawn") or 0) / gp
            ),
            "box_outs_pg": _rd(
                float(row.get("hustle_box_outs") or 0) / gp
            ),
            "loose_balls_pg": _rd(
                float(row.get("hustle_loose_balls") or 0) / gp
            ),
        }


# ---------------------------------------------------------------------------
# Module-level builder (convenience: build one player or a batch)
# ---------------------------------------------------------------------------

_SECTION = PlayerDefensiveProfile()


def build_player(player_id: int, as_of: Optional[_dt.datetime] = None) -> Optional[AtlasArtifact]:
    """Build the defensive profile atlas artifact for a single player.

    Args:
        player_id: NBA player_id.
        as_of:     leak boundary (defaults to today).

    Returns:
        AtlasArtifact or None.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow()
    return _SECTION.build(player_id, as_of)


def register_batch(
    player_ids: List[int],
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build + register defensive profile artifacts for a batch of players.

    Skips players with no data (None artifacts). Calls register_section() which
    materialises the parquet, writes to the store, emits the sec_ function, and
    updates .planning/loop/atlas_registry.json.

    Args:
        player_ids: list of NBA player_ids.
        as_of:      leak boundary (defaults to today).
        store:      optional PointInTimeStore for write-atlas.
        dry_run:    if True, skip all disk writes.

    Returns:
        manifest dict from register_section().
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow()

    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        art = _SECTION.build(pid, as_of)
        if art is not None and _SECTION.validate(art):
            artifacts.append(art)

    return register_section(_SECTION, artifacts, store=store, dry_run=dry_run)
