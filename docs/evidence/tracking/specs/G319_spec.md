GAP G319 | sport all | worktree a13 | log cx_g319_census_recomputable

**TOOLING + EVIDENCE-HYGIENE ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ only. Build in
`scripts/platformkit/`. NEVER edit a committed evidence hash, a committed evidence artifact, a landed memo,
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.** Landed memos are FROZEN: this row
ADDS a dated sweep memo and a harness check; it rewrites nothing.

**WHERE THIS ROW RUNS:** LOCAL only. No pod, no GPU, no video. Everything this row reads is committed bytes
on master.

**WHY THIS ROW EXISTS.** Repeated-census claims are not artifact-recomputable: G317 reported a 56/58/58
ledger-row sequence but committed only the final 58-row snapshot, so two of the three counts in its memo
cannot be recomputed from committed bytes. The same defect was suspected in the other 2026-09-07 census
memos (G309, G312, G313, S314) and the rule was never written down. Since then, G329 attempt 1 hit exactly
this (its 184-row snapshot was not retained; fix 1b had to re-snapshot at 201 rows and attempt 2 at 224),
and G327 attempt 2 found that attempt 1's frame snapshot existed only in memory. The register needs a
binding rule plus an automated check, and a sweep that says per memo which counts ARE recomputable.

**PREMISE (step 0, BINDING before-condition):** open `docs/evidence/tracking/g317*` (memo + artifacts) on
master and show, by listing the committed artifacts and their row counts, that the 56 and the first 58 of
the 56/58/58 sequence have NO committed snapshot behind them. PRINT the artifact list with row counts.
**If every count in the G317 memo is recomputable from committed bytes, the premise is FALSE: STOP, write
the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **THE RULE (write it, do not restate it elsewhere).** `docs/evidence/tracking/CENSUS_RULE.md` (<= 40
     lines): every count a memo reports over a mutable source (a ledger, a corpus listing, a job root, a
     log) must be recomputable from a committed snapshot of that source at the time of the count, or from a
     committed hash-chained snapshot list (sha256 + row count + timestamp per snapshot) when the bytes are
     too large to commit (> 5 MB per file: commit the projection of the columns the count uses). A count
     with neither is reported as NOT RECOMPUTABLE in the memo, never silently. Snapshots are taken AFTER the
     prereg seal (Q1) and BEFORE the count (the count is computed from the snapshot, not the live source).
  2. **THE CHECK (harness).** `scripts/platformkit/tracking/census_recomputable.py` (<= 200 lines): given a
     memo path, extract every `<int>/<int>` and `n = <int>` style count that names a source (ledger rows,
     files, frames, clips) and every committed artifact the memo names, and report per count whether a
     committed artifact reproduces it (by recount of CSV/JSONL rows, or by a snapshot-list entry) -- verdict
     RECOMPUTABLE / NOT RECOMPUTABLE / UNPARSED, with the artifact used. Heuristic parsing is acceptable;
     say what it cannot parse. One per-file test on a synthetic memo + artifacts (hand-pinned).
  3. **THE SWEEP.** Run the check over the 2026-09-07 census memos (G309, G312, G313, G317, S314) and the
     2026-09-08 ones (G329 attempts 1 and 2, G327 attempts 1 and 2, G330 attempts 1 and 2, G310 attempt 2,
     G331) on master. Report the table: memo, counts found, RECOMPUTABLE, NOT RECOMPUTABLE (which), UNPARSED,
     n. This is the finding; it changes no landed memo. For each NOT RECOMPUTABLE count, name the owning row
     so its status cell can carry the caveat (the orchestrator edits the register, not this row).
  4. **CHANGE NOTHING ELSE.** No landed memo edit, no register edit, no threshold, no artifact edit.

**HONEST LIMITATIONS to state, not discover:** the check parses prose heuristically and will miss counts
written in words; a RECOMPUTABLE verdict means a committed artifact reproduces the number, not that the
number is right; the rule cannot retroactively create snapshots for landed rows -- their caveats are the
deliverable.

ACCEPTANCE RULE:
  metric        = the premise artifact list for G317; CENSUS_RULE.md; the check + test; the sweep table
                  with n per memo
  before        = no written census rule; no automated check; G317's 56 and first 58 have no committed
                  snapshot
  bar           = the sweep covers every listed memo (none skipped; a memo the parser cannot handle is
                  reported UNPARSED with the reason); the check's test pins RECOMPUTABLE and NOT
                  RECOMPUTABLE on a construct; 0 landed files modified
  n             = the listed memos (exhaustive; Q7); every count the parser finds
  eye check     = NONE. Say that.
  must not move = every landed memo and artifact; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`;
                  `src/`, `domains/`, `api/`, `kernel/`, `intel/`; `data/`; the pod
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g319_census_recomputable_2026-09-08.md` (<= 60 lines) with VERDICT on
line 1, the premise list, the sweep table, a **NOT VERIFIED** list, wall time and the SHA-256s; plus
`docs/evidence/tracking/g319_census_recomputable_2026-09-08/sweep.csv` (integer cells zero-padded to 6
digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g319_census_recomputable.py`. Run that ONE file. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
