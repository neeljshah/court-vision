GAP G235 | sport wnba | worktree a4 | log g235_build_court_crash_confirmation
**MEASUREMENT AND IN-PROCESS VALIDATION ONLY. Change NO production code.** `src/` is HUMAN-GATED:
**READ and IMPORT only.** You may monkey-patch **inside your own process** to observe and to test a
candidate guard; **you must not write a single byte into `src/`, and you must not deploy anything to the
pod checkout.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE.** G232 and G233 are running there and N=2 is the measured optimal
schedule (G200/G216: N=4 collapses). **Check first and say in your memo that you checked and when you
began.** The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and
`foundry_runner` are PERMANENT residents and the load floor -- never wait for them, never kill or
restart them. Harness and test preparation may proceed immediately.

**WHY THIS ROW EXISTS -- G234 LOCATED THE MOST ACTIONABLE DEFECT OF THE NIGHT BUT ONE LINK IS STILL
INFERRED, AND IT IS THE LINK THE FIX RESTS ON.**
  - **G234 / G234-COMPLETE (landed):** every non-tracked basketball job on the pod -- **9 of 9, being 4
    `ncaa_basketball` and 5 `wnba`** -- died with `cv2.error: OpenCV(5.0.0)` inside `_build_court` at
    `src/pipeline/unified_pipeline.py:1097`, `map_2d = cv2.resize(map_img, (_rw, _rh))`, in 30-45
    seconds. The same clip `wnba_01` tracked successfully once (3,377 rows, 174,430 decoded, 2,552 s), so
    it is not a footage property.
  - **The reading:** `_build_court` has THREE fallbacks to a 940x500 default (missing pano, PORTRAIT
    rectification, any exception) and **none covers a zero or degenerate dimension.**
    `_rh, _rw = rectified.shape[:2]` at `:1072` is unvalidated and the only shape test is `if _rh > _rw`,
    so a zero height falls through -- `0 > 940` is False -- and `cv2.resize(map_img, (940, 0))` raises,
    because `resize` rejects a destination whose area is not positive.
  - **WHAT IS NOT VERIFIED, and it is the whole point of this row: `rectified.shape` has NEVER BEEN
    OBSERVED on a failing run.** The zero-dimension path is inferred from the guard structure and the
    exception text. **If the real shape is something else -- a huge dimension, a wrong dtype, an empty
    `map_img` -- then the proposed guard is the wrong fix and a human would apply it for nothing.**

THE QUESTION: **what is `rectified.shape` (and `map_img.shape`) at the moment `_build_court` raises, and
does the proposed guard actually prevent the crash?**

METHOD:
  1. **Reproduce the crash first.** Run the legacy route the way the daemon does --
     `run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --game-id <fresh id> --no-show --frames
     3000 --data-dir <NEW dir>` (`track_daemon.py:83-105`) -- and confirm it dies in `_build_court` with
     the same signature in roughly 30-45 s. **If it does NOT crash, that is a major finding: say so
     immediately and stop**, because the failure would then be intermittent and the fix unproven.
  2. **Observe the shapes.** From your own process, wrap or trace `_build_court` so that at the moment
     of failure you capture and report: **`rectified.shape` and its dtype, `_rw` and `_rh`, `map_img.shape`
     and its dtype, and whether `pano` was non-empty** (`_pano_ok`). **Report the literal values.** Also
     report which of the three existing fallbacks, if any, fired.
  3. **Then test the candidate guard IN YOUR OWN PROCESS ONLY** -- monkey-patch `_build_court` (or the
     narrow helper it calls) to apply `if _rw <= 0 or _rh <= 0: _rw, _rh = 940, 500` and re-run the same
     bounded command. **Report whether the run then completes and how many rows it emits.** **Do NOT
     leave the patch in place, do NOT write it into `src/`, and do NOT deploy it.**
  4. **State plainly whether the proposed fix is CONFIRMED, WRONG, or INSUFFICIENT.** **"The shape is not
     zero and the proposal is wrong" is a FULL SUCCESS and is more valuable than a confirmation**,
     because it would stop a human applying a fix that does not address the cause. **"It completes but
     still emits 0 rows" is also a full success** -- it would mean the crash is not the only blocker.
  5. **If the guarded run DOES emit rows, report the row count and score it with the harness**, and say
     what stage it reaches. Expect `coordinate_contract` on `image_px`, exactly as G226c got. **Do not
     change any gate, threshold or contract to improve that.**
  6. **Also check the one loose end G234-COMPLETE left: the single `mlb` `thin` entry has an EMPTY tail
     and is unexplained.** If you can characterise it cheaply from the ledger or its tracking directory,
     do; if not, say so and leave it.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod (it reports the whole cluster filesystem
against a 50 GB volume cap; a `Disk quota exceeded` incident followed that misreading). **`dd conv=fsync`
write probe before writing, record `du -sm /workspace/nba-ai-system/data` (baseline ~31,840 MB of
50,000), STOP and report if it fails.** Write to a NEW tracking directory, **delete no legacy basketball
table** (G207, G226, G226c and G234 all cite them), delete every temporary artifact and report bytes
freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** a monkey-patched guard demonstrates BEHAVIOUR, not that
the production fix is correct in every path -- say so. One clip and a bounded run on a shared,
non-deterministic route (G190/G195/G198/G203): a single reproduction is one draw, and the crash was
observed 9 times historically but that history is not yours. **Emitting rows is not emitting CORRECT
rows** -- any resulting table would still be `image_px` and still fail `coordinate_contract`.

ACCEPTANCE RULE:
  metric        = the literal `rectified.shape`, dtype, `_rw`/`_rh`, `map_img.shape` and `_pano_ok` at
                  the moment of failure; whether the crash reproduced; whether the guarded re-run
                  completed and its row count; and an explicit CONFIRMED / WRONG / INSUFFICIENT verdict
                  on the proposed fix
  before        = 9 of 9 basketball failures are `cv2.error` in `_build_court:1097`; the zero-dimension
                  cause is INFERRED from the guard structure and has never been observed; a human-gated
                  fix is proposed on that inference
  bar           = NO pass bar. **"The proposal is WRONG because the shape is X" is the most valuable
                  outcome available** -- it stops a bad fix. A confirmation is equally acceptable. Do
                  not tune, do not leave a patch behind, and do not change a gate to make a run pass.
  n             = 1 reproduction + 1 guarded re-run on one clip (EXISTENCE, not a rate)
  eye check     = none; this row is exception state and row counts
  must not move = every threshold, bar and verdict, the coordinate contract, the harness, `CLIP_SPORTS`,
                  `src/` (READ and IMPORT only -- no writes, no deploys), the pod daemon and keeper, the
                  corpus, the legacy basketball tables
EVIDENCE: docs/evidence/tracking/g235_build_court_crash_confirmation_2026-09-04.md with the reproduction
result, the literal shapes and dtypes at failure, which fallback fired, the guarded re-run outcome and
row count, the harness stage if any, the CONFIRMED/WRONG/INSUFFICIENT verdict, the `mlb` loose end,
every disk-guard probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
