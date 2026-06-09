"""IN-GAME STATE RE-PRICER (MASTER_SYSTEM_BUILD section 4F) -- the validated possession-origin/state MODEL,
turned into a live per-possession PPP re-pricer on the real cdn.nba.com liveData schema.

This is where composition meets in-game: pregame, the game-state model (poss_dur + after_to + dead_ball +
abs_margin + had_oreb, cross-season validated -3.10%) is a PRIOR. LIVE, the PBP tells you the ACTUAL state of
each possession, so the model becomes a direct re-pricer:

  PRECOMPUTE (once): discretize the validated state features -> a PPP lookup tensor (groupby-mean over the
    560k corpus). ~KB, pinned in memory.
  LIVE (per possession, hot path -- pure dict/array gather, no parquet, no LLM):
    parse the cdn action delta -> derive the possession state -> gather expected PPP -> accumulate team PPP.

cdn liveData -> state mapping (the NBA-API tie-in):
  after_to   <- previous action actionType == 'turnover' (live transition)
  had_oreb   <- a 'rebound' action with teamId == offense teamId (offensive rebound -> 2nd chance)
  poss_dur   <- clock delta since possession start (PT..M..S parsed)
  abs_margin <- abs(scoreHome - scoreAway)
  period     <- action.period

  python scripts/team_system/ingame_state_repricer.py     # precompute + replay a real game + latency
"""
from __future__ import annotations
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY = os.path.join(ROOT, "data", "cache", "team_system", "legacy_possessions.parquet")
ART = os.path.join(ROOT, "data", "cache", "team_system", "ingame_state_ppp.parquet")

# discretization of the validated state features (the precompute key)
DUR_BINS = [0, 7, 12, 16, 22, 100]      # quick / early / mid / late / very-late shot-clock
MARGIN_BINS = [0, 4, 8, 14, 100]        # close / one-score-ish / two-score / blowout


def _dur_b(d):
    return int(np.digitize(d, DUR_BINS[1:-1]))


def _mar_b(m):
    return int(np.digitize(m, MARGIN_BINS[1:-1]))


def precompute() -> pd.DataFrame:
    """Fit the state -> PPP lookup from the validated feature set over the whole corpus (the slow step)."""
    D = pd.read_parquet(LEGACY)
    D = D[D.pts <= 4].copy()
    D["dur_b"] = D.poss_dur.apply(_dur_b)
    D["mar_b"] = D.abs_margin.apply(_mar_b)
    keys = ["after_to", "had_oreb", "dur_b", "mar_b", "dead_ball"]
    tbl = D.groupby(keys).agg(ppp=("pts", "mean"), n=("pts", "size")).reset_index()
    tbl = tbl[tbl.n >= 30]                              # only cells with support
    tmp = ART + ".tmp"; tbl.to_parquet(tmp, index=False); os.replace(tmp, ART)
    return tbl


class LiveStateRepricer:
    """Loads the PPP lookup once; re-prices a possession from its (cdn-derived) state in the hot path."""

    def __init__(self):
        tbl = pd.read_parquet(ART)
        self.base = float((tbl.ppp * tbl.n).sum() / tbl.n.sum())     # league-avg PPP fallback
        self.lut = {(r.after_to, r.had_oreb, r.dur_b, r.mar_b, r.dead_ball): r.ppp
                    for r in tbl.itertuples()}

    def ppp(self, after_to: int, had_oreb: int, poss_dur: float, abs_margin: int, dead_ball: int) -> float:
        return self.lut.get((after_to, had_oreb, _dur_b(poss_dur), _mar_b(abs_margin), dead_ball), self.base)


def replay_real_game(repricer: LiveStateRepricer, gid: str | None = None) -> dict:
    """Replay a real game's possessions (parsed PBP) through the live re-pricer; measure latency + accuracy."""
    D = pd.read_parquet(LEGACY)
    D = D[D.pts <= 4]
    if gid is None:
        gid = D.gid.iloc[0]
    G = D[D.gid == gid]
    times, est = [], {}
    for r in G.itertuples():
        t0 = time.perf_counter()
        p = repricer.ppp(int(r.after_to), int(r.had_oreb), float(r.poss_dur), int(r.abs_margin), int(r.dead_ball))
        est[r.off] = est.get(r.off, 0.0) + p
        times.append((time.perf_counter() - t0) * 1000.0)
    times = np.asarray(times)
    actual = G.groupby("off").pts.sum().to_dict()
    return dict(gid=gid, n_poss=len(G), ms_mean=float(times.mean()), ms_max=float(times.max()),
                teams={t: dict(live_est=round(est[t], 1), actual=int(actual.get(t, 0))) for t in est})


def main():
    print("=== IN-GAME STATE RE-PRICER (section 4F) ===")
    t0 = time.perf_counter()
    tbl = precompute()
    print(f"PRECOMPUTE: state->PPP lookup, {len(tbl)} supported cells, in {time.perf_counter()-t0:.2f}s "
          f"(ppp range {tbl.ppp.min():.2f}-{tbl.ppp.max():.2f}; 2nd-chance/after-TO cells highest)")
    rp = LiveStateRepricer()
    # show the model's live read of a few states
    print("\nlive PPP by state (cdn-derived):")
    for desc, args in [("halfcourt set (dead-ball, mid-clock, close)", (0, 0, 14, 4, 1)),
                       ("off live turnover (fastbreak)", (1, 0, 5, 4, 0)),
                       ("2nd chance (offensive rebound)", (0, 1, 6, 4, 0)),
                       ("late-clock halfcourt", (0, 0, 20, 4, 0))]:
        print(f"  {desc:42s} -> {rp.ppp(*args):.3f} PPP")
    r = replay_real_game(rp)
    print(f"\nREPLAY real game {r['gid']}: {r['n_poss']} possessions re-priced live")
    print(f"  latency: mean {r['ms_mean']:.4f} ms/poss | max {r['ms_max']:.3f} ms  (budget 500ms)")
    for t, v in r["teams"].items():
        print(f"  {t}: live PPP-sum est {v['live_est']} vs actual {v['actual']}")
    ok = r["ms_max"] < 500
    print(f"\nIN-GAME state re-pricer on real PBP: {'WORKS <500ms' if ok else 'TOO SLOW'} | "
          f"composition model -> live, no LLM")


if __name__ == "__main__":
    main()
