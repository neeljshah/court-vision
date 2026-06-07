"""Unified in-game projector — ONE entry that assembles the ROUTED in-game heads.

``project_unified(snapshot, as_of=None, device='auto')`` returns, for a single
live game snapshot:

  * per-(player, stat) FINAL projection from the ROUTED player-line ensemble
    (``src/ingame/routed_ensemble.py::project_player_lines_routed``): a held-out-
    weighted blend of {pregame-L5, SBS v2, production snapshot} that routes to the
    measured per-(stat, game-time) winner with a smooth clock handoff. On the
    held-out walk-forward grid (``.planning/ingame/eval_routed.json``) the routed
    head's POOLED player MAE is 1.0117 — better than production snapshot (1.8704),
    better than v2-alone (1.0287), AND better than the "just use SBS where it
    wins" hard switch (1.0148); routed <= the best individual head at 72/77
    (stat,bucket) cells and <= the SBS-switch at 77/77 (within 0.0002 of the
    un-achievable oracle floor). So routing is a genuine win across the FULL
    clock, not just where SBS already wins, AND
  * final team scores + home win probability from the SCORE ENSEMBLE
    (``src/ingame/score_ensemble.py::project_score_ensemble``): the possession-
    level rest-of-game sim (``src/sim/rest_of_game_sim.py::RestOfGameSim``) for the
    win-prob + score distribution (its measured strength — beats snapshot_pace on
    final score 7/7 game-times and the sigmoid on Brier/LogLoss from mid-game on),
    with the learned-ridge POINT injected by the caller when available (the ridge
    is the measured-best POINT estimate: pooled total MAE 9.88 vs production 20.69,
    margin MAE 8.11 vs 22.50). When no leak-free ridge point is available at serve
    time the ensemble transparently falls back to the sim mean — identical numbers
    to the raw sim, with honest ``point_source`` provenance, AND
  * a combined dict tying them together.

This module ONLY assembles the already-validated, already-trained heads via the
routed ensemble + score ensemble. It does NOT retrain, and it deliberately
excludes the NULLed experiments (atlas / matchup / learned win-prob head) — none
of those are imported here. The routing weights come from the held-out eval curve
(loaded inside ``routed_ensemble`` at import), never re-fit at serve time.

HONESTY ON THE TEAM WIN-PROB
----------------------------
The score ensemble's POINT estimate (ridge) and final-score MAE beat production
decisively, but on pooled win-prob BRIER the ensemble (==sim win-prob) is 0.1772
vs production's logistic 0.1706 — a small Brier loss that flips to a sim WIN late
(decisive Q4 LogLoss). The ensemble keeps the sim win-prob because it is the
measured-best from mid-game on (where bets are placed); the early-game Brier gap
is reported straight by the grader, not hidden.

GATING (HARD HONESTY)
---------------------
Everything is gated behind ``CV_INGAME_SBS`` via ``is_enabled()`` (re-exported
from ``src.ingame.sbs_shadow`` so there is ONE canonical flag reader for the
whole SBS surface, default OFF):

  * Flag OFF  -> ``project_unified`` is a PURE PASS-THROUGH: it returns exactly
    ``scripts.predict_in_game.project_snapshot(snapshot)`` — the production
    in-game serving default — byte-for-byte unchanged. The validated heads are
    NOT loaded, NOT called, and NOTHING about the served value changes. Proven by
    ``tests/test_unified_projector.py::test_disabled_is_noop_identity``.
  * Flag ON   -> ``project_unified`` returns the unified dict assembling the two
    validated heads (player lines + possession-sim team score/win-prob), with the
    production baseline still carried under ``"production_baseline"`` for shadow
    grading. It NEVER mutates the production output.

This module is ADDITIVE and changes no live serving path. Wiring it behind the
flag means a live engine that calls ``project_unified`` is identical to calling
``project_snapshot`` until the operator explicitly sets ``CV_INGAME_SBS=1``.

GPU: the v2 sub-head (used by the router inside its blend window) selects ``cuda``
with automatic CPU fallback (inherited from ``continuous_projection``);
``device='auto'`` (default) defers to that probe. ``device='cpu'`` forces CPU. The
L5 + snapshot sub-heads and the possession sim are pure CPU.

Granularity honesty: player lines update PER EVENT (this is a per-event/snapshot
projection, not per-second — the per-second DISPLAY layer lives in
``per_second_projector.py`` and rides the same routed head). The sim advances by
discrete possessions rolled to a final-score distribution, not wall-clock
seconds. Do not overclaim sub-event resolution.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

# Canonical flag reader for the whole SBS surface (default OFF). Re-exported so
# callers gate on ONE function. sbs_shadow.is_enabled reads CV_INGAME_SBS with
# the full truthy-spelling set ("1"/"true"/"yes"/...).
from src.ingame.sbs_shadow import (
    SBS_FLAG,
    is_enabled,
    snapshot_to_v2_rows,
)

# The routed player-line ensemble + score ensemble are imported lazily-at-call
# (inside the ENABLED branch) so the disabled path never touches a model file or a
# GPU probe. PLAYER_STATS is the only cheap top-level import.
from src.ingame.continuous_projection import PLAYER_STATS

# Production in-game serving DEFAULT — the byte-identical pass-through target.
from scripts.predict_in_game import project_snapshot as _production_project_snapshot


# --------------------------------------------------------------------------- #
# Public schema constants
# --------------------------------------------------------------------------- #
#: number of Monte-Carlo rollouts the possession sim uses by default.
DEFAULT_N_SIMS = 2000
#: deterministic seed so repeated calls on the same snapshot are reproducible.
DEFAULT_SEED = 0

__all__ = [
    "SBS_FLAG",
    "is_enabled",
    "project_unified",
    "PLAYER_STATS",
    "DEFAULT_N_SIMS",
    "DEFAULT_SEED",
]


# --------------------------------------------------------------------------- #
# Device helper
# --------------------------------------------------------------------------- #
def _resolve_device(device: str) -> Optional[str]:
    """Map the public ``device`` arg to the v2 loader's expectation.

    'auto' -> None  (let the v2 head probe cuda w/ CPU fallback)
    'cpu'  -> 'cpu' (force CPU; also honoured by NBA_FORCE_CPU=1 upstream)
    'cuda' -> 'cuda'
    """
    d = (device or "auto").strip().lower()
    if d == "auto":
        return None
    return d


# --------------------------------------------------------------------------- #
# Player-line head (validated SBS v2)
# --------------------------------------------------------------------------- #
def _project_player_lines(
    snapshot: Dict[str, Any],
    *,
    as_of=None,
    store=None,
    projector=None,
) -> List[Dict[str, Any]]:
    """Project every player's final line with the ROUTED player-line ensemble.

    Builds leak-free v2 CORE feature rows from the live snapshot
    (``snapshot_to_v2_rows`` — within-snapshot box accumulation + the player's L5
    prior over games STRICTLY before ``as_of``, never future info) and runs the
    ROUTED ensemble (``project_player_lines_routed``) on each row: a held-out-
    weighted blend of {pregame-L5, SBS v2, production snapshot} that picks the
    measured per-(stat, game-time) winner with a smooth clock handoff. Each value
    is floored at current accumulation by the router.

    The v2 sub-head (loaded once and reused via ``projector``) is only invoked when
    a route's blend weight on v2 is > 0 at the current game-time; the L5 +
    snapshot sub-heads are closed-form. The ``head`` is stamped ``"routed"`` and
    the dominant sub-head per stat is recorded under ``route_head`` for grading.

    Returns a list of per-(player, stat) dicts mirroring the production row shape
    plus the routed projection, so production and unified can be graded side-by-
    side downstream.
    """
    # Lazy imports so the disabled path never loads the model container or the
    # routed-ensemble curve.
    from src.ingame.continuous_projection import _PLAYER_CURRENT_COL
    from src.ingame.routed_ensemble import project_player_lines_routed

    rows = snapshot_to_v2_rows(snapshot, store=store, game_date=as_of)

    out: List[Dict[str, Any]] = []
    for row in rows:
        pid = row.get("player_id")
        # Route/blend per the held-out table at this row's game-time. Pass the
        # pre-loaded v2 projector so the v2 sub-head is loaded at most once across
        # all rows; the router only calls it when a route weights v2 > 0.
        routed = project_player_lines_routed(
            row, projector=projector, return_detail=True,
        )
        proj = routed.get("projected", {})
        weights = routed.get("weights", {})
        for stat in PLAYER_STATS:
            if stat not in proj:
                continue
            cur = float(row.get(_PLAYER_CURRENT_COL[stat], 0.0) or 0.0)
            # dominant sub-head for this (stat, time) — pure provenance, not used
            # for serving; lets the grader see which head the route leaned on.
            w = weights.get(stat) or {}
            route_head = max(w, key=w.get) if w else None
            out.append({
                "player_id": pid,
                "name": row.get("name"),
                "team": row.get("team"),
                "stat": stat,
                "current": cur,
                "projected_final": float(proj[stat]),
                "head": "routed",
                "route_head": route_head,
                "grid_bucket": row.get("_bucket"),
                "gate_decision": row.get("_gate_decision"),
            })
    return out


# --------------------------------------------------------------------------- #
# Team score + win prob (validated possession sim)
# --------------------------------------------------------------------------- #
def _sim_game_row(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the possession-sim ``game_row`` from a live snapshot.

    Uses the shared ``featurize_live_snapshot`` for clock/score, then layers any
    team-aggregate fields the snapshot carries (poss/fgm/fga/...). The sim's
    field reader tolerates missing keys (it shrinks to league priors), so a light
    box snapshot still produces a valid roll — it just leans on the priors more.
    """
    from src.ingame.state_featurizer import featurize_live_snapshot

    row = dict(featurize_live_snapshot(snapshot))
    # Carry through any team-aggregate fields present on the snapshot for the sim
    # (optional; absent -> sim uses league priors). Never invents data.
    for k in (
        "home_poss", "away_poss", "total_poss_count",
        "home_fgm", "home_fga", "home_fg3a", "home_ftm", "home_fta",
        "away_fgm", "away_fga", "away_fg3a", "away_ftm", "away_fta",
    ):
        if k in snapshot and k not in row:
            row[k] = snapshot[k]
    return row


