"""Highest-fidelity basketball simulation — the possession engine.

A data-driven, player-level Monte Carlo. Each possession is "used" by exactly one of the
5 on-court players (the shared scoring pie), with on-court lineups sampled from real stint
minutes — so teammate scoring competes for the same possessions and the correct (slightly
negative) teammate correlation EMERGES instead of being imposed by a ρ-matrix. This is the
fix for game_simulator's teammate-ρ 0.645-vs-(-0.011) bug.

Every mechanic is parameterized from data/cache/team_system/{player_rates.parquet,
team_rates.json} (built from boxscores + PBP; no broadcast CV). Context modulators
(rest/blowout/clutch/defender/scheme) are applied as rate multipliers — see signal_effects.

Public API:
  TeamModel.from_cache(tricode) -> TeamModel
  simulate_game(home, away, n_sims=1000, seed=0) -> GameSimResult

Pure/leak-free given the rate inputs. No I/O beyond loading the cache.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
ZONES = ("z_rim", "z_paint", "z_mid", "z_3")
_FG_FALLBACK = {"z_rim": 0.625, "z_paint": 0.455, "z_mid": 0.400, "z_3": 0.355}
_FG_COL = {"z_rim": "fg_rim", "z_paint": "fg_paint", "z_mid": "fg_mid"}
P_STEAL_ON_TOV = 0.55
MIN_MPG = 6.0           # rotation floor for sim eligibility
USAGE_CONCENTRATION = 1.25   # >1 routes more possessions to primary options (role-aware usage)
# DEFENSE MATTERS — the on-court defenders' ratings (INTERIOR_D / PERIMETER_D, which aggregate the
# whole defensive attribute vault) suppress the offense's make probability, relative to league-avg D (50).
DEF_RIM_SLOPE = 0.0024       # per-shot rim/paint make suppression per interior-D point above 50
DEF_PERIM_SLOPE = 0.0013     # per-shot mid/3 make suppression per perimeter-D point above 50
# anchor matchup: centered at the LEAGUE-AVERAGE TEAM defense (every team has a rim protector, so
# the average opposing team rim_d/perim_d is ~65, NOT the median-player 50) so an average opponent
# gives factor 1.0 (no bias). Slopes calibrated to the real-outcome backtest (backtest_defense.py).
REF_RIM_D = 65.0
REF_PERIM_D = 65.0
# calibrated on backtest_defense.py (real NYK/SAS outcomes): the defense adjustment reduces team
# scoring MAE 11.7->11.0 / RMSE 14.1->13.4 and matches the model-free bucket gradient (players score
# +0.42 vs weak D, -0.45 vs strong D). Slopes set conservatively (~1.5x) to avoid overfitting one
# in-sample season; the backtest sweep shows error keeps dropping past this but with growing bias.
RIM_ANCHOR_SLOPE = 0.0070    # anchor: a player's rim-share scoring dragged per opp team rim-D pt > REF
PERIM_ANCHOR_SLOPE = 0.0040  # anchor: perimeter-share scoring dragged per opp team perimeter-D pt > REF

# ── DEFENDER-SUPPRESSION L1 LEVER (P1.3, CV_AGENT_DEF_SUPP — the ONE cross-season-stable r=0.60 fidelity
# lever). `supp` (data/cache/team_system/defender_suppression.parquet) is the per-defender opponent-PPP delta
# (negative = suppresses the opponent). When CV_AGENT_DEF_SUPP is set, the on-court defenders' MEAN supp scales
# the make probability: base_x *= clip(1 + DEF_SUPP_SLOPE*supp_oc, LO, HI). Default-OFF => the supp data is never
# loaded and base_x is untouched => byte-identical (CPU + GPU). SHIPS only if it clears the sim walk-forward gate
# (scripts/team_system/gate_def_supp.py): improves on FIT (NYK/SAS) AND the CLE/DAL/BOS holdout, seed-stable, n_min.
DEF_SUPP_SLOPE = 1.0         # supp is already an opp-PPP delta; 1.0 = apply it directly (the gate sweeps this)
DEF_SUPP_LO, DEF_SUPP_HI = 0.85, 1.10   # clamp on the make-prob multiplier (symmetric-ish guardrail)
_TRUTHY_ENV = frozenset({"1", "true", "yes", "on", "y", "t"})


def _def_supp_on() -> bool:
    """True iff the CV_AGENT_DEF_SUPP lever flag is set (matches src.brain.flags.is_on semantics)."""
    return os.environ.get("CV_AGENT_DEF_SUPP", "").strip().lower() in _TRUTHY_ENV


def _scheme_on() -> bool:
    """True iff the CV_LLM_SCHEME prior layer flag is set (matches src.brain.flags.is_on semantics)."""
    return os.environ.get("CV_LLM_SCHEME", "").strip().lower() in _TRUTHY_ENV


@dataclass
class TeamModel:
    tri: str
    rate: dict                       # pid -> dict of rates
    pace: float
    ast_rate_on_make: float
    oreb_per_miss: float
    lineup_ids: list                 # list of (pid,pid,pid,pid,pid)
    lineup_p: np.ndarray             # sampling prob by minutes
    def_rtg: float = 113.3           # season defensive rating (for opp-defense modulator)
    ortg: float = 113.3              # season offensive rating (pts/100; anchors a realistic team total)
    tov_force: float = 1.0           # DEFENSIVE turnover-forcing mult (>1 = forces more; NYK 1.06)
    ft_force: float = 1.0            # DEFENSIVE FT/foul environment (>1 = allows more FT; NYK 1.07/SAS 0.94)
    rim_d: float = 50.0              # team rim protection (0-99; anchor matchup factor)
    perim_d: float = 50.0            # team perimeter defense (0-99; anchor matchup factor)
    mult: dict = field(default_factory=dict)   # team-level context multipliers (xfg/ft) — fallback
    player_xfg: dict = field(default_factory=dict)  # per-player xfg mult (entity-specific effects)
    pace_mult: float = 1.0
    assist_net: dict = field(default_factory=dict)  # scorer pid -> {assister pid: count} (real PBP network)

    @classmethod
    def from_cache(cls, tri: str, rates_df: pd.DataFrame = None, team_rates: dict = None, out_ids=None):
        """out_ids: same-day-unavailable player ids (the freshness lever). Excluded from the rotation so
        their minutes/usage re-route to the eligible rotation (lineups containing them are dropped, the
        rest re-normalized, the anchor re-pins the survivors). out_ids=None -> byte-identical (default)."""
        if rates_df is None:
            rates_df = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
        if team_rates is None:
            team_rates = json.load(open(os.path.join(TS, "team_rates.json")))
        out = set(int(x) for x in (out_ids or []))
        sub = rates_df[(rates_df.team == tri) & (rates_df.mpg >= MIN_MPG) & (~rates_df.pid.isin(out))]
        rate = {int(r.pid): r._asdict() for r in sub.itertuples(index=False)}
        attr = _attributes()                       # attach physical attributes per player
        rolz = _roles()                            # attach role propensities (usage/assist routing)
        rtg = _ratings()                           # attach defensive ratings (DEFENSE drives the sim)
        for pid in rate:
            a = attr.get(pid, {})
            rate[pid]["height"] = a.get("height", 78.4)
            rate[pid]["age_fatigue_w"] = a.get("age_fatigue_w", 0.3)
            rl = rolz.get(pid, {})
            rate[pid]["creation"] = rl.get("creation", 0.45)        # primary-creator propensity
            rate[pid]["self_create"] = rl.get("self_create", 0.40)  # share of own makes unassisted
            rate[pid]["pm_prop"] = rl.get("playmaking", 0.40)       # passing propensity
            rr = rtg.get(pid, {})
            rate[pid]["int_d"] = rr.get("int_d", 50.0)              # interior defense / rim protection
            rate[pid]["perim_d"] = rr.get("perim_d", 50.0)          # perimeter defense
        rec = _recency()                           # recency-weighted rates (current regime/form)
        for pid in rate:
            rr = rec.get(pid)
            if rr:
                rate[pid]["pts_pg_rec"] = rr["pts"]; rate[pid]["reb_pg_rec"] = rr["reb"]
                rate[pid]["ast_pg_rec"] = rr["ast"]; rate[pid]["mpg_rec"] = rr["mpg"]
        pbp = _pbp_knowledge()                     # PBP ground truth overrides estimates
        for pid in rate:
            if pid in pbp["self_create"]:
                rate[pid]["self_create"] = pbp["self_create"][pid]  # real unassisted-make share
        anet = {p: {ap: n for ap, n in pbp["net"].get(p, {}).items() if ap in rate} for p in rate}
        # DEFENDER-SUPPRESSION L1 lever (CV_AGENT_DEF_SUPP): attach per-defender supp ONLY when the flag is
        # set. OFF (default) => no key added, no parquet I/O => from_cache is byte-identical (the agent
        # byte-identity oracle and every existing sim test are untouched).
        if _def_supp_on():
            _supp = _defender_supp()
            for pid in rate:
                rate[pid]["supp"] = _supp.get(pid, 0.0)
        tr = team_rates[tri]
        # keep lineups whose 5 are all eligible rotation players
        elig = set(rate)
        lus, w = [], []
        for L in tr["lineups"]:
            ids = tuple(int(x) for x in L["ids"])
            if all(i in elig for i in ids):
                lus.append(ids); w.append(L["min"])
        if not lus:                  # fallback: top-5 by usage as one lineup
            top5 = tuple(sorted(rate, key=lambda p: -rate[p]["use_per_min"])[:5])
            lus, w = [top5], [1.0]
        p = np.array(w, dtype=float); p /= p.sum()
        # team defensive aggregates: rim protection is anchored by the best protector on the floor
        # (you only need one), perimeter D is distributed → minute-weighted mean.
        mins = {pid: max(rate[pid].get("mpg", 0) or 0.0, 1.0) for pid in rate}
        tot = sum(mins.values()) or 1.0
        wmean_int = sum(rate[q]["int_d"] * mins[q] for q in rate) / tot
        prot = [rate[q]["int_d"] for q in rate if mins[q] >= 15.0] or [wmean_int]
        rim_d = 0.5 * wmean_int + 0.5 * max(prot)   # rim identity = best protector + rotation depth
        perim_d = sum(rate[q]["perim_d"] * mins[q] for q in rate) / tot
        tdef = _team_defense().get(tri, {})
        model = cls(tri, rate, tr["pace"], tr["ast_rate_on_make"], tr["oreb_per_miss"], lus, p,
                    def_rtg=tr.get("def_rtg", 113.3), ortg=tr.get("ortg", 113.3),
                    tov_force=tdef.get("tov_force", 1.0), ft_force=tdef.get("ft_force", 1.0),
                    rim_d=rim_d, perim_d=perim_d, assist_net=anet)
        # LLM SCHEME-PRIOR layer (CV_LLM_SCHEME): apply bounded, named, confidence-weighted knob
        # nudges from the scout's cached artifact ONLY when the flag is set. OFF (default) => no
        # import, no I/O, no mutation => from_cache is byte-identical on CPU + GPU. Betting-mode
        # (leak-safe-only) is the conservative default; the harness/G4 call apply_scheme_priors
        # directly when measuring the full (scouting-inclusive) read.
        if _scheme_on():
            try:
                from sim.scheme_prior import apply_scheme_priors, load_scheme_adjustments
                _adj = load_scheme_adjustments(tri)
                if _adj:
                    apply_scheme_priors(model, _adj, betting_mode=True)
            except Exception as _exc:  # never let the optional layer break the base sim
                pass
        return model

    def sample_lineup(self, rng):
        return self.lineup_ids[rng.choice(len(self.lineup_ids), p=self.lineup_p)]


def _pick(ids, model, key, rng):
    w = np.array([model.rate[p].get(key, 0.0) or 0.0 for p in ids], dtype=float)
    if w.sum() <= 0:
        return ids[rng.integers(len(ids))]
    return ids[rng.choice(len(ids), p=w / w.sum())]


def _make_prob(r, zone):
    if zone == "z_3":
        return r.get("fg3_pct") or _FG_FALLBACK["z_3"]
    v = r.get(_FG_COL[zone])
    return v if (v is not None and not (isinstance(v, float) and np.isnan(v))) else _FG_FALLBACK[zone]


def _sample_zone(r, rng):
    p = np.array([max(0.0, r.get(z, 0.0) or 0.0) for z in ZONES])
    if p.sum() <= 0:
        p = np.array([0.3, 0.2, 0.2, 0.3])
    return ZONES[rng.choice(4, p=p / p.sum())]


def _possession(off: TeamModel, deff: TeamModel, on_off, on_def, box, rng, defense=True, def_supp=False) -> int:
    """Simulate one offensive possession; mutate box; return points scored.

    ``def_supp`` (CV_AGENT_DEF_SUPP, default False) folds the on-court defenders' mean opponent-PPP
    suppression into the make probability. OFF => no read, no base_x change, no extra RNG => byte-identical.
    """
    pts = 0
    for _ in range(4):                       # OREB continuation guard
        # role-aware usage: concentrate possessions toward primary options (a flat per-minute
        # split spreads scoring too evenly and under-routes stars). Superlinear in use_per_min.
        w = np.array([off.rate[p]["use_per_min"] for p in on_off], dtype=float) ** USAGE_CONCENTRATION
        u = on_off[rng.choice(5, p=w / w.sum())]
        r = off.rate[u]
        a = rng.random()
        tov_p = r["tov_share"] * deff.tov_force        # DEFENSE forces turnovers (NYK identity)
        if a < tov_p:
            box[u]["tov"] += 1
            if rng.random() < P_STEAL_ON_TOV:
                box[_pick(on_def, deff, "stl_per_min", rng)]["stl"] += 1
            return pts
        if a < tov_p + r["ft_share"] * off.mult.get("ft", 1.0) * deff.ft_force:  # drawn-foul FT trip (DEFENSE foul env)
            box[u]["fta"] += 2
            for _ in range(2):
                if rng.random() < r["ft_pct"]:
                    box[u]["ftm"] += 1; box[u]["pts"] += 1; pts += 1
            box[_pick(on_def, deff, "pf_per_min", rng)]["pf"] += 1
            return pts
        zone = _sample_zone(r, rng)
        box[u]["fga"] += 1
        three = zone == "z_3"
        if three:
            box[u]["fg3a"] += 1
        xfg = off.player_xfg.get(u) if off.player_xfg else None
        base_x = xfg if xfg is not None else off.mult.get("xfg", 1.0)
        rim = zone in ("z_rim", "z_paint")
        prot_h = max(deff.rate[p].get("height", 79.0) for p in on_def) if rim else 0.0
        # DEFENSE: the on-court defenders suppress the make, relative to league-average D (50).
        # Rim shots face the best interior defender on the floor; perimeter shots the lineup's
        # perimeter D. INTERIOR_D/PERIMETER_D aggregate the full defensive attribute vault.
        if defense and rim:
            rim_d_oc = max(deff.rate[p].get("int_d", 50.0) for p in on_def)
            base_x *= float(np.clip(1.0 - DEF_RIM_SLOPE * (rim_d_oc - 50.0), 0.78, 1.12))
        elif defense:
            perim_d_oc = sum(deff.rate[p].get("perim_d", 50.0) for p in on_def) / len(on_def)
            base_x *= float(np.clip(1.0 - DEF_PERIM_SLOPE * (perim_d_oc - 50.0), 0.88, 1.08))
        # DEFENDER-SUPPRESSION L1 lever (gated, default-OFF => byte-identical): the on-court defenders'
        # mean per-defender opponent-PPP suppression scales the make probability (no RNG consumed).
        if def_supp:
            supp_oc = sum(deff.rate[p].get("supp", 0.0) for p in on_def) / len(on_def)
            base_x *= float(np.clip(1.0 + DEF_SUPP_SLOPE * supp_oc, DEF_SUPP_LO, DEF_SUPP_HI))
        if rng.random() < _make_prob(r, zone) * base_x:
            box[u]["fgm"] += 1
            if three:
                box[u]["fg3m"] += 1; box[u]["pts"] += 3; pts += 3
            else:
                box[u]["pts"] += 2; pts += 2
            # assist network: a make is assisted less often when the scorer self-creates
            # (Brunson/SGA make their own); the assister is picked by his real assist rate.
            # The (1-self_create) factor is recentered (×1.67 at the ~0.4 league-mean self-create)
            # so the team assist TOTAL is preserved — only the per-shooter distribution shifts.
            p_assist = off.ast_rate_on_make * float(np.clip(1.9 * (1.0 - r.get("self_create", 0.4)), 0.5, 1.7))
            if rng.random() < p_assist:
                mates = [p for p in on_off if p != u]
                feeders = off.assist_net.get(u, {})          # REAL PBP feeders for this scorer
                net = np.array([feeders.get(p, 0.0) for p in mates], dtype=float)
                astpm = np.array([off.rate[p]["ast_per_min"] for p in mates], dtype=float)
                astpm = astpm / astpm.sum() if astpm.sum() > 0 else np.ones(len(mates)) / len(mates)
                # 70% real network + 30% ast-rate floor (so on-court backups aren't starved)
                aw = 0.7 * (net / net.sum()) + 0.3 * astpm if net.sum() > 0 else astpm
                box[mates[rng.choice(len(mates), p=aw / aw.sum())]]["ast"] += 1
            return pts
        # miss -> block? -> rebound
        blkp = min(0.16, sum(deff.rate[p]["blk_per_min"] for p in on_def) * 0.5)
        if rim:                                   # taller protector blocks more at the rim
            blkp = min(0.22, blkp + 0.004 * max(0.0, prot_h - 82.0))
        if not three and rng.random() < blkp:
            box[_pick(on_def, deff, "blk_per_min", rng)]["blk"] += 1
        if rng.random() < off.oreb_per_miss:
            box[_pick(on_off, off, "oreb_per_min", rng)]["oreb"] += 1
            continue                          # same offense continues
        box[_pick(on_def, deff, "dreb_per_min", rng)]["dreb"] += 1
        return pts
    return pts


_STATS = ("pts", "fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf")


def _anchor(d, key, target):
    """Rescale a stat's per-sim samples so its mean hits target (keeps shape + correlation)."""
    m = float(d[key].mean())
    if m > 0.1 and target > 0:
        d[key] *= float(np.clip(target / m, 0.4, 2.5))


