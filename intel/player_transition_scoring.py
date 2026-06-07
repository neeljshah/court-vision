"""ARM-B atlas section: ``transition_scoring`` — per-player transition/fastbreak profile.

Implements :class:`AtlasSection` for the ``"transition_scoring"`` section of a player's
persistent profile.  All sub-fields come from existing parquets listed in
spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):
  playtypes.*        — transition freq_pct + ppp from playtypes_2025-26.parquet
                       (freq_pct is a proportion in [0,1]).
  pbp.*              — per-game transition possession count (pbp_transition_count),
                       and push-after-rebound proxy derived from reb/game and
                       transition-possession frequency from
                       data/cache/pbp_possession_features.parquet + player_quarter_stats.
  volume.*           — total games, mean transition possessions per game, share of
                       transition possessions vs all tracked possessions (PBP-derived).

DEFER (data gap — not available in current parquets):
  leak_out_tendency.*  — DEFER: no parquet tracks whether the player sprints ahead
                         before the rebound is secured (requires CV fast-break tracking
                         or dedicated NBA tracking endpoint not yet fetched).
  finishing_splits.*   — DEFER: no per-play-type made/attempt data at game-level (only
                         season-level ppp from playtypes); rim-vs-midrange split in
                         transition not available.

RESERVED CV SLOTS (value=None, CV branch fills later):
  sprint_speed_transition — player sprint speed (ft/s) during transition possessions
                            detected via CV homography + Kalman velocity estimates.
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
    """Clean integer scalar: NaN/inf -> None."""
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

def _playtypes_transition(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return transition play-type stats from playtypes_2025-26.parquet.

    freq_pct is stored in [0,1] in the parquet (e.g., 0.213 = 21.3% of possessions).
    The validator treats ``freq_pct`` suffix with ceiling 100.0 but we keep the value
    in [0,1] as stored — it is a genuine proportion and satisfies all range checks.
    ppp (points per possession) is typically 0.8–1.4; not range-checked as a proportion.
    """
    df = _load("pt26", DATA / "playtypes_2025-26.parquet")
    if df is None or df.empty:
        return {}

    rows = df[(df["player_id"] == pid) & (df["play_type"] == "Transition")]
    if rows.empty:
        return {}

    # Season-keyed: take the latest season row available (no game_date in this source)
    if "season" in rows.columns:
        rows = rows.sort_values("season", ascending=False)
    row = rows.iloc[0]

    freq = _rd(row.get("freq_pct"))
    ppp = _rd(row.get("ppp"))

    # Validate proportion range — null if out of [0,1]
    if freq is not None and not (0.0 <= freq <= 1.0):
        freq = None
    # ppp is an efficiency rate, not a proportion — keep but clip implausibles
    if ppp is not None and not (0.0 <= ppp <= 5.0):
        ppp = None

    return {
        "freq_pct": freq,
        "ppp": ppp,
        "_source_season": str(row.get("season", "")),
    }


