"""L26_account_hygiene.py — Account Hygiene Tooling (execute_loop layer 26).

Monitors submission pace, IP consistency, betting patterns, and deposit
scheduling to reduce sportsbook account-limitation risk.

Storage:
    data/ledger/hygiene_report_<YYYY-MM-DD>.json

CLI:
    python L26_account_hygiene.py report
    python L26_account_hygiene.py pace --book dk
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parents[3]
_LEDGER_DIR = _PROJECT_DIR / "data" / "ledger"
_BETS_FILE = _LEDGER_DIR / "bets.parquet"
_BETS_CSV = _LEDGER_DIR / "bets.csv"

# ---------------------------------------------------------------------------
# Soft imports
# ---------------------------------------------------------------------------
try:
    import pyarrow  # noqa: F401
    _HAS_PARQUET = True
except ImportError:
    _HAS_PARQUET = False

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HygieneCheck:
    check_name: str
    status: str       # PASS | WARN | FAIL
    details: str


@dataclass
class BetPace:
    book: str
    n_bets_today: int
    max_bets_per_hour: int          # default 10
    current_pace_per_hour: float
    throttle_seconds_recommended: int  # 0 if OK, 480 if >8/hr

    @property
    def status(self) -> str:
        """Derived status matching the pace thresholds."""
        if self.current_pace_per_hour > 10:
            return "FAIL"
        if self.current_pace_per_hour >= 8:
            return "WARN"
        return "PASS"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(ts: str) -> datetime:
    """Parse ISO-8601 string; attach UTC if no tzinfo."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_ledger_bets() -> list[dict]:
    """Try loading bets from L07 parquet/CSV; return empty list on failure."""
    if not _HAS_PANDAS:
        log.info("pandas not available — skipping ledger load")
        return []
    try:
        if _HAS_PARQUET and _BETS_FILE.exists():
            import pandas as pd
            df = pd.read_parquet(_BETS_FILE)
            return df.to_dict("records")
        if _BETS_CSV.exists():
            import pandas as pd
            df = pd.read_csv(_BETS_CSV, dtype=str)
            return df.to_dict("records")
    except Exception as exc:  # pragma: no cover
        log.info("L07 ledger read failed: %s", exc)
    return []


def _try_send_alert(check: HygieneCheck) -> None:
    """Soft-import L22 alerting; silently skip if unavailable."""
    if check.status not in ("WARN", "FAIL"):
        return
    try:
        import importlib
        L22 = importlib.import_module("scripts.execute_loop.L22_alerting")
        L22.send_alert(
            channel="system",
            level="warning",
            title=f"Hygiene {check.status}: {check.check_name}",
            body=check.details,
            fields={},
        )
    except Exception as exc:
        log.debug("L22 alert skipped: %s", exc)


