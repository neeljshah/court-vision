# G226c Basketball Adapter Deployment and One Pod Run - 2026-09-04

## Verdict

**ACCEPT: basketball reached SCORED rather than EXCLUDED.** The one bounded pod
run emitted a real canonical tracking table, which the unchanged harness
accepted far enough to return the expected \`coordinate_contract\` failure. The
verdict is \`FAIL\`; this is the required visible, scorable outcome, not a claim
of court-coordinate validity.

**First failure head, verbatim:**

\`\`\`text
coordinate_contract: rows declare coordinate_space image_px not accepted for sport basketball; a preserved detection corpus is never a scorable game
\`\`\`

This memo executes \`docs/evidence/tracking/specs/G226c_spec.md\` and cites
\`docs/evidence/tracking/VERIFIER_CONTRACT.md\`. It changes no \`src/\` file,
coordinate contract, gate, threshold, harness, daemon source, \`CLIP_SPORTS\`,
legacy basketball table, corpus source, or permanent pod process.

## Hold check, machine, and input

G211b had reported before this row began. At \`2026-09-04T05:56:08Z\`, the live
preflight on the pod (\`/workspace/nba-ai-system\`, required because the adapter
and corpus clip are pod-resident) found no G211b or G226c measurement process.
The observed permanent load floor was the existing tennis \`adapter_run\` job
(85.3 percent CPU at this snapshot), \`foundry_runner\` (23.0 percent),
\`inplay_capture_runner\` (12.4 percent), the scheduler, odds runner,
\`track_daemon\`, and \`keep_track_daemon.sh\`. None was waited on, killed,
restarted, or otherwise changed.

| Full pod path | Bytes | Resolution | Frames | Use |
|---|---:|---|---:|---|
| \`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4\` | 2,931,985,407 | 1920x1080 | 174,430 | One bounded direct basketball adapter run |

This is one shared-pod existence draw, not a rate, repeatability, physical
tracking-accuracy, identity-quality, calibration, or court-coordinate claim.

## Disk guard

\`df\` was not used. The authoritative pre-write measurements and binding probe:

| Time UTC | Check | Result |
|---|---|---|
| 05:56:08 | \`du -sm /workspace/nba-ai-system/data\` | 31,621 MB |
| 05:56:40 | \`du -sm /workspace/nba-ai-system/data\` | 31,625 MB |
| After second measurement | \`dd if=/dev/zero of=/workspace/nba-ai-system/data/.g226c_dd_write_probe bs=1M count=4 conv=fsync\` | Passed; durable 4,194,304-byte probe, SHA-256 \`bb9f8df61474d25e71fa00722318cd387396ca1736605e1248821cc0de3d3af8\` |

The probe was removed after successful verification, freeing 4,194,304 bytes.
Nothing was deleted to make room.

## Exact three-file deployment

Before deployment, the pod runner was backed up at:

\`\`\`text
/workspace/nba-ai-system/scripts/platformkit/adapter_run.py.g226c_backup_20260904T0557Z
\`\`\`

Its SHA-256, and the pre-deploy runner SHA-256, were both:

\`\`\`text
90172789dc13bf771a93c5dacbb9568eceb06783dc51e8b591fa2f380621f4e0
\`\`\`

Exactly these three paths, and no other file, were copied with \`scp\`:

| File | Local SHA-256 | Pod SHA-256 | Match |
|---|---|---|---|
| \`domains/basketball/tracking/adapter.py\` | \`1ecf483df26b19c44d1fa25297caed845e5952fbfdd9b704f95a6125f4366c15\` | \`1ecf483df26b19c44d1fa25297caed845e5952fbfdd9b704f95a6125f4366c15\` | Yes |
| \`domains/basketball/tracking/geometry.py\` | \`3bb48c415131358b4512c795ffba30fa9d88a32c56aefd67ef6958c6a747ea5e\` | \`3bb48c415131358b4512c795ffba30fa9d88a32c56aefd67ef6958c6a747ea5e\` | Yes |
| \`scripts/platformkit/adapter_run.py\` | \`e4abc2f5e4e4fb2a977ca6beb2fed854e33e829eb0a5d96cef8645680f6181c5\` | \`e4abc2f5e4e4fb2a977ca6beb2fed854e33e829eb0a5d96cef8645680f6181c5\` | Yes |

\`bootstrap_pod.sh\` was not run. The adapter-runner backup remains, and the
deployed additive runner remains installed as required.

## Post-deploy daemon-routing check

The pod daemon full SHA-256 is
\`204a892086e9c62a66ff2e9789fa31033f316c7cafc7d548a3e09e0b80da5ada\`; the
local worktree daemon SHA-256 is
\`edbab0f4c4e2870406e3f1baeeda4e4145ee6f91d8d2fd0df0d3dca983bdb48d\`.
They differ outside this deployment. The required pod reread confirms the
safety argument is intact:

\`\`\`python
CLIP_SPORTS = {"wnba", "basketball", "ncaa_basketball", "nba"}

def build_command(sport: str, video: Path, game_id: str) -> list:
    if sport in CLIP_SPORTS:
        return [sys.executable, "scripts/run_clip.py", ...]
    adapter = SPORT_ADAPTER.get(sport, sport)
    return [sys.executable, "-m", "scripts.platformkit.adapter_run", ...]
\`\`\`

Thus every basketball alias returns to \`run_clip.py\` before adapter dispatch.
The differing full-file hash does not break this argument, so rollback was not
required. \`CLIP_SPORTS\` was not touched.

## One bounded adapter run and unchanged scoring

The only run used this new directory and direct adapter invocation:

\`\`\`text
cd /workspace/nba-ai-system
/usr/local/bin/python -m scripts.platformkit.adapter_run basketball \
  data/footage_corpus/wnba__wnba_01.mp4 g226c_basketball_20260904T0558Z \
  --max-frames 6000
\`\`\`

It deliberately did not invoke \`run_clip\` and did not pass \`--skip-features\`.
The direct image-space path reported 30.0 FPS and stride 3 (0.1-second sample
interval). It evaluated **6,000 adapter frames**; this is the named eligible
denominator, not a \`--frames\` argument and not a row-derived denominator. The
input is longer than this bound. The run emitted 64,171 data rows over 5,972
unique emitted frames, leaving 28 evaluated frames without an emitted row. Its
source-frame range was 0 through 17,997, and it has zero duplicate \`(frame,
track_id)\` rows.

The retained output is:

\`\`\`text
/workspace/nba-ai-system/data/tracking/g226c_basketball_20260904T0558Z/tracking_data.csv
\`\`\`

The adapter-run report and a separate direct invocation of the unchanged
\`scripts.platformkit.tracking_harness\` both produced \`verdict: FAIL\` and the
verbatim failure head above. The direct harness command exited 1 as expected.
Under the G207 stage rule, canonical tables that reach coordinate-contract
evaluation are **SCORED**; noncanonical tables are EXCLUDED. This basketball
table is therefore SCORED, not EXCLUDED.

## Header comparison from real pod tables

The basketball header was read from its retained pod CSV, not transcribed from
a specification:

\`\`\`text
frame,track_id,cls,x,y,calibration_provenance,projection_status,projection_rejection_reason,raw_projected_x_ft,raw_projected_y_ft,coordinate_space,observation,calibration,source_fps,source_height,source_duration
\`\`\`

For an independent real-adapter comparison, the pod table
\`/workspace/nba-ai-system/data/tracking/soccer_Z6NTDyxcODs/tracking_data.csv\`
was read. Its actual header is:

\`\`\`text
frame,track_id,cls,x,y,coordinate_space,observation,calibration,source_fps,source_height,source_duration
\`\`\`

| Column | Basketball emitted table | Real soccer adapter table |
|---|---|---|
| \`frame\` | Present | Present |
| \`track_id\` | Present | Present |
| \`cls\` | Present | Present |
| \`x\` | Present | Present |
| \`y\` | Present | Present |
| \`calibration_provenance\` | Present | Absent (basketball additive provenance field) |
| \`projection_status\` | Present | Absent (basketball additive provenance field) |
| \`projection_rejection_reason\` | Present | Absent (basketball additive provenance field) |
| \`raw_projected_x_ft\` | Present | Absent (basketball additive provenance field) |
| \`raw_projected_y_ft\` | Present | Absent (basketball additive provenance field) |
| \`coordinate_space\` | Present (\`image_px\`) | Present |
| \`observation\` | Present | Present |
| \`calibration\` | Present | Present |
| \`source_fps\` | Present | Present |
| \`source_height\` | Present | Present |
| \`source_duration\` | Present | Present |

## Pod route identity

The pod is not a Git checkout. These SHA-256 values identify the exercised
route files:

| File | SHA-256 |
|---|---|
| \`scripts/platformkit/adapter_run.py\` | \`e4abc2f5e4e4fb2a977ca6beb2fed854e33e829eb0a5d96cef8645680f6181c5\` |
| \`domains/basketball/tracking/adapter.py\` | \`1ecf483df26b19c44d1fa25297caed845e5952fbfdd9b704f95a6125f4366c15\` |
| \`domains/basketball/tracking/geometry.py\` | \`3bb48c415131358b4512c795ffba30fa9d88a32c56aefd67ef6958c6a747ea5e\` |
| \`scripts/platformkit/detection/shim.py\` | \`a25ef1fb801d3770546711601dcbaacaf599778d01e01bf18d6432140718b6d7\` |
| \`scripts/platformkit/coordinate_provenance.py\` | \`7532a9a63defee149ee88dd6df12e6b247b14388a8d9a3e4a74e5b3268e10f83\` |
| \`scripts/platformkit/tracking_media_inventory.py\` | \`b9e1d0d70064566d360dc8dec8813d6c936998f14f30fb0530e8596aaef989f0\` |
| \`scripts/platformkit/tracking_timebase.py\` | \`0dc67ff28e40e1c8b1dba9b191ea5f61d3b15f8904167402c54e9e75c2e2300c\` |
| \`scripts/platformkit/tracking_harness.py\` | \`59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d\` |
| \`scripts/platformkit/tracking_schema.py\` | \`72d21ae1dddded5bc6903dcbbd442de3f47240d5491305c1b6bd933bd007197e\` |
| \`scripts/platformkit/tracking/run_environment.py\` | \`5129bb37e4e23aba93883239078825292136feb331c82ac85c56ee31298cb931\` |

## Cleanup

Temporary artifacts only were removed after their contents were captured:

| Path | Bytes freed |
|---|---:|
| \`/workspace/nba-ai-system/data/.g226c_dd_write_probe\` | 4,194,304 |
| \`/tmp/g226c_basketball_adapter_20260904T0558Z.log\` | 218 |
| \`/tmp/g226c_basketball_harness_20260904T0558Z.log\` | 1,490 |
| **Total** | **4,196,012** |

The new basketball CSV and report remain as the measurement result. The
adapter-runner backup remains, and \`adapter_run.py\` is intentionally left
deployed.

## Focused local checks

```text
python -m pytest domains/basketball/tracking/test_geometry.py -q
3 passed in 0.59s

