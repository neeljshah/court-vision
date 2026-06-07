"""Shared helpers for the v2 second-by-second (SBS) player-line SHADOW path.

This module holds the small, testable pieces the shadow logger + grader share:

  * ``is_enabled()`` -- reads the NEW env flag ``CV_INGAME_SBS`` (default OFF).
    Mirrors ``src/loop/ingame_atlas_corrector.is_enabled`` exactly. When OFF the
    live/default projection is byte-identical to today: the logger is a strictly
    read-only/append-only shadow lane, and nothing in the live serving path calls
    into the v2 head while the flag is off.
  * ``snapshot_to_v2_rows()`` -- map a canonical LIVE box snapshot (real
    player_id + per-stat box-so-far + is_starter) into per-player v2 CORE feature
    rows (the validated variant), pulling the leak-free L5 prior from gamelog
    rows STRICTLY BEFORE the game date. No future info enters.
  * ``grid_bucket_for()`` -- map a snapshot's (period, clock-remaining) to the
    eval clock-grid bucket label, plus the game-time gate decision (which
    projection a *server* would use at that moment: pregame-L5 in Q1, the v2 head
    in the validated endQ1->midQ3 window, the production snapshot in Q4).

The gate is baked here (not in the logger) so the logger can record, per row,
BOTH the raw v2 projection AND the gated served-equivalent value, and the grader
can promote a (bucket, stat) cell only on a real held-out win.

LEAK / SAFETY:
  * v2 CORE features are pure within-snapshot accumulation + the player's L5 mean
    over games < game_date. The snapshot lacks team FGA/FGM splits, so the pace
    columns are unavailable live -- which is fine: the eval found v2_core (no
    pace) is the best variant, so the served head needs no pace columns.
  * This module never writes anywhere and never mutates the snapshot.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

# Truthy spellings for the gate flag (same set as the atlas corrector).
_TRUTHY = {"1", "true", "yes", "on", "y", "t"}

#: The NEW shadow-mode env flag. Default OFF -> live projection unchanged.
SBS_FLAG = "CV_INGAME_SBS"

PLAYER_STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

REG_PERIOD_LEN = 720  # sec in a regulation period
OT_PERIOD_LEN = 300

# Eval clock-grid (game-ELAPSED sec) -> human label, mirrors eval_sbs_v2.GRID_LABELS.
GRID_SEC: Tuple[int, ...] = (360, 720, 1080, 1440, 1800, 2160, 2520)
GRID_LABELS: Dict[int, str] = {
    360: "06min(midQ1)", 720: "12min(endQ1)", 1080: "18min(midQ2)",
    1440: "24min(endQ2/half)", 1800: "30min(midQ3)", 2160: "36min(endQ3)",
    2520: "42min(midQ4)",
}

# Buckets where the v2 head BEAT the production snapshot held-out (eval_curve_v2):
# endQ1(720) -> midQ3(1800). Outside this window a server defers:
#   * earlier than endQ1 (midQ1, 360s) -> pregame-L5 (season form still better)
#   * endQ3 / Q4 (2160, 2520) -> production snapshot (it catches up + wins late)
V2_WINDOW_SEC: Tuple[int, ...] = (720, 1080, 1440, 1800)


def is_enabled() -> bool:
    """True iff the v2 SBS shadow head is switched on via ``CV_INGAME_SBS``.

    Default OFF: unset / empty / "0" / any non-truthy value keeps the live
    projection byte-identical to today. Truthy spellings ("1", "true", ...) turn
    the shadow head on *inside the shadow process only* -- it never changes the
    served value (the logger always records the BASE projection unmodified).
    """
    return os.environ.get(SBS_FLAG, "0").strip().lower() in _TRUTHY


# --------------------------------------------------------------------------- #
# clock helpers
# --------------------------------------------------------------------------- #
def parse_clock_remaining_sec(clock: Any) -> int:
    """Parse a remaining-time clock to seconds. Accepts 'MM:SS' / ISO 'PT..S'."""
    if clock is None:
        return 0
    if isinstance(clock, (int, float)):
        return int(clock)
    s = str(clock).strip()
    if not s:
        return 0
    up = s.upper()
    if up.startswith("PT"):
        body = up[2:]
        mins = secs = 0.0
        if "M" in body:
            m_part, _, rest = body.partition("M")
            try:
                mins = float(m_part)
            except ValueError:
                pass
            body = rest
        if "S" in body:
            try:
                secs = float(body.split("S")[0])
            except ValueError:
                pass
        return int(mins * 60 + secs)
    if ":" in s:
        try:
            mm, ss = s.split(":")
            return int(float(mm)) * 60 + int(float(ss))
        except (ValueError, TypeError):
            return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def game_elapsed_sec(period: int, clock_remaining_sec: int) -> int:
    """Absolute game-elapsed seconds from period + remaining-clock seconds."""
    period = int(period or 1)
    if period <= 0:
        period = 1
    period_len = REG_PERIOD_LEN if period <= 4 else OT_PERIOD_LEN
    elapsed_in_period = max(0, period_len - int(clock_remaining_sec))
    if period <= 4:
        return REG_PERIOD_LEN * (period - 1) + elapsed_in_period
    return REG_PERIOD_LEN * 4 + OT_PERIOD_LEN * (period - 5) + elapsed_in_period


#: Statuses that mean the game clock has NOT started (no real game time elapsed).
_NOT_STARTED_STATUS = {"PRE_GAME", "PREGAME", "SCHEDULED", "NOT_STARTED", ""}


def grid_bucket_for(period: int, clock: Any,
                    game_status: Any = None) -> Tuple[Optional[int], Optional[str], str]:
    """Map (period, clock) -> (grid_sec, bucket_label, gate_decision).

    The grid_sec is the NEAREST eval grid point to the snapshot's game-elapsed
    time (so a live snapshot a few seconds off a boundary still buckets cleanly).
    gate_decision is what a server WOULD use at this moment:
        "v2"       -> inside the validated endQ1..midQ3 window
        "pregame"  -> before endQ1 (defer to season form / L5)
        "snapshot" -> endQ3..Q4 (defer to the production projector)
    Returns (None, None, "pregame") when the game hasn't started -- a PRE_GAME /
    not-started status, or period < 1 (live feeds emit period 0 + a pregame
    countdown clock that must NOT be mistaken for a game-elapsed grid point).
    """
    if game_status is not None:
        st = str(game_status).strip().upper()
        if st in _NOT_STARTED_STATUS:
            return None, None, "pregame"
    if int(period or 0) < 1:
        return None, None, "pregame"
    rem = parse_clock_remaining_sec(clock)
    elapsed = game_elapsed_sec(period, rem)
    if elapsed < 30:
        return None, None, "pregame"
    grid_sec = min(GRID_SEC, key=lambda g: abs(g - elapsed))
    label = GRID_LABELS[grid_sec]
    if grid_sec in V2_WINDOW_SEC:
        decision = "v2"
    elif grid_sec < min(V2_WINDOW_SEC):
        decision = "pregame"
    else:
        decision = "snapshot"
    return grid_sec, label, decision


# --------------------------------------------------------------------------- #
# snapshot -> v2 CORE feature rows
# --------------------------------------------------------------------------- #
def _l5_from_store(store, pid: int, game_date) -> Optional[Dict[str, float]]:
    """L5 prior (mean of <=5 games STRICTLY before game_date) via a GamelogStore.

    Returns None if the store/date is unavailable so callers can omit the prior
    columns (they default to 0.0 in the v2 vectorizer, never to future data).
    """
    if store is None or game_date is None:
        return None
    try:
        return store.l5_prior(int(pid), game_date)
    except Exception:
        return None


def snapshot_to_v2_rows(
    snap: Dict[str, Any],
    *,
    store=None,
    game_date=None,
) -> List[Dict[str, Any]]:
    """Build per-player v2 CORE feature rows from a canonical live box snapshot.

    Each output dict carries the v2 CORE feature keys (clock + box-so-far +
    p_prior_* from L5) PLUS identity (player_id / name / team) and the resolved
    grid bucket + gate decision, so the logger can record everything in one pass.

    Args:
        snap: canonical live snapshot (player_id + per-stat + is_starter).
        store: optional ``eval_second_by_second.GamelogStore`` for the L5 prior.
        game_date: ``datetime.date`` of the game (for the leak-free L5 cutoff).
    """
    period = int(snap.get("period", 0) or 0)
    clock = snap.get("clock", "12:00")
    rem_sec = parse_clock_remaining_sec(clock)
    elapsed = game_elapsed_sec(period, rem_sec)
    game_total = REG_PERIOD_LEN * 4 if period <= 4 else (
        REG_PERIOD_LEN * 4 + OT_PERIOD_LEN * (period - 4))
    game_rem_sec = max(0, game_total - elapsed)
    played_share = (elapsed / game_total) if game_total else 0.0

    home_score = float(snap.get("home_score", 0) or 0)
    away_score = float(snap.get("away_score", 0) or 0)
    margin = home_score - away_score
    total_so_far = home_score + away_score

    grid_sec, bucket, decision = grid_bucket_for(
        period, clock, game_status=snap.get("game_status"))

    rows: List[Dict[str, Any]] = []
    for p in snap.get("players") or []:
        pid = p.get("player_id")
        if pid is None:
            continue
        cur_min = float(p.get("min", 0) or 0)
        l5 = _l5_from_store(store, pid, game_date)
        row: Dict[str, Any] = {
            # identity (NOT features)
            "player_id": pid,
            "name": p.get("name"),
            "team": p.get("team"),
            # clock features
            "game_remaining_min": game_rem_sec / 60.0,
            "period": float(period or 1),
            "played_share": played_share,
            # box-so-far (snapshot lacks fga/fgm -> 0.0; v2_core tolerates it)
            "p_min_so_far": cur_min,
            "p_pts_so_far": float(p.get("pts", 0) or 0),
            "p_reb_so_far": float(p.get("reb", 0) or 0),
            "p_ast_so_far": float(p.get("ast", 0) or 0),
            "p_fg3m_so_far": float(p.get("fg3m", 0) or 0),
            "p_stl_so_far": float(p.get("stl", 0) or 0),
            "p_blk_so_far": float(p.get("blk", 0) or 0),
            "p_tov_so_far": float(p.get("tov", 0) or 0),
            "p_pf_so_far": float(p.get("pf", 0) or 0),
            "p_fga_so_far": 0.0,
            "p_fgm_so_far": 0.0,
            "p_on_court": 1.0 if cur_min > 0 else 0.0,
            "score_margin": margin,
            "total_so_far": total_so_far,
            # bucket + gate (NOT features)
            "_grid_sec": grid_sec,
            "_bucket": bucket,
            "_gate_decision": decision,
            "_l5": l5,
        }
        for s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min"):
            row[f"p_prior_{s}"] = float(l5[s]) if (l5 and s in l5) else 0.0
        rows.append(row)
    return rows


__all__ = [
    "SBS_FLAG", "is_enabled", "PLAYER_STATS",
    "GRID_SEC", "GRID_LABELS", "V2_WINDOW_SEC",
    "parse_clock_remaining_sec", "game_elapsed_sec", "grid_bucket_for",
    "snapshot_to_v2_rows",
]
