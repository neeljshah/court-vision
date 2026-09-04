# G221 runtime denominator-defect evidence

**Verdict: ACCEPT WITH CORRECTIONS.** The local section test refutes runtime
reachability of the frame-size fallback on the files measured: CV2 supplies a
nonzero count first. Its counterfactual is material, however: the section's
file-size estimate is below 3,000 and would select stride 1 rather than the
CV2-selected stride 3. The hand-truncation run shows that the production
prefetcher consumer receives the normal EOF sentinel after only 322 frames.
At the consumer API the matched clean control is indistinguishable; outer
process stderr does contain decoder diagnostics on the truncated run.

This is a local-only measurement on `C:\Users\neelj\nba-track-a7`, not the
pod (which was not contacted because G216 owns its throughput measurement).
`src/` was imported and called but not edited. The measurement harness is
`scripts/platformkit/tracking/g221_runtime_denominator.py` and the focused
test is `scripts/platformkit/tracking/test_g221_runtime_denominator.py`.

## Inputs and eligible denominator

The eligible denominator is exactly the three local MP4 files used below.
There were no MP4 files under the spec-named `data/videos/` directory in this
worktree. The unsliced local basketball source is therefore an NCAA-labelled
candidate under `tmp/`, not the requested local NBA corpus; it is reported
accurately rather than relabelled. No other MP4 was used.

| Input | Exact path | Bytes | Resolution | Role |
|---|---|---:|---|---|
| Unsliced source | `C:\Users\neelj\nba-track-a7\tmp\g136_source_clips\ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4` | 487,249,282 | 1920x1080 | Whole-file census source |
| Section | `C:\Users\neelj\nba-track-a7\data\videos\tmp\g221\g221_section_900s.mp4` | 444,960,015 | 1920x1080 | `ffmpeg -ss 00:00:15 -t 900 -map 0:v:0 -c copy -movflags +faststart`; 900.042 s |
| Hand truncation | `C:\Users\neelj\nba-track-a7\data\videos\tmp\g221\g221_section_first_8MiB_truncated.mp4` | 8,388,608 | 1920x1080 declared header | First 8 MiB copied from the section, cut mid-stream |

The section is a bounded 15-minute, 444.96 MB local stream copy. No download
occurred. It is the required 10-20 minute configuration.

## Defect B: count-source branch census

For every input, sources were queried in production order: CV2 first, then
PyAV metadata, then the unchanged `int(getsize / 250_000)` estimate. PyAV is
unavailable in both the base Python and `basketball_ai` environments
(`ModuleNotFoundError: No module named 'av'`), so it has no count or implied
stride. Production's actual short-circuit selection is shown separately.

Ground truth for the unsliced and section inputs is the inexpensive,
non-decoding `ffprobe` stream-duration times average-FPS product. It is
explicitly approximate. This avoids a whole-file frame scan, consistent with
the binding bounded-decode guard. The truncation's copied container header
still declares the original duration, so that proxy is invalid there; the
exact terminal result from its bounded production decode is 322 frames.

| Input | CV2 count / stride | PyAV frames / stride | File-size estimate / stride | Ground truth | Production branch / stride |
|---|---|---|---|---|---|
| Unsliced source | 28,905 / 3 | unavailable / n.a. | 1,948 / 1 | approx. 28,905 = 964.4635 s x 29.97002997 FPS | CV2 / 3 |
| **15-minute section** | **27,122 / 3** | unavailable / n.a. | **1,779 / 1** | approx. 26,974 = 900.042 s x 29.97002997 FPS | **CV2 / 3** |
| 8 MiB truncation | 27,122 / 3 (copied header) | unavailable / n.a. | 33 / 1 | 322 exact decodable frames to terminal sentinel; duration x FPS metadata proxy is invalid | CV2 / 3 (copied header) |

The section result is the key configuration: if the fallback had been reached,
1,779 is below 3,000 and would select stride 1; the real CV2-selected count,
27,122, is above 3,000 and selects the unchanged base stride 3. It did **not**
reach the fallback locally, because CV2 supplied a count. Thus Defect B is
live code but locally unexercised on these inputs, including the section case.
PyAV availability and fallback reachability are not generalized to the pod.

## Defect A: bounded truncated-versus-clean production prefetcher comparison

