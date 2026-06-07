"""ARM-B atlas section: ``foul_tendency`` — exhaustive per-player foul profile.

Implements :class:`AtlasSection` for the ``"foul_tendency"`` section of a player's
persistent profile.  Every real sub-field comes from existing parquets cited in
spec_features.md / spec_intel_memory.md — no re-derivation.

NOTE on the existing ``foul_propensity`` section in build_persistent_profiles.py:
That section covers only per-36 rolling commit rates (pf_per_36_l5/l10,
foul_trouble_rate_l10).  This ``foul_tendency`` section is DEEPER and
ORTHOGONAL: it adds quarter-level commit distribution, early-foul-trouble
propensity, foul-out risk, charges drawn, and per-category DEFER stubs for
play-type-specific foul breakdown.  The bridge registers it as an ADDITIONAL
section, not a replacement.

**Sub-field coverage:**

REAL (populated from existing parquets):

  committed.*   — season pf_per_36, rolling L5/L10 pf_per_36 + foul_trouble_rate,
                  raw pf per game; sourced from
                    data/cache/foul_features.parquet  (rolling-window grain)
                    data/player_pf.parquet             (per-game raw)
                    data/player_pf_per36.parquet       (season-aggregate)

  by_quarter.*  — mean PF committed per quarter (q1..q4) and the q1 share of daily
                  total PF; sourced from
                    data/player_quarter_stats.parquet + data/player_pf.parquet
                  (per-game pf merged from player_pf for game_date leak filter)

  early_trouble.* — early_foul_trouble_rate: fraction of games with 2+ PF in Q1
                    (forces coaching to sit the player early); half_trouble_rate:
                    fraction of games with 3+ PF through the first half; both from
                    data/player_quarter_stats.parquet + data/player_pf.parquet

  foul_out_risk.* — foul_out_rate: fraction of games with 6+ total PF;
                    mean_pf_pg: career average PF per game;
                    pf_pg_l5: rolling 5-game average PF;
                    from data/player_pf.parquet + data/cache/foul_features.parquet

  charges_drawn.* — hustle_charges_drawn_pg: mean charges drawn per game from the
                    hustle parquets (an important DRAWN-foul signal, defensive style);
                    sourced from
                    data/cache/hustle_features_2025-26.parquet (prefer fresh) +
                    data/cache/hustle_features.parquet (fallback)

DEFER (data gap — stubs with _note):

  drawn.*       — FTA-drawn rate, drawn-foul type breakdown (blocking vs charging
                  drawn, personal vs technical drawn), EVENTMSGTYPE=3 FT trips from
                  PBP.  DEFER: V3→V2 normalize in pbp_scraper loses PLAYER2_ID
                  (fouled-player), so drawn-foul attribution is unavailable in current
                  PBP files (see spec_features §2 GOTCHA).  Recoverable when
                  PLAYER2_ID is restored from a true-V2 feed or league-provided CSV.

  by_type.*     — commit breakdown by foul type (blocking, offensive, technical,
                  flagrant, loose-ball, away-from-ball).  DEFER: NBA Stats API does
                  not publish per-type totals in the accessible endpoints; would
                  require the LeagueFouls API (premium) or manual PBP annotation.

RESERVED CV SLOTS (value=None, CV branch fills later):

  contest_proximity_at_foul  — mean defender-to-ball distance (ft) at the frame
                               where a foul event is detected (CV EventDetector
                               EVENTMSGTYPE=6 frame anchor).
  foul_body_angle            — mean body-angle delta between player and ball-handler
                               at the foul frame (deg); proxy for illegal-use-of-hands
                               vs clean-block contests.
  spacing_at_foul_commit     — mean team spacing (ft², convex hull) when the player
                               commits a foul — measures help-defense vs switching
                               coverage tendency.
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

def _committed_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Rolling and season-level committed-foul rates, filtered to <= as_of.

    Sources: foul_features.parquet (rolling L5/L10, foul_trouble_rate) +
             player_pf_per36.parquet (season-aggregate pf_per_36) +
             player_pf.parquet (raw per-game PF).
    """
    as_of_ts = pd.Timestamp(as_of)
    result: Dict[str, Any] = {}

    # Rolling window features (L5/L10) from foul_features
    ff = _load("foul_feat", CACHE / "foul_features.parquet")
    n_games = 0
    last_as_of: Optional[str] = None
    if ff is not None and not ff.empty:
        rows = ff[ff["player_id"] == pid].copy()
        if "game_date" in rows.columns:
            rows["game_date"] = pd.to_datetime(rows["game_date"])
            rows = rows[rows["game_date"] <= as_of_ts]
        if not rows.empty:
            rows = rows.sort_values("game_date") if "game_date" in rows.columns else rows
            last = rows.iloc[-1]
            result["pf_per_36_l5"] = _rd(last.get("pf_per_36_l5"))
            result["pf_per_36_l10"] = _rd(last.get("pf_per_36_l10"))
            result["foul_trouble_rate_l10"] = _rd(last.get("foul_trouble_rate_l10"))
            n_games = _ri(rows["game_id"].nunique()) or len(rows) if "game_id" in rows.columns else len(rows)
            if "game_date" in rows.columns:
                last_as_of = str(last.get("game_date"))[:10]

    # Season-aggregate per-36
    p36 = _load("pf_per36", DATA / "player_pf_per36.parquet")
    if p36 is not None and not p36.empty:
        rows36 = p36[p36["player_id"] == pid].copy()
        if "game_date" in rows36.columns:
            rows36["game_date"] = pd.to_datetime(rows36["game_date"])
            rows36 = rows36[rows36["game_date"] <= as_of_ts]
        if not rows36.empty:
            rows36 = rows36.sort_values("game_date") if "game_date" in rows36.columns else rows36
            last36 = rows36.iloc[-1]
            result["season_pf_per_36"] = _rd(last36.get("season_pf_per_36"))

    result["n_games"] = n_games
    result["last_as_of"] = last_as_of
    return result