def _anchor_reb(d, target):
    m = float((d["oreb"] + d["dreb"]).mean())
    if m > 0.1 and target > 0:
        f = float(np.clip(target / m, 0.4, 2.5))
        d["oreb"] *= f; d["dreb"] *= f


@dataclass
class GameSimResult:
    home_tri: str
    away_tri: str
    players: dict           # pid -> {name, team, mean:{stat:..}, q10/q50/q90 pts, samples:{pts,reb,ast}}
    home_total: np.ndarray
    away_total: np.ndarray
    home_win_prob: float


# DISPERSION CALIBRATION — the possession MC under-disperses INDIVIDUAL scoring (calibration_sim.py:
# player pts cov[q10,q90] 66% vs 80% target, 24% of actuals above q90) while team totals are well
# calibrated (79%). measure_dispersion.py sized the gap: real/sim game-SD ratio ~1.15 for starters,
# much higher for intermittent bench (a minutes-uncertainty artifact). Fix = a per-player idiosyncratic
# right-skewed shock, renormalized per sim to HOLD THE TEAM TOTAL (so the good team calibration +
# coherence survive), with per-player means re-pinned last (marginals cannot regress).
# sigmas calibrated against calibration_sim.py coverage (the team-total hold cancels a star's common-mode
# shock, so the raw sigma must exceed the target CV inflation to net ~15% on high-share scorers).
DISP_BASE = 0.20         # lognormal sigma for a full-minutes starter
DISP_MINUTE = 0.60       # extra sigma scaled by how far below 20 mpg a player is (minutes uncertainty)


