"""scripts.platformkit.benchmarks.crps_market.run_mlb -- CRPS-vs-market
DISTRIBUTIONAL benchmark for MLB totals (edge queue item 4).

Compares the pitch engine's game-total ENSEMBLE (domains/mlb/pitch_engine,
imported unchanged -- fit on FIT_SEASON=2023, same tables validate.py uses) to
the devigged MARKET-implied total distribution (data/cache/line_history/mlb/) on
REAL, SETTLED 2026-season games, joined via mlb_join.py.

Sharpness only -- CRPS + 80%-interval coverage. NEVER a $/ROI claim; a market-
sharper or underpowered result is reported as plainly as a model-sharper one.

LEAK AUDIT: the engine's tables are fit on 2023 only (never refit here); each
2026 game is scored using ONLY that game's own PA/lineup data (as validate.py's
panel C already does) plus the market's OWN pre-game devigged prices (whichever
line snapshot predates that game's commence_time -- captured_at is checked).
No 2026 postseason info reaches the fit tables; no future game's price leaks
into another game's market fit (each game's market fit uses only that game_id's
own rows).

CLI: python -m scripts.platformkit.benchmarks.crps_market.run_mlb \
        --start 2026-06-18 --end 2026-07-08 --max-games 300
Tests: python -m pytest tests/platformkit/test_crps_market_mlb.py -q
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy.stats import norm

from domains.mlb.pitch_engine import corpus as C
from domains.mlb.pitch_engine.selection import SelectionModel
from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel
from domains.mlb.pitch_engine.game_sim import BaseOutTransition, simulate_game
from domains.mlb.pitch_engine.validate import _lineups, _slot_dists
from domains.basketball_nba.sim2.simulator import crps_ensemble, crps_gaussian

from scripts.platformkit.benchmarks.crps_market.mlb_join import (
    build_game_join, load_line_history_totals, load_statcast_games,
)
from scripts.platformkit.benchmarks.crps_market.market_dist import (
    devig_points, fit_market_gaussian,
)

_OUT = Path(__file__).resolve().parent / "last_run_mlb.json"
N_SIM = 1500


def _fit_engine():
    tr_pitch = C.load_pitch_frame(C.FIT_SEASON)
    tr_pa = C.build_pa_frame(tr_pitch)
    tiers = BatterTiers.fit(tr_pa)
    sel = SelectionModel.fit(tr_pitch)
    out = OutcomeModel.fit(tr_pitch, tiers)
    trans = BaseOutTransition.fit(tr_pa)
    m = tr_pa.groupby("game_pk")[["post_home_score", "post_away_score"]].max()
    sigma_clim = float((m["post_home_score"] + m["post_away_score"]).std())
    return sel, out, tiers, trans, sigma_clim


def _bootstrap_ci(delta: np.ndarray, b: int = 3000, seed: int = 0) -> List[float]:
    rng = np.random.default_rng(seed)
    n = len(delta)
    means = [rng.choice(delta, size=n, replace=True).mean() for _ in range(b)]
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def run(start: str, end: str, max_games: int, seed: int = 0) -> dict:
    statcast_games = load_statcast_games(2026)
    line_totals = load_line_history_totals(start, end)
    join = build_game_join(statcast_games, line_totals)
    n_line_games = line_totals["game_id"].nunique() if len(line_totals) else 0

    if not join:
        return {"sport": "mlb", "verdict": "NOT_TESTABLE",
                "blocker": "zero unambiguous game_pk<->game_id joins",
                "n_line_history_games": int(n_line_games)}

    gpk_realized = statcast_games.set_index("game_pk")["realized_total"].to_dict()
    sel, out, tiers, trans, sigma_clim = _fit_engine()

    te_pitch = C.load_pitch_frame(2026)
    te_pa = C.build_pa_frame(te_pitch)

    game_ids = sorted(join.keys())
    if len(game_ids) > max_games:
        rng = np.random.default_rng(seed)
        game_ids = sorted(rng.choice(game_ids, size=max_games, replace=False).tolist())

    rows_by_gid: Dict[str, List[dict]] = {
        gid: g.to_dict("records") for gid, g in line_totals.groupby("game_id")
    }

    model_crps, market_crps, n_lines_used = [], [], []
    model_cov, market_cov = [], []
    skipped_no_pa = skipped_market = 0

    for gid in game_ids:
        gpk = join[gid]
        realized = gpk_realized.get(gpk)
        if realized is None or np.isnan(realized):
            continue
        gpa = te_pa[te_pa["game_pk"] == gpk].sort_values("at_bat_number")
        if gpa.empty:
            skipped_no_pa += 1
            continue
        ab, hb, hp, ap, stand, throw = _lineups(gpa)
        if hp < 0 or ap < 0 or not ab or not hb:
            skipped_no_pa += 1
            continue
        try:
            points = devig_points(rows_by_gid[gid])
            mu, sigma, n_used = fit_market_gaussian(points, sigma_clim)
        except (ValueError, KeyError):
            skipped_market += 1
            continue

        pa_away = _slot_dists(sel, out, tiers, ab, hp, throw, stand)
        pa_home = _slot_dists(sel, out, tiers, hb, ap, throw, stand)
        h, a = simulate_game(pa_away, pa_home, trans, n=N_SIM, seed=int(gpk) % 100000)
        totals = (h + a).astype(float)

        model_crps.append(crps_ensemble(totals, float(realized)))
        market_crps.append(crps_gaussian(mu, sigma, float(realized)))
        n_lines_used.append(n_used)

        lo_m, hi_m = np.quantile(totals, [0.1, 0.9])
        model_cov.append(bool(lo_m <= realized <= hi_m))
        lo_k = norm.ppf(0.1) * sigma + mu
        hi_k = norm.ppf(0.9) * sigma + mu
        market_cov.append(bool(lo_k <= realized <= hi_k))

    n = len(model_crps)
    doc = {
        "sport": "mlb", "market": "total_runs", "edge_claimed": False,
        "n_line_history_games": int(n_line_games),
        "n_joined_game_pk": len(join), "n_scored": n,
        "n_skipped_no_pa_or_lineup": skipped_no_pa,
        "n_skipped_market_fit": skipped_market,
        "n_multi_line_games": int(sum(1 for x in n_lines_used if x >= 2)),
        "n_single_line_fallback_games": int(sum(1 for x in n_lines_used if x == 1)),
    }
    if n < 5:
        doc["verdict"] = "NOT_TESTABLE"
        doc["blocker"] = "fewer than 5 games survived join + lineup + market-fit filters"
        return doc

    mc = np.array(model_crps); kc = np.array(market_crps)
    delta = kc - mc  # positive => market CRPS higher => model sharper
    ci = _bootstrap_ci(delta)
    if n < 30:
        verdict = "UNDERPOWERED"
    elif ci[0] > 0:
        verdict = "MODEL_SHARPER"
    elif ci[1] < 0:
        verdict = "MARKET_SHARPER"
    else:
        verdict = "UNDERPOWERED"

    doc.update({
        "model_crps_mean": round(float(mc.mean()), 4),
        "market_crps_mean": round(float(kc.mean()), 4),
        "paired_delta_mean": round(float(delta.mean()), 4),
        "paired_delta_95ci": [round(ci[0], 4), round(ci[1], 4)],
        "model_80pct_interval_coverage": round(float(np.mean(model_cov)), 3),
        "market_80pct_interval_coverage": round(float(np.mean(market_cov)), 3),
        "verdict": verdict,
        "honest_note": ("CRPS/coverage sharpness only, no dollar edge. Single-line "
                        "games use a climatology-sigma Gaussian fallback (labeled "
                        "n_single_line_fallback_games); multi-line games fit both "
                        "mu and sigma from market prices alone."),
    })
    return doc


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="mlb", choices=["mlb"])
    ap.add_argument("--start", default="2026-06-18")
    ap.add_argument("--end", default="2026-07-08")
    ap.add_argument("--max-games", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    doc = run(a.start, a.end, a.max_games, a.seed)
    _OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(doc, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
