GAP G345 | sport basketball | worktree a21 | log cx_g345_tracklet_continuity_fixed_dets

**TRACKLET CONTINUITY ON FIXED DETECTIONS (label-free; local CPU; codex PREPARES, a finisher MEASURES).**
`src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/`.
NEVER write `data/registry/`, never flip a flag, never claim an edge, never claim a named-player identity,
never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. No video, no GPU, no pod.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line). Inputs: the
detector streams captured by G336 (`scripts/platformkit/tracking/g336_capture.py` output CSVs committed
under the G336 artifact directory: 4 sections x 240 frames, per-frame boxes + confidences) -- FIXED
detections; no detector is run. If the captures are absent on master, the finisher regenerates them with
G336's capture command on the pod scratch and commits nothing new but the derived CSVs.

**WHY THIS ROW EXISTS.** G336 measured that the production route's 10-slot exporter emits 134-559
instances over 40 frames and that its flagged association variant did not cut fragmentation (0 of 2 scored
sections; 1 of 4 in the 240-frame rerun), and the memo's lesson was that arms were scored on DIFFERENT
observation sets. Astra's ranked row 4: evaluate association on IDENTICAL cached detections, with
generation-scoped tracklet ids, gated reconnects, injected known gaps and crossings, and a reserved
evidence channel (optical flow / crop perturbation) the association never sees. Anonymous tracklets, never
NBA player ids.

**PREMISE (step 0, BINDING before-condition):** load the 4 capture CSVs; PRINT n frames, n detections,
detections per frame (median, p10, p90) per section. Confirm the capture is detector output (no track ids).
**If the captures carry track ids or differ between arms, the premise is FALSE: STOP, write the memo,
commit, report PREMISE FALSE.**

METHOD:
  1. **ASSOCIATORS (`scripts/platformkit/tracking/g345_associate.py`, <= 250 lines), all consuming the SAME
     detections per frame:** ARM_A the route's association (import `src/tracking/advanced_tracker.py`'s
     matcher on the cached boxes; if it cannot run without frames, say so and use its Hungarian + Kalman
     step only); ARM_B G336's variant if it is importable from master; ARM_C a two-stage IoU matcher
     (high-confidence first, then low-confidence, ByteTrack-style, own implementation, no new dependency),
     with a gated reconnect (a lost tracklet may reconnect within 30 frames only if IoU-of-prediction >= 0.3
     AND no other tracklet claims the box). Every id is generation-scoped: `<section>:<generation>:<k>`;
     a reconnect keeps the id; a new start increments k. No appearance model in this row (say so).
  2. **METRICS on the 4 sections (n adjacent frame pairs, n detections):** track starts per 1,000
     detection-supported adjacent pairs; matched observation-seconds / total observation-seconds
     (coverage); simultaneous merges (two detections in one frame assigned one id); mean tracklet length.
  3. **INJECTIONS (200, sealed seed) into the cached detections:** 100 gaps (delete a tracklet's boxes for
     k in [3, 20] frames -- the tracklet is defined by ARM_C on the clean stream, stated as the reference)
     and 100 crossings (swap two boxes' positions over 5 frames). Score reconnect correctness (the id
     after the gap equals the id before) and zero simultaneous merges under crossings.
  4. **RESERVED EVIDENCE.** A crop-perturbation channel the associators never see: for each accepted link,
     the grayscale crop correlation between the two boxes (ZNCC on 32x64 resized crops -- requires the
     section frames; if frames are unavailable locally, mark NOT RUN and say so). Report agreement >= 0.5
     share over accepted links with the denominator and abstentions.
  5. **DECISION TABLE (prereg it).** ARM_C is recommended for a PROPOSED src change only if starts fall
     >= 50 pct vs ARM_A on >= 3 of 4 sections with coverage drop <= 2 pp, reconnect correctness >= 0.95
     and 0 injected simultaneous merges. Otherwise report the measured gap. No src edit in this row.
  6. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** 4 sections x 240 frames is a screening; fewer ids alone is
gameable (coverage and injections guard it); same-kit players can swap while passing continuity; these
metrics are not IDF1 or identity accuracy; the reference tracklets for injections come from an arm.

ACCEPTANCE RULE:
  metric        = premise prints; the metric table (arms x sections) with n; the injection scores; the
                  reserved-evidence agreement (or NOT RUN with reason); the decision row
  before        = the route's association is measured only on its own changing observation sets (G336)
  bar           = every arm scored on byte-identical detections (assert digests); every cell carries n;
                  the injection protocol runs to completion (200/200 scored); the decision rule is
                  applied as preregistered; 0 src edits
  n             = 4 sections x 240 frames; every detection; 200 injections
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, G336's committed artifacts,
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds (the decision may be negative); **PARTIAL** with the arm or
                  injection set that could not run and why.
EVIDENCE: `docs/evidence/tracking/g345_tracklet_continuity_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g345_tracklet_continuity_2026-09-08/arms.csv` and
`injections.csv` (integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g345_associate.py` (ARM_C on a hand-pinned 3-track construct with one gap and
one crossing; generation-scoped ids; digest assertion), alone. **NEVER a full pytest.** Every new file <= 300
lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: seed, gap/crossing ranges, reconnect
thresholds, the decision rule), the module, the injector, the tests and the memo skeleton, and exits
`PREPARED FOR FINISHER` listing the exact commands; it must NOT score the captures itself (Q1). Absent
captures or `data/registry` in the worktree are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
