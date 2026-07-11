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

Three independent, low-false-positive checks per settled MLB KXMLBGAME row:
  settled_before_ticket_date -- settled_at's calendar date is STRICTLY EARLIER than
    the ticket's own embedded game date: definitionally impossible (a game cannot be
    graded final before its own date has even started) -- airtight proof.
  same_final_reused_across_dates -- >=2 settled rows share the SAME team pairing
    (from the ticket tail, not the free-text matchup label) and the SAME
    (home_score, away_score) but carry DIFFERENT ticket dates -- one literal final
    bound to more than one calendar date's bet.
  settled_before_scheduled_start -- settled_at is STRICTLY EARLIER than the
    ticket's own embedded (date, ET time) start (2026-07-11 AZLAD wrong-settle:
    a SAME-CALENDAR-DATE ticker whose scheduled TIME hadn't arrived yet -- the
    first check above misses this because the calendar dates are equal, only
    the TIME differs; airtight proof, same as check 1 but time-aware).

AUDIT ONLY: never re-settles, never edits a settled row (human-gated, see
.claude/rules/human-gated-paths.md). Quarantine flags are APPEND-ONLY: an
existing bet_id's flag entry is never rewritten, only NEW bet_ids are added
(data/frontend/ops/, write_json_atomic for the crash-safe full-file replace of
the merged result).

CLI:
  python -m scripts.platformkit.mlb_wrong_settle_audit

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_mlb_wrong_settle_audit.py -q
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.grade_paper_asof import _mlb_ticker, _mlb_ticker_date
from scripts.platformkit.grade_paper_dates import _mlb_ticker_start_et as _ticker_start_et
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
# mlb_ticker_fallback_match, so it is excluded from checks 1/2 (the fuzzy
# team+date matcher class). RETIRED for check 3 (2026-07-11, W5 class): a
# same-game_id row can still settle before its own scheduled start if the
# exact-match resolver itself fires early on contaminated state -- proven
# live, 3x KXMLBGAME-26JUL111605MILPIT settled ~63min before its 16:05 ET
# first pitch. Check 3 below scans paper_ingame too; checks 1/2 still don't.

_NPBKBO_TICKER_RE = re.compile(r"KX(?:NPB|KBO)GAME-[A-Z0-9]+")  # not previously
# scanned at all (2026-07-11: 3x KXNPBGAME-26JUL12* tomorrow's tickets settled
# today). Same date+HHMM ticket shape as KXMLBGAME -- reuses the existing MLB
# ticker parser (_parse_mlb_ticker / _mlb_ticker_start_et) via a prefix swap
# instead of duplicating its regex for a second ticket family.


def _npbkbo_ticker(bet: Dict[str, Any]) -> Optional[str]:
    """The raw KXNPBGAME-.../KXKBOGAME-... ticker embedded in *bet*'s bet_id,
    or None."""
    m = _NPBKBO_TICKER_RE.search(str(bet.get("bet_id") or ""))
    return m.group(0) if m else None


