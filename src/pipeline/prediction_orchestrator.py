"""
prediction_orchestrator.py — Runs all models in layer-dependency order.

Each layer's outputs inject into the next layer as additional features.
Missing models are skipped (logged as warnings). CV features only inject if
CV data exists for this game.

Public API
----------
    PredictionOrchestrator()
    orchestrator.predict_player(game_id, player_id, date) -> PlayerPrediction
    orchestrator.predict_game(game_id, date)              -> GamePrediction
    orchestrator.predict_today()                          -> list[PlayerPrediction]
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PlayerPrediction:
    player_id: int
    player_name: str
    game_id: str
    date: str
    team: str = ""
    opp_team: str = ""

    # Projections per stat
    proj_pts: float = 0.0
    proj_reb: float = 0.0
    proj_ast: float = 0.0
    proj_fg3m: float = 0.0
    proj_stl: float = 0.0
    proj_blk: float = 0.0
    proj_tov: float = 0.0
    proj_min: float = 0.0

    # Availability
    dnp_prob: float = 0.0
    load_risk: float = 0.0

    # Context multipliers
    home_boost: dict = field(default_factory=dict)
    matchup_adj: float = 1.0
    usage_adj: float = 1.0
    b2b_mult: float = 1.0

    # Betting context
    book_lines: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)   # {stat: edge_pct}

    # Meta
    model_layers_run: list = field(default_factory=list)
    confidence: str = "low"
    has_cv_data: bool = False
    features: dict = field(default_factory=dict)


@dataclass
class GamePrediction:
    game_id: str
    date: str
    home_team: str
    away_team: str
    home_win_prob: float = 0.5
    predicted_total: float = 220.0
    predicted_spread: float = 0.0
    blowout_prob: float = 0.1
    pace: float = 100.0
    ot_prob: float = 0.05
    player_predictions: list[PlayerPrediction] = field(default_factory=list)
    features: dict = field(default_factory=dict)


@dataclass
class BetEdge:
    player_id: str
    player_name: str
    stat: str
    direction: str        # 'over' / 'under'
    line: float
    projection: float
    ev: float
    kelly_fraction: float
    confidence: str       # 'high' / 'medium' / 'low'
    model_agreement: int
    game_id: str = ""
    date: str = ""


# ── Orchestrator ──────────────────────────────────────────────────────────────

class PredictionOrchestrator:
    """
    Runs all prediction layers in order. Layer N outputs become features for Layer N+1.
    Missing models are skipped gracefully — system degrades, not crashes.
    """

    # Juice thresholds for edge detection (American odds -110 standard)
    _JUICE = 0.0909   # vig on -110 line
    _MIN_EDGE_PCT = 0.03   # minimum edge to flag

    def __init__(self, season: str = "2024-25") -> None:
        self.season = season
        from src.pipeline.model_registry import get_registry
        self.registry = get_registry()
        log.info("PredictionOrchestrator ready — %s", self.registry)

    # ── Layer runners ─────────────────────────────────────────────────────────

    def _run_layer(self, layer_num: int, features: dict) -> dict:
        """Execute a single layer and return output features."""
        outputs: dict = {}
        try:
            method = getattr(self, f"_layer_{layer_num}", None)
            if method:
                outputs = method(features) or {}
        except Exception as e:
            log.warning("Layer %d failed: %s", layer_num, e)
        return outputs

    def _safe_model(self, model_id: str, default=None):
        """Load model safely — returns default if not available."""
        try:
            return self.registry.get(model_id)
        except Exception:
            return default

    # ── Layer 1 — Availability ────────────────────────────────────────────────

    def _layer_1(self, features: dict) -> dict:
        out: dict = {}
        player_id = features.get("player_id", 0)
        player_name = features.get("player_name", "")
        season = features.get("season", self.season)

        # M01 DNP prob
        try:
            from src.prediction.dnp_predictor import predict_dnp
            result = predict_dnp(str(player_id), season=season)
            out["dnp_prob"] = float(result.get("dnp_prob", 0.05) if isinstance(result, dict) else 0.05)
        except Exception:
            out["dnp_prob"] = features.get("dnp_prob", 0.05)

        # M02 Load management
        try:
            from src.prediction.load_management import predict_load
            lm = predict_load(player_name)
            if isinstance(lm, dict):
                out["load_risk"] = float(lm.get("load_risk", 0.0))
                out["min_reduction_load"] = float(lm.get("min_reduction", 0.0))
        except Exception:
            out.setdefault("load_risk", 0.0)

        # M03 Injury return curve
        try:
            from src.prediction.injury_return import predict_return
            ir = predict_return(player_name)
            if isinstance(ir, dict):
                out["injury_performance_discount"] = float(ir.get("performance_discount", 1.0))
        except Exception:
            out.setdefault("injury_performance_discount", 1.0)

        # M05 Foul trouble
        try:
            from src.prediction.foul_trouble_predictor import predict_foul_trouble
            ft = predict_foul_trouble(player_id, features)
            if isinstance(ft, dict):
                out["foul_out_prob"] = float(ft.get("foul_out_prob", 0.05))
                out["min_reduction_foul"] = float(ft.get("min_reduction", 0.0))
        except Exception:
            out.setdefault("foul_out_prob", 0.05)

        # M06 Garbage time
        try:
            from src.prediction.garbage_time_detector import predict_garbage_time
            gt = predict_garbage_time(features)
            if isinstance(gt, dict):
                out["garbage_time_min_lost"] = float(gt.get("garbage_time_min_lost", 0.0))
                out["garbage_time_prob"] = float(gt.get("garbage_time_prob", 0.1))
        except Exception:
            out.setdefault("garbage_time_min_lost", 0.0)

        # M07 Minutes floor
        try:
            from src.prediction.minutes_floor_model import predict_minutes
            mf = predict_minutes(player_id, {**features, **out})
            if isinstance(mf, dict):
                out["proj_min"] = float(mf.get("proj_min", features.get("season_avg_min", 24.0)))
        except Exception:
            out["proj_min"] = float(features.get("min_l5", features.get("season_avg_min", 24.0)) or 24.0)

        # M08 Beneficiary cascade (injected at game level, used here if available)
        out.setdefault("min_boost_from_star_dnp", 0.0)

        return out

    # ── Layer 2 — Game Context ────────────────────────────────────────────────

    def _layer_2(self, features: dict) -> dict:
        out: dict = {}
        game_id  = features.get("game_id", "")
        home     = features.get("home_team", "")
        away     = features.get("away_team", "")
        date     = features.get("date", "")
        season   = features.get("season", self.season)

        # M09/M11/M12/M14 Game prediction models
        try:
            from src.prediction.game_prediction import predict_game
            gp = predict_game(home, away, season=season, game_date=date)
            if isinstance(gp, dict):
                out["home_win_prob"]   = float(gp.get("home_win_prob", 0.5))
                out["predicted_total"] = float(gp.get("total_est", 220.0))
                out["predicted_spread"] = float(gp.get("spread_est", 0.0))
                out["blowout_prob"]    = float(gp.get("blowout_prob", 0.1))
                out["expected_pace"]   = float(gp.get("pace", 100.0))
        except Exception:
            out.setdefault("predicted_total", 220.0)
            out.setdefault("blowout_prob", 0.1)
            out.setdefault("expected_pace", 100.0)

        # M15 Overtime probability
        try:
            from src.prediction.overtime_probability import predict_ot_prob
            ot = predict_ot_prob(out.get("predicted_spread", 0.0))
            out["ot_prob"] = float(ot)
        except Exception:
            out.setdefault("ot_prob", 0.05)

        # M16 Referee tendency
        try:
            from src.data.referee_model import get_referee_adjustments
            ref_adj = get_referee_adjustments(game_id=game_id, date=date)
            if isinstance(ref_adj, dict):
                out["ref_pace_adj"]     = float(ref_adj.get("pace_adj", 1.0))
                out["ref_foul_adj"]     = float(ref_adj.get("foul_rate_adj", 1.0))
        except Exception:
            out.setdefault("ref_pace_adj", 1.0)
            out.setdefault("ref_foul_adj", 1.0)

        # M17 B2B discount
        try:
            from src.prediction.back_to_back_model import predict_b2b_mult
            b2b_mult = predict_b2b_mult(features)
            if isinstance(b2b_mult, dict):
                out["b2b_pts_mult"] = float(b2b_mult.get("pts", 1.0))
                out["b2b_min_mult"] = float(b2b_mult.get("min", 1.0))
            else:
                out.setdefault("b2b_pts_mult", 1.0 if not features.get("is_b2b") else 0.96)
        except Exception:
            out.setdefault("b2b_pts_mult", 1.0)

        # M18 Travel impact
        try:
            from src.prediction.travel_impact_model import predict_travel_adj
            ta = predict_travel_adj(features)
            out["travel_fatigue_adj"] = float(ta) if not isinstance(ta, dict) else float(ta.get("adj", 1.0))
        except Exception:
            out.setdefault("travel_fatigue_adj", 1.0)

        # M19 Altitude
        try:
            from src.prediction.altitude_model import predict_altitude_adj
            aa = predict_altitude_adj(features)
            out["altitude_adj"] = float(aa) if not isinstance(aa, dict) else float(aa.get("adj", 1.0))
        except Exception:
            out.setdefault("altitude_adj", 1.0)

        return out

    # ── Layer 3 — Player Baselines ────────────────────────────────────────────

    def _layer_3(self, features: dict) -> dict:
        out: dict = {}
        player_name = features.get("player_name", "")
        opp_team    = features.get("opp_team", features.get("away_team", ""))
        season      = features.get("season", self.season)

        # M20-M26 Props baseline
        try:
            from src.prediction.player_props import predict_props
            props = predict_props(player_name, opp_team, season=season)
            if isinstance(props, dict):
                for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                    out[f"proj_{stat}_base"] = float(props.get(stat, 0) or 0)
        except Exception:
            for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                out[f"proj_{stat}_base"] = float(features.get(f"{stat}_l10", 0) or 0)

        # M27 Usage rate
        try:
            from src.prediction.usage_rate_model import predict_usage
            usg = predict_usage(features)
            out["proj_usg_pct"] = float(usg.get("proj_usg_pct", 0.2) if isinstance(usg, dict) else usg)
        except Exception:
            out["proj_usg_pct"] = float(features.get("bbref_usg_pct", 0.2) or 0.2)

        # M28 True shooting
        try:
            from src.prediction.true_shooting_model import predict_ts
            ts = predict_ts(features)
            out["proj_ts_pct"] = float(ts.get("proj_ts_pct", 0.55) if isinstance(ts, dict) else ts)
        except Exception:
            out["proj_ts_pct"] = float(features.get("bbref_ts_pct", 0.55) or 0.55)

        # M29 Plus/minus
        try:
            from src.prediction.plus_minus_predictor import predict_pm
            pm = predict_pm(features)
            out["proj_plus_minus"] = float(pm.get("proj_pm", 0.0) if isinstance(pm, dict) else pm)
        except Exception:
            out["proj_plus_minus"] = float(features.get("on_off_diff", 0.0) or 0.0)

        # M30 Age curve discount
        try:
            from src.prediction.age_curve_model import predict_age_discount
            ad = predict_age_discount(features)
            out["age_discount"] = float(ad.get("discount", 1.0) if isinstance(ad, dict) else ad)
        except Exception:
            out["age_discount"] = 1.0

        # M32 Home/away split
        try:
            from src.prediction.home_away_model import predict_home_away
            ha = predict_home_away(features)
            if isinstance(ha, dict):
                out["home_pts_boost"] = float(ha.get("pts", 0.0))
                out["home_reb_boost"] = float(ha.get("reb", 0.0))
                out["home_ast_boost"] = float(ha.get("ast", 0.0))
        except Exception:
            out.setdefault("home_pts_boost", 0.0)

        # M33 Rest day multiplier
        try:
            from src.prediction.rest_day_model import predict_rest_mult
            rm = predict_rest_mult(features)
            out["rest_mult"] = float(rm.get("mult", 1.0) if isinstance(rm, dict) else rm)
        except Exception:
            out["rest_mult"] = 1.0

        return out

    # ── Layer 4 — Matchup ─────────────────────────────────────────────────────

    def _layer_4(self, features: dict) -> dict:
        out: dict = {}
        player_id = features.get("player_id", 0)
        opp_team  = features.get("opp_team", "")
        season    = features.get("season", self.season)

        # M35 Matchup model
        try:
            from src.prediction.matchup_model import predict_matchup
            ma = predict_matchup(player_id, opp_team, season=season)
            if isinstance(ma, dict):
                out["matchup_pts_adj"] = float(ma.get("pts_adj", 1.0))
        except Exception:
            out.setdefault("matchup_pts_adj", 1.0)

        # M39 Contested shot predictor
        try:
            from src.prediction.contested_shot_predictor import predict_contested_shot
            cs = predict_contested_shot(features)
            out["expected_contested_pct"] = float(cs.get("contested_pct", 0.4) if isinstance(cs, dict) else cs)
        except Exception:
            out["expected_contested_pct"] = float(features.get("contested_pct", 0.4) or 0.4)

        # M40 Defensive scheme
        try:
            from src.tracking.defensive_scheme_classifier import classify_defensive_scheme
            scheme = classify_defensive_scheme(opp_team, season)
            out["opp_def_scheme"] = scheme or "MAN"
        except Exception:
            out["opp_def_scheme"] = "MAN"

        # M47 Shot clock pressure
        try:
            from src.prediction.shot_clock_pressure_model import predict_pressure_discount
            pd = predict_pressure_discount(features)
            out["pressure_fg_discount"] = float(pd.get("discount", 1.0) if isinstance(pd, dict) else pd)
        except Exception:
            out["pressure_fg_discount"] = 1.0

        # M48 Shot type model
        try:
            from src.prediction.shot_type_model import predict_shot_type_adj
            sta = predict_shot_type_adj(features)
            if isinstance(sta, dict):
                out["shot_type_fg_adj"] = float(sta.get("fg_adj", 1.0))
        except Exception:
            out["shot_type_fg_adj"] = 1.0

        # M49 Contested rate
        try:
            from src.prediction.contested_rate_model import predict_contested_rate
            cr = predict_contested_rate(features)
            out["contested_rate_tonight"] = float(cr.get("rate", 0.4) if isinstance(cr, dict) else cr)
        except Exception:
            out["contested_rate_tonight"] = float(features.get("contested_pct", 0.4) or 0.4)

        return out

    # ── Layer 5 — Shot Quality ────────────────────────────────────────────────

    def _layer_5(self, features: dict) -> dict:
        out: dict = {}
        try:
            from src.analytics.shot_quality import ShotQualityScorer
            scorer = ShotQualityScorer()
            sq = scorer.score(features)
            if isinstance(sq, dict):
                out["shot_quality_score"] = float(sq.get("score", 0.5))
        except Exception:
            out["shot_quality_score"] = 0.5
        return out

    # ── Layer 6 — CV Spatial (skip if no CV data) ─────────────────────────────

    def _layer_6(self, features: dict) -> dict:
        if not features.get("has_cv_data", False):
            return {}
        out: dict = {}
        # Placeholder — CV features inject here when available
        return out

    # ── Layer 7 — Lineup/Team ─────────────────────────────────────────────────

    def _layer_7(self, features: dict) -> dict:
        out: dict = {}

        # M68 Rotation predictor
        try:
            from src.prediction.rotation_predictor import predict_rotation
            rp = predict_rotation(features)
            if isinstance(rp, dict):
                out["rotation_min_est"] = float(rp.get("expected_min", features.get("proj_min", 24.0)))
        except Exception:
            out["rotation_min_est"] = float(features.get("proj_min", 24.0))

        # M69 Substitution timing
        try:
            from src.prediction.substitution_timing_model import predict_sub_timing
            st = predict_sub_timing(features)
            if isinstance(st, dict):
                out["q4_min_pct"] = float(st.get("q4_min_pct", 0.25))
        except Exception:
            out.setdefault("q4_min_pct", 0.25)

        # M72 Clutch lineup
        try:
            from src.prediction.clutch_lineup_model import predict_clutch_prob
            cp = predict_clutch_prob(features)
            out["clutch_lineup_prob"] = float(cp.get("prob", 0.5) if isinstance(cp, dict) else cp)
        except Exception:
            out["clutch_lineup_prob"] = 0.5

        return out

    # ── Layer 8 — Normalise to team total ────────────────────────────────────

    def _normalise_to_team_total(self, player_pred: PlayerPrediction, team_total: float) -> None:
        """M70: Apply normalisation factor in-place after team total is known."""
        # Normalisation happens at game level in predict_game — placeholder here
        pass

    # ── Layer 9 — Edge Detection ──────────────────────────────────────────────

    def _layer_9(self, features: dict, projections: Optional[dict] = None) -> dict:
        """Edge vs book lines; `projections` defaults to merged layer outputs in `features`."""
        proj_src = projections if projections is not None else features
        out: dict = {}
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            proj  = proj_src.get(f"proj_{stat}", 0.0)
            line  = features.get(f"book_line_{stat}", float("nan"))
            if proj and not (isinstance(line, float) and (line != line)):  # NaN check
                edge = (proj - line) / max(line, 1.0)
                out[f"edge_{stat}"] = float(edge)
        return out

    # ── Full player prediction pipeline ──────────────────────────────────────

    def predict_player(
        self,
        game_id: str,
        player_id: int,
        date: str,
        team_abbrev: str = "",
        opp_team: str = "",
        game_features: Optional[dict] = None,
    ) -> PlayerPrediction:
        """
        Run full L1→L9 prediction cascade for a single player.
        Returns PlayerPrediction. Never raises.
        """
        from src.pipeline.feature_assembler import assemble_features

        # Base feature assembly
        features = assemble_features(
            game_id=game_id,
            player_id=player_id,
            date=date,
            season=self.season,
            team_abbrev=team_abbrev,
            opp_team=opp_team,
        )
        features["home_team"]  = team_abbrev
        features["away_team"]  = opp_team
        features["opp_team"]   = opp_team
        features["has_cv_data"] = False

        # Inject game-level features if provided
        if game_features:
            features.update(game_features)

        layers_run: list[str] = []

        # Run layers in order, each injecting outputs into features
        for layer_num in range(1, 10):
            try:
                layer_out = self._run_layer(layer_num, features)
                features.update(layer_out)
                if layer_out:
                    layers_run.append(f"L{layer_num}")
            except Exception as e:
                log.warning("predict_player L%d error: %s", layer_num, e)

        # Compose final projections
        def _stat(key: str, fallback: float = 0.0) -> float:
            v = features.get(key, fallback)
            return float(v) if v == v else fallback  # NaN guard

        # Apply multipliers to base projections
        pts_base  = _stat("proj_pts_base",  _stat("pts_l10"))
        reb_base  = _stat("proj_reb_base",  _stat("reb_l10"))
        ast_base  = _stat("proj_ast_base",  _stat("ast_l10"))
        fg3m_base = _stat("proj_fg3m_base", _stat("fg3m_l10"))

        # Combined multiplier
        b2b_mult  = _stat("b2b_pts_mult", 1.0)
        rest_mult = _stat("rest_mult", 1.0)
        age_disc  = _stat("age_discount", 1.0)
        travel_adj = _stat("travel_fatigue_adj", 1.0)
        matchup_adj = _stat("matchup_pts_adj", 1.0)
        injury_disc = _stat("injury_performance_discount", 1.0)

        combined_mult = b2b_mult * rest_mult * age_disc * travel_adj * injury_disc

        dnp_prob = _stat("dnp_prob", 0.05)
        survival = max(0.0, 1.0 - dnp_prob)

        proj = PlayerPrediction(
            player_id=player_id,
            player_name=features.get("player_name", ""),
            game_id=game_id,
            date=date,
            team=team_abbrev,
            opp_team=opp_team,
            proj_pts   = pts_base  * combined_mult * matchup_adj * survival,
            proj_reb   = reb_base  * combined_mult * survival,
            proj_ast   = ast_base  * combined_mult * survival,
            proj_fg3m  = fg3m_base * combined_mult * survival,
            proj_stl   = _stat("proj_stl_base",  _stat("stl_l10")) * combined_mult * survival,
            proj_blk   = _stat("proj_blk_base",  _stat("blk_l10")) * combined_mult * survival,
            proj_tov   = _stat("proj_tov_base",  _stat("tov_l10")) * combined_mult * survival,
            proj_min   = _stat("proj_min", 24.0) * _stat("b2b_min_mult", 1.0),
            dnp_prob   = dnp_prob,
            load_risk  = _stat("load_risk", 0.0),
            matchup_adj = matchup_adj,
            usage_adj   = _stat("proj_usg_pct", 0.2) / max(features.get("bbref_usg_pct", 0.2) or 0.2, 0.01),
            b2b_mult    = b2b_mult,
            book_lines  = {s: features.get(f"book_line_{s}", float("nan"))
                          for s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")},
            model_layers_run = layers_run,
            confidence  = self._confidence(len(layers_run), features),
            has_cv_data = bool(features.get("has_cv_data", False)),
            features    = {k: v for k, v in features.items() if not k.startswith("_")},
        )

        # Compute edges vs book lines
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk"):
            proj_val = getattr(proj, f"proj_{stat}", 0.0)
            line_val = proj.book_lines.get(stat, float("nan"))
            if proj_val and not (isinstance(line_val, float) and line_val != line_val):
                edge = (proj_val - line_val) / max(abs(line_val), 0.5)
                proj.edges[stat] = round(edge, 3)

        return proj

    def _confidence(self, layers_run: int, features: dict) -> str:
        if layers_run >= 7:
            return "high"
        elif layers_run >= 4:
            return "medium"
        return "low"

    # ── Game-level prediction ─────────────────────────────────────────────────

    def predict_game(
        self,
        game_id: str,
        date: str,
        home_team: str = "",
        away_team: str = "",
    ) -> GamePrediction:
        """Run full prediction for a single game including all players."""
        from src.prediction.game_prediction import predict_game as _pg
        try:
            gp = _pg(home_team, away_team, season=self.season, game_date=date)
        except Exception:
            gp = {}

        game_features = {
            "home_team":       home_team,
            "away_team":       away_team,
            "game_id":         game_id,
            "date":            date,
            "predicted_total": gp.get("total_est", 220.0),
            "home_win_prob":   gp.get("home_win_prob", 0.5),
            "predicted_spread": gp.get("spread_est", 0.0),
            "blowout_prob":    gp.get("blowout_prob", 0.1),
            "expected_pace":   gp.get("pace", 100.0),
        }

        # Get roster for this game
        player_ids = self._get_roster_player_ids(home_team, away_team)

        player_preds: list[PlayerPrediction] = []
        for pid, team, opp in player_ids:
            try:
                pred = self.predict_player(
                    game_id=game_id, player_id=pid, date=date,
                    team_abbrev=team, opp_team=opp,
                    game_features=game_features,
                )
                player_preds.append(pred)
            except Exception as e:
                log.warning("predict_player failed pid=%d: %s", pid, e)

        # M70: Normalise team totals
        if player_preds:
            predicted_total = game_features.get("predicted_total", 220.0)
            player_preds = self._apply_team_normalizer(player_preds, home_team, away_team, predicted_total)

        return GamePrediction(
            game_id=game_id, date=date,
            home_team=home_team, away_team=away_team,
            home_win_prob=float(gp.get("home_win_prob", 0.5)),
            predicted_total=float(gp.get("total_est", 220.0)),
            predicted_spread=float(gp.get("spread_est", 0.0)),
            blowout_prob=float(gp.get("blowout_prob", 0.1)),
            pace=float(gp.get("pace", 100.0)),
            player_predictions=player_preds,
            features=game_features,
        )

    def _apply_team_normalizer(
        self,
        preds: list[PlayerPrediction],
        home_team: str,
        away_team: str,
        predicted_total: float,
    ) -> list[PlayerPrediction]:
        """M70: Scale player proj_pts so each team sums to total/2 ± spread."""
        try:
            from src.prediction.team_total_normalizer import normalise_team_totals
            return normalise_team_totals(preds, home_team, away_team, predicted_total)
        except Exception as e:
            log.debug("team_total_normalizer skipped: %s", e)
            return preds

    def _get_roster_player_ids(
        self, home_team: str, away_team: str
    ) -> list[tuple[int, str, str]]:
        """Return [(player_id, team, opp_team)] for today's game."""
        import glob
        from src.pipeline.feature_assembler import _norm

        result: list[tuple[int, str, str]] = []
        seen: set[int] = set()

        # Find player IDs from gamelog files
        gamelog_files = glob.glob(
            os.path.join(PROJECT_DIR, "data", "nba", f"gamelog_full_*_{self.season}.json")
        )
        # We need to identify which players are on each team
        # Use the last game's matchup field to identify team
        for fpath in gamelog_files[:200]:  # cap for performance
            try:
                with open(fpath) as f:
                    logs = json.load(f)
                if not isinstance(logs, list) or not logs:
                    continue
                pid_str = os.path.basename(fpath).split("_")[2]
                pid = int(pid_str)
                if pid in seen:
                    continue
                last = sorted(logs, key=lambda g: g.get("game_date", ""))[-1]
                matchup = last.get("matchup", "")
                # matchup format: "GSW vs. BOS" or "GSW @ BOS"
                teams_in = {home_team, away_team}
                if any(t in matchup for t in teams_in):
                    # Determine which team this player is on
                    if home_team and home_team in matchup:
                        team, opp = home_team, away_team
                    else:
                        team, opp = away_team, home_team
                    result.append((pid, team, opp))
                    seen.add(pid)
            except Exception:
                continue

        return result

    # ── predict_today ─────────────────────────────────────────────────────────

    def predict_today(self) -> list[PlayerPrediction]:
        """
        Full today pipeline:
        1. Refresh injury reports + current props (cached 15-30 min)
        2. Fetch today's games from NBA schedule
        3. For each game → each player → full cascade
        4. Return player predictions sorted by max abs edge
        """
        from datetime import date as _date
        today = _date.today().isoformat()

        # Step 1: Refresh injury reports (non-blocking — logs warnings on fail)
        try:
            from src.data.injury_monitor import InjuryMonitor
            inj = InjuryMonitor()
            inj.refresh()
            self._injury_monitor = inj
            log.info("predict_today: injury reports refreshed")
        except Exception as e:
            log.debug("Injury refresh skipped: %s", e)
            self._injury_monitor = None

        # Step 2: Refresh current props for book lines
        try:
            from src.data.props_scraper import get_current_props
            self._current_props = get_current_props()
            log.info("predict_today: props fetched, %d entries", len(self._current_props or {}))
        except Exception as e:
            log.warning("Props scraper failed (%s) — trying local cache", e)
            self._current_props = self._load_cached_props(today)

        # Step 3: Fetch today's schedule
        games = self._fetch_today_games()
        if not games:
            log.warning("predict_today: no games found for %s", today)
            return []

        all_preds: list[PlayerPrediction] = []
        for game in games:
            gid   = game.get("game_id", "")
            home  = game.get("home_team", "")
            away  = game.get("away_team", "")
            try:
                gp = self.predict_game(gid, today, home, away)
                # Inject live props book lines into each player prediction
                self._inject_book_lines(gp.player_predictions)
                all_preds.extend(gp.player_predictions)
            except Exception as e:
                log.warning("predict_today game %s failed: %s", gid, e)

        # Sort by highest abs edge on any stat
        def _max_edge(p: PlayerPrediction) -> float:
            if not p.edges:
                return 0.0
            return max(abs(v) for v in p.edges.values())

        all_preds.sort(key=_max_edge, reverse=True)
        return all_preds

    def get_today_edges(self, min_ev: float = 0.03) -> list:
        """
        Full today pipeline returning ranked BetEdge list.
        Calls predict_today() then EdgeDetector.find_edges().

        Returns:
            list[BetEdge] sorted by EV descending.
        """
        preds = self.predict_today()
        if not preds:
            return []
        try:
            from src.analytics.edge_detector import EdgeDetector
            detector = EdgeDetector(season=self.season)
            edges = detector.find_edges(preds, min_ev=min_ev)
            log.info("get_today_edges: %d edges found (min_ev=%.2f)", len(edges), min_ev)
            return edges
        except Exception as e:
            log.warning("EdgeDetector failed: %s", e)
            return []

    def _inject_book_lines(self, preds: list[PlayerPrediction]) -> None:
        """Inject live prop book lines into PlayerPrediction.book_lines."""
        if not self._current_props:
            return
        for pred in preds:
            name_key = (pred.player_name or "").lower().replace(" ", "_")
            player_props = self._current_props.get(name_key, {})
            for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                line = player_props.get(stat)
                if line is not None:
                    pred.book_lines[stat] = float(line)
                    # Recompute edge
                    proj = getattr(pred, f"proj_{stat}", 0.0)
                    if proj and float(line) > 0:
                        pred.edges[stat] = round(
                            (proj - float(line)) / max(abs(float(line)), 0.5), 3
                        )

    def _load_cached_props(self, today: str) -> dict:
        """Fallback: load props from today's local JSON if scraper failed."""
        props_path = os.path.join(PROJECT_DIR, "data", "props", f"props_{today}.json")
        if os.path.exists(props_path):
            try:
                with open(props_path) as f:
                    data = json.load(f)
                log.info("_load_cached_props: loaded %d entries from %s", len(data), props_path)
                return data
            except Exception as e:
                log.warning("Could not load cached props %s: %s", props_path, e)
        return {}

    def predict_game_slate(
        self,
        game_list: list[dict],
        season: str = "2024-25",
    ) -> list[dict]:
        """
        Batch predict for a full game slate and return team-total-normalized results.

        Args:
            game_list: [{"home_team": "LAL", "away_team": "GSW",
                         "players": [...player_names], "game_id": "...", "date": "..."}]
            season:    NBA season string, e.g. "2024-25"

        Returns:
            Flat list of player prediction dicts with keys:
            player, team, opp_team, game_id, pts, reb, ast, fg3m, stl, blk, tov,
            proj_pts, proj_min, dnp_prob, confidence.
            Each game batch is team-total-normalized before inclusion.
        """
        from types import SimpleNamespace
        from src.prediction.player_props import predict_props, _get_player_season_avgs
        from src.prediction.team_total_normalizer import normalise_team_totals

        _season = season or self.season
        all_results: list[dict] = []

        for game in game_list:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            gid  = game.get("game_id", "")
            date = game.get("date", "")
            players = game.get("players", [])

            # Predict DNP prob for filtering
            from src.prediction.dnp_predictor import predict_dnp as _predict_dnp

            game_preds: list[SimpleNamespace] = []
            pred_dicts: list[dict] = []

            for pname in players:
                try:
                    # Skip high-probability DNPs
                    _avgs = _get_player_season_avgs(pname, _season)
                    if _avgs is None:
                        continue
                    _pid = _avgs.get("player_id", 0)
                    _pteam = _avgs.get("team", "")
                    _opp = away if _pteam == home else home

                    try:
                        _dnp = _predict_dnp(str(_pid), season=_season)
                        if float(_dnp.get("dnp_prob", 0) if isinstance(_dnp, dict) else 0) > 0.70:
                            log.debug("Skipping %s: dnp_prob > 0.70", pname)
                            continue
                    except Exception:
                        pass

                    props = predict_props(pname, _opp, season=_season)
                    if not props:
                        continue

                    _proj_min = float(props.get("min", _avgs.get("min", 24.0)) or 24.0)
                    _dnp_prob = float(props.get("dnp_prob", 0.05))

                    # Build SimpleNamespace for normaliser (needs proj_pts, proj_min, team)
                    ns = SimpleNamespace(
                        player_name=pname,
                        player_id=_pid,
                        team=_pteam,
                        opp_team=_opp,
                        game_id=gid,
                        date=date,
                        proj_pts=float(props.get("pts", 0) or 0),
                        proj_reb=float(props.get("reb", 0) or 0),
                        proj_ast=float(props.get("ast", 0) or 0),
                        proj_fg3m=float(props.get("fg3m", 0) or 0),
                        proj_stl=float(props.get("stl", 0) or 0),
                        proj_blk=float(props.get("blk", 0) or 0),
                        proj_tov=float(props.get("tov", 0) or 0),
                        proj_min=_proj_min,
                        dnp_prob=_dnp_prob,
                        confidence=props.get("confidence", "low"),
                    )
                    game_preds.append(ns)
                    pred_dicts.append(props)
                except Exception as e:
                    log.warning("predict_game_slate: error for player %s: %s", pname, e)
                    continue

            # Apply team-total normalizer
            if game_preds:
                # Fetch predicted game total from game models if possible
                predicted_total = 220.0
                try:
                    from src.prediction.game_models import predict as _gm
                    _gm_out = _gm(home, away, _season)
                    predicted_total = float(_gm_out.get("total_est", 220.0))
                except Exception:
                    pass

                try:
                    game_preds = normalise_team_totals(game_preds, home, away, predicted_total)
                except Exception as e:
                    log.debug("normalise_team_totals failed for %s vs %s: %s", home, away, e)

            # Convert back to dicts
            for ns in game_preds:
                all_results.append({
                    "player":     ns.player_name,
                    "player_id":  ns.player_id,
                    "team":       ns.team,
                    "opp_team":   ns.opp_team,
                    "game_id":    ns.game_id,
                    "date":       ns.date,
                    "pts":        round(ns.proj_pts,  1),
                    "reb":        round(ns.proj_reb,  1),
                    "ast":        round(ns.proj_ast,  1),
                    "fg3m":       round(ns.proj_fg3m, 1),
                    "stl":        round(ns.proj_stl,  1),
                    "blk":        round(ns.proj_blk,  1),
                    "tov":        round(ns.proj_tov,  1),
                    "proj_pts":   round(ns.proj_pts,  1),
                    "proj_min":   round(ns.proj_min,  1),
                    "dnp_prob":   round(ns.dnp_prob,  3),
                    "confidence": ns.confidence,
                })

        return all_results

    def _fetch_today_games(self) -> list[dict]:
        """Fetch today's games from NBA API schedule."""
        try:
            try:
                from nba_api.stats.endpoints import scoreboard as _sb_mod
                sb = _sb_mod.Scoreboard()
            except ImportError:
                from nba_api.stats.endpoints import scoreboardv2 as _sb_mod
                sb = _sb_mod.ScoreboardV2()
            games_df = sb.game_header.get_data_frame()
            result = []
            for _, row in games_df.iterrows():
                result.append({
                    "game_id":   str(row.get("GAME_ID", "")),
                    "home_team": str(row.get("HOME_TEAM_ABBREVIATION", "")),
                    "away_team": str(row.get("VISITOR_TEAM_ABBREVIATION", "")),
                })
            return result
        except Exception as e:
            log.warning("Could not fetch today's schedule: %s", e)
            return []
