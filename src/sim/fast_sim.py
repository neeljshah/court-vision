"""GPU-vectorized possession sim — same engine as basketball_sim, all N sims in parallel.

The reference engine (basketball_sim.simulate_game) loops in Python: ~11 ms/sim, 44 s for 4000
sims. This makes iterating on signals/calibration slow. This module runs the IDENTICAL possession
chain (role-aware usage, assist network, on-court defense, size-matchup, OREB continuation) as
batched torch tensor ops over all N sims at once, on CUDA when available. ~100x faster, so testing
and calibration sweeps are interactive.

It shares basketball_sim._finalize (anchor + matchup-defense + packaging) so the OUTPUT is identical
in structure and statistically equivalent to the reference (validated in validate_fast_sim.py).

  from sim.fast_sim import simulate_game_fast
  res = simulate_game_fast(TeamModel.from_cache("SAS"), TeamModel.from_cache("NYK"), n_sims=10000)
"""
from __future__ import annotations

import math
import os

import numpy as np

from .basketball_sim import (DEF_PERIM_SLOPE, DEF_RIM_SLOPE, DEF_SUPP_SLOPE, DEF_SUPP_LO, DEF_SUPP_HI,
                             USAGE_CONCENTRATION, TeamModel, _STATS, _def_supp_on, _finalize)

try:
    import torch
    _HAS_TORCH = True
except Exception:
    _HAS_TORCH = False

_FG_DEFAULT = (0.625, 0.455, 0.400, 0.355)   # rim, paint, mid, 3


def device() -> str:
    return "cuda" if (_HAS_TORCH and torch.cuda.is_available()) else "cpu"


class _FastTeam:
    """A team's rates as flat tensors indexed by local player index 0..P-1."""

    def __init__(self, tm: TeamModel, dev):
        self.tri = tm.tri
        self.pids = list(tm.rate)
        idx = {p: i for i, p in enumerate(self.pids)}

        def col(key, default=0.0):
            out = []
            for p in self.pids:
                v = tm.rate[p].get(key, default)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    v = default
                out.append(float(v))
            return torch.tensor(out, dtype=torch.float32, device=dev)

        self.use = col("use_per_min")
        self.tov_share = col("tov_share"); self.ft_share = col("ft_share")
        self.z = torch.stack([col("z_rim"), col("z_paint"), col("z_mid"), col("z_3")], 1)
        self.fg = torch.stack([col("fg_rim", _FG_DEFAULT[0]), col("fg_paint", _FG_DEFAULT[1]),
                               col("fg_mid", _FG_DEFAULT[2]), col("fg3_pct", _FG_DEFAULT[3])], 1)
        self.ft_pct = col("ft_pct", 0.75)
        self.ast = col("ast_per_min"); self.oreb = col("oreb_per_min"); self.dreb = col("dreb_per_min")
        self.stl = col("stl_per_min"); self.blk = col("blk_per_min"); self.pf = col("pf_per_min")
        self.self_create = col("self_create", 0.4); self.height = col("height", 78.4)
        self.int_d = col("int_d", 50.0); self.perim_d = col("perim_d", 50.0)
        self.supp = col("supp", 0.0)            # per-defender opp-PPP suppression (CV_AGENT_DEF_SUPP lever; 0 when OFF)
        self.ast_rate = float(tm.ast_rate_on_make); self.oreb_per_miss = float(tm.oreb_per_miss)
        self.tov_force = float(getattr(tm, "tov_force", 1.0))   # defensive turnover-forcing mult
        self.ft_force = float(getattr(tm, "ft_force", 1.0))     # defensive FT/foul-environment mult
        self.pace = float(tm.pace); self.P = len(self.pids)
        self.lineups = torch.tensor([[idx[p] for p in L] for L in tm.lineup_ids], dtype=torch.long, device=dev)
        lp = np.asarray(tm.lineup_p, dtype=np.float64); lp = lp / lp.sum()
        self.lineup_p = torch.tensor(lp, dtype=torch.float32, device=dev)
        # per-player context multiplier (home/road, B2B) from apply_context; 1.0 if not set
        pxfg = tm.player_xfg or {}
        self.xfg = torch.tensor([float(pxfg.get(p, 1.0)) for p in self.pids], dtype=torch.float32, device=dev)
        # REAL assist network (PBP): assist_W[scorer_local, assister_local] = feed count
        self.assist_W = torch.zeros(self.P, self.P, dtype=torch.float32, device=dev)
        for sc, feeders in (tm.assist_net or {}).items():
            if sc in idx:
                for ap, n in feeders.items():
                    if ap in idx:
                        self.assist_W[idx[sc], idx[ap]] = float(n)


