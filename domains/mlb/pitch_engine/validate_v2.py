"""domains.mlb.pitch_engine.validate_v2 -- does the RELIEVER SEAM fix v1's named
worst bucket (inn7 | home-lead over-projection)?

WALK-FORWARD (leak-free): every table -- selection, outcome, tiers, base-out
transition, AND the v2 additions (RemovalModel, RelieverPA, reliever cadence) -- is
fit on 2023+2024+2025 and applied to the held-out 2026 season (wholly later: zero
eval-season info). The v1 and v2 sims share the IDENTICAL selection/outcome/
transition tables and the SAME per-game seed, so any PIT/CRPS difference is the
reliever seam and nothing else.

Comparison (per eval game): snapshot start-of-inning-7 with the real score,
simulate the remainder under v1 (starter pitches on) and v2 (empirical starter
removal -> pooled reliever dist), PIT the realized final margin, bucket by the
home margin entering inning 7 (mb: 0 away-lead .. 2 home-lead). inn7|m2 IS the named
home-lead bucket. Also a pooled full-game margin PIT + CRPS vs a climatology Normal.

VERDICT is distributional calibration ONLY (PIT uniformity_dev, CRPS) -- no dollars,
no market, edge_claimed:false. A seam that does NOT reduce the inn7|m2 uniformity
deviation is reported plainly as such.

INVARIANTS: domains-only; corpus READ-ONLY; ASCII; threads<=4; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_validate_v2.py -q
CLI: python -m domains.mlb.pitch_engine.validate_v2 [--games N] [--sims N]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import corpus as C
from domains.mlb.pitch_engine import bullpen as bp
from domains.mlb.pitch_engine.selection import SelectionModel
from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel
from domains.mlb.pitch_engine.game_sim import BaseOutTransition, simulate_game, GameStart
from domains.mlb.pitch_engine.game_sim_v2 import simulate_game_v2
from domains.mlb.pitch_engine.validate import _lineups, _slot_dists
from domains.basketball_nba.sim2.simulator import crps_ensemble, crps_gaussian, pit_value

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "mlb_pitch_engine_v2.json"
FIT_SEASONS = (2023, 2024, 2025)
EVAL_SEASON = 2026
_COLS = list(C._PITCH_COLS) + ["home_score", "away_score", "game_date"]


def _pit_stat(vals: List[float]) -> dict:
    v = np.asarray(vals, dtype=float)
    if len(v) == 0:
        return {"n": 0, "mean_pit": None, "uniformity_dev": None}
    dev = max(abs((v <= q).mean() - q) for q in np.linspace(0.1, 1.0, 10))
    return {"n": int(len(v)), "mean_pit": round(float(v.mean()), 4),
            "uniformity_dev": round(float(dev), 4)}


def compare_snapshot(pa_away, pa_home, rp_a, rp_h, trans, removal, fh, fa,
                     st: Optional[GameStart], seed: int, n: int) -> Tuple[float, float]:
    """(pit_v1, pit_v2) of realized final margin fh-fa for one game/snapshot."""
    h1, a1 = simulate_game(pa_away, pa_home, trans, n=n, seed=seed, start=st)
    h2, a2 = simulate_game_v2(pa_away, pa_home, rp_a, rp_h, trans, removal,
                              n=n, seed=seed, start=st)
    tgt = float(fh - fa)
    return (pit_value((h1 - a1).astype(float), tgt),
            pit_value((h2 - a2).astype(float), tgt))


def _fit(seasons):
    parts = [C.load_pitch_frame(y, cols=_COLS) for y in seasons]
    tr_pitch = pd.concat(parts, ignore_index=True)
    del parts
    tr_pa = bp.mark_context(C.build_pa_frame(tr_pitch))
    tiers = BatterTiers.fit(tr_pa)
    sel = SelectionModel.fit(tr_pitch)
    out = OutcomeModel.fit(tr_pitch, tiers)
    trans = BaseOutTransition.fit(tr_pa)
    removal = bp.RemovalModel.fit(tr_pa)
    cad = bp.reliever_cadence(tr_pa)
    relpa = bp.RelieverPA.fit(tr_pa, tiers, cad)
    m = tr_pa.groupby("game_pk")[["post_home_score", "post_away_score"]].max()
    margins = (m["post_home_score"] - m["post_away_score"]).to_numpy()
    base_norm = (float(margins.mean()), float(margins.std()))
    del tr_pitch, tr_pa
    return sel, out, tiers, trans, removal, relpa, base_norm


def run(n_games: int = 125, n_sims: int = 1500, fit_seasons=FIT_SEASONS,
        eval_season: int = EVAL_SEASON, sample_seed: int = 2) -> dict:
    sel, out, tiers, trans, removal, relpa, base_norm = _fit(fit_seasons)
    mu_m, sd_m = base_norm
    te_pa = bp.mark_context(C.build_pa_frame(C.load_pitch_frame(eval_season, cols=_COLS)))
    fresh = bp.bullpen_freshness(te_pa, bp.reliever_cadence(te_pa))

    gids = te_pa["game_pk"].drop_duplicates()
    gids = gids.sample(min(n_games, len(gids)), random_state=sample_seed).tolist()
    snap1: Dict[str, list] = {}; snap2: Dict[str, list] = {}
    pit_full1: List[float] = []; pit_full2: List[float] = []
    crps1: List[float] = []; crps2: List[float] = []; crps_g: List[float] = []
    n_used = 0
    for gid in gids:
        gpa = te_pa[te_pa["game_pk"] == gid].sort_values("at_bat_number")
        ab, hb, hp, ap, stand, throw = _lineups(gpa)
        if hp < 0 or ap < 0 or not ab or not hb:
            continue
        pa_away = _slot_dists(sel, out, tiers, ab, hp, throw, stand)   # away bats vs home SP
        pa_home = _slot_dists(sel, out, tiers, hb, ap, throw, stand)   # home bats vs away SP
        rp_a = relpa.slot_matrix(ab, tiers, fresh.get((int(gid), "Top"), 1.0))  # away vs home pen
        rp_h = relpa.slot_matrix(hb, tiers, fresh.get((int(gid), "Bot"), 1.0))  # home vs away pen
        fh = int(gpa["post_home_score"].max()); fa = int(gpa["post_away_score"].max())
        seed = int(gid) % 100000
        n_used += 1
        # pooled full game
        h1, a1 = simulate_game(pa_away, pa_home, trans, n=n_sims, seed=seed)
        h2, a2 = simulate_game_v2(pa_away, pa_home, rp_a, rp_h, trans, removal,
                                  n=n_sims, seed=seed)
        pit_full1.append(pit_value((h1 - a1).astype(float), fh - fa))
        pit_full2.append(pit_value((h2 - a2).astype(float), fh - fa))
        crps1.append(crps_ensemble((h1 - a1).astype(float), fh - fa))
        crps2.append(crps_ensemble((h2 - a2).astype(float), fh - fa))
        crps_g.append(crps_gaussian(mu_m, sd_m, fh - fa))
        # inning-7 snapshot
        pre = gpa[gpa["inning"] < 7]
        if pre.empty:
            continue
        sh = int(pre["post_home_score"].iloc[-1]); sa = int(pre["post_away_score"].iloc[-1])
        mb = int(np.clip((sh - sa) + 4, 0, 8) // 3)
        st = GameStart(inning=7, half=0, home_score=sh, away_score=sa)
        p1, p2 = compare_snapshot(pa_away, pa_home, rp_a, rp_h, trans, removal,
                                  fh, fa, st, seed + 7, n_sims)
        snap1.setdefault("inn7|m%d" % mb, []).append(p1)
        snap2.setdefault("inn7|m%d" % mb, []).append(p2)

    buckets = {}
    for k in sorted(set(snap1) | set(snap2)):
        if len(snap1.get(k, [])) >= 10:
            buckets[k] = {"v1": _pit_stat(snap1[k]), "v2": _pit_stat(snap2.get(k, []))}
    named = buckets.get("inn7|m2", {"v1": _pit_stat(snap1.get("inn7|m2", [])),
                                    "v2": _pit_stat(snap2.get("inn7|m2", []))})
    doc = {
        "model": "mlb_pitch_engine_v2_bullpen_seam", "edge_claimed": False,
        "fit_seasons": list(fit_seasons), "eval_season": eval_season,
        "asof": "tables fit on fit_seasons, applied to held-out later eval_season; walk-forward, leak-free",
        "n_games_used": n_used, "n_sims": n_sims,
        "removal_model": removal.summary(), "reliever_model": relpa.summary(),
        "named_bucket_inn7_home_lead": named,
        "state_conditional_inn7_buckets": buckets,
        "pooled_full_game_margin": {"v1": _pit_stat(pit_full1), "v2": _pit_stat(pit_full2),
                                    "crps_v1": round(float(np.mean(crps1)), 4) if crps1 else None,
                                    "crps_v2": round(float(np.mean(crps2)), 4) if crps2 else None,
                                    "crps_gauss": round(float(np.mean(crps_g)), 4) if crps_g else None},
        "verdict_note": ("Reliever seam HELPS the named bucket iff v2 inn7|m2 "
                         "uniformity_dev < v1's. Distributional calibration only; no "
                         "market, no dollars, no edge."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=125)
    ap.add_argument("--sims", type=int, default=1500)
    ap.add_argument("--fit", type=str, default=",".join(str(s) for s in FIT_SEASONS))
    ap.add_argument("--eval", type=int, default=EVAL_SEASON)
    ap.add_argument("--sample-seed", type=int, default=2)
    a = ap.parse_args(argv)
    d = run(n_games=a.games, n_sims=a.sims,
            fit_seasons=tuple(int(s) for s in a.fit.split(",")),
            eval_season=a.eval, sample_seed=a.sample_seed)
    nb = d["named_bucket_inn7_home_lead"]; pf = d["pooled_full_game_margin"]
    v1, v2 = nb["v1"], nb["v2"]
    print("inn7|home-lead(m2) n=%s  v1 dev=%s mean=%s  v2 dev=%s mean=%s" % (
        v1["n"], v1["uniformity_dev"], v1["mean_pit"], v2["uniformity_dev"], v2["mean_pit"]))
    print("pooled margin  v1 dev=%s v2 dev=%s | CRPS v1=%s v2=%s gauss=%s" % (
        pf["v1"]["uniformity_dev"], pf["v2"]["uniformity_dev"],
        pf["crps_v1"], pf["crps_v2"], pf["crps_gauss"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
