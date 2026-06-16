"""N3 in-game blend -- leak-free OOS harness (synthetic-validated PATTERN).

Walk-forward: fit the weight surface + P_live on season A ONLY, evaluate on
season B ONLY (and B->A). Reports per-quarter Brier, per-quarter reliability/ECE,
the in-sample-vs-OOS w-Brier overfit-trap gap (< 0.01 = discipline wired), and a
cluster-robust Diebold-Mariano (blend vs pregame-only) via the verified
eval_gate.dm_test.diebold_mariano, clustered by game_id.

HONESTY FLAG -- this harness ships the ARCHITECTURE + a synthetic-validated test
pattern. REAL NBA A->B / B->A leak-free OOS on real corpora is a HUMAN-RUN step,
still PENDING. Every proof dict carries validation_pending=True / corpus=SYNTHETIC
when run on the bundled two-season synthetic data. No real Brier/BSS is printed;
an honest BSS <= 0 / "market efficient" verdict is logged as a SUCCESS, never
edited away. No $-edge is ever computed. ASCII only.

Run: python domains/basketball_nba/ingame_blend_eval.py
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Sequence, Tuple

import numpy as np

from scripts.platformkit.eval_gate.dm_test import DMResult, diebold_mariano
from scripts.platformkit.eval_gate.ingame_blend import (
    blended_predictions,
    exp_smooth,
)
from domains.basketball_nba.ingame_blend_surface import (
    blend,
    fit_surface_on_season,
)

EDGE_CLAIMED = False
# Loud, machine-readable flag: real-corpus leak-free OOS is a HUMAN-RUN step.
REAL_OOS_VALIDATION_PENDING = True
_PENDING_NOTE = (
    "real NBA A->B / B->A leak-free OOS run is HUMAN-RUN; numbers here are "
    "synthetic-pattern only -- NOT a real-data win"
)
_OUT_DIR = os.path.join("data", "cache", "ingame")
_REG_SEC = 2880.0


# --------------------------------------------------------------------------- metrics
def brier(p: Sequence[float], y: Sequence[float]) -> float:
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2)) if p.size else float("nan")


def quarter_of(sec_remaining: float) -> int:
    """1..4 from seconds remaining in regulation (Q1 = most time left)."""
    frac_elapsed = 1.0 - max(0.0, min(1.0, sec_remaining / _REG_SEC))
    return min(4, 1 + int(frac_elapsed * 4))


def ece(p: Sequence[float], y: Sequence[float], n_bins: int = 10) -> float:
    """Expected calibration error (equal-width bins). Reported, NEVER optimized."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if p.size == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    tot = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (p >= lo) & (p < hi if i < n_bins - 1 else p <= hi)
        if not np.any(m):
            continue
        tot += (np.sum(m) / p.size) * abs(float(p[m].mean()) - float(y[m].mean()))
    return float(tot)


def per_quarter_brier(states: List[dict], preds: Sequence[float]) -> Dict[str, float]:
    out: Dict[str, List[Tuple[float, float]]] = {}
    for s, p in zip(states, preds):
        q = "Q%d" % quarter_of(s["seconds_remaining"])
        out.setdefault(q, []).append((p, s["outcome"]))
    return {q: brier([a for a, _ in v], [b for _, b in v]) for q, v in sorted(out.items())}


def dm_blend_vs_pregame(states: List[dict], blended: Sequence[float]) -> DMResult:
    """Cluster-robust DM (by game_id). d = loss_pregame - loss_blend; POSITIVE
    mean => blend better. Reuses the VERIFIED eval_gate diebold_mariano."""
    y = np.array([s["outcome"] for s in states], dtype=float)
    p0 = np.array([s["p0"] for s in states], dtype=float)
    pb = np.asarray(blended, dtype=float)
    gid = [s["game_id"] for s in states]
    d = (p0 - y) ** 2 - (pb - y) ** 2
    return diebold_mariano(d, gid)


# --------------------------------------------------------------------------- synthetic corpus
def make_synthetic_season(season: str, n_games: int = 120, seed: int = 0) -> List[dict]:
    """Two-season synthetic generator: a true latent home strength per game drives
    both the pregame P0 and the realized state, so a state-conditioned P_live can
    legitimately add information late. Purely for wiring/pattern proof -- NOT a
    real corpus. Each state row carries game_id for clustered SEs."""
    rng = np.random.default_rng(seed)
    states: List[dict] = []
    for g in range(n_games):
        gid = "%s_%04d" % (season, g)
        strength = float(rng.normal(0.0, 0.18))  # latent home edge
        p0 = float(min(0.97, max(0.03, 0.5 + strength)))
        outcome = 1.0 if rng.random() < p0 else 0.0
        margin_final = (1 if outcome else -1) * abs(rng.normal(8, 6))
        n_states = rng.integers(8, 16)
        for k in range(int(n_states)):
            frac_el = (k + 1) / (int(n_states) + 1)
            sec_rem = _REG_SEC * (1.0 - frac_el)
            # realized margin converges to the final outcome as time elapses
            noise = rng.normal(0.0, 9.0 * (1.0 - frac_el) + 1.0)
            score_diff = margin_final * frac_el + noise
            p_live = float(min(0.99, max(0.01,
                        0.5 + 0.045 * score_diff * (0.3 + 0.7 * frac_el))))
            states.append({
                "game_id": gid, "season": season,
                "p0": p0, "p_live": p_live,
                "seconds_remaining": float(sec_rem),
                "score_diff": float(score_diff),
                "outcome": float(outcome),
            })
    return states


