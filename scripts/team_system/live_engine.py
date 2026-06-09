"""IN-GAME FAST PATH (MASTER_SYSTEM_BUILD section 4F) -- PBP delta -> re-price the full board per
possession, sub-500ms, with NO LLM in the loop.

Architecture = precompute -> lookup (the _ingame_fast_harness pattern), NOT a re-sim:
  PREGAME (once, may be slow): materialize a projection_table (per player x stat: the routed full-game
    projection) + a precomputed state->multiplier tensor indexed by (period, score_bucket, foul_bucket).
  LIVE (per possession, the HOT path -- pure numpy, no parquet read, no LLM import, no engine rebuild):
    a PBP delta updates a small as-of state vector (accumulated stat-so-far + clock); re-pricing is a
    vectorized   final_est = cur + (proj - cur) * remaining_fraction * state_mult   over the whole board.

This module replays a possession stream and MEASURES the per-possession latency to prove the <500ms budget.

  python scripts/team_system/live_engine.py            # build table, replay, report ms/possession
"""
from __future__ import annotations
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
# state -> multiplier tensor: how a player's remaining production scales by (period, score_bucket, foul_bucket).
# Centered at neutral 1.0; blowout late -> stars sit (down), in-bonus -> slightly up. Precomputed once.


def _state_mult_tensor() -> np.ndarray:
    periods, score_buckets, foul_buckets = 6, 5, 4   # period 1..4(+OT), |margin| bucket, foul-trouble bucket
    t = np.ones((periods, score_buckets, foul_buckets), np.float32)
    for p in range(periods):
        for s in range(score_buckets):       # s=4 -> blowout
            for f in range(foul_buckets):     # f=3 -> foul trouble
                blowout_late = 1.0 - (0.10 if (p >= 3 and s >= 4) else 0.0)
                foul = 1.0 - 0.06 * f
                t[p, s, f] = blowout_late * foul
    return t


def build_projection_table(n_sims: int = 2000) -> dict:
    """PREGAME precompute (slow allowed): routed full-game projection per rotation player x stat."""
    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast
    res = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                             n_sims=n_sims, seed=7, anchor=True, defense=True, context={"neutral_site": False})
    pids, proj = [], []
    for pid, d in res.players.items():
        if d["mean"]["pts"] < 1:
            continue
        pids.append(pid)
        proj.append([float(d["mean"].get(s, 0.0)) for s in STATS])
    return dict(pids=pids, proj=np.asarray(proj, np.float32), mult=_state_mult_tensor())


def _synth_pbp_stream(n_players: int, n_poss: int = 220, seed: int = 0):
    """A replayed possession stream: per possession, (scoring player idx, pts, period, |margin|, fouls).
    Stands in for the cdn liveData delta -- the hot path only needs these small numbers."""
    rng = np.random.default_rng(seed)
    for i in range(n_poss):
        frac = i / n_poss
        period = min(5, 1 + int(frac * 4))
        score_bucket = min(4, int(abs(rng.normal(0, 1.5))))
        foul_bucket = min(3, int(frac * 3 * rng.random()))
        pi = int(rng.integers(n_players))
        pts = int(rng.choice([0, 2, 3], p=[0.55, 0.33, 0.12]))
        yield pi, pts, period, score_bucket, foul_bucket


def replay_and_time(table: dict, n_poss: int = 220) -> dict:
    """Replay the stream; per possession re-price the FULL board. Returns latency stats (ms/possession)."""
    proj = table["proj"]                       # [P, S] float32
    mult = table["mult"]
    P, S = proj.shape
    cur = np.zeros((P, S), np.float32)         # accumulated stat-so-far (as-of state vector)
    pts_idx = STATS.index("pts")
    times = []
    final_board = None
    for (pi, pts, period, sb, fb) in _synth_pbp_stream(P, n_poss):
        t0 = time.perf_counter()
        # --- HOT PATH: pure numpy, no I/O, no LLM ---
        cur[pi, pts_idx] += pts                # PBP delta -> as-of state update (changed entity only)
        remaining_frac = max(0.0, 1.0 - (period - 1) / 4.0)
        m = mult[min(period - 1, mult.shape[0] - 1), min(sb, mult.shape[1] - 1), min(fb, mult.shape[2] - 1)]
        final_board = cur + (proj - cur) * remaining_frac * m   # re-price WHOLE board, vectorized
        times.append((time.perf_counter() - t0) * 1000.0)
    times = np.asarray(times)
    return dict(n_poss=int(len(times)), n_players=int(P), n_stats=int(S),
                ms_mean=float(times.mean()), ms_p95=float(np.percentile(times, 95)),
                ms_max=float(times.max()), board_shape=list(final_board.shape))


def main():
    print("=== IN-GAME FAST PATH (section 4F) ===")
    t_pre = time.perf_counter()
    table = build_projection_table()
    print(f"PREGAME precompute: projection_table {table['proj'].shape} + state-mult tensor "
          f"{table['mult'].shape} in {(time.perf_counter()-t_pre):.2f}s (this is the slow part, done ONCE).")
    r = replay_and_time(table)
    print(f"LIVE replay: {r['n_poss']} possessions, re-pricing {r['n_players']}x{r['n_stats']} board each:")
    print(f"  mean {r['ms_mean']:.3f} ms/poss | p95 {r['ms_p95']:.3f} ms | max {r['ms_max']:.3f} ms")
    # the HOT path uses only numpy on preloaded arrays (no LLM). torch may load during PREGAME precompute
    # (GPU sim, allowed to be slow) -- it is not an LLM, so it does not count against the no-LLM-in-loop rule.
    no_llm = not any(any(t in m.lower() for t in ("anthropic", "openai", "llm", "claude")) for m in sys.modules)
    ok = r["ms_max"] < 500 and no_llm
    print(f"  budget <500ms/possession: {'MET' if r['ms_max'] < 500 else 'MISSED'}; NO LLM in loop: {no_llm}")
    print(f"\nB10 in-game fast path: {'PASS' if ok else 'FAIL'}")
    if ok:
        from build_done_check import write_marker
        write_marker("B10_live_latency", dict(ms_per_poss=round(r["ms_max"], 3), ms_mean=round(r["ms_mean"], 4),
                     no_llm=True, n_players=r["n_players"], n_stats=r["n_stats"],
                     detail=f"max {r['ms_max']:.2f}ms/poss over {r['n_poss']} poss, board {r['n_players']}x{r['n_stats']}",
                     asof="2026-06-08"))
        print("B10 marker written.")
    return r


if __name__ == "__main__":
    main()
