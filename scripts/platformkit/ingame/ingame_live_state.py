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
    # {league} defaults to "atp" (unchanged single-league behavior for any caller that
    # does not go through _fetch_events's dual atp+wta merge, e.g. an explicit
    # league="wta" from a caller that already knows the tour).
    "tennis": {"path": "tennis/{league}", "kind": "tennis"},
}

# default ESPN league per soccer sport id when the caller omits an explicit league.
_SOCCER_DEFAULT_LEAGUE: Dict[str, str] = {"soccer": "eng.1", "soccer_intl": "fifa.world"}

# default ESPN tour path when a tennis caller passes no explicit league AND bypasses
# _fetch_events's dual-board merge (e.g. a direct _scoreboard_url call) -- keeps the
# prior hardcoded "tennis/atp" behavior as the single-league default.
_TENNIS_DEFAULT_LEAGUE = "atp"

# tennis has TWO tours sharing one ESPN sport id ("tennis/atp", "tennis/wta") but the
# in-play capture loop's DEFAULT_SPORTS/inplay_capture_loop keys BOTH tours under the
# single capture sport "tennis" (KXATPMATCH and KXWTAMATCH tickers alike) -- there is no
# per-tour sport id upstream to route on. So when the caller does not pin an explicit
# `league`, tennis fetches BOTH tour scoreboards and MERGES their flattened matches (an
# explicit league= still selects exactly that one tour, unchanged). Team sports (nba/mlb/
# soccer/soccer_intl) always use their single `_SPORTS[sport]["path"]` and are untouched
# by this -- this tuple is consulted ONLY when sport == "tennis" and league is None.
_TENNIS_LEAGUES: Tuple[str, ...] = ("atp", "wta")


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
    elif sport == "tennis":
        path = path.format(league=league or _TENNIS_DEFAULT_LEAGUE)
    return f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"


def _is_live(ev: dict) -> bool:
    st = (((ev.get("status") or {}).get("type")) or {})
    return bool(st.get("state") == "in") or str(st.get("name", "")).endswith("IN_PROGRESS")


def _tennis_matches(payload: dict) -> List[dict]:
    """Tennis' scoreboard is NOT flat like nba/mlb/soccer: each top-level event
    is a whole TOURNAMENT (no top-level `competitions`); real per-match
    competitions nest under event["groupings"][i]["competitions"] (verified
    live 2026-07-03: 1 tournament event, 5 groupings, 635 nested matches, 0
    top-level competitions). Flattens each match into a synthetic event dict
    so the rest of this module's flat-event code works UNCHANGED. Never raises."""
    return [{"id": m.get("id"), "status": m.get("status") or {}, "competitions": [m]}
            for ev in (payload.get("events") or [])
            for g in (ev.get("groupings") or [])
            for m in (g.get("competitions") or [])
            if isinstance(m, dict)]


def _events_for(sport: str, payload: dict) -> List[dict]:
    """Flat, per-match event dicts (tennis needs the groupings flatten)."""
    return _tennis_matches(payload) if sport == "tennis" else list(payload.get("events") or [])


def _competitors(ev: dict) -> Tuple[Optional[dict], Optional[dict]]:
    comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
    home = next((c for c in comps if c.get("homeAway") == "home"), None)
    away = next((c for c in comps if c.get("homeAway") == "away"), None)
    return home, away


def _name(c: Optional[dict]) -> str:
    """.team first (byte-identical for team sports); tennis carries .athlete
    instead of .team (verified live 2026-07-03) -- ADDITIVE fallback."""
    team = (c or {}).get("team") or {}
    val = team.get("abbreviation") or team.get("displayName")
    if val:
        return val
    athlete = (c or {}).get("athlete") or {}
    return athlete.get("shortName") or athlete.get("displayName") or ""


def _display(c: Optional[dict]) -> str:
    """Full display name, abbreviation as fallback. Tennis: athlete.displayName
    additive fallback (same team-first/athlete-fallback shape as _name)."""
    team_disp = ((c or {}).get("team") or {}).get("displayName")
    if team_disp:
        return team_disp
    athlete_disp = ((c or {}).get("athlete") or {}).get("displayName")
    return athlete_disp or _name(c)


def _score(c: Optional[dict]) -> Optional[float]:
    """.score first (team sports). Tennis competitors carry NO score field
    (verified live 2026-07-03) -- only per-set .linescores + a .winner bool;
    ADDITIVE fallback derives a sets-won count so tennis isn't just dropped."""
    try:
        return float((c or {}).get("score"))
    except (TypeError, ValueError):
        pass
    ls = (c or {}).get("linescores")
    if not isinstance(ls, list) or not ls:
        return None
    try:
        return float(sum(1 for s in ls if isinstance(s, dict) and s.get("winner")))
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


