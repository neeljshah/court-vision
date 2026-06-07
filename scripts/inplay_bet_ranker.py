"""inplay_bet_ranker.py — in-play (live) prop bet ranker (R18_K2).

Activates AFTER tip-off. Every --interval-sec, builds a cumulative
snapshot from the latest data/cache/quarter_box/<game_id>_q*.json files,
runs project_from_snapshot (which composes the cycle-88 linear
extrapolator + endQ1/Q2/Q3 residual heads (R2_F / R3_A / R4_A), the
R10_M5 in-play win-prob, R10_M16 streak heads, R12_F3 cross-stat xstat
heads, and the learned minute trajectory at endQ3), prices every live
book line against the model projection, and writes a ranked top-N
output to:

    data/cache/live_bets/inplay_<game_id>.json   (atomic temp+rename)
    vault/Predictions/inplay_<game_id>.md

Guards:
  * Pre-tip no-op (no _q1.json yet  →  exit early with status PREGAME).
  * Snapshot-stale guard (any q-file mtime > --max-snapshot-age-sec  →
    flag stale; ranked_bets emitted with stale=True).
  * Garbage-time dampener: when |score_margin| > 20 at start of Q4
    (the endQ3 boundary), shrink projected REMAINING delta by 0.5x for
    starters of the trailing team and the bench of both teams (the
    cycle-88 blow_factor already handles starters on the leading team;
    we mirror it for the other side).
  * Stat-already-scored math: handled implicitly by project_from_snapshot
    which adds projected REMAINING on top of `current_<stat>`. We surface
    `current_<stat>` and `remaining_needed_for_line` on each bet row so
    operators see the math.

Run:
    python scripts/inplay_bet_ranker.py \
        --game-id 0042400317 \
        --slate sas_okc_2026-05-26 \
        --interval-sec 30
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from math import erf, sqrt
from typing import Any, Dict, List, Optional, Tuple

# CV_INGAME_SIGMA — gated in-game calibrated sigma for bet sizing (default OFF).
# When ON: ingame_sigma(stat, elapsed_min) replaces the ±25% heuristic sigma so
# Kelly sizing is calibrated against the 1987-game OOF residual distribution.
# When OFF: byte-identical — no change to any existing bet logic.
# See: src/prediction/ingame_sigma.py, docs/_audits/INGAME_SIGMA.md
_CV_INGAME_SIGMA = os.environ.get("CV_INGAME_SIGMA", "0") == "1"
_ingame_sigma_fn = None  # lazy-loaded below
if _CV_INGAME_SIGMA:
    try:
        from src.prediction.ingame_sigma import ingame_sigma as _ingame_sigma_fn  # noqa: E402
    except Exception:
        _CV_INGAME_SIGMA = False  # graceful degradation; never crash the ranker

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

QBOX_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
OUT_DIR = os.path.join(PROJECT_DIR, "data", "cache", "live_bets")
VAULT_DIR = os.path.join(PROJECT_DIR, "vault", "Predictions")

# Stat label  →  quarter-box JSON key (NBA Stats uses "to" for turnovers).
QB_STAT_KEY = {
    "pts": "pts", "reb": "reb", "ast": "ast", "fg3m": "fg3m",
    "stl": "stl", "blk": "blk", "tov": "to", "pf": "pf",
}
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

DEFAULT_INTERVAL = 30
DEFAULT_BANKROLL = 1000.0
KELLY_FRACTION = 0.25
PER_BET_CAP = 0.05
SLATE_CAP = 0.25
MIN_EDGE_PCT = 0.5
MAX_ODDS_ABS = 400
MIN_PRICE_PROB = 0.20
MAX_SNAPSHOT_AGE_SEC = 120  # 2 min staleness gate (in-play prop)
GARBAGE_TIME_MARGIN = 20    # |score_margin| > 20 at endQ3 → dampener
GARBAGE_TIME_SHRINK = 0.5   # 0.5x shrink on REMAINING delta


# ─────────────────────────────────────────────────────────────────────────────
# Atomic I/O
# ─────────────────────────────────────────────────────────────────────────────
def atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".tmp_", suffix=".json",
        dir=os.path.dirname(path) or ".",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def atomic_write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".tmp_", suffix=".md",
        dir=os.path.dirname(path) or ".",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Quarter-box snapshot construction
# ─────────────────────────────────────────────────────────────────────────────
def find_quarter_files(game_id: str, qbox_dir: str = QBOX_DIR) -> Dict[int, str]:
    """Return {period_int -> path} for every <game_id>_q<N>.json that exists."""
    out: Dict[int, str] = {}
    if not os.path.isdir(qbox_dir):
        return out
    pat = re.compile(rf"^{re.escape(str(game_id))}_q(\d)\.json$")
    for fn in os.listdir(qbox_dir):
        m = pat.match(fn)
        if m:
            out[int(m.group(1))] = os.path.join(qbox_dir, fn)
    return out


def _parse_min_str(s: Any) -> float:
    """Parse '9:18' or 9.3 -> minutes (float)."""
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0
    s = str(s).strip()
    if not s:
        return 0.0
    if ":" in s:
        a, _, b = s.partition(":")
        try:
            return float(a) + (float(b) / 60.0 if b else 0.0)
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _snapshot_age_sec(quarter_files: Dict[int, str], now_t: float | None = None) -> float:
    if not quarter_files:
        return float("inf")
    if now_t is None:
        now_t = time.time()
    newest = max(os.path.getmtime(p) for p in quarter_files.values())
    return now_t - newest


def build_cumulative_snapshot(game_id: str,
                              quarter_files: Dict[int, str],
                              pregame_win_prob: Optional[float] = None,
                              season: Optional[str] = None) -> Optional[dict]:
    """Aggregate per-quarter boxes into a cumulative snapshot for
    project_from_snapshot. Returns None if no quarter files present.

    The snapshot is positioned at the END of the latest available quarter
    (i.e. period = max_q + 1, clock = "12:00" or 0:00 of period boundary)
    so the inplay_winprob _period_to_snapshot gate fires (endQ1 / endQ2 /
    endQ3) for the residual heads + WP model.
    """
    if not quarter_files:
        return None

    max_q = max(quarter_files.keys())
    # Aggregate per-player by player_id (sum stats, sum minutes, last team).
    players_agg: Dict[int, Dict[str, Any]] = {}
    team_score: Dict[str, int] = {}
    team_per_q: Dict[str, Dict[int, int]] = {}
    home_team = away_team = ""
    home_team_id = None

    for q in sorted(quarter_files.keys()):
        try:
            with open(quarter_files[q], encoding="utf-8") as f:
                qj = json.load(f)
        except Exception:
            continue
        for tm in qj.get("teams") or []:
            abbr = tm.get("team_abbreviation") or ""
            pts = int(tm.get("pts") or 0)
            team_score[abbr] = team_score.get(abbr, 0) + pts
            team_per_q.setdefault(abbr, {})[q] = pts

        for p in qj.get("players") or []:
            try:
                pid = int(p["player_id"])
            except (KeyError, TypeError, ValueError):
                continue
            team = p.get("team_abbreviation") or ""
            row = players_agg.setdefault(pid, {
                "player_id": pid,
                "name": p.get("player_name") or f"pid_{pid}",
                "team": team,
                "min": 0.0,
                "pts": 0, "reb": 0, "ast": 0, "fg3m": 0,
                "stl": 0, "blk": 0, "tov": 0, "pf": 0,
                "start_position": p.get("start_position") or "",
            })
            row["team"] = team or row["team"]
            row["min"] += _parse_min_str(p.get("min"))
            for k in STATS:
                row[k] += int(p.get(QB_STAT_KEY[k]) or 0)
            row["pf"] += int(p.get("pf") or 0)
            # per-quarter min for endQ2/endQ3 residual heads
            row[f"min_q{q}"] = _parse_min_str(p.get("min"))

    # Pick home / away by NBA convention: in NBA Stats per-game box, teams
    # array is [away, home] usually but order varies. Fall back to first two
    # distinct abbrs.
    abbrs = list(team_score.keys())
    if len(abbrs) >= 2:
        # Try to read home/away off the first quarter JSON's teams payload
        # — many NBA shards include team_city implicitly via teams ordering.
        try:
            with open(quarter_files[min(quarter_files)], encoding="utf-8") as f:
                qj0 = json.load(f)
            teams0 = qj0.get("teams") or []
            if len(teams0) >= 2:
                # In NBA Stats payload the second team listed is usually
                # home (visit/home is encoded in matchup, not here). For
                # downstream code only the abbrev needs to be consistent —
                # we just pick a deterministic order.
                away_team = teams0[0].get("team_abbreviation") or abbrs[0]
                home_team = teams0[1].get("team_abbreviation") or abbrs[1]
                home_team_id = teams0[1].get("team_id")
        except Exception:
            home_team, away_team = abbrs[1], abbrs[0]
    elif abbrs:
        home_team = abbrs[0]

    snap: Dict[str, Any] = {
        "game_id": str(game_id),
        # Position the snapshot at the START of the NEXT period so it lines
        # up with the _period_to_snapshot gate (period N+1, clock 12:00).
        "period": min(max_q + 1, 4) if max_q < 4 else 4,
        "clock": "12:00" if max_q < 4 else "0:00",
        "home_team": home_team,
        "away_team": away_team,
        "home_team_id": home_team_id,
        "home_score": team_score.get(home_team, 0),
        "away_score": team_score.get(away_team, 0),
        "players": list(players_agg.values()),
        # Per-quarter splits used by inplay_winprob.features_from_snapshot.
        # When teams aren't differentiated the WP head will skip.
        "home_q1": team_per_q.get(home_team, {}).get(1),
        "home_q2": team_per_q.get(home_team, {}).get(2),
        "home_q3": team_per_q.get(home_team, {}).get(3),
        "away_q1": team_per_q.get(away_team, {}).get(1),
        "away_q2": team_per_q.get(away_team, {}).get(2),
        "away_q3": team_per_q.get(away_team, {}).get(3),
        "max_quarter_observed": max_q,
    }
    if pregame_win_prob is not None:
        snap["pregame_win_prob"] = float(pregame_win_prob)
    if season:
        snap["season"] = season
    return snap


# ─────────────────────────────────────────────────────────────────────────────
# Garbage-time dampener
# ─────────────────────────────────────────────────────────────────────────────
def apply_garbage_time_dampener(snap: dict, rows: List[Dict]) -> List[Dict]:
    """When |home - away| > 20 at endQ3 boundary, shrink REMAINING delta
    by 0.5x for ALL players. The cycle-88 blow_factor already shrinks
    starters on the LEADING team; this catches the trailing-team rotation
    (also pulled in true blowouts) and any benches missed by the
    star-threshold proxy.

    Operates on `projected_final` = current + REMAINING. We rewrite to
    current + 0.5 * REMAINING. No-op when:
      - max_quarter_observed < 3 (Q1/Q2 too early; gap can swing)
      - |margin| <= 20
      - projected_final <= current (already non-positive delta)
    """
    max_q = snap.get("max_quarter_observed") or 0
    if max_q < 3:
        return rows
    home_pts = float(snap.get("home_score") or 0)
    away_pts = float(snap.get("away_score") or 0)
    if abs(home_pts - away_pts) <= GARBAGE_TIME_MARGIN:
        return rows
    out = []
    for r in rows:
        r2 = dict(r)
        try:
            cur = float(r2.get("current", 0) or 0)
            proj = float(r2.get("projected_final", 0) or 0)
        except (TypeError, ValueError):
            out.append(r2)
            continue
        remaining = proj - cur
        if remaining > 0:
            r2["projected_final"] = round(cur + GARBAGE_TIME_SHRINK * remaining, 4)
            r2["garbage_time_applied"] = True
        else:
            r2["garbage_time_applied"] = False
        out.append(r2)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Line ingestion + pricing
# ─────────────────────────────────────────────────────────────────────────────
def _read_lines_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def load_live_lines_for_date(date_str: str,
                             books: Tuple[str, ...] = ("bov", "pin", "fd")
                             ) -> List[dict]:
    """Latest-snapshot-per-(player, stat, book, line) for the date."""
    out: Dict[Tuple[str, str, str, float], dict] = {}
    for book in books:
        path = os.path.join(LINES_DIR, f"{date_str}_{book}.csv")
        for r in _read_lines_csv(path):
            try:
                line = float(r.get("line") or 0)
            except (TypeError, ValueError):
                continue
            key = (r.get("player_name", ""), r.get("stat", ""),
                   r.get("book") or book, line)
            ts = r.get("captured_at", "")
            prev = out.get(key)
            if prev is None or (ts and ts > prev.get("captured_at", "")):
                out[key] = r
    return list(out.values())


def american_to_payout(odds: int, stake: float = 1.0) -> float:
    return stake * (odds / 100.0) if odds > 0 else stake * (100.0 / -odds)


def implied_prob(odds: int) -> float:
    return 100.0 / (odds + 100) if odds > 0 else (-odds) / ((-odds) + 100)


def kelly_fraction(prob: float, odds: int) -> float:
    b = american_to_payout(odds, 1.0)
    p = max(0.0, min(1.0, prob))
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


# iter-28 risk-reducing fix: counting stats that need a sigma floor.
_COUNTING_STAT_SIGMA_FLOOR = {"blk", "stl", "fg3m"}


def model_prob_over(point: float, q10: float, q90: float, line: float,
                    stat: Optional[str] = None,
                    q50: Optional[float] = None) -> float:
    """Gaussian CDF using q10/q90 to estimate sigma. Returns P(stat > line).

    iter-28: also enforces a quantile sanity guard (widen q90 if inverted)
    and a sigma floor for low-base-rate counting stats (BLK/STL/FG3M).
    The point prediction is NOT changed - only the sigma derivation.
    """
    if q10 is None or q90 is None:
        return 0.5
    q50_eff = q50 if q50 is not None else point
    # iter-28 risk-reducing fix: quantile sanity guard - widen if inverted.
    if not (q10 <= q50_eff <= q90):
        if q10 <= q50_eff:
            q90 = q50_eff + max(q90 - q50_eff, q50_eff - q10, 1.0)
        else:
            # Lower-tail inversion too - bail to neutral.
            return 0.5
    sigma = max((q90 - q10) / (2 * 1.2816), 1e-6)
    # iter-28 risk-reducing fix: sigma floor for counting stats.
    if stat is not None and str(stat).lower() in _COUNTING_STAT_SIGMA_FLOOR:
        floor_sigma = max(0.4 * float(q50_eff or 0), 0.5)
        sigma = max(sigma, floor_sigma)
    z = (line - point) / sigma
    cdf_at_line = 0.5 * (1 + erf(z / sqrt(2)))
    return 1 - cdf_at_line


# ─────────────────────────────────────────────────────────────────────────────
# Name normalization (book name -> roster name in snapshot)
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_name(s: str) -> str:
    import unicodedata
    n = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in n if not unicodedata.combining(c)).lower().strip()


def build_pred_index(rows: List[Dict]) -> Dict[Tuple[str, str], Dict]:
    """{(normalized_name, stat) -> row} for line lookup."""
    out: Dict[Tuple[str, str], Dict] = {}
    for r in rows:
        nm = _normalize_name(r.get("name", ""))
        stat = r.get("stat")
        out[(nm, stat)] = r
    return out


# R23_P2 — injury-kill guard. Pulls the multiplicative availability_factor
# from the R22_O8 nba_injuries_<date>.parquet (via injury_availability) so
# any OUT / NOT-WITH-TEAM player surfaced by the projection engine gets
# their bet excluded from ranked output. The legacy in-play ranker had NO
# injury wire — once a player went on the inactive list mid-day, their
# pregame quarter-box totals would still produce a rec.
def _availability_factor(pid: Optional[int], pname: str) -> float:
    """Return availability factor in [0, 1]. 1.0 on any lookup error so we
    never kill a real bet because the injury cache is unreadable."""
    try:
        from src.prediction.injury_availability import (  # noqa: PLC0415
            get_availability_factor,
        )
        pid_int: Optional[int] = None
        if pid is not None:
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                pid_int = None
        return float(get_availability_factor(player_id=pid_int,
                                             player_name=pname))
    except Exception:
        return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Pretip + tick
# ─────────────────────────────────────────────────────────────────────────────
def is_pretip(game_id: str, qbox_dir: str = QBOX_DIR) -> bool:
    """True iff no _q1.json for the game exists yet."""
    qf = find_quarter_files(game_id, qbox_dir=qbox_dir)
    return 1 not in qf


def _project_with_engine(snap: dict, period_override: Optional[int] = None) -> List[Dict]:
    """Lazy-load + call src.prediction.live_engine.project_from_snapshot."""
    from src.prediction import live_engine
    return live_engine.project_from_snapshot(snap, period=period_override)


def run_tick(game_id: str,
             date_str: str,
             bankroll: float,
             pregame_win_prob: Optional[float] = None,
             season: Optional[str] = None,
             qbox_dir: str = QBOX_DIR,
             books: Tuple[str, ...] = ("bov", "pin", "fd"),
             snapshot_age_sec: Optional[float] = None,
             dampener: bool = True) -> dict:
    """Single tick. Returns a payload dict (also persisted by caller)."""
    t0 = time.time()
    now = datetime.now(timezone.utc)
    qfiles = find_quarter_files(game_id, qbox_dir=qbox_dir)
    pretip = (1 not in qfiles)
    age = snapshot_age_sec if snapshot_age_sec is not None \
        else _snapshot_age_sec(qfiles)
    stale = (age > MAX_SNAPSHOT_AGE_SEC) and not pretip

    if pretip:
        return {
            "game_id": str(game_id),
            "captured_at": now.isoformat(),
            "status": "PREGAME",
            "pretip": True,
            "stale": False,
            "ranked_bets": [],
            "n_props_evaluated": 0,
            "n_positive_ev": 0,
            "snapshot_age_sec": None,
            "tick_latency_ms": int((time.time() - t0) * 1000),
        }

    snap = build_cumulative_snapshot(
        game_id, qfiles,
        pregame_win_prob=pregame_win_prob, season=season,
    )
    if snap is None:
        return {
            "game_id": str(game_id), "captured_at": now.isoformat(),
            "status": "NO_SNAPSHOT", "pretip": False,
            "stale": stale, "snapshot_age_sec": age,
            "ranked_bets": [], "n_props_evaluated": 0, "n_positive_ev": 0,
            "tick_latency_ms": int((time.time() - t0) * 1000),
        }

    try:
        rows = _project_with_engine(snap)
    except Exception as exc:
        return {
            "game_id": str(game_id), "captured_at": now.isoformat(),
            "status": f"PROJECT_ERROR: {exc}",
            "pretip": False, "stale": stale, "snapshot_age_sec": age,
            "ranked_bets": [], "n_props_evaluated": 0, "n_positive_ev": 0,
            "tick_latency_ms": int((time.time() - t0) * 1000),
        }

    if dampener:
        rows = apply_garbage_time_dampener(snap, rows)

    pred_idx = build_pred_index(rows)
    lines = load_live_lines_for_date(date_str, books=books)

    # CV_INGAME_SIGMA: compute game_elapsed_min from snapshot period/clock once,
    # so all bets in this tick share the same bucket assignment.  When flag is OFF
    # this block is a no-op (both values stay None, the heuristic path below is
    # unchanged).
    _snap_elapsed_min: Optional[float] = None
    if _CV_INGAME_SIGMA:
        try:
            _speriod = int(snap.get("period") or 1)
            _sclock = str(snap.get("clock") or "12:00")
            _cparts = _sclock.split(":")
            _cmin = float(_cparts[0]) + float(_cparts[1]) / 60.0
            _snap_elapsed_min = max(0.0, (_speriod - 1) * 12.0 + (12.0 - _cmin))
        except (TypeError, ValueError, IndexError):
            _snap_elapsed_min = None

    bets: List[Dict] = []
    n_evaluated = 0
    n_killed_by_injury = 0
    killed_players: Dict[str, float] = {}
    margin = float(snap.get("home_score", 0)) - float(snap.get("away_score", 0))

    for ln in lines:
        pname = ln.get("player_name", "")
        stat = ln.get("stat", "")
        nm = _normalize_name(pname)
        pred = pred_idx.get((nm, stat))
        if pred is None:
            continue
        # R23_P2 — kill bets for OUT / NOT-WITH-TEAM players. We do this
        # BEFORE the pricing math so an OUT player's stat-line never
        # contributes to n_evaluated either.
        pid_for_avail = pred.get("player_id")
        factor = _availability_factor(pid_for_avail, pname)
        if factor == 0.0:
            n_killed_by_injury += 1
            killed_players[pname] = 0.0
            continue
        try:
            line = float(ln.get("line") or 0)
        except (TypeError, ValueError):
            continue
        try:
            point = float(pred.get("projected_final", 0) or 0)
            cur = float(pred.get("current", 0) or 0)
        except (TypeError, ValueError):
            continue
        # Bands optionally on the engine row (q10/q90); else  ±25% heuristic.
        q10 = pred.get("q10")
        q90 = pred.get("q90")
        q50_in = pred.get("q50")
        try:
            q50_in = float(q50_in) if q50_in is not None else None
        except (TypeError, ValueError):
            q50_in = None
        # iter-28 risk-reducing fix: promote the heuristic fallback so it
        # also fires when the model returned q10/q90 but they're inverted
        # (q90 < q50 or q10 > q50). Same widening pattern as the missing-
        # quantile fallback above so the downstream sigma stays honest.
        needs_heuristic = False
        if q10 is None or q90 is None:
            needs_heuristic = True
        else:
            try:
                q10_f = float(q10); q90_f = float(q90)
                q50_ref = q50_in if q50_in is not None else point
                if not (q10_f <= q50_ref <= q90_f):
                    needs_heuristic = True
                else:
                    q10 = q10_f; q90 = q90_f
            except (TypeError, ValueError):
                needs_heuristic = True
        if needs_heuristic:
            # CV_INGAME_SIGMA (default OFF): when ON, replace the ±25% heuristic
            # with the calibrated per-(stat,bucket) sigma derived from the 1987-game
            # OOF eval cache.  Coverage at calibrated_sigma = 0.68 by construction.
            # When OFF: byte-identical — original heuristic unchanged.
            if (_CV_INGAME_SIGMA and _ingame_sigma_fn is not None
                    and _snap_elapsed_min is not None):
                try:
                    from src.prediction.ingame_sigma import sigma_to_gaussian_q10_q90
                    _cal_sigma = _ingame_sigma_fn(stat, _snap_elapsed_min)
                    q10, q90 = sigma_to_gaussian_q10_q90(point, _cal_sigma)
                except Exception:
                    spread = max(0.4 * point, 1.5)
                    q10 = max(0.0, point - spread)
                    q90 = point + spread
            else:
                spread = max(0.4 * point, 1.5)
                q10 = max(0.0, point - spread)
                q90 = point + spread

        for side, price_col in (("OVER", "over_price"),
                                ("UNDER", "under_price")):
            raw = ln.get(price_col)
            if raw in (None, "", "NA"):
                continue
            try:
                odds = int(float(raw))
            except (TypeError, ValueError):
                continue
            if abs(odds) > MAX_ODDS_ABS:
                continue
            impl = implied_prob(odds)
            if impl < MIN_PRICE_PROB:
                continue
            # iter-28 risk-reducing fix: pass stat + q50 so the sigma
            # floor for low-base-rate counting stats kicks in.
            p_over = model_prob_over(
                point, q10, q90, line, stat=stat, q50=q50_in,
            )
            prob = p_over if side == "OVER" else 1.0 - p_over
            n_evaluated += 1
            net = american_to_payout(odds, 1.0)
            ev = prob * net - (1.0 - prob) * 1.0
            kf_full = kelly_fraction(prob, odds)
            kf_used = min(kf_full * KELLY_FRACTION, PER_BET_CAP)
            stake = round(kf_used * bankroll, 2)
            edge_pct = (prob - impl) * 100.0
            remaining_needed = (line - cur) if side == "OVER" else (cur - line)
            bets.append({
                "player": pname,
                "stat": stat,
                "side": side,
                "book": ln.get("book") or "",
                "line": line,
                "current_stat": round(cur, 2),
                "remaining_needed": round(remaining_needed, 2),
                "model_point": round(point, 2),
                "model_q10": round(float(q10), 2),
                "model_q90": round(float(q90), 2),
                "odds": odds,
                "implied_prob": round(impl, 4),
                "model_prob": round(prob, 4),
                "edge_pct": round(edge_pct, 2),
                "ev_per_dollar": round(ev, 4),
                "kelly_pct_used": round(kf_used * 100, 2),
                "kelly_stake_$": stake,
                "snapshot_period": snap["period"],
                "home_win_prob_inplay": pred.get("home_win_prob_inplay"),
                "garbage_time_applied": pred.get("garbage_time_applied", False),
                "availability_factor": factor,
                "stale": stale,
                # CV_INGAME_SIGMA: when ON, surface the calibrated sigma used for
                # this bet's Kelly sizing.  None when flag is OFF (byte-identical
                # default behaviour — existing consumers see no new required field).
                "ingame_sigma": (
                    round(_ingame_sigma_fn(stat, _snap_elapsed_min), 4)
                    if (_CV_INGAME_SIGMA and _ingame_sigma_fn is not None
                        and _snap_elapsed_min is not None)
                    else None
                ),
            })

    bets.sort(key=lambda b: b["ev_per_dollar"], reverse=True)
    pos = [b for b in bets if b["edge_pct"] >= MIN_EDGE_PCT]
    cap_dollars = SLATE_CAP * bankroll
    capped: List[Dict] = []
    total = 0.0
    for b in pos:
        if total + b["kelly_stake_$"] <= cap_dollars:
            capped.append(b)
            total += b["kelly_stake_$"]
        else:
            remaining = max(0.0, cap_dollars - total)
            if remaining >= 5.0:
                b2 = dict(b)
                b2["kelly_stake_$"] = round(remaining, 2)
                capped.append(b2)
                total += remaining
            break

    top = capped[0] if capped else None
    payload = {
        "game_id": str(game_id),
        "captured_at": now.isoformat(),
        "status": ("IN_PLAY_STALE" if stale else "IN_PLAY"),
        "pretip": False,
        "stale": stale,
        "snapshot_age_sec": round(age, 2),
        "max_quarter_observed": snap.get("max_quarter_observed"),
        "snapshot_period": snap["period"],
        "score_margin": int(margin),
        "garbage_time_active": (snap.get("max_quarter_observed") or 0) >= 3
                               and abs(margin) > GARBAGE_TIME_MARGIN
                               and dampener,
        "bankroll": bankroll,
        "n_props_evaluated": n_evaluated,
        "n_positive_ev": len(pos),
        "top_edge_pct": top["edge_pct"] if top else None,
        "top_bet_str": (
            f"{top['player']} {top['stat'].upper()} {top['side']} "
            f"{top['line']:.1f} @ {top['book']} {top['odds']:+d}"
            if top else None
        ),
        "total_recommended_exposure_$": round(total, 2),
        "ranked_bets": capped,
        # R23_P2 — injury kill telemetry.
        "n_killed_by_injury": n_killed_by_injury,
        "killed_by_injury_players": sorted(killed_players.keys()),
        "tick_latency_ms": int((time.time() - t0) * 1000),
    }
    return payload


def render_md(payload: dict) -> str:
    lines = []
    lines.append(f"# In-Play Bet Ranker — game {payload['game_id']}\n")
    lines.append(f"_Updated: {payload['captured_at']}_  ")
    lines.append(f"_Status: {payload['status']}_  ")
    if payload.get("pretip"):
        lines.append("**Game is PREGAME — no in-play bets.**\n")
        return "\n".join(lines)
    lines.append(f"_Quarter observed: Q{payload.get('max_quarter_observed', '?')} "
                 f"(snapshot period={payload.get('snapshot_period')})_  ")
    lines.append(f"_Score margin (home - away): {payload.get('score_margin')}_  ")
    if payload.get("stale"):
        lines.append(f"**STALE snapshot (age={payload['snapshot_age_sec']:.0f}s "
                     f"> {MAX_SNAPSHOT_AGE_SEC}s)**  ")
    if payload.get("garbage_time_active"):
        lines.append("**GARBAGE-TIME dampener active (0.5x REMAINING delta)**  ")
    lines.append(f"\nProps evaluated: {payload['n_props_evaluated']}  ")
    lines.append(f"Positive-EV: {payload['n_positive_ev']}  ")
    lines.append(f"Total exposure: ${payload['total_recommended_exposure_$']:.2f}  ")
    lines.append("\n## Top Ranked Live Bets\n")
    lines.append(
        "| # | Player | Stat | Side | Book | Line | Cur | Need | Proj | Edge % | EV/$ | Stake $ |"
    )
    lines.append("|--|--|--|--|--|--|--|--|--|--|--|--|")
    for i, b in enumerate(payload["ranked_bets"][:10], 1):
        lines.append(
            f"| {i} | {b['player']} | {b['stat'].upper()} | {b['side']} | "
            f"{b['book']} | {b['line']:.1f} | {b['current_stat']:.1f} | "
            f"{b['remaining_needed']:+.1f} | {b['model_point']:.2f} | "
            f"{b['edge_pct']:+.2f}% | {b['ev_per_dollar']:+.3f} | "
            f"${b['kelly_stake_$']:.2f} |"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Daemon loop
# ─────────────────────────────────────────────────────────────────────────────
def run_daemon(game_id: str,
               date_str: str,
               interval: int = DEFAULT_INTERVAL,
               bankroll: float = DEFAULT_BANKROLL,
               max_ticks: Optional[int] = None,
               pregame_win_prob: Optional[float] = None,
               season: Optional[str] = None,
               wait_for_tip: bool = True,
               wait_poll_sec: int = 15,
               max_wait_sec: int = 7200,
               log_path: Optional[str] = None) -> dict:
    """Run the daemon. Blocks waiting for q1.json if wait_for_tip is True
    (up to max_wait_sec). Once q1 appears, ranks every `interval` seconds.

    Stops automatically when q4.json appears AND the game has ended
    (snapshot_age > 30 min — game is effectively final).
    """
    out_json = os.path.join(OUT_DIR, f"inplay_{game_id}.json")
    out_md = os.path.join(VAULT_DIR, f"inplay_{game_id}.md")
    if log_path is None:
        log_path = os.path.join(PROJECT_DIR, "vault", "Improvements",
                                "inplay_bet_ranker.log")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger(f"inplay_bet_ranker.{game_id}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(sh)

    pid = os.getpid()
    logger.info(
        f"START pid={pid} game_id={game_id} date={date_str} "
        f"interval={interval}s bankroll=${bankroll}"
    )

    # Wait for tip
    if wait_for_tip:
        waited = 0
        while is_pretip(game_id) and waited < max_wait_sec:
            # Emit a heartbeat output so dashboards see we're alive.
            payload = run_tick(game_id, date_str, bankroll,
                               pregame_win_prob=pregame_win_prob,
                               season=season)
            atomic_write_json(out_json, payload)
            atomic_write_text(out_md, render_md(payload))
            time.sleep(wait_poll_sec)
            waited += wait_poll_sec
        if is_pretip(game_id):
            logger.info(f"max_wait_sec={max_wait_sec} reached, no tip — exiting")
            return {"daemon_pid": pid, "status": "WAIT_TIMEOUT",
                    "ticks_observed": 0}

    logger.info("Q1 detected → entering IN_PLAY tick loop")
    tick_idx = 0
    summary = {"daemon_pid": pid, "ticks_observed": 0,
               "n_positive_ev_per_tick": [], "latency_ms": []}
    while True:
        # R19_L3 heartbeat
        _r19_hb('inplay_bet_ranker')
        t_start = time.time()
        try:
            payload = run_tick(game_id, date_str, bankroll,
                               pregame_win_prob=pregame_win_prob,
                               season=season)
        except Exception as exc:
            logger.exception(f"tick {tick_idx} ERROR: {exc}")
            tick_idx += 1
            if max_ticks is not None and tick_idx >= max_ticks:
                break
            time.sleep(max(0, interval - (time.time() - t_start)))
            continue
        payload["tick_idx"] = tick_idx
        atomic_write_json(out_json, payload)
        atomic_write_text(out_md, render_md(payload))
        top = payload.get("top_bet_str") or "—"
        logger.info(
            f"tick={tick_idx} q={payload.get('max_quarter_observed')} "
            f"margin={payload.get('score_margin')} "
            f"n_props={payload['n_props_evaluated']} "
            f"pos_ev={payload['n_positive_ev']} "
            f"top_edge={payload.get('top_edge_pct')} "
            f"top={top} "
            f"stale={payload['stale']} "
            f"latency_ms={payload['tick_latency_ms']}"
        )
        summary["ticks_observed"] += 1
        summary["n_positive_ev_per_tick"].append(payload["n_positive_ev"])
        summary["latency_ms"].append(payload["tick_latency_ms"])

        # Q4 done + stale → final
        max_q = payload.get("max_quarter_observed") or 0
        if max_q >= 4 and payload.get("snapshot_age_sec", 0) > 1800:
            logger.info("Q4 final + stale > 30min → daemon exiting cleanly")
            break

        tick_idx += 1
        if max_ticks is not None and tick_idx >= max_ticks:
            break

        elapsed = time.time() - t_start
        time.sleep(max(0, interval - elapsed))

    logger.info(f"STOP pid={pid} ticks={summary['ticks_observed']}")
    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", required=True,
                    help="NBA Stats game_id (e.g. 0042400317)")
    ap.add_argument("--date", required=True,
                    help="game date YYYY-MM-DD (used to look up live lines)")
    ap.add_argument("--interval-sec", type=int, default=DEFAULT_INTERVAL)
    ap.add_argument("--bankroll", type=float, default=DEFAULT_BANKROLL)
    ap.add_argument("--max-ticks", type=int, default=None,
                    help="cap ticks then exit")
    ap.add_argument("--pregame-win-prob", type=float, default=None)
    ap.add_argument("--season", default=None,
                    help="e.g. '2024-25' (passed to inplay_winprob feats)")
    ap.add_argument("--no-wait", action="store_true",
                    help="exit immediately if no q1.json (no tip wait)")
    ap.add_argument("--max-wait-sec", type=int, default=7200,
                    help="max wall-clock seconds to wait for q1.json")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    summary = run_daemon(
        game_id=args.game_id,
        date_str=args.date,
        interval=args.interval_sec,
        bankroll=args.bankroll,
        max_ticks=args.max_ticks,
        pregame_win_prob=args.pregame_win_prob,
        season=args.season,
        wait_for_tip=(not args.no_wait),
        max_wait_sec=args.max_wait_sec,
        log_path=args.log,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
