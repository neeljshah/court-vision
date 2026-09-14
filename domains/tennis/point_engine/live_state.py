"""domains.tennis.point_engine.live_state -- turn a LIVE tennis match-state
payload into the point engine's OWN canonical pre-point state
(server_id, score_bucket, set_bucket), so the SAME PointModel.prob /
simulate_match_ensemble the historical corpora feed can be conditioned on a
real in-progress match instead of only on a finished corpus.

WHY THIS IS THE HONEST SEAM: corpus.build_point_frame / corpus_2026.
build_point_frame_2026 both emit one row per point as
(server_id, returner_id, score_bucket, set_bucket, server_won) -- the PRE-point
state plus the realized label. A live feed gives the identical PRE-point state
(who serves, the point/game/set score) with the label not yet known. This module
is the third producer of that same triple: a thin reshape of a live payload, no
new model and no market. score_bucket()/set_bucket() and the tiebreak DEUCE
proxy are REUSED verbatim from corpus.py/match_sim.py -- the live path collapses
score exactly as the fit path did, so the conditioning is apples-to-apples.

SOURCE CONTRACT (Live Tennis API public v1 Match/Score, per its published
OpenAPI schema -- github.com/livetennisapi/openapi): a match dict carries
players.p1.name / players.p2.name, status (upcoming|live|completed|cancelled),
event_status (Retired|Cancelled|Walk Over|Postponed|Interrupted|null -- HOW it
ended if it did not run its course), and score with:
  sets   : [sets_won_p1, sets_won_p2]
  games  : [games_p1_per_set, games_p2_per_set]   (two per-set integer lists)
  points : [p1_point, p2_point] as tennis strings "0"/"15"/"30"/"40"/"AD",
           entries may be NULL (observed live on completed matches -- do not
           decode a null into a non-nullable string)
  server : 1|2|null   (1 -> players.p1, 2 -> players.p2)
  is_tiebreak : bool
This module NEVER fetches by itself in its tested core; `fetch_live` is an
optional stdlib-urllib convenience that the tests do not exercise.

BREAK POINT (three-valued, matching the product's own semantics): TRUE when the
RECEIVER is one point from winning the game on the opponent's serve (receiver at
AD, or receiver at 40 with server at 0/15/30); FALSE when it is a served point
that is not a break point; UNDEF (None) when there is no decidable served point
-- inside a tiebreak, when the server or a point is null, or once the match is
terminal.

TIEBREAK: raw tiebreak point digits ("1".."12"+) are NOT in SCORE_MAP; rather
than mis-collapse them, a tiebreak routes the model lookup to match_sim's
declared DEUCE proxy bucket (the same simplification play_tiebreak already uses),
and its break_point is UNDEF.

INVARIANTS: domains-only; ASCII; no src/kernel imports; no network in the tested
core; <=300 LOC.
Tests: python -m pytest domains/tennis/point_engine/test_live_state.py -q
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from domains.tennis.point_engine.corpus import SCORE_MAP, score_bucket, set_bucket
from domains.tennis.point_engine.match_sim import DEUCE_BUCKET, ProbFn

# event_status values that mean the match is OVER and has no next point.
_TERMINAL_EVENT_STATUS = {"retired", "walk over", "walkover", "cancelled", "canceled"}
# status values that mean the match is OVER.
_TERMINAL_STATUS = {"completed", "cancelled", "canceled"}


@dataclass(frozen=True)
class LiveState:
    """The point engine's canonical PRE-point state read off a live match, plus
    the derived signals a caller needs to gate on (break point, terminal)."""

    match_id: Optional[str]
    server_id: Optional[str]
    returner_id: Optional[str]
    server_pts: Optional[int]        # 0..4 (4 == 'AD'), None if undecodable
    returner_pts: Optional[int]
    score_bucket: Optional[int]      # 0..18, or None when no served point is decodable
    set_bucket: int                  # 0,1,2  (set1 / set2 / set>=3), always defined
    set_no: int                      # 1-based current set number
    is_tiebreak: bool
    break_point: Optional[bool]      # three-valued: True / False / None(UNDEF)
    status: Optional[str]
    event_status: Optional[str]
    is_live: bool                    # a next point is expected
    terminal_reason: Optional[str]   # "completed"/"retired"/"walk over"/... or None


def _name(players: Any, slot: str) -> Optional[str]:
    if not isinstance(players, dict):
        return None
    p = players.get(slot)
    if isinstance(p, dict):
        n = p.get("name")
        return str(n) if n is not None else None
    return str(p) if p is not None else None


def _point_int(points: Any, ix: int) -> Optional[int]:
    """Decode one player's in-game point string to 0..4, or None if absent/null/
    not a recognised tennis point (e.g. a raw tiebreak digit)."""
    if not isinstance(points, (list, tuple)) or ix >= len(points):
        return None
    raw = points[ix]
    if raw is None:
        return None
    return SCORE_MAP.get(str(raw))


def _current_set_no(sets: Any, games: Any, live: bool) -> int:
    """1-based current set. Prefer the number of sets that already have games
    recorded; fall back to (sets won so far)+1 while live."""
    if isinstance(games, (list, tuple)) and games and isinstance(games[0], (list, tuple)):
        n = len(games[0])
        if n >= 1:
            return n
    won = 0
    if isinstance(sets, (list, tuple)):
        for v in sets:
            try:
                won += int(v)
            except (TypeError, ValueError):
                pass
    return won + 1 if live else max(won, 1)


def _break_point(server_pts: Optional[int], returner_pts: Optional[int],
                 is_tiebreak: bool, live: bool) -> Optional[bool]:
    if not live or is_tiebreak or server_pts is None or returner_pts is None:
        return None
    # receiver at AD (4), or receiver at 40 (3) with server at 0/15/30 (<=2)
    if returner_pts == 4:
        return True
    if returner_pts == 3 and server_pts <= 2:
        return True
    return False


def live_state_from_match(match: Dict[str, Any]) -> LiveState:
    """Reshape one Live Tennis API match dict into the canonical LiveState.
    Tolerant of missing/partial score blocks (completed matches carry null
    points and empty games) -- such a match yields score_bucket=None and
    is_live=False rather than an exception."""
    score = match.get("score") or {}
    status = match.get("status")
    event_status = match.get("event_status")
    status_l = str(status).strip().lower() if status is not None else None
    event_l = str(event_status).strip().lower() if event_status is not None else None

    terminal_reason: Optional[str] = None
    if event_l in _TERMINAL_EVENT_STATUS:
        terminal_reason = event_l
    elif status_l in _TERMINAL_STATUS:
        terminal_reason = status_l
    is_live = (status_l == "live") and terminal_reason is None

    p1 = _name(match.get("players"), "p1")
    p2 = _name(match.get("players"), "p2")
    server = score.get("server")
    is_tiebreak = bool(score.get("is_tiebreak", False))

    server_id = returner_id = None
    server_pts = returner_pts = None
    bucket: Optional[int] = None
    if server in (1, 2):
        if server == 1:
            server_id, returner_id = p1, p2
            server_pts = _point_int(score.get("points"), 0)
            returner_pts = _point_int(score.get("points"), 1)
        else:
            server_id, returner_id = p2, p1
            server_pts = _point_int(score.get("points"), 1)
            returner_pts = _point_int(score.get("points"), 0)
        if is_tiebreak:
            bucket = DEUCE_BUCKET
        elif server_pts is not None and returner_pts is not None:
            bucket = score_bucket(server_pts, returner_pts)

    set_no = _current_set_no(score.get("sets"), score.get("games"), is_live)
    return LiveState(
        match_id=(str(match["id"]) if match.get("id") is not None else None),
        server_id=server_id, returner_id=returner_id,
        server_pts=server_pts, returner_pts=returner_pts,
        score_bucket=bucket, set_bucket=set_bucket(set_no), set_no=set_no,
        is_tiebreak=is_tiebreak,
        break_point=_break_point(server_pts, returner_pts, is_tiebreak, is_live),
        status=(str(status) if status is not None else None),
        event_status=(str(event_status) if event_status is not None else None),
        is_live=is_live, terminal_reason=terminal_reason,
    )


def live_states_from_feed(payload: Dict[str, Any]) -> List[LiveState]:
    """Reshape a {"data": [match, ...]} feed response into LiveStates."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    return [live_state_from_match(m) for m in data if isinstance(m, dict)]