def _as_mlb_shaped_bet_id(bet: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Shallow copy of *bet* with its NPB/KBO ticker's bet_id prefix swapped to
    KXMLBGAME- so the existing MLB ticker date/HHMM parser can run on it
    unchanged. Used ONLY to compute a start time / ticker_date -- flags are
    always recorded against the ORIGINAL row, never this shaped copy."""
    out = dict(bet)
    out["bet_id"] = str(bet.get("bet_id") or "").replace(
        ticker, "KXMLBGAME-" + ticker.split("-", 1)[1])
    return out


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

    def _flag(r: Dict[str, Any], reason: str, ticker_date: Optional[str] = None) -> None:
        bid = str(r.get("bet_id") or r.get("settle_key") or "")
        if not bid:
            return
        entry = flags.setdefault(bid, {
            "bet_id": bid, "matchup": r.get("matchup"),
            "ticker_date": ticker_date if ticker_date is not None else _mlb_ticker_date(r),
            "settled_at": r.get("settled_at"),
            "home_score": r.get("home_score"), "away_score": r.get("away_score"),
            "channel": r.get("channel") or str(r.get("sport") or "").lower() or None,
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

    # Check 3 (2026-07-11 AZLAD wrong-settle): settled_at strictly earlier than
    # the ticket's own (date, ET time) scheduled start -- catches the same-
    # calendar-date-different-TIME class check 1 cannot see (its dates are equal).
    for r in mlb_settled:
        start = _ticker_start_et(r)
        settled = _parse_settled_at(r.get("settled_at"))
        if start is not None and settled is not None and settled < start:
            _flag(r, "settled_before_scheduled_start")

    # Check 3, paper_ingame class (2026-07-11, W5 class): the exact-game_id
    # resolver can still fire early -- same signature, exclusion retired here.
    ingame_mlb_settled = [r for r in rows
                          if str(r.get("sport", "")).lower() == "mlb"
                          and r.get("status") == "settled" and _mlb_ticker(r) is not None
                          and r.get("channel") == _INGAME_CHANNEL]
    for r in ingame_mlb_settled:
        start = _ticker_start_et(r)
        settled = _parse_settled_at(r.get("settled_at"))
        if start is not None and settled is not None and settled < start:
            _flag(r, "settled_before_scheduled_start")

    # Check 3, NPB/KBO class (2026-07-11): channel not previously scanned at
    # all. Same date+HHMM ticket shape as KXMLBGAME -- reuse the MLB parser via
    # a prefix-swapped copy instead of a duplicate regex.
    npbkbo_settled = [r for r in rows if r.get("status") == "settled" and _npbkbo_ticker(r) is not None]
    for r in npbkbo_settled:
        ticker = _npbkbo_ticker(r)
        shaped = _as_mlb_shaped_bet_id(r, ticker)
        start = _ticker_start_et(shaped)
        settled = _parse_settled_at(r.get("settled_at"))
        if start is not None and settled is not None and settled < start:
            _flag(r, "settled_before_scheduled_start", ticker_date=_mlb_ticker_date(shaped))

    return sorted(flags.values(), key=lambda f: str(f.get("bet_id")))


def _parse_settled_at(settled_at: Any) -> Optional[datetime]:
    """*settled_at* (an ISO string) as a tz-aware datetime, or None. Never raises."""
    if not settled_at:
        return None
    try:
        dt = datetime.fromisoformat(str(settled_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _load_existing_flags(flags_path: Path) -> Dict[str, Dict[str, Any]]:
    """bet_id -> flag entry already on disk, or {} if the file is absent/unreadable.
    Never raises (a torn/missing sidecar degrades to "no prior flags")."""
    if not flags_path.is_file():
        return {}
    try:
        obj = json.loads(flags_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(f.get("bet_id")): f for f in obj.get("flags", []) if f.get("bet_id")}


def run_audit(ledger_path: Optional[Path] = None, flags_path: Optional[Path] = None
             ) -> Dict[str, Any]:
    """One AUDIT pass: scan, MERGE new flags into the quarantine file, never touch
    the ledger. APPEND-ONLY on the flag list itself: an existing bet_id's entry is
    reused byte-for-byte (never re-derived/overwritten), only bet_ids not already
    present get a new entry -- a human decides what happens to a flagged row."""
    ledger_path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    flags_path = Path(flags_path) if flags_path else DEFAULT_FLAGS_PATH
    rows = _clv.load_ledger(ledger_path)
    new_flags = find_wrong_settles(rows)
    existing = _load_existing_flags(flags_path)
    merged = dict(existing)
    for f in new_flags:
        bid = str(f.get("bet_id") or "")
        if bid and bid not in merged:
            merged[bid] = f
    flags = sorted(merged.values(), key=lambda f: str(f.get("bet_id")))
    n_scanned = sum(1 for r in rows if str(r.get("sport", "")).lower() == "mlb"
                    and r.get("status") == "settled" and _mlb_ticker(r) is not None
                    and r.get("channel") != _INGAME_CHANNEL)
    report = {
        "generated_at": _now_iso(), "component": "mlb_wrong_settle_audit",
        "n_settled_mlb_ticker_scanned": n_scanned, "n_flagged": len(flags),
        "flags": flags,
        "note": ("AUDIT ONLY -- never re-settles or edits a settled row (human-gated); "
                "the root-cause date + start-time guards (grade_paper._find_final_game / "
                "grade_paper_asof.mlb_ticker_fallback_match / grade_paper_dates."
                "bet_not_yet_started) now block NEW wrong settles of this class. "
                "2026-07-11: the paper_ingame exclusion assumption (its exact-game_id "
                "resolver 'can't wrong-settle') is RETIRED for the settled_before_"
                "scheduled_start check -- W5-contaminated bets defeated it live. NPB/KBO "
                "channels are now scanned too. Flags are append-only across runs -- an "
                "existing bet_id is never rewritten."),
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
