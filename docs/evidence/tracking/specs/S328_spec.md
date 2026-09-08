GAP S328 | sport nba | worktree aX | log cx_s328_asof_join_falsification

**HARNESS ROW (S register; astra midday review 2026-09-08: the cheapest timestamp falsification of the
direct-state backbone). Codex PREPARES, a finisher MEASURES.** `src/`, `kernel/`, `api/` and `intel/` are
READ and IMPORT only. Build in `scripts/platformkit/ingame/` and `scripts/platformkit/eval_gate/`. NEVER
write `data/registry/`, never flip a flag, never claim an edge (calibration language only), never edit a
landed memo, `docs/evidence/HARNESS_GAPS_2026-09-03.md` or `docs/evidence/RESULTS_LEDGER_SYSTEM.md`.
Never rename or remove a sealed column (additive fields only).

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai` for every python call; batch reads; check free
RAM first). Inputs: the 313 sealed S320 attempt-2 states (`docs/evidence/harness/S320_timestamp_artifact_
audit_2026-09-08b/states.csv` once landed; else the sealed rule from that prereg), the NBA checkpoints
parquet, the landed S323 adapter contract (`scripts/platformkit/eval_gate/adapter_contract.py`,
`domains/basketball_nba/ingame_adapter.py`), the S309 mask, and the strongest recalibrated null N as
LANDED (S310 / S309 grouped-CPCV null -- the S320 verifier found S320's N was a fresh fit; this row uses the
landed identity and records its hash).

**WHY THIS ROW EXISTS.** S322 stopped simulator expansion; the replacement backbone is a direct conditional
outcome model (S321 attempt 2: logit(M0) + f(margin, remaining) + overtime). Before its numbers mean
anything, the cheapest falsification must run: replay the candidate and the landed null through an
INDEPENDENTLY REBUILT as-of join (not the predictors' internal state-time filter, which makes prefix
equality structural -- S320 verifier NEW GAP), delete future rows, recompute every aggregate, exclude
terminal states, and sweep feature delays of 0 / 30 / 60 / 120 s. Prefix deletion must be invariant;
deliberate delays may change predictions and the question is whether the calibration conclusion survives.

**PREMISE (step 0, BINDING before-condition):** show that the landed predictors filter history at state
time INTERNALLY (cite `file:line`) so that an external prefix-deletion replay is not already exercised by
any landed test; print the 313 sealed states' strata. **If a landed row already replays both models
through an external as-of join with delay sweeps, the premise is FALSE: STOP, write the memo, commit,
report PREMISE FALSE.**

METHOD:
  1. **EXTERNAL AS-OF JOIN (`s328_asof_replay.py`, <= 250 lines).** Build the feature frame for each sealed
     state from the raw parquet OUTSIDE the predictors (rows with ts <= state_ts - delay, delay in {0, 30,
     60, 120} s), validate it with the S323 contract, and call each predictor with ONLY that frame (a
     predictor that reaches for more history must fail: assert via a monkeypatched loader that records
     every row access). Exclude terminal states by the S309 mask (report n).
  2. **ARMS.** For the landed null N and, if landed by then, the S321 attempt-2 candidate (else the S320
     substitute callback, labelled): p at delay 0 (full prefix), p after deleting every row after the
     state, p at each delay. Bar: prefix deletion changes 0 predictions; any delay change must trace to a
     record inside the delay window; every row access outside the allowed frame is a VIOLATION.
  3. **CONCLUSION SURVIVAL.** For the states that carry outcomes, recompute Brier / log score per delay for
     each arm with paired game-cluster bootstrap CIs (2,000); report whether the sign of (null minus
     candidate) survives each delay (descriptive here; this row establishes no gain).
  4. **TESTS.** A planted future row is refused by the external join; a predictor that reads outside the
     frame is caught by the recording loader; the delay sweep on a 20-state construct yields the pinned
     changes.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** without received_at this falsifies ORDERING defects but
cannot verify historical availability (prospective receipt capture is the fix; never backfill invented
receipt times); 313 states are a screening.

ACCEPTANCE RULE:
  metric        = premise citations; the replay table per arm x delay (n states, n changed, max change,
                  n access violations); the conclusion-survival table with CIs; tests
  before        = prefix equality is structural inside the predictors; no external as-of replay exists
  bar           = 0 predictions changed under prefix deletion for every arm; 0 row accesses outside the
                  allowed frame (any is a VIOLATION, reported, blocks S321 scoring until fixed); every
                  delay change traced; all tests pass; 0 landed files edited
  n             = 313 sealed states x 2 arms x 4 delays
  eye check     = NONE. Say that.
  must not move = every landed number; `src/`; `data/`; the registers/ledgers; every threshold
  verdict       = **CLEAN** if the bar holds; **VIOLATION** with the list; **PARTIAL** naming what could
                  not run.
EVIDENCE: `docs/evidence/harness/S328_asof_join_falsification_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S328 | <finding with n> | <VERDICT>`) + `replay.csv`, `survival.csv`
under `docs/evidence/harness/S328_asof_join_falsification_2026-09-08/` (each <= 5 MB; integer cells
zero-padded; additive unit-suffixed columns beside any float column).
TEST: `tests/platformkit/test_s328_asof_replay.py`, alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the delays, the state list reference,
the access-recording rule, the bar), the module, the tests and the memo skeleton, and exits with the line
`agent: PREPARED FOR FINISHER` plus the exact commands; it must NOT run the replay on the parquet (Q1).
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
