"""domains.baseball_npb.ingame_base_fit -- attempts to fit the NPB in-game BASE
win-prob model p_home = sigmoid((a + b*frac_elapsed) * state_diff) for live
win-prob grading, using the proven cross-sport BASE machinery
(scripts.platformkit.ingame.ingame_gate_generic_models.fit_base / base_predict /
base_is_degenerate -- same fitter NBA/MLB/soccer/tennis use).

DATA-AVAILABILITY WALL (documented, not silently worked around): investigation this
lane (see test_npb_kbo_live_model_gap.py, data/domains/npb_kbo_model_wire_proof.json
from the prior npb-kbo-live-model lane) found ZERO real intra-game tick files for NPB
-- data/cache/ingame has no npb_states__*.parquet, the live feed
(scripts.platformkit.ingame.npb_kbo_live_state) always returns frac_elapsed=None
(npb.jp's schedule-detail page has no mid-game marker keyless), and
data/domains/npb/npb_results.parquet is FINAL-SCORE-ONLY (no innings/running-score,
3,964 games, rebuilt 2026-07-05).

FIX ROUND 2026-07-05 (dual-Opus BLOCKING review) -- HONEST_NEGATIVE, no persist:
the first pass synthesized states via a Brownian bridge pinned at (frac=0 -> 0,
frac=1 -> the known final margin) and reported a positive pooled bss_vs_coin
(0.4269) as evidence of a non-degenerate in-game base. Both reviewers proved
this is NOT usable evidence: (1) E[state_diff(t)] = t*final_diff at every
checkpoint -- the bridge mean drifts deterministically toward the outcome, and
at frac=1.0 state_diff EQUALS the final margin (100% sign-accuracy by
construction); (2) per-checkpoint BSS (frac1_leak_decomposition()) rises
monotonically from ~coin-flip at k=1 to near-perfect at k=9 -- pooling lets
the late, outcome-pinned checkpoints dominate; (3) DECISIVE PROOF
(pure_noise_control()): the identical fit+guard pipeline on a PURE-NOISE
corpus (coin-flip outcome, random margin, zero real signal) still returns
degenerate=False with a similar positive BSS -- a guard that cannot tell real
data from noise is not evidence of skill, it is re-reading the endpoint pin.

pure_noise_control() ALWAYS passes as non-degenerate for this synthesis method
(proven, not suspected), so fit_and_eval() treats that as an automatic
disqualifier regardless of what base_is_degenerate reports on the real corpus,
and gate_and_persist() refuses to write ingame_base_params.json. This is a
genuine data wall, not a fixable bug: NPB has zero real intra-game ticks
(reconfirmed this round), so no in-game BASE fit can be evidenced from this
corpus by any final-score-only synthesis. The prior (fabricated) params file
is superseded by ingame_base_fit_verdict.json (honest blocked-on-data verdict
+ the pure-noise-control proof numbers).

Calibration baseline only -- never an edge. State synthesis is in ingame_base_fit_io.py.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_ingame_base_fit.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.ingame.ingame_gate_generic_models import (
    base_is_degenerate,
    base_predict,
    fit_base,
)
from scripts.platformkit.eval_gate.scoring import brier

from .ingame_base_fit_io import (
    GAMES_PARQUET,
    STATES_SOURCE,
    group_by_checkpoint,
    load_games,
    synth_states_for_split,
    synth_states_pure_noise,
)

logger = logging.getLogger(__name__)

# SUPERSEDED -- no longer written (see module docstring): a bridge-synthesized base
# can never pass pure_noise_control(), so no in-game base is ever persisted here.
PARAMS_PATH = "data/domains/npb/ingame_base_params.json"
# Honest verdict artifact this module DOES write (blocked-on-data + proof numbers).
VERDICT_PATH = "data/domains/npb/ingame_base_fit_verdict.json"


# --------------------------------------------------------------------------- fit
def _date_of(row: pd.Series) -> dt.date:
    return pd.to_datetime(row["date"]).date()


def walk_forward_split(games_df: pd.DataFrame, min_eval: int = 200) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological split: earliest games train, latest >=min_eval games eval (or all,
    if fewer). Train is strictly before the eval slice's first date (no same-day leak)."""
    n = len(games_df)
    n_eval = min(max(min_eval, 1), n)
    split_idx = n - n_eval
    split_date = _date_of(games_df.iloc[split_idx])
    train = games_df[pd.to_datetime(games_df["date"]).dt.date < split_date].reset_index(drop=True)
    eval_ = games_df[pd.to_datetime(games_df["date"]).dt.date >= split_date].reset_index(drop=True)
    return train, eval_


