GAP G175 | sport tennis | worktree a3 | log cx_g175_rally_stage_histogram
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A2, A3, A7, Q8); self-check B.
RAILS: heavy work ON THE POD under nohup, batched collection, never poll -- a local decode was
RAM-killed today at 1.4 GB. NEVER kill, restart or deploy over the pod daemon or keeper.

WHY THIS ROW IS THE PRIORITY. The coverage bar is NOT the binding constraint; that was adjudicated
today and closed. The binding fact is that **at stride 1 the court solver produces no usable output on
about three of every four rally-view frames, and no geometry on seven of eight**: G152b emitted rows
on 2,597 of 28,773 frames and geometry-usable rows on 1,350, against a rally denominator of roughly
10,838 frames from G161's 0.3767 share. Nobody knows WHICH STAGE kills those frames.

**The data to answer it already exists and no new measurement pass is needed.** The tennis adapter
writes a per-frame `status` into `frame_manifest.csv` -- values include `skipped_stride`, the
calibration statuses, `no_complete_player_pair` and `emitted_players`. G161 committed 300 seeded,
evenly spaced hand labels under `docs/evidence/tracking/g161_rally/labels_pass1.csv`, of which 113 are
RALLY_VIEW. **Joining that status column onto those 113 rally frames is a histogram, not an
experiment.**

DO THIS:
  (a) Q8 FIRST: confirm a `frame_manifest.csv` exists for a tennis run whose frame indices are
      commensurable with G161's labels, and say which run and which file. **G170 matters here: the
      local reference clip was overwritten at 09:45:18, and G161 labelled the 2 GB encode while G152b
      measured the 38 MB one. Both decode 28,773 frames, so indices are comparable -- but say
      explicitly which artefact you joined and do not assume.** If no commensurable manifest exists,
      produce one by running the adapter ON THE POD under nohup, and say so.
  (b) The histogram: over the ELIGIBLE DENOMINATOR of the 113 RALLY_VIEW-labelled frames, report the
      count and share in each `status` value. Never a bare sample size. Report the NOT_RALLY frames as
      a separate column so the contrast is visible.
  (c) Name the single largest killer of rally frames and its share. That is the deliverable. If two
      stages are within noise of each other, say so rather than picking one.
  (d) For the largest killer, say from QUOTED CODE what condition produces it, with file:line. Do not
      propose a fix in this row and do not change a threshold -- the point is to know where to aim.
  (e) State the label-agreement caveat: G161's 49/50 = 0.980 is SELF-agreement by one rater and says
      nothing about validity, so every share here inherits that limit. Say it in the memo.

DO NOT change the adapter, the solver, the harness, any threshold, the coverage bar, the coordinate
contract, or any verdict. Do not re-label. Do not build a rally classifier -- that was adjudicated as
work with no decision attached.

ACCEPTANCE RULE:
  metric        = per-`status` counts and shares over the 113 rally-labelled frames, with NOT_RALLY
                  alongside; the largest killer named with its share; its condition quoted from code
  before        = the solver is known to fail on ~3 of 4 rally frames and the stage is unidentified
  bar           = NO pass bar. Success is the histogram with its denominator named and the largest
                  killer identified. "Two stages are indistinguishable" is a full success.
  n             = 113 rally-labelled frames (CONSTRUCT, exhaustive over G161's committed labels)
  eye check     = REQUIRED: render 5 frames EVENLY sampled from the largest-killer bucket (A3, B7 --
                  never a head slice) and say what the eye sees in each
  must not move = the adapter, the solver, the harness, every threshold and bar, the coordinate
                  contract, G161's labels, and every verdict
EVIDENCE: docs/evidence/tracking/g175_rally_stage_histogram_2026-09-03.md with the histogram, the
named killer, the quoted condition, renders under docs/evidence/tracking/g175_stages/, and a NOT
VERIFIED list. Commit BEFORE reporting (A7).
TEST: one per-file test only if you add code. NEVER a full pytest.
COMMIT: explicit pathspec only, in a3, no push. Report the sha and the largest killer with its share.
NEVER PARK.
