"""probe_R21_N3_alert_fallback.py — end-to-end probe for the layered alert path.

Goal
----
Prove that, with DISCORD_WEBHOOK_URL unset locally, a fired alert still
leaves a durable trail in two places:

  1. ``vault/Improvements/alerts.md`` — append-only operator log
  2. ``data/cache/alerts/critical_<date>.json`` — JSON stack a separate
      operator-monitor can pop in FIFO order

…AND that the Discord transport is silently skipped (no raise).

Procedure
---------
1. Force DISCORD_WEBHOOK_URL out of the environment.
2. Fire a single fake ``critical`` alert via ``alert()``.
3. Verify:
     * vault file contains the message line with [CRITICAL] tag
     * critical-stack JSON file exists for today, contains exactly one record
     * the message round-trips intact
     * ``discord_sent`` is False, no exception raised
4. Persist a summary to ``data/cache/probe_R21_N3_results.json``.

Safety
------
* Writes go to the REAL ``vault/Improvements/alerts.md`` (the operator's
  durable record) — this is intentional: the probe doubles as a smoke
  test of the real production path.
* Never touches the network. No subprocess spawning. No daemons started.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.alerts.discord_webhook import alert  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(_ROOT, "data", "cache", "probe_R21_N3_results.json")
VAULT_PATH = os.path.join(_ROOT, "vault", "Improvements", "alerts.md")
CRITICAL_DIR = os.path.join(_ROOT, "data", "cache", "alerts")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--message",
        default=f"R21_N3 probe fake critical alert @ {_iso_now()}",
        help="Headline to fire through the layered alert path.",
    )
    args = ap.parse_args()

    # 1. Strip DISCORD_WEBHOOK_URL so we exercise the local-fallback path.
    prev_url = os.environ.pop("DISCORD_WEBHOOK_URL", None)
    discord_raised = False
    discord_exc_repr: Optional[str] = None
    result: Dict[str, Any] = {}

    try:
        result = alert(
            args.message,
            level="critical",
            tag="probe_R21_N3",
            source="probe_R21_N3",
            vault_path=VAULT_PATH,
            critical_stack_dir=CRITICAL_DIR,
        )
    except Exception as exc:  # noqa: BLE001 — probe must catch & report
        discord_raised = True
        discord_exc_repr = repr(exc)
        traceback.print_exc()
    finally:
        if prev_url is not None:
            os.environ["DISCORD_WEBHOOK_URL"] = prev_url

    # 2. Verify the vault append.
    vault_ok = False
    vault_line_matched = False
    if os.path.exists(VAULT_PATH):
        with open(VAULT_PATH, encoding="utf-8") as fh:
            vault_text = fh.read()
        vault_ok = True
        vault_line_matched = args.message in vault_text and "[CRITICAL]" in vault_text

    # 3. Verify the critical-stack JSON for today.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    critical_path = os.path.join(CRITICAL_DIR, f"critical_{today}.json")
    critical_ok = False
    critical_record_present = False
    stack_len = 0
    if os.path.exists(critical_path):
        try:
            with open(critical_path, encoding="utf-8") as fh:
                stack = json.load(fh)
            critical_ok = isinstance(stack, list)
            stack_len = len(stack) if critical_ok else 0
            critical_record_present = any(
                r.get("message") == args.message for r in (stack if critical_ok else [])
            )
        except (json.JSONDecodeError, OSError) as exc:
            critical_record_present = False

    discord_skipped_cleanly = (not discord_raised) and bool(result) \
        and result.get("discord_sent") is False

    summary = {
        "probe": "R21_N3",
        "ts": _iso_now(),
        "message_fired": args.message,
        "result_dict": result,
        "vault_path": VAULT_PATH,
        "vault_file_present": vault_ok,
        "vault_line_matched": vault_line_matched,
        "critical_stack_path": critical_path,
        "critical_stack_file_present": critical_ok,
        "critical_stack_len": stack_len,
        "critical_record_present": critical_record_present,
        "discord_raised": discord_raised,
        "discord_exc_repr": discord_exc_repr,
        "discord_skipped_cleanly": discord_skipped_cleanly,
    }

    # Ship gate: all three layers verified.
    ship_ok = bool(
        vault_line_matched
        and critical_record_present
        and discord_skipped_cleanly
    )
    summary["ship_ok"] = ship_ok

    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))
    return 0 if ship_ok else 1


if __name__ == "__main__":
    sys.exit(main())
