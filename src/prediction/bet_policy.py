"""src/prediction/bet_policy.py — flag-gated bet-policy selector.

Picks which stats the live bet_selector is allowed to place. Strict no-op
unless ``CV_BET_POLICY`` is set to a non-default value; the default keeps
every shipped behavior exactly as it was.

Why this exists
---------------
``scripts/betting_policy_validation.py`` on a clean temporal held-out split
(early half tunes, late half grades) shows:

  policy (held-out late n=2,172)        ROI
  --------------------------------------------
  Iter-57 FILTERED (product's bets)    -13.54%   <- the shipped book
  base unfiltered                       -3.04%
  calibrated, drop PTS                  +4.76%
  calibrated, REB + AST only            +3.82%

The Iter-57 filter's lineage is the market-follow artifact in §1 of
docs/VS_VEGAS_ASSESSMENT.md; it bets 81% PTS and PTS robustly loses to real
closes. The robust positive book on a temporal held-out split is **REB+AST,
calibrated, no Iter-57 filter** — positive in both halves (+0.65% early,
+3.82% late). AST alone is stronger but period-unstable; pairing with REB
is the conservative-sizing version.

How to use it
-------------
This module exposes ONE flag-gated decision: should the live bet_selector
allow a bet on *stat*?

  iter57       (default; back-compat) — all 7 stats allowed
  reb_ast      — only {"reb", "ast"}
  reb_ast_fg3m — drop PTS only; keep {"reb","ast","fg3m"} (broader candidate)

Flag-gating discipline (per CV_PREGAME_CAL / CV_LIVE_ADJUST):
* CV_BET_POLICY unset or = "iter57" -> ``policy_allows_stat(s)`` is True for
  every s -> strict pass-through, the shipped live path is unchanged.
* CV_BET_POLICY = "reb_ast" or "reb_ast_fg3m" -> bet_selector skips any
  candidate whose stat is not in the allowlist. AST is period-unstable so
  callers using reb_ast should also lower the AST Kelly multiplier.
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

_DEFAULT_POLICY = "iter57"
_ALLOWED_STATS: dict[str, frozenset[str]] = {
    "iter57":      frozenset(),  # empty set = "no allowlist" = allow all
    "reb_ast":     frozenset({"reb", "ast"}),
    "reb_ast_fg3m": frozenset({"reb", "ast", "fg3m"}),
    "ast_high":    frozenset({"ast"}),  # AST with edge>=0.75; see _POLICY_EDGES
}

# Per-policy per-stat minimum |pred - line| to place a bet. Augments the
# global edge_min config; callers should use max(global_min, policy_min) so
# this layer can only TIGHTEN, never loosen, the live selection. Empty/missing
# means "no per-stat override -- use the global default".
#
# SIZING CAVEAT (cross-corpus, VS_VEGAS_ASSESSMENT §8e, 2026-06-01): the in-window
# gated numbers below (~+19-27%) are a REGIME-INFLATED PEAK. The edge is book-robust
# (replicates on an independent book, same window) but its magnitude collapses
# cross-season: on 2024-25 regular season the gated edge is only ~+5% (61% win, n=72),
# and it BREAKS in playoffs (-2.78%). Size Kelly on the durable ~+5% core, not the
# in-window peak, and do NOT bet AST in playoffs.
#
# ast_high (validated 2026-06-01, scripts/bet_policy_sweep.py): AST is the one
# stat with a robust positive-in-both-halves threshold sweep. At edge>=0.75 it
# is early +11.83% / late +23.47% on a held-out temporal split (n=135 late).
# Tighter and looser thresholds are both also robust (0.50 -> +6/+18, 1.0 ->
# +22/+17), so 0.75 is the late-ROI max within the robust band, not a knife-
# edge pick. REB, FG3M, PTS each FAIL the robustness bar at every threshold
# tested (REB sign-flips between halves; PTS loses in both; FG3M robust subset
# is n<20 -- too small to ship).
_POLICY_EDGES: dict[str, dict[str, float]] = {
    "iter57":       {},
    "reb_ast":      {},
    "reb_ast_fg3m": {},
    "ast_high":     {"ast": 0.75},
}

# Per-policy per-stat MAX closing-line cap. A bet's `line` strictly greater
# than the cap is dropped. Empty/missing means no cap.
#
# ast_high cap=7.5 (validated 2026-06-01,
# scripts/ast_subsegment_audit.py): the AST very_high (>7.5) line slice
# sign-flips between halves (+87.70% early on n=4, -23.63% late on n=10) --
# both the sign-flip and the n<20 early sample are reasons to drop. Dropping
# only this slice (vs the high 5.5-7.5 tier whose n=10 is right at the
# robustness floor) is the conservative tightening: AST policy late ROI
# +23.47% -> +27.23% on n=125 (vs n=135 unfiltered), both halves still
# positive.
_POLICY_LINE_CAPS: dict[str, dict[str, float]] = {
    "iter57":       {},
    "reb_ast":      {},
    "reb_ast_fg3m": {},
    "ast_high":     {"ast": 7.5},
}


def active_policy() -> str:
    """Return the active policy name, defaulting to ``iter57`` (back-compat)."""
    p = (os.environ.get("CV_BET_POLICY") or _DEFAULT_POLICY).strip().lower()
    return p if p in _ALLOWED_STATS else _DEFAULT_POLICY


def is_iter57_default() -> bool:
    """True when no override is active — bet_selector behaves exactly as shipped."""
    return active_policy() == _DEFAULT_POLICY


def policy_allows_stat(stat: str) -> bool:
    """Return True if *stat* is allowed under the active policy.

    Strict no-op under the default policy (returns True for every stat).
    """
    if stat is None:
        return True
    allow = _ALLOWED_STATS.get(active_policy(), frozenset())
    if not allow:
        return True  # iter57 / unknown -> pass-through
    return stat.lower() in allow


def allowed_stats() -> Iterable[str]:
    """Return the active policy's stat allowlist (empty under iter57)."""
    return tuple(sorted(_ALLOWED_STATS.get(active_policy(), frozenset())))


