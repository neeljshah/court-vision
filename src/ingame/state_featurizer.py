"""Leak-free in-game state featurizer (event-ordered) from historical PBP.

Given a historical game's play-by-play (the one-file-per-period
``data/nba/pbp_<gid>_p<period>.json`` dump) OR a single live snapshot/event,
produce EVENT-ORDERED, strictly leak-free state feature rows.

Each row at event E uses ONLY information available at E's game-clock moment:
prior events in THIS game (events with (period, elapsed) <= E). It carries NO
season-aggregate / as-of-today snapshot of the current game and NO information
from any event after E. (Prior-form features computed from the player/team's
games strictly BEFORE this game's date are the caller's concern -- this module
deliberately produces only WITHIN-GAME state so the leak surface is zero here.)

Two row granularities are emitted per event:
  * one TEAM-LEVEL / game-level row (clock, score, possession, pace, four-factors)
  * optionally per-player rows (minutes/usage/pts/reb/ast/... so far)

Schema is documented in ``GAME_STATE_FIELDS`` / ``PLAYER_STATE_FIELDS`` below.

The historical PBP clock (``game_clock_sec``) is ELAPSED within the period
(0 at tip -> 720 at end of a 12-min period; OT periods 0->300). We convert to
remaining and absolute game-elapsed here, matching ``predict_in_game`` semantics
(which use REMAINING). See SPEC section 1.1 / 4.

No external heavy deps: stdlib + (optional) pandas for the backfill helper.
"""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# CV_PBP_QUALIFIERS — when "1"/"true", the event accumulation loop reads
# first-class qualifier fields (sub_type, qualifiers, offensive_foul,
# technical, flagrant, and_1, fastbreak, ejection) promoted by
# pbp_poller._event_from_play.  When OFF the per-event logic is byte-identical
# to the pre-qualifier behaviour (only event_type + event_desc are used).
_CV_PBP_QUALIFIERS: bool = (
    os.environ.get("CV_PBP_QUALIFIERS", "0").strip().lower() in ("1", "true", "yes")
)

# CV_LATE_FOUL_STATE — when "1"/"true", _compute_pace_state emits the
# composite ``late_foul_active`` field: 1 when late-game intentional-foul
# conditions are detected (trailing team, low clock, opp in bonus).
# When OFF the field is omitted entirely → byte-identical for downstream
# consumers that don't read this key.
_CV_LATE_FOUL_STATE: bool = (
    os.environ.get("CV_LATE_FOUL_STATE", "0").strip().lower() in ("1", "true", "yes")
)

# ---------------------------------------------------------------------------
# Constants / clock semantics
# ---------------------------------------------------------------------------
REG_PERIOD_LEN = 720          # seconds in a regulation period (12 min)
OT_PERIOD_LEN = 300           # seconds in an overtime period (5 min)
REG_GAME_LEN_SEC = 4 * REG_PERIOD_LEN  # 2880 = 48 min

# NBA EVENTMSGTYPE codes used (verified empirically, SPEC 1.1).
EVT_MADE_FG = 1
EVT_MISS_FG = 2
EVT_FREE_THROW = 3
EVT_REBOUND = 4
EVT_TURNOVER = 5
EVT_FOUL = 6
EVT_SUB = 8
EVT_END_PERIOD = 13

# Regex helpers over the human ``event_desc`` text.
_RE_PTS = re.compile(r"\((\d+)\s*PTS\)")            # running player point total
_RE_AST = re.compile(r"\((?:[A-Za-z'.\- ]+?)\s+(\d+)\s*AST\)")  # assister's running AST
_RE_STL = re.compile(r"\((\d+)\s*STL\)")
_RE_BLK = re.compile(r"\((\d+)\s*BLK\)")
_RE_REB_SPLIT = re.compile(r"\(Off:(\d+)\s*Def:(\d+)\)")
_RE_PF = re.compile(r"\(P(\d+)\.T(\d+)\)")           # player PF . team PF
_RE_SUB = re.compile(r"SUB:\s*(.+?)\s+FOR\s+(.+?)\s*$")
_RE_SHOTDIST = re.compile(r"(\d+)'")                 # weak shot distance from desc

GAME_STATE_FIELDS = [
    "game_id", "event_idx", "period",
    "elapsed_sec_in_period", "game_elapsed_sec", "game_remaining_sec",
    "played_share",
    "home_team", "away_team",
    "home_score", "away_score", "score_margin",   # margin = home - away
    "possession_team",                            # 'home'/'away'/'' (best-effort)
    "pace_poss_per_min",                          # possessions-so-far / minutes-so-far
    # team four-factors so far (home/away)
    "home_fga", "home_fgm", "home_fg3a", "home_fg3m", "home_fta", "home_ftm",
    "home_oreb", "home_dreb", "home_tov", "home_poss",
    "away_fga", "away_fgm", "away_fg3a", "away_fg3m", "away_fta", "away_ftm",
    "away_oreb", "away_dreb", "away_tov", "away_poss",
    "home_efg", "home_tov_pct", "home_oreb_pct", "home_ft_rate",
    "away_efg", "away_tov_pct", "away_oreb_pct", "away_ft_rate",
]

