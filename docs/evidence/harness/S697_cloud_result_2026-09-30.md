# S697 cloud result -- external dead-man ping (2026-09-30)

Row: S697 (AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md section 2; register line is a pointer only).
Run: cloud routine desk-improve, ONE-OFF OVERRIDE pinned to S697 (architecture doc section 3a).
Branch: cloud/S697-2026-09-30 (from trunk bb34a09c). NOT landed; the register and DESK_STATE.md
were NOT edited on this branch. PAPER ONLY. This is ops tooling: no score, no metric, nothing to claim.

## Premise (Q8)

Before the build, `grep -rni "deadman\|dead_man" scripts/platformkit tests/platformkit` on trunk
bb34a09c returned 0 hits. The contract verifier re-measured the same thing with `git grep` and got
0 files. The premise holds.

## What was built (new files only; no existing file edited)

- `scripts/platformkit/ops/deadman_ping.py` (194 lines, stdlib only). It sends start, success and
  fail pings to a URL read ONLY from the environment variable `COURTVISION_DEADMAN_URL`.
  - The row does not name a variable. The spec declares this one, and the contract tier judged
    that consistent with the row.
  - If the variable is unset or blank, the result is deadman_unconfigured and no network call is
    made.
  - Each ping makes exactly one attempt: no retry, no sleep loop.
  - Proxies are bypassed and redirects are not followed.
  - The wall-clock bound is timeout_s + 0.5 s. timeout_s must be in (0, 10]; anything else falls
    back to 3.0.
  - Errors are recorded by class name only, and the URL never reaches any output.
  - `with_pings(tick)` returns the tick's code unchanged.
  - The CLI prints one JSON line and exits 0.
  - The code has two decision values the spec did not list: `deadman_invalid_kind` and
    `deadman_internal_error`. They are declared here; nothing reads them yet.
- `tests/platformkit/ops/test_deadman_ping.py` (288 lines) and the helper
  `tests/platformkit/ops/_deadman_loopback.py` (81 lines): a raw 127.0.0.1 server only.
- `docs/evidence/harness/S697_spec_2026-09-30.md`: the spec plus AMENDMENT 1.
- `docs/evidence/harness/S697_PROPOSED_tick_hook_2026-09-30.md`: the PROPOSED diff for
  paper_desk_tick.main. It is NOT applied, and paper_desk_tick.py is byte-identical to trunk.

## Tiers (every sub-agent was a separate Opus agent; codex is not available here)

| tier | who | verdict | items |
|---|---|---|---|
| pre-build critic (astra) | independent Opus sub-agent | REVISE | 16 items, all folded into the spec as AMENDMENT 1 (the bar was only tightened) |
| CONTRACT (A/B/Q + spec + AMENDMENT 1) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS | 2 corrections, 8 follow-ups |
| ADVERSARIAL (15 listed mutants + 15 extra + probes) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS | 4 corrections, 4 follow-ups; 0 blocking |

### Corrections applied after the tiers

These are in commit 5c574bed and the final commit. Each test added below is red on its mutant,
re-run by the builder.

1. **Contract 1 / adversarial 7:** this memo now exists.
2. **Contract 2:** the PROPOSED hook now passes `journal=` by default, so an unset variable
   journals deadman_unconfigured, as the row says.
3. **Adversarial 2 / contract 3, spec A5:** test_a5 injects KeyboardInterrupt into the worker.
   Mutant "worker catches Exception" is now RED (it was green).
4. **Adversarial 3 / contract 4, spec A8:** test_a8 uses a bigbody server that declares 100000
   bytes and sends 2048. Mutant "read() with no cap" is now RED.
5. **Adversarial 4 / contract 5, spec A12:** test_a12 checks that an env whose get() raises
   RuntimeError gives deadman_internal_error, and that KeyboardInterrupt propagates. Mutant
   "ping catches BaseException" is now RED.
6. **Contract 6:** the C10 "://" and domain grep now also scans `_deadman_loopback.py`.
7. **Adversarial 5 and 6 (follow-ups, taken):** the tick call counter makes mutant "tick called
   twice" RED, and recording the HTTP method makes mutant "POST instead of GET" RED.

### Not changed, on purpose

- **Adversarial 1:** it asked to relax the c14 bound (elapsed < 1.0 s; about 0.80 s by
  construction). That bound is the spec's own bar (AMENDMENT 1 A8), and Q3 forbids moving it.
  The flake risk is recorded here instead. In the verifier's 5 runs plus the builder's runs,
  c14 measured 0.80 s with no failure. On a loaded box this test may go red for timing, not for
  logic.
- **Contract 7:** argparse exits 2 on an invalid `--kind`. C12 requires exit 0 only for a valid
  invocation: variable unset, set, or failing.
- **Contract 9:** there is a second BaseException catch, around HTTPError.close(). It is inside
  the worker thread, where A5 requires one.
- **Adversarial 8:** after the wall-clock bound, the daemon worker keeps its socket open until
  the socket timeout or process exit. That is harmless for a one-shot tick process. It is noted
  in case ping() is ever used from a long-lived process.
- **Adversarial 5:** with_pings(tick returning None) sends fail. paper_desk_tick.main always
  returns an int.

## Test commands (per file, this box: Ubuntu, Python 3.11.15)

- `python3 tools/desk_bin/run_files.py . tests/platformkit/ops/test_deadman_ping.py`: 24 passed
- `python3 -m pytest tests/platformkit/ops/test_deadman_ping.py -q`: 24 passed (about 2.7 s)
- `python3 tools/desk_bin/run_files.py . tests/platformkit/test_loc_rail_scope.py`: 1 passed
- Fails on the old code: with deadman_ping.py removed, the test file errors at collection.
- Before the corrections, the tiers observed 21 passed on dc1bcbbe, including 5 extra runs
  without a flake. The adversarial tier caught every listed mutant except m12, which is now
  fixed. Its probes found nothing escaping ping() or with_pings, and no token in any output
  surface across odd URLs, server behaviours, kinds, timeouts, journals and 20 concurrent pings.

## Must not move

`git diff bb34a09c` touches only new files. These are byte-identical to trunk:

- paper_desk_tick.py
- docs/evidence/HARNESS_GAPS_2026-09-03.md
- docs/operations/DESK_STATE.md
- every seal-pinned file

None of the new paths appears in any docs/evidence/forward/**/PREREG*.json. No bar was moved.

## Secrets

The files hold no URL, hostname or token. The only token is the synthetic test string. Loopback
URLs are built at run time from "http", a separator and 127.0.0.1. No external host was contacted
from this box.

## NOT VERIFIED

- **The owner's external check:** not created. The variable is not set on the recorder. Owner
  step: DESK_STATE section 6 item 11.
- **The tick hook:** PROPOSED only, not applied, and never run on the recorder's Windows tick.
- **A real alert:** stopping the task on the recorder should alert within period 30 min + grace
  20 min = 50 min. This needs the check, the variable and the hook.
- **Other interpreters:** Windows and Python 3.10 (the recorder) were not tested. Only
  Python 3.11 on Ubuntu ran.
- **IPv6 loopback:** not probed; this box has no IPv6.

PORTABLE: yes (code and construct tests). The recorder half is OWNER / WINDOWS.
