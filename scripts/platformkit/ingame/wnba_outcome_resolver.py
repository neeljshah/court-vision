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

TICKER SHAPE (GROUNDED live 2026-07-03 against the Kalshi public API -- REPLACES the
earlier assumed KXMLBGAME-style shape; see git history for the retracted assumption)
--------------------------------------------------------------------------------------
Fetched twice: 12 open + up to 200 settled KXWNBAGAME markets (330 total rows, 165
games). REAL shape:
  KXWNBAGAME-<YY><MON><DD><AWAY+HOME concatenated>[-<SIDE>]
e.g. KXWNBAGAME-26JUL05DALTOR-TOR (Dallas Wings @ Toronto Tempo, ticker verified open
2026-07-03). Differences from the original assumption, both confirmed on every one of
the 330 fetched tickers:
  1. NO HHMM field at all -- the date digits are followed IMMEDIATELY by the tail.
  2. The tail is Kalshi's OWN city-code shorthand (from its market title), not an ESPN
     team abbreviation: e.g. "Golden State" -> GS (not GSV), "Washington" -> WSH (not
     WAS), "New York" -> NY (not NYL), "Los Angeles" -> LA (not LAS), "Portland" -> PDX
     (airport code, not POR), "Connecticut" -> CONN (not CON). All 15 codes for the
     2026 season's real franchises were enumerated directly off `yes_sub_title` +
     the ticker's own -<SIDE> suffix (never hand-typed): ATL, CHI, CONN, DAL, GS, IND,
     LV, LA, MIN, NY, PDX, PHX, SEA, TOR, WSH.
The tail concatenates AWAY then HOME with NO delimiter (verified: e.g. LVCHI settled
with Las Vegas -- away, listed first in "Las Vegas vs Chicago" -- winning; cross-checked
against data/domains/wnba/espn_scoreboard.parquet's home_team/away_team columns for the
same date, home team = whichever half is NOT the away leader in the title). Split at the
ONE position where BOTH halves are real Kalshi codes (see _KALSHI_CODES) -- an ambiguous
or no-match split returns None, never a guess. 326/330 fetched tickers resolved uniquely
via this grounded code set; the 4 that did not are national-team exhibition legs (NGR =
Nigeria, JNT = Japan National Team) that are not real WNBA franchises -- correctly
excluded (n_labeled=0 for those, never a guess), consistent with the module's honesty
contract. Toronto Tempo (2026 expansion team, code TOR) is confirmed present both in the
live tickers and in the parquet's team-name column.

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

# KXWNBAGAME-<YY><MON><DD><AWAY+HOME concatenated>[-<side>] -- GROUNDED live 2026-07-03
# against 330 real Kalshi tickers (open + settled); see module docstring. NO HHMM field
# (the original assumed shape had one; every real ticker confirms it does not).
_TICKER_RE = re.compile(r"^KXWNBAGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)")

# Kalshi's OWN city-code shorthand for each of the 2026 season's 15 real WNBA franchises,
# enumerated directly off 330 fetched tickers' `yes_sub_title` + `-<SIDE>` suffix (never
# hand-typed) -- see module docstring for the full derivation + verification count. An
# override is only ever ACCEPTED if the resulting name is ALSO present in the loaded
# scoreboard's own name index (see _resolve_abbr), so a stale/wrong entry here just fails
# to match -- it can never mislabel a different real team. Toronto Tempo (TOR) is the
# 2026 expansion franchise, confirmed present in both live tickers and the parquet.
_ABBR_OVERRIDES: Dict[str, str] = {
    "ATL": "Atlanta Dream", "CHI": "Chicago Sky", "CONN": "Connecticut Sun",
    "DAL": "Dallas Wings", "GS": "Golden State Valkyries", "IND": "Indiana Fever",
    "LV": "Las Vegas Aces", "LA": "Los Angeles Sparks", "MIN": "Minnesota Lynx",
    "NY": "New York Liberty", "PDX": "Portland Fire", "PHX": "Phoenix Mercury",
    "SEA": "Seattle Storm", "TOR": "Toronto Tempo", "WSH": "Washington Mystics",
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
        yy, mon, dd, tail = m.groups()
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
