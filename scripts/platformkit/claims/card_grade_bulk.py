"""scripts.platformkit.claims.card_grade_bulk -- grade 10,000s of grid cards.

card_grader.grade_card loops files PER CARD; at 21k cards x 1.2k grade files
that is dead on arrival. This module inverts the loop for the bulk-miner's
conjunction-shaped cards:

  1. load every grade row ONCE (with resolvable outcome, same source as
     card_grader: ingame_grade files + its outcome resolver);
  2. RETRO-TAG: evaluate each DISTINCT trigger FRAGMENT once per row
     (condition_tagger.eval_trigger, fail-closed) -> fragment -> row bitmask;
  3. a card's fired-mask = AND of its fragments' masks (big-int AND, ~free);
  4. only cards with enough fired rows get the full two-half 4-condition gate
     (imported VERBATIM from card_grader: _split_halves/_grade_half/verdict
     logic) -- the statistical gate is identical, only row collection differs.

RETRO-TAGGING HONESTY: rows predate these cards' registration. The trigger
fields are all as-of-tick captured values (leak-free by capture construction)
and the grid is mechanical/pre-outcome, but a verdict from retro rows is
labelled corpus="retro" (vs card_grader's forward claim_tags path) and the
consumer must treat retro VALIDATED as provisional until forward rows concur.
No $ claims; probability units only. Honest REJECTs are successes.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/claims/test_card_grade_bulk.py -q
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.claims import card_grader as _cg
from scripts.platformkit.claims import card_registry as _reg
from scripts.platformkit.claims.condition_tagger import eval_trigger
from scripts.platformkit.io_atomic import append_jsonl_atomic

logger = logging.getLogger(__name__)

_ALL_SPORTS = ("mlb", "tennis", "soccer_intl", "soccer", "nba", "wnba")
MIN_FIRED_TOTAL = 2 * _cg.MIN_FIRED_PER_HALF  # cheap pre-filter before the real gate


def _load_rows(grade_dir: Optional[Path], sports: Sequence[str],
               outcome_fn: Optional[_cg.OutcomeFn] = None) -> List[Dict[str, Any]]:
    """Every grade row with a resolvable outcome, loaded once. Never raises."""
    fn = outcome_fn or _cg._default_outcome_fn()
    rows: List[Dict[str, Any]] = []
    for sport, p in _cg._discover_files(grade_dir, sports):
        try:
            pairs = _cg._lg._load_pairs(Path(p))
        except Exception:  # noqa: BLE001
            pairs = []
        if not pairs:
            continue
        gid = str(pairs[0].get("game_id") or Path(p).stem)
        y = fn(sport, gid)
        if y is None:
            continue
        for r in pairs:
            try:
                mp, kp = float(r["model_prob"]), float(r["market_prob"])
            except (KeyError, TypeError, ValueError):
                continue
            ts = str(r.get("ts", ""))
            rows.append({"game_id": gid, "sport": sport, "date": ts[:10],
                         "model_prob": mp, "market_prob": kp, "y": y,
                         "state": r})
    return rows


def _split_fragments(trigger: str) -> List[str]:
    """The bulk miner writes triggers as '(f1) and (f2) and ...'. Non-miner
    triggers fall back to a single fragment (still correct, just uncached
    across cards)."""
    parts = [p for p in trigger.split(") and (") if p]
    if len(parts) <= 1:
        return [trigger]
    parts[0] = parts[0].lstrip("(")
    parts[-1] = parts[-1].rstrip(")")
    return parts


def _fragment_masks(cards: Sequence[Dict[str, Any]],
                    rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """fragment -> bitmask over rows (bit i set = row i satisfies fragment)."""
    frags: set = set()
    for c in cards:
        frags.update(_split_fragments((c.get("condition") or {}).get("trigger", "")))
    masks: Dict[str, int] = {}
    for frag in frags:
        m = 0
        for i, r in enumerate(rows):
            if eval_trigger(frag, r["state"]):
                m |= 1 << i
        masks[frag] = m
    return masks


def _mask_rows(mask: int, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    while mask:
        lsb = mask & -mask
        i = lsb.bit_length() - 1
        r = rows[i]
        out.append({**{k: r[k] for k in ("game_id", "sport", "date",
                                         "model_prob", "market_prob", "y")},
                    "fired": True})
        mask ^= lsb
    return out


def _verdict(card: Dict[str, Any], fired_rows: List[Dict[str, Any]],
             all_rows: Sequence[Dict[str, Any]], fired_mask: int,
             ts: str) -> Dict[str, Any]:
    """The SAME 4-condition two-half gate as card_grader.grade_card, fed by
    mask-collected rows. notfired = complement rows (control)."""
    notfired = [{**{k: r[k] for k in ("game_id", "sport", "date",
                                      "model_prob", "market_prob", "y")},
                 "fired": False}
                for i, r in enumerate(all_rows) if not (fired_mask >> i) & 1]
    rows = fired_rows + notfired
    half_a, half_b = _cg._split_halves(rows)
    ga, gb = _cg._grade_half(half_a), _cg._grade_half(half_b)
    base = {"card_id": card["card_id"], "family": card.get("family"),
            "cell": card.get("cell"), "graded_at": ts, "corpus": "retro",
            "units": "probability", "edge_claimed": False,
            "n_fired": len(fired_rows), "n_total": len(rows)}
    if ga["status"] != "graded" or gb["status"] != "graded":
        return {**base, "verdict": "OPEN",
                "reason": "accruing: half A=%d half B=%d, need >=%d each" % (
                    ga["fired"]["n_rows"], gb["fired"]["n_rows"], _cg.MIN_FIRED_PER_HALF)}
    exp = 1 if card.get("expected_sign") == "+" else -1
    sign_a = 1 if ga["fired"]["clv"] > 0 else (-1 if ga["fired"]["clv"] < 0 else 0)
    sign_b = 1 if gb["fired"]["clv"] > 0 else (-1 if gb["fired"]["clv"] < 0 else 0)
    cond_sign = sign_a == exp and sign_b == exp
    cond_beats = (-ga["fired"]["brier_delta"] > -ga["notfired"]["brier_delta"]
                  and -gb["fired"]["brier_delta"] > -gb["notfired"]["brier_delta"])
    cond_sig = ga["significant"] and gb["significant"]
    validated = cond_sign and cond_beats and cond_sig
    return {**base, "verdict": "VALIDATED" if validated else "REJECTED",
            "reason": "all 4 conditions met (retro corpus)" if validated else
            "failed: %s" % ",".join(k for k, v in (
                ("sign", cond_sign), ("beats_control", cond_beats),
                ("significant", cond_sig)) if not v),
            "detail": {"half_a": {"n_fired": ga["fired"]["n_rows"],
                                  "brier_delta": round(ga["fired"]["brier_delta"], 6),
                                  "clv": round(ga["fired"]["clv"], 6),
                                  "ci95": [ga["ci_lo"], ga["ci_hi"]]},
                       "half_b": {"n_fired": gb["fired"]["n_rows"],
                                  "brier_delta": round(gb["fired"]["brier_delta"], 6),
                                  "clv": round(gb["fired"]["clv"], 6),
                                  "ci95": [gb["ci_lo"], gb["ci_hi"]]}}}


def grade_bulk(*, grade_dir: Optional[Path] = None,
               sports: Optional[Sequence[str]] = None,
               outcome_fn: Optional[_cg.OutcomeFn] = None,
               now: Optional[datetime] = None,
               ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Grade every OPEN ingame card against the full retro corpus. Terminal
    verdicts close the card (peek-locked first); OPEN verdicts keep accruing
    forward via the live tagger. Never raises."""
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    lpath = Path(ledger_path) if ledger_path is not None else _cg.LEDGER_PATH
    cards = [c for c in _reg.get_open()
             if (c.get("condition") or {}).get("scope") == "ingame"]
    rows = _load_rows(grade_dir, sports or _ALL_SPORTS, outcome_fn)
    summary: Dict[str, Any] = {"graded_at": ts, "n_cards": len(cards),
                               "n_rows": len(rows), "corpus": "retro",
                               "counts": {"VALIDATED": 0, "REJECTED": 0, "OPEN": 0},
                               "edge_claimed": False}
    if not cards or not rows:
        return summary
    masks = _fragment_masks(cards, rows)
    peek: Dict[str, Dict[str, Any]] = {}
    closes: Dict[str, Dict[str, Any]] = {}
    validated_ids: List[str] = []
    for card in cards:
        trigger = (card.get("condition") or {}).get("trigger", "")
        fired_mask = (1 << len(rows)) - 1
        for frag in _split_fragments(trigger):
            fired_mask &= masks.get(frag, 0)
        n_fired = bin(fired_mask).count("1")
        if n_fired < MIN_FIRED_TOTAL:
            summary["counts"]["OPEN"] += 1
            continue  # accruing -- no peek, no ledger noise at 21k cards
        peek[card["card_id"]] = {"outcomes_peeked": True}
        result = _verdict(card, _mask_rows(fired_mask, rows), rows, fired_mask, ts)
        v = result["verdict"]
        summary["counts"][v] = summary["counts"].get(v, 0) + 1
        try:
            append_jsonl_atomic(lpath, result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bulk ledger append failed: %s", exc)
        if v in ("VALIDATED", "REJECTED"):
            closes[card["card_id"]] = {"status": v, "reason": result.get("reason", ""),
                                       "outcomes_peeked": True}
            peek.pop(card["card_id"], None)
        if v == "VALIDATED":
            validated_ids.append(card["card_id"])
    _reg.bulk_update({**peek, **closes}, ts)
    summary["validated_card_ids"] = validated_ids
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Bulk retro+forward card grading (honest 4-condition gate)")
    ap.add_argument("--grade-dir", default=None)
    args = ap.parse_args()
    out = grade_bulk(grade_dir=Path(args.grade_dir) if args.grade_dir else None)
    out.pop("validated_card_ids_detail", None)
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