def _samp_lineup(team, N, gen, dev):
    return team.lineups[torch.multinomial(team.lineup_p, N, replacement=True, generator=gen)]  # (N,5)


def _pick(weights, gen):
    """Per-row categorical over (N,K) weights -> (N,) chosen column index."""
    return torch.multinomial(weights + 1e-9, 1, generator=gen).squeeze(1)


def _possession(off, deff, ob, db, lo, ld, N, gen, dev, defense, def_supp=False):
    """One offensive possession (incl. OREB continuation) for all N sims; updates boxes in place.
    lo/ld = the offensive/defensive on-court 5 (sampled once per possession).
    ``def_supp`` (CV_AGENT_DEF_SUPP, default False) scales the make prob by the on-court defenders' mean
    supp; OFF => base_x untouched, no extra RNG => byte-identical to the pre-lever GPU path."""
    ar = torch.arange(N, device=dev)
    active = torch.ones(N, dtype=torch.bool, device=dev)
    for _ in range(4):                                       # OREB continuation guard
        w = off.use[lo] ** USAGE_CONCENTRATION               # role-aware usage concentration
        ul = _pick(w, gen); u = lo[ar, ul]
        rnd = torch.rand(N, generator=gen, device=dev)
        tov, ft = off.tov_share[u] * deff.tov_force, off.ft_share[u] * deff.ft_force   # DEFENSE forces TOV / foul env
        is_tov = active & (rnd < tov)
        is_ft = active & ~is_tov & (rnd < tov + ft)
        is_shot = active & ~is_tov & ~is_ft
        # turnover (+ steal)
        ob["tov"].scatter_add_(1, u[:, None], is_tov.float()[:, None])
        steal = is_tov & (torch.rand(N, generator=gen, device=dev) < 0.55)
        dl = _pick(deff.stl[ld], gen)
        db["stl"].scatter_add_(1, ld[ar, dl][:, None], steal.float()[:, None])
        # drawn-foul FT trip
        ob["fta"].scatter_add_(1, u[:, None], (is_ft.float() * 2)[:, None])
        ftm = ((torch.rand(N, generator=gen, device=dev) < off.ft_pct[u]).float()
               + (torch.rand(N, generator=gen, device=dev) < off.ft_pct[u]).float()) * is_ft.float()
        ob["ftm"].scatter_add_(1, u[:, None], ftm[:, None]); ob["pts"].scatter_add_(1, u[:, None], ftm[:, None])
        dlf = _pick(deff.pf[ld], gen)
        db["pf"].scatter_add_(1, ld[ar, dlf][:, None], is_ft.float()[:, None])
        # shot
        zp = off.z[u]; zone = _pick(zp, gen); three = zone == 3
        rim = (zone == 0) | (zone == 1)
        ob["fga"].scatter_add_(1, u[:, None], is_shot.float()[:, None])
        ob["fg3a"].scatter_add_(1, u[:, None], (is_shot & three).float()[:, None])
        fgz = off.fg[u].gather(1, zone[:, None]).squeeze(1)
        base_x = off.xfg[u]                                  # per-player context (home/road, B2B)
        if defense:                                          # DEFENSE: on-court defenders suppress
            int_oc = deff.int_d[ld].max(dim=1).values
            per_oc = deff.perim_d[ld].mean(dim=1)
            base_x = base_x * torch.where(rim, torch.clamp(1 - DEF_RIM_SLOPE * (int_oc - 50), 0.78, 1.12),
                                          torch.clamp(1 - DEF_PERIM_SLOPE * (per_oc - 50), 0.88, 1.08))
        if def_supp:                                         # DEFENDER-SUPPRESSION L1 lever (gated; no RNG)
            supp_oc = deff.supp[ld].mean(dim=1)
            base_x = base_x * torch.clamp(1 + DEF_SUPP_SLOPE * supp_oc, DEF_SUPP_LO, DEF_SUPP_HI)
        make = is_shot & (torch.rand(N, generator=gen, device=dev) < fgz * base_x)
        miss = is_shot & ~make
        pts = torch.where(three, 3.0, 2.0) * make.float()
        ob["fgm"].scatter_add_(1, u[:, None], make.float()[:, None])
        ob["fg3m"].scatter_add_(1, u[:, None], (make & three).float()[:, None])
        ob["pts"].scatter_add_(1, u[:, None], pts[:, None])
        # assist network: self-creators assisted less; assister picked by ast rate
        p_assist = off.ast_rate * torch.clamp(1.9 * (1 - off.self_create[u]), 0.5, 1.7)
        do_ast = make & (torch.rand(N, generator=gen, device=dev) < p_assist)
        aw_net = off.assist_W[u].gather(1, lo)               # REAL feeders of this scorer, on-court
        aw_net[ar, ul] = 0.0
        fb = off.ast[lo].clone(); fb[ar, ul] = 0.0           # ast-rate floor: who passes
        fb_n = fb / (fb.sum(1, keepdim=True) + 1e-9)
        net_n = aw_net / (aw_net.sum(1, keepdim=True) + 1e-9)
        aw = torch.where(aw_net.sum(1, keepdim=True) > 0, 0.7 * net_n + 0.3 * fb_n, fb_n)  # 70% real net + 30% floor
        al = _pick(aw, gen)
        ob["ast"].scatter_add_(1, lo[ar, al][:, None], do_ast.float()[:, None])
        # miss -> block? -> rebound
        prot_h = deff.height[ld].max(dim=1).values
        blkp = torch.clamp(deff.blk[ld].sum(dim=1) * 0.5, max=0.16)
        blkp = torch.where(rim, torch.clamp(blkp + 0.004 * torch.clamp(prot_h - 82, min=0.0), max=0.22), blkp)
        blocked = miss & ~three & (torch.rand(N, generator=gen, device=dev) < blkp)
        dlb = _pick(deff.blk[ld], gen)
        db["blk"].scatter_add_(1, ld[ar, dlb][:, None], blocked.float()[:, None])
        oreb = miss & (torch.rand(N, generator=gen, device=dev) < off.oreb_per_miss)
        olo = _pick(off.oreb[lo], gen)
        ob["oreb"].scatter_add_(1, lo[ar, olo][:, None], oreb.float()[:, None])
        dreb = miss & ~oreb
        dld = _pick(deff.dreb[ld], gen)
        db["dreb"].scatter_add_(1, ld[ar, dld][:, None], dreb.float()[:, None])
        active = oreb                                        # only OREB sims continue


