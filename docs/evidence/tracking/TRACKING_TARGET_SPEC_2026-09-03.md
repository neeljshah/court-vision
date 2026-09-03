# What tracking has to build to, derived from what actually consumes it

**Method note.** This is derived by READING the real consumers, not invented. The
consumer of record is `src/features/feature_engineering.py`, which is human-gated
and was read only. Where a claim is inference rather than something measured, it
says so.

## 1. The contract the intelligence layer already imposes

`feature_engineering.py` consumes these columns from the tracking table. This is
the FLOOR, not the ambition -- it is what already exists downstream and is
already broken by the defects below.

| group | columns | consumer |
|---|---|---|
| geometry | `ft_x`, `ft_y` | `add_ft_coordinates:277` |
| spacing | `team_spacing` (hull area), `nearest_opponent`, `nearest_teammate` | `compute_spatial_features:92` |
| zone | `paint_count_own`, `paint_count_opp` | same |
| pressure | `defender_distance`, `handler_isolation` | same, with sentinel `200.0` scrubbed |
| pose | `contest_arm_angle`, `jump_detected` | `add_pose_features:1369` |
| event | `event`, `shot_quality_proxy` | `add_event_features:212`, `add_pose_features` |
| identity | `player_id`, `team` (incl. `referee`) | referee rows are NaN-ed out of every spatial column |

Two sentinels are already documented as failure signals rather than data:
`defender_distance == 200.0` and `handler_isolation == 200.0` are the isolation
default from `unified_pipeline`, and **`team_spacing == 0.0` is commented in the
consumer as "invalid hull area: no players detected this frame"**. The downstream
layer is already scrubbing tracking failures rather than being fed clean data.

## 2. Why none of these features is currently trustworthy

Every one of them depends on four properties, and all four are open:

1. **Correct court geometry.** `team_spacing`, `paint_count_*` and both
   `nearest_*` are only meaningful in court feet. G194 measured that basketball
   projects through a static `Rectify1.npy` whose result is **degenerate** -- the
   court model collapses to a line. So for basketball these columns are
   contaminated, not merely noisy.
2. **Enough simultaneous players.** A convex hull over a team needs five players.
   Route runs are surviving **2-3 players per frame** out of ten. **A hull over
   two points has zero area**, which is exactly the `team_spacing == 0.0` the
   consumer scrubs. So the primary spacing feature is undefined, not degraded,
   whenever coverage is thin. The harness's `min_players = 6` for basketball
   already encodes this requirement.
3. **Stable identity.** `nearest_teammate`, `contest_arm_mean_30` (a 30-frame
   rolling mean grouped by `player_id`) and every per-player rolling feature
   require `player_id` to mean the same person across frames. G166 measured
   **89.08 pct of tennis identity resets as FALSE** -- fired by an emission gap,
   not a real cut. G195 measured player ids differing across identical runs.
4. **Detections attached to the right frame.** Under investigation in G198.

**The dependency runs one way.** Fixing the detector cannot rescue a degenerate
homography, and fixing the homography cannot rescue an identity that resets every
few frames. That ordering is why method work is sequenced ahead of quality work.

## 3. The target, stated as testable properties

What "as accurate and in-depth as possible" has to mean concretely, so progress
is measurable rather than asserted:

| # | property | how it would be tested | status |
|---|---|---|---|
| T1 | The route returns the same output twice on the same input | 3 fresh runs byte-identical | OPEN (G198) |
| T2 | Coverage is scored against frames ATTEMPTED, not frames emitted | corrected gate is non-`None` on a real table | OPEN (G199) |
| T3 | Court geometry is per-clip and lands on the painted court | render eye check, plus out-of-sample arc | **geometry proven recoverable from hand labels (G196)**; automatic detection OPEN |
| T4 | At least `min_players` players survive per frame | coverage gate on the T2 denominator | OPEN |
| T5 | `player_id` survives an occlusion or a shot cut | false-reset rate, as G166 measured for tennis | OPEN, measured only for tennis |
| T6 | Pose columns exist and are attributable | `contest_arm_angle` non-null rate on shot frames | NOT MEASURED |
| T7 | Events align to the frame they happened on | offset distribution against labelled events | NOT MEASURED, and G198 may make it urgent |

