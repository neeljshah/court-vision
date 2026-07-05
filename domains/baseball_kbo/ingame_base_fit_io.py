"""domains.baseball_kbo.ingame_base_fit_io -- synthetic in-game state
construction for ingame_base_fit.py (split out to keep both files <=300 LOC,
mirrors domains.baseball_npb.ingame_base_fit_io's split).

QUARANTINED (2026-07-06, synthesis-leak rail): the multinomial per-inning
synthesis here is kept ONLY as the artifact under diagnosis (used by
pure_noise_control() and fit_and_gate() in ingame_base_fit.py) -- it is NEVER
fit-on for a persisted params file. See ingame_base_fit.py module docstring
for the full HONEST_NEGATIVE verdict and proof.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_ingame_base_fit.py -q
"""
from __future__ import annotations

import hashlib
from typing import List

import numpy as np
import pandas as pd

N_INNINGS = 9
# Fixed, NOT fit-to-KBO, mildly back-loaded per-inning run-share curve (sums to 1.0).
# Documented assumption: innings 1-3 lighter (starters settling in), 4-6 mid, 7-9
# slightly heavier (bullpen volatility / late-inning scoring bursts) -- a generic
# baseball pattern, not a KBO-specific fit, so it cannot leak KBO outcomes.
_INNING_SHARE = np.array([0.095, 0.10, 0.105, 0.11, 0.115, 0.115, 0.12, 0.12, 0.12])
_INNING_SHARE = _INNING_SHARE / _INNING_SHARE.sum()


def _game_seed(home: str, away: str, date: pd.Timestamp) -> int:
    """Deterministic per-game seed so synthesis is reproducible, not random-per-run."""
    key = f"{home}|{away}|{date.date().isoformat()}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _allocate_innings(total_runs: int, rng: np.random.Generator) -> np.ndarray:
    """Multinomial-allocate total_runs across N_INNINGS using _INNING_SHARE."""
    if total_runs <= 0:
        return np.zeros(N_INNINGS, dtype=int)
    return rng.multinomial(total_runs, _INNING_SHARE)


def synthesize_states(games: pd.DataFrame, drop_terminal: bool = True) -> List[dict]:
    """Build synthetic intra-game (game_id, state_diff, frac_elapsed, p0, outcome)
    checkpoints for every non-tied game, one row per inning boundary (9 per game
    by default; 8 with drop_terminal=True).

    Requires games already carries p_home_elo (from walk_forward_elo). Ties
    (home_win NaN) are dropped -- no label to score against.

    drop_terminal=True (default) excludes the frac_elapsed=1.0 checkpoint: by
    construction its state_diff IS the true final score_diff, so its sign
    determines outcome tautologically (a trivial, not a modeled, prediction).
    NOTE (quarantine): even with drop_terminal=True the leak is NOT removed --
    checkpoints k=1..8 still drift toward the pinned frac=1.0 endpoint their own
    construction guarantees. See ingame_base_fit.py module docstring.
    """
    states: List[dict] = []
    last_inning = N_INNINGS - 1 if drop_terminal else N_INNINGS
    for row in games.itertuples(index=False):
        home_win = getattr(row, "home_win")
        if pd.isna(home_win):
            continue
        home_r = int(round(float(getattr(row, "home_score"))))
        away_r = int(round(float(getattr(row, "away_score"))))
        date = pd.Timestamp(getattr(row, "date"))
        home = str(getattr(row, "home_team"))
        away = str(getattr(row, "away_team"))
        game_id = f"{date.date().isoformat()}_{home}_{away}"
        seed = _game_seed(home, away, date)
        rng = np.random.default_rng(seed)
        home_by_inning = _allocate_innings(home_r, rng)
        away_by_inning = _allocate_innings(away_r, rng)
        p0 = float(getattr(row, "p_home_elo"))
        outcome = int(float(home_win) >= 0.5)
        running_diff = 0.0
        for inn in range(N_INNINGS):
            running_diff += float(home_by_inning[inn] - away_by_inning[inn])
            if inn >= last_inning:
                break
            frac = (inn + 1) / N_INNINGS
            states.append({
                "game_id": game_id, "state_diff": running_diff,
                "frac_elapsed": frac, "p0": p0, "outcome": outcome,
            })
    return states


def synthesize_states_pure_noise(games: pd.DataFrame, rng: np.random.Generator) -> List[dict]:
    """Diagnostic control corpus (mirrors domains.baseball_npb.ingame_base_fit_io
    .synth_states_pure_noise exactly): SAME multinomial per-inning synthesis
    machinery, but each game's outcome/final margin is PURE NOISE (coin-flip
    home_win, random margin matching the real corpus's margin std) -- zero real
    team-strength or in-game dynamics, p0 fixed at 0.5. If fit_base/
    base_is_degenerate still reports this non-degenerate with positive BSS, that
    PROVES a positive result on the real corpus is a synthesis artifact (the
    frac=1.0 endpoint pin), not in-game skill -- see ingame_base_fit.py."""
    diff = games["home_score"].astype(float) - games["away_score"].astype(float)
    sigma = float(diff.std()) or 1.0
    out: List[dict] = []
    for i in range(len(games)):
        outcome = int(rng.random() < 0.5)
        sign = 1.0 if outcome == 1 else -1.0
        final_diff = sign * abs(rng.normal(0.0, sigma))
        base_runs = max(1, int(round(abs(rng.normal(4.0, 1.5)))))
        margin = max(0, int(round(abs(final_diff))))
        if outcome == 1:
            home_r, away_r = base_runs + margin, base_runs
        else:
            home_r, away_r = base_runs, base_runs + margin
        gid = f"noise-{i}"
        seed = int(hashlib.sha256(gid.encode("utf-8")).hexdigest()[:8], 16)
        path_rng = np.random.default_rng(seed)
        home_by_inning = _allocate_innings(home_r, path_rng)
        away_by_inning = _allocate_innings(away_r, path_rng)
        running_diff = 0.0
        for inn in range(N_INNINGS - 1):  # drop terminal, same as synthesize_states
            running_diff += float(home_by_inning[inn] - away_by_inning[inn])
            out.append({
                "game_id": gid, "state_diff": running_diff,
                "frac_elapsed": (inn + 1) / N_INNINGS, "p0": 0.5, "outcome": outcome,
            })
    return out


__all__ = [
    "N_INNINGS", "_game_seed", "_allocate_innings",
    "synthesize_states", "synthesize_states_pure_noise",
]