def policy_min_edge(stat: str) -> float:
    """Return the active policy's per-stat min |pred - line| to place a bet.

    Returns 0.0 (no per-stat tightening) when:
      * the policy doesn't override this stat
      * the policy / stat is unknown
      * the active policy is the default (iter57)

    Callers should combine via ``max(global_min, policy_min_edge(stat))`` so
    this layer can only TIGHTEN the live edge threshold, never relax it.
    """
    if stat is None:
        return 0.0
    edges = _POLICY_EDGES.get(active_policy(), {})
    return float(edges.get(stat.lower(), 0.0))


def policy_max_line(stat: str) -> Optional[float]:
    """Return the active policy's per-stat max closing-line cap, or None.

    A line strictly greater than the returned cap should be DROPPED. Returns
    None (no cap) when the policy / stat is unknown or the active policy is
    the default.
    """
    if stat is None:
        return None
    caps = _POLICY_LINE_CAPS.get(active_policy(), {})
    v = caps.get(stat.lower())
    return None if v is None else float(v)


def policy_drops_line(stat: str, line: float) -> bool:
    """Return True iff this (stat, line) is excluded by the active policy.

    Convenience wrapper -- callers can also use ``policy_max_line`` directly.
    """
    cap = policy_max_line(stat)
    if cap is None:
        return False
    try:
        return float(line) > cap
    except (TypeError, ValueError):
        return False


# Multiplicative Kelly SIZING tilt (flag CV_KELLY_TILT). Strict no-op (returns
# 1.0 for everything) unless CV_KELLY_TILT is enabled. This is a SIZING tilt, NOT
# a selection filter — it only ever tilts UP, never drops or shrinks a bet.
#
# H1 (docs/_audits/INTEL_CAMPAIGN_PUNCHLIST.md + VS_VEGAS_ASSESSMENT §8d): high
# opponent PACE *appeared* to concentrate the gated ast_high edge on the
# extended_oos primary window (+17.3% high vs +12.1% low+mid, both halves).
#
# ⚠️ DO NOT ENABLE — FAILED CROSS-SEASON (2026-06-01, analyze_crosstime_fixed.py):
# on two INDEPENDENT leak-free rolling-origin reg seasons the gated high-pace AST
# slice is EMPTY (2024-25 n=0) or noise (2025-26 n=5, +77.7%); the primary +5.2pp
# did NOT replicate. The capability below is kept ONLY as a strict-no-op default-
# OFF hook (byte-identical when CV_KELLY_TILT unset); it should remain OFF. No
# pregame conditioner was found to robustly concentrate the AST edge cross-season
# — the durable strategy is the gated ast_high book itself (~+5%, reg-season only).
# Threshold mirrors §8d's 101.9; AST breaks in playoffs (policy_allows_context
# guard already blocks those).
_KELLY_TILT_AST_HIGH_PACE = 1.25
_HIGH_PACE_THRESHOLD = 101.9
_KELLY_TILT_CLAMP = (1.0, 1.5)


def kelly_tilt_enabled() -> bool:
    """True iff CV_KELLY_TILT is set to a truthy value (default OFF)."""
    return (os.environ.get("CV_KELLY_TILT", "0").strip().lower()
            in {"1", "true", "yes", "on", "y", "t"})


