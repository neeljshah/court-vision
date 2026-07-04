"""scripts.platformkit.ingame.ingame_freshness_cross_corpus -- CROSS-CORPUS
adjudication of wave-7's MLB fresh-only WORSE_THAN_VENUE finding (queue item 4).

WHY
---
ingame_outcome_verdict_freshness.py found, on the FULL 105-game labeled MLB corpus,
that the RAW (all-ticks) verdict is MATCH in every segment but the FRESH_ONLY arm
(ticks where the venue quote genuinely moved -- quote_freshness.freshness_mask)
flips I4/I5/I6 to WORSE_THAN_VENUE (I9 flips to INSUFFICIENT_DATA). fresh_share is
thin (0.218) and this is a SINGLE corpus -- the exact shape the discipline forbids
acting on (">=2 independent corpora; single-fold lifts/drops are artifacts", see
ingame_segment_trust.py, which caught wave-27's I5-I9 BETTER lift the same way).

This module is the adjudication: run the FRESH_ONLY arm on >=2 independent split
schemes of the SAME corpus and report WORSE-REPLICATED / NOT-REPLICATED /
INSUFFICIENT per segment per scheme.

SPLIT SCHEMES (both additive; neither touches ingame_segment_trust.py's
_split_corpora, which is imported and reused unchanged for scheme A)
----------------------------------------------------------------------------
  A. date_parity  -- reuses ingame_segment_trust._split_corpora (day%2 halves;
     the SAME scheme wave-28 used to correct wave-27). Two disjoint halves.
  B. date_era     -- NEW: median-date split of the SAME labeled corpus into an
     EARLY half and a LATE half (the corpus spans ~2026-06-19..07-05) --a second,
     independent way of asking "does this hold up over time", not just parity.

METHOD
------
For each split scheme, for each half, run the SAME fresh_only Brier-vs-outcome
accumulation ingame_outcome_verdict_freshness.py uses (imported, not reimplemented)
restricted to that half's files, then _ov._seg_verdict with the SAME gate
(MIN_GAMES_PER_SEG / MIN_TICKS_PER_SEG). Fresh-tick counts are thin per half by
construction -- INSUFFICIENT_DATA is the expected, honest outcome for many
segments, not a bug.

VERDICT (per segment, across a scheme's halves)
  WORSE-REPLICATED  -- WORSE_THAN_VENUE in EVERY non-insufficient half (>=2 ruling)
  NOT-REPLICATED    -- ruled in >=2 halves but not unanimous WORSE (mirrors the
                        wave-28 correction shape: one half worse, other MATCH/BETTER)
  INSUFFICIENT      -- fewer than 2 non-insufficient halves for this scheme

HONESTY (binding, same framing as ingame_outcome_verdict_freshness.py): venue price
= thin/laggy Kalshi in-play quote; Brier/probability space only; no $/roi/pnl field;
edge_claimed always False. This module MEASURES ONLY -- it changes no floor, no
threshold, no execution behavior; ingame_segment_trust.py's ADVERSE gate already
covers execution effects and is untouched here.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network; never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_freshness_cross_corpus.py -q
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
from scripts.platformkit.ingame import ingame_outcome_verdict as _ov
from scripts.platformkit.ingame import ingame_outcome_verdict_freshness as _ovf
from scripts.platformkit.ingame import ingame_segment_trust as _trust
from scripts.platformkit.ingame import live_grade as _lg

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_freshness_cross_corpus.json"
COMPONENT = "m_ingame_freshness_cross_corpus"

SPLIT_SCHEMES = ["date_parity", "date_era"]
MIN_HALVES_RULING = 2

_WORSE_REPLICATED = "WORSE-REPLICATED"
_NOT_REPLICATED = "NOT-REPLICATED"
_INSUFFICIENT = "INSUFFICIENT"


def _game_date(gid: str, valid_abbrs: set):
    """Best-effort ticker date for one MLB grade file's game_id; None if unparsable."""
    try:
        from scripts.platformkit.ingame.ingame_outcome_label import parse_mlb_ticker
        parsed = parse_mlb_ticker(gid, valid_abbrs)
        return parsed[0] if parsed is not None else None
    except Exception:  # noqa: BLE001
        return None


