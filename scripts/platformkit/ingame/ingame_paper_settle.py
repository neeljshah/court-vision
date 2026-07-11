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
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.clv import kx_close_math as _kxm
from scripts.platformkit.ingame import paper_ingame as _pi

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
STATUS_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_paper_settle_status.json"
COMPONENT = "m_ingame_paper_settle"
# Ticks with open bets but ZERO settles before status flips to STUCK
# (24 ticks * 900s = ~6h). Override via env INGAME_SETTLE_STUCK_TICKS.
STUCK_AFTER_TICKS = int(os.environ.get("INGAME_SETTLE_STUCK_TICKS", "24"))

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


def _wnba_score_fn() -> Optional[ScoreFn]:
    """WnbaOutcomeResolver.final_score already matches the ScoreFn contract
    (ticker -> (home_score, away_score) | None) -- no wrapper needed. None
    (bets stay open) if the resolver has no usable local scoreboard parquet."""
    try:
        from scripts.platformkit.ingame.wnba_outcome_resolver import WnbaOutcomeResolver
        res = WnbaOutcomeResolver()
        if res.available:
            return res.final_score
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_paper_settle WNBA resolver unavailable: %s", exc)
    return None


def _npb_score_fn() -> Optional[ScoreFn]:
    """NpbOutcomeResolver.final_score already matches the ScoreFn contract
    (ticker -> (home_score, away_score) | None) -- no wrapper needed. None
    (bets stay open) if the resolver has no usable local results parquet."""
    try:
        from scripts.platformkit.ingame.npb_outcome_resolver import NpbOutcomeResolver
        res = NpbOutcomeResolver()
        if res.available:
            return res.final_score
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_paper_settle NPB resolver unavailable: %s", exc)
    return None


def _kbo_score_fn() -> Optional[ScoreFn]:
    """KboOutcomeResolver.final_score already matches the ScoreFn contract."""
    try:
        from scripts.platformkit.ingame.kbo_outcome_resolver import KboOutcomeResolver
        res = KboOutcomeResolver()
        if res.available:
            return res.final_score
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_paper_settle KBO resolver unavailable: %s", exc)
    return None


def _tennis_score_fn() -> Optional[ScoreFn]:
    """Wrap TennisOutcomeResolver.home_win -> a synthetic (1,0)/(0,1) score pair
    so it satisfies the ScoreFn/grade_live contract (grade_one only ever compares
    home_score>away_score, never reads a real tennis game score -- see
    tennis_outcome_resolver's module docstring). None (bet stays open) when the
    resolver can't resolve a winner (ambiguous/live/unparseable)."""
    try:
        from scripts.platformkit.ingame.tennis_outcome_resolver import TennisOutcomeResolver
        res = TennisOutcomeResolver()
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_paper_settle tennis resolver unavailable: %s", exc)
        return None

    def _fn(ticker: str) -> Optional[Tuple[int, int]]:
        hw = res.home_win(ticker)
        if hw is None:
            return None
        return (1, 0) if hw == 1 else (0, 1)
    return _fn


def _dispatch_score_fn(mlb_fn: Optional[ScoreFn],
                       soccer_fn: Optional[ScoreFn],
                       tennis_fn: Optional[ScoreFn] = None,
                       wnba_fn: Optional[ScoreFn] = None,
                       npb_fn: Optional[ScoreFn] = None,
                       kbo_fn: Optional[ScoreFn] = None) -> ScoreFn:
    """Route a ticker to the resolver matching its Kalshi series prefix. A
    ticker neither resolver recognises (or an inert resolver) -> None, never a
    guess -- the bet just stays open."""
    def _fn(ticker: str) -> Optional[Tuple[int, int]]:
        t = str(ticker or "")
        if t.startswith("KXMLBGAME") and mlb_fn is not None:
            return mlb_fn(ticker)
        if t.startswith("KXWCGAME") and soccer_fn is not None:
            return soccer_fn(ticker)
        if (t.startswith("KXATPMATCH") or t.startswith("KXWTAMATCH")) and tennis_fn is not None:
            return tennis_fn(ticker)
        if t.startswith("KXWNBAGAME") and wnba_fn is not None:
            return wnba_fn(ticker)
        if t.startswith("KXNPBGAME") and npb_fn is not None:
            return npb_fn(ticker)
        if t.startswith("KXKBOGAME") and kbo_fn is not None:
            return kbo_fn(ticker)
        return None
    return _fn


def _default_score_fn() -> ScoreFn:
    """Build the combined ticker->final-score resolver (MLB + WC soccer + WNBA +
    NPB + KBO, all offline parquet reads; tennis disk-first/live-ESPN-fallback).
    A sport whose resolver is unavailable simply never matches -- its bets stay
    open, never fabricated. NOTE: npb/kbo currently place NO bets (no live
    model wired -- see inplay_capture_loop.DEFAULT_SPORTS), so this settle arm
    for them is a no-op today (nothing to settle) and becomes active the
    moment a future lane wires a live model for either sport."""
    return _dispatch_score_fn(_mlb_score_fn(), _soccer_score_fn(), _tennis_score_fn(),
                              _wnba_score_fn(), _npb_score_fn(), _kbo_score_fn())


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
                # W1 fix: append an honestly-labelled kx-proxy CLV correction when
                # our own tick capture derived a close for this ticker -- see
                # kx_close_math module docstring for why this can't go through
                # grade_live's own closing_decimal_* kwargs (Shin-devig landmine).
                try:
                    if res.get("clv_status") == "no_close":
                        corr = _kxm.proxy_clv_for_row(res)
                        if corr is not None:
                            _clv.append_settlement(corr, path=ledger_path)
                except Exception as exc:  # noqa: BLE001 -- must never sink the tick
                    logger.debug("kx proxy correction failed for %s: %s",
                                b.get("game_id"), exc)
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


def write_status(doc: Dict[str, Any], path: Optional[Path] = None,
                 stuck_after: Optional[int] = None) -> None:
    """Write the status doc, folding in the STUCK detector: a tick that ends
    with open bets but zero settles bumps consecutive_zero_ticks (persisted in
    the status file itself); >= stuck_after consecutive such ticks flips
    status to STUCK so ops_sentinel/feed_health can alert -- the 2026-07-07
    incident (63+ silent zero-settle ticks) becomes visible, not silent."""
    p = Path(path) if path is not None else STATUS_PATH
    n = int(stuck_after) if stuck_after is not None else STUCK_AFTER_TICKS
    prev = 0
    try:
        prev = int(json.loads(p.read_text(encoding="ascii"))
                   .get("consecutive_zero_ticks", 0))
    except Exception:  # noqa: BLE001 -- first write / unreadable -> counter restarts
        prev = 0
    zero = int(doc.get("settled", 0)) == 0 and int(doc.get("still_open", 0)) > 0
    doc["consecutive_zero_ticks"] = prev + 1 if zero else 0
    doc["status"] = "STUCK" if doc["consecutive_zero_ticks"] >= n else "OK"
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
