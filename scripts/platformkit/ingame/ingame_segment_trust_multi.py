"""scripts.platformkit.ingame.ingame_segment_trust_multi -- the MULTI-SPORT
counterpart to ingame_segment_trust.py (which is MLB-only). Same cross-corpus
proof-gated trust logic (>=2 disjoint date-parity corpora; a segment is TRUSTED
only if BETTER_THAN_VENUE in EVERY non-insufficient corpus, ADVERSE only if
WORSE in every), run for soccer_intl, tennis, and wnba so every CAPTURING sport
accrues the same honest replication discipline as MLB.

WHY A SEPARATE MODULE (reuses, never rebuilds, the MLB module's machinery)
----------------------------------------------------------------------------
ingame_segment_trust._split_corpora already has a NON-MLB fallback (files
whose sport != "mlb" split by a deterministic md5(game_id) hash, since only
MLB tickers carry a directly-parseable date via parse_mlb_ticker) and
_classify is already sport-agnostic (TRUSTED/ADVERSE/NEUTRAL from a list of
per-corpus verdict strings). The only real gap was that build_trust's default
outcome_fn hardcodes MlbOutcomeResolver and its verdict step calls
ingame_outcome_verdict.build_verdict (MLB-default) rather than the per-sport
outcome_fn wiring in ingame_outcome_verdict_multi. This module supplies that
per-sport wiring and composes all three sports into ONE ops artifact.

MEASUREMENT ONLY (binding, per the brief)
----------------------------------------------------------------------------
This module computes and WRITES a trust map only. It does NOT wire any
floor/execution routing anywhere -- the MLB-only ingame_segment_trust.
floor_for_segment() path is UNTOUCHED and remains the only trust gate that
affects execution, pending a human review of whether/how to extend routing to
these sports. No $/roi/pnl field; edge_claimed always False; flips no feature
flag; places no bet.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network; never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_segment_trust_multi.py -q
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
from scripts.platformkit.ingame import ingame_outcome_verdict as _ov
from scripts.platformkit.ingame import ingame_outcome_verdict_multi as _ovm
from scripts.platformkit.ingame import ingame_segment_trust as _st

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
TRUST_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_segment_trust_multi.json"
COMPONENT = "m_ingame_segment_trust_multi"

SPORTS: List[str] = list(_ovm.SPORTS)
N_CORPORA = _st.N_CORPORA
MIN_CORPORA = _st.MIN_CORPORA


def build_trust_for_sport(sport: str, *, grade_dir: Optional[Path] = None,
                          paths: Optional[Sequence[Path]] = None,
                          outcome_fn: Optional[Callable[[str], Optional[int]]] = None,
                          n_corpora: int = N_CORPORA) -> Dict[str, Any]:
    """One sport's cross-corpus trust doc, reusing ingame_segment_trust's
    disjoint-split + classify machinery with the per-sport outcome_fn from
    ingame_outcome_verdict_multi. Never raises."""
    try:
        files = list(paths) if paths is not None else _seg._discover(grade_dir, sport)
        ofn = outcome_fn
        if ofn is None:
            factory = _ovm._OUTCOME_FACTORY.get(sport)
            ofn = factory() if factory is not None else (lambda _g: None)
        corpora = _st._split_corpora(files, sport, n_corpora)
        docs = [_ov.build_verdict(sport=sport, paths=c, outcome_fn=ofn) for c in corpora]
        per_seg: Dict[str, List[str]] = defaultdict(list)
        for d in docs:
            for seg, v in (d.get("segments") or {}).items():
                per_seg[seg].append(str(v.get("verdict")))
        segments: Dict[str, Any] = {}
        for seg in _ov._SEGMENT_ORDER + sorted(s for s in per_seg
                                               if s not in _ov._SEGMENT_ORDER):
            if seg not in per_seg and seg not in _ov._SEGMENT_ORDER:
                continue
            pc = per_seg.get(seg, [])
            segments[seg] = {"trust": _st._classify(pc), "per_corpus": pc}
        trusted = [s for s, v in segments.items() if v["trust"] == _st._TRUSTED]
        adverse = [s for s, v in segments.items() if v["trust"] == _st._ADVERSE]
        return {
            "sport": sport, "n_corpora": len(corpora),
            "corpus_labeled": [d.get("n_labeled", 0) for d in docs],
            "segments": segments, "trusted": trusted, "adverse": adverse,
            "units": "brier", "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_trust_for_sport(%s) failed: %s", sport, exc)
        return {"sport": sport, "n_corpora": 0, "corpus_labeled": [], "segments": {},
                "trusted": [], "adverse": [], "error": type(exc).__name__,
                "edge_claimed": False}


def build_trust_all(sports: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Per-sport trust docs composed into ONE ops artifact. MEASUREMENT ONLY --
    wires no floor/execution routing. Never raises."""
    want = list(sports) if sports is not None else SPORTS
    per_sport: Dict[str, Any] = {}
    for sport in want:
        per_sport[sport] = build_trust_for_sport(sport)
    trusted_by_sport = {s: d.get("trusted", []) for s, d in per_sport.items()
                        if d.get("trusted")}
    adverse_by_sport = {s: d.get("adverse", []) for s, d in per_sport.items()
                        if d.get("adverse")}
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component": COMPONENT, "sports": want,
        "per_sport": per_sport,
        "trusted_by_sport": trusted_by_sport,
        "adverse_by_sport": adverse_by_sport,
        "units": "brier", "edge_claimed": False,
        "measurement_only": True,
        "note": ("cross-corpus (independent date/hash-split) replicated segment "
                 "trust for every CAPTURING sport beyond MLB (soccer_intl/tennis/"
                 "wnba): TRUSTED/ADVERSE only if BETTER/WORSE_THAN_VENUE in EVERY "
                 "non-insufficient corpus, else NEUTRAL. MEASUREMENT ONLY -- this "
                 "does NOT wire any floor/execution routing; the MLB-only "
                 "ingame_segment_trust.floor_for_segment path is untouched and "
                 "remains the sole trust gate that affects execution, pending "
                 "human review. No $ edge; venue = thin Kalshi in-play quote."),
    }


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else TRUST_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 70, "IN-GAME SEGMENT TRUST -- MULTI-SPORT (soccer_intl/tennis/wnba)",
         "measurement_only=%s" % doc.get("measurement_only")]
    for sport, d in (doc.get("per_sport") or {}).items():
        L.append("-" * 70)
        L.append("SPORT=%s corpus_labeled=%s" % (sport, d.get("corpus_labeled")))
        for seg, v in (d.get("segments") or {}).items():
            if v.get("trust") == "NEUTRAL" and all(
                    p in ("INSUFFICIENT_DATA", "None", "") for p in v.get("per_corpus", [])):
                continue
            L.append("  %-5s %-9s %s" % (seg, v.get("trust"), v.get("per_corpus")))
    L.append("-" * 70)
    L.append("TRUSTED by sport: %s" % (doc.get("trusted_by_sport") or "none"))
    L.append("ADVERSE by sport: %s" % (doc.get("adverse_by_sport") or "none"))
    L.append("NOTE: MEASUREMENT ONLY -- no floor/execution wiring. No $ edge; "
             "venue=thin Kalshi in-play.")
    L.append("=" * 70)
    return "\n".join(L)


def run(*, interval_sec: float = 1800.0, path: Optional[Path] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
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
            doc = build_trust_all()
            write_doc(doc, path)
            print("%s | tick=%d trusted=%s adverse=%s" % (
                COMPONENT, ticks, doc.get("trusted_by_sport"),
                doc.get("adverse_by_sport")), flush=True)
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
    ap = argparse.ArgumentParser(prog="ingame_segment_trust_multi")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--interval", type=float, default=None)
    a = ap.parse_args(argv)
    if a.interval is not None:
        print("%s | started interval=%ss sports=%s" % (COMPONENT, a.interval, SPORTS),
              flush=True)
        run(interval_sec=a.interval)
        return 0
    doc = build_trust_all()
    if not a.no_write:
        write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TRUST_PATH", "COMPONENT", "SPORTS", "build_trust_for_sport", "build_trust_all",
    "write_doc", "render", "run",
]
