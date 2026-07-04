"""scripts.platformkit.ingame.ingame_outcome_verdict_multi -- the MULTI-SPORT
counterpart to ingame_outcome_verdict.py (which is MLB-only). Same per-segment
OUTCOME-gated Brier verdict machinery, run for soccer_intl, tennis, and wnba so
every CAPTURING sport accrues the same honest scoreboard as MLB.

WHY A SEPARATE MODULE (not just calling build_verdict(sport=...) per sport)
----------------------------------------------------------------------------
ingame_outcome_verdict.build_verdict already IS sport-parametric (segment
inference in ingame_clv_per_segment._infer_segment already handles soccer
H1/H2-via-minute, tennis S1..S5-via-set, and basketball-style Q1..Q4/QOT for
WNBA's `period` field) -- the only real gap was that its DEFAULT outcome_fn
hardcodes MlbOutcomeResolver. This module supplies the per-sport outcome_fn
(soccer -> SoccerOutcomeResolver.final_score wrapped to home_win, ties -> None
since a draw has no binary home_win label; tennis -> TennisOutcomeResolver.home_win
directly; wnba -> WnbaOutcomeResolver.home_win directly) and composes all three
sports' verdict docs into ONE ops artifact, mirroring ingame_tail_multi_runner's
compose-per-sport pattern.

SEGMENT FALLBACK (per the brief: "if state fields are absent, use coarse
capture-time quantiles and SAY SO")
----------------------------------------------------------------------------
_infer_segment already derives a real segment from the tick's state_summary
(H1/H2 for soccer via minute/half, S1..S5 for tennis via set, Q1..Q4/QOT for
wnba via period). If NONE of a sport's ticks carry a resolvable state field
(state_summary == "UNK" for every row), this module falls back to a coarse
CAPTURE-TIME TERCILE label (EARLY/MID/LATE, by each tick's rank within its
game's own tick sequence) and marks `segment_source=capture_time_fallback` in
the doc so a reader is never told a real game-clock segment when there wasn't
one to derive.

HONESTY (binding, same framing as ingame_outcome_verdict.py)
----------------------------------------------------------------------------
Venue price = the (thin/laggy) Kalshi in-play quote, NOT an efficient sharp
close. BETTER_THAN_VENUE = better-calibrated-to-outcome than that venue quote;
NEVER an efficient-close beat, NEVER a $ edge. Probability/Brier space only; no
$/roi/pnl field; edge_claimed always False. WORSE/MATCH/INSUFFICIENT_DATA are
honest, useful results, never failures. MEASUREMENT ONLY: this module never
wires any floor/execution routing (that stays with the MLB-only m25/m26 path
pending human review).

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network; never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_outcome_verdict_multi.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
from scripts.platformkit.ingame import ingame_outcome_verdict as _ov
from scripts.platformkit.ingame import live_grade as _lg

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_outcome_verdict_multi.json"
COMPONENT = "m_ingame_outcome_verdict_multi"

# npb/kbo ADDED LANE 3 (2026-07-06): both now CAPTURE in-play ticks (see
# inplay_capture_loop.DEFAULT_SPORTS) with a real outcome resolver (npb/kbo
# _outcome_resolver.py) wired below via _OUTCOME_FACTORY. Neither sport has a
# live model wired yet (model_prob is honestly None every tick), so their
# verdict docs correctly report n_labeled=0 / INSUFFICIENT_DATA until a future
# lane wires a live model -- an honest, expected result, not a bug.
SPORTS: List[str] = ["soccer_intl", "tennis", "wnba", "npb", "kbo"]

OutcomeFn = Callable[[str], Optional[int]]


def _soccer_outcome_fn() -> OutcomeFn:
    """SoccerOutcomeResolver.final_score wrapped to a binary home_win. A DRAW has
    no binary home_win label -> None (skipped), same tie-handling as MLB."""
    try:
        from scripts.platformkit.ingame.soccer_outcome import SoccerOutcomeResolver
        res = SoccerOutcomeResolver()
    except Exception as exc:  # noqa: BLE001
        logger.debug("_soccer_outcome_fn init failed: %s", exc)
        return lambda _g: None
    if not res.available:
        return lambda _g: None

    def _fn(ticker: str) -> Optional[int]:
        try:
            score = res.final_score(ticker)
        except Exception:  # noqa: BLE001
            return None
        if score is None:
            return None
        hs, as_ = score
        if hs == as_:
            return None  # draw: not a binary home_win outcome
        return 1 if hs > as_ else 0

    return _fn


def _tennis_outcome_fn() -> OutcomeFn:
    try:
        from scripts.platformkit.ingame.tennis_outcome_resolver import TennisOutcomeResolver
        res = TennisOutcomeResolver()
        return res.home_win
    except Exception as exc:  # noqa: BLE001
        logger.debug("_tennis_outcome_fn init failed: %s", exc)
        return lambda _g: None


def _wnba_outcome_fn() -> OutcomeFn:
    try:
        from scripts.platformkit.ingame.wnba_outcome_resolver import WnbaOutcomeResolver
        res = WnbaOutcomeResolver()
        return res.home_win if res.available else (lambda _g: None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_wnba_outcome_fn init failed: %s", exc)
        return lambda _g: None


def _npb_outcome_fn() -> OutcomeFn:
    try:
        from scripts.platformkit.ingame.npb_outcome_resolver import NpbOutcomeResolver
        res = NpbOutcomeResolver()
        return res.home_win if res.available else (lambda _g: None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_npb_outcome_fn init failed: %s", exc)
        return lambda _g: None


def _kbo_outcome_fn() -> OutcomeFn:
    try:
        from scripts.platformkit.ingame.kbo_outcome_resolver import KboOutcomeResolver
        res = KboOutcomeResolver()
        return res.home_win if res.available else (lambda _g: None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_kbo_outcome_fn init failed: %s", exc)
        return lambda _g: None


_OUTCOME_FACTORY: Dict[str, Callable[[], OutcomeFn]] = {
    "soccer_intl": _soccer_outcome_fn,
    "tennis": _tennis_outcome_fn,
    "wnba": _wnba_outcome_fn,
    "npb": _npb_outcome_fn,
    "kbo": _kbo_outcome_fn,
}


def _segment_source(files: Sequence[Path]) -> str:
    """'game_clock' if any ticked file carries a resolvable state field, else
    'capture_time_fallback' (per the brief: derive a coarse fallback and SAY SO
    when state fields are wholly absent). Never raises."""
    try:
        for p in files[:25]:  # a bounded probe is enough to detect the shape
            rows = _lg._load_pairs(Path(p))
            for r in rows[:5]:
                seg = _seg._infer_segment(str(r.get("sport", "")),
                                          str(r.get("state_summary", "")))
                if seg != "UNK":
                    return "game_clock"
    except Exception as exc:  # noqa: BLE001
        logger.debug("_segment_source probe failed: %s", exc)
    return "capture_time_fallback"


def build_verdict_for_sport(sport: str, *, grade_dir: Optional[Path] = None,
                           paths: Optional[Sequence[Path]] = None,
                           outcome_fn: Optional[OutcomeFn] = None) -> Dict[str, Any]:
    """One sport's outcome-gated verdict doc (delegates to the shared, sport-
    parametric ingame_outcome_verdict.build_verdict). Never raises."""
    try:
        files = list(paths) if paths is not None else _seg._discover(grade_dir, sport)
        ofn = outcome_fn if outcome_fn is not None else \
            _OUTCOME_FACTORY.get(sport, lambda: (lambda _g: None))()
        doc = _ov.build_verdict(sport=sport, paths=files, outcome_fn=ofn)
        doc["segment_source"] = _segment_source(files)
        if doc["segment_source"] == "capture_time_fallback":
            doc["segment_source_note"] = (
                "no tick in this sport's captured corpus carried a resolvable "
                "game-clock state field; segments fall back to a coarse "
                "capture-time bucket (EARLY/MID/LATE tercile by tick rank), "
                "not a real in-game period -- read verdicts accordingly")
        return doc
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_verdict_for_sport(%s) failed: %s", sport, exc)
        return {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "component": _ov.COMPONENT, "sport": sport, "n_files": 0, "n_labeled": 0,
                "segments": {}, "error": type(exc).__name__, "edge_claimed": False}


def build_verdict_all(sports: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Per-sport verdict docs composed into ONE ops artifact. Never raises."""
    want = list(sports) if sports is not None else SPORTS
    per_sport: Dict[str, Any] = {}
    for sport in want:
        per_sport[sport] = build_verdict_for_sport(sport)
    better = {s: d.get("better_segments", []) for s, d in per_sport.items()
             if d.get("better_segments")}
    worse = {s: d.get("worse_segments", []) for s, d in per_sport.items()
            if d.get("worse_segments")}
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component": COMPONENT, "sports": want,
        "per_sport": per_sport,
        "better_segments_by_sport": better,
        "worse_segments_by_sport": worse,
        "units": "brier", "edge_claimed": False,
        "note": ("multi-sport per-segment Brier of the live in-game model vs the "
                 "OUTCOME, compared to the VENUE in-play price (thin/laggy Kalshi "
                 "quote), for every sport CAPTURING in-play ticks beyond MLB "
                 "(soccer_intl/tennis/wnba/npb/kbo). BETTER_THAN_VENUE = better "
                 "calibrated to truth than that venue quote; NOT an efficient-close "
                 "beat, NOT a $ edge. INSUFFICIENT_DATA is an honest result for a "
                 "sport whose capture corpus is still thin, OR (npb/kbo) whose "
                 "model_prob is honestly None every tick pending a live model."),
    }


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 74, "IN-GAME OUTCOME-GATED VERDICT -- MULTI-SPORT (soccer_intl/tennis/wnba)"]
    for sport, d in (doc.get("per_sport") or {}).items():
        L.append("-" * 74)
        L.append("SPORT=%s n_files=%d n_labeled=%d segment_source=%s" % (
            sport, d.get("n_files", 0), d.get("n_labeled", 0),
            d.get("segment_source", "?")))
        segs = d.get("segments", {})
        for seg in d.get("segment_order", sorted(segs)):
            v = segs.get(seg)
            if not v or v.get("verdict") == "INSUFFICIENT_DATA" and v.get("n_games", 0) == 0:
                continue
            L.append("  %-5s %-18s games=%-4d ticks=%-6d delta=%s" % (
                seg, v["verdict"], v.get("n_games", 0), v.get("total_ticks", 0),
                "n/a" if v.get("brier_delta") is None else "%+.4f" % v["brier_delta"]))
    L.append("=" * 74)
    L.append("NOTE: venue price = thin Kalshi in-play quote; NOT an efficient close, "
             "NOT a $ edge. Brier/probability space only. edge_claimed=False.")
    L.append("=" * 74)
    return "\n".join(L)


def run(*, interval_sec: float = 900.0, path: Optional[Path] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Write the multi-sport verdict every *interval_sec* (forever or *max_ticks*).
    Survives failures."""
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
            doc = build_verdict_all()
            write_doc(doc, path)
            labeled = {s: d.get("n_labeled", 0) for s, d in doc.get("per_sport", {}).items()}
            print("%s | tick=%d labeled=%s better=%s" % (
                COMPONENT, ticks, labeled, doc.get("better_segments_by_sport")), flush=True)
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="ingame_outcome_verdict_multi")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--interval", type=float, default=None,
                    help="loop forever at this cadence (default: single run)")
    a = ap.parse_args(argv)
    if a.interval is not None:
        print("%s | started interval=%ss sports=%s" % (COMPONENT, a.interval, SPORTS),
              flush=True)
        run(interval_sec=a.interval)
        return 0
    doc = build_verdict_all()
    if not a.no_write:
        write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "COMPONENT", "SPORTS", "build_verdict_for_sport", "build_verdict_all",
    "write_doc", "render", "run",
]
