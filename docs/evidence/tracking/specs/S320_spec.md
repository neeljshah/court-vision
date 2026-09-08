GAP S320 | sport nba | worktree a16 | log cx_s320_timestamp_artifact_audit

**HARNESS ROW (S register; astra 2026-09-08 "biggest risk, cheapest two-hour falsification").** `src/`,
`kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/ingame/` and
`scripts/platformkit/eval_gate/`. NEVER write `data/registry/`, never flip a flag, never claim an edge
(calibration language only), never edit a landed memo or artifact, `docs/evidence/HARNESS_GAPS_2026-09-03.md`
or `docs/evidence/RESULTS_LEDGER_SYSTEM.md` (the lander appends; put the proposed ledger line in the memo).

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line). Input:
`data/cache/inplay_odds/nba_checkpoints_full.parquet` (465,249 ticks / 1,593 games; read columns, never a
whole-store load over 300 MB) plus the landed S309 canonical-loss module and the S310 / S309 recalibrated
null. Cached predictions only: NO new model is fit beyond the train-only null.

**WHY THIS ROW EXISTS.** S309 measured 244,183 terminal-like zero-clock ticks inside the s86 denominator and
S277's "stale" ticks were almost all zero-clock. The program's biggest risk is that apparent in-game state
information is a TIMESTAMP / SETTLEMENT ARTIFACT (future records, terminal states, wrong-target sides,
duplicate keys), so that a clean input adds nothing over the recalibrated null. Before any per-sport model
row (S321+) is scored, this row proves the replay path cannot see the future.

**PREMISE (step 0, BINDING before-condition):** print the parquet's columns, n ticks, n games, n seasons,
the status/active mask fields the S309 module uses, and the share of ticks with clock == 0 (n). **If a
landed row already replays a frozen model with future records deleted and delayed availability and reports
zero violations with n, the premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **SEAL 100 game/state pairs** (prereg: seed, strata = period x |margin| bucket {0-3, 4-9, 10+} x clock
     bucket {> 300 s, 60-300 s, < 60 s, == 0}, at least 5 per non-empty stratum; the exact (game_id,
     state_ts) list with a digest) BEFORE any audit.
  2. **AUDIT each pair (`s320_state_audit.py`, <= 250 lines):** availability (every feature the null reads at
     the state has `received_at`/tick time <= prediction time; if the parquet lacks a received-at field,
     say so and audit tick-order only); status (active vs terminal per the S309 mask); target polarity
     (home-win probability and the side/venue columns agree; paired sides merged); duplicate (game_id,
     state_ts) keys (S301 guard); settlement (the outcome is known only after the final tick). Table with n
     per stratum and per check: ACCEPTED / VIOLATION with the reason.
  3. **REPLAY.** For the recalibrated null N (train-only, chronological folds, whole-game grouping, 24 h
     embargo) and the market prior M0: predict each sealed state (a) with the full history, (b) with every
     record after the state deleted, (c) with event availability delayed by 60 s (features available only
     from records >= 60 s old). Bar: max |p_b - p_a| == 0 and max |p_c - p_a| explained only by the delayed
     records (report it; a change with NO record inside the 60 s window is a violation).
  4. **REPORT** the violation counts (n) by check and stratum, the prefix deltas, and the list of violating
     states; a `--report` CSV. Paired game CIs are descriptive here (this row establishes no gain).
  5. **TESTS.** Synthetic: a planted future record changes the full-history prediction but not the truncated
     one (the harness must flag it); a terminal state is rejected; a duplicate key is rejected; a clean
     construct passes every check.
  6. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** timestamp-only validation cannot certify a feed that
retrospectively overwrites its own records; 100 states are a screening; a clean audit is not a gain.

ACCEPTANCE RULE:
  metric        = premise prints; the sealed list; the audit table (n per check x stratum); the replay
                  deltas (max, n changed) for N and M0; tests
  before        = no sealed audit of availability / status / polarity / duplicates with replay exists
  bar           = 0 accepted future, terminal or wrong-target states among the 100 (any violation is
                  listed and BLOCKS scoring rows until fixed -- an honest VIOLATION verdict is a success);
                  0 prefix prediction changes under (b); every (c) change traced to a record in the window;
                  all tests pass; 0 landed files edited
  n             = 100 sealed states; every check; 2 models
  eye check     = NONE. Say that.
  must not move = every landed number; `src/`; `data/`; the registers/ledgers; every threshold
  verdict       = **CLEAN** if the bar holds; **VIOLATION** with the list (this blocks S321+ scoring until
                  the named fix lands); **PARTIAL** with the check that could not run and why.
EVIDENCE: `docs/evidence/harness/S320_timestamp_artifact_audit_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S320 | <finding with n> | <VERDICT>`) + `states.csv`, `audit.csv`,
`replay.csv` under `docs/evidence/harness/S320_timestamp_artifact_audit_2026-09-08/` (each <= 5 MB; integer
cells zero-padded to 6 digits).
TEST: `tests/platformkit/test_s320_state_audit.py`, alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: seed, strata, the 100-state rule, the
checks, the delay window), the audit module, the tests and the memo skeleton, and exits `PREPARED FOR
FINISHER` with the exact commands; it must NOT run the audit on the parquet itself (Q1). A missing
`data/registry` in the worktree is expected; an absent parquet is reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
