"""scripts.platformkit.ingame.tick_segment_backfill -- LANE 5: deterministic
PAST-tick H1/H2 segment backfill for soccer_intl UNK-bucket games.

THE GAP: 22 soccer_intl games captured pre-fix carry bare state_summary="live"
on every tick -> ingame_clv_per_segment._infer_segment buckets all 4,416 of
their ticks into UNK. Lane 1 fixes FUTURE capture; this asks whether PAST
ticks can be segment-labeled WITHOUT FABRICATION using only each tick's own
capture ts (on disk) plus each game's ESPN kickoff time, recovered via ONE
bounded keyless scoreboard fetch per CALENDAR DATE (not per game -- one
date's scoreboard covers every game kicking off that date; 22 games span
only 6 dates).

METHOD: elapsed_min = (tick.ts - kickoff_utc) / 60. No true half-2-start
anchor exists on the ESPN payload (only a final completed status), so the
true 45-min mark's wall-clock position is uncertain by ~H1 stoppage (0-8 min)
+ halftime variance (nominal 15, commonly 12-20 min) -> worst case ~+/-10 min
around the naive kickoff+45 boundary. Ticks inside that band are EXCLUDED
(neither H1 nor H2), never guessed.

SIDECAR ONLY, never a raw-file mutation: writes ONE sidecar,
data/domains/soccer_intl/tick_segment_backfill.json ({game_id: {ts: label}});
never touches data/cache/ingame_grade/soccer_intl/*.jsonl. Any verdict
consuming it must tag segment_source="backfilled" so raw-vs-backfilled
verdicts are never conflated. No $ field; not an edge claim. No network at
import time (fetch is explicit + injectable).

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no data/registry write; never
raises out of its public entrypoints.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_tick_segment_backfill.py -q
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "soccer_intl"
DEFAULT_SIDECAR_PATH = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "tick_segment_backfill.json"

_UA = "curl/8.0"  # plain UA: ESPN 403s browser UAs from datacenter IPs (2026-08-31)
_TIMEOUT = 12
_SCOREBOARD_URL = ("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                    "fifa.world/scoreboard?dates={date}")

# +/- minutes around the naive kickoff+45 mark excluded as ambiguous (see
# module docstring); never guessed inside this band.
BOUNDARY_BUFFER_MIN: float = 10.0

_TICKER_RE = re.compile(r"^KXWCGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]{6})")
_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# Mirrors soccer_outcome.py's _CODE_OVERRIDES (independent local copy).
_CODE_OVERRIDES: Dict[str, str] = {
    "CIV": "Ivory Coast", "COD": "Congo DR", "COG": "Congo", "KOR": "South Korea",
    "PRK": "North Korea", "NED": "Netherlands", "ESP": "Spain", "SUI": "Switzerland",
    "USA": "United States", "CPV": "Cape Verde", "KSA": "Saudi Arabia",
    "NZL": "New Zealand", "CRC": "Costa Rica", "JPN": "Japan", "MAR": "Morocco",
    "BIH": "Bosnia-Herzegovina", "RSA": "South Africa", "UAE": "United Arab Emirates",
    "CHN": "China", "TPE": "Chinese Taipei", "GER": "Germany", "URU": "Uruguay",
    "DEN": "Denmark", "POR": "Portugal", "GRE": "Greece", "TUR": "Turkey",
    "SCO": "Scotland", "WAL": "Wales", "IRL": "Republic of Ireland",
    "AUT": "Austria", "AUS": "Australia", "DZA": "Algeria", "HTI": "Haiti",
    "IRQ": "Iraq", "IRI": "Iran",
}

HttpGet = Callable[[str], dict]

def _default_http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        logger.warning("tick_segment_backfill fetch failed url=%s err=%s", url, exc)
        return {}

def parse_ticker(ticker: str) -> Optional[Tuple[Any, str, str]]:
    """Kalshi WC ticker -> (date, code_a, code_b). None on no match, never a guess."""
    import datetime as _dt
    m = _TICKER_RE.match(str(ticker or "").strip().upper())
    if not m:
        return None
    yy, mon, dd, tail = m.groups()
    month = _MONTHS.get(mon)
    if month is None:
        return None
    try:
        date = _dt.date(2000 + int(yy), month, int(dd))
    except ValueError:
        return None
    return (date, tail[:3], tail[3:6])

def _code_matches(code: str, name_upper: str) -> bool:
    override = _CODE_OVERRIDES.get(code)
    if override is not None and override.upper() == name_upper:
        return True
    return name_upper[:3] == code

def fetch_kickoffs(dates: List[str], http_get: Optional[HttpGet] = None) -> List[dict]:
    """ESPN scoreboard events for each YYYYMMDD date (one call per date, not per game)."""
    getter = http_get or _default_http_get
    events: List[dict] = []
    for d in dates:
        events.extend(getter(_SCOREBOARD_URL.format(date=d)).get("events") or [])
    return events

def _event_names(ev: dict) -> Tuple[str, str]:
    comp = (ev.get("competitions") or [{}])[0]
    names: Dict[str, str] = {}
    for c in comp.get("competitors") or []:
        side = c.get("homeAway")
        nm = ((c.get("team") or {}).get("displayName") or "").strip().upper()
        if side and nm:
            names[side] = nm
    return names.get("home", ""), names.get("away", "")

def _parse_espn_ts(date_str: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None

def resolve_kickoff(ticker: str, events: List[dict]) -> Optional[Tuple[datetime, str]]:
    """(kickoff_utc, status) for *ticker* by unique code-pair match; None if unresolvable/ambiguous."""
    parsed = parse_ticker(ticker)
    if parsed is None:
        return None
    _date, code_a, code_b = parsed
    cands = []
    for ev in events:
        h, a = _event_names(ev)
        if not h or not a:
            continue
        if ((_code_matches(code_a, h) and _code_matches(code_b, a)) or
                (_code_matches(code_a, a) and _code_matches(code_b, h))):
            cands.append(ev)
    if len(cands) != 1:
        return None
    ev = cands[0]
    kickoff = _parse_espn_ts(ev.get("date") or "")
    if kickoff is None:
        return None
    comp = (ev.get("competitions") or [{}])[0]
    status = ((comp.get("status") or {}).get("type") or {}).get("name", "")
    return (kickoff, str(status))

def label_tick(ts: str, kickoff: datetime, *,
               buffer_min: float = BOUNDARY_BUFFER_MIN) -> Optional[str]:
    """H1/H2/None for one tick; None = too close to the boundary, excluded."""
    try:
        t = datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    elapsed_min = (t - kickoff).total_seconds() / 60.0
    if elapsed_min < 45.0 - buffer_min:
        return "H1"
    if elapsed_min > 45.0 + buffer_min:
        return "H2"
    return None

def backfill_game(ticker: str, ticks: List[dict], events: List[dict], *,
                   buffer_min: float = BOUNDARY_BUFFER_MIN) -> Dict[str, Any]:
    """Backfill one game: per-tick labels (by ts) + counts; unresolvable -> method="unresolved"."""
    resolved = resolve_kickoff(ticker, events)
    if resolved is None:
        return {"game_id": ticker, "method": "unresolved", "kickoff_utc": None,
                "labels": {}, "n_h1": 0, "n_h2": 0, "n_excluded": 0, "n_ticks": len(ticks)}
    kickoff, status = resolved
    labels: Dict[str, str] = {}
    n_h1 = n_h2 = n_excl = 0
    for r in ticks:
        ts = str(r.get("ts", ""))
        if not ts:
            continue
        lab = label_tick(ts, kickoff, buffer_min=buffer_min)
        if lab is None:
            n_excl += 1
            continue
        labels[ts] = lab
        if lab == "H1":
            n_h1 += 1
        else:
            n_h2 += 1
    return {"game_id": ticker, "method": "kickoff_plus_elapsed",
            "kickoff_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "espn_status": status, "buffer_min": buffer_min,
            "labels": labels, "n_h1": n_h1, "n_h2": n_h2, "n_excluded": n_excl,
            "n_ticks": len(ticks)}

def _is_unk_bucket(ticks: List[dict]) -> bool:
    """True iff every tick's state_summary is the bare 'live' sentinel."""
    return bool(ticks) and all(str(r.get("state_summary", "")).strip().lower() == "live" for r in ticks)

