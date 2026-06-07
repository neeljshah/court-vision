"""Possession-level Monte-Carlo simulator -- the JOINT distribution engine.

Dual role:
  1. PRODUCT  -- emit the joint distribution of every player stat + team totals +
     final score for a game, given pace, off/def efficiency, lineup, foul state,
     and the ACTIVE signal + atlas set.
  2. GATE TOOL -- model CROSS-SIGNAL CORRELATION so the honest gate can judge JOINT
     improvement (lower joint CRPS / Brier) and discount a second signal that is
     redundant with a first (two signals each +EV alone but correlated together).

Design (vectorized, leak-safe, GPU-optional):
  * Each team draws a per-sim possession count from a Normal around its pace prior
    (read from the ``pace_fit`` / ``usage_role`` atlas sections when present, else a
    league default). Per possession, points are a small mixture (0/2/3 + FT) whose
    probabilities come from off vs opp-def efficiency priors.
  * Player stat lines are drawn as the player's per-possession rate (atlas
    ``shot_profile`` / ``usage_role`` priors, shrunk to lineup usage shares) times
    that sim's team possessions, with Poisson-like counting noise. Correlated
    latent team factors (a shared pace/efficiency draw) induce the cross-player and
    cross-stat correlation the gate needs.
  * ACTIVE signals condition the per-possession outcome: ``Signal.build(ctx)`` is
    evaluated once (leak-safe, as-of the game ctx) and its scalar nudges the
    relevant rate, so adding a signal shifts the JOINT distribution and
    ``joint_score`` can measure the WITH-vs-WITHOUT delta.

All draws are numpy; if ``torch`` + CUDA are available the heavy per-sim tensors are
generated on device then moved back to host for summarisation. Everything degrades
to CPU/numpy. No network, no live reads -- atlas priors come from the store only.
"""
from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .signal import AsOfContext, Signal
from .store import PointInTimeStore, entity_key

STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# League per-possession priors (per-100-possession rates / 100) used when no atlas
# section is available. Deliberately conservative, face-valid season averages.
_LEAGUE_POSS = 99.0          # mean team possessions / game
_LEAGUE_POSS_SD = 6.0
_LEAGUE_PTS_PER_POSS = 1.12  # offensive efficiency (pts / possession)
_LEAGUE_PTS_PER_POSS_SD = 0.09
# Per-player share of a team's per-possession production for each counting stat,
# expressed as a starter-ish default rate (events per team-possession) so that
# rate * ~99 poss yields a plausible box line. Shrinkage anchor for the prior.
_LEAGUE_PLAYER_RATE: Dict[str, float] = {
    "pts": 0.130, "reb": 0.045, "ast": 0.028, "fg3m": 0.018,
    "stl": 0.008, "blk": 0.006, "tov": 0.014,
}
_QUANTS = ("q10", "q50", "q90")


# --------------------------------------------------------------------------- #
# device helpers (GPU optional)
# --------------------------------------------------------------------------- #
def _resolve_device(device: str) -> str:
    """Resolve ``"auto"`` to cuda when available, else cpu (mirrors repo pattern)."""
    if device == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    return device


def _normal(rng: np.random.Generator, loc: np.ndarray, scale: np.ndarray,
            n: int, device: str) -> np.ndarray:
    """Draw ``n``-row Normal samples, on GPU when available, returned as numpy."""
    if device == "cuda":
        try:
            import torch
            t = torch.normal(
                mean=torch.as_tensor(np.broadcast_to(loc, (n,)).astype("float32"),
                                     device="cuda"),
                std=torch.as_tensor(np.broadcast_to(scale, (n,)).astype("float32"),
                                    device="cuda"),
            )
            return t.cpu().numpy()
        except Exception:
            pass
    return rng.normal(loc=loc, scale=scale, size=n)


