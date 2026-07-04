"""scripts.platformkit.ingame.ingame_unk_backfill_verdict -- LANE 5: RAW-vs-
BACKFILLED outcome-gated Brier verdict for soccer_intl's 22 UNK-bucket games.

WHY A SEPARATE MODULE (never edits ingame_outcome_verdict.py / _multi.py)
--------------------------------------------------------------------------
ingame_outcome_verdict._brier_by_game_segment calls _infer_segment(sport,
state_summary) with no ts/game_id context, so it cannot consume the
tick_segment_backfill sidecar without a shared-code change to a file MLB's
live verdict path also depends on. This module instead recomputes per-game
Brier DIRECTLY for soccer_intl's UNK-bucket games only, in two variants:

  RAW        : every UNK-bucket tick stays segment "UNK" (today's baseline).
  BACKFILLED : a tick gets its sidecar H1/H2 label if tick_segment_backfill.py
               resolved one for it; ticks the sidecar excluded (ambiguous
               boundary) OR that have no sidecar entry stay "UNK".

Both variants reuse ingame_outcome_verdict's own per-segment verdict math
(_seg_verdict / _ci_delta) so the BEAT/MATCH/WORSE thresholds and bootstrap CI
are identical to the shared path -- only the segment LABEL SOURCE differs.

HONESTY: this NEVER claims the backfilled labels are as trustworthy as a real
game-clock capture -- every backfilled-variant doc carries
segment_source="backfilled" plus the buffer_min / excluded-tick count, so a
reader can never mistake it for a raw game-clock verdict. No $ field;
edge_claimed always False.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no data/registry write; never
mutates raw capture files or the shared ingame_outcome_verdict module; never
raises out of its public entrypoints.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_unk_backfill_verdict.py -q
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame import ingame_outcome_verdict as _ov
from scripts.platformkit.ingame import tick_segment_backfill as _tsb

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_unk_backfill_verdict.json"
COMPONENT = "m_ingame_unk_backfill_verdict"
SPORT = "soccer_intl"

OutcomeFn = Callable[[str], Optional[int]]


def _default_outcome_fn() -> OutcomeFn:
    try:
        from scripts.platformkit.ingame.soccer_outcome import SoccerOutcomeResolver
        res = SoccerOutcomeResolver()
    except Exception as exc:  # noqa: BLE001
        logger.debug("_default_outcome_fn init failed: %s", exc)
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
        return None if hs == as_ else int(hs > as_)
    return _fn


def _segment_for_tick(ticker: str, row: Dict[str, Any], sidecar: Optional[Dict[str, Any]],
                      variant: str) -> str:
    """'UNK' for the raw variant; sidecar H1/H2 (if resolved) else 'UNK' for backfilled."""
    if variant == "raw" or sidecar is None:
        return "UNK"
    ts = str(row.get("ts", ""))
    lab = _tsb.lookup_segment(sidecar, ticker, ts)
    return lab if lab is not None else "UNK"


def _brier_by_segment_for_games(
    games: Dict[str, List[dict]], outcome_fn: OutcomeFn, sidecar: Optional[Dict[str, Any]],
    variant: str,
) -> Tuple[Dict[str, Dict[str, Tuple[float, float, int]]], int]:
    """seg -> {game_id: (sse_model, sse_market, n_ticks)} for *games* only,
    labeling each tick per *variant* ('raw' or 'backfilled'). Returns
    (per_segment_map, n_labeled_games). Never raises."""
    per: Dict[str, Dict[str, Tuple[float, float, int]]] = defaultdict(dict)
    n_labeled = 0
    for ticker, rows in games.items():
        try:
            y = outcome_fn(ticker)
        except Exception:  # noqa: BLE001
            y = None
        if y is None:
            continue
        n_labeled += 1
        acc: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        for r in rows:
            mp, kp = r.get("model_prob"), r.get("market_prob")
            if mp is None or kp is None:
                continue
            seg = _segment_for_tick(ticker, r, sidecar, variant)
            a = acc[seg]
            a[0] += (float(mp) - y) ** 2
            a[1] += (float(kp) - y) ** 2
            a[2] += 1
        for seg, a in acc.items():
            if a[2] > 0:
                per[seg][ticker] = (a[0], a[1], int(a[2]))
    return per, n_labeled


def _build_variant_doc(games: Dict[str, List[dict]], outcome_fn: OutcomeFn,
                       sidecar: Optional[Dict[str, Any]], variant: str, *,
                       eps: float = _ov.EPS_DEFAULT,
                       min_games: int = _ov.MIN_GAMES_PER_SEG,
                       min_ticks: int = _ov.MIN_TICKS_PER_SEG) -> Dict[str, Any]:
    per, n_labeled = _brier_by_segment_for_games(games, outcome_fn, sidecar, variant)
    order = ["H1", "H2", "UNK"] if variant == "backfilled" else ["UNK"]
    order += sorted(s for s in per if s not in order)
    segments = {seg: _ov._seg_verdict(per.get(seg, {}), eps=eps, min_games=min_games,
                                       min_ticks=min_ticks) for seg in order}
    better = [s for s, v in segments.items() if v["verdict"] == "BETTER_THAN_VENUE"]
    worse = [s for s, v in segments.items() if v["verdict"] == "WORSE_THAN_VENUE"]
    return {
        "variant": variant, "n_games": len(games), "n_labeled": n_labeled,
        "segment_order": order, "segments": segments,
        "better_segments": better, "worse_segments": worse,
        "units": "brier", "edge_claimed": False,
    }


def build_verdict(grade_dir: Optional[Path] = None, sidecar_path: Optional[Path] = None,
                  outcome_fn: Optional[OutcomeFn] = None) -> Dict[str, Any]:
    """RAW-vs-BACKFILLED verdict doc for soccer_intl's UNK-bucket games. Never raises."""
    try:
        games = _tsb.find_unk_games(grade_dir)
        sidecar = _tsb.load_sidecar(sidecar_path)
        ofn = outcome_fn if outcome_fn is not None else _default_outcome_fn()
        raw_doc = _build_variant_doc(games, ofn, None, "raw")
        if sidecar is not None:
            backfilled_doc = _build_variant_doc(games, ofn, sidecar, "backfilled")
        else:
            backfilled_doc = {"variant": "backfilled", "n_games": len(games),
                              "n_labeled": 0, "segment_order": [], "segments": {},
                              "better_segments": [], "worse_segments": [],
                              "units": "brier", "edge_claimed": False,
                              "note": "no sidecar on disk -- run tick_segment_backfill first"}
        return {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": COMPONENT, "sport": SPORT,
            "n_unk_games_on_disk": len(games),
            "sidecar_present": sidecar is not None,
            "sidecar_buffer_min": (sidecar or {}).get("buffer_min"),
            "raw": raw_doc, "backfilled": backfilled_doc,
            "units": "brier", "edge_claimed": False,
            "note": ("RAW keeps every UNK-bucket tick in segment 'UNK' (today's "
                     "baseline). BACKFILLED re-splits ticks into H1/H2 using the "
                     "kickoff-derived tick_segment_backfill sidecar; ticks the "
                     "sidecar excluded as boundary-ambiguous (or lacking a sidecar "
                     "entry) stay 'UNK' in the backfilled variant too. Neither "
                     "variant is an edge/$ claim; BETTER/WORSE_THAN_VENUE means "
                     "better/worse-calibrated Brier vs the venue's own in-play "
                     "quote, never an efficient-close beat."),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_verdict failed: %s", exc)
        return {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "component": COMPONENT, "sport": SPORT, "error": type(exc).__name__,
                "edge_claimed": False}


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> Path:
    p = Path(path) if path is not None else OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(p)
    return p


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 74, "UNK-BUCKET BACKFILL VERDICT -- soccer_intl (raw vs backfilled)"]
    for variant in ("raw", "backfilled"):
        d = doc.get(variant) or {}
        L.append("-" * 74)
        L.append("VARIANT=%s n_games=%d n_labeled=%d" % (
            variant, d.get("n_games", 0), d.get("n_labeled", 0)))
        for seg in d.get("segment_order", []):
            v = (d.get("segments") or {}).get(seg)
            if not v:
                continue
            L.append("  %-5s %-18s games=%-4d ticks=%-6d delta=%s" % (
                seg, v["verdict"], v.get("n_games", 0), v.get("total_ticks", 0),
                "n/a" if v.get("brier_delta") is None else "%+.4f" % v["brier_delta"]))
    L.append("=" * 74)
    L.append("NOTE: neither variant is a $/edge claim; Brier/probability space only.")
    L.append("=" * 74)
    return "\n".join(L)


def main() -> int:
    doc = build_verdict()
    write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "COMPONENT", "SPORT", "build_verdict", "write_doc", "render",
]
