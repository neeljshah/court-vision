GAP G226b | sport wnba | worktree a6 | log g226b_basketball_adapter_pod_run
**VALIDATION RUN ONLY. Change NO production code** unless a defect in the new adapter blocks the run --
see the narrow exception below. `src/` is HUMAN-GATED: READ and IMPORT only. Build in
`scripts/platformkit/tracking/`.

**HELD -- DO NOT RUN ON THE POD UNTIL G211 HAS REPORTED.** G211 is measuring per-frame cost there and a
route job would corrupt it. **Check first and say in your memo that you checked and when you began.**
The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and
`foundry_runner` are PERMANENT residents and the load floor -- **never wait for them and never kill or
restart them.** Harness and test preparation may proceed immediately.

**WHY THIS ROW EXISTS -- G226 BUILT THE ADAPTER BUT DELIBERATELY DID NOT VALIDATE IT, AND SAID SO.**
G226 landed `domains/basketball/tracking/adapter.py` (169 lines) and `geometry.py` (29 lines), registered
`"basketball"` in `scripts/platformkit/adapter_run.py`, and added basketball to `PLAYER_ONLY` and
`IMAGE_SPACE`. **8 adapter/geometry tests, the 9 shared `test_adapter_run.py` tests and the LOC rail all
pass in master.** But the lane correctly declined the pod run because G211 had not reported, and wrote:
*"No G211 result artifact is present in this worktree. Its specification is not a report."* **So the
claim "basketball reaches SCORED" is currently UNEVIDENCED. This row evidences it or refutes it.**

**THE BEFORE STATE, from G207's landed census:** basketball is the only sport with **zero scored rows** --
`wnba` 0 scored / 2 EXCLUDED, `ncaa_basketball` 0 scored / 1 EXCLUDED -- all for **noncanonical
columns**. The legacy `unified_pipeline` table emits `frame, timestamp, player_id, team, x_position,
y_position, x_norm, ...` and declares **no `coordinate_space`, no `calibration_provenance`, no
`projection_status`**, so the harness cannot audit its frame of reference and drops it before any gate.

THE QUESTION: **does the new adapter produce a table the harness SCORES rather than EXCLUDES?**

**WHAT SUCCESS LOOKS LIKE, AND IT IS DELIBERATELY MODEST: SCORED, then FAILING `coordinate_contract`.**
Football, baseball and soccer all emit `image_px` and all fail that gate -- **but they are scored, so
their failure is visible and measurable. Basketball is not even that.** **A `coordinate_contract`
failure here is the EXPECTED and ACCEPTED outcome and must be reported as the success it is.** **Do NOT
change the coordinate contract, any gate, any threshold, or the harness to make a row pass** -- that is
the one action that would make this row worthless. Automatic basketball corner search is measured at
**0/17** (G210b, G214), and tonight **G224 closed the top-hat transfer AT LIMIT** and **G223 showed the
line error is scatter with no deterministic correction**, so there is no basis whatever for emitting a
court coordinate here.

