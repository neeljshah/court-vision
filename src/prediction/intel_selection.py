"""src/prediction/intel_selection.py — flag-gated INTEL SELECTION/SIZING levers.

Two SELECTION/SIZING signals that survived rigorous leak-free testing in the
2026-06-01 prediction campaign — the first real prediction-improving levers found
(both are SELECTION/SIZING, not point-shift signals; both are 2025-26-regular-season-
confirmed; cross-season is UNCONFIRMED and they BREAK in playoffs):

  (1) vac_ast SIZE-UP — when a primary creator is confirmed OUT (vacated L10
      assists >= 3), SIZE UP the already-gated AST book (edge>=0.75, line<=7.5).
      On the big sample (Family A, extended_oos/benashkar 2025-26) the gated-AST
      ROI rises +4.89% (no creator out) -> +15.59% (vac_ast>=3, n=100, 67% win).
      See docs/_audits/PRED_EXP_freshness_reproject_2026-06-01.md.

  (2) blowout model-UNDER FLAG — in a projected-BLOWOUT game (top-quartile as-of
      SRS mismatch), starters sit the 4th quarter, so the model's own UNDER bets
      on STARTERS over-perform, *especially PTS* (the stat the model otherwise
      loses on). Rolling-origin +17.35% (n=254), PTS +28.78%, CI clears 0 on
      Family A; replicates cross-book same-season (Family B +9.3%) but does NOT
      replicate cross-season (Family C 2024-25 is power-starved / negative).
      See docs/_audits/PRED_EXP_blowout_rolling_2026-06-01.md.

GATING DISCIPLINE (mirrors bet_policy.py CV_KELLY_TILT / CV_BET_POLICY):
  * Both functions are DEFAULT-OFF. With their env flag unset (or the explicit
    ``enabled=`` argument left at its env-resolved default), they are STRICT
    no-ops: ``vac_ast_size_multiplier`` returns 1.0 and ``blowout_under_flag``
    returns a 0.0 score / False — byte-identical to not calling them.
  * They are SELECTION/SIZING helpers: the multiplier only ever tilts UP (never
    drops or shrinks a bet); the flag only ever UP-weights an UNDER it already
    likes. Neither introduces a new bet the base selector wouldn't see.
  * NEVER fire in the playoffs. ``is_playoff`` short-circuits both to the no-op,
    because the AST edge breaks (-2.78% gated) and the blowout minutes mechanism
    inverts (stars play more in close playoff games) in the postseason.

SIZING RATIONALE — size on the DURABLE magnitude, NOT the in-window peak.
  The headline +15.59% (vac_ast) and +17.35% / +28.78% (blowout) are 2025-26
  in-window peaks. The campaign's hard-won lesson (memory: "AST edge is REAL,
  but +19% is a regime-inflated PEAK; durable core ~+5%; never bet in playoffs")
  applies here too: the cross-season leg is unconfirmed-to-negative for BOTH
  levers. So the multipliers below are deliberately CONSERVATIVE — sized as if
  the durable edge is ~+5-8%, not +15-28%. The vac_ast multiplier tops out at
  1.5x (half-again, not the ~3x a naive +16% vs +5% ratio would imply), and the
  blowout score is a bounded [0,1] up-weight a caller folds into Kelly, not a
  raw ROI multiple. Treat every number as a regime-local peak; size on the floor.

This module is RECOMMEND-not-auto-apply. It is NOT imported by bet_selector.py.
Wiring instructions: docs/_audits/INTEL_SELECTION_WIRING_2026-06-01.md.
"""
from __future__ import annotations

import os
from typing import Optional

# --------------------------------------------------------------------------- #
# Gating thresholds (match the lever docs exactly)
# --------------------------------------------------------------------------- #
# vac_ast lever — only ever fires inside the ALREADY-VALIDATED gated-AST book.
_AST_GATE_EDGE = 0.75      # |pred - line| floor (bet_policy ast_high)
_AST_GATE_LINE = 7.5       # closing-line cap   (bet_policy ast_high)
_VAC_AST_MIN = 3.0         # vacated L10 assists of confirmed-OUT regulars

# Conservative SIZING for the vac_ast lever (size on durable ~+5-8%, not +15.6%).
# A multiplier banded [1.0, 1.5]: base 1.25x for the confirmed creator-out slice,
# stepping to 1.5x only on a very large vacancy (vac_ast >= 6, two+ creators out).
# These are HALF-KELLY-flavored nudges, NOT the +15.6%/+4.9% raw ROI ratio.
_VAC_AST_MULT_BASE = 1.25
_VAC_AST_MULT_BIG = 1.50
_VAC_AST_BIG_THRESHOLD = 6.0
_VAC_AST_CLAMP = (1.0, 1.5)

