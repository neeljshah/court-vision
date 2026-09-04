GAP G245 | sport basketball (amateur) | worktree a6 | log g245_amateur_footage_acquisition
**ACQUISITION AND VERIFICATION ONLY. Change NO production code.** `src/` and `domains/` are READ and
IMPORT only. Use the landed `scripts/platformkit/footage_bridge.py` machinery; build any new helper in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G241b is running on a5; N=2 is optimal per G200/G216, so you are the
permitted second lane). **Check first, do NOT interrupt a running row, and say in your memo that you
checked and when you began** -- G243 did this correctly. The `track_daemon`, `keep_track_daemon.sh`,
`adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT residents and the load
floor.

**WHY THIS ROW EXISTS -- THE STATED GOAL HAS NO TEST MATERIAL.**
G243 was specified against an amateur high-school clip and **falsified the premise**: the file exists at no
worktree, local or pod path, and `find /workspace -iname '*jh3fnwMi7dM*' -o -iname '*g220c*'` returns
nothing. **That was my error, landed as G243-PREMISE-CORRECTION.**

**The corpus is 9 clips and EVERY ONE is professional broadcast:** `baseball__kbo_10`,
`baseball__npb_04`, `mlb__mlb_gDv5xF2AA2E`, `mlb__mlb_nLoG6gvC-Nk`,
`ncaa_basketball__ncaa_basketball_IB-_u4gW3ds`, `soccer__soccer_Z6NTDyxcODs`, `tennis__tennis_02`,
`tennis__tennis_03`, `wnba__wnba_01`. **The goal is tracking on arbitrary footage -- high-school and
amateur video included -- and there is currently nothing in the corpus to test that against.**

THE QUESTION: **can amateur basketball footage suitable for a calibration attempt be acquired and landed
in the corpus, and is it actually suitable?**

METHOD:
  1. **Use the landed acquisition machinery** in `scripts/platformkit/footage_bridge.py`. **The proven
     recipe is an EXPLICIT HLS section**: a rung like `-f "232+233"` with
     `--download-sections "*HH:MM:SS-HH:MM:SS"`, which fetched 4.56 MiB in 3 s, while the DASH rung
     `136+251` was still unfinished after 170 s. **Three prior acquisition failures were all selector
     problems, not network problems** -- if a rung stalls, change the rung, do not wait it out.
  2. **Acquire amateur or high-school basketball**, preferring **a fixed or near-fixed camera with the
     painted court visible**. A wide static view is worth more here than a well-produced one.
  3. **SUITABILITY IS THE DELIVERABLE, NOT THE DOWNLOAD.** Landing an unusable file would repeat G243 in a
     new form. **Decode several evenly spaced frames, commit them, and state by eye whether painted court
     geometry -- baseline, sideline, lane, three-point arc, centre circle -- is actually visible and
     whether the camera is fixed.** If it is not suitable, **say so and reject the candidate**; try
     another before concluding.
  4. **Report full identity for whatever you land**: exact corpus path, byte size, SHA-256, resolution,
     frame count, fps and duration from `ffprobe`, plus the source URL and the exact command used.
  5. **PROVE IT IS VISIBLE WHERE THE NEXT ROW WILL LOOK.** End with an `ls -la` of
     `/workspace/nba-ai-system/data/footage_corpus/` in the memo showing the new file present, and use the
     existing `<sport>__<name>.mp4` naming convention already used by all 9 clips. **This is the exact
     check whose absence caused G243.**
  6. **If nothing suitable can be acquired, that is a complete and honest result** -- report what you
     tried, which rungs and sources failed and how, and stop. Do NOT substitute professional footage and
     call it amateur.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod -- it reports the whole cluster filesystem
against a 50 GB volume cap, and a `Disk quota exceeded` incident followed that misreading. **`dd
conv=fsync` probe before writing, record `du -sm /workspace/nba-ai-system/data` (baseline ~32,976 MB of
50,000), STOP and report if it fails.** Current composition: `footage_corpus` 22,321 MB and
`footage_bridge` 7,147 MB. **`footage_bridge` holds two abandoned partial downloads --
`football__football_m8UWuQoflJo.mp4.part` (4,768 MB) and `baseball__npb_05.mp4.part` (2,376 MB). DO NOT
DELETE THEM; they may be resumable and that decision is not yours.** Report their size and mtime so the
orchestrator can decide. **Prefer a bounded section over a whole game** -- a few hundred MB is ample for a
calibration test and the volume has roughly 17 GB free. Delete every temporary artifact and report bytes
freed. **Delete no corpus source.**

**HONEST LIMITATIONS to state, not discover:** one acquisition attempt says nothing about calibration,
detection or tracking quality on the clip -- **it establishes only that test material exists.** Suitability
here is a **single-labeller eye judgement** on a handful of frames, not a measurement; eye-label
reliability in this programme has never cleared 80 pct blind agreement on any of four measured criteria.
"Amateur" is a description of the source, not a controlled condition: resolution, encoder, camera height
and framing all vary and none is held fixed. Nothing here bears on automatic calibration, which remains
0/17.

ACCEPTANCE RULE:
  metric        = whether a suitable amateur basketball clip is landed in the corpus; its full identity
                  (path, bytes, SHA-256, resolution, frames, fps, duration, source, command); the eye
                  judgement on painted-geometry visibility and camera fixity with committed frames; and
                  the `ls -la` proof of corpus presence
  before       = the corpus is 9 clips, all professional broadcast; the any-footage goal has no test
                 material, and G243 was falsified for exactly this reason
  bar          = NO pass bar. **"No suitable amateur footage could be acquired, and here is what failed"
                 is a FULL SUCCESS** and is far better than landing an unusable file. **A landed, verified,
                 suitable clip is the other full success** and unblocks G243b. Do not substitute
                 professional footage, and do not report a download as a result without the suitability
                 check.
  n            = as many candidates as you try -- report every one, kept or rejected, with the reason
  eye check    = the committed sample frames ARE the suitability evidence
  must not move = every threshold, bar and verdict, the two existing `.part` files, the 9 existing corpus
                  clips, the coordinate contract, the harness, `src/` and `domains/` (READ and IMPORT
                  ONLY), the pod daemon and keeper
EVIDENCE: docs/evidence/tracking/g245_amateur_footage_acquisition_2026-09-04.md with every candidate tried
and its outcome, the full identity of anything landed, the committed sample frames and the eye judgement,
the `ls -la` corpus proof, the `.part` file sizes and mtimes, every disk-guard probe, bytes freed, and a
NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. **`tests/platformkit/test_footage_bridge.py` is the
existing per-file test if you touch the bridge -- run only that file.** NEVER a full pytest. **If a commit
grows an allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME
commit (contract A12).**
COMMIT: explicit pathspec only, no push. **NEVER commit the video itself -- `data/` is gitignored and must
stay untracked.** **If your work spans several commits, make EVERY commit before you finish.** Report the
sha.
NEVER PARK.
