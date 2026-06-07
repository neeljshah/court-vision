"""ARM-B atlas section: ``halfcourt_offense`` — half-court offensive efficiency profile.

Implements :class:`AtlasSection` for the ``"halfcourt_offense"`` section of a
team's persistent profile.  Covers half-court ppp, iso/pnr/post play-type mix,
shot-quality indicators, and ball/player-movement proxies sourced from
``data/team_advanced_stats.parquet`` and ``data/playtypes_2025-26.parquet``
(team-joined via ``data/player_pf.parquet``).

**Sub-field coverage:**

REAL (populated from parquets):
  efficiency.*   — halfcourt off_rtg, efg_pct, ts_pct, tov_ratio from
                   data/team_advanced_stats.parquet (per-game rolling mean <=as_of;
                   full multi-season history for robust n).
  play_mix.*     — mean freq_pct per play type (PRBallHandler, Isolation, Postup,
                   Spotup, Handoff, Cut, OffScreen, PRRollMan, Transition, OffRebound)
                   from data/playtypes_2025-26.parquet joined to team via
                   data/player_pf.parquet (latest team per player <= as_of).
                   freq_pct is each player's share of their own possessions by type
                   (sums ~1.0 per player); team value = mean across roster.
  ppp.*          — mean ppp per play type (pnr_ppp, iso_ppp, post_ppp, spotup_ppp,
                   hc_ppp = half-court weighted mean) from playtypes_2025-26.parquet.
  ball_movement.* — passes_made_per_g_mean, ast_to_pass_pct, ast_to_pass_pct_adj,
                   drives_per_g_mean, drive_fg_pct from
                   data/cache/player_tracking_features.parquet grouped by drives_team
                   (2024-25 season; season-level, no game_date filter possible;
                   treated as pre-published season summary; safe for as_of >= season end).

DEFER:
  halfcourt_ppp_direct — DEFER: no team-level direct halfcourt possession ppp parquet.
                         Computable from PBP once build_pbp_possession_features.py emits
                         a team-grain companion with possession_type='halfcourt'.
  motion_score        — DEFER: no team-level off-ball movement speed / distance parquet.
                        Wire when cv_pace_per_game.parquet is aggregated to team grain.

RESERVED CV SLOTS (value=None; CV branch fills later):
  avg_passes_per_poss — mean pass count per half-court possession from CV EventDetector
                        frame-sequence tagging (team × game aggregate).
"""
from __future__ import annotations

import datetime as _dt
import json
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
# Half-court play types (non-transition half-court offensive possessions)
# ---------------------------------------------------------------------------
_HC_TYPES = frozenset([
    "PRBallHandler", "Isolation", "Postup", "Spotup",
    "Handoff", "Cut", "OffScreen", "PRRollMan", "OffRebound", "Misc",
])