# Additional POSSESSION / PACE-STATE columns (SPEC 4 momentum + pace). These let
# the projection update BETWEEN scoring events (toward true per-second). All are
# leak-free: each value at event E is a pure function of events <= E in THIS game
# plus (optionally) caller-supplied PRIOR-form season pace (games strictly before
# this game's date), which is a game-constant injected once, not future state.
PACE_STATE_FIELDS = [
    # discrete possession counts (one increment per change of possession)
    "home_poss_count", "away_poss_count", "total_poss_count",
    # tempo so-far
    "sec_per_poss_so_far",          # game_elapsed_sec / total_poss_count
    "poss_per_48_so_far",           # total_poss_count scaled to 48 min
    # time since the last made field goal (drives between-event updates)
    "sec_since_last_fg",            # game_sec - game_sec(last made FG); 0 at event
    "sec_since_last_score",         # game_sec - game_sec(last point scored)
    "sec_since_last_home_fg", "sec_since_last_away_fg",
    # pace vs both teams' season (PRIOR-form) pace -- 0.0 if prior not supplied
    "home_prior_pace", "away_prior_pace",
    "pace_vs_prior_ratio",          # (poss_per_48_so_far) / mean(prior pace)
    # run-state: signed (home POV) point margin over the last 10 SCORING events
    "run_last10_margin",            # home_pts - away_pts over last <=10 score events
    "run_last5_margin",
    # bonus / foul-state per team for the CURRENT period (from "(Pk.Tn)" desc)
    "home_team_fouls_period", "away_team_fouls_period",
    "home_in_bonus", "away_in_bonus",   # 1 if team fouls in period >= BONUS_FOULS
    # continuous expected possessions remaining (time + pace), the toward-second
    # signal: how many possessions are left to be played.
    "exp_poss_remaining",           # game_remaining_sec / sec_per_poss_so_far
    "exp_home_poss_remaining", "exp_away_poss_remaining",
]

# Number of team fouls in a period that puts the OPPONENT in the bonus (NBA: 5).
BONUS_FOULS = 5
# How many of the most recent SCORING events define the "run" window.
RUN_WINDOW_LONG = 10
RUN_WINDOW_SHORT = 5

PLAYER_STATE_FIELDS = [
    "game_id", "event_idx", "period",
    "game_elapsed_sec", "game_remaining_sec",
    "team_abbrev", "side", "last_name", "player_id",
    "on_court",
    "min_so_far",                                  # approximate, from sub intervals
    "pts", "reb", "oreb", "dreb", "ast", "fg3m", "stl", "blk", "tov", "pf",
    "fga", "fgm",
]


