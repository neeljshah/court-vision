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

TICKER SHAPE (grounded against 201 real tickers captured 2026-06-28..07-04,
PLUS a real doubleheader slate captured 2026-07-07: KXMLBGAME-26JUL071415MILSTLG1
/ KXMLBGAME-26JUL071945MILSTLG2)
----------------------------------------------------------------------------
    KXMLBGAME-<YY><MON><DD><HHMM><AWAY><HOME>[G<n>]
e.g. KXMLBGAME-26JUL011235CWSBAL (2026-07-01, 12:35 ET book time, Cubs... no --
away=CWS (Chicago White Sox), home=BAL (Baltimore Orioles)). Unlike the WNBA
ticker (no HHMM field), the MLB ticker DOES carry a 4-digit HHMM between the
date and the team-code tail -- confirmed on every one of the 201 captured
tickers (fixed-width \\d{4} immediately after the 2-digit day, immediately
before the first non-digit character). A doubleheader ticker carries a
trailing G1/G2 (game number) appended directly to the team tail with no
delimiter -- the tail regex is LAZY and the G-group requires a digit so a
real team code ending in "G" (e.g. SFG) never loses its letter (mirrors
ingame_outcome_label.py's proven-correct ticker regex; this module previously
used a GREEDY tail regex that swallowed the "G" of "G1"/"G2" into the team
tail, corrupting the split for every doubleheader ticker -- FIXED 2026-07-11).

Kalshi's OWN team-code shorthand differs from ESPN's abbreviation for a
handful of franchises (grounded from the 201 real tickers' team-code tails
cross-checked against espn_boxscores.parquet's home_abbr/away_abbr for the
same date, same override set as ingame_outcome_label.py): AZ->ARI
(Diamondbacks), CWS->CHW (White Sox), WSN->WSH, SFG->SF, SDP->SD, TBR->TB,
KCR->KC, OAK->ATH. An override is only ever ACCEPTED if the resulting
abbreviation is ALSO present in the loaded boxscore's own abbr index (see
_resolve_abbr, same "never mislabel" contract as wnba_outcome_resolver.
_resolve_abbr) -- a stale or wrong override entry here just fails to match,
it can never mislabel a different real team.

DOUBLEHEADERS: a (date, away, home) key can legitimately carry 2 boxscore
rows. Rows are kept as a start-time-ordered LIST (never a single overwritten
scalar -- the pre-fix version silently overwrote G1's outcome with G2's, or
vice versa, on dict insert). A ticker carrying no G-suffix on a 2-row key
fails CLOSED (None, never a guess); a ticker carrying G<n> picks the n-th row
by start_time order, itself failing closed if rows lack a start_time to order
by. Mirrors ingame_outcome_label.MlbOutcomeResolver._pick exactly.

HONESTY: probability/label space only; no $ field; an unresolvable ticker, an
ambiguous split, an ambiguous doubleheader, a tie, or a not-yet-final game
returns None (never a guess).

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

# KXMLBGAME-<YY><MON><DD><HHMM><AWAY+HOME concatenated>[G<n> doubleheader][-<side>]
# -- grounded 2026-07-04 against 201 real captured tickers, doubleheader shape
# (...MILSTLG1 / ...MILSTLG2) grounded 2026-07-07 (data/cache/inplay_history/mlb).
# Team tail is LAZY + the G-group needs a DIGIT, so an abbr ending in G (SFG)
# never loses its G to the doubleheader group (mirrors ingame_outcome_label.py).
_TICKER_RE = re.compile(
    r"^KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+?)(?:G(\d))?(?=-|$)")

# Kalshi city/franchise shorthand -> ESPN abbreviation, ONLY where they differ
# (grounded off real tickers cross-checked against espn_boxscores.parquet for
# the same date -- see module docstring; same set as ingame_outcome_label.py).
# An override only takes effect if the mapped code is present in the loaded
# boxscore's OWN abbr index.
_ABBR_OVERRIDES: Dict[str, str] = {
    "AZ": "ARI", "CWS": "CHW", "WSN": "WSH", "SFG": "SF", "SDP": "SD",
    "TBR": "TB", "KCR": "KC", "OAK": "ATH",
}


def _norm(s: str) -> str:
    return str(s or "").strip().upper()


def _build_abbr_index(abbrs: Any) -> set:
    return {_norm(a) for a in abbrs if str(a).strip()}


def parse_mlb_ticker(ticker: str) -> Optional[Tuple[Any, str, Optional[int]]]:
    """Parse a Kalshi MLB ticker -> (date, tail, game_number) where tail is the
    raw uppercase AWAY+HOME concatenation (unsplit, doubleheader G-suffix
    already stripped) and game_number is the doubleheader index from a
    trailing G<digit> (e.g. ...MILSTLG1 -> 1), None for a single game. None on
    no match -- never a guess. *date* is a datetime.date. Never raises."""
    try:
        import datetime as _dt
        m = _TICKER_RE.match(_norm(ticker))
        if not m:
            return None
        yy, mon, dd, _hhmm, tail, gnum = m.groups()
        month = _MONTHS.get(mon)
        if month is None:
            return None
        date = _dt.date(2000 + int(yy), month, int(dd))
        if len(tail) < 4:
            return None
        return (date, tail, int(gnum) if gnum else None)
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