# ---------------------------------------------------------------------------
# Module-level lazy parquet cache (one load per process)
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
    """Clean scalar: NaN/inf → None, numpy → python float, round 4 dp."""
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
    """Clean integer: NaN/inf → None."""
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
    """Null out proportions outside [0, ceil] (validator face-validity guard)."""
    if v is None:
        return None
    if v < 0.0 or v > ceil:
        return None
    return v


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _adv_stats(team_tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate team_advanced_stats for all games <= as_of.

    Returns efficiency metrics (off_rtg, efg_pct, ts_pct, tov_ratio) and n_games.
    LEAK-SAFE: filters game_date <= as_of.
    """
    df = _load("team_adv", DATA / "team_advanced_stats.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["team_tricode"] == team_tricode].copy()
    if rows.empty:
        return {}

    rows["game_date"] = pd.to_datetime(rows["game_date"])
    rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    means = rows[[c for c in ["off_rtg", "efg_pct", "ts_pct", "tov_ratio", "pace"]
                  if c in rows.columns]].mean()

    efg = _rd(means.get("efg_pct"))
    ts = _rd(means.get("ts_pct"))
    return {
        "off_rtg": _rd(means.get("off_rtg")),
        "efg_pct": _clamp_pct(efg, ceil=1.6),   # efg ceil is 1.6 per validator
        "ts_pct": _clamp_pct(ts, ceil=1.6),      # ts ceil is 1.6 per validator
        "tov_ratio": _rd(means.get("tov_ratio")),
        "pace": _rd(means.get("pace")),
        "n_games": n,
    }


def _build_player_team_map(as_of: _dt.datetime) -> pd.DataFrame:
    """Return player_id -> team_tricode for the team each player played for most recently <= as_of.

    Source: data/player_pf.parquet (game-level player foul data with team_abbreviation).
    LEAK-SAFE: only games with game_date <= as_of.
    """
    df = _load("player_pf", DATA / "player_pf.parquet")
    if df is None or df.empty:
        return pd.DataFrame(columns=["player_id", "team_tricode"])

    rows = df.copy()
    rows["game_date"] = pd.to_datetime(rows["game_date"])
    rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return pd.DataFrame(columns=["player_id", "team_tricode"])

    latest = (
        rows.sort_values("game_date")
        .groupby("player_id")
        .last()
        .reset_index()[["player_id", "team_abbreviation"]]
        .rename(columns={"team_abbreviation": "team_tricode"})
    )
    return latest


def _playtypes(team_tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate playtypes_2025-26.parquet by play type for this team.

    Joins playtypes player_id to team_tricode via player_pf.parquet (latest game
    for each player <= as_of).  freq_pct is each player's share of own possessions
    by type (sums ~1.0 per player); team value = mean freq_pct across roster.
    ppp = mean ppp across players for that play type.

    LEAK-SAFE: player_pf join uses only games with game_date <= as_of.
    NOTE: playtypes_2025-26.parquet is season-summary (no per-game dates);
    treated as pre-published season data, safe once 2025-26 season data is in.
    Falls back to older playtypes.parquet (2024-25) when the newer is absent.
    """
    # Prefer 2025-26 season; fall back to 2024-25
    pt = _load("pt_2526", DATA / "playtypes_2025-26.parquet")
    if pt is None or pt.empty:
        pt = _load("pt_2425", DATA / "playtypes.parquet")
    if pt is None or pt.empty:
        return {}

    team_map = _build_player_team_map(as_of)
    if team_map.empty:
        return {}

    merged = pt.merge(team_map, on="player_id", how="left")
    team_rows = merged[merged["team_tricode"] == team_tricode]
    if team_rows.empty:
        return {}

    # Aggregate per play type: mean freq_pct and ppp across roster
    agg = (
        team_rows.groupby("play_type")
        .agg(freq_pct_mean=("freq_pct", "mean"),
             ppp_mean=("ppp", "mean"),
             n_players=("player_id", "nunique"))
        .reset_index()
    )

    def _get_row(play_type: str) -> Dict[str, Any]:
        r = agg[agg["play_type"] == play_type]
        if r.empty:
            return {}
        row = r.iloc[0]
        raw_freq = _rd(row["freq_pct_mean"])
        # freq_pct is [0,1] per player share -- safe to clip
        freq = _clamp_pct(raw_freq, ceil=1.0)
        return {
            "freq_pct": freq,
            "ppp": _rd(row["ppp_mean"]),
            "n_players": _ri(row["n_players"]),
        }

    pnr = _get_row("PRBallHandler")
    iso = _get_row("Isolation")
    post = _get_row("Postup")
    spotup = _get_row("Spotup")
    handoff = _get_row("Handoff")
    cut = _get_row("Cut")
    off_screen = _get_row("OffScreen")
    pnr_roll = _get_row("PRRollMan")

    # Halfcourt weighted ppp: mean ppp across halfcourt play-type rows
    hc_rows = team_rows[team_rows["play_type"].isin(_HC_TYPES)]
    hc_ppp = _rd(hc_rows["ppp"].mean()) if not hc_rows.empty else None

    n_players_total = team_rows["player_id"].nunique()

    return {
        "pnr": pnr,
        "iso": iso,
        "post": post,
        "spotup": spotup,
        "handoff": handoff,
        "cut": cut,
        "off_screen": off_screen,
        "pnr_roll": pnr_roll,
        "hc_ppp": hc_ppp,
        "n_players": n_players_total,
        "_source": (
            "playtypes_2025-26.parquet joined to team via player_pf.parquet "
            "(latest game <= as_of); freq_pct = mean player share per play type."
        ),
    }


def _ball_movement(team_tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate player_tracking_features.parquet drive/pass signals by team.

    Groups by drives_team column.  Season-level parquet (no game_date);
    treated as pre-published 2024-25 season summary — acceptable for as_of at or
    after season end.

    LEAK-SAFE caveat: season-level data has no game_date; if as_of is mid-season
    this may include games not yet played.  Acceptable per spec (same treatment as
    in team_offensive_scheme.py).
    """
    df = _load("trk_feat", CACHE / "player_tracking_features.parquet")
    if df is None or df.empty:
        return {}
    if "drives_team" not in df.columns:
        return {}

    rows = df[df["drives_team"] == team_tricode]
    if rows.empty:
        return {}

    want = ["drives_per_g", "drive_fg_pct", "drive_pts_pct",
            "drive_ast_per_drive", "passes_made_per_g",
            "ast_to_pass_pct", "ast_to_pass_pct_adj"]
    means = rows[[c for c in want if c in rows.columns]].mean()

    drive_fg = _rd(means.get("drive_fg_pct"))
    drive_pts = _rd(means.get("drive_pts_pct"))
    ast2pass = _rd(means.get("ast_to_pass_pct"))
    ast2pass_adj = _rd(means.get("ast_to_pass_pct_adj"))

    return {
        "drives_per_g_mean": _rd(means.get("drives_per_g")),
        "drive_fg_pct": _clamp_pct(drive_fg, ceil=1.0),
        "drive_pts_pct": _clamp_pct(drive_pts, ceil=1.0),
        "drive_ast_rate": _clamp_pct(_rd(means.get("drive_ast_per_drive")), ceil=1.0),
        "passes_made_per_g_mean": _rd(means.get("passes_made_per_g")),
        "ast_to_pass_pct": _clamp_pct(ast2pass, ceil=1.0),
        "ast_to_pass_pct_adj": _clamp_pct(ast2pass_adj, ceil=1.0),
        "n_players": len(rows),
        "_source": (
            "player_tracking_features.parquet grouped by drives_team; "
            "season-level (no game_date filter); pre-published 2024-25 summary."
        ),
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamHalfcourtOffense(AtlasSection):
    """Deep team half-court offensive profile (team entity, section='halfcourt_offense').

    Builds a provenance-stamped, leak-safe artifact covering half-court efficiency,
    play-type mix (iso/pnr/post), ppp per play type, ball/player movement proxies,
    and one reserved CV slot for avg_passes_per_poss.

    Sources used:
      - data/team_advanced_stats.parquet         (off_rtg, efg, ts, tov_ratio — per game)
      - data/playtypes_2025-26.parquet           (play-type freq_pct and ppp — season-level)
      - data/player_pf.parquet                   (player->team linkage for playtypes join)
      - data/cache/player_tracking_features.parquet (drives, passes, ball movement)

    DEFER sub-fields (no source parquet available):
      - halfcourt_ppp_direct: requires PBP team-grain possession_type split (not built yet)
      - motion_score: requires team-grain cv_pace or off-ball movement aggregate (not built yet)
    """

    name: str = "halfcourt_offense"
    entity: str = "team"
    source_name: str = (
        "team_advanced_stats.parquet + playtypes_2025-26.parquet "
        "+ player_pf.parquet + player_tracking_features.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the halfcourt_offense artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. "OKC").
            as_of:     leak boundary — only data with game_date <= as_of is used.

        Returns:
            AtlasArtifact or None when primary source is missing for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        adv = _adv_stats(tricode, as_of)
        if not adv:
            return None  # primary source missing

        pt = _playtypes(tricode, as_of)
        bm = _ball_movement(tricode, as_of)

        # --- efficiency sub-dict (team_advanced_stats) ---
        efficiency: Dict[str, Any] = {
            "off_rtg": adv.get("off_rtg"),
            "efg_pct": adv.get("efg_pct"),
            "ts_pct": adv.get("ts_pct"),
            "tov_ratio": adv.get("tov_ratio"),
            "pace": adv.get("pace"),
        }

        # --- play_mix sub-dict (playtypes fraction per play type) ---
        play_mix: Dict[str, Any] = {}
        ppp_sub: Dict[str, Any] = {}
        if pt:
            def _freq(key: str) -> Optional[float]:
                return pt.get(key, {}).get("freq_pct") if pt.get(key) else None

            def _ppp(key: str) -> Optional[float]:
                return pt.get(key, {}).get("ppp") if pt.get(key) else None

            play_mix = {
                "pnr_freq": _freq("pnr"),
                "iso_freq": _freq("iso"),
                "post_freq": _freq("post"),
                "spotup_freq": _freq("spotup"),
                "handoff_freq": _freq("handoff"),
                "cut_freq": _freq("cut"),
                "off_screen_freq": _freq("off_screen"),
                "pnr_roll_freq": _freq("pnr_roll"),
                "n_players_in_sample": pt.get("n_players"),
                "_source": pt.get("_source"),
            }
            ppp_sub = {
                "pnr_ppp": _ppp("pnr"),
                "iso_ppp": _ppp("iso"),
                "post_ppp": _ppp("post"),
                "spotup_ppp": _ppp("spotup"),
                "handoff_ppp": _ppp("handoff"),
                "cut_ppp": _ppp("cut"),
                "off_screen_ppp": _ppp("off_screen"),
                "pnr_roll_ppp": _ppp("pnr_roll"),
                "hc_ppp": pt.get("hc_ppp"),
            }
        else:
            play_mix = {"_note": "DEFER: playtypes_2025-26.parquet or player_pf.parquet missing."}
            ppp_sub = {"_note": "DEFER: playtypes_2025-26.parquet or player_pf.parquet missing."}

        # --- ball_movement sub-dict (player_tracking_features) ---
        ball_movement: Dict[str, Any] = dict(bm) if bm else {
            "_note": (
                "DEFER: player_tracking_features.parquet missing or drives_team "
                "column absent for this team."
            )
        }

        # --- DEFER placeholders ---
        halfcourt_ppp_direct: Dict[str, Any] = {
            "_note": (
                "DEFER: no team-grain direct halfcourt ppp parquet. "
                "Computable from PBP once build_pbp_possession_features.py emits "
                "a team-grain companion with possession_type='halfcourt'."
            )
        }
        motion_score: Dict[str, Any] = {
            "_note": (
                "DEFER: no team-level off-ball movement speed parquet. "
                "Wire when cv_pace_per_game.parquet is aggregated to team grain."
            )
        }

        sub_fields: Dict[str, Any] = {
            "efficiency": efficiency,
            "play_mix": play_mix,
            "ppp": ppp_sub,
            "ball_movement": ball_movement,
            "halfcourt_ppp_direct": halfcourt_ppp_direct,
            "motion_score": motion_score,
        }

        # Headline scalar: halfcourt ppp if available, else off_rtg
        value = pt.get("hc_ppp") if pt else adv.get("off_rtg")

        # Primary n from team_advanced_stats (# games; per critical lesson #1)
        n = adv.get("n_games", 0)
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
            entity_id=tricode,
            value=value,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity: required sub-field keys present + sane ranges.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {"efficiency", "play_mix", "ppp", "ball_movement",
                         "halfcourt_ppp_direct", "motion_score"}
        if not required_keys.issubset(sf.keys()):
            return False

        # off_rtg must be in a plausible NBA range when present
        off_rtg = sf.get("efficiency", {}).get("off_rtg")
        if off_rtg is not None and not (80.0 <= off_rtg <= 160.0):
            return False

        # efg_pct, ts_pct must be in [0, 1.6] (validator ceiling for eFG/TS)
        for pct_key in ("efg_pct", "ts_pct"):
            v = sf.get("efficiency", {}).get(pct_key)
            if v is not None and not (0.0 <= v <= 1.6):
                return False

        # freq_pct values must be in [0, 1]
        for freq_key in ("pnr_freq", "iso_freq", "post_freq", "spotup_freq",
                         "handoff_freq", "cut_freq", "off_screen_freq", "pnr_roll_freq"):
            v = sf.get("play_mix", {}).get(freq_key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False

        # CV slots must be reserved (null)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for halfcourt_offense (values None; CV fills later).

        The CV-fix session calls::
            store.fill_cv_slot("team", tricode, "halfcourt_offense", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild.  Key is stable contract.
        """
        return {
            "avg_passes_per_poss": CVSlot(
                name="avg_passes_per_poss",
                dtype="float",
                description=(
                    "Mean number of passes per half-court offensive possession, "
                    "computed by CV EventDetector frame-sequence tagging — ball "
                    "pass events between offensive player detections within a "
                    "single possession window (ball_handler_change events), "
                    "averaged across all half-court possessions for this team "
                    "over the tracked game window.  Proxy for ball/player movement "
                    "and motion-offense identity (high = motion, low = isolation)."
                ),
                unit="passes/possession",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    team_tricodes: Optional[List[str]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build halfcourt_offense for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of NBA team tricodes (str, e.g. ["OKC", "BOS"]).
                       If None, discovers from team_advanced_stats.parquet.
        as_of:         leak boundary date (defaults to today UTC midnight).
        store:         optional PointInTimeStore; when provided, writes artifacts.
        dry_run:       skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if team_tricodes is None:
        df = _load("team_adv_disc", DATA / "team_advanced_stats.parquet")
        if df is not None and "team_tricode" in df.columns:
            team_tricodes = sorted(df["team_tricode"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamHalfcourtOffense()
    artifacts: List[AtlasArtifact] = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
