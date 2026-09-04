GAP G281 | sport wnba | worktree a6 | log g281_identity_purity_one_second
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **The RECORD ANALYSIS is LOCAL.** G267's artifact is committed in this worktree at
    `docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`.
    Sampling, pair construction and all arithmetic happen locally, no pod.
  - **The CROP RENDER is on the POD**, because the full-resolution source lives only there. Use
    **`~/bin/pod_run a6 --ship <harness> --fetch <crops and summaries> -- <cmd>`**. **The disk guard
    belongs INSIDE that command.** A missing `/workspace` locally is NOT a disk failure; it means that
    step belongs in `pod_run`.

**HOLD RULE -- COUNT DISTINCT LANE WORKTREES, NOT PYTHON PIDs.** One lane routinely shows TWO python PIDs
sharing one `cwd` (G274 verified this for `/workspace/wt/a17`). **Reduce to the SET of distinct
`/workspace/wt/a*` directories and compare THAT to 2.** Exclude your own process, your checker and its
parent. **Report the SET you observed, and also record `nvidia-smi` utilisation and each occupant's ARGS
as evidence only -- do NOT act on them and do NOT propose a new N.**

**READ THE LANDED G272b, G273 AND G276b MEMOS AND THE G272b-CATEGORY-A-CORRECTION ROW FIRST.**

**WHY THIS ROW EXISTS -- IDENTITY IS THE ONE AXIS THIS PROGRAMME HAS NEVER MEASURED.**
Every memo in the tracking chain closes with "identity remains unvalidated". G272b judged "same person?"
only on **jump-conditioned adjacent-frame** steps; G276b measured **person-ness**, not identity. **Nobody
has asked whether a track id refers to the same human a second later**, which is the minimum an
identity claim requires.

**The population exists and is large.** Verified locally 2026-09-04 from the committed artifact:
**98 distinct `track_id`s, 20,551 same-id pairs exactly 30 frames apart (1.00 s at 30 fps), 17,681 pairs
90 frames apart, 83 ids spanning at least 30 frames and 66 spanning at least 90.** **G267's records are
every-frame and contiguous**, unlike the stride-3 pod runs G277 hit, so a fixed 30-frame gap is exact
here.

THE QUESTION: **when a track id persists for one second, is it still on the same person?**

METHOD:
  1. **BUILD THE PAIR POPULATION LOCALLY.** Same `track_id` present at both frame `f` and `f+30`, **both
     endpoints `finite`, and both endpoints on court** using G270's on-court definition unchanged.
     **State the eligible pair count** -- it is the denominator and it is NOT 20,551, which is the
     pre-on-court figure. **If your count differs from mine, report yours and say so.**
  2. **SAMPLE AT LEAST 80 PAIRS**, spread across the span AND across distinct ids, **not a head slice**.
     Report id and frame coverage. **Sample on NOTHING downstream** -- not speed, not displacement, not
     jumps. **At most a handful of pairs per id**, so a single long track cannot dominate; say the cap.
  3. **RENDER BOTH ENDPOINTS AS SEPARATE CROPS** with G272b's technique: footpoint-centred, full
     resolution, **NO bounding box drawn or inferred** (G267 retained no box extents). State the crop size.
  4. **PASS 1 -- PERSON-NESS, PAIRING HIDDEN.** Pool **all 160+ crops into ONE randomised blind order** so
     the labeller cannot tell which two belong to the same pair, exactly as G276b did. **Commit the order
     and verdicts in their own commit BEFORE un-blinding.** Categories are **G273's four, unchanged**:
     **(a) PLAYER on the court of play; (b) PERSON, not a player in play; (c) NOT A PERSON; (d) CANNOT
     JUDGE.** **Keep (d) separate.**
  5. **PASS 2 -- IDENTITY, PAIRING NOW VISIBLE BY NECESSITY.** **Only for pairs where BOTH endpoints were
     classified (a) or (b) in Pass 1** -- i.e. both are people -- present the two crops together in a
     fresh randomised order and judge exactly: **SAME PERSON / DIFFERENT PERSON / CANNOT JUDGE.**
     **Commit this order and its verdicts in their own commit before un-blinding too.** **Say explicitly
     in the memo that Pass 2 must show both crops, so its pairing is visible by necessity, and that this
     is why person-ness was measured separately in Pass 1 where the pairing was hidden.**
  6. **REPORT ID PURITY WITH ITS DENOMINATOR SPELLED OUT**: `SAME / (SAME + DIFFERENT)` among judgeable
     person-person pairs. **Give the full funnel: sampled pairs -> both-endpoints-person pairs -> judgeable
     pairs -> same / different.** **Never quote the purity against the sampled-pair count.** Give a 95 pct
     Wilson interval and **do not present the rate as exact**.
  7. **REPORT THE RECORD-ONLY TRACK STATISTICS TOO**, which cost nothing: distinct id count, track length
     distribution in frames and seconds, and how many ids span at least 30 and at least 90 frames.
  8. **FRAGMENTATION IS OUT OF SCOPE AND MUST BE NAMED AS SUCH.** This row measures whether ONE id stays
     on ONE person. **It does NOT measure whether one person is split across several ids**, which is the
     opposite failure and needs its own row. **Say so; do not let a good purity number read as good
     identity.**
  9. **Do NOT re-detect, re-associate, re-render G267's records, or touch `src/`. Do NOT propose a
     production change, filter, gate or threshold.**
 10. **The population is detector boxes, not authenticated players.** **Name every denominator; never say
     "players" unqualified.**

