"""src/prediction/availability.py — tonight's confirmed inactives -> vacated load.

The biggest pregame miscalibration is minutes-surprise, and its #1 predictable
cause is teammates ruled OUT. This turns the official injury feed
(data/injuries_<date>.json: {players:[{team,name,status}]}) into the serve-time
signals the v2 calibrator and the live_adjustment layer need:

  team_vacated_map(date) -> {TEAM: {vac_min, vac_pts, n_out}}
      sum of the L10 minutes / points of that team's OUT players.
  player_vacated(pid, date) -> {vac_min, vac_pts, n_out, vac_share}
      the share of usage freed up for one player (their team's vacated load).

Leak-free at serve time (uses only games before today + tonight's injury report).
Best-effort: missing feed / unresolved name -> zeros, never raises.
"""
from __future__ import annotations

import json
import os
from datetime import date as _date
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent.parent
_NBA = _ROOT / "data" / "nba"

from src.data.injuries import (  # noqa: E402
    load_injuries, UNAVAILABLE_STATUSES, _name_key)
from src.prediction.live_adjustment import vacated_usage_share  # noqa: E402

# Minimum L10 minutes for an OUT player to count as a "regular" whose absence
# actually redistributes load (matches the calibration reconstruction).
_REGULAR_MIN = 15.0


def _injury_path(date: Optional[str]) -> str:
    if date:
        return str(_ROOT / "data" / f"injuries_{date}.json")
    return str(_ROOT / "data" / f"injuries_{_date.today().isoformat()}.json")


def _avail_parquet_fallback_enabled() -> bool:
    """CV_AVAIL_PARQUET_FALLBACK (default OFF). When ON, out_players_by_team falls
    back to data/cache/nba_injuries_<date>.parquet (the file golive's scraper
    actually writes) when data/injuries_<date>.json is absent/empty — bridging the
    production feed gap that silently kills the vac-bump (CV_SLATE_VAC_BUMP)."""
    return (os.environ.get("CV_AVAIL_PARQUET_FALLBACK", "").strip().lower()
            not in ("", "0", "false", "no", "off"))


def _payload_from_injuries_parquet(date: str) -> dict:
    """Build the {date, players:[{team,name,status}]} payload from
    data/cache/nba_injuries_<date>.parquet (the scraper's output schema:
    player_name/team/status/report_date). golive writes this parquet but NOT the
    injuries_<date>.json this module reads, so the freshness vac-bump is silently
    dead in production. Best-effort: returns {} on any failure (never raises)."""
    try:
        import pandas as pd  # noqa: PLC0415
        pq = _ROOT / "data" / "cache" / f"nba_injuries_{date}.parquet"
        if not pq.exists():
            return {}
        df = pd.read_parquet(pq)
        players = []
        for _, r in df.iterrows():
            nm = str(r.get("player_name") or "").strip()
            tm = str(r.get("team") or "").strip().upper()
            st = str(r.get("status") or "").strip().upper()
            if nm and tm and st:
                players.append({"team": tm, "name": nm, "status": st})
        rep = (str(df["report_date"].iloc[0])[:10]
               if "report_date" in df.columns and len(df) else None)
        return {"date": rep or date, "players": players}
    except Exception:
        return {}


def out_players_by_team(date: Optional[str] = None,
                        path: Optional[str] = None) -> Dict[str, List[str]]:
    """{TEAM_ABBR: [out player name, ...]} from the injury report (OUT/DOUBTFUL/NWT).

    FRESHNESS GUARD: when a date is explicitly requested (not when only path= is
    provided for testing/override), validates that the feed's "date" field matches
    the requested date, returning {} if it doesn't. This prevents a stale feed
    (e.g. injuries_2026-05-31.json accidentally read for 2026-06-04) from firing
    the vac-bump with wrong OUTs. Best-effort: feeds without a "date" field pass
    through (old format compatibility). Only active when date is not None.
    """
    effective_date = date or _date.today().isoformat()
    payload = load_injuries(path or _injury_path(date))
    # CV_AVAIL_PARQUET_FALLBACK: bridge the golive feed gap — the scraper writes
    # data/cache/nba_injuries_<date>.parquet but this reads data/injuries_<date>.json,
    # so the vac-bump is silently dead in production. Only on the explicit-date
    # production path (not the path= testing override), when the json is missing/
    # empty and the flag is ON: build the payload from the same-date parquet.
    # BYTE-IDENTICAL when OFF or when the json exists.
    if (not payload) and date is not None and path is None and _avail_parquet_fallback_enabled():
        payload = _payload_from_injuries_parquet(date)
    if not payload:
        return {}
    # Freshness guard: only when date was explicitly passed (production path).
    # When only path= is given (testing / manual override), skip the guard.
    if date is not None:
        feed_date = payload.get("date") or payload.get("report_date")
        if feed_date and str(feed_date).strip() != effective_date:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "availability: injury feed date '%s' != requested date '%s' — "
                "treating as stale, no bump",
                feed_date, effective_date,
            )
            return {}
    out: Dict[str, List[str]] = {}
    for p in payload.get("players", []) or []:
        status = str(p.get("status", "")).upper().strip()
        team = (p.get("team") or "").strip().upper()
        name = p.get("name", "")
        if name and team and status in UNAVAILABLE_STATUSES:
            out.setdefault(team, []).append(name)
    return out


