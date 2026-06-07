"""/live/{game_id} per-game live projection panel.

Surfaces for every player in the game:
  * Pregame projection (q50) from data/cache/predictions_cache_<date>.parquet
  * Current actual (if a live boxscore is cached)
  * Pace-projected final (= current / minutes_played * projected_minutes)
  * Best current sportsbook line (from consolidate())
  * Edge vs line (= pace_projected - line) for the most-bet stat (PTS)

Read-only -- does NOT poll NBA API or write to disk.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_ROOT = Path(__file__).resolve().parent.parent

_PROJECTED_MINUTES_FALLBACK = 32.0  # rough average starter mp

# ── CV_QSHAPE_DECAY — mirror of W-015 for the pace_proj column ───────────────
# When ON, scales pace_proj by the same league-uniform quarter-shape decay
# factor as scripts/predict_in_game.py, so the live-page "pace_projected"
# column reflects the same Q4 rate reduction for PTS/AST/FG3M/REB.
# Byte-identical when OFF (factor = 1.0 for all stats).
_CV_QSHAPE_DECAY_ROUTER: bool = os.environ.get(
    "CV_QSHAPE_DECAY", "0"
).strip().lower() not in ("", "0", "false", "off")

# League per-minute rates by quarter (same as predict_in_game.py W-015)
_ROUTER_QSHAPE_RATES = {
    "pts":  {1: 0.4758, 2: 0.4727, 3: 0.4798, 4: 0.4586},
    "reb":  {1: 0.1880, 2: 0.1845, 3: 0.1803, 4: 0.1782},
    "ast":  {1: 0.1176, 2: 0.1113, 3: 0.1109, 4: 0.1001},
    "fg3m": {1: 0.0598, 2: 0.0559, 3: 0.0562, 4: 0.0512},
}
_ROUTER_QSHAPE_STATS = frozenset({"pts", "reb", "ast", "fg3m"})


def _router_qshape_factor(stat: str, period: int) -> float:
    """Quarter-shape decay factor for the router pace_proj column (W-015 mirror).

    Same formula as qshape_pace_factor() in predict_in_game.py but simplified:
    takes integer period only (no sub-quarter clock needed for the router path).
    Returns 1.0 for stats outside the target set or when no remaining quarters.
    """
    if not _CV_QSHAPE_DECAY_ROUTER or stat not in _ROUTER_QSHAPE_RATES:
        return 1.0
    rates = _ROUTER_QSHAPE_RATES[stat]
    p = max(1, int(period))
    elapsed_qs = list(range(1, p + 1))
    remaining_qs = list(range(p + 1, 5))
    if not remaining_qs:
        return 1.0
    mean_elapsed = sum(rates.get(q, 0.0) for q in elapsed_qs) / len(elapsed_qs)
    mean_remaining = sum(rates.get(q, 0.0) for q in remaining_qs) / len(remaining_qs)
    if mean_elapsed <= 0.0:
        return 1.0
    factor = mean_remaining / mean_elapsed
    return max(0.80, min(1.20, factor))


def _today_et() -> str:
    """Approximate ET date (UTC-4)."""
    return (datetime.now(timezone.utc) + timedelta(hours=-4)).strftime("%Y-%m-%d")


def _load_pregame_for_game(game_id: str, date: str) -> list[dict]:
    """Return pregame projection rows belonging to ``game_id``.

    The parquet itself has no ``game_id`` column, so we cross-reference
    with the per-date sportsbook consolidate() to learn which players are
    in this game, then filter the parquet by player name (case-insensitive).
    """
    try:
        import pandas as pd  # noqa: PLC0415
    except Exception:
        return []
    pq = _ROOT / "data" / "cache" / f"predictions_cache_{date}.parquet"
    if not pq.exists():
        return []
    try:
        df = pd.read_parquet(pq)
    except Exception:
        return []

    # Discover the player roster that maps to this game_id via the lines CSVs.
    players_in_game: set[str] = set()
    team_abbrevs: set[str] = set()
    try:
        from api._courtvision_odds import consolidate, resolve_game_id  # noqa: PLC0415
        for p in consolidate(date):
            if str(p.get("game_id") or "") == str(game_id):
                nm = (p.get("player") or "").strip().lower()
                if nm:
                    players_in_game.add(nm)
        # Resolve home/away team abbreviations from games_lookup so we can
        # filter by team when player-name lookup returns nothing.
        resolved = resolve_game_id(game_id)
        if resolved:
            for key in ("home_abbr", "away_abbr"):
                abbr = (resolved.get(key) or "").strip().upper()
                if abbr:
                    team_abbrevs.add(abbr)
    except Exception:
        players_in_game = set()
        team_abbrevs = set()

    if "player_name" not in df.columns:
        return []

    if players_in_game:
        # Primary filter: player names extracted from sportsbook lines.
        mask = df["player_name"].astype(str).str.strip().str.lower().isin(players_in_game)
        df = df[mask]
    elif team_abbrevs and "team" in df.columns:
        # Fallback: filter by the game's two team abbreviations.
        mask = df["team"].astype(str).str.strip().str.upper().isin(team_abbrevs)
        df = df[mask]
    else:
        # Neither player names nor team abbrevs are available — return empty
        # rather than the entire predictions_cache (508 players / 30 teams).
        return []

    cols = [c for c in ["player_id", "player_name", "team", "stat",
                        "q50", "q10", "q90", "sigma"] if c in df.columns]
    df = df[cols].copy()
    # Surface as ``player`` so downstream code (and the template) can stay generic.
    if "player_name" in df.columns:
        df = df.rename(columns={"player_name": "player"})
    return df.to_dict(orient="records")


def _load_live_boxscore(game_id: str) -> Optional[dict]:
    """Return live boxscore dict (or None) if a cache file exists.

    Order of preference:
      1. data/cache/boxscore_live/<game_id>.json (preferred — fresh in-play feed)
      2. data/cache/m2_family_predictions_<game_id>.json (in-play prediction snapshot)
    """
    p1 = _ROOT / "data" / "cache" / "boxscore_live" / f"{game_id}.json"
    if p1.exists():
        try:
            return json.loads(p1.read_text(encoding="utf-8"))
        except Exception:
            return None
    p2 = _ROOT / "data" / "cache" / f"m2_family_predictions_{game_id}.json"
    if p2.exists():
        try:
            return json.loads(p2.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _parse_minutes(raw) -> Optional[float]:
    """Coerce a minutes-played value (int, float, or 'MM:SS' string) to float."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if ":" in s:
            try:
                mm, ss = s.split(":", 1)
                return int(mm) + int(ss) / 60.0
            except Exception:
                return None
        try:
            return float(s)
        except Exception:
            return None
    return None