def _apply_dispersion(samp, pids_h, pids_a, home, away, seed):
    rng = np.random.default_rng(seed + 7)
    n = len(next(iter(samp.values()))["pts"]) if samp else 0
    # stat groups: (component cols moved by one shock, hold-team-total?). reb = oreb+dreb share a shock.
    groups = [(("pts",), True), (("oreb", "dreb"), False), (("ast",), False)]
    for tm, pids in ((home, pids_h), (away, pids_a)):
        if not pids:
            continue
        lam = {p: float(np.clip(DISP_BASE + DISP_MINUTE * max(0.0, (20.0 - (tm.rate[p].get("mpg", 0) or 0.0)) / 20.0),
                                DISP_BASE, 0.55)) for p in pids}
        for cols, hold_total in groups:
            pre_mean = {p: {c: float(samp[p][c].mean()) for c in cols} for p in pids}
            agg_pre = np.sum([sum(samp[p][c] for c in cols) for p in pids], axis=0)  # per-sim team total of group
            for p in pids:                                  # one mean-1 right-skewed shock per player per group
                s = np.exp(lam[p] * rng.standard_normal(n) - 0.5 * lam[p] ** 2)
                for c in cols:
                    samp[p][c] = samp[p][c] * s
            if hold_total:                                  # hold team total per sim -> team dist preserved
                agg_post = np.sum([sum(samp[p][c] for c in cols) for p in pids], axis=0)
                scale = np.where(agg_post > 1e-6, agg_pre / np.maximum(agg_post, 1e-6), 1.0)
                for p in pids:
                    for c in cols:
                        samp[p][c] = samp[p][c] * scale
            for p in pids:                                  # re-pin each component mean LAST -> marginals exact
                for c in cols:
                    m = float(samp[p][c].mean())
                    if m > 1e-6 and pre_mean[p][c] > 0:
                        samp[p][c] *= pre_mean[p][c] / m
    return samp


