GAP G304 | sport wnba | worktree a4 | log g304_e1_sealed_heldout_packet
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check against every line of
section B before you report.
**ANNOTATION AND SEALING ONLY. NO FITTING, NO HOMOGRAPHY, NO PREDICTION, NO DETECTOR AND NO MODEL RUN
OF ANY KIND IN THIS ROW.** `src/`, `domains/` and `kernel/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/` (not human-gated; additive only; <= 300 LOC per file).
**THIS ROW IS THE PREREQUISITE FOR G306, G307 AND G308. All three are BLOCKED-ON it. A registration
result never translates into the ledger passed field.**
SOURCE OF EVERY RULE BELOW: `docs/research/astra_tracking_registration_2026-09-07.md` section 2. The
numbers are quoted from it verbatim and may NOT be moved by this row or by any consumer.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **ENTIRELY LOCAL. NO POD, NO GPU, NO `pod_run`, NO GPU LEASE.** Every source file named below is
    on this box. Decoding 60 frames from two local mp4 files is CPU work.
  - **NO DISK GUARD IS REQUIRED** -- this row writes frames, crops and JSON, never corpus video.
    **Delete no corpus source and no bridge partial download.** Report bytes you added.
  - If a step of yours would need the pod, you have misread the row: STOP and say so.

**PREMISE (step 0) -- BINDING BEFORE-CONDITION. The orchestrator has already measured the inventory
below with `ffprobe`; your job is to CONFIRM it and to seal it, not to rediscover it.**
E1 requires (memo section 2): "two native-1080p broadcasts from different arenas, 30 frames each:
20 eligible court views from >=4 shots and 10 negatives."
  - **CANDIDATE A: `data/videos/bridge/wnba_01.f137.mp4`** -- h264, **1920x1080**, avg_frame_rate
    **30/1**, duration **5814.333333** s, size **2841750689** bytes.
  - **CANDIDATE B: `data/videos/bridge/wnba_04.f137.mp4`** -- h264, **1920x1080**, avg_frame_rate
    **30/1**, duration **3193.666667** s, size **1114349874** bytes.
  - **FALLBACK C (different league, use only if A or B fails identity):**
    `data/videos/bridge/ncaa_basketball_IB-_u4gW3ds.mp4` -- h264, **1920x1080**, **30000/1001**,
    nb_frames **205444**, duration **6855.014000** s, size **3580059573** bytes.
  - **ARENA IDENTITY IS TRANSCRIBED, NOT VERIFIED.** `RESULTS_LEDGER.md:63` and
    `TRACKING_GAPS_2026-09-01.md:403` record `wnba_01` as the Atlanta Dream's **Gateway Center Arena**
    and `wnba_04` as **Climate Pledge Arena** (a two-tone tan hardwood plus forest-green painted
    apron). **Confirm arena distinctness YOURSELF by eye on decoded frames from each and record what
    you saw**; E1 is void if the two broadcasts share an arena.
  - **The other local basketball sources are 720p and are INELIGIBLE**: `data/videos/*.mp4`
    (cavs_broadcast_2025, bos_mia_2025, nba_highlights_gsw and siblings) all probe **1280x720**.
  - **Verify the two videos exist as the declared original 1080p bytes. An `_1080p` filename, a
    derivative or a historical frame index is INSUFFICIENT.** Record the **SHA256 of each source
    file** yourself. **Any mismatch => PREMISE FALSE, write the memo, commit, stop.**
  - **A SECOND ARENA IS ALREADY PRESENT, so the footage bridge is NOT part of this row.** Only if
    candidate A or B fails byte identity may you acquire a replacement, and then **LOCALLY ONLY** via
    the existing footage bridge (`scripts/platformkit/tracking/` bridge tooling; the 1080p recipe is
    `--cookies` plus HLS 300/301 -- `player_client=web` exposes only itag 18 and yields 360p).
    **NEVER acquire footage on the pod.**