def find_unk_games(grade_dir: Optional[Path] = None) -> Dict[str, List[dict]]:
    """{ticker: ticks} for every UNK-bucket game on disk. Never raises."""
    base = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    out: Dict[str, List[dict]] = {}
    if not base.is_dir():
        return out
    for f in sorted(base.glob("*.jsonl")):
        if f.name.startswith("_"):
            continue
        try:
            rows = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except Exception as exc:  # noqa: BLE001
            logger.debug("find_unk_games: bad file %s: %s", f, exc)
            continue
        if _is_unk_bucket(rows):
            out[f.stem] = rows
    return out

def build_sidecar(grade_dir: Optional[Path] = None, http_get: Optional[HttpGet] = None,
                   *, buffer_min: float = BOUNDARY_BUFFER_MIN) -> Dict[str, Any]:
    """Full sidecar doc for every UNK-bucket game; one ESPN fetch per date spanned."""
    games = find_unk_games(grade_dir)
    dates: List[str] = []
    for ticker in games:
        parsed = parse_ticker(ticker)
        if parsed is None:
            continue
        date, _a, _b = parsed
        for delta in (-1, 0, 1):  # pad +/-1 day for date-boundary kickoffs (UTC roll)
            d = (date + timedelta(days=delta)).strftime("%Y%m%d")
            if d not in dates:
                dates.append(d)
    events = fetch_kickoffs(dates, http_get=http_get) if dates else []
    per_game: Dict[str, Any] = {}
    n_h1 = n_h2 = n_excl = n_unresolved = 0
    for ticker, ticks in games.items():
        doc = backfill_game(ticker, ticks, events, buffer_min=buffer_min)
        per_game[ticker] = doc
        if doc["method"] == "unresolved":
            n_unresolved += 1
        n_h1 += doc["n_h1"]; n_h2 += doc["n_h2"]; n_excl += doc["n_excluded"]
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component": "m_tick_segment_backfill",
        "method": "kickoff_plus_elapsed_minute",
        "buffer_min": buffer_min,
        "n_games": len(games), "n_games_unresolved": n_unresolved,
        "n_ticks_h1": n_h1, "n_ticks_h2": n_h2, "n_ticks_excluded": n_excl,
        "per_game": per_game,
        "segment_source": "backfilled",
        "note": ("Deterministic H1/H2 from tick ts vs ESPN kickoff time only -- NO true "
                 "half-2-start anchor exists, so ticks within buffer_min of the naive "
                 "kickoff+45 boundary are EXCLUDED, never guessed. Consumers MUST tag "
                 "any verdict using this sidecar segment_source='backfilled' so raw-vs-"
                 "backfilled verdicts stay comparable, never conflated. No $ field."),
    }