def policy_kelly_tilt(stat: str, opp_pace: Optional[float] = None) -> float:
    """Return a multiplicative Kelly stake tilt in [1.0, 1.5]; 1.0 = no-op.

    Strict no-op (returns 1.0) when CV_KELLY_TILT is disabled, when the stat is
    not the tilted one, or when opp_pace is unavailable. Only tilts UP the
    high-pace AST slice (H1) — never tilts down, never drops a bet.

    Callers apply it as ``size = round(size * policy_kelly_tilt(stat, opp_pace), 2)``
    AFTER kelly sizing. Default (flag off) => multiplier 1.0 => byte-identical.
    """
    if not kelly_tilt_enabled() or stat is None:
        return 1.0
    try:
        pace = float(opp_pace) if opp_pace is not None else None
    except (TypeError, ValueError):
        pace = None
    mult = 1.0
    if stat.lower() == "ast" and pace is not None and pace > _HIGH_PACE_THRESHOLD:
        mult = _KELLY_TILT_AST_HIGH_PACE
    lo, hi = _KELLY_TILT_CLAMP
    return max(lo, min(hi, mult))


def _is_playoff_game_id(game_id: Optional[str]) -> bool:
    """True iff *game_id* is an NBA playoff game (canonical prefix ``004``).

    ROBUST to leading-zero stripping: the legacy slate builder does ``int(gid)``,
    turning a 10-digit playoff id ``0042500401`` into ``42500401`` (and a
    regular-season ``0022500401`` into ``22500401``). The naive ``[:3]=="004"``
    check then mis-classified every served playoff bet as regular-season, so the
    playoff-pregame guard and the always-on playoff-AST guard were BOTH inert on
    the live path even with CV_PLAYOFF_PREGAME_GUARD=1 (the bet's game_id never
    carries the leading ``00``). ``zfill(10)`` restores the canonical 10-digit
    form before the prefix check, so BOTH the padded ``0042500401`` and the
    stripped ``42500401`` classify as playoff, while regular-season ``22500401``
    -> ``0022500401`` -> ``002`` stays correctly non-playoff (byte-identical).
    Non-numeric / book event ids (``35669206`` -> ``003``, ``KAMBI_x`` -> ``000``)
    never match ``004`` (no false positive).
    """
    if game_id is None:
        return False
    try:
        return str(game_id).zfill(10)[:3] == "004"
    except Exception:
        return False


def playoff_pregame_guard_enabled() -> bool:
    """True iff CV_PLAYOFF_PREGAME_GUARD is set to a truthy value (default OFF).

    When enabled, ``policy_allows_context`` blocks ALL pregame prop bets on
    playoff game_ids (prefix ``004``) — every stat, not just AST.
    Default OFF = byte-identical current behavior (only the existing AST guard fires).
    """
    return (os.environ.get("CV_PLAYOFF_PREGAME_GUARD", "0").strip().lower()
            in {"1", "true", "yes", "on", "y", "t"})


def playoff_guard_failclosed_enabled() -> bool:
    """True iff CV_PLAYOFF_GUARD_FAILCLOSED is set to a truthy value (default OFF).

    When enabled AND a playoff window is detected (the caller passes
    ``playoff_window=True``, derived from the slate DATE not the game_id),
    ``policy_allows_context`` treats an UNCLASSIFIABLE game_id (a raw book event
    id like ``35669206`` -> ``003``, a KAMBI hash -> ``000``, ``None``/empty —
    anything that is neither a known playoff ``004`` nor a known regular-season
    ``002`` NBA id) as PLAYOFF, i.e. fails CLOSED (blocks the bet) rather than
    fail-open (serving a -EV playoff prop). See SYNTH_PATH_PLAYOFF_GUARD.md:
    the synth/no-CSV serve path carries raw book ids that ``_is_playoff_game_id``
    cannot classify, so the playoff guard was evaded for every synth bet on a
    Finals slate. Default OFF = byte-identical (no date-context branch runs).
    """
    return (os.environ.get("CV_PLAYOFF_GUARD_FAILCLOSED", "0").strip().lower()
            in {"1", "true", "yes", "on", "y", "t"})


def _is_regular_season_game_id(game_id: Optional[str]) -> bool:
    """True iff *game_id* is an unambiguous NBA REGULAR-SEASON game (prefix ``002``).

    Mirror of ``_is_playoff_game_id`` for the reg-season prefix, robust to the
    legacy ``int(gid)`` leading-zero strip (``0022500401`` -> ``22500401`` ->
    ``zfill(10)`` -> ``002``). Used ONLY by the fail-closed playoff branch to
    decide whether an id is a KNOWN reg-season game (in which case it is NEVER
    blocked, even in a playoff window) versus an UNCLASSIFIABLE book/hash id.
    Non-numeric and book event ids do not zfill to ``002`` (``35669206`` ->
    ``003``), so they are correctly NOT treated as known reg-season games.
    """
    if game_id is None:
        return False
    try:
        s = str(game_id)
        # Must be an all-digit NBA-style id to be a *known* reg-season game; a
        # raw book id can be all-digits too but its zfill prefix won't be 002.
        return s.isdigit() and s.zfill(10)[:3] == "002"
    except Exception:
        return False