# blowout lever — model-UNDER on a starter in a top-quartile blowout-risk game.
# The caller supplies blowout_risk already normalized to "is this in the top
# quartile of as-of |SRS mismatch|" (a bool or a [0,1] percentile). We accept a
# bool, or a float in [0,1] (percentile rank) with a 0.75 cut, or a raw
# |exp_margin| with a caller-supplied threshold (see blowout_under_flag docstring).
_BLOWOUT_PCTILE_CUT = 0.75
_STARTER_MIN = 28.0        # as-of L10 minutes for "starter" (informational; the
                           # caller is expected to pass role already resolved)

# Conservative blowout up-weight scores. PTS is the standout (the model otherwise
# LOSES on PTS, and the minutes mechanism bites hardest there), so it gets the
# larger up-weight; REB/AST a smaller one. Scores are bounded [0, 1] — a caller
# folds the score into Kelly as e.g. ``size *= (1 + SCALE * score)`` with its own
# SCALE, so the score itself never multiplies stake directly (keeps the sizing
# decision and its magnitude in the caller's hands).
_BLOWOUT_SCORE_PTS = 1.00
_BLOWOUT_SCORE_OTHER = 0.50


# --------------------------------------------------------------------------- #
# env-flag resolvers (default OFF) — mirror bet_policy.kelly_tilt_enabled()
# --------------------------------------------------------------------------- #
_TRUTHY = {"1", "true", "yes", "on", "y", "t"}


def _env_on(name: str) -> bool:
    return (os.environ.get(name, "0") or "0").strip().lower() in _TRUTHY


def vac_ast_enabled() -> bool:
    """True iff CV_INTEL_VAC_AST is set truthy (default OFF)."""
    return _env_on("CV_INTEL_VAC_AST")


def ingame_vac_ast_enabled() -> bool:
    """True iff CV_INGAME_VAC_AST is set truthy (default OFF).

    W-023: the LIVE-PATH flag for in-game vac_ast row attachment and AST
    projection sizing.  Distinct from the pregame CV_INTEL_VAC_AST flag so
    the two levers are independently controllable.  HARD-OFF in playoffs —
    callers must check is_playoff separately (live_engine does so via the
    game_id prefix "004" guard).
    """
    return _env_on("CV_INGAME_VAC_AST")


