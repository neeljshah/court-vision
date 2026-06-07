"""ARM-B AtlasSection: player_quarter_shape_fatigue.

Deep per-player fatigue profile: Q1-Q4 production curve, Q4 fade ratio,
minutes load, and B2B decay (both full-game and Q4-specific).

Data sources (REUSED, not re-derived):
  * data/player_quarter_stats.parquet   -- Q1-Q4 pts/reb/ast/min per game
  * data/player_adv_stats.parquet       -- game_date + full-game minutes load;
                                          also used to derive is_b2b from
                                          consecutive game-date gaps per player

Sub-fields:
  REAL (populated from parquets):
    q1_pts, q2_pts, q3_pts, q4_pts           -- mean pts per quarter
    q1_reb, q2_reb, q3_reb, q4_reb           -- mean reb per quarter
    q1_ast, q2_ast, q3_ast, q4_ast           -- mean ast per quarter
    q1_min, q2_min, q3_min, q4_min           -- mean minutes per quarter
    q4_vs_early_ratio                         -- Q4 pts / mean(Q1+Q2+Q3) pts
    q4_fade_abs                               -- Q4 pts - mean(Q1+Q2+Q3) pts
    min_per_game                              -- mean full-game minutes (adv_stats)
    n_games                                   -- sample size
    b2b_n_games                               -- number of B2B games
    b2b_q4_pts_delta                          -- Q4 pts on B2B minus non-B2B
    b2b_pts_delta                             -- all-quarter pts on B2B minus non-B2B
    b2b_decay_ratio                           -- B2B total pts / non-B2B total pts

  DEFER (insufficient source data; must await B2B team-level enrichment or
  CV data to fill; see cv_fields for reserved CV slots):
    Late-half speed decay and on-court fatigue signals from CV.

CV slots (RESERVED, values=None until CV branch fills):
  speed_decay     -- per-frame velocity drop Q4 vs Q1 (CV pipeline)
  late_game_lift  -- fraction of late-clock shots showing positive velocity
                     spike (burst/effort measure from tracking)
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
_QS_PATH = ROOT / "data" / "player_quarter_stats.parquet"
_ADV_PATH = ROOT / "data" / "player_adv_stats.parquet"

_CONF_CAP: Optional[str] = None  # no external cap; confidence from sample size only


def _rd(v: Any) -> Optional[float]:
    """Round float to 4 dp; NaN/None/inf -> None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 4)


def _load_sources(as_of: _dt.datetime) -> tuple:
    """Load quarter_stats and adv_stats filtered to as_of date (leak-safe).

    Returns (pqs_dated, game_info) or (None, None) on missing source.
    pqs_dated: per-player per-game per-period rows with game_date + B2B flag.
    game_info: per-player per-game with minutes + B2B.
    """
    if not _QS_PATH.exists() or not _ADV_PATH.exists():
        return None, None

    as_of_date = as_of.date().isoformat()

    # adv_stats: game_date + minutes; derive per-player B2B from consecutive dates
    adv = pd.read_parquet(_ADV_PATH, columns=["player_id", "game_id", "game_date", "minutes"])
    adv["game_date"] = pd.to_datetime(adv["game_date"])
    # Leak guard: drop rows whose game_date is AFTER as_of
    adv = adv[adv["game_date"] <= as_of_date].copy()
    adv = adv.sort_values(["player_id", "game_date"])

    # Derive is_b2b: days_rest == 1 means consecutive game (back-to-back)
    adv["prev_game_date"] = adv.groupby("player_id")["game_date"].shift(1)
    adv["days_rest"] = (adv["game_date"] - adv["prev_game_date"]).dt.days
    adv["is_b2b"] = (adv["days_rest"] == 1).astype("Int8")

    game_info = adv[["player_id", "game_id", "game_date", "minutes", "is_b2b"]].copy()
    game_info["game_date_str"] = game_info["game_date"].dt.date.astype(str)

    # quarter_stats: period-level box-score rows
    pqs = pd.read_parquet(_QS_PATH)
    # Join game_date + B2B onto pqs via (player_id, game_id) -- avoids game_date leak
    pqs_dated = pqs.merge(game_info, on=["player_id", "game_id"], how="inner")

    return pqs_dated, game_info