def _segment_fields(sport: str, ev: dict) -> Dict[str, object]:
    """Sport-aware game-state fields for the grade-row state_summary (period/inning/half/
    minute/set). These are the keys live_grade._state_summary and ingame_clv_per_segment.
    _infer_segment read -- without them every captured tick falls into the UNK bucket and
    score-margin / phase CLV cannot be measured. Best-effort; never raises."""
    status = (ev.get("status") or {})
    typ = (status.get("type") or {})
    out: Dict[str, object] = {}
    try:
        period = int(status.get("period") or 0)
    except (TypeError, ValueError):
        period = 0
    detail = str(typ.get("shortDetail") or typ.get("detail") or "").lower()
    if sport == "nba" and period > 0:
        out["period"] = period
    elif sport == "mlb" and period > 0:
        out["inning"] = period
        if detail.startswith("top") or " top" in detail:
            out["half"] = "top"
        elif "bot" in detail:
            out["half"] = "bottom"
    elif sport in ("soccer", "soccer_intl"):
        disp = str(status.get("displayClock") or "").replace("'", "").strip()
        try:
            out["minute"] = int(float(disp))
        except (TypeError, ValueError):
            pass
    elif sport == "tennis" and period > 0:
        out["set"] = period
    return out


def _neutral_site(sport: str, ev: dict) -> bool:
    """True iff the game is at a NEUTRAL venue (no home tilt). International soccer
    (World Cup / national-team tournaments) is neutral by default -- the intl predictor
    already prices it neutral=True, so the home/away labels are only pairing tags, NOT a
    home advantage. ESPN's competition.neutralSite is honored when present (it is often
    None for these), else soccer_intl defaults True. Other sports default False."""
    try:
        comp = (ev.get("competitions") or [{}])[0]
        flag = comp.get("neutralSite")
        if isinstance(flag, bool):
            return flag
    except Exception:  # noqa: BLE001
        pass
    return str(sport).lower() == "soccer_intl"


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
        # home_score/away_score ALIAS the goals under the names live_grade._state_summary
        # reads, so the captured state_summary carries real score (margin) instead of "live".
        "home_score": hs, "away_score": as_,
        "state_diff": float(hs - as_),  # signed toward home, matches offline ingest
        # neutral-site flag: True = no home advantage (World Cup / intl is neutral by
        # default). The home/away labels stay only as pairing tags; the intl model already
        # prices neutral=True, so this just makes that EXPLICIT instead of an implied home.
        "neutral": _neutral_site(sport, ev),
        "frac_elapsed": frac,
        "p0": p0v,            # leak-free pregame prior (auto-supplied when caller omits it)
        "p0_source": p0_src,  # 'CALLER' | 'PRIOR' | 'BASE_FALLBACK' (honest label)
        "status": str(st.get("shortDetail") or st.get("detail") or st.get("name", "")),
    }
    out.update(_segment_fields(sport, ev))  # period/inning/half/minute/set for segment CLV
    # DEEP in-game state (MLB): base-out + run-expectancy from the live situation block.
    # ADDITIVE (outs/base/bos/re keys); makes the captured series carry the high-signal
    # in-game variables a score+inning summary discards, so the data deepens every tick.
    # Best-effort, leak-free, never raises; {} for non-MLB or when no situation is present.
    try:
        from scripts.platformkit.ingame.ingame_baseout_mlb import baseout_summary_fields
        out.update(baseout_summary_fields(sport, ev))
    except Exception:  # noqa: BLE001 -- deep state is additive; never break capture
        pass
    return out


def _fetch_events(sport: str, league: Optional[str],
                  getter: Callable[[str], dict]) -> List[dict]:
    """Flat, per-match event dicts for *sport*, fetching a single league board -- EXCEPT
    tennis with no explicit `league`, which fetches BOTH tour boards (atp, wta) and merges
    their flattened matches (see _TENNIS_LEAGUES). An explicit league= (e.g. from a caller
    that already knows the tour) still fetches exactly that one board, unchanged. Team
    sports are always single-board, byte-identical to the prior behavior. Never raises
    (a per-league fetch error just contributes no events for that league)."""
    if sport == "tennis" and league is None:
        out: List[dict] = []
        for lg in _TENNIS_LEAGUES:
            try:
                payload = getter(_scoreboard_url(sport, lg))
                out.extend(_events_for(sport, payload))
            except Exception:  # noqa: BLE001 -- one tour's feed failing must not lose the other
                continue
        return out
    payload = getter(_scoreboard_url(sport, league))
    return _events_for(sport, payload)


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
    Tennis with no explicit `league` scans BOTH atp and wta boards (see _fetch_events).
    """
    if sport not in _SPORTS:
        return None
    getter = http_get or _http_get
    events = _fetch_events(sport, league, getter)
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
    match a Kalshi market's legs. Tennis with no explicit `league` merges BOTH atp+wta boards
    (see _fetch_events) so a WTA match's teams are also scannable -- inplay_capture_loop
    passes the bare capture sport "tennis" for both tours (KXATPMATCH and KXWTAMATCH alike),
    so this is the merge point that makes WTA games bridgeable at all. Leak-free + never
    raises (any error -> [])."""
    try:
        events = _fetch_events(sport, league, http_get or _http_get) if sport in _SPORTS else []
        out: List[Dict] = []
        for ev in events:
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
