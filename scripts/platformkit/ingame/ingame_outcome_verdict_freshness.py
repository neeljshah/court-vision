"""scripts.platformkit.ingame.ingame_outcome_verdict_freshness -- QUOTE-FRESHNESS
CONTROL on the outcome-gated verdict (queue item 2, LANE 2).

WHY
----------------------------------------------------------------------------
wave-6 found only 10-40% of soccer in-play ticks carry a genuinely NEW venue quote
(stale runs up to 62 consecutive ticks; a live re-measurement over the real MLB/soccer
corpora on this box shows the same shape, e.g. one MLB game's stale run reaching 337
ticks). Every existing model-vs-venue Brier verdict (ingame_outcome_verdict.py for MLB,
ingame_outcome_verdict_multi.py for soccer_intl/tennis/wnba/npb/kbo) scores against
these possibly-stale venue quotes, which can inflate the model-vs-venue gap in EITHER
direction. This module is an ADDITIVE control: for the SAME segments, it emits BOTH the
existing raw verdict (all ticks) and a fresh_only verdict (ticks where
quote_freshness.freshness_mask says the venue quote actually moved), same
game-clustered bootstrap methodology, so a reader can see directly whether a verdict
survives once stale repeats are excluded.

WHY A SEPARATE MODULE (per the brief: "do NOT edit ingame_outcome_verdict.py")
----------------------------------------------------------------------------
ingame_outcome_verdict.py is the MLB-only production verdict path; the brief
explicitly keeps it out of scope for this control. This module REUSES its pure,
side-effect-free helpers (_seg_verdict, _ci_delta -- no I/O, no MLB-specific logic) by
import, and supplies its OWN row-accumulator (parametrized by an optional row filter)
so the same Brier/CI verdict math runs once over ALL ticks and once over the
freshness-filtered subset, without touching the production module's file.

MLB CONTROL (per the brief: "re-read MLB ... via the multi machinery")
----------------------------------------------------------------------------
MLB is added to a LOCAL sport list for this control's outcome-factory only (mirrors
ingame_outcome_verdict.build_verdict's own MlbOutcomeResolver wiring) -- the production
SPORTS list in ingame_outcome_verdict_multi.py is left untouched.

HONESTY (binding, same framing as ingame_outcome_verdict.py)
----------------------------------------------------------------------------
Venue price = the (thin/laggy) Kalshi in-play quote, NOT an efficient sharp close.
BETTER_THAN_VENUE = better-calibrated-to-outcome than that venue quote; NEVER an
efficient-close beat, NEVER a $ edge. Probability/Brier space only; no $/roi/pnl field;
edge_claimed always False. If n_fresh_ticks is too thin to clear the same min-ticks/
min-games gate, fresh_only reports INSUFFICIENT_DATA honestly -- never a fabricated
verdict on a starved fresh-only sample.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network;
never writes data/registry/; never raises out; MEASUREMENT ONLY (no execution/threshold
wiring).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_outcome_verdict_freshness.py -q
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
from scripts.platformkit.ingame import ingame_outcome_verdict as _ov
from scripts.platformkit.ingame import ingame_outcome_verdict_multi as _ovm
from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.ingame import quote_freshness as _qf

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_outcome_verdict_freshness.json"
COMPONENT = "m_ingame_outcome_verdict_freshness"

# Sports this control runs over (production SPORTS list + mlb, LOCAL to this module
# only -- ingame_outcome_verdict_multi.SPORTS is left untouched per the brief).
CONTROL_SPORTS: List[str] = ["mlb"] + list(_ovm.SPORTS)

OutcomeFn = Callable[[str], Optional[int]]


def _mlb_outcome_fn() -> OutcomeFn:
    try:
        from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
        res = MlbOutcomeResolver()
        return res.home_win if res.available else (lambda _g: None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_mlb_outcome_fn init failed: %s", exc)
        return lambda _g: None


def _outcome_fn_for(sport: str) -> OutcomeFn:
    if sport == "mlb":
        return _mlb_outcome_fn()
    return _ovm._OUTCOME_FACTORY.get(sport, lambda: (lambda _g: None))()


def _brier_by_game_segment_both(
    files: Sequence[Path], outcome_fn: OutcomeFn, sport: str,
) -> Tuple[Dict[str, Dict[str, Tuple[float, float, int]]],
          Dict[str, Dict[str, Tuple[float, float, int]]],
          int, int, int, int]:
    """Same accumulation as ingame_outcome_verdict._brier_by_game_segment, but computed
    TWICE per game: once over all ticks (raw) and once over the freshness-filtered
    subset (fresh_only). Returns (raw_per, fresh_per, n_files, n_labeled,
    n_ticks_total, n_fresh_ticks_total). Never raises."""
    raw: Dict[str, Dict[str, Tuple[float, float, int]]] = defaultdict(dict)
    fresh: Dict[str, Dict[str, Tuple[float, float, int]]] = defaultdict(dict)
    n_files = n_labeled = 0
    n_ticks_total = n_fresh_ticks_total = 0
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
        except Exception:  # noqa: BLE001
            y = None
        if y is None:
            continue
        n_labeled += 1
        mask = _qf.freshness_mask(rows)
        n_ticks_total += len(rows)
        n_fresh_ticks_total += sum(1 for m in mask if m)

        def _accumulate(row_iter) -> Dict[str, List[float]]:
            acc: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
            for r in row_iter:
                mp, kp = r.get("model_prob"), r.get("market_prob")
                if mp is None or kp is None:
                    continue
                seg = _seg._infer_segment(sport, str(r.get("state_summary", "")))
                a = acc[seg]
                a[0] += (float(mp) - y) ** 2
                a[1] += (float(kp) - y) ** 2
                a[2] += 1
            return acc

        for seg, a in _accumulate(rows).items():
            if a[2] > 0:
                raw[seg][gid] = (a[0], a[1], int(a[2]))
        fresh_rows = [r for r, m in zip(rows, mask) if m]
        for seg, a in _accumulate(fresh_rows).items():
            if a[2] > 0:
                fresh[seg][gid] = (a[0], a[1], int(a[2]))
    return raw, fresh, n_files, n_labeled, n_ticks_total, n_fresh_ticks_total


def build_verdict_with_control(
    *, sport: str, grade_dir: Optional[Path] = None,
    paths: Optional[Sequence[Path]] = None,
    outcome_fn: Optional[OutcomeFn] = None,
    eps: float = _ov.EPS_DEFAULT,
    min_games: int = _ov.MIN_GAMES_PER_SEG,
    min_ticks: int = _ov.MIN_TICKS_PER_SEG,
) -> Dict[str, Any]:
    """Per-segment {'raw': ..., 'fresh_only': ...} verdict pair for *sport*. Never
    raises. Same min_games/min_ticks gate applies independently to each arm -- a
    thin fresh_only sample honestly reports INSUFFICIENT_DATA rather than a
    fabricated verdict."""
    try:
        files = list(paths) if paths is not None else _seg._discover(grade_dir, sport)
        ofn = outcome_fn if outcome_fn is not None else _outcome_fn_for(sport)
        raw_per, fresh_per, n_files, n_labeled, n_ticks, n_fresh = \
            _brier_by_game_segment_both(files, ofn, sport)
        all_segs = sorted(set(raw_per) | set(fresh_per))
        order = [s for s in _ov._SEGMENT_ORDER if s in all_segs] + \
            [s for s in all_segs if s not in _ov._SEGMENT_ORDER]
        segments: Dict[str, Any] = {}
        flips: List[str] = []
        for s in order:
            raw_v = _ov._seg_verdict(raw_per.get(s, {}), eps=eps,
                                     min_games=min_games, min_ticks=min_ticks)
            fresh_v = _ov._seg_verdict(fresh_per.get(s, {}), eps=eps,
                                       min_games=min_games, min_ticks=min_ticks)
            segments[s] = {"raw": raw_v, "fresh_only": fresh_v}
            if raw_v["verdict"] != fresh_v["verdict"]:
                flips.append(s)
        share = (n_fresh / n_ticks) if n_ticks > 0 else None
        return {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": COMPONENT, "sport": sport,
            "n_files": n_files, "n_labeled": n_labeled,
            "n_ticks": n_ticks, "n_fresh_ticks": n_fresh, "fresh_share": share,
            "segments": segments, "segment_order": order,
            "flipped_segments": flips,
            "units": "brier", "edge_claimed": False,
            "note": ("per-segment Brier of the live in-game model vs OUTCOME, model "
                     "vs VENUE in-play price, reported BOTH raw (all ticks) and "
                     "fresh_only (ticks where the venue quote genuinely moved since "
                     "the previous tick -- see quote_freshness.py). "
                     "flipped_segments lists segments whose verdict differs between "
                     "the two arms -- the honest signal that the raw verdict may be "
                     "an artifact of stale-quote scoring. Never a $ edge."),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_verdict_with_control(%s) failed: %s", sport, exc)
        return {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "component": COMPONENT, "sport": sport, "n_files": 0, "n_labeled": 0,
                "n_ticks": 0, "n_fresh_ticks": 0, "fresh_share": None,
                "segments": {}, "flipped_segments": [],
                "error": type(exc).__name__, "edge_claimed": False}


def build_all(sports: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Per-sport {'raw','fresh_only'} verdict docs composed into ONE ops artifact."""
    want = list(sports) if sports is not None else CONTROL_SPORTS
    per_sport = {s: build_verdict_with_control(sport=s) for s in want}
    flips_by_sport = {s: d.get("flipped_segments", []) for s, d in per_sport.items()
                      if d.get("flipped_segments")}
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component": COMPONENT, "sports": want,
        "per_sport": per_sport,
        "flipped_segments_by_sport": flips_by_sport,
        "units": "brier", "edge_claimed": False,
        "note": ("LANE 2 quote-freshness control: raw vs fresh_only model-vs-venue "
                 "Brier verdicts per sport+segment. flipped_segments_by_sport is the "
                 "headline -- any non-empty entry means an existing verdict does NOT "
                 "survive restricting to genuinely-fresh venue quotes."),
    }


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    import json
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 78, "QUOTE-FRESHNESS CONTROL -- raw vs fresh_only model-vs-venue Brier"]
    for sport, d in (doc.get("per_sport") or {}).items():
        L.append("-" * 78)
        L.append("SPORT=%s n_files=%d n_labeled=%d n_ticks=%d n_fresh=%d fresh_share=%s"
                 % (sport, d.get("n_files", 0), d.get("n_labeled", 0),
                    d.get("n_ticks", 0), d.get("n_fresh_ticks", 0),
                    "n/a" if d.get("fresh_share") is None else "%.3f" % d["fresh_share"]))
        segs = d.get("segments", {})
        for seg in d.get("segment_order", sorted(segs)):
            pair = segs.get(seg)
            if not pair:
                continue
            r, f = pair["raw"], pair["fresh_only"]
            if r["verdict"] == "INSUFFICIENT_DATA" and f["verdict"] == "INSUFFICIENT_DATA":
                continue
            flip = " <-- FLIP" if seg in d.get("flipped_segments", []) else ""
            L.append("  %-5s raw=%-18s(g=%-4d t=%-6d) fresh=%-18s(g=%-4d t=%-6d)%s" % (
                seg, r["verdict"], r.get("n_games", 0), r.get("total_ticks", 0),
                f["verdict"], f.get("n_games", 0), f.get("total_ticks", 0), flip))
    L.append("=" * 78)
    L.append("NOTE: venue price = thin Kalshi in-play quote. Brier/probability space "
             "only. edge_claimed=False. flipped segments = honest headline.")
    L.append("=" * 78)
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="ingame_outcome_verdict_freshness")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--sports", nargs="*", default=None)
    a = ap.parse_args(argv)
    doc = build_all(sports=a.sports)
    if not a.no_write:
        write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "COMPONENT", "CONTROL_SPORTS",
    "build_verdict_with_control", "build_all", "write_doc", "render",
]