python -m pytest domains/basketball/tracking/test_adapter.py -q
5 passed in 0.59s

python -m pytest scripts/platformkit/test_adapter_run.py -q
9 passed in 0.63s

python -m pytest scripts/platformkit/test_tracking_harness.py -q
24 passed in 0.80s

python -m pytest scripts/platformkit/test_coordinate_provenance.py -q
5 passed in 0.35s

python -m pytest scripts/platformkit/test_tracking_schema_coordinate_space.py -q
4 passed in 0.37s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
1 passed in 1.83s
```

No allowlisted production file grew in this evidence-only landing, so no LOC
allowlist change is required by A12.

## Verifier-contract self-check (section B)

- B1: The 6,000 adapter-evaluated-frame denominator is named independently of
  64,171 emitted rows and 5,972 emitted frames; the 28 zero-row evaluated
  frames are explicitly retained.
- B2: No schema was removed or renamed. The real-header comparison shows all
  shared adapter columns remain and the five basketball provenance columns are
  additive.
- B3 and B4: No gate, quarantine, claim, or re-claim flow changed.
- B5: This row is the expressly authorized, exactly-three-file deployment in
  its acceptance method; no bootstrap or additional file transfer occurred.
- B6: No module moved or retired.
- B7 and B8: No render sample or fitted residual is claimed.
- B9: The eligible denominator is actual adapter evaluations, not ids, rows,
  or a fixed recycled value.
- B10: The coordinate contract, harness, thresholds, and gates were not
  modified; both observed failures came from unchanged code.
- A7: This evidence path exists before commit.

## NOT VERIFIED

- A second run, repeatability, a corpus rate, or any property beyond this one
  bounded shared-pod draw.
- Basketball physical positions, player identities, ball tracking, court
  coordinates, calibration correctness, or detector accuracy.
- The cause of the 28 no-row adapter evaluations.
- Any claim about the pre-existing legacy basketball feature tables; they were
  not read, changed, migrated, or declared wrong.
