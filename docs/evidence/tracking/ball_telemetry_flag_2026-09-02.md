# G29 Ball Telemetry Capability Flag (2026-09-02)

## Decision and implementation

The harness thresholds are unchanged. A producer now writes a sibling
`tracking_capability.json` next to `tracking_data.csv`, declaring
`ball_telemetry_available`. The platformkit adapter producer declares `true`
only for tennis, where `TennisAdapter` runs `MotionDiffDetector`; its current
baseball, soccer, and football paths declare `false`. NBA production rows
remain unavailable by schema.

At normalized-table identification, the harness uses the producer declaration
when the sidecar is present. G29b supersedes the original row-presence fallback:
a table without a sidecar has unknown availability and retains the existing
ball-validity gate. The report records both `ball_telemetry_available` and
`ball_telemetry_rule` (`producer_declaration`, `unknown_no_sidecar`, or
`nba_production_schema`).

When availability is false, `ball_valid_pct` is `null`, `ball_valid` is
`"not_evaluated"`, and no `ball_valid` threshold failure is added. A table
whose remaining gates pass receives `verdict: "PASS_NO_BALL"`; it is never
reported as bare `PASS`. `PASS_NO_BALL` is a weaker rung: it does not establish
ball tracking quality and must not be read as a full tracking pass. A true
declaration with no ball rows still evaluates to zero and fails the existing
sport threshold.

## G29b correction: declarations and precedence

Row presence is evidence of detected rows, never evidence that the producer did
or did not run a ball detector. `BALL_TELEMETRY_AVAILABLE` is the authoritative
producer declaration and is emitted beside every adapter-run or footage-cycle
table. The track daemon directly invokes `run_clip.py` for its basketball
family, so its post-output writer emits the same false declaration there; it
does not write through `footage_cycle`.

| producer sport | declaration | evidence |
| --- | --- | --- |
| tennis | true | `TennisAdapter` instantiates `MotionDiffDetector` |
| soccer | false | person-class-only path; no validated ball detector |
| baseball | false | no validated fast-ball detector |
| football | false | no ball detector |
| basketball, wnba, ncaa_basketball, nba | false | `run_clip` production output has no validated ball telemetry |

Rule precedence is fixed:

1. A valid sibling `tracking_capability.json` is authoritative. `true` evaluates
   the unchanged ball-validity threshold; `false` marks the gate inapplicable
   and can yield only `PASS_NO_BALL`.
2. With no sidecar, availability is `unknown_no_sidecar`. The gate remains
   applicable and a zero-ball tennis table fails exactly as it did before G29:
   `ball_valid 0.00 < 0.20`.
3. NBA production schema rows remain unavailable by schema declaration.

`basketball_relabel_image_px.reemit_game` copies a source sidecar only when one
exists; it never fabricates a declaration for a legacy source.

## Focused verification

```
python -m pytest scripts/platformkit/test_tracking_harness.py -q
21 passed
python -m pytest scripts/platformkit/test_tracking_schema_coordinate_space.py -q
3 passed
```

The harness cases cover: a false declaration skips the gate and returns
`PASS_NO_BALL`; a true declaration without rows still fails `ball_valid`; and
a no-sidecar table remains unknown while the ball-validity gate stays active.

## Pod measurement

Changed platformkit modules were copied to `/workspace/nba-ai-system` and a
read-only job was launched with `nohup setsid nice -n 15`. No daemon, pid file,
pod Git state, registry, or feature flag was changed. The first job exited
because a `/tmp` script was outside Python's import path; the corrected job
used `PYTHONPATH=/workspace/nba-ai-system` and completed without terminating
any process.

The 2026-09-01 sweep memo is the required before reference. Its game-ID
manifest is not preserved. The current 2026-09-02 census provides 173
explicit IDs, but its sport composition differs from the memo, so this is not
a valid same-input delta. The initial broad current-pod glob found 182 CSVs
and was discarded.

| sport | memo before PASS / PASS_NO_BALL / FAIL | 2026-09-02 census after PASS / PASS_NO_BALL / FAIL | after top failure head |
|---|---:|---:|---|
| baseball | 0 / 0 / 86 | 0 / 0 / 90 | `coordinate_contract image_px` (66) |
| football | 0 / 0 / 41 | 0 / 0 / 38 | `coordinate_contract image_px` (30) |
| soccer | 0 / 0 / 24 | 0 / 0 / 24 | `coordinate_contract image_px` (15) |
| basketball | 0 / 0 / 11 | 0 / 0 / 11 | `coordinate_contract image_px` (11) |
| tennis | 0 / 0 / 11 | 0 / 0 / 10 | `coordinate_contract missing coordinate_space` (5) |
| **total** | **0 / 0 / 173** | **0 / 0 / 173** | |

The before report predates the `PASS_NO_BALL` label, so its middle zero means
no such label existed, not that a no-ball capability had been validated.
All after inputs were legacy CSVs without newly emitted sidecars; their rule
was row-presence fallback. Earlier coordinate-contract failures dominate, so
the pod sweep cannot show a corpus-wide `PASS_NO_BALL` uplift. The focused
tests prove the label and skipped-gate behavior; a future producer run is
needed to verify persisted producer declarations on the pod.
