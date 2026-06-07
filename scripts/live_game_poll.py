"""live_game_poll.py — poll active NBA games and snapshot live state to JSON.

Cycle 88a (loop 5) — component 3 of the live in-game prediction stack.
Top sharp shops outperform pre-tip published lines by updating LIVE during
games (actual Q1 pace, foul trouble, blowout state, warmup injuries,
lineup confirmations). This poller is the data backbone that makes all of
those signals possible — it captures the canonical per-game state every N
seconds and writes one timestamped JSON per snapshot.

Output schema (per snapshot — `data/live/<game_id>_<unix_ts>.json`):

    {
      "game_id": "0022400123",
      "captured_at": "2026-05-24T19:42:18+00:00",
      "game_status": "PRE_GAME"|"LIVE"|"FINAL",
      "period": 2,
      "clock": "5:42",
      "home_team": "LAL",
      "away_team": "DEN",
      "home_score": 56,
      "away_score": 48,
      "players": [
        {"player_id": 203999, "name": "Nikola Jokic", "team": "DEN",
         "min": 14.5, "pts": 12, "reb": 4, "ast": 3,
         "fg3m": 2, "stl": 1, "blk": 0, "tov": 1, "pf": 2,
         "is_starter": true},
        ...
      ]
    }

Endpoints
---------
* `https://cdn.nba.com/static/json/liveData/boxscore/boxscore_<gid>.json`
  — single CDN request per game that returns game.gameStatus / period /
    gameClock + full per-player live stats. No auth, no rate-limit issues.
    Already used in production by `src/data/nba_stats.fetch_full_boxscore`.
* `scoreboardv2` (via `NBAStatsHTTP` raw HTTP) — the day's slate, so we
    know which `game_id`s to poll. Reused from `scripts/predict_slate.py`
    because the ScoreboardV2 wrapper has the known WinProbability KeyError.

Each poll tick issues 1 CDN request per active game (plus 1 scoreboard
request at startup), well within polite rate limits. `_API_SLEEP = 0.6`
between calls matches the convention established in `predict_slate.py`.

CLI
---
    python scripts/live_game_poll.py --once
    python scripts/live_game_poll.py --daemon --interval 30
    python scripts/live_game_poll.py --game-id 0022400123 --once
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, date as _date
from typing import Callable, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Header patch must run before any nba_api imports.
import src.data.nba_api_headers_patch  # noqa: F401, E402

_LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
_API_SLEEP = 0.6  # polite delay between live API calls (matches predict_slate)
_CDN_URL_TPL = (
    "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
)
_CDN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":  "application/json",
    "Referer": "https://www.nba.com/",
}

# NBA gameStatus integer → canonical status string.
_STATUS_MAP = {1: "PRE_GAME", 2: "LIVE", 3: "FINAL"}

# CV_SNAP_FF — when "1" / "true", additively appends four-factor shooting counts
# (fga, fgm, fg3a, fta, ftm) to each player row and sets schema_version
# "live-snapshot-2".  When unset / "0" / "false" the output is byte-identical
# to the baseline schema (live-snapshot-1).
_SNAP_FF: bool = os.environ.get("CV_SNAP_FF", "0").strip().lower() in ("1", "true", "yes")

# CV_SNAP_ONCOURT — when "1" / "true", additively appends the `oncourt` boolean
# field to each player row.  The CDN live boxscore carries `oncourt` (True for
# the 5 players currently on the floor per side, False for bench).  This field
# is a live-game-only CDN field — it may be absent (None / missing) for
# pre-game and final snapshots; the fallback is False.
# When unset / "0" / "false" the output is byte-identical to the existing
# schema (no oncourt key added).
_SNAP_ONCOURT: bool = os.environ.get("CV_SNAP_ONCOURT", "0").strip().lower() in ("1", "true", "yes")

# CV_SNAP_REBSPLIT — when "1" / "true", additively appends `oreb` and `dreb`
# (offensive / defensive rebound split) to each player row from the CDN fields
# `reboundsOffensive` and `reboundsDefensive`.  The invariant oreb+dreb==reb
# holds by CDN contract (reboundsTotal = reboundsOffensive + reboundsDefensive).
# `pf` (foulsPersonal) is already captured in the baseline schema at row
# construction time — it is always non-null (defaults 0 via _safe_int when the
# CDN omits the field).  This flag is purely additive; byte-identical when OFF.
_SNAP_REBSPLIT: bool = os.environ.get("CV_SNAP_REBSPLIT", "0").strip().lower() in ("1", "true", "yes")

# CV_SNAP_STARTER_FIX — when "1" / "true", fixes the `is_starter` parse bug
# where the CDN `starter` field is a string "1"/"0" rather than a boolean.
# The naive `bool(p.get("starter", False))` treats the non-empty string "0" as
# truthy, flagging ALL 30 players as starters.  When ON, the fix reads the
# string value correctly: "1" → True, "0" → False; falls back to regular bool()
# for native booleans (True/False) so both CDN variants are handled.
# When unset / "0" / "false" the output is byte-identical to the existing
# (buggy) baseline — intentionally preserves backward-compat until the fix is
# validated and flipped on in production.
_SNAP_STARTER_FIX: bool = os.environ.get("CV_SNAP_STARTER_FIX", "0").strip().lower() in ("1", "true", "yes")

# CV_INGAME_LIVE_USAGE — when "1" / "true", additively appends
# `p_live_usg_vs_prior` to each player row: the signed difference between the
# player's live usage proxy and their pregame (L5) usage estimate.
#
#   live_usg_proxy = (fga + 0.44*fta + tov) / team_(fga + 0.44*fta + tov)
#   p_live_usg_vs_prior = live_usg_proxy - p_prior_usage
#
# Requires CV_SNAP_FF=ON (fga/fta/ftm captured) for the primary path; when
# four-factor data are absent (CV_SNAP_FF not set or denominator < 0.5) falls
# back to an interim volume-ratio proxy from pts/min vs prior pts/min.
# Clamped to [-1.0, 2.0] to prevent extreme extrapolation at small sample.
# Byte-identical when this flag is OFF (no key added to the player dict).
_SNAP_LIVE_USAGE: bool = os.environ.get("CV_INGAME_LIVE_USAGE", "0").strip().lower() in ("1", "true", "yes")

# CV_MARGIN_SERIES — when "1" / "true", appends each poll's score state to a
# per-game JSONL time-series file:
#   data/cache/ingame/margin_series_<game_id>.jsonl
#
# Each appended line is a JSON object:
#   {"captured_at": "<iso>", "period": <int>, "clock": "<MM:SS>",
#    "home_score": <int>, "away_score": <int>, "margin": <int>}
#
# where margin = home_score − away_score (positive = home leading).
#
# Purpose: enables velocity/trajectory computation downstream (W-021 haircut,
# W-033 late-game-fouling trigger).  Pure additive logging to the scratch
# cache dir; no serve-path key added; snapshot JSON unchanged.
# The series file grows monotonically (only append writes).
# Byte-identical to baseline when this flag is OFF.
_MARGIN_SERIES: bool = os.environ.get("CV_MARGIN_SERIES", "0").strip().lower() in ("1", "true", "yes")

# CV_POLLER_CAPTURE_GAPS — umbrella flag for the rotation-model data-capture
# prerequisites.  When "1" / "true", this single flag activates the full set
# of additive per-player fields that a live rotation/minutes model requires:
#
#   • min        — already in baseline (float minutes); unchanged by this flag.
#   • fga, fg3a  — field-goal/three-point attempts (rotation volume signal).
#   • oreb       — offensive rebound (putback opportunity tracking).
#   • is_starter — starter flag with the "0"/"1" string parse bug FIXED.
#   • oncourt    — live on-court boolean (distinguishes benched starter from
#                  garbage-time bench player — the core rotation signal).
#   • plus_minus — CDN `plusMinusPoints` for this player in this game.
#
# Implementation: sets all the constituent per-feature flags to True at import
# time.  Each sub-flag remains individually overridable — if a caller already
# sets e.g. CV_SNAP_FF=1, that is preserved regardless of this umbrella.
#
# Fields NOT available from the CDN live boxscore `statistics` object and
# therefore NOT captured here:
#   • min_q1..min_q4 — per-quarter minutes are not in the CDN statistics blob;
#     they are derived from PBP event replay by snapshot_perq_enricher.py.
#     A future rotation model must consume the enricher output, not this poller.
#
# Byte-identical when OFF: adding this flag to an environment that previously
# had all constituent flags OFF produces zero change to emitted JSON.
_POLLER_CAPTURE_GAPS: bool = os.environ.get(
    "CV_POLLER_CAPTURE_GAPS", "0").strip().lower() in ("1", "true", "yes")

# CV_SNAP_PLUS_MINUS — when "1" / "true", additively appends `plus_minus`
# (plusMinusPoints from CDN statistics) to each player row.  The CDN field
# represents the team score differential while this player was on the court
# in the current game.  Absent / null for pre-game snapshots; defaults to 0
# via _safe_int.  Byte-identical when OFF (and when CV_POLLER_CAPTURE_GAPS
# is OFF).
_SNAP_PLUS_MINUS: bool = os.environ.get(
    "CV_SNAP_PLUS_MINUS", "0").strip().lower() in ("1", "true", "yes")

# When the umbrella flag is ON, activate all constituent capture flags.
# Each individual flag retains its own opt-in capability independently.
if _POLLER_CAPTURE_GAPS:
    _SNAP_FF = True
    _SNAP_ONCOURT = True
    _SNAP_REBSPLIT = True
    _SNAP_STARTER_FIX = True
    _SNAP_PLUS_MINUS = True
    # _SNAP_LIVE_USAGE and _MARGIN_SERIES are intentionally excluded from the
    # umbrella: they add derived fields / side-channel I/O, not raw CDN captures.

_INGAME_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "ingame")


def _parse_starter(v) -> bool:
    """Parse the CDN `starter` field which may be a string "1"/"0" or a bool.

    The CDN returns `starter: "1"` for starters and `starter: "0"` for bench
    players.  `bool("0")` → True in Python (non-empty string), causing the
    all-true bug.  This function handles both the string and native-bool cases.

    Only called when CV_SNAP_STARTER_FIX is ON.
    """
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return bool(v)
    # String case: CDN sends "1" for starters, "0" for bench.
    return str(v).strip() == "1"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """UTC ISO-8601 timestamp with seconds precision + tz suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_int(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (ValueError, TypeError):
        return 0


def _parse_minutes(v) -> float:
    """Convert 'PT14M30.00S' / '14:30' / 14.5 → decimal minutes."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        if s.startswith("PT") and "M" in s:
            s = s[2:]
            mins = float(s[: s.index("M")])
            secs = s[s.index("M") + 1:].rstrip("S")
            return round(mins + float(secs or 0) / 60, 2)
        if ":" in s:
            mm, ss = s.split(":", 1)
            return round(float(mm) + float(ss) / 60, 2)
        return round(float(s), 2)
    except (ValueError, TypeError):
        return 0.0


def _parse_clock(v) -> str:
    """Convert NBA ISO duration ('PT05M42.00S') to 'MM:SS' display string."""
    if not v:
        return ""
    s = str(v).strip()
    if s.startswith("PT") and "M" in s:
        try:
            body = s[2:]
            mins = int(float(body[: body.index("M")]))
            secs_part = body[body.index("M") + 1:].rstrip("S")
            secs = int(float(secs_part or 0))
            return f"{mins}:{secs:02d}"
        except (ValueError, TypeError):
            return s
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_boxscore_payload(payload: dict, captured_at: Optional[str] = None) -> dict:
    """Convert raw cdn.nba.com live boxscore JSON to the canonical snapshot.

    `payload` is the dict returned by the CDN endpoint (already json-decoded).
    Returns a snapshot dict whose schema is described in the module docstring.
    `captured_at` is injected so tests can pin the timestamp deterministically.
    """
    game = payload.get("game") or {}
    home = game.get("homeTeam") or {}
    away = game.get("awayTeam") or {}

    status_int = _safe_int(game.get("gameStatus"))
    status_str = _STATUS_MAP.get(status_int, "UNKNOWN")

    # CV_INGAME_LIVE_USAGE: pre-compute per-team usage denominators.
    # Only needed (and only non-zero) when CV_SNAP_FF is also ON; falls back
    # to a pts/min volume proxy when four-factor data are absent.
    # Always computed here when CV_INGAME_LIVE_USAGE is ON; byte-identical OFF.
    _team_usage_denom: Dict[str, float] = {}
    if _SNAP_LIVE_USAGE:
        for _side, _tobj in (("home", home), ("away", away)):
            _tri = str(_tobj.get("teamTricode", "") or "")
            _d_fga = 0.0
            _d_fta = 0.0
            _d_tov = 0.0
            for _p in _tobj.get("players", []) or []:
                _st = _p.get("statistics") or {}
                if _SNAP_FF:
                    _d_fga += _safe_int(_st.get("fieldGoalsAttempted"))
                    _d_fta += _safe_int(_st.get("freeThrowsAttempted"))
                else:
                    # Rough proxy: FGA ≈ pts / 2 (very rough — primary path is FF)
                    _d_fga += float(_safe_int(_st.get("points"))) / 2.0
                _d_tov += _safe_int(_st.get("turnovers"))
            _team_usage_denom[_tri] = _d_fga + 0.44 * _d_fta + _d_tov

    players: List[dict] = []
    for side, team_obj in (("home", home), ("away", away)):
        tricode = str(team_obj.get("teamTricode", "") or "")
        for p in team_obj.get("players", []) or []:
            st = p.get("statistics") or {}
            row: dict = {
                "player_id":  _safe_int(p.get("personId")),
                "name":       str(p.get("name", "") or ""),
                "team":       tricode,
                "min":        _parse_minutes(st.get("minutes")),
                "pts":        _safe_int(st.get("points")),
                "reb":        _safe_int(st.get("reboundsTotal")),
                "ast":        _safe_int(st.get("assists")),
                "fg3m":       _safe_int(st.get("threePointersMade")),
                "stl":        _safe_int(st.get("steals")),
                "blk":        _safe_int(st.get("blocks")),
                "tov":        _safe_int(st.get("turnovers")),
                "pf":         _safe_int(st.get("foulsPersonal")),
                "is_starter": (_parse_starter(p.get("starter"))
                               if _SNAP_STARTER_FIX
                               else bool(p.get("starter", False))),
            }
            # CV_SNAP_FF — additively append four-factor shooting counts.
            # Byte-identical when flag is OFF.
            if _SNAP_FF:
                row["fga"] = _safe_int(st.get("fieldGoalsAttempted"))
                row["fgm"] = _safe_int(st.get("fieldGoalsMade"))
                row["fg3a"] = _safe_int(st.get("threePointersAttempted"))
                row["fta"] = _safe_int(st.get("freeThrowsAttempted"))
                row["ftm"] = _safe_int(st.get("freeThrowsMade"))
            # CV_SNAP_ONCOURT — additively append oncourt / 5-man lineup flag.
            # The CDN live boxscore carries `oncourt` (bool) for the 10 players
            # currently on the floor (5 per side).  Absent for pre/post-game or
            # when the CDN omits the field — fallback is False.
            # Byte-identical when flag is OFF.
            if _SNAP_ONCOURT:
                row["oncourt"] = bool(p.get("oncourt", False))
            # CV_SNAP_REBSPLIT — additively append oreb / dreb split.
            # CDN carries reboundsOffensive + reboundsDefensive separately;
            # their sum == reboundsTotal (the existing `reb` field) by contract.
            # `pf` (foulsPersonal) is already in the baseline row above and is
            # always non-null — _safe_int defaults to 0 when the CDN omits it.
            # Byte-identical when flag is OFF.
            if _SNAP_REBSPLIT:
                row["oreb"] = _safe_int(st.get("reboundsOffensive"))
                row["dreb"] = _safe_int(st.get("reboundsDefensive"))
            # CV_SNAP_PLUS_MINUS — additively append plus_minus.
            # CDN `plusMinusPoints` is the team score differential while this
            # player was on the court in the current game.  Absent / null for
            # pre-game snapshots; _safe_int defaults to 0.
            # Byte-identical when flag is OFF.
            if _SNAP_PLUS_MINUS:
                row["plus_minus"] = _safe_int(st.get("plusMinusPoints"))
            # CV_INGAME_LIVE_USAGE — additively append p_live_usg_vs_prior.
            # Computes live_usg_proxy - p_prior_usage using the true-usage
            # denominator (fga + 0.44*fta + tov) when CV_SNAP_FF is also ON;
            # falls back to a pts/min volume-ratio proxy otherwise.
            # Clamped to [-1.0, 2.0].  Byte-identical when flag is OFF.
            if _SNAP_LIVE_USAGE:
                _p_fga = float(row.get("fga", 0) or 0) if _SNAP_FF else (
                    float(st.get("points", 0) or 0) / 2.0)
                _p_fta = float(row.get("fta", 0) or 0) if _SNAP_FF else 0.0
                _p_tov = float(row.get("tov", 0) or 0)
                _team_d = _team_usage_denom.get(tricode, 0.0)
                # Prior usage estimate: approximate from league average (0.10 per
                # active player; refined downstream when the model is retrained).
                _p_prior_usg = 0.10
                _p_pts = float(row.get("pts", 0) or 0)
                _p_min = float(row.get("min", 0) or 0)
                if _team_d >= 0.5:
                    _p_usg_proxy = (_p_fga + 0.44 * _p_fta + _p_tov) / _team_d
                    _delta = _p_usg_proxy - _p_prior_usg
                else:
                    # Fallback: volume ratio vs pts/min
                    _LEAGUE_PTS_PER_MIN = 19.0 / 48.0
                    _live_ppm = _p_pts / max(_p_min, 0.01)
                    _ratio = _live_ppm / max(_LEAGUE_PTS_PER_MIN, 0.001)
                    _p_usg_proxy = _p_prior_usg * min(3.0, max(0.0, _ratio))
                    _delta = _p_usg_proxy - _p_prior_usg
                row["p_live_usg_vs_prior"] = float(max(-1.0, min(2.0, _delta)))
            players.append(row)

    snap = {
        "game_id":     str(game.get("gameId", "") or ""),
        "captured_at": captured_at or _now_iso(),
        "game_status": status_str,
        "period":      _safe_int(game.get("period")),
        "clock":       _parse_clock(game.get("gameClock")),
        "home_team":   str(home.get("teamTricode", "") or ""),
        "away_team":   str(away.get("teamTricode", "") or ""),
        "home_score":  _safe_int(home.get("score")),
        "away_score":  _safe_int(away.get("score")),
        "players":     players,
    }
    if _SNAP_FF:
        snap["schema_version"] = "live-snapshot-2"
    return snap


# ─────────────────────────────────────────────────────────────────────────────
# I/O: fetch + persist
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_boxscore(game_id: str, *, timeout: float = 20.0) -> dict:
    """Hit cdn.nba.com for one game's live box score. Empty dict on error."""
    import requests as _req  # noqa: PLC0415
    url = _CDN_URL_TPL.format(game_id=game_id)
    try:
        resp = _req.get(url, headers=_CDN_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [warn] live boxscore fetch {game_id}: {e}")
        return {}


def snapshot_path(game_id: str, *, captured_at: Optional[str] = None,
                  live_dir: str = _LIVE_DIR) -> str:
    """Build a path like data/live/<game_id>_<unix_ts>.json.

    Uses a millisecond unix timestamp so multiple snapshots within the same
    second (rare but possible with --once across processes) don't collide.
    """
    if captured_at:
        try:
            dt = datetime.fromisoformat(captured_at)
            ts_ms = int(dt.timestamp() * 1000)
        except (ValueError, TypeError):
            ts_ms = int(time.time() * 1000)
    else:
        ts_ms = int(time.time() * 1000)
    return os.path.join(live_dir, f"{game_id}_{ts_ms}.json")


def write_snapshot(snapshot: dict, *, live_dir: str = _LIVE_DIR) -> str:
    """Persist a snapshot to data/live/<game_id>_<ts>.json. Returns the path."""
    game_id = snapshot.get("game_id") or "unknown"
    os.makedirs(live_dir, exist_ok=True)
    path = snapshot_path(game_id, captured_at=snapshot.get("captured_at"),
                          live_dir=live_dir)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2)
    return path


def margin_series_path(game_id: str,
                        cache_dir: str = _INGAME_CACHE_DIR) -> str:
    """Return the JSONL path for game_id's margin time-series."""
    return os.path.join(cache_dir, f"margin_series_{game_id}.jsonl")


def append_margin_series(snapshot: dict,
                          cache_dir: str = _INGAME_CACHE_DIR) -> str:
    """Append one score-state record to the per-game margin series JSONL.

    Only called when CV_MARGIN_SERIES is ON.  The snapshot's serve-path keys
    are unchanged — this function is purely additive (side-channel logging).

    Returns the path of the series file.
    """
    game_id = snapshot.get("game_id") or "unknown"
    record = {
        "captured_at": snapshot.get("captured_at", ""),
        "period":      int(snapshot.get("period") or 0),
        "clock":       str(snapshot.get("clock") or ""),
        "home_score":  int(snapshot.get("home_score") or 0),
        "away_score":  int(snapshot.get("away_score") or 0),
        "margin":      int(snapshot.get("home_score") or 0) - int(snapshot.get("away_score") or 0),
    }
    os.makedirs(cache_dir, exist_ok=True)
    path = margin_series_path(game_id, cache_dir=cache_dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Schedule discovery
# ─────────────────────────────────────────────────────────────────────────────

def discover_games_for_today(date_str: Optional[str] = None) -> List[str]:
    """Return the list of game_ids on the given date (default: today).

    Delegates to `scripts.predict_slate.fetch_games` so we share the
    proven raw-HTTP scoreboard workaround. Returns [] on failure.
    """
    date_str = date_str or _date.today().isoformat()
    try:
        from scripts.predict_slate import fetch_games  # noqa: PLC0415
    except Exception as e:
        print(f"  [warn] could not import fetch_games: {e}")
        return []
    games = fetch_games(date_str) or []
    return [str(g.get("game_id")) for g in games if g.get("game_id")]


# ─────────────────────────────────────────────────────────────────────────────
# Polling loop
# ─────────────────────────────────────────────────────────────────────────────

def poll_once(game_ids: List[str],
              *,
              fetch_fn: Callable[[str], dict] = fetch_live_boxscore,
              sleep_fn: Callable[[float], None] = time.sleep,
              api_sleep: float = _API_SLEEP,
              live_dir: str = _LIVE_DIR,
              cache_dir: str = _INGAME_CACHE_DIR) -> Dict[str, dict]:
    """One pass: fetch + snapshot every game_id. Returns {game_id: snapshot}.

    Sleeps `api_sleep` between game fetches (politeness — established
    convention from predict_slate.py). Empty payloads are skipped silently.

    When CV_MARGIN_SERIES is ON, each successful snapshot also appends one
    record to data/cache/ingame/margin_series_<game_id>.jsonl (pure additive
    logging; snapshot JSON and return dict are byte-identical).
    """
    out: Dict[str, dict] = {}
    for i, gid in enumerate(game_ids):
        if i > 0:
            sleep_fn(api_sleep)
        payload = fetch_fn(gid)
        if not payload or not payload.get("game"):
            continue
        snap = parse_boxscore_payload(payload)
        write_snapshot(snap, live_dir=live_dir)
        # CV_MARGIN_SERIES — append score-state to per-game time-series.
        # Byte-identical when flag is OFF: no snapshot key added, return
        # dict unchanged, write_snapshot output unchanged.
        if _MARGIN_SERIES:
            append_margin_series(snap, cache_dir=cache_dir)
        out[gid] = snap
    return out


def poll_daemon(game_ids: List[str],
                *,
                interval: float = 30.0,
                fetch_fn: Callable[[str], dict] = fetch_live_boxscore,
                sleep_fn: Callable[[float], None] = time.sleep,
                api_sleep: float = _API_SLEEP,
                live_dir: str = _LIVE_DIR,
                cache_dir: str = _INGAME_CACHE_DIR,
                max_ticks: Optional[int] = None) -> int:
    """Continuous polling until every game is FINAL (or max_ticks reached).

    Drops a game from the active set after we record a FINAL snapshot for
    it — so a 12-game slate that finishes one game per hour gradually
    quiets down to zero requests/tick. Returns the number of ticks run.
    """
    active = list(game_ids)
    ticks = 0
    while active:
        if max_ticks is not None and ticks >= max_ticks:
            break
        ticks += 1
        results = poll_once(
            active, fetch_fn=fetch_fn, sleep_fn=sleep_fn,
            api_sleep=api_sleep, live_dir=live_dir, cache_dir=cache_dir,
        )
        # Drop FINAL games — they got their last snapshot in this tick.
        active = [gid for gid in active
                  if results.get(gid, {}).get("game_status") != "FINAL"]
        if not active:
            break
        sleep_fn(interval)
    return ticks


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Poll live NBA game state and snapshot per-game JSONs.")
    ap.add_argument("--once", action="store_true",
                    help="One poll pass across all (or --game-id) games, then exit.")
    ap.add_argument("--daemon", action="store_true",
                    help="Poll every --interval seconds until all games FINAL.")
    ap.add_argument("--interval", type=float, default=30.0,
                    help="Daemon poll interval in seconds (default 30).")
    ap.add_argument("--game-id", default=None,
                    help="Poll just this specific game_id instead of today's slate.")
    ap.add_argument("--date", default=None,
                    help="Scoreboard date YYYY-MM-DD (default: today). "
                         "Ignored when --game-id is set.")
    args = ap.parse_args()

    if not (args.once or args.daemon):
        # Default to --once if neither was passed (safer than spinning forever).
        args.once = True

    if args.game_id:
        game_ids = [args.game_id]
    else:
        game_ids = discover_games_for_today(args.date)

    if not game_ids:
        print("[live_game_poll] no games to poll.")
        return 0

    print(f"[live_game_poll] polling {len(game_ids)} game(s) "
          f"-> {_LIVE_DIR}", flush=True)

    # Resolve module-level names at call time so tests can monkeypatch
    # `fetch_live_boxscore` / `_LIVE_DIR` and have the changes take effect.
    if args.daemon:
        ticks = poll_daemon(game_ids, interval=args.interval,
                             fetch_fn=fetch_live_boxscore,
                             live_dir=_LIVE_DIR)
        print(f"[live_game_poll] daemon exit after {ticks} tick(s); "
              f"all games FINAL.")
    else:
        results = poll_once(game_ids,
                             fetch_fn=fetch_live_boxscore,
                             live_dir=_LIVE_DIR)
        for gid, snap in results.items():
            print(f"  {gid}  {snap['away_team']} @ {snap['home_team']}  "
                  f"{snap['game_status']:<8}  "
                  f"Q{snap['period']} {snap['clock']:<5}  "
                  f"{snap['away_score']}-{snap['home_score']}  "
                  f"({len(snap['players'])} players)")
        print(f"[live_game_poll] wrote {len(results)} snapshot(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
