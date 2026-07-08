"""relevance_gate -- does conditioning on a claim feature improve OOS Brier?

For one (sport, family, metric):
  base model      = leak-free walk-forward Elo (reuse GenericRatingModel),
                    recalibrated with a fitted INTERCEPT on the train prefix.
  candidate model = same base logit + intercept + beta * standardized claim
                    feature-diff (home_z - away_z), beta fit on the SAME train.
Base and candidate differ ONLY by the feature term (comparability rail): same
games, same folds, same optimizer. Claim feature is the PRIOR season's
season-end value -- known before the eval season starts, so no leak.

Walk-forward: eval-season games ordered by date, split by time (train prefix
fits {intercept[, beta]}, test suffix is scored). ponytail: single temporal
split, not a per-game expanding refit -- beta is one scalar, and refitting it
1156 times buys nothing here; upgrade to expanding refit if beta drifts.

Truncation: delta recomputed after dropping the last 20% of the test window.
"Beyond noise" = cluster-robust Diebold-Mariano on the paired squared-error
diffs (reuse eval_gate.dm_test), clustered by game_id.

NO dollar/edge language: Brier / log-loss deltas only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.generic_rating import GenericRatingModel, _SPORT_HFA
from scripts.platformkit.intel_weighting.claim_features import (
    load_family_features,
    prior_season_metrics,
)
from scripts.platformkit.intel_weighting.player_team_agg import aggregate_to_team
from scripts.platformkit.intel_weighting.sport_config import (
    SEASON_STYLE, load_games, prior_season_str, soccer_referee_view, win_col,
)

_MIN_TEST = 60          # too few OOS games -> UNTESTABLE
_TRAIN_FRAC = 0.6       # temporal train prefix within the eval season
_DM_ALPHA = 0.05        # two-tailed p for "beyond noise"
METHOD = "prior_season_claim_walkforward_v1"
# entity_key spellings seen in claim payloads for a player-id-keyed family.
_PLAYER_ENTITY_KEYS = {"player_id", "player", "pid"}
# sports with a wired playing-time source for player->team aggregation
# (see player_team_agg._BOX_SOURCES). Others fall through to UNTESTABLE.
_PLAYER_TEAM_AGG_SPORTS = {"nba", "mlb"}
# sports where the "player" IS one of the two game sides directly -- no
# team roll-up needed, home_team/away_team already carry the player's id.
_PLAYER_DIRECT_SPORTS = {"tennis"}
_REFEREE_ENTITY_KEYS = {"referee"}
_REFEREE_SPORTS = {"soccer"}


@dataclass
class GateResult:
    family: str
    sport: str
    metric: str
    entity_mapping: str
    n_games: int
    brier_base: float
    brier_cond: float
    delta: float            # brier_base - brier_cond  (>0 = conditioning helps)
    delta_trunc80: float
    dm_p: float
    verdict: str            # MATTERS_PROVISIONAL | NULL | UNTESTABLE
                            # single-fold gate by construction: its strongest
                            # verdict stays PROVISIONAL until replicated on an
                            # independent season/corpus
    caveats: List[str] = field(default_factory=list)


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _fit(base_logit: np.ndarray, design: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit theta minimizing log-loss of sigmoid(base_logit + design @ theta)."""
    def nll(theta: np.ndarray) -> float:
        p = _sigmoid(base_logit + design @ theta)
        p = np.clip(p, 1e-12, 1 - 1e-12)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    res = minimize(nll, np.zeros(design.shape[1]), method="BFGS")
    return res.x


def _base_probs(sport: str, games_df: pd.DataFrame) -> np.ndarray:
    """Leak-free walk-forward Elo home-win prob for every row, in df order.

    home_win here may be fractional (soccer H/D/A -> 1.0/0.5/0.0) -- Elo's
    update rule and the gate's Brier/log-loss are proper scoring rules for any
    target in [0,1], so a 0.5 draw needs no special-casing."""
    wc = win_col(sport)
    games = [
        {"home": str(h), "away": str(a), "season": str(s), "home_win": float(w)}
        for h, a, s, w in zip(
            games_df["home_team"], games_df["away_team"],
            games_df["season"], games_df[wc])
    ]
    mdl = GenericRatingModel(hfa=_SPORT_HFA.get(sport, 65.0))
    return mdl.walkforward(games)


