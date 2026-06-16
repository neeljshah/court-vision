"""ESPN free-scoreboard feed normalizer for the live multi-sport board.

fetch_games(sport, *, leagues=None, timeout=8, _fixture_path=None) -> list[dict]
Each game: {sport, league, state, start_time, home_name, away_name,
home_score(int|None), away_score(int|None), period(int|None),
half(str|None 'top'/'bottom'), minute(float|None), clock_text(str),
market: {ml_home, ml_away, draw, total, provider}}.
NEVER raises on a bad/None field -> skips the game or returns [].
Source (verified 2026-06-15): ESPN site.api.espn.com scoreboard, no API key.
Tennis events are tournaments; matches live under groupings[].competitions[].
"""

import json
import urllib.request

_BASE = "https://site.api.espn.com/apis/site/v2/sports"

_SOCCER_DEFAULT_LEAGUES = ["eng.1", "esp.1", "ita.1", "ger.1", "usa.1",
                           "uefa.champions", "fifa.world"]
_TENNIS_DEFAULT_TOURS = ["atp", "wta"]

_UA = {"User-Agent": "Mozilla/5.0 (live-board)"}


def _urls(sport, leagues):
    s = (sport or "").lower()
    if s == "mlb":
        return [("mlb", _BASE + "/baseball/mlb/scoreboard")]
    if s == "soccer":
        lgs = leagues or _SOCCER_DEFAULT_LEAGUES
        return [(lg, _BASE + "/soccer/%s/scoreboard" % lg) for lg in lgs]
    if s == "tennis":
        lgs = leagues or _TENNIS_DEFAULT_TOURS
        return [(lg, _BASE + "/tennis/%s/scoreboard" % lg) for lg in lgs]
    return []


def _get_json(url, timeout):
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _as_int(v):
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except Exception:
        return None


