"""courtvision_router.py — CourtVision UI routes.

Routes: / (home), /game/{game_id}, /tonight, /parlays, /share/{slug} (+ qr.svg),
        /plus_ev, /healthz, /api/{slate, bet/{id}, parlays, plus_ev}.
Helpers in api._courtvision_data. Parlay engine in src.prediction.parlay_engine.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from api._courtvision_data import (
    grade_bet, load_lines_csv, load_slate_csv, slate_no_lines,
)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    _limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    _public_limit = _limiter.limit("60/minute")
except Exception:
    _limiter = None
    _public_limit = lambda f: f  # noqa: E731

def register_with_app(app) -> None:
    from api._courtvision_middleware import install; install(app, _limiter)
    # Pre-warm ALL cold-path caches on startup so the first user request
    # never pays the 77s cold-load penalty.
    #
    # Ranked culprits (measured on prod hardware):
    #   1. get_form_lookup()        — player_quarter_stats.parquet  ~1.4-5s
    #   2. _get_win_prob_model()    — win_prob_v3.pkl (2GB RAM scan) ~2-8s
    #   3. _load_predictions()      — predictions_cache_<date>.parquet ~0.5-2s
    #   4. _next_game_day()         — walks O(days x books) CSVs    ~0.5-2s
    #   5. _build_slate()           — CSV I/O + grade_bet grading    ~1-3s
    #
    # All five run concurrently in a background thread at startup. Railway boot
    # stays well under 60s; every subsequent request gets a cache hit (0.24s).
    @app.on_event("startup")
    async def _warm_caches() -> None:
        import asyncio
        import logging as _log
        _logger = _log.getLogger(__name__)

        def _warm_all() -> None:
            _t0 = time.perf_counter()
            steps: list[tuple[str, float]] = []

            def _step(label: str, fn):
                t = time.perf_counter()
                try:
                    fn()
                except Exception as exc:
                    _logger.warning("warmup/%s failed: %s", label, exc)
                steps.append((label, time.perf_counter() - t))

            # 1. form lookup (player_quarter_stats.parquet) — biggest single hit
            from api._courtvision_form import get_form_lookup
            _step("form_lookup", get_form_lookup)

            # 2. win_prob model (win_prob_v3.pkl) — ~2s pickle load on Railway
            _step("win_prob_model", _get_win_prob_model)

            # 3. next-game-day CSV scan — called on every route, cached 60s
            _step("next_game_day", _next_game_day)

            # 4. team stats JSON (instant but ensures the module-level dict is populated)
            _step("team_stats", lambda: _load_nba_team_stats(_NBA_CURRENT_SEASON))

            # 5. NBA player roster (used by consolidate to filter non-NBA props)
            try:
                from api._courtvision_odds import _load_nba_players
                _step("nba_roster", _load_nba_players)
            except Exception:
                pass

            # 6. predictions_cache parquet for today/latest date
            try:
                from api._predictions_overlay import _load_predictions
                warm_date = _today_et()
                _step(f"predictions_cache({warm_date})", lambda: _load_predictions(warm_date))
            except Exception:
                pass

            # 7. slate + grading (triggers consolidate + attach_form, already warm after step 1)
            _step("build_slate", lambda: _build_slate(_today_et()))

            total = time.perf_counter() - _t0
            detail = " | ".join(f"{label}={dur:.2f}s" for label, dur in steps)
            _logger.info("courtvision warmup done in %.2fs: %s", total, detail)

        asyncio.create_task(asyncio.to_thread(_warm_all))

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))
_PRED_DIR = _ROOT / "data" / "predictions"
_LINES_DIR = _ROOT / "data" / "lines"
_BANKROLL_DEFAULT, _TOP_N, _TTL_SEC, _SHARE_TOP_N = 100.0, 50, 300, 8
_PUBLIC_BASE_URL = __import__("os").environ.get("COURTVISION_PUBLIC_URL", "").rstrip("/")
_STAT_SIGMA = {"pts": 6.2, "reb": 2.6, "ast": 2.0, "fg3m": 1.4, "stl": 1.0, "blk": 0.9, "tov": 1.2}  # Empirically calibrated against 50K OOF rows per stat (pregame_oof.parquet) — tail-aware: each value is the smallest multiplier of the residual std where empirical 2σ coverage ≥ 95% AND 3σ coverage ≥ 99% (i.e., honest about fat tails without being over-conservative). Previous (8.5/3.6/2.6/1.7/1.4/1.0/1.7) was ~1.4x too wide vs the OOF residual distribution.
_STATS = tuple(_STAT_SIGMA.keys())
# Playoff-aware sigma boost. Model was trained on regular-season residuals;
# OOF dataset has no playoff games, so the multiplier is from literature
# (NBA playoff prop residuals run ~15-25% wider than regular season due to
# tighter rotations, defensive scheme adjustments, higher-stakes variance).
# 1.20x is the conservative middle of that range.
_PLAYOFF_SIGMA_MULT = 1.20


def _is_playoff_date(date_str: str) -> bool:
    """True if `date_str` (YYYY-MM-DD) falls in the NBA playoff window
    (roughly Apr 15 – Jun 30). Heuristic, not authoritative."""
    if not date_str or len(date_str) < 10:
        return False
    try:
        m = int(date_str[5:7]); d = int(date_str[8:10])
    except (ValueError, TypeError):
        return False
    if m == 4:
        return d >= 15
    if m in (5, 6):
        return True
    return False


def _stat_sigma_for_date(date_str: str) -> dict[str, float]:
    """Per-stat sigma dict, widened for playoff dates."""
    mult = _PLAYOFF_SIGMA_MULT if _is_playoff_date(date_str) else 1.0
    if mult == 1.0:
        return _STAT_SIGMA
    return {k: v * mult for k, v in _STAT_SIGMA.items()}


_BOX_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _parse_clock_to_minutes(clock_str) -> float | None:
    """Parse an NBA clock string like '7:06' or '0:42.3' to minutes."""
    if clock_str is None:
        return None
    if isinstance(clock_str, (int, float)):
        return float(clock_str)
    s = str(clock_str).strip()
    if not s:
        return None
    if ":" in s:
        try:
            mm, ss = s.split(":", 1)
            return float(mm) + float(ss) / 60.0
        except (ValueError, TypeError):
            return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _wp_interpolate_to_boundary(booster_p_home: float, period: int,
                                clock_min: float | None) -> float:
    """Shrink the booster's home-win-prob toward 0.5 by how far the current
    clock is from the snapshot boundary the booster was trained on.

    Boosters are trained at the END of each period (clock 0:00). Using them
    mid-period asks them to predict from out-of-distribution state. We blend
    booster output with 0.5 (uninformative prior) based on clock_min: at the
    boundary, full booster; at the start of the period, exactly 0.5.
    """
    if clock_min is None or clock_min < 0:
        return booster_p_home
    quarter_len = 12.0
    # live_weight = how close we are to the snapshot boundary
    live_weight = max(0.0, min(1.0, 1.0 - (clock_min / quarter_len)))
    return live_weight * booster_p_home + (1.0 - live_weight) * 0.5


def _live_shrink_weight(minutes_played: float) -> float:
    """Sigmoid weight for blending live projection with pregame q50 prior.

    At mp=4 → ~0.07 (mostly pregame), mp=14 → 0.5 (even blend), mp=24 → ~0.93
    (mostly live), mp=36+ → ~1.0. Stops the early-game noise from showing
    silly projections like a star headed for 0 PTS just because he has 3 min
    and hasn't shot yet."""
    if minutes_played is None or minutes_played <= 0:
        return 0.0
    import math as _m  # noqa: PLC0415
    return 1.0 / (1.0 + _m.exp(-(float(minutes_played) - 14.0) / 4.0))


def _shrink_player_minutes_from_snapshot(snap: dict) -> dict[str, float]:
    """Extract player_name.lower → minutes_played from a snapshot. Used by
    live-regrade callsites that don't have direct access to box_score rows."""
    out: dict[str, float] = {}
    if not isinstance(snap, dict):
        return out
    for lp in snap.get("players") or []:
        if not isinstance(lp, dict):
            continue
        nm = (lp.get("name") or lp.get("player") or lp.get("player_name") or "").lower()
        if not nm:
            continue
        mp_raw = lp.get("minutes") or lp.get("min") or lp.get("mp")
        mp = None
        if isinstance(mp_raw, (int, float)):
            mp = float(mp_raw)
        elif isinstance(mp_raw, str) and ":" in mp_raw:
            try:
                mm, ss = mp_raw.split(":", 1)
                mp = int(mm) + int(ss) / 60.0
            except Exception:
                mp = None
        elif isinstance(mp_raw, str):
            try:
                mp = float(mp_raw)
            except ValueError:
                mp = None
        if mp is not None:
            out[nm] = mp
    return out


def _regrade_bet_with_live_q50(bet: dict, new_q50: float,
                               stat_sigma: dict[str, float],
                               bankroll: float = 100.0,
                               cap_model_prob: float = 0.85) -> None:
    """Mutate `bet` in place to reflect a live q50 update.

    Recomputes side, edge_units, model_prob (under Normal), ev_pct (with 0.85
    cap), and kelly_stake_dollars (quarter-Kelly + 4% hard cap). Marks the
    bet with `live_regraded: True` so the UI can flag it."""
    from math import erf, sqrt  # noqa: PLC0415

    def _cdf(z): return 0.5 * (1.0 + erf(z / sqrt(2.0)))

    stat = (bet.get("prop_stat") or "").lower()
    sigma = stat_sigma.get(stat, 1.0)
    line = float(bet["line"])
    price = int(bet["best_price"])

    side = "OVER" if new_q50 >= line else "UNDER"
    z = (line - new_q50) / sigma
    p_over = 1.0 - _cdf(z)
    model_prob = p_over if side == "OVER" else (1.0 - p_over)

    payout = float(price) if price > 0 else 10000.0 / abs(price)
    ev_capped = False
    if model_prob > cap_model_prob:
        model_prob = cap_model_prob
        ev_capped = True
    ev_pct = model_prob * payout - (1.0 - model_prob) * 100.0

    # Quarter-Kelly with MAX_BET_PCT=0.04 hard cap (matches grade_bet behavior).
    b = payout / 100.0
    p = model_prob; q = 1.0 - p
    full_kelly = (p * b - q) / b if b > 0 else 0.0
    kf = max(0.0, full_kelly) * 0.25
    kelly_dollars = round(min(kf, 0.04) * bankroll, 2)

    bet["q50"] = round(new_q50, 3)
    bet["side"] = side
    bet["edge_units"] = round(new_q50 - line, 3)
    bet["model_prob"] = round(model_prob, 4)
    payoff_inv = 100.0 / (100.0 + payout)
    bet["market_prob"] = round(payoff_inv if price > 0 else float(abs(price) / (100.0 + abs(price))), 4)
    bet["ev_pct"] = round(ev_pct, 2)
    bet["ev_capped"] = ev_capped
    bet["kelly_stake_dollars"] = kelly_dollars
    bet["live_regraded"] = True
    bet["live_q50"] = round(new_q50, 3)


def _build_box_score(date: str, away_abbr: str, home_abbr: str) -> dict:
    """Projected per-player box score for a matchup, pivoted from
    predictions_cache_<date>.parquet. Pregame-only; live overlay is added
    client-side by polling /api/live/<game_id>."""
    import pandas as pd  # noqa: PLC0415
    pq = _ROOT / "data" / "cache" / f"predictions_cache_{date}.parquet"
    if not pq.exists():
        return {"away": None, "home": None, "have_data": False, "stats": list(_BOX_STATS)}
    try:
        df = pd.read_parquet(pq)
    except Exception:
        return {"away": None, "home": None, "have_data": False, "stats": list(_BOX_STATS)}

    teams = {(away_abbr or "").upper(), (home_abbr or "").upper()}
    df = df[df["team"].str.upper().isin(teams)].copy()
    if df.empty:
        return {"away": None, "home": None, "have_data": False, "stats": list(_BOX_STATS)}

    def team_rows(abbr: str) -> dict:
        ab = abbr.upper()
        team_df = df[df["team"].str.upper() == ab]
        if team_df.empty:
            return {"abbr": ab, "players": [], "totals": {}, "mean_totals": {}}
        pivot = team_df.pivot_table(
            index=["player_id", "player_name"],
            columns="stat", values="q50", aggfunc="first",
        ).reset_index()
        if "pts" in pivot.columns:
            pivot = pivot.sort_values("pts", ascending=False, na_position="last")
        players = []
        for _, r in pivot.iterrows():
            row = {"player_id": int(r["player_id"]) if pd.notna(r["player_id"]) else None,
                   "player_name": str(r["player_name"])}
            for s in _BOX_STATS:
                v = r.get(s) if s in pivot.columns else None
                row[s] = round(float(v), 1) if (v is not None and pd.notna(v)) else None
            players.append(row)
        # Sum-of-medians per stat (the literal q50 totals; conservative for skewed counts).
        totals = {s: round(float(team_df[team_df["stat"] == s]["q50"].sum()), 1) for s in _BOX_STATS}
        # Mean-of-distribution estimate per player using Pearson-Tukey right-skew
        # weighting (0.05*q10 + 0.70*q50 + 0.25*q90). Sums to a number comparable
        # to Pinnacle's team-total line, NOT to the sum of medians above.
        mean_totals = {}
        for s in _BOX_STATS:
            sub = team_df[team_df["stat"] == s]
            est = (0.05 * sub["q10"] + 0.70 * sub["q50"] + 0.25 * sub["q90"]).sum()
            mean_totals[s] = round(float(est), 1)
        return {"abbr": ab, "players": players, "totals": totals, "mean_totals": mean_totals}

    away = team_rows(away_abbr)
    home = team_rows(home_abbr)
    return {
        "away": away, "home": home,
        "have_data": bool(away["players"] or home["players"]),
        "stats": list(_BOX_STATS),
    }


router = APIRouter()
_CACHE: dict = {}


def _today_et() -> str:
    """Default date: today if it has lines or a slate, else the next date with
    live odds, else the most-recent slate.

    Pages like /odds, /tonight, /parlays render off this date. We DON'T want
    them showing yesterday's stale slate when today's lines CSVs already have
    fresh odds targeted at tomorrow's game (common during off-days between
    playoff games — odds are posted 2-3 days in advance).
    """
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    # Today wins if it has either a model slate OR fresh lines.
    if _slate_csv_path(today):
        return today
    if _lines_exist_for(today):
        return today
    # No data for today — look for the NEXT date with fresh lines (typical
    # case: today is an off-day, but DK/FD/etc. have already posted lines for
    # tomorrow / day-after).
    nxt = _next_lines_date(today)
    if nxt:
        return nxt
    # Final fallback: most-recent slate (yesterday's results page).
    return _latest_slate_date() or today


def _lines_exist_for(date: str) -> bool:
    """True if at least one `data/lines/<date>_<book>.csv` exists with rows."""
    if not _LINES_DIR.exists():
        return False
    for p in _LINES_DIR.iterdir():
        if not p.is_file() or p.suffix != ".csv":
            continue
        if not p.stem.startswith(f"{date}_"):
            continue
        try:
            if p.stat().st_size > 100:  # > header line
                return True
        except OSError:
            continue
    return False