def _project_team(
    snapshot: Dict[str, Any],
    *,
    priors: Optional[Dict[str, Any]] = None,
    ridge_point: Optional[Any] = None,
    n_sims: int = DEFAULT_N_SIMS,
    seed: int = DEFAULT_SEED,
) -> Dict[str, Any]:
    """Final team scores + win prob from the SCORE ENSEMBLE.

    Combines the possession-sim win-prob + score distribution (its measured
    strength) with the learned-ridge POINT (the measured-best point estimate) when
    a leak-free ``ridge_point`` is injected by the caller. When ``ridge_point`` is
    None (the live default — a server has no per-bucket ridge fit at serve time),
    the ensemble transparently falls back to the sim mean: identical numbers to the
    raw possession sim, with honest ``point_source="sim_fallback"`` provenance.

    The returned dict keeps the SIM-style keys (``home_final_mean`` /
    ``away_final_mean`` / ``margin_mean`` / ``total_mean`` / ``home_win_prob`` /
    ``n_sims`` / ``poss_remaining_mean``) so the shadow logger / grader contract is
    unchanged, and ADDS the ensemble provenance (point/winprob/distribution
    sources) for honest grading.
    """
    from src.ingame.score_ensemble import project_score_ensemble

    game_row = _sim_game_row(snapshot)
    res = project_score_ensemble(
        game_row,
        ridge_point=ridge_point,
        priors=priors,
        n_sims=int(n_sims),
        seed=int(seed),
    )
    # Map the ensemble result onto the sim-style team dict the logger expects. The
    # served point estimate (ridge when injected, else sim mean) is reported as
    # home/away_final_mean; the win prob is always the sim's (measured-best).
    return {
        "head": "score_ensemble",
        "home_final_mean": float(res.home_final),
        "away_final_mean": float(res.away_final),
        "margin_mean": float(res.margin),
        "total_mean": float(res.total),
        "home_win_prob": float(res.home_win_prob),
        "n_sims": int(res.n_sims),
        "poss_remaining_mean": float(res.poss_remaining_mean),
        # ensemble provenance (honest grading; never overrides the served value)
        "point_source": res.point_source,
        "winprob_source": res.winprob_source,
        "distribution_source": res.distribution_source,
        "sim_home_final_mean": float(res.sim_home_final_mean),
        "sim_away_final_mean": float(res.sim_away_final_mean),
        "ridge_home_final": res.ridge_home_final,
        "ridge_away_final": res.ridge_away_final,
    }


