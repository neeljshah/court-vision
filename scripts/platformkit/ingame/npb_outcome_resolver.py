"""scripts.platformkit.ingame.npb_outcome_resolver -- OFFLINE leak-free outcome
resolver for Kalshi NPB in-play tickers (the NPB counterpart to
wnba_outcome_resolver.WnbaOutcomeResolver / ingame_outcome_label.MlbOutcomeResolver).

THE GAP THIS CLOSES
-------------------
inplay_capture_loop.DEFAULT_SPORTS now includes "npb" (KXNPBGAME, verified live
2026-07-04/07-06) but no NPB outcome resolver existed, so a captured NPB in-play
grade series could never be joined to a held-out home_win label. This module
supplies home_win(ticker) -> {0,1}|None keyed DIRECTLY off the Kalshi ticker,
reading the local data/domains/npb/npb_results.parquet (date, season, home_team,
away_team, home_score, away_score, home_win, tied -- home_team/away_team are the
npb.jp scrape's native Japanese kanji/katakana club names, e.g. "DeNA"/
"日本ハム").

TICKER SHAPE (VERIFIED LIVE 2026-07-06 against the Kalshi public API)
-----------------------------------------------------------------------
  KXNPBGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[-<side>]
e.g. KXNPBGAME-26JUL050500YOKYAK-YOK (Yokohama DeNA BayStars @ Tokyo Yakult
Swallows). Sampled 24 open markets 2026-07-06 across 6 distinct matchups: every
observed tail is a fixed 3+3 split (e.g. YOKYAK, HIRHAN, HOKTOH, SAIORI, CHIFUK,
YOMCHU), but this resolver does NOT assume fixed width -- it tries every 2-way
split (mirroring wnba_outcome_resolver's _split_tail) and keeps the game only if
EXACTLY ONE split resolves both halves to a real team code, so a future
variable-width ticker (a short/long club code, as tennis/WNBA both saw) degrades
to an honest None rather than a silent mis-split.

ENGLISH CODE -> JAPANESE PARQUET NAME
---------------------------------------
npb.jp's scrape (domains/baseball_npb/ingest_npb.py) stores each club under its
native kanji/katakana name (e.g. "巨人" = Yomiuri Giants, "楽天" = Tohoku Rakuten
Golden Eagles) -- NOT the English 3-letter code Kalshi's ticker uses. _CODE_TO_NAME
below is the single explicit map from each of the 12 real NPB clubs' Kalshi ticker
code (verified live 2026-07-06 against every open KXNPBGAME market's title) to its
exact npb_results.parquet spelling. An override is only ever ACCEPTED if the target
name is ALSO present in the loaded parquet's own team set (same safety discipline as
wnba_outcome_resolver._resolve_abbr) -- a stale/wrong entry here just fails to
match, it can never mislabel a different real team. Two rare ALL-STAR rows in the
parquet (home_team/away_team == a league name, not a club) never match any club
code and are silently skipped, same as any other unresolvable row.

HONESTY: probability/label space only; no $ field; an unresolvable ticker, an
ambiguous split, or a not-yet-final game returns None (NEVER a guess or a
fabricated settle). This only supplies the held-out target for a CALIBRATION
verdict, never an edge or ROI.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network; never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_npb_outcome_resolver.py -q
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS_PARQUET = _REPO_ROOT / "data" / "domains" / "npb" / "npb_results.parquet"

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KXNPBGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[-<side>] (verified live
# 2026-07-06 -- see module docstring).
_TICKER_RE = re.compile(r"^KXNPBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)")

# Kalshi ticker code -> exact npb_results.parquet team-name spelling. Verified
# live 2026-07-06 against every open KXNPBGAME market title (all 12 real clubs,
# 6 distinct current matchups -- see module docstring).
_CODE_TO_NAME: Dict[str, str] = {
    "YOK": "DeNA",              # Yokohama DeNA BayStars
    "YAK": "ヤクルト",     # Tokyo Yakult Swallows
    "HIR": "広島",                # Hiroshima Toyo Carp
    "HAN": "阪神",                # Hanshin Tigers
    "HOK": "日本ハム",     # Hokkaido Nippon-Ham Fighters
    "TOH": "楽天",                # Tohoku Rakuten Golden Eagles
    "SAI": "西武",                # Saitama Seibu Lions
    "ORI": "オリックス",  # Orix Buffaloes
    "FUK": "ソフトバンク",  # Fukuoka (SoftBank Hawks)
    "CHI": "ロッテ",           # Chiba Lotte Marines
    "YOM": "巨人",                # Yomiuri Giants
    "CHU": "中日",                # Chunichi Dragons
}


def _norm(s: str) -> str:
    return str(s or "").strip().upper()


def _build_code_index(names: Any) -> Dict[str, str]:
    """UPPERCASED ticker-code -> real parquet team-name spelling, restricted to
    codes whose mapped name is ACTUALLY present in the loaded parquet's own
    team set (a stale/unmatched override just never appears here, never
    mislabels a different real team)."""
    present = {str(n).strip() for n in names}
    return {code: name for code, name in _CODE_TO_NAME.items() if name in present}


def parse_npb_ticker(ticker: str) -> Optional[Tuple[Any, str]]:
    """Parse a Kalshi NPB ticker -> (date, tail) -- the tail is the RAW
    uppercase away+home code concatenation (not yet split); the resolver joins
    it against the parquet's own code index. None on no match. Never raises."""
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
        return (date, tail)
    except Exception as exc:  # noqa: BLE001 -- a bad ticker is unresolvable, never fatal
        logger.debug("parse_npb_ticker(%s) failed: %s", ticker, exc)
        return None