def _next_lines_date(after: str) -> Optional[str]:
    """Earliest date strictly after `after` that has populated lines CSVs."""
    if not _LINES_DIR.exists():
        return None
    dates: set[str] = set()
    for p in _LINES_DIR.iterdir():
        if not p.is_file() or p.suffix != ".csv":
            continue
        stem = p.stem
        if len(stem) < 10 or stem[10] != "_":
            continue
        d = stem[:10]
        if d > after:
            try:
                if p.stat().st_size > 100:
                    dates.add(d)
            except OSError:
                continue
    return min(dates) if dates else None


def _slate_csv_path(date: str) -> Optional[Path]:
    for name in (f"slate_{date}_post_inj_refresh.csv", f"slate_{date}.csv"):
        p = _PRED_DIR / name
        if p.exists():
            return p
    return None


def _lines_csv_path(date: str) -> Optional[Path]:
    p = _LINES_DIR / f"lines_{date}.csv"
    return p if p.exists() else None


def _latest_slate_date() -> Optional[str]:
    if not _PRED_DIR.exists():
        return None
    dates = set()
    for p in _PRED_DIR.glob("slate_*.csv"):
        parts = p.stem.split("_")
        if len(parts) >= 2 and len(parts[1]) == 10:
            dates.add(parts[1])
    return max(dates) if dates else None


def _filter_to_mainline(line_rows: list[dict]) -> list[dict]:
    """Collapse alt-line ladders to one mainline row per (player, stat).

    Sportsbooks publish many alt lines per prop (e.g. SGA pts at 19.5 / 24.5 /
    28.5 / 29.5 / 30.5 / 40.5 / 43.5). Only the consensus line — usually the
    one offered by the most books — is the real mainline; the rest are
    juiced-vig alt markets. Grading every line as an independent bet inflates
    EV (model trivially says "99% under 43.5" → fake +112% EV).

    Mainline = the line with the most book entries. Ties broken by closeness
    to the median of all lines for that (player, stat).
    """
    from collections import defaultdict
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in line_rows:
        key = (str(r.get("player", "")).lower(), r.get("stat", ""))
        groups[key].append(r)
    out: list[dict] = []
    for rows in groups.values():
        if len(rows) == 1:
            out.append(rows[0]); continue
        max_books = max(len(r.get("books") or []) for r in rows)
        candidates = [r for r in rows if len(r.get("books") or []) == max_books]
        if len(candidates) == 1:
            out.append(candidates[0]); continue
        lines = sorted(float(r["line"]) for r in rows)
        median_line = lines[len(lines) // 2]
        out.append(min(candidates, key=lambda r: abs(float(r["line"]) - median_line)))
    return out


def _build_slate(date: str) -> dict:
    """Cached slate builder. Returns the JSON envelope dict."""
    cache_key = ("slate", date)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC:
        return entry[1]

    slate_path = _slate_csv_path(date)
    if slate_path is None:
        envelope = {"date": date, "generated_at": datetime.utcnow().isoformat() + "Z",
            "bankroll_default_dollars": _BANKROLL_DEFAULT, "stale_data": True,
            "has_lines": False, "latest_available": _latest_slate_date(),
            "summary": {"n_bets": 0, "avg_ev_pct": 0.0, "n_over": 0, "n_under": 0},
            "bets": []}
        _CACHE[cache_key] = (time.time(), envelope)
        return envelope

    slate_rows = load_slate_csv(slate_path, _STATS)
    # Lines source order: live consolidated (multi-book scrapers) > manual CSV.
    from api._courtvision_odds import consolidate_for_slate
    line_rows = consolidate_for_slate(date)
    lines_path = _lines_csv_path(date)
    if not line_rows and lines_path is not None:
        line_rows = load_lines_csv(lines_path)
    # Filter to mainline per (player, stat) — alt-line ladders (e.g. SGA pts at
    # 19.5/24.5/40.5/43.5 alongside the real 29.5 line) otherwise inflate EV
    # because the model trivially says "99% under 43.5". Mainline = the line
    # offered by the most books; ties broken by closeness to median line.
    line_rows = _filter_to_mainline(line_rows)
    has_lines = bool(line_rows)
    if has_lines:
        ps_idx = {(r["player_name"].lower(), r["stat"]): r for r in slate_rows.values()}
        stat_sigma_for_slate = _stat_sigma_for_date(date)
        bets = [grade_bet(ps_idx[(ln["player"].lower(), ln["stat"])], ln,
                          stat_sigma_for_slate, _BANKROLL_DEFAULT)
                for ln in line_rows
                if ln["stat"] in _STATS and (ln["player"].lower(), ln["stat"]) in ps_idx]
        # Honest-EV gate: cap model_prob at 0.85 (no real single-prop model is
        # more than 85% sure; anything higher reflects sigma understatement or
        # alt-line residual that slipped past _filter_to_mainline). Recompute
        # EV with the capped probability so downstream sizing is realistic.
        for b in bets:
            mp = b.get("model_prob")
            if mp is not None and mp > 0.85:
                price = int(b.get("best_price") or -110)
                payout = float(price) if price > 0 else (10000.0 / abs(price))
                b["model_prob"] = 0.85
                b["ev_pct"] = round(0.85 * payout - 0.15 * 100.0, 2)
                b["ev_capped"] = True
        bets.sort(key=lambda b: (b["ev_pct"] is None, -(b["ev_pct"] or 0.0)))
        bets = bets[:_TOP_N]
    else:
        bets = slate_no_lines(slate_rows, _STATS, _TOP_N)

    _log = __import__("logging").getLogger(__name__)
    try: from api._courtvision_form import attach_form; attach_form(bets)
    except Exception as exc: _log.warning("attach_form: %s", exc)
    try: from src.llm.bet_narrator import narrate_slate; narrate_slate(bets, date)
    except Exception as exc: _log.warning("narrate_slate: %s", exc)

    evs = [b["ev_pct"] for b in bets if b.get("ev_pct") is not None]
    envelope = {"date": date, "generated_at": datetime.utcnow().isoformat() + "Z",
        "bankroll_default_dollars": _BANKROLL_DEFAULT,
        "stale_data": date != _today_et(),
        "is_playoff": _is_playoff_date(date),
        "has_lines": has_lines, "latest_available": _latest_slate_date(),
        "summary": {"n_bets": len(bets), "avg_ev_pct": round(sum(evs)/len(evs), 2) if evs else 0.0,
                    "n_over": sum(1 for b in bets if b["side"] == "OVER"),
                    "n_under": sum(1 for b in bets if b["side"] == "UNDER")},
        "bets": bets}
    _CACHE[cache_key] = (time.time(), envelope)
    return envelope


def _build_parlays(date: str, seed: int = 0, top_n: int = 25) -> dict:
    """Same-book parlays only. For each sportsbook on the slate, run ParlayEngine
    against the bets best-priced at that book, then pool/rank by EV.

    Live behavior: when any game on the slate has a live snapshot in
    data/live/<gid>_*.json, we re-grade that game's bets via
    live_engine.project_from_snapshot first, so parlays reflect current game
    state (a player in foul trouble or having a hot Q1 shifts the parlay EV
    accordingly). Cache key includes the newest snapshot mtime so each live
    update invalidates the cache automatically.
    """
    # Build the slate first — need its bets for live regrade matching
    env = _build_slate(date)
    bets = env.get("bets", [])

    # Probe for live snapshots — any file written in the last 6 hours is a
    # candidate. We don't try to match snapshot game_ids to slate game_ids
    # (the alias map is too incomplete and the test snapshot uses sportsbook
    # ids); instead we project each recent snapshot and merge into a
    # (player_name, stat) → projected_final map. Bets match by player name.
    live_dir = _ROOT / "data" / "live"
    snap_mtime = 0
    recent_snaps: list = []
    if live_dir.exists() and bets:
        cutoff = time.time() - 6 * 3600
        # Keep one entry per unique snapshot file-stem prefix (gid_<ts>).
        latest_per_gid: dict[str, tuple[float, "Path"]] = {}
        try:
            for p in live_dir.iterdir():
                if not p.is_file() or p.suffix != ".json":
                    continue
                try:
                    mt = p.stat().st_mtime
                except OSError:
                    continue
                if mt < cutoff:
                    continue
                gid = p.stem.split("_")[0]
                cur = latest_per_gid.get(gid)
                if cur is None or mt > cur[0]:
                    latest_per_gid[gid] = (mt, p)
                if mt > snap_mtime:
                    snap_mtime = mt
            recent_snaps = [path for _, path in latest_per_gid.values()]
        except Exception:
            recent_snaps = []

    cache_key = ("parlays", date, seed, top_n, int(snap_mtime))
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC:
        return entry[1]
    has_lines = env.get("has_lines", False)
    gen_at = datetime.utcnow().isoformat() + "Z"
    if not bets or not has_lines:
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0,
               "has_lines": has_lines, "parlays": []}
        _CACHE[cache_key] = (time.time(), out)
        return out

    # ── Live regrade ─────────────────────────────────────────────────────
    # For each recent snapshot, run live_engine and merge its (player_name,
    # stat) → projected_final into a single map. Then deep-copy bets and
    # re-grade those whose (name, stat) match the map.
    live_games_count = 0
    if recent_snaps:
        try:
            from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415
            import copy as _copy_p  # noqa: PLC0415
            import json as _json_p  # noqa: PLC0415

            sig_table = _stat_sigma_for_date(date)
            live_q50_map: dict[tuple, float] = {}
            player_minutes: dict[str, float] = {}
            for snap_path in recent_snaps:
                try:
                    snap = _json_p.loads(snap_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not snap.get("period"):
                    continue
                try:
                    rows = project_from_snapshot(snap) or []
                except Exception:
                    continue
                if rows:
                    live_games_count += 1
                for r in rows:
                    nm = (r.get("name") or "").lower()
                    st = (r.get("stat") or "").lower()
                    pf = r.get("projected_final")
                    if nm and st and pf is not None:
                        try:
                            live_q50_map[(nm, st)] = float(pf)
                        except (TypeError, ValueError):
                            continue
                # Merge per-player minutes (last writer wins — recent snapshots
                # take precedence for the same player in a multi-game scan).
                player_minutes.update(
                    _shrink_player_minutes_from_snapshot(snap))

            if live_q50_map:
                regraded_bets = []
                for b in bets:
                    key = ((b.get("player_name") or "").lower(),
                           (b.get("prop_stat") or "").lower())
                    if key in live_q50_map:
                        cp = _copy_p.copy(b)
                        try:
                            mp = player_minutes.get(key[0], 0.0)
                            w_live = _live_shrink_weight(mp)
                            live_raw = live_q50_map[key]
                            pregame_q50 = float(cp.get("q50") or live_raw)
                            shrunk = w_live * live_raw + (1.0 - w_live) * pregame_q50
                            _regrade_bet_with_live_q50(cp, shrunk, sig_table)
                            regraded_bets.append(cp)
                        except Exception:
                            regraded_bets.append(b)
                    else:
                        regraded_bets.append(b)
                # Re-sort by EV so the best (live) bets are buckets-ready
                regraded_bets.sort(
                    key=lambda b: (b.get("ev_pct") is None,
                                   -(b.get("ev_pct") or 0.0))
                )
                bets = regraded_bets
        except Exception as exc:
            import logging as _lgp  # noqa: PLC0415
            _lgp.getLogger(__name__).warning(
                "parlay live regrade failed: %s", exc)

    from src.prediction.parlay_engine import ParlayEngine
    # Bucket bets by their best book — every leg in the same bucket can be
    # placed at the same sportsbook.
    buckets: dict[str, list[dict]] = {}
    for b in bets:
        bk = (b.get("best_book") or "").strip()
        if not bk:
            continue
        buckets.setdefault(bk, []).append(b)

    # Playoff dates get a sigma boost on the parlay sampler so joint hit-rate
    # is honest for the wider playoff residual distribution.
    sigma_mult = _PLAYOFF_SIGMA_MULT if _is_playoff_date(date) else 1.0

    def _has_same_player_legs(parlay: dict) -> bool:
        """True when the parlay has two legs on the same player. These have
        high correlation (player health/role drives both); the engine's RHO
        matrix dampens but the resulting EV is still inflated, so we exclude."""
        seen = set()
        for leg in parlay.get("legs", []):
            nm = (leg.get("player_name") or "").lower() if isinstance(leg, dict) else ""
            if nm in seen and nm:
                return True
            if nm:
                seen.add(nm)
        return False

    def _legs_signature(parlay: dict) -> frozenset:
        out = set()
        for leg in parlay.get("legs", []):
            if not isinstance(leg, dict):
                continue
            key = (
                (leg.get("player_name") or "").lower(),
                (leg.get("prop_stat") or "").lower(),
                leg.get("side"),
                leg.get("line"),
            )
            out.add(key)
        return frozenset(out)

    # Per-book parlay generation. Take top-K per book per leg-count so every
    # book that produces ≥2 valid combos gets representation in the output —
    # otherwise BetMGM (which usually wins per-leg EV) monopolizes the slate.
    PER_BOOK_PER_LEGCOUNT_CAP = 5  # ceiling on parlays per (book, n_legs)
    per_book_results: dict[str, list[dict]] = {}
    for book, pool in buckets.items():
        if len(pool) < 2:
            continue
        try:
            parlays = ParlayEngine(
                pool, rng_seed=seed, sigma_multiplier=sigma_mult
            ).enumerate_parlays(max_legs=4, min_ev_pct=-999.0)
        except Exception:
            continue
        by_id = {b.get("bet_id"): b for b in pool if b.get("bet_id")}
        # Normalize legs + drop same-player parlays + dedup by leg signature
        cleaned: list[dict] = []
        seen_sigs: set[frozenset] = set()
        for p in parlays:
            p["book"] = book
            resolved: list[dict] = []
            for leg_ref in p.get("legs", []):
                if isinstance(leg_ref, dict):
                    resolved.append(leg_ref)
                    continue
                bet = by_id.get(leg_ref) or {}
                resolved.append({
                    "player_name": bet.get("player_name"),
                    "prop_stat": bet.get("prop_stat"),
                    "line": bet.get("line"),
                    "side": bet.get("side"),
                    "best_price": bet.get("best_price"),
                })
            p["legs"] = resolved
            if p.get("combined_american") is None and p.get("combined_odds_american") is not None:
                p["combined_american"] = p["combined_odds_american"]
            if _has_same_player_legs(p):
                continue
            sig = _legs_signature(p)
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            cleaned.append(p)
        # Per-leg-count diversity within this book: top K from each leg count
        by_legcount: dict[int, list[dict]] = {}
        for p in cleaned:
            by_legcount.setdefault(p.get("n_legs") or len(p.get("legs", [])), []).append(p)
        book_out: list[dict] = []
        for k_legs in (2, 3, 4):
            xs = by_legcount.get(k_legs) or []
            xs.sort(key=lambda p: -(p.get("ev_pct") or 0.0))
            book_out.extend(xs[:PER_BOOK_PER_LEGCOUNT_CAP])
        per_book_results[book] = book_out

    # Pooled output: round-robin across books, EV-ranked within each book's
    # contribution. Round-robin guarantees every book gets at least 1 parlay
    # before any book gets its 2nd.
    book_iters = {bk: iter(sorted(xs, key=lambda p: -(p.get("ev_pct") or 0.0)))
                  for bk, xs in per_book_results.items() if xs}
    # Also enforce leg-count mix at the global level: drop parlays whose legs
    # overlap ≥2 with an already-emitted parlay (so we don't show 8 minor
    # variations of the same anchor pair).
    emitted_sigs: list[frozenset] = []
    pooled: list[dict] = []
    while book_iters and len(pooled) < top_n:
        empties = []
        for book, it in book_iters.items():
            if len(pooled) >= top_n:
                break
            picked = None
            while True:
                try:
                    cand = next(it)
                except StopIteration:
                    empties.append(book); break
                sig = _legs_signature(cand)
                # Drop if it shares 2+ legs with any already-emitted parlay
                overlapping = any(len(sig & ex) >= 2 for ex in emitted_sigs)
                if overlapping:
                    continue
                picked = cand; break
            if picked is not None:
                pooled.append(picked)
                emitted_sigs.append(_legs_signature(picked))
        for bk in empties:
            book_iters.pop(bk, None)

    # If we didn't fill top_n via the diverse round-robin, backfill from the
    # leftovers — BUT still apply the diversity filter so we don't undo the
    # work. Better to return 15 diverse parlays than 25 with heavy duplication.
    if len(pooled) < top_n:
        emitted_ids = {p.get("parlay_id") for p in pooled}
        leftovers: list[dict] = []
        for xs in per_book_results.values():
            for p in xs:
                if p.get("parlay_id") not in emitted_ids:
                    leftovers.append(p)
        leftovers.sort(key=lambda p: -(p.get("ev_pct") or 0.0))
        for p in leftovers:
            if len(pooled) >= top_n:
                break
            sig = _legs_signature(p)
            if any(len(sig & ex) >= 2 for ex in emitted_sigs):
                continue
            pooled.append(p)
            emitted_sigs.append(sig)

    # Final sort: keep diverse round-robin order but lift highest-EV to the top
    pooled.sort(key=lambda p: -(p.get("ev_pct") or 0.0))
    pooled = pooled[:top_n]
    out = {"date": date, "generated_at": gen_at, "n_parlays": len(pooled),
           "has_lines": True, "parlays": pooled,
           "live_games_count": live_games_count}
    _CACHE[cache_key] = (time.time(), out)
    return out


def _build_parlays_constructor(date: str, max_legs: int, min_ev_pct: float,
                               top_n: int = 25, seed: int = 0) -> dict:
    """Build parlays via src.prediction.parlay_constructor (SGP-penalty model).

    Reuses the cached single-leg slate, then enumerates valid combos via the
    Iter-43-validated constructor that applies the 15% SGP penalty + correlation
    shrinkage on same-player combos. Output is JSON-safe.
    """
    cache_key = ("parlays_constructor", date, max_legs, min_ev_pct, top_n, seed)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC:
        return entry[1]
    env = _build_slate(date)
    bets = env.get("bets", [])
    has_lines = env.get("has_lines", False)
    gen_at = datetime.utcnow().isoformat() + "Z"
    if not bets or not has_lines:
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0,
               "has_lines": has_lines, "parlays": [], "engine": "constructor"}
        _CACHE[cache_key] = (time.time(), out)
        return out

    import pandas as _pd  # noqa: PLC0415
    rows: list[dict] = []
    for b in bets:
        ev_pct = b.get("ev_pct")
        if ev_pct is None or ev_pct < min_ev_pct:
            continue
        # The constructor only consumes OVER legs (model places positive-edge OVERs).
        if (b.get("side") or "").upper() != "OVER":
            continue
        stat = (b.get("prop_stat") or b.get("stat") or "").lower()
        if not stat:
            continue
        rows.append({
            "player":     b.get("player_name"),
            "player_id":  b.get("player_id"),
            "stat":       stat,
            "side":       "OVER",
            "line":       b.get("line"),
            "odds":       b.get("best_price") if b.get("best_price") is not None else -110,
            "prob":       b.get("model_prob"),
            "ev":         ev_pct,
            "game_id":    b.get("game_id"),
            "team":       b.get("team"),
            "book":       b.get("best_book"),
        })

    if not rows:
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0,
               "has_lines": True, "parlays": [], "engine": "constructor"}
        _CACHE[cache_key] = (time.time(), out)
        return out

    df = _pd.DataFrame(rows)
    from src.prediction.parlay_constructor import (  # noqa: PLC0415
        build_parlay_candidates, rank_parlays,
    )
    try:
        candidates = build_parlay_candidates(df)
    except Exception as exc:
        import logging as _log  # noqa: PLC0415
        _log.getLogger(__name__).warning("parlay_constructor build failed: %s", exc)
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0,
               "has_lines": True, "parlays": [], "engine": "constructor",
               "error": str(exc)}
        _CACHE[cache_key] = (time.time(), out)
        return out

    if candidates.empty:
        parlays_list: list[dict] = []
    else:
        ranked = rank_parlays(candidates, top_n=top_n)
        parlays_list = ranked.to_dict(orient="records")
        # JSON-safety pass: serialize any numpy / nested types defensively.
        import json as _json  # noqa: PLC0415
        parlays_list = _json.loads(_json.dumps(parlays_list, default=str))

    out = {"date": date, "generated_at": gen_at,
           "n_parlays": len(parlays_list), "has_lines": True,
           "parlays": parlays_list, "engine": "constructor"}
    _CACHE[cache_key] = (time.time(), out)
    return out


