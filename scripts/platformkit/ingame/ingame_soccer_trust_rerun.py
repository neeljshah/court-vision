"""scripts.platformkit.ingame.ingame_soccer_trust_rerun -- QUEUE ITEM 3, LANE 3:
soccer_intl trust RE-ADJUDICATION on the enlarged corpus (RAW vs BACKFILLED).

WHY: wave-6 (docs/research/organization-sprint/PROPOSED_soccer_inplay_suppression.md
section 2) found the md5(game_id) hash split put only 6-and-6 real-state games
per corpus per half (H1/H2), below MIN_GAMES_PER_SEG=8 -- INSUFFICIENT, not
ADVERSE-REPLICATED. Since then: the soccer outcome resolver fix took labeled
games 8 -> 30, and tick_segment_backfill.py (LANE 5) segment-labeled the 22
formerly-UNK games via kickoff+elapsed-minute with a +/-10min excluded
boundary band (sidecar: data/domains/soccer_intl/tick_segment_backfill.json).
Re-runs the adjudication in TWO VARIANTS, never merged: RAW (only the 18
games whose ticks natively carry minute/half state, today's baseline
_infer_segment path) vs BACKFILLED (RAW's 18 + the 22 sidecar-labeled games,
each tick H1/H2-labeled via the sidecar if resolved else left UNK, never
guessed; provenance-tagged segment_source="backfilled").

WHY A SEPARATE MODULE: same reasoning as ingame_unk_backfill_verdict.py --
_infer_segment has no ts/game_id context and cannot consume the sidecar
without touching files MLB's live path depends on. Reuses shared PURE math
(_ov._seg_verdict) and split machinery (_st._split_corpora, _st._classify)
by import; never edits ingame_outcome_verdict.py / _multi.py /
ingame_segment_trust.py / _multi.py.

SECOND SPLIT SCHEME: Scheme A = md5(game_id) hash parity (module default).
Scheme B = ticker calendar-day-of-month parity -- replaces wave-6's
chronological split, DEGENERATE for H1/H2 since minute-instrumented capture
only began 2026-06-27 (every native-state game on/after that day).

FRESHNESS ARM (queue item 3.2): same splits, also reports fresh_only (ticks
where quote_freshness.freshness_mask says the venue quote actually moved),
same machinery as ingame_outcome_verdict_freshness.py. Below
MIN_TICKS_PER_SEG -> honest INSUFFICIENT_DATA, never fabricated.

HONESTY: venue price = thin/laggy Kalshi in-play quote, NOT an efficient
close. WORSE/BETTER_THAN_VENUE is calibration only, never a $ edge.
Probability/Brier space only; edge_claimed always False. MEASUREMENT ONLY --
writes no floor/execution wiring; ingame_segment_trust.floor_for_segment
(MLB-only) is untouched.

INVARIANTS: <=300 LOC; ASCII only; no network at import time; never writes
data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_soccer_trust_rerun.py -q
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
from scripts.platformkit.ingame import ingame_outcome_verdict as _ov
from scripts.platformkit.ingame import ingame_outcome_verdict_multi as _ovm
from scripts.platformkit.ingame import ingame_segment_trust as _st
from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.ingame import quote_freshness as _qf
from scripts.platformkit.ingame import tick_segment_backfill as _tsb

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_soccer_trust_rerun.json"
COMPONENT = "m_ingame_soccer_trust_rerun"
SPORT = "soccer_intl"
_HALVES = ("H1", "H2")

OutcomeFn = Callable[[str], Optional[int]]


def _day_parity_split(files: Sequence[Path], n: int = 2) -> List[List[Path]]:
    """Scheme B: ticker calendar-day-of-month parity. Deterministic; a ticker
    whose date can't be parsed falls back to md5(game_id) (never dropped)."""
    buckets: List[List[Path]] = [[] for _ in range(n)]
    for p in files:
        gid = Path(p).stem
        parsed = _tsb.parse_ticker(gid)
        if parsed is not None:
            date, _a, _b = parsed
            idx = date.day % n
        else:
            idx = int(hashlib.md5(gid.encode("utf-8")).hexdigest(), 16) % n
        buckets[idx].append(Path(p))
    return buckets


def _segment_for_row(game_id: str, row: Dict[str, Any], variant: str, sidecar: Optional[Dict[str, Any]]) -> str:
    """H1/H2/UNK for one tick under *variant* ('raw' or 'backfilled')."""
    seg = _seg._infer_segment(SPORT, str(row.get("state_summary", "")))
    if seg in _HALVES:
        return seg
    if variant == "backfilled" and sidecar is not None:
        lab = _tsb.lookup_segment(sidecar, game_id, str(row.get("ts", "")))
        if lab in _HALVES:
            return lab
    return "UNK"


