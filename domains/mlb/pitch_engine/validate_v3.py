"""domains.mlb.pitch_engine.validate_v3 -- does PITCHER-QUALITY-TIER composition
(the queued fix from v2's REJECT) fix v1's named worst bucket (inn7|home-lead)
without the symmetric over-correction v2 showed?

WALK-FORWARD (leak-free): identical protocol to validate_v2 -- every table (incl.
the v3 addition, bullpen_v3.PitcherQualityTier + RelieverPAv3) is fit on
2023+2024+2025 and applied to the held-out 2026 season. v1 and v3 share the
IDENTICAL selection/outcome/transition tables, starter-removal model, and the
SAME per-game seed, so any PIT/CRPS difference is the composition seam alone.

VERDICT is distributional calibration ONLY (PIT uniformity_dev, CRPS) -- no
market, no dollars, edge_claimed:false.

INVARIANTS: domains-only; corpus READ-ONLY; ASCII; threads<=4; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_validate_v3.py -q
CLI: python -m domains.mlb.pitch_engine.validate_v3 [--games N] [--sims N] [--sample-seed N]
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
from domains.mlb.pitch_engine.bullpen_v3 import PitcherQualityTier, RelieverPAv3
from domains.mlb.pitch_engine.selection import SelectionModel
from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel
from domains.mlb.pitch_engine.game_sim import BaseOutTransition, simulate_game, GameStart
from domains.mlb.pitch_engine.game_sim_v3 import simulate_game_v3
from domains.mlb.pitch_engine.validate import _lineups, _slot_dists
from domains.mlb.pitch_engine.validate_v2 import _pit_stat
from domains.basketball_nba.sim2.simulator import crps_ensemble, crps_gaussian, pit_value

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "mlb_pitch_engine_v3.json"
FIT_SEASONS = (2023, 2024, 2025)
EVAL_SEASON = 2026
_COLS = list(C._PITCH_COLS) + ["home_score", "away_score", "game_date"]


def compare_snapshot_v3(pa_away, pa_home, rp_a, rp_h, trans, removal, fh, fa,
                        st: Optional[GameStart], seed: int, n: int) -> Tuple[float, float]:
    """(pit_v1, pit_v3) of realized final margin fh-fa for one game/snapshot."""
    h1, a1 = simulate_game(pa_away, pa_home, trans, n=n, seed=seed, start=st)
    h3, a3 = simulate_game_v3(pa_away, pa_home, rp_a, rp_h, trans, removal,
                              n=n, seed=seed, start=st)
    tgt = float(fh - fa)
    return (pit_value((h1 - a1).astype(float), tgt),
            pit_value((h3 - a3).astype(float), tgt))


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
    ptiers = PitcherQualityTier.fit(tr_pa)
    relpa3 = RelieverPAv3.fit(tr_pa, ptiers)
    m = tr_pa.groupby("game_pk")[["post_home_score", "post_away_score"]].max()
    margins = (m["post_home_score"] - m["post_away_score"]).to_numpy()
    base_norm = (float(margins.mean()), float(margins.std()))
    del tr_pitch, tr_pa
    return sel, out, tiers, trans, removal, ptiers, relpa3, base_norm


def run(n_games: int = 125, n_sims: int = 1500, fit_seasons=FIT_SEASONS,
        eval_season: int = EVAL_SEASON, sample_seed: int = 2) -> dict:
    sel, out, tiers, trans, removal, ptiers, relpa3, base_norm = _fit(fit_seasons)
    mu_m, sd_m = base_norm
    rp_matrix = relpa3.bucket_lead_matrix()               # [N_BUCKET,N_LEAD,8], fixed
    te_pa = bp.mark_context(C.build_pa_frame(C.load_pitch_frame(eval_season, cols=_COLS)))

    gids = te_pa["game_pk"].drop_duplicates()
    gids = gids.sample(min(n_games, len(gids)), random_state=sample_seed).tolist()
    snap1: Dict[str, list] = {}; snap3: Dict[str, list] = {}
    pit_full1: List[float] = []; pit_full3: List[float] = []
    crps1: List[float] = []; crps3: List[float] = []; crps_g: List[float] = []
    n_used = 0
    for gid in gids:
        gpa = te_pa[te_pa["game_pk"] == gid].sort_values("at_bat_number")
        ab, hb, hp, ap, stand, throw = _lineups(gpa)
        if hp < 0 or ap < 0 or not ab or not hb:
            continue
        pa_away = _slot_dists(sel, out, tiers, ab, hp, throw, stand)   # away bats vs home SP
        pa_home = _slot_dists(sel, out, tiers, hb, ap, throw, stand)   # home bats vs away SP
        fh = int(gpa["post_home_score"].max()); fa = int(gpa["post_away_score"].max())
        seed = int(gid) % 100000
        n_used += 1
        h1, a1 = simulate_game(pa_away, pa_home, trans, n=n_sims, seed=seed)
        h3, a3 = simulate_game_v3(pa_away, pa_home, rp_matrix, rp_matrix, trans, removal,
                                  n=n_sims, seed=seed)
        pit_full1.append(pit_value((h1 - a1).astype(float), fh - fa))
        pit_full3.append(pit_value((h3 - a3).astype(float), fh - fa))
        crps1.append(crps_ensemble((h1 - a1).astype(float), fh - fa))
        crps3.append(crps_ensemble((h3 - a3).astype(float), fh - fa))
        crps_g.append(crps_gaussian(mu_m, sd_m, fh - fa))
        pre = gpa[gpa["inning"] < 7]
        if pre.empty:
            continue
        sh = int(pre["post_home_score"].iloc[-1]); sa = int(pre["post_away_score"].iloc[-1])
        mb = int(np.clip((sh - sa) + 4, 0, 8) // 3)
        st = GameStart(inning=7, half=0, home_score=sh, away_score=sa)
        p1, p3 = compare_snapshot_v3(pa_away, pa_home, rp_matrix, rp_matrix, trans, removal,
                                     fh, fa, st, seed + 7, n_sims)
        snap1.setdefault("inn7|m%d" % mb, []).append(p1)
        snap3.setdefault("inn7|m%d" % mb, []).append(p3)

    buckets = {}
    for k in sorted(set(snap1) | set(snap3)):
        if len(snap1.get(k, [])) >= 10:
            buckets[k] = {"v1": _pit_stat(snap1[k]), "v3": _pit_stat(snap3.get(k, []))}
    named = buckets.get("inn7|m2", {"v1": _pit_stat(snap1.get("inn7|m2", [])),
                                    "v3": _pit_stat(snap3.get("inn7|m2", []))})
    doc = {
        "model": "mlb_pitch_engine_v3_composition_seam", "edge_claimed": False,
        "fit_seasons": list(fit_seasons), "eval_season": eval_season,
        "sample_seed": sample_seed,
        "asof": "tables fit on fit_seasons, applied to held-out later eval_season; walk-forward, leak-free",
        "n_games_used": n_used, "n_sims": n_sims,
        "pitcher_quality_tiers": ptiers.summary(), "reliever_composition": relpa3.summary(),
        "named_bucket_inn7_home_lead": named,
        "state_conditional_inn7_buckets": buckets,
        "pooled_full_game_margin": {"v1": _pit_stat(pit_full1), "v3": _pit_stat(pit_full3),
                                    "crps_v1": round(float(np.mean(crps1)), 4) if crps1 else None,
                                    "crps_v3": round(float(np.mean(crps3)), 4) if crps3 else None,
                                    "crps_gauss": round(float(np.mean(crps_g)), 4) if crps_g else None},
        "verdict_note": ("Composition seam HELPS the named bucket iff v3 inn7|m2 "
                         "uniformity_dev < v1's AND pooled CRPS does not degrade vs v1. "
                         "Distributional calibration only; no market, no dollars, no edge."),
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
    v1, v3 = nb["v1"], nb["v3"]
    print("inn7|home-lead(m2) n=%s  v1 dev=%s mean=%s  v3 dev=%s mean=%s" % (
        v1["n"], v1["uniformity_dev"], v1["mean_pit"], v3["uniformity_dev"], v3["mean_pit"]))
    print("pooled margin  v1 dev=%s v3 dev=%s | CRPS v1=%s v3=%s gauss=%s" % (
        pf["v1"]["uniformity_dev"], pf["v3"]["uniformity_dev"],
        pf["crps_v1"], pf["crps_v3"], pf["crps_gauss"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