# ── home page helpers ────────────────────────────────────────────────────────

_TEAM_ABBREVS: dict[str, str] = {
    # Full name fragments → display short name used on cards
    "76ers": "PHI", "bucks": "MIL", "bulls": "CHI", "cavaliers": "CLE",
    "celtics": "BOS", "clippers": "LAC", "grizzlies": "MEM", "hawks": "ATL",
    "heat": "MIA", "hornets": "CHA", "jazz": "UTA", "kings": "SAC",
    "knicks": "NYK", "lakers": "LAL", "magic": "ORL", "mavericks": "DAL",
    "nets": "BKN", "nuggets": "DEN", "pacers": "IND", "pelicans": "NOP",
    "pistons": "DET", "raptors": "TOR", "rockets": "HOU", "spurs": "SAS",
    "suns": "PHX", "thunder": "OKC", "timberwolves": "MIN", "trail blazers": "POR",
    "warriors": "GSW", "wizards": "WAS",
}


_GAMES_LOOKUP_CACHE: dict | None = None
_GAMES_LOOKUP_MTIME: float = 0.0


def _load_games_lookup() -> dict:
    """Cached load of `data/cache/games_lookup.json` — refreshes when file mtime
    changes. Empty dict if file missing."""
    global _GAMES_LOOKUP_CACHE, _GAMES_LOOKUP_MTIME
    import json as _json
    path = _ROOT / "data" / "cache" / "games_lookup.json"
    if not path.exists():
        return _GAMES_LOOKUP_CACHE or {}
    try:
        mt = path.stat().st_mtime
        if _GAMES_LOOKUP_CACHE is None or mt > _GAMES_LOOKUP_MTIME:
            with path.open() as f:
                _GAMES_LOOKUP_CACHE = _json.load(f)
            _GAMES_LOOKUP_MTIME = mt
    except (OSError, ValueError):
        pass
    return _GAMES_LOOKUP_CACHE or {}


def _guess_teams_from_game_id(game_id: str) -> tuple[str, str]:
    """Resolve team abbrs from the NBA games_lookup.json cache. Falls back to
    generic labels when the game isn't in the lookup yet."""
    lookup = _load_games_lookup()
    info = lookup.get(str(game_id))
    if info:
        return (info.get("away_abbr", "AWAY"), info.get("home_abbr", "HOME"))
    # Some scrapers use non-NBA game_ids (e.g. KAMBI event IDs). Match by start_time.
    return ("AWAY", "HOME")


def _fmt_tipoff(start_time_iso: str) -> str:
    """Convert ISO timestamp to human-readable tipoff string, e.g. '8:40 PM ET'."""
    if not start_time_iso:
        return "TBD"
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
        # Convert to ET (UTC-4 in summer / UTC-5 in winter — approximate)
        et_offset = timedelta(hours=-4)
        et = dt + et_offset
        hour = et.hour
        ampm = "AM" if hour < 12 else "PM"
        if hour == 0:
            hour = 12
        elif hour > 12:
            hour -= 12
        return f"{hour}:{et.minute:02d} {ampm} ET"
    except Exception:
        return start_time_iso[:16] if len(start_time_iso) >= 16 else start_time_iso


def _game_status(start_time_iso: str) -> str:
    """'live', 'pregame', or 'final' based on start time."""
    if not start_time_iso:
        return "pregame"
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (now - dt).total_seconds()
        if delta < 0:
            return "pregame"
        if delta < 4 * 3600:   # within 4-hour active game window
            return "live"
        return "final"
    except Exception:
        return "pregame"


def _build_home_data(date: str) -> dict:
    """Build the home page data payload. Cached for 60s."""
    cache_key = ("home", date)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < 60:
        return entry[1]

    from api._courtvision_odds import games_index, consolidate
    from api._predictions_overlay import overlay_predictions

    # --- games ---
    games_raw = games_index(date)

    # --- props with EV overlay (once per date) ---
    props_all: list[dict] = []
    try:
        raw_props = consolidate(date)
        props_all = overlay_predictions(date, raw_props)
    except Exception:
        props_all = []

    # Index props by game_id for fast per-game lookup
    props_by_game: dict[str, list[dict]] = {}
    for p in props_all:
        gid = p.get("game_id") or "?"
        props_by_game.setdefault(gid, []).append(p)

    # --- build game card data ---
    upcoming: list[dict] = []
    live: list[dict] = []

    for g in games_raw:
        gid = g["game_id"]
        st = g.get("start_time") or ""
        # Drop entries with no start_time — those are non-NBA / WNBA / scraper-
        # internal IDs that don't represent a real upcoming NBA game.
        if not st:
            continue
        status = _game_status(st)
        game_props = props_by_game.get(gid, [])

        # Top edges: props with rec_side and edge_pct, sorted by edge desc
        edge_props = [p for p in game_props if p.get("rec_side") and p.get("edge_pct") is not None]
        edge_props.sort(key=lambda p: -(p.get("edge_pct") or 0))

        top_edges = []
        for ep in edge_props[:5]:  # Pull 5 so client-side book filter still has 3 after filtering
            side = ep.get("rec_side", "OVER")
            best_o, best_u = None, None
            best_book_o, best_book_u = None, None
            for b in ep.get("books", []):
                bo = b.get("over_price"); bu = b.get("under_price"); bk = b.get("book") or ""
                if bo is not None and (best_o is None or bo > best_o):
                    best_o, best_book_o = bo, bk
                if bu is not None and (best_u is None or bu > best_u):
                    best_u, best_book_u = bu, bk
            odds = best_o if side == "OVER" else best_u
            best_book = best_book_o if side == "OVER" else best_book_u
            top_edges.append({
                "label": f"{ep['player']} {side[0]}{ep['line']:g} {ep['stat'].upper()}",
                "odds": odds,
                "edge_pct": ep.get("edge_pct"),
                "book": best_book or "",     # for client-side book filter
                "stat": ep.get("stat", ""),
                "side": side,
                "line": ep.get("line"),
                "player": ep.get("player", ""),
            })

        away_abbr, home_abbr = _guess_teams_from_game_id(gid)
        # Drop KAMBI / non-NBA event IDs that the scraper ingested but we can't
        # resolve to real NBA teams.  These show "AWAY @ HOME" on the card and
        # are pure noise on the home page.
        if away_abbr == "AWAY" and home_abbr == "HOME":
            continue

        n_props = g.get("n_props", 0)
        # Skip games with fewer than 3 props — too sparse to be useful on the
        # home page (typical case: single-prop KAMBI side-events).
        if n_props < 3:
            continue

        card = {
            "game_id": gid,
            "start_time": st,
            "start_time_iso": st,
            "tipoff_display": _fmt_tipoff(st),
            "status": status,
            "away_team": away_abbr,
            "home_team": home_abbr,
            "matchup": f"{away_abbr} @ {home_abbr}",
            "n_props": n_props,
            "n_players": g.get("n_players", 0),
            "top_edges": top_edges,
            "score_away": None,
            "score_home": None,
        }

        if status == "live":
            live.append(card)
        elif status == "pregame":
            upcoming.append(card)
        # 'final' games are omitted from both sections

    # Sort upcoming by start_time
    upcoming.sort(key=lambda g: g.get("start_time") or "")
    live.sort(key=lambda g: g.get("start_time") or "")

    # --- recently settled bets ---
    settled: list[dict] = []
    try:
        from database.bet_db import BetDB
        db = BetDB()
        rows_won = db.list_bets(status="won", limit=5)
        rows_lost = db.list_bets(status="lost", limit=5)
        combined = sorted(rows_won + rows_lost,
                          key=lambda b: b.get("settled_at") or b.get("created_at") or "",
                          reverse=True)[:8]
        settled = combined
    except Exception:
        settled = []

    result = {
        "upcoming_games": upcoming,
        "live_games": live,
        "settled_bets": settled,
        "slate_date": date,
        "section_label": "Tonight" if date == _today_et() else "Upcoming",
    }
    _CACHE[cache_key] = (time.time(), result)
    return result


_NBA_AVG_PACE = 99.5  # NBA 2024-25 season average possessions/game
_NBA_CURRENT_SEASON = "2025-26"

_TEAM_PACE_CACHE: dict | None = None
_TEAM_PACE_MTIME: float = 0.0

# Module-level cache for the win-prob model (avoids re-loading pickle on every request)
_WIN_PROB_MODEL_CACHE: Optional[object] = None
_WIN_PROB_MODEL_LOADED: bool = False
_WIN_PROB_MODEL_LOCK: threading.Lock = threading.Lock()  # prevents thundering-herd on cold start

# Module-level cache for nba team_stats JSON (keyed by season string)
_TEAM_STATS_CACHE: dict = {}
_TEAM_STATS_MTIME: dict = {}

# Static NBA abbreviation → team_id mapping (all 30 teams as of 2025-26).
# Baked in so lookup never depends on a runtime nba_api import and can never
# silently return {} on Railway if nba_api is missing or its import fails.
_STATIC_ABBREV_TO_ID: dict[str, int] = {
    "ATL": 1610612737, "BKN": 1610612751, "BOS": 1610612738, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}

# Module-level abbrev→id mapping (starts pre-populated from static map)
_ABBREV_TO_TEAM_ID: dict = dict(_STATIC_ABBREV_TO_ID)


def _get_abbrev_to_id() -> dict:
    """Return NBA team abbreviation → integer team_id mapping.

    Always returns the fully-populated static map. nba_api is used to extend
    it (e.g. expansion teams) but is never required — if it fails the static
    map is returned as-is, covering all 30 current teams.
    """
    global _ABBREV_TO_TEAM_ID
    if len(_ABBREV_TO_TEAM_ID) >= 30:
        return _ABBREV_TO_TEAM_ID
    try:
        from nba_api.stats.static import teams as _nba_teams
        _ABBREV_TO_TEAM_ID = {t["abbreviation"]: int(t["id"]) for t in _nba_teams.get_teams()}
    except Exception:
        pass  # static map already set — nba_api is an optional enhancement only
    return _ABBREV_TO_TEAM_ID


def _load_nba_team_stats(season: str = _NBA_CURRENT_SEASON) -> dict:
    """Load data/nba/team_stats_{season}.json cached by season (keyed by int team_id)."""
    global _TEAM_STATS_CACHE, _TEAM_STATS_MTIME
    import json as _json
    path = _ROOT / "data" / "nba" / f"team_stats_{season}.json"
    if not path.exists():
        return {}
    try:
        mt = path.stat().st_mtime
        if season not in _TEAM_STATS_CACHE or mt > _TEAM_STATS_MTIME.get(season, 0.0):
            with path.open() as f:
                raw = _json.load(f)
            # Keys may be strings or ints — normalise to int
            _TEAM_STATS_CACHE[season] = {int(k): v for k, v in raw.items()}
            _TEAM_STATS_MTIME[season] = mt
    except (OSError, ValueError):
        pass
    return _TEAM_STATS_CACHE.get(season, {})


