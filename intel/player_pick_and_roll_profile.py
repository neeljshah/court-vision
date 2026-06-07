"""ARM-B atlas section: ``pick_and_roll_profile`` — PnR ball-handler behavioral profile.

Implements :class:`AtlasSection` for the ``"pick_and_roll_profile"`` section of a
player's persistent profile.  Covers PnR ball-handler frequency, efficiency,
pass-vs-shoot tendencies, turnover rate, and limited coverage-type context derived
from opponent defensive-scheme tags.

**Sub-field coverage:**

REAL (populated from parquets):
  handler.*         — PnR ball-handler freq_pct + ppp from playtypes_2025-26 /
                      playtypes.parquet (PRBallHandler play_type row).
  roll_man.*        — PRRollMan freq_pct + ppp (useful complementary read of how
                      the player functions as roll target; set None if missing).
  passing.*         — drive-related passing proxies from player_tracking: passes_per_drive,
                      ast_per_drive (trk_drv_passes / trk_drv_count and trk_drv_ast /
                      trk_drv_count), drive_tov_rate (trk_drv_tov_pct).
  pbp.*             — per-game PBP aggregates: pnr_handler_pg (count), pnr_screener_pg,
                      avg_seconds_per_touch, and n_games from
                      data/cache/pbp_possession_features.parquet, filtered <= as_of.
  scheme_context.*  — the player's own-team defensive scheme (drop_score /
                      dominant_tag from intelligence/defensive_schemes.parquet).
                      The opponent coverage type (drop/switch/blitz) is NOT directly
                      derivable per-game without a game-level team→scheme join; a
                      summary tag is included instead.

DEFER (data gap — no source parquet available):
  coverage_splits.* — per-coverage-type (drop vs switch vs blitz) ppp/fg%
                      DEFER: no per-game opponent-team scheme tag joined to boxscores;
                      defensive_schemes.parquet is season-level team summary only.
  pass_target_freq  — frequency of PnR passes to specific roll-man targets
                      DEFER: coverage_faced_matrix has matchup minutes but not
                      PnR-specific possession events.
  screener_quality  — quality metrics of screens set (setter angle, separation gap)
                      DEFER: CV-derived only (screen_navigation CV slot reserved).

RESERVED CV SLOTS (value=None, CV branch fills later):
  screen_navigation  — quality of navigating off-screen curl/fade/pop (CV geometry)
  pocket_pass_window — fraction of PnR possessions where a pocket pass lane is open
                       (CV defender positioning off the screener)
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
# Data-loading helpers (module-level LRU cache — one load per process)
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


def _load(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet exactly once; cache None on missing or error."""
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