_PLAYER_FX = None
_ATTR = None
_ROLES = None
_RATINGS = None
_RECENCY = None
# Recency blend for the anchor target: flat season rates over-predict PLAYOFF scoring +0.98/player
# (walkforward_recency.py); an exponentially recency-weighted rate (build_recency_rates.py, half-life
# ~10 games) self-adapts to the current regime. RECENCY_W blends flat<->recent (0=flat, 1=pure recent).
RECENCY_W = 0.6


_TEAM_DEF = None


def _team_defense():
    """Lazy-load team DEFENSIVE traits (turnover-forcing multiplier). {} if not built."""
    global _TEAM_DEF
    if _TEAM_DEF is None:
        fp = os.path.join(TS, "team_defense.parquet")
        _TEAM_DEF = {}
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                _TEAM_DEF[r.team] = {"tov_force": float(r.tov_force), "oreb_strength": float(r.oreb_strength),
                                     "ft_force": float(getattr(r, "ft_force", 1.0))}
    return _TEAM_DEF


_DEF_SUPP = None


def _defender_supp():
    """Lazy-load the per-defender opponent-PPP suppression (CV_AGENT_DEF_SUPP lever). {def_id: supp}; {} if
    not built. Negative supp = the defender suppresses opponent scoring (LeBron -0.067)."""
    global _DEF_SUPP
    if _DEF_SUPP is None:
        fp = os.path.join(TS, "defender_suppression.parquet")
        _DEF_SUPP = {}
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                _DEF_SUPP[int(r.def_id)] = float(r.supp)
    return _DEF_SUPP


