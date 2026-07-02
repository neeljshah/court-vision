"""scripts.platformkit.improve.ingame_clv_grade -- turn CAPTURED in-play graded
series into an honest in-game CLV verdict (closes the in-play feedback loop).

Each data/cache/ingame_grade/<sport>/<game>.jsonl row carries a point-in-time
model_prob AND the live market_prob. This module replays those series, leak-free,
through forward_capture.inplay_clv_replay.replay_series and asks: did the engine's
live repriced number anticipate where the in-play market CLOSED?

This is the wiring that was missing: in-play ticks were captured + graded, but the
graded pairs were never turned into a CLV verdict (ingame_segment_emit hard-coded
INSUFFICIENT_DATA / "NBA offseason"). MLB is in-season; the data exists.

HONEST RAILS:
  - Reuses the single CLV math source (replay_series); no parallel re-implementation.
  - Leak-free by construction: each model_prob was logged at its tick's time by M11;
    the close is derived AFTER scoring from the last market tick (never handed in).
  - INSUFFICIENT_DATA when aggregate scored ticks < MIN_TICKS; never a fabricated BEAT.
  - CLV is PROBABILITY space (anticipation of the venue in-play close). NOT a $ edge,
    NOT a claim of beating a sharp pregame market. No $/roi/pnl/stake key anywhere.
  - Never raises out of the public API; ASCII only; <=300 LOC.

Public API:
  load_grade_series(path) -> Dict[side, List[tick]]
  grade_game(path, ...)   -> List[dict]   # one verdict per side-market in the file
  grade_sport(sport, ...) -> dict         # aggregate per-sport in-play CLV verdict
  format_sport_report(summary) -> str
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional

from scripts.platformkit.forward_capture.inplay_clv_replay import (
    replay_series, _verdict, EPS_DEFAULT, MIN_TICKS_DEFAULT,
)

logger = logging.getLogger("ingame_clv_grade")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_GRADE_DIR = _REPO / "data" / "cache" / "ingame_grade"

_BANNED = ("$", "roi", "pnl", "profit", "stake", "bankroll")

HONEST_NOTE = (
    "in-play CLV vs the captured venue in-play close (probability space; "
    "+ = the engine's live number anticipated where the market closed). "
    "Calibration / anticipation only -- NOT a dollar edge and NOT a claim of "
    "beating a sharp pregame market. UNITS not $."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _f(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _assert_clean(d: Dict[str, Any]) -> None:
    """Defense in depth: refuse any dollar/ROI key on an emitted summary."""
    for k in d:
        kl = str(k).lower()
        for bad in _BANNED:
            if bad in kl:
                raise ValueError("banned key %r violates no-dollar-field contract" % k)


def _logged_model_fn(tick: dict, history: List[dict]) -> float:
    """Leak-free repriced number: the model_prob logged AT this tick's time.

    history is series[:i+1] (handed in by replay_series) but is unused -- the engine's
    point-in-time number was already computed causally by M11 and stored on the tick.
    """
    return float(tick.get("_model_prob", tick.get("prob", 0.5)))


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_grade_series(path: Any) -> Dict[str, List[dict]]:
    """Read one ingame_grade JSONL -> {side: [canonical ticks sorted by ts]}.

    Each tick carries prob=market_prob (the live price) and _model_prob (the engine's
    point-in-time repriced number). Rows missing either prob, ts, or with an
    out-of-[0,1] prob are skipped (never fabricated). Never raises.
    """
    out: Dict[str, List[dict]] = {}
    p = pathlib.Path(path)
    if not p.exists():
        return out
    try:
        with p.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                mp = _f(rec.get("market_prob"))
                pm = _f(rec.get("model_prob"))
                ts = rec.get("ts")
                if mp is None or pm is None or ts is None:
                    continue
                if not (0.0 <= mp <= 1.0 and 0.0 <= pm <= 1.0):
                    continue
                side = str(rec.get("side", "?"))
                out.setdefault(side, []).append({
                    "prob": mp,
                    "_model_prob": pm,
                    "ts": str(ts),
                    "game_id": str(rec.get("game_id", p.stem)),
                    "market_type": str(rec.get("market_type", "moneyline")),
                    "venue": str(rec.get("venue", "kalshi")),
                    "side": side,
                    "_state": str(rec.get("state_summary", "")),
                })
    except Exception as exc:  # noqa: BLE001
        logger.debug("load_grade_series(%s): %s", path, exc)
        return {}
    for s in out:
        out[s].sort(key=lambda t: t["ts"])
    return out


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
def grade_game(path: Any, eps: float = EPS_DEFAULT,
               min_ticks: int = MIN_TICKS_DEFAULT) -> List[Dict[str, Any]]:
    """Grade every side-market series in one game grade file. Never raises.

    Returns a list of verdict dicts (one per side traded in the file). Each is the
    as_dict() of a ReplayResult plus the side label.
    """
    series_by_side = load_grade_series(path)
    results: List[Dict[str, Any]] = []
    for side, series in series_by_side.items():
        try:
            r = replay_series(series, _logged_model_fn, eps=eps, min_ticks=min_ticks)
        except Exception as exc:  # noqa: BLE001
            logger.debug("grade_game(%s/%s): %s", path, side, exc)
            continue
        d = r.as_dict()
        d["side"] = side
        results.append(d)
    return results


def grade_sport(sport: str, grade_dir: Any = None, eps: float = EPS_DEFAULT,
                min_ticks: int = MIN_TICKS_DEFAULT) -> Dict[str, Any]:
    """Aggregate in-play CLV across all captured games for one sport. Honest verdict.

    The aggregate mean_clv / hit_rate are tick-weighted across every scored market.
    Verdict uses the same gated thresholds as replay_series: below min_ticks scored
    in aggregate -> INSUFFICIENT_DATA (an honest "can't tell yet", never a BEAT).
    """
    base = pathlib.Path(grade_dir) if grade_dir is not None else _GRADE_DIR
    sdir = base / str(sport)
    per_game: List[Dict[str, Any]] = []
    if sdir.exists():
        for fp in sorted(sdir.glob("*.jsonl")):
            per_game.extend(grade_game(fp, eps=eps, min_ticks=min_ticks))

    scored = [g for g in per_game if int(g.get("n_ticks_scored", 0)) > 0]
    total_ticks = sum(int(g.get("n_ticks_scored", 0)) for g in scored)
    if total_ticks > 0:
        mean_clv = sum(float(g["mean_clv"]) * int(g["n_ticks_scored"])
                       for g in scored) / total_ticks
        hit_rate = sum(float(g["hit_rate"]) * int(g["n_ticks_scored"])
                       for g in scored) / total_ticks
    else:
        mean_clv = 0.0
        hit_rate = 0.0

    tick_verdict = _verdict(mean_clv, hit_rate, total_ticks, eps, min_ticks)
    beat = sum(1 for g in scored if g.get("verdict") == "BEAT")
    behind = sum(1 for g in scored if g.get("verdict") == "BEHIND")

    # Artifact guard: tick-weighting lets a few high-volume markets manufacture a
    # BEAT (or BEHIND) the market-MAJORITY contradicts. Refuse the directional call
    # unless the per-market tally agrees -- an honest MATCH beats a fragile BEAT.
    verdict = tick_verdict
    downgraded = False
    if tick_verdict == "BEAT" and beat <= behind:
        verdict, downgraded = "MATCH", True
    elif tick_verdict == "BEHIND" and behind <= beat:
        verdict, downgraded = "MATCH", True

    summary = {
        "sport": str(sport),
        "verdict": verdict,
        "tick_verdict": tick_verdict,
        "majority_downgraded": bool(downgraded),
        "mean_clv": round(float(mean_clv), 6),
        "hit_rate": round(float(hit_rate), 6),
        "n_markets": len(per_game),
        "n_markets_scored": len(scored),
        "n_markets_beat": int(beat),
        "n_markets_behind": int(behind),
        "n_ticks_scored": int(total_ticks),
        "min_ticks": int(min_ticks),
        "eps": float(eps),
        "vs_close": "in_play_venue_close",
        "edge_claimed": False,
        "note": HONEST_NOTE,
    }
    _assert_clean(summary)
    return summary


def resolve_clv_status(sport: str, summary: Optional[Dict[str, Any]] = None,
                       eps: float = EPS_DEFAULT,
                       min_ticks: int = MIN_TICKS_DEFAULT) -> tuple:
    """(clv_status, clv_reason) for a sport from its captured in-play series.

    Data-driven BEAT/BEHIND/MATCH when data exists, else the honest INSUFFICIENT_DATA.
    NEVER raises. `summary` injects a precomputed grade_sport() result for hermetic tests.
    """
    try:
        if summary is None:
            summary = grade_sport(str(sport), eps=eps, min_ticks=min_ticks)
        v = str(summary.get("verdict", "INSUFFICIENT_DATA"))
        if v == "INSUFFICIENT_DATA":
            return "INSUFFICIENT_DATA", (
                "in-game CLV INSUFFICIENT_DATA: only %d graded in-play ticks for %s "
                "(need >= %d); honest can't-tell, not a beat" % (
                    int(summary.get("n_ticks_scored", 0)), sport,
                    int(summary.get("min_ticks", min_ticks))))
        return v, (
            "in-game CLV %s vs captured in-play close: mean_clv=%+.4f hit_rate=%.3f over "
            "%d ticks / %d markets (BEAT=%d BEHIND=%d)%s -- calibration, not a $ edge" % (
                v, float(summary.get("mean_clv", 0.0)), float(summary.get("hit_rate", 0.0)),
                int(summary.get("n_ticks_scored", 0)), int(summary.get("n_markets_scored", 0)),
                int(summary.get("n_markets_beat", 0)), int(summary.get("n_markets_behind", 0)),
                " [majority-downgraded]" if summary.get("majority_downgraded") else ""))
    except Exception as exc:  # noqa: BLE001
        logger.debug("resolve_clv_status(%s): %s", sport, exc)
        return "INSUFFICIENT_DATA", "in-game CLV INSUFFICIENT_DATA: grading unavailable"


# ---------------------------------------------------------------------------
# Reporting / CLI
# ---------------------------------------------------------------------------
def format_sport_report(summary: Dict[str, Any]) -> str:
    """ASCII summary of one per-sport in-play CLV verdict. No $ figure."""
    s = summary
    return "\n".join([
        "=== In-play CLV (captured -> graded, honest) ===",
        "sport            : %s" % s.get("sport"),
        "verdict          : %s" % s.get("verdict"),
        "mean_clv         : %+.4f  (probability space; + = anticipated the close)"
        % float(s.get("mean_clv", 0.0)),
        "hit_rate         : %.3f  (lean-toward-close fraction)"
        % float(s.get("hit_rate", 0.0)),
        "markets scored   : %d / %d  (BEAT=%d BEHIND=%d)" % (
            s.get("n_markets_scored", 0), s.get("n_markets", 0),
            s.get("n_markets_beat", 0), s.get("n_markets_behind", 0)),
        "tick_verdict     : %s%s" % (
            s.get("tick_verdict", s.get("verdict")),
            "  (downgraded: market-majority disagrees)"
            if s.get("majority_downgraded") else ""),
        "ticks scored     : %d  (min %d for a verdict)" % (
            s.get("n_ticks_scored", 0), s.get("min_ticks", 0)),
        "units            : probability (CLV / calibration only -- never dollars)",
    ])


def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Grade captured in-play series into an honest in-game CLV verdict. "
                    "Probability space; no $ edge; INSUFFICIENT_DATA when thin.")
    p.add_argument("sport", help="sport key (e.g. mlb, nba, soccer_intl)")
    p.add_argument("--eps", type=float, default=EPS_DEFAULT)
    p.add_argument("--min-ticks", type=int, default=MIN_TICKS_DEFAULT)
    a = p.parse_args()
    summary = grade_sport(a.sport, eps=a.eps, min_ticks=a.min_ticks)
    print(format_sport_report(summary), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "load_grade_series", "grade_game", "grade_sport", "resolve_clv_status",
    "format_sport_report", "HONEST_NOTE",
]
