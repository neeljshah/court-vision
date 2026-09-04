GAP G239 | sport ncaa_basketball (amateur tier) | worktree a4 | log g239_adapter_on_amateur_footage
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. Build
in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G236 and G238 may be running; N=2 is the measured optimal schedule per
G200/G216). **Check first and say in your memo that you checked and when you began.** The `track_daemon`,
`keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT
residents and the load floor -- never wait for them, never kill or restart them.

**WHY THIS ROW EXISTS -- IT IS THE FIRST TIME THE PROGRAMME CAN ASK ITS OWN CENTRAL QUESTION WITH REAL
EVIDENCE: DOES THE TRACKER WORK ON FOOTAGE THAT IS NOT A PROFESSIONAL BROADCAST?** G213 established the
corpus was MONOLITHIC -- every clip professional broadcast with a moving camera, and **zero** fixed
single-camera and **zero** amateur game-camera footage -- so no robustness claim was supportable by
construction. **G220c-ACQUIRED changed that.** There is now a verified clip on the local box:

    data/videos/g220c_amateur_footage/g220c__jh3fnwMi7dM.mp4
    346,739,796 bytes | ffprobe: 1920x1080, 28,865 frames, 960.100 s

a 16-minute section of a Coaches Camera high-school varsity game. Two extracted frames 13 minutes apart
show **identical framing** -- same bleachers, court position and letterbox bars, no pan or zoom -- in a
school gymnasium with wooden bleachers, a small crowd, a light scoreboard overlay that does not occlude
the floor, roughly half-court visible, and gym lighting with visible floor glare. **Those are
single-labeller judgements from 2 of 5 frames; treat them as a hypothesis about the footage, not a fact.**

**THE BASELINE TO COMPARE AGAINST IS ALREADY MEASURED, on professional broadcast footage, through the
SAME adapter (G226c, G226c-OUTPUT, G226c-IDENTITY, G226c-HONESTY):**

    clip                 wnba__wnba_01.mp4 (professional broadcast, moving camera)
    invocation           adapter_run basketball ... --max-frames 6000
    evaluated frames     6,000        emitted rows      64,171
    frames with players  5,972        players/frame     min 1, MEDIAN 11.0, p90 16, max 27
    distinct track ids   207          track length      min 1, MEDIAN 205, p90 730, max 2,270
    one-frame tracks     1 of 207     duplicate (frame,track_id)  0
    in-frame fraction    100.00 pct of rows inside 1920x1080
    harness              SCORED, first failure head coordinate_contract on image_px

METHOD:
  1. **Upload the clip to the pod** (346 MB; ~17 GB headroom). **DISK GUARD, BINDING:** `df` is
     NON-AUTHORITATIVE here -- **`dd conv=fsync` probe before and after, record
     `du -sm /workspace/nba-ai-system/data` (baseline ~32,250 MB of 50,000), STOP and report if a probe
     fails.** **Do NOT add it to `footage_corpus` and do NOT put it anywhere the daemon will pick it
     up** -- this is a controlled measurement, not an ingest. Say where you put it.
  2. **Run `adapter_run basketball` on it with `--max-frames 6000`, matching G226c exactly**, so the two
     runs are commensurable. **Do NOT use `run_clip`**: G211b measured 400 detector calls and ZERO rows,
     and 9 of 9 historical basketball daemon jobs died in `_build_court` (G234, G234-COMPLETE).
  3. **Report the SAME measures as the baseline table above, in the same units**: evaluated frames,
     emitted rows, frames with players, the players-per-frame distribution, distinct track ids, the
     track-length distribution and one-frame count, duplicate `(frame, track_id)` rows, the fraction of
     rows inside 1920x1080, and the harness stage plus first failure head verbatim.
  4. **Then answer the question directly: how does the tracker behave on fixed-camera amateur footage
     compared with professional broadcast?** **Name every difference with numbers.** **A large
     degradation is a FULL SUCCESS and is the more important result** -- it would be the programme's
     first measured evidence about arbitrary-footage robustness, which is the stated goal. **Equally,
     "it behaves about the same" is a full success** and would be strong evidence the tracker generalises.
  5. **Expect `coordinate_contract` on `image_px` and do NOT try to beat it.** Calibration is unsolved
     for basketball and this clip has no labels. **Change no gate, threshold, contract or harness.**
  6. **Do NOT tune anything for this clip**, do not change `imgsz`, `conf` or `min_players`, and do not
     propose a fix. One clip, one configuration, reported honestly.
  7. **Clean up**: delete every temporary artifact and report bytes freed. **Leave the uploaded clip in
     place only if you say so explicitly and it is outside any daemon-watched directory**; otherwise
     remove it and report the bytes.

**HONEST LIMITATIONS to state, not discover:** **ONE amateur clip against ONE broadcast clip is a
comparison of two clips, not of two populations** -- say so, and do not generalise to "amateur footage"
as a class. The route is NON-DETERMINISTIC (G190/G195/G198/G203), so each side is one draw; G226c's
baseline is itself a single run. The two clips differ in more than production tier -- venue, teams,
lighting, resolution encoding and camera geometry all differ at once -- **so any difference you measure
is CONFOUNDED and cannot be attributed to "amateur" alone.** Row counts measure emission, never
correctness: nothing here says a detection is in the right place.

ACCEPTANCE RULE:
  metric        = the full baseline measure set recomputed on the amateur clip, reported beside G226c's
                  numbers, plus the harness stage and first failure head; and a named, numeric
                  difference statement
  before        = the corpus was monolithic and no robustness claim about non-broadcast footage was
                  supportable; the adapter has been measured on exactly one professional broadcast clip
  bar          = NO pass bar. **A measured degradation and a measured equivalence are equally full
                  successes.** Do not tune for the clip, do not change a gate to improve a number, and
                  do not attribute a confounded difference to production tier alone.
  n            = 1 amateur clip, 1 bounded run, against 1 broadcast baseline run
  eye check    = none required; the extracted frames already exist under
                 `docs/evidence/tracking/g220c_amateur_footage_working_rung_2026-09-04_frames/`
  must not move = every threshold, `imgsz`, `conf`, `min_players`, every bar and verdict, the coordinate
                  contract, the harness, `footage_corpus`, `CLIP_SPORTS`, `src/` and `domains/` (READ
                  and IMPORT ONLY), the pod daemon and keeper
EVIDENCE: docs/evidence/tracking/g239_adapter_on_amateur_footage_2026-09-04.md with the upload location
and disk probes, the side-by-side measure table against G226c, the harness stage and failure head, the
numeric difference statement, an explicit confounding caveat, bytes freed, and a NOT VERIFIED list.
Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
