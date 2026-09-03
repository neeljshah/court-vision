# G186: the daemon spent its life decoding files to count frames the container already stores

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md) A1, A2, A5, A7, B2, B3, B10, Q3, Q7.
**No bar, threshold, gate, coordinate contract or verdict changed. This changes HOW a
denominator is computed, and the equality table below is the evidence that its VALUE
does not move.**

## Provenance: the lane died and the orchestrator finished the row

The codex lane in worktree a3 wrote the code and its test, then **exited without
writing an EXIT line and without committing**. Its log froze at 14:52 with no
process alive. Its uncommitted work was recovered from the worktree before
anything was freed, committed as a WIP, and completed here. **The mandatory
equality evidence was never produced by the lane; the orchestrator produced it.**

This is recorded rather than presented as a clean lane result, because a reader
should know which parts had two sets of eyes on them and which had one.

## What was measured, before any change

On the live pod, read-only:

- The daemon (pid 33064, `--workers 10`) had **ZERO `adapter_run` processes** while
  load average sat at 40. No tracking was happening.
- It was blocked in `ffprobe -count_frames` on a 3.37 GB clip -- observed at
  **22:15 elapsed, 99.0 pct CPU**, and earlier on the same file at 6:52. That call
  fully decodes the file single-threaded to count frames.
- The **RTX 3090 measured 0 pct utilization and 1 MiB of 24,576 MiB**, sampled ten
  times over twenty seconds. Nothing reaches inference while the tick loop counts.
- Two `[python] <defunct>` children of the daemon (33:01 and 07:09 elapsed) were
  unreaped. **Diagnosed only, not changed** -- see NOT VERIFIED.

A metadata-only probe of the same file returned **in under a second**:
`nb_frames=250200`, `r_frame_rate=30/1`, `duration=8340.000000`, and
8340 * 30 = 250,200 exactly.

## The change

`decoded_frame_count` now reads `nb_frames`, `r_frame_rate` and `duration` in one
metadata probe and accepts the count **only** when it is a positive integer, is
unambiguous across streams, and agrees with `duration * frame_rate` to within
**1.0 frame** -- a tolerance justified in the code by finite-decimal duration
rounding at the stream endpoint. Every rejection path falls back to the original
`-count_frames` decode and logs its reason (`unreadable metadata`, `missing
stream metadata`, `missing positive metadata`, `metadata disagrees with duration
and frame rate`, `ambiguous metadata counts`). The path taken is logged either
way, so the choice is auditable per file.

**The fallback is the point.** VFR streams and some containers genuinely lack a
usable `nb_frames`; trusting bad metadata would corrupt a denominator, which is
far worse than being slow.

## Equality evidence: the value does not move

Rather than re-run `-count_frames` (which is the defect being fixed), this
compares metadata against the `decoded_frames` values **the daemon already
computed via `-count_frames`** and persisted in its ledger.

| game | count_frames (ledger) | metadata | within 1 frame | equal |
|---|---:|---:|---|---|
| `football_Z8Ezd95NnjM` | 288,230 | 288,230 | yes | **yes** |
| `kbo_06` | 53,196 | 53,196 | yes | **yes** |
| `kbo_07` | 54,180 | 54,180 | yes | **yes** |
| `mlb_nLoG6gvC-Nk` | 220,624 | 220,624 | yes | **yes** |
| `npb_02` | 411,191 | 411,191 | yes | **yes** |
| `soccer_dnR5C6WLJI4` | 250,200 | 250,200 | yes | **yes** |

**ELIGIBLE DENOMINATOR: 6** -- every game that has BOTH a ledger
`decoded_frames` and its video still present on the pod. **6 of 6 agree exactly.**
22 further ledger rows carry a `decoded_frames` but their file is no longer on the
pod, so they are not comparable and are excluded for that stated reason, not
because they disagreed.

**Six is a small denominator and all six are constant-frame-rate h264 broadcast
files.** They do not exercise the VFR or missing-`nb_frames` cases the fallback
exists for. This table supports "the fast path returns the identical value on the
footage we have", NOT "metadata is always safe".

## Tests

    scripts/platformkit/tracking/test_decode_manifest_g186.py   2 passed
    scripts/platformkit/tracking/test_decode_manifest.py        3 passed

The new test asserts the fallback fires and logs `path=decode_fallback` when
metadata is internally inconsistent (`nb_frames=99` against a duration*rate of 30),
returning the decoded value, and that `-count_frames` appears in the second call.

## NOT VERIFIED

- **Any throughput improvement.** None is measured here. The daemon holds its
  modules in memory from process start, so this is inert in the RUNNING daemon
  until it next cycles; the standing rule is never to kill anything on the pod, so
  no restart was taken and no before/after tracking rate is claimed.
- Behaviour on VFR or missing-`nb_frames` containers, which the eligible six do
  not include.
- The unreaped defunct children: observed, not diagnosed to a missing reap call,
  and not changed.
- Whether any consumer of `decoded_frame_count` is sensitive to the LOGGING added.
- Whether the 22 excluded ledger rows would have agreed; their files are gone.
