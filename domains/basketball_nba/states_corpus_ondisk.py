"""domains.basketball_nba.states_corpus_ondisk -- NBA checkpoint-states corpus
built ENTIRELY from on-disk ESPN sources, NO cdn.nba.com backfill (wave-22
lane 5: cdn.nba.com confirmed BLOCKED all tiers, see cdn_probe.py; this module
is the promised "on-disk states path" states_gate_runner.py's NO_CORPUS note
and NOW.md's wave-20 entry point to).

INPUT: data/domains/basketball_nba/linescores.parquet (quarter scores, the
states_gate.py join target) + data/cache/ingame/pbp_states_<season>.parquet
(ingest_pbp_states.py's 120s-regulation-second margin trajectory, ALREADY on
disk -- built from ESPN summary plays[], not any CDN backfill). Every row of
pbp_states_2025_26.parquet has a matching linescores event_id (1313/1313
verified this wave) -- no join-loss the CDN path suffers.

WHAT THIS PROVIDES vs THE CDN PATH: only run_last_3min is derivable from the
margin trajectory (a home-score-margin DELTA over a trailing window); in_bonus
requires foul-count state the ESPN summary plays[] trajectory does not carry
here -- HONESTLY UNAVAILABLE from this source, not fabricated. states_gate.py
already declares run_last_3min and in_bonus as SEPARATE features scored
independently, so shipping run_last_3min alone is a valid partial run of the
pre-declared question, not a new one.

WINDOW APPROXIMATION (documented, not hidden): the CDN's run_last_3min is an
EXACT trailing-180s (RUN_WINDOW_MIN=3.0) window over individual scoring
actions (domains.basketball_wnba.ingame_live_cdn._run_last_3min). The on-disk
grid here is quantized to 120s steps, so an exact 180s lookback does not land
on a grid point. This module uses a 240s (2-grid-step) trailing window --
documented as RUN_WINDOW_GRID_STEPS=2 -- as the closest on-disk approximation;
it is NOT the same statistic as the CDN's, and any adoption decision must
account for that before comparing coefficients across corpora.

CHECKPOINTS: reuses states_gate.py's CHECKPOINTS/_CHECKPOINT_PERIOD mapping;
NBA regulation seconds-remaining at each checkpoint (end_q1=2160, half=1440,
end_q3=720) land EXACTLY on the pbp_states 120s grid (verified: 2160/1440/720
are all multiples of 120), so no interpolation is needed at the checkpoint
itself.

PROVENANCE: this corpus's home_win label comes from linescores' cumulative
final quarters (states_gate.py's existing _checkpoint_diff / linescores path)
-- unrelated to and never pooled with any forward-capture stream, matching
AUTONOMY_CHARTER.

INVARIANTS: <=300 LOC; ASCII only; pandas + stdlib only; no network; no
$/roi/edge fields; never mutates states_gate.py/states_gate_join.py/
states_gate_runner.py (those stay wired to the CDN path so they activate
unchanged if lane 4's blocked CDN ever opens up); this module is a SEPARATE,
additive corpus + row-builder feeding the SAME states_gate.py Row/crossfit
math via build_rows_from_ondisk (parallel to states_gate.py's build_rows).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_corpus_ondisk.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from domains.basketball_nba.states_gate import (
    CHECKPOINTS,
    Row,
    _CHECKPOINT_PERIOD,
    half_of,
)

EDGE_CLAIMED = False

_REPO_ROOT = Path(__file__).resolve().parents[2]
LINESCORES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "linescores.parquet"
PBP_STATES_PARQUET = _REPO_ROOT / "data" / "cache" / "ingame" / "pbp_states_2025_26.parquet"

_PERIOD_SEC = 720.0
_SECONDS_REMAINING_AT_CHECKPOINT = {
    cp: (4 - period) * _PERIOD_SEC for cp, period in _CHECKPOINT_PERIOD.items()
}  # end_q1->2160, half->1440, end_q3->720

# On-disk margin-trajectory grid step (matches ingest_pbp_states._GRID_STEP).
_GRID_STEP_SEC = 120.0
# Trailing window for run_last_3min approximation, in grid steps (see module
# docstring: 2 steps = 240s, the closest fit to the CDN's exact 180s window).
RUN_WINDOW_GRID_STEPS = 2

# ONLY the feature actually derivable from this on-disk source; in_bonus is
# honestly absent (see module docstring). Kept as its own constant (not
# states_gate.FEATURES) so callers never silently assume in_bonus coverage.
FEATURES_AVAILABLE: tuple = ("run_last_3min",)


def _margin_at(traj_by_sr: Dict[float, float], sr: float) -> Optional[float]:
    return traj_by_sr.get(sr)


def run_last_3min_ondisk(traj_by_sr: Dict[float, float], sr: float,
                          window_steps: int = RUN_WINDOW_GRID_STEPS) -> Optional[float]:
    """Home-margin delta over the trailing `window_steps` grid steps ending at
    seconds_remaining=sr. None if either endpoint is missing from the
    trajectory (never fabricated). PURE -- no I/O."""
    cur = _margin_at(traj_by_sr, sr)
    prior_sr = sr + window_steps * _GRID_STEP_SEC
    prior = _margin_at(traj_by_sr, prior_sr)
    if cur is None or prior is None:
        return None
    return cur - prior


def _trajectory_by_event(pbp_df: pd.DataFrame) -> Dict[str, Dict[float, float]]:
    out: Dict[str, Dict[float, float]] = {}
    for event_id, grp in pbp_df.groupby("event_id"):
        out[str(event_id)] = dict(zip(grp["seconds_remaining"].astype(float),
                                       grp["home_margin"].astype(float)))
    return out


def build_rows_from_ondisk(
    games_with_p0: pd.DataFrame,
    linescores_df: pd.DataFrame,
    pbp_states_df: pd.DataFrame,
) -> List[Row]:
    """games_with_p0 (event_id, p_anchored, home_win) + linescores_df
    (event_id, home_q1..away_q4) + pbp_states_df (event_id, seconds_remaining,
    home_margin) -> one Row per (game, checkpoint) with run_last_3min from the
    on-disk margin trajectory. in_bonus_diff is always 0.0 (honestly absent
    from this source -- see module docstring; NOT used to claim an in_bonus
    result, callers must restrict crossfit to FEATURES_AVAILABLE).

    Games/checkpoints missing any leg (no p_anchored, no linescores row, no
    trajectory value at the checkpoint or its window-prior point) are
    skipped, never faked."""
    ls_by_id = {str(r["event_id"]): r for _, r in linescores_df.iterrows()}
    p0_by_id = {str(r["event_id"]): float(r["p_anchored"]) for _, r in games_with_p0.iterrows()}
    outcome_by_id = {str(r["event_id"]): float(r["home_win"]) for _, r in games_with_p0.iterrows()}
    traj_by_event = _trajectory_by_event(pbp_states_df)

    rows: List[Row] = []
    for event_id, traj in traj_by_event.items():
        ls = ls_by_id.get(event_id)
        p_anchored = p0_by_id.get(event_id)
        outcome = outcome_by_id.get(event_id)
        if ls is None or p_anchored is None or outcome is None:
            continue
        for cp in CHECKPOINTS:
            sr = _SECONDS_REMAINING_AT_CHECKPOINT[cp]
            run = run_last_3min_ondisk(traj, sr)
            if run is None:
                continue
            rows.append(Row(
                event_id=event_id, checkpoint=cp, p_anchored=p_anchored,
                outcome=outcome, run_last_3min=run, in_bonus_diff=0.0,
                half=half_of(event_id),
            ))
    return rows


def load_default_corpus() -> Dict[str, pd.DataFrame]:
    """Read the two on-disk parquets this module needs, keyed for direct use
    with build_rows_from_ondisk (after joining p_anchored elsewhere, e.g. via
    states_gate_runner._compute_p_anchored). Raises FileNotFoundError if
    either path is absent -- callers (a runner) decide the honest NO_CORPUS
    fallback message, this loader never fabricates an empty frame silently."""
    lines = pd.read_parquet(LINESCORES_PARQUET)
    lines = lines.copy()
    lines["event_id"] = lines["event_id"].astype(str)
    pbp = pd.read_parquet(PBP_STATES_PARQUET)
    pbp = pbp.copy()
    pbp["event_id"] = pbp["event_id"].astype(str)
    return {"linescores": lines, "pbp_states": pbp}


__all__ = [
    "LINESCORES_PARQUET", "PBP_STATES_PARQUET", "RUN_WINDOW_GRID_STEPS",
    "FEATURES_AVAILABLE", "run_last_3min_ondisk", "build_rows_from_ondisk",
    "load_default_corpus",
]
