GAP G186 | sport all | worktree a3 | log g186_frame_count_stall
**This changes HOW a denominator is COMPUTED, never its VALUE.** The new path must return the
IDENTICAL integer the old one returns, or the difference is a finding you report rather than accept.
No bar, threshold, gate, coordinate contract or verdict moves. Editing a bar is an automatic REJECT
under B10/Q3.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full, especially A5, B2, B3, B10.
Self-check section B before reporting.

WHY (measured by the orchestrator on the live pod, 2026-09-03, read-only):
  - The daemon (pid 33064, `--workers 10`) had **ZERO `adapter_run` processes running** while load
    average sat at 40. No tracking was happening at all.
  - What it was doing instead: `ffprobe -v error -count_frames -select_streams v:0 -show_entries
    stream=nb_read_frames` on `data/footage_bridge/soccer__soccer_dnR5C6WLJI4.mp4` (3,373,680,742
    bytes), **still running after 7 minutes at 98.7 pct CPU**. `-count_frames` fully decodes the file
    single-threaded to count frames.
  - The container already holds the answer. A metadata-only probe returned **in under a second**:
    `nb_frames=250200`, `r_frame_rate=30/1`, `duration=8340.000000`. They agree exactly:
    8340 * 30 = 250,200.
  - **The RTX 3090 measured 0 pct utilization and 1 MiB of 24,576 MiB used, sampled 10 times over 20
    seconds.** Nothing reaches inference because the tick loop is stuck counting frames.
  - Two `[python] <defunct>` children of the daemon (33:01 and 07:09 elapsed) were unreaped.

THE CHANGE, in `scripts/platformkit/tracking/decode_manifest.py` (`decoded_frame_count`) and any
sibling caller:
  (a) Read `nb_frames` from container metadata first. Accept it ONLY when it is present, a positive
      integer, and consistent with `duration * r_frame_rate` within a tolerance you state and justify.
  (b) Fall back to the existing `-count_frames` decode when metadata is absent, zero, or inconsistent
      -- VFR and some containers genuinely lack a usable `nb_frames`. **The fallback must stay.**
      Silently trusting bad metadata would corrupt a denominator, which is far worse than being slow.
  (c) Log which path was taken per file so the choice is auditable afterwards.

MANDATORY EVIDENCE, this is the acceptance test:
  - **Equality check on real files, not synthetic ones.** For every video currently on the pod
    (`data/footage_bridge` and `data/footage_corpus`), report metadata-count vs `-count_frames` SIDE
    BY SIDE with the wall time of each. Name the ELIGIBLE denominator (all files present), not a
    sample size. **Any file where the two disagree is the most important row in your memo** -- report
    it, do not tune a tolerance until it passes.
  - The timing table is the throughput claim. State total seconds saved across the corpus.
  - **A5 reader survey** over every caller of `decoded_frame_count` and every consumer of the value.
    A denominator is read by more things than write it, and G164 already found three quantities
    sharing one name.
  - A per-file test that fails without the change, plus the existing decode-manifest and daemon tests.
  - Separately: say whether the unreaped defunct children are a real leak and where the reap is
    missing. Diagnose only; do not change process handling in this row.

ACCEPTANCE RULE:
  metric        = per-file metadata-count vs count_frames equality, plus wall time of each
  before        = daemon blocked >7 min on one 3.37 GB file; 0 adapter_run processes; GPU at 0 pct
  bar           = NO pass bar. Success is the equality table produced and the fast path landed WITH
                  its fallback. **"Metadata disagrees with the decode on N files so the fast path is
                  unsafe for them" is a FULL SUCCESS** -- the fallback exists for exactly that.
  n             = every video file present on the pod (CONSTRUCT, exhaustive); name any excluded
  eye check     = replaced by REPRODUCTION (Q7): the equality table recomputed from real files
  must not move = every bar, the coordinate contract, every verdict, every ledger field NAME, src/
                  (human-gated), and the VALUE any denominator takes
DO NOT kill, restart or deploy over the pod daemon or keeper. The orchestrator deploys after ACCEPT.
The running daemon will not pick this up until it next cycles; that is expected and not your problem.
EVIDENCE: docs/evidence/tracking/g186_frame_count_stall_2026-09-03.md with the equality+timing table,
the A5 survey, the defunct-children diagnosis, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: your new per-file test plus the existing decode_manifest and track_daemon tests -- paste all
results. NEVER a full pytest.
POD: READ-ONLY and BATCHED.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
