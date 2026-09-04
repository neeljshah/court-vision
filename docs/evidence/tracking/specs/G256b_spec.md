GAP G256b | sport soccer | worktree a5 | log g256b_soccer_line_conic_calibration
**READ `docs/evidence/tracking/specs/G256_spec.md` IN FULL AND FOLLOW IT EXACTLY. This file changes ONE
thing: where the source lives and how to reach it.** Everything else in G256 -- the method, the dimension
trap, the identity crops, the degeneracy diagnostics, the hard gate on withheld geometry, the pixel-offset
measurement, the limitations and the acceptance rule -- **applies unchanged.**

**HELD UNTIL A POD LANE IS FREE** (G257 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**WHY THIS RE-ISSUE EXISTS -- MY SPEC ERROR, NOT THE LANE'S.**
G256 returned FALSIFIED because it searched the **local Windows filesystem**, correctly found no
`/workspace` mount there, and concluded the source was absent. **That conclusion is wrong about the world.**
My spec named a `/workspace` path without saying it is a **POD** path. G252, G253 and G254 all reached the
pod because their specs said so explicitly.

**The lane was RIGHT not to substitute the available football clip for the named soccer input.** That
discipline is why this is a cheap re-issue rather than a corrupted result. **Keep it.**

**THE SOURCE IS ON THE POD, AND I HAVE VERIFIED IT DIRECTLY:**
  - Path: `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4`
  - **2,341,768,743 bytes**
  - **SHA-256 `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e`**
  - mtime Sep 4 02:21
  - **`/workspace` exists ONLY on the pod. There is no local `/workspace` mount, and the local
    `data/footage_corpus` is a DIFFERENT, smaller corpus -- do not use it and do not compare against it.**
  - **Reach the pod over ssh the way G252, G253 and G254 did**, decode by streaming from there, and keep
    the corpus file read-only. **Confirm the byte size and SHA-256 above before doing anything else** and
    **STOP and report if either differs.**

**EVERYTHING ELSE IS G256's.** In particular, do not lose these, which are the substance of the row:
  - **The pitch is NOT a fixed size.** Roughly 100-110 m by 64-75 m by rule. **Fit ONLY from
    standard-dimension geometry:** centre circle radius **9.15 m**, penalty area **16.5 m x 40.32 m**, goal
    area **5.5 m x 18.32 m**, penalty mark **11 m** from the goal line. **Never fit touchline length or
    pitch width**, and report which features you used and what dimension you assumed for each.
  - **Verify identity BEFORE any fit: commit a zoomed crop for every fitted line and for the conic**,
    stating what is at it (G246's protocol).
  - **HARD GATE on INDEPENDENT geometry the fit did NOT use**, PASS or FAIL in one line, first.
    **The fit residual is NOT evidence** -- G242, G244, G247 and G248 closed that, and **G254 showed an
    optimiser can improve its own objective while moving the projection off the markings and failing the
    gate.**
  - **Do NOT change `IMAGE_SPACE`, the coordinate contract, or any production module.**
  - **A FAIL is a full success** -- name the feature or configuration that defeated it.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` ON THE POD (baseline ~33,139 MB of 50,000), STOP and report if it
fails.** Stream the decode; never write a full decode to disk. **Do NOT delete any corpus source or the
two abandoned partials in `footage_bridge`.** Report bytes freed.

ACCEPTANCE RULE, EVIDENCE, TEST and COMMIT: **as in G256_spec.md**, with the memo at
`docs/evidence/tracking/g256b_soccer_line_conic_calibration_2026-09-04.md`. **ADD A RESULTS_LEDGER.md ROW
IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7). Explicit pathspec, no push, report the
sha. Per-file tests only, never a full pytest. ASCII stdout. **NEVER PARK.**
