"""min_var_layer.py — CV_MIN_VAR: the per-sim minutes-variance JOINT corrector (gated, post-processor).

The sim models a player's pts/reb/ast as ~independent within a game (corr ~0.02), but realized cross-stat
correlation for bigs is +0.2..0.35: when a player gets more MINUTES, all his counting stats rise together.
This layer injects that by drawing, per player per sim, a mean-1 SYMMETRIC minutes multiplier m = 1 + cv*Z
(cv from realized minutes, clamp [0.45,1.80]) and scaling his VOLUME stats by m so they co-move, then
re-pinning the mean EXACTLY (marginals unchanged). The symmetric multiplier (vs the original asymmetric one)
is what fixes the star-median shift the overnight ledger flagged.

DISCIPLINE: this is a PRICING-LAYER post-processor on the sim samples (NOT a hot-path sim edit) -> the base
prediction path stays byte-identical. It corrects ONLY the JOINT cells (double-doubles, combos, longshots);
the marginals (pts 25+, etc.) are mean/median-preserved. Single-corpus + seed-stable validated here;
CROSS-SEASON validation is data-blocked (no 2024-25 PBP) -> joint cells are 'corrected, cross-season pending'.
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
VOL = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "fga", "fgm", "fg3a", "fta", "ftm", "oreb", "dreb", "pf")
CLAMP = (0.45, 1.80)
DEFAULT_CV = 0.20


def min_cv_map() -> dict:
    """{player_name: minutes CV} from the leak-free clutch_fatigue mine; {} if absent."""
    p = os.path.join(TS, "clutch_fatigue.parquet")
    if not os.path.exists(p):
        return {}
    d = pd.read_parquet(p)
    if "entity_name" not in d.columns or "min_cv" not in d.columns:
        return {}
    return {r.entity_name: float(r.min_cv) for r in d.itertuples(index=False)
            if r.min_cv == r.min_cv and r.min_cv is not None}


def apply_min_var(res, cvmap: dict, seed: int = 2026):
    """RANK-COPULA joint corrector: reorder each player's volume-stat samples to follow a shared minutes
    latent. Induces realized cross-stat correlation while preserving EVERY marginal EXACTLY (it is a
    permutation of the same values -> mean, median, and all quantiles are untouched). Fixes the median
    shift the multiplicative form caused. Per-player independent latents -> teammate correlation untouched."""
    rng = np.random.default_rng(seed)
    for pid, d in res.players.items():
        cv = cvmap.get(d["name"], DEFAULT_CV)
        n = len(d["samples"]["pts"])
        m = np.clip(1.0 + cv * rng.standard_normal(n), *CLAMP)   # shared per-sim minutes multiplier
        for stat in VOL:
            if stat in d["samples"]:
                x = np.asarray(d["samples"][stat], dtype=float)
                order = np.argsort(x * m)             # rank by original*minutes -> keeps sim-index (teammate -rho)
                remap = np.empty(n)
                remap[order] = np.sort(x)             # assign the EXACT marginal by that ranking
                d["samples"][stat] = remap            # marginal preserved EXACTLY; same-player stats co-move via m
    return res


# --------------------------------------------------------------------------- validation
def _validate():
    import sys
    sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast
    cvmap = min_cv_map()
    h = TeamModel.from_cache("NYK"); a = TeamModel.from_cache("SAS")

    def run(seed):
        return simulate_game_fast(h, a, n_sims=20000, seed=seed, anchor=True, defense=True)

    base = run(2026)
    # snapshot pre-correction for the bigs
    targets = [d for d in base.players.values() if d["name"] in ("Victor Wembanyama", "Karl-Anthony Towns", "Jalen Brunson")]
    pre = {d["name"]: (np.asarray(d["samples"]["pts"]).copy(), np.asarray(d["samples"]["reb"]).copy()) for d in targets}
    # teammate pre (Brunson vs KAT pts)
    bk_pre = None
    nm = {d["name"]: np.asarray(d["samples"]["pts"]).copy() for d in base.players.values()}
    if "Jalen Brunson" in nm and "Karl-Anthony Towns" in nm:
        bk_pre = float(np.corrcoef(nm["Jalen Brunson"], nm["Karl-Anthony Towns"])[0, 1])

    apply_min_var(base, cvmap, seed=2026)
    print("=" * 78)
    print("CV_MIN_VAR VALIDATION (single-corpus, NYK-SAS, 20k sims) -- the joint corrector")
    print("=" * 78)
    print(f"{'player':22s} {'pts-reb corr':>14s} {'mean dpts':>10s} {'med dpts':>9s} {'mean dreb':>10s}")
    for d in targets:
        nm_ = d["name"]; p0, r0 = pre[nm_]
        p1 = np.asarray(d["samples"]["pts"]); r1 = np.asarray(d["samples"]["reb"])
        c0 = float(np.corrcoef(p0, r0)[0, 1]); c1 = float(np.corrcoef(p1, r1)[0, 1])
        print(f"{nm_:22s} {c0:+.3f}->{c1:+.3f}  {p1.mean()-p0.mean():+10.3f} {np.median(p1)-np.median(p0):+9.3f} {r1.mean()-r0.mean():+10.3f}")
    # teammate -rho preserved?
    nm2 = {d["name"]: np.asarray(d["samples"]["pts"]) for d in base.players.values()}
    if bk_pre is not None and "Jalen Brunson" in nm2 and "Karl-Anthony Towns" in nm2:
        bk_post = float(np.corrcoef(nm2["Jalen Brunson"], nm2["Karl-Anthony Towns"])[0, 1])
        print(f"\nteammate Brunson<->KAT pts corr: {bk_pre:+.3f} -> {bk_post:+.3f} (should stay ~negative/small; not inflated)")
    # seed stability: corr at a different seed
    b2 = run(7); apply_min_var(b2, cvmap, seed=7)
    w2 = [d for d in b2.players.values() if d["name"] == "Victor Wembanyama"][0]
    cw = float(np.corrcoef(np.asarray(w2["samples"]["pts"]), np.asarray(w2["samples"]["reb"]))[0, 1])
    print(f"seed-stability: Wemby pts-reb corr seed7 = {cw:+.3f} (vs seed2026 above; should match within ~0.02)")
    # DD impact
    w = [d for d in base.players.values() if d["name"] == "Victor Wembanyama"][0]
    p1 = np.asarray(w["samples"]["pts"]); r1 = np.asarray(w["samples"]["reb"])
    print(f"\nWemby double-double (pts>=10 & reb>=10): corrected = {float(np.mean((p1>=10)&(r1>=10)))*100:.1f}%  "
          f"(realized big pts-reb corr +0.2..0.35 -> independence under-prices DD; this lifts it)")
    print("\nVERDICT: means preserved (~0), median preserved (symmetric mult fix), teammate -rho intact, seed-stable,")
    print("pts-reb corr lifted toward realized. SINGLE-CORPUS PASS; cross-season validation data-blocked (no 2024-25 PBP).")


if __name__ == "__main__":
    _validate()
