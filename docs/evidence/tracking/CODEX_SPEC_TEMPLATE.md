# Codex spec template for tracking (G) and harness (S) gaps
Copy this template into each codex spec artifact; fill in the placeholders and run through the ACCEPTANCE RULE validation before dispatching. Max 40 lines.

TWO ADJUSTMENTS FOR AN S-ROW (added 2026-09-03; without them the template
contradicts more than half the S-register):
- **`eye check` is a TRACKING element.** An S-row has no frames. Write
  `eye check = n/a (S-row); reproduction = <exactly how the verifier recomputes
  the headline from the artifact>` -- contract A2 still applies, A3 does not.
- **`n >= 30` is a SAMPLING rail, not a universal one.** A deterministic
  CONSTRUCT test enumerates every case rather than sampling, so its n is the case
  count: write `n = <k> (CONSTRUCT)` and the verifier may NOT reject on the rail.
  Use CONSTRUCT only when every case is enumerated; a sampled or scored
  measurement keeps `n >= 30`. On the S-register today the construct rows are
  S01, S07, S08, S09, S12, S13, S15, S17, S21, S23, S24, S28, S29.
Also cite `VERIFIER_CONTRACT.md` section Q on an S-row, not just section B.

---

GAP <GID> | sport <sport> | worktree a<N> | log cx_<gid>_<slug>
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check
against every line of section B before you report.
WHERE THIS ROW RUNS (step -1, MANDATORY -- state it PER STEP, not per row):
  local  = reading committed records/artifacts in the worktree, arithmetic, tests.
  pod    = anything needing full-resolution corpus video or GPU. Ship and run it
           with `~/bin/pod_run <aN> --ship <paths> --fetch <paths> -- <cmd>`, which
           copies this worktree's code tree to /workspace/wt/<aN>, runs there under
           nohup, fetches the listed paths back, and never writes the deployed tree
           /workspace/nba-ai-system.
  A "mostly local" row is exactly where this gets missed (G256, G276). If a step
  names a /workspace path, SAY it is a pod path.
  DISK GUARD SCOPE: `du -sm /workspace` and the `dd conv=fsync` probe are POD-side
  and belong INSIDE the pod_run command. A missing /workspace in the local checkout
  is NOT a disk failure -- it means move that step to pod_run, not STOP.
  HOLD RULE, CORRECTED 2026-09-04 21:00: GATE ON THE RESOURCE THE ROW ACTUALLY
  CONTENDS FOR, NOT ON A LANE COUNT. The old rule -- count DISTINCT
  /workspace/wt/a* directories and hold at 2 -- is a PROXY, and it held a GPU row
  out for five hours while the GPU sat at 0 pct with ZERO compute processes and
  24,575 of 24,576 MiB free, because five peer lanes were running CPU-only
  simulations on a 256-core box at load15 = 108. Measure the real constraint:
    - GPU rows (detection, decode-to-tensor): `nvidia-smi
      --query-compute-apps=pid,used_memory --format=csv,noheader` EMPTY, or free
      VRAM above what the run needs. THAT is the gate for a GPU row.
    - any row that WRITES: the `dd conv=fsync` probe must pass.
    - CPU-heavy rows: load15 (field 3 of /proc/loadavg) below `nproc`.
  Still NEVER interrupt a running row, and still never count python PIDs -- one
  lane routinely shows two PIDs sharing one cwd (G274). Report the SET of
  occupied worktrees as CONTEXT and report the gate measurement you gated on.
  THIS IS NOT MOVING A BAR. An EVIDENTIARY threshold (a speed bar, an acceptance
  bar, a p-value) may NEVER be moved to let a result pass. An OPERATIONAL
  resource gate IS replaced when it is measured to gate on the wrong resource.
  Keep the two categories apart and say plainly which one you touched.
  DISK GUARD, CORRECTED 2026-09-04: `du -sm /workspace` is a NETWORK filesystem
  walk (MooseFS) and under load it takes minutes or returns NOTHING. An empty
  result means UNKNOWN, NEVER 0 -- a monitor that parsed empty as 0 raised a
  false "corpus deleted" alarm, and a lane died parsing empty du output and lost
  a completed 3,801-frame pass. So: `v=$(timeout 60 du -sm /workspace | cut -f1);
  [ -z "$v" ] && v=UNKNOWN`, report v verbatim, and NEVER stop on UNKNOWN --
  stop only on a failed `dd conv=fsync` probe, which is cheap and decisive.
  `df` is useless here: it reports the 929T cluster, not the 50 GB quota.
  Rows that write only summaries need no disk guard at all.
PREMISE (step 0): <the one measurement that proves the gap is real today>. If
falsified, STOP, write the memo, commit, report FALSIFIED -- a valid result
that earns its own register row.
LIMIT (step 1): <the measurement that bounds what is achievable>. If the limit
is below the acceptance bar, STOP and report CLOSED AT LIMIT. Do not fix.
CHANGE (step 2): <the smallest change>. Additive only: new columns, new opt-in
modes, new files. Renaming or removing an existing field, column or status
value is an automatic reject -- if unavoidable, keep the old name as an alias
in the same commit and name every reader you checked.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = <name + exact denominator: decoded frames/rows/segments>
  before        = <measured today, with n>
  bar           = <the number "after" must beat; fixed now, never moved>
  n             = <>= 30 for a sampled/scored metric; "<k> (CONSTRUCT)" when every case is enumerated>
  eye check     = <k renders EVENLY SPACED over the decision set, no head slice>
  must not move = <thresholds/files that must be byte-identical after>
NON-TAUTOLOGY: state which rows the metric covers and which are excluded. If
excluding the failing rows is what makes the number good, the metric is
circular -- say so and report REJECT yourself.
EVIDENCE: docs/evidence/tracking/<gid>_<slug>_<TODAY>.md -- before/after
table, n, denominator, render tally, and a "NOT VERIFIED" list.
REQUIRED EVIDENCE DURABILITY: before reporting, copy under docs/evidence/ every artifact a verifier must use to reproduce a number: at minimum a summary JSON and the sampled rows. A directory of renders may stay local, but the numbers behind the renders must not.
RE-EMITTED TABLES: preserve the FULL column set, not only the subset this lane uses; a table written for one purpose can omit columns a later lane needs (for example frame_width and frame_height).
TEST: exactly one new per-file test; run only that file.
POD: heavy compute only; own nohup setsid nice job, unique /tmp log, never
kill anything, no git on the pod, and NO scp of any module until the verifier
accepts. Report the files you would deploy; do not deploy them.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha.
NEVER PARK: poll your own jobs in a blocking loop; never end waiting.
