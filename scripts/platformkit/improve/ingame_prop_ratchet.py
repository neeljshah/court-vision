"""scripts.platformkit.improve.ingame_prop_ratchet -- the IN-GAME prop calibration ratchet.

The in-game twin of prop_calibration_ratchet. That ratchet folds ALL settled props
(pregame + in-game mixed) into ONE per-sport verdict; this one isolates the IN-GAME rows
(ingame=True) and BUCKETS them by frac_elapsed, because a live prop's calibration is
conditional on how much of the game has elapsed -- an "early" re-price (little realized
state) is a different forecaster than a "late" one (most state already known). This is the
PROP-channel analogue of the game-level margin x period x time segment recal (which scores
win-prob, not player props), filling the gap the in-game prop placer leaves: it ranks on
tier + EV with NO calibration evidence behind it.

Each (sport, frac_bucket) group is scored through the SAME leak-free eval-gate as the
pregame prop ratchet (walk-forward isotonic recal + planted-null + market-shrink do-no-harm),
reusing prop_calibration_ratchet.improve_cycle on the curated subset. Verdict per bucket:
SHIP / HOLD / REJECT / INSUFFICIENT_DATA. Writes a gate read-surface
(data/frontend/ingame_prop_meta.json) the placer can consult to SUPPRESS buckets whose
calibration is untrustworthy (REJECT) -- a ratchet that can only ever HOLD or REMOVE bad
bets, never arm new ones.

HONESTY (binding): calibration != edge (no $ claim). In-game props have no true close;
p_market is the contemporaneous LIVE two-way line (available at bet time -> no leak), used
ONLY for the do-no-harm shrink control. PROPOSE/RECORD only: writes the meta + tagged
verdicts, NEVER flips a flag / arms serving / writes data/registry/. <=300 LOC; ASCII.
CLI: python -m scripts.platformkit.improve.ingame_prop_ratchet
Per-file test: tests/platformkit/improve/test_ingame_prop_ratchet.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.recalibration import CALIBRATION_NOTE
from scripts.platformkit.self_improve import (
    _read_jsonl, _outcome_to_binary, _raw_prob, _append, DEFAULT_CLV_LEDGER,
)
from scripts.platformkit.improve.prop_calibration_ratchet import (
    improve_cycle, DEFAULT_PROP_LEDGER,
)

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
DEFAULT_META_PATH = _REPO / "data" / "frontend" / "ingame_prop_meta.json"

# Sports whose IN-GAME props can settle today (mirrors the live trader's ticked sports).
INGAME_SPORTS = ("mlb", "soccer_intl")

# frac_elapsed -> bucket. Coarse on purpose: settled in-game props fragment fast and a
# real leak-free cycle needs >= MIN_RECAL_GAMES per group (else INSUFFICIENT_DATA, honest).
BUCKETS: Tuple[Tuple[str, float, float], ...] = (
    ("early", 0.0, 0.34),
    ("mid", 0.34, 0.67),
    ("late", 0.67, 1.01),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def bucket_for(frac: Any) -> Optional[str]:
    """frac_elapsed -> bucket label, or None if out of range / not a number."""
    try:
        f = float(frac)
    except (TypeError, ValueError):
        return None
    for name, lo, hi in BUCKETS:
        if lo <= f < hi:
            return name
    return None


def load_settled_ingame_props(sport: str,
                              clv_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Settled IN-GAME prop rows for one sport, each carrying its frac + bucket.

    Like prop_calibration_ratchet.load_settled_props but keeps ONLY ingame=True rows and
    additionally stamps 'frac'/'bucket'. p_raw=model_prob (picked side), y=win/loss (push
    dropped), p_market=devigged LIVE two-way prob. Deduped + chronological (leak-free WF)."""
    clv_path = Path(clv_path) if clv_path else DEFAULT_CLV_LEDGER
    raw = _read_jsonl(clv_path)
    sp = str(sport).lower()
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in raw:
        if str(r.get("sport", "")).lower() != sp:
            continue
        if str(r.get("market_type") or "") != "prop":
            continue
        if r.get("ingame") is not True:
            continue
        if str(r.get("status") or "") != "settled":
            continue
        y = _outcome_to_binary(r)   # win=1 / loss=0 / push->None
        p = _raw_prob(r)            # model_prob (picked side)
        if y is None or p is None:
            continue
        bk = bucket_for(r.get("frac_elapsed"))
        if bk is None:
            continue
        ts = str(r.get("settled_at") or r.get("ts") or "")
        key = (str(r.get("bet_id") or r.get("market") or ""), ts)
        if key in seen:
            continue
        seen.add(key)
        mp = r.get("market_prob")
        out.append({
            "ts": ts,
            "market": str(r.get("market") or ""),
            "p_raw": p,
            "y": int(y),
            "p_market": float(mp) if isinstance(mp, (int, float)) else None,
            "frac": float(r.get("frac_elapsed")),
            "bucket": bk,
        })
    out.sort(key=lambda d: d["ts"])
    return out