# --------------------------------------------------------------------------- #
# Unified entry
# --------------------------------------------------------------------------- #
def project_unified(
    snapshot: Dict[str, Any],
    as_of=None,
    device: str = "auto",
    *,
    store=None,
    priors: Optional[Dict[str, Any]] = None,
    ridge_point: Optional[Any] = None,
    n_sims: int = DEFAULT_N_SIMS,
    seed: int = DEFAULT_SEED,
    player_projector=None,
) -> Any:
    """ONE entry assembling the two validated in-game heads for a live snapshot.

    Args:
        snapshot: canonical live box snapshot (``scripts.predict_in_game`` /
            ``src/data/live.py`` schema: period, clock, home/away team + score,
            players[]).
        as_of: ``datetime.date`` of the game, used ONLY for the leak-free L5
            prior cutoff on the player head (games strictly before this date).
            None -> the prior columns default to 0.0 (never future data).
        device: 'auto' (default; v2 head probes cuda w/ CPU fallback), 'cpu', or
            'cuda'.
        store: optional gamelog store for the L5 prior (see ``snapshot_to_v2_rows``).
        priors: optional per-team prior-form strengths for the sim
            (``home_ppp``/``away_ppp``/``home_pace_per48``/``away_pace_per48``),
            derived by the caller from games strictly before this game's date.
        ridge_point: optional learned-ridge POINT estimate for the FINAL team
            score (dict ``{home_final, away_final}`` or ``(home, away)``), derived
            leak-free by the caller (per-bucket ridge fit on games strictly before
            this game). When given, the score ensemble uses it as the served point
            (its measured-best); when None, the ensemble falls back to the sim mean
            (identical to the raw sim, ``point_source="sim_fallback"``).
        n_sims / seed: possession-sim rollout count + RNG seed (deterministic).
        player_projector: optional pre-loaded ``UnifiedPlayerLineProjector`` for
            the v2 sub-head (skip the disk load; used by tests / a warm server).

    Returns:
        * Flag OFF -> EXACTLY ``project_snapshot(snapshot)`` (the production
          in-game serving default), unchanged. Pure pass-through.
        * Flag ON  -> a unified dict:
            {
              "enabled": True,
              "schema_version": "unified-1",
              "device": "<resolved>",
              "player_lines": [ {player_id, name, team, stat, current,
                                 projected_final, head, route_head, grid_bucket,
                                 gate_decision}, ... ],   # ROUTED ensemble
              "team": { home_final_mean, away_final_mean, margin_mean,
                        total_mean, home_win_prob, n_sims, poss_remaining_mean,
                        head, point_source, winprob_source,
                        distribution_source, ... },        # score ensemble
              "production_baseline": <project_snapshot(snapshot) output>,
              "_resolution": "...honesty stamp...",
            }
          The production baseline travels with the payload for shadow grading —
          the unified heads NEVER overwrite it.
    """
    # --- DISABLED: pure pass-through. Do NOT touch the validated heads, the GPU,
    #     or any model file. Byte-identical to production serving. ---
    if not is_enabled():
        return _production_project_snapshot(snapshot)

    # --- ENABLED: assemble the two validated heads. ---
    resolved = _resolve_device(device)
    # Honour an explicit cpu request via the upstream env knob too (covers the
    # sim-side / any incidental xgb probe).
    _restore_force_cpu = None
    if resolved == "cpu":
        _restore_force_cpu = os.environ.get("NBA_FORCE_CPU")
        os.environ["NBA_FORCE_CPU"] = "1"
    try:
        player_lines = _project_player_lines(
            snapshot, as_of=as_of, store=store, projector=player_projector,
        )
        team = _project_team(
            snapshot, priors=priors, ridge_point=ridge_point,
            n_sims=n_sims, seed=seed,
        )
    finally:
        if resolved == "cpu":
            if _restore_force_cpu is None:
                os.environ.pop("NBA_FORCE_CPU", None)
            else:
                os.environ["NBA_FORCE_CPU"] = _restore_force_cpu

    return {
        "enabled": True,
        "schema_version": "unified-1",
        "device": resolved or "auto",
        "player_lines": player_lines,        # routed player-line ensemble
        "team": team,                        # score ensemble (sim + ridge point)
        # Production output carried for shadow grading; never overwritten.
        "production_baseline": _production_project_snapshot(snapshot),
        "_resolution": (
            "player lines = ROUTED ensemble {pregame-L5, SBS v2, snapshot} held-"
            "out-weighted per (stat, game-time), floored at current; team score + "
            "win prob = score ensemble (possession-sim win-prob/distribution + "
            "learned-ridge point when injected, else sim-mean fallback); per-event "
            "accuracy (NOT per-second); production baseline carried unchanged for "
            "shadow grading"
        ),
    }
