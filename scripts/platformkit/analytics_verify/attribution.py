"""Claim attribution: join settled predictions back to the claims/cards that
licensed them, roll up per-claim-family realized performance.

CALIBRATION / CLV ONLY -- never dollars, ROI, or edge. Every output carries
edge_claimed=false.

Data reality (2026-07-15): graded/clv ledgers share zero event_ids and no
card's claim_tags condition has ever fired, so there is no id-join. Linkage
is therefore: (1) claim_tags -- a card tag that FIRED -> "licensed"; (2)
condition_match(candidate) -- screened against a claim_tags set but none
fired -> lower-confidence per-card link; (3) condition_match(scope) --
fallback on the bet's scope matching a card family.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GRADED = ROOT / "data/frontend/paper_predictions_graded.jsonl"
CLV = ROOT / "data/frontend/clv_ledger.jsonl"
INGAME = ROOT / "data/frontend/ingame_realized_clv.jsonl"
CARDS = ROOT / "data/cache/claims/cards.jsonl"
OUT_DIR = ROOT / "data/cache/analytics_verify"
LEDGER = OUT_DIR / "attribution_ledger.jsonl"
ROLLUP = OUT_DIR / "attribution_rollup.json"

HONEST_NOTE = (
    "Calibration/CLV attribution only; edge_claimed=false. paper_predictions_"
    "graded settled bets carry no claim linkage and null clv; clv_ledger holds "
    "the CLV + claim_tags but shares zero event_ids with graded and no card "
    "condition fired in any tagged bet. link_method mix is reported honestly."
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def iter_jsonl(path: Path):
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


def _scope(rec: dict) -> str:
    # ponytail: coarse scope heuristic -- refine if a real scope field appears.
    hay = " ".join(
        str(rec.get(k, "")) for k in ("channel", "market_type", "market", "tier")
    ).lower()
    return "ingame" if "ingame" in hay or "in_play" in hay or "live" in hay else "pregame"


def _fnum(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _norm(r: dict, source: str) -> dict:
    """graded and clv ledgers use different field names for the same concept;
    normalize both to one shape."""
    if source == "graded":
        pred_key = r.get("pred_key"); key = pred_key or r.get("event_id")
        market, side = r.get("group") or r.get("market"), r.get("selection") or r.get("side")
    else:
        pred_key = None
        key = r.get("bet_id") or r.get("event_id")
        market, side = r.get("market") or r.get("market_type"), r.get("side")
    return {
        "key": key, "pred_key": pred_key, "bet_id": r.get("bet_id"),
        "event_id": r.get("event_id"), "sport": r.get("sport"),
        "market": market, "side": side, "scope": _scope(r),
        "outcome": r.get("outcome"), "unit_result": _fnum(r.get("unit_result")),
        "clv_pct": _fnum(r.get("clv_pct")), "clv_is_proxy": bool(r.get("clv_is_proxy")),
        "settled_at": r.get("settled_at"), "claim_tags": r.get("claim_tags") or None,
        "source": source,
    }


def load_settled(graded=GRADED, clv=CLV):
    """Yield normalized settled bets from both ledgers (they are disjoint)."""
    for path, source in ((graded, "graded"), (clv, "clv")):
        for r in iter_jsonl(path):
            if r.get("status") in ("settled", "graded"):
                yield _norm(r, source)


def build_card_index(wanted: set, cards=CARDS) -> dict:
    """Look up scope/window for referenced card_ids only (cards.jsonl is 31MB)."""
    idx = {}
    if not wanted:
        return idx
    for r in iter_jsonl(cards):
        cid = r.get("card_id")
        if cid in wanted:
            cond = r.get("condition") or {}
            sc = cond.get("scope") or "unknown"
            win = cond.get("window") or "na"
            idx[cid] = {"scope": sc, "window": win, "family": f"{sc}:{win}"}
            if len(idx) == len(wanted):
                break
    return idx


def load_ingame_clv(path=INGAME) -> dict:
    out = {}
    for r in iter_jsonl(path):
        bid = r.get("bet_id")
        if bid:
            out[bid] = r
    return out


def _best_ingame_clv(rec: dict):
    for k in ("ingame_realized_clv_300s", "ingame_realized_clv_120s",
              "ingame_realized_clv_30s"):
        v = _fnum(rec.get(k))
        if v is not None:
            return v
    return None


def _tag_map(tags) -> dict:
    """Normalize claim_tags to {card_id: fired_bool}: dict-of-bool (real
    ledgers) as-is, or a bare list/tuple of fired card_ids -> all-fired."""
    if isinstance(tags, dict):
        return tags
    return {cid: True for cid in tags} if isinstance(tags, (list, tuple)) else {}


def attribute(bets, card_index, ingame_idx):
    """One row per (bet, claim/card) link."""
    now = utcnow()
    for b in bets:
        # ingame enrichment overrides clv when a bet_id match exists.
        clv = b["clv_pct"]
        proxy = b["clv_is_proxy"]
        ig = ingame_idx.get(b["bet_id"]) if b["bet_id"] else None
        if ig is not None:
            v = _best_ingame_clv(ig)
            if v is not None:
                clv, proxy = v, False
        base = {
            "pred_key": b["pred_key"], "bet_id": b["bet_id"],
            "event_id": b["event_id"], "sport": b["sport"],
            "market": b["market"], "clv_pct": clv, "clv_is_proxy": proxy,
            "unit_result": b["unit_result"], "outcome": b["outcome"],
            "settled_at": b["settled_at"], "attributed_at": now,
            "edge_claimed": False,
        }
        tags = _tag_map(b["claim_tags"])
        if tags:
            for cid, fired in tags.items():
                fam = card_index.get(cid, {}).get("family", "unknown")
                yield {**base, "card_id": cid, "claim_family": fam,
                       "link_method": "claim_tags" if fired else "condition_match",
                       "confidence": 1.0 if fired else 0.5}
        else:
            yield {**base, "card_id": None,
                   "claim_family": f"scope:{b['scope']}",
                   "link_method": "condition_match", "confidence": 0.2}


def existing_keys(path=LEDGER) -> set:
    seen = set()
    for r in iter_jsonl(path):
        seen.add((r.get("pred_key") or r.get("bet_id"), r.get("card_id")))
    return seen


def append_ledger(rows, path=LEDGER):
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = existing_keys(path)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            k = (r.get("pred_key") or r.get("bet_id"), r.get("card_id"))
            if k in seen:
                continue
            seen.add(k)
            fh.write(json.dumps(r) + "\n")
            n += 1
    return n


def _agg(rows):
    clvs = [r["clv_pct"] for r in rows if r.get("clv_pct") is not None]
    keys = {(r.get("pred_key") or r.get("bet_id")) for r in rows}
    return {
        "n_bets": len(keys),
        "n_settled": sum(1 for r in rows if r.get("outcome")),
        "mean_clv_pct": round(statistics.fmean(clvs), 4) if clvs else None,
        "median_clv_pct": round(statistics.median(clvs), 4) if clvs else None,
        "pct_beat_close": round(sum(c > 0 for c in clvs) / len(clvs), 4) if clvs else None,
        "flat_units_result": round(
            sum(r["unit_result"] for r in rows if r.get("unit_result") is not None), 4),
        "n_proxy_close": sum(1 for r in rows if r.get("clv_is_proxy")),
    }


def build_rollup(ledger=LEDGER, join_rates=None) -> dict:
    rows = list(iter_jsonl(ledger))
    by_family = defaultdict(list)
    by_card = defaultdict(list)
    mix = Counter()
    for r in rows:
        by_family[r.get("claim_family", "unknown")].append(r)
        if r.get("card_id"):
            by_card[r["card_id"]].append(r)
        mix[r.get("link_method", "unknown")] += 1
    fam = {k: _agg(v) for k, v in by_family.items()}
    card = {k: _agg(v) for k, v in by_card.items()}
    ranked = sorted(
        ((k, v["median_clv_pct"]) for k, v in fam.items() if v["median_clv_pct"] is not None),
        key=lambda x: x[1])
    return {
        "generated_at": utcnow(), "edge_claimed": False, "honest_note": HONEST_NOTE,
        "n_attribution_rows": len(rows),
        "link_method_mix": dict(mix), "join_rates": join_rates or {},
        "by_family": fam, "by_card": card,
        "top_decayed": [k for k, _ in ranked[:5]],
        "top_holding": [k for k, _ in reversed(ranked[-5:])],
    }


def compute_join_rates(graded=GRADED, clv=CLV, ingame=INGAME, limit=None) -> dict:
    def _ids(p, field):
        s = set()
        for i, r in enumerate(iter_jsonl(p)):
            if limit and i >= limit:
                break
            if r.get(field):
                s.add(str(r[field]))
        return s

    g_e, c_e = _ids(graded, "event_id"), _ids(clv, "event_id")
    c_b, i_b = _ids(clv, "bet_id"), _ids(ingame, "bet_id")
    return {
        "graded_clv_event_overlap": round(len(g_e & c_e) / len(g_e), 4) if g_e else None,
        "clv_ingame_bet_overlap": round(len(c_b & i_b) / len(c_b), 4) if c_b else None,
    }


def atomic_write_json(obj, path=ROLLUP):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def run(graded=GRADED, clv=CLV, ingame=INGAME, cards=CARDS,
        ledger=LEDGER, rollup=ROLLUP):
    bets = list(load_settled(graded, clv))
    wanted = set()
    for b in bets:
        if isinstance(b["claim_tags"], dict):
            wanted |= set(b["claim_tags"].keys())
    card_index = build_card_index(wanted, cards)
    ingame_idx = load_ingame_clv(ingame)
    rows = list(attribute(bets, card_index, ingame_idx))
    appended = append_ledger(rows, ledger)
    jr = compute_join_rates(graded, clv, ingame)
    snap = build_rollup(ledger, jr)
    atomic_write_json(snap, rollup)
    return {"settled_bets": len(bets), "rows_generated": len(rows),
            "rows_appended": appended, "families": len(snap["by_family"]),
            "cards": len(snap["by_card"]), "join_rates": jr,
            "link_method_mix": snap["link_method_mix"]}


def main():
    ap = argparse.ArgumentParser(description="claim attribution ledger + rollup")
    ap.add_argument("--graded", type=Path, default=GRADED)
    ap.add_argument("--clv", type=Path, default=CLV)
    ap.add_argument("--ingame", type=Path, default=INGAME)
    ap.add_argument("--cards", type=Path, default=CARDS)
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--rollup", type=Path, default=ROLLUP)
    a = ap.parse_args()
    res = run(a.graded, a.clv, a.ingame, a.cards, a.ledger, a.rollup)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
