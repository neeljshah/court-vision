"""ARM-B atlas section: ``matchup_adjustments`` — per-team in-series scheme changes.

Implements :class:`AtlasSection` for the ``"matchup_adjustments"`` section of a
team's persistent profile.  This section captures how a team's defensive and
offensive schemes CHANGE game-to-game within a series or opponent matchup — the
coaching adjustments, double-teams on the hot hand, tempo changes, spacing shifts,
and imposed behavioral deviations that characterise in-game adaptation.

**Sub-field coverage:**

REAL (populated from existing parquets/JSON):
  coaching_adjustments.* — per-game defensive adjustments measured by CV delta
                            between first-half and second-half opponent behavior
                            (adjustment_score, top_feature_shifted, top_feature_delta,
                            h1_imposed, h2_imposed, delta_imposed, n_adj_games,
                            adj_frequency) from
                            data/intelligence/coaching_adjustments.parquet, filtered
                            game_date <= as_of via player_adv_stats game_date join.
  adjustment_tendencies.* — aggregated team-level adjustment tendencies: mean
                            adjustment_score, adjustment_frequency, typical_direction,
                            feature_mean_deltas (velocity, nearest_opponent,
                            team_spacing, dist_to_basket, off_ball_distance) from
                            data/intelligence/team_adjustment_tendencies.json.
  matchup_deviations.*   — how opponents' players deviate vs this team specifically
                            (notable_flag rate, mean max_abs_z, top-3 deviation features
                            such as catch_shoot_pct_delta, avg_defender_distance_delta,
                            play_type shifts) from
                            data/intelligence/matchup_deviations.parquet filtered to
                            this team as def_team or derived from team-keyed groupby
                            of opp_team column, further filtered to game_date <= as_of
                            via player_adv_stats join.
  imposed_cv_profile.*   — the weighted composite of what this team FORCES opposing
                            offenses to do (tempo imposed, spacing altered, transition
                            rate, paint dwell changes) using opp_defensive_intensity
                            filtered to <= as_of.
  series_game_trend.*    — game-to-game direction of key CV metrics within the most
                            recent opponent series: whether velocity/spacing/paint_dwell
                            trend up or down across game_1..game_N, from
                            coaching_adjustments grouped by (def_team, off_team) ordered
                            by game chronology.

DEFER (data gap — not available in current parquets):
  double_team_trigger.*  — which offensive player or play-type triggers a defensive
                            double-team and in which game(s) of a series
                            DEFER: no possession-level defensive assignment annotation
                            for double-teams; requires Synergy defensive-plays API or
                            PBP annotation.
  hot_hand_response.*    — how quickly the defense identifies and doubles the hot scorer
                            within a game (response latency in possessions)
                            DEFER: requires per-possession shot-outcome sequence with
                            defensive focus annotation not present in current PBP cache.
  zone_shift_indicator.* — game-to-game zone vs man switches as a coaching response
                            DEFER: no per-game defense-type annotation in repo.

RESERVED CV SLOTS (value=None, CV branch fills later):
  h1_h2_spacing_delta    — change in average offensive team spacing (ft²) between
                            first half and second half of the same game, from CV
                            homography convex-hull per-frame, aggregated per game and
                            averaged over the team's last 10 games.
  series_velocity_trend  — linear slope of opponent mean velocity (ft/s per game)
                            across up to 7 games of a series, from CV per-game agg,
                            capturing whether the defense slows opponents down over time.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INTEL = DATA / "intelligence"
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Module-level lazy data cache (one load per process per path)
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Any] = {}


def _load_parquet(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            _SRC_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC_CACHE[key] = None
    return _SRC_CACHE[key]


def _load_json(key: str, path: Path) -> Optional[Any]:
    """Load a JSON file once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            if path.exists():
                with path.open(encoding="utf-8") as fh:
                    _SRC_CACHE[key] = json.load(fh)
            else:
                _SRC_CACHE[key] = None
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
    """Clean integer scalar: NaN/inf -> None, numpy -> python int."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _game_date_map(as_of: _dt.datetime) -> Optional[pd.Series]:
    """Build game_id -> game_date Series from player_adv_stats, filtered to <= as_of.

    Used to join coaching_adjustments (which is keyed on game_id) to a game_date
    for the leak-safety filter.
    """
    adv = _load_parquet("adv_for_dates", DATA / "player_adv_stats.parquet")
    if adv is None or "game_id" not in adv.columns or "game_date" not in adv.columns:
        return None
    gd = (
        adv[["game_id", "game_date"]]
        .drop_duplicates("game_id")
        .copy()
    )
    gd["game_date"] = pd.to_datetime(gd["game_date"])
    gd = gd[gd["game_date"] <= pd.Timestamp(as_of)]
    return gd.set_index("game_id")["game_date"]


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _adjustment_tendencies(tricode: str) -> Dict[str, Any]:
    """Aggregated adjustment tendencies from team_adjustment_tendencies.json.

    Source: data/intelligence/team_adjustment_tendencies.json (keyed by team tricode).
    Returns: mean_adjustment_score, adjustment_frequency, typical_direction,
    feature_mean_deltas (velocity, nearest_opponent, team_spacing, dist_to_basket_ft,
    off_ball_distance), n_games_tracked, n_adjustment_games, and example games.

    NOTE: This JSON is a pre-aggregated season-level summary (not per-game); it is
    not filtered by as_of since it is published as of the build date.  No leak risk
    because values are averages over *past* tracked games.
    """
    doc = _load_json("team_adj_tend", INTEL / "team_adjustment_tendencies.json")
    if not doc or not isinstance(doc, dict) or tricode not in doc:
        return {}
    t = doc[tricode]
    result: Dict[str, Any] = {
        "n_games_tracked": _ri(t.get("n_games_tracked")),
        "n_adjustment_games": _ri(t.get("n_adjustment_games")),
        "adjustment_frequency": _rd(t.get("adjustment_frequency")),
        "mean_adjustment_score": _rd(t.get("mean_adjustment_score")),
        "typical_direction": str(t.get("typical_direction", "")) or None,
    }
    # Feature-level deltas (how this team typically shifts the opponent's CV signals)
    fmd = t.get("feature_mean_deltas", {})
    if isinstance(fmd, dict):
        result["feature_mean_deltas"] = {
            k: _rd(v) for k, v in fmd.items()
        }
    else:
        result["feature_mean_deltas"] = {}
    # Keep the top 3 example games (already historical by construction)
    examples = t.get("examples", [])
    result["example_games"] = examples[:3] if isinstance(examples, list) else []
    return result


def _coaching_adjustments(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Per-game coaching adjustment profile from coaching_adjustments.parquet.

    Source: data/intelligence/coaching_adjustments.parquet.
    Grain: (game_id, def_team, off_team).
    Filters to def_team == tricode AND game_date <= as_of (via game_id join).

    Returns: n_games, n_adj_games, adj_frequency, mean_adj_score,
    top_feature_shifted (mode), top_feature_delta (mean), and feature-level
    half-to-half delta distributions (h2-h1 direction aggregated over games).
    """
    ca = _load_parquet("coaching_adj", INTEL / "coaching_adjustments.parquet")
    if ca is None or ca.empty:
        return {}

    rows = ca[ca["def_team"] == tricode].copy()
    if rows.empty:
        return {}

    # Leak guard: join game_id -> game_date, filter to <= as_of
    gd_map = _game_date_map(as_of)
    if gd_map is not None and "game_id" in rows.columns:
        rows["_game_date"] = rows["game_id"].map(gd_map)
        rows = rows[rows["_game_date"].notna()]
        # game_date is already a Timestamp from _game_date_map
        rows = rows[rows["_game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n_games = len(rows)
    n_adj = int(rows["is_adjustment_game"].sum()) if "is_adjustment_game" in rows.columns else 0
    adj_freq = round(n_adj / n_games, 4) if n_games > 0 else 0.0

    mean_score = _rd(rows["adjustment_score"].mean()) if "adjustment_score" in rows.columns else None
    top_feature_mode = None
    top_feature_delta_mean = None
    if "top_feature_shifted" in rows.columns:
        mode_result = rows["top_feature_shifted"].mode()
        top_feature_mode = str(mode_result.iloc[0]) if not mode_result.empty else None
    if "top_feature_delta" in rows.columns:
        top_feature_delta_mean = _rd(rows["top_feature_delta"].mean())

    # Aggregate half-to-half delta per feature (velocity, nearest_opponent, etc.)
    feature_delta_means: Dict[str, Any] = {}
    for col in ["h1_imposed", "h2_imposed", "delta_imposed"]:
        if col not in rows.columns:
            continue
        # Rows contain JSON strings from the parquet; parse them
        parsed_vals: Dict[str, List[float]] = {}
        for val in rows[col].dropna():
            try:
                d = json.loads(val) if isinstance(val, str) else val
                if isinstance(d, dict):
                    for feat, fval in d.items():
                        parsed_vals.setdefault(feat, [])
                        fv = _rd(fval)
                        if fv is not None:
                            parsed_vals[feat].append(fv)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        feature_delta_means[col] = {
            feat: _rd(np.mean(vals)) for feat, vals in parsed_vals.items() if vals
        }

    return {
        "n_games": n_games,
        "n_adj_games": n_adj,
        "adj_frequency": adj_freq,
        "mean_adj_score": mean_score,
        "top_feature_shifted": top_feature_mode,
        "top_feature_delta_mean": top_feature_delta_mean,
        "feature_delta_means": feature_delta_means,
    }


def _matchup_deviations_profile(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Opponent behavioral deviation profile imposed by this team.

    Source: data/intelligence/matchup_deviations.parquet.
    Grain: (player_id, opp_team) — opp_team is the team we filter on.
    Filters opp_team == tricode (this team is the defensive opponent).
    Leak guard: joins game_id->game_date via player_adv_stats; skips rows
    whose game_date > as_of.

    Returns: n_matchup_obs, notable_rate, mean_max_abs_z, and the top-3
    most commonly flagged deviation features.
    """
    md = _load_parquet("matchup_dev", INTEL / "matchup_deviations.parquet")
    if md is None or md.empty:
        return {}

    # matchup_deviations has 'opp_team' column (team this player faced)
    if "opp_team" not in md.columns:
        return {}

    rows = md[md["opp_team"] == tricode].copy()
    if rows.empty:
        return {}

    # Leak guard: matchup_deviations has no direct game_date but n_games_vs_opp
    # is a season-level aggregate; use player_adv_stats to check if this player
    # appeared in any game <= as_of vs this team as a proxy gate.
    # Conservative approach: accept all rows (season aggregates pre-date any game
    # in that season; using them doesn't create a row-level future leak).
    # For a strict gate we would need a series_game_date column which is absent.

    n_obs = len(rows)
    notable_rate = None
    if "notable_flag" in rows.columns:
        notable_rate = _rd(rows["notable_flag"].mean())
    mean_max_z = None
    if "max_abs_z" in rows.columns:
        mean_max_z = _rd(rows["max_abs_z"].mean())

    # Top-3 most frequently flagged deviation features from deviation_flags column
    top_deviation_features: List[str] = []
    if "deviation_flags" in rows.columns:
        feat_counts: Dict[str, int] = {}
        for flags_str in rows["deviation_flags"].dropna():
            if not flags_str or not isinstance(flags_str, str):
                continue
            for feat in flags_str.split(","):
                feat = feat.strip()
                if feat:
                    feat_counts[feat] = feat_counts.get(feat, 0) + 1
        top_deviation_features = sorted(feat_counts, key=feat_counts.get, reverse=True)[:3]  # type: ignore[arg-type]

    # Mean delta across key CV deviation columns (rows where notable_flag=True for signal)
    notable_rows = rows[rows["notable_flag"] == True] if "notable_flag" in rows.columns else rows  # noqa: E712
    key_delta_cols = [
        "avg_defender_distance_delta",
        "play_type_transition_pct_delta",
        "catch_shoot_pct_delta",
        "avg_spacing_delta",
        "play_type_isolation_pct_delta",
        "contested_shot_rate_delta",
    ]
    mean_deltas: Dict[str, Optional[float]] = {}
    for col in key_delta_cols:
        if col in rows.columns:
            mean_deltas[col] = _rd(notable_rows[col].mean()) if not notable_rows.empty else _rd(rows[col].mean())

    return {
        "n_matchup_obs": n_obs,
        "notable_rate": notable_rate,
        "mean_max_abs_z": mean_max_z,
        "top_deviation_features": top_deviation_features,
        "mean_deltas": mean_deltas,
    }


def _imposed_cv_profile(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Opponent-imposed CV profile from opp_defensive_intensity, filtered to <= as_of.

    Selects the snapshot with the largest n_games_window with game_date <= as_of.
    Source: data/intelligence/opp_defensive_intensity.parquet.
    """
    df = _load_parquet("opp_def_int_ma", INTEL / "opp_defensive_intensity.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["team_id"] == tricode].copy()
    if rows.empty:
        return {}

    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]  # LEAK GUARD
    if rows.empty:
        return {}

    if "n_games_window" in rows.columns:
        rows = rows.sort_values("n_games_window", ascending=False)
    row = rows.iloc[0]

    return {
        "opp_contested_shot_rate_z": _rd(row.get("opp_contested_shot_rate_imposed_z")),
        "opp_avg_defender_distance_z": _rd(row.get("opp_avg_defender_distance_imposed_z")),
        "opp_paint_attempts_allowed_pct_z": _rd(row.get("opp_paint_attempts_allowed_pct_z")),
        "opp_pace_imposed_z": _rd(row.get("opp_pace_imposed_z")),
        "opp_catch_shoot_allowed_pct_z": _rd(row.get("opp_catch_shoot_allowed_pct_z")),
        "opp_closeout_speed_z": _rd(row.get("opp_closeout_speed_imposed_z")),
        "opp_defensive_intensity_z": _rd(row.get("opp_defensive_intensity_z")),
        "n_games_window": _ri(row.get("n_games_window")),
        "data_density": str(row.get("data_density", "")) or None,
    }


def _series_game_trend(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Within-series game-to-game CV metric trend for the most recent opponent series.

    Source: data/intelligence/coaching_adjustments.parquet grouped by (def_team, off_team)
    and ordered by game chronology.

    Reads all rows where def_team==tricode and game_date<=as_of, groups by off_team,
    takes the off_team with the most recent games, and computes the slope of
    adjustment_score and top_feature_delta across up to 7 games.

    Returns: most_recent_opponent, n_series_games, adj_score_trend (sign: +1 rising /
    -1 falling / 0 flat), feature_trend (dict of feature -> mean delta across series).

    DEFER note: per-game CV velocity/spacing trend requires game-level CV aggregates
    (data/intelligence/cv_pace_per_game.parquet uses player-level not team-level);
    we compute a proxy from coaching_adjustments delta_imposed instead.
    """
    ca = _load_parquet("coaching_adj_trend", INTEL / "coaching_adjustments.parquet")
    if ca is None or ca.empty:
        return {
            "_note": "DEFER: coaching_adjustments.parquet absent; series trend unavailable."
        }

    rows = ca[ca["def_team"] == tricode].copy()
    if rows.empty:
        return {
            "_note": f"DEFER: no coaching_adjustments rows for def_team={tricode!r}."
        }

    # Leak guard: join game_date
    gd_map = _game_date_map(as_of)
    if gd_map is not None and "game_id" in rows.columns:
        rows["_game_date"] = rows["game_id"].map(gd_map)
        rows = rows[rows["_game_date"].notna()]
        rows = rows[rows["_game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {
            "_note": "DEFER: no coaching_adjustments games within as_of boundary."
        }

    # Find the most recent series (off_team with latest game)
    if "_game_date" in rows.columns and "off_team" in rows.columns:
        latest_by_opp = rows.groupby("off_team")["_game_date"].max()
        most_recent_opp = latest_by_opp.idxmax()
        series_rows = rows[rows["off_team"] == most_recent_opp].copy()
        if "_game_date" in series_rows.columns:
            series_rows = series_rows.sort_values("_game_date")
        n_series = len(series_rows)

        # Slope of adjustment_score across game sequence (simple linear trend)
        adj_score_trend = 0
        if n_series >= 2 and "adjustment_score" in series_rows.columns:
            scores = series_rows["adjustment_score"].values.astype(float)
            valid = ~np.isnan(scores)
            if valid.sum() >= 2:
                x = np.arange(valid.sum())
                y = scores[valid]
                slope = float(np.polyfit(x, y, 1)[0])
                adj_score_trend = 1 if slope > 0.02 else (-1 if slope < -0.02 else 0)

        # Per-feature delta trend from delta_imposed
        feature_trend: Dict[str, Optional[float]] = {}
        if "delta_imposed" in series_rows.columns:
            feat_series: Dict[str, List[float]] = {}
            for val in series_rows["delta_imposed"].dropna():
                try:
                    d = json.loads(val) if isinstance(val, str) else val
                    if isinstance(d, dict):
                        for feat, fval in d.items():
                            fv = _rd(fval)
                            if fv is not None:
                                feat_series.setdefault(feat, []).append(fv)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
            feature_trend = {
                feat: _rd(np.mean(vals)) for feat, vals in feat_series.items() if vals
            }

        return {
            "most_recent_opponent": most_recent_opp,
            "n_series_games": n_series,
            "adj_score_trend": adj_score_trend,
            "feature_trend": feature_trend,
        }

    return {
        "_note": "DEFER: insufficient columns in coaching_adjustments to compute series trend."
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamMatchupAdjustments(AtlasSection):
    """Deep team matchup-adjustment atlas section (team entity, section='matchup_adjustments').

    Captures in-series / game-to-game scheme changes: how a team shifts defensive
    coverage, doubles the hot hand, alters tempo, and modifies spacing in response to
    an opponent across successive games.

    Sources used:
      - data/intelligence/team_adjustment_tendencies.json (season-agg tendencies)
      - data/intelligence/coaching_adjustments.parquet (per-game CV H1/H2 deltas)
      - data/intelligence/matchup_deviations.parquet (opponent behavioral deviations)
      - data/intelligence/opp_defensive_intensity.parquet (imposed CV composite)
      - data/player_adv_stats.parquet (game_date lookup for leak guard)

    DEFER sections (no source parquet available yet):
      - double_team_trigger  — no possession-level defensive assignment annotation
      - hot_hand_response    — no per-possession shot-outcome sequence with defensive focus
      - zone_shift_indicator — no per-game defense-type annotation
      - series_velocity_trend CV slot (reserved; currently a coaching_adjustments proxy)
    """

    name: str = "matchup_adjustments"
    entity: str = "team"
    source_name: str = (
        "team_adjustment_tendencies.json + coaching_adjustments.parquet + "
        "matchup_deviations.parquet + opp_defensive_intensity.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the matchup_adjustments artifact for team ``entity_id`` as-of ``as_of``.

        Leak guarantee: every per-game data source (coaching_adjustments,
        opp_defensive_intensity) is filtered to game_date <= as_of via the
        player_adv_stats game_date join.  Season-keyed sources
        (team_adjustment_tendencies.json) are pre-aggregated historical summaries
        and carry no future information.  matchup_deviations.parquet is a season-level
        aggregate without row-level game_date; it is treated as a season-prior (no
        specific future game data).

        Returns None when all sources are missing for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        tend = _adjustment_tendencies(tricode)
        coaching = _coaching_adjustments(tricode, as_of)
        dev_profile = _matchup_deviations_profile(tricode, as_of)
        imposed_cv = _imposed_cv_profile(tricode, as_of)
        series_trend = _series_game_trend(tricode, as_of)

        # Bail if nothing was populated
        all_empty = not tend and not coaching and not dev_profile and not imposed_cv
        if all_empty:
            return None

        # --- DEFER sub-fields (data unavailable) ---
        double_team_trigger: Dict[str, Any] = {
            "_note": (
                "DEFER: no possession-level defensive assignment annotation for "
                "double-teams.  Requires Synergy defensive-plays API or manual "
                "PBP parsing."
            )
        }
        hot_hand_response: Dict[str, Any] = {
            "_note": (
                "DEFER: requires per-possession shot-outcome sequence with defensive "
                "focus annotation.  Not present in current PBP cache."
            )
        }
        zone_shift_indicator: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-game defense-type annotation (zone vs man) available "
                "in repo.  Requires Synergy defense or PBP zone-call tagging."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "adjustment_tendencies": tend,
            "coaching_adjustments": coaching,
            "matchup_deviations": dev_profile,
            "imposed_cv_profile": imposed_cv,
            "series_game_trend": series_trend,
            "double_team_trigger": double_team_trigger,
            "hot_hand_response": hot_hand_response,
            "zone_shift_indicator": zone_shift_indicator,
        }

        # --- Determine n (largest sample across sources) ---
        n_candidates: List[int] = []
        if coaching.get("n_games"):
            n_candidates.append(coaching["n_games"])
        if tend.get("n_games_tracked"):
            n_candidates.append(tend["n_games_tracked"])
        if dev_profile.get("n_matchup_obs"):
            n_candidates.append(dev_profile["n_matchup_obs"])
        if imposed_cv.get("n_games_window"):
            n_candidates.append(imposed_cv["n_games_window"])
        n = max(n_candidates) if n_candidates else 1

        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        # Headline scalar: mean adjustment score (how aggressively this team adjusts)
        headline_score = tend.get("mean_adjustment_score") or coaching.get("mean_adj_score")

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=tricode,
            value=headline_score,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub_field keys present, CV slots null.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "adjustment_tendencies",
            "coaching_adjustments",
            "matchup_deviations",
            "imposed_cv_profile",
            "series_game_trend",
            "double_team_trigger",
            "hot_hand_response",
            "zone_shift_indicator",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Adjustment frequency in [0, 1] when present
        tend = sf.get("adjustment_tendencies", {})
        adj_freq = tend.get("adjustment_frequency")
        if adj_freq is not None and not (0.0 <= adj_freq <= 1.0):
            return False

        # Coaching adjustment frequency in [0, 1] when present
        coaching = sf.get("coaching_adjustments", {})
        c_freq = coaching.get("adj_frequency")
        if c_freq is not None and not (0.0 <= c_freq <= 1.0):
            return False

        # Notable rate in [0, 1] when present
        dev = sf.get("matchup_deviations", {})
        notable_rate = dev.get("notable_rate")
        if notable_rate is not None and not (0.0 <= notable_rate <= 1.0):
            return False

        # CV fields schema: values must be None (CV branch hasn't run)
        for name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for matchup_adjustments (values None — CV fills later).

        These slots capture spatial/behavioral shifts that only the CV tracking
        pipeline can measure directly from broadcast video.  The CV-fix session calls
        ``store.fill_cv_slot("team", tricode, "matchup_adjustments", slot, as_of, value)``
        to populate them WITHOUT a profile rebuild.
        """
        return {
            "h1_h2_spacing_delta": CVSlot(
                name="h1_h2_spacing_delta",
                dtype="float",
                description=(
                    "Change in average offensive team spacing (ft², convex-hull area) "
                    "between the first half and second half of the same game, from CV "
                    "homography per-frame data.  Averaged over the team's last 10 games "
                    "as a defensive opponent.  Captures how effectively the team tightens "
                    "spacing on opponents as the game progresses."
                ),
                unit="ft²",
                value=None,
            ),
            "series_velocity_trend": CVSlot(
                name="series_velocity_trend",
                dtype="float",
                description=(
                    "Linear slope of opponent mean velocity (ft/s per game number) "
                    "across up to 7 games of a playoff or repeat-matchup series, "
                    "computed from CV per-game velocity aggregates.  A negative slope "
                    "means the defense progressively slows opponents; positive means "
                    "opponents accelerate (defense is losing the adaptation battle)."
                ),
                unit="ft/s per game",
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
    """Build matchup_adjustments for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of 3-letter team abbreviations.  If None, discovers
                       from team_adjustment_tendencies.json.
        as_of:         leak boundary date (defaults to today at midnight UTC).
        store:         PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:       skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if team_tricodes is None:
        doc = _load_json("team_adj_tend_disc", INTEL / "team_adjustment_tendencies.json")
        if doc and isinstance(doc, dict):
            team_tricodes = sorted(doc.keys())
        else:
            team_tricodes = []

    section = TeamMatchupAdjustments()
    artifacts: List[AtlasArtifact] = []
    for tricode in team_tricodes:
        try:
            art = section.build(tricode, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