def write_sidecar(doc: Dict[str, Any], path: Optional[Path] = None) -> Path:
    p = Path(path) if path is not None else DEFAULT_SIDECAR_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)
    return p

def load_sidecar(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    p = Path(path) if path is not None else DEFAULT_SIDECAR_PATH
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("load_sidecar failed for %s: %s", p, exc)
        return None

def lookup_segment(sidecar: Dict[str, Any], game_id: str, ts: str) -> Optional[str]:
    """H1/H2 for one (game_id, ts) tick from a loaded sidecar doc; None if unlabeled."""
    per_game = (sidecar or {}).get("per_game") or {}
    game_doc = per_game.get(game_id)
    if not game_doc:
        return None
    return (game_doc.get("labels") or {}).get(str(ts))

def main() -> int:
    doc = build_sidecar()
    path = write_sidecar(doc)
    print("tick_segment_backfill | games=%d unresolved=%d h1=%d h2=%d excluded=%d" % (
        doc["n_games"], doc["n_games_unresolved"], doc["n_ticks_h1"],
        doc["n_ticks_h2"], doc["n_ticks_excluded"]))
    print("wrote %s" % path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

__all__ = [
    "BOUNDARY_BUFFER_MIN", "DEFAULT_GRADE_DIR", "DEFAULT_SIDECAR_PATH",
    "parse_ticker", "fetch_kickoffs", "resolve_kickoff", "label_tick",
    "backfill_game", "find_unk_games", "build_sidecar", "write_sidecar",
    "load_sidecar", "lookup_segment",
]