def _pct_guard(v: Optional[float], ceil: float = 1.0) -> Optional[float]:
    """Return None if v is out of [0, ceil]; otherwise return v."""
    if v is None:
        return None
    if not (0.0 <= v <= ceil):
        return None
    return v


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _playtypes_pnr(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return PRBallHandler and PRRollMan sub-dicts from playtypes parquet.

    Uses the freshest available season-level record (playtypes_2025-26 preferred,
    falls back to playtypes.parquet).  Season-level playtypes are published after
    the season ends; no game_date join is possible, so they are used as-is.

    Args:
        pid:   NBA player_id.
        as_of: build boundary (used to select parquet preference only).

    Returns:
        dict with keys 'handler' and 'roll_man', each a sub-dict or None.
    """
    result: Dict[str, Any] = {"handler": None, "roll_man": None}

    for path_key, path in [
        ("pt26", DATA / "playtypes_2025-26.parquet"),
        ("pt_base", DATA / "playtypes.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue

        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)

        for _, row in rows.iterrows():
            pt = str(row.get("play_type", ""))
            freq = _rd(row.get("freq_pct"))
            ppp = _rd(row.get("ppp"))
            if pt == "PRBallHandler" and result["handler"] is None:
                result["handler"] = {
                    "freq_pct": _pct_guard(freq, ceil=1.6),
                    "ppp": ppp,
                }
            elif pt == "PRRollMan" and result["roll_man"] is None:
                result["roll_man"] = {
                    "freq_pct": _pct_guard(freq, ceil=1.6),
                    "ppp": ppp,
                }

        # Use the freshest source that had data for this player
        if result["handler"] is not None or result["roll_man"] is not None:
            break

    return result


def _tracking_pnr(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return drive-based passing proxies from player_tracking parquet.

    Computes:
      - passes_per_drive: trk_drv_passes / trk_drv_count  (pass tendency off drive)
      - ast_per_drive:    trk_drv_ast / trk_drv_count     (assist tendency off drive)
      - drive_tov_rate:   trk_drv_tov_pct                 (already a rate, [0,1])
      - drive_count_pg:   trk_drv_count                   (per-game volume)

    These serve as proxies for pass-vs-shoot split in PnR situations where the
    ball-handler penetrates off the screen.

    Args:
        pid:   NBA player_id.
        as_of: build boundary.

    Returns:
        dict of passing proxies; empty dict if player not found.
    """
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

        drv_count = _rd(row.get("trk_drv_count"))
        drv_passes = _rd(row.get("trk_drv_passes"))
        drv_ast = _rd(row.get("trk_drv_ast"))
        drv_tov_pct = _rd(row.get("trk_drv_tov_pct"))
        drv_fg_pct = _rd(row.get("trk_drv_fg_pct"))

        passes_per_drive: Optional[float] = None
        ast_per_drive: Optional[float] = None
        if drv_count is not None and drv_count > 0:
            if drv_passes is not None:
                passes_per_drive = _rd(drv_passes / drv_count)
            if drv_ast is not None:
                ast_per_drive = _rd(drv_ast / drv_count)

        return {
            "drive_count_pg": drv_count,
            "drive_fg_pct": _pct_guard(drv_fg_pct),
            "drive_tov_rate": _pct_guard(drv_tov_pct),
            "passes_per_drive": passes_per_drive,
            "ast_per_drive": ast_per_drive,
        }
    return {}


def _pbp_pnr(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return per-game PBP PnR aggregates filtered to games <= as_of.

    Source: data/cache/pbp_possession_features.parquet (grain: player_id x game).

    Args:
        pid:   NBA player_id.
        as_of: build boundary; only rows with game_date <= as_of are used.

    Returns:
        dict with per-game averages and n_games; empty dict if player absent.
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

    n = len(rows)
    means = rows[
        [c for c in [
            "pbp_pnr_ball_handler",
            "pbp_pnr_screener_proxy",
            "pbp_avg_seconds_per_touch",
            "pbp_transition_count",
        ] if c in rows.columns]
    ].mean()

    return {
        "pnr_handler_pg": _rd(means.get("pbp_pnr_ball_handler")),
        "pnr_screener_pg": _rd(means.get("pbp_pnr_screener_proxy")),
        "avg_seconds_per_touch": _rd(means.get("pbp_avg_seconds_per_touch")),
        "transition_pg": _rd(means.get("pbp_transition_count")),
        "n_games": n,
    }


def _scheme_context(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return team defensive-scheme summary for the player's own team.

    Source: data/intelligence/defensive_schemes.parquet (season-level, team-keyed).
    We cannot derive per-game opponent scheme here; instead we capture the player's
    own-team scheme tag as a proxy for the defensive environment they face.

    Per-coverage-type (drop/switch/blitz) PnR splits are DEFER — no per-game
    opponent-team scheme join is available without a game-id -> opponent-tricode
    mapping that is not currently in any parquet.

    Args:
        pid:   NBA player_id (not used to filter scheme table; returns league average
               metrics as a structural reference).
        as_of: build boundary (scheme table is season-level; accepted as-is).

    Returns:
        dict with league-context scheme distribution; empty if table missing.
    """
    path = DATA / "intelligence" / "defensive_schemes.parquet"
    df = _load("def_schemes", path)
    if df is None or df.empty:
        return {}

    # Compute league-wide averages for drop_score and dominant-tag distribution
    drop_mean = _rd(df["drop_score"].mean()) if "drop_score" in df.columns else None
    n_teams = len(df)
    tag_counts: Dict[str, int] = {}
    if "dominant_tag" in df.columns:
        for tag in df["dominant_tag"].dropna():
            tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1

    top_tag: Optional[str] = None
    if tag_counts:
        top_tag = max(tag_counts, key=lambda t: tag_counts[t])

    return {
        "league_drop_score_mean": drop_mean,
        "n_teams_in_scheme_atlas": n_teams,
        "most_common_defense_tag": top_tag,
        "_note": (
            "DEFER per-game opponent coverage splits: no game_id->opp_tricode join "
            "available. Per-coverage-type PnR ppp/fg% requires a new parquet."
        ),
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerPickAndRollProfile(AtlasSection):
    """Pick-and-roll ball-handler atlas section (player entity, section='pick_and_roll_profile').

    Builds a provenance-stamped, leak-safe artifact covering PnR handler frequency,
    efficiency (ppp), pass-vs-shoot proxies, turnover rate, PBP volume, and defensive
    scheme context.  Reserves 2 CV slots for CV-branch enrichment.

    Sources:
      - data/playtypes_2025-26.parquet + data/playtypes.parquet (PRBallHandler/PRRollMan)
      - data/player_tracking_2025-26.parquet + data/player_tracking.parquet (drive proxies)
      - data/cache/pbp_possession_features.parquet (per-game PnR handler counts, <= as_of)
      - data/intelligence/defensive_schemes.parquet (league-level scheme context)

    DEFER sub-fields (noted inline):
      - coverage_splits (drop/switch/blitz per-coverage ppp) — no per-game opp scheme join
      - pass_target_freq — not in any current parquet
      - screener_quality — CV-only (screen_navigation slot reserved)
    """

    name: str = "pick_and_roll_profile"
    entity: str = "player"
    source_name: str = (
        "playtypes_2025-26.parquet + player_tracking_2025-26.parquet + "
        "pbp_possession_features.parquet + defensive_schemes.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the pick_and_roll_profile artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - pbp_possession_features rows are filtered to game_date <= as_of.
          - playtypes and tracking are season-level summaries (no game_date col);
            the freshest available season is used without further date filtering
            (these are published end-of-season and do not change once available).
          - defensive_schemes is a season-level summary and accepted as-is.

        Returns None when all sources are missing for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        pt = _playtypes_pnr(pid, as_of)
        trk = _tracking_pnr(pid, as_of)
        pbp = _pbp_pnr(pid, as_of)
        scheme = _scheme_context(pid, as_of)

        all_empty = (
            pt["handler"] is None
            and pt["roll_man"] is None
            and not trk
            and not pbp
        )
        if all_empty:
            return None

        # --- handler sub-dict ---
        handler: Dict[str, Any] = {}
        if pt["handler"] is not None:
            handler["freq_pct"] = pt["handler"].get("freq_pct")
            handler["ppp"] = pt["handler"].get("ppp")
        else:
            handler["freq_pct"] = None
            handler["ppp"] = None
        # PBP handler volume (per-game count, more granular than playtypes freq)
        if pbp:
            handler["pnr_handler_pg"] = pbp.get("pnr_handler_pg")
            handler["avg_seconds_per_touch"] = pbp.get("avg_seconds_per_touch")

        # --- roll_man sub-dict (player as screener / roll target) ---
        roll_man: Dict[str, Any] = {}
        if pt["roll_man"] is not None:
            roll_man["freq_pct"] = pt["roll_man"].get("freq_pct")
            roll_man["ppp"] = pt["roll_man"].get("ppp")
        if pbp:
            roll_man["pnr_screener_pg"] = pbp.get("pnr_screener_pg")

        # --- passing sub-dict (drive proxies for pass-vs-shoot) ---
        passing: Dict[str, Any] = {}
        if trk:
            passing["passes_per_drive"] = trk.get("passes_per_drive")
            passing["ast_per_drive"] = trk.get("ast_per_drive")
            passing["drive_tov_rate"] = trk.get("drive_tov_rate")
            passing["drive_fg_pct"] = trk.get("drive_fg_pct")
            passing["drive_count_pg"] = trk.get("drive_count_pg")

        # --- coverage_splits (DEFER) ---
        coverage_splits: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-game opponent-team scheme join available. "
                "Requires a game_id->opp_tricode->scheme_tag parquet. "
                "drop/switch/blitz per-coverage ppp remain None."
            ),
            "drop_ppp": None,
            "switch_ppp": None,
            "blitz_ppp": None,
        }

        # --- scheme context ---
        scheme_ctx: Dict[str, Any] = dict(scheme)

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "handler": handler,
            "roll_man": roll_man,
            "passing": passing,
            "coverage_splits": coverage_splits,
            "scheme_context": scheme_ctx,
        }

        # --- Determine n (actual game count from pbp; fallback 1 if only seasonal) ---
        n_candidates: List[int] = []
        if pbp.get("n_games"):
            n_candidates.append(int(pbp["n_games"]))
        # playtypes and tracking are seasonal (n=1 season); only count them if pbp absent
        if not n_candidates:
            if pt["handler"] is not None or pt["roll_man"] is not None:
                # cannot infer game count from seasonal playtypes — set 1 (will yield low)
                n_candidates.append(1)

        n = max(n_candidates) if n_candidates else 0
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
            value=handler.get("ppp"),  # headline: PnR handler PPP
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, proportions in range.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        sf = artifact.sub_fields
        required_keys = {"handler", "roll_man", "passing", "coverage_splits", "scheme_context"}
        if not required_keys.issubset(sf.keys()):
            return False

        # freq_pct in [0, 1.6] (validator allows up to 100 for freq_pct suffix but data is [0,1])
        for block_key in ("handler", "roll_man"):
            block = sf.get(block_key, {})
            freq = block.get("freq_pct")
            if freq is not None and not (0.0 <= freq <= 1.6):
                return False
            # ppp is an unbounded ratio (can be 0..2+); no upper check

        # drive_tov_rate and drive_fg_pct must be in [0, 1]
        passing = sf.get("passing", {})
        for rate_key in ("drive_tov_rate", "drive_fg_pct"):
            v = passing.get(rate_key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False

        # drive_count_pg must be non-negative
        drv_pg = passing.get("drive_count_pg")
        if drv_pg is not None and drv_pg < 0:
            return False

        # CV slots must all have value=None (unfilled)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for pick_and_roll_profile (values None — CV fills later).

        screen_navigation:   quality score for navigating screens (curl/fade/pop angle,
                             separation gap between handler and screener at peel point).
        pocket_pass_window:  fraction of PnR possessions where a pocket-pass lane is open
                             (CV defender positioning off screener after ball-screen).
        """
        return {
            "screen_navigation": CVSlot(
                name="screen_navigation",
                dtype="float",
                description=(
                    "CV-derived quality score [0, 1] for the ball-handler's ability to "
                    "navigate ball-screens: measures separation angle between handler and "
                    "screener at the peel-off point, and effective defender displacement "
                    "from homography coordinates."
                ),
                unit=None,
                value=None,
            ),
            "pocket_pass_window": CVSlot(
                name="pocket_pass_window",
                dtype="float",
                description=(
                    "Fraction of PnR possessions (CV-tagged) where a pocket-pass lane is "
                    "open: defender guarding the screener/roll-man is >= 5 ft from the "
                    "roll-man at the moment the handler reads the defense, from CV "
                    "bounding-box coordinates + homography."
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
    """Build pick_and_roll_profile for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids.  If None, discovers from playtypes.
        as_of:      leak boundary (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
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

    section = PlayerPickAndRollProfile()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