def _as_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _g(d, *keys, default=None):
    """Nested safe get: _g(d,'a','b') == d['a']['b'] or default."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _ml_str(v):
    """American moneyline int -> display string ('-115' / '+120')."""
    if v is None:
        return None
    return ("+%d" % v) if v > 0 else ("%d" % v)


def _parse_market(competition):
    out = {"ml_home": None, "ml_away": None, "draw": None,
           "total": None, "provider": None, "details": None, "odds_text": None}
    odds = competition.get("odds") if isinstance(competition, dict) else None
    if not odds or not isinstance(odds, list):
        return out
    o = odds[0]
    if not isinstance(o, dict):
        return out
    out["ml_home"] = _as_int(_g(o, "homeTeamOdds", "moneyLine"))
    out["ml_away"] = _as_int(_g(o, "awayTeamOdds", "moneyLine"))
    out["draw"] = _as_int(_g(o, "drawOdds", "moneyLine"))
    out["total"] = _as_float(o.get("overUnder"))
    out["details"] = o.get("details") if isinstance(o.get("details"), str) else None
    out["provider"] = _g(o, "provider", "name")
    # Compact market-line display for the board: full moneylines if present, else the
    # raw ESPN 'details' favorite string (e.g. 'IRN -115'), else the total only.
    mls = [_ml_str(out["ml_home"]), _ml_str(out["draw"]), _ml_str(out["ml_away"])]
    mls = [m for m in mls if m]
    if len(mls) >= 2:
        out["odds_text"] = " / ".join(mls)
    elif out["details"]:
        out["odds_text"] = out["details"]
    elif out["total"] is not None:
        out["odds_text"] = "O/U %.1f" % out["total"]
    return out


def _comp_name(comp):
    team = comp.get("team") if isinstance(comp, dict) else None
    if isinstance(team, dict) and team.get("displayName"):
        return team.get("displayName")
    ath = comp.get("athlete") if isinstance(comp, dict) else None
    if isinstance(ath, dict) and ath.get("displayName"):
        return ath.get("displayName")
    return None


def _tennis_set_score(comp):
    """Return current games-per-set summary string from linescores."""
    ls = comp.get("linescores") if isinstance(comp, dict) else None
    if not isinstance(ls, list) or not ls:
        return None
    parts = []
    for s in ls:
        if isinstance(s, dict):
            v = s.get("value")
            if v is not None:
                try:
                    parts.append(str(int(v)))
                except Exception:
                    pass
    return " ".join(parts) if parts else None


def _sides(competitors):
    """Return (home_comp, away_comp). Falls back to order if homeAway absent."""
    home = away = None
    for c in competitors or []:
        ha = c.get("homeAway") if isinstance(c, dict) else None
        if ha == "home" and home is None:
            home = c
        elif ha == "away" and away is None:
            away = c
    if home is None or away is None:
        lst = [c for c in (competitors or []) if isinstance(c, dict)]
        if len(lst) >= 2:
            home = home or lst[0]
            away = away or lst[1]
    return home, away


def _mlb_half(short_detail):
    sd = (short_detail or "").strip().lower()
    if sd.startswith("top") or sd.startswith("beg"):
        return "top"
    if sd.startswith("bot") or sd.startswith("end") or sd.startswith("mid"):
        return "bottom"
    return None


def _norm_team_game(sport, league, event, competition):
    status = event.get("status") or {}
    st_type = status.get("type") or {}
    state = st_type.get("state")
    short = st_type.get("shortDetail")
    competitors = competition.get("competitors") or []
    home, away = _sides(competitors)
    if home is None or away is None:
        return None
    hn, an = _comp_name(home), _comp_name(away)
    if not hn or not an:
        return None
    period = _as_int(status.get("period"))
    minute = None
    half = None
    if sport == "mlb":
        half = _mlb_half(short)
    elif sport == "soccer":
        clk = _as_float(status.get("clock"))
        minute = clk / 60.0 if clk is not None else None
    if sport == "mlb":
        # shortDetail ('Bot 7th') is more informative than displayClock ('0:00').
        clock_text = short or status.get("displayClock") or ""
    else:
        clock_text = status.get("displayClock") or short or ""
    return {
        "sport": sport,
        "league": league,
        "state": state,
        "start_time": event.get("date") or competition.get("date"),
        "home_name": hn,
        "away_name": an,
        "home_score": _as_int(home.get("score")),
        "away_score": _as_int(away.get("score")),
        "period": period,
        "half": half,
        "minute": minute,
        "clock_text": str(clock_text),
        "market": _parse_market(competition),
    }


def _norm_tennis_match(league, event, competition):
    status = competition.get("status") or event.get("status") or {}
    st_type = status.get("type") or {}
    state = st_type.get("state")
    short = st_type.get("shortDetail")
    competitors = competition.get("competitors") or []
    home, away = _sides(competitors)
    if home is None or away is None:
        return None
    hn, an = _comp_name(home), _comp_name(away)
    if not hn or not an:
        return None
    # Tennis: score lives in linescores (games per set); flatten to a string.
    hs = _tennis_set_score(home)
    as_ = _tennis_set_score(away)
    return {
        "sport": "tennis",
        "league": league,
        "state": state,
        "start_time": competition.get("date") or event.get("date"),
        "home_name": hn,
        "away_name": an,
        "home_score": hs,
        "away_score": as_,
        "period": _as_int(status.get("period")),
        "half": None,
        "minute": None,
        "clock_text": str(short or ""),
        "market": _parse_market(competition),
    }


def _normalize_payload(sport, league, data):
    out = []
    events = (data or {}).get("events")
    if not isinstance(events, list):
        return out
    for ev in events:
        if not isinstance(ev, dict):
            continue
        try:
            if sport == "tennis":
                groupings = ev.get("groupings")
                if isinstance(groupings, list) and groupings:
                    for grp in groupings:
                        if not isinstance(grp, dict):
                            continue
                        for comp in grp.get("competitions") or []:
                            if not isinstance(comp, dict):
                                continue
                            row = _norm_tennis_match(league, ev, comp)
                            if row:
                                out.append(row)
                    continue
                # Fallback: some tennis events expose top-level competitions.
                for comp in ev.get("competitions") or []:
                    if isinstance(comp, dict):
                        row = _norm_tennis_match(league, ev, comp)
                        if row:
                            out.append(row)
            else:
                comps = ev.get("competitions") or []
                if not comps or not isinstance(comps[0], dict):
                    continue
                row = _norm_team_game(sport, league, ev, comps[0])
                if row:
                    out.append(row)
        except Exception:
            # One bad event must never sink the whole feed.
            continue
    return out


def fetch_games(sport, *, leagues=None, timeout=8, _fixture_path=None):
    """Fetch + normalize ESPN scoreboard games for a sport.

    sport: 'mlb' | 'soccer' | 'tennis'
    leagues: optional list of league/tour slugs (soccer/tennis).
    _fixture_path: when given, load this JSON file instead of the network
        (used for offline tests). The fixture is one ESPN payload; its games
        are tagged with the first configured league for the sport.
    """
    s = (sport or "").lower()
    if _fixture_path is not None:
        try:
            with open(_fixture_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return []
        urls = _urls(s, leagues)
        league = urls[0][0] if urls else s
        return _normalize_payload(s, league, data)

    rows = []
    for league, url in _urls(s, leagues):
        data = _get_json(url, timeout)
        if data is None:
            continue
        rows.extend(_normalize_payload(s, league, data))
    return rows