def simulate_game_fast(home: TeamModel, away: TeamModel, n_sims: int = 10000, seed: int = 0,
                       anchor: bool = True, defense: bool = True, context: dict = None, dev: str = None,
                       dispersion: bool = True):
    if not _HAS_TORCH:
        raise RuntimeError("torch not available; use basketball_sim.simulate_game")
    if context is not None:
        from .basketball_sim import apply_context
        apply_context(home, away, context)               # sets per-player xfg (home/road, B2B) + pace
    dev = dev or device()
    gen = torch.Generator(device=dev); gen.manual_seed(seed)
    H, A = _FastTeam(home, dev), _FastTeam(away, dev)
    hp = getattr(home, "pace_mult", 1.0); ap = getattr(away, "pace_mult", 1.0)
    n_poss = int(round((home.pace * hp + away.pace * ap) / 2))
    hb = {k: torch.zeros(n_sims, H.P, device=dev) for k in _STATS}
    ab = {k: torch.zeros(n_sims, A.P, device=dev) for k in _STATS}
    dsupp = _def_supp_on()                       # CV_AGENT_DEF_SUPP lever (read once; False => byte-identical)
    for _ in range(n_poss):
        _possession(H, A, hb, ab, _samp_lineup(H, n_sims, gen, dev), _samp_lineup(A, n_sims, gen, dev), n_sims, gen, dev, defense, dsupp)
        _possession(A, H, ab, hb, _samp_lineup(A, n_sims, gen, dev), _samp_lineup(H, n_sims, gen, dev), n_sims, gen, dev, defense, dsupp)
    # to numpy samp dict keyed by global pid
    samp = {}
    for team, box in ((H, hb), (A, ab)):
        npbox = {k: box[k].cpu().numpy() for k in _STATS}
        for i, pid in enumerate(team.pids):
            samp[pid] = {k: npbox[k][:, i] for k in _STATS}
    ht = sum(samp[p]["pts"] for p in H.pids)
    at = sum(samp[p]["pts"] for p in A.pids)
    return _finalize(samp, ht, at, home, away, H.pids, A.pids, anchor, defense, dispersion, seed, n_poss)


if __name__ == "__main__":
    import sys, time
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    h, a = TeamModel.from_cache("SAS"), TeamModel.from_cache("NYK")
    print("device:", device())
    t = time.time(); res = simulate_game_fast(h, a, n_sims=10000, seed=1); dt = time.time() - t
    print(f"10000 sims in {dt:.2f}s ({1000 * dt / 10000:.3f} ms/sim)")
    asc = lambda s: str(s).encode("ascii", "replace").decode()
    for p, d in sorted(res.players.items(), key=lambda x: -x[1]["mean"]["pts"])[:5]:
        print(f"  {asc(d['name']):22s} {d['team']} pts {d['mean']['pts']:.1f} reb {d['reb_mean']:.1f} ast {d['mean']['ast']:.1f}")
    print(f"team totals: {h.tri} {res.home_total.mean():.1f}  {a.tri} {res.away_total.mean():.1f}")