**CHANGE (step 1) -- build the sealed packet, in this order, and never out of it:**
  1. **TIME-STRATIFIED INVENTORY FIRST.** Build a candidate-frame inventory stratified over each
     broadcast's full duration. **The annotator who selects frames must not see any candidate output,
     any projection, any homography or any detector result** -- none exists yet, and this row is what
     keeps it that way.
  2. **SELECT 30 FRAMES PER BROADCAST = 60 ROWS TOTAL.** Per broadcast: **20 eligible court views
     drawn from >=4 distinct camera shots**, and **10 negatives declared OUT OF SCOPE BEFORE any
     inference: exactly 4 close-ups, 3 graphics/transitions, 3 replay/alternate-camera views.**
     Eligibility requires identifiable, well-spread court evidence -- state the rule you applied.
  3. **SIX NAMED COURT LANDMARKS PER ELIGIBLE FRAME, ACROSS >=3 DISTINCT MARKING STRUCTURES**
     (for example a sideline, a free-throw-lane boundary and an arc -- not six points on one line).
     These are RESERVED FOR EVALUATION and must be **separate from any manually fitted seed feature**
     that G306 will later use. 40 eligible frames x 6 = **240 held-out correspondences**.
  4. **TWO INDEPENDENT LOCATORS annotate NATIVE ZOOMED CROPS before seeing any projection.**
     **Declare plainly whether each locator is a human or a model** and name it. G296b is ONE model
     locator's input, not verified truth (memo section 3), and G280b/G291 measured crop judgements to
     be rater-sensitive -- so **inter-locator agreement must be reported, not assumed.**
  5. **ADJUDICATE feature identity and every difference > 4 px before sealing.**
     **Unresolved labels mean INSTRUMENT NOT VALIDATED -- they are NOT omitted frames and NOT
     successful abstentions. Agreement alone never establishes correctness.** Say both sentences.
  6. **SEAL, BEFORE ANY PREDICTION EXISTS.** Freeze in one committed manifest: **source SHA256,
     decode hashes, frame indices, PTS, dimensions, league, shot identity, court-end identity, and
     all 60 rows.** Emit a single SHA256 over the manifest -- that hash is the packet's identity and
     every consumer row (G306, G307, G308) must quote it.
  7. **RECORD THE FRAME-GOOD RULE AND THE ACCEPTANCE BARS IN THE MANIFEST so consumers cannot restate
     them differently:** frame-good = correct shot/end orientation, finite H, and named held-out
     reprojection error **p90 <= 12 px AND max <= 24 px in original 1920x1080 pixels**; errors use the
     **fixed six correspondences**, never nearest arbitrary edges, candidate-chosen points, fitted
     corners or a censored search window; primary acceptance = **>=16/20 frame-good in EACH arena,
     <=1/10 accepted negatives in EACH arena, and no accepted wrong-end map**; **abstentions on
     eligible frames count as failures**; **zero false acceptances among the 40 eligible frames**.
  8. **Attempt 2 of every consumer route needs a DIFFERENT sealed packet.** Record the wall time and
     the annotation burden this packet cost, so that second packet can be budgeted honestly.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the sealed packet: 2 broadcasts x 30 frames = **60 rows**; per broadcast 20 eligible
                  from **>=4 distinct shots** plus 10 negatives in the declared **4 / 3 / 3** split;
                  **240** held-out correspondences (40 eligible x 6 landmarks across >=3 marking
                  structures); two-locator annotation with every **>4 px** disagreement adjudicated;
                  one manifest SHA256 over source SHA256s, decode hashes, frame indices, PTS,
                  dimensions, league, shot and court-end identities and all 60 rows
  before        = **no E1 exists.** The memo states it plainly (section 5): E1, its second-attempt
                  replacement, a second native-1080p arena and reviewed seed atlases are
                  "prerequisites, not claimed existing artifacts". E0 (the 17 G140 frames / 68
                  targets, of which 12 are native 1080p) is repeatedly inspected development material
                  and **a success on it is feasibility evidence only, never a held-out success**
  bar         = every count above met EXACTLY, sealed BEFORE any prediction exists, with the source
                  bytes confirmed and the two arenas confirmed distinct. **A shortfall is not a
                  failure of this row -- report the exact shortfall and the reason; an incomplete
                  packet means INSTRUMENT NOT VALIDATED and G306-G308 stay blocked.**
  n             = 60 rows (CONSTRUCT -- every selected frame is enumerated, not sampled), 40 eligible,
                  20 negatives, 240 correspondences, 2 broadcasts, 2 arenas, 2 locators. Name every
                  denominator in the verdict line
  eye check     = **ALL 60 selected frames are themselves the eye check** -- render each at native
                  size with its six landmarks overlaid, EVENLY SPACED by construction over the
                  stratified inventory, no head slice. Publish the negatives' renders too
  must not move = `src/`, `domains/`, `kernel/` (READ and IMPORT ONLY); `scripts/platformkit/
                  tracking_harness.py` and CONFIG_VERSIONS `2026-09-01-v1`; every existing threshold
                  and verdict; E0 and the G140 labels; both bridge sources and every partial download;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` (the orchestrator owns it)
NON-TAUTOLOGY: the packet covers all 60 selected rows and excludes nothing after selection. **A frame
may NOT be dropped once selected** -- if a frame proves unannotatable, it stays in the manifest marked
UNRESOLVED and counts against the instrument, because dropping the hard frames is precisely the
circularity the memo names.

ATTEMPT 2 (the memo's limit measurement, if attempt 1 falls short): **measure the achievable
annotation yield and its cost** -- how many of 60 frames survive independent adjudication, the
inter-locator disagreement distribution, and the wall-clock annotation burden per frame. **If a second
native-1080p arena cannot be staged at all, that is the LIMIT and the row closes CLOSED AT LIMIT with
that stated; it is not a model failure and no route is thereby refuted.**

EVIDENCE: `docs/evidence/tracking/g304_e1_sealed_heldout_packet_2026-09-07.md` with the ffprobe
confirmation, both source SHA256s, the arena-distinctness eye note, the selection rule, the per-frame
table, the inter-locator agreement and adjudication log, the manifest SHA256, bytes added, and a
**NOT VERIFIED list** that at minimum carries: the transcribed arena identities if you could not
confirm one by eye, any unresolved label, whether either locator is a model rather than a human, and
that this row measures NO registration, NO calibration and NO tracking quality whatsoever.
**REQUIRED EVIDENCE DURABILITY:** the manifest JSON and all 60 rows go under `docs/evidence/`; a
directory of renders may stay local, but the numbers behind them must not.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test, **importing full package paths**
(`scripts.platformkit.tracking....`), run as a single file only -- **NEVER a full pytest.** It must
pin: the 60/40/20 counts, the 4/3/3 negative split, the >=4-shot rule, six landmarks across >=3
marking structures, the >4 px adjudication threshold, and that the frame-good rule stored in the
manifest reads p90 <= 12 px AND max <= 24 px. **If a commit grows an allowlisted file, raise its entry
in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
