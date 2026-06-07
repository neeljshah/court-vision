"""snapshot_bonus_enricher.py — W-035: in_bonus / team_fouls_period flag capture.

Derives team fouls in the current period and bonus/penalty state from PBP events
(strictly causal, up to but not past the snapshot clock), then attaches the
results to the snapshot dict and to each player row.

Purpose
-------
Needed for:
  - W-033 late-foul trigger (is_trailing AND remaining<3min AND opp_in_bonus)
  - W-027 FT-floor bonus FT bump (when team_fouls_period>=5 or close+clock<3min)

Emitted fields (snapshot root)
-------------------------------
  home_team_fouls_period  — int: fouls committed by the HOME team in the CURRENT
                             period that count toward the penalty (personal/flagrant;
                             offensive and technical skipped).
  away_team_fouls_period  — int: same for AWAY team.
  home_in_bonus           — bool: True if AWAY team has >=5 qualifying fouls in
                             period (home team is in bonus = shooting FTs on any foul).
  away_in_bonus           — bool: True if HOME team has >=5 qualifying fouls in period.
  snap_margin             — float: home_score - away_score at snapshot time.
  snap_clock_remaining_sec — float: seconds remaining in current period.

Emitted fields (per player row)
--------------------------------
Each player row receives a copy of the four team-level fields above so downstream
consumers (W-033, W-027) can read them without accessing the snapshot root:
  team_fouls_period  — int: qualifying fouls committed by THIS player's team in the
                        current period.
  in_bonus           — bool: True if this player is "in the bonus" (shooting FTs on
                        any foul), i.e. the OPPONENT team has >=5 fouls in period.
  snap_margin        — float: home_score - away_score (positive = home leading).
  snap_clock_remaining_sec — float: seconds remaining in current period.

Key guarantees
--------------
1. **Strictly causal** — only PBP events at game_elapsed_sec <= snapshot clock are
   folded.  Appending later events does NOT change enriched values at T
   (as-of-invariance).
2. **in_bonus flips correctly at 5th team foul** — BONUS_FOULS=5 (NBA rule); the
   flag transitions exactly on the 5th qualifying foul in a period, and resets to
   False on period change.
3. **Byte-identical when OFF** — with ``CV_SNAP_BONUS`` unset / "0" / "false" the
   snapshot dict is returned UNCHANGED (no new keys, no mutation).
4. **Non-destructive** — existing keys in snapshot or player rows are never
   overwritten.

Flag
----
``CV_SNAP_BONUS`` (env var) — when "1"/"true"/"yes", ``enrich_snapshot_bonus`` is
active.  When unset / "0" / "false" the function is a transparent no-op.

Public API
----------
``enrich_snapshot_bonus(snapshot, pbp_events)``
    Enriches ``snapshot`` root and ``snapshot["players"]`` rows with bonus-state
    fields derived from PBP replay.  Returns the (possibly mutated) snapshot dict.

``reconstruct_bonus_state(pbp_events, snapshot_game_elapsed_sec, snapshot_period,
                          home_team, away_team)``
    Pure function: returns a dict with ``home_team_fouls``, ``away_team_fouls``,
    ``home_in_bonus``, ``away_in_bonus``.  Useful for testing in isolation.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------
_CV_SNAP_BONUS: bool = (
    os.environ.get("CV_SNAP_BONUS", "0").strip().lower()
    in ("1", "true", "yes")
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Number of qualifying team fouls in a period that puts the OPPONENT in the bonus.
BONUS_FOULS = 5

# PBP event type constants (matches state_featurizer)
_EVT_FOUL = 6
_EVT_END_PERIOD = 13

# ---------------------------------------------------------------------------
# Clock / time helpers (standalone; mirrors snapshot_perq_enricher)
# ---------------------------------------------------------------------------
_REG_PERIOD_LEN = 720      # 12 min in seconds
_OT_PERIOD_LEN = 300       # 5 min in seconds
_REG_GAME_LEN_SEC = 4 * _REG_PERIOD_LEN  # 2880

_RE_ISO_CLOCK = re.compile(r"PT0?(\d+)M([\d.]+)S")

# Regex for "(Pk.Tn)" in foul description — Tn is running TEAM foul count in period.
_RE_PF = re.compile(r"\(P(\d+)\.T(\d+)\)")


def _period_len(period: int) -> int:
    return _REG_PERIOD_LEN if period <= 4 else _OT_PERIOD_LEN


def _game_elapsed_sec(period: int, elapsed_in_period: int) -> int:
    if period <= 4:
        return _REG_PERIOD_LEN * (period - 1) + elapsed_in_period
    return _REG_GAME_LEN_SEC + _OT_PERIOD_LEN * (period - 5) + elapsed_in_period


def _parse_clock_remaining(clock: str) -> float:
    """Parse remaining-time clock string to seconds (float).

    Accepts ISO format ``PTmMsS`` (CDN live) and ``MM:SS`` (historical).
    Returns 0.0 on parse failure.
    """
    if not clock:
        return 0.0
    clock = str(clock).strip()
    m = _RE_ISO_CLOCK.match(clock)
    if m:
        return float(m.group(1)) * 60.0 + float(m.group(2))
    if ":" in clock:
        try:
            mm, ss = clock.split(":", 1)
            return float(mm) * 60.0 + float(ss)
        except (ValueError, TypeError):
            return 0.0
    try:
        return float(clock)
    except (ValueError, TypeError):
        return 0.0


def _event_game_elapsed_sec(ev: Dict[str, Any]) -> int:
    """Extract absolute game-elapsed seconds from a PBP event dict."""
    period = int(ev.get("period", 1) or 1)
    plen = _period_len(period)
    if "clock" in ev and ev["clock"] is not None:
        remaining = _parse_clock_remaining(str(ev["clock"]))
        elapsed = max(0, min(int(plen - remaining), plen))
        return _game_elapsed_sec(period, elapsed)
    if "game_clock_sec" in ev:
        elapsed = int(ev.get("game_clock_sec", 0) or 0)
        elapsed = max(0, min(elapsed, plen))
        return _game_elapsed_sec(period, elapsed)
    return _game_elapsed_sec(period, 0)


def _snapshot_game_elapsed_sec(snap: Dict[str, Any]) -> int:
    """Derive game-elapsed seconds from a snapshot dict."""
    period = int(snap.get("period", 1) or 1)
    clock = str(snap.get("clock") or "12:00")
    remaining = _parse_clock_remaining(clock)
    plen = _period_len(period)
    elapsed_in_period = max(0, plen - int(remaining))
    return _game_elapsed_sec(period, elapsed_in_period)


def _snapshot_clock_remaining_sec(snap: Dict[str, Any]) -> float:
    """Return seconds remaining in the current period from a snapshot dict."""
    clock = str(snap.get("clock") or "12:00")
    return _parse_clock_remaining(clock)


def _snapshot_scores(snap: Dict[str, Any]) -> tuple:
    """Return (home_score, away_score) from snapshot. Returns (0, 0) when absent."""
    home = snap.get("home_score") or snap.get("homeScore") or snap.get("home_pts") or 0
    away = snap.get("away_score") or snap.get("awayScore") or snap.get("away_pts") or 0
    try:
        return float(home), float(away)
    except (TypeError, ValueError):
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Core reconstruction
# ---------------------------------------------------------------------------

def reconstruct_bonus_state(
    pbp_events: List[Dict[str, Any]],
    snapshot_game_elapsed_sec: int,
    snapshot_period: int,
    home_team: str,
    away_team: str,
) -> Dict[str, Any]:
    """Reconstruct team bonus state from PBP events up to snapshot clock.

    Strictly causal: only events at game_elapsed_sec <= snapshot_game_elapsed_sec
    are processed.

    Team-foul counting rules (NBA):
    - Personal fouls and flagrant fouls count toward team foul total.
    - Offensive fouls and technical fouls do NOT advance the opponent toward the bonus.
    - When the PBP description carries "(Pk.Tn)" (player foul k, team foul n in period),
      the running Tn is used authoritatively (takes max to avoid stale events).
    - Team foul counts reset to 0 at each period change.

    Args:
        pbp_events: ordered list of raw PBP event dicts.
        snapshot_game_elapsed_sec: upper bound clock (inclusive).
        snapshot_period: current period of the snapshot.
        home_team: home team tricode.
        away_team: away team tricode.

    Returns:
        dict with:
          ``home_team_fouls`` — int: qualifying fouls by HOME team in current period.
          ``away_team_fouls`` — int: qualifying fouls by AWAY team in current period.
          ``home_in_bonus``   — bool: True if AWAY team has >= BONUS_FOULS fouls
                                (home team is in the bonus).
          ``away_in_bonus``   — bool: True if HOME team has >= BONUS_FOULS fouls.
    """
    team_fouls: Dict[str, int] = {"home": 0, "away": 0}
    cur_period_seen: Optional[int] = None

    def _side(team_tricode: str) -> str:
        """Return 'home' or 'away' for a team tricode, or '' if unknown."""
        t = str(team_tricode).strip()
        if home_team and t == home_team:
            return "home"
        if away_team and t == away_team:
            return "away"
        return ""

    for ev in pbp_events:
        ev_elapsed = _event_game_elapsed_sec(ev)
        if ev_elapsed > snapshot_game_elapsed_sec:
            continue  # strictly causal

        period = int(ev.get("period", 1) or 1)

        # Reset team fouls at period boundary.
        if cur_period_seen is None:
            cur_period_seen = period
        elif period != cur_period_seen:
            team_fouls = {"home": 0, "away": 0}
            cur_period_seen = period

        etype = int(ev.get("event_type", -1) or -1)
        action_type = str(ev.get("action_type") or ev.get("actionType") or "")
        desc = str(ev.get("event_desc") or ev.get("description") or "")
        team = str(ev.get("team_tricode") or ev.get("team_abbrev") or "").strip()
        side = _side(team)

        is_foul = (etype == _EVT_FOUL) or ("foul" in action_type.lower())
        is_end_period = (etype == _EVT_END_PERIOD) or (
            "end" in action_type.lower() and "period" in action_type.lower()
        )

        if is_end_period:
            # Period ended: fouls will reset on the next period's first event.
            # We do nothing here; reset logic fires on period change above.
            continue

        if is_foul and side:
            # Determine whether this foul counts toward the bonus.
            # Offensive and technical fouls do NOT advance toward bonus.
            # We detect offensive/technical via:
            #   (a) qualifier fields set by W-028 (CV_PBP_QUALIFIERS)
            #   (b) description text heuristics as fallback.
            is_offensive = bool(ev.get("offensive_foul"))
            is_technical = bool(ev.get("technical"))

            # Description-based fallback detection.
            desc_upper = desc.upper()
            if not is_offensive:
                is_offensive = "OFFENSIVE" in desc_upper
            if not is_technical:
                is_technical = "TECHNICAL" in desc_upper or "T.FOUL" in desc_upper

            if is_offensive or is_technical:
                # Offensive/technical fouls: skip team-foul increment.
                continue

            # Use the authoritative running team-foul count "(Pk.Tn)" when present.
            pm = _RE_PF.search(desc)
            if pm:
                running_team_fouls = int(pm.group(2))
                team_fouls[side] = max(team_fouls[side], running_team_fouls)
            else:
                team_fouls[side] += 1

    # Post-loop: if the snapshot is in a later period than the last event seen in the
    # PBP stream (e.g. all events were in Q1, snapshot is in Q2), the team fouls for
    # the snapshot period are 0 — they haven't happened yet.
    if cur_period_seen is not None and cur_period_seen < snapshot_period:
        team_fouls = {"home": 0, "away": 0}

    return {
        "home_team_fouls": team_fouls["home"],
        "away_team_fouls": team_fouls["away"],
        "home_in_bonus": team_fouls["away"] >= BONUS_FOULS,
        "away_in_bonus": team_fouls["home"] >= BONUS_FOULS,
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def enrich_snapshot_bonus(
    snapshot: Dict[str, Any],
    pbp_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Enrich snapshot and player rows with in_bonus / team_fouls_period state.

    **When ``CV_SNAP_BONUS`` is OFF** (the default), returns the snapshot
    unchanged — byte-identical guarantee.

    **When ON:**
    1. Replays PBP foul events up to the snapshot clock (strictly causal).
    2. Adds to the snapshot root (non-destructive — existing keys NOT overwritten):
       - ``home_team_fouls_period``  (int)
       - ``away_team_fouls_period``  (int)
       - ``home_in_bonus``           (bool)
       - ``away_in_bonus``           (bool)
       - ``snap_margin``             (float, home_score - away_score)
       - ``snap_clock_remaining_sec`` (float)
    3. Adds to each player row (non-destructive):
       - ``team_fouls_period``       (int, this player's team fouls in period)
       - ``in_bonus``                (bool, this player is in the bonus = opp has >=5 fouls)
       - ``snap_margin``             (float)
       - ``snap_clock_remaining_sec`` (float)

    Args:
        snapshot: live box snapshot dict (mutable; modified in-place).
        pbp_events: ordered PBP event dicts for this game.  May be None/empty;
            if so, team fouls default to 0, in_bonus defaults to False.

    Returns:
        The (possibly mutated) snapshot dict.
    """
    if not _CV_SNAP_BONUS:
        return snapshot  # byte-identical when flag OFF

    snap_elapsed_sec = _snapshot_game_elapsed_sec(snapshot)
    snap_period = int(snapshot.get("period", 1) or 1)
    home_team = str(snapshot.get("home_team") or "")
    away_team = str(snapshot.get("away_team") or "")
    clock_remaining = _snapshot_clock_remaining_sec(snapshot)
    home_score, away_score = _snapshot_scores(snapshot)
    margin = home_score - away_score

    events_to_fold: List[Dict[str, Any]] = pbp_events or []

    bonus_state = reconstruct_bonus_state(
        events_to_fold,
        snap_elapsed_sec,
        snap_period,
        home_team,
        away_team,
    )

    home_fouls = bonus_state["home_team_fouls"]
    away_fouls = bonus_state["away_team_fouls"]
    home_in_bonus = bonus_state["home_in_bonus"]
    away_in_bonus = bonus_state["away_in_bonus"]

    # --- Attach fields to snapshot root (non-destructive) ---
    if "home_team_fouls_period" not in snapshot:
        snapshot["home_team_fouls_period"] = home_fouls
    if "away_team_fouls_period" not in snapshot:
        snapshot["away_team_fouls_period"] = away_fouls
    if "home_in_bonus" not in snapshot:
        snapshot["home_in_bonus"] = home_in_bonus
    if "away_in_bonus" not in snapshot:
        snapshot["away_in_bonus"] = away_in_bonus
    if "snap_margin" not in snapshot:
        snapshot["snap_margin"] = margin
    if "snap_clock_remaining_sec" not in snapshot:
        snapshot["snap_clock_remaining_sec"] = clock_remaining

    # --- Attach per-player fields (non-destructive) ---
    players: List[Dict[str, Any]] = snapshot.get("players") or []
    for p in players:
        team = str(p.get("team") or "")
        is_home = home_team and team == home_team
        is_away = away_team and team == away_team

        if is_home:
            p_team_fouls = home_fouls
            p_in_bonus = home_in_bonus  # home player in bonus = away has >=5 fouls
        elif is_away:
            p_team_fouls = away_fouls
            p_in_bonus = away_in_bonus  # away player in bonus = home has >=5 fouls
        else:
            # Unknown team — conservative defaults.
            p_team_fouls = 0
            p_in_bonus = False

        if "team_fouls_period" not in p:
            p["team_fouls_period"] = p_team_fouls
        if "in_bonus" not in p:
            p["in_bonus"] = p_in_bonus
        if "snap_margin" not in p:
            p["snap_margin"] = margin
        if "snap_clock_remaining_sec" not in p:
            p["snap_clock_remaining_sec"] = clock_remaining

    return snapshot
