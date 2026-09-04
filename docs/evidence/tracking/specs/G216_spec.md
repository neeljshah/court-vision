GAP G216 | sport wnba | worktree a6 | log g216_local_staging_concurrency
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: RUN ON THE POD.** **Reuse G200's harness** (`scripts/platformkit/tracking/g200_pod_concurrency.py`)
unchanged wherever possible, so the two rows are directly comparable. Record concurrent load before
and after every arm; **a timing without its load context is not a result.**

**S3 DEPENDENCY -- G200 (landed) produced a collapse nobody predicted:**
    | N | jobs/min | mean per-job slowdown |
    |---|---:|---:|
    | 1 | 0.427 | 1.00x |
    | 2 | **0.567** | 1.52x |
    | 4 | 0.294 | 5.86x |
    | 8 | 0.150 | **21.83x** |
  **N=8 yields LESS throughput than N=1.** And **none of the resources I was counting bind**: at N=8
  the route used about **24 of 256 cores**, host RAM peaked at **109 GiB of ~1007 GiB**, and GPU memory
  peaked at **6,506 of 24,576 MiB**. The orchestrator's earlier claim of room for 19-30 concurrent jobs
  was withdrawn. G200 named the limit as a shared route path and stated exact IO causality as
  **NOT VERIFIED**.

**THE HYPOTHESIS THIS ROW TESTS, verified as a premise by reading the mounts (S2):**
  - `findmnt /workspace` -> **`mfs#eu-cz-1.runpod.net:9421[/podvolumes/...]`, fstype `fuse`** -- a
    NETWORK filesystem. **Every byte of footage is read over it.**
  - `findmnt /` -> **`overlay`**, a LOCAL filesystem, `df` showing **47 GB free of 50 GB**.
  - **So N concurrent jobs each stream a multi-gigabyte clip over network storage.** That fits G200's
    signature exactly: idle cores, idle GPU, collapsing throughput.
  **If true, the pod's real concurrency ceiling is far above 2 and the fix is a file copy.**
  **If false, the limit is elsewhere in the route and that is equally worth knowing.**

METHOD:
  1. **Copy ONE clip to the local overlay** (e.g. `/root/g216_stage/`), verify by **size and md5
     against the `/workspace` original**, and record both. **DISK GUARD: `/` has ~47 GB free but is
     also the container root -- check free space first, use ONE clip, and DELETE it at the end,
     reporting bytes freed.** Do not fill the container root.
  2. Re-run G200's arms at **N = 1, 2, 4, 8** reading from the LOCAL copy, and report the same table:
     jobs/minute, mean per-job slowdown, aggregate CPU, peak host RAM, peak GPU memory.
  3. **Put the two tables side by side** -- network-mounted (G200) against locally-staged (this row) --
     and state the throughput at each N for both.
  4. **Also measure the read path directly**, so the conclusion does not rest on job timings alone:
     sequential read throughput of the same clip from `/workspace` and from the local copy
     (`dd ... of=/dev/null`), single-stream and with 4 concurrent readers. **This is the decisive
     evidence; the job timings are the consequence.**
  5. **State the cost of the fix honestly.** Staging means copying a multi-GB clip before every job.
     Report the copy time and say whether the throughput gain exceeds it at each N. **A speedup that
     costs more in copying than it saves is not a speedup.**

**DO NOT change the route, any threshold, `imgsz`, `conf`, batch sizes or thread counts.** This row
changes WHERE the file is read from and nothing else. **Never kill, restart or deploy over the pod
daemon or keeper. Delete no corpus source.**

**HONEST LIMITATIONS to state, not discover:** the pod is shared -- the daemon, keeper, a supervisor
and possibly G203 are running, and the peer session also uses this machine -- so record the load and
do not present these numbers as clean-machine figures. One clip is one clip: this measures a mechanism,
not a rate across the corpus.

ACCEPTANCE RULE:
  metric        = jobs/minute and per-job slowdown at N = 1, 2, 4, 8 from LOCAL storage, beside G200's
                  network-mounted table; plus measured sequential read throughput from both
                  filesystems, single and concurrent
  before        = throughput peaks at N=2 and collapses to 0.150 jobs/min at N=8 while cores, RAM and
                  VRAM are all far from saturated; the cause is unattributed
  bar           = NO pass bar. **"Local staging removes the collapse" identifies the bottleneck and
                  hands us a large throughput win for the cost of a copy. "The collapse persists on
                  local storage" ELIMINATES the network filesystem and is equally valuable**, because
                  it would move the search inside the route. Do not tune anything to make either
                  outcome look better.
  n             = 1 + 2 + 4 + 8 = 15 job runs on one clip, plus the read-throughput measurements
  eye check     = none; this row is about time and bytes
  must not move = every threshold, `conf`, `imgsz`, batch sizes, thread counts, the coordinate
                  contract, every bar and verdict, `src/` (READ ONLY), the pod daemon and keeper, the
                  corpus (delete NOTHING from `footage_corpus`)
EVIDENCE: docs/evidence/tracking/g216_local_staging_concurrency_2026-09-03.md with both tables side by
side, the read-throughput measurements, the md5 parity of the staged copy, the copy-cost analysis,
bytes freed on cleanup, load context for every timing, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
