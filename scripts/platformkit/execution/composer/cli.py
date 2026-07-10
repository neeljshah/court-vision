"""CLI for the best-bets portfolio composer (Lane B4).

  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.execution.composer.cli

Outputs (as-of stamped, append-only like the rest of data/frontend/ops/*.jsonl):
  data/frontend/ops/bestbets_composed.jsonl     -- one composed position per line
  data/frontend/ops/bestbets_composed_board.md  -- human-readable board

Consumes data/frontend/ops/timing_policy.json (SHIPPED by lane B1) purely as
an OPERATIONAL entry-timing default per sport/market (currently
last_pregame_tick everywhere) -- informational hint only, never a
beat-the-close claim (see .claude/rules/no-edge-claims.md).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.execution.composer.composer import (
    SPORTS_DEFAULT, collect_candidates, compose,
)

ROOT = Path(__file__).resolve().parents[4]
OUT_JSONL = ROOT / "data" / "frontend" / "ops" / "bestbets_composed.jsonl"
OUT_BOARD = ROOT / "data" / "frontend" / "ops" / "bestbets_composed_board.md"
TIMING_POLICY = ROOT / "data" / "frontend" / "ops" / "timing_policy.json"

HONEST_NOTE = (
    "Calibrated decision-support portfolio, as-of the stamped instant. UNITS "
    "not $; CLV-expectation language only; markets are efficient, no $ edge "
    "claimed. entry_horizon_hint is an OPERATIONAL default from the entry-"
    "timing study (currently last_pregame_tick), not a beat-the-close claim."
)


def _load_timing_policies() -> Dict[str, Any]:
    try:
        doc = json.loads(TIMING_POLICY.read_text(encoding="utf-8"))
        return doc.get("policies") or {}
    except Exception:  # noqa: BLE001 -- missing/malformed policy file -> no hint, not a crash
        return {}


def _entry_hint(policies: Dict[str, Any], sport: str, market_type: str) -> Optional[str]:
    sp = policies.get(sport)
    if not isinstance(sp, dict):
        return None
    mk = sp.get(market_type)
    return mk.get("entry_horizon") if isinstance(mk, dict) else None


def build_board(sports=SPORTS_DEFAULT, candidates=None) -> Dict[str, Any]:
    """candidates: inject a pre-collected card list (tests); default collects live."""
    as_of = datetime.now(timezone.utc).isoformat()
    policies = _load_timing_policies()
    raw = candidates if candidates is not None else collect_candidates(sports)
    composed = compose(list(raw))
    rows = []
    for rank, c in enumerate(composed, start=1):
        rows.append({
            "as_of": as_of, "rank": rank, "sport": c.get("sport"),
            "game_id": c.get("game_id"), "matchup": c.get("matchup"),
            "market_type": c.get("market_type"), "side": c.get("side"),
            "tier": c.get("tier"), "confidence": c.get("confidence"),
            "model_prob": c.get("model_prob"), "market_prob": c.get("market_prob"),
            "edge_vs_market": c.get("edge_vs_market"), "units": c.get("units"),
            "score": round(float(c.get("_score", 0.0)), 6),
            "clv": c.get("clv"), "status": c.get("status"),
            "entry_horizon_hint": _entry_hint(policies, str(c.get("sport") or ""),
                                              str(c.get("market_type") or "")),
            "honest_note": HONEST_NOTE,
        })
    return {"as_of": as_of, "count": len(rows), "edge_claimed": False,
            "honest_note": HONEST_NOTE, "positions": rows}


def _md_board(doc: Dict[str, Any]) -> str:
    lines = [
        "# Best-bets portfolio -- composed board", "",
        f"as-of: {doc['as_of']}  |  positions: {doc['count']}  |  edge_claimed: false",
        "",
        "UNITS not $. CLV-expectation language only. entry_horizon_hint is an "
        "operational default (last_pregame_tick), not a beat-the-close claim.",
        "",
        "| rank | sport | matchup | market | side | tier | conf | edge(pp) | units | entry hint |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in doc["positions"]:
        edge_pp = round((r.get("edge_vs_market") or 0.0) * 100, 2)
        lines.append(
            "| {rk} | {sp} | {mu} | {mt} | {sd} | {tr} | {cf} | {ed} | {un} | {eh} |".format(
                rk=r["rank"], sp=r["sport"], mu=r["matchup"], mt=r["market_type"],
                sd=r["side"], tr=r["tier"], cf=r["confidence"], ed=edge_pp,
                un=r["units"], eh=r.get("entry_horizon_hint") or "-"))
    return "\n".join(lines) + "\n"


def run(sports=SPORTS_DEFAULT, out_jsonl: Optional[Path] = OUT_JSONL,
        out_board: Optional[Path] = OUT_BOARD) -> Dict[str, Any]:
    doc = build_board(sports)
    if out_jsonl:
        out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(out_jsonl, "a", encoding="utf-8") as f:
            for r in doc["positions"]:
                f.write(json.dumps(r, ensure_ascii=True) + "\n")
        print(f"[composer] +{doc['count']} positions -> {out_jsonl}")
    if out_board:
        out_board.parent.mkdir(parents=True, exist_ok=True)
        out_board.write_text(_md_board(doc), encoding="utf-8")
        print(f"[composer] board -> {out_board}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Best-bets portfolio composer (units, CLV language)")
    ap.add_argument("--sport", action="append", default=None,
                   help="restrict to one sport (repeatable); default: all known sports")
    ap.add_argument("--dry-run", action="store_true", help="compute, write nothing")
    a = ap.parse_args(argv)
    sports = tuple(a.sport) if a.sport else SPORTS_DEFAULT
    doc = run(sports, None if a.dry_run else OUT_JSONL, None if a.dry_run else OUT_BOARD)
    print(json.dumps({"as_of": doc["as_of"], "count": doc["count"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