# ---------------------------------------------------------------------------
# Canonical event normalizer (historical schema)
# ---------------------------------------------------------------------------
def normalize_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one HISTORICAL pbp event into a canonical dict.

    Historical events carry: period, game_clock_sec (ELAPSED), event_type,
    event_desc, player_name (LAST NAME / for subs = player OUT), team_abbrev,
    score ("L-R"), score_margin. We keep them and add nothing that requires
    future info.

    When CV_PBP_QUALIFIERS is ON AND the raw dict already carries first-class
    qualifier fields (promoted by pbp_poller._event_from_play on live events),
    those fields are forwarded so the accumulation loop can use them.  For
    historical events that lack these keys the additions are absent (None /
    empty list), which is the correct default and preserves byte-identity when
    the flag is OFF.
    """
    period = int(raw.get("period", 1))
    elapsed = int(raw.get("game_clock_sec", 0) or 0)
    period_len = REG_PERIOD_LEN if period <= 4 else OT_PERIOD_LEN
    elapsed = max(0, min(elapsed, period_len))
    ev: Dict[str, Any] = {
        "period": period,
        "elapsed_sec_in_period": elapsed,
        "period_len": period_len,
        "event_type": int(raw.get("event_type", 0) or 0),
        "event_desc": raw.get("event_desc", "") or "",
        "player_name": (raw.get("player_name", "") or "").strip(),
        "team_abbrev": (raw.get("team_abbrev", "") or "").strip(),
        "score": raw.get("score", "") or "",
        "score_margin": raw.get("score_margin", "") or "",
    }
    # CV_PBP_QUALIFIERS: forward first-class qualifier fields when present.
    # These are absent from historical PBP (no-op for the historical path).
    # Byte-identical when flag is OFF because the branch is never entered.
    if _CV_PBP_QUALIFIERS:
        ev["sub_type"] = raw.get("sub_type", "")
        ev["qualifiers"] = raw.get("qualifiers") or []
        ev["offensive_foul"] = bool(raw.get("offensive_foul", False))
        ev["technical"] = bool(raw.get("technical", False))
        ev["flagrant"] = bool(raw.get("flagrant", False))
        ev["and_1"] = bool(raw.get("and_1", False))
        ev["fastbreak"] = bool(raw.get("fastbreak", False))
        ev["ejection"] = bool(raw.get("ejection", False))
        ev["in_penalty"] = bool(raw.get("in_penalty", False))
    return ev


def _game_elapsed_sec(period: int, elapsed_in_period: int) -> int:
    """Absolute game-elapsed seconds. Regulation periods are 720s; OT 300s."""
    if period <= 4:
        return REG_PERIOD_LEN * (period - 1) + elapsed_in_period
    return REG_GAME_LEN_SEC + OT_PERIOD_LEN * (period - 5) + elapsed_in_period


def _game_total_sec(max_period: int) -> int:
    """Total scheduled game length given the max period reached (handles OT)."""
    if max_period <= 4:
        return REG_GAME_LEN_SEC
    return REG_GAME_LEN_SEC + OT_PERIOD_LEN * (max_period - 4)


# ---------------------------------------------------------------------------
# PBP loading
# ---------------------------------------------------------------------------
def load_pbp_events(game_id: str, pbp_dir: str = os.path.join("data", "nba")) -> List[Dict[str, Any]]:
    """Load and concatenate all period files for a game, in event order.

    Returns the RAW event dicts (period 1..N concatenated). Periods are
    concatenated in ascending order; within a file events are already ordered by
    ascending elapsed clock.
    """
    events: List[Dict[str, Any]] = []
    for period in range(1, 12):  # up to many OTs; stop at first missing
        path = os.path.join(pbp_dir, f"pbp_{game_id}_p{period}.json")
        if not os.path.exists(path):
            break
        with open(path, "r", encoding="utf-8") as fh:
            chunk = json.load(fh)
        if isinstance(chunk, list):
            events.extend(chunk)
    return events


# ---------------------------------------------------------------------------
# Per-player running accumulator
# ---------------------------------------------------------------------------
@dataclass
class _PlayerState:
    team_abbrev: str
    last_name: str
    pts: int = 0
    oreb: int = 0
    dreb: int = 0
    ast: int = 0
    fg3m: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0
    pf: int = 0
    fga: int = 0
    fgm: int = 0
    on_court: bool = False
    # minutes tracking: when did this player last go on court (game_elapsed_sec)
    _on_since: Optional[int] = None
    sec_played: float = 0.0

    @property
    def reb(self) -> int:
        return self.oreb + self.dreb

    def go_on(self, game_sec: int) -> None:
        if not self.on_court:
            self.on_court = True
            self._on_since = game_sec

    def go_off(self, game_sec: int) -> None:
        if self.on_court and self._on_since is not None:
            self.sec_played += max(0, game_sec - self._on_since)
        self.on_court = False
        self._on_since = None

    def minutes_now(self, game_sec: int) -> float:
        extra = 0.0
        if self.on_court and self._on_since is not None:
            extra = max(0, game_sec - self._on_since)
        return (self.sec_played + extra) / 60.0


# ---------------------------------------------------------------------------
# Orientation resolver
# ---------------------------------------------------------------------------
def resolve_orientation(
    events: Iterable[Dict[str, Any]],
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
) -> Dict[str, Any]:
    """Determine which side of the "L-R" score string each team occupies.

    The score string is "{left}-{right}" with the LEFT number tracking the team
    that scored the game's first basket. We detect, for the first scoring event,
    which side incremented; the acting team owns that side. Then map side ->
    home/away using the provided tricodes (from season_games).

    Returns dict with keys: left_team, right_team, home_side ('left'/'right'),
    and whether resolution succeeded.

    NOTE: this scans the full event list, which is fine -- orientation is a
    GAME-CONSTANT (resolved once at load) not a per-event feature, so it does not
    leak future per-event state into any row. Every row uses the SAME orientation.
    """
    prev_l, prev_r = 0, 0
    left_team: Optional[str] = None
    for raw in events:
        ev = normalize_event(raw)
        sc = ev["score"]
        if "-" not in sc:
            continue
        try:
            l, r = sc.split("-")
            l, r = int(l), int(r)
        except (ValueError, TypeError):
            continue
        if (l > prev_l or r > prev_r) and ev["team_abbrev"]:
            if l > prev_l:
                left_team = ev["team_abbrev"]
            elif r > prev_r:
                # acting team owns the right side
                left_team = None  # we know right team; left is the other
                right_team = ev["team_abbrev"]
                # infer left from home/away if available
                if home_team and away_team:
                    left_team = home_team if right_team == away_team else away_team
                out = {
                    "left_team": left_team,
                    "right_team": right_team,
                    "home_side": "left" if (home_team and left_team == home_team) else "right",
                    "resolved": bool(home_team and away_team),
                }
                return out
            break
        prev_l, prev_r = l, r

    if left_team is not None:
        right_team = None
        if home_team and away_team:
            right_team = home_team if left_team == away_team else away_team
        return {
            "left_team": left_team,
            "right_team": right_team,
            "home_side": "left" if (home_team and left_team == home_team) else "right",
            "resolved": bool(home_team and away_team),
        }
    # Fallback: assume left=home (common but NOT guaranteed); flag unresolved.
    return {
        "left_team": home_team,
        "right_team": away_team,
        "home_side": "left",
        "resolved": False,
    }


def _side_for_team(team: str, orient: Dict[str, Any]) -> str:
    """Map a team tricode -> 'home'/'away' given resolved orientation."""
    left = orient.get("left_team")
    home_side = orient.get("home_side", "left")
    if team and left:
        is_left = (team == left)
        if home_side == "left":
            return "home" if is_left else "away"
        return "away" if is_left else "home"
    return ""


# ---------------------------------------------------------------------------
# Core: featurize a full historical game event-by-event (leak-free)
# ---------------------------------------------------------------------------
def featurize_game(
    events: List[Dict[str, Any]],
    game_id: str,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    *,
    player_id_resolver: Optional[Callable[[str, str], Optional[Any]]] = None,
    emit_players: bool = True,
    prior_pace: Optional[Dict[str, float]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Replay events in order, emitting leak-free state rows AFTER each event.

    The state row for event index i reflects the cumulative state INCLUDING
    event i and NOTHING after it. Time is monotonically non-decreasing.

    Args:
        events: raw historical pbp events (concatenated periods, in order).
        game_id: token for tagging rows.
        home_team / away_team: tricodes from season_games (for orientation +
            side mapping). Optional but recommended; orientation degrades to a
            left=home assumption (flagged) without them.
        player_id_resolver: optional callable (team_abbrev, last_name) ->
            player_id; attaches a global player_id to per-player rows. This is
            the ONLY place a roster map enters and it is a pure function of
            (team, last_name) -- no game state -- so it cannot leak.
        emit_players: whether to emit per-player rows (can be large).
        prior_pace: optional {"home": poss_per_48, "away": poss_per_48} from the
            two teams' games STRICTLY BEFORE this game's date (a leak-free
            game-constant the caller computes). Used only for the
            pace-vs-prior-pace ratio feature; absent -> ratio feature is 0.

    Returns:
        {"game": [game_state_rows], "players": [player_state_rows]}
    """
    orient = resolve_orientation(events, home_team, away_team)

    # Running team aggregates.
    team_agg = {
        "home": dict(fga=0, fgm=0, fg3a=0, fg3m=0, fta=0, ftm=0,
                     oreb=0, dreb=0, tov=0, poss=0),
        "away": dict(fga=0, fgm=0, fg3a=0, fg3m=0, fta=0, ftm=0,
                     oreb=0, dreb=0, tov=0, poss=0),
    }
    players: Dict[Tuple[str, str], _PlayerState] = {}
    home_score = away_score = 0
    last_possession_side = ""

    # --- POSSESSION / PACE-STATE running trackers (all leak-free) ------------
    # Discrete possession counts: increment the acting side's count when
    # possession demonstrably ends (made FG, defensive rebound flips it, turnover,
    # last FT of a trip). We approximate with a "possession owner" that flips on
    # change-of-possession events; each flip credits the side that JUST had it.
    poss_count = {"home": 0, "away": 0}
    poss_owner = ""               # side currently with the ball ('' until first)
    # last made-FG / last-score timing (absolute game seconds)
    last_fg_sec: Optional[int] = None
    last_score_sec: Optional[int] = None
    last_home_fg_sec: Optional[int] = None
    last_away_fg_sec: Optional[int] = None
    # scoring-event history for run-state: list of (home_delta, away_delta)
    score_event_deltas: List[Tuple[int, int]] = []
    # team fouls in the CURRENT period (reset on period change). Tracked from the
    # running "(Pk.Tn)" team-foul count in the desc when present, else incremented.
    team_fouls_period = {"home": 0, "away": 0}
    cur_period_seen = None
    # prior-form season pace (poss/48) supplied by caller; 0.0 if unknown.
    home_prior_pace = float(prior_pace.get("home", 0.0)) if prior_pace else 0.0
    away_prior_pace = float(prior_pace.get("away", 0.0)) if prior_pace else 0.0

    def _credit_possession(side: str) -> None:
        """Credit one possession to ``side`` (the side that just had the ball)."""
        if side in poss_count:
            poss_count[side] += 1

    max_period = 1
    for raw in events:
        max_period = max(max_period, int(raw.get("period", 1) or 1))

    game_rows: List[Dict[str, Any]] = []
    player_rows: List[Dict[str, Any]] = []

    def _pstate(team: str, name: str) -> _PlayerState:
        key = (team, name)
        if key not in players:
            players[key] = _PlayerState(team_abbrev=team, last_name=name)
        return players[key]

    prev_game_sec = -1
    for idx, raw in enumerate(events):
        ev = normalize_event(raw)
        period = ev["period"]
        elapsed = ev["elapsed_sec_in_period"]
        game_sec = _game_elapsed_sec(period, elapsed)
        # enforce non-decreasing time (defensive against any out-of-order rows)
        game_sec = max(game_sec, prev_game_sec) if prev_game_sec >= 0 else game_sec
        prev_game_sec = game_sec

        etype = ev["event_type"]
        desc = ev["event_desc"]
        team = ev["team_abbrev"]
        side = _side_for_team(team, orient) if team else ""
        name = ev["player_name"]

        # --- period foul-state reset on entering a new period (leak-free: only
        # depends on this event's period vs the previous event's) ---
        if cur_period_seen is None:
            cur_period_seen = period
        elif period != cur_period_seen:
            team_fouls_period = {"home": 0, "away": 0}
            cur_period_seen = period

        # --- score (parse running "L-R", map to home/away) + scoring delta ---
        prev_home_score, prev_away_score = home_score, away_score
        if "-" in ev["score"]:
            try:
                l, r = ev["score"].split("-")
                l, r = int(l), int(r)
                if orient.get("home_side", "left") == "left":
                    home_score, away_score = l, r
                else:
                    home_score, away_score = r, l
            except (ValueError, TypeError):
                pass
        d_home = home_score - prev_home_score
        d_away = away_score - prev_away_score
        if d_home > 0 or d_away > 0:
            # a scoring event: record for run-state and last-score timing
            score_event_deltas.append((max(0, d_home), max(0, d_away)))
            last_score_sec = game_sec

        # --- player resolution helper ---
        def _touch_player(t: str, n: str) -> Optional[_PlayerState]:
            if not t or not n:
                return None
            return _pstate(t, n)

        # --- per-event accumulation ---
        if etype == EVT_MADE_FG:
            ps = _touch_player(team, name)
            if ps is not None:
                ps.fga += 1
                ps.fgm += 1
                m = _RE_PTS.search(desc)
                if m:
                    ps.pts = int(m.group(1))  # running total (authoritative)
                if "3PT" in desc:
                    ps.fg3m += 1
                am = _RE_AST.search(desc)
                if am:
                    # assister last name precedes "N AST"; credit to that player
                    assist_name = _extract_assist_name(desc)
                    if assist_name:
                        aps = _pstate(team, assist_name)
                        aps.ast = int(am.group(1))
            if side in team_agg:
                team_agg[side]["fga"] += 1
                team_agg[side]["fgm"] += 1
                if "3PT" in desc:
                    team_agg[side]["fg3a"] += 1
                    team_agg[side]["fg3m"] += 1
            last_possession_side = side
            # pace-state: a made FG ends the possession (credit shooter's side)
            _credit_possession(side)
            poss_owner = _other(side) if side in ("home", "away") else poss_owner
            last_fg_sec = game_sec
            last_score_sec = game_sec
            if side == "home":
                last_home_fg_sec = game_sec
            elif side == "away":
                last_away_fg_sec = game_sec

        elif etype == EVT_MISS_FG:
            ps = _touch_player(team, name)
            if ps is not None:
                ps.fga += 1
            if side in team_agg:
                team_agg[side]["fga"] += 1
                if "3PT" in desc:
                    team_agg[side]["fg3a"] += 1
            last_possession_side = side

        elif etype == EVT_FREE_THROW:
            ps = _touch_player(team, name)
            made = "MISS" not in desc
            if ps is not None:
                ps_pts = _RE_PTS.search(desc)
                if made and ps_pts:
                    ps.pts = int(ps_pts.group(1))
            if side in team_agg:
                team_agg[side]["fta"] += 1
                if made:
                    team_agg[side]["ftm"] += 1
            last_possession_side = side
            if made:
                last_score_sec = game_sec
            # pace-state: the LAST FT of a trip ends the possession. Desc reads
            # "Free Throw k of n"; credit when k == n (and not a technical 1-of-1
            # that doesn't change possession -- treat any "n of n" as poss end).
            ftm = re.search(r"Free Throw (\d+) of (\d+)", desc)
            if ftm and ftm.group(1) == ftm.group(2):
                _credit_possession(side)
                poss_owner = _other(side) if side in ("home", "away") else poss_owner

        elif etype == EVT_REBOUND:
            ps = _touch_player(team, name)
            rm = _RE_REB_SPLIT.search(desc)
            is_team_rebound = "TEAM" in desc.upper() or not name
            if rm:
                o, d = int(rm.group(1)), int(rm.group(2))
                if ps is not None and not is_team_rebound:
                    ps.oreb = o
                    ps.dreb = d
                # offensive vs defensive at team level: infer from increment
                # (use the rebounding team's side)
            if side in team_agg and not is_team_rebound and rm:
                # team-level: recompute from per-player sums would be ideal but
                # we approximate by counting; offensive reb continues possession
                pass
            # team four-factor OREB/DREB counts: count this rebound
            if side in team_agg and rm:
                # determine off vs def by whether the missed shot was by same side
                if last_possession_side == side:
                    team_agg[side]["oreb"] += 1
                else:
                    team_agg[side]["dreb"] += 1
                    # pace-state: a DEFENSIVE rebound ends the prior possession;
                    # credit the side that just shot (the OTHER side) & flip ball.
                    shooter = _other(side)
                    _credit_possession(shooter)
                    poss_owner = side

        elif etype == EVT_TURNOVER:
            ps = _touch_player(team, name)
            if ps is not None:
                ps.tov += 1
            if side in team_agg:
                team_agg[side]["tov"] += 1
            last_possession_side = side
            # pace-state: a turnover ends the possession (credit committing side)
            _credit_possession(side)
            poss_owner = _other(side) if side in ("home", "away") else poss_owner

        elif etype == EVT_FOUL:
            ps = _touch_player(team, name)
            pm = _RE_PF.search(desc)
            if ps is not None and pm:
                ps.pf = int(pm.group(1))
            elif ps is not None:
                ps.pf += 1
            # CV_PBP_QUALIFIERS: when qualifier fields are present, determine
            # whether this foul type accrues to the team-foul count for bonus
            # purposes.  NBA rules: offensive fouls and technical fouls do NOT
            # put the opponent in the bonus (they do not count as team fouls for
            # the fouled team's bonus tracking).  Flagrant fouls DO count.
            # When the flag is OFF (or qualifier fields are absent / all False),
            # the logic falls through to the existing running-Tn / +1 path —
            # byte-identical to the pre-qualifier behaviour.
            _q_is_offensive = _CV_PBP_QUALIFIERS and bool(ev.get("offensive_foul"))
            _q_is_technical = _CV_PBP_QUALIFIERS and bool(ev.get("technical"))
            _q_has_qualifiers = _CV_PBP_QUALIFIERS and bool(
                ev.get("sub_type") or ev.get("qualifiers")
            )
            # pace-state: team fouls THIS period. Prefer the authoritative running
            # team-foul count "(Pk.Tn)" -> Tn; else increment. Only count personal
            # fouls that accrue to the penalty (skip offensive/technical noise is
            # hard from desc alone, so we use the running Tn when present).
            # When qualifiers are present and this is an offensive/technical foul,
            # skip the team-foul increment (does not advance opponent toward bonus).
            if side in team_fouls_period:
                if _q_is_offensive or _q_is_technical:
                    # Offensive/technical: no team-foul increment for bonus.
                    pass
                elif pm:
                    team_fouls_period[side] = max(team_fouls_period[side],
                                                  int(pm.group(2)))
                else:
                    team_fouls_period[side] += 1

        elif etype == EVT_SUB:
            # player_name = player going OUT; desc "SUB: {in} FOR {out}"
            sm = _RE_SUB.search(desc)
            if sm:
                in_name = sm.group(1).strip()
                out_name = sm.group(2).strip()
                if team:
                    _pstate(team, out_name).go_off(game_sec)
                    _pstate(team, in_name).go_on(game_sec)

        elif etype == 0:
            # mixed: STEAL / BLOCK lines carry running per-player totals.
            sm = _RE_STL.search(desc)
            bm = _RE_BLK.search(desc)
            if (sm or bm) and team and name:
                ps = _pstate(team, name)
                if sm:
                    ps.stl = int(sm.group(1))
                if bm:
                    ps.blk = int(bm.group(1))

        # mark acting player on-court (anyone who does something is on court)
        if name and team and etype not in (EVT_SUB, EVT_END_PERIOD):
            ps = _pstate(team, name)
            ps.go_on(game_sec)

        # --- emit GAME state row (state AFTER this event) ---
        game_total = _game_total_sec(max_period)
        game_rem = max(0, game_total - game_sec)
        played_share = game_sec / game_total if game_total else 0.0
        elapsed_min = game_sec / 60.0
        poss_total = team_agg["home"]["poss"] + team_agg["away"]["poss"]

        def _ff(s: str) -> Dict[str, float]:
            a = team_agg[s]
            fga = a["fga"]
            efg = (a["fgm"] + 0.5 * a["fg3m"]) / fga if fga else 0.0
            # possessions estimate (so-far): FGA + 0.44*FTA + TOV - OREB
            poss = a["fga"] + 0.44 * a["fta"] + a["tov"] - a["oreb"]
            denom = poss if poss > 0 else 0.0
            tov_pct = a["tov"] / denom if denom else 0.0
            oreb_pct = a["oreb"] / (a["oreb"] + team_agg[_other(s)]["dreb"]) \
                if (a["oreb"] + team_agg[_other(s)]["dreb"]) else 0.0
            ft_rate = a["fta"] / fga if fga else 0.0
            return dict(efg=efg, tov_pct=tov_pct, oreb_pct=oreb_pct,
                        ft_rate=ft_rate, poss=poss)

        ff_home = _ff("home")
        ff_away = _ff("away")
        total_poss = ff_home["poss"] + ff_away["poss"]
        pace = (total_poss / elapsed_min) if elapsed_min > 0 else 0.0

        grow = {
            "game_id": game_id,
            "event_idx": idx,
            "period": period,
            "elapsed_sec_in_period": elapsed,
            "game_elapsed_sec": game_sec,
            "game_remaining_sec": game_rem,
            "played_share": played_share,
            "home_team": home_team or orient.get("left_team"),
            "away_team": away_team or orient.get("right_team"),
            "home_score": home_score,
            "away_score": away_score,
            "score_margin": home_score - away_score,
            "possession_team": last_possession_side,
            "pace_poss_per_min": pace,
        }
        for s, prefix in (("home", "home"), ("away", "away")):
            a = team_agg[s]
            for k in ("fga", "fgm", "fg3a", "fg3m", "fta", "ftm",
                      "oreb", "dreb", "tov"):
                grow[f"{prefix}_{k}"] = a[k]
        grow["home_poss"] = ff_home["poss"]
        grow["away_poss"] = ff_away["poss"]
        grow["home_efg"] = ff_home["efg"]
        grow["home_tov_pct"] = ff_home["tov_pct"]
        grow["home_oreb_pct"] = ff_home["oreb_pct"]
        grow["home_ft_rate"] = ff_home["ft_rate"]
        grow["away_efg"] = ff_away["efg"]
        grow["away_tov_pct"] = ff_away["tov_pct"]
        grow["away_oreb_pct"] = ff_away["oreb_pct"]
        grow["away_ft_rate"] = ff_away["ft_rate"]

        # --- POSSESSION / PACE-STATE fields (leak-free; events <= E only) -----
        pace_fields = _compute_pace_state(
            game_sec=game_sec,
            game_rem=game_rem,
            poss_count=poss_count,
            last_fg_sec=last_fg_sec,
            last_score_sec=last_score_sec,
            last_home_fg_sec=last_home_fg_sec,
            last_away_fg_sec=last_away_fg_sec,
            score_event_deltas=score_event_deltas,
            team_fouls_period=team_fouls_period,
            home_prior_pace=home_prior_pace,
            away_prior_pace=away_prior_pace,
        )
        grow.update(pace_fields)
        game_rows.append(grow)

        # --- emit PLAYER state rows (state AFTER this event) ---
        if emit_players:
            for (pteam, pname), ps in players.items():
                pside = _side_for_team(pteam, orient) if pteam else ""
                pid = None
                if player_id_resolver is not None:
                    try:
                        pid = player_id_resolver(pteam, pname)
                    except Exception:
                        pid = None
                player_rows.append({
                    "game_id": game_id,
                    "event_idx": idx,
                    "period": period,
                    "game_elapsed_sec": game_sec,
                    "game_remaining_sec": game_rem,
                    "team_abbrev": pteam,
                    "side": pside,
                    "last_name": pname,
                    "player_id": pid,
                    "on_court": ps.on_court,
                    "min_so_far": round(ps.minutes_now(game_sec), 3),
                    "pts": ps.pts,
                    "reb": ps.reb,
                    "oreb": ps.oreb,
                    "dreb": ps.dreb,
                    "ast": ps.ast,
                    "fg3m": ps.fg3m,
                    "stl": ps.stl,
                    "blk": ps.blk,
                    "tov": ps.tov,
                    "pf": ps.pf,
                    "fga": ps.fga,
                    "fgm": ps.fgm,
                })

    return {"game": game_rows, "players": player_rows, "orientation": orient}