Each decode was sequential, one process at a time, through the imported
production `_FramePrefetcher` with `queue_size=4`; no decode requested more
than 1,200 source frames. The successful production runs used
`conda run -n basketball_ai` (NumPy 1.26.4). The base Python could not import
the pipeline because of its incompatible NumPy 2 / TensorFlow binary stack;
this environment limitation was not fixed or written to production code.

| Run | Input / bound | Frames emitted and indices | Consumer exception | Sentinel | Captured Python stdout, stderr, warnings | Outer process stderr |
|---|---|---|---|---|---|---|
| Clean health control | Section / 1,200 | 1,200, 0-1199 | None | `(False, None, -1)` | all empty | 1,170 bytes: environment `RequestsDependencyWarning` only |
| Hand truncation | First 8 MiB / 1,200 | 322, 0-321 | None | `(False, None, -1)` | all empty | 2,064 bytes: same environment warning plus invalid H.264 NAL, missing picture, access-unit, and MP4 `partial file` diagnostics |
| Matched clean control | Section / 322 | 322, 0-321 | None | `(False, None, -1)` | all empty | 1,170 bytes: environment `RequestsDependencyWarning` only |

The decisive comparison is the truncated run and the matched 322-frame clean
control. A consumer of `_FramePrefetcher.read()` sees the same frame range,
no surfaced exception, empty captured Python signals, and the same sentinel
tuple. Therefore that API has no completion-versus-truncation signal. The
outer process stderr is distinguishable: the truncated run adds decoder
diagnostics. This run does not establish that the Python `except Exception:
pass` clause itself fired; CV2 may instead have ended its iterator normally
after emitting C-level diagnostics. It does establish the consumer-boundary
behavior that makes a truncated decode look like clean EOF.

## Ledger consequence

The demonstrated risk is to `decoded`, `evaluated`, and every coverage figure
computed using either quantity as its denominator: a truncated decode can
terminate with the production EOF sentinel after fewer frames while the direct
prefetcher consumer receives no completion-failure distinction. This names a
real denominator exposure, not an assertion that any specific landed number
is wrong. No landed row is retracted, reopened, or otherwise changed by G221.

## Cleanup

All temporary artifacts created under
`C:\Users\neelj\nba-track-a7\data\videos\tmp\g221` were deleted after the
measurements: the 444,960,015-byte section, 8,388,608-byte truncation, six
nonzero JSON/stderr captures totaling 6,418 bytes, and four zero-byte failed
capture files. **Bytes freed: 453,355,041.** The pre-existing unsliced source
under `tmp/g136_source_clips/` was not deleted.

## Limitations and NOT VERIFIED

- The local source is not the pod corpus and is not the requested local NBA
  file set; its no-fallback result does not generalize to the pod or another
  acquisition path.
- PyAV is unavailable locally, so its real stream-frame metadata branch was
  not measured on any file.
- Duration times average FPS is approximate and cannot resolve the 148-frame
  difference between the section's CV2 metadata and its proxy. It is invalid
  for the hand-truncated container because the copied header retains the full
  duration.
- The hand truncation is one realization, not a driver fault, corrupt live
  stream, or OOM. It is a single controlled pair, not a repeatability claim
  for every decoder failure.
- No trace was installed to prove that the Python broad-exception clause fired;
  the reported evidence is the actual production prefetcher consumer behavior.
- No production threshold, frame stride, coordinate contract, gate, corpus,
  or pod state changed.

## Verifier-contract self-check

This memo cites and self-checks
`docs/evidence/tracking/VERIFIER_CONTRACT.md` section B. B1: the input
denominator names all three files and none is silently excluded. B2-B4: this
measurement adds no schema, gate, claim, or retry path. B5: no pod deployment
or pod access occurred. B6: the added test imports the harness by full package
path. B7-B9: there are no renders, fitted metrics, or recycled denominators;
the units are named physical files and emitted frames. B10: the unchanged
3,000 threshold and base stride 3 are reported, not modified. Section Q is
not applicable because G221 is a tracking G-row, not an S-row. A9 input paths,
bytes, and resolutions appear above; B11 is addressed by labelling the single
pair as one controlled realization rather than a system-wide repeatability
claim.

## Focused verification

```text
python -m pytest scripts/platformkit/tracking/test_g221_runtime_denominator.py -q
1 passed in 4.33s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
1 passed in 1.76s
```
