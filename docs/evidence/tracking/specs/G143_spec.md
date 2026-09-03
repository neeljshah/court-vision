GAP G143 | sport all | worktree a5 | log cx_g143_staging_hygiene
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. An UNATTENDED-SAFETY question. The pipeline now runs overnight and this is about
whether it can run for hours without filling the disk.
WHAT PROMPTED IT. On 2026-09-02 local staging (data/videos/bridge) reached **37 GB across 67 files**
and had grown from 23 GB in roughly twenty minutes. 60 of those files, 23 GB, had not been touched
for over twenty minutes and were orphans left by workers that had been killed mid-download; they
were removed by hand, taking staging to 15 GB across 7 genuinely active files. The reference corpus
(data/videos/reference, 2.4 GB, one best clip per sport) is a separate directory and was untouched.
THE QUESTION: in NORMAL operation -- no killed workers -- does staging stay bounded, or does it leak?
  (a) READ the cleanup path. footage_bridge's per-item `finally` deletes the local file and its
      yt-dlp siblings unless `keep_reference` retains it, and `_purge_leftovers` handles the 416
      resume case. Establish exactly which files each removes and, importantly, which it does NOT:
      yt-dlp writes per-stream files (game.f137.mp4), fragment files (game.mp4-FragNNNN) and
      .ytdl resume state, and a glob that misses one pattern leaks it forever.
  (b) MEASURE the steady state. Watch staging over at least 30 minutes of undisturbed operation and
      report total bytes and file count at intervals. Do NOT kill any worker during the window --
      that is what produced the orphans in the first place and it would invalidate the measurement.
  (c) NAME any pattern that survives a COMPLETED item and any that survives a FAILED item. Those are
      different paths and only one of them is exercised by a happy-path test.
  (d) BOUND THE RISK: at the observed steady-state growth, and at the current disk headroom (963 GB
      free), how long could the pipeline run before staging became a problem? State it as a number
      of hours with the arithmetic shown.
  (e) RECOMMEND a fix only if a real leak exists. A reaper that deletes by age is dangerous: a large
      full game legitimately takes many minutes to download, and an age-based sweep would delete
      work in progress. If you propose one, state how it distinguishes an in-flight file from an
      orphan, and prefer an mtime check over a wall-clock age.
DO NOT kill any worker or fetcher, change the bridge's cleanup logic without evidence of a leak, or
delete anything under data/videos/reference. NEVER KILL ANYTHING ON THE POD.
ACCEPTANCE RULE:
  metric        = staging bytes and file count over >= 30 minutes of undisturbed operation, plus the
                  set of filename patterns that survive a completed and a failed item
  before        = 37 GB / 67 files with 23 GB of kill-orphans; steady-state behaviour unmeasured
  bar           = NO pass bar. Success is the steady state measured over a real window, the
                  surviving patterns named, and the runway bounded in hours. "Cleanup is correct and
                  staging is bounded" is the best outcome and a full success.
  n             = >= 30 minutes of observation with at least 4 sample points; state the window
  eye check     = n/a. Reproduction = the interval measurements, with timestamps.
  must not move = the bridge's cleanup logic unless a leak is demonstrated, data/videos/reference,
                  every threshold, and every pod process
EVIDENCE: docs/evidence/tracking/g143_staging_hygiene_2026-09-0X.md with the interval table, the
surviving patterns, the runway arithmetic, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g143_hygiene/ BEFORE reporting (A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree and
commit with explicit pathspecs only.
TEST: exactly one new per-file test if you change code; run only that file. Never a full pytest.
POD: READ-ONLY.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