def _try_get_max_single_bet(book: str) -> Optional[float]:
    """Soft-import L18 for max single bet; return None if unavailable."""
    try:
        import importlib
        L18 = importlib.import_module("scripts.execute_loop.L18_bankroll_manager")
        state = L18.get_bankroll_state()  # expected to return a dict or dataclass
        if isinstance(state, dict):
            return state.get("max_single_bet")
        return getattr(state, "max_single_bet", None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_submission_pace(book: str, recent_bets: list[dict]) -> BetPace:
    """Count bets for *book* placed in the last 60 minutes.

    Thresholds:
        >10 bets/hr  → FAIL, throttle 480s
        8-10 bets/hr → WARN, throttle 480s
        <8 bets/hr   → PASS, throttle 0s
    """
    now = _now_utc()
    cutoff = now - timedelta(hours=1)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    book_bets = [b for b in recent_bets if b.get("book", "").lower() == book.lower()]
    bets_last_hour = [
        b for b in book_bets
        if "placed_at_iso" in b and _parse_iso(b["placed_at_iso"]) >= cutoff
    ]
    bets_today = [
        b for b in book_bets
        if "placed_at_iso" in b and _parse_iso(b["placed_at_iso"]) >= today_start
    ]

    n_last_hour = len(bets_last_hour)
    pace = float(n_last_hour)  # per-hour rate (measured over 1h window)

    if n_last_hour > 10:
        throttle = 480
    elif n_last_hour >= 8:
        throttle = 480
    else:
        throttle = 0

    return BetPace(
        book=book,
        n_bets_today=len(bets_today),
        max_bets_per_hour=10,
        current_pace_per_hour=pace,
        throttle_seconds_recommended=throttle,
    )


def check_ip_consistency(recent_bets: list[dict]) -> HygieneCheck:
    """Inspect distinct IPs across all recent bets.

    ≤2 distinct IPs → PASS
    >2 distinct IPs → WARN
    """
    if not recent_bets:
        return HygieneCheck(
            check_name="ip_consistency",
            status="PASS",
            details="no recent activity",
        )

    ips = {b.get("ip", "local") for b in recent_bets}
    distinct = len(ips)

    if distinct <= 2:
        return HygieneCheck(
            check_name="ip_consistency",
            status="PASS",
            details=f"{distinct} distinct IP(s) — OK",
        )
    return HygieneCheck(
        check_name="ip_consistency",
        status="WARN",
        details=f"{distinct} distinct IPs could trigger account flag",
    )


def check_pattern_flags(recent_bets: list[dict]) -> list[HygieneCheck]:
    """Return a list of HygieneChecks for suspicious betting patterns.

    Checks:
    1. Sharp +EV pattern: ≥80% of last 20 bets near -110 with positive model edge.
    2. Max-stake repetition: ≥5 of last 10 bets at max single bet amount.
    3. News-trading pattern: ≥3 of last 10 bets within 2 min of lock_time.
    """
    checks: list[HygieneCheck] = []

    if not recent_bets:
        return [HygieneCheck("pattern_flags", "PASS", "no recent activity")]

    # ── 1. Sharp +EV pattern (last 20) ──────────────────────────────────────
    last_20 = recent_bets[-20:]
    ev_sharp_count = 0
    for b in last_20:
        odds = b.get("odds")
        edge = b.get("model_edge_pp")
        if odds is not None and edge is not None:
            try:
                if abs(float(odds) - (-110)) <= 5 and float(edge) > 0:
                    ev_sharp_count += 1
            except (ValueError, TypeError):
                pass

    if last_20 and ev_sharp_count / len(last_20) >= 0.80:
        checks.append(HygieneCheck(
            check_name="sharp_ev_pattern",
            status="WARN",
            details=(
                f"{ev_sharp_count}/{len(last_20)} bets near -110 with positive "
                "model_edge_pp — sharp +EV pattern detected"
            ),
        ))

    # ── 2. Max-stake repetition (last 10) ───────────────────────────────────
    last_10 = recent_bets[-10:]
    max_stake_count = sum(
        1 for b in last_10
        if "max_single_bet" in b and "stake" in b
        and _safe_eq(b.get("max_single_bet"), b.get("stake"))
    )
    if max_stake_count >= 5:
        checks.append(HygieneCheck(
            check_name="max_stake_repetition",
            status="WARN",
            details=(
                f"{max_stake_count}/10 bets used max single bet amount — "
                "pattern may flag account"
            ),
        ))

    # ── 3. News-trading / lock-time proximity (last 10) ─────────────────────
    near_lock_count = 0
    for b in last_10:
        placed = b.get("placed_at_iso")
        lock = b.get("lock_time")
        if placed and lock:
            try:
                delta = abs((_parse_iso(lock) - _parse_iso(placed)).total_seconds())
                if delta <= 120:
                    near_lock_count += 1
            except (ValueError, TypeError):
                pass

    if near_lock_count >= 3:
        checks.append(HygieneCheck(
            check_name="news_trading_pattern",
            status="WARN",
            details=(
                f"{near_lock_count}/10 bets placed within 2 min of lock_time — "
                "news-trading pattern detected"
            ),
        ))

    if not checks:
        checks.append(HygieneCheck("pattern_flags", "PASS", "no suspicious patterns"))

    return checks


def _safe_eq(a, b) -> bool:
    """Numeric equality with type coercion."""
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def recommend_deposit_schedule(bankroll_targets: dict[str, float]) -> list[dict]:
    """Produce 2-3 staggered deposit amounts for each book across 3+ days.

    Uses non-round amounts to avoid pattern detection.
    """
    schedule: list[dict] = []
    today = datetime.now(tz=timezone.utc).date()

    _NON_ROUND_SPLITS = [
        [0.487, 0.312, 0.201],   # template A
        [0.453, 0.327, 0.220],   # template B
    ]

    for idx, (book, target) in enumerate(bankroll_targets.items()):
        splits = _NON_ROUND_SPLITS[idx % len(_NON_ROUND_SPLITS)]
        used_days: set = set()

        for i, frac in enumerate(splits):
            raw_amount = target * frac
            # Make non-round: truncate cents, then force a non-zero cents digit
            amount = int(raw_amount)           # whole dollars only
            if amount % 10 == 0:              # if round, nudge by 1
                amount = amount + 1

            day_offset = i + 1                # Day 1, 2, 3 …
            deposit_date = today + timedelta(days=day_offset)

            # Guarantee uniqueness per (book, day)
            while (book, deposit_date) in used_days:
                deposit_date += timedelta(days=1)
            used_days.add((book, deposit_date))

            schedule.append({
                "book": book,
                "date": deposit_date.isoformat(),
                "amount": amount,
                "note": f"deposit {i + 1}/{len(splits)} for {book}",
            })

    return schedule


def daily_hygiene_report(
    recent_bets: Optional[list[dict]] = None,
    bankroll_targets: Optional[dict[str, float]] = None,
) -> dict:
    """Run all hygiene checks and write data/ledger/hygiene_report_<date>.json.

    Returns the report dict.  If L07 is unavailable and *recent_bets* is None,
    returns {"status": "no_data", "checks": []}.
    """
    if recent_bets is None:
        recent_bets = _load_ledger_bets()

    if not recent_bets:
        log.info("No recent bets — skipping hygiene checks")
        return {"status": "no_data", "checks": []}

    # Infer books from bet records
    books = list({b.get("book", "unknown") for b in recent_bets if b.get("book")})

    all_checks: list[HygieneCheck] = []

    # Pace checks per book
    for book in books:
        pace = check_submission_pace(book, recent_bets)
        status = (
            "FAIL" if pace.throttle_seconds_recommended > 0 and pace.current_pace_per_hour > 10
            else "WARN" if pace.throttle_seconds_recommended > 0
            else "PASS"
        )
        hc = HygieneCheck(
            check_name=f"submission_pace_{book}",
            status=status,
            details=(
                f"{pace.current_pace_per_hour:.1f} bets/hr "
                f"(today: {pace.n_bets_today}, throttle: {pace.throttle_seconds_recommended}s)"
            ),
        )
        all_checks.append(hc)
        _try_send_alert(hc)

    # IP consistency
    ip_check = check_ip_consistency(recent_bets)
    all_checks.append(ip_check)
    _try_send_alert(ip_check)

    # Pattern flags
    for pattern_hc in check_pattern_flags(recent_bets):
        all_checks.append(pattern_hc)
        _try_send_alert(pattern_hc)

    # Overall status = worst of all checks
    statuses = {c.status for c in all_checks}
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "WARN" in statuses:
        overall = "WARN"
    else:
        overall = "PASS"

    recommendations: list[dict] = []
    if bankroll_targets:
        recommendations = recommend_deposit_schedule(bankroll_targets)

    report = {
        "status": overall,
        "generated_at": _now_utc().isoformat(),
        "checks": [asdict(c) for c in all_checks],
        "recommendations": recommendations,
    }

    # Write to disk
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    out_path = _LEDGER_DIR / f"hygiene_report_{today_str}.json"
    out_path.write_text(json.dumps(report, indent=2))
    log.info("Hygiene report written → %s", out_path)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="L26 Account Hygiene Tooling")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("report", help="Run full daily hygiene report")

    pace_cmd = sub.add_parser("pace", help="Check submission pace for a book")
    pace_cmd.add_argument("--book", required=True, help="Book name (e.g. dk, fd)")

    return p


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "report":
        report = daily_hygiene_report()
        print(json.dumps(report, indent=2))

    elif args.command == "pace":
        bets = _load_ledger_bets()
        result = check_submission_pace(args.book, bets)
        print(json.dumps(asdict(result), indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
