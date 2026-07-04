"""scripts.platformkit.ingame.kbo_outcome_resolver -- OFFLINE leak-free outcome
resolver for Kalshi KBO in-play tickers (the KBO counterpart to
npb_outcome_resolver.NpbOutcomeResolver / ingame_outcome_label.MlbOutcomeResolver).

THE GAP THIS CLOSES
-------------------
inplay_capture_loop.DEFAULT_SPORTS now includes "kbo" (KXKBOGAME, verified live
2026-07-04/07-06) but no KBO outcome resolver existed, so a captured KBO in-play
grade series could never be joined to a held-out home_win label. This module
supplies home_win(ticker) -> {0,1}|None keyed DIRECTLY off the Kalshi ticker,
reading the local data/domains/kbo/kbo_results.parquet (date, season, home_team,
away_team, home_score, away_score, home_win, tied). The parquet's team names are
ALREADY the domains.baseball_kbo.team_map canonical ASCII EN codes (DOOSAN,
HANWHA, KIA, KIWOOM, KT, LG, LOTTE, NC, SAMSUNG, SSG -- verified live 2026-07-06:
this resolver's own parquet read shows the identical 10-code set), so unlike NPB
there is no kanji/katakana translation needed here -- only a Kalshi-ticker-code
-> parquet-code ALIAS map, since Kalshi's 3-letter tail codes do not always equal
the parquet's own codes (e.g. Kalshi "KTW" for KT, "NCD" for NC, "LOT" for LOTTE,
"SAM" for SAMSUNG, "HAN" for HANWHA, "KIW" for KIWOOM, "DOO" for DOOSAN; "LG"/
"KIA"/"SSG" ARE identical). Mirrors ingame_outcome_label.py's _KALSHI_TO_ESPN
alias-map pattern for MLB.

TICKER SHAPE (VERIFIED LIVE 2026-07-06 against the Kalshi public API)
-----------------------------------------------------------------------
  KXKBOGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[-<side>]
e.g. KXKBOGAME-26JUL050500NCDKIA-NCD (NC Dinos @ Kia Tigers). Sampled 20 open
markets 2026-07-06 across 5 distinct matchups: tail widths are VARIABLE
(NCDKIA=3+3, LOTKTW=3+3, SAMSSG=3+3, HANLG=3+2, DOOKIW=3+3) -- so, mirroring
ingame_outcome_label.parse_mlb_ticker / wnba_outcome_resolver._split_tail, this
resolver tries every 2-way split and keeps the game only if EXACTLY ONE split
resolves both halves to a real (aliased) team code -- an ambiguous or no-match
split returns None, never a guess.

HONESTY: probability/label space only; no $ field; an unresolvable ticker, an
ambiguous split, or a not-yet-final game returns None (NEVER a guess or a
fabricated settle). This only supplies the held-out target for a CALIBRATION
verdict, never an edge or ROI.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network; never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_outcome_resolver.py -q
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS_PARQUET = _REPO_ROOT / "data" / "domains" / "kbo" / "kbo_results.parquet"

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KXKBOGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[-<side>] (verified live
# 2026-07-06 -- see module docstring).
_TICKER_RE = re.compile(r"^KXKBOGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)")

# Kalshi ticker code -> domains.baseball_kbo.team_map ASCII EN code (the
# parquet's own spelling). Verified live 2026-07-06 against every open
# KXKBOGAME market title (all 10 real clubs, 5 distinct current matchups --
# see module docstring). Codes already identical to the parquet (LG/KIA/SSG)
# are omitted -- _norm passes them through unchanged.
_KALSHI_TO_PARQUET: Dict[str, str] = {
    "KTW": "KT", "NCD": "NC", "LOT": "LOTTE", "SAM": "SAMSUNG",
    "HAN": "HANWHA", "KIW": "KIWOOM", "DOO": "DOOSAN",
}


def _norm(code: str) -> str:
    c = str(code or "").strip().upper()
    return _KALSHI_TO_PARQUET.get(c, c)


def parse_kbo_ticker(ticker: str, valid_codes: set) -> Optional[Tuple[Any, str, str]]:
    """Parse a Kalshi KBO ticker -> (date, away_code, home_code) in parquet
    codes. The tail concatenates AWAY then HOME with no delimiter and is
    VARIABLE WIDTH, so we split it at the ONE position where BOTH sides
    (after alias normalisation) resolve to a real parquet code. Ambiguous or
    no valid split -> None (never a guess). *date* is a datetime.date. Never
    raises."""
    try:
        import datetime as _dt
        m = _TICKER_RE.match(str(ticker or "").strip().upper())
        if not m:
            return None
        yy, mon, dd, _hhmm, tail = m.groups()
        month = _MONTHS.get(mon)
        if month is None:
            return None
        date = _dt.date(2000 + int(yy), month, int(dd))
        good = []
        for i in range(2, len(tail) - 1):
            a, h = _norm(tail[:i]), _norm(tail[i:])
            if a in valid_codes and h in valid_codes and a != h:
                good.append((a, h))
        uniq = list({p for p in good})
        if len(uniq) != 1:
            return None
        return (date, uniq[0][0], uniq[0][1])
    except Exception as exc:  # noqa: BLE001 -- a bad ticker is unresolvable, never fatal
        logger.debug("parse_kbo_ticker(%s) failed: %s", ticker, exc)
        return None


class KboOutcomeResolver:
    """Resolve home_win for a Kalshi KBO ticker from the local kbo_results
    parquet. Loads ONCE and caches the code set + a (date, away, home) ->
    home_win lookup. Reused across many tickers; the per-file test can inject
    an in-memory frame instead of touching disk."""

    def __init__(self, results_df: Any = None,
                 results_parquet: Optional[Path] = None) -> None:
        self._ok = False
        self._codes: set = set()
        self._final: Dict[Tuple[Any, str, str], int] = {}
        self._scores: Dict[Tuple[Any, str, str], Tuple[int, int]] = {}
        # Every (date, away, home) key seen in the parquet AT ALL, resolved or
        # not (KBO plays the SAME matchup on consecutive days in a series, so
        # an in-progress today-row must never fall through to yesterday's
        # already-final identical matchup -- see module docstring update).
        self._known_dates: set = set()
        try:
            df = results_df
            if df is None:
                import pandas as pd
                p = Path(results_parquet) if results_parquet is not None \
                    else DEFAULT_RESULTS_PARQUET
                if not p.exists():
                    return
                df = pd.read_parquet(p)
            self._ingest(df)
            self._ok = True
        except Exception as exc:  # noqa: BLE001 -- no parquet -> resolver is inert
            logger.debug("KboOutcomeResolver init failed: %s", exc)

    def _ingest(self, df: Any) -> None:
        import pandas as pd
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        self._codes = set(d["home_team"].astype(str)) | set(d["away_team"].astype(str))
        for _, r in d.iterrows():
            home, away = str(r["home_team"]).strip(), str(r["away_team"]).strip()
            if not home or not away or pd.isna(r["date"]):
                continue
            key = (r["date"].date(), away, home)
            self._known_dates.add(key)  # row exists for this exact date, resolved or not
            try:
                hs, as_ = float(r["home_score"]), float(r["away_score"])
            except (TypeError, ValueError):
                continue
            if bool(r.get("tied", False)) or pd.isna(r.get("home_win")):
                continue  # ties/unresolved are not a binary home_win label
            self._scores[key] = (int(hs), int(as_))
            hw = r.get("home_win")
            try:
                self._final[key] = 1 if float(hw) >= 0.5 else 0
            except (TypeError, ValueError):
                continue

    @property
    def available(self) -> bool:
        return self._ok and bool(self._final)

    def _valid_codes(self) -> set:
        return self._codes | set(_KALSHI_TO_PARQUET.keys())

    def _resolve_key(self, date: Any, away: str, home: str
                      ) -> Optional[Tuple[Any, str, str]]:
        """Exact-date match wins ALWAYS if a row exists for it (resolved or
        not) -- KBO reruns the SAME matchup on consecutive days, so an
        in-progress today's game must never silently borrow yesterday's
        already-final identical matchup. The +-1 day neighbor fallback is
        used ONLY when the exact date has no row at all (genuine schedule/
        timezone slop), never to skip past an unresolved exact-date row."""
        import datetime as _dt
        exact = (date, away, home)
        if exact in self._known_dates:
            return exact if exact in self._final or exact in self._scores else None
        for delta in (-1, 1):
            key = (date + _dt.timedelta(days=delta), away, home)
            if key in self._known_dates:
                return key
        return None

    def home_win(self, ticker: str) -> Optional[int]:
        """1 if home won, 0 if away won, None if unresolved/tie/not-final/
        ambiguous-split. Never raises."""
        if not self._ok:
            return None
        parsed = parse_kbo_ticker(ticker, self._valid_codes())
        if parsed is None:
            return None
        date, away, home = parsed
        key = self._resolve_key(date, away, home)
        return self._final.get(key) if key is not None else None

    def final_score(self, ticker: str) -> Optional[Tuple[int, int]]:
        """(home_score, away_score) for a Kalshi ticker's FINAL game, else None.
        Never raises."""
        if not self._ok:
            return None
        parsed = parse_kbo_ticker(ticker, self._valid_codes())
        if parsed is None:
            return None
        date, away, home = parsed
        key = self._resolve_key(date, away, home)
        return self._scores.get(key) if key is not None else None


__all__ = [
    "DEFAULT_RESULTS_PARQUET", "KboOutcomeResolver", "parse_kbo_ticker",
]
