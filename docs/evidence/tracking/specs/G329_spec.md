GAP G329 | sport all | worktree a6 | log cx_g329_degenerate_resume

**TOOLING ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only.
Build in `scripts/platformkit/`. NEVER edit a committed evidence hash, a committed evidence
artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL for code and tests; the pod is READ-ONLY for the census
(`ssh -F ~/.ssh/config.pod pod`, ledger `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`,
per-clip data dirs under `/workspace/nba-ai-system/data/tracking/`). **NEVER stop, signal,
restart or interfere with `track_daemon` (pid 929149) or `vol_guard.py`; NEVER delete, move or
write anything on the pod.** Copy what you need with `scp`/`ssh cat` into the worktree.

**WHY THIS ROW EXISTS.** The daemon died at the `/workspace` quota event (2026-09-08 05:26Z) and
was relaunched. Of the 11 clips it resumed, 4 completed with `rows` of 0 to 2 in about 370 s:
`run_clip` resumed against a PARTIAL data dir left by the killed worker and treated the leftover
state as done. Those rows look like finished work. The pod-side volume guard prunes any corpus
source whose clip id carries a ledger row, so a degenerate row can cause the DELETION of a source
that was never tracked. That is silent data loss, and it is the reason this row outranks G328.

**PREMISE (step 0, BINDING before-condition):** census the pod ledger: count rows with
`rows < 50` grouped by whether the row was a resume (a data dir or partial output existed before
the run started -- derive from the ledger's own fields, e.g. `resumed`, `attempt`, start/end
timestamps straddling 05:26Z, or the data-dir mtimes; SAY which field you used). **PRINT the
census table with n.** If 0 rows with `rows < 50` exist, the premise is FALSE: STOP, write the
memo, commit, report PREMISE FALSE.

METHOD:
  1. **CENSUS (pod, read-only).** For every ledger row with `rows < 50`: clip id, rows, wall
     seconds, resume status, whether its source mp4 still exists in
     `data/footage_corpus/`, and whether `vol_guard.log` names it as pruned. **Report the
     data-loss count: degenerate rows whose source is gone.** n = all such rows, exhaustive.
  2. **TRACE.** Cite the resume path with `file:line` in `scripts/platformkit/run_clip.py` and
     `scripts/platformkit/track_daemon.py` (how a clip is picked up after a daemon death, what it
     finds in the data dir, why it exits early with 0-2 rows). Name the cause in one sentence.
  3. **FIX (additive, `scripts/platformkit/`).** Before re-tracking a clip whose data dir already
     holds partial output from an unfinished run, either clean that clip's data dir (only files
     the daemon itself wrote for that clip) or write the ledger row with
     `status=RESUMED_DEGENERATE` and `rows` as measured, never as a completed row. Also add an
     explicit `degenerate: true|false` field to every new ledger row (`rows < 50` and wall < 600 s)
     so downstream readers (the volume guard, the census) can exclude it without parsing. Existing
     field names and meanings stay (B2 additivity). No default changes for the running daemon.
  4. **TEST.** One per-file test: a tmp data dir with partial output + a stub tracker -> the
     resume path cleans it (or marks the row degenerate), and a completed row is written only
     when the tracker actually ran. Plus the existing test file of every touched module, each run
     individually.
  5. **GUARD NOTE.** Do NOT edit the pod's `vol_guard.py`. Write the exact one-line change it
     needs (skip sources whose only ledger rows are degenerate) as a PROPOSED snippet in the memo.
  6. **CHANGE NOTHING ELSE.** No threshold, no committed hash, no register edit, no adoption, no
     daemon restart, no deployment to the pod.

**HONEST LIMITATIONS to state, not discover:** the census reads the ledger as written; rows
lost with the killed worker are not recoverable and are not counted. The fix is not deployed by
this row; the running daemon keeps the old behaviour until the orchestrator ships and restarts
it. This row measures no recall, precision or registration.

ACCEPTANCE RULE:
  metric        = the census table (rows < 50 by resume status, n), the data-loss count, the
                  traced cause with `file:line`, the fix + passing per-file test
  before        = 4 of 11 resumed clips wrote rows 0-2 in ~370 s and were treated as done; no
                  `degenerate` field exists on any ledger row
  bar           = every degenerate row in the census is explained by the traced cause (or listed
                  as unexplained with n); the test proves a partial data dir can no longer yield a
                  completed row; 0 pod writes
  n             = all ledger rows with rows < 50 (CONSTRUCT, exhaustive; Q7 applies)
  eye check     = NONE. No frames, no renders. Say that.
  must not move = the running daemon and guard; every committed artifact; `src/`, `domains/`,
                  `api/`, `kernel/`, `intel/`; `data/`; anything on the pod;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g329_degenerate_resume_2026-09-08.md` (<= 60 lines) with VERDICT
on line 1, the census table, the data-loss count, the trace, the PROPOSED guard line, a
**NOT VERIFIED** list, wall time and the SHA-256s; plus the census CSV
`docs/evidence/tracking/g329_degenerate_resume_2026-09-08/census.csv` (zero-pad integer cells to
6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: `tests/platformkit/test_g329_degenerate_resume.py`. **n = CONSTRUCT.** Run that ONE file, and
separately re-run the existing test file of every touched module. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first. **NEVER PARK.**

VERSION 2026-09-08
