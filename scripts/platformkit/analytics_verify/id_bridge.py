"""scripts.platformkit.analytics_verify.id_bridge -- offline join spine that
unifies the two independent settled-bet ledgers.

Measured reality (2026-07-15): paper_predictions_graded.jsonl (pred_key) and
clv_ledger.jsonl (bet_id) share ZERO event_ids, so a bet placed and a prediction
graded on the SAME game never joined. Both writers now stamp a canonical event
key `ckey` (sport|date|home|away|market_family via make_event_key) on NEW rows;
this module BACKFILLS the same ckey for EXISTING rows (which predate the stamp)
by recomputing it from each row's own fields, then emits the graded<->clv link.

Honest: ckey is event+market granularity, not bet granularity, and the two
histories genuinely cover different bets -- so the backfill join rate is reported
as-measured, never forced. edge_claimed=false on every row.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; UTC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/analytics_verify/test_id_bridge.py -q
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from scripts.platformkit.clv_ledger import event_ckey as _event_ckey

ROOT = Path(__file__).resolve().parents[3]
GRADED = ROOT / "data/frontend/paper_predictions_graded.jsonl"
CLV = ROOT / "data/frontend/clv_ledger.jsonl"
OUT_DIR = ROOT / "data/cache/analytics_verify"
BRIDGE = OUT_DIR / "id_bridge.jsonl"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def row_ckey(row: Dict[str, Any], source: str) -> Optional[str]:
    """Canonical event key for one ledger row. Prefers the stamped `ckey` (new
    rows); recomputes from the row's own fields for pre-stamp history using the
    SAME make_event_key path both writers use, so backfilled and stamped keys are
    identical. `source` is 'graded' or 'clv'."""
    ck = row.get("ckey")
    if ck:
        return str(ck)
    if source == "graded":  # normalize graded fields onto the clv record shape
        return _event_ckey({
            "sport": row.get("sport"), "matchup": row.get("matchup"),
            "market": row.get("group"),
            "game_date": str(row.get("commence_time")
                             or row.get("logged_at") or "")[:10],
        })
    return _event_ckey(row)


def _clv_index(clv_path: Path) -> Dict[str, List[str]]:
    """ckey -> list of clv bet_ids (any row carrying a bet_id)."""
    idx: Dict[str, List[str]] = {}
    for r in iter_jsonl(clv_path):
        bid = r.get("bet_id")
        if not bid:
            continue
        ck = row_ckey(r, "clv")
        if not ck:
            continue
        idx.setdefault(ck, [])
        if bid not in idx[ck]:
            idx[ck].append(str(bid))
    return idx


def _existing(path: Path) -> set:
    """Idempotency set of (pred_key, bet_id) already bridged."""
    seen = set()
    for r in iter_jsonl(path):
        seen.add((r.get("pred_key"), r.get("bet_id")))
    return seen


def build(graded: Path = GRADED, clv: Path = CLV, out: Path = BRIDGE
          ) -> Dict[str, Any]:
    """Backfill the graded<->clv join. Streams both ledgers, keys each row by
    ckey, links every settled graded prediction to the clv bet(s) on the same
    event+market, and appends bridge rows (idempotent). Returns the honest join
    rate = settled graded rows matched to >=1 clv bet / all settled graded rows.
    """
    clv_idx = _clv_index(clv)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = _existing(out)
    now = utcnow()

    n_graded = n_matched = n_appended = 0
    n_backfilled = 0  # rows whose ckey was recomputed (not stamped)
    bmap: Dict[Any, Any] = {}  # pred_key -> first bet_id, same shape apply_bridge_join wants
    with out.open("a", encoding="utf-8") as fh:
        for r in iter_jsonl(graded):
            if r.get("status") not in ("settled", "graded"):
                continue
            n_graded += 1
            pk = r.get("pred_key")
            stamped = bool(r.get("ckey"))
            ck = row_ckey(r, "graded")
            if not ck:
                continue
            if not stamped:
                n_backfilled += 1
            bids = clv_idx.get(ck)
            if not bids:
                continue
            n_matched += 1
            if pk and pk not in bmap:
                bmap[pk] = bids[0]
            for bid in bids:
                if (pk, bid) in seen:
                    continue
                seen.add((pk, bid))
                # confidence: 1.0 when BOTH sides carried a stamped ckey (exact
                # new-row join), 0.7 when either was recomputed from history.
                conf = 1.0 if stamped else 0.7
                fh.write(json.dumps({
                    "pred_key": pk, "bet_id": bid, "ckey": ck,
                    "match_basis": "ckey" if stamped else "ckey_backfill",
                    "confidence": conf, "built_at": now, "edge_claimed": False,
                }) + "\n")
                n_appended += 1

    join_rate = round(n_matched / n_graded, 4) if n_graded else None
    return {
        "graded_settled": n_graded, "graded_matched": n_matched,
        "join_rate": join_rate, "rows_appended": n_appended,
        "ckey_backfilled": n_backfilled, "clv_ckeys": len(clv_idx),
        "bridge_path": str(out), "edge_claimed": False,
        "bmap": bmap,  # this call's pred_key->bet_id map, reusable by apply_bridge_join
    }


def apply_bridge_join(bets: List[Dict[str, Any]], bridge: Path = BRIDGE,
                       bmap: Optional[Dict[Any, Any]] = None
                      ) -> Optional[float]:
    """Enrich normalized attribution *bets* in place using the ckey bridge: a
    graded bet whose pred_key is bridged to a clv bet_id inherits that clv row's
    claim_tags + CLV (graded rows carry neither) and is stamped _ckey_bet_id so
    the caller can link it at bet/ckey grain. Returns the honest fraction of
    graded bets that gained a ckey join. Shared here so attribution stays <=300.

    bmap, if given (e.g. build()'s own return value), is used as-is instead of
    re-reading the bridge file -- callers that already built() in the same run
    skip a redundant full scan. Default (None) reads *bridge* from disk."""
    if bmap is None:
        bmap = {}
        for r in iter_jsonl(bridge):
            pk = r.get("pred_key")
            if pk and pk not in bmap:
                bmap[pk] = r.get("bet_id")
    clv_by_bet = {b["bet_id"]: b for b in bets
                  if b.get("source") == "clv" and b.get("bet_id")}
    n_graded = n_joined = 0
    for b in bets:
        if b.get("source") != "graded":
            continue
        n_graded += 1
        src = clv_by_bet.get(bmap.get(b.get("pred_key")))
        if src is None:
            continue
        n_joined += 1
        b["_ckey_bet_id"] = src["bet_id"]
        if not b.get("claim_tags"):
            b["claim_tags"] = src.get("claim_tags")
        if b.get("clv_pct") is None:
            b["clv_pct"], b["clv_is_proxy"] = src.get("clv_pct"), src.get("clv_is_proxy")
    return round(n_joined / n_graded, 4) if n_graded else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill graded<->clv ckey join bridge.")
    ap.add_argument("--graded", type=Path, default=GRADED)
    ap.add_argument("--clv", type=Path, default=CLV)
    ap.add_argument("--out", type=Path, default=BRIDGE)
    a = ap.parse_args()
    print(json.dumps(build(a.graded, a.clv, a.out), indent=2))


if __name__ == "__main__":
    main()