def _split_tail(tail: str, code_index: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """Try every 2-way split of *tail* against the code index; return the
    UNIQUE (away_name, home_name) pairing, else None (ambiguous or no match)."""
    good = []
    for i in range(2, len(tail) - 1):
        a, h = code_index.get(tail[:i]), code_index.get(tail[i:])
        if a is not None and h is not None and a != h:
            good.append((a, h))
    uniq = list({p for p in good})
    if len(uniq) != 1:
        return None
    return uniq[0]


class NpbOutcomeResolver:
    """Resolve home_win for a Kalshi NPB ticker from the local npb_results
    parquet. Loads ONCE and caches a ticker-code index + a (date, away, home)
    -> home_win lookup. Reused across many tickers; the per-file test can
    inject an in-memory frame instead of touching disk."""

    def __init__(self, results_df: Any = None,
                 results_parquet: Optional[Path] = None) -> None:
        self._ok = False
        self._code_index: Dict[str, str] = {}
        self._final: Dict[Tuple[Any, str, str], int] = {}
        self._scores: Dict[Tuple[Any, str, str], Tuple[int, int]] = {}
        # Every (date, away, home) key seen in the parquet AT ALL, resolved or
        # not (NPB, like KBO, can repeat the SAME matchup on consecutive days
        # -- an in-progress today-row must never fall through to yesterday's
        # already-final identical matchup; see kbo_outcome_resolver twin fix).
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
            logger.debug("NpbOutcomeResolver init failed: %s", exc)

    def _ingest(self, df: Any) -> None:
        import pandas as pd
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        names = set(d["home_team"].astype(str)) | set(d["away_team"].astype(str))
        self._code_index = _build_code_index(names)
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

    def _resolve_key(self, date: Any, away: str, home: str
                      ) -> Optional[Tuple[Any, str, str]]:
        """Exact-date match wins ALWAYS if a row exists for it (resolved or
        not) -- see kbo_outcome_resolver._resolve_key twin fix for the full
        rationale (consecutive-day same-matchup series). +-1 day neighbor
        fallback fires ONLY when the exact date has no row at all."""
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
        parsed = parse_npb_ticker(ticker)
        if parsed is None:
            return None
        date, tail = parsed
        split = _split_tail(tail, self._code_index)
        if split is None:
            return None
        away, home = split
        key = self._resolve_key(date, away, home)
        return self._final.get(key) if key is not None else None

    def final_score(self, ticker: str) -> Optional[Tuple[int, int]]:
        """(home_score, away_score) for a Kalshi ticker's FINAL game, else None.
        Never raises."""
        if not self._ok:
            return None
        parsed = parse_npb_ticker(ticker)
        if parsed is None:
            return None
        date, tail = parsed
        split = _split_tail(tail, self._code_index)
        if split is None:
            return None
        away, home = split
        key = self._resolve_key(date, away, home)
        return self._scores.get(key) if key is not None else None


__all__ = [
    "DEFAULT_RESULTS_PARQUET", "NpbOutcomeResolver", "parse_npb_ticker",
]