def _other(side: str) -> str:
    return "away" if side == "home" else "home"


def _extract_assist_name(desc: str) -> Optional[str]:
    """Pull the assister's last name from a made-FG desc.

    Example: "Tatum 24' 3PT Jump Shot (3 PTS) (Smart 1 AST)" -> "Smart".
    """
    m = re.search(r"\(([A-Za-z'.\- ]+?)\s+\d+\s*AST\)", desc)
    if m:
        return m.group(1).strip()
    return None


def _compute_pace_state(
    *,
    game_sec: int,
    game_rem: int,
    poss_count: Dict[str, int],
    last_fg_sec: Optional[int],
    last_score_sec: Optional[int],
    last_home_fg_sec: Optional[int],
    last_away_fg_sec: Optional[int],
    score_event_deltas: List[Tuple[int, int]],
    team_fouls_period: Dict[str, int],
    home_prior_pace: float,
    away_prior_pace: float,
) -> Dict[str, Any]:
    """Derive the POSSESSION / PACE-STATE feature columns from running trackers.

    Pure function of the CURRENT accumulated trackers (all of which were built
    from events <= E), so it cannot leak future state. Factored out so the same
    math serves both the per-event emission and the between-event ``at_time``
    interpolation (toward true per-second updates).
    """
    total_poss = poss_count.get("home", 0) + poss_count.get("away", 0)
    elapsed_min = game_sec / 60.0 if game_sec else 0.0
    sec_per_poss = (game_sec / total_poss) if total_poss > 0 else 0.0
    # Conventional "pace" = possessions PER TEAM per 48 min (~96-100 in the NBA).
    # total_poss counts BOTH teams, so divide by 2 to match season-pace scale
    # (and the caller-supplied prior_pace, which is per-team).
    per_team_poss = total_poss / 2.0
    poss_per_48 = (per_team_poss / elapsed_min * 48.0) if elapsed_min > 0 else 0.0
    # CV_LATE_FOUL_STATE: compute composite late_foul_active indicator.
    # 1 when all hold: (a) <=3 min remaining, (b) |score_margin|>=1, (c) opp
    # is in the bonus (trailing team has committed 5+ team fouls in period).
    # Uses run-time scores from the score_event_deltas list to derive margin;
    # only emitted when _CV_LATE_FOUL_STATE flag is ON.  Byte-identical when OFF.
    if _CV_LATE_FOUL_STATE:
        _rem_sec = game_rem
        _home_in_bonus = 1 if team_fouls_period.get("home", 0) >= BONUS_FOULS else 0
        _away_in_bonus = 1 if team_fouls_period.get("away", 0) >= BONUS_FOULS else 0
        # score_event_deltas: list of (home_pts, away_pts) per scoring event
        _cum_h = sum(h for h, _ in score_event_deltas)
        _cum_a = sum(a for _, a in score_event_deltas)
        _margin = _cum_h - _cum_a  # home - away; neg = home trailing
        _abs_margin = abs(_margin)
        # late foul active: meaningful deficit, low clock, trailing team in penalty.
        # featurizer convention: home_in_bonus=1 means HOME has 5+ team fouls
        # (HOME is in the penalty → any HOME foul → AWAY player shoots FTs).
        # Trailing HOME intentionally fouls → needs home_in_bonus=1.
        # Trailing AWAY intentionally fouls → needs away_in_bonus=1.
        _lfa = (
            _rem_sec <= 180
            and _abs_margin >= 1
            and (
                (_margin < 0 and _home_in_bonus == 1)   # home trailing, home in penalty
                or (_margin > 0 and _away_in_bonus == 1)  # away trailing, away in penalty
            )
        )

    # time-since features (default to current game_sec if nothing yet -> "long")
    def _since(t: Optional[int]) -> int:
        return int(game_sec - t) if t is not None else int(game_sec)

    # run-state: signed home-POV margin over the last N scoring events
    def _run(n: int) -> int:
        window = score_event_deltas[-n:] if n > 0 else score_event_deltas
        return int(sum(h for h, _ in window) - sum(a for _, a in window))

    mean_prior = 0.0
    n_prior = 0
    for p in (home_prior_pace, away_prior_pace):
        if p > 0:
            mean_prior += p
            n_prior += 1
    mean_prior = (mean_prior / n_prior) if n_prior else 0.0
    pace_vs_prior = (poss_per_48 / mean_prior) if mean_prior > 0 else 0.0

    # expected possessions remaining from time + tempo so-far
    exp_poss_rem = (game_rem / sec_per_poss) if sec_per_poss > 0 else 0.0

    home_bonus = 1 if team_fouls_period.get("home", 0) >= BONUS_FOULS else 0
    away_bonus = 1 if team_fouls_period.get("away", 0) >= BONUS_FOULS else 0

    out = {
        "home_poss_count": poss_count.get("home", 0),
        "away_poss_count": poss_count.get("away", 0),
        "total_poss_count": total_poss,
        "sec_per_poss_so_far": round(sec_per_poss, 4),
        "poss_per_48_so_far": round(poss_per_48, 4),
        "sec_since_last_fg": _since(last_fg_sec),
        "sec_since_last_score": _since(last_score_sec),
        "sec_since_last_home_fg": _since(last_home_fg_sec),
        "sec_since_last_away_fg": _since(last_away_fg_sec),
        "home_prior_pace": round(home_prior_pace, 4),
        "away_prior_pace": round(away_prior_pace, 4),
        "pace_vs_prior_ratio": round(pace_vs_prior, 4),
        "run_last10_margin": _run(RUN_WINDOW_LONG),
        "run_last5_margin": _run(RUN_WINDOW_SHORT),
        "home_team_fouls_period": team_fouls_period.get("home", 0),
        "away_team_fouls_period": team_fouls_period.get("away", 0),
        "home_in_bonus": home_bonus,
        "away_in_bonus": away_bonus,
        "exp_poss_remaining": round(exp_poss_rem, 4),
        # split remaining possessions ~evenly (alternating possession model)
        "exp_home_poss_remaining": round(exp_poss_rem / 2.0, 4),
        "exp_away_poss_remaining": round(exp_poss_rem / 2.0, 4),
    }
    # CV_LATE_FOUL_STATE: additive key — only emitted when flag ON.
    if _CV_LATE_FOUL_STATE:
        out["late_foul_active"] = int(_lfa)
    return out