def _build_artifact(
    entity_id: int,
    pqs_dated: pd.DataFrame,
    game_info: pd.DataFrame,
    as_of_iso: str,
) -> Optional[AtlasArtifact]:
    """Compute all sub-fields for one player_id."""
    p = pqs_dated[pqs_dated["player_id"] == entity_id]
    gi = game_info[game_info["player_id"] == entity_id]

    if p.empty or gi.empty:
        return None

    n_games = int(p["game_id"].nunique())
    if n_games < 1:
        return None

    # -- Q1-Q4 production curve ------------------------------------------------
    q_agg = p.groupby("period").agg(
        pts=("pts", "mean"),
        reb=("reb", "mean"),
        ast=("ast", "mean"),
        min=("min", "mean"),
    )

    def _qval(q: int, col: str) -> Optional[float]:
        if q in q_agg.index:
            return _rd(q_agg.at[q, col])
        return None

    q1_pts = _qval(1, "pts")
    q2_pts = _qval(2, "pts")
    q3_pts = _qval(3, "pts")
    q4_pts = _qval(4, "pts")

    q1_reb = _qval(1, "reb")
    q2_reb = _qval(2, "reb")
    q3_reb = _qval(3, "reb")
    q4_reb = _qval(4, "reb")

    q1_ast = _qval(1, "ast")
    q2_ast = _qval(2, "ast")
    q3_ast = _qval(3, "ast")
    q4_ast = _qval(4, "ast")

    q1_min = _qval(1, "min")
    q2_min = _qval(2, "min")
    q3_min = _qval(3, "min")
    q4_min = _qval(4, "min")

    # -- Q4 fade ---------------------------------------------------------------
    early_vals = [v for v in [q1_pts, q2_pts, q3_pts] if v is not None]
    early_avg = float(np.mean(early_vals)) if early_vals else None

    q4_vs_early_ratio: Optional[float] = None
    q4_fade_abs: Optional[float] = None
    if early_avg is not None and early_avg > 0 and q4_pts is not None:
        q4_vs_early_ratio = _rd(q4_pts / early_avg)
        q4_fade_abs = _rd(q4_pts - early_avg)

    # -- Minutes load ----------------------------------------------------------
    min_per_game = _rd(gi["minutes"].mean())

    # -- B2B decay -------------------------------------------------------------
    b2b_rows = p[p["is_b2b"] == 1]
    non_b2b_rows = p[p["is_b2b"] == 0]
    b2b_n_games = int(b2b_rows["game_id"].nunique())

    b2b_q4_pts_delta: Optional[float] = None
    b2b_pts_delta: Optional[float] = None
    b2b_decay_ratio: Optional[float] = None

    if b2b_n_games >= 3:
        b2b_q4 = b2b_rows[b2b_rows["period"] == 4]["pts"].mean()
        non_b2b_q4 = non_b2b_rows[non_b2b_rows["period"] == 4]["pts"].mean()
        if not (np.isnan(b2b_q4) or np.isnan(non_b2b_q4)):
            b2b_q4_pts_delta = _rd(b2b_q4 - non_b2b_q4)

        b2b_all_pts = b2b_rows["pts"].mean()
        non_b2b_all_pts = non_b2b_rows["pts"].mean()
        if not (np.isnan(b2b_all_pts) or np.isnan(non_b2b_all_pts)):
            b2b_pts_delta = _rd(b2b_all_pts - non_b2b_all_pts)
            if non_b2b_all_pts > 0:
                b2b_decay_ratio = _rd(b2b_all_pts / non_b2b_all_pts)

    # -- latest as_of from the data (use most recent game_date in filtered set) -
    latest_date = gi["game_date"].max()
    data_as_of = str(latest_date.date()) if pd.notna(latest_date) else as_of_iso

    sub_fields: Dict[str, Any] = {
        # Q-level production curve
        "q1_pts": q1_pts,
        "q2_pts": q2_pts,
        "q3_pts": q3_pts,
        "q4_pts": q4_pts,
        "q1_reb": q1_reb,
        "q2_reb": q2_reb,
        "q3_reb": q3_reb,
        "q4_reb": q4_reb,
        "q1_ast": q1_ast,
        "q2_ast": q2_ast,
        "q3_ast": q3_ast,
        "q4_ast": q4_ast,
        "q1_min": q1_min,
        "q2_min": q2_min,
        "q3_min": q3_min,
        "q4_min": q4_min,
        # Q4 fade
        "q4_vs_early_ratio": q4_vs_early_ratio,
        "q4_fade_abs": q4_fade_abs,
        # Minutes load
        "min_per_game": min_per_game,
        # B2B decay
        "b2b_n_games": b2b_n_games,
        "b2b_q4_pts_delta": b2b_q4_pts_delta,
        "b2b_pts_delta": b2b_pts_delta,
        "b2b_decay_ratio": b2b_decay_ratio,
        # sample meta
        "n_games": n_games,
    }

    confidence = confidence_from_n(n_games, cap=_CONF_CAP)

    provenance = {
        "source": "player_quarter_stats.parquet+player_adv_stats.parquet",
        "n": n_games,
        "confidence": confidence,
        "as_of": data_as_of,
    }

    return AtlasArtifact(
        section=PlayerQuarterShapeFatigue.name,
        entity="player",
        entity_id=entity_id,
        value=q4_vs_early_ratio,  # headline scalar
        sub_fields=sub_fields,
        provenance=provenance,
        confidence=confidence,
        as_of=data_as_of,
        cv_fields=PlayerQuarterShapeFatigue().cv_fields(),
    )