_SECONDARY = None


def _secondary_targets():
    """Lazy-load real per-game means for the low-frequency count stats (blk/stl/fg3m/ftm/tov), so those
    props are Poisson-calibrated to the right FREQUENCY (the possession chain produces zero-clumped counts:
    sim P(Wemby>=1 blk) 60% vs 95% real). {} if not built -> chain samples kept (byte-identical)."""
    global _SECONDARY
    if _SECONDARY is None:
        fp = os.path.join(TS, "secondary_targets.parquet")
        _SECONDARY = {}
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                d = {s: float(getattr(r, s)) for s in ("blk", "stl", "fg3m", "ftm", "tov") if hasattr(r, s)}
                for s in ("blk", "fg3m", "ftm", "stl"):            # per-game variance for NB dispersion
                    if hasattr(r, f"{s}_var"):
                        d[f"{s}_var"] = float(getattr(r, f"{s}_var"))
                _SECONDARY[int(r.pid)] = d
    return _SECONDARY


def _recency():
    """Lazy-load recency-weighted per-game rates (pts/reb/ast/mpg). {} if not built."""
    global _RECENCY
    if _RECENCY is None:
        fp = os.path.join(TS, "recency_rates.parquet")
        _RECENCY = {}
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                _RECENCY[int(r.pid)] = {"pts": float(r.pts_pg_rec), "reb": float(r.reb_pg_rec),
                                        "ast": float(r.ast_pg_rec), "mpg": float(r.mpg_rec)}
    return _RECENCY


def _ratings():
    """Lazy-load per-player defensive ratings (INTERIOR_D, PERIMETER_D) so DEFENSE drives the sim.
    These aggregate the whole defensive attribute vault (block, opp-adj stops, fg suppression, size)."""
    global _RATINGS
    if _RATINGS is None:
        fp = os.path.join(TS, "player_ratings.parquet")
        _RATINGS = {}
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                _RATINGS[int(r.pid)] = {"int_d": float(r.INTERIOR_D), "perim_d": float(r.PERIMETER_D),
                                        "overall": float(r.OVERALL)}
    return _RATINGS