def _team_stats_for(abbr: str, season: str = _NBA_CURRENT_SEASON) -> dict:
    """Return the team_stats dict for a given abbreviation and season, or defaults."""
    _D = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
          "pace": _NBA_AVG_PACE, "efg_pct": 0.53, "ts_pct": 0.57,
          "tov_pct": 13.0, "reb_pct": 0.5, "win_pct": 0.5}
    ts = _load_nba_team_stats(season)
    if not ts:
        return _D
    a2id = _get_abbrev_to_id()
    tid = a2id.get(abbr.upper())
    if tid:
        return ts.get(tid, _D)
    return _D


def _load_team_pace() -> dict:
    """Load data/cache/team_pace.json if it exists, else empty dict."""
    global _TEAM_PACE_CACHE, _TEAM_PACE_MTIME
    import json as _json
    path = _ROOT / "data" / "cache" / "team_pace.json"
    if not path.exists():
        return {}
    try:
        mt = path.stat().st_mtime
        if _TEAM_PACE_CACHE is None or mt > _TEAM_PACE_MTIME:
            with path.open() as f:
                _TEAM_PACE_CACHE = _json.load(f)
            _TEAM_PACE_MTIME = mt
    except (OSError, ValueError):
        pass
    return _TEAM_PACE_CACHE or {}


def _compute_pace(away_abbr: str, home_abbr: str) -> tuple[Optional[float], Optional[float]]:
    """Return (pace_away, pace_home) using real team stats.

    Priority:
    1. data/cache/team_pace.json  (manual override cache)
    2. data/nba/team_stats_{season}.json  (NBA API advanced stats — has real PACE)
    3. data/games/*.parquet  (tracking-derived pace)
    4. NBA season average (99.5) — only if all above fail
    """
    pace_map = _load_team_pace()
    if pace_map:
        away = pace_map.get(away_abbr) or pace_map.get(away_abbr.lower())
        home = pace_map.get(home_abbr) or pace_map.get(home_abbr.lower())
        if away or home:
            return (float(away) if away else _NBA_AVG_PACE,
                    float(home) if home else _NBA_AVG_PACE)

    # Tier 2: real per-team PACE from NBA advanced team stats cache
    generic = {"AWAY", "HOME", "away", "home"}
    if away_abbr not in generic and home_abbr not in generic:
        try:
            ht = _team_stats_for(home_abbr)
            at = _team_stats_for(away_abbr)
            h_pace = ht.get("pace")
            a_pace = at.get("pace")
            if h_pace and h_pace != _NBA_AVG_PACE:
                return (round(float(a_pace or _NBA_AVG_PACE), 1),
                        round(float(h_pace), 1))
        except Exception:
            pass

    # Tier 3: scan recent games parquet for pace columns
    try:
        import glob as _glob
        games_dir = _ROOT / "data" / "games"
        if games_dir.exists():
            parquets = sorted(_glob.glob(str(games_dir / "*.parquet")))[-5:]
            if parquets:
                import importlib
                pd = importlib.import_module("pandas")
                dfs = []
                for p in parquets:
                    try:
                        dfs.append(pd.read_parquet(p, columns=["team_abbr", "pace"]))
                    except Exception:
                        pass
                if dfs:
                    df = pd.concat(dfs, ignore_index=True)
                    pace_by_team = df.groupby("team_abbr")["pace"].mean().to_dict()
                    away_p = pace_by_team.get(away_abbr, _NBA_AVG_PACE)
                    home_p = pace_by_team.get(home_abbr, _NBA_AVG_PACE)
                    return (round(away_p, 1), round(home_p, 1))
    except Exception:
        pass
    # Return NBA average as sensible default
    return (_NBA_AVG_PACE, _NBA_AVG_PACE)


def _get_win_prob_model():
    """Load and cache the win-prob model (CalibratedClassifierCV from win_prob_v3.pkl).

    Returns (clf, feature_cols) tuple or (None, None) on failure.
    Module-level cache avoids re-loading the ~5MB pickle on every request.
    Thread lock (double-checked) prevents thundering-herd on cold-start: without
    it, N concurrent first-requests would each start a ~2s pickle.load in parallel,
    holding the GIL during deserialization and causing 77s page loads on Railway.
    """
    global _WIN_PROB_MODEL_CACHE, _WIN_PROB_MODEL_LOADED
    if _WIN_PROB_MODEL_LOADED:  # fast path: no lock needed once loaded
        return _WIN_PROB_MODEL_CACHE
    with _WIN_PROB_MODEL_LOCK:  # only one thread loads; others wait then hit fast path
        if _WIN_PROB_MODEL_LOADED:  # re-check under lock (double-checked locking)
            return _WIN_PROB_MODEL_CACHE
        # Perform the load under the lock so concurrent cold requests don't all
        # start a ~2s pickle.load simultaneously.
        try:
            import pickle as _pickle
            import warnings as _warn
            model_path = _ROOT / "data" / "models" / "win_prob_v3.pkl"
            if model_path.exists():
                with _warn.catch_warnings():
                    _warn.simplefilter("ignore")
                    with model_path.open("rb") as f:
                        data = _pickle.load(f)
                clf = data.get("model")
                cols = data.get("feature_cols", [])
                if clf is not None and cols:
                    _WIN_PROB_MODEL_CACHE = (clf, cols)
        except Exception:
            pass
        _WIN_PROB_MODEL_LOADED = True  # mark done (even on failure — don't retry)
    return _WIN_PROB_MODEL_CACHE


def _pregame_wp_from_projection(date: str, away_abbr: str, home_abbr: str
                                 ) -> Optional[float]:
    """Return P(home wins) derived from the projected box score's team totals.

    Used in place of the buggy win_prob_v3.pkl model (which has a documented
    polarity bug — vault/Models/Polarity Bug Audit 2026-05-27.md). This stays
    consistent with whatever projection the user sees in the box score.

    Calibration: margin shrunk ×0.30 (known role-player under-projection bias),
    Normal CDF with sigma=14 (playoff) or 13 (regular), clamped to [0.35, 0.65]
    since no honest model can be more confident than that on an NBA matchup
    without market data.
    """
    if not (away_abbr and home_abbr):
        return None
    try:
        box = _build_box_score(date, away_abbr, home_abbr)
        away_t = box.get("away") or {}; home_t = box.get("home") or {}
        proj_a = (away_t.get("mean_totals") or {}).get("pts")
        proj_h = (home_t.get("mean_totals") or {}).get("pts")
        if proj_a is None or proj_h is None:
            return None
        from math import erf, sqrt  # noqa: PLC0415
        margin = (float(proj_h) - float(proj_a)) * 0.30
        margin_sigma = 14.0 if _is_playoff_date(date) else 13.0
        z = margin / margin_sigma
        p_home = 0.5 * (1.0 + erf(z / sqrt(2.0)))
        return max(0.35, min(0.65, p_home))
    except Exception:
        return None


def _compute_win_prob(game_id: str, props: list,
                      away_abbr: str = "", home_abbr: str = "") -> Optional[float]:
    """Return away-team win probability [0,1].

    Priority:
    1. win_prob_v3.pkl (CalibratedClassifierCV, 156 features) built from cached
       team_stats — fills real values for all key features, zeros for rare extras.
       Returns None if teams are unknown (generic AWAY/HOME placeholders).
    2. Moneyline no-vig proxy from props books (unlikely in player-prop data).
    3. None — template hides the section.
    """
    import numpy as _np

    # Attempt 1: model prediction from cached team stats
    generic = {"AWAY", "HOME", "away", "home", ""}
    if away_abbr not in generic and home_abbr not in generic:
        model_info = _get_win_prob_model()
        if model_info is not None:
            try:
                clf, feature_cols = model_info
                ht = _team_stats_for(home_abbr)
                at = _team_stats_for(away_abbr)

                # Build feature dict: real values for the ~25 high-importance
                # stats we have, sensible defaults for the rest.
                feats: dict = {c: 0.0 for c in feature_cols}
                feats.update({
                    "home_off_rtg":        ht.get("off_rtg", 112.0),
                    "home_def_rtg":        ht.get("def_rtg", 112.0),
                    "home_net_rtg":        ht.get("net_rtg", 0.0),
                    "home_pace":           ht.get("pace", _NBA_AVG_PACE),
                    "home_efg_pct":        ht.get("efg_pct", 0.53),
                    "home_ts_pct":         ht.get("ts_pct", 0.57),
                    "home_tov_pct":        ht.get("tov_pct", 13.0),
                    "home_rest_days":      2.0,
                    "home_back_to_back":   0.0,
                    "home_last5_wins":     round(ht.get("win_pct", 0.5) * 5, 1),
                    "home_season_win_pct": ht.get("win_pct", 0.5),
                    "away_off_rtg":        at.get("off_rtg", 112.0),
                    "away_def_rtg":        at.get("def_rtg", 112.0),
                    "away_net_rtg":        at.get("net_rtg", 0.0),
                    "away_pace":           at.get("pace", _NBA_AVG_PACE),
                    "away_efg_pct":        at.get("efg_pct", 0.53),
                    "away_ts_pct":         at.get("ts_pct", 0.57),
                    "away_tov_pct":        at.get("tov_pct", 13.0),
                    "away_rest_days":      2.0,
                    "away_back_to_back":   0.0,
                    "away_travel_miles":   1000.0,
                    "away_last5_wins":     round(at.get("win_pct", 0.5) * 5, 1),
                    "away_season_win_pct": at.get("win_pct", 0.5),
                    "net_rtg_diff":        round(ht.get("net_rtg", 0.0) - at.get("net_rtg", 0.0), 2),
                    "pace_diff":           round(ht.get("pace", _NBA_AVG_PACE) - at.get("pace", _NBA_AVG_PACE), 2),
                    "home_advantage":      1.0,
                    # L10 rolling — use season stats as proxy when not cached
                    "home_off_rtg_L10":    ht.get("off_rtg", 112.0),
                    "home_def_rtg_L10":    ht.get("def_rtg", 112.0),
                    "home_net_rtg_L10":    ht.get("net_rtg", 0.0),
                    "away_off_rtg_L10":    at.get("off_rtg", 112.0),
                    "away_def_rtg_L10":    at.get("def_rtg", 112.0),
                    "away_net_rtg_L10":    at.get("net_rtg", 0.0),
                    "home_efg_L10":        ht.get("efg_pct", 0.50),
                    "away_efg_L10":        at.get("efg_pct", 0.50),
                    "home_tov_pct_L10":    ht.get("tov_pct", 13.0) / 100,
                    "away_tov_pct_L10":    at.get("tov_pct", 13.0) / 100,
                    "home_oreb_pct_L10":   ht.get("reb_pct", 0.5) * 0.5,
                    "away_oreb_pct_L10":   at.get("reb_pct", 0.5) * 0.5,
                    # Ref defaults (league average)
                    "ref_avg_fouls":       42.0,
                    "ref_home_win_pct":    0.5,
                    "ref_fta_tendency":    0.0,
                    "ref_crew_known":      0.0,
                    # ELO defaults
                    "home_elo":            1500.0,
                    "away_elo":            1500.0,
                    "elo_differential":    0.0,
                    "home_elo_v2":         1500.0,
                    "away_elo_v2":         1500.0,
                    "elo_diff_v2":         0.0,
                    "v3_home_elo_v2":      1500.0,
                    "v3_away_elo_v2":      1500.0,
                    "v3_elo_diff_v2":      0.0,
                })

                X = _np.array([[feats.get(c, 0.0) for c in feature_cols]], dtype=_np.float32)
                prob_home = float(clf.predict_proba(X)[0][1])
                prob_away = round(1.0 - prob_home, 3)
                if 0.05 <= prob_away <= 0.95:
                    return prob_away
            except Exception:
                pass

    # Attempt 2: no-vig moneyline from any book in props
    try:
        for p in props:
            for b in p.get("books", []):
                ml_o = b.get("ml_over") or b.get("moneyline_home")
                ml_u = b.get("ml_under") or b.get("moneyline_away")
                if ml_o and ml_u:
                    def _imp(american: int) -> float:
                        if american > 0:
                            return 100 / (american + 100)
                        return -american / (-american + 100)
                    p_home = _imp(int(ml_o))
                    p_away = _imp(int(ml_u))
                    total = p_home + p_away
                    if total > 0:
                        return round(p_away / total, 3)
    except Exception:
        pass

    return None


def _build_model_total(game_props: list, home_abbr: str, away_abbr: str) -> tuple:
    """Return (model_total, model_spread) from PTS projections in game_props.

    Uses ALL props (not just recommended bets) so the total reflects the full
    roster, not only edge bets.  Deduplicates to one projection per player
    (highest model_projection wins when the same player has multiple PTS lines).
    Team split uses the model_team field attached by overlay_predictions from
    the predictions parquet (parquet carries a 'team' column).  Falls back to
    splitting the sorted PTS list in half when no team labels are present.
    Returns (None, None) when no PTS projections exist.
    model_spread = home_pts - away_pts (positive = home favored).
    """
    import logging as _log
    _logger = _log.getLogger(__name__)
    try:
        # Step 1: collect best PTS projection per player (deduplicate multiple lines)
        best_by_player: dict[str, dict] = {}
        for p in game_props:
            if (p.get("stat") or "").lower() != "pts":
                continue
            proj = p.get("model_projection")
            if proj is None:
                continue
            player = p.get("player") or ""
            existing = best_by_player.get(player)
            if existing is None or proj > (existing.get("model_projection") or 0):
                best_by_player[player] = p

        if not best_by_player:
            return (None, None)

        # Step 2: split by team using model_team (set by overlay from parquet)
        home_pts = 0.0
        away_pts = 0.0
        untagged: list[float] = []
        home_u = home_abbr.upper()
        away_u = away_abbr.upper()
        generic = {"AWAY", "HOME", "", "UNKNOWN"}

        for p in best_by_player.values():
            proj = float(p.get("model_projection") or 0)
            mt = (p.get("model_team") or "").upper()
            if mt and mt not in generic:
                if mt == home_u:
                    home_pts += proj
                elif mt == away_u:
                    away_pts += proj
                else:
                    untagged.append(proj)
            else:
                untagged.append(proj)

        # If team labels resolved both sides, distribute any untagged evenly
        if home_pts or away_pts:
            if untagged:
                half = sum(untagged) / 2.0
                home_pts += half
                away_pts += half
        else:
            # Fallback: no team labels at all — split sorted list in half
            sorted_pts = sorted(best_by_player.values(),
                                key=lambda x: x.get("player") or "")
            all_proj = [float(p.get("model_projection") or 0) for p in sorted_pts]
            half = max(len(all_proj) // 2, 1)
            away_pts = sum(all_proj[:half])
            home_pts = sum(all_proj[half:])

        total = round(home_pts + away_pts, 1)
        spread = round(home_pts - away_pts, 1)

        if total < 150 or total > 280:
            _logger.warning(
                "_build_model_total: suspicious total=%.1f for %s@%s "
                "(home=%.1f away=%.1f n_players=%d)",
                total, away_abbr, home_abbr, home_pts, away_pts, len(best_by_player),
            )

        if home_pts or away_pts:
            return (total, spread)
    except Exception:
        pass
    return (None, None)


def _build_key_players(game_props: list) -> list:
    """Top-3 players per team (6 total) by PTS model projection descending.

    Falls back to prop count when no PTS projections are available (rare case
    where predictions parquet was not generated).  Returns at most 6 names
    (top-3 away + top-3 home) ordered by projection desc.
    """
    # Best PTS projection per player
    pts_proj: dict[str, float] = {}
    pts_team: dict[str, str] = {}
    for p in game_props:
        if (p.get("stat") or "").lower() != "pts":
            continue
        proj = p.get("model_projection")
        if proj is None:
            continue
        player = p.get("player") or ""
        if not player:
            continue
        if player not in pts_proj or proj > pts_proj[player]:
            pts_proj[player] = float(proj)
            mt = (p.get("model_team") or "").upper()
            if mt:
                pts_team[player] = mt

    if pts_proj:
        # Group into two teams, pick top-3 each, return sorted by projection desc
        teams: dict[str, list] = {}
        untagged: list[tuple[float, str]] = []
        for player, proj in pts_proj.items():
            team = pts_team.get(player, "")
            if team:
                teams.setdefault(team, []).append((proj, player))
            else:
                untagged.append((proj, player))

        result = []
        # Sort each team's players by projection desc, take top 3
        for team_players in teams.values():
            team_players.sort(reverse=True)
            result.extend(name for _, name in team_players[:3])
        # Append untagged (sorted desc) filling up to 6 total
        untagged.sort(reverse=True)
        for _, name in untagged:
            if len(result) >= 6:
                break
            if name not in result:
                result.append(name)
        return result[:6]

    # Fallback: no PTS projections — use prop count as proxy
    counts: dict[str, int] = {}
    for p in game_props:
        player = p.get("player") or ""
        if player:
            counts[player] = counts.get(player, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:6]]


