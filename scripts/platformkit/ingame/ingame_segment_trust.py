"""scripts.platformkit.ingame.ingame_segment_trust -- CROSS-CORPUS proof-gated
segment trust for in-game execution (the self-improving-execution loop).

WHY
---
ingame_outcome_verdict, run on the FULL captured corpus, said the live model beats the
Kalshi in-play price on Brier in innings I5-I9.  Split into two INDEPENDENT corpora
(even-dated vs odd-dated games) that lift did NOT replicate -- one half showed it strongly,
the other was all MATCH.  That is the classic single-fold artifact the discipline forbids
acting on (">= 2 independent corpora; single-fold lifts are artifacts").

This module is the gate that enforces that discipline AUTOMATICALLY so execution can only
ever change on REPLICATED evidence, and improves on its own as games accrue:

  * Split the labeled grade corpus into >=2 disjoint corpora (by game-date parity).
  * Run the outcome verdict on EACH corpus independently.
  * A segment is TRUSTED  only if it is BETTER_THAN_VENUE in EVERY non-insufficient corpus
    (and at least MIN_CORPORA of them are non-insufficient).
    ADVERSE  only if it is WORSE_THAN_VENUE in EVERY non-insufficient corpus.
    Otherwise NEUTRAL (the honest default -- no proven, replicated signal).

EXECUTION EFFECT (do-no-harm, reversible)
-----------------------------------------
floor_for_segment() returns the in-game EV floor to use for a tick's segment:
  * ADVERSE segment -> None (the STRICT pre-registered policy floor) = suppress the marginal
    relaxed-floor bets in a segment PROVEN, across corpora, worse than the venue price.
  * TRUSTED / NEUTRAL / unknown / disabled -> the caller's relaxed floor (today's behaviour).
So it ONLY tightens segments with cross-corpus PROOF of being worse; thin/unreplicated data
changes nothing and can never starve the channel.  Env CV_INGAME_SEGMENT_TRUST=0 fully
disables (always returns the relaxed floor).

HONESTY: probability/Brier space; no $/roi/pnl; edge_claimed always False; flips no feature
flag; places no bet (only chooses which pre-registered floor applies).  A gate that trusts
NOTHING is the correct, honest state until a lift replicates.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network;
never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_segment_trust.py -q
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
from scripts.platformkit.ingame import ingame_outcome_verdict as _ov
from scripts.platformkit.ingame import live_grade as _lg

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
TRUST_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_segment_trust.json"
COMPONENT = "m_ingame_segment_trust"
ENV_FLAG = "CV_INGAME_SEGMENT_TRUST"  # "0" disables; anything else = enabled (default on)
N_CORPORA = 2
MIN_CORPORA = 2  # a segment must be non-insufficient in at least this many corpora to rule

_TRUSTED = "TRUSTED"
_ADVERSE = "ADVERSE"
_NEUTRAL = "NEUTRAL"

# module-level cache: (path, mtime) -> {seg: trust}
_CACHE: Dict[str, Any] = {"key": None, "map": {}}


def is_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "1").strip() != "0"


def _split_corpora(files: Sequence[Path], sport: str,
                   n: int = N_CORPORA) -> List[List[Path]]:
    """Split grade files into *n* disjoint corpora by GAME DATE parity (independent games).

    MLB files are keyed by the Kalshi ticker (date-encoded) -> split by day % n; a file
    whose date can't be parsed is dropped from every corpus (it cannot be placed stably).
    Non-MLB (no ticker date) falls back to file-name hash so the split is still disjoint."""
    buckets: List[List[Path]] = [[] for _ in range(n)]
    valid: set = set()
    try:
        from scripts.platformkit.ingame.ingame_outcome_label import (
            MlbOutcomeResolver, _KALSHI_TO_ESPN)
        _res = MlbOutcomeResolver()
        valid = (_res._abbrs | set(_KALSHI_TO_ESPN.keys())) if _res.available else set()
    except Exception:  # noqa: BLE001
        valid = set()
    for p in files:
        try:
            rows = _lg._load_pairs(Path(p))
            gid = str(rows[0].get("game_id")) if rows else Path(p).stem
        except Exception:  # noqa: BLE001
            gid = Path(p).stem
        idx: Optional[int] = None
        if str(sport).lower() == "mlb" and valid:
            from scripts.platformkit.ingame.ingame_outcome_label import parse_mlb_ticker
            parsed = parse_mlb_ticker(gid, valid)
            if parsed is not None:
                idx = parsed[0].day % n
        if idx is None:
            # DETERMINISTIC fallback (builtin hash() is per-process randomized -> would make
            # the corpus split -- and thus the verdict -- non-reproducible run to run).
            import hashlib
            idx = int(hashlib.md5(gid.encode("utf-8")).hexdigest(), 16) % n
        buckets[idx].append(Path(p))
    return buckets


def _classify(per_corpus: List[str]) -> str:
    """TRUSTED / ADVERSE / NEUTRAL from the per-corpus verdict list."""
    ruling = [v for v in per_corpus if v not in ("INSUFFICIENT_DATA", None, "")]
    if len(ruling) < MIN_CORPORA:
        return _NEUTRAL
    if all(v == "BETTER_THAN_VENUE" for v in ruling):
        return _TRUSTED
    if all(v == "WORSE_THAN_VENUE" for v in ruling):
        return _ADVERSE
    return _NEUTRAL


def build_trust(*, sport: str = "mlb", grade_dir: Optional[Path] = None,
                paths: Optional[Sequence[Path]] = None,
                outcome_fn: Optional[Callable[[str], Optional[int]]] = None,
                n_corpora: int = N_CORPORA) -> Dict[str, Any]:
    """Compute the cross-corpus segment trust map for *sport*. NEVER raises."""
    try:
        files = list(paths) if paths is not None else _seg._discover(grade_dir, sport)
        ofn = outcome_fn
        if ofn is None:
            from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
            res = MlbOutcomeResolver()
            ofn = res.home_win if res.available else (lambda _g: None)
        corpora = _split_corpora(files, sport, n_corpora)
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
            segments[seg] = {"trust": _classify(pc), "per_corpus": pc}
        trusted = [s for s, v in segments.items() if v["trust"] == _TRUSTED]
        adverse = [s for s, v in segments.items() if v["trust"] == _ADVERSE]
        return {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": COMPONENT, "sport": sport, "n_corpora": len(corpora),
            "corpus_labeled": [d.get("n_labeled", 0) for d in docs],
            "segments": segments, "trusted": trusted, "adverse": adverse,
            "enabled": is_enabled(), "units": "brier", "edge_claimed": False,
            "note": ("cross-corpus (independent date-split) replicated segment trust: a "
                     "segment is TRUSTED/ADVERSE only if BETTER/WORSE_THAN_VENUE in EVERY "
                     "non-insufficient corpus. ADVERSE -> strict floor (suppress). NEUTRAL "
                     "-> unchanged. No $ edge; venue = thin Kalshi in-play quote."),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_trust(%s) failed: %s", sport, exc)
        return {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "component": COMPONENT, "sport": sport, "segments": {},
                "trusted": [], "adverse": [], "enabled": is_enabled(),
                "error": type(exc).__name__, "edge_claimed": False}


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else TRUST_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)


def _load_trust_map(sport: str, path: Optional[Path] = None) -> Dict[str, str]:
    """Read the persisted trust map (seg -> trust) for *sport*. Cached by (path, mtime)."""
    p = Path(path) if path is not None else TRUST_PATH
    try:
        if not p.is_file():
            return {}
        key = "%s|%s" % (p, p.stat().st_mtime_ns)
        if _CACHE.get("key") == key:
            return _CACHE["map"]
        doc = json.loads(p.read_text(encoding="ascii"))
        if str(doc.get("sport")) != str(sport):
            return {}
        mp = {s: str(v.get("trust")) for s, v in (doc.get("segments") or {}).items()}
        _CACHE["key"], _CACHE["map"] = key, mp
        return mp
    except Exception as exc:  # noqa: BLE001 -- unreadable trust file -> permissive (no map)
        logger.debug("_load_trust_map failed: %s", exc)
        return {}


def _segment_of(sport: str, state: Dict[str, Any]) -> str:
    """Segment label (I1..I9/H1/H2/UNK) for a live state. Never raises."""
    try:
        return _seg._infer_segment(str(sport or ""), _lg._state_summary(state or {}))
    except Exception:  # noqa: BLE001
        return "UNK"


def floor_for_segment(sport: str, segment_or_state: Any, relaxed_floor: Any, *,
                      path: Optional[Path] = None) -> Any:
    """Return the EV floor to apply for a tick's segment (do-no-harm; never raises).

    ADVERSE (cross-corpus proven worse-than-venue) -> None (strict policy floor = suppress
    the relaxed marginal bets).  Everything else -> *relaxed_floor* unchanged.  Disabled or
    any error -> *relaxed_floor* (permissive).  *segment_or_state* may be a segment label
    string or a live-state dict (from which the segment is inferred)."""
    try:
        if not is_enabled():
            return relaxed_floor
        seg = segment_or_state if isinstance(segment_or_state, str) \
            else _segment_of(sport, segment_or_state)
        trust = _load_trust_map(sport, path).get(seg)
        if trust == _ADVERSE:
            return None  # strict pre-registered floor -> suppress marginal in this segment
        return relaxed_floor
    except Exception as exc:  # noqa: BLE001
        logger.debug("floor_for_segment(%s) failed: %s", sport, exc)
        return relaxed_floor


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 70,
         "IN-GAME SEGMENT TRUST (%s) -- cross-corpus replicated; enabled=%s"
         % (doc.get("sport", "?"), doc.get("enabled")),
         "corpus_labeled=%s" % (doc.get("corpus_labeled"),),
         "%-5s %-9s %s" % ("SEG", "TRUST", "per_corpus")]
    for seg, v in (doc.get("segments") or {}).items():
        L.append("%-5s %-9s %s" % (seg, v.get("trust"), v.get("per_corpus")))
    L.append("-" * 70)
    L.append("TRUSTED (relaxed-ok): %s" % (doc.get("trusted") or "none"))
    L.append("ADVERSE (suppress) : %s" % (doc.get("adverse") or "none"))
    L.append("NOTE: acts ONLY on cross-corpus proof; no $ edge; venue=thin Kalshi in-play.")
    L.append("=" * 70)
    return "\n".join(L)


def run(*, interval_sec: float = 1800.0, sport: str = "mlb",
        path: Optional[Path] = None, sleep: Optional[Callable[[float], None]] = None,
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
            doc = build_trust(sport=sport)
            write_doc(doc, path)
            print("%s | tick=%d trusted=%s adverse=%s" % (
                COMPONENT, ticks, doc.get("trusted"), doc.get("adverse")), flush=True)
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
    ap = argparse.ArgumentParser(prog="ingame_segment_trust")
    ap.add_argument("--sport", default="mlb")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--interval", type=float, default=None)
    a = ap.parse_args(argv)
    if a.interval is not None:
        print("%s | started interval=%ss sport=%s" % (COMPONENT, a.interval, a.sport),
              flush=True)
        run(interval_sec=a.interval, sport=a.sport)
        return 0
    doc = build_trust(sport=a.sport)
    if not a.no_write:
        write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TRUST_PATH", "COMPONENT", "ENV_FLAG", "is_enabled", "build_trust", "write_doc",
    "floor_for_segment", "render", "run",
]
