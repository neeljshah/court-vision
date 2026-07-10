"""scripts.platformkit.mlb_wrong_settle_audit -- one-shot AUDIT (never repairs) for
the settled-MLB wrong-settle class proven live in the adversarial review of 0889b481:
grade_paper._find_final_game / grade_paper_asof.mlb_ticker_fallback_match matched a
FINAL game by team only, no date guard -- so a KXMLBGAME-ticketed bet could settle
against a same-teams final from the WRONG calendar date (proven: COL@SF tickers
dated 26JUL09/26JUL10/26JUL11 all settled against the identical 26JUL09 8-2 final;
the 26JUL11 ticket -- placed 07-08 -- settled before its own game could even be
final). The date guard added in grade_paper._find_final_game / mlb_ticker_fallback_match
(same lane) stops NEW wrong settles going forward; this module finds rows that were
ALREADY settled before that fix landed.

Two independent, low-false-positive checks per settled MLB KXMLBGAME row:
  settled_before_ticket_date -- settled_at's calendar date is STRICTLY EARLIER than
    the ticket's own embedded game date: definitionally impossible (a game cannot be
    graded final before its own date has even started) -- airtight proof.
  same_final_reused_across_dates -- >=2 settled rows share the SAME team pairing
    (from the ticket tail, not the free-text matchup label) and the SAME
    (home_score, away_score) but carry DIFFERENT ticket dates -- one literal final
    bound to more than one calendar date's bet.

AUDIT ONLY: never re-settles, never edits a settled row (human-gated, see
.claude/rules/human-gated-paths.md). Writes a full-replace quarantine flag list
(bet_ids + reason) as a sidecar, mirroring the ingame_score_drift_audit convention
(data/frontend/ops/, write_json_atomic).

CLI:
  python -m scripts.platformkit.mlb_wrong_settle_audit

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_mlb_wrong_settle_audit.py -q
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.grade_paper_asof import _mlb_ticker, _mlb_ticker_date
from scripts.platformkit.ingame.hist_mlb_outcome_resolver import parse_mlb_ticker as _parse_mlb_ticker
from scripts.platformkit.io_atomic import write_json_atomic

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FLAGS_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "mlb_wrong_settle_quarantine.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _team_pair_key(bet: Dict[str, Any]) -> Optional[str]:
    """Order-independent team-pair signature straight from the ticket tail (not the
    free-text matchup label -- that alias gap is exactly what this fix's fallback
    already solves; identical tail string = identical pairing)."""
    ticker = _mlb_ticker(bet)
    if ticker is None:
        return None
    parsed = _parse_mlb_ticker(ticker)
    return parsed[1] if parsed else None


_INGAME_CHANNEL = "paper_ingame"  # settles via exact game_id match -- a DIFFERENT
# resolver (ingame_paper_settle.py) that never calls _find_final_game /
# mlb_ticker_fallback_match; excluded below so it is never falsely flagged.


def find_wrong_settles(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scan settled MLB KXMLBGAME rows for the two proven wrong-settle signatures.
    Never mutates *rows*. Returns one flag dict per implicated bet_id.

    Scoped to the actual bug surface: rows settled through grade_paper.py's own
    team+date fuzzy matcher (channel="paper_pm" / Kalshi pregame-and-live-moneyline
    bets). *_INGAME_CHANNEL* rows carry the same KXMLBGAME ticker in bet_id/game_id
    but are settled by a DIFFERENT resolver keyed on the exact game_id -- verified
    live (2026-07-10): 407 paper_ingame rows vs 23 paper_pm rows share this ticker
    pattern; only the paper_pm ones ever pass through the code this fix touches.
    """
    mlb_settled = [r for r in rows
                   if str(r.get("sport", "")).lower() == "mlb"
                   and r.get("status") == "settled" and _mlb_ticker(r) is not None
                   and r.get("channel") != _INGAME_CHANNEL]

    flags: Dict[str, Dict[str, Any]] = {}

    def _flag(r: Dict[str, Any], reason: str) -> None:
        bid = str(r.get("bet_id") or r.get("settle_key") or "")
        if not bid:
            return
        entry = flags.setdefault(bid, {
            "bet_id": bid, "matchup": r.get("matchup"),
            "ticker_date": _mlb_ticker_date(r), "settled_at": r.get("settled_at"),
            "home_score": r.get("home_score"), "away_score": r.get("away_score"),
            "reasons": [],
        })
        if reason not in entry["reasons"]:
            entry["reasons"].append(reason)

    # Check 1: settled_at predates the ticket's own game date -- impossible.
    for r in mlb_settled:
        tdate = _mlb_ticker_date(r)
        settled_at = str(r.get("settled_at") or "")[:10]
        if tdate and settled_at and settled_at < tdate:
            _flag(r, "settled_before_ticket_date")

    # Check 2: identical (team-pair, final score) reused across >=2 distinct dates.
    groups: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for r in mlb_settled:
        pair = _team_pair_key(r)
        hs, aws = r.get("home_score"), r.get("away_score")
        if pair is None or hs is None or aws is None:
            continue
        groups[(pair, hs, aws)].append(r)
    for members in groups.values():
        dates = {_mlb_ticker_date(m) for m in members} - {None}
        if len(dates) > 1:
            for m in members:
                _flag(m, "same_final_reused_across_dates")

    return sorted(flags.values(), key=lambda f: str(f.get("bet_id")))


def run_audit(ledger_path: Optional[Path] = None, flags_path: Optional[Path] = None
             ) -> Dict[str, Any]:
    """One AUDIT pass: scan, write the quarantine flag list, never touch the ledger."""
    ledger_path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    flags_path = Path(flags_path) if flags_path else DEFAULT_FLAGS_PATH
    rows = _clv.load_ledger(ledger_path)
    flags = find_wrong_settles(rows)
    n_scanned = sum(1 for r in rows if str(r.get("sport", "")).lower() == "mlb"
                    and r.get("status") == "settled" and _mlb_ticker(r) is not None
                    and r.get("channel") != _INGAME_CHANNEL)
    report = {
        "generated_at": _now_iso(), "component": "mlb_wrong_settle_audit",
        "n_settled_mlb_ticker_scanned": n_scanned, "n_flagged": len(flags),
        "flags": flags,
        "note": ("AUDIT ONLY -- never re-settles or edits a settled row (human-gated); "
                "the root-cause date guard (grade_paper._find_final_game / "
                "grade_paper_asof.mlb_ticker_fallback_match) now blocks NEW wrong "
                "settles of this class."),
    }
    write_json_atomic(flags_path, report)
    return report


def main() -> int:
    report = run_audit()
    summary = {k: v for k, v in report.items() if k != "flags"}
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["find_wrong_settles", "run_audit", "DEFAULT_FLAGS_PATH"]