def _accumulate(files: Sequence[Path], outcome_fn: OutcomeFn, variant: str,
                sidecar: Optional[Dict[str, Any]], *, fresh_only: bool = False,
                ) -> Tuple[Dict[str, Dict[str, Tuple[float, float, int]]], int]:
    """seg -> {game_id: (sse_model, sse_market, n_ticks)} + n_labeled. Never raises."""
    per: Dict[str, Dict[str, Tuple[float, float, int]]] = defaultdict(dict)
    n_labeled = 0
    for p in files:
        try:
            rows = _lg._load_pairs(Path(p))
        except Exception:  # noqa: BLE001
            rows = []
        if not rows:
            continue
        gid = str(rows[0].get("game_id") or Path(p).stem)
        try:
            y = outcome_fn(gid)
        except Exception:  # noqa: BLE001
            y = None
        if y is None:
            continue
        n_labeled += 1
        if fresh_only:
            mask = _qf.freshness_mask(rows)
            rows = [r for r, m in zip(rows, mask) if m]
        acc: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        for r in rows:
            mp, kp = r.get("model_prob"), r.get("market_prob")
            if mp is None or kp is None:
                continue
            seg = _segment_for_row(gid, r, variant, sidecar)
            a = acc[seg]
            a[0] += (float(mp) - y) ** 2
            a[1] += (float(kp) - y) ** 2
            a[2] += 1
        for seg, a in acc.items():
            if a[2] > 0:
                per[seg][gid] = (a[0], a[1], int(a[2]))
    return per, n_labeled


def _verdicts_by_half(per: Dict[str, Dict[str, Tuple[float, float, int]]]) -> Dict[str, Any]:
    return {h: _ov._seg_verdict(per.get(h, {}), eps=_ov.EPS_DEFAULT,
                                min_games=_ov.MIN_GAMES_PER_SEG,
                                min_ticks=_ov.MIN_TICKS_PER_SEG) for h in _HALVES}


def _scheme_doc(corpora: List[List[Path]], outcome_fn: OutcomeFn, variant: str,
                sidecar: Optional[Dict[str, Any]], *, with_freshness: bool,
                ) -> Dict[str, Any]:
    """One scheme's per-corpus, per-half verdicts (+ optional fresh_only arm)."""
    per_corpus: List[Dict[str, Any]] = []
    per_seg_verdicts: Dict[str, List[str]] = defaultdict(list)
    for files in corpora:
        per, n_labeled = _accumulate(files, outcome_fn, variant, sidecar)
        segs = _verdicts_by_half(per)
        entry: Dict[str, Any] = {"n_files": len(files), "n_labeled": n_labeled,
                                 "segments": segs}
        if with_freshness:
            fper, _ = _accumulate(files, outcome_fn, variant, sidecar, fresh_only=True)
            entry["segments_fresh_only"] = _verdicts_by_half(fper)
        per_corpus.append(entry)
        for h in _HALVES:
            per_seg_verdicts[h].append(segs[h]["verdict"])
    classify = {h: _st._classify(per_seg_verdicts[h]) for h in _HALVES}
    return {"per_corpus": per_corpus, "classify": classify}


def _final_verdict(scheme_a: Dict[str, Any], scheme_b: Dict[str, Any], half: str,
                   ) -> Tuple[str, str]:
    """(verdict, reason) for one half; requires replication in BOTH schemes
    (samples never merged). ADVERSE-REPLICATED only if both classify ADVERSE."""
    a = scheme_a["classify"][half]
    b = scheme_b["classify"][half]
    def _all_insufficient(s: Dict[str, Any]) -> bool:
        return all(c["segments"][half]["verdict"] == "INSUFFICIENT_DATA" for c in s["per_corpus"])
    if a == "ADVERSE" and b == "ADVERSE":
        return "ADVERSE-REPLICATED", "WORSE_THAN_VENUE in every non-insufficient corpus of both schemes"
    if _all_insufficient(scheme_a) or _all_insufficient(scheme_b):
        return "INSUFFICIENT", "at least one scheme has zero non-insufficient corpora for this half"
    if a == "NEUTRAL" or b == "NEUTRAL":
        return "INSUFFICIENT", "at least one scheme did not reach a clean ADVERSE/TRUSTED ruling (mixed or one-sided corpora)"
    return "NOT-REPLICATED", "not ADVERSE in both schemes"


