3. **S682: HOLD**

   - **Stale premise silently omits a sealed estimand:** `scripts/platformkit/ops/power_ledger.py:51` permanently declares S644 unsealed; line 156 returns `NOT_SEALED` without consulting disk. Master now has S644's sealed prereg: `docs/evidence/forward/late_game/PREREG_R2.json:102`, with its seal at line 109.
     **Fix:** resolve S644's existing prereg and report its sealed population/floor; preserve the separately declared sport populations.
   - **Test entrenches the stale premise:** `tests/platformkit/ops/test_power_ledger_s682.py:137` requires S644 to remain `NOT_SEALED`, even when its prereg exists.
     **Fix:** construct both absent and present S644 prereg cases instead of asserting permanent absence.
   - **Malformed input becomes successful empty evidence:** `scripts/platformkit/ops/power_ledger.py:224` converts a list or null accrual document into no estimands; the CLI can then write a successful ledger.
     **Fix:** reject non-object top-level accrual before extracting `estimands`; test exit 2 and no artifact.
   - **Finite input can produce non-finite output:** `scripts/platformkit/ops/power_ledger.py:100` can overflow while summing finite differences. Serialization at line 262 sits outside the refusal handler.
     **Fix:** refuse non-finite intermediate/final MDE values and include serialization in the CLI refusal boundary. Add a finite-overflow case.

   The rounding and projection tests otherwise discriminate meaningful arithmetic errors.

Windows symlink tests also need explicit capability handling: S678 at `tests/platformkit/eval_gate/test_corpus_manifest.py:265`, S682 at `tests/platformkit/ops/test_power_ledger_s682.py:268`, and S684 at `tests/platformkit/evidence/test_subset_census.py:288` create links unconditionally. Without Windows symlink privileges, they fail before exercising their assertions. Preserve deterministic mocked link/reparse coverage if integration cases are capability-gated.
| private/cloud/S682-2026-09-30 | HOLD | S644, already on master | Sealed S644 reported unsealed | M |
**LANDING ORDER:** Land S679 now. After corrections and fresh per-file Windows verification, use S678, S682, S683, S684, S685, S686, S687. There is no mandatory runtime dependency between these eight branches; coordinate the shared oracle initializer. Keep S678's real three-day acceptance open after its tooling lands.
