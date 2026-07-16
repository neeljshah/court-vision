"""Claim survival regrader -- re-score ever-VALIDATED claim cards on POST-validation evidence.

Reads (never mutates) the claims engine's own files (card_ledger.jsonl,
cards.jsonl under data/cache/claims/) and post-validation evidence
(paper_predictions_graded.jsonl, ingame_realized_clv.jsonl under
data/frontend/). For every card whose ledger verdict is terminal-positive it
collects linked outcomes settled AFTER the card's graded_at, computes a
post-validation CLV metric per horizon (7/30/60 day), and emits a regrade
verdict: HOLDS / DECAYED / INSUFFICIENT. Demotion is a PROPOSAL appended to
this module's OWN ledger, surfaced for the autoloop / human -- it never
rewrites the claims engine's files. Calibration / CLV language only. No
dollars, no ROI, no edge. Stdlib only.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.analytics_verify.regrader
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

_REPO = Path(__file__).resolve().parents[3]

# --- source (read-only) + output paths --------------------------------------
CARD_LEDGER = _REPO / "data" / "cache" / "claims" / "card_ledger.jsonl"
CARDS = _REPO / "data" / "cache" / "claims" / "cards.jsonl"
PAPER_GRADED = _REPO / "data" / "frontend" / "paper_predictions_graded.jsonl"
INGAME_CLV = _REPO / "data" / "frontend" / "ingame_realized_clv.jsonl"
OUT_DIR = _REPO / "data" / "cache" / "analytics_verify"
REGRADE_LEDGER = OUT_DIR / "regrade_ledger.jsonl"
SURVIVAL_JSON = OUT_DIR / "claim_survival.json"

# ledger verdict names that count as "ever-VALIDATED" (terminal-positive).
POSITIVE_VERDICTS = frozenset({"VALIDATED", "CONFIRMED", "HOLDS", "SHIP", "PASS"})
HORIZONS = (7, 30, 60)
MIN_N = 25
# median clv_pct below this (percentage points) at n>=min_n => DECAYED (sign-flip / materially worse).
DECAY_MARGIN = 0.0
HONEST_NOTE = (
    "Calibration/CLV re-grading of already-validated claims. No dollars, no ROI, no edge. "
    "Demotions are PROPOSALS for the autoloop/human; the claims engine files are never mutated."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(s: Any) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    t = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iter_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _median(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 4) if xs else None


# --- evidence linkage (local copy; do NOT import attribution.py) -------------
def _ingame_clv(row: dict) -> float | None:
    """Best available realized in-game CLV, densest window first."""
    for k in ("ingame_realized_clv_300s", "ingame_realized_clv_120s", "ingame_realized_clv_30s"):
        v = row.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _evidence_rows(scope: str, cards_ingame: Path, cards_pregame: Path) -> Iterator[tuple[datetime, float, dict]]:
    """Yield (settled_ts, clv_pct, row) for the evidence file matching the card scope."""
    if scope == "ingame":
        for row in _iter_jsonl(cards_ingame):
            clv = _ingame_clv(row)
            if clv is None:
                continue
            # bet_id trailing token is a YYYY-MM-DD settle date: mlb|...|...|2026-06-29
            ts = None
            bid = row.get("bet_id")
            if isinstance(bid, str):
                ts = _parse_ts(bid.rsplit("|", 1)[-1] + "T00:00:00Z")
            if ts is not None:
                yield ts, clv, row
    else:
        for row in _iter_jsonl(cards_pregame):
            clv = row.get("clv_pct")
            ts = _parse_ts(row.get("settled_at"))
            if isinstance(clv, (int, float)) and ts is not None:
                yield ts, float(clv), row


def _fired_tags(tags: Any) -> set:
    """claim_tags -> set of fired card_ids. Accepts the real dict-of-bool
    shape ({card_id: fired_bool}) or a bare list/tuple of fired card_ids."""
    if isinstance(tags, dict):
        return {k for k, v in tags.items() if v}
    return set(tags) if isinstance(tags, (list, tuple)) else set()


def _link(card: dict, graded_at: datetime, scope: str, ev_ingame: Path, ev_pregame: Path):
    """Return (link_method, [(settled_ts, clv_pct, row), ...]) for outcomes settled AFTER graded_at."""
    card_id = card.get("card_id")
    sport = (card.get("sport") or card.get("condition", {}).get("sport") or "").lower() or None

    tagged, condm = [], []
    for ts, clv, row in _evidence_rows(scope, ev_ingame, ev_pregame):
        if ts <= graded_at:
            continue
        if card_id in _fired_tags(row.get("claim_tags")):
            tagged.append((ts, clv, row))
            continue
        if sport and str(row.get("sport", "")).lower() != sport:
            continue
        condm.append((ts, clv, row))
    if tagged:
        return "claim_tags", tagged
    return "condition_match", condm


def _regrade_one(linked, graded_at: datetime, window_days: int, min_n: int, decay_margin: float):
    horizon_end = graded_at.timestamp() + window_days * 86400
    clvs = [clv for ts, clv, _ in linked if ts.timestamp() <= horizon_end]
    n = len(clvs)
    med = _median(clvs)
    pct_beat = round(sum(1 for c in clvs if c > 0) / n, 4) if n else None
    if n < min_n:
        return "INSUFFICIENT", f"n_post={n} < min_n={min_n}", n, med, pct_beat
    if med is not None and med < decay_margin:
        return "DECAYED", f"post median clv_pct {med} < {decay_margin} at n={n} (sign-flip / materially worse)", n, med, pct_beat
    return "HOLDS", f"post median clv_pct {med} >= {decay_margin}, pct_beat_close {pct_beat} at n={n}", n, med, pct_beat


def _eligible_cards(ledger: Path, cards: Path):
    """Join ledger (terminal-positive verdict) to card definitions."""
    graded: dict[str, dict] = {}
    total = 0
    for row in _iter_jsonl(ledger):
        total += 1
        cid = row.get("card_id")
        if cid and str(row.get("verdict", "")).upper() in POSITIVE_VERDICTS:
            graded[cid] = row  # last wins
    defs = {row["card_id"]: row for row in _iter_jsonl(cards) if row.get("card_id") in graded}
    elig = [(cid, graded[cid], defs.get(cid, {})) for cid in graded]
    return total, elig


def _atomic_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _existing_keys(ledger: Path) -> set[tuple]:
    """(card_id, as-of-date, window_days) already present -> idempotent skip."""
    keys = set()
    for row in _iter_jsonl(ledger):
        rt = _parse_ts(row.get("regraded_at"))
        if rt is not None:
            keys.add((row.get("card_id"), rt.date().isoformat(), row.get("window_days")))
    return keys


def run(
    ledger_path: Path = CARD_LEDGER,
    cards_path: Path = CARDS,
    ev_pregame: Path = PAPER_GRADED,
    ev_ingame: Path = INGAME_CLV,
    out_ledger: Path = REGRADE_LEDGER,
    out_survival: Path = SURVIVAL_JSON,
    min_n: int = MIN_N,
    decay_margin: float = DECAY_MARGIN,
) -> dict:
    now = _utcnow()
    as_of = now.date().isoformat()
    total_ledger, elig = _eligible_cards(ledger_path, cards_path)
    out_ledger.parent.mkdir(parents=True, exist_ok=True)
    seen = _existing_keys(out_ledger)

    verdict_counts: dict[str, int] = {}
    horizon_holds = {h: [0, 0] for h in HORIZONS}  # [holds, decided(holds+decayed)]
    decayed_cards: list[dict] = []
    insufficient_cards = 0
    new_rows: list[dict] = []

    for cid, led, cdef in elig:
        graded_at = _parse_ts(led.get("graded_at"))
        scope = (cdef.get("condition", {}) or {}).get("scope", "pregame")
        if graded_at is None:
            insufficient_cards += 1
            continue
        link_method, linked = _link(cdef, graded_at, scope, ev_ingame, ev_pregame)
        all_insufficient, decayed_reason = True, None
        for h in HORIZONS:
            verdict, reason, n_post, med, pct_beat = _regrade_one(linked, graded_at, h, min_n, decay_margin)
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
            if verdict != "INSUFFICIENT":
                all_insufficient = False
                horizon_holds[h][1] += 1
                if verdict == "HOLDS":
                    horizon_holds[h][0] += 1
                elif verdict == "DECAYED" and decayed_reason is None:
                    decayed_reason = reason
            key = (cid, as_of, h)
            if key in seen:
                continue
            seen.add(key)
            new_rows.append({
                "card_id": cid,
                "regraded_at": now.isoformat(),
                "original_verdict": led.get("verdict"),
                "graded_at": led.get("graded_at"),
                "window_days": h,
                "n_post": n_post,
                "post_median_clv_pct": med,
                "post_pct_beat_close": pct_beat,
                "regrade_verdict": verdict,
                "reason": reason,
                "link_method": link_method,
                "edge_claimed": False,
            })
        if decayed_reason is not None:
            decayed_cards.append({"card_id": cid, "reason": decayed_reason})
        if all_insufficient:
            insufficient_cards += 1

    if new_rows:
        with out_ledger.open("a", encoding="utf-8") as fh:
            for r in new_rows:
                fh.write(json.dumps(r) + "\n")

    survival = {
        f"{h}d": (round(hd[0] / hd[1], 4) if hd[1] else None)
        for h, hd in horizon_holds.items()
    }
    snapshot = {
        "generated_at": now.isoformat(),
        "edge_claimed": False,
        "honest_note": HONEST_NOTE,
        "n_cards_total": total_ledger,
        "n_eligible": len(elig),
        "verdict_counts": verdict_counts,
        "survival": survival,
        "decayed_cards": decayed_cards,
        "insufficient_cards": insufficient_cards,
    }
    _atomic_write_json(out_survival, snapshot)
    snapshot["_rows_appended"] = len(new_rows)
    return snapshot


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Claim survival regrader (calibration/CLV only).")
    ap.add_argument("--min-n", type=int, default=MIN_N)
    ap.add_argument("--decay-margin", type=float, default=DECAY_MARGIN)
    args = ap.parse_args(argv)
    snap = run(min_n=args.min_n, decay_margin=args.decay_margin)
    print(
        f"[regrader] eligible={snap['n_eligible']}/{snap['n_cards_total']} "
        f"rows_appended={snap['_rows_appended']} verdicts={snap['verdict_counts']} "
        f"survival7/30/60={snap['survival'].get('7d')}/{snap['survival'].get('30d')}/{snap['survival'].get('60d')} "
        f"decayed={len(snap['decayed_cards'])} insufficient={snap['insufficient_cards']}"
    )
    if snap["n_eligible"] == 0:
        print("[regrader] 0 eligible for regrade (no terminal-positive VALIDATED cards yet) -- ledger unchanged, honest snapshot written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
