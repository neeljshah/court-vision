"""domains.mlb.pitch_engine.game_sim_v3 -- COMPOSITION-conditioned reliever
game Monte-Carlo (pitch-engine v3 candidate, gate lane G1).

Near-copy of game_sim_v2.simulate_game_v2 with ONE change: the reliever PA-event
matrix is [N_BUCKET, N_LEAD, 8] (bullpen_v3.RelieverPAv3.bucket_lead_matrix) --
NOT per-slot like v2's [N_BUCKET, N_LEAD, 9, 8] -- because v3 conditions the
reliever pool on pitcher-quality-TIER composition instead of batter tier
(ponytail: isolates the one new variable under test; batter-tier x reliever-
tier interaction is a v4 seam if this one ships). Starter removal timing
(bullpen.RemovalModel) and starter PA dists are UNCHANGED from v1/v2.

INVARIANTS: domains-only; ASCII; numpy only; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_game_sim_v3.py -q
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from domains.mlb.pitch_engine.game_sim import (BaseOutTransition, GameStart,
                                               INNING_OVER, _MAX_STEPS, _EXTRA_CAP)
from domains.mlb.pitch_engine.bullpen import RemovalModel, MIN_REMOVAL_INN, inn_bucket_arr


def simulate_game_v3(pa_away_sp: np.ndarray, pa_home_sp: np.ndarray,
                     rp_vs_away: np.ndarray, rp_vs_home: np.ndarray,
                     trans: BaseOutTransition, removal: RemovalModel,
                     n: int = 2000, seed: int = 0,
                     start: Optional[GameStart] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Return (home_final[n], away_final[n]).

    pa_away_sp/pa_home_sp : [9,8] STARTER PA-event dists per lineup slot.
    rp_vs_away/rp_vs_home : [N_BUCKET,N_LEAD,8] COMPOSITION-mixed RELIEVER
        PA-event dists per (inn_bucket, leverage/lead_state) -- no slot axis.
        rp_vs_away = dist faced by AWAY batters (home bullpen), rp_vs_home =
        faced by HOME batters (away bullpen)."""
    rng = np.random.default_rng(seed)
    s = start or GameStart()
    inn = np.full(n, s.inning); half = np.full(n, s.half)
    outs = np.full(n, s.outs); mask = np.full(n, s.base_mask)
    sh = np.full(n, s.home_score, dtype=int); sa = np.full(n, s.away_score, dtype=int)
    aslot = np.full(n, s.away_slot); hslot = np.full(n, s.home_slot)
    done = np.zeros(n, dtype=bool)

    cdf_a_sp = np.cumsum(pa_away_sp, axis=1); cdf_h_sp = np.cumsum(pa_home_sp, axis=1)
    cdf_rp_a = np.cumsum(rp_vs_away, axis=2); cdf_rp_h = np.cumsum(rp_vs_home, axis=2)

    home_sp_out = np.zeros(n, dtype=bool); away_sp_out = np.zeros(n, dtype=bool)
    home_eval = np.full(n, -1); away_eval = np.full(n, -1)
    if s.inning > MIN_REMOVAL_INN:                       # snapshot: pre-resolve survival
        home_lead = int(np.sign(s.home_score - s.away_score)) + 1
        away_lead = int(np.sign(s.away_score - s.home_score)) + 1
        home_sp_out = rng.random(n) < removal.removed_by(s.inning, home_lead)
        away_sp_out = rng.random(n) < removal.removed_by(s.inning, away_lead)
        home_eval[:] = s.inning; away_eval[:] = s.inning

    for _ in range(_MAX_STEPS):
        act = ~done
        if not act.any():
            break
        bat_home = half == 1                              # home batting -> away pitches
        sp_out = np.where(bat_home, away_sp_out, home_sp_out)
        eval_inn = np.where(bat_home, away_eval, home_eval)
        pit_lead = np.where(bat_home, sa - sh, sh - sa)   # pitcher-team perspective
        lead_idx = np.where(pit_lead > 0, 2, np.where(pit_lead < 0, 0, 1))
        need = act & (~sp_out) & (eval_inn != inn) & (inn >= MIN_REMOVAL_INN)
        haz = removal.hazard_vec(inn, lead_idx)
        new_out = need & (rng.random(n) < haz)
        away_sp_out = np.where(bat_home & new_out, True, away_sp_out)
        home_sp_out = np.where(~bat_home & new_out, True, home_sp_out)
        away_eval = np.where(bat_home & need, inn, away_eval)
        home_eval = np.where(~bat_home & need, inn, home_eval)
        sp_out = np.where(bat_home, away_sp_out, home_sp_out)

        slot = np.where(bat_home, hslot, aslot)
        ib = inn_bucket_arr(inn)
        cdf_sp = np.where(bat_home[:, None], cdf_h_sp[slot], cdf_a_sp[slot])
        cdf_rp = np.where(bat_home[:, None], cdf_rp_h[ib, lead_idx], cdf_rp_a[ib, lead_idx])
        cdf = np.where(sp_out[:, None], cdf_rp, cdf_sp)
        u = rng.random(n)
        evt = np.clip((u[:, None] >= cdf).sum(axis=1), 0, 7)

        bos = mask * 3 + outs
        key = bos * 8 + evt
        runs, nxt = trans.sample(key, evt, rng)
        runs = np.where(act, runs, 0)
        sh = sh + np.where(act & bat_home, runs, 0)
        sa = sa + np.where(act & ~bat_home, runs, 0)
        aslot = np.where(act & ~bat_home, (aslot + 1) % 9, aslot)
        hslot = np.where(act & bat_home, (hslot + 1) % 9, hslot)
        prev_half = half.copy()
        over = act & (nxt >= INNING_OVER)
        cont = act & (nxt < INNING_OVER)
        outs = np.where(cont, nxt % 3, np.where(over, 0, outs))
        mask = np.where(cont, nxt // 3, np.where(over, 0, mask))
        inc_inn = over & (prev_half == 1)
        half = np.where(over, 1 - prev_half, half)
        inn = np.where(inc_inn, inn + 1, inn)
        done |= act & bat_home & (inn >= 9) & (sh > sa)
        done |= over & (prev_half == 0) & (inn >= 9) & (sh > sa)
        done |= inc_inn & ((inn - 1) >= 9) & (sh != sa)
        done |= inn > _EXTRA_CAP
    tie = (~done) & (sh == sa)
    if tie.any():
        sh = sh + (rng.random(n) < 0.5) * tie
    return sh, sa


__all__ = ["simulate_game_v3"]
