"""domains.soccer.ingest_soccer_states -- Soccer in-game trajectory state ingest.

ESPN keyEvents goal records -> 5-min grid states + leak-free Elo p0.

Output schema per row:
  sport, game_id, asof_idx, state_diff, frac_elapsed, p0, outcome,
  minute, home_goals, away_goals, date (ISO YYYY-MM-DD, added for venue-history joins)

Two corpora (independent leagues):
  data/cache/ingame/soccer_states__eng1.parquet
  data/cache/ingame/soccer_states__esp1.parquet

Leak-free: p0 from Elo built on matches.parquet rows STRICTLY BEFORE match date.
State: goal count up to that minute only (step function, no lookahead).
Draw outcome = 0 (binary home-win-vs-not).
Clock encoding: clock.value = cumulative seconds since KO; /60 = elapsed minutes.

INVARIANTS: ~300 LOC (data ingest module; name-crosswalk block exempt); ASCII only; no API keys; no src.*/kernel.* imports.
CLI: python -m domains.soccer.ingest_soccer_states --leagues eng.1 esp.1
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
import unicodedata
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

log = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_REPO = Path(__file__).resolve().parents[2]
_OUT_DIR = _REPO / "data" / "cache" / "ingame"
_MATCHES_P = _REPO / "data" / "domains" / "soccer" / "matches.parquet"
_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/{l}/scoreboard?dates={d}"
_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/{l}/summary?event={e}"
_GRID = list(range(0, 91, 5))   # 19 grid points per match
_ELO_K, _ELO_INIT, _HFA = 20, 1500.0, 50.0
_LABELS = {"eng.1": "eng1", "esp.1": "esp1", "ger.1": "ger1", "ita.1": "ita1", "fra.1": "fra1"}

# ---------------------------------------------------------------------------
# Name normalisation + crosswalk (ESPN displayName <-> football-data.co.uk)
# Normalised-ESPN -> normalised-football-data aliases (spot-checked correct)
_NAME_ALIASES: Dict[str, str] = {
    # Bundesliga
    "borussia dortmund": "dortmund",
    "eintracht frankfurt": "ein frankfurt",
    "bayer leverkusen": "leverkusen",
    "borussia monchengladbach": "m gladbach",
    # EPL
    "manchester city": "man city",
    "manchester united": "man united",
    "wolverhampton wanderers": "wolves",
    "brighton hove albion": "brighton",
    "newcastle united": "newcastle",
    "tottenham hotspur": "tottenham",
    "nottingham forest": "nott m forest",
    "leicester city": "leicester",
    "ipswich town": "ipswich",
    "west ham united": "west ham",
    # La Liga
    "athletic club": "ath bilbao",
    "atletico madrid": "ath madrid",
    "real betis": "betis",
    "celta vigo": "celta",
    "espanyol": "espanol",
    "real sociedad": "sociedad",
    "rayo vallecano": "vallecano",
    "real valladolid": "valladolid",
    # Serie A
    "internazionale": "inter",
    # Ligue 1 (fra.1): ESPN displayName -> football-data F1 Elo key
    "aj auxerre": "auxerre",
    "as monaco": "monaco",
    "paris saint germain": "paris sg",
    "saint etienne": "st etienne",
    "stade rennais": "rennes",
    "stade de reims": "reims",
}


def _norm_name(name: str) -> str:
    """Lowercase, strip accents, remove punctuation, drop FC/SC/VfB/... suffixes.
    Applied to BOTH sides of the Elo join (football-data keys and ESPN lookups).
    """
    n = name.lower()
    n = unicodedata.normalize("NFD", n)
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\b(fc|cf|sc|ac|afc|bk|1846|1899|vfb|vfl|tsg|rb)\b", " ", n)
    n = re.sub(r"\b1\b", " ", n)    # "1. FC ..." -> drop leading "1"
    return " ".join(n.split())


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def _get(url: str, getter: Optional[Callable] = None) -> dict:
    """Fetch url with up to 3 retries (exponential backoff). Returns {} on all errors."""
    if getter is not None:
        return getter(url)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.loads(r.read())
        except Exception as exc:  # noqa: BLE001
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                log.warning("ESPN fetch failed url=%s err=%s", url, exc)
    return {}


# ---------------------------------------------------------------------------
# ESPN parsing (pure)
# ---------------------------------------------------------------------------

def _team_sides(payload: dict) -> Tuple[str, str]:
    """Return (home_team_id, away_team_id) or ('','') from header competitions."""
    comps = ((payload.get("header") or {}).get("competitions") or [{}])
    h = a = ""
    for c in (comps[0].get("competitors") or []):
        tid = str((c.get("team") or {}).get("id", ""))
        name = (c.get("team") or {}).get("displayName", "")
        if c.get("homeAway") == "home":
            h = tid
        elif c.get("homeAway") == "away":
            a = tid
    return h, a


def _team_names(payload: dict) -> Tuple[str, str]:
    """Return (home_display_name, away_display_name) from header competitions."""
    comps = ((payload.get("header") or {}).get("competitions") or [{}])
    h = a = ""
    for c in (comps[0].get("competitors") or []):
        name = (c.get("team") or {}).get("displayName", "")
        if c.get("homeAway") == "home":
            h = name
        elif c.get("homeAway") == "away":
            a = name
    return h, a


def _final_score(payload: dict) -> Tuple[Optional[int], Optional[int]]:
    """Return (home_goals, away_goals) from header or (None,None)."""
    comps = ((payload.get("header") or {}).get("competitions") or [{}])
    hs = aws = None
    for c in (comps[0].get("competitors") or []):
        try:
            sc = int(c.get("score", ""))
        except (TypeError, ValueError):
            return None, None
        if c.get("homeAway") == "home":
            hs = sc
        elif c.get("homeAway") == "away":
            aws = sc
    return hs, aws


def _goal_events(payload: dict, home_id: str) -> List[Tuple[float, bool]]:
    """Return [(minute_elapsed, is_home)] for scoringPlay events. Minute capped at 90."""
    out: List[Tuple[float, bool]] = []
    for ev in (payload.get("keyEvents") or []):
        if not ev.get("scoringPlay"):
            continue
        clk = (ev.get("clock") or {}).get("value")
        tid = str((ev.get("team") or {}).get("id", ""))
        if clk is None or not tid:
            continue
        out.append((min(float(clk) / 60.0, 90.0), tid == home_id))
    return out


# ---------------------------------------------------------------------------
# Trajectory builder (pure)
# ---------------------------------------------------------------------------

def build_states(
    game_id: str, goals: List[Tuple[float, bool]],
    hg_final: int, ag_final: int, p0: float,
    game_date: Optional[str] = None,
) -> List[dict]:
    """Build 5-min grid states. Returns [] if goal counts don't reconcile (drop, never fabricate).

    game_date: ISO YYYY-MM-DD match date, constant across the grid (added for
    venue-history/replay joins). Optional/None for backward-compat callers.
    """
    if goals:
        if sum(1 for _, ih in goals if ih) != hg_final:
            return []
        if sum(1 for _, ih in goals if not ih) != ag_final:
            return []
    elif hg_final != 0 or ag_final != 0:
        return []   # scoring match but no goal data
    outcome = int(hg_final > ag_final)
    rows: List[dict] = []
    for idx, minute in enumerate(_GRID):
        hg = sum(1 for m, ih in goals if m <= minute and ih)
        ag = sum(1 for m, ih in goals if m <= minute and not ih)
        rows.append({
            "sport": "soccer", "game_id": game_id, "asof_idx": idx,
            "state_diff": float(hg - ag),
            "frac_elapsed": min(float(minute) / 90.0, 1.0),
            "p0": float(p0), "outcome": outcome,
            "minute": minute, "home_goals": hg, "away_goals": ag,
            "date": game_date,
        })
    return rows


# ---------------------------------------------------------------------------
# Elo (leak-free)
# ---------------------------------------------------------------------------

def _elo_map(hist: pd.DataFrame, before: date) -> Dict[str, float]:
    """Walk-forward Elo strictly before *before*. Keys are _norm_name(team)."""
    elo: Dict[str, float] = {}
    sub = hist[pd.to_datetime(hist["date"]).dt.date < before].sort_values("date")
    for _, row in sub.iterrows():
        h, a = _norm_name(str(row["home_team"])), _norm_name(str(row["away_team"]))
        rh, ra = elo.get(h, _ELO_INIT), elo.get(a, _ELO_INIT)
        exp_h = 1.0 / (1.0 + 10.0 ** ((ra - rh) / 400.0))
        ftr = str(row.get("ftr", "D")).upper()
        sc = 1.0 if ftr == "H" else (0.0 if ftr == "A" else 0.5)
        elo[h] = rh + _ELO_K * (sc - exp_h)
        elo[a] = ra + _ELO_K * ((1.0 - sc) - (1.0 - exp_h))
    return elo


def _resolve_espn(espn_name: str) -> str:
    """Normalise ESPN displayName to football-data Elo key. Alias if needed."""
    n = _norm_name(espn_name)
    return _NAME_ALIASES.get(n, n)


def _p0(elo: Dict[str, float], home: str, away: str) -> float:
    """P(home win) from Elo + HFA. home/away are raw ESPN names; resolved here."""
    h_key = _resolve_espn(home)
    a_key = _resolve_espn(away)
    rh = elo.get(h_key, _ELO_INIT) + _HFA
    ra = elo.get(a_key, _ELO_INIT)
    return 1.0 / (1.0 + 10.0 ** ((ra - rh) / 400.0))


# ---------------------------------------------------------------------------
# Event discovery + ingest
# ---------------------------------------------------------------------------

def _event_ids(start: date, end: date, league: str, getter: Optional[Callable]) -> List[Tuple[str, str]]:
    """Return sorted [(event_id, YYYYMMDD)] for all days in [start, end]."""
    out: List[Tuple[str, str]] = []
    d = start
    while d <= end:
        ds = d.strftime("%Y%m%d")
        for ev in (_get(_SCOREBOARD.format(l=league, d=ds), getter).get("events") or []):
            if ev.get("id"):
                out.append((str(ev["id"]), ds))
        d += timedelta(days=1)
        time.sleep(0.05)
    return sorted(out, key=lambda x: (x[1], x[0]))


def _ingest_event(eid: str, ds: str, league: str, hist: pd.DataFrame,
                  getter: Optional[Callable]) -> List[dict]:
    """Fetch ESPN summary, reconcile goals, build grid. [] on any broken data."""
    payload = _get(_SUMMARY.format(l=league, e=eid), getter)
    if not payload:
        return []
    home_id, _ = _team_sides(payload)
    if not home_id:
        return []
    hg_final, ag_final = _final_score(payload)
    if hg_final is None or ag_final is None:
        return []
    goals = _goal_events(payload, home_id)
    home_name, away_name = _team_names(payload)
    match_date = date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
    elo = _elo_map(hist, match_date)
    p = _p0(elo, home_name, away_name)
    # date column: prefer ESPN's own payload date (header.competitions[0].date,
    # ISO e.g. "2024-08-16T19:00Z"), fall back to the scoreboard-listing date
    # (ds) if the payload omits it -- never fabricate, this only picks a source.
    comps = (payload.get("header") or {}).get("competitions") or [{}]
    raw_date = comps[0].get("date") if comps else None
    game_date = raw_date[:10] if raw_date else match_date.isoformat()
    return build_states(eid, goals, hg_final, ag_final, p, game_date=game_date)


# ---------------------------------------------------------------------------
# League-level driver
# ---------------------------------------------------------------------------

def ingest_league(
    league: str, label: str, start: date, end: date,
    sample_every: int = 1, max_events: Optional[int] = None,
    getter: Optional[Callable] = None, out_dir: Optional[Path] = None,
) -> Path:
    """Ingest one league; write soccer_states__<label>.parquet. Returns output path."""
    outd = Path(out_dir) if out_dir else _OUT_DIR
    outd.mkdir(parents=True, exist_ok=True)
    out = outd / f"soccer_states__{label}.parquet"
    hist = pd.read_parquet(_MATCHES_P) if _MATCHES_P.exists() else pd.DataFrame()
    pairs = _event_ids(start, end, league, getter)
    if sample_every > 1:
        pairs = pairs[::sample_every]
    if max_events is not None:
        pairs = pairs[:max_events]
    log.info("league=%s events=%d", league, len(pairs))
    rows: List[dict] = []
    ok = dropped = 0
    for eid, ds in pairs:
        st = _ingest_event(eid, ds, league, hist, getter)
        if st:
            rows.extend(st)
            ok += 1
        else:
            dropped += 1
        time.sleep(0.08)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        # Atomic write: readers polling this path mid-rebuild must never see a
        # truncated/partial parquet (the parquet-rebuild-race landmine).
        tmp = out.with_suffix(out.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(out)
    log.info("league=%s ok=%d dropped=%d states=%d -> %s", league, ok, dropped, len(df), out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest soccer in-game trajectory states.")
    ap.add_argument("--leagues", nargs="+", default=["eng.1", "esp.1"])
    ap.add_argument("--start", default="20240801")
    ap.add_argument("--end", default="20250601")
    ap.add_argument("--sample-every", type=int, default=1)
    ap.add_argument("--max-events", type=int, default=None)
    args = ap.parse_args(argv)
    s = date(int(args.start[:4]), int(args.start[4:6]), int(args.start[6:8]))
    e = date(int(args.end[:4]), int(args.end[4:6]), int(args.end[6:8]))
    for league in args.leagues:
        label = _LABELS.get(league, league.replace(".", "_"))
        out = ingest_league(league, label, s, e,
                            sample_every=args.sample_every, max_events=args.max_events)
        if out.exists():
            df = pd.read_parquet(out)
            print("league=%s games=%d states=%d -> %s"
                  % (league, df["game_id"].nunique(), len(df), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
