"""possession_simulator.py — Possession-level Monte Carlo orchestrator (Phase 8).

10 000-simulation game engine chaining 7 sub-models:
  PlayTypeSelector → ShotSelector → xFGModel → TurnoverFoulModel →
  ReboundModel → FatigueModel → SubstitutionModel

Sub-model classes live in sim_models.py. Training helper: sim_models.train_play_type_selector.
"""

from __future__ import annotations

import bisect
import logging
import os
import warnings
from typing import Any, Optional

import numpy as np

from src.prediction.sim_models import (
    DEFAULT_ZONE_DATA, PLAY_TYPE_ZONE_DATA,
    ZONE_XFG, ZONE_PTS, XFG_FEATS,
    FatigueModel, PlayTypeSelector, SubstitutionModel,
)
from src.prediction.live_models import (
    FoulTroubleModel, GarbageTimePredictor, Q4UsageModel,
)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODEL_DIR   = os.path.join(_PROJECT_DIR, "data", "models")
_XFG_PATH    = os.path.join(_MODEL_DIR, "xfg_v1.pkl")

_PROP_STATS = ("pts", "reb", "ast", "stl", "blk", "tov", "fg3m")


def _load_cv_minutes(csv_path: str) -> dict[str, float]:
    """Load per-player tracked minutes from a tracking_data.csv file.

    Computes minutes as (max_timestamp - min_timestamp) per player_id.
    Falls back to empty dict on any error so callers use season avg instead.
    """
    import csv as _csv
    result: dict[str, float] = {}
    try:
        rows_by_pid: dict[str, list[float]] = {}
        with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
            for row in _csv.DictReader(f):
                pid = str(row.get("player_id", "")).strip()
                ts  = row.get("timestamp", "")
                if not pid or not ts:
                    continue
                try:
                    rows_by_pid.setdefault(pid, []).append(float(ts))
                except ValueError:
                    pass
        for pid, timestamps in rows_by_pid.items():
            if len(timestamps) >= 2:
                result[pid] = (max(timestamps) - min(timestamps)) / 60.0
    except Exception as e:
        logging.warning("_load_cv_minutes: failed to parse %s: %s", csv_path, e)
    return result


