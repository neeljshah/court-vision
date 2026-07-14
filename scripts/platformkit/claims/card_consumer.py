"""scripts.platformkit.claims.card_consumer -- P5 consumption for VALIDATED cards.

ONLY consumes cards whose LATEST registry row has status=="VALIDATED" (card_grader's
4-condition verdict, see card_grader.py). Zero cards are VALIDATED today (10 accruing,
n_fired=0) -- this module is the MECHANISM, exercised end-to-end by a synthetic
VALIDATED card in the test, never a real one yet. Idempotent: re-running consume_all
skips any card already in the consumed-log.

Three outputs per scope, all APPEND-ONLY jsonl, all read-only imports elsewhere:

  ingame VALIDATED  -> ingame_routes.jsonl: a routing entry naming the card's
    window+trigger and a PER-CARD env flag (CV_CLAIMS_<CARD_ID>), default OFF,
    shadow_only=True. This module only WRITES the entry -- it does not wire any
    serving path (that would touch gated api/kernel/src files) and does not flip
    the flag. Promotion out of shadow_only is advisory, same as the CV_INGAME_SBS
    pattern (src/ingame/sbs_shadow.py): needs >=3 real shadow-win nights, judged
    by a human/grader reading the shadow log, not auto-promoted here.

  pregame VALIDATED -> pregame_trust_segments.jsonl: a TRUSTED/ADVERSE trust-segment
    record (which bets get sized, not the point prediction), same shape family as
    ingame_segment_trust_multi's {"trust": ..., "per_corpus": [...]} record.

  either scope        -> proven_lines.jsonl: one PROVEN-claim line with n + effect
    size, keyed by card_id. FALLBACK artifact, not a dossier merge: no existing
    platformkit writer merges into data/cache/profiles/ (confirmed by research --
    SCHEMA.md's provenance-merge convention exists but has zero writers today), so
    building that merge here would be new, untested, risky surface for a mechanism
    with zero real validated cards to prove it against. This emits the artifact for
    a human/later lane to merge once it matters.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/claims/test_card_consumer.py -q
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.claims import card_registry as _reg
from scripts.platformkit.io_atomic import append_jsonl_atomic

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLAIMS_DIR = _REPO_ROOT / "data" / "cache" / "claims"
ROUTES_PATH = _CLAIMS_DIR / "ingame_routes.jsonl"
TRUST_PATH = _CLAIMS_DIR / "pregame_trust_segments.jsonl"
PROVEN_PATH = _CLAIMS_DIR / "proven_lines.jsonl"
CONSUMED_PATH = _CLAIMS_DIR / "consumed.jsonl"

SHADOW_PROMOTE_MIN_NIGHTS = 3  # advisory only, see module docstring


def env_flag_name(card_id: str) -> str:
    return "CV_CLAIMS_%s" % card_id.upper()


def is_flag_on(card_id: str) -> bool:
    """Read-only check of the per-card flag. Default OFF; never set by this module."""
    val = os.environ.get(env_flag_name(card_id), "0").strip().lower()
    return val in {"1", "true", "yes", "on", "y", "t"}


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _consumed_ids(consumed_path: Path) -> set:
    return {r["card_id"] for r in _read_jsonl(consumed_path) if r.get("card_id")}


def _latest_grade(card_id: str, ledger_path: Path) -> Optional[Dict[str, Any]]:
    """Latest card_ledger.jsonl row for card_id (n_fired, detail), or None."""
    rows = [r for r in _read_jsonl(ledger_path) if r.get("card_id") == card_id]
    return rows[-1] if rows else None


def route_ingame(card: Dict[str, Any], ts: str, *, path: Path = ROUTES_PATH) -> Dict[str, Any]:
    cond = card.get("condition") or {}
    entry = {
        "card_id": card["card_id"], "kind": "ingame_route", "ts": ts,
        "window": cond.get("window"), "trigger": cond.get("trigger"),
        "entity": cond.get("entity"), "expected_sign": card.get("expected_sign"),
        "env_flag": env_flag_name(card["card_id"]), "env_flag_default": "0",
        "shadow_only": True, "promoted": False,
        "promote_rule": "advisory: >=%d real shadow-win nights (see docstring)" % SHADOW_PROMOTE_MIN_NIGHTS,
        "edge_claimed": False,
    }
    append_jsonl_atomic(path, entry)
    return entry


def route_pregame(card: Dict[str, Any], ts: str, *, path: Path = TRUST_PATH) -> Dict[str, Any]:
    entry = {
        "card_id": card["card_id"], "kind": "pregame_trust_segment", "ts": ts,
        "segment": card.get("claim", "")[:80], "condition": card.get("condition"),
        "trust": "TRUSTED", "expected_sign": card.get("expected_sign"),
        "note": "trust-segment: gates which bets are SIZED, not the point prediction",
        "edge_claimed": False,
    }
    append_jsonl_atomic(path, entry)
    return entry


def emit_proven_line(card: Dict[str, Any], grade: Optional[Dict[str, Any]], ts: str,
                     *, path: Path = PROVEN_PATH) -> Dict[str, Any]:
    detail = (grade or {}).get("detail") or {}
    line = {
        "card_id": card["card_id"], "kind": "proven_line", "ts": ts,
        "claim": card.get("claim"), "condition": card.get("condition"),
        "mechanism": card.get("mechanism"), "expected_sign": card.get("expected_sign"),
        "n_fired": (grade or {}).get("n_fired", 0),
        "effect": {
            "half_a_brier_delta": detail.get("half_a", {}).get("brier_delta"),
            "half_b_brier_delta": detail.get("half_b", {}).get("brier_delta"),
        },
        "units": "probability (calibration, not $ edge)", "edge_claimed": False,
    }
    append_jsonl_atomic(path, line)
    return line


def consume_card(card: Dict[str, Any], *, grade: Optional[Dict[str, Any]] = None,
                 ts: Optional[str] = None, routes_path: Path = ROUTES_PATH,
                 trust_path: Path = TRUST_PATH, proven_path: Path = PROVEN_PATH,
                 consumed_path: Path = CONSUMED_PATH) -> Dict[str, Any]:
    """Consume ONE VALIDATED card. Caller must have already verified status=='VALIDATED'."""
    ts = ts or _now_ts()
    scope = (card.get("condition") or {}).get("scope")
    result: Dict[str, Any] = {"card_id": card["card_id"], "scope": scope, "ts": ts}
    if scope == "ingame":
        result["route"] = route_ingame(card, ts, path=routes_path)
    elif scope == "pregame":
        result["trust_segment"] = route_pregame(card, ts, path=trust_path)
    else:
        result["route"] = None  # unknown scope: proven-line only, no routing decision made
    result["proven_line"] = emit_proven_line(card, grade, ts, path=proven_path)
    append_jsonl_atomic(consumed_path, {"card_id": card["card_id"], "consumed_ts": ts})
    return result


def consume_all(*, ts: Optional[str] = None, registry_module=_reg,
                ledger_path: Optional[Path] = None, routes_path: Path = ROUTES_PATH,
                trust_path: Path = TRUST_PATH, proven_path: Path = PROVEN_PATH,
                consumed_path: Path = CONSUMED_PATH) -> Dict[str, Any]:
    """Consume every VALIDATED card not already consumed. Idempotent, never raises."""
    ts = ts or _now_ts()
    lpath = ledger_path
    if lpath is None:
        from scripts.platformkit.claims.card_grader import LEDGER_PATH as lpath  # noqa: PLC0415
    already = _consumed_ids(consumed_path)
    consumed: List[Dict[str, Any]] = []
    for card in registry_module.get_all_latest().values():
        if card.get("status") != "VALIDATED" or card["card_id"] in already:
            continue
        try:
            grade = _latest_grade(card["card_id"], lpath)
            consumed.append(consume_card(
                card, grade=grade, ts=ts, routes_path=routes_path, trust_path=trust_path,
                proven_path=proven_path, consumed_path=consumed_path))
        except Exception as exc:  # noqa: BLE001 -- one bad card must never sink the pass
            consumed.append({"card_id": card["card_id"], "error": type(exc).__name__})
    return {"ts": ts, "n_validated_total": sum(
        1 for c in registry_module.get_all_latest().values() if c.get("status") == "VALIDATED"),
        "n_newly_consumed": len(consumed), "consumed": consumed, "edge_claimed": False}


__all__ = [
    "ROUTES_PATH", "TRUST_PATH", "PROVEN_PATH", "CONSUMED_PATH",
    "SHADOW_PROMOTE_MIN_NIGHTS", "env_flag_name", "is_flag_on",
    "route_ingame", "route_pregame", "emit_proven_line", "consume_card", "consume_all",
]
