GAP G221 | sport all | worktree a7 | log g221_denominator_defect_runtime_evidence
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: **READ and IMPORT only** -- you
may import and CALL production functions from your own process, which is how you get runtime evidence
without editing anything. **Write no file into `src/`.** Build in `scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- G216 is measuring read throughput there and any
load corrupts it. Everything this row needs is a local `.mp4`; several sit in `data/videos/`
(`gsw_lakers_2025.mp4`, `lal_sas_2025.mp4`, `mem_nop_2025.mp4`, `mia_bkn_2025.mp4`, `mil_chi_2025.mp4`,
`okc_dal_2025.mp4`, `phi_tor_2025.mp4`, `sac_por_2025.mp4`, `nba_highlights_gsw.mp4`), 170-300 MB each.
**LOCAL LOAD GUARD, BINDING: this box has crashed twice from concurrent unbounded load** (recorded in
`footage_bridge.py:95`). **Run ONE decode at a time, bound every decode to a few thousand frames, and
never decode a whole game.** Put every temporary file under the scratch directory or `data/videos/tmp`,
and **delete all of them at the end, reporting bytes freed.**

**WHY THIS ROW EXISTS -- G218 LANDED TONIGHT AND ITS OWN STATED LIMITATION IS THE THING TO FIX.** G218
classified 19 DEGRADED-SUBSTITUTE handlers by STATIC reading and said plainly: *"this establishes what a
handler CAN do; it cannot establish that it has fired in production"*, obtaining **no runtime evidence
for any of the 19.** **This row converts the two that threaten a COVERAGE DENOMINATOR from "can" into
measured fact, or refutes them.** Both were re-verified in master by the orchestrator before this row
was written; **you are not being asked whether the code says this, you are being asked what it DOES.**

**DEFECT A -- EOF MASKS DECODER FAILURE (`src/pipeline/unified_pipeline.py:283-286`).** The prefetcher's
decode loop ends with `except Exception: pass`, then a comment reading `# Always push sentinel so
consumer can detect EOF`, then `self._q.put(self._SENTINEL)` **unconditionally**. **So a decoder crash
at frame 5,000 of 174,430 delivers the same sentinel as a clip that genuinely ended.** If true at
runtime, a truncated observation is reported as a complete one and every coverage figure computed from
it is against the wrong denominator.

**DEFECT B -- FRAME COUNT FALLS BACK TO A FILE-SIZE GUESS (`src/pipeline/unified_pipeline.py:1505-1521`).**
`cv2.CAP_PROP_FRAME_COUNT` is tried first; on 0 it tries PyAV; if that also yields 0 it uses
**`int(os.path.getsize(path) / 250_000)`** with the comment *"1 GB ~= full game at typical bitrate"*, and
on exception `_FRAME_STRIDE_THRESH + 1`. **The count then selects the stride at :1529 --
`_stride = _base_stride if total_video_frames > _FRAME_STRIDE_THRESH else 1` with
`_FRAME_STRIDE_THRESH = 3000`** -- and `self.max_frames` is divided by that stride at :1533.

**THE ORCHESTRATOR'S SPECIFIC HYPOTHESIS ABOUT DEFECT B, WHICH YOU SHOULD TRY TO REFUTE.** Because the
count only matters through a **single threshold at 3,000**, the file-size guess is HARMLESS whenever both
the guess and the truth land on the same side of it. For a 2-3 GB whole game the guess is roughly
8,000-12,000 and the truth is far larger: **both above 3,000, same stride, no effect.** **But a
16-minute SECTION download of ~300 MB gives a guess of about 1,200, which is BELOW 3,000 and yields
stride 1, while the true count for 16 minutes at 30 fps is about 28,800, which is ABOVE and yields the
strided path.** **Section downloads are now the main acquisition mode** (`footage_bridge.py`,
`SECTION_MINUTES = 16`), **so this is the case that matters and it is the one nobody has measured.**
**Test it; do not assume I am right.** If cv2 or PyAV reliably supply a real count on these files, the
fallback never fires and **Defect B is a live-but-unreachable branch -- that is a FULL SUCCESS and must
be reported plainly.**

METHOD:
  1. **Defect B, branch census.** For every local `.mp4` you use, call the same three sources the
     production code calls, **in the same order**, and record ALL of them side by side: the
     `cv2.CAP_PROP_FRAME_COUNT` value, the PyAV `streams.video[0].frames` value, the file-size estimate
     `int(getsize / 250_000)`, and a **ground-truth count**. State how you obtained ground truth and
     what it cost -- an `ffprobe -count_frames` is exact but expensive, and a duration x fps product is
     cheap but approximate; **say which you used and treat an approximate truth as approximate.**
     **Then report which branch production would actually have taken for each file, and the stride each
     source implies against the 3,000 threshold.**
  2. **Defect B, the section case.** Produce at least one **bounded section-sized clip** (roughly
     10-20 minutes, a few hundred MB) by copying a bounded slice of a local file with `ffmpeg -ss/-t`.
     **Do NOT download anything.** Repeat step 1 on it. **This is the configuration the hypothesis is
     about; report it separately and prominently.**
  3. **Defect A, the decisive demonstration.** Make a **truncated copy** of a local `.mp4` in your temp
     area -- copy the first N bytes so the container is cut mid-stream. Then drive the production decode
     path over it **from your own process** (import the prefetcher / frame iterator; do not edit it) and
     record: how many frames came out, whether any exception surfaced anywhere observable, and
     **whether ANY signal distinguishes this run from a clean decode of the same clip's first N frames.**
     **Run the clean control too** -- a truncation result without its control proves nothing.
  4. **State the consequence for the ledger in one paragraph, carefully.** If Defect A is confirmed,
     say exactly which published quantity is at risk (`decoded`, `evaluated`, and every coverage figure
     computed on them) **and be precise that this shows the RISK is real, not that any specific landed
     number is wrong.** **Do NOT retract or re-open any landed row on this evidence** -- that is a
     separate adjudication with its own id. Naming the exposure is this row's job.
  5. If a defect does NOT reproduce, **say so as the headline.** "The fallback never fires because PyAV
     always returns a real count on our files" retires a concern and is worth as much as confirming one.

**HONEST LIMITATIONS to state, not discover:** local NBA `.mp4` files are not the pod corpus and were
produced by a different acquisition path, so a branch that never fires here may still fire there -- **say
that explicitly and do not generalise to the pod.** A hand-truncated file is not identical to a decoder
crashing from a driver fault, a corrupt stream or an OOM; it is one realisation of the failure mode.
Ground truth by duration x fps is approximate and cannot resolve small differences.

**DO NOT** change any threshold, `_FRAME_STRIDE`, `_FRAME_STRIDE_THRESH`, the coordinate contract, or any
gate. **DO NOT apply a fix** -- G218's human-gated proposals already cover the remedy shape (keep the
fallback, make it observable) and adding another proposal is not this row's job.

ACCEPTANCE RULE:
  metric        = per-file table of cv2 / PyAV / file-size / ground-truth frame counts, the branch
                  production would take, and the implied stride against the 3,000 threshold, for
                  whole-game files AND for at least one section-sized clip; plus the truncated-versus-
                  clean decode comparison with the count of frames emitted and every observable signal
  before        = G218 established both defects by static reading and obtained NO runtime evidence for
                  either; whether either branch is ever reached at runtime is unknown
  bar           = NO pass bar. **"Neither branch fires on any file tested" is a FULL SUCCESS** and would
                  substantially downgrade two findings I judged the most serious of the 19. **"Truncation
                  is indistinguishable from clean EOF" is the other full success.** Do not tune, and do
                  not prefer the alarming outcome.
  n             = every local `.mp4` used (name them and the ELIGIBLE DENOMINATOR) + >=1 section-sized
                  clip + 1 truncated/clean decode pair
  eye check     = none; this row is counts and signals
  must not move = every threshold, `_FRAME_STRIDE`, `_FRAME_STRIDE_THRESH`, every bar and verdict, the
                  coordinate contract, `src/` (READ and IMPORT only -- no writes, no fixes), the pod
                  (DO NOT USE IT), the corpus, and every landed ledger row (name exposure, retract
                  nothing)
EVIDENCE: docs/evidence/tracking/g221_denominator_defect_runtime_evidence_2026-09-04.md with the
per-file branch table, the section-sized result reported separately, the truncated-versus-clean
comparison with its control, an explicit statement of which branch production takes and when, the
consequence paragraph, bytes freed on cleanup, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
