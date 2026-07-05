"""domains.baseball_npb.ingame_base_fit_io -- corpus load + synthetic in-game state
construction for ingame_base_fit.py (split out to keep both files <=300 LOC).

DATA-AVAILABILITY WALL: investigation this lane (test_npb_kbo_live_model_gap.py,
data/domains/npb_kbo_model_wire_proof.json from the prior npb-kbo-live-model lane)
found ZERO real intra-game tick files for NPB -- no npb_states__*.parquet in
data/cache/ingame, the live feed (npb_kbo_live_state) always returns
frac_elapsed=None, and npb_results.parquet is FINAL-SCORE-ONLY. So states here are
SYNTHESIZED from the final score (STATES_SOURCE records this honestly).

FIX ROUND 2026-07-05 (dual-Opus BLOCKING review): the Brownian-bridge synthesis
below is PROVEN NOT USABLE as in-game signal, even though its middle checkpoints
have nonzero spread. Because the bridge is pinned EXACTLY to the known final
margin at frac=1.0, and every earlier checkpoint's mean drifts monotonically
toward that pin (E[state_diff(t)] = t*final_diff), pooling all 9 checkpoints
into one BSS re-reads the outcome through the late checkpoints and reports it as
"in-game skill". The reviewer proved this is a synthesis artifact, not signal, by
feeding fit_and_eval a PURE-NOISE corpus (home_win := sign(random final margin),
zero real team-strength/dynamics) and getting the SAME positive
bss_vs_coin/degenerate=False verdict the real corpus got. A guard that passes on
pure noise is not a guard. See ingame_base_fit.py::pure_noise_control() -- this
control now runs automatically and BLOCKS persistence if it also reports
non-degenerate (which it always will, for this synthesis method).

CONCLUSION: no honest in-game BASE fit is possible from npb_results.parquet
alone (final-score-only, no real ticks). synth_states_for_split /
_bridge_path are KEPT ONLY as the artifact under diagnosis (used by
pure_noise_control and the per-checkpoint decomposition in
frac1_leak_decomposition, and by the existing bridge-shape tests) -- they are
NOT fit on for a persisted params file anymore. See ingame_base_fit.py module
docstring for the resulting HONEST_NEGATIVE verdict.

SYNTHESIS METHOD (unchanged, kept for the diagnostic above): 9 checkpoints per
game at frac_elapsed=k/9 (NPB's 9-inning regulation length used only as a
monotone TIME axis, no real per-inning shape claimed). state_diff at each
checkpoint is a BROWNIAN-BRIDGE sample pinned at (frac=0 -> 0) and (frac=1 ->
the known final margin), var ~ margin_sigma^2 * frac*(1-frac) (margin_sigma =
the corpus's OWN final-margin std, data-derived). A deterministic LINEAR ramp
was tried first and rejected for the same reason this bridge is now rejected:
it makes state_diff a function of the outcome at every checkpoint. p0 is the
REAL leak-free walk-forward Elo snapshot (same math as ratings.walk_forward_elo,
done in ONE O(n) pass here instead of ratings.replay() per game which is
O(n^2) over ~4k games). Tied games (home_win NaN) are EXCLUDED.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_ingame_base_fit.py -q
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .elo_config import ELO_K, ELO_MEAN, SEASON_REGRESS
from .ratings import EloState, _p_home

GAMES_PARQUET = "data/domains/npb/npb_results.parquet"
N_CHECKPOINTS = 9          # NPB 9-inning regulation length used as a TIME axis only
# PROVEN OUTCOME-LEAKING (2026-07-05 review) -- kept only as the artifact under
# diagnosis in pure_noise_control()/frac1_leak_decomposition(). Never fit-on for
# a persisted params file; see ingame_base_fit.py module docstring.
STATES_SOURCE = "synthetic_brownian_bridge_from_final_score_REJECTED_outcome_leak"


def load_games(root: Optional[Path] = None) -> pd.DataFrame:
    """Load npb_results.parquet, sorted chronologically (date, home_team, away_team)."""
    base = root or Path(__file__).resolve().parents[2]
    path = base / GAMES_PARQUET
    if not path.exists():
        raise FileNotFoundError(f"npb_results.parquet not found at {path}")
    df = pd.read_parquet(path)
    df["season"] = df["season"].astype(str)
    sort_key = pd.DataFrame({
        "k0": pd.to_datetime(df["date"]).values,
        "k1": df["home_team"].astype(str).values,
        "k2": df["away_team"].astype(str).values,
    }, index=df.index)
    idx = sort_key.sort_values(["k0", "k1", "k2"], kind="mergesort").index
    return df.loc[idx].reset_index(drop=True)


def _maybe_regress(state: EloState, team: str, season: int) -> None:
    """ratings._maybe_regress, thin local copy: lets this module do ONE O(n) pass
    over full_games instead of calling ratings.replay() per game (O(n^2) over ~4k)."""
    if team not in state.elo:
        state.elo[team] = ELO_MEAN
        state.last_season[team] = season
        return
    prev = state.last_season.get(team)
    if prev is not None and prev != season:
        state.elo[team] += SEASON_REGRESS * (ELO_MEAN - state.elo[team])
        state.last_season[team] = season


def _p0_snapshots(full_games: pd.DataFrame) -> Dict[str, float]:
    """One leak-free pass over the FULL chronological corpus recording the PRE-GAME
    p_home Elo snapshot per (date,home,away) row as reached (never sees that row's own
    outcome) -- same math as ratings.walk_forward_elo, keyed for O(1) lookup."""
    dates = pd.to_datetime(full_games["date"]).dt.date
    state = EloState()
    snap: Dict[str, float] = {}
    for i in range(len(full_games)):
        row = full_games.iloc[i]
        home, away = str(row["home_team"]), str(row["away_team"])
        season = int(row["season"])
        _maybe_regress(state, home, season)
        _maybe_regress(state, away, season)
        p0 = _p_home(state.elo[home], state.elo[away])
        key = f"{dates.iloc[i].isoformat()}|{home}|{away}"
        snap[key] = p0
        hw = row.get("home_win")
        if not pd.isna(hw):
            s_home = 1.0 if float(hw) >= 0.5 else 0.0
            delta = ELO_K * (s_home - p0)
            state.elo[home] += delta
            state.elo[away] -= delta
        state.last_season[home] = season
        state.last_season[away] = season
    return snap


def _corpus_margin_sigma(full_games: pd.DataFrame) -> float:
    """Data-derived std of the final home-away run margin (no hardcoded constant)."""
    diff = full_games["home_score"].astype(float) - full_games["away_score"].astype(float)
    sigma = float(diff.std())
    return sigma if sigma > 0 else 1.0


def _bridge_path(final_diff: float, sigma: float, n: int, rng: np.random.Generator) -> List[float]:
    """One Brownian-bridge sample pinned at (frac=0 -> 0) and (frac=1 -> final_diff),
    evaluated at fracs k/n for k=1..n. Var at interior frac t is sigma^2*t*(1-t) --
    withholds the outcome early, converges to the (by-definition-known) final margin
    only at frac=1.0. Sequential bridge fill: sample each midpoint conditional on its
    two filled neighbors, recursing into both halves (standard bridge construction)."""
    fracs = [k / n for k in range(0, n + 1)]
    vals = [0.0] * (n + 1)
    vals[0], vals[-1] = 0.0, final_diff

    def fill(lo: int, hi: int) -> None:
        if hi - lo <= 1:
            return
        mid = (lo + hi) // 2
        t_lo, t_mid, t_hi = fracs[lo], fracs[mid], fracs[hi]
        span = t_hi - t_lo
        w = (t_mid - t_lo) / span
        mean = vals[lo] + w * (vals[hi] - vals[lo])
        var = (sigma ** 2) * (t_mid - t_lo) * (t_hi - t_mid) / span
        vals[mid] = mean + rng.normal(0.0, max(var, 0.0) ** 0.5)
        fill(lo, mid)
        fill(mid, hi)

    fill(0, n)
    return vals[1:]  # drop the frac=0 anchor; checkpoints are k=1..n


def synth_states_for_split(games_df: pd.DataFrame, full_games: pd.DataFrame) -> List[dict]:
    """Synthetic per-checkpoint in-game states for every non-tied game in games_df. p0
    is the leak-free walk-forward Elo snapshot (_p0_snapshots). state_diff at each
    checkpoint is a BROWNIAN-BRIDGE sample pinned at (0, final margin) -- synthetic by
    construction (STATES_SOURCE records this; see module docstring for why a
    deterministic linear ramp was rejected). Tied games (home_win NaN) excluded."""
    snap = _p0_snapshots(full_games)
    sigma = _corpus_margin_sigma(full_games)
    out: List[dict] = []
    for _, row in games_df.iterrows():
        hw = row.get("home_win")
        if pd.isna(hw):
            continue  # tied game -- no winner label, matches ratings/adapter discipline
        game_date = pd.to_datetime(row["date"]).date()
        home = str(row["home_team"])
        away = str(row["away_team"])
        key = f"{game_date.isoformat()}|{home}|{away}"
        p0 = float(snap.get(key, 0.5))
        final_diff = float(row["home_score"]) - float(row["away_score"])
        outcome = int(round(float(hw)))
        gid = f"npb-{game_date.isoformat()}-{away}-{home}"
        # stable hash: Python's built-in hash() is salted per-process (PYTHONHASHSEED),
        # which would make the "deterministic" bridge synthesis silently non-reproducible
        # across runs -- hashlib is unsalted, so the SAME game_id always seeds the SAME
        # bridge path (verified: two separate process invocations now fit identical a,b).
        seed = int(hashlib.sha256(gid.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        path = _bridge_path(final_diff, sigma, N_CHECKPOINTS, rng)
        for k in range(1, N_CHECKPOINTS + 1):
            frac = k / N_CHECKPOINTS
            out.append({
                "game_id": gid,
                "state_diff": path[k - 1],
                "frac_elapsed": frac,
                "p0": p0,
                "outcome": outcome,
            })
    return out


def synth_states_pure_noise(games_df: pd.DataFrame, rng: np.random.Generator) -> List[dict]:
    """Diagnostic control corpus for pure_noise_control() (ingame_base_fit.py): SAME
    bridge-synthesis machinery, but final_diff/outcome are pure noise (a coin-flip
    home_win with a matching-sign random margin) -- NO real team-strength, NO real
    game dynamics, p0 fixed at 0.5. If fit_base/base_is_degenerate report this
    non-degenerate (BSS > 0), that proves the positive BSS on the real corpus is
    a synthesis artifact (the endpoint pin), not evidence of in-game skill --
    exactly the reviewer's proof method. sigma matches the real corpus's margin
    spread so the control is apples-to-apples with the real fit."""
    sigma = _corpus_margin_sigma(games_df)
    out: List[dict] = []
    for i in range(len(games_df)):
        outcome = int(rng.random() < 0.5)
        sign = 1.0 if outcome == 1 else -1.0
        final_diff = sign * abs(rng.normal(0.0, sigma))
        gid = f"noise-{i}"
        seed = int(hashlib.sha256(gid.encode("utf-8")).hexdigest()[:8], 16)
        path_rng = np.random.default_rng(seed)
        path = _bridge_path(final_diff, sigma, N_CHECKPOINTS, path_rng)
        for k in range(1, N_CHECKPOINTS + 1):
            out.append({
                "game_id": gid,
                "state_diff": path[k - 1],
                "frac_elapsed": k / N_CHECKPOINTS,
                "p0": 0.5,
                "outcome": outcome,
            })
    return out


def group_by_checkpoint(states: List[dict]) -> Dict[int, List[dict]]:
    """Split a flat states list back into per-checkpoint (k=1..N_CHECKPOINTS) groups,
    keyed by round(frac_elapsed*N_CHECKPOINTS) -- lets callers evaluate BSS PER
    checkpoint instead of pooling all 9 together (pooling is what hid the frac=1.0
    outcome-pin leak; see ingame_base_fit.py::frac1_leak_decomposition)."""
    out: Dict[int, List[dict]] = {}
    for s in states:
        k = int(round(s["frac_elapsed"] * N_CHECKPOINTS))
        out.setdefault(k, []).append(s)
    return out


__all__ = [
    "load_games", "synth_states_for_split", "synth_states_pure_noise",
    "group_by_checkpoint", "GAMES_PARQUET", "STATES_SOURCE", "N_CHECKPOINTS",
]
