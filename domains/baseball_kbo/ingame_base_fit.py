"""domains.baseball_kbo.ingame_base_fit -- KBO in-game BASE win-prob fit
(LANE kbo-quarantine supersedes the prior kbo-base-fit lane).

QUARANTINE (2026-07-06, synthesis-leak rail): this module previously shipped a
DONE verdict + a persisted ingame_base_params.json fit on SYNTHETIC per-inning
run allocations (states_source="synthetic_from_final_score"). That is exactly
the pattern the platform's synthesis-leak rail forbids -- see the SISTER lane
domains/baseball_npb/ingame_base_fit.py, which proved (dual-Opus review,
2026-07-05) that ANY synthesis pinned to end at the true final score at
frac_elapsed=1.0 makes state_diff a function of the outcome at every earlier
checkpoint too (E[state_diff(t)] drifts toward the pin), and that the
degenerate-base guard alone CANNOT detect this -- a pure_noise_control (same
fit+guard pipeline run on a zero-signal corpus) reports the SAME
non-degenerate/positive-BSS verdict. Dropping the frac=1.0 checkpoint (as this
module already did) does NOT fix this: checkpoints k=1..8 still drift toward
the pinned endpoint their own construction guarantees, so the leak persists at
every earlier fraction too. This module was never actually re-audited with a
noise control before its params were persisted -- that gap is closed below.

DATA-AVAILABILITY WALL (confirmed, matches npb_kbo_model_wire_proof.json):
KBO has NO intra-game tick corpus. data/cache/ingame/kbo_states__*.parquet does
not exist; the live feed (npb_kbo_live_state.py) always returns
frac_elapsed=None; data/domains/kbo/kbo_results.parquet is FINAL-SCORE-ONLY.

SYNTHESIS METHOD (kept ONLY as the artifact under diagnosis, per the rail --
never fit-on for a persisted params file anymore; see ingame_base_fit_io.py):
each team's final runs allocated across 9 innings via a game-seeded
multinomial draw over a FIXED (not-fit-to-KBO) per-inning share curve,
yielding a running state_diff at 9 inning-end checkpoints, terminating at the
TRUE final state_diff at frac_elapsed=1.0 by construction.

PURE-NOISE CONTROL (added this round, mirrors NPB's decisive proof exactly):
pure_noise_control() re-runs the identical fit_base/base_predict/
base_is_degenerate pipeline on a corpus with pure-noise outcomes (coin-flip
home_win, random margin matching the real corpus's margin spread, zero real
team-strength signal). It reports control_passes_as_nondegenerate=True --
i.e. the guard ALSO calls the zero-signal noise corpus non-degenerate with a
positive BSS. This DISQUALIFIES the real-corpus result for the same reason it
disqualified NPB's: a guard that cannot tell real data from noise is not
evidence of in-game skill, it is re-reading the multinomial synthesis's
endpoint pin.

CONCLUSION: verdict is HONEST_NEGATIVE. ingame_base_params.json is DELETED
(quarantined, no longer persisted); the honest artifact is
data/domains/kbo/ingame_base_fit_verdict.json (blocked-on-data conclusion +
the pure_noise_control proof numbers), matching NPB's committed treatment
(4414086d) exactly.

p0 (pregame prior) = domains.baseball_kbo.ratings.walk_forward_elo's leak-free
p_home_elo. Tied games (home_win NaN) are dropped, matching ratings.py.

INVARIANTS: domains/baseball_kbo/ only; <=300 LOC; ASCII-only; ONLY imports
numpy/pandas/stdlib + scripts.platformkit.ingame.ingame_gate_generic_models
(a platformkit reuse, not src/kernel/api); no src/kernel/api imports; never
writes data/registry/; calibration baseline only, never an edge.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_ingame_base_fit.py -q
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.ingame.ingame_gate_generic_models import (
    base_is_degenerate,
    base_predict,
    fit_base,
)
from domains.baseball_kbo.ratings import walk_forward_elo
from domains.baseball_kbo.ingame_base_fit_io import (
    _allocate_innings,
    _game_seed,
    N_INNINGS,
    synthesize_states,
    synthesize_states_pure_noise,
)

_REPO = Path(__file__).resolve().parents[2]
_RESULTS_PARQUET = _REPO / "data" / "domains" / "kbo" / "kbo_results.parquet"
# QUARANTINED (2026-07-06, synthesis-leak rail): superseded, never written anymore.
_PARAMS_OUT = _REPO / "data" / "domains" / "kbo" / "ingame_base_params.json"
_VERDICT_OUT = _REPO / "data" / "domains" / "kbo" / "ingame_base_fit_verdict.json"

_MIN_EVAL_GAMES = 200
_A_GRID_START = 1.0   # center of fit_base's np.linspace(0,4,17) grid -- documented start
_B_GRID_START = 1.0
_C_GRID = np.linspace(-0.5, 0.5, 11)  # home-advantage intercept search


def _fit_intercept(states: List[dict], ab: Tuple[float, float]) -> float:
    """Grid-search a home-advantage intercept c on TRAIN, holding (a,b) fixed:
    p = sigmoid((a+b*frac)*state_diff + c). Reported alongside (a,b) per the
    task's [+c intercept] spec; c=0.0 is a valid outcome (no residual HFA
    after state_diff/frac_elapsed already explain it)."""
    a, b = ab
    sd = np.array([s["state_diff"] for s in states], float)
    fe = np.array([s["frac_elapsed"] for s in states], float)
    y = np.array([s["outcome"] for s in states], float)
    logit_base = (a + b * fe) * sd
    best_c, best_score = 0.0, float("inf")
    for c in _C_GRID:
        p = 1.0 / (1.0 + np.exp(-(logit_base + c)))
        sc = float(np.mean((p - y) ** 2))
        if sc < best_score:
            best_score, best_c = sc, float(c)
    return best_c


def base_predict_c(states: List[dict], abc: Tuple[float, float, float]) -> np.ndarray:
    a, b, c = abc
    sd = np.array([s["state_diff"] for s in states], float)
    fe = np.array([s["frac_elapsed"] for s in states], float)
    return 1.0 / (1.0 + np.exp(-((a + b * fe) * sd + c)))


def pure_noise_control(games: pd.DataFrame, min_eval_games: int, seed: int = 20260706) -> Dict:
    """DECISIVE PROOF (mirrors domains.baseball_npb.ingame_base_fit.pure_noise_control):
    re-runs the identical fit + degenerate guard on a PURE-NOISE corpus. Passing
    (degenerate=False here) DISQUALIFIES the real-corpus result as synthesis
    leak rather than evidence of in-game skill."""
    rng = np.random.default_rng(seed)
    noise_states = synthesize_states_pure_noise(games, rng)
    n = len(games)
    n_eval_games = min(max(min_eval_games, 1), n)
    per_game = (len(noise_states) // n) if n else 0
    n_eval_states = n_eval_games * per_game
    train_states = noise_states[:-n_eval_states] if n_eval_states else noise_states
    eval_states = noise_states[-n_eval_states:] if n_eval_states else noise_states

    ab = fit_base(train_states)
    p_eval = base_predict(eval_states, ab)
    y_eval = np.array([s["outcome"] for s in eval_states], float)
    b = float(np.mean((p_eval - y_eval) ** 2))
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


@dataclass
class FitResult:
    verdict: str
    payload: Dict


def fit_and_gate(results_path: Path = _RESULTS_PARQUET,
                 min_eval_games: int = _MIN_EVAL_GAMES) -> FitResult:
    """Full walk-forward fit + degenerate-base guard + pure_noise_control.
    Returns FitResult with verdict in {"DONE", "HONEST_NEGATIVE"} -- always
    HONEST_NEGATIVE for this synthesis method (see module docstring)."""
    games = pd.read_parquet(results_path)
    games = games.sort_values(["date", "home_team", "away_team"], kind="mergesort").reset_index(drop=True)
    games_elo = walk_forward_elo(games)

    game_ids_chrono = games_elo.loc[~games_elo["home_win"].isna()].reset_index(drop=True)
    n_nontied = len(game_ids_chrono)
    n_eval = max(min_eval_games, int(round(n_nontied * 0.2)))
    if n_nontied - n_eval < 200:
        return FitResult("HONEST_NEGATIVE", {
            "reason": "insufficient non-tied games for a >=200/>=200 walk-forward split",
            "n_nontied": n_nontied,
        })
    split_date = game_ids_chrono.iloc[n_nontied - n_eval]["date"]

    train_games = games_elo[games_elo["date"] < split_date]
    eval_games = games_elo[games_elo["date"] >= split_date]

    train_states = synthesize_states(train_games)
    eval_states = synthesize_states(eval_games)

    n_eval_games_actual = eval_games["home_win"].notna().sum()

    ab_final = fit_base(train_states)

    c_final = _fit_intercept(train_states, ab_final)
    abc_final = (ab_final[0], ab_final[1], c_final)

    base_eval_pred_noc = base_predict(eval_states, ab_final)
    base_eval_pred = base_predict_c(eval_states, abc_final)

    y_eval = np.array([s["outcome"] for s in eval_states], float)
    heldout_brier = float(np.mean((base_eval_pred - y_eval) ** 2))
    heldout_brier_noc = float(np.mean((base_eval_pred_noc - y_eval) ** 2))

    degen = base_is_degenerate(ab_final, train_states, base_eval_pred_noc, y_eval)
    bss_vs_coin = 1.0 - heldout_brier / 0.25

    noise_ctrl = pure_noise_control(games_elo, min_eval_games=min_eval_games)
    disqualified = noise_ctrl["control_passes_as_nondegenerate"]

    verdict = ("DONE" if (not degen["degenerate"] and bss_vs_coin > 0.0 and not disqualified)
               else "HONEST_NEGATIVE")

    payload = {
        "sport": "kbo",
        "a": round(float(ab_final[0]), 6),
        "b": round(float(ab_final[1]), 6),
        "c": round(float(c_final), 6),
        "fit_method": "grid_search_normalized_ab_then_1d_intercept_grid",
        "grid_start": {"a": _A_GRID_START, "b": _B_GRID_START, "c": 0.0},
        "grid_final": {"a": round(float(ab_final[0]), 6), "b": round(float(ab_final[1]), 6),
                       "c": round(float(c_final), 6)},
        "moved_off_init": bool(abs(ab_final[0] - _A_GRID_START) > 1e-9
                              or abs(ab_final[1] - _B_GRID_START) > 1e-9
                              or abs(c_final) > 1e-9),
        "corpus_id": str(results_path),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_train": len(train_states),
        "n_eval": len(eval_states),
        "n_train_games": int(train_games["home_win"].notna().sum()),
        "n_eval_games": int(n_eval_games_actual),
        "heldout_brier": round(heldout_brier, 6),
        "heldout_brier_no_intercept": round(heldout_brier_noc, 6),
        "bss_vs_coin": round(bss_vs_coin, 6),
        "degenerate_base_guard": degen,
        "states_source": "synthetic_from_final_score",
        "states_source_note": ("NO real intra-game tick corpus exists for KBO "
                               "(confirmed: data/cache/ingame/kbo_states__*.parquet "
                               "absent, live feed frac_elapsed always None, results "
                               "parquet is final-score-only). States here are "
                               "SYNTHESIZED per-inning run allocations from final "
                               "scores using a fixed (not-fit-to-KBO) inning-share "
                               "curve -- see ingame_base_fit_io.py. The tautological "
                               "frac_elapsed=1.0 checkpoint (state_diff == true "
                               "final diff by construction) is DROPPED from both "
                               "fit and eval; checkpoints cover innings 1-8 only. "
                               "This is a labeled proxy, not a measurement of real "
                               "in-game paths, and pure_noise_control (below) proves "
                               "it is NOT usable as in-game signal even so."),
        "pure_noise_control": noise_ctrl,
        "disqualified_by_noise_control": disqualified,
        "verdict": verdict,
    }
    return FitResult(verdict, payload)


def persist_verdict(result: FitResult, out_path: Path = _VERDICT_OUT) -> None:
    """QUARANTINED (2026-07-06): NEVER persists ingame_base_params.json -- the
    multinomial-inning synthesis cannot pass pure_noise_control (proven, mirrors
    NPB). Writes the HONEST verdict artifact instead: blocked-on-data conclusion
    + the noise-control proof numbers, so the negative result is reproducible."""
    p = result.payload
    doc = {
        "verdict": result.verdict,
        "reason": ("zero real intra-game tick corpus for KBO (confirmed); the only "
                   "available fallback (multinomial per-inning run allocation from "
                   "final score) is disqualified by the same synthesis-leak proof "
                   "used for NPB -- pure_noise_control shows the identical fit+guard "
                   "pipeline reports non-degenerate/positive BSS even on a corpus "
                   "with ZERO real signal, so a positive result here cannot be "
                   "trusted as in-game skill."),
        "corpus_id": p.get("corpus_id"), "as_of": p.get("as_of"),
        "n_train": p.get("n_train"), "n_eval": p.get("n_eval"),
        "states_source": p.get("states_source"),
        "heldout_brier_pooled": p.get("heldout_brier"),
        "bss_vs_coin_pooled": p.get("bss_vs_coin"),
        "degenerate_base_guard": p.get("degenerate_base_guard"),
        "pure_noise_control": p.get("pure_noise_control"),
        "disqualified_by_noise_control": p.get("disqualified_by_noise_control"),
        "params_persisted": False,
        "superseded_params_path": str(_PARAMS_OUT),
        "source_wall_ref": "npb_kbo_tick_payload_report.json",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="backslashreplace") as f:
        json.dump(doc, f, indent=2)


def main() -> FitResult:
    result = fit_and_gate()
    persist_verdict(result)
    return result


if __name__ == "__main__":
    r = main()
    print(json.dumps(r.payload, indent=2))


__all__ = [
    "fit_and_gate", "persist_verdict", "main", "pure_noise_control",
    "FitResult", "base_predict_c", "_fit_intercept",
    "_allocate_innings", "_game_seed", "N_INNINGS",
    "synthesize_states", "synthesize_states_pure_noise",
    "_PARAMS_OUT", "_VERDICT_OUT", "_RESULTS_PARQUET",
]
