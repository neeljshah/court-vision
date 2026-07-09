"""attribute_conditioning -- do PROFILE ATTRIBUTES (team-aggregated PRIOR
traits) sharpen the in-game win-prob update BEYOND the surviving live-state
rung? The v2 ladder (conditional_gate_v2) tested WHO is on the floor / foul
trouble / in-game luck; the one thing that survived is endQ1 star_minutes_load.
This module tests whether strictly-prior ATTRIBUTE x realized-live INTERACTIONS
add anything on top -- the arena the attribute engine is meant to pay in.

LEAK-LEGALITY (the load-bearing decision):
  data/cache/profiles/nba_player_profiles.parquet carries ONLY windows
  season_2025_26 / last20_2025_26 -- WHOLE-SEASON aggregates. Conditioning a
  2025-26 game on them is a look-ahead LEAK, and they do not cover 2024-25 or
  2023-24 at all. So the profile parquet is UNUSABLE here. Instead every prior
  is recomputed DIRECTLY AS-OF from raw pbp / stints with a strictly-prior
  `date < game_date` cut -- identical discipline to livestate_priors' top3-FGA
  / league-rate / net48 tables. The per-season season-aggregate artifacts
  (zone_onoff_*, on_off_*) are NOT used as priors either (they are whole-season
  = the same leak). Result: leak-legal on all 3 seasons pbp/stints cover.

Three preregistered ATTRIBUTE x LIVE interactions (each a single home-minus-away
scalar = prior_diff * realized_diff, added as ONE column to the base):
  H1 rim_pressure_def (half)   : prior opp-rim-share-allowed x realized rim
                                 pressure faced through half.
  H2 shot_diet_three_share(endQ1): prior 3PA-share x realized Q1 3PT luck
                                 (cold-from-three regression signal).
  H3 lineup_continuity (half)  : prior starting-5 stability x realized
                                 starter-minutes disruption (foul-trouble proxy).

Realized sides reuse the leak-free checkpoint machinery verbatim (shot_tally_
before / floor_lineup_at / truncated_minutes_at, all elapsed<=t or start_g<t).
The incremental gate is score_rung's twin: base and candidate differ by EXACTLY
the one new interaction column (base carries the surviving star_minutes_load at
endQ1). Ledger method 'ingame_attribute_conditioning_v1'. Calibration only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from scripts.platformkit.compose.team_form import team_id_to_abbr
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.ingame_compose.attribute_priors import (
    build_continuity, build_shot_priors, continuity_asof, luck3, rim_allowed_asof,
    rim_share, rim_tally_before, starter_disruption, three_share_asof,
)
from scripts.platformkit.ingame_compose.checkpoints import CHECKPOINTS
from scripts.platformkit.ingame_compose.conditional_gate_v2 import (
    _load_v2_states, _season_paths, _standardize_cols,
)
from scripts.platformkit.ingame_compose.livestate_ingame import (
    add_global_times, shot_tally_before,
)
from scripts.platformkit.ingame_compose.livestate_priors import (
    build_league_shot_rate_table, league_shot_rates_asof,
)
from scripts.platformkit.intel_weighting.relevance_gate import (
    _DM_ALPHA, _MIN_TEST, _TRAIN_FRAC, _brier, _fit, _sigmoid,
)

METHOD = "ingame_attribute_conditioning_v1"
# hypothesis -> (checkpoint, base survivor cols added to intercept+score)
_HYPS = {
    "rim_pressure_def x realized rim pressure": ("half", []),
    "shot_diet_three_share x realized Q1 3PT luck": ("endQ1", ["star_minutes_load"]),
    "lineup_continuity x realized starter disruption": ("half", []),
}
_TERM = {  # hypothesis -> feature column carrying its interaction scalar
    "rim_pressure_def x realized rim pressure": "term_rim",
    "shot_diet_three_share x realized Q1 3PT luck": "term_diet",
    "lineup_continuity x realized starter disruption": "term_cont",
}


# ------------------------------- the gate ------------------------------------
@dataclass
class HypResult:
    hypothesis: str
    season: str
    checkpoint: str
    n_test: int
    delta: float
    delta_trunc80: float
    dm_p: float
    verdict: str
    beta: float = 0.0
    caveats: List[str] = field(default_factory=list)


def _score_incremental(base_cols: List[str], term: str, elo: np.ndarray,
                       feats: pd.DataFrame, y: np.ndarray, gid: np.ndarray,
                       hyp: str, season: str, checkpoint: str) -> HypResult:
    """base = intercept + score_z + base_cols; candidate = base + term. They
    differ by EXACTLY the one `term` column -- the comparability invariant.
    Identical fit/score/DM as conditional_gate_v2.score_rung."""
    n = len(y)
    n_tr = int(n * _TRAIN_FRAC)
    n_te = n - n_tr
    if n_te < _MIN_TEST:
        return HypResult(hyp, season, checkpoint, n_te, 0.0, 0.0, 1.0,
                         "NOT_TESTABLE", 0.0, [f"only {n_te} OOS games"])
    tr, te = slice(0, n_tr), slice(n_tr, n)
    cols = ["score"] + base_cols + [term]
    z = _standardize_cols(feats, cols, tr)
    ones_tr, ones_te = np.ones((n_tr, 1)), np.ones((n_te, 1))
    base_names = ["score"] + base_cols

    base_tr = np.column_stack([ones_tr] + [z[c][tr] for c in base_names])
    base_te = np.column_stack([ones_te] + [z[c][te] for c in base_names])
    th_b = _fit(elo[tr], base_tr, y[tr])
    p_b = _sigmoid(elo[te] + base_te @ th_b)

    cand_tr = np.column_stack([base_tr, z[term][tr]])
    cand_te = np.column_stack([base_te, z[term][te]])
    th_c = _fit(elo[tr], cand_tr, y[tr])
    p_c = _sigmoid(elo[te] + cand_te @ th_c)

    yb = y[te]
    delta = _brier(p_b, yb) - _brier(p_c, yb)
    d = (p_b - yb) ** 2 - (p_c - yb) ** 2
    dm_p = diebold_mariano(d, gid[te]).p_value
    cut = int(n_te * 0.8)
    delta_t80 = _brier(p_b[:cut], yb[:cut]) - _brier(p_c[:cut], yb[:cut])
    verdict = ("MATTERS_PROVISIONAL" if delta > 0 and dm_p < _DM_ALPHA and delta_t80 > 0
               else "NULL")
    cav = (["single-fold, one season: PROVISIONAL until replicated on >=2 seasons"]
           if verdict == "MATTERS_PROVISIONAL" else [])
    return HypResult(hyp, season, checkpoint, n_te, round(delta, 6), round(delta_t80, 6),
                     round(dm_p, 4), verdict, round(float(th_c[-1]), 4), cav)


def _build_feature_rows(season: str):
    """Per (game, checkpoint) row: score_diff + star_minutes_load (from the
    reused v2 loader) + the 3 interaction scalars + y + elo. A game/checkpoint
    is INCLUDED per-hypothesis only where that hypothesis' prior+realized are
    both defined (never imputed)."""
    ev, states, elo, _skips = _load_v2_states(season)
    pbp_dir, stints_path = _season_paths(season)
    stints_all = add_global_times(pd.read_parquet(stints_path))
    shot_tbl = build_shot_priors(pbp_dir, ev)
    cont = build_continuity(stints_all, ev)
    rate_tbl = build_league_shot_rate_table()
    id_by_abbr = {v: k for k, v in team_id_to_abbr().items()}

    rows: Dict[str, List[dict]] = {cid: [] for cid, _t, _f in CHECKPOINTS}
    for r in ev.itertuples(index=False):
        gid = str(r.game_id)
        if gid not in states:
            continue
        fp = pbp_dir / f"{gid}.json"
        acts = json.loads(fp.read_text(encoding="utf-8"))["game"]["actions"]
        gstints = stints_all[stints_all["game_id"].astype(str) == gid]
        h_id, a_id = id_by_abbr.get(r.home_team), id_by_abbr.get(r.away_team)
        if h_id is None or a_id is None:
            continue
        # strictly-prior priors (home-away diffs; None -> hypothesis skips game)
        ra_h, ra_a = rim_allowed_asof(shot_tbl, r.home_team, r.date), rim_allowed_asof(shot_tbl, r.away_team, r.date)
        ts_h, ts_a = three_share_asof(shot_tbl, r.home_team, r.date), three_share_asof(shot_tbl, r.away_team, r.date)
        co_h, co_a = continuity_asof(cont, h_id, r.date), continuity_asof(cont, a_id, r.date)
        _p2, p3, _pft = league_shot_rates_asof(rate_tbl, r.date)

        for cid, t, _f in CHECKPOINTS:
            st = states[gid].get(cid)
            if st is None:
                continue
            score_diff, _fq, star_load, _lk, _bd = st
            base = {"date": r.date, "gid": gid, "y": float(r.home_win),
                    "elo": elo[gid], "score": score_diff, "star_minutes_load": star_load}
            rt = rim_tally_before(acts, t)
            stal = shot_tally_before(acts, t)
            # H1 rim
            rs_h, rs_a = rim_share(rt, h_id), rim_share(rt, a_id)
            if None not in (ra_h, ra_a, rs_h, rs_a):
                base["term_rim"] = (ra_h - ra_a) * (rs_a - rs_h)
            # H2 shot diet
            if None not in (ts_h, ts_a):
                base["term_diet"] = (ts_h - ts_a) * (luck3(stal, h_id, p3) - luck3(stal, a_id, p3))
            # H3 continuity
            dh, da = starter_disruption(gstints, h_id, t), starter_disruption(gstints, a_id, t)
            if None not in (co_h, co_a, dh, da):
                base["term_cont"] = (co_h - co_a) * (dh - da)
            rows[cid].append(base)
    return rows


def run_hypotheses(season: str) -> List[HypResult]:
    rows_by_cp = _build_feature_rows(season)
    out: List[HypResult] = []
    for hyp, (cid, base_cols) in _HYPS.items():
        term = _TERM[hyp]
        rows = [r for r in rows_by_cp[cid] if term in r]
        if not rows:
            out.append(HypResult(hyp, season, cid, 0, 0.0, 0.0, 1.0, "NOT_TESTABLE",
                                 0.0, ["no game had this prior+realized defined"]))
            continue
        rows.sort(key=lambda x: x["date"])
        feats = pd.DataFrame(rows)
        y = feats["y"].to_numpy(dtype=float)
        elo = feats["elo"].to_numpy(dtype=float)
        gid = feats["gid"].to_numpy()
        out.append(_score_incremental(base_cols, term, elo, feats, y, gid, hyp, season, cid))
    return out


if __name__ == "__main__":  # pragma: no cover - smoke
    import sys
    season = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
    for r in run_hypotheses(season):
        print(f"{r.season} {r.checkpoint:6s} {r.hypothesis[:34]:34s} n={r.n_test:4d} "
              f"d={r.delta:+.6f} dm={r.dm_p:.4f} {r.verdict}")
