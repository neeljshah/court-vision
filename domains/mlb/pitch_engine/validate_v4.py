"""domains.mlb.pitch_engine.validate_v4 -- does PER-SIMULATED-TEAM reliever
conditioning AT SIMULATE TIME (bullpen_v4.TeamReliever) fix v1's named worst
bucket (inn7|home-lead) where the TIER-mixture axis (v3, v3_team) proved inert?

v3/v3_team ROOT-CAUSE FINDING (validate_v3_team.py verdict_note): mixed_probs
is an exact law-of-total-probability identity, so bucket_lead_matrix() is
BYTE-IDENTICAL between the pitcher-tier and team-tier candidates whenever every
tier cell clears the min-sample floor -- the tiering VARIABLE is inert. The
real gap named there: game_sim_v3 shares ONE league-mixed matrix for BOTH
simulated sides. This gate tests the corrected seam: rp_vs_away/rp_vs_home are
now the SPECIFIC home/away team's own bullpen matrix (bullpen_v4.TeamReliever),
not one shared pooled table -- game_sim_v3 (simulate_game_v3) is reused
verbatim, since its API already took two separate matrices.

SAME walk-forward protocol as validate_v2/v3/v3_team: every table fit on
2023-2025, applied to held-out 2026. v1 and v4 share the IDENTICAL
selection/outcome/transition/removal tables and per-game seed as v3's gate
(reuses validate_v3.compare_snapshot_v3 verbatim), so any PIT/CRPS delta is the
team-simtime-conditioning seam alone.

VERDICT bars (pre-stated, all distributional -- no market, no dollars, no edge):
  (a) named inn7|m2 uniformity_dev(v4) < uniformity_dev(v1)
  (b) pooled full-game CRPS(v4) <= CRPS(v1) (no pooled regression)
  (c) no_bucket_regression: no OTHER state-conditional inn7 bucket's
      uniformity_dev worsens by more than _REGRESSION_EPS vs v1
IMPROVES iff (a) and (b) and (c) all hold. NO_IMPROVEMENT is an honest,
expected outcome (prior two seams were inert/regressed). A large, clean win
here is SUSPECT given that history -- recheck cell floors and leakage before
believing it.

INVARIANTS: domains-only; corpus READ-ONLY; ASCII; threads<=4; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_validate_v4.py -q
CLI: python -m domains.mlb.pitch_engine.validate_v4 [--games N] [--sims N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import corpus as C
from domains.mlb.pitch_engine import bullpen as bp
from domains.mlb.pitch_engine.bullpen_v4 import TeamReliever
from domains.mlb.pitch_engine.selection import SelectionModel
from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel
from domains.mlb.pitch_engine.game_sim import BaseOutTransition, GameStart, simulate_game
from domains.mlb.pitch_engine.game_sim_v3 import simulate_game_v3
from domains.mlb.pitch_engine.validate import _lineups, _slot_dists
from domains.mlb.pitch_engine.validate_v2 import _pit_stat
from domains.mlb.pitch_engine.validate_v3 import compare_snapshot_v3, FIT_SEASONS, EVAL_SEASON
from domains.basketball_nba.sim2.simulator import crps_ensemble, pit_value

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "mlb_pitch_engine_v4_team_simtime.json"
LEDGER = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
_COLS = list(C._PITCH_COLS) + ["home_score", "away_score", "game_date",
                                "home_team", "away_team"]
_REGRESSION_EPS = 0.01


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
    team_rel = TeamReliever.fit(tr_pa)
    m = tr_pa.groupby("game_pk")[["post_home_score", "post_away_score"]].max()
    margins = (m["post_home_score"] - m["post_away_score"]).to_numpy()
    base_norm = (float(margins.mean()), float(margins.std()))
    del tr_pitch, tr_pa
    return sel, out, tiers, trans, removal, team_rel, base_norm


def _ledger_append(doc: dict, verdict: str) -> None:
    """Own writer (no shared ledger helper touched) -- appends ONE ASCII JSONL
    row to the shared prereg hypothesis ledger."""
    row = {
        "hypothesis": "mlb_pitch_engine_v4_team_simtime_bullpen_seam",
        "sport": "mlb", "atomic_unit": "game_snapshot_inn7",
        "method": "pitch_engine_v4_team_conditioned_reliever_simtime",
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
    sel, out, tiers, trans, removal, team_rel, base_norm = _fit(fit_seasons)
    te_pa = bp.mark_context(C.build_pa_frame(C.load_pitch_frame(eval_season, cols=_COLS)))

    gids = te_pa["game_pk"].drop_duplicates()
    gids = gids.sample(min(n_games, len(gids)), random_state=sample_seed).tolist()
    snap1: Dict[str, list] = {}; snap4: Dict[str, list] = {}
    pit_full1: List[float] = []; pit_full4: List[float] = []
    crps1: List[float] = []; crps4: List[float] = []
    n_used = 0
    n_direct_total = 0; n_fallback_total = 0
    for gid in gids:
        gpa = te_pa[te_pa["game_pk"] == gid].sort_values("at_bat_number")
        ab, hb, hp, ap, stand, throw = _lineups(gpa)
        if hp < 0 or ap < 0 or not ab or not hb:
            continue
        home_team = str(gpa["home_team"].iloc[0]); away_team = str(gpa["away_team"].iloc[0])
        rp_vs_away, nd1, nf1 = team_rel.team_matrix(home_team)  # home bullpen faces away batters
        rp_vs_home, nd2, nf2 = team_rel.team_matrix(away_team)  # away bullpen faces home batters
        n_direct_total += nd1 + nd2; n_fallback_total += nf1 + nf2
        pa_away = _slot_dists(sel, out, tiers, ab, hp, throw, stand)
        pa_home = _slot_dists(sel, out, tiers, hb, ap, throw, stand)
        fh = int(gpa["post_home_score"].max()); fa = int(gpa["post_away_score"].max())
        seed = int(gid) % 100000
        n_used += 1
        h1, a1 = simulate_game(pa_away, pa_home, trans, n=n_sims, seed=seed)
        h4, a4 = simulate_game_v3(pa_away, pa_home, rp_vs_away, rp_vs_home, trans, removal,
                                  n=n_sims, seed=seed)
        pit_full1.append(pit_value((h1 - a1).astype(float), fh - fa))
        pit_full4.append(pit_value((h4 - a4).astype(float), fh - fa))
        crps1.append(crps_ensemble((h1 - a1).astype(float), fh - fa))
        crps4.append(crps_ensemble((h4 - a4).astype(float), fh - fa))
        pre = gpa[gpa["inning"] < 7]
        if pre.empty:
            continue
        sh = int(pre["post_home_score"].iloc[-1]); sa = int(pre["post_away_score"].iloc[-1])
        mb = int(np.clip((sh - sa) + 4, 0, 8) // 3)
        st = GameStart(inning=7, half=0, home_score=sh, away_score=sa)
        p1, p4 = compare_snapshot_v3(pa_away, pa_home, rp_vs_away, rp_vs_home, trans, removal,
                                     fh, fa, st, seed + 7, n_sims)
        snap1.setdefault("inn7|m%d" % mb, []).append(p1)
        snap4.setdefault("inn7|m%d" % mb, []).append(p4)

    buckets = {}
    for k in sorted(set(snap1) | set(snap4)):
        if len(snap1.get(k, [])) >= 10:
            buckets[k] = {"v1": _pit_stat(snap1[k]), "v4_team_sim": _pit_stat(snap4.get(k, []))}
    named = buckets.get("inn7|m2", {"v1": _pit_stat(snap1.get("inn7|m2", [])),
                                    "v4_team_sim": _pit_stat(snap4.get("inn7|m2", []))})
    regressions = {k: round(v["v4_team_sim"]["uniformity_dev"] - v["v1"]["uniformity_dev"], 4)
                   for k, v in buckets.items()}
    no_bucket_regression = all(d <= _REGRESSION_EPS for d in regressions.values())
    n_total = max(1, n_direct_total + n_fallback_total)
    doc = {
        "model": "mlb_pitch_engine_v4_team_simtime_seam", "edge_claimed": False,
        "fit_seasons": list(fit_seasons), "eval_season": eval_season,
        "sample_seed": sample_seed,
        "asof": "tables fit on fit_seasons, applied to held-out later eval_season; walk-forward, leak-free",
        "n_games_used": n_used, "n_sims": n_sims,
        "team_reliever": team_rel.summary(),
        "fallback_cells": {"n_direct": n_direct_total, "n_fallback": n_fallback_total,
                           "fallback_frac": round(n_fallback_total / n_total, 4)},
        "named_bucket_inn7_home_lead": named,
        "state_conditional_inn7_buckets": buckets,
        "bucket_regressions_vs_v1": regressions,
        "no_bucket_regression": no_bucket_regression,
        "regression_eps": _REGRESSION_EPS,
        "pooled_full_game_margin": {"v1": _pit_stat(pit_full1), "v4_team_sim": _pit_stat(pit_full4),
                                    "crps_v1": round(float(np.mean(crps1)), 4) if crps1 else None,
                                    "crps_v4_team_sim": round(float(np.mean(crps4)), 4) if crps4 else None},
        "verdict_note": ("Team-simtime seam IMPROVES iff (a) named inn7|m2 v4_team_sim "
                         "uniformity_dev < v1's, (b) pooled CRPS(v4) <= CRPS(v1), (c) "
                         "no_bucket_regression true (no OTHER inn7 bucket's uniformity_dev "
                         "worsens by more than regression_eps vs v1). Prior seams on this "
                         "line (v2 pooled-relief, v3/v3_team tier-mixture) were REJECT/inert "
                         "-- NO_IMPROVEMENT here is an honest, expected outcome, and a large "
                         "clean win is SUSPECT (recheck fallback_cells + leakage first). "
                         "Distributional calibration only; no market, no dollars, no edge."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")

    v1d = named["v1"]["uniformity_dev"]; v4d = named["v4_team_sim"]["uniformity_dev"]
    pf = doc["pooled_full_game_margin"]
    verdict = "UNDERPOWERED" if named["v4_team_sim"]["n"] < 10 else "NO_IMPROVEMENT"
    if named["v4_team_sim"]["n"] >= 10:
        crps_ok = pf["crps_v4_team_sim"] is not None and pf["crps_v1"] is not None \
            and pf["crps_v4_team_sim"] <= pf["crps_v1"]
        if v4d < v1d and crps_ok and no_bucket_regression:
            verdict = "IMPROVES"
        elif v4d > v1d + _REGRESSION_EPS:
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
    nb = d["named_bucket_inn7_home_lead"]; pf = d["pooled_full_game_margin"]
    v1, v4 = nb["v1"], nb["v4_team_sim"]
    print("verdict=%s  fallback_frac=%s" % (d["verdict"], d["fallback_cells"]["fallback_frac"]))
    print("inn7|home-lead(m2) n=%s  v1 dev=%s mean=%s  v4 dev=%s mean=%s" % (
        v1["n"], v1["uniformity_dev"], v1["mean_pit"], v4["uniformity_dev"], v4["mean_pit"]))
    print("pooled margin  v1 dev=%s v4 dev=%s | CRPS v1=%s v4=%s | no_bucket_regression=%s" % (
        pf["v1"]["uniformity_dev"], pf["v4_team_sim"]["uniformity_dev"],
        pf["crps_v1"], pf["crps_v4_team_sim"], d["no_bucket_regression"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