def _l10_min_pts(pid: int, season: str, on_or_before: Optional[str]) -> Tuple[float, float]:
    """(L10 minutes, L10 points) from games strictly before *on_or_before*."""
    path = _NBA / f"gamelog_{pid}_{season}.json"
    if not path.exists():
        return 0.0, 0.0
    try:
        log = json.load(open(path, encoding="utf-8"))
    except Exception:
        return 0.0, 0.0
    import pandas as pd
    rows = []
    for g in log:
        d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
        if pd.isna(d):
            continue
        if on_or_before and d.date().isoformat() >= on_or_before:
            continue
        try:
            m = float(g.get("MIN"))
        except (TypeError, ValueError):
            continue
        if m >= 1:
            try:
                pts = float(g.get("PTS"))
            except (TypeError, ValueError):
                pts = 0.0
            rows.append((d, m, pts))
    if not rows:
        return 0.0, 0.0
    rows.sort(key=lambda r: r[0])
    mins = [r[1] for r in rows[-10:]]
    ptss = [r[2] for r in rows[-10:]]
    return float(np.mean(mins)), float(np.mean(ptss))


def player_form_covariates(pid: int, season: str = "2025-26",
                           on_or_before: Optional[str] = None) -> Dict[str, float]:
    """Per-player minutes-shape + scoring-rate covariates for the v2 calibrator,
    computed from the gamelog EXACTLY as scripts/build_calibration_frame_v2.py did
    (so serve-time inputs match training). Empty-ish dict if too little history."""
    path = _NBA / f"gamelog_{pid}_{season}.json"
    out = {"l3_min": 24.0, "l5_min": 24.0, "l10_min": 24.0, "std_min": 0.0,
           "prev_min": 24.0, "min_trend": 0.0, "l5_pts_pm": 0.0, "l5_reb_pm": 0.0,
           "days_into_season": 60}
    if not path.exists():
        return out
    try:
        log = json.load(open(path, encoding="utf-8"))
    except Exception:
        return out
    import pandas as pd
    recs = []
    for g in log:
        d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
        if pd.isna(d):
            continue
        if on_or_before and d.date().isoformat() >= on_or_before:
            continue
        try:
            m = float(g.get("MIN"))
        except (TypeError, ValueError):
            continue
        if m >= 1:
            def _n(k):
                try:
                    return float(g.get(k))
                except (TypeError, ValueError):
                    return 0.0
            recs.append((d, m, _n("PTS"), _n("REB")))
    if len(recs) < 5:
        return out
    recs.sort(key=lambda r: r[0])
    am = np.array([r[1] for r in recs]); ap = np.array([r[2] for r in recs])
    ar = np.array([r[3] for r in recs])
    l3 = float(am[-3:].mean()); l5 = float(am[-5:].mean()); l10 = float(am[-10:].mean())
    season_start = recs[0][0]
    for i in range(1, len(recs)):  # reset at >60-day gaps (new season)
        if (recs[i][0] - recs[i - 1][0]).days > 60:
            season_start = recs[i][0]
    out.update({
        "l3_min": l3, "l5_min": l5, "l10_min": l10,
        "std_min": float(am[-10:].std()), "prev_min": float(am[-1]),
        "min_trend": l3 - l10,
        "l5_pts_pm": float(ap[-5:].mean()) / max(l5, 1e-6),
        "l5_reb_pm": float(ar[-5:].mean()) / max(l5, 1e-6),
        "days_into_season": int((recs[-1][0] - season_start).days),
    })
    return out


def player_team(pid: int, season: str = "2025-26") -> Optional[str]:
    """Most-recent team abbrev for a player, from their gamelog MATCHUP."""
    path = _NBA / f"gamelog_{pid}_{season}.json"
    if not path.exists():
        return None
    try:
        log = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    import pandas as pd
    best = None; best_d = None
    for g in log:
        m = g.get("MATCHUP") or ""
        d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
        if pd.isna(d) or not m:
            continue
        t = m.split(" @ ")[0].strip() if " @ " in m else (
            m.split(" vs. ")[0].strip() if " vs. " in m else None)
        if t and (best_d is None or d > best_d):
            best_d, best = d, t
    return best


def team_vacated_map(date: Optional[str], resolve_pid: Callable[[str], Optional[int]],
                     season: str = "2025-26") -> Dict[str, Dict[str, float]]:
    """{TEAM: {vac_min, vac_pts, n_out}} for tonight's OUT regulars."""
    out = {}
    for team, names in out_players_by_team(date).items():
        vm = vp = 0.0; n = 0
        for nm in names:
            pid = resolve_pid(nm)
            if pid is None:
                continue
            l10m, l10p = _l10_min_pts(int(pid), season, date)
            if l10m >= _REGULAR_MIN:
                vm += l10m; vp += l10p; n += 1
        out[team] = {"vac_min": vm, "vac_pts": vp, "n_out": n}
    return out


def player_vacated(player_l10_pts: float, team: Optional[str],
                   vac_map: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Vacated load + usage share for a player given their team's vacated map entry."""
    rec = vac_map.get((team or "").upper(), {}) if team else {}
    vm = rec.get("vac_min", 0.0); vp = rec.get("vac_pts", 0.0)
    return {
        "vac_min": vm, "vac_pts": vp, "n_out": int(rec.get("n_out", 0)),
        "vac_share": vacated_usage_share([vp] if vp > 0 else [], player_l10_pts),
    }
