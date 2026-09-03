# G177: coverage has a strided numerator over an unstrided denominator, so it is capped at 1/stride

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), sections A (A2, A7) and
B. Measured by the orchestrator on 2026-09-03 from live pod ledger rows and from
quoted code. **No threshold, bar, gate value, denominator or verdict was
changed.** Every number is recomputed here from artefacts.

## What was found

The daemon path samples frames on a WALL-CLOCK interval and then divides by ALL
decoded frames.

- `scripts/platformkit/tracking_timebase.py:13` -- `TARGET_SAMPLE_SECONDS = 0.1`
- `tracking_timebase.py:30-37` -- `sampling_plan` returns
  `stride = max(1, int(round(frame_rate * target_seconds)))`
- `scripts/platformkit/adapter_run.py:100-101` -- the daemon path builds that plan
  and passes `{"max_frames": ..., "stride": plan.stride}` into the adapter
- `domains/tennis/tracking/adapter.py:223` -- `evaluated = source_frame % stride == 0`,
  and `:242` marks every other frame `skipped_stride`
- `scripts/platformkit/tracking/decode_manifest.py` -- `decoded_frame_count` counts
  EVERY decoded frame, with no knowledge of the stride

So a frame the pipeline **never evaluated by design** still sits in the
denominator. Coverage is therefore capped at `1/stride` no matter how good the
tracker is.

| fps | stride | structural max coverage |
|---:|---:|---:|
| 23.976 / 25.0 | 2 | 0.5000 |
| 29.97 / 30.0 | 3 | 0.3333 |
| 50.0 | 5 | 0.2000 |
| 59.94 / 60.0 | 6 | 0.1667 |

## The live rows, and why baseball settles it

Every ledger row on the pod, recomputed against its own cap:

| sport | fps | stride | cap | observed `coverage_pct` | share of cap |
|---|---:|---:|---:|---:|---:|
| baseball x12 | 59.94 | 6 | 0.1667 | 0.1499 - 0.1607 | **89.9 - 96.4 pct** |
| soccer | 30.00 | 3 | 0.3333 | 0.0806 | 24.2 pct |
| tennis (`tennis_ref01`) | 29.97 | 3 | 0.3333 | 0.0252 | 7.6 pct |

**Baseball is the proof.** Twelve independent games all land between 89.9 and
96.4 pct of the maximum value the metric can take. The baseball tracker is
solving very nearly every frame it is given, and the metric still reports ~0.157
because five of every six frames were never looked at. Against a baseball
`coverage_min` of 0.70 that is **unreachable by construction**: the ceiling is
0.1667.

The same holds for tennis at a 0.90 bar against a 0.3333 ceiling.

## What this does and does not say

**Does say:** for these sports and frame rates, the coverage gate cannot be
passed by any tracker at any quality. A gate whose ceiling is below its bar is
not measuring the tracker; over baseball's twelve rows it is measuring `1/stride`
to within about 6 pct.

**Does NOT say tennis is fine.** Tennis sits at **7.6 pct of its cap** while
baseball sits at ~94 pct. Tennis is genuinely weak on the frames it does
evaluate, and today's separate finding stands: the court solver produces no
usable output on about three of four rally-view frames. The stride mismatch
means the metric **overstates** how bad tennis is by roughly 3x -- 0.0252
reported against 0.0756 of evaluable frames -- but it does not make tennis good.

**Does NOT retract the adjudication.** Today's ruling kept the 0.90 bar on the
decoded denominator and recorded tennis CLOSED AT LIMIT. That still holds:
tennis fails on evaluable frames too. What changes is the REASON baseball fails,
and whether the gate discriminates at all.


## CORRECTION, added by the orchestrator within the hour (G176)

**Baseball is not actually being failed by coverage, and the framing above overstates
what fixing the denominator would achieve.** Measured across all 18 ledger rows on the
pod: **only 1 row has a coverage failure head** (the tennis row). **14 fail at
`coordinate_contract`** -- baseball rows declare `image_px`, which is not accepted for
baseball, so they are rejected BEFORE the coverage gate is ever evaluated. 3 rows carry
no failure head at all.

So the cap arithmetic above stands exactly as measured -- coverage IS capped at 1/stride,
and baseball's observed values ARE 89.9-96.4 pct of that ceiling -- but the sentence
"against a baseball `coverage_min` of 0.70 that is unreachable by construction" describes
a gate baseball never reaches. Correcting the denominator would move baseball's coverage
NUMBER from ~0.157 to ~0.94; it would NOT flip baseball from FAIL to PASS, because the
coordinate contract fails it first and independently.

The metric-correctness argument is unaffected: a strided numerator over an unstrided
denominator is wrong regardless of which gate fires first. But "this rescues baseball" was
an over-read and is withdrawn.

## NOT VERIFIED

- The gating quantity itself. These `coverage_pct` values are the LEDGER figure
  (G164's quantity 1: frames emitting any row over decoded frames). The quantity
  that decides `passed` is `(per_frame >= min_players)` over the same
  decoded-padded denominator, and `adjudicate` discards it. The cap argument
  applies to both because both divide by decoded frames, but the per-row gating
  values were NOT read and are not quoted here.
- Whether any sport's frame rate yields a stride of 1, where no cap would apply.
- The wnba and ncaa_basketball rows carry `coverage_pct = None` and were excluded;
  why they are null is unexamined.
- Whether `max_frames` interacts with the stride to change the denominator.
- What the correct remedy is. Counting only evaluated frames in the denominator
  is the obvious candidate and is NOT proposed here as a change -- it alters what
  the metric means and is an orchestrator decision under B10/Q3, not a lane fix.
