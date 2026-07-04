"""scripts.platformkit.ingame.soccer_outcome -- OFFLINE leak-free outcome resolver
for Kalshi WORLD CUP in-game tickers (the soccer counterpart to
ingame_outcome_label.MlbOutcomeResolver, contract-compatible: final_score(ticker)
-> (home_score, away_score) | None).

THE GAP THIS CLOSES
-------------------
paper_ingame in-game bets are keyed by the KALSHI TICKER (e.g.
KXWCGAME-26JUN29GERPAR), which encodes the date plus the away+home 3-letter FIFA
codes with NO delimiter -- and, unlike MLB, WC games can legitimately end in a
draw. ingame_paper_settle had an MLB resolver but no soccer one, so every
paper_ingame soccer_intl bet stayed open forever (9 stuck at 2026-07-01).

WHY THIS READS data/domains/soccer_intl/espn_finals.parquet, NOT results.parquet
----------------------------------------------------------------------------
The historical results.parquet corpus is (a) stale (not refreshed past
2026-06-27) and (b) sourced independently of ESPN, so for a neutral-site
tournament match its home/away assignment is NOT guaranteed to match the
home/away ESPN reported when inplay_capture_loop wrote the bet's `side` field.
Joining against a differently-sourced home/away label risks a SILENTLY SWAPPED
side. Instead this resolves against domains.soccer_intl.ingest_espn_finals'
output -- the SAME provider (ESPN) inplay_capture_loop already reads for live
state -- so the settle-side home/away always agrees with the placement-side
label. We never assume the ticker's away+home ORDER either: the ambiguous 3/3
split is resolved to two team NAMES, then the pair is looked up (order-
independent) against the real finals corpus, which supplies the true home/away
+ scores directly from ESPN.

HONESTY: probability/label space only; no $ field; an unresolvable ticker, an
ambiguous code split, or a not-yet-final game returns None (NEVER a guess or a
fabricated settle).

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network (reads a local parquet); never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_soccer_outcome.py -q
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FINALS_PARQUET = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "espn_finals.parquet"

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KXWCGAME-<YY><MON><DD><CODE3><CODE3>[-<side>]  (no HHMM component, unlike MLB;
# FIFA/IOC country codes are ALWAYS exactly 3 letters, so the tail is a fixed 6-char
# block -- no ambiguous multi-position search needed like MLB's variable-length
# club abbreviations).
_TICKER_RE = re.compile(r"^KXWCGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]{6})")

# Well-known FIFA-code exceptions where the code is NOT simply the team's first 3
# letters (e.g. "Ivory Coast" -> CIV, not IVO). Small + safe: an override is only
# ever ACCEPTED if the resulting name also appears in the real loaded finals data
# (see _resolve_code), so a stale/wrong entry here just fails to match -- it can
# never mislabel a different real team.
_CODE_OVERRIDES: Dict[str, str] = {
    "CIV": "Ivory Coast", "COD": "Congo DR", "COG": "Congo", "KOR": "South Korea",
    "PRK": "North Korea", "NED": "Netherlands", "ESP": "Spain", "SUI": "Switzerland",
    "USA": "United States", "CPV": "Cape Verde", "KSA": "Saudi Arabia",
    "NZL": "New Zealand", "CRC": "Costa Rica", "JPN": "Japan", "MAR": "Morocco",
    "BIH": "Bosnia-Herzegovina", "RSA": "South Africa", "UAE": "United Arab Emirates",
    "CHN": "China", "TPE": "Chinese Taipei", "GER": "Germany", "URU": "Uruguay",
    "DEN": "Denmark", "POR": "Portugal", "GRE": "Greece", "TUR": "Turkey",
    "SCO": "Scotland", "WAL": "Wales", "IRL": "Republic of Ireland",
    # Added 2026-07-03 (Lane 5 soccer resolver audit) -- confirmed against real
    # failing WC tickers in data/cache/ingame_grade/soccer_intl/. Each of these
    # FIFA/IOC codes has NO unique first-3-letter match in the real ESPN name
    # corpus (either no match at all, or a prefix collision with another team),
    # so without an explicit override the ticker resolved to None forever.
    "AUT": "Austria",   # "Austria"[:3]="AUS" != "AUT" -- no natural match
    "AUS": "Australia", # "AUS" prefix-collides Austria/Australia -- disambiguate
    "DZA": "Algeria",   # "Algeria"[:3]="ALG" != "DZA"
    "HTI": "Haiti",     # "Haiti"[:3]="HAI" != "HTI"
    "IRQ": "Iraq",      # "Iraq"[:3]="IRA" != "IRQ" -- also collides with Iran
    "IRI": "Iran",      # "Iran"[:3]="IRA" != "IRI" -- also collides with Iraq
}


def _norm(s: str) -> str:
    return str(s or "").strip().upper()


def parse_wc_ticker(ticker: str) -> Optional[Tuple[Any, str, str]]:
    """Parse a Kalshi WC ticker -> (date, codeA, codeB) -- order UNKNOWN/irrelevant
    (the resolver looks the pair up regardless of order). None on no match --
    never a guess. *date* is a datetime.date."""
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
        return (date, tail[:3], tail[3:6])
    except Exception as exc:  # noqa: BLE001 -- a bad ticker is unresolvable, never fatal
        logger.debug("parse_wc_ticker(%s) failed: %s", ticker, exc)
        return None


def _resolve_code(code: str, name_index: Dict[str, str]) -> Optional[str]:
    """3-letter FIFA code -> the EXACT team-name spelling in the loaded finals
    data, or None if no single confident match exists. *name_index* maps an
    UPPERCASED team name to its real (ESPN) spelling.

    Order: (1) an override whose target name is actually present in this corpus;
    (2) the UNIQUE real name whose first 3 letters equal the code (auto-derived
    from the corpus itself, not hand-typed -- avoids encoding a wrong spelling).
    Ambiguous (>1 match) or no match -> None, never a guess.
    """
    code = _norm(code)
    override = _CODE_OVERRIDES.get(code)
    if override is not None and _norm(override) in name_index:
        return name_index[_norm(override)]
    matches = [real for key, real in name_index.items() if key[:3] == code]
    if len(matches) == 1:
        return matches[0]
    return None


class SoccerOutcomeResolver:
    """Resolve the final (home_score, away_score) for a Kalshi WC ticker from the
    local ESPN-sourced finals parquet (domains.soccer_intl.ingest_espn_finals).

    Loads the parquet ONCE (completed rows only) and caches a team-name index +
    a (date, unordered-team-pair) -> (home_name, away_name, home_score,
    away_score) lookup. Reused across many tickers; the per-file test can inject
    an in-memory frame instead of touching disk.
    """

    def __init__(self, finals_df: Any = None,
                 finals_parquet: Optional[Path] = None) -> None:
        self._ok = False
        self._name_index: Dict[str, str] = {}
        self._by_pair: Dict[Tuple[Any, FrozenSet[str]], Tuple[str, str, int, int]] = {}
        try:
            df = finals_df
            if df is None:
                import pandas as pd
                p = Path(finals_parquet) if finals_parquet is not None else DEFAULT_FINALS_PARQUET
                if not p.exists():
                    return
                df = pd.read_parquet(p)
            self._ingest(df)
            self._ok = True
        except Exception as exc:  # noqa: BLE001 -- no parquet -> resolver is inert, not fatal
            logger.debug("SoccerOutcomeResolver init failed: %s", exc)

    def _ingest(self, df: Any) -> None:
        import pandas as pd
        d = df
        if "completed" in d.columns:
            d = d[d["completed"].astype(bool)]
        d = d.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        for _, r in d.iterrows():
            home, away = str(r["home_team"]).strip(), str(r["away_team"]).strip()
            if not home or not away or pd.isna(r["date"]):
                continue
            try:
                hs, as_ = int(float(r["home_score"])), int(float(r["away_score"]))
            except (TypeError, ValueError):
                continue
            self._name_index[_norm(home)] = home
            self._name_index[_norm(away)] = away
            key = (r["date"].date(), frozenset({_norm(home), _norm(away)}))
            self._by_pair[key] = (home, away, hs, as_)

    @property
    def available(self) -> bool:
        return self._ok and bool(self._by_pair)

    def final_score(self, ticker: str) -> Optional[Tuple[int, int]]:
        """(home_score, away_score) for a Kalshi WC ticker's FINAL game, else
        None. Draws resolve fine (returned tied -- grade_paper._outcome pushes
        soccer draws). Never raises."""
        if not self._ok:
            return None
        parsed = parse_wc_ticker(ticker)
        if parsed is None:
            return None
        import datetime as _dt
        date, code_a, code_b = parsed
        name_a = _resolve_code(code_a, self._name_index)
        name_b = _resolve_code(code_b, self._name_index)
        if name_a is None or name_b is None:
            return None
        pair = frozenset({_norm(name_a), _norm(name_b)})
        for delta in (0, -1, 1):
            key = (date + _dt.timedelta(days=delta), pair)
            hit = self._by_pair.get(key)
            if hit is not None:
                _home, _away, hs, as_ = hit
                return (hs, as_)
        return None


__all__ = [
    "DEFAULT_FINALS_PARQUET", "SoccerOutcomeResolver", "parse_wc_ticker",
]
