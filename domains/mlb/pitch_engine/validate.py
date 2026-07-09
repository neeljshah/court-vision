"""domains.mlb.pitch_engine.validate -- fit the pitch engine on 2023, VALIDATE on
held-out 2024 (never fitted). Four panels, edge_claimed:false throughout.

  (A) PITCH-SELECTION log-loss vs a no-context class-mix baseline.
  (B) PA-OUTCOME log-loss: the pitch-chain assembly vs the DIRECT PA model (same
      context, no chain). Assembly carrying MORE structure at <= log-loss is the
      win condition for sim use; worse is reported plainly.
  (C) GAME-LEVEL: simulate full 2024 games -> PIT of realized final margin + total
      within the sim distribution, CRPS vs a prior-season Normal (climatology)
      baseline.
  (D) STATE-CONDITIONAL PIT: snapshot start-of-inning-4 / -7 with the real score,
      simulate the remainder, PIT the realized final margin, bucketed inning x margin.

AS-OF (leak-free): every table fits on the FULL 2023 season and is applied to 2024;
a 2024 pitch/PA/game is scored with zero 2024 information. Game lineups use the
batters who appeared (first-appearance order, 9 slots) and the game's starter as
the whole-game pitcher (declared v1 simplifications; reliever + within-season
expanding are v2 seams). 2025/2026 parquets are being backfilled -- NOT read.

INVARIANTS: domains-only; corpus READ-ONLY; ASCII; threads<=4; local only; no
$/edge claim; <=300 LOC. Tests: python -m pytest domains/mlb/pitch_engine/test_validate.py -q
CLI: python -m domains.mlb.pitch_engine.validate [--games N] [--sub N]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import corpus as C
from domains.mlb.pitch_engine.selection import SelectionModel, no_context_baseline, _CLASS_IX
from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel
from domains.mlb.pitch_engine.pa_chain import assemble, DirectPAModel, _PA_IX
from domains.mlb.pitch_engine.game_sim import BaseOutTransition, simulate_game, GameStart
from domains.basketball_nba.sim2.simulator import crps_ensemble, crps_gaussian, pit_value

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "mlb_pitch_engine_v1.json"
SCORE = _REPO / "data" / "frontend" / "ops" / "mlb_pitch_engine_v1_scoreboard.json"
N_DIST = 1500
_EPS = 1e-12


def _logloss(p_true: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p_true, _EPS, 1.0))))


def _panel_selection(sel: SelectionModel, base: np.ndarray, te: pd.DataFrame,
                     sub: int, rng) -> dict:
    d = te.sample(min(sub, len(te)), random_state=0) if len(te) > sub else te
    cix = d["pclass"].map(_CLASS_IX).to_numpy()
    cache: Dict[tuple, np.ndarray] = {}
    p_model = np.empty(len(d)); p_base = base[cix]
    for i, (pid, ci, pi, bb, tc) in enumerate(zip(
            d["pitcher"], d["cidx"], d["pidx"], d["bbucket"], cix)):
        k = (int(pid), int(ci), int(pi), int(bb))
        v = cache.get(k)
        if v is None:
            v = sel.class_probs(*k); cache[k] = v
        p_model[i] = v[tc]
    return {"n": int(len(d)), "logloss_model": round(_logloss(p_model), 5),
            "logloss_no_context": round(_logloss(p_base), 5),
            "model_better": bool(_logloss(p_model) < _logloss(p_base))}


def _panel_pa(sel, out, tiers, direct: DirectPAModel, te_pa: pd.DataFrame,
              sub: int) -> dict:
    d = te_pa.sample(min(sub, len(te_pa)), random_state=1) if len(te_pa) > sub else te_pa
    evix = d["pa_evt"].map(_PA_IX).to_numpy()
    p_chain = np.empty(len(d)); p_direct = np.empty(len(d))
    cache: Dict[tuple, np.ndarray] = {}
    for i, r in enumerate(d.itertuples(index=False)):
        tc = (tiers.tier(r.batter, 0), tiers.tier(r.batter, 1), tiers.tier(r.batter, 2))
        k = (int(r.pitcher), int(r.pidx), int(r.bbucket), tc)
        v = cache.get(k)
        if v is None:
            v = assemble(sel, out, tiers, r.pitcher, r.batter, r.pidx, r.bbucket)
            cache[k] = v
        p_chain[i] = v[evix[i]]
        p_direct[i] = direct.probs(tiers.tier(r.batter, -1), r.pidx, r.bbucket)[evix[i]]
    ll_c, ll_d = _logloss(p_chain), _logloss(p_direct)
    return {"n": int(len(d)), "logloss_chain": round(ll_c, 5),
            "logloss_direct_pa": round(ll_d, 5),
            "chain_matches_or_beats_direct": bool(ll_c <= ll_d + 1e-4),
            "delta_chain_minus_direct": round(ll_c - ll_d, 5)}


def _lineups(gpa: pd.DataFrame):
    """(away_batters, home_batters, away_starter, home_starter, stands, throws)."""
    top = gpa[gpa["inning_topbot"] == "Top"]; bot = gpa[gpa["inning_topbot"] == "Bot"]
    ab = list(dict.fromkeys(top["batter"].tolist()))[:9]
    hb = list(dict.fromkeys(bot["batter"].tolist()))[:9]
    hp = int(top["pitcher"].iloc[0]) if len(top) else -1   # home fields in Top
    ap = int(bot["pitcher"].iloc[0]) if len(bot) else -1
    stand = dict(zip(gpa["batter"], gpa["stand"]))
    throw = dict(zip(gpa["pitcher"], gpa["p_throws"]))
    return ab, hb, hp, ap, stand, throw


def _slot_dists(sel, out, tiers, batters, pitcher, throw, stand) -> np.ndarray:
    pt_l = 2 if str(throw.get(pitcher, "R")) == "L" else 0
    m = np.zeros((9, 8))
    for i in range(9):
        b = batters[i] if i < len(batters) else (batters[0] if batters else -1)
        pidx = pt_l + (1 if str(stand.get(b, "R")) == "L" else 0)
        m[i] = assemble(sel, out, tiers, pitcher, b, pidx, 0)
    return m


def _panel_games(sel, out, tiers, trans, te_pa, base_norm, n_games, rng) -> dict:
    gids = te_pa["game_pk"].drop_duplicates()
    gids = gids.sample(min(n_games, len(gids)), random_state=2).tolist()
    pit_m: List[float] = []; pit_t: List[float] = []
    crps_s: List[float] = []; crps_g: List[float] = []
    pit_snap: Dict[str, list] = {}
    mu_m, sd_m, mu_t, sd_t = base_norm
    for gid in gids:
        gpa = te_pa[te_pa["game_pk"] == gid].sort_values("at_bat_number")
        ab, hb, hp, ap, stand, throw = _lineups(gpa)
        if hp < 0 or ap < 0 or not ab or not hb:
            continue
        pa_away = _slot_dists(sel, out, tiers, ab, hp, throw, stand)   # away bats vs home P
        pa_home = _slot_dists(sel, out, tiers, hb, ap, throw, stand)
        fh = int(gpa["post_home_score"].max()); fa = int(gpa["post_away_score"].max())
        seed = int(gid) % 100000
        h, a = simulate_game(pa_away, pa_home, trans, n=N_DIST, seed=seed)
        margin = (h - a).astype(float); total = (h + a).astype(float)
        pit_m.append(pit_value(margin, fh - fa)); pit_t.append(pit_value(total, fh + fa))
        crps_s.append(crps_ensemble(margin, fh - fa))
        crps_g.append(crps_gaussian(mu_m, sd_m, fh - fa))
        # panel D: start-of-inning snapshots with real score
        for inn in (4, 7):
            pre = gpa[gpa["inning"] < inn]
            if pre.empty:
                continue
            sh = int(pre["post_home_score"].iloc[-1]); sa = int(pre["post_away_score"].iloc[-1])
            hs, as_ = simulate_game(pa_away, pa_home, trans, n=N_DIST, seed=seed + inn,
                                    start=GameStart(inning=inn, half=0,
                                                    home_score=sh, away_score=sa))
            mb = int(np.clip((sh - sa) + 4, 0, 8) // 3)   # 3 coarse margin buckets
            pit_snap.setdefault("inn%d|m%d" % (inn, mb), []).append(
                pit_value((hs - as_).astype(float), fh - fa))
    def _pit_stat(vals):
        v = np.array(vals)
        dev = max(abs((v <= q).mean() - q) for q in np.linspace(0.1, 1.0, 10))
        return {"n": len(v), "mean_pit": round(float(v.mean()), 4),
                "uniformity_dev": round(float(dev), 4)}
    snap = {k: _pit_stat(v) for k, v in sorted(pit_snap.items()) if len(v) >= 10}
    return {"n_games": len(pit_m), "pit_margin": _pit_stat(pit_m),
            "pit_total": _pit_stat(pit_t),
            "crps_margin_sim": round(float(np.mean(crps_s)), 4),
            "crps_margin_gauss": round(float(np.mean(crps_g)), 4),
            "sim_beats_gauss": bool(np.mean(crps_s) < np.mean(crps_g)),
            "panel_D_state_conditional_pit": snap}


def run(n_games: int = 120, sub: int = 150000) -> dict:
    rng = np.random.default_rng(0)
    tr_pitch = C.load_pitch_frame(C.FIT_SEASON)
    tr_pa = C.build_pa_frame(tr_pitch)
    tiers = BatterTiers.fit(tr_pa)
    sel = SelectionModel.fit(tr_pitch)
    out = OutcomeModel.fit(tr_pitch, tiers)
    direct = DirectPAModel.fit(tr_pa, tiers)
    trans = BaseOutTransition.fit(tr_pa)
    base_mix = no_context_baseline(tr_pitch)
    # prior-season Normal (climatology) baseline for CRPS
    m = (tr_pa.groupby("game_pk")[["post_home_score", "post_away_score"]].max())
    margins = (m["post_home_score"] - m["post_away_score"]).to_numpy()
    totals = (m["post_home_score"] + m["post_away_score"]).to_numpy()
    base_norm = (float(margins.mean()), float(margins.std()),
                 float(totals.mean()), float(totals.std()))

    te_pitch = C.load_pitch_frame(C.TEST_SEASON)
    te_pa = C.build_pa_frame(te_pitch)
    pa_sel = _panel_selection(sel, base_mix, te_pitch, sub, rng)
    pa_pa = _panel_pa(sel, out, tiers, direct, te_pa, min(sub, 120000))
    games = _panel_games(sel, out, tiers, trans, te_pa, base_norm, n_games, rng)

    doc = {
        "model": "mlb_pitch_engine_v1", "edge_claimed": False,
        "fit_season": C.FIT_SEASON, "test_season": C.TEST_SEASON,
        "asof": "prior-full-season (2023) tables applied to 2024; zero test-season info",
        "n_pitches_fit": int(len(tr_pitch)), "n_pa_fit": int(len(tr_pa)),
        "selection_model": sel.summary(), "outcome_model": out.summary(),
        "transition_model": trans.summary(),
        "climatology_normal": {"mu_margin": round(base_norm[0], 3),
                               "sd_margin": round(base_norm[1], 3),
                               "mu_total": round(base_norm[2], 3),
                               "sd_total": round(base_norm[3], 3)},
        "panel_A_selection_logloss": pa_sel,
        "panel_B_pa_chain_vs_direct": pa_pa,
        "panel_C_game_pit_crps": games,
        "honest_note": ("Distributional calibration only vs held-out 2024; no dollars, "
                        "no edge. Chain-worse-than-direct on PA log-loss would still leave "
                        "the engine's value in conditional simulation (any game path), "
                        "measured by the PIT panels."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    SCORE.write_text(json.dumps({
        "row": "mlb_pitch_engine_v1", "edge_claimed": False,
        "selection_logloss_model": pa_sel["logloss_model"],
        "selection_logloss_base": pa_sel["logloss_no_context"],
        "pa_chain_logloss": pa_pa["logloss_chain"],
        "pa_direct_logloss": pa_pa["logloss_direct_pa"],
        "pit_margin_dev": games["pit_margin"]["uniformity_dev"],
        "sim_beats_gauss_crps": games["sim_beats_gauss"],
    }, indent=2), encoding="utf-8")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=120)
    ap.add_argument("--sub", type=int, default=150000)
    a = ap.parse_args(argv)
    d = run(n_games=a.games, sub=a.sub)
    A, B, Cc = (d["panel_A_selection_logloss"], d["panel_B_pa_chain_vs_direct"],
                d["panel_C_game_pit_crps"])
    print("selection LL model=%.4f base=%.4f | PA chain=%.4f direct=%.4f (d=%+.4f) | "
          "PIT margin dev=%.3f total dev=%.3f | CRPS sim=%.3f gauss=%.3f" % (
              A["logloss_model"], A["logloss_no_context"], B["logloss_chain"],
              B["logloss_direct_pa"], B["delta_chain_minus_direct"],
              Cc["pit_margin"]["uniformity_dev"], Cc["pit_total"]["uniformity_dev"],
              Cc["crps_margin_sim"], Cc["crps_margin_gauss"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