def _build_game_detail(game_id: str, date: str) -> dict:
    """Build game-detail page data for one game_id. Cached 60s per (game_id, date).

    Bug 1 fix — game_id alias resolution:
    DK, PointsBet, KAMBI, and oddsapi each assign different IDs to the same
    NBA matchup. We resolve the incoming game_id to its canonical set of aliases
    via games_lookup.json, then filter props by matching ANY of those IDs.
    This means /game/34201426 and /game/2734554 (both OKC@SAS) return the same
    data — which is the correct behavior: same matchup, same page.
    The URL /game/<any_alias_id> is treated as equivalent to the canonical ID.
    """
    cache_key = ("game_detail", game_id, date)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < 60:
        return entry[1]

    from api._courtvision_odds import consolidate, resolve_game_id
    from api._predictions_overlay import overlay_predictions

    # Resolve the incoming ID to its full alias set (may be a singleton when
    # the ID is not in games_lookup.json).
    alias_info = resolve_game_id(game_id)
    canonical_ids: frozenset[str] = alias_info.get("canonical_ids", frozenset([game_id]))

    props_all: list[dict] = []
    raw_props: list[dict] = []
    try:
        raw_props = consolidate(date)
        # Filter by ANY canonical alias — this collapses DK/PB/KAMBI IDs for
        # the same matchup into one unified props list.
        game_raw = [p for p in raw_props if p.get("game_id") in canonical_ids]
        if not game_raw:
            # Last-resort fallback: show all props (old behaviour).
            game_raw = raw_props
        props_all = overlay_predictions(date, game_raw)
    except Exception:
        raw_props = []
        props_all = []

    # Re-filter after overlay (overlay may add props not in game_raw).
    game_props = [p for p in props_all if p.get("game_id") in canonical_ids]
    if not game_props:
        game_props = props_all  # show all props if nothing matched

    # Start time from first matching prop
    start_time = ""
    for p in (game_props or props_all or raw_props):
        if p.get("game_id") in canonical_ids and p.get("start_time"):
            start_time = p["start_time"]
            break
    if not start_time and (game_props or props_all):
        cands = [p.get("start_time") or "" for p in (game_props or props_all)]
        start_time = next((s for s in cands if s), "")

    status = _game_status(start_time)

    # Recommended bets: has rec_side + edge_pct, sorted desc
    rec_bets_raw = [p for p in game_props if p.get("rec_side") and p.get("edge_pct") is not None]
    rec_bets_raw.sort(key=lambda p: -(p.get("edge_pct") or 0))

    rec_bets = []
    for p in rec_bets_raw[:15]:
        side = p.get("rec_side", "OVER")
        best_book = ""
        best_odds = None
        deeplink_web = ""
        for b in p.get("books", []):
            price = b.get("over_price") if side == "OVER" else b.get("under_price")
            if price is not None and (best_odds is None or price > best_odds):
                best_odds = price
                best_book = b.get("display") or b.get("book") or ""
                deeplink_web = (b.get("deeplink_over_web") if side == "OVER"
                                else b.get("deeplink_under_web")) or ""
        rec_bets.append({
            "player": p["player"],
            "stat": p["stat"],
            "line": p["line"],
            "rec_side": side,
            "edge_pct": p.get("edge_pct"),
            "kelly_pct": p.get("kelly_pct"),
            "best_odds": best_odds,
            "best_book": best_book,
            "deeplink_web": deeplink_web,
        })

    away_abbr, home_abbr = _guess_teams_from_game_id(game_id)

    # ── Intelligence: win probability + pace ──────────────────────────
    # Use projection-derived WP (consistent with box score, no polarity bug)
    # rather than the legacy team-level model.
    p_home_pre = _pregame_wp_from_projection(date, away_abbr, home_abbr)
    win_prob_away = (1.0 - p_home_pre) if p_home_pre is not None else None
    pace_away, pace_home = _compute_pace(away_abbr, home_abbr)

    # ── Key matchup hints: top-2 props by edge ────────────────────────
    key_bets = []
    for p in rec_bets_raw[:2]:
        side = p.get("rec_side", "OVER")
        key_bets.append({
            "player": p["player"],
            "stat": p["stat"].upper(),
            "line": p["line"],
            "rec_side": side,
            "edge_pct": p.get("edge_pct"),
        })

    # Pull off/def ratings for Intelligence card display
    _generic = {"AWAY", "HOME", "away", "home"}
    _ht_stats = _team_stats_for(home_abbr) if home_abbr not in _generic else {}
    _at_stats = _team_stats_for(away_abbr) if away_abbr not in _generic else {}
    off_rtg_home = round(_ht_stats["off_rtg"], 1) if _ht_stats.get("off_rtg") else None
    def_rtg_home = round(_ht_stats["def_rtg"], 1) if _ht_stats.get("def_rtg") else None
    off_rtg_away = round(_at_stats["off_rtg"], 1) if _at_stats.get("off_rtg") else None
    def_rtg_away = round(_at_stats["def_rtg"], 1) if _at_stats.get("def_rtg") else None
    # Determine pace_source label for transparency
    _pace_from_nba_stats = (
        pace_away != _NBA_AVG_PACE or pace_home != _NBA_AVG_PACE
    ) and away_abbr not in _generic and home_abbr not in _generic
    pace_source = "season_avg" if _pace_from_nba_stats else "default"

    _mt, _ms = _build_model_total(game_props, home_abbr, away_abbr)
    game_info = {
        "game_id": game_id,
        "start_time_iso": start_time,
        "tipoff_display": _fmt_tipoff(start_time),
        "status": status,
        "away_team": away_abbr,
        "home_team": home_abbr,
        "matchup": f"{away_abbr} @ {home_abbr}",
        "n_props": len(game_props),
        "n_players": len({p["player"] for p in game_props}),
        "score_away": None,
        "score_home": None,
        "clock": None,
        "win_prob_away": win_prob_away,
        "win_prob_home": round(1.0 - win_prob_away, 3) if win_prob_away is not None else None,
        "model_total": _mt,
        "model_spread": _ms,
        "key_players": _build_key_players(game_props),
        "injury_status": [],  # no live feed; source: api/_courtvision_injuries.py TBD
        "pace_away": pace_away,
        "pace_home": pace_home,
        "pace_source": pace_source,
        "off_rtg_away": off_rtg_away,
        "def_rtg_away": def_rtg_away,
        "off_rtg_home": off_rtg_home,
        "def_rtg_home": def_rtg_home,
        "injury_notes": "",
        "key_bets": key_bets,
    }

    result = {
        "game": game_info,
        "rec_bets": rec_bets,
        "has_predictions": bool(rec_bets_raw),
        "slate_date": date,
    }
    _CACHE[cache_key] = (time.time(), result)
    return result


# ── routes ───────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def home(request: Request, date: str = Query(default=None)):
    """Games hub landing page — upcoming + live game cards with top EV edges."""
    if not date:
        date = _next_game_day() or _today_et()
    data = _build_home_data(date)
    return _TEMPLATES.TemplateResponse("home.html", {"request": request, **data})


@router.get("/api/home.json", tags=["courtvision"])
def api_home(date: Optional[str] = Query(default=None)):
    """Same payload as the home HTML page but as JSON — used by the WS live-tick
    to refresh edge cards without a full page reload."""
    if not date:
        date = _next_game_day() or _today_et()
    return JSONResponse(_build_home_data(date))


