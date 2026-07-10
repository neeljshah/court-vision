"""domains.mlb.pitch_engine.validate_platoon_inn4 -- does the PLATOON-conditioned
OUTCOME table (outcome_platoon.PlatoonOutcomeModel, mechanism #1 CONFIRMED
REPLICATED) fix the OPEN inn4|m2 bucket (home leading entering inning 4, never
gate-targeted -- sim heatmap sweep 2026-07-10)?

Chosen over the mirror inn4|m0 (identical mechanism support) for its larger n
(31 vs 24, which the sweep's next-wave queue flags as a power caveat) and over
inn7|m0/inn7|m1 because their only mechanism analog (#29 strand-prevention) is
bullpen-tier conditioning, a CLOSED class in any form (e334c91f/dfc3b065).

WALK-FORWARD (leak-free): identical protocol to validate_v2/v3/v4 -- every
table (selection, base outcome, transition, tiers) is fit on 2023+2024+2025 and
applied to the held-out 2026 season. v1 and the platoon candidate share the
IDENTICAL selection/tier/transition tables and the SAME per-game seed; the
candidate's OutcomeModel gains ONLY the same_hand dimension (outcome_platoon.py),
so any PIT/CRPS delta is that seam alone. simulate_game (game_sim.py, v1,
UNCHANGED) is reused verbatim -- the candidate only changes which per-slot [9,8]
PA-event matrix it is fed.

VERDICT bars (pre-stated, all distributional -- no market, no dollars, no edge):
  (a) named inn4|m2 uniformity_dev(platoon) < uniformity_dev(v1)
  (b) pooled full-game CRPS(platoon) <= CRPS(v1) (no pooled regression)
  (c) no_bucket_regression: no OTHER state-conditional inn4 bucket's
      uniformity_dev worsens by more than _REGRESSION_EPS vs v1
IMPROVES iff (a) and (b) and (c) all hold. NO_IMPROVEMENT is an honest,
expected outcome given this bucket's mechanism was never tested before.

INVARIANTS: domains-only; corpus READ-ONLY; ASCII; threads<=4; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_validate_platoon_inn4.py -q
CLI: python -m domains.mlb.pitch_engine.validate_platoon_inn4 [--games N] [--sims N] [--sample-seed N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import corpus as C
from domains.mlb.pitch_engine.selection import SelectionModel
from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel
from domains.mlb.pitch_engine.outcome_platoon import PlatoonOutcomeModel, assemble_platoon
from domains.mlb.pitch_engine.game_sim import BaseOutTransition, GameStart, simulate_game
from domains.mlb.pitch_engine.validate import _lineups, _slot_dists
from domains.mlb.pitch_engine.validate_v2 import _pit_stat
from domains.mlb.pitch_engine.validate_v3 import FIT_SEASONS, EVAL_SEASON
from domains.basketball_nba.sim2.simulator import crps_ensemble, pit_value

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "mlb_pitch_engine_platoon_inn4.json"
LEDGER = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
_COLS = list(C._PITCH_COLS) + ["home_score", "away_score", "game_date"]
_REGRESSION_EPS = 0.01
NAMED_BUCKET = "inn4|m2"


def _slot_dists_platoon(sel, out_p, tiers, batters, pitcher, throw, stand) -> np.ndarray:
    """validate._slot_dists twin using the platoon-conditioned outcome table."""
    pt_l = 2 if str(throw.get(pitcher, "R")) == "L" else 0
    m = np.zeros((9, 8))
    for i in range(9):
        b = batters[i] if i < len(batters) else (batters[0] if batters else -1)
        pidx = pt_l + (1 if str(stand.get(b, "R")) == "L" else 0)
        m[i] = assemble_platoon(sel, out_p, tiers, pitcher, b, pidx, 0)
    return m


def _fit(seasons):
    parts = [C.load_pitch_frame(y, cols=_COLS) for y in seasons]
    tr_pitch = pd.concat(parts, ignore_index=True)
    del parts
    tr_pa = C.build_pa_frame(tr_pitch)
    tiers = BatterTiers.fit(tr_pa)
    sel = SelectionModel.fit(tr_pitch)
    base_out = OutcomeModel.fit(tr_pitch, tiers)
    plat_out = PlatoonOutcomeModel.fit(tr_pitch, tiers, base_out)
    trans = BaseOutTransition.fit(tr_pa)
    m = tr_pa.groupby("game_pk")[["post_home_score", "post_away_score"]].max()
    margins = (m["post_home_score"] - m["post_away_score"]).to_numpy()
    del tr_pitch, tr_pa
    return sel, base_out, plat_out, tiers, trans, (float(margins.mean()), float(margins.std()))


def _ledger_append(doc: dict, verdict: str) -> None:
    """Own writer (no shared ledger helper touched) -- appends ONE ASCII JSONL
    row to the shared prereg hypothesis ledger."""
    row = {
        "hypothesis": "mlb_pitch_engine_platoon_outcome_seam_inn4_m2",
        "sport": "mlb", "atomic_unit": "game_snapshot_inn4",
        "method": "pitch_engine_platoon_conditioned_outcome_table",
        "season": "fit_%s_test_%s" % ("_".join(str(s) for s in doc["fit_seasons"]),
                                      doc["eval_season"]),
        "verdict": verdict,
        "lesson": doc["verdict_note"],
        "edge_claimed": False,
        "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="ascii", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def run(n_games: int = 125, n_sims: int = 1500, fit_seasons=FIT_SEASONS,
        eval_season: int = EVAL_SEASON, sample_seed: int = 2) -> dict:
    sel, base_out, plat_out, tiers, trans, base_norm = _fit(fit_seasons)
    te_pa = C.build_pa_frame(C.load_pitch_frame(eval_season, cols=_COLS))

    gids = te_pa["game_pk"].drop_duplicates()
    gids = gids.sample(min(n_games, len(gids)), random_state=sample_seed).tolist()
    snap1: Dict[str, list] = {}; snapP: Dict[str, list] = {}
    pit_full1: List[float] = []; pit_fullP: List[float] = []
    crps1: List[float] = []; crpsP: List[float] = []
    n_used = 0
    for gid in gids:
        gpa = te_pa[te_pa["game_pk"] == gid].sort_values("at_bat_number")
        ab, hb, hp, ap, stand, throw = _lineups(gpa)
        if hp < 0 or ap < 0 or not ab or not hb:
            continue
        pa_away1 = _slot_dists(sel, base_out, tiers, ab, hp, throw, stand)
        pa_home1 = _slot_dists(sel, base_out, tiers, hb, ap, throw, stand)
        pa_awayP = _slot_dists_platoon(sel, plat_out, tiers, ab, hp, throw, stand)
        pa_homeP = _slot_dists_platoon(sel, plat_out, tiers, hb, ap, throw, stand)
        fh = int(gpa["post_home_score"].max()); fa = int(gpa["post_away_score"].max())
        seed = int(gid) % 100000
        n_used += 1
        h1, a1 = simulate_game(pa_away1, pa_home1, trans, n=n_sims, seed=seed)
        hP, aP = simulate_game(pa_awayP, pa_homeP, trans, n=n_sims, seed=seed)
        pit_full1.append(pit_value((h1 - a1).astype(float), fh - fa))
        pit_fullP.append(pit_value((hP - aP).astype(float), fh - fa))
        crps1.append(crps_ensemble((h1 - a1).astype(float), fh - fa))
        crpsP.append(crps_ensemble((hP - aP).astype(float), fh - fa))
        pre = gpa[gpa["inning"] < 4]
        if pre.empty:
            continue
        sh = int(pre["post_home_score"].iloc[-1]); sa = int(pre["post_away_score"].iloc[-1])
        mb = int(np.clip((sh - sa) + 4, 0, 8) // 3)
        st = GameStart(inning=4, half=0, home_score=sh, away_score=sa)
        h1s, a1s = simulate_game(pa_away1, pa_home1, trans, n=n_sims, seed=seed + 4, start=st)
        hPs, aPs = simulate_game(pa_awayP, pa_homeP, trans, n=n_sims, seed=seed + 4, start=st)
        tgt = float(fh - fa)
        snap1.setdefault("inn4|m%d" % mb, []).append(pit_value((h1s - a1s).astype(float), tgt))
        snapP.setdefault("inn4|m%d" % mb, []).append(pit_value((hPs - aPs).astype(float), tgt))

    buckets = {}
    for k in sorted(set(snap1) | set(snapP)):
        if len(snap1.get(k, [])) >= 10:
            buckets[k] = {"v1": _pit_stat(snap1[k]), "platoon": _pit_stat(snapP.get(k, []))}
    named = buckets.get(NAMED_BUCKET, {"v1": _pit_stat(snap1.get(NAMED_BUCKET, [])),
                                       "platoon": _pit_stat(snapP.get(NAMED_BUCKET, []))})
    regressions = {k: round(v["platoon"]["uniformity_dev"] - v["v1"]["uniformity_dev"], 4)
                   for k, v in buckets.items() if k != NAMED_BUCKET}
    no_bucket_regression = all(d <= _REGRESSION_EPS for d in regressions.values())
    doc = {
        "model": "mlb_pitch_engine_platoon_outcome_seam", "edge_claimed": False,
        "fit_seasons": list(fit_seasons), "eval_season": eval_season,
        "sample_seed": sample_seed,
        "asof": "tables fit on fit_seasons, applied to held-out later eval_season; walk-forward, leak-free",
        "n_games_used": n_used, "n_sims": n_sims,
        "platoon_outcome_model": plat_out.summary(),
        "named_bucket": NAMED_BUCKET, "named_bucket_result": named,
        "state_conditional_inn4_buckets": buckets,
        "bucket_regressions_vs_v1": regressions,
        "no_bucket_regression": no_bucket_regression,
        "regression_eps": _REGRESSION_EPS,
        "pooled_full_game_margin": {"v1": _pit_stat(pit_full1), "platoon": _pit_stat(pit_fullP),
                                    "crps_v1": round(float(np.mean(crps1)), 4) if crps1 else None,
                                    "crps_platoon": round(float(np.mean(crpsP)), 4) if crpsP else None},
        "verdict_note": ("Platoon-outcome seam IMPROVES iff (a) named inn4|m2 platoon "
                         "uniformity_dev < v1's, (b) pooled CRPS(platoon) <= CRPS(v1), (c) "
                         "no_bucket_regression true (no OTHER inn4 bucket's uniformity_dev "
                         "worsens by more than regression_eps vs v1). Never gate-targeted "
                         "before this row -- NO_IMPROVEMENT is an honest, expected outcome. "
                         "Distributional calibration only; no market, no dollars, no edge."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")

    v1d = named["v1"]["uniformity_dev"]; vPd = named["platoon"]["uniformity_dev"]
    pf = doc["pooled_full_game_margin"]
    verdict = "UNDERPOWERED" if named["platoon"]["n"] < 10 else "NO_IMPROVEMENT"
    if named["platoon"]["n"] >= 10 and v1d is not None and vPd is not None:
        crps_ok = pf["crps_platoon"] is not None and pf["crps_v1"] is not None \
            and pf["crps_platoon"] <= pf["crps_v1"]
        if vPd < v1d and crps_ok and no_bucket_regression:
            verdict = "IMPROVES"
        elif vPd > v1d + _REGRESSION_EPS:
            verdict = "REGRESSES"
    _ledger_append(doc, verdict)
    doc["verdict"] = verdict
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
    nb = d["named_bucket_result"]; pf = d["pooled_full_game_margin"]
    v1, vP = nb["v1"], nb["platoon"]
    print("verdict=%s  seed=%s" % (d["verdict"], d["sample_seed"]))
    print("inn4|m2 n=%s  v1 dev=%s mean=%s  platoon dev=%s mean=%s" % (
        v1["n"], v1["uniformity_dev"], v1["mean_pit"], vP["uniformity_dev"], vP["mean_pit"]))
    print("pooled margin  v1 dev=%s platoon dev=%s | CRPS v1=%s platoon=%s | no_bucket_regression=%s" % (
        pf["v1"]["uniformity_dev"], pf["platoon"]["uniformity_dev"],
        pf["crps_v1"], pf["crps_platoon"], d["no_bucket_regression"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
