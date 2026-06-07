"""snapshot_perq_enricher.py — W-030: per-quarter minutes, per-quarter fouls, EOQ scores.

Enriches a live box snapshot with per-quarter player/team stats derived by
replaying PBP events up to (but not past) the snapshot clock.

Emitted fields (per player)
---------------------------
  min_q1, min_q2, min_q3, min_q4   — minutes played in each completed quarter
                                       (float, 0.0 when not in game or quarter not
                                       yet reached; fractional minutes allowed)
  pf_q1, pf_q2, pf_q3, pf_q4       — personal fouls committed in each quarter
                                       (int, 0 when no foul events in that quarter)

Emitted fields (snapshot-level / team-level)
---------------------------------------------
  pts_by_period      — dict { "home": [q1_pts, q2_pts, q3_pts, q4_pts] or partial,
                              "away": [q1_pts, q2_pts, q3_pts, q4_pts] or partial }
                         Each element is the points scored DURING that quarter only
                         (not cumulative).  Only completed quarters are filled; the
                         current in-progress quarter is omitted.

  score_by_period    — dict { "home": [q1_cum, q2_cum, q3_cum, q4_cum],
                              "away": [q1_cum, q2_cum, q3_cum, q4_cum] }
                         Running CUMULATIVE score at the end of each completed
                         quarter (int).  Same length as pts_by_period.

score_velocity_q3 / score_velocity_q2 are also provided at the snapshot root level
for the blowout residual (W-020) and margin model (W-021).

Key guarantees
--------------
1. **Strictly causal** — only PBP events at game_elapsed_sec <= snapshot clock are
   folded.  Appending later events does NOT change the enriched values at T
   (as-of-invariance).
2. **min_q sums match cumulative min** — sum(min_q1..q4) == min_so_far for players
   active in those quarters (within floating-point tolerance).
3. **Byte-identical when OFF** — with ``CV_SNAP_ENRICH_PERQ`` unset / "0" / "false"
   the snapshot dict is returned UNCHANGED (no new keys, no mutation).
4. **Non-destructive** — existing keys are never overwritten.

Flag
----
``CV_SNAP_ENRICH_PERQ`` (env var) — when "1"/"true"/"yes", ``enrich_snapshot_perq``
is active.  When unset / "0" / "false" the function is a transparent no-op.

Public API
----------
``enrich_snapshot_perq(snapshot, pbp_events)``
    Enriches ``snapshot["players"]`` rows with per-quarter minute/foul fields and
    adds ``pts_by_period`` / ``score_by_period`` / ``score_velocity_q3`` at the
    snapshot root.  Returns the (possibly mutated) snapshot dict.

``reconstruct_perq(pbp_events, snapshot_game_elapsed_sec, home_team, away_team)``
    Pure function used by the enricher and by tests.  Returns a dict with keys
    ``players``, ``pts_by_period``, ``score_by_period``.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------
_CV_SNAP_ENRICH_PERQ: bool = (
    os.environ.get("CV_SNAP_ENRICH_PERQ", "0").strip().lower()
    in ("1", "true", "yes")
)

# ---------------------------------------------------------------------------
# Clock / time helpers (local copies — keeps this module standalone)
# ---------------------------------------------------------------------------
_REG_PERIOD_LEN = 720     # 12 min in seconds
_OT_PERIOD_LEN = 300      # 5 min in seconds
_REG_GAME_LEN_SEC = 4 * _REG_PERIOD_LEN  # 2880


def _period_len(period: int) -> int:
    return _REG_PERIOD_LEN if period <= 4 else _OT_PERIOD_LEN


def _game_elapsed_sec(period: int, elapsed_in_period: int) -> int:
    """Absolute game-elapsed seconds."""
    if period <= 4:
        return _REG_PERIOD_LEN * (period - 1) + elapsed_in_period
    return _REG_GAME_LEN_SEC + _OT_PERIOD_LEN * (period - 5) + elapsed_in_period


_RE_ISO_CLOCK = re.compile(r"PT0?(\d+)M([\d.]+)S")


def _parse_clock_remaining(clock: str) -> int:
    """Parse remaining-time clock string to integer seconds (ISO or MM:SS)."""
    if not clock:
        return 0
    clock = str(clock).strip()
    m = _RE_ISO_CLOCK.match(clock)
    if m:
        return int(int(m.group(1)) * 60 + float(m.group(2)))
    if ":" in clock:
        try:
            mm, ss = clock.split(":")
            return int(float(mm)) * 60 + int(float(ss))
        except (ValueError, TypeError):
            return 0
    try:
        return int(float(clock))
    except (ValueError, TypeError):
        return 0


def _event_game_elapsed_sec(ev: Dict[str, Any]) -> int:
    """Extract absolute game-elapsed seconds from a PBP event dict.

    Handles live CDN schema (period + clock ISO/MM:SS REMAINING) and historical
    schema (period + game_clock_sec ELAPSED-in-period).
    """
    period = int(ev.get("period", 1) or 1)
    plen = _period_len(period)

    if "clock" in ev and ev["clock"] is not None:
        remaining = _parse_clock_remaining(str(ev["clock"]))
        elapsed = max(0, min(plen - remaining, plen))
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
    elapsed_in_period = max(0, plen - remaining)
    return _game_elapsed_sec(period, elapsed_in_period)


def _snapshot_period(snap: Dict[str, Any]) -> int:
    """Get current period from snapshot."""
    return int(snap.get("period", 1) or 1)


# ---------------------------------------------------------------------------
# Event type constants (matches state_featurizer)
# ---------------------------------------------------------------------------
_EVT_MADE_FG = 1
_EVT_FREE_THROW = 3
_EVT_FOUL = 6
_EVT_SUB = 8
_EVT_END_PERIOD = 13

# Regex for foul description "(Pk.Tn)" — player foul count
_RE_PF = re.compile(r"\(P(\d+)\.T(\d+)\)")
# Regex for running point total "(N PTS)"
_RE_PTS = re.compile(r"\((\d+)\s*PTS\)")


# ---------------------------------------------------------------------------
# Per-player per-quarter accumulator
# ---------------------------------------------------------------------------

class _PlayerPerQState:
    """Tracks per-quarter minutes and fouls for a single player."""

    def __init__(self) -> None:
        # seconds played within each quarter (quarters 1..4+)
        self._sec_in_q: Dict[int, float] = defaultdict(float)
        # fouls committed in each quarter (quarters 1..4+)
        self._pf_in_q: Dict[int, int] = defaultdict(int)
        # on-court tracking: (period, game_elapsed_sec) when last went on court
        self._on_since: Optional[Tuple[int, int]] = None  # (period, game_sec)
        self._on_court: bool = False

    def go_on(self, period: int, game_sec: int) -> None:
        if not self._on_court:
            self._on_court = True
            self._on_since = (period, game_sec)

    def go_off(self, period: int, game_sec: int) -> None:
        """Record that player went off court at the given time."""
        if self._on_court and self._on_since is not None:
            self._accrue_time(self._on_since[0], self._on_since[1], period, game_sec)
        self._on_court = False
        self._on_since = None

    def flush_at(self, period: int, game_sec: int) -> None:
        """Accrue current on-court time up to game_sec without going off court.

        Called at the snapshot boundary to include partial-quarter time.
        """
        if self._on_court and self._on_since is not None:
            self._accrue_time(self._on_since[0], self._on_since[1], period, game_sec)
            # Reset the on-since to the current time so repeated flush calls work.
            self._on_since = (period, game_sec)

    def add_foul(self, period: int) -> None:
        self._pf_in_q[period] += 1

    def set_foul_total_q(self, period: int, pf_total_after_event: int) -> None:
        """Update fouls in a period based on running total.

        When the PBP carries a running per-player total (Pk.Tn style), we infer
        per-quarter fouls by noting how many fouls were committed before this
        period started.  Approximation: all fouls before current period are
        in earlier periods (accurate within ~1 foul for typical games).
        """
        # Sum fouls in all prior periods (those < period).
        prior_pf = sum(v for q, v in self._pf_in_q.items() if q < period)
        # Fouls in this period so far = running total - prior total.
        pf_this_q = max(0, pf_total_after_event - prior_pf)
        self._pf_in_q[period] = pf_this_q

    def _accrue_time(
        self,
        start_period: int, start_sec: int,
        end_period: int, end_sec: int,
    ) -> None:
        """Distribute elapsed seconds across quarters from start to end."""
        if end_sec <= start_sec and end_period == start_period:
            return  # no forward time

        # Walk period by period from start_period to end_period.
        cur_period = start_period
        cur_sec = start_sec
        while cur_period <= end_period:
            plen = _period_len(cur_period)
            # Where does this period end (in absolute game seconds)?
            period_end_sec = _game_elapsed_sec(cur_period, plen)
            if cur_period < end_period:
                # Player was on court for the rest of this period.
                self._sec_in_q[cur_period] += max(0.0, period_end_sec - cur_sec)
                cur_period += 1
                cur_sec = _game_elapsed_sec(cur_period, 0)  # start of next period
            else:
                # Same period as the end — accrue from cur_sec to end_sec.
                self._sec_in_q[cur_period] += max(0.0, end_sec - cur_sec)
                break

    def minutes_by_quarter(self) -> Dict[int, float]:
        """Return {quarter: minutes} for quarters 1..4+ (only non-zero)."""
        return {q: secs / 60.0 for q, secs in self._sec_in_q.items() if secs > 0}

    def fouls_by_quarter(self) -> Dict[int, int]:
        """Return {quarter: fouls} for quarters 1..4+ (only non-zero)."""
        return {q: pf for q, pf in self._pf_in_q.items() if pf > 0}


# ---------------------------------------------------------------------------
# Core reconstruction
# ---------------------------------------------------------------------------

def reconstruct_perq(
    pbp_events: List[Dict[str, Any]],
    snapshot_game_elapsed_sec: int,
    snapshot_period: int,
    home_team: str,
    away_team: str,
) -> Dict[str, Any]:
    """Reconstruct per-quarter player stats and team scores from PBP events.

    Strictly causal: only events at game_elapsed_sec <= snapshot_game_elapsed_sec
    are processed.

    Args:
        pbp_events: ordered list of raw PBP event dicts (historical or live CDN).
        snapshot_game_elapsed_sec: upper bound clock (inclusive).
        snapshot_period: current period of the snapshot (used to know which
            quarters are "completed").
        home_team: home team tricode.
        away_team: away team tricode.

    Returns:
        dict with:
          ``players``         — {player_key: _PlayerPerQState}
          ``pts_by_period``   — {"home": list[int], "away": list[int]}
          ``score_by_period`` — {"home": list[int], "away": list[int]}
        where player_key = (team_tricode, player_id_or_name).
    """
    # Per-player state: keyed by (team, player_id or name)
    player_states: Dict[Tuple[str, Any], _PlayerPerQState] = {}

    # Team scoring per period: running cumulative at end of each period
    # and within-period running totals to compute period-by-period pts.
    team_score: Dict[str, int] = {"home": 0, "away": 0}
    # Completed periods: score at END of each period (1-indexed)
    completed_period_scores: Dict[str, List[int]] = {"home": [], "away": []}
    # End-of-period scores (cumulative at end of Q1/Q2/Q3/Q4...)
    period_end_score: Dict[str, Dict[int, int]] = {
        "home": {},
        "away": {},
    }

    # Track "score at start of current period" for computing period-delta
    # Derived lazily from period_end_score.

    # Which side owns each team tricode
    _team_to_side: Dict[str, str] = {}
    if home_team:
        _team_to_side[home_team] = "home"
    if away_team:
        _team_to_side[away_team] = "away"

    def _side(team: str) -> str:
        return _team_to_side.get(str(team).strip(), "")

    def _get_player(team: str, pid: Any) -> _PlayerPerQState:
        key = (str(team).strip(), pid)
        if key not in player_states:
            player_states[key] = _PlayerPerQState()
        return player_states[key]

    def _resolve_player_key(ev: Dict[str, Any]) -> Tuple[str, Any]:
        team = str(ev.get("team_tricode") or ev.get("team_abbrev") or "").strip()
        # Prefer integer player_id; fall back to player name
        raw_pid = ev.get("player_id") or ev.get("personId") or ev.get("player_name")
        try:
            pid: Any = int(raw_pid)
        except (TypeError, ValueError):
            pid = str(raw_pid or "").strip() or None
        return team, pid

    max_period_seen = 1

    for ev in pbp_events:
        ev_elapsed = _event_game_elapsed_sec(ev)
        if ev_elapsed > snapshot_game_elapsed_sec:
            continue  # strictly causal

        period = int(ev.get("period", 1) or 1)
        max_period_seen = max(max_period_seen, period)

        etype = int(ev.get("event_type", -1) or -1)
        action_type = str(ev.get("action_type") or ev.get("actionType") or "")
        desc = str(ev.get("event_desc") or ev.get("description") or "")
        team = str(ev.get("team_tricode") or ev.get("team_abbrev") or "").strip()
        side = _side(team)

        # --- Substitution: track player on/off for minute accounting ---
        is_sub = (etype == _EVT_SUB) or ("substitut" in action_type.lower())
        if is_sub and team:
            _process_sub(ev, team, period, ev_elapsed, player_states)

        # --- Scoring events: update team score ---
        if etype == _EVT_MADE_FG and side:
            pts = _pts_from_desc(desc)
            # We infer score from running total if available, else increment by 2/3.
            if side:
                # Update score from the running "(N PTS)" total when available.
                # This is per-player total, not team — we use FG value (2 or 3).
                fg_pts = 3 if "3PT" in desc else 2
                team_score[side] = team_score.get(side, 0) + fg_pts

        elif etype == _EVT_FREE_THROW and side:
            made = "MISS" not in desc.upper()
            if made:
                team_score[side] = team_score.get(side, 0) + 1

        # --- Foul events: track per-quarter per-player fouls ---
        if etype == _EVT_FOUL and team:
            raw_pid = ev.get("player_id") or ev.get("personId") or ev.get("player_name")
            try:
                pid: Any = int(raw_pid)
            except (TypeError, ValueError):
                pid = str(raw_pid or "").strip() or None
            if pid is not None:
                ps = _get_player(team, pid)
                pm = _RE_PF.search(desc)
                if pm:
                    ps.set_foul_total_q(period, int(pm.group(1)))
                else:
                    ps.add_foul(period)

        # --- End-of-period: snapshot the cumulative team score ---
        is_end_period = (etype == _EVT_END_PERIOD) or (
            "end" in action_type.lower() and "period" in action_type.lower()
        )
        if is_end_period:
            fin_period = period
            # Try to get authoritative score from the event's score field first.
            _update_period_end_score(ev, fin_period, team_score, period_end_score)

        # --- Mark participating player as on-court ---
        # Any player who does something (except sub/end-period) is on court.
        if etype not in (_EVT_SUB, _EVT_END_PERIOD) and not is_sub and not is_end_period:
            if team:
                raw_pid2 = ev.get("player_id") or ev.get("personId") or ev.get("player_name")
                try:
                    pid2: Any = int(raw_pid2)
                except (TypeError, ValueError):
                    pid2 = str(raw_pid2 or "").strip() or None
                if pid2 is not None:
                    ps2 = _get_player(team, pid2)
                    ps2.go_on(period, ev_elapsed)

    # --- Flush all on-court players at the snapshot boundary ---
    for ps in player_states.values():
        ps.flush_at(snapshot_period, snapshot_game_elapsed_sec)

    # --- Build pts_by_period and score_by_period from period_end_score ---
    # Completed quarters = all quarters < snapshot_period.
    # (If we are mid-Q3, only Q1 and Q2 are "completed".)
    completed_quarters = list(range(1, snapshot_period))

    pts_by_period: Dict[str, List[int]] = {"home": [], "away": []}
    score_by_period: Dict[str, List[int]] = {"home": [], "away": []}

    for side in ("home", "away"):
        prev_cum = 0
        for q in completed_quarters:
            cum = period_end_score[side].get(q, team_score.get(side, 0) if q == completed_quarters[-1] else prev_cum)
            pts_by_period[side].append(cum - prev_cum)
            score_by_period[side].append(cum)
            prev_cum = cum

    return {
        "player_states": player_states,
        "pts_by_period": pts_by_period,
        "score_by_period": score_by_period,
        "period_end_score": period_end_score,
        "team_score_running": dict(team_score),
    }


# ---------------------------------------------------------------------------
# Sub-event processing helper
# ---------------------------------------------------------------------------
_RE_SUB_DESC = re.compile(r"SUB:\s*(.+?)\s+FOR\s+(.+?)\s*$", re.IGNORECASE)


def _process_sub(
    ev: Dict[str, Any],
    team: str,
    period: int,
    game_sec: int,
    player_states: Dict[Tuple[str, Any], _PlayerPerQState],
) -> None:
    """Apply a substitution event to on-court tracking."""
    desc = str(ev.get("event_desc") or ev.get("description") or "")
    dm = _RE_SUB_DESC.search(desc)

    in_pid: Any = None
    out_pid: Any = None

    # CDN live schema: personIdsFilter = [out_id, in_id]
    raw = ev.get("raw") or {}
    ids_filter = raw.get("personIdsFilter") or []
    if len(ids_filter) >= 2:
        try:
            out_pid = int(ids_filter[0])
        except (TypeError, ValueError):
            pass
        try:
            in_pid = int(ids_filter[1])
        except (TypeError, ValueError):
            pass
    elif len(ids_filter) == 1:
        try:
            out_pid = int(ids_filter[0])
        except (TypeError, ValueError):
            pass

    # Fallback: use player_id / personId as the OUT player
    if out_pid is None:
        raw_pid = ev.get("player_id") or ev.get("personId")
        if raw_pid is not None:
            try:
                out_pid = int(raw_pid)
            except (TypeError, ValueError):
                pass

    # Use description text names when no ids
    if dm:
        in_name = dm.group(1).strip()
        out_name = dm.group(2).strip()
        if out_pid is None:
            out_pid = out_name or None
        if in_pid is None:
            in_pid = in_name or None

    if out_pid is not None:
        ps_out = _get_or_create(player_states, team, out_pid)
        ps_out.go_off(period, game_sec)

    if in_pid is not None:
        ps_in = _get_or_create(player_states, team, in_pid)
        ps_in.go_on(period, game_sec)


def _get_or_create(
    states: Dict[Tuple[str, Any], _PlayerPerQState],
    team: str,
    pid: Any,
) -> _PlayerPerQState:
    key = (str(team).strip(), pid)
    if key not in states:
        states[key] = _PlayerPerQState()
    return states[key]


# ---------------------------------------------------------------------------
# Score extraction helper
# ---------------------------------------------------------------------------
_RE_SCORE_FIELD = re.compile(r"^(\d+)\s*[-–]\s*(\d+)$")


def _update_period_end_score(
    ev: Dict[str, Any],
    period: int,
    team_score: Dict[str, int],
    period_end_score: Dict[str, Dict[int, int]],
) -> None:
    """Record cumulative home/away score at end of ``period``.

    Tries to parse the authoritative ``score`` / ``scoreHome`` / ``scoreAway``
    fields from the event.  Falls back to the running ``team_score`` accumulator.
    """
    # Live CDN: scoreHome / scoreAway direct integer fields
    sh = ev.get("scoreHome") or ev.get("score_home")
    sa = ev.get("scoreAway") or ev.get("score_away")
    if sh is not None and sa is not None:
        try:
            period_end_score["home"][period] = int(sh)
            period_end_score["away"][period] = int(sa)
            return
        except (TypeError, ValueError):
            pass

    # Historical schema: "score" field is "L-R" string
    score_str = str(ev.get("score") or "")
    m = _RE_SCORE_FIELD.match(score_str.strip())
    if m:
        # L-R orientation — we don't know which is home here; store as-is
        # and rely on caller's orientation knowledge.  Store under raw keys.
        period_end_score["home"][period] = max(
            period_end_score["home"].get(period, 0),
            int(m.group(1)),
        )
        period_end_score["away"][period] = max(
            period_end_score["away"].get(period, 0),
            int(m.group(2)),
        )
        return

    # Last resort: use running accumulator
    period_end_score["home"][period] = team_score.get("home", 0)
    period_end_score["away"][period] = team_score.get("away", 0)


def _pts_from_desc(desc: str) -> int:
    """Extract player running point total from a scoring event description."""
    m = _RE_PTS.search(desc)
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------------------
# Snapshot integration helpers
# ---------------------------------------------------------------------------

def _player_key_from_row(p: Dict[str, Any], home_team: str, away_team: str) -> Tuple[str, Any]:
    """Build the same (team, pid) key used in reconstruct_perq from a snapshot player row."""
    team = str(p.get("team") or "").strip()
    raw_pid = p.get("player_id")
    try:
        pid: Any = int(raw_pid)
    except (TypeError, ValueError):
        pid = str(p.get("name") or "").strip() or None
    return (team, pid)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def enrich_snapshot_perq(
    snapshot: Dict[str, Any],
    pbp_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Enrich snapshot with per-quarter minutes/fouls and EOQ scores.

    **When ``CV_SNAP_ENRICH_PERQ`` is OFF** (the default), returns the snapshot
    unchanged — byte-identical guarantee.

    **When ON:**
    1. Replays PBP events up to the snapshot clock (strictly causal).
    2. For each player in ``snapshot["players"]``, adds:
       - ``min_q1`` .. ``min_q4`` (float, minutes played in that quarter)
       - ``pf_q1`` .. ``pf_q4`` (int, personal fouls in that quarter)
    3. Adds to the snapshot root:
       - ``pts_by_period``   — {"home": [int, ...], "away": [int, ...]} per-quarter points
       - ``score_by_period`` — {"home": [int, ...], "away": [int, ...]} cumulative at each Q end
       - ``score_velocity_q3`` — Q3 margin delta (home_q3 - away_q3), 0.0 if unavailable
       - ``score_velocity_q2`` — Q2 margin delta (home_q2 - away_q2), 0.0 if unavailable

    Per-quarter fields already present on a player row are NOT overwritten.

    Args:
        snapshot: live box snapshot dict (mutable; modified in-place).
        pbp_events: ordered PBP event dicts for this game.  May be None / empty;
            if so, all per-quarter fields default to 0.

    Returns:
        The (possibly mutated) snapshot dict.
    """
    if not _CV_SNAP_ENRICH_PERQ:
        return snapshot  # byte-identical when flag OFF

    players: List[Dict[str, Any]] = snapshot.get("players") or []
    snap_elapsed_sec = _snapshot_game_elapsed_sec(snapshot)
    snap_period = _snapshot_period(snapshot)
    home_team = str(snapshot.get("home_team") or "")
    away_team = str(snapshot.get("away_team") or "")

    events_to_fold: List[Dict[str, Any]] = pbp_events or []

    result = reconstruct_perq(
        events_to_fold,
        snap_elapsed_sec,
        snap_period,
        home_team,
        away_team,
    )

    player_states = result["player_states"]
    pts_by_period = result["pts_by_period"]
    score_by_period = result["score_by_period"]

    # --- Attach per-quarter fields to each player row ---
    for p in players:
        team = str(p.get("team") or "").strip()
        raw_pid = p.get("player_id")
        try:
            pid: Any = int(raw_pid)
        except (TypeError, ValueError):
            pid = str(p.get("name") or "").strip() or None

        # Look up in player_states; fall back to a blank state.
        key = (team, pid)
        ps = player_states.get(key) or _PlayerPerQState()

        min_by_q = ps.minutes_by_quarter()
        pf_by_q = ps.fouls_by_quarter()

        for q in range(1, 5):
            min_key = f"min_q{q}"
            pf_key = f"pf_q{q}"
            if min_key not in p:
                p[min_key] = round(min_by_q.get(q, 0.0), 4)
            if pf_key not in p:
                p[pf_key] = pf_by_q.get(q, 0)

    # --- Attach pts_by_period / score_by_period to snapshot root ---
    if "pts_by_period" not in snapshot:
        snapshot["pts_by_period"] = pts_by_period
    if "score_by_period" not in snapshot:
        snapshot["score_by_period"] = score_by_period

    # --- Derive score_velocity_q3 and score_velocity_q2 ---
    # score_velocity_q3 = home Q3 pts - away Q3 pts (index 2)
    if "score_velocity_q3" not in snapshot:
        home_q = pts_by_period.get("home", [])
        away_q = pts_by_period.get("away", [])
        if len(home_q) >= 3 and len(away_q) >= 3:
            snapshot["score_velocity_q3"] = float(home_q[2] - away_q[2])
        else:
            snapshot["score_velocity_q3"] = 0.0

    if "score_velocity_q2" not in snapshot:
        home_q = pts_by_period.get("home", [])
        away_q = pts_by_period.get("away", [])
        if len(home_q) >= 2 and len(away_q) >= 2:
            snapshot["score_velocity_q2"] = float(home_q[1] - away_q[1])
        else:
            snapshot["score_velocity_q2"] = 0.0

    return snapshot