class PlayerQuarterShapeFatigue(AtlasSection):
    """Per-player Q1-Q4 production curve, Q4 fade, minutes load, and B2B decay.

    Reads:
      - data/player_quarter_stats.parquet  (Q1-Q4 box-score rows)
      - data/player_adv_stats.parquet      (game_date + minutes; B2B derivation)

    All reads are filtered to ``as_of`` (leak-safe). The athlete's own game-date
    sequence is used to derive B2B status without needing a team-level join.

    CV slots reserved (values=None until CV session fills):
      speed_decay     -- Q4 vs Q1 velocity drop from broadcast tracking
      late_game_lift  -- fraction of late-clock possessions with a positive
                         velocity burst (effort signal from player tracking)
    """

    name: str = "quarter_shape_fatigue"
    entity: str = "player"
    source_name: str = "player_quarter_stats.parquet+player_adv_stats.parquet"
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the leak-safe fatigue atlas artifact for one player.

        Args:
            entity_id: NBA player_id (int).
            as_of:     decision datetime; only data with game_date <= as_of is used.

        Returns:
            AtlasArtifact with Q1-Q4 curve + Q4 fade + B2B decay sub-fields,
            or None if the player is not present in the source parquets.
        """
        pqs_dated, game_info = _load_sources(as_of)
        if pqs_dated is None:
            return None
        return _build_artifact(entity_id, pqs_dated, game_info, as_of.date().isoformat())

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: key sub-fields present, ratios in sane range.

        Checks:
          - required keys present in sub_fields
          - q4_vs_early_ratio in [0, 3] when not None
          - b2b_decay_ratio in [0, 3] when not None
          - n_games >= 1
        """
        sf = artifact.sub_fields
        required = {"q1_pts", "q4_pts", "q4_vs_early_ratio", "n_games"}
        if not required.issubset(sf.keys()):
            return False
        ratio = sf.get("q4_vs_early_ratio")
        if ratio is not None and not (0 <= ratio <= 3):
            return False
        b2b_ratio = sf.get("b2b_decay_ratio")
        if b2b_ratio is not None and not (0 <= b2b_ratio <= 3):
            return False
        if (sf.get("n_games") or 0) < 1:
            return False
        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Return the reserved CV-slot schema (values=None; CV branch fills later).

        Slots:
            speed_decay     -- Q4 vs Q1 per-frame velocity drop from broadcast CV.
            late_game_lift  -- fraction of late-clock possessions with a positive
                               velocity burst (effort signal, broadcast CV).
        """
        return {
            "speed_decay": CVSlot(
                name="speed_decay",
                dtype="float",
                description=(
                    "Mean per-frame velocity in Q4 minus Q1 (ft/s), derived from "
                    "broadcast tracking. Negative = player slows late."
                ),
                unit="ft/s",
                value=None,
            ),
            "late_game_lift": CVSlot(
                name="late_game_lift",
                dtype="float",
                description=(
                    "Fraction of Q4 or clutch possessions where the player shows "
                    "a positive velocity burst vs their own game mean (0-1 scale)."
                ),
                unit=None,
                value=None,
            ),
        }


def build_all_players(
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
    min_games: int = 1,
) -> Dict[str, Any]:
    """Build and register the section for all available players.

    Args:
        as_of:     decision datetime (defaults to today 00:00 UTC).
        store:     optional PointInTimeStore to write artifacts into.
        dry_run:   skip all disk writes (useful for testing).
        min_games: skip players with fewer than this many games.

    Returns:
        manifest dict from ``profile_factory_bridge.register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    section = PlayerQuarterShapeFatigue()
    pqs_dated, game_info = _load_sources(as_of)
    if pqs_dated is None:
        return {"section": section.name, "n_entities": 0, "error": "missing_sources"}

    player_ids = sorted(pqs_dated["player_id"].unique())
    artifacts = []
    for pid in player_ids:
        art = _build_artifact(int(pid), pqs_dated, game_info, as_of.date().isoformat())
        if art is None:
            continue
        if (art.sub_fields.get("n_games") or 0) < min_games:
            continue
        if section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