def advance_to_time(last_game_row: Dict[str, Any], target_game_sec: int,
                    game_total_sec: int = REG_GAME_LEN_SEC) -> Dict[str, Any]:
    """Roll a per-event game-state row forward to an arbitrary clock moment.

    Between PBP events nothing changes except the clock ticking; this is the
    deterministic time-decay that turns the per-EVENT featurizer into a
    per-SECOND one without inventing new event information. Given the last event
    row (state at event E) and a later wall-clock ``target_game_sec`` (still
    BEFORE the next event, so leak-free), it returns a COPY with only the
    clock-derived + time-since + expected-possessions-remaining fields advanced.
    All count/score/box fields are carried forward UNCHANGED (no new events
    occurred), so this cannot leak future info.

    This is the honest "per-second" update: it does NOT fabricate scoring; it
    only ages the clock and recomputes time-decayed quantities.
    """
    row = dict(last_game_row)
    last_sec = int(last_game_row.get("game_elapsed_sec", 0) or 0)
    target_game_sec = max(last_sec, int(target_game_sec))
    game_rem = max(0, game_total_sec - target_game_sec)
    delta = target_game_sec - last_sec

    row["game_elapsed_sec"] = target_game_sec
    row["game_remaining_sec"] = game_rem
    row["played_share"] = (target_game_sec / game_total_sec) if game_total_sec else 0.0

    # advance time-since clocks by the elapsed wall-time delta
    for k in ("sec_since_last_fg", "sec_since_last_score",
              "sec_since_last_home_fg", "sec_since_last_away_fg"):
        if k in row:
            row[k] = int(row[k]) + delta

    # recompute tempo-derived fields against the advanced clock (counts unchanged)
    total_poss = int(last_game_row.get("total_poss_count", 0) or 0)
    sec_per_poss = (target_game_sec / total_poss) if total_poss > 0 else 0.0
    row["sec_per_poss_so_far"] = round(sec_per_poss, 4)
    exp_poss_rem = (game_rem / sec_per_poss) if sec_per_poss > 0 else 0.0
    row["exp_poss_remaining"] = round(exp_poss_rem, 4)
    row["exp_home_poss_remaining"] = round(exp_poss_rem / 2.0, 4)
    row["exp_away_poss_remaining"] = round(exp_poss_rem / 2.0, 4)
    return row


