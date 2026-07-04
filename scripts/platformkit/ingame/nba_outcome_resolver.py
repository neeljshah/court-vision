"""scripts.platformkit.ingame.nba_outcome_resolver -- OFFLINE leak-free outcome
resolver for Kalshi NBA in-play tickers (the NBA counterpart to
wnba_outcome_resolver.WnbaOutcomeResolver / ingame_outcome_label.MlbOutcomeResolver
/ npb_outcome_resolver.NpbOutcomeResolver / kbo_outcome_resolver.KboOutcomeResolver).

THE GAP THIS CLOSES
-------------------
Every other sport wired into inplay capture has an outcome resolver; NBA does
not, and neither ingame_tail_scan_multi nor ingame_tail_gate_multi has an 'nba'
entry. This module supplies home_win(ticker) -> {0,1}|None keyed DIRECTLY off
the Kalshi ticker, reading the local data/domains/basketball_nba/games.parquet
(game_id, date, season, home_team, away_team, home_win -- home_win is ALREADY a
clean 0/1 float derived upstream, no ties possible in NBA regulation+OT), the
SAME "already-resolved home_win column" pattern used by npb/kbo (not the
espn_boxscores.parquet route, which mixes STATUS_FINAL rows with older
None-status rows and has 67 same-score rows that look like data-quality noise,
not real NBA ties -- games.parquet is the clean source).

TICKER SHAPE (GROUNDED live 2026-07-04 against the Kalshi public API)
-----------------------------------------------------------------------
Fetched 182 settled KXNBAGAME markets (48 distinct events, 26 distinct
matchup-tails, 15 teams -- 2026 playoffs only; off-season, so no open markets
exist and the regular-season's other 15 franchises never appear in this
sample). REAL shape, identical to WNBA/NPB (no HHMM field):
  KXNBAGAME-<YY><MON><DD><AWAY+HOME concatenated>-<SIDE>
e.g. KXNBAGAME-26JUN13NYKSAS-SAS (Game 5: New York at San Antonio, San
Antonio home team, ticker verified settled 2026-07-04). The tail concatenates
AWAY then HOME with NO delimiter, mirroring wnba_outcome_resolver's
_split_tail (tries every 2-way split, keeps ONLY a unique match -- an
ambiguous or no-match split returns None, never a guess).

TEAM CODES: all 15 codes observed live (ATL, BOS, CLE, DEN, DET, HOU, LAL,
MIN, NYK, OKC, ORL, PHI, POR, SAS, TOR) are IDENTICAL, byte-for-byte, to
games.parquet's own home_team/away_team spelling -- confirmed by direct set
intersection, not assumed. The 15 franchises never observed live this
off-season (BKN, CHA, CHI, DAL, GSW, IND, LAC, MEM, MIA, MIL, NOP, PHX, SAC,
UTA, WAS) are given the SAME plain 3-letter code Kalshi already used for every
other team (its own convention, not ESPN's -- e.g. Kalshi's own confirmed
"NYK" not ESPN's "NY", confirmed "SAS" not ESPN's "SA") as the override
target; per _resolve_abbr's safety discipline (mirrored from
wnba_outcome_resolver), an override is ACCEPTED only if that exact string is
ALSO present in the loaded games.parquet's own team-name index, so a wrong
guess for an unobserved team just fails to match -- it can never mislabel a
different real team.

HONESTY: probability/label space only; no $ field; an unresolvable ticker, an
ambiguous split, a tied score (0 rows in games.parquet, but the guard stays
for defense-in-depth), or a game not present in games.parquet returns None
(NEVER a guess or a fabricated settle). This only supplies the held-out
target for a CALIBRATION verdict, never an edge or ROI.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network; never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_nba_outcome_resolver.py -q
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KXNBAGAME-<YY><MON><DD><AWAY+HOME concatenated>[-<side>] -- GROUNDED live
# 2026-07-04 against 182 real settled Kalshi tickers; see module docstring.
# NO HHMM field (same shape family as WNBA/NPB).
_TICKER_RE = re.compile(r"^KXNBAGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)")

# Kalshi ticker code -> games.parquet team-name spelling. The 15 codes marked
# "observed" were fetched directly off 182 live settled KXNBAGAME tickers
# (2026 playoffs); the other 15 are the same plain-code convention Kalshi
# already confirmed for every observed team, offered ONLY as a fallback that
# _resolve_abbr accepts solely if it is ALSO present in games.parquet's own
# index (see module docstring) -- a wrong guess here degrades to an honest
# unresolved split, never a mislabel.
_ABBR_OVERRIDES: Dict[str, str] = {
    "ATL": "ATL", "BOS": "BOS", "CLE": "CLE", "DEN": "DEN", "DET": "DET",
    "HOU": "HOU", "LAL": "LAL", "MIN": "MIN", "NYK": "NYK", "OKC": "OKC",
    "ORL": "ORL", "PHI": "PHI", "POR": "POR", "SAS": "SAS", "TOR": "TOR",
    # unobserved this off-season (fallback only; must also match parquet index)
    "BKN": "BKN", "CHA": "CHA", "CHI": "CHI", "DAL": "DAL", "GSW": "GSW",
    "IND": "IND", "LAC": "LAC", "MEM": "MEM", "MIA": "MIA", "MIL": "MIL",
    "NOP": "NOP", "PHX": "PHX", "SAC": "SAC", "UTA": "UTA", "WAS": "WAS",
}


def _norm(s: str) -> str:
    return str(s or "").strip().upper()


def _build_name_index(names: Any) -> Dict[str, str]:
    """UPPERCASED code -> real parquet spelling, derived from the parquet's
    own team codes (verbatim + first-3-letters), never hand-typed spellings."""
    idx: Dict[str, str] = {}
    for name in names:
        n = str(name).strip()
        if not n:
            continue
        key_full = _norm(n)
        idx.setdefault(key_full, n)
        idx.setdefault(key_full[:3], n)
    return idx


def parse_nba_ticker(ticker: str) -> Optional[Tuple[Any, str, str]]:
    """Parse a Kalshi NBA ticker -> (date, tail, tail) -- the tail is a RAW
    uppercase substring (not yet resolved to a team code); the resolver joins
    it against games.parquet's own name index. None on no match -- never a
    guess. *date* is a datetime.date. Never raises."""
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
        logger.debug("parse_nba_ticker(%s) failed: %s", ticker, exc)
        return None


def _resolve_abbr(code: str, name_index: Dict[str, str]) -> Optional[str]:
    code = _norm(code)
    override = _ABBR_OVERRIDES.get(code)
    if override is not None and _norm(override) in name_index and \
            name_index[_norm(override)] == override:
        return override
    return name_index.get(code)


def _split_tail(tail: str, name_index: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """Try every 2-way split of *tail* against the name index; return the UNIQUE
    (away_code, home_code) pairing, else None (ambiguous or no match)."""
    good = []
    for i in range(2, len(tail) - 1):
        a, h = _resolve_abbr(tail[:i], name_index), _resolve_abbr(tail[i:], name_index)
        if a is not None and h is not None and a != h:
            good.append((a, h))
    uniq = list({p for p in good})
    if len(uniq) != 1:
        return None
    return uniq[0]


class NbaOutcomeResolver:
    """Resolve home_win for a Kalshi NBA ticker from the local games.parquet
    (already-clean home_win column, no ties possible). Loads ONCE and caches
    a team-code index + a (date, away, home) -> home_win lookup. Reused
    across many tickers; the per-file test can inject an in-memory frame
    instead of touching disk."""

    def __init__(self, games_df: Any = None,
                 games_parquet: Optional[Path] = None) -> None:
        self._ok = False
        self._name_index: Dict[str, str] = {}
        self._final: Dict[Tuple[Any, str, str], int] = {}
        self._scores: Dict[Tuple[Any, str, str], Tuple[int, int]] = {}
        try:
            df = games_df
            if df is None:
                import pandas as pd
                p = Path(games_parquet) if games_parquet is not None \
                    else DEFAULT_GAMES_PARQUET
                if not p.exists():
                    return
                df = pd.read_parquet(p)
            self._ingest(df)
            self._ok = True
        except Exception as exc:  # noqa: BLE001 -- no parquet -> resolver is inert
            logger.debug("NbaOutcomeResolver init failed: %s", exc)

    def _ingest(self, df: Any) -> None:
        import pandas as pd
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        names = set(d["home_team"].astype(str)) | set(d["away_team"].astype(str))
        self._name_index = _build_name_index(names)
        has_scores = "home_pts" in d.columns and "away_pts" in d.columns
        for _, r in d.iterrows():
            home, away = str(r["home_team"]).strip(), str(r["away_team"]).strip()
            if not home or not away or pd.isna(r["date"]):
                continue
            try:
                hw = r["home_win"]
                if pd.isna(hw):
                    continue
                hw = int(round(float(hw)))
            except (TypeError, ValueError):
                continue
            key = (r["date"].date(), away, home)
            self._final[key] = hw
            if has_scores:
                try:
                    hp, ap = float(r["home_pts"]), float(r["away_pts"])
                    self._scores[key] = (int(hp), int(ap))
                except (TypeError, ValueError):
                    pass

    @property
    def available(self) -> bool:
        return self._ok and bool(self._final)

    def home_win(self, ticker: str) -> Optional[int]:
        """1 if home won, 0 if away won, None if unresolved/not-final/
        ambiguous-split. Never raises."""
        if not self._ok:
            return None
        parsed = parse_nba_ticker(ticker)
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
        """(home_score, away_score) for a Kalshi ticker's FINAL game, else
        None -- only available when games_df carries home_pts/away_pts.
        Never raises."""
        if not self._ok:
            return None
        parsed = parse_nba_ticker(ticker)
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
    "DEFAULT_GAMES_PARQUET", "NbaOutcomeResolver", "parse_nba_ticker",
]