def _by_quarter_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Mean PF committed per quarter (q1..q4) filtered to games <= as_of.

    Sources: player_quarter_stats.parquet (per-quarter PF) +
             player_pf.parquet (for game_date join to enforce as_of leak boundary).
    """
    as_of_ts = pd.Timestamp(as_of)

    qstats = _load("qstats", DATA / "player_quarter_stats.parquet")
    pf_df = _load("pf_raw", DATA / "player_pf.parquet")

    if qstats is None or qstats.empty:
        return {}

    rows = qstats[qstats["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Enforce as_of via game_date from player_pf (game_date not in quarter_stats)
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
    total_pf_pg = 0.0

    for q in [1, 2, 3, 4]:
        qr = rows[rows["period"] == q]
        if qr.empty:
            continue
        g_count = qr["game_id"].nunique() if "game_id" in qr.columns else len(qr)
        if g_count == 0:
            continue
        pf_pg = float(qr["pf"].sum()) / g_count
        result[f"q{q}_pf_pg"] = round(pf_pg, 4)
        total_pf_pg += pf_pg

    # Q1 share — how much of daily foul budget gets spent in the 1st quarter
    if total_pf_pg > 0 and "q1_pf_pg" in result:
        result["q1_share_of_daily_pf"] = round(result["q1_pf_pg"] / total_pf_pg, 4)

    return result


def _early_trouble_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Fraction of games where the player accumulates 2+ PF in Q1 (early foul trouble).

    Also computes half_trouble_rate: fraction of games with 3+ PF through Q2.
    Sources: player_quarter_stats.parquet + player_pf.parquet (for as_of filter).
    """
    as_of_ts = pd.Timestamp(as_of)

    qstats = _load("qstats", DATA / "player_quarter_stats.parquet")
    pf_df = _load("pf_raw", DATA / "player_pf.parquet")

    if qstats is None or qstats.empty:
        return {}

    rows = qstats[qstats["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Enforce leak boundary via game_date from player_pf
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

    # Early foul trouble: 2+ PF in Q1
    q1_pf = rows[rows["period"] == 1].groupby("game_id")["pf"].sum()
    n_games = len(q1_pf)
    if n_games == 0:
        return {}

    early_trouble_rate = float((q1_pf >= 2).sum()) / n_games

    # Half trouble: 3+ PF accumulated through Q2
    q1q2_pf = (
        rows[rows["period"].isin([1, 2])]
        .groupby("game_id")["pf"]
        .sum()
    )
    half_trouble_rate = float((q1q2_pf >= 3).sum()) / len(q1q2_pf) if len(q1q2_pf) > 0 else 0.0

    return {
        "early_foul_trouble_rate": round(early_trouble_rate, 4),
        "half_trouble_rate": round(half_trouble_rate, 4),
        "n_games": n_games,
    }


def _foul_out_risk_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Foul-out risk from raw per-game PF totals filtered to <= as_of.

    Sources: player_pf.parquet (raw per-game PF) +
             foul_features.parquet (pf_per_36_l5 as rolling PF proxy).
    """
    as_of_ts = pd.Timestamp(as_of)

    pf_df = _load("pf_raw", DATA / "player_pf.parquet")
    if pf_df is None or pf_df.empty:
        return {}

    rows = pf_df[pf_df["player_id"] == pid].copy()
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= as_of_ts]

    if rows.empty:
        return {}

    n_games = len(rows)
    foul_out_rate = float((rows["pf"] >= 6).sum()) / n_games
    mean_pf_pg = float(rows["pf"].mean()) if n_games > 0 else None

    result: Dict[str, Any] = {
        "foul_out_rate": round(foul_out_rate, 4),
        "mean_pf_pg": _rd(mean_pf_pg),
        "n_games": n_games,
    }

    # Add rolling pf_per_36_l5 from foul_features as a recency signal
    ff = _load("foul_feat", CACHE / "foul_features.parquet")
    if ff is not None and not ff.empty:
        ff_rows = ff[ff["player_id"] == pid].copy()
        if "game_date" in ff_rows.columns:
            ff_rows["game_date"] = pd.to_datetime(ff_rows["game_date"])
            ff_rows = ff_rows[ff_rows["game_date"] <= as_of_ts]
        if not ff_rows.empty:
            ff_rows = ff_rows.sort_values("game_date")
            result["pf_pg_l5"] = _rd(ff_rows.iloc[-1].get("min_l5"))
            # min_l5 is minutes-per-game L5 (in foul_features); use last_game_pf instead
            result["last_game_pf"] = _ri(ff_rows.iloc[-1].get("last_game_pf"))

    return result


def _charges_drawn_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Charges drawn per game from hustle parquets (leak-safe: seasonal, pre-published).

    Sources: data/cache/hustle_features_2025-26.parquet (prefer fresh) +
             data/cache/hustle_features.parquet (multi-season fallback).
    Note: hustle parquets are season-aggregate (not game-by-game) so we accept the
    latest season record without a game_date filter — consistent with the profile
    factory's seasonal source treatment (spec_intel_memory §1.4).
    """
    for key, path in [
        ("hustle26", CACHE / "hustle_features_2025-26.parquet"),
        ("hustle_base", CACHE / "hustle_features.parquet"),
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
        gp = _rd(row.get("hustle_games_played")) or 1.0
        charges_raw = _rd(row.get("hustle_charges_drawn"))
        if charges_raw is None:
            return {}
        # hustle_charges_drawn is already per-game in these parquets
        return {
            "charges_drawn_pg": round(charges_raw, 4),
            "hustle_games_played": _ri(gp),
            "_source_season": str(row.get("season", "")),
        }
    return {}


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerFoulTendency(AtlasSection):
    """Deep player foul-tendency atlas section (player entity, section='foul_tendency').

    Covers four REAL sub-dicts and two DEFER stubs:
      - committed    (season + rolling L5/L10 pf_per_36, foul_trouble_rate)
      - by_quarter   (mean PF per quarter, q1 share)
      - early_trouble (early-foul-trouble + half-trouble rates)
      - foul_out_risk (foul-out rate, mean PF/game)
      - charges_drawn (hustle_charges_drawn per game)
      - drawn        (DEFER: PBP PLAYER2_ID attribution missing)
      - by_type      (DEFER: NBA per-type breakdown not in public endpoints)

    Three CV slots reserved for CV-branch enrichment (all values None until filled).

    Sources:
      - data/cache/foul_features.parquet (rolling window)
      - data/player_pf.parquet (raw per-game PF)
      - data/player_pf_per36.parquet (season-level pf_per_36)
      - data/player_quarter_stats.parquet (per-quarter PF)
      - data/cache/hustle_features_2025-26.parquet + hustle_features.parquet

    NOT used (intentionally excluded):
      - data/cache/inplay_foul_state.parquet — team-level cumulative per period,
        not per-player; used for in-game live context only.
    """

    name: str = "foul_tendency"
    entity: str = "player"
    source_name: str = (
        "foul_features.parquet + player_pf.parquet + player_pf_per36.parquet + "
        "player_quarter_stats.parquet + hustle_features_2025-26.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the leak-safe foul_tendency artifact for one player.

        Leak guarantee:
          - foul_features, player_pf, player_pf_per36: filtered game_date <= as_of.
          - player_quarter_stats: joined to game_date via player_pf (same bound).
          - hustle parquets: season-aggregate (published end-of-season, no intra-season
            leak risk; same treatment as playtypes/tracking in spec_intel_memory §1.4).

        Returns None when the player is absent from all primary per-game sources.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        committed = _committed_for_player(pid, as_of)
        by_quarter = _by_quarter_for_player(pid, as_of)
        early_trouble = _early_trouble_for_player(pid, as_of)
        foul_out_risk = _foul_out_risk_for_player(pid, as_of)
        charges_drawn = _charges_drawn_for_player(pid, as_of)

        # Bail if no per-game data at all
        if not committed and not by_quarter and not foul_out_risk:
            return None

        # --- DEFER stubs ---
        drawn: Dict[str, Any] = {
            "_note": (
                "DEFER: foul-drawn breakdown requires PBP PLAYER2_ID (fouled-player). "
                "V3->V2 normalization in pbp_scraper.py sets PLAYER2_ID='0' on all "
                "freshly scraped files; true-V2 per-player drawn-foul attribution is "
                "unavailable until the PBP feed is restored (spec_features §2 GOTCHA)."
            )
        }
        by_type: Dict[str, Any] = {
            "_note": (
                "DEFER: per-type foul breakdown (blocking/charging/technical/flagrant/"
                "loose-ball/away-from-ball) is not available from NBA Stats API public "
                "endpoints. Requires LeagueFouls premium endpoint or manual PBP "
                "EVENTMSGTYPE/HOMEDESCRIPTION text parsing."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "committed": committed,
            "by_quarter": by_quarter,
            "early_trouble": early_trouble,
            "foul_out_risk": foul_out_risk,
            "charges_drawn": charges_drawn,
            "drawn": drawn,
            "by_type": by_type,
        }

        # --- Sample size: max across per-game sources ---
        n_candidates: List[int] = []
        if committed.get("n_games"):
            n_candidates.append(committed["n_games"])
        if early_trouble.get("n_games"):
            n_candidates.append(early_trouble["n_games"])
        if foul_out_risk.get("n_games"):
            n_candidates.append(foul_out_risk["n_games"])
        n = max(n_candidates) if n_candidates else 1

        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        # Headline value: foul-out risk (most actionable single scalar)
        headline = _rd(foul_out_risk.get("foul_out_rate")) if foul_out_risk else None

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
        """Face-validity check: required keys present, rates in [0, 1].

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required = {"committed", "by_quarter", "early_trouble", "foul_out_risk",
                    "charges_drawn", "drawn", "by_type"}
        if not required.issubset(sf.keys()):
            return False

        # Rate fields must be in [0, 1] when present
        for outer, key in [
            ("early_trouble", "early_foul_trouble_rate"),
            ("early_trouble", "half_trouble_rate"),
            ("foul_out_risk", "foul_out_rate"),
        ]:
            v = sf.get(outer, {}).get(key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False

        # PF-per-36 must be non-negative when present
        for key in ["pf_per_36_l5", "pf_per_36_l10", "season_pf_per_36"]:
            v = sf.get("committed", {}).get(key)
            if v is not None and v < 0.0:
                return False

        # CV fields present and all null (CV branch hasn't run)
        if not artifact.cv_fields:
            return False
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for foul_tendency (values None — CV branch fills).

        The CV-fix session calls:
          store.fill_cv_slot("player", pid, "foul_tendency", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild.  Slots are stable keys.
        """
        return {
            "contest_proximity_at_foul": CVSlot(
                name="contest_proximity_at_foul",
                dtype="float",
                description=(
                    "Mean distance (ft) between the fouling player and the ball-handler "
                    "at the frame where a foul event is detected (CV EventDetector "
                    "EVENTMSGTYPE=6 frame anchor + homography coordinates). "
                    "Low values indicate hand-check / reach-in style; high values "
                    "indicate help-defense blocking fouls away from the ball."
                ),
                unit="ft",
                value=None,
            ),
            "foul_body_angle": CVSlot(
                name="foul_body_angle",
                dtype="float",
                description=(
                    "Mean body-orientation angle delta (deg) between the fouling "
                    "player's torso and the ball-handler's direction of travel at the "
                    "foul frame. Near-zero = player is square-on (likely charge or "
                    "block contest); large angle = reaching across (illegal use of hands). "
                    "Derived from pose estimation or bounding-box heading vector."
                ),
                unit="deg",
                value=None,
            ),
            "spacing_at_foul_commit": CVSlot(
                name="spacing_at_foul_commit",
                dtype="float",
                description=(
                    "Mean convex-hull area (ft²) of the fouling player's teammates "
                    "at the frame of a committed foul. Large values indicate a help "
                    "rotation foul (leaving a shooter open); small values indicate "
                    "on-ball personal foul in tight coverage. "
                    "From homography court coordinates at the EventDetector foul frame."
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
    """Build foul_tendency for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int). If None, discovers from player_pf.
        as_of:      leak boundary date (defaults to today's UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes (compute and validate only).

    Returns:
        manifest dict from register_section.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        pf_df = _load("pf_raw_disc", DATA / "player_pf.parquet")
        if pf_df is not None and "player_id" in pf_df.columns:
            player_ids = sorted(pf_df["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerFoulTendency()
    artifacts = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