def improve_bucket(sport: str, bucket: str, settled: Sequence[Dict[str, Any]],
                   ledger_path: Optional[Path] = None,
                   append: bool = True) -> Dict[str, Any]:
    """Score ONE (sport, bucket) group through the shared leak-free gate (reusing
    prop_calibration_ratchet.improve_cycle on the curated subset), tag with channel +
    bucket, and append the verdict to the prop_improve_ledger."""
    rows = [s for s in settled if s.get("bucket") == bucket]
    rec = improve_cycle(sport, settled=list(rows), append=False, ledger_path=ledger_path)
    rec["channel"] = "ingame"
    rec["frac_bucket"] = bucket
    if append:
        _append(Path(ledger_path) if ledger_path else DEFAULT_PROP_LEDGER, rec)
    return rec


def _group_summary(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Slim a verdict rec down to the gate read-surface row."""
    return {
        "sport": rec.get("sport"),
        "bucket": rec.get("frac_bucket"),
        "n": rec.get("n_settled", 0),
        "verdict": rec.get("verdict"),
        "baseline_brier": rec.get("baseline_brier"),
        "recal_brier": rec.get("recal_brier"),
        "delta_brier": rec.get("delta_brier"),
        "null_shipped": rec.get("null_shipped"),
    }


def improve_all_ingame(clv_path: Optional[Path] = None,
                       ledger_path: Optional[Path] = None,
                       meta_path: Optional[Path] = None,
                       append: bool = True,
                       write_meta: bool = True) -> Dict[str, Any]:
    """Run every (sport, bucket) in-game cycle; write the gate read-surface meta + return."""
    groups: List[Dict[str, Any]] = []
    results: Dict[str, Dict[str, Any]] = {}
    for sp in INGAME_SPORTS:
        settled = load_settled_ingame_props(sp, clv_path)
        for name, _lo, _hi in BUCKETS:
            rec = improve_bucket(sp, name, settled, ledger_path, append)
            results["%s|%s" % (sp, name)] = rec
            groups.append(_group_summary(rec))
    meta = {
        "schema_version": "1.0.0",
        "generated_at": _now_iso(),
        "buckets": {n: [lo, hi] for n, lo, hi in BUCKETS},
        "suppress_verdicts": ["REJECT"],
        "groups": groups,
        "note": CALIBRATION_NOTE,
    }
    meta_path = Path(meta_path) if meta_path else DEFAULT_META_PATH
    if write_meta:
        try:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(meta, ensure_ascii=True, indent=1),
                                 encoding="utf-8")
        except Exception:  # noqa: BLE001 -- meta write must never sink the loop
            pass
    return {"ts": _now_iso(), "meta": meta, "results": results, "note": CALIBRATION_NOTE}


def _main(argv: Optional[List[str]] = None) -> int:
    summary = improve_all_ingame()
    print()
    print("IN-GAME PROP CALIBRATION RATCHET -- leak-free, bucketed by frac_elapsed")
    print("NOTE: %s" % CALIBRATION_NOTE)
    print("-" * 78)
    print("%-11s%-7s%7s  %-18s%10s" % ("sport", "bucket", "n", "verdict", "d_brier"))
    print("-" * 78)
    for g in summary["meta"]["groups"]:
        db = g.get("delta_brier")
        db_s = "%+.5f" % db if isinstance(db, (int, float)) else "      --"
        print("%-11s%-7s%7d  %-18s%10s" % (
            str(g.get("sport")), str(g.get("bucket")), int(g.get("n") or 0),
            str(g.get("verdict")), db_s))
    print("-" * 78)
    print("meta: %s" % DEFAULT_META_PATH)
    print("Gate: in-game placer may SUPPRESS REJECT buckets; SHIP/HOLD/INSUFFICIENT place "
          "as today. Ratchet holds/removes only -- never arms. calibration != edge.")
    return 0


__all__ = [
    "bucket_for", "load_settled_ingame_props", "improve_bucket",
    "improve_all_ingame", "INGAME_SPORTS", "BUCKETS", "DEFAULT_META_PATH",
]


if __name__ == "__main__":
    raise SystemExit(_main())