def _zmap(values: Dict[str, float]) -> Dict[str, float]:
    v = np.array(list(values.values()), dtype=float)
    mu, sd = float(v.mean()), float(v.std())
    if sd == 0:
        return {k: 0.0 for k in values}
    return {k: (val - mu) / sd for k, val in values.items()}


def run_gate(sport: str, family: str, metric: str,
             feat: Dict[str, float], games_df: pd.DataFrame,
             base_logit_all: np.ndarray, eval_mask: np.ndarray,
             entity_mapping: str) -> GateResult:
    """Score one (family, metric). games_df/base_logit_all cover ALL seasons;
    eval_mask selects the eval-season rows (date-ordered)."""
    caveats: List[str] = []
    z = _zmap(feat)
    wc = win_col(sport)
    ev = games_df[eval_mask].reset_index(drop=True)
    base_logit = base_logit_all[eval_mask]
    y = ev[wc].to_numpy(dtype=float)
    gid = ev["game_id"].astype(str).to_numpy() if "game_id" in ev.columns \
        else ev.get("event_id", pd.Series(range(len(ev)))).astype(str).to_numpy()

    fdiff = np.array([z.get(str(h), 0.0) - z.get(str(a), 0.0)
                      for h, a in zip(ev["home_team"], ev["away_team"])], dtype=float)
    covered = sum(1 for h, a in zip(ev["home_team"], ev["away_team"])
                  if str(h) in z and str(a) in z)
    if covered < len(ev):
        caveats.append(f"{len(ev) - covered}/{len(ev)} games had an entity missing from the claim (fdiff=0)")

    n = len(ev)
    n_tr = int(n * _TRAIN_FRAC)
    n_te = n - n_tr
    if n_te < _MIN_TEST:
        return GateResult(family, sport, metric, entity_mapping, n, 0.0, 0.0, 0.0,
                          0.0, 1.0, "UNTESTABLE", caveats + [f"only {n_te} OOS games"])

    tr, te = slice(0, n_tr), slice(n_tr, n)
    # base: intercept only. cand: intercept + feature. Same optimizer/train/test.
    a_base = _fit(base_logit[tr], np.ones((n_tr, 1)), y[tr])
    theta = _fit(base_logit[tr], np.column_stack([np.ones(n_tr), fdiff[tr]]), y[tr])

    p_base = _sigmoid(base_logit[te] + a_base[0])
    p_cond = _sigmoid(base_logit[te] + theta[0] + theta[1] * fdiff[te])
    yb = y[te]
    brier_base, brier_cond = _brier(p_base, yb), _brier(p_cond, yb)
    delta = brier_base - brier_cond

    d = (p_base - yb) ** 2 - (p_cond - yb) ** 2   # >0 => cond better
    dm = diebold_mariano(d, gid[te])

    cut = int(n_te * 0.8)
    delta_t80 = _brier(p_base[:cut], yb[:cut]) - _brier(p_cond[:cut], yb[:cut])

    if delta > 0 and dm.p_value < _DM_ALPHA and delta_t80 > 0:
        verdict = "MATTERS_PROVISIONAL"
        caveats.append(
            "single-fold verdict at alpha=0.05 across many tested metrics: "
            "expected chance hits ~0.05*n_metrics; stays PROVISIONAL until "
            "replicated on an independent season/corpus")
    else:
        verdict = "NULL"
    return GateResult(family, sport, metric, entity_mapping, n,
                      round(brier_base, 6), round(brier_cond, 6), round(delta, 6),
                      round(delta_t80, 6), round(dm.p_value, 4), verdict, caveats)


def _team_codes(games_df: pd.DataFrame) -> Set[str]:
    return set(games_df["home_team"].astype(str)) | set(games_df["away_team"].astype(str))


def _composite_to_team(values: Dict[str, float], team_codes: Set[str]) -> Dict[str, float]:
    """Composite entity ids like 'MIL|GUARD' (team_posgroup): mean the ranked
    value across all of a team's segments, keyed off the FIRST '|' segment.
    Segments whose prefix isn't a real team code are dropped silently -- an
    all-dropped result is empty, and the caller turns that into a clean
    UNTESTABLE, never a raise."""
    sums: Dict[str, List[float]] = {}
    for k, v in values.items():
        seg = k.split("|", 1)[0]
        if seg in team_codes:
            sums.setdefault(seg, []).append(v)
    return {t: sum(vs) / len(vs) for t, vs in sums.items()}