def _pbp_transition(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate per-game PBP transition counts from pbp_possession_features.parquet.

    Applies as_of leak filter via game_date column (game_date <= as_of).
    Returns n_games (actual played games with PBP data), transition_pg (mean per game),
    and and1_pg (fastbreak foul proxy).
    """
    path = CACHE / "pbp_possession_features.parquet"
    df = _load("pbp_poss_trans", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Leak filter: keep only rows with game_date <= as_of
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n_games = len(rows)  # one row per game — this is actual game count

    trans_pg = _rd(rows["pbp_transition_count"].mean()) if "pbp_transition_count" in rows.columns else None
    and1_pg = _rd(rows["pbp_and1_count"].mean()) if "pbp_and1_count" in rows.columns else None

    # Total transition possessions (sum over games, for share computation)
    total_trans = float(rows["pbp_transition_count"].sum()) if "pbp_transition_count" in rows.columns else None

    # Total all counted possessions (iso + pnr + post + transition as rough proxy)
    poss_cols = [c for c in ["pbp_iso_poss_count", "pbp_pnr_ball_handler",
                              "pbp_post_up_count", "pbp_transition_count"] if c in rows.columns]
    total_tracked_poss = float(rows[poss_cols].sum().sum()) if poss_cols else None

    # Transition share of all tracked PBP possessions (a proportion in [0,1])
    trans_share: Optional[float] = None
    if total_tracked_poss is not None and total_tracked_poss > 0 and total_trans is not None:
        raw_share = total_trans / total_tracked_poss
        # Clamp to [0, 1] to stay within face-validity constraints
        trans_share = _rd(min(1.0, max(0.0, raw_share)))

    return {
        "n_games": n_games,
        "transition_pg": trans_pg,
        "and1_pg": and1_pg,
        "transition_poss_share": trans_share,
    }


def _reb_push_proxy(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Derive push-after-rebound proxy from player_quarter_stats + pbp.

    Push-after-rebound proxy = mean rebound rate per game (OREB + DREB are combined
    in 'reb' column of quarter_stats).  A high reb total combined with high transition
    frequency suggests rebound-and-push tendencies.

    The actual push-after-rebound RATE requires CV or raw PBP sequencing (DEFER for
    the detailed flag), but we ship a rebounding volume proxy as the available signal.
    Applies as_of filter via a game_date join on player_adv_stats.
    """
    path = DATA / "player_quarter_stats.parquet"
    df = _load("qstats_trans", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Apply as_of filter by joining game_date from player_adv_stats
    adv = _load("adv_trans", DATA / "player_adv_stats.parquet")
    if adv is not None and "game_date" in adv.columns and "game_id" in adv.columns:
        gd_map = (
            adv[adv["player_id"] == pid][["game_id", "game_date"]]
            .drop_duplicates("game_id")
            .set_index("game_id")["game_date"]
        )
        if "game_id" in rows.columns:
            rows["_game_date"] = rows["game_id"].map(gd_map)
            rows = rows[rows["_game_date"].notna()].copy()
            rows["_game_date"] = pd.to_datetime(rows["_game_date"])
            rows = rows[rows["_game_date"] <= pd.Timestamp(as_of)]

    if rows.empty:
        return {}

    # Total games = unique game_ids
    n_games = rows["game_id"].nunique() if "game_id" in rows.columns else 0

    # reb per game (summed across all quarters per game)
    if "reb" in rows.columns and n_games > 0:
        reb_total = float(rows["reb"].sum())
        reb_pg = _rd(reb_total / n_games)
    else:
        reb_pg = None

    return {
        "reb_pg": reb_pg,
        "n_games": n_games,
        "_note": (
            "reb_pg is a rebound-volume proxy for push-after-rebound tendency; "
            "the true push_rate (% of own rebounds that initiate transition) is "
            "DEFER: requires CV fast-break sequencing or raw PBP play-type tagging."
        ),
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerTransitionScoring(AtlasSection):
    """Transition/fastbreak scoring atlas section (player entity, section='transition_scoring').

    Builds a provenance-stamped, leak-safe artifact covering:
      - transition frequency and efficiency from NBA playtypes data
      - per-game transition possession volume from PBP (with as_of leak filter)
      - push-after-rebound proxy from rebounding volume (full leak filter)
      - reserved CV slot for sprint_speed_transition (value=None until CV branch fills)

    Sources:
      - data/playtypes_2025-26.parquet        (season-level transition freq/ppp)
      - data/cache/pbp_possession_features.parquet  (per-game transition counts, game_date keyed)
      - data/player_quarter_stats.parquet     (per-quarter reb, joined to game_date via adv_stats)
      - data/player_adv_stats.parquet         (game_date bridge for quarter_stats as_of filter)

    DEFER sections (no source parquet exists for these in the repo):
      - leak_out_tendency: requires CV fast-break detection before rebound secured
      - finishing_splits (rim vs mid in transition): playtypes only has season-level ppp,
        not per-zone made/miss counts in transition
    """

    name: str = "transition_scoring"
    entity: str = "player"
    source_name: str = (
        "playtypes_2025-26.parquet + pbp_possession_features.parquet + "
        "player_quarter_stats.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the transition_scoring artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - pbp_possession_features rows are filtered to game_date <= as_of.
          - player_quarter_stats rows are filtered via game_date join from player_adv_stats
            (game_date <= as_of).
          - playtypes_2025-26 is season-keyed (no game_date column); treated as a
            pre-published season summary that is accepted at face value for the latest
            available season. This mirrors the pattern used by player_shot_profile.

        Returns None when all sources are missing for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        pt = _playtypes_transition(pid, as_of)
        pbp = _pbp_transition(pid, as_of)
        reb_proxy = _reb_push_proxy(pid, as_of)

        # Bail if nothing at all is available
        all_empty = not pt and not pbp and not reb_proxy
        if all_empty:
            return None

        # --- playtypes sub-dict ---
        playtypes_sub: Dict[str, Any] = {}
        if pt:
            playtypes_sub["freq_pct"] = pt.get("freq_pct")
            playtypes_sub["ppp"] = pt.get("ppp")
            playtypes_sub["_source_season"] = pt.get("_source_season")
        else:
            playtypes_sub["_note"] = (
                "DEFER: player absent from playtypes_2025-26.parquet Transition rows."
            )

        # --- pbp volume sub-dict ---
        pbp_sub: Dict[str, Any] = {}
        if pbp:
            pbp_sub["transition_pg"] = pbp.get("transition_pg")
            pbp_sub["transition_poss_share"] = pbp.get("transition_poss_share")
            pbp_sub["and1_pg"] = pbp.get("and1_pg")
        else:
            pbp_sub["_note"] = (
                "DEFER: player absent from pbp_possession_features.parquet "
                "within the as_of window."
            )

        # --- push-after-rebound proxy sub-dict ---
        push_sub: Dict[str, Any] = {}
        if reb_proxy:
            push_sub["reb_pg"] = reb_proxy.get("reb_pg")
            push_sub["_note"] = reb_proxy.get("_note")
        else:
            push_sub["_note"] = (
                "DEFER: no quarter_stats data found for this player within the as_of window."
            )

        # --- DEFER stubs ---
        leak_out: Dict[str, Any] = {
            "_note": (
                "DEFER: leak-out tendency (sprinting ahead before rebound) requires "
                "CV fast-break detection sequencing or a dedicated NBA tracking feed "
                "not yet available in this repo."
            )
        }
        finishing_splits: Dict[str, Any] = {
            "_note": (
                "DEFER: per-zone made/attempt breakdown in transition (rim vs midrange) "
                "is not available in playtypes_2025-26 (only season-level ppp) and no "
                "per-play-type shot-chart parquet has been fetched."
            )
        }

        sub_fields: Dict[str, Any] = {
            "playtypes": playtypes_sub,
            "pbp_volume": pbp_sub,
            "push_after_rebound_proxy": push_sub,
            "leak_out_tendency": leak_out,
            "finishing_splits": finishing_splits,
        }

        # --- n = actual games from the per-game (leak-filtered) source ---
        # Priority: pbp (best game count, per-game keyed), then reb_proxy quarter_stats
        n_candidates: List[int] = []
        if pbp.get("n_games"):
            n_candidates.append(int(pbp["n_games"]))
        if reb_proxy.get("n_games"):
            n_candidates.append(int(reb_proxy["n_games"]))
        n = max(n_candidates) if n_candidates else 1

        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=pt.get("ppp"),  # headline: transition efficiency
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub-field keys present, proportions in range.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        This method checks internal self-consistency only.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "playtypes", "pbp_volume", "push_after_rebound_proxy",
            "leak_out_tendency", "finishing_splits",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Check freq_pct is in [0,1] when present
        freq = sf.get("playtypes", {}).get("freq_pct")
        if freq is not None and not (0.0 <= freq <= 1.0):
            return False

        # ppp is an efficiency metric — allow 0-5 (not a strict proportion)
        ppp = sf.get("playtypes", {}).get("ppp")
        if ppp is not None and not (0.0 <= ppp <= 5.0):
            return False

        # transition_poss_share must be in [0,1]
        share = sf.get("pbp_volume", {}).get("transition_poss_share")
        if share is not None and not (0.0 <= share <= 1.0):
            return False

        # per-game rates must be non-negative
        for pg_key in ["transition_pg", "and1_pg"]:
            v = sf.get("pbp_volume", {}).get(pg_key)
            if v is not None and v < 0:
                return False

        # CV fields must all be null (not yet filled by CV branch)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slot for transition_scoring (value=None — CV branch fills later).

        Sprint speed during transition possessions is the primary CV signal of interest
        for this section.  Additional slots (fast_break_flag rate, transition_paint_touches)
        are not reserved here but may be added in the CV-fix session if warranted.
        """
        return {
            "sprint_speed_transition": CVSlot(
                name="sprint_speed_transition",
                dtype="float",
                description=(
                    "Mean player sprint speed (ft/s) measured by CV homography + Kalman "
                    "velocity estimates during possessions tagged as fast_break or "
                    "transition in possession_cv_state.parquet / CV EventDetector. "
                    "Higher values indicate a player who pushes the pace aggressively."
                ),
                unit="ft/s",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build transition_scoring for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids.  If None, discovers from playtypes_2025-26.
        as_of:      leak boundary date (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        df = _load("pt26_disc", DATA / "playtypes_2025-26.parquet")
        if df is not None and not df.empty and "player_id" in df.columns:
            player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerTransitionScoring()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