def policy_allows_context(
    stat: str,
    game_id: Optional[str],
    *,
    playoff_window: bool = False,
) -> bool:
    """Return False iff this (stat, game_context) is excluded by a regime guard.

    Two guards are evaluated in order, either of which can veto a bet:

    1. **Playoff-pregame guard** (CV_PLAYOFF_PREGAME_GUARD, default OFF):
       When enabled, blocks ALL stats on playoff game_ids (prefix ``004``).
       Evidence: docs/_audits/PLAYOFF_PREGAME_EDGE.md — every pregame prop stat
       is negative at real 2026 playoff odds (PTS -9.07%, REB -6.82%,
       AST -10.62%, FG3M -11.05%), and the model MAE is WORSE than the line MAE
       on all four stats.  Escape hatch: set CV_ALLOW_PLAYOFF_PREGAME=1.
       Default OFF so the existing live path is byte-identical until the owner
       explicitly flips the flag for a playoff slate.

    2. **Playoff-AST guard** (always-on, no extra flag needed):
       VS_VEGAS_ASSESSMENT §8e — the AST pregame edge is validated on the
       regular season (~+5% gated cross-season) but BREAKS in the playoffs
       (gated -35.6% in 2026, -2.78% in §8e).  Unless CV_ALLOW_PLAYOFF_AST=1
       is set, AST bets on playoff games are always skipped — even when the
       broader playoff-pregame guard is OFF (back-compat with existing behavior).

    Both guards fire independently; the broader guard (1) subsumes the AST
    guard (2) when it is enabled, but guard (2) remains the only default-on
    change so old behavior is preserved when CV_PLAYOFF_PREGAME_GUARD is unset.
    """
    if stat is None:
        return True

    is_playoff = _is_playoff_game_id(game_id)

    # --- Fail-closed playoff window (CV_PLAYOFF_GUARD_FAILCLOSED, default OFF) ---
    # Closes the SYNTH-PATH hole (SYNTH_PATH_PLAYOFF_GUARD.md): on a no-CSV serve
    # path the bet carries a RAW BOOK id (e.g. '35669206' -> '003') or None, which
    # _is_playoff_game_id cannot classify as playoff, so the playoff guard was
    # evaded for every synth bet on a Finals slate. When the caller has detected a
    # PLAYOFF WINDOW from the slate DATE (date-derived, robust to a stale
    # games_lookup), treat an UNCLASSIFIABLE id (not a known 004 playoff AND not a
    # known 002 regular-season NBA id) as playoff -> block it outright.
    # STRICT no-op unless the flag is ON *and* playoff_window is True: in the
    # regular season playoff_window is False, so an unclassifiable id is NEVER
    # blocked here (reg-season byte-identical). A known reg-season 002 id is also
    # never caught (it returns True below). Default OFF / no playoff_window =
    # byte-identical (this whole block is skipped).
    if (not is_playoff
            and playoff_window
            and playoff_guard_failclosed_enabled()
            and not _is_regular_season_game_id(game_id)):
        # CV_ALLOW_PLAYOFF_PREGAME=1 is the owner's explicit opt-in escape hatch
        # (same hatch guard 1 honors) — let a future validated edge through.
        if os.environ.get("CV_ALLOW_PLAYOFF_PREGAME", "0") == "1":
            return True
        # Fail CLOSED: an unclassifiable id in a detected playoff window is a
        # playoff prop the guards were meant to suppress; block it outright
        # (every stat), independent of CV_PLAYOFF_PREGAME_GUARD. This is the
        # whole point of the fail-closed safety net — the broad guard keys on a
        # 004 prefix this id does not carry, so without this branch a synth
        # book-id bet would fall through to ``return True`` below.
        return False

    if game_id is None and not is_playoff:
        return True
    if not is_playoff:
        return True  # regular-season game: no regime guard applies

    # --- Guard 1: broad playoff-pregame guard (default OFF, owner must flip) ---
    if playoff_pregame_guard_enabled():
        # Escape hatch: CV_ALLOW_PLAYOFF_PREGAME=1 re-enables a future validated edge
        if os.environ.get("CV_ALLOW_PLAYOFF_PREGAME", "0") == "1":
            return True
        return False  # block all stats on playoff game_ids

    # --- Guard 2: AST-specific playoff guard (always-on, back-compat) ---
    if stat.lower() == "ast":
        return os.environ.get("CV_ALLOW_PLAYOFF_AST", "0") == "1"

    return True
