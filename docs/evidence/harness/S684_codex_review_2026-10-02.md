5. **S684: HOLD**

   - **Inconsistent game denominator:** `scripts/platformkit/evidence/subset_census.py:105` counts distinct universe keys, while line 121 retains duplicates and line 122 uses their list length for the selection bound. Repeating a schedule game changes the reported interval without adding a game.
     **Fix:** validate nonmissing, unique game keys when loading the schedule; refuse duplicates explicitly. Add a duplicate-universe case.
   - **Registry write route:** the output guard at `scripts/platformkit/evidence/subset_census.py:205` protects only `docs/evidence/forward`; line 215 can write into `data/registry`.
     **Fix:** add lexical and resolved registry checks before writing.
   - **Windows replacement risk:** `scripts/platformkit/evidence/subset_census.py:216` uses bare `os.replace`.
     **Fix:** use the existing durable retry helper.

   The Decimal reconstruction, unequal-tick game weighting, bucket boundaries and WITHHELD cases are substantive tests. They do not cover duplicate universe keys.

| private/cloud/S684-2026-09-30 | HOLD | None | Duplicate games alter bound denominator | S |

Windows symlink tests also need explicit capability handling: S678 at `tests/platformkit/eval_gate/test_corpus_manifest.py:265`, S682 at `tests/platformkit/ops/test_power_ledger_s682.py:268`, and S684 at `tests/platformkit/evidence/test_subset_census.py:288` create links unconditionally. Without Windows symlink privileges, they fail before exercising their assertions. Preserve deterministic mocked link/reparse coverage if integration cases are capability-gated.

**LANDING ORDER:** Land S679 now. After corrections and fresh per-file Windows verification, use S678, S682, S683, S684, S685, S686, S687. There is no mandatory runtime dependency between these eight branches; coordinate the shared oracle initializer. Keep S678's real three-day acceptance open after its tooling lands.