def _split_date_era(files: Sequence[Path], sport: str) -> List[List[Path]]:
    """EARLY/LATE halves by median ticker date (the second, independent split
    scheme). A file whose date can't be parsed is dropped from both halves (mirrors
    _split_corpora's "drop if unparsable" behaviour for MLB)."""
    if str(sport).lower() != "mlb":
        # non-MLB has no ticker date; fall back to the parity split so the caller
        # still gets 2 disjoint halves rather than raising.
        return _trust._split_corpora(files, sport, 2)
    valid: set = set()
    try:
        from scripts.platformkit.ingame.ingame_outcome_label import (
            MlbOutcomeResolver, _KALSHI_TO_ESPN)
        res = MlbOutcomeResolver()
        valid = (res._abbrs | set(_KALSHI_TO_ESPN.keys())) if res.available else set()
    except Exception:  # noqa: BLE001
        valid = set()
    dated: List[tuple] = []
    for p in files:
        try:
            rows = _lg._load_pairs(Path(p))
            gid = str(rows[0].get("game_id")) if rows else Path(p).stem
        except Exception:  # noqa: BLE001
            gid = Path(p).stem
        d = _game_date(gid, valid) if valid else None
        if d is not None:
            dated.append((d, Path(p)))
    if not dated:
        return [[], []]
    dated.sort(key=lambda t: t[0])
    mid = len(dated) // 2
    early = [p for _, p in dated[:mid]]
    late = [p for _, p in dated[mid:]]
    return [early, late]


def _split_for_scheme(scheme: str, files: Sequence[Path], sport: str) -> List[List[Path]]:
    if scheme == "date_era":
        return _split_date_era(files, sport)
    return _trust._split_corpora(files, sport, 2)  # date_parity (reused, unchanged)


def _fresh_only_verdict_for_half(files: Sequence[Path], outcome_fn, sport: str,
                                 eps: float, min_games: int, min_ticks: int
                                 ) -> Dict[str, Any]:
    """fresh_only-arm segment verdicts for one half, using the SAME accumulator
    ingame_outcome_verdict_freshness.py uses (imported, no reimplementation)."""
    _raw_per, fresh_per, n_files, n_labeled, n_ticks, n_fresh = \
        _ovf._brier_by_game_segment_both(files, outcome_fn, sport)
    segments = {s: _ov._seg_verdict(fresh_per.get(s, {}), eps=eps,
                                    min_games=min_games, min_ticks=min_ticks)
                for s in _ov._SEGMENT_ORDER}
    share = (n_fresh / n_ticks) if n_ticks > 0 else None
    return {"n_files": n_files, "n_labeled": n_labeled, "n_ticks": n_ticks,
            "n_fresh_ticks": n_fresh, "fresh_share": share, "segments": segments}


def _classify(per_half_verdicts: List[Optional[str]]) -> str:
    ruling = [v for v in per_half_verdicts if v not in (None, "INSUFFICIENT_DATA")]
    if len(ruling) < MIN_HALVES_RULING:
        return _INSUFFICIENT
    if all(v == "WORSE_THAN_VENUE" for v in ruling):
        return _WORSE_REPLICATED
    return _NOT_REPLICATED


