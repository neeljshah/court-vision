GAP G209 | sport all | worktree a7 | log g209_footage_heterogeneity_census
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build any harness
in `scripts/platformkit/tracking/`.

**S1 MACHINE: the corpus lives on the POD, but this row must stay LIGHT.** G203 is measuring decode
BYTE IDENTITY on that machine and heavy decode would perturb it.
  - **ALLOWED:** `ffprobe` **metadata only** (`-show_streams`, `-show_format`). Instant, no decode.
  - **FORBIDDEN in this row:** `ffprobe -count_frames` (the orchestrator measured one at **1,958
    seconds of CPU**), full decodes, `run_clip.py`, any model inference, and any GPU use.
  - Extracting a handful of single frames per clip is allowed ONLY if G203 has finished by the time
    you reach that step. **Check for its EXIT line first; if it is still running, SKIP frame
    extraction, do the metadata half, and say so.**
**Never kill, restart or deploy over the pod daemon or keeper. Delete NOTHING.**

**WHY THIS ROW EXISTS -- the programme's goal has been sharpened by the user.** The target is
**tracking ANY game, from ANY video, per sport** -- broadcast, amateur, high-school, whatever -- the
way commercial systems claim to. **Heterogeneity IS the problem, not a detail.**

**THE GAP THIS ROW MEASURES, and the orchestrator's honest statement of it:** essentially every
measurement in this programme has run on **ONE clip, `wnba__wnba_01.mp4`** -- G189, G190, G193, G195,
G198, G203 all use it. G191 is the only per-sport baseline. **So we have almost no evidence about how
the route behaves on footage that differs from that one file**, and no description of what our corpus
even spans.

**You cannot claim robustness across footage you have never characterised. Characterise it.**

METHOD:
  1. **Enumerate the whole corpus.** The orchestrator measured **11 clips across 7 sports** (wnba,
     ncaa_basketball, tennis, soccer, football x2, mlb, kbo x2, npb x2) totalling 24 GB, plus 2
     staging downloads. Confirm the current set yourself and **name the ELIGIBLE DENOMINATOR** as the
     number of clips you could probe, with every exclusion named.
  2. **Per clip, from metadata only:** resolution, aspect ratio, frame rate (and whether it is
     variable), codec, profile, bit rate, duration, container, audio presence, and file size.
     **Report the DISTRIBUTION over the whole corpus, not examples** (S2).
  3. **Then answer the question that decides where robustness work goes: what does this corpus NOT
     span?** Be concrete and unflattering. Consider at least: amateur or high-school footage; fixed
     single-camera footage; sub-720p sources; variable frame rate; portrait or non-16:9; heavy
     scoreboard or graphics overlay; non-green/non-standard courts; poor lighting. **State plainly
     which of these we have ZERO examples of.**
  4. **Tie it to a known failure mechanism.** `unified_pipeline.py:1007` comments that at `imgsz=640`
     players are about **25 px** tall on a 1280-wide broadcast frame, and that 480 gives ~19 px which
     is "below reliable detection". **So player pixel height is a first-class robustness variable.**
     For each clip, estimate the expected player pixel height purely from its resolution and the
     stated relationship, and say which clips would fall near or below the 19 px figure at the
     configured `imgsz`. **Label this an ARITHMETIC PROJECTION from a code comment, not a
     measurement** -- you are not running the detector in this row.

**DO NOT propose a fix, tune anything, or recommend a model change.** The deliverable is a
characterisation and an honest gap list.

ACCEPTANCE RULE:
  metric        = per-clip metadata table; the whole-corpus distribution of each field; an explicit
                  list of footage classes with ZERO representation; the player-pixel-height projection
  before        = the corpus has never been characterised, and almost every measurement in the
                  programme rests on a single 1920x1080 professional broadcast clip
  bar           = NO pass bar. **"The corpus is entirely professional broadcast and we have zero
                  amateur, zero fixed-camera and zero sub-720p footage" is a FULL SUCCESS** and is
                  exactly the kind of statement that should redirect the programme. Do not soften it.
  n             = every corpus clip (CONSTRUCT, exhaustive); name exclusions
  eye check     = only if G203 has finished: one frame per clip, and say in one line what each shows
                  (camera style, surface visibility, overlay). Otherwise SKIP and say so.
  must not move = every threshold, bar, verdict, the coordinate contract, `src/` (READ ONLY), the pod
                  daemon and keeper, the corpus (delete NOTHING, download NOTHING)
EVIDENCE: docs/evidence/tracking/g209_footage_heterogeneity_census_2026-09-03.md with the per-clip
table, the distributions, the zero-representation gap list, the player-pixel projection clearly
labelled as a projection, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