@router.get("/game/{game_id}", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def game_detail(game_id: str, request: Request, date: str = Query(default=None)):
    """Per-game intelligence report + ranked bets + all props."""
    if not date:
        date = _next_game_day() or _today_et()
    data = _build_game_detail(game_id, date)
    return _TEMPLATES.TemplateResponse("game_detail.html", {"request": request, **data})


@router.get("/api/game/{game_id}.json", tags=["courtvision"])
def api_game_detail(game_id: str, date: Optional[str] = Query(default=None)):
    """Same data as /game/{game_id} HTML page but as JSON."""
    if not date:
        date = _next_game_day() or _today_et()
    return JSONResponse(_build_game_detail(game_id, date))


@router.get("/tonight", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def tonight(request: Request, date: str = Query(default=None),
            side: str = Query("ALL"), min_ev: float = Query(-999.0),
            game_id: str = Query(default="")):
    """Tonight's slate. Optional ?game_id= filter shows only one matchup's bets
    (this is what the homepage game cards link to — gives a per-game view using
    the same rich bet-card layout)."""
    if not date:
        date = _next_game_day() or _today_et()
    slate = _build_slate(date)
    side_u = (side or "ALL").upper()
    gid_filter = (game_id or "").strip()
    needs_filter = (side_u in ("OVER", "UNDER")) or (min_ev > -999.0) or bool(gid_filter)
    matchup_label = ""
    # Resolve the URL game_id (often a sportsbook id like KAMBI) to the canonical
    # set of NBA game_ids AND the matchup's team abbrs. Some bet feeds tag the
    # official NBA game_id that isn't in the alias map, so we accept either an id
    # match or a (team, opp) abbr match.
    canonical_ids: frozenset[str] = frozenset()
    alias_pair: frozenset[str] = frozenset()
    alias_away = ""
    alias_home = ""
    if gid_filter:
        from api._courtvision_odds import resolve_game_id
        alias_info = resolve_game_id(gid_filter)
        canonical_ids = alias_info.get("canonical_ids", frozenset([gid_filter]))
        alias_away = alias_info.get("away_abbr") or ""
        alias_home = alias_info.get("home_abbr") or ""
        if alias_away and alias_home:
            alias_pair = frozenset([alias_away.upper(), alias_home.upper()])

    def _gid_matches(b):
        if not gid_filter:
            return True
        if str(b.get("game_id", "")) in canonical_ids:
            return True
        if alias_pair:
            t = (b.get("team") or "").upper()
            o = (b.get("opp") or "").upper()
            if t in alias_pair and o in alias_pair:
                return True
        return False

    if needs_filter:
        bets = [b for b in slate["bets"]
                if (side_u == "ALL" or b["side"] == side_u)
                and (b.get("ev_pct") is None or b["ev_pct"] >= min_ev)
                and _gid_matches(b)]
        # If filtered to a specific game, derive matchup label from any bet
        if gid_filter and bets:
            sample = bets[0]
            home_or_away_indicator = "@" if sample.get("venue") == "away" else "vs"
            matchup_label = f"{sample.get('team','')} {home_or_away_indicator} {sample.get('opp','')}"
        slate = {**slate, "bets": bets}
    # When filtered to a single game AND a live snapshot exists, re-grade
    # the bets using live_engine q50s (so the cards reflect what the model
    # would project given current game state, not the pregame call).
    live_regrade_count = 0
    if gid_filter and slate.get("bets"):
        snap_for_game = None
        canon_for_game = list(canonical_ids) + [gid_filter]
        live_dir_chk = _ROOT / "data" / "live"
        if live_dir_chk.exists():
            for gid_chk in canon_for_game:
                m = sorted(live_dir_chk.glob(f"{gid_chk}_*.json"))
                if m:
                    try:
                        import json as _json2  # noqa: PLC0415
                        snap_for_game = _json2.loads(m[-1].read_text(encoding="utf-8"))
                        break
                    except Exception:
                        continue
        if snap_for_game and snap_for_game.get("period"):
            try:
                from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415
                proj_rows = project_from_snapshot(snap_for_game) or []
                live_map: dict[tuple, float] = {}
                for r in proj_rows:
                    nm = (r.get("name") or "").lower()
                    st = (r.get("stat") or "").lower()
                    pf = r.get("projected_final")
                    if nm and st and pf is not None:
                        try:
                            live_map[(nm, st)] = float(pf)
                        except (TypeError, ValueError):
                            continue
                player_minutes = _shrink_player_minutes_from_snapshot(snap_for_game)
                if live_map:
                    import copy as _copy  # noqa: PLC0415
                    sig_table = _stat_sigma_for_date(date)
                    new_bets = [_copy.copy(b) for b in slate["bets"]]
                    for b in new_bets:
                        key = ((b.get("player_name") or "").lower(),
                               (b.get("prop_stat") or "").lower())
                        if key in live_map:
                            mp = player_minutes.get(key[0], 0.0)
                            w_live = _live_shrink_weight(mp)
                            live_raw = live_map[key]
                            pregame_q50 = float(b.get("q50") or live_raw)
                            shrunk = w_live * live_raw + (1.0 - w_live) * pregame_q50
                            _regrade_bet_with_live_q50(b, shrunk, sig_table)
                            live_regrade_count += 1
                    new_bets.sort(
                        key=lambda b: (b.get("ev_pct") is None,
                                       -(b.get("ev_pct") or 0.0))
                    )
                    slate = {**slate, "bets": new_bets}
            except Exception as exc:
                import logging as _lg2  # noqa: PLC0415
                _lg2.getLogger(__name__).warning(
                    "tonight live regrade failed: %s", exc)

    # When filtered to a single game, build a pregame projected box score
    # for the matchup. JS polls /api/box_score for live updates.
    box_score = None
    if gid_filter:
        away_a = alias_away
        home_a = alias_home
        # Alias lookup may be empty for some book ids — fall back to deriving
        # away/home from the bets themselves (which carry team + opp + venue).
        if not (away_a and home_a) and slate.get("bets"):
            sample = slate["bets"][0]
            t = (sample.get("team") or "").upper()
            o = (sample.get("opp") or "").upper()
            if t and o:
                if sample.get("venue") == "home":
                    home_a, away_a = t, o
                else:
                    away_a, home_a = t, o
        if away_a and home_a:
            box_score = _build_box_score(date, away_a, home_a)
    return _TEMPLATES.TemplateResponse("tonight.html",
        {"request": request, "slate": slate, "side": side_u, "min_ev": min_ev,
         "game_id_filter": gid_filter, "matchup_label": matchup_label,
         "box_score": box_score, "live_regrade_count": live_regrade_count})


@router.get("/api/slate", tags=["courtvision"])
def api_slate(date: str = Query(default=None),
              fresh: int = Query(0, ge=0, le=1)):
    """Slate envelope. ?fresh=1 busts the 5-min cache (used by /tonight's WS
    handler when a `lines.refreshed` event fires so price updates reach the
    UI within a couple seconds instead of waiting for TTL)."""
    if date is None:
        date = _next_game_day() or _today_et()
    if fresh:
        _CACHE.pop(("slate", date), None)
    return JSONResponse(_build_slate(date))


@router.get("/api/box_score", tags=["courtvision"])
def api_box_score(date: str = Query(default=None),
                  game_id: str = Query(default="")):
    """Projected per-player box score for one matchup. Merges pregame q50 with
    any available live boxscore feed (current totals + minutes-paced projection)."""
    if not date:
        date = _next_game_day() or _today_et()
    if not game_id:
        return JSONResponse({"have_data": False, "error": "game_id required"}, status_code=400)
    from api._courtvision_odds import resolve_game_id
    alias_info = resolve_game_id(game_id)
    away_a = alias_info.get("away_abbr") or ""
    home_a = alias_info.get("home_abbr") or ""
    if not (away_a and home_a):
        # Best-effort fall back: look up from the slate's bets
        slate = _build_slate(date)
        sample = next((b for b in slate.get("bets", []) if str(b.get("game_id", ""))), None)
        if sample:
            t = (sample.get("team") or "").upper(); o = (sample.get("opp") or "").upper()
            if sample.get("venue") == "home":
                home_a, away_a = t, o
            else:
                away_a, home_a = t, o
    box = _build_box_score(date, away_a, home_a)

    # Overlay live data. Snapshots are written by box_snapshot_poller.py to
    # data/live/<game_id>_<timestamp>.json (newest = latest). Try canonical
    # game_ids in case the URL id is a sportsbook id (KAMBI, DK, FD, etc.).
    import json as _json  # noqa: PLC0415
    live_overlay = None
    canonical = list(alias_info.get("canonical_ids", frozenset([game_id])))
    canonical.append(game_id)
    live_dir = _ROOT / "data" / "live"
    if live_dir.exists():
        for gid in canonical:
            matches = sorted(live_dir.glob(f"{gid}_*.json"))
            if not matches:
                continue
            try:
                live_overlay = _json.loads(matches[-1].read_text(encoding="utf-8"))
                break
            except Exception:
                continue
    # Legacy fallback: old cache path (in case some component still writes there)
    if live_overlay is None:
        for gid in canonical:
            legacy_path = _ROOT / "data" / "cache" / "boxscore_live" / f"{gid}.json"
            if legacy_path.exists():
                try:
                    live_overlay = _json.loads(legacy_path.read_text(encoding="utf-8"))
                    break
                except Exception:
                    continue

    # If we have a snapshot, run the FULL live_engine projection pipeline.
    # This applies the residual heads (R4-A, period heads), foul-trouble
    # factors, blowout adjustment, heat-check shrinkage, and learned Q4
    # minutes — the same projection your box_snapshot_poller emits.
    engine_projections: dict[tuple[str, str], dict] = {}
    if live_overlay and isinstance(live_overlay, dict) and live_overlay.get("period"):
        try:
            from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415
            proj_rows = project_from_snapshot(live_overlay) or []
            for r in proj_rows:
                pid = str(r.get("player_id") or "")
                nm = (r.get("name") or "").lower()
                stat = (r.get("stat") or "").lower()
                if not stat:
                    continue
                if pid:
                    engine_projections[(pid, stat)] = r
                if nm:
                    engine_projections[(nm, stat)] = r
        except Exception as exc:
            import logging as _lg  # noqa: PLC0415
            _lg.getLogger(__name__).warning(
                "live_engine.project_from_snapshot failed: %s", exc)

    def attach_live(team_dict):
        if not team_dict or not team_dict.get("players"):
            return
        if not live_overlay:
            return
        players_live = live_overlay.get("players") or live_overlay.get("boxscore") or live_overlay.get("rows") or []
        if not isinstance(players_live, list):
            return
        by_id = {}
        by_name = {}
        for lp in players_live:
            if not isinstance(lp, dict): continue
            if lp.get("player_id") is not None:
                by_id[str(lp["player_id"])] = lp
            nm = (lp.get("player") or lp.get("player_name") or lp.get("name") or "").lower()
            if nm: by_name[nm] = lp
        for row in team_dict["players"]:
            lp = by_id.get(str(row.get("player_id"))) or by_name.get((row.get("player_name") or "").lower())
            if not lp: continue
            # Pull current stats
            cur = {}
            for s in _BOX_STATS:
                v = lp.get(s)
                if v is None and isinstance(lp.get("stats"), dict):
                    v = lp["stats"].get(s)
                if v is not None:
                    try: cur[s] = float(v)
                    except (TypeError, ValueError): pass
            # Minutes-paced projection: scale current by 36/minutes_played
            mp_raw = lp.get("minutes") or lp.get("min") or lp.get("mp")
            mp = None
            if isinstance(mp_raw, (int, float)):
                mp = float(mp_raw)
            elif isinstance(mp_raw, str) and ":" in mp_raw:
                try:
                    mm, ss = mp_raw.split(":", 1)
                    mp = int(mm) + int(ss) / 60.0
                except Exception:
                    mp = None
            elif isinstance(mp_raw, str):
                try: mp = float(mp_raw)
                except ValueError: mp = None
            row["current"] = cur
            row["minutes_played"] = mp
            # Foul count — flag foul trouble (4+ fouls = at risk of fouling out).
            pf_raw = lp.get("pf") or lp.get("fouls") or lp.get("personal_fouls")
            try:
                row["fouls"] = int(pf_raw) if pf_raw is not None else None
            except (TypeError, ValueError):
                row["fouls"] = None
            # Prefer the live_engine projected_final (uses residual heads, foul
            # trouble, blowout, heat-check, learned Q4 minutes). Fall back to
            # naive minutes-pacing if no engine projection exists for this row.
            pid_key = str(row.get("player_id"))
            nm_key = (row.get("player_name") or "").lower()
            paced_final: dict = {}
            for s in _BOX_STATS:
                eng = engine_projections.get((pid_key, s)) or engine_projections.get((nm_key, s))
                pf = None
                if eng and eng.get("projected_final") is not None:
                    try: pf = round(float(eng["projected_final"]), 1)
                    except (TypeError, ValueError): pf = None
                if pf is None and mp and mp > 1.0 and s in cur:
                    pf = round(cur[s] * (36.0 / mp), 1)
                if pf is not None:
                    paced_final[s] = pf
            if paced_final:
                row["paced_final"] = paced_final

    if live_overlay:
        attach_live(box.get("away"))
        attach_live(box.get("home"))
        box["live_available"] = True
        box["engine_projection_used"] = bool(engine_projections)

        # ── Bayesian shrinkage toward pregame q50 ─────────────────────────
        # Early in the game (low minutes_played), pace extrapolation is
        # dominated by noise — a star with 3 minutes and 0 PTS would project
        # to 0-PTS final, which is silly when his pregame median is 27. Blend
        # live extrapolation with the pregame q50 (the prior). Weight grows
        # with minutes: at 4 min ~90% pregame; at 14 min 50/50; at 24 min
        # ~93% live; at 36+ min ~100% live. See _live_shrink_weight.
        def _shrink_team(team_dict):
            if not team_dict or not team_dict.get("players"):
                return
            for row in team_dict["players"]:
                mp = row.get("minutes_played") or 0
                w_live = _live_shrink_weight(mp)
                row["_shrink_weight"] = round(w_live, 3)
                if w_live <= 0:
                    continue
                paced = row.get("paced_final") or {}
                for s in _BOX_STATS:
                    pregame_v = row.get(s)            # pregame q50 (cell value)
                    live_v = paced.get(s)             # live engine projection
                    if pregame_v is None or live_v is None:
                        continue
                    try:
                        blended = w_live * float(live_v) + (1.0 - w_live) * float(pregame_v)
                        paced[s] = round(blended, 1)
                    except (TypeError, ValueError):
                        continue
                if paced:
                    row["paced_final"] = paced

        _shrink_team(box.get("away"))
        _shrink_team(box.get("home"))

        # ── Pace-aware team total projection ──────────────────────────────
        # Sum of player paced_finals undershoots team totals during the
        # game because each player's projection has been shrunk toward q50
        # (the median). Real team totals are means, which are higher for
        # right-skewed scoring distributions.
        #
        # Build a separate team-total projection that uses:
        #   pace_extrap = current_team_pts × (48 / minutes_elapsed)
        # blended with the pregame team mean estimate.
        period_i = int(live_overlay.get("period") or 0)
        clock_min = _parse_clock_to_minutes(live_overlay.get("clock"))
        # Total game minutes elapsed: full periods done + (12 - clock) for current
        if period_i >= 1 and clock_min is not None:
            full_periods_done = max(0, period_i - 1)
            minutes_elapsed = full_periods_done * 12.0 + (12.0 - clock_min)
            minutes_elapsed = max(1.0, min(48.0, minutes_elapsed))
        else:
            minutes_elapsed = 0.0

        def _team_total_proj(team_dict):
            if not team_dict:
                return
            elapsed_frac = minutes_elapsed / 48.0
            current_totals: dict[str, float] = {}
            projected_totals: dict[str, float] = {}
            pace_extraps: dict[str, float] = {}
            for s in _BOX_STATS:
                cur_sum = 0.0
                any_v = False
                for row in team_dict.get("players") or []:
                    cur = row.get("current") or {}
                    v = cur.get(s)
                    if v is None:
                        continue
                    try:
                        cur_sum += float(v); any_v = True
                    except (TypeError, ValueError):
                        continue
                if any_v:
                    current_totals[s] = round(cur_sum, 1)
                pregame_mean = (team_dict.get("mean_totals") or {}).get(s)
                if not isinstance(pregame_mean, (int, float)):
                    pregame_mean = None
                pace_extrap = None
                if minutes_elapsed >= 1.0 and any_v and cur_sum > 0:
                    pace_extrap = cur_sum * (48.0 / minutes_elapsed)
                    pace_extraps[s] = round(pace_extrap, 1)
                # Blend pace × pregame mean by elapsed_frac. When elapsed_frac=0,
                # we trust pregame; when elapsed_frac=1, we trust the pace.
                if pace_extrap is not None and pregame_mean is not None:
                    projected = elapsed_frac * pace_extrap + (1.0 - elapsed_frac) * pregame_mean
                elif pace_extrap is not None:
                    projected = pace_extrap
                else:
                    projected = pregame_mean
                if projected is not None:
                    projected_totals[s] = round(float(projected), 1)
            team_dict["current_totals"] = current_totals
            team_dict["pace_extraps"] = pace_extraps
            team_dict["projected_totals"] = projected_totals
            # PTS-specific convenience fields (backward compat with JS pill)
            if "pts" in current_totals:
                team_dict["current_total_pts"] = current_totals["pts"]
            if "pts" in projected_totals:
                team_dict["projected_total_pts"] = projected_totals["pts"]
            if "pts" in pace_extraps:
                team_dict["pace_extrap_pts"] = pace_extraps["pts"]

        _team_total_proj(box.get("away"))
        _team_total_proj(box.get("home"))
    else:
        box["live_available"] = False
        box["engine_projection_used"] = False

    # Pregame win probability — projection-derived helper (see
    # _pregame_wp_from_projection for math). Stays consistent with the box
    # score and avoids the polarity-bug team-level model.
    p_home_pre = _pregame_wp_from_projection(date, away_a, home_a)
    if p_home_pre is not None:
        box["pregame_home_win_prob"] = round(p_home_pre, 3)
        box["pregame_away_win_prob"] = round(1.0 - p_home_pre, 3)
        box["pregame_wp_source"] = "projected_margin_shrunk"

    # Live win probability — call the appropriate snapshot booster for the
    # current period. Boosters are calibrated at end-of-period boundaries
    # (clock 0:00). We interpolate toward 0.5 (uninformative) when the clock
    # is far from the boundary, since the booster is out-of-distribution
    # mid-period and would otherwise be overconfident.
    if live_overlay and isinstance(live_overlay, dict):
        period_i = int(live_overlay.get("period") or 0)
        if period_i >= 1:
            snap_key = "endQ1" if period_i <= 1 else ("endQ2" if period_i == 2 else "endQ3")
            try:
                from src.prediction.inplay_winprob import (  # noqa: PLC0415
                    features_from_snapshot, predict_home_win_prob,
                    active_stack,
                )
                feats = features_from_snapshot(live_overlay)
                p_home_raw = predict_home_win_prob(feats, snapshot=snap_key)
                if p_home_raw is not None:
                    clock_min = _parse_clock_to_minutes(live_overlay.get("clock"))
                    p_home = _wp_interpolate_to_boundary(
                        float(p_home_raw), period_i, clock_min)
                    box["home_win_prob"] = round(p_home, 3)
                    box["away_win_prob"] = round(1.0 - p_home, 3)
                    box["winprob_snapshot"] = snap_key
                    box["winprob_raw_booster"] = round(float(p_home_raw), 3)
                    if clock_min is not None:
                        box["winprob_clock_minutes"] = round(clock_min, 2)
                    # Honest provenance: surface which artifact stack drove
                    # this probability so the UI tooltip / status pill can
                    # show the user it's the validated model, not v1 raw.
                    try:
                        stack = active_stack(snap_key)
                        box["winprob_stack"] = {
                            "layer": stack.get("layer"),
                            "detail": stack.get("detail"),
                            "components_loaded": {
                                "v6_hp": bool(stack.get("v6_hp_loaded")),
                                "iter62_iso": bool(stack.get("iter62_iso_loaded")),
                                "v7_bag5": bool(stack.get("v7_bag5_loaded")),
                                "meta_blend": bool(stack.get("meta_blend_loaded")),
                                "v3": bool(stack.get("v3_loaded")),
                                "v2": bool(stack.get("v2_loaded")),
                                "v1": bool(stack.get("v1_loaded")),
                            },
                        }
                    except Exception as _stack_exc:
                        import logging as _lg_stack  # noqa: PLC0415
                        _lg_stack.getLogger(__name__).warning(
                            "active_stack(%s) failed: %s", snap_key, _stack_exc)
            except Exception as exc:
                import logging as _lg3  # noqa: PLC0415
                _lg3.getLogger(__name__).warning(
                    "inplay_winprob failed: %s", exc)

    # Live-regraded bet snippets for this matchup. The JS poller inline-updates
    # the bet cards' EV / model_prob / side text so they don't go stale during
    # the game (without a full page reload).
    if engine_projections and game_id:
        try:
            slate_cur = _build_slate(date)
            sig_table = _stat_sigma_for_date(date)
            from api._courtvision_odds import resolve_game_id  # noqa: PLC0415
            alias_for_filter = resolve_game_id(game_id)
            canon_ids = alias_for_filter.get("canonical_ids", frozenset([game_id]))
            ab = (alias_for_filter.get("away_abbr") or "").upper()
            hb = (alias_for_filter.get("home_abbr") or "").upper()
            pair = frozenset([ab, hb]) if ab and hb else frozenset()

            def _in_game(b):
                if str(b.get("game_id", "")) in canon_ids:
                    return True
                if pair:
                    t = (b.get("team") or "").upper()
                    o = (b.get("opp") or "").upper()
                    if t in pair and o in pair:
                        return True
                return False

            import copy as _copy2  # noqa: PLC0415
            live_bets = []
            player_minutes = _shrink_player_minutes_from_snapshot(live_overlay or {})
            for b in slate_cur.get("bets", []):
                if not _in_game(b):
                    continue
                nm = (b.get("player_name") or "").lower()
                st = (b.get("prop_stat") or "").lower()
                eng = engine_projections.get((nm, st))
                if not eng or eng.get("projected_final") is None:
                    continue
                cp = _copy2.copy(b)
                # Apply minutes-based shrinkage so early-game projections blend
                # toward pregame q50 instead of trusting noisy extrapolation.
                mp = player_minutes.get(nm, 0.0)
                w_live = _live_shrink_weight(mp)
                live_q50_raw = float(eng["projected_final"])
                pregame_q50 = float(cp.get("q50") or live_q50_raw)
                shrunk_q50 = w_live * live_q50_raw + (1.0 - w_live) * pregame_q50
                try:
                    _regrade_bet_with_live_q50(cp, shrunk_q50, sig_table)
                except Exception:
                    continue
                live_bets.append({
                    "bet_id": cp.get("bet_id"),
                    "player_name": cp.get("player_name"),
                    "prop_stat": cp.get("prop_stat"),
                    "line": cp.get("line"),
                    "side": cp.get("side"),
                    "q50": cp.get("q50"),
                    "edge_units": cp.get("edge_units"),
                    "model_prob": cp.get("model_prob"),
                    "market_prob": cp.get("market_prob"),
                    "ev_pct": cp.get("ev_pct"),
                    "ev_capped": cp.get("ev_capped"),
                    "kelly_stake_dollars": cp.get("kelly_stake_dollars"),
                    "best_book": cp.get("best_book"),
                    "best_price": cp.get("best_price"),
                })
            if live_bets:
                box["live_bets"] = live_bets
        except Exception as exc:
            import logging as _lglb  # noqa: PLC0415
            _lglb.getLogger(__name__).warning(
                "live bets snippet build failed: %s", exc)

    box["date"] = date
    box["game_id"] = game_id
    box["generated_at"] = datetime.utcnow().isoformat() + "Z"
    return JSONResponse(box)


@router.get("/api/bet/{bet_id}", tags=["courtvision"])
def api_bet(bet_id: str, request: Request, date: str = Query(default_factory=_today_et),
            partial: int = 0):
    m = next((b for b in _build_slate(date)["bets"] if b["bet_id"] == bet_id), None)
    if m is None:
        if partial: return HTMLResponse('<div class="pending">not found</div>', 404)
        raise HTTPException(404, detail="bet not found")
    return (_TEMPLATES.TemplateResponse("_bet_card_reasoning.html",
            {"request": request, "bet": m}) if partial else JSONResponse(m))


@router.get("/api/parlays", tags=["courtvision"])
def api_parlays(date: Optional[str] = Query(default=None),
                seed: int = Query(0, ge=0, le=10**9)):
    # Same-book parlays, 2-3 legs auto-tuned, top 25 by EV. No knobs.
    if not date:
        date = _next_game_day() or _today_et()
    return JSONResponse(_build_parlays(date, seed=seed))


@router.get("/api/parlays/constructor", tags=["courtvision"])
def api_parlays_constructor(
    date: Optional[str] = Query(default=None),
    max_legs: int = Query(3, ge=2, le=5),
    min_ev_pct: float = Query(2.0, ge=-100.0, le=500.0),
    top_n: int = Query(25, ge=1, le=100),
    seed: int = Query(0, ge=0, le=10**9),
):
    """SGP-penalty parlay candidates from src.prediction.parlay_constructor.

    Returns ranked 3-leg combos with `expected_roi_sgp_pct`, `hit_rate_adj`,
    `decimal_odds`, `american_odds`, and per-leg dicts under leg_0/leg_1/leg_2.
    """
    if not date:
        date = _next_game_day() or _today_et()
    return JSONResponse(_build_parlays_constructor(date, max_legs, min_ev_pct, top_n, seed))


def _american_to_decimal(odds: int) -> float:
    return (odds / 100 + 1) if odds >= 0 else (-100 / odds + 1)


def _decimal_to_american(dec: float) -> int:
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


@router.post("/api/parlays/build", tags=["courtvision"])
def api_parlays_build(body: dict = Body(...)):
    """Compute combined American / decimal odds for an arbitrary set of legs.

    Body: {"legs": [{"player": str, "stat": str, "line": float,
                     "side": "over"|"under", "price": int}]}
    Returns: {"n_legs": int, "decimal": float, "american": int, "payout_100": float}
    """
    legs = body.get("legs") or []
    if not legs:
        raise HTTPException(status_code=422, detail="legs required: provide at least one leg")
    if len(legs) > 12:
        raise HTTPException(status_code=400, detail="max 12 legs")
    decimal = 1.0
    for leg in legs:
        price = leg.get("price")
        if price is None:
            raise HTTPException(status_code=422, detail=f"leg missing price: {leg}")
        try:
            decimal *= _american_to_decimal(int(price))
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise HTTPException(status_code=422, detail=f"invalid price {price}: {exc}") from exc
    american = _decimal_to_american(decimal)
    return JSONResponse({
        "n_legs": len(legs),
        "decimal": round(decimal, 6),
        "american": american,
        "payout_100": round((decimal - 1) * 100, 2),
        "legs": legs,
    })


@router.get("/api/auto_parlay", tags=["courtvision"])
def api_auto_parlay(date: str = Query(default_factory=_today_et),
                    stake: float = Query(20.0, ge=1.0, le=10000.0),
                    max_legs: int = Query(5, ge=2, le=5)):
    """Highest-EV parlay whose Kelly stake fits the requested $stake."""
    c = [p for p in _build_parlays(date, max_legs, 5.0, 0).get("parlays", [])
         if p["kelly_stake_dollars"] <= stake]
    return JSONResponse({"date": date, "stake": stake, "max_legs": max_legs,
                         "pick": c[0] if c else None, "n_candidates_under_stake": len(c)})


_SHARE_HIDE = ("kelly_stake_dollars", "kelly_pct", "market_prob", "model_prob")

@router.get("/share/{slug}", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def share(slug: str, request: Request):
    slate = _build_slate(slug)
    if not slate.get("bets"):
        raise HTTPException(status_code=404, detail="no slate for this slug")
    shown = [{k: v for k, v in b.items() if k not in _SHARE_HIDE}
             for b in slate["bets"][:_SHARE_TOP_N]]
    evs = [b.get("ev_pct") for b in shown if b.get("ev_pct") is not None]
    avg_ev = round(sum(evs) / len(evs), 2) if evs else 0.0
    from api._courtvision_data import share_text
    return _TEMPLATES.TemplateResponse("share.html",
        {"request": request, "slate": slate, "shown": shown,
         "avg_ev": avg_ev, "share_text": share_text(slate, shown)})


@router.get("/share/{slug}/qr.svg", tags=["courtvision"])
def share_qr(slug: str, request: Request):
    import io, qrcode
    from qrcode.image.svg import SvgPathImage
    base = _PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    q = qrcode.QRCode(box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(f"{base}/share/{slug}"); q.make(fit=True)
    buf = io.BytesIO(); q.make_image(image_factory=SvgPathImage).save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/healthz", tags=["courtvision"])
def healthz():
    from api._courtvision_data import healthz_payload
    return JSONResponse(healthz_payload(_ROOT, _latest_slate_date()))


@router.get("/help", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def help_page(request: Request):
    """About / Help page — explains CourtVision, model, and key terms."""
    return _TEMPLATES.TemplateResponse("help.html", {"request": request})


@router.get("/about", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def about_page(request: Request):
    """Alias for /help."""
    return RedirectResponse(url="/help", status_code=307)


@router.get("/games", tags=["courtvision"])
def games_alias(): return RedirectResponse(url="/tonight", status_code=302)


@router.get("/bets", tags=["courtvision"])
def bets_alias(): return RedirectResponse(url="/risk", status_code=302)


@router.get("/cv", tags=["courtvision"])
def cv_shortlink(): return RedirectResponse(url="/tonight", status_code=307)


@router.get("/api/odds/{date}.json", tags=["courtvision"])
def api_odds_for_date(date: str, stat: str = Query(""), player: str = Query("")):
    """Multi-book scraped prop odds for `date`. Filterable by stat + player."""
    from api._courtvision_odds import odds_env
    return JSONResponse(odds_env(date, stat, player))


_WITH_EV_CACHE: dict[str, tuple[float, dict]] = {}
_WITH_EV_TTL = 30.0


@router.get("/api/odds/with-ev/{date}.json", tags=["courtvision"])
def api_odds_with_ev(date: str, stat: str = Query(""), player: str = Query(""),
                     limit: int = Query(1000, ge=1, le=5000),
                     offset: int = Query(0, ge=0)):
    """Consolidated odds + model projection overlay (projection, edge, rec) for `date`.

    Falls back gracefully when predictions parquet missing — returns normal odds
    with None model fields. Never 500s due to missing predictions.
    Supports ?limit=N&offset=M for pagination (default limit=1000 = return all).
    Overlay result is cached for 30s per date (the parquet read is the hot path).
    """
    from api._courtvision_odds import odds_env
    from api._predictions_overlay import overlay_predictions

    # Cache the full overlay per date (stat/player filters applied after cache hit)
    cache_key = date
    cached = _WITH_EV_CACHE.get(cache_key)
    if cached is None or time.time() - cached[0] >= _WITH_EV_TTL:
        env_full = odds_env(date)
        try:
            env_full["props"] = overlay_predictions(date, env_full["props"])
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("overlay_predictions failed: %s", exc)

        # Stale-date fallback: if the requested date returned 0 props OR every
        # book's last_scrape timestamp belongs to a different calendar day,
        # redirect internally to the next slate with live data and attach a
        # `next_slate` hint so callers can surface the right date.
        _n_props = len(env_full.get("props") or [])
        _books = env_full.get("books") or []
        _all_stale = _n_props == 0 or all(
            (b.get("last_scrape") or "")[:10] != date for b in _books
        )
        if _all_stale:
            _next = _next_game_day() or _today_et()
            if _next != date:
                _fb_env = odds_env(_next)
                try:
                    _fb_env["props"] = overlay_predictions(_next, _fb_env["props"])
                except Exception:
                    pass
                _fb_env["next_slate"] = _next
                _fb_env["requested_date"] = date
                env_full = _fb_env
            else:
                env_full["next_slate"] = None
                env_full["requested_date"] = date
        else:
            env_full["next_slate"] = None

        _WITH_EV_CACHE[cache_key] = (time.time(), env_full)
    else:
        env_full = cached[1]

    # Apply stat/player filters and pagination on the cached result
    env = dict(env_full)
    props = list(env.get("props") or [])
    if stat:
        props = [p for p in props if p.get("stat") == stat.lower()]
    if player:
        pl = player.lower()
        props = [p for p in props if pl in p.get("player", "").lower()]
    total = len(props)
    if offset or limit < 5000:
        props = props[offset: offset + limit]
    env = dict(env)
    env["props"] = props
    env["n_props"] = total
    env["n_props_page"] = len(props)
    return JSONResponse(env)

@router.get("/api/odds", tags=["courtvision"])
def api_odds_today(stat: str = Query(""), player: str = Query("")):
    from api._courtvision_odds import odds_env
    date = _next_game_day() or _today_et()
    return JSONResponse(odds_env(date, stat, player))

# /odds page removed 2026-05-28 (user request: was broken and not useful).
# The /api/odds/* JSON endpoints remain — they back the homepage book filter
# and game-detail page. Only the standalone HTML page was deleted.

_NEXT_GAME_DAY_CACHE: tuple[float, Optional[str]] | None = None
_NEXT_GAME_DAY_TTL = 60.0  # recompute at most once per minute


def _next_game_day() -> Optional[str]:
    """Earliest distinct start_time date across all lines whose `start_time`
    is in the future. Cached for 60s — this function opens O(days × files)
    CSVs and is the root cause of slow TTFB when many line files are present.
    """
    global _NEXT_GAME_DAY_CACHE
    now_ts = time.time()
    if _NEXT_GAME_DAY_CACHE is not None and now_ts - _NEXT_GAME_DAY_CACHE[0] < _NEXT_GAME_DAY_TTL:
        return _NEXT_GAME_DAY_CACHE[1]

    from datetime import datetime, timezone, timedelta
    import csv as _csv
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    candidates: list[str] = []
    # Walk today + the next 14 days of line CSVs (scrapers store under the
    # scrape date, but props reference future start_times).
    for offset in range(0, 15):
        d = (now + timedelta(days=offset)).strftime("%Y-%m-%d")
        if not _LINES_DIR.exists():
            break
        for p in _LINES_DIR.iterdir():
            if not p.is_file() or p.suffix != ".csv":
                continue
            if not p.stem.startswith(f"{d}_"):
                continue
            try:
                with p.open(newline="", encoding="utf-8") as fh:
                    for r in _csv.DictReader(fh):
                        st = (r.get("start_time") or "").strip()
                        if len(st) < 10:
                            continue
                        # Parse the ISO date; only count games at or after today.
                        st_date = st[:10]
                        if st_date >= today:
                            candidates.append(st_date)
                        break  # one start_time per file is enough
            except OSError:
                continue
    result = min(candidates) if candidates else None
    _NEXT_GAME_DAY_CACHE = (now_ts, result)
    return result

@router.get("/api/docs", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def api_docs(request: Request):
    return _TEMPLATES.TemplateResponse("api_docs.html", {"request": request})

@router.get("/api/odds/best/{date}.json", tags=["courtvision"])
def api_odds_best(date: str):
    """Best (most favorable) book per (player, stat, line) per side."""
    from api._courtvision_odds import best_book_envelope
    return JSONResponse(best_book_envelope(date))

@router.get("/api/odds/history/{player}/{stat}", tags=["courtvision"])
def api_odds_history(player: str, stat: str,
                     date: str = Query(default_factory=_today_et)):
    """Every captured quote for one (player, stat) — useful for line-movement charts."""
    from api._courtvision_odds import line_history
    rows = line_history(date, player, stat)
    return JSONResponse({"date": date, "player": player, "stat": stat,
                         "n": len(rows), "history": rows})

def _spread_env(date: str, min_spread_pp: float) -> dict:
    from api._courtvision_odds import cross_book_spread
    rows = cross_book_spread(date, min_spread_pp=min_spread_pp)
    return {"date": date, "min_spread_pp": min_spread_pp, "n": len(rows),
            "n_arbs": sum(1 for r in rows if r["is_arb"]), "rows": rows}

@router.get("/api/odds/spread/{date}.json", tags=["courtvision"])
def api_odds_spread(date: str, min_spread_pp: float = Query(2.0, ge=0.0, le=50.0)):
    return JSONResponse(_spread_env(date, min_spread_pp))


@router.get("/api/odds/arbs/{date}.json", tags=["courtvision"])
def api_odds_arbs(
    date: str,
    max_age_sec: float = Query(60.0, ge=10.0, le=600.0,
                               description="Max seconds since capture to include a book in arb"),
    min_spread_pp: float = Query(2.0, ge=0.0, le=50.0),
    quality: str = Query("tight,loose",
                         description="Comma-separated arb_quality values to return (tight,loose,stale)"),
):
    """High-confidence arb opportunities only.

    Filters cross_book_spread results to rows with is_arb=True whose
    arb_quality is in the requested set. Default: tight + loose (omits stale).
    """
    from api._courtvision_odds import cross_book_spread
    allowed_quality = {q.strip().lower() for q in quality.split(",") if q.strip()}
    rows = cross_book_spread(date, min_spread_pp=min_spread_pp, max_age_sec=max_age_sec)
    arbs = [
        r for r in rows
        if r.get("is_arb")
        and r.get("arb_quality", "stale") in allowed_quality
    ]
    return JSONResponse({
        "date": date, "max_age_sec": max_age_sec,
        "min_spread_pp": min_spread_pp, "quality_filter": sorted(allowed_quality),
        "n_arbs": len(arbs), "arbs": arbs,
    })


@router.get("/api/odds/summary/{date}", tags=["courtvision"])
def api_odds_summary(date: str):
    """Compact day-level snapshot: counts, books, per-stat tally, freshness."""
    from api._courtvision_odds import summary
    return JSONResponse(summary(date))

@router.get("/api/odds/games/{date}", tags=["courtvision"])
def api_odds_games(date: str):
    """List distinct games in the day's odds data.

    Entries where the book-specific game_id cannot be resolved to real NBA team
    abbreviations are dropped (fail-closed). A WARNING is logged for each drop.
    """
    import logging as _log
    _logger = _log.getLogger(__name__)
    from api._courtvision_odds import games_index
    raw = games_index(date)
    resolved = []
    for g in raw:
        away = g.get("away_abbr", "")
        home = g.get("home_abbr", "")
        # Orphan: away_abbr is the raw game_id or either abbr is empty/generic
        _is_raw_id = away == g.get("game_id") or away in ("", "AWAY", "HOME") or home in ("", "AWAY", "HOME")
        if _is_raw_id:
            _logger.warning(
                "api_odds_games: dropping unresolvable game_id=%s (away_abbr=%r, home_abbr=%r)",
                g.get("game_id"), away, home,
            )
            continue
        resolved.append(g)
    return JSONResponse({"date": date, "games": resolved})

@router.get("/api/odds/freshness/{date}", tags=["courtvision"])
def api_odds_freshness(date: str):
    """Per-book CSV freshness: file mtime, latest captured_at, row count."""
    from api._courtvision_odds import freshness
    return JSONResponse(freshness(date))

@router.get("/api/odds/moves/{date}.json", tags=["courtvision"])
def api_odds_moves(date: str, window_minutes: int = Query(60, ge=5, le=720)):
    """Props whose line moved within `window_minutes` — live-day alerts."""
    from api._courtvision_odds import line_moves
    rows = line_moves(date, window_minutes=window_minutes)
    return JSONResponse({"date": date, "window_minutes": window_minutes,
                         "n": len(rows), "moves": rows})


# ── Steam / sharp-move endpoints ──────────────────────────────────────────────

def _read_steam_events_tail(hours: float = 12.0, max_bytes: int = 2 * 1024 * 1024) -> list:
    """Tail-read steam_events.jsonl without scanning the full file.

    Uses os.path.getsize to compute read offset so only trailing `max_bytes`
    are examined — safe on large audit files.
    """
    import os as _os
    import json as _json
    from datetime import datetime, timedelta, timezone
    path = _ROOT / "data" / "cache" / "steam_events.jsonl"
    if not path.exists():
        return []
    try:
        size = _os.path.getsize(str(path))
        offset = max(0, size - max_bytes)
        with open(path, "rb") as f:
            if offset:
                f.seek(offset)
                f.readline()  # skip possible partial first line after seek
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp()
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = _json.loads(line)
            ts_str = ev.get("ts", "")
            try:
                ev_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                ev_ts = 0.0
            if ev_ts >= cutoff_ts:
                events.append(ev)
        except (ValueError, KeyError):
            continue
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return events


@router.get("/api/steam/recent", tags=["courtvision"])
def api_steam_recent(hours: float = Query(12.0, ge=0.1, le=168.0)):
    """Recent sharp/steam move events emitted by steam_detector in the last N hours.

    Reads from data/cache/steam_events.jsonl using tail-read (no full scan).
    Returns events sorted newest-first.
    """
    events = _read_steam_events_tail(hours=hours)
    return JSONResponse({
        "window_hours": hours,
        "n_events": len(events),
        "events": events,
    })


@router.get("/api/odds/{date}.csv", tags=["courtvision"])
def api_odds_csv(date: str, stat: str = Query(""), player: str = Query("")):
    """CSV export of consolidated odds — one row per (player, stat, line, book)."""
    from api._courtvision_odds import consolidate_csv
    body = consolidate_csv(date, stat or None, player or None)
    return Response(content=body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="odds_{date}.csv"'})

# /arbs page removed 2026-05-28 (user request: cross-book arbitrage isn't
# the product anymore; users want direct "what bet to place" guidance per
# their selected books, not arb scanning).


@router.get("/api/today_summary", tags=["courtvision"])
def api_today_summary(date: str = Query(default=None), n: int = Query(3, ge=1, le=10)):
    # Use the same next-game-day fallback as /api/home.json and /tonight so that
    # off-day requests (e.g. 2026-05-28 with no slate) resolve to the next slate
    # that has live lines (e.g. 2026-05-29) rather than returning n_total:0.
    if date is None:
        date = _next_game_day() or _today_et()
    s = _build_slate(date); bets = s.get("bets", [])[:n]
    return JSONResponse({"date": s["date"], "generated_at": s["generated_at"],
        "n_total": s["summary"]["n_bets"], "avg_ev_pct": s["summary"]["avg_ev_pct"],
        "top": [{"player": b["player_name"], "team": b["team"], "opp": b["opp"],
                 "prop": f"{b['prop_stat']} {'o' if b['side']=='OVER' else 'u'}{b['line']:g}",
                 "ev_pct": b.get("ev_pct"), "book": b.get("best_book"),
                 "price": b.get("best_price")} for b in bets],
        "share_url": f"{_PUBLIC_BASE_URL or ''}/share/{s['date']}"})


@router.get("/api/clv/summary", tags=["courtvision"])
def api_clv_summary(days: int = Query(30, ge=1, le=365)):
    """Rolling CLV + P&L summary over the last N days.

    Reads data/clv/daily_clv.csv (written by nightly_grader) plus the raw
    per-game CLV JSON blobs in data/clv/ for by_book / by_stat breakdowns.

    Query params:
        days  — look-back window in days (default 30, max 365)

    Returns:
        {
            window_days, n_bets, n_days, total_stake, total_pnl, roi_pct,
            avg_clv_bps, win_pct, sharpe_30d,
            by_book: {book: {n_bets, roi_pct, avg_clv_bps}},
            by_stat: {stat: {n_bets, roi_pct, avg_clv_bps, win_pct}},
        }
    """
    import csv as _csv_mod  # noqa: PLC0415
    import json as _json     # noqa: PLC0415
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    from math import sqrt  # noqa: PLC0415

    clv_dir      = _ROOT / "data" / "clv"
    daily_csv    = clv_dir / "daily_clv.csv"
    cutoff       = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # ── Aggregate daily_clv.csv rows ──────────────────────────────────────────
    daily_rows: list = []
    if daily_csv.exists():
        try:
            with open(daily_csv, encoding="utf-8") as f:
                daily_rows = [r for r in _csv_mod.DictReader(f)
                              if r.get("date", "") >= cutoff]
        except Exception:
            daily_rows = []

    def _fsum(field: str) -> float:
        return sum(float(r.get(field) or 0) for r in daily_rows)

    n_days      = len(daily_rows)
    n_bets      = sum(int(r.get("n_bets") or 0) for r in daily_rows)
    total_stake = _fsum("total_stake")
    total_pnl   = _fsum("total_pnl")
    roi_pct     = round(100.0 * total_pnl / total_stake, 2) if total_stake else 0.0

    clv_vals    = [float(r.get("avg_clv_bps") or 0) for r in daily_rows]
    avg_clv_bps = round(sum(clv_vals) / len(clv_vals), 1) if clv_vals else 0.0

    win_vals    = [float(r.get("win_pct") or 0) for r in daily_rows]
    win_pct     = round(sum(win_vals) / len(win_vals), 2) if win_vals else 0.0

    sharpe_30d  = 0.0
    roi_list    = [float(r.get("roi_pct") or 0) for r in daily_rows]
    if len(roi_list) >= 2:
        mean_r = sum(roi_list) / len(roi_list)
        var_r  = sum((v - mean_r) ** 2 for v in roi_list) / (len(roi_list) - 1)
        sigma  = sqrt(var_r)
        sharpe_30d = round(mean_r / sigma, 4) if sigma > 0 else 0.0

    if not daily_rows:
        return JSONResponse({
            "window_days": days, "n_bets": 0, "n_days": 0,
            "total_stake": 0.0, "total_pnl": 0.0, "roi_pct": 0.0,
            "avg_clv_bps": 0.0, "win_pct": 0.0, "sharpe_30d": 0.0,
            "note": "no data yet — nightly_grader has not run for this window",
            "by_book": {}, "by_stat": {},
        })

    # ── by_book / by_stat from raw per-game CLV JSON blobs ───────────────────
    by_book: dict = {}
    by_stat: dict = {}

    if clv_dir.exists():
        for p in sorted(clv_dir.glob("*_clv.json")):
            # filename: <date>_<game_id>_clv.json  or  <date>_<game_id>_clv.json
            stem_parts = p.stem.split("_")
            date_part = stem_parts[0] if stem_parts else ""
            if date_part < cutoff:
                continue
            try:
                blob = _json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for bet in blob.get("bets", []):
                book = str(bet.get("book") or "unknown")
                stat = str(bet.get("stat") or "unknown")
                clv  = float(bet.get("clv_pct") or 0)

                # by_book aggregation
                bb = by_book.setdefault(book, {"n_bets": 0, "_sum_clv": 0.0})
                bb["n_bets"]   += 1
                bb["_sum_clv"] += clv

                # by_stat aggregation
                bs = by_stat.setdefault(stat, {"n_bets": 0, "_sum_clv": 0.0})
                bs["n_bets"]   += 1
                bs["_sum_clv"] += clv

    # Finalise derived fields and strip private accumulators
    for d in by_book.values():
        n = d["n_bets"]
        d["avg_clv_bps"] = round(d.pop("_sum_clv") / n * 100.0, 1) if n else 0.0

    for d in by_stat.values():
        n = d["n_bets"]
        d["avg_clv_bps"] = round(d.pop("_sum_clv") / n * 100.0, 1) if n else 0.0

    return JSONResponse({
        "window_days":  days,
        "n_bets":       n_bets,
        "n_days":       n_days,
        "total_stake":  round(total_stake, 2),
        "total_pnl":    round(total_pnl, 2),
        "roi_pct":      roi_pct,
        "avg_clv_bps":  avg_clv_bps,
        "win_pct":      win_pct,
        "sharpe_30d":   sharpe_30d,
        "by_book":      by_book,
        "by_stat":      by_stat,
    })


@router.get("/sse/live_edges", tags=["courtvision"])
async def sse_live_edges(request: Request):
    from api._courtvision_live import live_edge_stream
    return await live_edge_stream(request)

@router.get("/live", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def live(request: Request, date: str = Query(default_factory=_today_et)):
    return _TEMPLATES.TemplateResponse("live.html", {"request": request, "date": date})


@router.get("/api/plus_ev", tags=["courtvision"])
def api_plus_ev(date: str = Query(default_factory=_today_et),
                min_ev_pct: float = Query(2.0, ge=-100.0, le=500.0)):
    from api._courtvision_data import plus_ev_rows
    r = plus_ev_rows(_build_slate(date), min_ev_pct)
    return JSONResponse({"date": date, "n": len(r), "rows": r})


@router.get("/plus_ev", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def plus_ev(request: Request,
            date: str = Query(default_factory=_today_et),
            min_ev_pct: float = Query(2.0, ge=-100.0, le=500.0)):
    from api._courtvision_data import plus_ev_rows
    rows = plus_ev_rows(_build_slate(date), min_ev_pct)
    return _TEMPLATES.TemplateResponse("plus_ev.html",
        {"request": request, "date": date, "rows": rows, "min_ev_pct": min_ev_pct})


@router.get("/parlays", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def parlays(request: Request, date: str = Query(default=None)):
    """SSR-lite: sends only metadata shell; JS fetches /api/parlays after paint.

    Single-engine, same-book, auto-tuned leg-size. No user knobs.
    """
    if not date:
        date = _next_game_day() or _today_et()
    meta_envelope = {
        "date": date,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_parlays": None,
        "has_lines": True,
        "parlays": [],
        "ssr_lite": True,
        "is_playoff": _is_playoff_date(date),
    }
    return _TEMPLATES.TemplateResponse("parlays.html",
        {"request": request, "envelope": meta_envelope})


# ── SQLite-backed bet ledger endpoints ───────────────────────────────────────

def _get_db():
    """Lazy import so the DB is only loaded if these endpoints are called."""
    from database.bet_db import BetDB  # noqa: PLC0415
    return BetDB()


@router.get("/api/bets", tags=["courtvision"])
def api_bets(
    date:   Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    player: Optional[str] = Query(default=None),
    limit:  int           = Query(default=100, ge=1, le=1000),
):
    """List bets from the SQLite ledger. Filters: date, status, player (substring).

    Response shape is backwards-compatible with the previous CSV-reading version.
    Falls back to an empty list if the DB does not yet exist.
    """
    try:
        rows = _get_db().list_bets(date=date, status=status, player=player, limit=limit)
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("api_bets DB error: %s", exc)
        rows = []
    return JSONResponse({"bets": rows, "n": len(rows)})


@router.get("/api/bets/recent", tags=["courtvision"])
def api_bets_recent(n: int = Query(default=20, ge=1, le=200)):
    """Last N bets across all dates — for the bet-history widget on /odds."""
    try:
        rows = _get_db().recent_bets(n)
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("api_bets_recent DB error: %s", exc)
        rows = []
    return JSONResponse({"bets": rows, "n": len(rows)})


@router.get("/api/bankroll", tags=["courtvision"])
def api_bankroll():
    """Current bankroll snapshot + risk metrics.

    Returns:
        current       — latest recorded bankroll
        open_stake    — sum of pending bets
        available     — current − open_stake
        today_pnl     — settled P&L for today (UTC)
        today_stake   — total stake placed today
        drawdown_30d_pct — (HWM − current) / HWM × 100 over 30 days
        high_water_mark  — peak bankroll in last 90 days
    """
    try:
        db          = _get_db()
        current     = db.current_bankroll()
        open_stake  = db.open_bet_value()
        today       = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_sum   = db.daily_summary(today)
        hwm         = db.high_water_mark(90)
        drawdown    = db.drawdown_pct(30)
        return JSONResponse({
            "current":          round(current, 2),
            "open_stake":       round(open_stake, 2),
            "available":        round(current - open_stake, 2),
            "today_pnl":        today_sum.get("total_pnl", 0.0),
            "today_stake":      today_sum.get("total_stake", 0.0),
            "drawdown_30d_pct": drawdown,
            "high_water_mark":  round(hwm, 2),
        })
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("api_bankroll DB error: %s", exc)
        return JSONResponse({"error": str(exc), "current": 0.0,
                             "open_stake": 0.0, "available": 0.0,
                             "today_pnl": 0.0, "today_stake": 0.0,
                             "drawdown_30d_pct": 0.0, "high_water_mark": 0.0})
