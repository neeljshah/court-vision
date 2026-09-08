GAP S317 | sport nba | worktree a4 | log cx_s317_series_schema

**HARNESS ROW (S register).** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/ingame/` and `scripts/platformkit/eval_gate/`. NEVER write `data/registry/`, never
flip a flag, never claim an edge (calibration language only), never edit a landed memo or artifact,
`docs/evidence/HARNESS_GAPS_2026-09-03.md` or `docs/evidence/RESULTS_LEDGER_SYSTEM.md` (the lander appends;
put the proposed ledger line in the memo).

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line -- this box has
more than one interpreter). No pod, no GPU.

**WHY THIS ROW EXISTS.** S287's per-game paired-loss series
(`docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_per_game_paired_loss_series.csv`)
stores a state key such as `401809239:120` in its `timestamp` field and carries no probabilities or
outcomes, so simulator ECE cannot be recomputed from it alone (verifier NEW GAP, S287). And the S92/S294
archives were staged at `/workspace/wt/<wt>/data/cache/eval_gate/` instead of the preregistered scratch
`inputs/` location, so a prereg cannot be checked against where bytes actually went. Both are schema and
rule gaps that make landed numbers less recomputable.

**PREMISE (step 0, BINDING before-condition):** open the S287 per-game series and PRINT its header and
first 3 rows; confirm that (a) the `timestamp` column holds `<game_id>:<elapsed>` keys and (b) no
probability or outcome column exists, so ECE is not recomputable from the file. Then list the S287
memo's staging paths vs its prereg's `inputs/` rule. **If the series already carries probabilities and
outcomes, the premise is FALSE for (a): report and continue with (b) only.**

METHOD:
  1. **SERIES SCHEMA v2 (additive).** A writer `scripts/platformkit/ingame/series_schema.py` (<= 200
     lines) that emits the per-game series with: `game_id`, `elapsed_s` (int), `timestamp_utc` (the real
     tick time when known, else null with `timestamp_reason`), `p_market`, `p_null`, `p_simulator`,
     `outcome` (0/1), `loss_market`, `loss_null`, `loss_simulator`, plus the legacy `timestamp` key
     column retained verbatim for readers that parse it. A reader that accepts both v1 and v2 (v1 rows
     yield null probabilities) and a recomputation function for Brier and ECE (the S287 binning) from a
     v2 file. Existing S287 files are NOT rewritten: regenerate a v2 series from S287's committed
     `S287_selected_tick_series.csv` + `S287_summary.json` if the ticks carry the needed fields (say
     which), write it as a NEW artifact under `docs/evidence/harness/S317_series_schema_2026-09-08/`, and
     show the recomputed Brier/ECE equal S287's memo numbers to 1e-9 (n=2,130) -- that is the check.
  2. **ARCHIVE LOCATION RULE.** Add to the prereg template used by the S lanes (find it: grep the specs
     for `inputs/`; if none exists, write `docs/evidence/harness/PREREG_ARCHIVE_RULE.md`, <= 30 lines) the
     rule: a prereg names the exact scratch path where inputs are staged; the memo prints the realised
     path; a harness check `scripts/platformkit/eval_gate/archive_path_check.py` (<= 120 lines) compares
     the two and reports MATCH / MISMATCH / UNSTATED per artifact. Run it over S287 and S308 attempt 2
     memos and report the table with n.
  3. **TESTS.** Per-file test: v1 and v2 round trips; the recomputation on a hand-pinned 12-tick construct
     (known Brier/ECE); the archive check on constructed memo/prereg pairs.
  4. CHANGE NOTHING ELSE; no landed file edits.

**HONEST LIMITATIONS to state, not discover:** a v2 regenerated from S287's ticks is only as complete as
those ticks; real tick timestamps may be unavailable (null with reason); the archive rule cannot check
landed rows retroactively beyond reporting UNSTATED.

ACCEPTANCE RULE:
  metric        = the premise prints; the v2 schema + reader + recomputation; the S287 recomputation
                  equality (Brier, ECE, n=2,130) to 1e-9; the archive rule + check with its S287/S308
                  table
  before        = the series cannot recompute ECE alone; no archive-path rule or check
  bar           = recomputation matches S287's memo numbers to 1e-9 on the regenerated v2 (or the memo
                  states exactly which fields the ticks lack, with n); the check runs on both memos; all
                  tests pass; 0 landed files edited
  n             = 2,130 ticks; every artifact named by the two memos
  eye check     = NONE. Say that.
  must not move = every S287 number; every landed artifact; `src/`; `data/`; the registers/ledgers
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/harness/S317_series_schema_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S317 | <finding with n> | <VERDICT>`) + the v2 series and the archive
check table under `docs/evidence/harness/S317_series_schema_2026-09-08/` (each file <= 5 MB).
TEST: `tests/platformkit/test_s317_series_schema.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08

---
**VERSION 2026-09-08b (orchestrator amendment after codex attempt 1 stopped on a missing path).** The
S308 attempt-2 memo is not landed yet (its pod scorer is still running). METHOD step 2 is amended: run
the archive-path check over every memo PRESENT on master among `docs/evidence/harness/S287_*.md`,
`S287_repeatability_*.md`, `S293_*.md`, `S296_*.md`, `S298_*.md`, `S309_*.md`, `S310_*.md`, `S313_*.md`
(list them with `ls`); a memo named in the rule that is absent is reported as ABSENT in the table (n),
never a stop. Everything else stands. A missing `data/registry` in the worktree is expected (local-only
tree; never write it).
