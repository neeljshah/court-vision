"""L05_submission_engine.py — DFS Lineup Submission Engine (PAPER MODE).

Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
env-var list).  Per-layer flags checked: dk_submission, fd_submission.
Env vars below are kept as fallbacks for backward compatibility when L44 is
absent (soft-import pattern).

Storage:
    data/ledger/submission_cache.json   — idempotency cache (TTL 24 h)
    data/ledger/paper_submissions.json  — paper-mode log

Mode: SUBMISSION_MODE=paper (default) | live (requires USER_TOKEN + book gates).

CLI:
    python L05_submission_engine.py submit --book {dk|fd} --contest_id X --lineup PATH [--live]
    python L05_submission_engine.py status --submission_id X

Environment Variables:
    SUBMISSION_MODE — Controls paper vs live submission routing.
        "paper" (default when absent): all submissions are logged locally to
        data/ledger/paper_submissions.json and no real money is wagered.
        "live": activates real API calls; requires USER_TOKEN + book-specific gates.

    USER_TOKEN — Bearer token used in the Authorization header for all live API
        requests (DraftKings and FanDuel). Required when SUBMISSION_MODE=live;
        if absent in live mode, _check_live_gates raises PermissionError and
        the submission is blocked. Defaults to empty string (disables live calls).

    DK_API_KEY — DraftKings API key sent as the X-Api-Key header for DK live
        submissions. Must be non-empty when SUBMISSION_MODE=live and book=dk.
        Absent value causes _check_live_gates to block the submission.

    DK_LIVE_ENABLED — Safety flag that must equal "1" to permit live DraftKings
        submissions. When absent or set to any other value, DK live submissions
        are blocked regardless of DK_API_KEY. Defaults to disabled (not "1").
        Also controlled via L44: DK_LIVE_SUBMISSION_ENABLED=1.

    FD_API_KEY — FanDuel API key sent as the X-Api-Key header for FD live
        submissions. Must be non-empty when SUBMISSION_MODE=live and book=fd.
        Absent value causes _check_live_gates to block the submission.

    FD_LIVE_ENABLED — Safety flag that must equal "1" to permit live FanDuel
        submissions. When absent or set to any other value, FD live submissions
        are blocked regardless of FD_API_KEY. Defaults to disabled (not "1").
        Also controlled via L44: FD_LIVE_SUBMISSION_ENABLED=1.

Paper vs Live Mode (MODE GATING):
    Default behavior is paper mode — no environment variables need to be set.
    Live submission is gated by ALL of the following conditions being true:
      1. SUBMISSION_MODE=live
      2. USER_TOKEN is non-empty
      3. For DK: DK_LIVE_ENABLED=1 (or L44 dk_submission live) AND DK_API_KEY is non-empty
         For FD: FD_LIVE_ENABLED=1 (or L44 fd_submission live) AND FD_API_KEY is non-empty
    If any gate is unsatisfied, _check_live_gates raises PermissionError and
    submit_lineup falls back to no submission (error propagates to caller).
    The --live CLI flag sets SUBMISSION_MODE=live in the current process only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_DIR))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# L44 soft-import — paper/live mode delegation
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop import L44_paper_mode as _L44  # type: ignore
except Exception:
    _L44 = None  # type: ignore


def _is_live_dk() -> bool:
    """Return True if DraftKings live submission is enabled.

    Checks L44 per-layer flag first; always also accepts the legacy
    DK_LIVE_ENABLED=1 env var for backward compatibility.
    """
    if _L44 is not None and _L44.is_live_for_layer("dk_submission"):
        return True
    return os.environ.get("DK_LIVE_ENABLED", "0").lower() in ("1", "true")


def _is_live_fd() -> bool:
    """Return True if FanDuel live submission is enabled.

    Checks L44 per-layer flag first; always also accepts the legacy
    FD_LIVE_ENABLED=1 env var for backward compatibility.
    """
    if _L44 is not None and _L44.is_live_for_layer("fd_submission"):
        return True
    return os.environ.get("FD_LIVE_ENABLED", "0").lower() in ("1", "true")

_LEDGER_DIR = PROJECT_DIR / "data" / "ledger"
_CACHE_FILE = _LEDGER_DIR / "submission_cache.json"
_PAPER_FILE = _LEDGER_DIR / "paper_submissions.json"
_CACHE_TTL_HOURS = 24
_BUCKET_CAPACITY = 5
_REFILL_RATE = 5  # tokens per minute

class _TokenBucket:
    def __init__(self, capacity: int = _BUCKET_CAPACITY, rate_per_min: int = _REFILL_RATE):
        self.capacity = capacity
        self.tokens: float = float(capacity)
        self.rate = rate_per_min / 60.0
        self._last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self._last_refill) * self.rate)
        self._last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

_buckets: dict[str, _TokenBucket] = {}

def _get_bucket(book: str) -> _TokenBucket:
    if book not in _buckets:
        _buckets[book] = _TokenBucket()
    return _buckets[book]

@dataclass
class SubmissionResult:
    contest_id: str
    book: str
    lineup_id: str
    status: str          # ACCEPTED|REJECTED|DUPLICATE|RATE_LIMITED|PAPER_OK
    submission_id: Optional[str]
    error_message: Optional[str]
    ts: str

def _auto_key(book: str, contest_id: str, lineup: dict) -> str:
    player_ids = sorted(str(p) for p in lineup.get("players", []))
    raw = f"{book}|{contest_id}|{'|'.join(player_ids)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _load_cache() -> dict:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def _save_cache(cache: dict) -> None:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_FILE.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    tmp.replace(_CACHE_FILE)

def _prune_cache(cache: dict) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_CACHE_TTL_HOURS)
    return {k: v for k, v in cache.items() if datetime.fromisoformat(v["ts"]) > cutoff}

def _cache_lookup(key: str) -> Optional[SubmissionResult]:
    cache = _prune_cache(_load_cache())
    _save_cache(cache)
    entry = cache.get(key)
    return SubmissionResult(**entry) if entry else None

def _cache_store(key: str, result: SubmissionResult) -> None:
    cache = _prune_cache(_load_cache())
    cache[key] = asdict(result)
    _save_cache(cache)

def _append_paper(record: dict) -> None:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if _PAPER_FILE.exists():
        try:
            existing = json.loads(_PAPER_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []
    existing.append(record)
    tmp = _PAPER_FILE.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    tmp.replace(_PAPER_FILE)

def _check_live_gates(book: str) -> None:
    _ERR = "live submission gates not satisfied"
    if os.environ.get("SUBMISSION_MODE", "paper").lower() != "live":
        raise PermissionError(_ERR)
    if not os.environ.get("USER_TOKEN"):
        raise PermissionError(_ERR)
    b = book.upper()
    if b == "DK" and (not _is_live_dk() or not os.environ.get("DK_API_KEY")):
        raise PermissionError(_ERR)
    elif b == "FD" and (not _is_live_fd() or not os.environ.get("FD_API_KEY")):
        raise PermissionError(_ERR)
    elif b not in ("DK", "FD"):
        raise PermissionError(_ERR)

def _validate_lineup(lineup: dict) -> Optional[str]:
    if not lineup or not isinstance(lineup, dict) or not lineup.get("players"):
        return "invalid_lineup"
    return None

_BACKOFF = [1, 2, 4, 8, 16, 32]
_MAX_RETRIES = 3

def _submit_live(book: str, contest_id: str, lineup: dict) -> SubmissionResult:
    import requests  # noqa: PLC0415
    b = book.upper()
    url = (f"https://api.draftkings.com/lineups/v1/contests/{contest_id}" if b == "DK"
           else f"https://api.fanduel.com/contest-management/v2/contests/{contest_id}/entries")
    headers = {"Authorization": f"Bearer {os.environ.get('USER_TOKEN', '')}",
               "X-Api-Key": os.environ.get(f"{b}_API_KEY", ""), "Content-Type": "application/json"}
    lid = _auto_key(book, contest_id, lineup)
    ts = datetime.now(timezone.utc).isoformat()
    last_rate = False
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(url, json=lineup, headers=headers, timeout=10)
        except requests.Timeout:
            log.warning("submit_live timeout attempt=%d", attempt + 1)
            time.sleep(min(_BACKOFF[attempt], 60))
            continue
        except requests.RequestException:
            break
        if resp.status_code == 200:
            return SubmissionResult(contest_id, book, lid, "ACCEPTED",
                                    resp.json().get("submission_id", uuid4_hex12()), None, ts)
        if resp.status_code == 429:
            last_rate = True
            time.sleep(min(_BACKOFF[attempt], 60))
            continue
        if resp.status_code in (401, 403):
            log.error("auth failure book=%s", book)
            return SubmissionResult(contest_id, book, lid, "REJECTED", None, "auth_failed", ts)
        _err_map = {409: ("DUPLICATE", None), 423: ("REJECTED", "locked"),
                    422: ("REJECTED", "invalid_lineup")}
        if resp.status_code in _err_map:
            s, e = _err_map[resp.status_code]
            return SubmissionResult(contest_id, book, lid, s, None, e, ts)
        break
    if last_rate:
        return SubmissionResult(contest_id, book, lid, "RATE_LIMITED", None, None, ts)
    return SubmissionResult(contest_id, book, lid, "REJECTED", None, "network_timeout", ts)

def _submit_paper(book: str, contest_id: str, lineup: dict) -> SubmissionResult:
    lineup_id = _auto_key(book, contest_id, lineup)
    sub_id = f"paper_{uuid4_hex12()}"
    ts = datetime.now(timezone.utc).isoformat()
    result = SubmissionResult(contest_id, book, lineup_id, "PAPER_OK", sub_id, None, ts)

    _append_paper({**asdict(result), "lineup": lineup})

    entry_fee = float(lineup.get("entry_fee", 0))
    try:
        from scripts.execute_loop.L07_pnl_ledger import place_bet, BetRow  # noqa: PLC0415
        place_bet(BetRow(book=book, market=f"dfs_lineup_{book.lower()}",
                         player=f"lineup_{lineup_id}", stat="dfs", line=0.0,
                         side="lineup", stake=entry_fee, test_mode=True,
                         notes=f"paper sub {sub_id} contest={contest_id}"))
    except Exception as exc:
        log.debug("_submit_paper: L07 unavailable: %s", exc)

    try:
        from scripts.execute_loop.L22_alerting import send_fill_alert  # noqa: PLC0415
    except ImportError:
        send_fill_alert = lambda *a, **k: None  # noqa: E731
    try:
        send_fill_alert(sub_id, book, entry_fee, "PAPER_OK")
    except Exception:
        pass

    log.info("_submit_paper: book=%s contest=%s sub_id=%s", book, contest_id, sub_id)
    return result

def uuid4_hex12() -> str:
    return uuid.uuid4().hex[:12]

def submit_lineup(
    book: str,
    contest_id: str,
    lineup: dict,
    idempotency_key: Optional[str] = None,
) -> SubmissionResult:
    book = book.lower()
    ts = datetime.now(timezone.utc).isoformat()
    lid = _auto_key(book, contest_id, lineup)

    err = _validate_lineup(lineup)
    if err:
        return SubmissionResult(contest_id, book, lid, "REJECTED", None, err, ts)

    ikey = idempotency_key or _auto_key(book, contest_id, lineup)
    cached = _cache_lookup(ikey)
    if cached:
        log.debug("submit_lineup: idempotency hit key=%s", ikey)
        return cached

    if not _get_bucket(book).consume():
        return SubmissionResult(contest_id, book, lid, "RATE_LIMITED", None, None, ts)

    mode = os.environ.get("SUBMISSION_MODE", "paper").lower()
    if mode == "live":
        _check_live_gates(book)
        result = _submit_live(book, contest_id, lineup)
    else:
        result = _submit_paper(book, contest_id, lineup)

    _cache_store(ikey, result)
    return result


def submit_batch(submissions: list[dict]) -> list[SubmissionResult]:
    results = []
    for sub in submissions:
        try:
            r = submit_lineup(sub["book"], sub["contest_id"], sub["lineup"],
                              sub.get("idempotency_key"))
        except Exception as exc:
            r = SubmissionResult(sub.get("contest_id", ""), sub.get("book", ""), "",
                                 "REJECTED", None, str(exc),
                                 datetime.now(timezone.utc).isoformat())
        results.append(r)
    return results


def cancel_submission(book: str, submission_id: str) -> bool:
    if not submission_id or submission_id.startswith("paper_"):
        return False
    if os.environ.get("SUBMISSION_MODE", "paper").lower() != "live":
        return False
    try:
        _check_live_gates(book)
    except PermissionError:
        return False
    try:
        import requests  # noqa: PLC0415
        b = book.upper()
        url = (f"https://api.draftkings.com/lineups/v1/entries/{submission_id}" if b == "DK"
               else f"https://api.fanduel.com/contest-management/v2/entries/{submission_id}")
        resp = requests.delete(url, headers={
            "Authorization": f"Bearer {os.environ.get('USER_TOKEN', '')}",
            "X-Api-Key": os.environ.get(f"{b}_API_KEY", ""),
        }, timeout=10)
        return resp.status_code in (200, 204)
    except Exception as exc:
        log.warning("cancel_submission failed: %s", exc)
        return False

def _cli_submit(args) -> None:
    if args.live:
        os.environ["SUBMISSION_MODE"] = "live"
    p = Path(args.lineup)
    if not p.exists():
        print(f"[L05] ERROR: lineup file not found: {p}"); sys.exit(1)
    result = submit_lineup(args.book, args.contest_id, json.loads(p.read_text()))
    print(f"[L05] {result.status}  sub_id={result.submission_id}  "
          f"book={result.book}  contest={result.contest_id}  err={result.error_message}")


def _cli_status(args) -> None:
    if _PAPER_FILE.exists():
        for r in json.loads(_PAPER_FILE.read_text()):
            if r.get("submission_id") == args.submission_id:
                print(f"[L05] PAPER  sub_id={r['submission_id']}  contest={r['contest_id']}  ts={r['ts']}")
                return
    print(f"[L05] {args.submission_id!r} not found in paper log")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L05_submission_engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("submit")
    ps.add_argument("--book", required=True, choices=["dk", "fd"])
    ps.add_argument("--contest_id", required=True)
    ps.add_argument("--lineup", required=True)
    ps.add_argument("--live", action="store_true")
    ps.set_defaults(func=_cli_submit)
    pst = sub.add_parser("status")
    pst.add_argument("--submission_id", required=True)
    pst.set_defaults(func=_cli_status)
    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
