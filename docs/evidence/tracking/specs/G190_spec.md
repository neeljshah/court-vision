GAP G190 | sport wnba | worktree a3 | log g190_determinism_cause
**DIAGNOSIS ONLY. Change NO production code.** `src/` is HUMAN-GATED: you may READ and you may
import from it, but you must NOT edit it. The determinism mode itself is a human-applied change
already written up in `docs/evidence/tracking/PROPOSED_determinism_mode_2026-09-03.md`; this row
only establishes WHICH cause is real so that proposal is applied for a measured reason.

**S1 MACHINE: RUN EVERYTHING ON THE POD.** The local box is 16 GB with other lanes live and two RAM
guards have already fired on this programme today. The pod has an RTX 3090 with 24 GB.

**S3 DEPENDENCY:** this row exists because G189 (ACCEPT, landed) measured the `run_clip.py` route
producing 1,104 / 1,246 / 1,247 / 1,360 / 1,549 player rows across five identical runs -- a 40 pct
spread on one file with one command.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full, self-check section B.

PREMISES, VERIFIED BY THE ORCHESTRATOR BEFORE DISPATCH (S2). Re-confirm each cheaply, then proceed;
if any is false, STOP and report FALSIFIED:
  - `src/pipeline/unified_pipeline.py:657` sets `torch.backends.cudnn.benchmark = True`, with a
    comment claiming a ~10-15 pct throughput gain.
  - FP16 is used at `unified_pipeline.py:919` and `:1024`, and `advanced_tracker.py:284, 344, 435,
    444, 1218, 1227` (`half=...`).
  - There is NO seeding in the route: `manual_seed`, `np.random.seed` and `random.seed` do not appear
    in `unified_pipeline.py`, `advanced_tracker.py` or `scripts/run_clip.py`.
  - G189 observed three raw-detector invocations on one frame each returning exactly 15 boxes with
    coordinates and confidences differing in low digits (`594.750` vs `594.000`; `0.24365` vs
    `0.24438`).

THE QUESTION: **which of the three named causes actually produces the variance, and is any ONE of
them sufficient to remove it?** The proposal should be applied for a measured reason, not a
plausible one.

METHOD -- test the detector IN ISOLATION, not the whole pipeline. Build an additive harness under
`scripts/platformkit/tracking/` (never in `src/`) that loads the same detector the route loads and
runs it repeatedly on ONE fixed decoded frame, under these four conditions:

  | condition | cudnn.benchmark | seeds set | half |
  |---|---|---|---|
  | A baseline (route default) | True | no | True |
  | B tuner off | **False** | no | True |
  | C tuner off + seeded | False | **yes** | True |
  | D tuner off + seeded + FP32 | False | yes | **False** |

  Run each condition **in a FRESH PROCESS at least 3 times** -- process boundary matters, because the
  tuner re-benchmarks per process and that is the hypothesis. Compare the full box tensors
  BIT-EXACTLY (coordinates and confidences), not just the box count: G189 already showed the count
  can be stable at 15 while the values differ.

  Report for each condition: identical across runs, yes or no, and if no, the largest absolute
  difference in any coordinate and any confidence.

**A9 EXACT SOURCE:** use `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes, 1920x1080, 174,430 frames. State the frame index you decode. Do NOT use the
1280x720 `g130_recensus/` derivative -- two different videos answer to `wnba_01`.

**B13 PER-UNIT RECORDS:** store every run's full box tensor in the artifact, not a summary verdict.
The verifier must be able to recompute "identical or not" without rerunning anything.

ACCEPTANCE RULE:
  metric        = per-condition bit-exact reproducibility across >= 3 fresh processes, with the
                  largest coordinate and confidence deltas where not identical
  before        = 40 pct row spread across five identical full-route runs; three causes named, none
                  isolated
  bar           = NO pass bar. **"All four conditions still vary" is a FULL SUCCESS** and would mean
                  the cause is elsewhere (the tracker, or ROI ordering) -- report it and stop.
                  "B alone is sufficient" is the most useful outcome but must not be assumed.
  n             = >= 3 fresh processes per condition, 4 conditions (EXISTENCE of variance, not a rate)
  eye check     = not applicable; this is a numerical reproducibility row
  must not move = every threshold, `conf`, `imgsz`, the detector backend default, every bar and
                  verdict, `src/` (human-gated, READ ONLY), the pod daemon and keeper
DO NOT apply the determinism proposal, edit `src/`, or restart the pod daemon. If you find the fix,
you report it; the human applies it.
EVIDENCE: docs/evidence/tracking/g190_determinism_cause_2026-09-03.md with the four-condition table,
the per-run box tensors, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for your harness, pasted. NEVER a full pytest.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
