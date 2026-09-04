# G226b Basketball Adapter Pod Run - 2026-09-04

## Verdict

**NOT VALIDATED: no basketball adapter table was created on the pod, so no
tracking row reached EXCLUDED, UNSCORABLE, or SCORED.** The required source
presence check failed before the disk guard and bounded run: the pod lacks both
new basketball adapter modules. This is an honest failure to reach the G226b
bar, not a harness failure and not a coordinate result.

The stage reached is **no row / no stage**. The harness verdict and first
failure head are **not available** because there was no emitted CSV to score.
Verbatim precondition result from the read-only pod query:

```text
MISSING domains/basketball/tracking/adapter.py
MISSING domains/basketball/tracking/geometry.py
PRESENT 90172789dc13bf771a93c5dacbb9568eceb06783dc51e8b591fa2f380621f4e0  scripts/platformkit/adapter_run.py
POD_GIT_PRESENT=no
```

G226b's intended accepted outcome remains unchanged: a real canonical
basketball table reaching SCORED and then failing `coordinate_contract`. No
coordinate contract, harness, gate, threshold, legacy basketball table, other
sport adapter, registry entry, or `src/` file was changed.

## Scope, hold check, and pod route

This result executes `docs/evidence/tracking/specs/G226b_spec.md` and cites
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. Before the pod preflight began
at `2026-09-04T00:09:04-05:00`, this lane checked the reported G211 artifact:
`docs/evidence/tracking/g211_per_frame_cost_attribution_2026-09-03.md`.
It reports `NOT VALIDATED`; that report lifts G226b's hold but supplies no
result for this row.

The pod was `/workspace/nba-ai-system`. The repository's documented normal
code-transfer route is the `git archive HEAD ... | ssh ... tar -x` command in
`scripts/platformkit/ops/pod_bootstrap.sh`. This pod is not a git checkout and
does not contain the two G226 modules. G226b directs the lane to stop rather
than hand-copy absent files; additionally, copying them before this result
would violate verifier contract B5. No archive transfer, bootstrap command,
manual copy, daemon action, keeper action, process wait, kill, restart, or
deployment occurred.

## Input and source identity

The intended input was read only; it was not opened by the adapter:

| Full pod path | Bytes | Resolution | Frames | Use |
|---|---:|---|---:|---|
| `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080 | 174,430 | G226b's one bounded reference clip, verified by `stat` and `ffprobe`, not processed |

At the time of the read-only pod preflight, the exercised/required route-file
identity was:

| File | Pod SHA-256 | State |
|---|---|---|
| `domains/basketball/tracking/adapter.py` | Not available | Missing on pod |
| `domains/basketball/tracking/geometry.py` | Not available | Missing on pod |
| `scripts/platformkit/adapter_run.py` | `90172789dc13bf771a93c5dacbb9568eceb06783dc51e8b591fa2f380621f4e0` | Present on pod, but it is not the current checkout version |

For diagnosis only, the current `track-a6` checkout hashes are
`adapter.py` `1ecf483df26b19c44d1fa25297caed845e5952fbfdd9b704f95a6125f4366c15`,
`geometry.py` `3bb48c415131358b4512c795ffba30fa9d88a32c56aefd67ef6958c6a747ea5e`,
and `adapter_run.py` `e4abc2f5e4e4fb2a977ca6beb2fed854e33e829eb0a5d96cef8645680f6181c5`.
They are not presented as pod code identity.

## Disk guard and artifact preservation

The read-only pod disk census was:

```text
data_du_mb=31248 /workspace/nba-ai-system/data
```

The binding `dd ... conv=fsync` write probe was **not run**. The mandatory
adapter-source check had already failed, and G226b requires stopping rather
than writing or deploying code to make the run possible. Consequently, no new
`g226b_*` tracking directory, CSV, harness report, or temporary pod artifact
was created. Existing legacy basketball tables were not read, overwritten,
migrated, or deleted. Bytes freed: **0**.

## Emitted-schema comparison

No real adapter table exists on the pod for this run, so a header cannot be
read from one and no columns can honestly be labelled present, missing, or
extra. The table below is therefore an explicit non-observation, not a
transcription of the expected adapter schema.

| Canonical column | Emitted-table observation |
|---|---|
| `frame` | Not observed: no emitted table |
| `track_id` | Not observed: no emitted table |
| `cls` | Not observed: no emitted table |
| `x` | Not observed: no emitted table |
| `y` | Not observed: no emitted table |
| `calibration_provenance` | Not observed: no emitted table |
| `projection_status` | Not observed: no emitted table |
| `projection_rejection_reason` | Not observed: no emitted table |
| `raw_projected_x_ft` | Not observed: no emitted table |
| `raw_projected_y_ft` | Not observed: no emitted table |
| `coordinate_space` | Not observed: no emitted table |
| `observation` | Not observed: no emitted table |
| `calibration` | Not observed: no emitted table |
| `source_fps` | Not observed: no emitted table |
| `source_height` | Not observed: no emitted table |
| `source_duration` | Not observed: no emitted table |
| Extra columns | Not assessable: no emitted header |

Emitted row count: **not available**. Eligible denominator (attempted/evaluated
frames): **not available**. Neither is replaced with `--frames`, which was not
passed because the adapter job did not start.

## Focused local checks

No narrow-exception code change was made. The pre-existing local adapter and
harness contract checks passed:

```text
python -m pytest domains/basketball/tracking/test_geometry.py -q
3 passed in 0.56s

python -m pytest domains/basketball/tracking/test_adapter.py -q
5 passed in 0.58s

python -m pytest scripts/platformkit/test_adapter_run.py -q
9 passed in 0.41s

python -m pytest scripts/platformkit/test_tracking_harness.py -q
24 passed in 0.68s

python -m pytest scripts/platformkit/test_coordinate_provenance.py -q
5 passed in 0.43s

python -m pytest scripts/platformkit/test_tracking_schema_coordinate_space.py -q
4 passed in 0.42s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
1 passed in 0.77s
```

No allowlisted production file changed, so verifier contract A12 requires no
allowlist adjustment.

## Verifier-contract self-check (section B)

- B1: No metric was computed or filtered; the absent source files and absent
  table are named.
- B2: No schema, status, or reader changed; focused schema/provenance tests
  passed.
- B3 and B4: No gate or claim flow changed.
- B5: No pod code was copied, archived, deployed, or bootstrapped.
- B6: No module moved or retired.
- B7 and B8: No render sample or fitted residual is claimed.
- B9: No row-count or coverage metric is claimed; no denominator is invented.
- B10: No harness threshold, gate, or coordinate contract changed.
- A7: This required evidence path exists before commit.

## NOT VERIFIED

- A normal pod transfer that makes the G226 adapter files available without a
  pre-verification deployment violation.
- The mandatory `dd` write probe, a new tracking directory, the bounded run,
  emitted header, emitted rows, eligible denominator, harness verdict, and
  first harness failure head.
- Whether basketball reaches SCORED or then fails `coordinate_contract` on the
  pod.
- Physical tracking accuracy, player identities, court coordinates,
  calibration, repeatability, or any rate. A future one-clip run would be an
  existence draw only because the route is non-deterministic.
