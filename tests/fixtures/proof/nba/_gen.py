"""Deterministic synthetic NBA fixture corpus for the platformkit NBA proofs.

Generates tiny (~200-game), schema-faithful replicas of the three real files the
NBA proofs read from data/domains/basketball_nba/:
  * espn_boxscores.parquet  (totals beat-close + ml beat-close)
  * odds.parquet            (the devigged closing line both beat-close proofs target)
  * linescores.parquet      (in-game per-quarter reconstruction)

The data is synthetic-but-realistic: each team has a latent strength, scores are
drawn around a possession/efficiency model, and the closing line/moneyline are the
true expectation PLUS market noise -- so the market is a strong-but-imperfect
forecaster and every proof returns status=ok with a FINITE, well-behaved gap.

Deterministic: fixed numpy seed, no wall-clock. Re-run to regenerate identical files:
    python tests/fixtures/proof/nba/_gen.py
INVARIANTS: ASCII-only; tiny parquets (<200KB each).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_SEED = 20260615
_N_GAMES = 220
_HFA_PTS = 2.7
_TEAMS = [
    "BOS", "NYK", "MIL", "CLE", "ORL", "PHI", "MIA", "IND", "ATL", "CHI",
    "OKC", "DEN", "MIN", "LAC", "DAL", "PHX", "LAL", "GSW", "SAC", "HOU",
]


def _american(p: float, rng: np.random.Generator) -> float:
    """True win prob -> a vigged American moneyline (book adds ~4.5% hold)."""
    p = float(np.clip(p, 0.04, 0.96))
    pv = np.clip(p + 0.022, 0.02, 0.98)             # half-vig on this side
    return round((-100.0 * pv / (1.0 - pv)) / 5.0) * 5.0 if pv >= 0.5 \
        else round((100.0 * (1.0 - pv) / pv) / 5.0) * 5.0


def generate() -> None:
    rng = np.random.default_rng(_SEED)
    nt = len(_TEAMS)
    # latent team offensive/defensive ratings (points per 100 around league mean)
    off = rng.normal(113.0, 4.5, nt)
    dfn = rng.normal(113.0, 4.5, nt)
    pace = rng.normal(99.5, 3.0, nt)

    start = pd.Timestamp("2025-10-21")
    rows_box, rows_odds, rows_ls = [], [], []
    for g in range(_N_GAMES):
        hi, ai = rng.choice(nt, size=2, replace=False)
        ht, at = _TEAMS[hi], _TEAMS[ai]
        date = start + pd.Timedelta(days=g // 4)      # ~4 games/day
        gp = float(np.clip(0.5 * (pace[hi] + pace[ai]) + rng.normal(0, 2.0), 88, 108))
        # expected points per team via off-vs-def efficiency, home gets HFA
        eh = gp * 0.5 * (off[hi] + dfn[ai]) / 100.0 / 100.0 * 100.0 + _HFA_PTS / 2.0
        ea = gp * 0.5 * (off[ai] + dfn[hi]) / 100.0 / 100.0 * 100.0 - _HFA_PTS / 2.0
        hp = int(np.clip(rng.normal(eh, 9.0), 80, 150))
        ap = int(np.clip(rng.normal(ea, 9.0), 80, 150))
        if hp == ap:
            hp += 1                                    # no ties (proofs drop them)

        # --- box detail (poss model reads fg/ft attempted, oreb, tov) ---
        def _detail(pts: int, poss: float):
            fga = int(np.clip(poss * 0.84 + rng.normal(0, 3), 70, 105))
            fta = int(np.clip(pts * 0.24 + rng.normal(0, 3), 8, 38))
            oreb = int(np.clip(rng.normal(10, 3), 3, 18))
            tov = int(np.clip(rng.normal(13.5, 3), 6, 22))
            return fga, fta, oreb, tov
        hfga, hfta, horeb, htov = _detail(hp, gp)
        afga, afta, aoreb, atov = _detail(ap, gp)

        eid = f"00224{g:05d}"
        rows_box.append({
            "event_id": eid, "date": date, "home_abbr": ht, "away_abbr": at,
            "home_score": float(hp), "away_score": float(ap),
            "home_pts": float(hp), "away_pts": float(ap),
            "home_fg_attempted": float(hfga), "away_fg_attempted": float(afga),
            "home_ft_attempted": float(hfta), "away_ft_attempted": float(afta),
            "home_oreb": float(horeb), "away_oreb": float(aoreb),
            "home_tov": float(htov), "away_tov": float(atov),
        })

        # --- closing line/ml: true expectation + market noise (book is sharp not perfect) ---
        true_total = eh + ea
        close_total = round((true_total + rng.normal(0, 2.0)) * 2) / 2 - 0.5
        margin_sigma = 13.5
        p_home = 0.5 * (1.0 + np.tanh((eh - ea) / (margin_sigma * 1.2)))
        p_home_mkt = float(np.clip(p_home + rng.normal(0, 0.03), 0.04, 0.96))
        rows_odds.append({
            "date": date.strftime("%Y-%m-%d"), "home_team": ht, "away_team": at,
            "home_ml": _american(p_home_mkt, rng),
            "away_ml": _american(1.0 - p_home_mkt, rng),
            "total": float(close_total),
            "spread": round((ea - eh) * 2) / 2,
        })

        # --- linescores: split each team's final into 4 quarters (Q4 slightly higher) ---
        def _split(total_pts: int):
            w = rng.dirichlet([4.0, 4.0, 4.0, 4.3])
            q = np.round(w * total_pts).astype(int)
            q[-1] += total_pts - int(q.sum())          # make quarters sum to final
            return [int(x) for x in q]
        hq, aq = _split(hp), _split(ap)
        rows_ls.append({
            "event_id": eid, "home_abbr": ht,
            "home_q1": float(hq[0]), "home_q2": float(hq[1]),
            "home_q3": float(hq[2]), "home_q4": float(hq[3]),
            "away_abbr": at,
            "away_q1": float(aq[0]), "away_q2": float(aq[1]),
            "away_q3": float(aq[2]), "away_q4": float(aq[3]),
            "date": date,
        })

    pd.DataFrame(rows_box).to_parquet(_HERE / "espn_boxscores.parquet", index=False)
    pd.DataFrame(rows_odds).to_parquet(_HERE / "odds.parquet", index=False)
    pd.DataFrame(rows_ls).to_parquet(_HERE / "linescores.parquet", index=False)
    print(f"wrote {len(rows_box)} games to {_HERE}")


if __name__ == "__main__":
    generate()
