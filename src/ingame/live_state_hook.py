"""src/ingame/live_state_hook.py — P3.1/P3.2/P3.4: the live wiring seam for the typed in-game brain.

This is the ADDITIVE, default-OFF bridge between ``live_engine.project_from_snapshot`` and the typed,
tested in-game modules (``GameState`` + ``bayes_player_update`` + ``universal_winprob``). It is reached
ONLY when a brain in-game flag is set:

  - ``CV_INGAME_STATE``        -> ``apply_ingame_state``: the ONE parametric Bayesian player update that
                                  CONSOLIDATES the 4-5 endQ3 correction heads behind a single trust curve.
  - ``CV_INGAME_UNIVERSAL_WP`` -> ``apply_universal_winprob``: the projected-final win-prob interface.

THE LOAD-BEARING DISCIPLINE (why this is byte-identical even when ON):
  - The DEFAULT trust curve is IDENTITY (no json on disk) -> ``trust_w == 0`` for every row -> the
    Bayesian posterior reproduces each row's BASE ``projected_final`` EXACTLY. ``apply_ingame_state``
    therefore LEAVES every row untouched whenever ``trust_w == 0`` (the common case) — so turning
    ``CV_INGAME_STATE`` on is byte-identical to today until the trust-curve json is GATED on RMSE+bias
    (see scripts/ingame/ingame_rmsebias_harness.py). This module is CONSOLIDATION plumbing, not a new
    accuracy lever (the MAE-vs-RMSE artifact is why a non-identity curve must clear an RMSE+bias gate).
  - prior FROZEN at tip: the prior is the row's existing ``projected_final`` (the BASE/tip projection);
    it is never recomputed from same-day info here.
  - ``apply_universal_winprob`` never takes the raw live margin; it scores the PROJECTED final margin,
    serves no sim-WP before Q4, and FAILS CLOSED (returns the advisory ``None``, leaves the served
    win-prob untouched) off mc_full coverage.

Everything is wrapped so any failure falls through to the unchanged rows — this can never break live
serving. numpy is NOT imported at module load (hot-path-adjacent + import-safe).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# The 7 counting stats that carry a per-(player, stat) posterior (mirrors game_state.STAT_COLS;
# kept local so this module has no heavy import at load time).
_STAT_SET = frozenset(("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"))


# ---------------------------------------------------------------------------
# Dual-path lazy imports (works whether `src` OR the repo root is on sys.path —
# the live server uses `src.ingame.*`, the brain test-suite uses `ingame.*`).
# ---------------------------------------------------------------------------

def _import_state_modules():
    try:
        from ingame.game_state import GameState
        from ingame.bayes_player_update import posterior_projection
    except ImportError:  # pragma: no cover - live server path
        from src.ingame.game_state import GameState  # type: ignore
        from src.ingame.bayes_player_update import posterior_projection  # type: ignore
    return GameState, posterior_projection


def _import_uwp():
    try:
        from ingame import universal_winprob as uwp
    except ImportError:  # pragma: no cover - live server path
        from src.ingame import universal_winprob as uwp  # type: ignore
    return uwp


def _coverage_class(home: str, away: str) -> str:
    """Coverage class for the matchup; FAILS CLOSED to ``league_min`` on any error."""
    try:
        try:
            from brain.coverage import coverage_class as _cc
        except ImportError:  # pragma: no cover - live server path
            from src.brain.coverage import coverage_class as _cc  # type: ignore
        return _cc(home, away)
    except Exception:
        return "league_min"


# ---------------------------------------------------------------------------
# Shared minutes helper (the harness re-derives this vectorised and asserts parity).
# ---------------------------------------------------------------------------

def remaining_min_from(cur_min: float, game_elapsed_sec: float, game_remaining_sec: float) -> float:
    """Estimate a player's remaining minutes from their share of elapsed game time.

    A player who has logged 24 of 36 elapsed wall-clock minutes (share 0.667) is projected to play
    0.667 of the remaining game minutes. This ONLY affects the GATED (non-identity) trust-curve path;
    with the default identity curve ``trust_w`` is 0 so this value never reaches the served output.
    """
    elapsed_min = float(game_elapsed_sec) / 60.0
    remaining_game_min = float(game_remaining_sec) / 60.0
    if elapsed_min <= 0.0:
        return remaining_game_min  # tip-off: no pace yet -> allow the full remaining
    share = float(cur_min) / elapsed_min
    if share < 0.0:
        share = 0.0
    elif share > 1.0:
        share = 1.0
    return remaining_game_min * share


def _margin_bucket(margin: float) -> int:
    """Coarse |margin| bucket used as a trust-curve regime key (0: <=5, 1: <=12, 2: blowout)."""
    am = abs(float(margin))
    if am <= 5.0:
        return 0
    if am <= 12.0:
        return 1
    return 2


# ---------------------------------------------------------------------------
# CV_INGAME_STATE — the consolidated Bayesian player update
# ---------------------------------------------------------------------------

def apply_ingame_state(snap: Dict[str, Any], rows: List[Dict[str, Any]], *,
                       trust_override: Optional[float] = None) -> List[Dict[str, Any]]:
    """Re-price each ``projected_final`` through the ONE Bayesian posterior (GameState + bayes update).

    With the default identity trust curve (``trust_w == 0``) every row is left UNTOUCHED -> byte-identical
    to the input. A gated, RMSE+bias-validated trust curve (or an explicit ``trust_override`` for tests)
    pulls a cold star UP toward its frozen prior and a hot player DOWN. Never raises.
    """
    try:
        GameState, posterior_projection = _import_state_modules()
        gs = GameState.from_snapshot(snap, prior_projection=None)
    except Exception:
        return rows  # never break the hot path

    game_id = str(snap.get("game_id", "") or "")
    regime = {"is_playoff": game_id.startswith("004"),
              "margin_bucket": _margin_bucket(getattr(gs, "score_margin", 0))}

    elapsed_sec = float(getattr(gs, "game_elapsed_sec", 0.0) or 0.0)
    remaining_sec = float(getattr(gs, "game_remaining_sec", 0.0) or 0.0)
    msf_by_pid: Dict[int, float] = {}
    rem_min_by_pid: Dict[int, float] = {}
    for pid, ps in getattr(gs, "players", {}).items():
        msf = float(getattr(ps, "min_so_far", 0.0) or 0.0)
        msf_by_pid[pid] = msf
        rem_min_by_pid[pid] = remaining_min_from(msf, elapsed_sec, remaining_sec)
    default_rem_min = remaining_sec / 60.0

    for r in rows:
        if r.get("stat") not in _STAT_SET:
            continue
        pf = r.get("projected_final")
        if pf is None:
            continue
        try:
            prior = float(pf)
            current = float(r.get("current") or 0.0)
        except (TypeError, ValueError):
            continue
        try:
            pid_i: Optional[int] = int(r["player_id"]) if r.get("player_id") is not None else None
        except (TypeError, ValueError):
            pid_i = None
        msf = msf_by_pid.get(pid_i, 0.0)
        rem_min = rem_min_by_pid.get(pid_i, default_rem_min)
        try:
            post, tw, _ = posterior_projection(
                prior=prior, current=current, min_so_far=msf, remaining_min=rem_min,
                stat=str(r.get("stat")), regime=regime, trust_override=trust_override,
            )
        except Exception:
            continue
        # IDENTITY GUARD: trust_w == 0 -> posterior == prior EXACTLY. Leave the row dict untouched so
        # the served output is byte-identical to the OFF path (the whole point of the consolidation).
        if not tw:
            continue
        r["projected_final"] = max(float(post), current)  # never below the live box
        src = str(r.get("projection_source") or "")
        if "+bayes" not in src:
            r["projection_source"] = src + "+bayes"
    return rows


# ---------------------------------------------------------------------------
# CV_INGAME_UNIVERSAL_WP — projected-final win-prob (interface, not router)
# ---------------------------------------------------------------------------

def apply_universal_winprob(snap: Dict[str, Any], rows: List[Dict[str, Any]], *,
                            coverage_class: Optional[str] = None) -> List[Dict[str, Any]]:
    """Stamp the projected-final win-prob; ROUTE it to the served win-prob only when eligible.

    Eligible iff Q4+ AND ``coverage_class == "mc_full"`` AND a projected margin exists (the
    ``universal_winprob`` router enforces this). When eligible, ``home_win_prob_inplay`` is overwritten
    with the projected-final win% and ``winprob_source`` set to ``"universal_projection"``. Otherwise it
    FAILS CLOSED: the advisory ``universal_home_win_prob`` is stamped ``None`` and the served win-prob is
    left exactly as the existing stack produced it. Never raises.
    """
    try:
        GameState, _ = _import_state_modules()
        uwp = _import_uwp()
        gs = GameState.from_snapshot(snap, prior_projection=None)
    except Exception:
        return rows

    home = str(snap.get("home_team", "") or "")
    away = str(snap.get("away_team", "") or "")
    if coverage_class is None:
        coverage_class = _coverage_class(home, away)

    try:
        period = int(getattr(gs, "period", 0) or snap.get("period", 1) or 1)
        remaining_frac = float(getattr(gs, "remaining_frac", 1.0))
    except (TypeError, ValueError):
        return rows

    # Projected FINAL margin = sum(home pts projection) - sum(away pts projection). NEVER the raw margin.
    home_pts = 0.0
    away_pts = 0.0
    have = False
    for r in rows:
        if r.get("stat") != "pts":
            continue
        pf = r.get("projected_final")
        if pf is None:
            continue
        try:
            v = float(pf)
        except (TypeError, ValueError):
            continue
        team = str(r.get("team", "") or "")
        if team == home:
            home_pts += v
            have = True
        elif team == away:
            away_pts += v
            have = True
    proj_margin = (home_pts - away_pts) if have else None

    try:
        wp = uwp.win_prob_routed(period, coverage_class, proj_margin, remaining_frac)
    except Exception:
        wp = None

    for r in rows:
        r["universal_home_win_prob"] = wp
        r["universal_coverage_class"] = coverage_class
    if wp is not None:  # eligible -> route into the served win-prob
        for r in rows:
            r["home_win_prob_inplay"] = float(wp)
            r["winprob_source"] = "universal_projection"
    return rows