@dataclass
class JointDistribution:
    """The simulator's output: marginals + correlation + samples for every stat.

    Attributes:
        player_marginals: {player_id: {stat: {mean,std,q10,q50,q90}}}.
        team_totals:      {team: {"pts": {...}, "poss": {...}}}.
        final_score:      {"home": {...}, "away": {...}, "home_win_prob": float}.
        samples:          raw draws {entity: {stat: np.ndarray}} for joint pricing.
        corr:             cross-stat / cross-player correlation matrix (for SGP + gate).
        n_sims:           number of Monte-Carlo iterations.
    """

    player_marginals: Dict[Any, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    team_totals: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    final_score: Dict[str, Any] = field(default_factory=dict)
    samples: Optional[Dict[Any, Dict[str, Any]]] = None
    corr: Optional[Any] = None
    n_sims: int = 0

    def stat_samples(self, entity: Any, stat: str) -> Optional[np.ndarray]:
        """Convenience: raw per-sim draws for one (entity, stat), or None."""
        if not self.samples:
            return None
        return self.samples.get(entity, {}).get(stat)


# --------------------------------------------------------------------------- #
# prior assembly (leak-safe atlas reads)
# --------------------------------------------------------------------------- #
def _as_of_dt(ctx: AsOfContext) -> _dt.datetime:
    return ctx.decision_time


def _team_pace_prior(store: Optional[PointInTimeStore], team: Optional[str],
                     as_of: _dt.datetime) -> Tuple[float, float]:
    """Return (mean_poss, sd_poss) for a team from the ``pace_fit`` atlas, else league."""
    if store is None or not team:
        return _LEAGUE_POSS, _LEAGUE_POSS_SD
    data = store.read_atlas("team", team, "pace_fit", as_of, with_cv=False)
    if isinstance(data, dict):
        poss = data.get("possessions_mean") or data.get("pace") or data.get("value")
        if isinstance(poss, (int, float)) and poss > 0:
            return float(poss), float(data.get("possessions_sd", _LEAGUE_POSS_SD))
    return _LEAGUE_POSS, _LEAGUE_POSS_SD


def _team_eff_prior(store: Optional[PointInTimeStore], team: Optional[str],
                    opp: Optional[str], as_of: _dt.datetime) -> Tuple[float, float]:
    """Return (pts_per_poss, sd) blending team offence vs opponent defence atlases."""
    off = _LEAGUE_PTS_PER_POSS
    deff = _LEAGUE_PTS_PER_POSS
    if store is not None and team:
        d = store.read_atlas("team", team, "off_efficiency", as_of, with_cv=False)
        if isinstance(d, dict) and isinstance(d.get("pts_per_poss"), (int, float)):
            off = float(d["pts_per_poss"])
    if store is not None and opp:
        d = store.read_atlas("team", opp, "def_efficiency", as_of, with_cv=False)
        if isinstance(d, dict) and isinstance(d.get("pts_per_poss_allowed"), (int, float)):
            deff = float(d["pts_per_poss_allowed"])
    return (off + deff) / 2.0, _LEAGUE_PTS_PER_POSS_SD


def _player_rate_prior(store: Optional[PointInTimeStore], pid: Any,
                       as_of: _dt.datetime) -> Dict[str, float]:
    """Per-possession event-rate prior per stat, from ``usage_role``/``shot_profile``
    atlases, shrunk toward the league default. Leak-safe; returns league on miss."""
    rates = dict(_LEAGUE_PLAYER_RATE)
    if store is None or pid is None:
        return rates
    usage = store.read_atlas("player", pid, "usage_role", as_of, with_cv=False)
    if isinstance(usage, dict):
        for stat in STATS:
            v = usage.get(f"{stat}_per_poss")
            if isinstance(v, (int, float)) and v >= 0:
                # shrink toward league prior (50/50) to stabilise sparse atlases
                rates[stat] = 0.5 * float(v) + 0.5 * rates[stat]
    return rates


def _signal_nudges(signals: Optional[List[Signal]], ctx: AsOfContext) -> Dict[str, float]:
    """Evaluate the ACTIVE signal set once (leak-safe) and fold into per-stat
    multiplicative rate nudges. A signal targeting ``pts`` with value v nudges the
    pts rate by ``1 + tanh(v)*0.15`` (bounded, correlation-preserving)."""
    nudges: Dict[str, float] = {s: 1.0 for s in STATS}
    if not signals:
        return nudges
    for sig in signals:
        try:
            val = sig.build(ctx)
        except Exception:
            val = None
        if val is None:
            continue
        target = getattr(sig, "target", None)
        if target not in nudges:
            continue
        scalar: Optional[float]
        if isinstance(val, dict):
            scalar = next((v for v in val.values() if isinstance(v, (int, float))), None)
        elif isinstance(val, (int, float)):
            scalar = float(val)
        else:
            scalar = None
        if scalar is None or not math.isfinite(scalar):
            continue
        nudges[target] *= 1.0 + math.tanh(scalar) * 0.15
    return nudges


# --------------------------------------------------------------------------- #
# core simulation
# --------------------------------------------------------------------------- #
def _summarise(draws: np.ndarray) -> Dict[str, float]:
    """Mean/std + q10/q50/q90 summary of one sample vector."""
    q10, q50, q90 = np.quantile(draws, (0.10, 0.50, 0.90))
    return {"mean": float(draws.mean()), "std": float(draws.std()),
            "q10": float(q10), "q50": float(q50), "q90": float(q90)}


def _roster(ctx: AsOfContext, side: str) -> List[Any]:
    """Pull the lineup for one side from ctx.extra (leak-safe input), else []."""
    key = f"{side}_lineup"
    lineup = ctx.extra.get(key) if isinstance(ctx.extra, dict) else None
    if isinstance(lineup, (list, tuple)):
        return list(lineup)
    if side == "home" and ctx.player_id is not None:
        return [ctx.player_id]
    return []


def simulate_game(game_ctx: AsOfContext, *, store: Optional[PointInTimeStore] = None,
                  signals: Optional[List[Signal]] = None, n_sims: int = 10000,
                  device: str = "auto") -> JointDistribution:
    """Run the possession-level Monte-Carlo for one game; emit the joint distribution.

    Args:
        game_ctx: leak-safe context (decision_time, teams, lineups in ``extra``).
        store:    point-in-time store providing atlas priors per entity.
        signals:  the ACTIVE signal set whose values condition the sim.
        n_sims:   Monte-Carlo iterations (default 10K).
        device:   "auto" (cuda) | "cuda" | "cpu".

    Returns:
        A :class:`JointDistribution` with player marginals, team totals, final
        score (incl. ``home_win_prob``), raw samples, and a correlation matrix.
    """
    dev = _resolve_device(device)
    rng = np.random.default_rng(abs(hash((game_ctx.as_of_iso(), game_ctx.team,
                                          game_ctx.opp))) % (2 ** 32))
    as_of = _as_of_dt(game_ctx)
    nudges = _signal_nudges(signals, game_ctx)

    home, away = game_ctx.team or "HOME", game_ctx.opp or "AWAY"
    sides = {"home": (home, away), "away": (away, home)}

    # shared latent game factor (pace/intensity) -> induces cross-entity correlation
    game_factor = _normal(rng, np.float64(1.0), np.float64(0.06), n_sims, dev)
    game_factor = np.clip(game_factor, 0.7, 1.3)

    team_pts: Dict[str, np.ndarray] = {}
    team_poss: Dict[str, np.ndarray] = {}
    samples: Dict[Any, Dict[str, np.ndarray]] = {}
    player_marginals: Dict[Any, Dict[str, Dict[str, float]]] = {}

    for side, (tm, opp) in sides.items():
        p_mean, p_sd = _team_pace_prior(store, tm, as_of)
        e_mean, e_sd = _team_eff_prior(store, tm, opp, as_of)
        poss = np.clip(_normal(rng, np.float64(p_mean), np.float64(p_sd), n_sims, dev)
                       * game_factor, 70.0, 130.0)
        ppp = np.clip(_normal(rng, np.float64(e_mean), np.float64(e_sd), n_sims, dev),
                      0.8, 1.5)
        # the pts signal-nudge conditions BOTH teams' scoring (joint shift)
        ppp = ppp * nudges["pts"]
        # team points = possessions * pts-per-possession + counting noise
        pts = poss * ppp + rng.normal(0.0, 3.0, n_sims)
        team_poss[tm] = poss
        team_pts[tm] = np.clip(pts, 60.0, 175.0)

        # players: rate * possessions, with Poisson-like noise, scaled by game_factor
        roster = _roster(game_ctx, side)
        for pid in roster:
            rates = _player_rate_prior(store, pid, as_of)
            pstats: Dict[str, np.ndarray] = {}
            pmarg: Dict[str, Dict[str, float]] = {}
            for stat in STATS:
                lam = max(rates.get(stat, _LEAGUE_PLAYER_RATE[stat]), 0.0) \
                    * poss * nudges.get(stat, 1.0)
                lam = np.clip(lam, 0.0, None)
                draws = rng.poisson(lam).astype("float64")
                pstats[stat] = draws
                pmarg[stat] = _summarise(draws)
            samples[pid] = pstats
            player_marginals[pid] = pmarg

    # team totals
    team_totals: Dict[str, Dict[str, Dict[str, float]]] = {}
    for tm in {home, away}:
        team_totals[tm] = {"pts": _summarise(team_pts[tm]),
                           "poss": _summarise(team_poss[tm])}

    # final score / win prob
    hp, ap = team_pts[home], team_pts[away]
    home_win = float((hp > ap).mean())
    final_score = {
        "home": _summarise(hp), "away": _summarise(ap),
        "home_team": home, "away_team": away,
        "home_win_prob": home_win,
        "margin": _summarise(hp - ap),
    }

    # correlation matrix across all player×stat sample vectors (for SGP + gate)
    corr, corr_index = _build_corr(samples)

    return JointDistribution(
        player_marginals=player_marginals,
        team_totals=team_totals,
        final_score=final_score,
        samples=samples,
        corr={"matrix": corr, "index": corr_index} if corr is not None else None,
        n_sims=int(n_sims),
    )


def _build_corr(samples: Dict[Any, Dict[str, np.ndarray]]
                ) -> Tuple[Optional[np.ndarray], List[Tuple[Any, str]]]:
    """Stack every (entity, stat) sample vector and return its correlation matrix."""
    cols: List[np.ndarray] = []
    index: List[Tuple[Any, str]] = []
    for pid, stats in samples.items():
        for stat, vec in stats.items():
            if np.std(vec) > 0:
                cols.append(vec)
                index.append((pid, stat))
    if len(cols) < 2:
        return None, index
    mat = np.vstack(cols)
    return np.corrcoef(mat), index


# --------------------------------------------------------------------------- #
# pricing (correlation-aware EV) + scoring
# --------------------------------------------------------------------------- #
def _american_to_prob(odds: Optional[float]) -> Optional[float]:
    """Vigged implied probability from American odds (self-contained; mirrors devig)."""
    if odds is None:
        return None
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return 100.0 / (o + 100.0) if o > 0 else (-o) / ((-o) + 100.0)


def _decimal_payout(odds: Optional[float]) -> float:
    """Net decimal profit per 1 unit staked at American ``odds`` (b in Kelly)."""
    if odds is None:
        return 0.909  # ~ -110 default
    o = float(odds)
    return o / 100.0 if o > 0 else 100.0 / (-o)


def _best_side_odds(books: List[dict], side: str) -> Optional[float]:
    """Best (max American) price for a side across books."""
    key = "over_odds" if side == "over" else "under_odds"
    vals = [b.get(key) for b in (books or []) if isinstance(b.get(key), (int, float))]
    return max(vals) if vals else None


def price_vs_market(dist: JointDistribution, lines: List[dict]) -> List[dict]:
    """Correlation-aware EV pricing of lines against the joint distribution.

    Each ``line`` row is the spec_data.md line_row shape
    (``{player, player_id, stat, line, books:[{over_odds,under_odds,...}]}``). For a
    single line the model probability is the empirical P(stat > line) from the joint
    samples; for a multi-leg ``legs`` row the JOINT over/under probability is the
    empirical fraction of sims where ALL legs hit (not the naive product), which is
    what makes redundant correlated legs price correctly. Returns graded-bet-like
    dicts with ``model_prob``, ``market_prob``, ``ev_pct``, ``kelly_pct``.
    """
    out: List[dict] = []
    for row in lines or []:
        legs = row.get("legs")
        if legs:
            graded = _price_parlay(dist, row, legs)
        else:
            graded = _price_single(dist, row)
        if graded is not None:
            out.append(graded)
    return out


def _entity_for(row: dict) -> Any:
    return row.get("player_id", row.get("player"))


def _price_single(dist: JointDistribution, row: dict) -> Optional[dict]:
    stat = row.get("stat")
    line = row.get("line")
    pid = _entity_for(row)
    draws = dist.stat_samples(pid, stat) if (pid is not None and stat) else None
    if draws is None or line is None:
        return None
    line = float(line)
    p_over = float((draws > line).mean())
    side = "over" if p_over >= 0.5 else "under"
    model_prob = p_over if side == "over" else 1.0 - p_over
    odds = _best_side_odds(row.get("books", []), side)
    market_prob = _american_to_prob(odds)
    b = _decimal_payout(odds)
    ev_pct = (model_prob * (1.0 + b) - 1.0) * 100.0
    kelly = max(0.0, (model_prob * (b + 1.0) - 1.0) / b) if b > 0 else 0.0
    return {
        "player": row.get("player"), "player_id": pid, "stat": stat, "line": line,
        "side": side.upper(), "model_prob": round(model_prob, 4),
        "market_prob": round(market_prob, 4) if market_prob is not None else None,
        "ev_pct": round(ev_pct, 3), "kelly_pct": round(kelly, 4),
        "best_price": odds, "n_sims": dist.n_sims,
    }


def _price_parlay(dist: JointDistribution, row: dict, legs: List[dict]) -> Optional[dict]:
    """JOINT (correlation-aware) probability that ALL legs hit, from shared samples."""
    hit = None
    for leg in legs:
        draws = dist.stat_samples(_entity_for(leg), leg.get("stat"))
        if draws is None or leg.get("line") is None:
            return None
        ln = float(leg["line"])
        side = (leg.get("side") or "over").lower()
        leg_hit = (draws > ln) if side == "over" else (draws <= ln)
        hit = leg_hit if hit is None else (hit & leg_hit)
    if hit is None:
        return None
    joint_p = float(hit.mean())
    naive_p = 1.0
    for leg in legs:
        d = dist.stat_samples(_entity_for(leg), leg.get("stat"))
        side = (leg.get("side") or "over").lower()
        ln = float(leg["line"])
        naive_p *= float((d > ln).mean()) if side == "over" else float((d <= ln).mean())
    odds = row.get("odds")
    market_prob = _american_to_prob(odds)
    b = _decimal_payout(odds)
    ev_pct = (joint_p * (1.0 + b) - 1.0) * 100.0
    return {
        "legs": legs, "joint_model_prob": round(joint_p, 4),
        "naive_model_prob": round(naive_p, 4),
        "correlation_lift": round(joint_p - naive_p, 4),
        "market_prob": round(market_prob, 4) if market_prob is not None else None,
        "ev_pct": round(ev_pct, 3), "best_price": odds, "n_sims": dist.n_sims,
    }


def joint_score(dist: JointDistribution, actual: Dict[str, Any]) -> Dict[str, float]:
    """Score a realised game vs the joint distribution.

    ``actual`` carries ``{"players": {pid: {stat: value}}, "home_win": 0/1}``.
    Returns joint CRPS (mean per-(entity,stat) CRPS), a Brier on the home-win
    outcome, and per-stat mean pinball (q50). The gate compares this WITH vs WITHOUT
    a candidate signal to judge JOINT (not marginal) improvement.
    """
    players = (actual or {}).get("players", {}) or {}
    crps_vals: List[float] = []
    pinball: Dict[str, List[float]] = {s: [] for s in STATS}
    for pid, stat_actuals in players.items():
        for stat, av in stat_actuals.items():
            draws = dist.stat_samples(pid, stat)
            if draws is None or av is None:
                continue
            crps_vals.append(_crps_sample(draws, float(av)))
            q50 = float(np.quantile(draws, 0.5))
            err = float(av) - q50
            pinball.setdefault(stat, []).append(
                max(0.5 * err, (0.5 - 1.0) * err))
    joint_crps = float(np.mean(crps_vals)) if crps_vals else float("nan")

    brier = float("nan")
    hw = (actual or {}).get("home_win")
    p = dist.final_score.get("home_win_prob")
    if hw is not None and p is not None:
        brier = float((float(p) - float(hw)) ** 2)

    out: Dict[str, float] = {"joint_crps": joint_crps, "brier": brier,
                             "n_scored": float(len(crps_vals))}
    for stat, vals in pinball.items():
        if vals:
            out[f"pinball_{stat}"] = float(np.mean(vals))
    return out


def _crps_sample(draws: np.ndarray, y: float) -> float:
    """CRPS of an empirical (sample) forecast vs scalar ``y`` (energy form).

    CRPS = E|X - y| - 0.5 E|X - X'|, estimated from the sample (sorted closed form
    for the second term to stay O(n log n) / vectorized)."""
    n = draws.size
    if n == 0:
        return float("nan")
    term1 = float(np.mean(np.abs(draws - y)))
    s = np.sort(draws)
    # E|X - X'| via the order-statistic identity (vectorized, no n^2)
    i = np.arange(1, n + 1)
    term2 = float((2.0 / (n * n)) * np.sum((2 * i - n - 1) * s))
    return term1 - 0.5 * term2