# ---------------------------------------------------------------------------
# LIVE single-event / single-snapshot featurizer
# ---------------------------------------------------------------------------
def featurize_live_snapshot(snap: Dict[str, Any]) -> Dict[str, Any]:
    """Produce ONE game-state row from a canonical LIVE box snapshot.

    Live snapshots (``src/data/live.py`` schema, SPEC 3.1) carry remaining clock
    ("MM:SS") and explicit home/away scores, so orientation is trivial. This
    yields a row comparable to a historical game-state row at the same moment.

    Only fields derivable WITHOUT future info are filled; four-factor counts are
    left at 0 unless present in the snapshot's per-player stats (box snapshots do
    not carry team FGA/FGM splits reliably), so this is a lighter row than the
    historical one. It exists so the offline + live paths share a row shape.
    """
    period = int(snap.get("period", 1) or 1)
    clock = snap.get("clock", "12:00") or "12:00"
    rem_in_period = _parse_clock_remaining(clock)
    period_len = REG_PERIOD_LEN if period <= 4 else OT_PERIOD_LEN
    elapsed_in_period = max(0, period_len - rem_in_period)
    game_sec = _game_elapsed_sec(period, elapsed_in_period)
    game_total = _game_total_sec(period)
    game_rem = max(0, game_total - game_sec)
    home_score = int(snap.get("home_score", 0) or 0)
    away_score = int(snap.get("away_score", 0) or 0)
    elapsed_min = game_sec / 60.0

    return {
        "game_id": snap.get("game_id"),
        "event_idx": None,
        "period": period,
        "elapsed_sec_in_period": elapsed_in_period,
        "game_elapsed_sec": game_sec,
        "game_remaining_sec": game_rem,
        "played_share": (game_sec / game_total) if game_total else 0.0,
        "home_team": snap.get("home_team"),
        "away_team": snap.get("away_team"),
        "home_score": home_score,
        "away_score": away_score,
        "score_margin": home_score - away_score,
        "possession_team": "",
        "pace_poss_per_min": 0.0,
    }