def _best_line_for_player(consolidated: list[dict], player: str, stat: str) -> Optional[dict]:
    """Return the consolidate() prop row for (player, stat) with the most books."""
    pl = (player or "").lower().strip()
    st = (stat or "").lower().strip()
    matching = [p for p in consolidated
                if (p.get("player") or "").lower().strip() == pl
                and (p.get("stat") or "").lower().strip() == st]
    if not matching:
        return None
    return max(matching, key=lambda p: len(p.get("books") or []))


def _extract_current_stat(live: Optional[dict], player_id, player_name: str, stat: str):
    """Pull current actual stat value + raw minutes string from a live cache shape."""
    if not live or not isinstance(live, dict):
        return None, None
    players = live.get("players") or live.get("boxscore") or live.get("rows") or []
    if not isinstance(players, list):
        return None, None
    pl_lower = (player_name or "").lower()
    pid = str(player_id or "")
    for lp in players:
        if not isinstance(lp, dict):
            continue
        match_id = pid and str(lp.get("player_id") or "") == pid
        match_nm = pl_lower and (
            (lp.get("player") or lp.get("name") or "").lower() == pl_lower
        )
        if not (match_id or match_nm):
            continue
        # Stat lookup — top-level first, then nested under "stats".
        cur = lp.get(stat)
        if cur is None:
            cur = (lp.get("stats") or {}).get(stat) if isinstance(lp.get("stats"), dict) else None
        mp_raw = lp.get("minutes") or lp.get("min") or lp.get("mp")
        return cur, mp_raw
    return None, None