def build_report(*, sport: str = "mlb", grade_dir: Optional[Path] = None,
                 paths: Optional[Sequence[Path]] = None,
                 outcome_fn=None,
                 eps: float = _ov.EPS_DEFAULT,
                 min_games: int = _ov.MIN_GAMES_PER_SEG,
                 min_ticks: int = _ov.MIN_TICKS_PER_SEG,
                 schemes: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Cross-corpus adjudication of the fresh_only WORSE finding. NEVER raises."""
    try:
        files = list(paths) if paths is not None else _seg._discover(grade_dir, sport)
        ofn = outcome_fn
        if ofn is None:
            from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
            res = MlbOutcomeResolver()
            ofn = res.home_win if res.available else (lambda _g: None)
        want_schemes = list(schemes) if schemes is not None else SPLIT_SCHEMES
        by_scheme: Dict[str, Any] = {}
        for scheme in want_schemes:
            halves = _split_for_scheme(scheme, files, sport)
            half_docs = [_fresh_only_verdict_for_half(h, ofn, sport, eps, min_games,
                                                       min_ticks) for h in halves]
            per_seg: Dict[str, Any] = {}
            for s in _ov._SEGMENT_ORDER:
                per_half = [hd["segments"].get(s, {}).get("verdict") for hd in half_docs]
                per_seg[s] = {
                    "verdict": _classify(per_half),
                    "per_half_verdict": per_half,
                    "per_half_n_games": [hd["segments"].get(s, {}).get("n_games", 0)
                                        for hd in half_docs],
                    "per_half_fresh_ticks": [hd["segments"].get(s, {}).get("total_ticks", 0)
                                            for hd in half_docs],
                    "per_half_delta": [hd["segments"].get(s, {}).get("brier_delta")
                                      for hd in half_docs],
                }
            by_scheme[scheme] = {
                "n_halves": len(halves),
                "half_n_files": [hd["n_files"] for hd in half_docs],
                "half_n_labeled": [hd["n_labeled"] for hd in half_docs],
                "half_n_ticks": [hd["n_ticks"] for hd in half_docs],
                "half_n_fresh_ticks": [hd["n_fresh_ticks"] for hd in half_docs],
                "half_fresh_share": [hd["fresh_share"] for hd in half_docs],
                "segments": per_seg,
            }
        # overall per-segment verdict = WORSE-REPLICATED only if every scheme agrees;
        # else the weaker of what the schemes say (never overstate replication).
        overall: Dict[str, str] = {}
        for s in _ov._SEGMENT_ORDER:
            per_scheme_v = [by_scheme[sc]["segments"][s]["verdict"] for sc in by_scheme]
            if not per_scheme_v:
                overall[s] = _INSUFFICIENT
            elif all(v == _WORSE_REPLICATED for v in per_scheme_v):
                overall[s] = _WORSE_REPLICATED
            elif any(v == _NOT_REPLICATED for v in per_scheme_v):
                overall[s] = _NOT_REPLICATED
            else:
                overall[s] = _INSUFFICIENT
        return {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": COMPONENT, "sport": sport,
            "source_finding": ("wave-7 ingame_outcome_verdict_freshness.py: raw=MATCH "
                               "all segments, fresh_only flips I4/I5/I6 to "
                               "WORSE_THAN_VENUE (I9 to INSUFFICIENT_DATA) on the full "
                               "105-game labeled corpus, fresh_share=0.218"),
            "schemes": by_scheme, "overall_segment_verdict": overall,
            "units": "brier", "edge_claimed": False,
            "note": ("Cross-corpus adjudication of a single-corpus fresh_only finding, "
                     "per the >=2-independent-corpora replication rule. "
                     "WORSE-REPLICATED = WORSE_THAN_VENUE in every non-insufficient "
                     "half of EVERY split scheme. NOT-REPLICATED = ruled but not "
                     "unanimous (the wave-28-shaped correction pattern). INSUFFICIENT "
                     "= fewer than 2 ruling halves. Measurement only -- no floor/"
                     "threshold/execution change. Venue price = thin Kalshi in-play "
                     "quote; probability/Brier space only; edge_claimed=False."),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_report(%s) failed: %s", sport, exc)
        return {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "component": COMPONENT, "sport": sport, "schemes": {},
                "overall_segment_verdict": {}, "error": type(exc).__name__,
                "edge_claimed": False}


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    import json
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 84, "MLB FRESH-ONLY WORSE -- cross-corpus adjudication (queue item 4)"]
    L.append(doc.get("source_finding", ""))
    for scheme, d in (doc.get("schemes") or {}).items():
        L.append("-" * 84)
        L.append("SCHEME=%s halves_n_labeled=%s halves_n_fresh_ticks=%s fresh_share=%s"
                 % (scheme, d.get("half_n_labeled"), d.get("half_n_fresh_ticks"),
                    d.get("half_fresh_share")))
        for seg, sv in d.get("segments", {}).items():
            L.append("  %-5s %-16s per_half=%s n_games=%s fresh_ticks=%s delta=%s"
                     % (seg, sv["verdict"], sv["per_half_verdict"],
                        sv["per_half_n_games"], sv["per_half_fresh_ticks"],
                        sv["per_half_delta"]))
    L.append("=" * 84)
    L.append("OVERALL (both schemes combined, conservative):")
    for seg, v in (doc.get("overall_segment_verdict") or {}).items():
        L.append("  %-5s %s" % (seg, v))
    L.append("NOTE: venue=thin Kalshi in-play quote. Brier/probability space only. "
             "edge_claimed=False. Measurement only.")
    L.append("=" * 84)
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="ingame_freshness_cross_corpus")
    ap.add_argument("--sport", default="mlb")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    doc = build_report(sport=a.sport)
    if not a.no_write:
        write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "COMPONENT", "SPLIT_SCHEMES", "build_report", "write_doc", "render",
]