def _parse_clock_remaining(clock: str) -> int:
    """Parse a remaining-time clock. Accepts 'MM:SS' or ISO 'PT07M24.00S'."""
    if not clock:
        return 0
    clock = str(clock).strip()
    iso = re.match(r"PT0?(\d+)M([\d.]+)S", clock)
    if iso:
        return int(int(iso.group(1)) * 60 + float(iso.group(2)))
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


# ---------------------------------------------------------------------------
# HISTORICAL backfill over data/nba/pbp_*.json
# ---------------------------------------------------------------------------
_JUNK_TOKENS = {"None", "TESTGAME", "COMPLETEGAME", "atl_ind_2025", "bos_mia_2025"}


def discover_game_ids(pbp_dir: str = os.path.join("data", "nba")) -> List[str]:
    """List distinct real numeric game_ids that have pbp files (junk filtered)."""
    ids = set()
    for path in glob.glob(os.path.join(pbp_dir, "pbp_*_p*.json")):
        base = os.path.basename(path)
        m = re.match(r"pbp_(.+)_p\d+\.json$", base)
        if not m:
            continue
        tok = m.group(1)
        if tok in _JUNK_TOKENS:
            continue
        if not tok.isdigit():
            continue
        ids.add(tok)
    return sorted(ids)


def _load_team_map(nba_dir: str) -> Dict[str, Tuple[str, str]]:
    """Map game_id -> (home_team, away_team) from all season_games files."""
    out: Dict[str, Tuple[str, str]] = {}
    for path in glob.glob(os.path.join(nba_dir, "season_games_*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        rows = data.get("rows", data) if isinstance(data, dict) else data
        for r in rows:
            gid = str(r.get("game_id", ""))
            if gid:
                out[gid] = (r.get("home_team"), r.get("away_team"))
    return out


def backfill_states(
    game_ids: Optional[Iterable[str]] = None,
    *,
    pbp_dir: str = os.path.join("data", "nba"),
    emit_players: bool = True,
    player_id_resolver: Optional[Callable[[str, str], Optional[Any]]] = None,
    limit: Optional[int] = None,
    on_game: Optional[Callable[[str, Dict[str, List[Dict[str, Any]]]], None]] = None,
) -> Dict[str, Any]:
    """Backfill leak-free state rows across many historical PBP games.

    Args:
        game_ids: iterable of game_ids; defaults to all discovered ids.
        pbp_dir: directory holding pbp_*.json + season_games_*.json.
        emit_players: include per-player rows.
        player_id_resolver: optional (team, last_name) -> player_id.
        limit: cap number of games (for quick runs / tests).
        on_game: optional callback(game_id, result) invoked per game; if given,
            rows are NOT accumulated in the return value (streaming mode) to keep
            memory bounded.

    Returns:
        dict with 'n_games', 'n_game_rows', 'n_player_rows', 'failed' (list),
        and (only when on_game is None) 'games' mapping game_id -> result.
    """
    team_map = _load_team_map(pbp_dir)
    if game_ids is None:
        game_ids = discover_game_ids(pbp_dir)
    game_ids = list(game_ids)
    if limit is not None:
        game_ids = game_ids[:limit]

    n_games = 0
    n_game_rows = 0
    n_player_rows = 0
    failed: List[Tuple[str, str]] = []
    games_out: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for gid in game_ids:
        try:
            events = load_pbp_events(gid, pbp_dir)
            if not events:
                failed.append((gid, "no_events"))
                continue
            home, away = team_map.get(gid, (None, None))
            result = featurize_game(
                events, gid, home, away,
                player_id_resolver=player_id_resolver,
                emit_players=emit_players,
            )
            n_games += 1
            n_game_rows += len(result["game"])
            n_player_rows += len(result["players"])
            if on_game is not None:
                on_game(gid, result)
            else:
                games_out[gid] = result
        except Exception as exc:  # keep the backfill robust
            failed.append((gid, repr(exc)))

    summary = {
        "n_games": n_games,
        "n_game_rows": n_game_rows,
        "n_player_rows": n_player_rows,
        "failed": failed,
    }
    if on_game is None:
        summary["games"] = games_out
    return summary
