"""scripts.platformkit.pm_trading.paper_today_support -- pure/IO helpers for the
PAPER today-runner (run_paper_today).

Split out to keep both files small and the orchestrator readable. Everything here
is pure or local-file IO: odds-index building, event-metadata + side resolution,
the closing-line proxy, dedup keys, the predictions JSONL store, and the per-cycle
_Ctx. NO network at import; no $ edge; no real orders (this layer never bets).

Build only under scripts/platformkit/; <=300 LOC; no secrets.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from scripts.platformkit.odds_provider.aggregate import aggregate, teams_match
from scripts.platformkit.odds_provider.base import OddsEvent
from scripts.platformkit.pm_trading.paper_autobet import AutoBetConfig

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
# repo_root/data/frontend/... (parents[2] is the repo root, matching clv_ledger).
DEFAULT_PREDICTIONS = _HERE.parents[2] / "data" / "frontend" / "paper_predictions.jsonl"

# Permissive paper floor: record a priced pick unless deeply -EV (we GATHER CLV
# data, not filter to winners). would_pass_real_gate is the stricter EV>0 tag.
PAPER_EV_FLOOR = -0.02
DEFAULT_SPORTS = ("mlb", "soccer_intl", "nba", "tennis", "wnba")


@dataclass
class Ctx:
    """Per-cycle invariant context threaded through the row handlers."""
    cfg: AutoBetConfig
    day: str
    lpath: Path
    ppath: Path
    ledger_keys: Set = field(default_factory=set)
    pred_keys: Set = field(default_factory=set)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def odds_index(sport: str) -> Tuple[Callable[..., Optional[Dict[str, Dict[str, float]]]],
                                    List[OddsEvent]]:
    """Aggregated odds lookup for *sport* + merged events (for event metadata).
    Mirrors aggregate.to_odds_lookup, keeping events for event_id/commence_time."""
    try:
        payload = aggregate(sport)
        events = [OddsEvent(**dict(e)) for e in payload.get("events", [])]
    except Exception as exc:  # noqa: BLE001 -- an odds miss is never fatal
        logger.warning("odds aggregate failed for %s: %s", sport, exc)
        events = []

    def _lookup(s: str, home: str, away: str
                ) -> Optional[Dict[str, Dict[str, float]]]:
        if s.lower() != sport.lower():
            return None
        for ev in events:
            straight = teams_match(ev.home, home, s) and teams_match(ev.away, away, s)
            flipped = teams_match(ev.home, away, s) and teams_match(ev.away, home, s)
            if not (straight or flipped):
                continue
            out: Dict[str, Dict[str, float]] = {}
            for venue, sides in ev.prices.items():
                h = sides.get("away") if flipped else sides.get("home")
                a = sides.get("home") if flipped else sides.get("away")
                clean: Dict[str, float] = {}
                if h is not None:
                    clean[home] = float(h)
                if a is not None:
                    clean[away] = float(a)
                if clean:
                    out[venue] = clean
            return out or None
        return None

    return _lookup, events


def event_meta(events: Sequence[OddsEvent], sport: str, home: str, away: str
               ) -> Dict[str, Any]:
    """event_id + commence_time for the (home, away) game, or empty strings."""
    for ev in events:
        if ((teams_match(ev.home, home, sport) and teams_match(ev.away, away, sport))
                or (teams_match(ev.home, away, sport)
                    and teams_match(ev.away, home, sport))):
            return {"event_id": ev.event_id or "",
                    "commence_time": ev.commence_time or ""}
    return {"event_id": "", "commence_time": ""}


def side_of(selection: Any, home: str, away: str) -> Optional[str]:
    """Map a moneyline selection label to the ledger's 'home'/'away'; else None."""
    if selection == home:
        return "home"
    if selection == away:
        return "away"
    return None


def close_proxy_decimals(book_prices: Optional[Dict[str, Dict[str, float]]],
                         home: str, away: str) -> Optional[Tuple[float, float]]:
    """Two-way closing-line PROXY (home_dec, away_dec) from the current book -- the
    grader's target. Uses the worst (lowest-decimal) real quote per side; None if
    not two-way. Never fabricated."""
    if not book_prices:
        return None
    hs = [p[home] for p in book_prices.values() if home in p]
    aws = [p[away] for p in book_prices.values() if away in p]
    if not hs or not aws:
        return None
    return (min(hs), min(aws))


def ledger_keys(rows: Sequence[Dict[str, Any]]) -> set:
    """(sport, matchup, side, day) keys already in the CLV ledger (bets)."""
    return {(str(r.get("sport")), str(r.get("matchup")), str(r.get("side")),
             str(r.get("ts", ""))[:10]) for r in rows}


def prediction_keys(rows: Sequence[Dict[str, Any]]) -> set:
    """(sport, matchup, selection, day) keys already in the predictions store."""
    return {(str(r.get("sport")), str(r.get("matchup")), str(r.get("selection")),
             str(r.get("logged_at", ""))[:10]) for r in rows}


def log_prediction(rec: Dict[str, Any], *, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def load_predictions(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def iter_rows(board: Dict[str, Any]) -> List[Dict[str, Any]]:
    """All bet rows across the board's groups (deduped by group+selection)."""
    seen, rows = set(), []
    for grp in board.get("groups") or []:
        for r in grp.get("bets") or []:
            key = (r.get("group"), r.get("selection"))
            if key not in seen:
                seen.add(key)
                rows.append(r)
    return rows


def live_state(g: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map a live_board row to bet_board's live state dict, only when in-progress."""
    if g.get("state") != "in":
        return None
    return {"state": "in", "home_score": g.get("home_score"),
            "away_score": g.get("away_score"), "clock": g.get("clock"),
            "elapsed": None}


__all__ = [
    "Ctx", "DEFAULT_PREDICTIONS", "DEFAULT_SPORTS", "PAPER_EV_FLOOR",
    "now_iso", "today_key", "odds_index", "event_meta", "side_of",
    "close_proxy_decimals", "ledger_keys", "prediction_keys",
    "log_prediction", "load_predictions", "iter_rows", "live_state",
]
