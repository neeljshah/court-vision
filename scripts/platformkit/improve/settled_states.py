"""scripts.platformkit.improve.settled_states -- leak-free {p0, outcome} state
reconstruction for a SETTLED final (FIX A), split out of settled_ingest to keep each file
<=300 LOC.

THE STATE ADAPTER the self-improve loop was missing: settled_finals.states_for_game
delegated to settled_ingest.states_for_game, which DID NOT EXIST -> every settled game came
back stateless -> the MF3 audit quarantined the whole batch as empty_states ->
FeedDegradedError -> recalibrator returned None -> perpetual NO_CANDIDATE (the gate never
ran). This module supplies that reconstruction.

LEAK-FREE (mirrors ingame_live_state's encoding, but for a FINISHED game):
  * p0      = the PREGAME prior (live_p0.p0_for, read off the pre-tip snapshot -- NEVER
              derived from the live score, the close, or the outcome).
  * outcome = the realized {0,1} home_win from the FINAL score (the LABEL, not an input).
  * the close is held OUT (we never attach a market price as a prediction to grade).
A game with no pregame prior OR an unresolved/tie outcome yields [] (skipped, never
fabricated -- absent != 0).

INVARIANTS: never writes data/registry/, never flips a flag; calibration not edge (no $).
NEVER raises (any failure -> []). stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("settled_states")


def home_win_outcome(game: Dict[str, Any],
                     http_get: Optional[Callable[[str], Any]] = None
                     ) -> Optional[float]:
    """Realized {0,1} home-win OUTCOME for a settled final, leak-free, or None.

    Source order (both leak-free -- a settled game's FINAL score is the label, not a
    prediction input): the board-carried final scores first (no extra network), then a
    summary fallback via paper.finals_fetch.final_for_event. A tie or absent score -> None
    (the game is skipped, never fabricated; absent != 0). NEVER raises.
    """
    hs = game.get("home_score")
    as_ = game.get("away_score")
    try:
        if hs is not None and as_ is not None:
            h, a = float(hs), float(as_)
            if h == a:
                return None  # tie / unresolved -> skip, never coerce
            return 1.0 if h > a else 0.0
    except (TypeError, ValueError):
        pass
    # Fallback: summary endpoint (still the realized final, leak-free).
    try:
        from scripts.platformkit.paper.finals_fetch import final_for_event
        fin = final_for_event(str(game.get("game_id") or ""), str(game.get("sport") or ""),
                              http_get=http_get)
    except Exception:  # noqa: BLE001 -- no summary -> no outcome, never a guess
        fin = None
    if not isinstance(fin, dict):
        return None
    try:
        h, a = float(fin["home_score"]), float(fin["away_score"])
    except (TypeError, ValueError, KeyError):
        return None
    if h == a:
        return None
    return 1.0 if h > a else 0.0


def p0_prior(sport: str, game_id: str,
             p0_provider: Optional[Callable[..., Any]] = None) -> Optional[float]:
    """Leak-free pregame prior p0 for one game from the PREGAME snapshot, or None.

    Reuses ingame.live_p0.p0_for, which reads data/frontend/predict_service/<sport>/
    latest.json READ-only (pregame_probs.home_ml -- computed BEFORE tip, no live score, no
    close, no outcome -> leak-free). Absent prior -> None (the game yields no state row;
    later audited as empty_states, honest IDLE -- NEVER a fabricated 0.5). NEVER raises.
    """
    try:
        provider = p0_provider
        if provider is None:
            from scripts.platformkit.ingame.live_p0 import p0_for as provider  # type: ignore
        val = provider(str(sport).lower(), str(game_id or ""))
    except Exception:  # noqa: BLE001 -- a prior miss is "no state", not a crash
        return None
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def states_for_game(sport: str, game: Dict[str, Any], *,
                    http_get: Optional[Callable[[str], Any]] = None,
                    p0_provider: Optional[Callable[..., Any]] = None,
                    **_kw: Any) -> List[Dict[str, Any]]:
    """Reconstruct leak-free frozen-schema state rows {p0, outcome} for a settled final.

    Returns a single terminal state row per game (frac_elapsed=1.0, signed home margin for
    schema-parity, the leak-free pregame p0, and the realized home_win outcome). A game with
    no pregame prior OR an unresolved/tie outcome yields [] (skipped, never fabricated).
    NEVER raises.
    """
    try:
        gid = str(game.get("game_id") or "")
        p0 = p0_prior(sport, gid, p0_provider)
        if p0 is None:
            return []  # no leak-free prior -> no state (honest empty, never a 0.5 guess)
        outcome = home_win_outcome(game, http_get=http_get)
        if outcome is None:
            return []  # unresolved/tie -> skipped, never 0-filled
        hs, as_ = game.get("home_score"), game.get("away_score")
        try:
            diff = float(hs) - float(as_) if (hs is not None and as_ is not None) else None
        except (TypeError, ValueError):
            diff = None
        return [{
            "sport": str(sport).lower(), "game_id": gid,
            "asof_idx": 0, "frac_elapsed": 1.0,   # terminal state (game over)
            "state_diff": diff,                    # signed home margin (schema-parity)
            "p0": float(p0),                       # leak-free pregame prior (the BASE)
            "outcome": float(outcome),             # realized home_win label
            # PROVENANCE: this {0,1} label is CONFIRMED from the realized FINAL score (not a
            # 0-fill of a missing label). The MF3 audit trusts a confirmed-0 home-loss as a
            # real observation, while an ABSENT label stays quarantined (anti-0-fill intact).
            "outcome_source": "final_score",
            "outcome_confirmed": True,
        }]
    except Exception as exc:  # noqa: BLE001 -- a bad game yields no states, never a crash
        logger.debug("states_for_game(%s) failed: %s", sport, exc)
        return []


def attach_game_outcome(games: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Lift each enriched game's state outcome to the GAME level so the MF3 audit can confirm
    a real label (the audit reads game['outcome']). Leak-free: copies the already-
    reconstructed terminal outcome + its CONFIRMED provenance; never invents one. NEVER
    raises."""
    out: List[Dict[str, Any]] = []
    for g in games:
        ng = dict(g)
        states = g.get("states") or []
        if states:
            s0 = states[0]
            if ng.get("outcome") is None and s0.get("outcome") is not None:
                ng["outcome"] = s0.get("outcome")
            if s0.get("outcome_confirmed") and "outcome_confirmed" not in ng:
                ng["outcome_confirmed"] = True
        out.append(ng)
    return out


__all__ = ["home_win_outcome", "p0_prior", "states_for_game", "attach_game_outcome"]
