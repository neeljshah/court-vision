"""scripts.platformkit.ingame.ingame_paper_settle -- the MISSING settle arm for the
in-game paper channel (channel="paper_ingame").

THE GAP THIS CLOSES
-------------------
inplay_daytrader places in-game paper bets via paper_ingame.record_ingame_bet, and
paper_ingame.grade_live can settle one against a final score -- but NOTHING ever called
grade_live for this channel.  So every in-game paper bet sat status="open" forever: 82
placed, 0 ever settled -> the channel produced no outcome, no CLV, no bankroll impact and
no learning, even though placement (the two-sided fix) is now working.  The pregame paper
channels each have a settler; the in-game channel never got one.  Root cause is the same
id gap fixed elsewhere: in-game rows are keyed by the KALSHI TICKER, not an ESPN id, so an
ESPN-id settler could never match them.

This module drives the settle: it loads OPEN paper_ingame rows, resolves each bet's final
score DIRECTLY from the ticker -- MLB via ingame_outcome_label.MlbOutcomeResolver (local
realized-box parquet), World Cup soccer via soccer_outcome.SoccerOutcomeResolver (local
ESPN-sourced finals parquet) -- dispatching on the ticker's series prefix, and calls
paper_ingame.grade_live so the row settles with a real outcome + unit_result (+ proxy CLV
where available).  Idempotent: a bet whose edge_key already has a settled twin is skipped;
a bet whose game is not yet final, or whose ticker neither resolver recognises, stays OPEN
(never a fabricated settle).

HONESTY: UNITS / probability only; no $/roi/pnl field; executed stays False (real money is a
separate default-DENY gate); edge_claimed False; flips no flag.  A game not yet final -> the
bet stays open (honest), never force-settled.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network
(reads a local parquet); never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_paper_settle.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame import paper_ingame as _pi

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
STATUS_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_paper_settle_status.json"
COMPONENT = "m_ingame_paper_settle"

# game_id -> (home_score, away_score) | None. MLB via the ticker->boxscore resolver.
ScoreFn = Callable[[str], Optional[Tuple[int, int]]]


def _mlb_score_fn() -> Optional[ScoreFn]:
    try:
        from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
        res = MlbOutcomeResolver()
        if res.available:
            return res.final_score
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_paper_settle MLB resolver unavailable: %s", exc)
    return None


def _refresh_soccer_finals() -> None:
    """Pull the last 3 UTC days of ESPN WC final scores before resolving, so a
    newly-completed match settles on THIS tick rather than waiting on someone to
    re-run the ingest by hand. Small + cheap (<=3 scoreboard fetches); NEVER
    raises -- a network hiccup just means today's ticks fall back to whatever
    was already on disk (bets stay open, never fabricated)."""
    try:
        from datetime import timedelta
        from scripts.platformkit.ingame.soccer_outcome import DEFAULT_FINALS_PARQUET
        from domains.soccer_intl import ingest_espn_finals as ief
        today = datetime.now(timezone.utc).date()
        dates = [(today - timedelta(days=d)).strftime("%Y%m%d") for d in range(3)]
        ief.ingest_range(dates, out_path=DEFAULT_FINALS_PARQUET)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_paper_settle soccer finals refresh failed: %s", exc)


def _soccer_score_fn() -> Optional[ScoreFn]:
    _refresh_soccer_finals()
    try:
        from scripts.platformkit.ingame.soccer_outcome import SoccerOutcomeResolver
        res = SoccerOutcomeResolver()
        if res.available:
            return res.final_score
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_paper_settle soccer resolver unavailable: %s", exc)
    return None


def _dispatch_score_fn(mlb_fn: Optional[ScoreFn],
                       soccer_fn: Optional[ScoreFn]) -> ScoreFn:
    """Route a ticker to the resolver matching its Kalshi series prefix. A
    ticker neither resolver recognises (or an inert resolver) -> None, never a
    guess -- the bet just stays open."""
    def _fn(ticker: str) -> Optional[Tuple[int, int]]:
        t = str(ticker or "")
        if t.startswith("KXMLBGAME") and mlb_fn is not None:
            return mlb_fn(ticker)
        if t.startswith("KXWCGAME") and soccer_fn is not None:
            return soccer_fn(ticker)
        return None
    return _fn


def _default_score_fn() -> ScoreFn:
    """Build the combined ticker->final-score resolver (MLB + WC soccer, both
    offline parquet reads). A sport whose resolver is unavailable simply never
    matches -- its bets stay open, never fabricated."""
    return _dispatch_score_fn(_mlb_score_fn(), _soccer_score_fn())


def _settled_edge_keys(rows: List[Dict[str, Any]]) -> set:
    """edge_keys that already have a settled/graded twin -> idempotency guard."""
    keys = set()
    for r in rows:
        if str(r.get("status")) == "settled" or r.get("graded"):
            k = r.get("edge_key") or r.get("settle_key")
            if k:
                keys.add(k)
    return keys


def settle_open(*, score_fn: Optional[ScoreFn] = None,
                ledger_path: Optional[Path] = None,
                grade_fn: Optional[Callable[..., Dict[str, Any]]] = None,
                ) -> Dict[str, Any]:
    """Settle every resolvable OPEN paper_ingame bet against its final score. NEVER raises.

    Returns a status dict (counts + per-sport breakdown). Idempotent: already-settled
    edge_keys are skipped; unresolved (game not final / non-MLB) bets stay open."""
    sfn = score_fn or _default_score_fn()
    gfn = grade_fn or _pi.grade_live
    settled = skipped_open = errors = 0
    by_sport: Dict[str, Dict[str, int]] = {}
    try:
        rows = _pi.load_ingame_bets(path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_paper_settle load failed: %s", exc)
        rows = []
    done = _settled_edge_keys(rows)
    for b in rows:
        if str(b.get("status")) != "open":
            continue
        ek = b.get("edge_key")
        if ek in done:
            continue
        sport = str(b.get("sport") or "?")
        bucket = by_sport.setdefault(sport, {"settled": 0, "open": 0})
        score = None
        try:
            score = sfn(str(b.get("game_id")))
        except Exception as exc:  # noqa: BLE001 -- a bad resolve leaves the bet open
            logger.debug("score_fn failed for %s: %s", b.get("game_id"), exc)
        if not score:
            skipped_open += 1
            bucket["open"] += 1
            continue
        try:
            res = gfn(b, int(score[0]), int(score[1]), path=ledger_path)
            if str(res.get("status")) == "settled":
                settled += 1
                bucket["settled"] += 1
                if ek:
                    done.add(ek)  # guard against a duplicate open twin in the same pass
            else:
                errors += 1
        except Exception as exc:  # noqa: BLE001 -- one bad settle never stops the rest
            logger.warning("grade_live failed for %s: %s", b.get("game_id"), exc)
            errors += 1
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component": COMPONENT, "settled": settled, "still_open": skipped_open,
        "errors": errors, "by_sport": by_sport, "executed": False,
        "edge_claimed": False, "units": "probability",
        "note": ("settles OPEN paper_ingame bets against the realized final score "
                 "(MLB via ticker->boxscore); units/probability only, no $; a game not "
                 "yet final stays open. This is the missing in-game settle arm."),
    }


def write_status(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else STATUS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)


def run(*, interval_sec: float = 900.0, path: Optional[Path] = None,
        ledger_path: Optional[Path] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Settle open in-game paper bets every *interval_sec* (forever or *max_ticks*)."""
    import time as _time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            doc = settle_open(ledger_path=ledger_path)
            write_status(doc, path)
            print("%s | tick=%d settled=%d still_open=%d errors=%d" % (
                COMPONENT, ticks, doc.get("settled", 0), doc.get("still_open", 0),
                doc.get("errors", 0)), flush=True)
        except Exception as exc:  # noqa: BLE001
            print("%s | tick=%d ERROR %s" % (COMPONENT, ticks, str(exc)[:150]), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="ingame_paper_settle")
    ap.add_argument("--interval", type=float, default=None,
                    help="loop forever at this cadence (default: single pass)")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if a.interval is not None:
        print("%s | started interval=%ss" % (COMPONENT, a.interval), flush=True)
        run(interval_sec=a.interval)
        return 0
    doc = settle_open()
    if not a.no_write:
        write_status(doc)
    print("%s: settled=%d still_open=%d errors=%d by_sport=%s" % (
        COMPONENT, doc.get("settled", 0), doc.get("still_open", 0),
        doc.get("errors", 0), doc.get("by_sport")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["STATUS_PATH", "COMPONENT", "settle_open", "write_status", "run"]