_PBP = None


def _pbp_knowledge():
    """Lazy-load PBP-mined ground truth: per-player real self-create share + the real assist network
    (who assists whom). Built by build_pbp_knowledge.py over every game. Empty if not built."""
    global _PBP
    if _PBP is None:
        _PBP = {"self_create": {}, "net": defaultdict(dict)}
        fp = os.path.join(TS, "pbp_player_knowledge.parquet")
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                _PBP["self_create"][int(r.pid)] = float(r.self_create_rate)
        nf = os.path.join(TS, "assist_network.parquet")
        if os.path.exists(nf):
            for r in pd.read_parquet(nf).itertuples(index=False):
                _PBP["net"][int(r.scorer)][int(r.assister)] = float(r.n)
    return _PBP


def _roles():
    """Lazy-load per-player role propensities (creation, self-create share, playmaking). {} if absent."""
    global _ROLES
    if _ROLES is None:
        fp = os.path.join(TS, "player_roles.parquet")
        _ROLES = {}
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                _ROLES[int(r.pid)] = {"creation": float(r.creation), "self_create": float(r.self_create),
                                      "playmaking": float(r.playmaking), "archetype": r.archetype}
    return _ROLES


def _attributes():
    """Lazy-load per-player physical attributes (height, age fatigue weight). {} if absent."""
    global _ATTR
    if _ATTR is None:
        fp = os.path.join(TS, "player_attributes.parquet")
        _ATTR = {}
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                _ATTR[int(r.pid)] = {"height": float(r.height_in), "age_fatigue_w": float(r.age_fatigue_w),
                                     "size_z": float(r.size_z)}
    return _ATTR


def _player_effects():
    """Lazy-load per-player entity effects (home/road eFG mult). {} if not built yet."""
    global _PLAYER_FX
    if _PLAYER_FX is None:
        fp = os.path.join(TS, "player_effects.parquet")
        _PLAYER_FX = {}
        if os.path.exists(fp):
            for r in pd.read_parquet(fp).itertuples(index=False):
                _PLAYER_FX[int(r.pid)] = {"home": r.home_xfg, "road": r.road_xfg}
    return _PLAYER_FX


def apply_context(home: TeamModel, away: TeamModel, context: dict) -> None:
    """Set rate multipliers from the verified effects. TEAM-level effects (B2B, opponent
    defense) multiply a team base; the ENTITY-SPECIFIC home/road effect is per-PLAYER
    (each shooter's own shrunk multiplier from player_effects.parquet) — so Bridges' road
    bump and Brunson's home lean are applied individually, not as one league constant.
    context keys: home_b2b/away_b2b, neutral_site.
    """
    fx = _player_effects()
    for off, deff, is_home in ((home, away, True), (away, home, False)):
        team_x = 1.0; ft = 1.0; pace = 1.0
        b2b = bool(context.get("home_b2b" if is_home else "away_b2b"))
        if b2b:
            pace *= 0.997                                          # B2B pace dip (team-level)
        if not context.get("neutral_site"):
            ft *= 1.010 if is_home else 0.990                     # home FT tilt (team-level)
        # (opponent defense is no longer a flat team multiplier here — it is now applied per-shot
        #  from the on-court defenders' ratings in _possession + the anchor matchup factor, so it
        #  reflects WHO is on the floor and the shooter's shot profile, not one season constant.)
        side = "home" if is_home else "road"
        league_hr = 1.010 if is_home else 0.990
        pxfg = {}
        for pid in off.rate:
            hr = league_hr if context.get("neutral_site") else fx.get(pid, {}).get(side, league_hr)
            # age × B2B interaction: older players decline MORE on no rest
            b2b_pid = 1.0 - (0.008 + 0.005 * off.rate[pid].get("age_fatigue_w", 0.3)) if b2b else 1.0
            pxfg[pid] = team_x * hr * b2b_pid                     # entity-specific × interactions × team
        off.mult = {"xfg": team_x * league_hr * (0.989 if b2b else 1.0), "ft": ft}
        off.player_xfg = pxfg
        off.pace_mult = pace


def _matchup_mult(r: dict, opp: TeamModel, defense: bool) -> float:
    """Anchor-level defense: a player's scoring is dragged by the OPPOSING team's defense,
    weighted by his shot profile (rim scorers feel rim protection; shooters feel perimeter D),
    PLUS the opponent's FT/foul environment scaled by the player's FT-point reliance (a foul-drawer
    scores more vs a high-fouling defense, fewer vs one that suppresses FTs). Centered at
    league-average D (50) / ft_force 1.0 so vs an average defense the prediction is his season avg."""
    if not defense:
        return 1.0
    rim = (r.get("z_rim", 0) or 0) + (r.get("z_paint", 0) or 0)
    per = (r.get("z_mid", 0) or 0) + (r.get("z_3", 0) or 0)
    s = rim + per
    if s <= 0:
        return 1.0
    drag = (rim * RIM_ANCHOR_SLOPE * (opp.rim_d - REF_RIM_D) + per * PERIM_ANCHOR_SLOPE * (opp.perim_d - REF_PERIM_D)) / s
    # FT-defense: only the FT-point portion of his scoring scales by the opponent's foul environment.
    ft_factor = 1.0 + (r.get("ft_pts_share", 0.0) or 0.0) * (getattr(opp, "ft_force", 1.0) - 1.0)
    return float(np.clip((1.0 - drag) * ft_factor, 0.85, 1.12))


