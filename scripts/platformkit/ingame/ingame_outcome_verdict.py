"""scripts.platformkit.ingame.ingame_outcome_verdict -- per-segment OUTCOME-gated
calibration verdict for the live in-game model (MLB).

WHAT / WHY
----------
ingame_clv_per_segment measures model_prob - market_prob (does the live model lean vs
the CONTEMPORANEOUS venue price).  That is CLV, not truth: it cannot tell whether a
systematic per-segment lean is the model being WRONG (lag) or the model being RIGHT (the
thin venue quote lagging).  With outcome labels now resolvable offline
(ingame_outcome_label), we can settle it: for each segment compare the model's Brier vs
the realized outcome against the VENUE in-play price's Brier vs the same outcome.

  delta = Brier(model) - Brier(venue_price)   (per game, then pooled over games)
    delta < 0  -> the model is BETTER calibrated to the outcome than the venue price.
    delta > 0  -> WORSE.

HONEST FRAMING (binding)
------------------------
The venue in-play price here is the KALSHI in-play quote, which is thin / laggy -- NOT an
efficient sharp close.  A model that is better-calibrated-to-outcome than a stale venue
quote is a genuine, useful PLACEMENT signal for that venue, but it is NOT "beating the
market" / not a $ edge / not an efficient-close beat.  Probability/Brier space only; no
$/roi/pnl field; edge_claimed always False.  A WORSE or MATCH verdict is an honest,
useful result (tells us which segments to be cautious in), never a failure.

METHOD (leak-free)
------------------
* One grade file == one game (keyed by the Kalshi ticker).  Outcome resolved from the
  local realized-box parquet via MlbOutcomeResolver (None -> game skipped, never faked).
* Per game, per segment: mean squared error of model and of venue price vs the game's
  outcome (the game is the clustering unit -> a long game cannot dominate).
* Per segment: pooled mean over games + a game-clustered bootstrap 95% CI on the per-game
  (model - venue) Brier delta.  BETTER only when the CI upper bound is < 0.
* Below min_games or min_ticks -> INSUFFICIENT_DATA (never fabricated).

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network;
never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_outcome_verdict.py -q
"""
from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
from scripts.platformkit.ingame import live_grade as _lg

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_outcome_verdict.json"
COMPONENT = "m_ingame_outcome_verdict"

