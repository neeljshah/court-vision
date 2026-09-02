"""scripts.platformkit.ingame.ingame_outcome_label -- OFFLINE leak-free outcome
resolver for the captured in-game grade series.

THE GAP THIS CLOSES
-------------------
The in-play capture loop writes each game's (model_prob, market_prob) grade series
keyed by its KALSHI TICKER (e.g. KXMLBGAME-26JUN241845PHIWSH), not the ESPN numeric
event id.  settle_stamp keys the held-out home_win label by the ESPN id, so the label
NEVER lands on the ticker-keyed file -> the whole in-game measurement layer has had
ZERO outcome labels and could only compare model-vs-market (CLV), never model-vs-truth.

This module resolves the outcome DIRECTLY from the ticker: the ticker ENCODES the date
plus the away+home team abbreviations, so we parse it and join to the local realized
box-score parquet (data/domains/mlb/espn_boxscores.parquet) to read the final score and
return home_win in {0,1}.  Pure/offline (reads a local parquet only); an unresolvable
ticker or a game not-yet-final returns None (NEVER a fabricated label).

LEAK-FREE: the label is the realized final only; it is joined to a tick series whose
model_prob is already as-of-tick.  The resolver adds NO forward information to any tick.

HONESTY: probability/label space only; no $ field; this only supplies the held-out
target for a CALIBRATION verdict, never an edge or ROI.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network
(reads a local parquet); never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_outcome_label.py -q
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BOX_PARQUET = _REPO_ROOT / "data" / "domains" / "mlb" / "espn_boxscores.parquet"

# Kalshi uses a few abbreviations that differ from ESPN's box-score abbrs.
_KALSHI_TO_ESPN = {
    "AZ": "ARI", "CWS": "CHW", "WSN": "WSH", "SFG": "SF", "SDP": "SD",
    "TBR": "TB", "KCR": "KC", "OAK": "ATH",
}

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KXMLBGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[G<n> doubleheader][-<side>]
# Team tail is lazy + G-group needs a DIGIT, so an abbr ending in G (SFG) never
# loses its G to the doubleheader group.
_TICKER_RE = re.compile(
    r"^KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+?)(?:G(\d))?(?=-|$)")


def _norm(abbr: str) -> str:
    return _KALSHI_TO_ESPN.get(abbr, abbr)


def _extract_hhmm(ticker: str) -> Optional[str]:
    """Re-parse a ticker's own HHMM digits (group 4) without changing
    parse_mlb_ticker's public 4-tuple contract -- that function is called by
    17+ other modules and must keep its shape."""
    m = _TICKER_RE.match(str(ticker or "").strip())
    return m.group(4) if m else None


def _clock_minutes(start_time_iso: str) -> Optional[int]:
    """HH:MM digits off an ISO start_time string -> UTC minutes-of-day.
    Box start_times in espn_boxscores.parquet are UTC (opus judge 2026-07-12
    proved it: 22:10-ET ticker maps to 02:10Z box row)."""
    try:
        return int(start_time_iso[11:13]) * 60 + int(start_time_iso[14:16])
    except (TypeError, ValueError, IndexError):
        return None


def _circ_diff(a: int, b: int) -> int:
    """Circular minutes-of-day distance (nightcaps cross midnight UTC)."""
    d = abs(a - b) % 1440
    return min(d, 1440 - d)


def parse_mlb_ticker(ticker: str, valid_abbrs: set
                     ) -> Optional[Tuple[Any, str, str, Optional[int]]]:
    """Parse a Kalshi MLB ticker -> (date, away_abbr, home_abbr, game_number).

    The tail concatenates AWAY then HOME with no delimiter, so we split it at the ONE
    position where BOTH sides normalise to a real box-score abbr.  Ambiguous or no valid
    split -> None (never a guess -- a mis-split would mislabel a different game). *date*
    is a datetime.date.  *game_number* is the doubleheader index from a trailing
    G<digit> (e.g. ...MILSTLG1 -> 1), None for a single game.  Never raises.
    """
    try:
        import datetime as _dt
        m = _TICKER_RE.match(str(ticker or "").strip())
        if not m:
            return None
        yy, mon, dd, _hhmm, tail, gnum = m.groups()
        month = _MONTHS.get(mon)
        if month is None:
            return None
        date = _dt.date(2000 + int(yy), month, int(dd))
        good = []
        for i in range(2, len(tail) - 1):
            a, h = _norm(tail[:i]), _norm(tail[i:])
            if a in valid_abbrs and h in valid_abbrs:
                good.append((a, h))
        if len(good) != 1:
            return None
        return (date, good[0][0], good[0][1], int(gnum) if gnum else None)
    except Exception as exc:  # noqa: BLE001 -- a bad ticker is unresolvable, never fatal
        logger.debug("parse_mlb_ticker(%s) failed: %s", ticker, exc)
        return None


class MlbOutcomeResolver:
    """Resolve home_win for a Kalshi MLB ticker from the local realized-box parquet.

    Loads the parquet ONCE (final rows only) and caches the abbr set + a lookup keyed by
    (date, away, home).  home_win(ticker) -> 1/0/None.  Reused across many tickers so the
    per-file test can inject an in-memory frame instead of touching disk.
    """

    def __init__(self, box_df: Any = None,
                 box_parquet: Optional[Path] = None,
                 games_fallback: bool = True) -> None:
        self._ok = False
        self._abbrs: set = set()
        # (date, away, home) -> [(start_time_iso_str, (home_score, away_score)), ...]
        # A list because a doubleheader legitimately has 2 rows for one key.
        self._rows: Dict[Tuple[Any, str, str], list] = {}
        self._fb: Dict[Tuple[Any, str, str], list] = {}  # S91 second source
        try:
            df = box_df
            if df is None:
                import pandas as pd
                p = Path(box_parquet) if box_parquet is not None else DEFAULT_BOX_PARQUET
                if not p.exists():
                    return
                df = pd.read_parquet(p)
            self._ingest(df)
            self._ok = True
        except Exception as exc:  # noqa: BLE001 -- no parquet -> resolver is inert, not fatal
            logger.debug("MlbOutcomeResolver init failed: %s", exc)
        if games_fallback and box_df is None:
            self._load_fallback()

    def _load_fallback(self) -> None:
        """S91: games{,_current}.parquet finals -> _fb. Never raises."""
        try:
            from scripts.platformkit.ingame import mlb_games_outcome_fallback as _g
            if (df := _g.load_games_box_frame()) is not None:
                self._ingest(df, into=self._fb)
            self._ok = self._ok or bool(self._fb)
        except Exception as exc:  # noqa: BLE001 -- no fallback is not fatal
            logger.debug("MlbOutcomeResolver fallback load failed: %s", exc)

    def _ingest(self, df: Any, into: Optional[Dict] = None) -> None:
        import pandas as pd
        target = self._rows if into is None else into
        d = df[df["status"].astype(str).str.upper().str.endswith("FINAL")].copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        self._abbrs |= set(d["home_abbr"].astype(str)) | set(d["away_abbr"].astype(str))
        has_st = "start_time" in d.columns
        for _, r in d.iterrows():
            try:
                hs, as_ = float(r["home_score"]), float(r["away_score"])
            except (TypeError, ValueError):
                continue
            if pd.isna(r["date"]):
                continue
            key = (r["date"].date(), str(r["away_abbr"]), str(r["home_abbr"]))
            st = str(r["start_time"]) if has_st and pd.notna(r["start_time"]) else ""
            target.setdefault(key, []).append((st, (int(hs), int(as_))))

    @property
    def available(self) -> bool:
        return self._ok and bool(self._rows or self._fb)

    def _pick(self, key: Tuple[Any, str, str], game_number: Optional[int],
              ticker_hhmm: Optional[str] = None,
              rows_map: Optional[Dict] = None) -> Optional[Tuple[int, int]]:
        """Pick ONE final score for a (date, away, home) key, doubleheader-aware.

        game_number None + exactly 1 row -> that row (the pre-doubleheader path).
        game_number None + exactly 2 rows -> HHMM tie-break (see _pick_by_hhmm);
        None on 3+ rows (ambiguous doubleheader, fail closed).
        game_number N -> rows ordered by start_time (ISO strings sort correctly),
        G1 = earliest; N beyond the finals on disk, or 2+ rows we cannot order
        (missing start_time), -> None (fail closed, never a guess)."""
        # S95: caller returns the FIRST non-None _pick -> the map read here answered.
        self.last_source = "espn_boxscores_parquet" if rows_map is None else "games_parquet_fallback"
        rows = (self._rows if rows_map is None else rows_map).get(key)
        if not rows:
            return None
        if game_number is None:
            if len(rows) == 1:
                return rows[0][1]
            if len(rows) == 2:
                return self._pick_by_hhmm(rows, ticker_hhmm)
            return None
        if len(rows) > 1 and any(not st for st, _ in rows):
            return None
        if game_number > len(rows):
            return None
        return sorted(rows)[game_number - 1][1]

    @staticmethod
    def _pick_by_hhmm(rows: list, ticker_hhmm: Optional[str]
                      ) -> Optional[Tuple[int, int]]:
        """Postponement-created doubleheader: 2 same-date finals, no G-suffix on
        the ticker (see module/class docstring). Break the tie by proximity to
        the ticker's own HHMM -- but only when the two finals are >=90min apart
        AND one is strictly closer; anything closer/tied/missing data stays
        failed-closed (never a guessed coin flip)."""
        if ticker_hhmm is None:
            return None
        sts = [st for st, _ in rows]
        if any(not st for st in sts):
            return None
        minutes = [_clock_minutes(st) for st in sts]
        if any(m is None for m in minutes):
            return None
        if _circ_diff(minutes[0], minutes[1]) < 90:
            return None
        try:
            # Ticker HHMM is ET; box start_times are UTC. MLB season runs
            # entirely under EDT (UTC-4), so ET+240 mod 1440 = UTC minutes-of-
            # day; circular distance handles nightcaps crossing midnight UTC.
            # ponytail: fixed EDT offset -- add zoneinfo DST math only if a
            # March/November MLB ticker ever exists.
            tk = (int(ticker_hhmm[:2]) * 60 + int(ticker_hhmm[2:]) + 240) % 1440
        except (TypeError, ValueError):
            return None
        diffs = [_circ_diff(m, tk) for m in minutes]
        if diffs[0] == diffs[1]:
            return None
        return rows[0 if diffs[0] < diffs[1] else 1][1]

    def _resolve(self, ticker: str, today: Optional[Any] = None
                ) -> Optional[Tuple[int, int]]:
        """(home_score, away_score) for a ticker's FINAL game, else None. Never raises."""
        if not self._ok:
            return None
        parsed = parse_mlb_ticker(ticker, self._abbrs | set(_KALSHI_TO_ESPN.keys()))
        if parsed is None:
            return None
        import datetime as _dt
        date, away, home, gnum = parsed
        hhmm = _extract_hhmm(ticker)
        # Join with a +1 day tolerance (a late game can file on the NEXT day).
        for delta in (0, 1):
            score = self._pick((date + _dt.timedelta(days=delta), away, home), gnum, hhmm)
            if score is not None:
                return score
        # S91: games.parquet finals, EXACT date only (+/-1 mislabels, 1 in 225).
        fb = self._pick((date, away, home), gnum, hhmm, self._fb)
        if fb is not None:
            return fb
        # delta=-1 is RISK-SCOPED, not forbidden outright: a naive -1 caused a live
        # 2026-07-07 wrong-match (a bet on the 07-08 MIL@STL game settled against
        # 07-07's just-final G1 score). Reinstated ONLY when (a) delta 0 AND +1
        # buckets are BOTH truly empty (no ambiguity to paper over), (b) the -1
        # bucket has exactly ONE final for these teams, (c) the ticker's game date
        # is >=2 days in the past (ingest-race guard: the correct forward game
        # must have had time to land by now). Any one guard failing -> None.
        key0 = (date, away, home)
        key1 = (date + _dt.timedelta(days=1), away, home)
        if self._rows.get(key0) or self._rows.get(key1):
            return None
        today = today if today is not None else _dt.date.today()
        if (today - date).days < 2:
            return None
        key_neg1 = (date - _dt.timedelta(days=1), away, home)
        rows = self._rows.get(key_neg1)
        if not rows or len(rows) != 1:
            return None
        return self._pick(key_neg1, gnum, hhmm)

    def home_win(self, ticker: str, today: Optional[Any] = None) -> Optional[int]:
        """1 if home won, 0 if away won, None if unresolved/tie/not-final. Never raises."""
        score = self._resolve(ticker, today)
        if score is None or score[0] == score[1]:
            return None  # ties/unresolved are not a binary home_win label
        return 1 if score[0] > score[1] else 0

    def final_score(self, ticker: str, today: Optional[Any] = None
                    ) -> Optional[Tuple[int, int]]:
        """(home_score, away_score) for a Kalshi ticker's FINAL game, else None.

        Unlike home_win this also resolves ties (needed to settle a paper bet against the
        realized score). *today* overrides the age guard's "now" reference (defaults to
        the real date; tests inject a fixed value). Never raises."""
        return self._resolve(ticker, today)


__all__ = ["DEFAULT_BOX_PARQUET", "MlbOutcomeResolver", "parse_mlb_ticker"]
