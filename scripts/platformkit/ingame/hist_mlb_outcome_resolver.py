"""scripts.platformkit.ingame.hist_mlb_outcome_resolver -- OFFLINE leak-free
outcome resolver for Kalshi MLB in-play tickers (KXMLBGAME-...), mirroring
wnba_outcome_resolver.py's contract exactly but keyed to
data/domains/mlb/espn_boxscores.parquet (home_abbr/away_abbr/home_score/
away_score/date/status) instead of the WNBA scoreboard parquet.

THE GAP THIS CLOSES (LANE 3 sub-task B)
----------------------------------------
data/cache/inplay_history/mlb/*.jsonl (the forward Kalshi in-play capture
corpus, provenance="kalshi", phase="in_play") carries ONLY {sport, game_id
(the Kalshi ticker), venue, market_type, side, ticker, prob, ts, source_ts} --
no final-score / outcome field at all. hist_mlb_forward_gate.py (this lane's
companion module) needs a leak-free home_win(ticker) label to grade the
recalibrated-vs-raw venue-prob comparison on this corpus; this module supplies
exactly that, read-only, from the LOCAL ESPN boxscore parquet (a DIFFERENT
provenance than both the Kalshi ticks themselves and the Polymarket pm_backfill
training corpus -- genuinely a third, independent outcome source).

TICKER SHAPE (grounded against 201 real tickers captured 2026-06-28..07-04)
----------------------------------------------------------------------------
    KXMLBGAME-<YY><MON><DD><HHMM><AWAY><HOME>
e.g. KXMLBGAME-26JUL011235CWSBAL (2026-07-01, 12:35 ET book time, Cubs... no --
away=CWS (Chicago White Sox), home=BAL (Baltimore Orioles)). Unlike the WNBA
ticker (no HHMM field), the MLB ticker DOES carry a 4-digit HHMM between the
date and the team-code tail -- confirmed on every one of the 201 captured
tickers (fixed-width \\d{4} immediately after the 2-digit day, immediately
before the first non-digit character).

Kalshi's OWN team-code shorthand differs from ESPN's abbreviation for a
handful of franchises (grounded from the 201 real tickers' team-code tails
cross-checked against espn_boxscores.parquet's home_abbr/away_abbr for the
same date): AZ->ARI (Diamondbacks), CWS->CHW (White Sox), ATH->ATH (Athletics,
same both sides -- kept for clarity), LAA/LAD/SD/SF/TB/KC/WSH match ESPN
directly. An override is only ever ACCEPTED if the resulting abbreviation is
ALSO present in the loaded boxscore's own abbr index (see _resolve_abbr, same
"never mislabel" contract as wnba_outcome_resolver._resolve_abbr) -- a stale or
wrong override entry here just fails to match, it can never mislabel a
different real team.

HONESTY: probability/label space only; no $ field; an unresolvable ticker, an
ambiguous split, a tie, or a not-yet-final game returns None (never a guess).

INVARIANTS: scripts/platformkit/ingame/ only (NEW file, hist_ prefix); <=300
LOC; ASCII only; no network; never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_hist_mlb_outcome_resolver.py -q
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BOXSCORE_PARQUET = (
    _REPO_ROOT / "data" / "domains" / "mlb" / "espn_boxscores.parquet"
)

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KXMLBGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[-<side>] -- grounded
# 2026-07-04 against 201 real captured tickers (data/cache/inplay_history/mlb).
_TICKER_RE = re.compile(r"^KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)")

# Kalshi city/franchise shorthand -> ESPN abbreviation, ONLY where they differ
# (grounded off real tickers cross-checked against espn_boxscores.parquet for
# the same date -- see module docstring). An override only takes effect if the
# mapped code is present in the loaded boxscore's OWN abbr index.
_ABBR_OVERRIDES: Dict[str, str] = {
    "AZ": "ARI", "CWS": "CHW",
}


def _norm(s: str) -> str:
    return str(s or "").strip().upper()


def _build_abbr_index(abbrs: Any) -> set:
    return {_norm(a) for a in abbrs if str(a).strip()}


def parse_mlb_ticker(ticker: str) -> Optional[Tuple[Any, str]]:
    """Parse a Kalshi MLB ticker -> (date, tail) where tail is the raw
    uppercase AWAY+HOME concatenation (unsplit). None on no match -- never a
    guess. *date* is a datetime.date. Never raises."""
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
        logger.debug("parse_mlb_ticker(%s) failed: %s", ticker, exc)
        return None


def _resolve_abbr(code: str, abbr_index: set) -> Optional[str]:
    code = _norm(code)
    override = _ABBR_OVERRIDES.get(code)
    if override is not None and override in abbr_index:
        return override
    return code if code in abbr_index else None


def _split_tail(tail: str, abbr_index: set) -> Optional[Tuple[str, str]]:
    """Try every 2-way split of *tail* against the abbr index; return the
    UNIQUE (away_abbr, home_abbr) pairing, else None (ambiguous or no match)."""
    good = []
    for i in range(2, len(tail) - 1):
        a, h = _resolve_abbr(tail[:i], abbr_index), _resolve_abbr(tail[i:], abbr_index)
        if a is not None and h is not None and a != h:
            good.append((a, h))
    uniq = list({p for p in good})
    if len(uniq) != 1:
        return None
    return uniq[0]


class MlbTickerOutcomeResolver:
    """Resolve home_win for a Kalshi MLB in-play ticker from the local ESPN
    boxscore parquet. Loads ONCE (final rows only) and caches an abbr index +
    a (date, away, home) -> home_win lookup. Reused across many tickers; the
    per-file test can inject an in-memory frame instead of touching disk."""

    def __init__(self, boxscore_df: Any = None,
                 boxscore_parquet: Optional[Path] = None) -> None:
        self._ok = False
        self._abbr_index: set = set()
        self._final: Dict[Tuple[Any, str, str], int] = {}
        try:
            df = boxscore_df
            if df is None:
                import pandas as pd
                p = Path(boxscore_parquet) if boxscore_parquet is not None \
                    else DEFAULT_BOXSCORE_PARQUET
                if not p.exists():
                    return
                df = pd.read_parquet(p)
            self._ingest(df)
            self._ok = True
        except Exception as exc:  # noqa: BLE001 -- no parquet -> resolver is inert
            logger.debug("MlbTickerOutcomeResolver init failed: %s", exc)

    def _ingest(self, df: Any) -> None:
        import pandas as pd
        d = df
        if "status" in d.columns:
            d = d[d["status"].astype(str).str.upper().str.contains("FINAL")]
        d = d.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        self._abbr_index = _build_abbr_index(
            set(d["home_abbr"].astype(str)) | set(d["away_abbr"].astype(str)))
        for _, r in d.iterrows():
            home, away = _norm(r["home_abbr"]), _norm(r["away_abbr"])
            if not home or not away or pd.isna(r["date"]):
                continue
            try:
                hs, aws = float(r["home_score"]), float(r["away_score"])
            except (TypeError, ValueError):
                continue
            if hs == aws:
                continue  # ties are not a binary home_win label
            key = (r["date"].date(), away, home)
            self._final[key] = 1 if hs > aws else 0

    @property
    def available(self) -> bool:
        return self._ok and bool(self._final)

    def home_win(self, ticker: str) -> Optional[int]:
        """1 if home won, 0 if away won, None if unresolved/tie/not-final/
        ambiguous-split. Checks the parsed date +/- 1 day (Kalshi's ET book
        date can roll relative to the boxscore's own date convention). Never
        raises."""
        if not self._ok:
            return None
        parsed = parse_mlb_ticker(ticker)
        if parsed is None:
            return None
        import datetime as _dt
        date, tail = parsed
        split = _split_tail(tail, self._abbr_index)
        if split is None:
            return None
        away, home = split
        for delta in (0, -1, 1):
            key = (date + _dt.timedelta(days=delta), away, home)
            if key in self._final:
                return self._final[key]
        return None


__all__ = [
    "DEFAULT_BOXSCORE_PARQUET", "MlbTickerOutcomeResolver", "parse_mlb_ticker",
]