**T1 and T2 are prerequisites for measuring T3-T7 honestly**, because a
non-reproducible route makes any single-run quality number unrepeatable, and a
circular denominator makes any coverage number unfalsifiable.

## 4. What "understanding the sport" adds, and where it belongs

The ambition is richer than boxes: knowing HOW a player plays. That is a layer
ABOVE the table -- it consumes `ft_x/ft_y`, identity and pose over time. Two
honest observations:

- **It cannot be built first.** Every play-style feature is a function over a
  player's trajectory, so it inherits T1, T3, T4 and T5 exactly. Building it on
  the current substrate would produce confident numbers with no support, which is
  the retraction pattern this programme has already been caught by three times.
- **It does change what tracking must emit.** Play style needs continuous
  trajectories, not per-frame detections: possession-level tracks, ball-carrier
  attribution, and off-ball movement. **`median_track_len` is the existing metric
  closest to this**, and G166 showed it fails for a reason we now understand.

**Sport-specific dimensions are NOT interchangeable** and a single model silently
corrupts one league: NCAA uses a **12-ft** lane and WNBA a **16-ft** lane
(rule-book cited in G196). Any court model must be per-league.

## 5. What this means for sequencing

1. Finish T1 and T2. In flight.
2. Then T4, coverage on a fixed denominator -- this is the first row that could
   legitimately PASS anything.
3. Then T3 automatic court detection. G196 established the ceiling is detection.
   Any learned-calibration proposal must cite **G31**, which closed that path at
   limit for tennis, and say what is different.
4. T5, T6, T7 after that, because each is measured per-player over time and needs
   T1 and T5's own prerequisites.

**NOT VERIFIED in this document:** the 2-3 survivor figure is from route runs
recorded in G189/G193/G195 survivor tuples and is a route-run observation, not a
dedicated census. T6 and T7 have no measurement at all yet. Nothing here claims
any feature is currently correct.


## 6. Status update, same day, after G195-G206

| # | property | status now |
|---|---|---|
| T1 | route reproducible | **OPEN.** Five candidates eliminated: cuDNN tuner/FP16 (G190), torch seeds and FP32 (G190), OpenCV's six RNG sites (G195), the YOLO prefetch cache (G198), and wall-clock branching (no branch reads a clock). Decode byte-identity (G203) is the last enumerated candidate. |
| T2 | coverage on an honest denominator | **HALF DONE.** The harness gate is corrected (G197) and the route now emits a validated pre-tracking evaluated-frame count (G206). **But a `--frames N` run writes `null`**, because the cap is detector-dependent via `_is_gameplay`. So T2 holds for FULL-LENGTH runs only. |
| T3 | per-clip court geometry | **OPEN, and better characterised.** G196: recoverable from hand labels. G205: classical line intersections give 0/17 all-four but **22/68 corner recall** against G141's 0/68 -- real signal -- at ~1,928 proposals per frame, which is the actual blocker. G208 is running the learned zero-shot candidates. |
| T4 | enough players per frame | **OPEN**, and now known to be measurable only on full-length runs (see T2). |
| T5 | identity survives occlusion | OPEN, measured only for tennis (G166: 89.08 pct of resets are FALSE). |
| T6 | pose columns attributable | NOT MEASURED. |
| T7 | events aligned to their frame | **WORSE THAN ASSUMED.** G198 measured **100 pct of detections attributed to the next processed frame** (offset +3 source frames at stride 3). A fix is proposed and human-gated, not applied. |

### The new constraint that reorders the plan

T2's `--frames` limitation means **every coverage and quality number requires a
full-length run** -- 174,430 frames against the 1,200 the measurement rows use.
The pod is a 256-core machine running one job at ~13 cores, so the throughput to
do that exists but has never been used. **Pod concurrency (G200) moved from an
efficiency nicety to a prerequisite for T2 and T4.**

### A second circularity, upstream of the one we fixed

`unified_pipeline.py:992` `_is_gameplay` selects frames by whether YOLO found
enough players, and is sticky for ~3 seconds either way. **The producer's own
notion of an attempted frame is detector-selected.** No gameplay-derived quantity
can ever be a denominator, which is why G199's candidate failed and why G204 had
to exclude it by construction rather than by care.
