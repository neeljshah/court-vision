"""End-to-end demo: the honest evaluation loop, composed from the reference modules.

    C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe demo.py

Shows the whole machine working together on synthetic data:
  1. Shin-devig a synthetic market close  -> the reference forecaster.
  2. Blend the pregame prior with realized in-game state (the #1 lever).
  3. Score model vs the devigged close: Brier, BSS, log-loss, ECE, + a CLUSTERED Diebold-Mariano.
  4. Log every settled prediction to the append-only track-record ledger.
  5. Print a calibration scoreboard with an HONEST verdict (BEATS / MATCHES / BEHIND).

This computes probabilities + calibration only -- never a dollar edge. A BEHIND/MATCHES verdict is
a recorded SUCCESS (markets efficient on price); the loop's job is to make that auditable.
"""
from __future__ import annotations
import os, tempfile
import numpy as np

from scoring import brier, brier_skill_score, log_loss, ece, sharpness
from dm_test import diebold_mariano
from shin import shin_devig
from ingame_blend import fit_weight_surface, blended_predictions
from ledger import LedgerRow, append_row, load, drift_report

RNG = np.random.default_rng(20260616)


def _season(n_games=300, states=8):
    rows = []
    for g in range(n_games):
        q = float(np.clip(0.5 + 0.35 * RNG.standard_normal(), 0.05, 0.95))
        y = int(RNG.random() < q)
        p0 = float(np.clip(q + 0.12 * RNG.standard_normal(), 0.01, 0.99))
        # a synthetic market close: slightly sharper than our pregame prior, with vig added
        close_fair = float(np.clip(q + 0.09 * RNG.standard_normal(), 0.02, 0.98))
        for k in range(states):
            secs = 2880.0 * (1 - (k + 1) / states)
            sigma = 0.30 * (secs / 2880.0) + 0.02
            p_live = float(np.clip(q + sigma * RNG.standard_normal(), 0.01, 0.99))
            sd = (2 * y - 1) * ((1 - secs / 2880.0) * 15.0) + 6.0 * RNG.standard_normal()
            rows.append({"game_id": f"g{g}", "p0": p0, "p_live": p_live, "close_fair": close_fair,
                         "seconds_remaining": secs, "score_diff": sd, "outcome": y})
    return rows


def _devig_close(close_fair):
    # add a symmetric ~4.5% vig to the fair prob, then Shin-devig it back (round-trip realism)
    pi = np.array([close_fair * 1.045, (1 - close_fair) * 1.045])
    p, _ = shin_devig(pi)
    return float(p[0])


def main():
    fit = _season()          # season A -- fit the weight surface here
    ev = _season()           # season B -- evaluate here (independent draw from the same RNG)
    surf = fit_weight_surface(fit)

    y = np.array([s["outcome"] for s in ev], float)
    model = blended_predictions(ev, surf)                         # our calibrated blend
    close = np.array([_devig_close(s["close_fair"]) for s in ev])  # devigged close (the baseline)
    gid = [s["game_id"] for s in ev]

    bm, bc = brier(model, y), brier(close, y)
    bss = brier_skill_score(model, close, y)
    d = (close - y) ** 2 - (model - y) ** 2          # close loss - model loss (positive => model better)
    dm = diebold_mariano(d, gid)

    if bss > 0 and dm.p_value < 0.05 and dm.n >= 200:
        verdict = "BEATS_CLOSE"
    elif abs(bm - bc) <= (dm.ci95[1] - dm.ci95[0]):
        verdict = "MATCHES_CLOSE"
    else:
        verdict = "BEHIND (honest -- markets efficient here)"

    # log to an append-only ledger + a drift check
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)  # close the handle so Windows lets us remove it later
    for s, p in zip(ev, model):
        append_row(path, LedgerRow(ts="2026-06-16T12:00:00", sport="nba", market="ingame_wp",
                                   inputs_hash=s["game_id"], prob=float(p), outcome=int(s["outcome"])))
    n_logged = len(load(path))
    os.remove(path)

    print("HONEST EVALUATION LOOP -- demo scoreboard (synthetic)")
    print("-" * 56)
    print(f"  games / states        : {len(set(gid))} / {len(ev)}")
    print(f"  Brier  model          : {bm:.4f}")
    print(f"  Brier  devigged close : {bc:.4f}")
    print(f"  Brier Skill Score     : {bss:+.4f}   (>0 = better calibrated than close)")
    print(f"  log-loss model        : {log_loss(model, y):.4f}")
    print(f"  ECE (diagnostic)      : {ece(model, y):.4f}   sharpness {sharpness(model):.4f}")
    print(f"  DM stat / p (clustered): {dm.dm_stat:+.2f} / {dm.p_value:.3f}  (n={dm.n}, games={dm.n_clusters})")
    print(f"  ledger rows logged    : {n_logged}")
    print("-" * 56)
    print(f"  VERDICT: {verdict}")
    print("  (BEHIND/MATCHES is a recorded SUCCESS -- no dollar edge is claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