def simulate_game(home: TeamModel, away: TeamModel, n_sims: int = 1000, seed: int = 0,
                  context: dict = None, anchor: bool = True, defense: bool = True,
                  dispersion: bool = True) -> GameSimResult:
    rng = np.random.default_rng(seed)
    if context is not None:
        apply_context(home, away, context)
    hp = getattr(home, "pace_mult", 1.0); ap = getattr(away, "pace_mult", 1.0)
    n_poss = int(round((home.pace * hp + away.pace * ap) / 2))
    pids_h, pids_a = list(home.rate), list(away.rate)
    allp = pids_h + pids_a
    dsupp = _def_supp_on()                       # CV_AGENT_DEF_SUPP lever (read once; False => byte-identical)
    # per-sim accumulators
    samp = {p: {s: np.zeros(n_sims) for s in _STATS} for p in allp}
    ht = np.zeros(n_sims); at = np.zeros(n_sims)
    for s in range(n_sims):
        box = {p: {k: 0.0 for k in _STATS} for p in allp}
        for _ in range(n_poss):
            ht[s] += _possession(home, away, home.sample_lineup(rng), away.sample_lineup(rng), box, rng, defense, dsupp)
            at[s] += _possession(away, home, away.sample_lineup(rng), home.sample_lineup(rng), box, rng, defense, dsupp)
        for p in allp:
            for k in _STATS:
                samp[p][k][s] = box[p][k]
    return _finalize(samp, ht, at, home, away, pids_h, pids_a, anchor, defense, dispersion, seed, n_poss)