def _build_payload(game_id: str, date: str) -> dict:
    """Compose the player projection table payload."""
    pregame = _load_pregame_for_game(game_id, date)
    live = _load_live_boxscore(game_id)

    consolidated: list[dict] = []
    try:
        from api._courtvision_odds import consolidate  # noqa: PLC0415
        consolidated = consolidate(date)
    except Exception:
        consolidated = []

    # W-015 (CV_QSHAPE_DECAY): extract live period for the shape factor.
    # When flag OFF, _router_qshape_factor always returns 1.0 (byte-identical).
    _live_period = 1
    if live and isinstance(live, dict):
        try:
            _live_period = max(1, int(live.get("period") or 1))
        except (TypeError, ValueError):
            _live_period = 1

    rows: list[dict] = []
    for r in pregame:
        player = r.get("player") or ""
        team = r.get("team") or ""
        stat = (r.get("stat") or "").lower()
        q50 = r.get("q50")
        q10 = r.get("q10")
        q90 = r.get("q90")

        current, mp_raw = _extract_current_stat(live, r.get("player_id"), player, stat)
        mp_float = _parse_minutes(mp_raw)

        pace_proj = None
        if current is not None and mp_float and mp_float > 1.0:
            try:
                # W-015: apply quarter-shape decay factor (1.0 when flag OFF)
                _qsf = _router_qshape_factor(stat, _live_period)
                pace_proj = round(
                    float(current) * (_PROJECTED_MINUTES_FALLBACK / mp_float) * _qsf,
                    2,
                )
            except Exception:
                pace_proj = None

        prop = _best_line_for_player(consolidated, player, stat)
        best_line = prop.get("line") if prop else None
        best_book = None
        if prop and prop.get("books"):
            # pick the book with the best (highest) over_price as a representative
            try:
                best_book_entry = max(
                    prop["books"],
                    key=lambda b: (b.get("over_price") or -10_000),
                )
                best_book = best_book_entry.get("display") or best_book_entry.get("book")
            except Exception:
                best_book = None

        edge = None
        if pace_proj is not None and best_line is not None:
            try:
                edge = round(pace_proj - float(best_line), 2)
            except Exception:
                edge = None

        rows.append({
            "player": player,
            "team": team,
            "stat": stat,
            "pregame_q50": q50,
            "pregame_q10": q10,
            "pregame_q90": q90,
            "current": current,
            "minutes_played": mp_float,
            "pace_projected": pace_proj,
            "best_line": best_line,
            "best_book": best_book,
            "edge_vs_line": edge,
        })

    # Sort by |edge| desc — rows with no edge fall to the bottom but remain visible.
    rows.sort(key=lambda r: (r["edge_vs_line"] is None, -abs(r["edge_vs_line"]) if r["edge_vs_line"] is not None else 0))

    return {
        "game_id": game_id,
        "date": date,
        "live_available": bool(live),
        "pregame_loaded": len(pregame) > 0,
        "n_rows": len(rows),
        "rows": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/live/{game_id}", tags=["live"])
def api_live_game(game_id: str, date: Optional[str] = Query(default=None)):
    """JSON payload powering /live/{game_id}."""
    if not date:
        date = _today_et()
    return JSONResponse(_build_payload(game_id, date))


@router.get("/live/{game_id}", response_class=HTMLResponse, tags=["live"])
def live_game_page(request: Request, game_id: str,
                   date: Optional[str] = Query(default=None)):
    """HTML companion to /live (date level) — per-game projection panel."""
    if not date:
        date = _today_et()
    payload = _build_payload(game_id, date)
    return _TEMPLATES.TemplateResponse(
        "live_game.html",
        {"request": request, "env": payload},
    )