class PossessionSimulator:
    """Vectorized game simulator. Chains all Phase-8 sub-models per possession."""

    def __init__(self, cv_minutes_csv: Optional[str] = None) -> None:
        self._selector     = PlayTypeSelector()
        self._fatigue      = FatigueModel()
        self._sub_model    = SubstitutionModel()
        self._xfg_mdl      = None
        self._po_predict   = None
        self._po_cache: dict[tuple, dict] = {}
        self._usage_model  = None
        self._dnp_model    = None
        self._dnp_scaler   = None
        # Per-player CV minutes: {player_id_str: minutes_float}
        self._cv_minutes: dict[str, float] = {}
        if cv_minutes_csv is not None:
            self._cv_minutes = _load_cv_minutes(cv_minutes_csv)
        self._load_models()
        self._foul_mdl    = FoulTroubleModel()
        self._garbage_mdl = GarbageTimePredictor()
        self._q4_mdl      = Q4UsageModel()

    # ── model loading ─────────────────────────────────────────────────────────

    def _load_models(self) -> None:
        try:
            if os.path.exists(_XFG_PATH):
                from src.prediction.xfg_model import load as xfg_load
                self._xfg_mdl = xfg_load(_XFG_PATH)
        except Exception as e:
            logging.warning("PossessionSimulator: failed to load xfg_model: %s", e)
        try:
            from src.prediction.possession_outcome_model import predict_outcome
            self._po_predict = predict_outcome
        except Exception as e:
            logging.warning("PossessionSimulator: failed to load possession_outcome_model: %s", e)
        try:
            import pickle as _pkl
            with open(os.path.join(_MODEL_DIR, "usage_rate_model.pkl"), "rb") as f:
                self._usage_model = _pkl.load(f)["model"]
        except Exception as e:
            logging.warning("PossessionSimulator: failed to load usage_rate_model: %s", e)
        try:
            import pickle as _pkl
            with open(os.path.join(_MODEL_DIR, "dnp_model.pkl"), "rb") as f:
                warnings.filterwarnings("ignore", category=UserWarning)
                d = _pkl.load(f)
                self._dnp_model, self._dnp_scaler = d["model"], d["scaler"]
        except Exception as e:
            logging.warning("PossessionSimulator: failed to load dnp_model: %s", e)

    # ── sub-model helpers ─────────────────────────────────────────────────────

    def _shot_select(self, play_type: str, rng: np.random.Generator) -> str:
        zones, cum = PLAY_TYPE_ZONE_DATA.get(play_type, DEFAULT_ZONE_DATA)
        return zones[min(bisect.bisect(cum, float(rng.random())), len(zones) - 1)]

    def _xfg(self, zone: str, adj: float, rng: np.random.Generator) -> tuple[float, int]:
        """Return (xfg_prob, points_if_made)."""
        fallback = max(0.25, min(0.75, ZONE_XFG.get(zone, 0.45) * adj))
        pts      = ZONE_PTS.get(zone, 2)
        xfg_val  = fallback
        if self._xfg_mdl is not None:
            try:
                raw    = float(self._xfg_mdl.predict(dict(XFG_FEATS.get(zone, XFG_FEATS["mid_range"]))))
                xfg_val = max(0.25, min(0.75, raw * adj))
            except Exception:
                pass
        return xfg_val, pts

    def _tov_foul_probs(self, play_type: str, player_id: Optional[str]) -> tuple[float, float]:
        """Cached turnover / foul probabilities per (player, play_type)."""
        key = (player_id, play_type)
        if key not in self._po_cache:
            tov, fta = 0.13, 0.08
            if self._po_predict is not None:
                try:
                    res = self._po_predict(player_id, play_type, "other", "")
                    tov = float(res.get("tov_prob", 0.13))
                    fta = float(res.get("fta_prob", 0.08))
                except Exception:
                    pass
            self._po_cache[key] = (tov, fta)
        return self._po_cache[key]

    def _usage_weights(self, roster: list[str]) -> np.ndarray:
        n = len(roster)
        if n == 0:
            return np.array([])
        if self._usage_model is None:
            return np.ones(n) / n
        try:
            X     = np.zeros((n, 8), dtype=np.float32)
            preds = np.clip(self._usage_model.predict(X), 0.01, 1.0)
            return preds / preds.sum()
        except Exception:
            return np.ones(n) / n

    def _filter_dnp(self, roster: list[str]) -> list[str]:
        if not roster or self._dnp_model is None or self._dnp_scaler is None:
            return roster
        try:
            mean_feat = self._dnp_scaler.mean_.reshape(1, -1)
            X         = np.tile(mean_feat, (len(roster), 1))
            probs     = self._dnp_model.predict_proba(self._dnp_scaler.transform(X))[:, 1]
            active    = [p for p, pr in zip(roster, probs) if pr <= 0.5]
            return active if active else roster
        except Exception:
            return roster

    def _matchup_adj(self, stats_a: Optional[dict], stats_b: Optional[dict]) -> tuple[float, float]:
        a_off  = float((stats_a or {}).get("off_rtg", 110))
        a_def  = float((stats_a or {}).get("def_rtg", 110))
        b_off  = float((stats_b or {}).get("off_rtg", 110))
        b_def  = float((stats_b or {}).get("def_rtg", 110))
        return (a_off / 110) / (b_def / 110), (b_off / 110) / (a_def / 110)

    # ── single possession ─────────────────────────────────────────────────────

    def simulate_possession(self, game_state: dict, play_type: Optional[str] = None,
                            rng: Optional[np.random.Generator] = None) -> dict:
        if rng is None:
            rng = np.random.default_rng()
        if play_type is None:
            play_type = self._selector.sample(game_state)

        pid            = game_state.get("player_id")
        adj            = game_state.get("xfg_adj_factor", 1.0)
        fatigue_mult   = game_state.get("fatigue_mult", 1.0)
        effective_adj  = adj * fatigue_mult
        tov_p, fta_p   = self._tov_foul_probs(play_type, pid)

        r = float(rng.random())
        if r < tov_p:
            return {"play_type": play_type, "outcome": "turnover", "points": 0}
        if r < tov_p + fta_p:
            n_ft = 3 if play_type in ("catch_shoot", "spot_up", "pullup") else 2
            return {"play_type": play_type, "outcome": "foul",
                    "points": int((rng.random(n_ft) < 0.77).sum())}

        zone        = self._shot_select(play_type, rng)
        xfg_v, pts  = self._xfg(zone, effective_adj, rng)
        oreb        = game_state.get("oreb_rate", 0.27)

        if rng.random() < xfg_v:
            made_pts = pts + (1 if rng.random() < 0.04 and rng.random() < 0.77 else 0)  # and-1
            return {"play_type": play_type, "outcome": "shot", "shot_zone": zone,
                    "xfg": xfg_v, "made": True, "points": made_pts}

        # Miss — offensive rebound chance
        if rng.random() < oreb:
            zone2      = self._shot_select(play_type, rng)
            xfg2, pts2 = self._xfg(zone2, effective_adj, rng)
            pts2       = pts2 if rng.random() < xfg2 else 0
            return {"play_type": play_type, "outcome": "oreb", "shot_zone": zone,
                    "xfg": xfg_v, "made": False, "points": pts2}

        return {"play_type": play_type, "outcome": "shot", "shot_zone": zone,
                "xfg": xfg_v, "made": False, "points": 0}

    # ── 10 K game simulation ──────────────────────────────────────────────────

    def simulate_game(self, team_a: str, team_b: str,
                      n_sims: int = 10000, team_a_stats: Optional[dict] = None,
                      team_b_stats: Optional[dict] = None,
                      player_stats: Optional[dict] = None,
                      home_team: Optional[str] = None,
                      prop_lines: Optional[dict] = None,
                      lstm_engine: Optional[Any] = None) -> dict:
        """Run n_sims Monte Carlo game simulations.

        Args:
            prop_lines: {player_id: {stat: line}} e.g. {"Murray": {"pts": 22.5}}
                        Adds p_over_X.X to each player's stat distribution.
        """
        # Pace → possessions per game
        pace_a       = float((team_a_stats or {}).get("pace", 100))
        pace_b       = float((team_b_stats or {}).get("pace", 100))
        n_possessions = max(160, int((pace_a + pace_b) / 2 / 100 * 200))

        adj_a, adj_b = self._matchup_adj(team_a_stats, team_b_stats)
        if home_team == team_a:
            adj_a *= 1.012
        elif home_team == team_b:
            adj_b *= 1.012

        oreb_a = float((team_a_stats or {}).get("oreb_pct", 0.27))
        oreb_b = float((team_b_stats or {}).get("oreb_pct", 0.27))

        roster_a = self._filter_dnp((player_stats or {}).get(team_a, []))
        roster_b = self._filter_dnp((player_stats or {}).get(team_b, []))
        all_pids = roster_a + roster_b
        usage_a  = self._usage_weights(roster_a)
        usage_b  = self._usage_weights(roster_b)
        # CV minutes: use per-player tracked minutes if available, else season avg default
        _cv = self._cv_minutes
        def _roster_minutes(roster: list[str]) -> "Optional[np.ndarray]":
            if not _cv:
                return None
            mins = np.array([_cv.get(pid, 36.0) for pid in roster], dtype=np.float32)
            return mins if len(mins) > 0 else None

        fatigue_a = self._fatigue.batch_predict(
            max(len(roster_a), 1), minutes=_roster_minutes(roster_a))
        fatigue_b = self._fatigue.batch_predict(
            max(len(roster_b), 1), minutes=_roster_minutes(roster_b))

        rng = np.random.default_rng()

        # Batch-generate ALL play-type features for n_sims × n_possessions in one call
        total   = n_sims * n_possessions
        X_all   = np.column_stack([
            rng.uniform(60, 180, total),
            rng.uniform(100, 400, total),
            rng.uniform(0, 2, total),
            rng.integers(0, 15, total).astype(np.float32),
            rng.integers(0, 5, total).astype(np.float32),
            rng.integers(0, 3, total).astype(np.float32),
            rng.normal(0, 8, total).astype(np.float32),
            (rng.random(total) < 0.08).astype(np.float32),
            rng.uniform(4, 24, total),
        ]).astype(np.float32)
        play_idx_grid = self._selector.sample_batch_np(X_all, rng).reshape(n_sims, n_possessions)
        classes       = self._selector._classes or ["other"]

        sa_arr = np.zeros(n_sims)
        sb_arr = np.zeros(n_sims)
        a_wins = 0
        pid_sims: Optional[dict[str, dict[str, np.ndarray]]] = (
            {p: {s: np.zeros(n_sims) for s in _PROP_STATS} for p in all_pids}
            if all_pids else None
        )
        q_len = max(1, n_possessions // 4)

        for sim_i in range(n_sims):
            sa, sb   = 0.0, 0.0
            play_row = play_idx_grid[sim_i]
            garbage  = False
            foul_cts: dict = {}

            for i in range(n_possessions):
                period           = min(i // q_len + 1, 4)
                min_rem_q        = max(0.0, 12.0 * (1.0 - (i % q_len) / q_len))
                min_rem_game     = max(0.0, 12.0 * (4 - period) + min_rem_q)

                # Garbage time check at quarter boundaries
                if i % q_len == 0 and self._garbage_mdl is not None:
                    score_diff_now = sa - sb
                    garbage = self._garbage_mdl.predict(score_diff_now, min_rem_game, period)

                off_a    = (i % 2 == 0)
                adj      = adj_a if off_a else adj_b
                oreb     = oreb_a if off_a else oreb_b
                roster   = roster_a if off_a else roster_b
                usage    = (usage_a if off_a else usage_b).copy()
                fat      = fatigue_a if off_a else fatigue_b

                # Foul suppression: reduce usage by 50% if foul-out risk > 0.3
                if self._foul_mdl is not None and len(roster) > 0:
                    for fi, fp in enumerate(roster):
                        fc = foul_cts.get(fp, 0)
                        if fc >= 2:
                            risk = self._foul_mdl.predict(fc, period, min_rem_game)
                            if risk > 0.3:
                                usage[fi] *= 0.5
                    s = usage.sum()
                    if s > 0:
                        usage = usage / s

                # Q4 usage boost for star players in close games
                score_diff_now = sa - sb
                if period == 4 and abs(score_diff_now) <= 5 and self._q4_mdl is not None:
                    star_usage = float(usage.max()) if len(usage) > 0 else 0.2
                    mult = self._q4_mdl.predict(score_diff_now, star_usage,
                                                1 if abs(score_diff_now) <= 5 else 0)
                    mult = float(np.clip(mult, 0.7, 1.5))
                    if len(usage) > 0:
                        peak_idx = int(usage.argmax())
                        usage[peak_idx] *= mult
                        usage = usage / usage.sum()

                play_type = classes[play_row[i]]
                pid_idx   = int(rng.choice(len(roster), p=usage)) if len(usage) > 0 else 0
                pid       = roster[pid_idx] if roster else None
                fat_mult  = float(fat[pid_idx]) if pid_idx < len(fat) else 1.0

                if garbage:
                    gs     = {"xfg_adj_factor": 0.42 / 0.45, "oreb_rate": oreb,
                              "player_id": None, "fatigue_mult": 1.0,
                              "score_diff": score_diff_now}
                    result = self.simulate_possession(gs, play_type=play_type, rng=rng)
                    pts    = result["points"]
                    if off_a: sa += pts
                    else:     sb += pts
                    continue  # skip prop accumulation for starters

                gs = {"xfg_adj_factor": adj, "oreb_rate": oreb,
                      "player_id": pid, "fatigue_mult": fat_mult,
                      "score_diff": (sa - sb if off_a else sb - sa)}
                result = self.simulate_possession(gs, play_type=play_type, rng=rng)
                pts    = result["points"]

                if off_a: sa += pts
                else:     sb += pts

                if pid is not None and result["outcome"] == "foul":
                    foul_cts[pid] = foul_cts.get(pid, 0) + 1

                if pid_sims is not None and pid in pid_sims:
                    d = pid_sims[pid]
                    d["pts"][sim_i] += pts
                    if result["outcome"] == "turnover":
                        d["tov"][sim_i] += 1
                    if result.get("made"):
                        zone = result.get("shot_zone", "")
                        if zone == "3pt_arc":
                            d["fg3m"][sim_i] += 1
                    # heuristic per-possession secondary stats
                    if rng.random() < 0.05:
                        d["reb"][sim_i] += 1
                    if result.get("made") and rng.random() < 0.35:
                        d["ast"][sim_i] += 1
                    if rng.random() < 0.012:
                        d["stl"][sim_i] += 1
                    if result.get("outcome") == "shot" and not result.get("made") and rng.random() < 0.012:
                        d["blk"][sim_i] += 1

            # Overtime (up to 4 periods, 10 possessions each)
            ot = 0
            while sa == sb and ot < 4:
                ot += 1
                for ot_i in range(10):
                    off_a = (ot_i % 2 == 0)
                    res   = self.simulate_possession(
                        {"xfg_adj_factor": adj_a if off_a else adj_b,
                         "oreb_rate": oreb_a if off_a else oreb_b}, rng=rng)
                    if off_a:
                        sa += res["points"]
                    else:
                        sb += res["points"]

            sa_arr[sim_i] = sa
            sb_arr[sim_i] = sb
            if sa > sb:
                a_wins += 1

        out: dict = {
            "win_probability": {
                team_a: round(a_wins / n_sims, 4),
                team_b: round((n_sims - a_wins) / n_sims, 4),
            },
            "score_distribution": {
                team_a: {"mean": round(float(sa_arr.mean()), 1), "std": round(float(sa_arr.std()), 1)},
                team_b: {"mean": round(float(sb_arr.mean()), 1), "std": round(float(sb_arr.std()), 1)},
            },
        }

        # LSTM win probability gate (optional)
        _team_a_pts_mean = round(float(sa_arr.mean()), 1)
        _team_b_pts_mean = round(float(sb_arr.mean()), 1)
        live_win_prob: Optional[dict] = None
        if lstm_engine is not None:
            try:
                _game_dict = {
                    'possessions': [
                        {
                            'home_pts': int(_team_a_pts_mean),
                            'away_pts': int(_team_b_pts_mean),
                            'time_remaining_s': 0.0,
                            'spacing_index': 3.5,
                        }
                    ],
                    'home_team': {'off_rtg': 112.0, 'def_rtg': 110.0},
                    'away_team': {'off_rtg': 110.0, 'def_rtg': 112.0},
                    'home_lineup_net_rtg': 2.0,
                    'outcome': 1 if a_wins > (n_sims - a_wins) else 0,
                }
                live_win_prob = lstm_engine.update(_game_dict)
            except Exception as _e:
                logging.warning("LSTM gate failed: %s", _e)

        if live_win_prob is not None:
            out['live_win_prob'] = live_win_prob

        if pid_sims is not None:
            player_out: dict = {}
            player_dist: dict = {}
            for pid, stat_arrs in pid_sims.items():
                stat_entries: dict = {}
                for stat, vals in stat_arrs.items():
                    entry: dict = {
                        "mean": round(float(vals.mean()), 2),
                        "std":  round(float(vals.std()), 2),
                        "p10":  round(float(np.percentile(vals, 10)), 2),
                        "p25":  round(float(np.percentile(vals, 25)), 2),
                        "p50":  round(float(np.percentile(vals, 50)), 2),
                        "p75":  round(float(np.percentile(vals, 75)), 2),
                        "p90":  round(float(np.percentile(vals, 90)), 2),
                    }
                    lines = (prop_lines or {}).get(pid, {})
                    if stat in lines:
                        entry[f"p_over_{lines[stat]}"] = round(float((vals > lines[stat]).mean()), 4)
                    stat_entries[stat] = entry
                player_out[pid] = {"pts": stat_entries["pts"]}
                player_dist[pid] = stat_entries
            out["player_stats"]        = player_out
            out["player_distributions"] = player_dist

        return out

    def over_prob(self, player_id: str, line: float,
                  team_a: str, team_b: str, roster_a: list[str], roster_b: list[str],
                  n_sims: int = 10000, team_a_stats: Optional[dict] = None,
                  team_b_stats: Optional[dict] = None) -> float:
        """Convenience wrapper: P(player pts > line) via simulate_game."""
        res  = self.simulate_game(
            team_a, team_b, n_sims=n_sims,
            team_a_stats=team_a_stats, team_b_stats=team_b_stats,
            player_stats={team_a: roster_a, team_b: roster_b},
            prop_lines={player_id: {"pts": line}},
        )
        return float(res.get("player_stats", {}).get(player_id, {}).get(
            "pts", {}).get(f"p_over_{line}", 0.5))