def _finalize(samp, ht, at, home, away, pids_h, pids_a, anchor, defense, dispersion=True, seed=0, n_poss=0):
    """Anchor each player-stat distribution to his (defense-adjusted) season level and package
    the result. Shared by the reference engine and the GPU engine so both behave identically."""
    if anchor:                                   # stars hit full season avg (× opponent defense); bench absorbs
        for tm, pids, raw_tot, opp in ((home, pids_h, float(ht.mean()), away), (away, pids_a, float(at.mean()), home)):
            cx = tm.player_xfg or {}
            # blend flat season pts with the recency-weighted pts (current regime: playoffs score below
            # the season rate -> recency self-corrects; flat fallback for players w/o a recency rate)
            def _pts_base(p):
                r = tm.rate[p]; rec = r.get("pts_pg_rec")
                return (1 - RECENCY_W) * r["pts_pg"] + RECENCY_W * rec if rec is not None else r["pts_pg"]
            tgt = {p: _pts_base(p) * cx.get(p, 1.0) * _matchup_mult(tm.rate[p], opp, defense) for p in pids}
            core = sorted(pids, key=lambda p: -tgt[p])[:8]   # the ~8 who carry a game
            bench = [p for p in pids if p not in core]
            core_sum = sum(tgt[p] for p in core)
            # NOTE: this over-predicts team totals ~+4.5 on a playoff-weighted eval. Two anchor-side fixes
            # were TRIED and BOTH made it WORSE (reverted): (a) a measured ortg*pace target -> +6.8 (ortg is
            # regular-season-weighted, playoffs score below it); (b) dropping the *1.02 floor -> +11.2,
            # because the _anchor rescale CLIP [0.4,2.5] won't scale tiny-target bench players to ~0, so
            # they retain ~40% of their raw points and the total exceeds T non-linearly. The real lever is
            # the bench-clip + the stars-exact constraint (pytest pins Brunson=26.1), not this max(). A
            # uniform 50/50 raw/anchor blend zeroes the bias (backtest_sim_accuracy.py s=0.5) but haircuts
            # correctly-anchored stars (Wemby 24.3->22.2). Left as a documented limit; trust spread not total.
            T = max(raw_tot, core_sum * 1.02)
            bsum = sum(tgt[p] for p in bench) or 1.0
            for p in core:
                _anchor(samp[p], "pts", tgt[p])              # full season average (× context)
            for p in bench:
                _anchor(samp[p], "pts", max(0.0, T - core_sum) * tgt[p] / bsum)
            for p in pids:                                   # reb/ast to season per-game, recency-blended
                r = tm.rate[p]
                reb_s = (r["oreb_per_min"] + r["dreb_per_min"]) * r["mpg"]; ast_s = r["ast_per_min"] * r["mpg"]
                rrec, arec = r.get("reb_pg_rec"), r.get("ast_pg_rec")
                reb_t = (1 - RECENCY_W) * reb_s + RECENCY_W * rrec if rrec is not None else reb_s
                ast_t = (1 - RECENCY_W) * ast_s + RECENCY_W * arec if arec is not None else ast_s
                _anchor_reb(samp[p], reb_t)
                _anchor(samp[p], "ast", ast_t)
                # SECONDARY counting stats -> season per-game (centered, honest marginals for the full
                # prop universe: 3PM/STL/BLK/TOV/FTM/PF). Derived from the same per-min rates the chain
                # uses, so the means are consistent; the joint shape (rank-corr) survives the rescale.
                mpg = r.get("mpg", 0) or 0.0
                use_pg = (r.get("use_per_min", 0) or 0.0) * mpg
                _anchor(samp[p], "stl", (r.get("stl_per_min", 0) or 0.0) * mpg)
                _anchor(samp[p], "blk", (r.get("blk_per_min", 0) or 0.0) * mpg)
                _anchor(samp[p], "pf", (r.get("pf_per_min", 0) or 0.0) * mpg)
                _anchor(samp[p], "tov", use_pg * (r.get("tov_share", 0) or 0.0))
                _anchor(samp[p], "fg3m", use_pg * (r.get("shot_share", 0) or 0.0)
                        * (r.get("fg3_rate", 0) or 0.0) * (r.get("fg3_pct", 0) or 0.0))
                _anchor(samp[p], "ftm", use_pg * (r.get("ft_share", 0) or 0.0) * 2.0 * (r.get("ft_pct", 0) or 0.0))
        if dispersion:                               # calibrate per-player spread (team total held)
            _apply_dispersion(samp, pids_h, pids_a, home, away, seed)
        # COUNT-STAT CALIBRATION: the possession chain produces zero-clumped low-frequency counts (sim
        # P(Wemby>=1 blk) 60% vs 95% real). Re-sample blk/fg3m/ftm at the player's REAL per-game mean ->
        # correct frequency + tail + mean (fixes the phantom 'under blocks/threes' edges). Marginal-correct
        # (the prop is the marginal); the weak cross-stat correlation is traded for honest single-prop pricing.
        # Default = Poisson. CV_COUNT_NB=1 upgrades over-dispersed counts (var>mean) to a NEGATIVE BINOMIAL at
        # the real (mean,var): real ftm is over-dispersed 1.8x + zero-inflated (P>=1 .64 vs Poisson .76); NB
        # matches both -> ftm shapeErr 8.0->5.3% (blk/fg3m -0.7/-0.8pp), no mean change (NB mean=lam).
        # CV_COUNT_STL=1 ALSO overrides stl: the chain over-clumps stl zeros (chain shapeErr 5.8% vs Poisson
        # 2.7%; stl disp 1.06 so it stays Poisson under the 1.5 gate) -- the old 'stl is chain-calibrated'
        # assumption was false. Self-limiting: var<=1.5*mean -> Poisson.
        nb = os.environ.get("CV_COUNT_NB", "0") == "1"
        override = ["blk", "fg3m", "ftm"] + (["stl"] if os.environ.get("CV_COUNT_STL", "0") == "1" else [])
        sec = _secondary_targets()
        if sec:
            prng = np.random.default_rng(seed + 777)
            ncount = len(samp[pids_h[0]]["pts"]) if pids_h else 0
            for p in pids_h + pids_a:
                tg = sec.get(p)
                if not tg or ncount == 0:
                    continue
                for st in override:
                    lam = tg.get(st)
                    if lam is None or lam < 0:
                        continue
                    m = max(float(lam), 0.0)
                    var = tg.get(f"{st}_var") if nb else None
                    # over-dispersion gate: require var/mean > 1.5 (~+1.5 sigma above Poisson noise at n~20,
                    # std(var/mean)~sqrt(2/(n-1))) so NB fires only on GENUINE over-dispersion, not a noisy
                    # low-count estimate -> protects blk (disp~1.1, already Poisson-calibrated) from a wobble.
                    thr = float(os.environ.get("CV_COUNT_NB_THR", "1.50"))
                    if nb and var is not None and m > 0 and var > m * thr:    # over-dispersed -> NB(mean,var)
                        rr = m * m / (var - m); pp = rr / (rr + m)
                        samp[p][st] = prng.negative_binomial(max(rr, 1e-6), min(max(pp, 1e-6), 1.0), ncount).astype(float)
                    else:
                        samp[p][st] = prng.poisson(m, ncount).astype(float)
        ht = sum(samp[p]["pts"] for p in pids_h)
        at = sum(samp[p]["pts"] for p in pids_a)
    rates = {**home.rate, **away.rate}
    players = {}
    for p in pids_h + pids_a:
        pts = samp[p]["pts"]; reb = samp[p]["oreb"] + samp[p]["dreb"]; ast = samp[p]["ast"]
        players[p] = {
            "name": rates[p]["player"], "team": rates[p]["team"],
            "mean": {k: float(samp[p][k].mean()) for k in _STATS},
            "reb_mean": float(reb.mean()),
            "q10": float(np.quantile(pts, 0.1)), "q50": float(np.quantile(pts, 0.5)),
            "q90": float(np.quantile(pts, 0.9)),
            # full per-sim box so the prop engine can derive EVERY prop + combo + threshold from the joint
            "samples": {**{k: samp[p][k] for k in _STATS}, "reb": reb},
        }
    return GameSimResult(home.tri, away.tri, players, ht, at, float((ht > at).mean()))