def blowout_enabled() -> bool:
    """True iff CV_INTEL_BLOWOUT is set truthy (default OFF)."""
    return _env_on("CV_INTEL_BLOWOUT")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _as_float(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v


def _in_ast_gate(edge, line) -> bool:
    """The validated gated-AST window: |edge| >= 0.75 AND line <= 7.5."""
    e = _as_float(edge)
    ln = _as_float(line)
    if e is None or ln is None:
        return False
    return abs(e) >= _AST_GATE_EDGE and ln <= _AST_GATE_LINE


def _is_top_quartile_blowout(blowout_risk, threshold: Optional[float]) -> bool:
    """Interpret the caller's blowout_risk into a top-quartile boolean.

    Accepts:
      * bool                      -> used directly ("caller already classified").
      * float in [0, 1]           -> a PERCENTILE rank; top quartile = >= 0.75.
      * float with `threshold`    -> a RAW |exp_margin|; top quartile = >= threshold
                                     (the caller passes the as-of top-quartile cut).
    Anything unparseable -> False (no-op).
    """
    if isinstance(blowout_risk, bool):
        return blowout_risk
    v = _as_float(blowout_risk)
    if v is None:
        return False
    if threshold is not None:
        t = _as_float(threshold)
        return t is not None and v >= t
    # No explicit threshold: treat as a percentile rank in [0, 1].
    if 0.0 <= v <= 1.0:
        return v >= _BLOWOUT_PCTILE_CUT
    # A raw magnitude with no threshold supplied -> cannot classify -> no-op.
    return False


# --------------------------------------------------------------------------- #
# LEVER 1 — vac_ast SIZE-UP (gated-AST only)
# --------------------------------------------------------------------------- #
def vac_ast_size_multiplier(
    stat: str,
    edge: float,
    line: float,
    vac_ast: float,
    is_playoff: bool,
    enabled: Optional[bool] = None,
) -> float:
    """Kelly SIZE multiplier in [1.0, 1.5] for the vac_ast creator-out lever.

    Returns > 1.0 ONLY when ALL of:
      * the lever is enabled (``enabled`` True, or env CV_INTEL_VAC_AST truthy),
      * ``stat == "ast"``,
      * the bet is inside the validated gated-AST window (|edge| >= 0.75, line <= 7.5),
      * ``vac_ast >= 3`` (a primary creator confirmed OUT),
      * the game is NOT a playoff game (``is_playoff`` False).
    In every other case it returns 1.0 (strict no-op) so wiring it in is byte-
    identical until a real confirmed-out vac_ast arrives on a regular-season
    gated-AST bet.

    The multiplier is CONSERVATIVE on purpose (1.25x base, 1.5x on a very large
    vacancy) — the +15.59% in-window peak is regime-inflated; size as if the
    durable edge is ~+5-8%. Clamped to [1.0, 1.5]; only ever tilts UP.

    Args:
        stat:        bet stat key (lower-cased internally).
        edge:        signed point edge (pred - line) in raw stat units.
        line:        the closing/book line for the bet.
        vac_ast:     vacated L10 assists of confirmed-OUT regulars (leak-free).
        is_playoff:  True for postseason games (forces no-op — AST breaks in playoffs).
        enabled:     override; None -> resolve from env CV_INTEL_VAC_AST (default OFF).

    Returns:
        A float in [1.0, 1.5]. 1.0 means "no change".
    """
    on = vac_ast_enabled() if enabled is None else bool(enabled)
    if not on:
        return 1.0
    if is_playoff:
        return 1.0
    if stat is None or str(stat).lower() != "ast":
        return 1.0
    if not _in_ast_gate(edge, line):
        return 1.0
    v = _as_float(vac_ast)
    if v is None or v < _VAC_AST_MIN:
        return 1.0
    mult = _VAC_AST_MULT_BIG if v >= _VAC_AST_BIG_THRESHOLD else _VAC_AST_MULT_BASE
    lo, hi = _VAC_AST_CLAMP
    return max(lo, min(hi, mult))


# --------------------------------------------------------------------------- #
# LEVER 2 — blowout model-UNDER FLAG (starter, top-quartile blowout, esp. PTS)
# --------------------------------------------------------------------------- #
def blowout_under_flag(
    stat: str,
    side: str,
    role: str,
    blowout_risk,
    is_playoff: bool,
    enabled: Optional[bool] = None,
    *,
    threshold: Optional[float] = None,
    as_score: bool = True,
):
    """Flag / up-weight a model-UNDER on a STARTER in a top-quartile blowout game.

    Fires (non-zero / True) ONLY when ALL of:
      * the lever is enabled (``enabled`` True, or env CV_INTEL_BLOWOUT truthy),
      * ``side`` is an UNDER bet (the model's pred < line),
      * ``role`` marks a starter (``"starter"``, or as-of L10 min >= 28 — see below),
      * ``blowout_risk`` is in the top quartile of as-of |SRS mismatch|,
      * the game is NOT a playoff game (``is_playoff`` False — the minutes
        mechanism INVERTS in the postseason: stars play MORE in close games).
    Otherwise it is a strict no-op: returns 0.0 (``as_score=True``) or False.

    The returned score is a bounded [0, 1] UP-WEIGHT a caller folds into Kelly
    (e.g. ``size *= 1 + SCALE * score``), NOT a raw ROI multiple — the +17%/+28.8%
    numbers are regime-inflated peaks (size on the durable floor). PTS gets the
    larger score (1.0) because the model otherwise LOSES on PTS and the minutes
    mechanism bites hardest there; other stats get 0.5.

    Args:
        stat:        bet stat key (PTS gets the higher up-weight).
        side:        bet direction; only "under" fires.
        role:        player role; "starter" (or "start"/"starting") fires. A
                     numeric value is treated as as-of L10 minutes and fires when
                     >= 28 (the validated starter cut).
        blowout_risk: bool (already classified) | float in [0,1] (percentile,
                     top quartile = >= 0.75) | raw |exp_margin| (pass ``threshold``).
        is_playoff:  True for postseason -> forced no-op.
        enabled:     override; None -> resolve from env CV_INTEL_BLOWOUT (default OFF).
        threshold:   optional raw-magnitude top-quartile cut for blowout_risk.
        as_score:    True (default) -> return a [0,1] float score; False -> return bool.

    Returns:
        ``as_score`` True  -> float in [0, 1] (0.0 == no-op).
        ``as_score`` False -> bool.
    """
    no_op = (0.0 if as_score else False)
    on = blowout_enabled() if enabled is None else bool(enabled)
    if not on:
        return no_op
    if is_playoff:
        return no_op
    if side is None or str(side).lower() != "under":
        return no_op
    # role: accept "starter"-ish strings OR a numeric as-of L10 minutes >= 28.
    is_starter = False
    if role is not None:
        rl = str(role).strip().lower()
        if rl in {"starter", "start", "starting", "s"}:
            is_starter = True
        else:
            m = _as_float(role)
            if m is not None and m >= _STARTER_MIN:
                is_starter = True
    if not is_starter:
        return no_op
    if not _is_top_quartile_blowout(blowout_risk, threshold):
        return no_op
    if not as_score:
        return True
    return _BLOWOUT_SCORE_PTS if (stat and str(stat).lower() == "pts") else _BLOWOUT_SCORE_OTHER
