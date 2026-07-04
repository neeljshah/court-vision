"""scripts.platformkit.venue_history.nba_close_corpus -- OWN-DATA NBA pregame
CLOSE corpus from our own Polymarket + Kalshi intra-game tick captures (user
declined a paid OddsAPI purchase; this builds the close corpus from venue
history already on disk). One row per NBA game = the venue's LAST price tick
strictly BEFORE tipoff, converted to home-win probability, oriented against
the REAL home team (see CRITICAL DATA FIX). Written as a provenance-labeled,
validation-only parquet -- NEVER pooled with forward pre-registered gates.
Kalshi-side building lives in the sibling nba_close_corpus_kalshi.py.

SOURCES (grounded 2026-07-04): PM data/venue_history/polymarket/nba/*.jsonl
(2023 pilot) + nba_2024plus/*.jsonl (both repeat docs, see DEDUP); Kalshi
data/venue_history/kalshi/nba/*.jsonl (2026 playoffs); games.parquet (regular-
season schedule, date-only, no clock); and data/cache/odds_api/
historical_events/*.json -- a PRE-EXISTING LOCAL CACHE (NOT a new purchase)
used STRICTLY as the tipoff-time reference (only on-disk source with a real UTC
commence_time), never as a probability source. Games outside its coverage, or
with no schedule match, are EXCLUDED + counted.

CRITICAL DATA FIX (do not regress): PM docs' "home"/"away" are OUTCOME[0]/[1]
from the market's listing order (e.g. slug "nba-sas-nyk-2024-12-25" lists SAS
first) -- NOT necessarily the true venue home. This module NEVER trusts that
label; it re-derives true home/away from games.parquet (unordered team-pair +
nearest-date join) and re-orients prob_home (flips 1-p when PM outcome0 is not
the real home). Kalshi tickers already carry an explicit away+home split.

DEDUP: PM jsonl repeats each game byte-for-byte (benign append artifact); keep
the FIRST per (date, market_slug). CLOSE DEFINITION: last tick with ts strictly
< the matched commence_time. PM/Kalshi are single-number prob feeds (no
bid/ask), so no two-sided vig-tolerance check applies -- recorded via `venue`.

OUTPUT: data/cache/venue_history/nba_close_corpus.parquet -- game_id, date,
home/away_team, home_win, venue, corpus_id, close_kind, close_ts,
close_prob_home, commence_time, seconds_before_tip, validation_only=True.
HONESTY: all exclusions are counted + returned in the build report, never
silently dropped. INVARIANTS: platformkit-only; ASCII only; offline; no
data/registry writes; no flag flips; no $-edge claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_nba_close_corpus.py -q
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.odds_provider.team_resolver import canonical

_REPO_ROOT = Path(__file__).resolve().parents[3]
PM_NBA_2023 = _REPO_ROOT / "data" / "venue_history" / "polymarket" / "nba"
PM_NBA_2024PLUS = _REPO_ROOT / "data" / "venue_history" / "polymarket" / "nba_2024plus"
KALSHI_NBA = _REPO_ROOT / "data" / "venue_history" / "kalshi" / "nba"
GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
ODDS_API_EVENTS_DIR = _REPO_ROOT / "data" / "cache" / "odds_api" / "historical_events"
DEFAULT_OUT = _REPO_ROOT / "data" / "cache" / "venue_history" / "nba_close_corpus.parquet"

_DATE_TOL_DAYS = 1  # schedule join tolerance (PM/Kalshi date vs games.parquet date)
_COMMENCE_TOL_DAYS = 2  # commence_time reference join tolerance


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@dataclass
class ScheduleIndex:
    """games.parquet -> {frozenset({canon_home, canon_away}): [(date, game_id,
    home_team, away_team, home_win), ...]}."""

    by_pair: Dict[frozenset, List[Tuple[Any, str, str, str, Optional[float]]]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = GAMES_PARQUET) -> "ScheduleIndex":
        import pandas as pd  # noqa: PLC0415

        idx: Dict[frozenset, List[Tuple[Any, str, str, str, Optional[float]]]] = {}
        if not path.exists():
            return cls(idx)
        df = pd.read_parquet(path)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for _, r in df.iterrows():
            if pd.isna(r["date"]):
                continue
            home, away = str(r["home_team"]), str(r["away_team"])
            ch, ca = canonical("nba", home), canonical("nba", away)
            hw = r.get("home_win")
            hw = None if hw is None or (isinstance(hw, float) and hw != hw) else float(hw)
            idx.setdefault(frozenset([ch, ca]), []).append(
                (r["date"].date(), str(r["game_id"]), home, away, hw))
        return cls(idx)

    def match(self, date_str: str, team_a: str, team_b: str) -> Optional[Tuple[Any, str, str, str, Optional[float]]]:
        """Unique nearest-date match for an unordered team pair, else None
        (no match or ambiguous -- both are honest exclusions upstream)."""
        key = frozenset([canonical("nba", team_a), canonical("nba", team_b)])
        cands = self.by_pair.get(key, [])
        if not cands:
            return None
        try:
            gdate = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None
        exact = [c for c in cands if c[0] == gdate]
        if len(exact) == 1:
            return exact[0]
        near = [c for c in cands if abs((c[0] - gdate).days) <= _DATE_TOL_DAYS]
        if len(near) == 1:
            return near[0]
        return None  # 0 or ambiguous (>=2) -- never guess


@dataclass
class CommenceIndex:
    """odds_api historical_events cache -> {frozenset(pair): [(commence_dt, home, away)]}.
    STRICTLY a tipoff-time reference (already-cached local data, not a new
    purchase) -- never used as the win-probability source."""

    by_pair: Dict[frozenset, List[Tuple[datetime, str, str]]] = field(default_factory=dict)
    n_events: int = 0

    @classmethod
    def load(cls, events_dir: Path = ODDS_API_EVENTS_DIR) -> "CommenceIndex":
        idx: Dict[frozenset, List[Tuple[datetime, str, str]]] = {}
        n = 0
        for fp in sorted(glob.glob(str(events_dir / "*.json"))):
            try:
                doc = json.loads(Path(fp).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for e in doc.get("data", []) or []:
                if e.get("sport_key") != "basketball_nba":
                    continue
                ct = _parse_ts(e.get("commence_time", ""))
                if ct is None:
                    continue
                home, away = str(e.get("home_team", "")), str(e.get("away_team", ""))
                key = frozenset([canonical("nba", home), canonical("nba", away)])
                idx.setdefault(key, []).append((ct, home, away))
                n += 1
        return cls(idx, n)

    def match(self, date_str: str, team_a: str, team_b: str) -> Optional[datetime]:
        key = frozenset([canonical("nba", team_a), canonical("nba", team_b)])
        cands = self.by_pair.get(key, [])
        if not cands:
            return None
        try:
            gdate = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        best, best_gap = None, None
        for ct, _h, _a in cands:
            gap = abs((ct - gdate).total_seconds())
            if gap <= _COMMENCE_TOL_DAYS * 86400 and (best_gap is None or gap < best_gap):
                best, best_gap = ct, gap
        return best


def _iter_pm_docs(directory: Path) -> List[Dict[str, Any]]:
    """Read every *.jsonl in *directory*, de-duplicating identical
    (date, market_slug) repeats (see module DEDUP note). Never raises on a
    malformed line -- skips it."""
    seen: set = set()
    docs: List[Dict[str, Any]] = []
    for fp in sorted(glob.glob(str(directory / "*.jsonl"))):
        try:
            lines = Path(fp).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (doc.get("date"), doc.get("market_slug") or doc.get("event_slug"))
            if key in seen:
                continue
            seen.add(key)
            docs.append(doc)
    return docs


def _last_tick_before(prices: List[Dict[str, Any]], cutoff: datetime,
                      prob_key: str) -> Optional[Tuple[datetime, float]]:
    best_ts, best_p = None, None
    for pt in prices:
        ts = _parse_ts(pt.get("ts", ""))
        p = pt.get(prob_key)
        if ts is None or p is None or ts >= cutoff:
            continue
        if best_ts is None or ts > best_ts:
            best_ts, best_p = ts, float(p)
    if best_ts is None:
        return None
    return best_ts, best_p


def _build_from_polymarket(directory: Path, corpus_id: str, sched: ScheduleIndex,
                           comm: CommenceIndex, exclusions: Dict[str, int]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for doc in _iter_pm_docs(directory):
        date_str = str(doc.get("date", ""))
        outcome0, outcome1 = str(doc.get("home", "")), str(doc.get("away", ""))
        if not date_str or not outcome0 or not outcome1:
            exclusions["malformed_doc"] += 1
            continue
        sched_match = sched.match(date_str, outcome0, outcome1)
        if sched_match is None:
            exclusions["no_schedule_match"] += 1
            continue
        _sdate, game_id, real_home, real_away, home_win = sched_match
        commence = comm.match(date_str, outcome0, outcome1)
        if commence is None:
            exclusions["no_commence_time_reference"] += 1
            continue
        prices = doc.get("prices") or []
        tick = _last_tick_before(prices, commence, "prob_home")
        if tick is None:
            exclusions["no_tick_before_tipoff"] += 1
            continue
        ts, p_outcome0 = tick
        # Re-orient: PM's prob_home is P(outcome0 wins); flip if outcome0 != real home.
        flip = canonical("nba", outcome0) != canonical("nba", real_home)
        close_prob_home = round(1.0 - p_outcome0, 4) if flip else round(p_outcome0, 4)
        rows.append({
            "game_id": game_id, "date": date_str, "home_team": real_home,
            "away_team": real_away, "home_win": home_win, "venue": "polymarket",
            "corpus_id": corpus_id, "close_kind": "last_tick_before_commence",
            "close_ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close_prob_home": close_prob_home,
            "commence_time": commence.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seconds_before_tip": round((commence - ts).total_seconds(), 1),
            "validation_only": True,
        })
    return rows


def build_corpus(*, out_path: Optional[Path] = None,
                 schedule_index: Optional[ScheduleIndex] = None,
                 commence_index: Optional[CommenceIndex] = None) -> Dict[str, Any]:
    """Build the NBA pregame close corpus from our own venue-history ticks.
    Writes a provenance-labeled parquet and returns a build report with
    honest exclusion counts. Never pools with forward gates (validation_only=True)."""
    sched = schedule_index or ScheduleIndex.load()
    comm = commence_index or CommenceIndex.load()
    exclusions: Dict[str, int] = {
        "malformed_doc": 0, "no_schedule_match": 0, "no_commence_time_reference": 0,
        "no_tick_before_tipoff": 0, "kalshi_unparseable_ticker": 0,
    }
    from scripts.platformkit.venue_history.nba_close_corpus_kalshi import build_from_kalshi  # noqa: PLC0415

    rows: List[Dict[str, Any]] = []
    rows += _build_from_polymarket(PM_NBA_2023, "polymarket_nba_2023_pilot", sched, comm, exclusions)
    rows += _build_from_polymarket(PM_NBA_2024PLUS, "polymarket_nba_2024plus", sched, comm, exclusions)
    rows += build_from_kalshi(KALSHI_NBA, sched, comm, exclusions)

    # De-dup across venues/windows on game_id (keep first: PM pilot, then
    # 2024plus, then Kalshi -- order rows were appended above).
    by_game: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        by_game.setdefault(r["game_id"], r)
    final_rows = list(by_game.values())

    dest = Path(out_path) if out_path is not None else DEFAULT_OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    _write_parquet(final_rows, dest)

    n_considered = len(rows) + sum(exclusions.values())
    return {
        "n_games_written": len(final_rows), "n_rows_pre_dedup": len(rows),
        "n_excluded_total": sum(exclusions.values()), "exclusions": exclusions,
        "n_considered": n_considered, "out_path": str(dest),
        "note": ("validation-only NBA pregame close corpus distilled from our own "
                 "Polymarket + Kalshi tick captures; NEVER pooled with forward gates"),
    }


def _write_parquet(rows: List[Dict[str, Any]], dest: Path) -> None:
    import pandas as pd  # noqa: PLC0415
    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415

    cols = ["game_id", "date", "home_team", "away_team", "home_win", "venue",
            "corpus_id", "close_kind", "close_ts", "close_prob_home",
            "commence_time", "seconds_before_tip", "validation_only"]
    df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, str(dest))


def _main() -> int:
    rep = build_corpus()
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