MIN_GAMES_PER_SEG = 8
MIN_TICKS_PER_SEG = 200
EPS_DEFAULT = 0.005
_BOOTSTRAP_ITERS = 2000
_SEGMENT_ORDER = ["I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "UNK"]

OutcomeFn = Callable[[str], Optional[int]]


def _brier_by_game_segment(
    files: Sequence[Path], outcome_fn: OutcomeFn, sport: str,
) -> Tuple[Dict[str, Dict[str, Tuple[float, float, int]]], int, int]:
    """seg -> {game_id: (sse_model, sse_market, n_ticks)}; plus (n_files, n_labeled).

    Only games with a resolvable outcome contribute. Never raises."""
    per: Dict[str, Dict[str, Tuple[float, float, int]]] = defaultdict(dict)
    n_files = n_labeled = 0
    for p in files:
        try:
            rows = _lg._load_pairs(Path(p))
        except Exception:  # noqa: BLE001
            rows = []
        if not rows:
            continue
        n_files += 1
        gid = str(rows[0].get("game_id") or Path(p).stem)
        try:
            y = outcome_fn(gid)
        except Exception:  # noqa: BLE001 -- a bad resolve is just an unlabeled game
            y = None
        if y is None:
            continue
        n_labeled += 1
        acc: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        for r in rows:
            mp, kp = r.get("model_prob"), r.get("market_prob")
            if mp is None or kp is None:
                continue
            seg = _seg._infer_segment(sport, str(r.get("state_summary", "")))
            a = acc[seg]
            a[0] += (float(mp) - y) ** 2
            a[1] += (float(kp) - y) ** 2
            a[2] += 1
        for seg, a in acc.items():
            if a[2] > 0:
                per[seg][gid] = (a[0], a[1], int(a[2]))
    return per, n_files, n_labeled


def _ci_delta(per_game_delta: List[float], *, seed: int = 42) -> Tuple[float, float]:
    """Game-clustered bootstrap 95% CI for the pooled per-game (model-market) Brier delta."""
    g = len(per_game_delta)
    if g == 0:
        return (0.0, 0.0)
    if g == 1:
        return (per_game_delta[0], per_game_delta[0])
    rng = random.Random(seed)
    means = sorted(
        sum(per_game_delta[rng.randrange(g)] for _ in range(g)) / g
        for _ in range(_BOOTSTRAP_ITERS)
    )
    lo = means[int(0.025 * (_BOOTSTRAP_ITERS - 1))]
    hi = means[int(0.975 * (_BOOTSTRAP_ITERS - 1))]
    return (lo, hi)


def _seg_verdict(game_map: Dict[str, Tuple[float, float, int]], *,
                 eps: float, min_games: int, min_ticks: int) -> Dict[str, Any]:
    """Per-segment verdict from {game: (sse_model, sse_market, n_ticks)}."""
    n_games = len(game_map)
    ticks = sum(v[2] for v in game_map.values())
    if n_games < min_games or ticks < min_ticks:
        return {"verdict": "INSUFFICIENT_DATA", "n_games": n_games,
                "total_ticks": ticks, "brier_model": None, "brier_market": None,
                "brier_delta": None, "delta_ci95": None,
                "units": "brier", "edge_claimed": False}
    # per-game mean Brier (game = clustering unit)
    bm = [v[0] / v[2] for v in game_map.values()]
    bk = [v[1] / v[2] for v in game_map.values()]
    delta_g = [m - k for m, k in zip(bm, bk)]
    mean_m = sum(bm) / n_games
    mean_k = sum(bk) / n_games
    delta = mean_m - mean_k
    lo, hi = _ci_delta(delta_g)
    if delta < -eps and hi < 0.0:
        verdict = "BETTER_THAN_VENUE"
    elif delta > eps and lo > 0.0:
        verdict = "WORSE_THAN_VENUE"
    else:
        verdict = "MATCH"
    return {"verdict": verdict, "n_games": n_games, "total_ticks": ticks,
            "brier_model": round(mean_m, 6), "brier_market": round(mean_k, 6),
            "brier_delta": round(delta, 6),
            "delta_ci95": [round(lo, 6), round(hi, 6)],
            "units": "brier", "edge_claimed": False}


def build_verdict(*, sport: str = "mlb", grade_dir: Optional[Path] = None,
                  paths: Optional[Sequence[Path]] = None,
                  outcome_fn: Optional[OutcomeFn] = None,
                  eps: float = EPS_DEFAULT,
                  min_games: int = MIN_GAMES_PER_SEG,
                  min_ticks: int = MIN_TICKS_PER_SEG) -> Dict[str, Any]:
    """Per-segment outcome-gated Brier verdict for *sport* (MLB). NEVER raises."""
    try:
        files = list(paths) if paths is not None else _seg._discover(grade_dir, sport)
        ofn = outcome_fn
        if ofn is None:
            from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
            res = MlbOutcomeResolver()
            ofn = res.home_win if res.available else (lambda _g: None)
        per, n_files, n_labeled = _brier_by_game_segment(files, ofn, sport)
        segments: Dict[str, Any] = {}
        order = list(_SEGMENT_ORDER) + sorted(s for s in per if s not in _SEGMENT_ORDER)
        for seg in order:
            if seg in per or seg in _SEGMENT_ORDER:
                segments[seg] = _seg_verdict(per.get(seg, {}), eps=eps,
                                             min_games=min_games, min_ticks=min_ticks)
        better = [s for s, v in segments.items() if v["verdict"] == "BETTER_THAN_VENUE"]
        worse = [s for s, v in segments.items() if v["verdict"] == "WORSE_THAN_VENUE"]
        return {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": COMPONENT, "sport": sport,
            "n_files": n_files, "n_labeled": n_labeled,
            "segments": segments, "segment_order": order,
            "better_segments": better, "worse_segments": worse,
            "units": "brier", "edge_claimed": False,
            "note": ("per-segment Brier of the live in-game model vs the OUTCOME, "
                     "compared to the VENUE in-play price (thin/laggy Kalshi quote). "
                     "BETTER_THAN_VENUE = better calibrated to truth than that venue "
                     "quote; this is NOT an efficient-close beat and NOT a $ edge."),
        }
    except Exception as exc:  # noqa: BLE001 -- diagnostic must never crash a daemon
        logger.warning("build_verdict(%s) failed: %s", sport, exc)
        return {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "component": COMPONENT, "sport": sport, "n_files": 0, "n_labeled": 0,
                "segments": {}, "error": type(exc).__name__, "edge_claimed": False}


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 74,
         "IN-GAME OUTCOME-GATED VERDICT (%s) -- Brier vs truth, model vs venue price"
         % doc.get("sport", "?"),
         "n_files=%d n_labeled=%d" % (doc.get("n_files", 0), doc.get("n_labeled", 0)),
         "%-5s %-18s %6s %7s %10s %10s %9s"
         % ("SEG", "VERDICT", "GAMES", "TICKS", "BRIER_mdl", "BRIER_mkt", "delta")]
    segs = doc.get("segments", {})
    for seg in doc.get("segment_order", sorted(segs)):
        v = segs.get(seg)
        if not v:
            continue
        bm = v.get("brier_model"); bk = v.get("brier_market"); d = v.get("brier_delta")
        L.append("%-5s %-18s %6d %7d %10s %10s %9s"
                 % (seg, v["verdict"], v.get("n_games", 0), v.get("total_ticks", 0),
                    "n/a" if bm is None else "%.4f" % bm,
                    "n/a" if bk is None else "%.4f" % bk,
                    "n/a" if d is None else "%+.4f" % d))
    L.append("-" * 74)
    L.append("BETTER-than-venue-price segments: %s" % (doc.get("better_segments") or "none"))
    L.append("NOTE: venue price = thin Kalshi in-play quote; NOT an efficient close, "
             "NOT a $ edge. Brier/probability space only.")
    L.append("=" * 74)
    return "\n".join(L)


def run(*, interval_sec: float = 900.0, sport: str = "mlb",
        path: Optional[Path] = None, sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Write the verdict every *interval_sec* (forever or *max_ticks*). Survives failures."""
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
            doc = build_verdict(sport=sport)
            write_doc(doc, path)
            print("%s | tick=%d labeled=%d better=%s" % (
                COMPONENT, ticks, doc.get("n_labeled", 0), doc.get("better_segments")),
                flush=True)
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
    ap = argparse.ArgumentParser(prog="ingame_outcome_verdict")
    ap.add_argument("--sport", default="mlb")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--interval", type=float, default=None,
                    help="loop forever at this cadence (default: single run)")
    a = ap.parse_args(argv)
    if a.interval is not None:
        print("%s | started interval=%ss sport=%s" % (COMPONENT, a.interval, a.sport),
              flush=True)
        run(interval_sec=a.interval, sport=a.sport)
        return 0
    doc = build_verdict(sport=a.sport)
    if not a.no_write:
        write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "COMPONENT", "MIN_GAMES_PER_SEG", "MIN_TICKS_PER_SEG",
    "build_verdict", "write_doc", "render", "run",
]
