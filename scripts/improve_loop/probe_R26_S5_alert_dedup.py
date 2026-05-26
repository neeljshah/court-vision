"""probe_R26_S5_alert_dedup.py — flapping-daemon simulation for the R26_S5
rate-limit + de-duplication layer.

Goal
----
Prove that when a daemon flaps red repeatedly (e.g. ``middle_finder``
crash-looping every 30s), the layered alert path:

  1. fires only the per-level cap of fires per dedup window;
  2. accumulates suppressed_count for every additional fire;
  3. emits a meta-alert every Nth suppression so the operator is never
     completely deaf to a persistent issue;
  4. persists state to ``data/cache/alerts/alert_dedup_state.json`` so a
     daemon restart does not "reset" the suppression.

Procedure
---------
1. Strip ``DISCORD_WEBHOOK_URL`` and pin every layer path to a hermetic
   tmp directory so the probe never touches production vault / critical
   stack files.
2. Flush dedup state so the run is deterministic.
3. Fire 50 IDENTICAL ``warn`` alerts (simulating 50 crash-loop
   restarts in a row).
4. Count fires / suppressions / meta-alerts via the returned dicts.
5. Verify state is present on disk and matches the in-memory tallies.
6. Persist a summary to ``data/cache/probe_R26_S5_results.json``.

Safety
------
* Pure local. No network. No subprocess spawning.
* All side-effect paths pinned to a ``tempfile.mkdtemp()`` directory so
  the probe never pollutes the real operator vault.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.alerts.discord_webhook import (  # noqa: E402
    alert,
    flush_dedup,
    get_dedup_stats,
)

PROBE_RESULTS_PATH = os.path.join(_ROOT, "data", "cache", "probe_R26_S5_results.json")

# Per-level cap that this probe expects to see in production. Mirrors
# ``_DEDUP_LEVEL_CAPS`` in src/alerts/discord_webhook.py. If the source
# changes the cap, update both sides.
EXPECTED_WARN_CAP = 3
EXPECTED_META_EVERY = 10


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fires", type=int, default=50,
                    help="Number of identical alerts to fire.")
    ap.add_argument(
        "--message",
        default=(
            "watchdog restarted middle_finder daemon "
            "(simulated R26_S5 crash loop)"
        ),
        help="Alert message body to spam.",
    )
    args = ap.parse_args()

    tmpdir = tempfile.mkdtemp(prefix="probe_R26_S5_")
    vault_path = os.path.join(tmpdir, "alerts.md")
    critical_dir = os.path.join(tmpdir, "critical")
    fallback_path = os.path.join(tmpdir, "discord_fallback.jsonl")
    dedup_path = os.path.join(tmpdir, "alert_dedup_state.json")

    prev_url = os.environ.pop("DISCORD_WEBHOOK_URL", None)
    flush_dedup(dedup_path)

    fires = 0
    suppressed = 0
    meta_fires = 0
    error_repr: str = ""
    raised = False

    fire_count_seen: List[int] = []
    suppressed_seen: List[int] = []

    try:
        for _ in range(args.fires):
            r = alert(
                args.message,
                level="warn",
                tag="middle_finder_watch",
                source="probe_R26_S5",
                vault_path=vault_path,
                critical_stack_dir=critical_dir,
                fallback_path=fallback_path,
                dedup_state_path=dedup_path,
            )
            if r.get("suppressed"):
                suppressed += 1
            else:
                fires += 1
            if r.get("meta_alert_fired"):
                meta_fires += 1
            fire_count_seen.append(int(r.get("fire_count", 0)))
            suppressed_seen.append(int(r.get("suppressed_count", 0)))
    except Exception as exc:  # noqa: BLE001
        raised = True
        error_repr = repr(exc)
        traceback.print_exc()
    finally:
        if prev_url is not None:
            os.environ["DISCORD_WEBHOOK_URL"] = prev_url

    # Verify dedup sidecar is present + non-empty.
    sidecar_ok = os.path.exists(dedup_path)
    sidecar_payload: Dict[str, Any] = {}
    if sidecar_ok:
        try:
            with open(dedup_path, encoding="utf-8") as fh:
                sidecar_payload = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            sidecar_ok = False
            error_repr = f"sidecar read failed: {exc!r}"

    sidecar_entries = sidecar_payload.get("entries", {}) if sidecar_ok else {}
    sidecar_one_key = isinstance(sidecar_entries, dict) and len(sidecar_entries) == 1

    stats = get_dedup_stats(dedup_path)

    # Vault should contain exactly EXPECTED_WARN_CAP copies of the main
    # message PLUS at least one meta-alert line.
    vault_msg_count = 0
    vault_meta_count = 0
    if os.path.exists(vault_path):
        with open(vault_path, encoding="utf-8") as fh:
            vault_text = fh.read()
        vault_msg_count = vault_text.count(args.message)
        vault_meta_count = vault_text.count(
            "identical alerts suppressed in last hour"
        )

    expected_meta = max(suppressed // EXPECTED_META_EVERY, 0)

    summary = {
        "probe": "R26_S5",
        "ts": _iso_now(),
        "fires_attempted": args.fires,
        "fires_in_simulation": fires,
        "suppressed_in_simulation": suppressed,
        "meta_alerts_in_simulation": meta_fires,
        "expected_warn_cap": EXPECTED_WARN_CAP,
        "expected_meta_count": expected_meta,
        "dedup_state_path": dedup_path,
        "sidecar_present": sidecar_ok,
        "sidecar_one_key": sidecar_one_key,
        "dedup_stats": stats,
        "vault_path": vault_path,
        "vault_main_message_count": vault_msg_count,
        "vault_meta_line_count": vault_meta_count,
        "raised": raised,
        "error_repr": error_repr,
        "tmpdir": tmpdir,
    }

    ship_ok = bool(
        not raised
        and fires == EXPECTED_WARN_CAP
        and suppressed == args.fires - EXPECTED_WARN_CAP
        and meta_fires == expected_meta
        and meta_fires >= 1
        and sidecar_one_key
        and vault_msg_count == EXPECTED_WARN_CAP
        and vault_meta_count == expected_meta
    )
    summary["ship_ok"] = ship_ok

    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))
    return 0 if ship_ok else 1


if __name__ == "__main__":
    sys.exit(main())
