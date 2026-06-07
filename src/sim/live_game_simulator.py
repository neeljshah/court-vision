"""Live, event-reactive REST-OF-GAME Monte-Carlo simulator.

WHAT THIS IS (and how it differs from game_simulator.simulate_game)
------------------------------------------------------------------
``game_simulator.simulate_game`` is a PREGAME sim: full 48 min remaining,
possession 0, seeded from prior-game pace/ppp + pregame per-player q50.

``simulate_rest_of_game`` is the LIVE version: it takes the CURRENT in-game
snapshot (current box score, clock, who is on the floor, foul state, margin)
and simulates only the **remaining** possessions, then adds the result onto the
current box to produce coherent FINAL distributions. Because the input is the
live snapshot, the projection is INHERENTLY reactive — every new event (a
bucket, a foul, a player sitting, a run) feeds a fresh snapshot and re-shapes
the rest-of-game distribution. The dynamics that "change what's going to happen"
are modelled EXPLICITLY in the remaining-minutes layer:

  * FOUL TROUBLE   pf>=6 -> out (0 remaining min); pf==5 late-risk haircut;
                   pf==4 early mild haircut. Vacated minutes redistribute to
                   teammates (usage absorption).
  * BLOWOUT        large margin + late clock -> starters' remaining minutes are
                   pulled (garbage time), bench minutes rise.
  * CLUTCH         close margin + late clock -> remaining usage CONCENTRATES to
                   the team's top scorers (stars finish the game).

OUTPUTS (coherent by construction)
  * per-player FINAL stat distributions (current box + simulated remainder),
  * team final-score distribution + win probability,
  * a `dynamics` report of which effects fired and how (inspectable),
  * raw samples for joint / live-SGP queries.

LEAK DISCIPLINE
  Reads ONLY the current snapshot (what has already happened) + leak-safe
  prior-form rates (season/l10). No future data. This is an IN-GAME estimator,
  so current-game box/rate is legitimate input.

GATING
  Pure function, no I/O, no global state. Importing/using it changes NOTHING in
  the live serve path. Wiring it into the router is a separate, gated step
  (CV_LIVE_SIM) — default OFF / byte-identical until validated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from src.sim.game_simulator import (
    LEAGUE_PACE_PER48,
    LEAGUE_PPP,
    STATS,
    _STAT_IDX,
    _SIGMA_TABLE,
    _build_player_cov,
    _draw_player_noise,
)

REG_PERIOD_SEC = 720          # 12 min
OT_PERIOD_SEC = 300           # 5 min
REG_TOTAL_SEC = 2880          # 48 min
PLAYERS_ON_COURT = 5


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------
@dataclass
class LivePlayerSim:
    player_id: int
    team: str
    name: str
    current: Dict[str, float]          # box so far
    proj_final: Dict[str, float]       # current + simulated remainder (mean)
    q10: Dict[str, float]
    q50: Dict[str, float]
    q90: Dict[str, float]
    exp_remaining_min: float
    samples: np.ndarray = field(repr=False, default=None)


@dataclass
class LiveGameSimResult:
    players: List[LivePlayerSim]
    home_score_samples: np.ndarray = field(repr=False, default=None)
    away_score_samples: np.ndarray = field(repr=False, default=None)
    home_win_prob: float = 0.0
    proj_home_score: float = 0.0
    proj_away_score: float = 0.0
    sec_remaining: float = 0.0
    dynamics: Dict[str, object] = field(default_factory=dict)
    n_sims: int = 0

    def player(self, pid: int) -> Optional[LivePlayerSim]:
        for p in self.players:
            if p.player_id == pid:
                return p
        return None


# ---------------------------------------------------------------------------
# Snapshot parsing helpers
# ---------------------------------------------------------------------------
def _clock_to_sec(clock) -> float:
    """'5:00' / '11:34.5' / 312 (sec) / None -> seconds remaining in the period."""
    if clock is None:
        return 0.0
    if isinstance(clock, (int, float)):
        return max(0.0, float(clock))
    s = str(clock).strip().upper().replace("PT", "").replace("M", ":").replace("S", "")
    try:
        if ":" in s:
            mm, ss = s.split(":")[:2]
            return max(0.0, float(mm) * 60.0 + float(ss))
        return max(0.0, float(s))
    except (ValueError, TypeError):
        return 0.0


def _sec_remaining(period: int, clock_sec: float) -> float:
    """Game seconds remaining. Regulation periods 1-4; OT periods >=5."""
    if period <= 4:
        return max(0.0, (4 - period) * REG_PERIOD_SEC + clock_sec)
    # In OT we only project the current OT period (don't speculate on further OTs).
    return max(0.0, clock_sec)


def _num(d: dict, key: str, default: float = 0.0) -> float:
    try:
        v = d.get(key, default)
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Remaining-minutes model — where the live dynamics live
# ---------------------------------------------------------------------------
def _remaining_minutes(players: List[dict], team_rem_min: float,
                       margin: float, sec_remaining: float,
                       dynamics: dict) -> np.ndarray:
    """Project each player's REMAINING minutes, applying foul/blowout/clutch
    dynamics, then renormalise to the team's remaining man-minutes
    (5 * remaining_game_minutes). Returns an array aligned with `players`.
    """
    n = len(players)
    base = np.zeros(n)
    rem_game_min = sec_remaining / 60.0

    for i, p in enumerate(players):
        proj_min = _num(p, "l10_min", 0.0) or _num(p, "proj_min", 0.0)
        if proj_min <= 0:
            proj_min = _num(p, "season_min", 24.0) or 24.0
        played = _num(p, "min", 0.0)
        oncourt = _num(p, "oncourt", 1.0 if p.get("is_starter") else 0.0)
        # Baseline: minutes left in their own projected workload, but they can't
        # play more than the game has left. A player currently ON the floor gets
        # at least a small floor of the remaining game.
        rem = max(0.0, proj_min - played)
        rem = min(rem, rem_game_min)
        if oncourt >= 1 and rem < 0.20 * rem_game_min:
            rem = 0.20 * rem_game_min   # on the floor now -> will keep playing
        base[i] = rem

    # ---- FOUL TROUBLE ----------------------------------------------------
    foul_hits = []
    for i, p in enumerate(players):
        pf = _num(p, "pf", 0.0)
        if pf >= 6:
            if base[i] > 0:
                foul_hits.append((p.get("name", p.get("player_id")), "fouled out", round(base[i], 1)))
            base[i] = 0.0
        elif pf == 5:
            # 1 foul from DQ: keep fewer minutes the more time is left (more risk).
            keep = 0.55 if sec_remaining > 360 else 0.80
            if base[i] > 0.1:
                foul_hits.append((p.get("name", p.get("player_id")), "5 fouls", f"x{keep:.2f}"))
            base[i] *= keep
        elif pf == 4 and sec_remaining > 600:
            base[i] *= 0.85
    if foul_hits:
        dynamics["foul_trouble"] = foul_hits

    # ---- BLOWOUT (garbage time) -----------------------------------------
    # Large margin + late clock -> starters pulled, bench absorbs.
    blowout_active = abs(margin) >= 18 and sec_remaining <= 480
    if blowout_active:
        pulled = []
        for i, p in enumerate(players):
            if p.get("is_starter") and base[i] > 0:
                new = base[i] * 0.45
                pulled.append((p.get("name", p.get("player_id")), round(base[i] - new, 1)))
                base[i] = new
        dynamics["blowout"] = {"margin": round(margin, 0), "starters_pulled": pulled}

    # ---- renormalise to team remaining man-minutes -----------------------
    team_target = team_rem_min
    s = base.sum()
    if s > 0 and team_target > 0:
        base = base * (team_target / s)
    return base


def _remaining_rates(players: List[dict], priors: Optional[Dict[int, Dict[str, float]]]) -> np.ndarray:
    """Per-player, per-stat REMAINING per-minute rate.

    Blend the current-game per-minute rate (what they're doing tonight) with a
    leak-safe prior per-minute rate (season/l10), weighting current-game more as
    minutes played accumulate (the validated in-game shrink intuition).
    Returns (n_players, n_stats).
    """
    n = len(players)
    rates = np.zeros((n, len(STATS)))
    for i, p in enumerate(players):
        played = _num(p, "min", 0.0)
        proj_min = _num(p, "l10_min", 0.0) or 24.0
        # weight on current-game rate grows with minutes played (cap 0.85)
        w_cur = min(0.85, played / 14.0) if played > 0 else 0.0
        prior = (priors or {}).get(int(p.get("player_id", -1)), {})
        for si, st in enumerate(STATS):
            cur_rate = (_num(p, st, 0.0) / played) if played > 0.5 else None
            # prior per-minute rate
            if st == "pts" and _num(p, "season_pts_per_min", 0.0) > 0:
                prior_rate = _num(p, "season_pts_per_min", 0.0)
            elif st in prior and proj_min > 0:
                prior_rate = float(prior[st]) / proj_min
            elif cur_rate is not None:
                prior_rate = cur_rate
            else:
                prior_rate = 0.0
            if cur_rate is None:
                rates[i, si] = prior_rate
            else:
                rates[i, si] = w_cur * cur_rate + (1.0 - w_cur) * prior_rate
    return rates


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
def simulate_rest_of_game(
    snapshot: dict,
    n_sims: int = 2000,
    seed: Optional[int] = 42,
    priors: Optional[Dict[int, Dict[str, float]]] = None,
    team_priors: Optional[Dict[str, float]] = None,
    anchor_final: Optional[Dict[int, Dict[str, float]]] = None,
) -> LiveGameSimResult:
    """Simulate the remainder of a live game into coherent FINAL player lines.

    snapshot: live game dict with keys home_team, away_team, home_score,
      away_score, period, clock, players=[{player_id,name,team,pts,reb,ast,
      fg3m,stl,blk,tov,min,pf,oncourt,is_starter,l10_min,season_pts_per_min}, ...].
    priors: optional {player_id: {stat: pregame_q50}} to anchor remaining rates.
    team_priors: optional {home_pace_per48, away_pace_per48, home_ppp, away_ppp}.
    """
    rng = np.random.default_rng(seed)
    dynamics: Dict[str, object] = {}

    home_team = str(snapshot.get("home_team", "HOME"))
    away_team = str(snapshot.get("away_team", "AWAY"))
    home_score = _num(snapshot, "home_score", 0.0)
    away_score = _num(snapshot, "away_score", 0.0)
    period = int(_num(snapshot, "period", 1) or 1)
    clock_sec = _clock_to_sec(snapshot.get("clock"))
    sec_remaining = _sec_remaining(period, clock_sec)
    elapsed = max(1.0, REG_TOTAL_SEC - sec_remaining) if period <= 4 else max(
        1.0, REG_TOTAL_SEC + (period - 4) * OT_PERIOD_SEC - sec_remaining)
    margin = home_score - away_score
    tp = team_priors or {}

    players = list(snapshot.get("players", []) or [])
    home_players = [p for p in players if str(p.get("team", "")).upper() == home_team.upper()]
    away_players = [p for p in players if str(p.get("team", "")).upper() == away_team.upper()]

    rem_game_min = sec_remaining / 60.0
    frac = sec_remaining / REG_TOTAL_SEC

    # CLUTCH detection (close + late) — concentrate remaining usage to top scorers.
    clutch = abs(margin) <= 6 and sec_remaining <= 360 and period >= 4
    if clutch:
        dynamics["clutch"] = {"margin": round(margin, 0), "sec_left": round(sec_remaining)}

    results: List[LivePlayerSim] = []
    team_score_samples = {home_team: None, away_team: None}

    for team_name, team_players in ((home_team, home_players), (away_team, away_players)):
        if not team_players:
            team_score_samples[team_name] = np.full(
                n_sims, home_score if team_name == home_team else away_score)
            continue

        cur_team_score = home_score if team_name == home_team else away_score
        cur_rate_pts = cur_team_score / elapsed                      # pts/sec so far

        # --- remaining minutes (dynamics) + rates FIRST, so the team total
        #     can be coupled to who is actually on the floor (availability flows
        #     into the score + win prob, not just into one player's line) -----
        team_rem_min = PLAYERS_ON_COURT * rem_game_min
        rem_min = _remaining_minutes(team_players, team_rem_min, margin if team_name == home_team
                                     else -margin, sec_remaining, dynamics)
        rates = _remaining_rates(team_players, priors)

        # CLUTCH usage concentration: boost the top-2 scorers' scoring rate,
        # damp the rest, keep total ~constant (zero-sum redistribution of shots).
        if clutch and len(team_players) > 2:
            cur_pts = np.array([_num(p, "pts", 0.0) for p in team_players])
            top = np.argsort(-cur_pts)[:2]
            boost = np.ones(len(team_players))
            for i in range(len(team_players)):
                boost[i] = 1.25 if i in top else 0.85
            rates[:, _STAT_IDX["pts"]] *= boost
            rates[:, _STAT_IDX["ast"]] *= boost
            dynamics.setdefault("clutch_usage", []).append(
                {"team": team_name, "finishers": [team_players[int(t)].get("name") for t in top]})

        # --- per-player remaining MEAN per stat ----------------------------
        # ANCHORED mode (anchor_final given, e.g. the routed-ensemble final): the
        # remaining mean = routed_final - current, so the sim's point estimate
        # matches the validated routed accuracy and the sim only ADDS the coherent
        # joint + win-prob + reactive distribution. RATE mode (no anchor): use the
        # standalone rate*minutes model (less accurate, fully self-contained).
        n_p = len(team_players)
        rem_means = np.zeros((n_p, len(STATS)))
        for i, p in enumerate(team_players):
            pid = int(p.get("player_id", -1))
            if anchor_final and pid in anchor_final:
                af = anchor_final[pid]
                for si, st in enumerate(STATS):
                    rem_means[i, si] = max(0.0, float(af.get(st, _num(p, st, 0.0))) - _num(p, st, 0.0))
            else:
                rem_means[i, :] = np.maximum(rates[i, :] * rem_min[i], 0.0)

        # --- remaining team points: BOTTOM-UP (sum of player production, which
        #     already reflects foul-out/blowout/clutch minutes) blended with the
        #     TOP-DOWN pace*ppp / live-rate estimate. Bottom-up is what makes the
        #     team total + win prob react when a star sits. -------------------
        bottom_up_mean = float(rem_means[:, _STAT_IDX["pts"]].sum())
        pace = tp.get(f"{'home' if team_name==home_team else 'away'}_pace_per48") or LEAGUE_PACE_PER48
        ppp = tp.get(f"{'home' if team_name==home_team else 'away'}_ppp") or LEAGUE_PPP
        prior_rem_mean = ppp * pace * frac
        w_live = min(0.80, elapsed / REG_TOTAL_SEC + 0.15)
        top_down_mean = max(0.0, w_live * (cur_rate_pts * sec_remaining) + (1 - w_live) * prior_rem_mean)
        # 55% bottom-up (availability-sensitive) / 45% top-down (pace anchor)
        rem_mean = max(0.0, 0.55 * bottom_up_mean + 0.45 * top_down_mean)
        r = max(2.0, 20.0 * frac)
        if rem_mean > 0.5:
            p_nb = r / (r + rem_mean)
            rem_team_pts = rng.negative_binomial(r, p_nb, size=n_sims).astype(float)
        else:
            rem_team_pts = np.zeros(n_sims)
        team_score_samples[team_name] = cur_team_score + rem_team_pts

        # --- per-player remaining stat draws (correlated noise) ------------
        rem_player_pts = np.zeros((n_sims, n_p))
        player_mat = np.zeros((n_sims, n_p, len(STATS)))
        # variance shrinks with remaining time: sigma scales ~ sqrt(frac)
        sig_scale = max(0.10, np.sqrt(max(frac, 1e-3)))
        for i, p in enumerate(team_players):
            sigma = np.array([_SIGMA_TABLE[s] for s in STATS]) * sig_scale
            cov = _build_player_cov(len(STATS), sigma, player_id=int(p.get("player_id", -1)))
            noise = _draw_player_noise(rng, n_sims, sigma, cov)
            mu = rem_means[i, :]                                     # remaining mean (anchored or rate)
            draws = mu[None, :] + noise
            draws = np.clip(draws, 0.0, None)
            rem_player_pts[:, i] = draws[:, _STAT_IDX["pts"]]
            player_mat[:, i, :] = draws

        # --- coherence: remaining player pts sum to remaining team pts -----
        sim_sum = rem_player_pts.sum(axis=1)
        safe_sum = np.where(sim_sum > 1.0, sim_sum, 1.0)
        ratio = np.where(sim_sum > 1.0, rem_team_pts / safe_sum, 1.0)
        ratio = np.clip(ratio, 0.5, 1.8)
        player_mat[:, :, _STAT_IDX["pts"]] *= ratio[:, None]

        # --- package (final = current box + remaining) ---------------------
        for i, p in enumerate(team_players):
            cur = {s: _num(p, s, 0.0) for s in STATS}
            final = player_mat[:, i, :] + np.array([cur[s] for s in STATS])[None, :]
            anchored_i = bool(anchor_final and int(p.get("player_id", -1)) in anchor_final)
            if anchored_i:
                # Point estimate = current + anchored remaining (== routed final),
                # so anchored mode is accuracy-neutral; the bands/joint below still
                # come from the simulated distribution. (pts uses the coherence-
                # renormed sample mean so it stays consistent with the team total.)
                proj_final = {s: (float(final[:, si].mean()) if s == "pts"
                                  else float(cur[s] + rem_means[i, si]))
                              for si, s in enumerate(STATS)}
            else:
                proj_final = {s: float(final[:, si].mean()) for si, s in enumerate(STATS)}
            q10 = {s: float(np.percentile(final[:, si], 10)) for si, s in enumerate(STATS)}
            q50 = {s: float(np.percentile(final[:, si], 50)) for si, s in enumerate(STATS)}
            q90 = {s: float(np.percentile(final[:, si], 90)) for si, s in enumerate(STATS)}
            results.append(LivePlayerSim(
                player_id=int(p.get("player_id", -1)),
                team=team_name,
                name=str(p.get("name", "")),
                current=cur,
                proj_final=proj_final,
                q10=q10, q50=q50, q90=q90,
                exp_remaining_min=float(rem_min[i]),
                samples=final,
            ))

    hs = team_score_samples[home_team]
    as_ = team_score_samples[away_team]
    win_prob = float((hs > as_).mean()) if hs is not None and as_ is not None else 0.5

    return LiveGameSimResult(
        players=results,
        home_score_samples=hs,
        away_score_samples=as_,
        home_win_prob=win_prob,
        proj_home_score=float(np.mean(hs)) if hs is not None else home_score,
        proj_away_score=float(np.mean(as_)) if as_ is not None else away_score,
        sec_remaining=sec_remaining,
        dynamics=dynamics,
        n_sims=n_sims,
    )
