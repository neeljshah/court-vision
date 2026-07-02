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

# KXMLBGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[-<side>]
_TICKER_RE = re.compile(r"^KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)")


def _norm(abbr: str) -> str:
    return _KALSHI_TO_ESPN.get(abbr, abbr)


def parse_mlb_ticker(ticker: str, valid_abbrs: set) -> Optional[Tuple[Any, str, str]]:
    """Parse a Kalshi MLB ticker -> (date, away_abbr, home_abbr) in ESPN abbrs.

    The tail concatenates AWAY then HOME with no delimiter, so we split it at the ONE
    position where BOTH sides normalise to a real box-score abbr.  Ambiguous or no valid
    split -> None (never a guess -- a mis-split would mislabel a different game). *date*
    is a datetime.date.  Never raises.
    """
    try:
        import datetime as _dt
        m = _TICKER_RE.match(str(ticker or "").strip())
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
            if a in valid_abbrs and h in valid_abbrs:
                good.append((a, h))
        if len(good) != 1:
            return None
        return (date, good[0][0], good[0][1])
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
                 box_parquet: Optional[Path] = None) -> None:
        self._ok = False
        self._abbrs: set = set()
        self._final: Dict[Tuple[Any, str, str], int] = {}
        self._scores: Dict[Tuple[Any, str, str], Tuple[int, int]] = {}
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

    def _ingest(self, df: Any) -> None:
        import pandas as pd
        d = df[df["status"].astype(str).str.upper().str.endswith("FINAL")].copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        self._abbrs = set(d["home_abbr"].astype(str)) | set(d["away_abbr"].astype(str))
        for _, r in d.iterrows():
            try:
                hs, as_ = float(r["home_score"]), float(r["away_score"])
            except (TypeError, ValueError):
                continue
            if pd.isna(r["date"]):
                continue
            key = (r["date"].date(), str(r["away_abbr"]), str(r["home_abbr"]))
            self._scores[key] = (int(hs), int(as_))  # final score kept even for ties
            if hs == as_:
                continue  # ties/unresolved are not a binary home_win label
            self._final[key] = 1 if hs > as_ else 0

    @property
    def available(self) -> bool:
        return self._ok and bool(self._final)

    def home_win(self, ticker: str) -> Optional[int]:
        """1 if home won, 0 if away won, None if unresolved/tie/not-final. Never raises."""
        if not self._ok:
            return None
        parsed = parse_mlb_ticker(ticker, self._abbrs | set(_KALSHI_TO_ESPN.keys()))
        if parsed is None:
            return None
        import datetime as _dt
        date, away, home = parsed
        # Join with +/- 1 day tolerance (a late UTC game files on the prior/next ET day).
        for delta in (0, -1, 1):
            key = (date + _dt.timedelta(days=delta), away, home)
            if key in self._final:
                return self._final[key]
        return None

    def final_score(self, ticker: str) -> Optional[Tuple[int, int]]:
        """(home_score, away_score) for a Kalshi ticker's FINAL game, else None.

        Unlike home_win this also resolves ties (needed to settle a paper bet against the
        realized score). Never raises."""
        if not self._ok:
            return None
        parsed = parse_mlb_ticker(ticker, self._abbrs | set(_KALSHI_TO_ESPN.keys()))
        if parsed is None:
            return None
        import datetime as _dt
        date, away, home = parsed
        for delta in (0, -1, 1):
            key = (date + _dt.timedelta(days=delta), away, home)
            if key in self._scores:
                return self._scores[key]
        return None


__all__ = [
    "DEFAULT_BOX_PARQUET", "MlbOutcomeResolver", "parse_mlb_ticker",
]