def _dispatch_metric(sport: str, entity_key: str, values: Dict[str, float], eval_season: str,
                      games_df: pd.DataFrame, team_codes: Set[str]
                      ) -> Tuple[Optional[Dict[str, float]], str, pd.DataFrame, List[str]]:
    """Resolve ONE metric's (entity_key, values) -> (team_values, entity_mapping,
    gate_df, caveats). Dispatched per metric, not once per family, because a
    family's claims can mix entity_key spellings across metrics (see
    claim_features module docstring) -- one metric's unmappable key must not
    sink a sibling metric that has a real one. team_values is None when there
    is no aggregation path; the caller turns that into a clean UNTESTABLE row."""
    if entity_key == "team":
        return values, "team", games_df, []
    if entity_key in _PLAYER_ENTITY_KEYS and sport in _PLAYER_DIRECT_SPORTS:
        # tennis: home_team/away_team ARE p1_id/p2_id -- fdiff = z_p1 - z_p2
        # falls out of the existing z.get(home)-z.get(away) formula unchanged,
        # no team roll-up needed (there is no team).
        return values, "player_direct", games_df, []
    if entity_key in _PLAYER_ENTITY_KEYS and sport in _PLAYER_TEAM_AGG_SPORTS:
        # design (a): prior-season claim values, rolled up to team with
        # prior-season roster+playing-time weights (see player_team_agg doc).
        roster_season = prior_season_str(eval_season, sport)
        team_vals, dropped = aggregate_to_team(values, roster_season, sport=sport)
        caveats = [f"{len(dropped)} team(s) dropped below 60% coverage floor: "
                   f"{','.join(dropped)}"] if dropped else []
        return (team_vals or None), "player_minwt_prior_season", games_df, caveats
    if entity_key in _REFEREE_ENTITY_KEYS and sport in _REFEREE_SPORTS:
        # a referee is not a side -- no home/away sign. soccer_referee_view
        # substitutes the assigned referee for home_team and a sentinel
        # (z=0) for away_team, so run_gate's fdiff collapses to the raw,
        # unsigned z(referee). Base Elo still rates the REAL teams (games_df).
        return values, "referee_raw_z", soccer_referee_view(games_df), []
    if any("|" in k for k in values):
        # composite entity id (e.g. team_posgroup's 'MIL|GUARD') -- aggregate
        # to team if the prefix names a real team, else clean UNTESTABLE.
        team_vals = _composite_to_team(values, team_codes)
        if team_vals:
            return team_vals, "composite_team_mean", games_df, []
        return None, f"{entity_key}->no_team", games_df, [f"no team mapping for entity_key={entity_key}"]
    return None, f"{entity_key}->none", games_df, [
        f"entity_key={entity_key}: no aggregation path wired for sport={sport} "
        "(team/player_minwt/referee/composite-team only)"]


def run_family(sport: str, family: str,
               claims_dir: Optional[Path] = None) -> List[GateResult]:
    """All prior-season team/player/referee/composite-mappable metrics of one
    family, dispatched PER METRIC (see _dispatch_metric)."""
    table = load_family_features(family, claims_dir)
    games_df = load_games(sport)
    style = SEASON_STYLE.get(sport, "split")
    eval_season = sorted(games_df["season"].astype(str).unique())[-1]
    per_metric = prior_season_metrics(table, eval_season, style)

    if not per_metric:
        return [GateResult(family, sport, "-", "-", len(games_df), 0.0, 0.0, 0.0,
                           0.0, 1.0, "UNTESTABLE",
                           [f"no prior-season ({eval_season} minus 1) plain window for any metric"])]

    team_codes = _team_codes(games_df)
    pb = np.clip(_base_probs(sport, games_df), 1e-9, 1 - 1e-9)
    base_logit_all = np.log(pb / (1 - pb))
    eval_mask = (games_df["season"].astype(str) == eval_season).to_numpy()

    results = []
    for metric, (entity_key, values) in sorted(per_metric.items()):
        feat, entity_mapping, gate_df, caveats = _dispatch_metric(
            sport, entity_key, values, eval_season, games_df, team_codes)
        if not feat:
            results.append(GateResult(family, sport, metric, entity_mapping, len(games_df),
                                      0.0, 0.0, 0.0, 0.0, 1.0, "UNTESTABLE",
                                      caveats or ["aggregation left zero entities above the coverage floor"]))
            continue
        g = run_gate(sport, family, metric, feat, gate_df, base_logit_all, eval_mask, entity_mapping)
        g.caveats.extend(caveats)
        results.append(g)
    return results
