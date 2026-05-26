"""probe_R26_S7_free_arb_alert_wire.py — end-to-end probe for the free-arb
critical alert wire (middle_finder_daemon -> R21_N3 alert()).

Goal
----
Prove that an injected free-arb middle, when run through one tick of
``middle_finder_daemon.loop()``, results in:

  1. exactly one CRITICAL alert fired with tag=``free_arb``
  2. headline matches the R26_S7 spec ("FREE ARB: ... — ... OVER ... / ... UNDER ...")
  3. dedup blocks the second consecutive tick of the same arb
  4. a non-free middle in the same batch does NOT fire
  5. the alert reaches the durable vault ledger + critical-stack JSON
     (via the real R21_N3 backend — no Discord URL needed)

Persists summary to ``data/cache/probe_R26_S7_results.json``.

Safety
------
* Writes go to a probe-only vault path + critical-stack dir under
  ``data/cache/probe_R26_S7/`` — production ``vault/Improvements/alerts.md``
  is left untouched.
* DISCORD_WEBHOOK_URL is stripped before the probe runs so no real network
  traffic is generated even if the env var is set.
* No daemon process is spawned. ``run_once`` is monkeypatched so no real
  CSV / model dependency is needed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import middle_finder_daemon as mfd  # noqa: E402
from src.alerts import discord_webhook as dwh  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(_ROOT, "data", "cache",
                                   "probe_R26_S7_results.json")
PROBE_VAULT_PATH = os.path.join(_ROOT, "data", "cache", "probe_R26_S7",
                                 "alerts.md")
PROBE_CRITICAL_DIR = os.path.join(_ROOT, "data", "cache", "probe_R26_S7",
                                   "critical")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fake_free_arb() -> Dict[str, Any]:
    """A synthetic primary↔primary free arb that survives the R20_M1
    + R24_Q1 classifier (both legs primary, both odds positive)."""
    return {
        "player": "Probe Player",
        "stat": "pts",
        "over_book": "fd",
        "over_line": 24.5,
        "over_price": 105,
        "under_book": "bov",
        "under_line": 25.5,
        "under_price": 110,
        "middle_width": 1.0,
        "worst_price": 105,
        "free_arb": True,
        "arb_profit_pct": 2.34,
        "market_tier": "primary",
        "is_alt_line": False,
    }


def _fake_non_free_middle() -> Dict[str, Any]:
    """Positive-EV middle but one leg has NEGATIVE odds — must not fire."""
    return {
        "player": "Filler Curry",
        "stat": "fg3m",
        "over_book": "fd",
        "over_line": 4.5,
        "over_price": -110,
        "under_book": "bov",
        "under_line": 5.5,
        "under_price": -105,
        "middle_width": 1.0,
        "worst_price": -110,
        "free_arb": False,
        "arb_profit_pct": None,
        "market_tier": "primary",
        "is_alt_line": False,
    }


def run_probe(out_json_dir: str) -> Dict[str, Any]:
    """Drive two ticks through loop(), inspect captured alert calls AND
    the durable vault/critical-stack artefacts."""
    # 1. Strip DISCORD_WEBHOOK_URL so no real network call escapes.
    prev_url = os.environ.pop("DISCORD_WEBHOOK_URL", None)

    captured: List[Dict[str, Any]] = []

    def capture_alert(message, level="info", tag=None, **kw):
        rec = {"message": message, "level": level, "tag": tag}
        rec.update({k: v for k, v in kw.items() if k in
                    ("source", "body", "fields")})
        captured.append(rec)
        # ALSO call the real layered backend so the vault + critical stack
        # get written — that's how the operator actually receives the alert.
        return dwh.alert(
            message, level=level, tag=tag,
            source=kw.get("source", "probe_R26_S7"),
            body=kw.get("body"),
            fields=kw.get("fields"),
            vault_path=PROBE_VAULT_PATH,
            critical_stack_dir=PROBE_CRITICAL_DIR,
        )

    # 2. Monkeypatch run_once to inject our fake snapshot every tick.
    def fake_run_once(date_str, min_width, max_juice, predictor=None,
                      min_band_prob=0.10):
        return [_fake_free_arb(), _fake_non_free_middle()], {}

    orig_run_once = mfd.run_once
    mfd.run_once = fake_run_once

    out_json_path = os.path.join(out_json_dir, "middles_live.json")
    os.makedirs(out_json_dir, exist_ok=True)

    raised = False
    exc_repr = None
    stats: Dict[str, Any] = {}
    try:
        # 3. Run 2 ticks back-to-back to exercise dedup.
        stats = mfd.loop(
            interval_sec=0.01, min_width=0.5, max_juice=-135, max_iters=2,
            use_model=False, out_json=out_json_path,
            log=lambda *a, **k: None,
            alert_fn=capture_alert, dedup_state={},
            dedup_ttl_sec=3600,
        )
    except Exception as exc:
        raised = True
        exc_repr = repr(exc)
        traceback.print_exc()
    finally:
        mfd.run_once = orig_run_once
        if prev_url is not None:
            os.environ["DISCORD_WEBHOOK_URL"] = prev_url

    # 4. Verify durable artefacts.
    vault_present = os.path.exists(PROBE_VAULT_PATH)
    vault_has_free_arb_line = False
    if vault_present:
        try:
            with open(PROBE_VAULT_PATH, encoding="utf-8") as fh:
                vault_text = fh.read()
            vault_has_free_arb_line = (
                "[free_arb]" in vault_text
                and "[CRITICAL]" in vault_text
                and "FREE ARB: Probe Player pts" in vault_text
            )
        except OSError:
            pass

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    critical_path = os.path.join(PROBE_CRITICAL_DIR, f"critical_{today}.json")
    critical_present = os.path.exists(critical_path)
    critical_records: List[Any] = []
    if critical_present:
        try:
            with open(critical_path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, list):
                critical_records = loaded
        except (json.JSONDecodeError, OSError):
            critical_records = []
    critical_has_free_arb = any(
        r.get("tag") == "free_arb"
        and "FREE ARB: Probe Player pts" in str(r.get("message", ""))
        for r in critical_records
    )

    # 5. Verdict
    n_alerts = len(captured)
    one_critical_with_free_arb_tag = (
        n_alerts == 1
        and captured[0]["level"] == "critical"
        and captured[0]["tag"] == "free_arb"
    )
    headline_matches_spec = (
        n_alerts >= 1
        and captured[0]["message"]
        == "FREE ARB: Probe Player pts — fd OVER 24.5@105 / bov UNDER 25.5@110"
    )
    dedup_worked = (n_alerts == 1)  # 2 ticks, same arb -> 1 alert
    non_free_skipped = not any(
        "Filler Curry" in c["message"] for c in captured
    )

    ship_ok = bool(
        not raised
        and one_critical_with_free_arb_tag
        and headline_matches_spec
        and dedup_worked
        and non_free_skipped
        and vault_has_free_arb_line
        and critical_has_free_arb
    )

    summary = {
        "probe": "R26_S7",
        "ts": _iso_now(),
        "stats": stats,
        "n_alerts_captured": n_alerts,
        "captured_first": captured[0] if captured else None,
        "dedup_worked": dedup_worked,
        "one_critical_with_free_arb_tag": one_critical_with_free_arb_tag,
        "headline_matches_spec": headline_matches_spec,
        "non_free_skipped": non_free_skipped,
        "vault_path": PROBE_VAULT_PATH,
        "vault_present": vault_present,
        "vault_has_free_arb_line": vault_has_free_arb_line,
        "critical_stack_path": critical_path,
        "critical_stack_present": critical_present,
        "critical_has_free_arb": critical_has_free_arb,
        "n_critical_records": len(critical_records),
        "raised": raised,
        "exc_repr": exc_repr,
        "ship_ok": ship_ok,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(_ROOT, "data", "cache",
                                                      "probe_R26_S7"))
    args = ap.parse_args()

    summary = run_probe(args.out_dir)

    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary.get("ship_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