def live_point_prob(prob_fn: ProbFn, state: LiveState) -> Optional[float]:
    """P(server wins the NEXT point) from the point model, conditioned on the
    realized live state -- the exact quantity the corpora fit. `prob_fn` is any
    ProbFn (PointModel.prob or a naive constant-rate wrapper). Returns None when
    there is no decidable served point (match not live, no server, or an
    undecodable non-tiebreak point)."""
    if not state.is_live or state.server_id is None or state.score_bucket is None:
        return None
    return float(prob_fn(state.server_id, state.score_bucket, state.set_bucket))


def to_point_frame_row(state: LiveState) -> Optional[Dict[str, Any]]:
    """The live state as one build_point_frame-shaped row (server_id/returner_id/
    score_bucket/set_bucket) with server_won LEFT NULL -- the label a live point
    does not have yet. This is the literal bridge into the corpus contract; a
    None return means the point is not yet decidable as a served-point row."""
    if state.server_id is None or state.score_bucket is None:
        return None
    return {
        "match_id": state.match_id,
        "server_id": state.server_id,
        "returner_id": state.returner_id,
        "score_bucket": state.score_bucket,
        "set_bucket": state.set_bucket,
        "server_won": None,
    }


def fetch_live(api_key: str,
               base_url: str = "https://api.livetennisapi.com/api/public/v1",
               path: str = "/matches/live", timeout: float = 10.0) -> List[LiveState]:
    """OPTIONAL convenience (NOT exercised by the tested core): pull the live
    feed with the stdlib and reshape it. Kept dependency-free (urllib, no
    requests) and network-isolated so the module stays a pure DATA transform.

    Free key (30/min, 100/day, no card): https://livetennisapi.com/subscribe/free
    """
    import urllib.request  # local import: keep the module import side-effect-free

    req = urllib.request.Request(base_url.rstrip("/") + path,
                                 headers={"X-API-Key": api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed host)
        payload = json.loads(resp.read().decode("utf-8"))
    return live_states_from_feed(payload)


__all__ = ["LiveState", "live_state_from_match", "live_states_from_feed",
           "live_point_prob", "to_point_frame_row", "fetch_live"]
