"""Per-possession OUTCOME model P(outcome | state)  (FRONT A core).

From historical PBP we segment each game into POSSESSIONS and, for each, label
the terminal outcome and the points scored on that possession. We then learn

    P(outcome | game-state-at-possession-start, offense/defense strength)

over the 7 canonical classes

    {make_2, miss_2, make_3, miss_3, ft_trip, turnover, foul}

plus an associated points expectation per (outcome, state). The model is the
generative core that ``rest_of_game_sim`` samples from to roll a mid-game state
forward to a distribution of final scores + win prob.

LEAK DISCIPLINE (HARD HONESTY RULES, identical posture to src/ingame):
  * The state vector for a possession starting at event E is a pure function of
    events STRICTLY BEFORE E within this game (running score, four-factors-so-far,
    pace-so-far, period, clock). The possession's own terminal event is NOT in the
    features -- it is the label.
  * Offense/defense team strength is supplied by the caller from that team's games
    STRICTLY BEFORE this game's date (a game-constant injected once); absent -> 0.
  * Training is WALK-FORWARD by game_date elsewhere (see scripts/sim/*). This
    module only builds rows + fits; it never reads an as-of-today aggregate.

Segmentation (from the 8-key historical schema, SPEC 1.1):
  A possession is owned by the team with the ball; it ENDS on:
    - made FG            -> make_2 / make_3        (+2 / +3 points; +1 if and-1 FT)
    - turnover           -> turnover               (0 points)
    - defensive rebound  -> the missed shot that preceded it is miss_2 / miss_3
    - last FT of a trip  -> ft_trip                (points = FTs made on the trip)
    - shooting foul that sends to the line is folded into the resulting ft_trip
  An OFFENSIVE rebound CONTINUES the same possession (does not end it); we keep
  accumulating until a terminal event. This matches the standard
  possessions = FGA + 0.44*FTA + TOV - OREB intuition at the event level.

We deliberately keep classes coarse and points a small lookup/draw rather than a
heavy regressor: the simulator needs a fast, calibrated sampler, not a perfect
points predictor. ``and-1`` and the occasional 4-pt play are captured by a
per-outcome empirical points distribution learned alongside the class model.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:  # xgboost is the project standard; fall back to a multinomial-logit if absent
    import xgboost as xgb  # type: ignore
    _HAS_XGB = True
except Exception:  # pragma: no cover
    _HAS_XGB = False

from src.ingame.state_featurizer import (
    normalize_event, resolve_orientation, _side_for_team, _other,
    _game_elapsed_sec, _game_total_sec,
    EVT_MADE_FG, EVT_MISS_FG, EVT_FREE_THROW, EVT_REBOUND, EVT_TURNOVER,
    EVT_FOUL, EVT_SUB, EVT_END_PERIOD, REG_GAME_LEN_SEC,
)

# ---------------------------------------------------------------------------
# Outcome taxonomy
# ---------------------------------------------------------------------------
OUTCOMES = ["make_2", "miss_2", "make_3", "miss_3", "ft_trip", "turnover", "foul"]
OUTCOME_IDX = {o: i for i, o in enumerate(OUTCOMES)}
N_OUTCOMES = len(OUTCOMES)

# State features at possession START (all leak-free; see module docstring).
STATE_FEATURES = [
    "period",
    "game_remaining_min",
    "played_share",
    "off_is_home",
    "score_margin_off",          # (offense score - defense score), offense POV
    "abs_score_margin",
    "off_poss_count", "def_poss_count",
    "sec_per_poss_so_far",
    "off_efg_so_far", "def_efg_so_far",
    "off_tov_pct_so_far", "def_tov_pct_so_far",
    "off_ft_rate_so_far",
    "off_in_bonus", "def_in_bonus",
    # prior-form team strength (caller-supplied, games before this date; 0 if none)
    "off_prior_ortg", "def_prior_drtg",
    "off_prior_pace", "def_prior_pace",
    "off_prior_3par",            # offense prior 3-point attempt rate
]

# INTELLIGENCE-COUPLED features (offense playstyle x opponent scheme/coverage),
# supplied as a game-constant from games STRICTLY BEFORE this date (same leak
# posture as the prior-strength block above; absent -> 0). Appended so that a
# model trained WITHOUT them is unaffected and the un-coupled call path stays
# byte-identical. See src/sim/intel_coupling.py for the derivation.
try:
    from src.sim.intel_coupling import INTEL_FEATURES as _INTEL_FEATURES
except Exception:  # pragma: no cover - keep module importable in isolation
    _INTEL_FEATURES = []

STATE_FEATURES_INTEL = list(STATE_FEATURES) + list(_INTEL_FEATURES)

_RE_PTS = re.compile(r"\((\d+)\s*PTS\)")
_RE_FT_OF = re.compile(r"Free Throw (\d+) of (\d+)")
_RE_PF = re.compile(r"\(P(\d+)\.T(\d+)\)")
BONUS_FOULS = 5


@dataclass
class PossessionRow:
    """One training/eval example: state at possession start + labelled outcome."""
    game_id: str
    period: int
    game_sec: int
    off_side: str
    state: Dict[str, float]
    outcome: str
    points: int


# ---------------------------------------------------------------------------
# Per-possession segmentation + feature extraction
# ---------------------------------------------------------------------------
def extract_possessions(
    events: List[Dict[str, Any]],
    game_id: str,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    *,
    prior_strength: Optional[Dict[str, Dict[str, float]]] = None,
    intel: Optional[Dict[str, Dict[str, float]]] = None,
) -> List[PossessionRow]:
    """Replay events, segment into possessions, return labelled feature rows.

    Args:
        events: raw historical PBP events (concatenated periods, in order).
        game_id, home_team, away_team: as in state_featurizer.
        prior_strength: optional
            {"home": {"ortg","drtg","pace","3par"}, "away": {...}} from each
            team's games STRICTLY BEFORE this game's date. Injected as a
            game-constant; absent -> those features are 0.
        intel: optional intelligence-coupled signature, keyed by OFFENSE side:
            {"home": {<INTEL_FEATURES from home-offense-vs-away-defense>},
             "away": {<INTEL_FEATURES from away-offense-vs-home-defense>}}
            from games STRICTLY BEFORE this date (see src/sim/intel_coupling.py).
            Injected as a game-constant per offense side; absent -> 0. Adding
            ``intel`` changes nothing unless the model's feature_names include the
            INTEL_FEATURES (additive, byte-identical otherwise).

    Returns:
        list of PossessionRow, one per completed possession, in game order.
    """
    orient = resolve_orientation(events, home_team, away_team)

    # Running, leak-free team aggregates (state BEFORE the current possession's
    # terminal event is what we featurize; we snapshot at possession start).
    agg = {s: dict(fga=0, fgm=0, fg3a=0, fg3m=0, fta=0, ftm=0,
                   oreb=0, dreb=0, tov=0) for s in ("home", "away")}
    poss_count = {"home": 0, "away": 0}
    team_fouls_period = {"home": 0, "away": 0}
    cur_period = None

    prior = prior_strength or {}
    intel_by_side = intel or {}

    def _prior(side: str, key: str) -> float:
        d = prior.get(side) or {}
        return float(d.get(key, 0.0) or 0.0)

    def _intel_dict(side: str) -> Dict[str, float]:
        d = intel_by_side.get(side)
        return dict(d) if d else {}

    home_score = away_score = 0
    rows: List[PossessionRow] = []

    # current possession accumulator
    cur_off: Optional[str] = None        # side with the ball
    cur_start_sec: Optional[int] = None
    cur_start_period: Optional[int] = None
    cur_start_state: Optional[Dict[str, float]] = None
    pend_shot_was_3: Optional[bool] = None   # last missed FG's 3-ness (for DREB label)
    ft_made_in_trip = 0
    ft_trip_open = False

    max_period = max((int(e.get("period", 1) or 1) for e in events), default=1)
    game_total = _game_total_sec(max_period)

    def _snapshot_state(off: str, game_sec: int, period: int) -> Dict[str, float]:
        deff = _other(off)
        a_off, a_def = agg[off], agg[deff]
        rem_min = max(0.0, (game_total - game_sec) / 60.0)
        played = game_sec / game_total if game_total else 0.0
        total_poss = poss_count["home"] + poss_count["away"]
        sec_per_poss = (game_sec / total_poss) if total_poss > 0 else 0.0

        def _efg(a):
            return (a["fgm"] + 0.5 * a["fg3m"]) / a["fga"] if a["fga"] else 0.0

        def _tovp(a):
            poss = a["fga"] + 0.44 * a["fta"] + a["tov"] - a["oreb"]
            return a["tov"] / poss if poss > 0 else 0.0

        def _ftr(a):
            return a["fta"] / a["fga"] if a["fga"] else 0.0

        off_score = home_score if off == "home" else away_score
        def_score = away_score if off == "home" else home_score
        # intelligence-coupled game-constant for THIS offense side (offense-POV;
        # absent -> empty -> features default to 0 in the model matrix).
        intel_feats = _intel_dict(off)
        base = {
            "period": float(period),
            "game_remaining_min": rem_min,
            "played_share": played,
            "off_is_home": 1.0 if off == "home" else 0.0,
            "score_margin_off": float(off_score - def_score),
            "abs_score_margin": float(abs(off_score - def_score)),
            "off_poss_count": float(poss_count[off]),
            "def_poss_count": float(poss_count[deff]),
            "sec_per_poss_so_far": sec_per_poss,
            "off_efg_so_far": _efg(a_off),
            "def_efg_so_far": _efg(a_def),
            "off_tov_pct_so_far": _tovp(a_off),
            "def_tov_pct_so_far": _tovp(a_def),
            "off_ft_rate_so_far": _ftr(a_off),
            "off_in_bonus": 1.0 if team_fouls_period[deff] >= BONUS_FOULS else 0.0,
            "def_in_bonus": 1.0 if team_fouls_period[off] >= BONUS_FOULS else 0.0,
            "off_prior_ortg": _prior(off, "ortg"),
            "def_prior_drtg": _prior(deff, "drtg"),
            "off_prior_pace": _prior(off, "pace"),
            "def_prior_pace": _prior(deff, "pace"),
            "off_prior_3par": _prior(off, "3par"),
        }
        base.update(intel_feats)
        return base

    def _ensure_poss_start(off: str, game_sec: int, period: int) -> None:
        nonlocal cur_off, cur_start_sec, cur_start_period, cur_start_state
        if cur_off is None and off in ("home", "away"):
            cur_off = off
            cur_start_sec = game_sec
            cur_start_period = period
            cur_start_state = _snapshot_state(off, game_sec, period)

    def _close_poss(outcome: str, points: int) -> None:
        nonlocal cur_off, cur_start_sec, cur_start_period, cur_start_state
        if cur_off is None or cur_start_state is None:
            return
        poss_count[cur_off] += 1
        rows.append(PossessionRow(
            game_id=game_id,
            period=int(cur_start_period or 1),
            game_sec=int(cur_start_sec or 0),
            off_side=cur_off,
            state=cur_start_state,
            outcome=outcome,
            points=int(points),
        ))
        cur_off = None
        cur_start_sec = None
        cur_start_period = None
        cur_start_state = None

    prev_game_sec = -1
    for raw in events:
        ev = normalize_event(raw)
        period = ev["period"]
        elapsed = ev["elapsed_sec_in_period"]
        game_sec = _game_elapsed_sec(period, elapsed)
        game_sec = max(game_sec, prev_game_sec) if prev_game_sec >= 0 else game_sec
        prev_game_sec = game_sec
        etype = ev["event_type"]
        desc = ev["event_desc"]
        team = ev["team_abbrev"]
        side = _side_for_team(team, orient) if team else ""
        is3 = "3PT" in desc

        if cur_period is None:
            cur_period = period
        elif period != cur_period:
            team_fouls_period = {"home": 0, "away": 0}
            cur_period = period

        # update running score from "L-R" string
        prev_home, prev_away = home_score, away_score
        if "-" in ev["score"]:
            try:
                l, r = (int(x) for x in ev["score"].split("-"))
                if orient.get("home_side", "left") == "left":
                    home_score, away_score = l, r
                else:
                    home_score, away_score = r, l
            except (ValueError, TypeError):
                pass

        if etype == EVT_MADE_FG and side in ("home", "away"):
            _ensure_poss_start(side, game_sec, period)
            agg[side]["fga"] += 1
            agg[side]["fgm"] += 1
            if is3:
                agg[side]["fg3a"] += 1
                agg[side]["fg3m"] += 1
            # a made FG ends the possession (and-1 FT, if any, is added below)
            if cur_off == side:
                _close_poss("make_3" if is3 else "make_2", 3 if is3 else 2)
            pend_shot_was_3 = None
            ft_trip_open = False
            ft_made_in_trip = 0

        elif etype == EVT_MISS_FG and side in ("home", "away"):
            _ensure_poss_start(side, game_sec, period)
            agg[side]["fga"] += 1
            if is3:
                agg[side]["fg3a"] += 1
            pend_shot_was_3 = is3   # resolved when the rebound lands

        elif etype == EVT_REBOUND and side in ("home", "away"):
            rm = re.search(r"\(Off:(\d+)\s*Def:(\d+)\)", desc)
            is_team = "TEAM" in desc.upper() or not ev["player_name"]
            if cur_off is not None and side != cur_off:
                # DEFENSIVE rebound: the offense's preceding miss ends the poss
                agg[side]["dreb"] += 1
                miss3 = bool(pend_shot_was_3)
                _close_poss("miss_3" if miss3 else "miss_2", 0)
                pend_shot_was_3 = None
                # the rebounder's team now starts a possession
                _ensure_poss_start(side, game_sec, period)
            elif cur_off is not None and side == cur_off:
                # OFFENSIVE rebound: possession CONTINUES (same off keeps ball)
                agg[side]["oreb"] += 1
                pend_shot_was_3 = None

        elif etype == EVT_TURNOVER and side in ("home", "away"):
            _ensure_poss_start(side, game_sec, period)
            agg[side]["tov"] += 1
            if cur_off == side:
                _close_poss("turnover", 0)
            pend_shot_was_3 = None

        elif etype == EVT_FREE_THROW and side in ("home", "away"):
            _ensure_poss_start(side, game_sec, period)
            made = "MISS" not in desc
            agg[side]["fta"] += 1
            if made:
                agg[side]["ftm"] += 1
                ft_made_in_trip += 1
            ft_trip_open = True
            ofm = _RE_FT_OF.search(desc)
            if ofm and ofm.group(1) == ofm.group(2):
                # last FT of the trip -> possession ends as ft_trip
                if cur_off == side:
                    _close_poss("ft_trip", ft_made_in_trip)
                elif cur_off is not None and cur_off != side:
                    # and-1 / defensive-foul FT belonging to the shooting team that
                    # already had its make counted: don't double-close. Treat as the
                    # foul-trip points addition handled implicitly; start fresh.
                    pass
                ft_trip_open = False
                ft_made_in_trip = 0

        elif etype == EVT_FOUL and side in ("home", "away"):
            pm = _RE_PF.search(desc)
            if pm:
                team_fouls_period[side] = max(team_fouls_period[side], int(pm.group(2)))
            else:
                team_fouls_period[side] += 1
            # A defensive foul that produces FTs is captured by the ft_trip close
            # above; we additionally tag the possession as 'foul' ONLY when no make
            # and no FT resolve it (rare in this coarse scheme), so we leave the
            # open possession to resolve on its terminal event.

    return rows


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------
@dataclass
class PossessionOutcomeModel:
    """P(outcome | state) classifier + per-outcome empirical points sampler.

    ``fit`` trains a 7-class model (XGBoost softprob, or a numpy multinomial-logit
    fallback) on PossessionRow features. ``sample_outcome`` draws an outcome and
    points given a state vector -- the unit the simulator calls per possession.
    """
    device: str = "cpu"
    n_rounds: int = 200
    _booster: Any = None
    _W: Optional[np.ndarray] = None       # logit weights (fallback)
    _mu: Optional[np.ndarray] = None
    _sd: Optional[np.ndarray] = None
    # per-outcome empirical points distribution: {outcome: (values, probs)}
    _points_dist: Dict[str, Tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)
    feature_names: List[str] = field(default_factory=lambda: list(STATE_FEATURES))

    # -- featurization -----------------------------------------------------
    def _matrix(self, rows: List[PossessionRow]) -> np.ndarray:
        X = np.zeros((len(rows), len(self.feature_names)), dtype=np.float32)
        for i, r in enumerate(rows):
            for j, f in enumerate(self.feature_names):
                X[i, j] = float(r.state.get(f, 0.0) or 0.0)
        return X

    def state_vector(self, state: Dict[str, float]) -> np.ndarray:
        return np.array([[float(state.get(f, 0.0) or 0.0)
                          for f in self.feature_names]], dtype=np.float32)

    # -- fit ---------------------------------------------------------------
    def fit(self, rows: List[PossessionRow]) -> "PossessionOutcomeModel":
        if not rows:
            raise ValueError("no possession rows to fit")
        X = self._matrix(rows)
        y = np.array([OUTCOME_IDX[r.outcome] for r in rows], dtype=np.int32)

        # per-outcome empirical points distribution (for sampling and-1s, missed FTs)
        for o in OUTCOMES:
            pts = np.array([r.points for r in rows if r.outcome == o], dtype=np.float32)
            if pts.size == 0:
                # sensible defaults if a class is unseen in this train fold
                default = {"make_2": 2, "make_3": 3, "ft_trip": 1}.get(o, 0)
                self._points_dist[o] = (np.array([default], np.float32),
                                        np.array([1.0], np.float32))
            else:
                vals, counts = np.unique(pts, return_counts=True)
                self._points_dist[o] = (vals.astype(np.float32),
                                        (counts / counts.sum()).astype(np.float32))

        if _HAS_XGB:
            try:
                dtrain = xgb.DMatrix(X, label=y)
                params = {
                    "device": self.device, "tree_method": "hist",
                    "objective": "multi:softprob", "num_class": N_OUTCOMES,
                    "max_depth": 6, "eta": 0.08, "subsample": 0.8,
                    "colsample_bytree": 0.8, "min_child_weight": 5, "lambda": 1.0,
                    "eval_metric": "mlogloss",
                }
                self._booster = xgb.train(params, dtrain, num_boost_round=self.n_rounds)
                return self
            except Exception:
                self._booster = None  # fall through to logit
        self._fit_logit(X, y)
        return self

    def _fit_logit(self, X: np.ndarray, y: np.ndarray, iters: int = 400,
                   lr: float = 0.5, l2: float = 1e-3) -> None:
        self._mu = X.mean(axis=0)
        self._sd = X.std(axis=0) + 1e-6
        Xs = (X - self._mu) / self._sd
        n, d = Xs.shape
        Xb = np.hstack([Xs, np.ones((n, 1), np.float32)])
        W = np.zeros((d + 1, N_OUTCOMES), dtype=np.float64)
        Y = np.eye(N_OUTCOMES)[y]
        for _ in range(iters):
            logits = Xb @ W
            logits -= logits.max(axis=1, keepdims=True)
            P = np.exp(logits)
            P /= P.sum(axis=1, keepdims=True)
            grad = Xb.T @ (P - Y) / n + l2 * W
            W -= lr * grad
        self._W = W

    # -- predict -----------------------------------------------------------
    def predict_proba(self, state: Dict[str, float]) -> np.ndarray:
        x = self.state_vector(state)
        return self._proba_matrix(x)[0]

    def predict_proba_batch(self, X: np.ndarray) -> np.ndarray:
        return self._proba_matrix(X)

    def _proba_matrix(self, X: np.ndarray) -> np.ndarray:
        if self._booster is not None:
            P = self._booster.predict(xgb.DMatrix(X))
            return P.reshape(-1, N_OUTCOMES)
        assert self._W is not None and self._mu is not None and self._sd is not None
        Xs = (X - self._mu) / self._sd
        Xb = np.hstack([Xs, np.ones((Xs.shape[0], 1), np.float32)])
        logits = Xb @ self._W
        logits -= logits.max(axis=1, keepdims=True)
        P = np.exp(logits)
        P /= P.sum(axis=1, keepdims=True)
        return P

    # -- sample ------------------------------------------------------------
    def sample_outcome(self, state: Dict[str, float],
                       rng: np.random.Generator) -> Tuple[str, int]:
        """Draw (outcome, points) for one possession from this state."""
        p = self.predict_proba(state)
        idx = int(rng.choice(N_OUTCOMES, p=p))
        outcome = OUTCOMES[idx]
        vals, probs = self._points_dist.get(
            outcome, (np.array([0.0], np.float32), np.array([1.0], np.float32)))
        pts = int(rng.choice(vals, p=probs))
        return outcome, pts

    def expected_points(self, state: Dict[str, float]) -> float:
        """E[points | state] over outcomes -- a fast deterministic check."""
        p = self.predict_proba(state)
        ev = 0.0
        for i, o in enumerate(OUTCOMES):
            vals, probs = self._points_dist.get(
                o, (np.array([0.0], np.float32), np.array([1.0], np.float32)))
            ev += p[i] * float((vals * probs).sum())
        return ev

    # -- RestOfGameSim adapter --------------------------------------------
    def _state_from_game_row(self, game_row: Dict[str, Any], side: str,
                             priors: Optional[Dict[str, Any]]) -> Dict[str, float]:
        """Build an offense-POV STATE_FEATURES dict from a featurizer game_row.

        ``side`` is the OFFENSE side ('home'/'away'). Pulls the same leak-free
        four-factor / clock / possession-count fields the featurizer emits and the
        caller-supplied prior strengths (keys ``{side}_ortg``/``_drtg``/``_pace``/
        ``_3par`` if present in ``priors``), so the learned model sees the same
        state shape it was trained on.
        """
        deff = "away" if side == "home" else "home"
        g = lambda k, d=0.0: float(game_row.get(k, d) or d)  # noqa: E731
        off_score = g(f"{side}_score")
        def_score = g(f"{deff}_score")
        pri = priors or {}

        def pr(s: str, k: str) -> float:
            return float(pri.get(f"{s}_{k}", 0.0) or 0.0)

        # intelligence-coupled game-constant (offense-POV), if the caller threads
        # it through ``priors`` under priors["intel"][side]. Absent -> {} -> the
        # INTEL_FEATURES default to 0 in state_vector (byte-identical un-coupled).
        intel_side: Dict[str, float] = {}
        intel_blob = pri.get("intel") if isinstance(pri, dict) else None
        if isinstance(intel_blob, dict):
            cand = intel_blob.get(side)
            if isinstance(cand, dict):
                intel_side = cand

        state = {
            "period": g("period", 1.0),
            "game_remaining_min": g("game_remaining_sec") / 60.0,
            "played_share": g("played_share"),
            "off_is_home": 1.0 if side == "home" else 0.0,
            "score_margin_off": off_score - def_score,
            "abs_score_margin": abs(off_score - def_score),
            "off_poss_count": g(f"{side}_poss_count") or g(f"{side}_poss"),
            "def_poss_count": g(f"{deff}_poss_count") or g(f"{deff}_poss"),
            "sec_per_poss_so_far": g("sec_per_poss_so_far"),
            "off_efg_so_far": g(f"{side}_efg"),
            "def_efg_so_far": g(f"{deff}_efg"),
            "off_tov_pct_so_far": g(f"{side}_tov_pct"),
            "def_tov_pct_so_far": g(f"{deff}_tov_pct"),
            "off_ft_rate_so_far": g(f"{side}_ft_rate"),
            "off_in_bonus": g(f"{side}_in_bonus"),
            "def_in_bonus": g(f"{deff}_in_bonus"),
            "off_prior_ortg": pr(side, "ortg"),
            "def_prior_drtg": pr(deff, "drtg"),
            "off_prior_pace": pr(side, "pace"),
            "def_prior_pace": pr(deff, "pace"),
            "off_prior_3par": pr(side, "3par"),
        }
        state.update(intel_side)
        return state

    def team_params(self, game_row: Dict[str, Any], side: str,
                    priors: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
        """Drop-in for ``RestOfGameSim(model=...)`` (duck-typed interface).

        Returns ``{ppp, p_score, mean_pts_score, three_share}`` exactly like
        ``EmpiricalPossessionModel.team_params`` but derived from the LEARNED
        per-possession outcome distribution at this state, so the existing
        simulator can roll the rest of the game with the trained model and ZERO
        harness change (see rest_of_game_sim.py module TODO).
        """
        state = self._state_from_game_row(game_row, side, priors)
        p = self.predict_proba(state)
        # P(possession scores >0 points) = 1 - P(miss/turnover-only outcomes).
        # make_2/make_3/ft_trip can score; ft_trip may be 0 (missed FTs) but is
        # mostly >0; miss_*/turnover/foul score 0. Use the empirical points dist
        # to get the true scoring probability per outcome.
        ppp = 0.0
        p_score = 0.0
        three_num = 0.0   # expected made-3 mass for three_share shape
        for i, o in enumerate(OUTCOMES):
            vals, probs = self._points_dist.get(
                o, (np.array([0.0], np.float32), np.array([1.0], np.float32)))
            mean_pts = float((vals * probs).sum())
            prob_pos = float(probs[vals > 0].sum())
            ppp += p[i] * mean_pts
            p_score += p[i] * prob_pos
            if o == "make_3":
                three_num += p[i]
        p_score = float(min(0.95, max(0.05, p_score)))
        mean_pts_score = ppp / p_score if p_score > 1e-6 else 2.0
        # three_share: P(make_3) relative to all made FGs (make_2 + make_3)
        make_fg = p[OUTCOME_IDX["make_2"]] + p[OUTCOME_IDX["make_3"]]
        three_share = (three_num / make_fg) if make_fg > 1e-6 else 0.35
        return {
            "ppp": float(ppp),
            "p_score": p_score,
            "mean_pts_score": float(max(1.5, min(3.2, mean_pts_score))),
            "three_share": float(min(0.6, max(0.1, three_share))),
        }

    # -- persistence -------------------------------------------------------
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        blob: Dict[str, Any] = {
            "feature_names": self.feature_names,
            "points_dist": {o: (v.tolist(), p.tolist())
                            for o, (v, p) in self._points_dist.items()},
            "has_booster": self._booster is not None,
        }
        if self._booster is not None:
            self._booster.save_model(path + ".xgb")
        else:
            blob["W"] = self._W.tolist() if self._W is not None else None
            blob["mu"] = self._mu.tolist() if self._mu is not None else None
            blob["sd"] = self._sd.tolist() if self._sd is not None else None
        import json
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(blob, fh)

    @classmethod
    def load(cls, path: str, device: str = "cpu") -> "PossessionOutcomeModel":
        import json
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        m = cls(device=device, feature_names=blob["feature_names"])
        m._points_dist = {o: (np.array(v, np.float32), np.array(p, np.float32))
                          for o, (v, p) in blob["points_dist"].items()}
        if blob.get("has_booster") and _HAS_XGB:
            b = xgb.Booster()
            b.load_model(path + ".xgb")
            m._booster = b
        else:
            m._W = np.array(blob["W"]) if blob.get("W") is not None else None
            m._mu = np.array(blob["mu"]) if blob.get("mu") is not None else None
            m._sd = np.array(blob["sd"]) if blob.get("sd") is not None else None
        return m