def multi_start_fit(states: List[dict]) -> Dict:
    """Grid pre-search (fit_base's own coarse grid) then a local multi-start refinement
    around the coarse argmin, so the optimizer PROVABLY moves off a naive (1.0, 0.0)
    init. Returns both the naive init score and the final fitted (a,b) + score."""
    sd = np.array([s["state_diff"] for s in states], float)
    fe = np.array([s["frac_elapsed"] for s in states], float)
    y = np.array([s["outcome"] for s in states], float)

    def _mse(a: float, b: float) -> float:
        p = 1.0 / (1.0 + np.exp(-(a + b * fe) * sd))
        return float(np.mean((p - y) ** 2))

    init_ab = (1.0, 0.0)
    init_score = _mse(*init_ab)

    coarse_ab = fit_base(states)  # existing grid search (scale-normalized)
    spread = float(np.std(sd)) or 1.0

    # Local multi-start refine: small perturbations around the coarse argmin, in
    # RAW units, to confirm/improve the grid optimum (proves the optimizer moves).
    starts = [coarse_ab]
    for da in (-0.5, 0.5):
        for db in (-0.5, 0.5):
            starts.append((coarse_ab[0] + da / spread, coarse_ab[1] + db / spread))

    best_ab, best_score = coarse_ab, _mse(*coarse_ab)
    for a0, b0 in starts:
        step = 0.25 / spread
        a, b = a0, b0
        cur = _mse(a, b)
        for _ in range(25):  # small local coordinate descent
            improved = False
            for da, db in ((step, 0), (-step, 0), (0, step), (0, -step)):
                cand = _mse(a + da, b + db)
                if cand < cur:
                    a, b, cur = a + da, b + db, cand
                    improved = True
            if not improved:
                step *= 0.5
                if step < 1e-6 / spread:
                    break
        if cur < best_score:
            best_ab, best_score = (a, b), cur

    return {
        "init_ab": [round(init_ab[0], 6), round(init_ab[1], 6)],
        "init_mse": round(init_score, 6),
        "final_ab": [round(best_ab[0], 6), round(best_ab[1], 6)],
        "final_mse": round(best_score, 6),
        "moved_off_init": bool(best_ab != init_ab and abs(best_score - init_score) > 1e-9),
    }


def frac1_leak_decomposition(eval_states: List[dict], ab: Tuple[float, float]) -> Dict[str, Dict]:
    """Per-checkpoint (k=1..9) BSS vs coin-flip -- the diagnostic that exposed the
    pooled-BSS artifact: one entry per checkpoint so the monotonic rise toward
    frac=1.0 (the outcome-pinned endpoint) is visible, not averaged away by pooling."""
    groups = group_by_checkpoint(eval_states)
    out: Dict[str, Dict] = {}
    for k in sorted(groups):
        grp = groups[k]
        p = base_predict(grp, ab)
        y = np.array([s["outcome"] for s in grp], float)
        b = float(brier(p, y))
        out[f"k{k}"] = {
            "frac_elapsed": round(grp[0]["frac_elapsed"], 6),
            "n": len(grp),
            "brier": round(b, 5),
            "bss_vs_coin": round(1.0 - b / 0.25, 6),
        }
    return out


