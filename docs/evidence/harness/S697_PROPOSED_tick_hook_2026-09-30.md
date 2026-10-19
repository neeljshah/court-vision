# S697 PROPOSED tick hook (NOT APPLIED) -- external dead-man ping around one S500 tick

Status: PROPOSED. paper_desk_tick.py is unchanged on branch cloud/S697-2026-09-30. The tick owner
applies this (AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md section 3b: "hooks for ... S697 ... applied by the tick owner"), after the owner
creates the external check (DESK_STATE section 6 item 11). PAPER ONLY.

Secret rule: the ping URL is set ONLY as the user-level environment variable
COURTVISION_DEADMAN_URL on the recorder. It is never written into this file, the repo, a task
definition argument, a log or chat. This document names the variable only.

## Diff (scripts/platformkit/ops/paper_desk_tick.py, main)

```diff
 def main(argv: list[str] | None = None) -> int:
     """Run one tick; --dry-run journals decisions without launching children."""
+    from scripts.platformkit.ops.deadman_ping import with_pings
+    journal = ROOT / "data/cache/paper_desk/deadman.jsonl"  # local cache on the recorder; never committed
+    return with_pings(lambda: _main(argv), journal=journal)
+
+
+def _main(argv: list[str] | None = None) -> int:
     parser = argparse.ArgumentParser(description=__doc__)
```

The journal row carries deadman_unconfigured while the variable is unset, as the row requires. The
hook uses ROOT (the module default), not --root; a journal write failure is swallowed and counted
(journal_error), never a tick failure. A missing data/cache/paper_desk directory is such a failure.

## Behaviour the hook inherits (tested in tests/platformkit/ops/test_deadman_ping.py)

- Variable unset: every ping is deadman_unconfigured, no network call; the tick code is unchanged.
- The tick's return code (0 or 2) is returned unchanged; 0 sends success, anything else sends fail.
- A tick that raises (BaseException; main() already turns Exception into 2) sends fail, then re-raises.
- One attempt per ping, no retry. Network wait added to one tick: at most 2 x (0.3 + 0.1) = 0.8 s, including explicit timeout overrides.
- Proxies bypassed; redirects not followed; errors recorded by class name only.

## Recorder half (NOT VERIFIED)

Declared check: period 30 min (the tick cadence) + grace 20 min. Acceptance on the recorder:
stopping the task produces an alert within period + grace = 50 min. Needs the owner's check,
the variable on the recorder and this hook applied. None of this ran in the cloud.