def _home_win(score: Tuple[float, float]) -> Optional[int]:
    """1/0 from (home_score, away_score); None on a tie (not a binary label)."""
    hs, aws = score
    return None if hs == aws else (1 if hs > aws else 0)


class MlbTickerOutcomeResolver:
    """Resolve home_win for a Kalshi MLB in-play ticker from the local ESPN
    boxscore parquet. Loads ONCE (final rows only) and caches an abbr index +
    a (date, away, home) -> home_win lookup. Reused across many tickers; the
    per-file test can inject an in-memory frame instead of touching disk."""

    def __init__(self, boxscore_df: Any = None,
                 boxscore_parquet: Optional[Path] = None,
                 games_fallback: bool = False) -> None:
        self._ok = False
        self._abbr_index: set = set()
        # S95: games{,_current}.parquet finals as a SECOND map, OFF by default.
        # Kept separate from _final (never merged) so the ESPN corpus always
        # answers first and the fallback is exact-date only -- the +/-1 hop
        # mislabelled a postponement doubleheader in S91.
        self._fb: Dict[Tuple[Any, str, str], list] = {}
        # (date, away, home) -> [(start_time_iso_str, (home_score, away_score)), ...]
        # A list because a doubleheader legitimately has 2 rows for one key --
        # NEVER a scalar overwrite (that was the bug: dict-assign silently
        # dropped one game of every doubleheader -- FIXED 2026-07-11).
        self._final: Dict[Tuple[Any, str, str], list] = {}
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
        if games_fallback and boxscore_df is None:
            self._load_fallback()

    def _load_fallback(self) -> None:
        """S95: games{,_current}.parquet finals -> _fb. Never raises."""
        try:
            from scripts.platformkit.ingame import mlb_games_outcome_fallback as _g
            df = _g.load_games_box_frame()
            if df is not None:
                self._ingest(df, into=self._fb)
            self._ok = self._ok or bool(self._fb)
        except Exception as exc:  # noqa: BLE001 -- no fallback is not fatal
            logger.debug("MlbTickerOutcomeResolver fallback load failed: %s", exc)

    def _ingest(self, df: Any, into: Optional[Dict] = None) -> None:
        import pandas as pd
        target = self._final if into is None else into
        d = df
        if "status" in d.columns:
            d = d[d["status"].astype(str).str.upper().str.contains("FINAL")]
        d = d.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        self._abbr_index |= _build_abbr_index(
            set(d["home_abbr"].astype(str)) | set(d["away_abbr"].astype(str)))
        has_st = "start_time" in d.columns
        for _, r in d.iterrows():
            home, away = _norm(r["home_abbr"]), _norm(r["away_abbr"])
            if not home or not away or pd.isna(r["date"]):
                continue
            try:
                hs, aws = float(r["home_score"]), float(r["away_score"])
            except (TypeError, ValueError):
                continue
            key = (r["date"].date(), away, home)
            st = str(r["start_time"]) if has_st and pd.notna(r["start_time"]) else ""
            target.setdefault(key, []).append((st, (hs, aws)))

    @property
    def available(self) -> bool:
        return self._ok and bool(self._final or self._fb)

    def _pick(self, key: Tuple[Any, str, str], game_number: Optional[int],
              rows_map: Optional[Dict] = None) -> Optional[Tuple[float, float]]:
        """Pick ONE (home_score, away_score) for a (date, away, home) key,
        doubleheader-aware -- mirrors ingame_outcome_label.MlbOutcomeResolver._pick.

        game_number None + exactly 1 row -> that row (the pre-doubleheader path).
        game_number None + 2+ rows -> None (ambiguous doubleheader, fail closed).
        game_number N -> rows ordered by start_time (ISO strings sort correctly),
        G1 = earliest; N beyond the finals on disk, or 2+ rows we cannot order
        (missing start_time), -> None (fail closed, never a guess)."""
        rows = (self._final if rows_map is None else rows_map).get(key)
        if not rows:
            return None
        if game_number is None:
            return rows[0][1] if len(rows) == 1 else None
        if len(rows) > 1 and any(not st for st, _ in rows):
            return None
        if game_number > len(rows):
            return None
        return sorted(rows)[game_number - 1][1]

    def home_win(self, ticker: str) -> Optional[int]:
        """1 if home won, 0 if away won, None if unresolved/tie/not-final/
        ambiguous-split/ambiguous-doubleheader. Checks the parsed date and a
        +1 day tolerance only (a late game can file on the NEXT day); -1 is
        FORBIDDEN -- ticker and box dates are both ET, so a box row dated
        BEFORE the ticker date is a different game of the same series (same
        landmine ingame_outcome_label.MlbOutcomeResolver._resolve fixed
        2026-07-07). Never raises."""
        if not self._ok:
            return None
        parsed = parse_mlb_ticker(ticker)
        if parsed is None:
            return None
        import datetime as _dt
        date, tail, gnum = parsed
        split = _split_tail(tail, self._abbr_index)
        if split is None:
            return None
        away, home = split
        for delta in (0, 1):
            score = self._pick((date + _dt.timedelta(days=delta), away, home), gnum)
            if score is not None:
                return _home_win(score)
        # S95 (opt-in, empty unless games_fallback=True): EXACT date only.
        fb = self._pick((date, away, home), gnum, self._fb)
        return _home_win(fb) if fb is not None else None


__all__ = [
    "DEFAULT_BOXSCORE_PARQUET", "MlbTickerOutcomeResolver", "parse_mlb_ticker",
]