**DISK GUARD, POD SIDE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- about
**39,011 MB at 2026-09-04 14:04**, roughly **11 GB free** against the 50 GB quota, and **a peer session
writes under `/workspace/wt`.** **Re-measure yourself.** **`dd conv=fsync` probe before writing, STOP and
report if it fails ON THE POD.** **160+ crops are the bulk -- keep them modest and report committed
bytes.** **Do NOT delete any corpus source, and do NOT delete the two abandoned bridge partials
(`baseball__npb_05.mp4.part` 2.4 GB, `football__football_m8UWuQoflJo.mp4.part` 4.7 GB): they are resumable
acquisitions and the football one is the only football footage in the programme.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** ONE clip, ONE camera shot (source frames 19599-23399), ONE
arena, **ONE labeller**, ONE non-deterministic detector draw. **Per G278 that span is measurably friendlier
than the clip (0.836 against 0.656 court-bearing, p = 0.0078), so this purity figure may NOT be quoted
clip-wide.** **Endpoint-only judgement cannot see a track that drifts onto a third person and back within
the second** -- it bounds purity from above. **A footpoint-centred crop is not the detector's box**; it
shows the neighbourhood claimed, not the extent. **One second is one horizon**: purity at 3 s or 10 s is a
different and probably worse number, and this row says nothing about it. Eye-label reliability in this
programme has never cleared 80 pct blind agreement on four measured criteria.

ACCEPTANCE RULE:
  metric        = the eligible pair count with its on-court definition; sample size with id and frame
                  coverage and the per-id cap; both committed blind orders and verdict sets; Pass 1's four
                  counts; the full funnel to Pass 2; **ID purity with its named denominator and a 95 pct
                  Wilson interval**; and the record-only track statistics
  before        = identity is unvalidated everywhere in this programme; no row has ever asked whether a
                  track id refers to the same human one second later
  bar           = **NO pass bar.** **A LOW purity would be a major finding and would mean the tracker's
                  ids cannot carry any per-player quantity.** **A HIGH purity would be the first positive
                  identity evidence the programme has, and would still be bounded above by the
                  endpoint-only limitation.** **"Too few judgeable pairs to say" is ALSO a full success.**
                  Do not tune, do not filter, do not assert causation.
  n             = 1 clip, 1 shot, the eligible pair count and sample size you state, 1 labeller -- name
                  every denominator in the verdict line, and name the detector-box population
  eye check     = both passes ARE the measurement; they are COARSE categorical judgements, not the
                  sub-pixel geometric one G257 bounded at 20 px. **Say that distinction.**
  must not move = every threshold, bar and verdict, G267's retained records and span, G270's on-court
                  definition, G273's four categories, G272b's and G276b's counts and sealed orders,
                  G233d's published map, the court model, the coordinate contract, `src/` and `domains/`
                  (READ and IMPORT ONLY), the pod daemon and keeper, the corpus, the bridge partials
EVIDENCE: docs/evidence/tracking/g281_identity_purity_one_second_2026-09-04.md with the pair population,
the sampling description, both committed blind orders, every crop, Pass 1's counts, the funnel, the purity
figure with its interval, the track statistics, the fragmentation-out-of-scope statement, every disk-guard
probe with the `du -sm /workspace` figure, bytes freed and committed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
