- **S697 -- HOLD.** The row requires a network error to leave the tick unchanged within one second. Two sequential pings can each wait 3.5 seconds (`deadman_ping.py:37-39,147-150,165-177`); the proposed hook acknowledges seven seconds (`docs/evidence/harness/S697_PROPOSED_tick_hook_2026-09-30.md:34`). The timing test covers immediate errors, not a silent endpoint at the default timeout (`test_deadman_ping.py:155-164`). Meet the one-second bound and test that case.

| S697 | HOLD | None | Seven-second worst case exceeds row bound | M |