METHOD:
  1. **Deploy nothing by hand.** Use the repository's normal mechanism to make the new adapter available
     on the pod, and **record exactly how the pod checkout obtained it, plus the SHA-256 of
     `adapter.py`, `geometry.py` and `adapter_run.py` as they exist ON THE POD at run time.** If the pod
     checkout does not have the new files, **say so and stop rather than hand-copying** -- how code
     reaches the pod is itself a finding worth recording (B5).
  2. **DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE here -- it reports the whole cluster filesystem
     against a 50 GB volume cap, which caused a `Disk quota exceeded` incident. **Do a real
     `dd ... conv=fsync` write probe of a few MB before writing, record
     `du -sm /workspace/nba-ai-system/data` (baseline ~31,100 MB of 50,000), and STOP and report if the
     probe fails -- do not delete anything to make room.**
  3. Run the adapter on **ONE basketball clip, BOUNDED** (`wnba__wnba_01.mp4` is the reference: A9
     2,931,985,407 bytes, 1920x1080, 174,430 frames). **Write to a NEW tracking directory. Do NOT
     delete, overwrite or migrate the existing legacy basketball tables** -- they are the historical
     record and G207, G226 and this spec all cite them.
  4. **Score the result with the harness** and report the **verdict and the FIRST FAILURE HEAD**
     verbatim. Report **which stage the row reached**: EXCLUDED, UNSCORABLE, or SCORED.
  5. **Give a column-by-column comparison of the emitted header against the canonical schema**
     (`frame, track_id, cls, x, y, calibration_provenance, projection_status,
     projection_rejection_reason, raw_projected_x_ft, raw_projected_y_ft, coordinate_space, observation,
     calibration, source_fps, source_height, source_duration`), read from a real adapter table on the
     pod rather than transcribed from this spec. **Name any column present, missing or extra.**
  6. **Report the emitted row count and the ELIGIBLE DENOMINATOR** as attempted/evaluated frames, never
     `--frames`. G206 established that `--frames N` counts detector-selected gameplay frames and fails
     closed, so **do not present it as a denominator.**
  7. **NARROW EXCEPTION, and use it only if the run is blocked:** if the new adapter has a defect that
     prevents it running at all, you MAY fix it in `domains/basketball/tracking/` -- that area is not
     human-gated -- **provided the fix is minimal, preserves the honest `image_px` provenance, keeps
     every file under the 300 LOC rail, adds or updates a per-file test, and is reported prominently as
     a CHANGE rather than buried.** **Never touch `src/`, the harness, any gate, or another sport's
     adapter.** If the defect is outside `domains/basketball/`, STOP and report it.
  8. **Clean up every temporary artifact and report bytes freed.**

**HONEST LIMITATIONS to state, not discover:** one clip and one bounded run is an EXISTENCE result, not
a rate. The route is NON-DETERMINISTIC and no deterministic mode exists -- G190, G195, G198, G199 and
G203 exhausted every enumerated candidate, and G203 showed decode is byte-identical while output still
differs -- **so a single score is one draw and must not be presented as stable.** An adapter is
**necessary but demonstrably NOT sufficient** for court coordinates: football, baseball and soccer all
have adapters and all still fail `coordinate_contract`. **You are not claiming the legacy basketball
feature table is wrong**; it is a different artifact and this row adds a canonical one beside it.

ACCEPTANCE RULE:
  metric        = the stage reached (EXCLUDED / UNSCORABLE / SCORED), the harness verdict and first
                  failure head verbatim, the column-by-column schema comparison, the emitted row count
                  with its named eligible denominator, and the pod-side SHA-256 of the three files
  before       = basketball is 0 scored / 3 EXCLUDED for noncanonical columns; the adapter is built and
                  unit-tested in master but has never run on real footage
  bar          = **basketball reaches SCORED rather than EXCLUDED.** A `coordinate_contract` failure at
                 that point is the expected success. **An honest failure to reach SCORED, with the
                 reason named, is also a real result** -- report what is missing. Change no gate,
                 threshold, contract or harness to force a pass.
  n            = 1 clip, 1 bounded run (EXISTENCE, not a rate)
  eye check    = none; this row is a schema and contract result
  must not move = the coordinate contract, the harness, every gate, threshold, bar and verdict,
                  `src/` (READ and IMPORT only), the other sports' adapters and registry entries, the
                  existing legacy basketball tables, the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g226b_basketball_adapter_pod_run_2026-09-04.md with the stage reached,
the verdict and first failure head, the schema comparison, the row count and denominator, the pod-side
file hashes and how the code got there, every disk-guard probe result, bytes freed, any change made
under the narrow exception reported prominently, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: per-file tests only, pasted. NEVER a full pytest. **If a commit grows an allowlisted file, raise
its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
POD: run there; never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