def build_rerun(*, grade_dir: Optional[Path] = None,
               outcome_fn: Optional[OutcomeFn] = None,
               sidecar_path: Optional[Path] = None) -> Dict[str, Any]:
    """Full LANE-3 re-adjudication doc: RAW vs BACKFILLED x scheme A/B x half,
    plus freshness arm. Never raises."""
    try:
        files = _seg._discover(grade_dir, SPORT)
        ofn = outcome_fn
        if ofn is None:
            factory = _ovm._OUTCOME_FACTORY.get(SPORT)
            ofn = factory() if factory is not None else (lambda _g: None)
        sidecar = _tsb.load_sidecar(sidecar_path)

        corpora_a = _st._split_corpora(files, SPORT, 2)
        corpora_b = _day_parity_split(files, 2)

        variants: Dict[str, Any] = {}
        for variant in ("raw", "backfilled"):
            sc_a = _scheme_doc(corpora_a, ofn, variant, sidecar, with_freshness=True)
            sc_b = _scheme_doc(corpora_b, ofn, variant, sidecar, with_freshness=True)
            per_half: Dict[str, Any] = {}
            for h in _HALVES:
                verdict, reason = _final_verdict(sc_a, sc_b, h)
                per_half[h] = {"verdict": verdict, "reason": reason}
            variants[variant] = {"scheme_a_md5_hash": sc_a, "scheme_b_day_parity": sc_b,
                                 "half_verdict": per_half}

        return {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": COMPONENT, "sport": SPORT,
            "n_files_total": len(files),
            "sidecar_present": sidecar is not None,
            "sidecar_buffer_min": (sidecar or {}).get("buffer_min"),
            "variants": variants,
            "units": "brier", "edge_claimed": False,
            "note": ("LANE 3 re-adjudication: RAW (native-state games) vs BACKFILLED "
                     "(RAW + sidecar-labeled games, segment_source=backfilled), each "
                     "split 2 independent ways (md5 hash parity; day-of-month parity), "
                     "per H1/H2, plus a fresh_only control on the same splits. "
                     "ADVERSE-REPLICATED requires WORSE_THAN_VENUE in every "
                     "non-insufficient corpus of both schemes. No $/roi claim; "
                     "venue = thin Kalshi in-play quote."),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_rerun failed: %s", exc)
        return {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "component": COMPONENT, "sport": SPORT, "error": type(exc).__name__,
                "edge_claimed": False}


def overall_verdict(doc: Dict[str, Any]) -> Tuple[str, str]:
    """Roll BOTH variants' per-half verdicts into one headline: ADVERSE-REPLICATED
    only if every half of every variant says so; INSUFFICIENT if any half says
    INSUFFICIENT; else NOT-REPLICATED."""
    variants = doc.get("variants") or {}
    verdicts = [(variants.get(variant) or {}).get("half_verdict", {}).get(h, {}).get("verdict")
                for variant in ("raw", "backfilled") for h in _HALVES]
    if any(v is None for v in verdicts):
        return "INSUFFICIENT", "verdict doc incomplete"
    if all(v == "ADVERSE-REPLICATED" for v in verdicts):
        return "ADVERSE-REPLICATED", "every half of both variants replicated WORSE"
    if any(v == "INSUFFICIENT" for v in verdicts):
        return "INSUFFICIENT", "at least one half/variant combination is INSUFFICIENT"
    return "NOT-REPLICATED", "not every half/variant combination replicated WORSE"


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> Path:
    p = Path(path) if path is not None else OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)
    return p


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 78, "SOCCER_INTL TRUST RE-ADJUDICATION (RAW vs BACKFILLED, 2 schemes)"]
    for variant in ("raw", "backfilled"):
        vd = (doc.get("variants") or {}).get(variant, {})
        L.append("-" * 78)
        L.append("VARIANT=%s" % variant)
        for scheme_key, label in (("scheme_a_md5_hash", "A(md5)"), ("scheme_b_day_parity", "B(dayparity)")):
            for i, corpus in enumerate(vd.get(scheme_key, {}).get("per_corpus", [])):
                L.append("  %s corpus%d n_labeled=%d" % (label, i, corpus.get("n_labeled", 0)))
                for h in _HALVES:
                    v = corpus["segments"].get(h, {})
                    d = "n/a" if v.get("brier_delta") is None else "%+.4f" % v["brier_delta"]
                    L.append("    %s %-18s games=%-3d ticks=%-5d delta=%s" % (
                        h, v.get("verdict"), v.get("n_games", 0), v.get("total_ticks", 0), d))
        for h in _HALVES:
            hv = vd.get("half_verdict", {}).get(h, {})
            L.append("  FINAL %s: %s (%s)" % (h, hv.get("verdict"), hv.get("reason")))
    ov, reason = overall_verdict(doc)
    L.append("=" * 78)
    L.append("OVERALL VERDICT: %s (%s)" % (ov, reason))
    L.append("NOTE: no $ edge; venue=thin Kalshi in-play quote. Brier space only.")
    L.append("=" * 78)
    return "\n".join(L)


def main() -> int:
    doc = build_rerun()
    write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "COMPONENT", "SPORT", "build_rerun", "overall_verdict", "write_doc", "render",
]