def pure_noise_control(games: pd.DataFrame, min_eval: int, seed: int = 20260705) -> Dict:
    """DECISIVE PROOF (per the blocking review): re-runs the IDENTICAL fit + degenerate
    guard pipeline on a corpus with PURE NOISE outcomes (coin-flip home_win, random
    margin matching the real corpus's margin spread, zero real signal -- see
    synth_states_pure_noise). degenerate=False here proves a positive BSS on the real
    corpus is a synthesis artifact, not in-game skill: a zero-signal corpus cannot
    legitimately beat coin-flip. Checked on every fit_and_eval call; passing (i.e.
    degenerate=False on noise) DISQUALIFIES the real-corpus result."""
    rng = np.random.default_rng(seed)
    noise_states = synth_states_pure_noise(games, rng)
    n = len(games)
    n_eval_games = min(max(min_eval, 1), n)
    n_eval_states = n_eval_games * (len(noise_states) // n if n else 0)
    train_states = noise_states[:-n_eval_states] if n_eval_states else noise_states
    eval_states = noise_states[-n_eval_states:] if n_eval_states else noise_states

    ab = fit_base(train_states)
    p_eval = base_predict(eval_states, ab)
    y_eval = np.array([s["outcome"] for s in eval_states], float)
    b = float(brier(p_eval, y_eval))
    degen = base_is_degenerate(ab, train_states, p_eval, y_eval)
    return {
        "purpose": "proves whether a positive BSS on the real corpus is a synthesis "
                   "artifact (endpoint pin) rather than in-game signal",
        "n_train": len(train_states), "n_eval": len(eval_states),
        "heldout_brier": round(b, 5),
        "bss_vs_coin": round(1.0 - b / 0.25, 6),
        "degenerate_check": degen,
        "control_passes_as_nondegenerate": bool(not degen["degenerate"]),
    }


def fit_and_eval(root: Optional[Path] = None, min_eval: int = 200) -> Dict:
    """Load corpus, synth states, walk-forward split, fit BASE on train, grade held-out,
    run the degenerate-base guard AND the pure-noise control (see module docstring).
    The control passing as non-degenerate DISQUALIFIES the result. Returned, not
    raised -- a disqualified result IS the honest answer this function reports."""
    games = load_games(root)
    train_games, eval_games = walk_forward_split(games, min_eval=min_eval)
    train_states = synth_states_for_split(train_games, games)
    eval_states = synth_states_for_split(eval_games, games)

    fit_info = multi_start_fit(train_states)
    ab = tuple(fit_info["final_ab"])

    base_eval = base_predict(eval_states, ab)
    y_eval = np.array([s["outcome"] for s in eval_states], float)
    heldout_brier = float(brier(base_eval, y_eval))
    degen = base_is_degenerate(ab, train_states, base_eval, y_eval)
    leak_decomp = frac1_leak_decomposition(eval_states, ab)
    noise_ctrl = pure_noise_control(games, min_eval=min_eval)

    # Disqualified if EITHER the real-corpus guard fails OR the noise control
    # passes as non-degenerate (guard can't tell this corpus's signal from noise).
    disqualified = noise_ctrl["control_passes_as_nondegenerate"]
    verdict = "HONEST_NEGATIVE" if (degen["degenerate"] or disqualified) else "OK"

    return {
        "corpus_id": GAMES_PARQUET,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fit_method": "grid_pre_search_then_local_multistart",
        "states_source": STATES_SOURCE,
        "n_train_games": int(len(train_games)), "n_eval_games": int(len(eval_games)),
        "n_train": int(len(train_states)), "n_eval": int(len(eval_states)),
        "a": ab[0], "b": ab[1], "c": 0.0,  # no separate intercept term fit (see module docstring)
        "fit_detail": fit_info,
        "heldout_brier": round(heldout_brier, 5),
        "bss_vs_coin": round(1.0 - heldout_brier / 0.25, 6),
        "degenerate_check": degen,
        "frac1_leak_decomposition": leak_decomp,
        "pure_noise_control": noise_ctrl,
        "disqualified_by_noise_control": disqualified,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------- persist
def gate_and_persist(root: Optional[Path] = None, min_eval: int = 200) -> Dict:
    """Runs fit_and_eval. NEVER persists ingame_base_params.json for this synthesis
    (pure_noise_control always disqualifies it -- see module docstring). Instead
    writes the HONEST verdict artifact (VERDICT_PATH): blocked-on-data conclusion
    + proof numbers, so the negative result is reproducible."""
    result = fit_and_eval(root=root, min_eval=min_eval)
    base = root or Path(__file__).resolve().parents[2]
    verdict_path = base / VERDICT_PATH
    verdict_path.parent.mkdir(parents=True, exist_ok=True)
    verdict_doc = {
        "verdict": result["verdict"],
        "reason": "zero real intra-game tick corpus for NPB (confirmed again this "
                  "round); the only available fallback (Brownian-bridge synthesis "
                  "from final score) is proven to leak the outcome via its frac=1.0 "
                  "endpoint pin -- pure_noise_control shows the identical "
                  "fit+guard pipeline reports non-degenerate/positive BSS even on "
                  "a corpus with ZERO real signal, so a positive result here cannot "
                  "be trusted as in-game skill.",
        "corpus_id": result["corpus_id"], "as_of": result["as_of"],
        "n_train": result["n_train"], "n_eval": result["n_eval"],
        "states_source": result["states_source"],
        "heldout_brier_pooled": result["heldout_brier"],
        "bss_vs_coin_pooled": result["bss_vs_coin"],
        "degenerate_check": result["degenerate_check"],
        "frac1_leak_decomposition": result["frac1_leak_decomposition"],
        "pure_noise_control": result["pure_noise_control"],
        "disqualified_by_noise_control": result["disqualified_by_noise_control"],
        "params_persisted": False,
        "superseded_params_path": PARAMS_PATH,
    }
    verdict_path.write_text(json.dumps(verdict_doc, indent=2), encoding="utf-8")
    result["verdict_persisted_path"] = str(verdict_path)
    logger.info("ingame_base_fit: HONEST_NEGATIVE, no params persisted (see %s)", verdict_path)
    return result


def main() -> None:
    result = fit_and_eval()
    print(json.dumps({k: v for k, v in result.items() if k != "fit_detail"}, indent=2))
    print(json.dumps(result["fit_detail"], indent=2))


if __name__ == "__main__":
    main()


__all__ = [
    "load_games", "synth_states_for_split", "walk_forward_split",
    "multi_start_fit", "fit_and_eval", "gate_and_persist",
    "frac1_leak_decomposition", "pure_noise_control",
    "STATES_SOURCE", "PARAMS_PATH", "VERDICT_PATH", "GAMES_PARQUET",
]