# --------------------------------------------------------------------------- harness
def _apply_smoothing(states: List[dict], blended: np.ndarray, alpha: float = 0.4) -> np.ndarray:
    """Causal EMA per game over the blended series (uses only past values)."""
    by_game: Dict[str, List[int]] = {}
    for i, s in enumerate(states):
        by_game.setdefault(s["game_id"], []).append(i)
    out = np.array(blended, dtype=float)
    for idxs in by_game.values():
        seq = [blended[i] for i in idxs]
        smoothed = [exp_smooth(seq[: j + 1], alpha=alpha) for j in range(len(seq))]
        for i, v in zip(idxs, smoothed):
            out[i] = v
    return out


def evaluate(fit_states: List[dict], eval_states: List[dict],
             direction: str) -> dict:
    """Fit on fit_states, evaluate on eval_states. Returns a proof dict tagged
    validation_pending / corpus=SYNTHETIC (the ONLY corpus this harness ships)."""
    surf = fit_surface_on_season(fit_states)

    # in-sample vs OOS w-Brier (the overfit-trap gap; discipline wiring only)
    in_blend = blended_predictions(fit_states, surf)
    oos_blend_raw = blended_predictions(eval_states, surf)
    in_brier = brier(in_blend, [s["outcome"] for s in fit_states])
    oos_brier = brier(oos_blend_raw, [s["outcome"] for s in eval_states])
    overfit_gap = float(oos_brier - in_brier)

    oos_blend = _apply_smoothing(eval_states, oos_blend_raw)

    pregame_only = np.array([s["p0"] for s in eval_states], dtype=float)
    dm = dm_blend_vs_pregame(eval_states, oos_blend)

    pq_blend = per_quarter_brier(eval_states, oos_blend)
    pq_pregame = per_quarter_brier(eval_states, pregame_only)
    pq_ece = {}
    for q in pq_blend:
        sel = [(p, s["outcome"]) for s, p in zip(eval_states, oos_blend)
               if "Q%d" % quarter_of(s["seconds_remaining"]) == q]
        pq_ece[q] = ece([a for a, _ in sel], [b for _, b in sel])

    blend_b = brier(oos_blend, [s["outcome"] for s in eval_states])
    pregame_b = brier(pregame_only, [s["outcome"] for s in eval_states])
    # BSS of blend vs pregame-only; <= 0 is an HONEST verdict logged as SUCCESS.
    bss = 1.0 - blend_b / pregame_b if pregame_b > 0 else 0.0
    honest_verdict = "blend_adds_calibration" if (bss > 0 and dm.p_value < 0.05) \
        else "market_efficient_or_no_gain__SUCCESS"

    return {
        "direction": direction,
        "validation_pending": True,
        "corpus": "SYNTHETIC",
        "note": _PENDING_NOTE,
        "edge_claimed": False,
        "overfit_gap": overfit_gap,
        "overfit_gap_ok": bool(overfit_gap < 0.01),
        "dm_stat": dm.dm_stat,
        "dm_p_value": dm.p_value,
        "dm_n_clusters": dm.n_clusters,
        "per_quarter_brier_blend": pq_blend,
        "per_quarter_brier_pregame": pq_pregame,
        "per_quarter_ece_blend": pq_ece,
        "blend_bss_vs_pregame": bss,
        "honest_verdict": honest_verdict,
    }


def run_synthetic_proof(write: bool = True) -> dict:
    """A->B and B->A on the bundled synthetic two-season data. Returns the proof
    bundle; every entry is validation_pending=True / SYNTHETIC."""
    a = make_synthetic_season("synthA", seed=11)
    b = make_synthetic_season("synthB", seed=29)
    proof = {
        "real_oos_validation_pending": REAL_OOS_VALIDATION_PENDING,
        "corpus": "SYNTHETIC",
        "note": _PENDING_NOTE,
        "edge_claimed": False,
        "runs": [evaluate(a, b, "A->B"), evaluate(b, a, "B->A")],
    }
    if write:
        os.makedirs(_OUT_DIR, exist_ok=True)
        with open(os.path.join(_OUT_DIR, "ingame_blend_proof.json"), "w") as fh:
            json.dump(proof, fh, indent=2)
    return proof


def _print_ascii(proof: dict) -> None:
    print("N3 IN-GAME BLEND -- SYNTHETIC PATTERN PROOF (ASCII)")
    print("REAL_OOS_VALIDATION_PENDING = %s" % REAL_OOS_VALIDATION_PENDING)
    print("corpus = SYNTHETIC ; edge_claimed = False")
    print("note: %s" % _PENDING_NOTE)
    for run in proof["runs"]:
        print("-" * 60)
        print("direction          : %s" % run["direction"])
        print("overfit_gap (<0.01): %.5f  ok=%s"
              % (run["overfit_gap"], run["overfit_gap_ok"]))
        print("DM stat / p        : %.3f / %.4f (clusters=%d)"
              % (run["dm_stat"], run["dm_p_value"], run["dm_n_clusters"]))
        print("per-Q Brier blend  : %s"
              % {k: round(v, 4) for k, v in run["per_quarter_brier_blend"].items()})
        print("honest_verdict     : %s" % run["honest_verdict"])
    print("-" * 60)
    print("VALIDATION_PENDING: real two-corpus leak-free OOS vs the devigged")
    print("close is HUMAN-RUN. Honest BSS<=0 / market-efficient = SUCCESS.")


if __name__ == "__main__":
    _print_ascii(run_synthetic_proof(write=True))
