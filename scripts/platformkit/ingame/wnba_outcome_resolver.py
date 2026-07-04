"""scripts.platformkit.ingame.wnba_outcome_resolver -- OFFLINE leak-free outcome
resolver for Kalshi WNBA in-play tickers (the WNBA counterpart to
ingame_outcome_label.MlbOutcomeResolver / soccer_outcome.SoccerOutcomeResolver /
tennis_outcome_resolver.TennisOutcomeResolver).

THE GAP THIS CLOSES
-------------------
inplay_capture_loop.DEFAULT_SPORTS now includes "wnba" (KXWNBAGAME, wired wave 1)
but no WNBA outcome resolver existed, so a captured WNBA in-play grade series could
never be joined to a held-out home_win label -- the outcome-verdict / segment-trust
machinery stayed MLB-only. This module supplies home_win(ticker) -> {0,1}|None keyed
DIRECTLY off the Kalshi ticker, mirroring the MLB resolver's contract, reading the
local data/domains/wnba/espn_scoreboard.parquet (event_id, date, home_team, away_team,
home_score, away_score, home_win, status_name).

TICKER SHAPE (ASSUMED, NOT YET VERIFIED LIVE -- see HONESTY below)
-------------------------------------------------------------------
No live KXWNBAGAME ticker sample was available in this repo at build time (WNBA
capture only just started per the brief). WNBA moneyline is structurally closest to
KXMLBGAME (city/team abbreviations, no set/half/period-count ambiguity like tennis),
so this mirrors that shape:
  KXWNBAGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[-<SIDE>]
e.g. KXWNBAGAME-26JUL051930LVACHI (Las Vegas Aces @ Chicago Sky). The tail
concatenates AWAY then HOME with NO delimiter (same ambiguity as MLB), so it is
split at the ONE position where BOTH halves normalise to a real ESPN team-name
abbreviation (derived from the loaded scoreboard itself, never hand-typed) --
an ambiguous or no-match split returns None, never a guess. If the live ticker
turns out to omit HHMM or use a different tail width, `parse_wnba_ticker` returning
None on every real ticker is the honest failure mode (never a silent mislabel) and
is surfaced via `n_labeled=0` in the verdict doc, not a crash.

HONESTY: probability/label space only; no $ field; an unresolvable ticker, an
ambiguous split, or a not-yet-final game returns None (NEVER a guess or a
fabricated settle). This only supplies the held-out target for a CALIBRATION
verdict, never an edge or ROI.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network; never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_wnba_outcome_resolver.py -q
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCOREBOARD_PARQUET = (
    _REPO_ROOT / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
)

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KXWNBAGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[-<side>] (mirrors
# KXMLBGAME's shape -- see module docstring for the "assumed, not yet verified
# live" caveat).
_TICKER_RE = re.compile(r"^KXWNBAGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)")

# Small set of common WNBA 3-letter city/team codes that do not simply equal the
# team name's first letters (e.g. "Golden State Valkyries" -> GSV, not GOL). An
# override is only ever ACCEPTED if the resulting name is ALSO present in the
# loaded scoreboard's own name index (see _resolve_abbr), so a stale/wrong entry
# here just fails to match -- it can never mislabel a different real team.
_ABBR_OVERRIDES: Dict[str, str] = {
    "LVA": "Las Vegas Aces", "LV": "Las Vegas Aces", "NYL": "New York Liberty",
    "GSV": "Golden State Valkyries", "CON": "Connecticut Sun",
    "PHX": "Phoenix Mercury", "WAS": "Washington Mystics", "IND": "Indiana Fever",
    "CHI": "Chicago Sky", "MIN": "Minnesota Lynx", "SEA": "Seattle Storm",
    "DAL": "Dallas Wings", "ATL": "Atlanta Dream", "LAS": "Los Angeles Sparks",
    "TOR": "Toronto Tempo", "POR": "Portland Fire",
}


def _norm(s: str) -> str:
    return str(s or "").strip().upper()


def _build_name_index(names: Any) -> Dict[str, str]:
    """UPPERCASED short-token -> real team-name spelling, derived from the
    scoreboard's own names (first word + first 3 letters of the whole name),
    never hand-typed team spellings."""
    idx: Dict[str, str] = {}
    for name in names:
        n = str(name).strip()
        if not n:
            continue
        key_full = _norm(n)
        idx.setdefault(key_full[:3], n)
        first_word = n.split()[0] if n.split() else n
        idx.setdefault(_norm(first_word)[:3], n)
    return idx


def parse_wnba_ticker(ticker: str) -> Optional[Tuple[Any, str, str]]:
    """Parse a Kalshi WNBA ticker -> (date, away_tail, home_tail) -- the tail
    halves are RAW uppercase substrings (not yet resolved to a team name); the
    resolver joins them against the scoreboard's own name index. None on no
    match -- never a guess. *date* is a datetime.date. Never raises."""
    try:
        import datetime as _dt
        m = _TICKER_RE.match(_norm(ticker))
        if not m:
            return None
        yy, mon, dd, _hhmm, tail = m.groups()
        month = _MONTHS.get(mon)
        if month is None:
            return None
        date = _dt.date(2000 + int(yy), month, int(dd))
        if len(tail) < 4:
            return None
        return (date, tail, tail)  # split resolved jointly in the resolver
    except Exception as exc:  # noqa: BLE001 -- a bad ticker is unresolvable, never fatal
        logger.debug("parse_wnba_ticker(%s) failed: %s", ticker, exc)
        return None


def _resolve_abbr(code: str, name_index: Dict[str, str]) -> Optional[str]:
    code = _norm(code)
    override = _ABBR_OVERRIDES.get(code)
    if override is not None and _norm(override)[:3] in name_index and \
            name_index[_norm(override)[:3]] == override:
        return override
    return name_index.get(code)


def _split_tail(tail: str, name_index: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """Try every 2-way split of *tail* against the name index; return the UNIQUE
    (away_name, home_name) pairing, else None (ambiguous or no match)."""
    good = []
    for i in range(2, len(tail) - 1):
        a, h = _resolve_abbr(tail[:i], name_index), _resolve_abbr(tail[i:], name_index)
        if a is not None and h is not None and a != h:
            good.append((a, h))
    uniq = list({p for p in good})
    if len(uniq) != 1:
        return None
    return uniq[0]


class WnbaOutcomeResolver:
    """Resolve home_win for a Kalshi WNBA ticker from the local ESPN scoreboard
    parquet. Loads ONCE (final rows only) and caches a team-name index + a
    (date, away, home) -> home_win lookup. Reused across many tickers; the
    per-file test can inject an in-memory frame instead of touching disk."""

    def __init__(self, scoreboard_df: Any = None,
                 scoreboard_parquet: Optional[Path] = None) -> None:
        self._ok = False
        self._name_index: Dict[str, str] = {}
        self._final: Dict[Tuple[Any, str, str], int] = {}
        self._scores: Dict[Tuple[Any, str, str], Tuple[int, int]] = {}
        try:
            df = scoreboard_df
            if df is None:
                import pandas as pd
                p = Path(scoreboard_parquet) if scoreboard_parquet is not None \
                    else DEFAULT_SCOREBOARD_PARQUET
                if not p.exists():
                    return
                df = pd.read_parquet(p)
            self._ingest(df)
            self._ok = True
        except Exception as exc:  # noqa: BLE001 -- no parquet -> resolver is inert
            logger.debug("WnbaOutcomeResolver init failed: %s", exc)

    def _ingest(self, df: Any) -> None:
        import pandas as pd
        d = df
        if "status_name" in d.columns:
            d = d[d["status_name"].astype(str).str.upper().str.endswith("FINAL")]
        d = d.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        names = set(d["home_team"].astype(str)) | set(d["away_team"].astype(str))
        self._name_index = _build_name_index(names)
        for _, r in d.iterrows():
            home, away = str(r["home_team"]).strip(), str(r["away_team"]).strip()
            if not home or not away or pd.isna(r["date"]):
                continue
            try:
                hs, as_ = float(r["home_score"]), float(r["away_score"])
            except (TypeError, ValueError):
                continue
            key = (r["date"].date(), away, home)
            self._scores[key] = (int(hs), int(as_))
            if hs == as_:
                continue  # ties are not a binary home_win label
            self._final[key] = 1 if hs > as_ else 0

    @property
    def available(self) -> bool:
        return self._ok and bool(self._final)

    def home_win(self, ticker: str) -> Optional[int]:
        """1 if home won, 0 if away won, None if unresolved/tie/not-final/
        ambiguous-split. Never raises."""
        if not self._ok:
            return None
        parsed = parse_wnba_ticker(ticker)
        if parsed is None:
            return None
        import datetime as _dt
        date, tail, _ = parsed
        split = _split_tail(tail, self._name_index)
        if split is None:
            return None
        away, home = split
        for delta in (0, -1, 1):
            key = (date + _dt.timedelta(days=delta), away, home)
            if key in self._final:
                return self._final[key]
        return None

    def final_score(self, ticker: str) -> Optional[Tuple[int, int]]:
        """(home_score, away_score) for a Kalshi ticker's FINAL game, else None.
        Resolves ties too (home_win does not). Never raises."""
        if not self._ok:
            return None
        parsed = parse_wnba_ticker(ticker)
        if parsed is None:
            return None
        import datetime as _dt
        date, tail, _ = parsed
        split = _split_tail(tail, self._name_index)
        if split is None:
            return None
        away, home = split
        for delta in (0, -1, 1):
            key = (date + _dt.timedelta(days=delta), away, home)
            if key in self._scores:
                return self._scores[key]
        return None


__all__ = [
    "DEFAULT_SCOREBOARD_PARQUET", "WnbaOutcomeResolver", "parse_wnba_ticker",
]
