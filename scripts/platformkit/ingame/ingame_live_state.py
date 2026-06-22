"""scripts.platformkit.ingame.ingame_live_state -- extract LIVE (state_diff,
frac_elapsed, p0) for an in-progress game from the keyless ESPN feed.

This is the LIVE counterpart to each sport's offline ingest_*states*.py. It reuses the
SAME ESPN scoreboard/summary conventions and the SAME state encoding (signed home-side
diff + frac_elapsed denominator) as the offline ingest so the served model sees inputs
on the corpus's scale. It does NOT duplicate ingest logic beyond the small live read.

  live_state(sport, event_id=None, *, http_get=None, p0=None) -> dict | None
     If event_id is None, scan the sport's scoreboard for an IN-PROGRESS event.
     Returns {sport, game_id, home, away, state_diff, frac_elapsed, p0, status}
     or None if nothing live / state unreadable. NEVER fabricates.

p0 is the leak-free pregame prior. If a caller passes it, it is used as-is. Otherwise
live_state now AUTO-SUPPLIES it from live_p0.p0_for (reads the canonical pregame snapshot
data/frontend/predict_service/<sport>/latest.json, READ-only) so the served / paired
in-game number CARRIES THE PROVEN PRIOR instead of silently degrading to BASE. p0 is
pregame -> leak-free. When no pregame snapshot exists, p0 stays None and serve_ingame
degrades to BASE honestly (labelled). ASCII only; stdlib + urllib; no src/kernel/api imports.

CLI: python -m scripts.platformkit.ingame.ingame_live_state <sport> [event_id] [p0]
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# per-sport ESPN path + frac_elapsed denominator semantics
_SPORTS: Dict[str, Dict] = {
    "nba": {"path": "basketball/nba", "kind": "clock", "reg_sec": 2880.0},
    "mlb": {"path": "baseball/mlb", "kind": "innings", "denom_half": 18.0},
    "soccer": {"path": "soccer/{league}", "kind": "minutes", "total_min": 90.0},
    # soccer_intl = the in-play capture loop's WC/international sport id; same ESPN soccer
    # scoreboard + minutes semantics, but the league defaults to fifa.world (World Cup) so
    # the in-game daytrader can pair the calibrated 1X2 model (p_home_win) with the live
    # Kalshi WC moneyline. Without this key live_state returned None -> "no_live_state".
    "soccer_intl": {"path": "soccer/{league}", "kind": "minutes", "total_min": 90.0},
    "tennis": {"path": "tennis/atp", "kind": "tennis"},
}

# default ESPN league per soccer sport id when the caller omits an explicit league.
_SOCCER_DEFAULT_LEAGUE: Dict[str, str] = {"soccer": "eng.1", "soccer_intl": "fifa.world"}


def _http_get(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=14) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return {}


def _scoreboard_url(sport: str, league: Optional[str]) -> str:
    path = _SPORTS[sport]["path"]
    if sport in _SOCCER_DEFAULT_LEAGUE:
        path = path.format(league=league or _SOCCER_DEFAULT_LEAGUE[sport])
    return f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"


def _is_live(ev: dict) -> bool:
    st = (((ev.get("status") or {}).get("type")) or {})
    return bool(st.get("state") == "in") or str(st.get("name", "")).endswith("IN_PROGRESS")


def _competitors(ev: dict) -> Tuple[Optional[dict], Optional[dict]]:
    comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
    home = next((c for c in comps if c.get("homeAway") == "home"), None)
    away = next((c for c in comps if c.get("homeAway") == "away"), None)
    return home, away


def _name(c: Optional[dict]) -> str:
    return ((c or {}).get("team") or {}).get("abbreviation") or \
        ((c or {}).get("team") or {}).get("displayName", "")


def _display(c: Optional[dict]) -> str:
    """Full display name (for cross-provider team matching), abbreviation as fallback."""
    return ((c or {}).get("team") or {}).get("displayName") or _name(c)


def _score(c: Optional[dict]) -> Optional[float]:
    try:
        return float((c or {}).get("score"))
    except (TypeError, ValueError):
        return None


def _frac_elapsed(sport: str, ev: dict) -> Optional[float]:
    """Sport-specific completed-fraction from the live status block. None if unreadable."""
    st = (ev.get("status") or {})
    typ = (st.get("type") or {})
    cfg = _SPORTS[sport]
    if sport == "nba":
        # period 1..4 (+OT); clock counts down within a 12-min quarter.
        period = int(st.get("period") or 0)
        clock = float(st.get("clock") or 0.0)  # seconds left in period
        if period <= 0:
            return None
        elapsed = (period - 1) * 720.0 + (720.0 - min(720.0, clock))
        return max(0.0, min(1.0, elapsed / cfg["reg_sec"]))
    if sport == "mlb":
        period = int(st.get("period") or 0)  # inning number
        if period <= 0:
            return None
        half = (1 if str(typ.get("shortDetail", "")).lower().startswith("top") else 2)
        return max(0.0, min(1.0, (2 * (period - 1) + half) / cfg["denom_half"]))
    if sport in ("soccer", "soccer_intl"):
        # displayClock like "57'" -> minute elapsed
        disp = str(st.get("displayClock") or "").replace("'", "").strip()
        try:
            minute = float(disp)
        except ValueError:
            minute = float(st.get("clock") or 0.0) / 60.0 if st.get("clock") else None
        if minute is None:
            return None
        return max(0.0, min(1.0, minute / cfg["total_min"]))
    if sport == "tennis":
        # tennis has no clock; fraction is unavailable from scoreboard -> None.
        return None
    return None


def _resolve_p0(sport: str, game_id: str, p0: Optional[float],
                p0_provider: Optional[Callable],
                home: Optional[str] = None,
                away: Optional[str] = None) -> Tuple[Optional[float], str]:
    """Resolve the leak-free pregame prior + its honest source label.

    If the caller passed an explicit p0 it WINS (source 'CALLER'). If a p0_provider is
    INJECTED (tests) it is consulted by exact game_id -> 'PRIOR'/'BASE_FALLBACK' (unchanged).
    Otherwise (production) we use live_p0.live_p0_resolved, which matches the pregame
    snapshot by exact game_id first ('PRIOR') and, on a miss, by a UNIQUE leak-free team
    match ('PRIOR_TEAMS') -- bridging the ESPN-vs-fallback-provider id gap so the served
    number carries the PROVEN prior for more games. Absent -> (None, 'BASE_FALLBACK') so
    serve_ingame degrades to BASE honestly. Never raises (any error -> BASE).
    """
    if p0 is not None:
        return float(p0), "CALLER"
    if not game_id:
        return None, "BASE_FALLBACK"
    try:
        if p0_provider is not None:
            val = p0_provider(sport, game_id)
            return (None, "BASE_FALLBACK") if val is None else (float(val), "PRIOR")
        from scripts.platformkit.ingame.live_p0 import live_p0_resolved
        res = live_p0_resolved(sport, game_id, home=home, away=away)
        val = res.get("p0")
        if val is None:
            return None, "BASE_FALLBACK"
        return float(val), str(res.get("source") or "PRIOR")
    except Exception:  # noqa: BLE001 -- a prior miss is BASE, never a crash
        return None, "BASE_FALLBACK"


def _extract(sport: str, ev: dict, p0: Optional[float],
             p0_provider: Optional[Callable] = None) -> Optional[Dict]:
    home, away = _competitors(ev)
    hs, as_ = _score(home), _score(away)
    if hs is None or as_ is None:
        return None
    frac = _frac_elapsed(sport, ev)
    st = ((ev.get("status") or {}).get("type") or {})
    game_id = str(ev.get("id", ""))
    p0v, p0_src = _resolve_p0(sport, game_id, p0, p0_provider,
                              home=_display(home), away=_display(away))
    out = {
        "sport": sport, "game_id": game_id,
        "home": _name(home), "away": _name(away),
        # full display names + absolute scores are ADDITIVE (existing consumers read
        # state_diff/frac_elapsed): they let the in-game model_fn resolve corpus team ids
        # and feed predict_live the absolute score (a 2-2 and a 0-0 share a diff of 0 but
        # price very differently), not just the differential.
        "home_display": _display(home), "away_display": _display(away),
        "home_goals": hs, "away_goals": as_,
        "state_diff": float(hs - as_),  # signed toward home, matches offline ingest
        "frac_elapsed": frac,
        "p0": p0v,            # leak-free pregame prior (auto-supplied when caller omits it)
        "p0_source": p0_src,  # 'CALLER' | 'PRIOR' | 'BASE_FALLBACK' (honest label)
        "status": str(st.get("shortDetail") or st.get("detail") or st.get("name", "")),
    }
    return out


def live_state(sport: str, event_id: Optional[str] = None, *,
               league: Optional[str] = None,
               http_get: Optional[Callable] = None,
               p0: Optional[float] = None,
               p0_provider: Optional[Callable] = None) -> Optional[Dict]:
    """Return live (state_diff, frac_elapsed, p0) for an in-progress game, or None.

    If event_id is given, fetch that event from the scoreboard; else pick the first
    in-progress event. p0 (leak-free pregame prior): an explicit p0 WINS; otherwise it is
    AUTO-SUPPLIED from p0_provider (default live_p0.p0_for, READ-only on the pregame
    snapshot -> leak-free) so the served number carries the PROVEN prior, not BASE. The
    returned dict carries 'p0_source' ('CALLER'|'PRIOR'|'BASE_FALLBACK') as an honest label.
    """
    if sport not in _SPORTS:
        return None
    getter = http_get or _http_get
    payload = getter(_scoreboard_url(sport, league))
    events = payload.get("events") or []
    if event_id is not None:
        ev = next((e for e in events if str(e.get("id")) == str(event_id)), None)
        if ev is None:
            return None
        return _extract(sport, ev, p0, p0_provider)
    for ev in events:
        if _is_live(ev):
            res = _extract(sport, ev, p0, p0_provider)
            if res is not None:
                return res
    return None


def live_states(sport: str, *, league: Optional[str] = None,
                http_get: Optional[Callable] = None,
                p0_provider: Optional[Callable] = None) -> List[Dict]:
    """ALL in-progress games for *sport* (each a full live_state dict), [] if none.

    The single-game live_state matches by ESPN event id; the in-play capture loop instead
    keys games by their Kalshi ticker, which never equals the ESPN id -> it needs to bridge
    by TEAM. This returns every in-progress state so the caller can pick the one whose teams
    match a Kalshi market's legs. Leak-free + never raises (any error -> [])."""
    try:
        getter = http_get or _http_get
        payload = getter(_scoreboard_url(sport, league)) if sport in _SPORTS else {}
        out: List[Dict] = []
        for ev in (payload.get("events") or []):
            if not _is_live(ev):
                continue
            res = _extract(sport, ev, None, p0_provider)
            if res is not None:
                out.append(res)
        return out
    except Exception:  # noqa: BLE001 -- a scan error is no live games, never a crash
        return []


def main() -> None:
    import sys
    sport = sys.argv[1] if len(sys.argv) > 1 else "mlb"
    eid = sys.argv[2] if len(sys.argv) > 2 else None
    p0 = float(sys.argv[3]) if len(sys.argv) > 3 else None
    res = live_state(sport, eid, p0=p0)
    print(json.dumps(res, indent=2) if res else f"no live {sport} state found")


if __name__ == "__main__":
    main()
