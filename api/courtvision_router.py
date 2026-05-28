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
_BANKROLL_DEFAULT, _TOP_N, _TTL_SEC, _SHARE_TOP_N = 100.0, 15, 300, 8
_PUBLIC_BASE_URL = __import__("os").environ.get("COURTVISION_PUBLIC_URL", "").rstrip("/")
_STAT_SIGMA = {"pts": 8.5, "reb": 3.6, "ast": 2.6, "fg3m": 1.7, "stl": 1.4, "blk": 1.0, "tov": 1.7}  # MAE x 1.253 systematically understates real prop volatility (residuals are heavier-tailed than Normal + model has prediction uncertainty beyond residual MAE); 1.5x bump empirically caps confidence around 80-90% even on strong-edge bets, vs the prior 99%+ that produced fake +100% EVs
_STATS = tuple(_STAT_SIGMA.keys())

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
        bets = [grade_bet(ps_idx[(ln["player"].lower(), ln["stat"])], ln,
                          _STAT_SIGMA, _BANKROLL_DEFAULT)
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
        "has_lines": has_lines, "latest_available": _latest_slate_date(),
        "summary": {"n_bets": len(bets), "avg_ev_pct": round(sum(evs)/len(evs), 2) if evs else 0.0,
                    "n_over": sum(1 for b in bets if b["side"] == "OVER"),
                    "n_under": sum(1 for b in bets if b["side"] == "UNDER")},
        "bets": bets}
    _CACHE[cache_key] = (time.time(), envelope)
    return envelope


def _build_parlays(date: str, max_legs: int, min_ev_pct: float, seed: int = 0) -> dict:
    cache_key = ("parlays", date, max_legs, min_ev_pct, seed)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC: return entry[1]
    env = _build_slate(date); bets = env.get("bets", []); has_lines = env.get("has_lines", False)
    gen_at = datetime.utcnow().isoformat() + "Z"
    if not bets or not has_lines:
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0, "has_lines": has_lines, "parlays": []}
    else:
        from src.prediction.parlay_engine import ParlayEngine
        parlays = ParlayEngine(bets, rng_seed=seed).enumerate_parlays(max_legs=max_legs, min_ev_pct=min_ev_pct)
        out = {"date": date, "generated_at": gen_at, "n_parlays": len(parlays), "has_lines": True, "parlays": parlays}
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
    win_prob_away = _compute_win_prob(game_id, game_props,
                                      away_abbr=away_abbr, home_abbr=home_abbr)
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
            side: str = Query("ALL"), min_ev: float = Query(-999.0)):
    if not date:
        date = _next_game_day() or _today_et()
    slate = _build_slate(date)
    side_u = (side or "ALL").upper()
    if side_u in ("OVER", "UNDER") or min_ev > -999.0:
        bets = [b for b in slate["bets"]
                if (side_u == "ALL" or b["side"] == side_u)
                and (b.get("ev_pct") is None or b["ev_pct"] >= min_ev)]
        slate = {**slate, "bets": bets}
    return _TEMPLATES.TemplateResponse("tonight.html",
        {"request": request, "slate": slate, "side": side_u, "min_ev": min_ev})


@router.get("/api/slate", tags=["courtvision"])
def api_slate(date: str = Query(default=None)):
    # Apply next-game-day fallback so off-day requests resolve to the next live slate.
    if date is None:
        date = _next_game_day() or _today_et()
    return JSONResponse(_build_slate(date))


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
                max_legs: int = Query(5, ge=2, le=5),
                min_ev_pct: float = Query(5.0, ge=-100.0, le=500.0),
                seed: int = Query(0, ge=0, le=10**9)):
    # Use the same resolver as /parlays UI so the API + page always agree on date.
    if not date:
        date = _next_game_day() or _today_et()
    return JSONResponse(_build_parlays(date, max_legs, min_ev_pct, seed))


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
def parlays(request: Request,
            date: str = Query(default=None),
            max_legs: int = Query(5, ge=2, le=5),
            min_ev_pct: float = Query(5.0, ge=-100.0, le=500.0),
            limit: int = Query(25, ge=1, le=100),
            engine: str = Query(default="engine")):
    """SSR-lite: sends only metadata shell; JS fetches /api/parlays after paint.

    `engine` selects the model: "engine" (default, ParlayEngine MC) or
    "constructor" (parlay_constructor with 15% SGP penalty).
    """
    if not date:
        date = _next_game_day() or _today_et()
    engine_norm = "constructor" if engine == "constructor" else "engine"
    # Lightweight metadata only — avoids the heavy ParlayEngine on SSR.
    meta_envelope = {
        "date": date,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_parlays": None,    # filled by JS
        "has_lines": True,    # optimistic; JS corrects if false
        "parlays": [],        # client fetches
        "ssr_lite": True,
        "engine": engine_norm,
    }
    return _TEMPLATES.TemplateResponse("parlays.html",
        {"request": request, "envelope": meta_envelope,
         "shown": [], "leg_meta": {},
         "min_ev_pct": min_ev_pct, "max_legs": max_legs,
         "engine": engine_norm})


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
