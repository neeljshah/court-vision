# G222: Direct-to-Seed Homography Propagation

## Result

**The chained G215 control reproduced, while a direct seed-to-frame map stayed
visually plausible through the final 1,200-frame check.** The direct arm did
not fail within the 1,200 frames tested. This is a horizon observation on one
continuous WNBA camera run, not a claim that it will hold longer or across
shots. Its match counts stayed between 509 and 1,809 (436-1,748 RANSAC
inliers), so the tested interval contains no overlap-loss count cliff.

The chained arm again came visibly off the painted court by 100 frames in the
separate unmodified G215 control, and its paired trace remained far from the
direct reference after 300. Its long-run numeric trace is not monotonic, so
the observed shape is an accumulated-drift pattern with fluctuations rather
than a clean smooth curve. The direct arm gives no observed failure shape yet:
there was neither a render failure nor a match-count cliff through 1,200.

## Scope, machine, source, and code identity

This ran **on the pod**, because consecutive native broadcast frames are
required. The source opened was exactly
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes, 1920x1080, 30 fps, and 174,430 frames. The input was
read only. The run starts at seed source frame 1600, uses stride 1, and tests
the next 1,200 frames (through source frame 2800, 40 seconds after the seed).

At 2026-09-04T05:08:31Z, before the run, an exact Python-executable process
inspection found the permanent `track_daemon`, other resident services,
`foundry_runner`, and a tennis `adapter_run`. None was stopped, restarted,
waited on, overwritten, or deployed over. G216 had reported, so its hold was
lifted. The pod did not have the G215 harness path, so the exact local G196,
G215, and G222 sources were assembled only in a standard-input stream to the
pod Python process; no source file was copied into the pod checkout.

The exercised source SHA-256 values were:

| Source | SHA-256 |
|---|---|
| `scripts/platformkit/tracking/g196_homography_from_labelled_corners.py` | `F9655C338C92BE6BCF90BE998EAC8B2904AAEE52346B2F1593A2814458C737A3` |
| `scripts/platformkit/tracking/g215_temporal_homography_propagation.py` | `B3EB085FA0B57AF006AF19FF29F1E5D2F2BF5B61ADDC649940B998CC52B6442A` |
| `scripts/platformkit/tracking/g222_direct_to_seed_propagation.py` | `2B99A30F3FF6DD1D633E0D088DEE150C379F655E2FB78556589B5A948743D8C4` |

## Fixed method

Nothing changed from G215 except how frame k's image-to-court homography is
selected for the direct arm. Both arms use the same decoded frames, G196 WNBA
court model, frame-1600 four hand-labelled image points, ORB with 2,000
features and `fastThreshold=12`, BF/Hamming matching, 0.75 ratio test, and
OpenCV RANSAC at 3 px. No labels after the seed were read.

Arm A composes each previous-image-to-current-image map onto the seed map,
unchanged from G215. Arm B estimates the seed-image-to-current-image map once
for each current frame and composes it directly with the fixed seed
image-to-court map. The G215 paint-corner drift compares the inverse-projected
four paint corners of an arm to the direct seed-to-current reference. Therefore
the direct arm's drift against that same direct reference is exactly zero by
construction; it is retained in the artifact to make the unchanged metric
explicit, but is not independent accuracy evidence. Renders are the
accuracy-bearing evidence.

The eligible denominators are named separately: chained propagation produced a
finite map for **1,200 of 1,200** decoded post-seed frames, and direct-to-seed
matching produced a finite map for **1,200 of 1,200**. These are processing
denominators, not accuracy-success denominators. The complete per-frame trace
is [paired CSV](g222_direct_to_seed_propagation_artifact/paired/drift_records.csv)
and [paired JSON](g222_direct_to_seed_propagation_artifact/paired/run_summary.json).

## Arm-A stop gate: G215 reproduction

Before extending the paired run, the unmodified G215 source was run for the
same 300-frame control and its artifact was retained at
[control records](g222_direct_to_seed_propagation_artifact/control/drift_records.csv).
It reproduced all required G215 values to the stated two-decimal precision:

| Distance frames | G215 required median px | Reproduced median px | Reproduced max px |
|---:|---:|---:|---:|
| 50 | 10.88 | 10.876 | 18.531 |
| 100 | 38.47 | 38.472 | 65.469 |
| 300 | 187.77 | 187.772 | 255.077 |

All 300 control frames had finite chained and direct reference maps. The stop
condition therefore did not trigger.

## Paired drift and matched-feature trace

`Chained drift` is the unchanged G215 median paint-corner displacement from
the direct seed reference. `Direct drift` is zero against that same reference
by definition, not a claim of ground-truth accuracy. The two arms are recorded
on the identical source frames. Match counts are accepted ratio-test matches;
inliers are RANSAC-retained matches.

| Distance | Chained drift median / max px | Direct drift median / max px | Chained inliers / matches | Direct inliers / matches |
|---:|---:|---:|---:|---:|
| 1 | 0.000 / 0.000 | 0.000 / 0.000 | 1748 / 1809 | 1748 / 1809 |
| 50 | 10.876 / 18.531 | 0.000 / 0.000 | 1825 / 1856 | 1166 / 1279 |
| 100 | 38.472 / 65.469 | 0.000 / 0.000 | 1451 / 1581 | 910 / 948 |
| 200 | 42.935 / 74.349 | 0.000 / 0.000 | 1469 / 1616 | 642 / 673 |
| 300 | 187.772 / 255.077 | 0.000 / 0.000 | 1812 / 1834 | 607 / 634 |
| 400 | 202.857 / 276.367 | 0.000 / 0.000 | 1830 / 1849 | 610 / 643 |
| 600 | 216.901 / 329.538 | 0.000 / 0.000 | 1754 / 1784 | 546 / 590 |
| 800 | 56.890 / 146.568 | 0.000 / 0.000 | 1695 / 1747 | 579 / 705 |
| 1000 | 247.765 / 536.865 | 0.000 / 0.000 | 1819 / 1838 | 495 / 606 |
| 1200 | 123.499 / 331.651 | 0.000 / 0.000 | 1828 / 1852 | 537 / 646 |

The direct match count never approaches zero: its full-range minimum is 509
matches and 436 inliers. Thus this run did not show the predicted appearance-
overlap failure cliff. The chained/direct displacement is large after 300 but
fluctuates (for example, 56.890 px at 800), so it must not be presented as a
monotone accuracy curve.

## Evenly spaced paired eye check

Yellow is the inverse-projected court model and red marks are inverse-projected
near-paint corners. The seven distances 0, 200, 400, 600, 800, 1000, and 1200
are evenly spaced over the 1,200-frame decision interval. This is a
single-labeller visual judgement. The separately retained G215 control gives
the 100-frame chained failure check required for reproduction.

| Distance | Chained render and judgement | Direct-to-seed render and judgement |
|---:|---|---|
| 0 | [render](g222_direct_to_seed_propagation_artifact/paired/chained_renders/render_distance_0000.jpg): fitted seed broadly follows the painted key. | [render](g222_direct_to_seed_propagation_artifact/paired/direct_seed_renders/render_distance_0000.jpg): same seed fit. |
| 200 | [render](g222_direct_to_seed_propagation_artifact/paired/chained_renders/render_distance_0200.jpg): visible departure from the painted key. | [render](g222_direct_to_seed_propagation_artifact/paired/direct_seed_renders/render_distance_0200.jpg): still follows the visible key. |
| 400 | [render](g222_direct_to_seed_propagation_artifact/paired/chained_renders/render_distance_0400.jpg): plainly off the painted court. | [render](g222_direct_to_seed_propagation_artifact/paired/direct_seed_renders/render_distance_0400.jpg): still plausible on the visible key. |
| 600 | [render](g222_direct_to_seed_propagation_artifact/paired/chained_renders/render_distance_0600.jpg): plainly off the painted court. | [render](g222_direct_to_seed_propagation_artifact/paired/direct_seed_renders/render_distance_0600.jpg): still plausible on the visible key. |
| 800 | [render](g222_direct_to_seed_propagation_artifact/paired/chained_renders/render_distance_0800.jpg): plainly off the painted court. | [render](g222_direct_to_seed_propagation_artifact/paired/direct_seed_renders/render_distance_0800.jpg): still plausible where the key is visible. |
| 1000 | [render](g222_direct_to_seed_propagation_artifact/paired/chained_renders/render_distance_1000.jpg): plainly off the painted court. | [render](g222_direct_to_seed_propagation_artifact/paired/direct_seed_renders/render_distance_1000.jpg): still plausible where the key is visible. |
| 1200 | [render](g222_direct_to_seed_propagation_artifact/paired/chained_renders/render_distance_1200.jpg): plainly off the painted court. | [render](g222_direct_to_seed_propagation_artifact/paired/direct_seed_renders/render_distance_1200.jpg): still plausibly follows the visible key; no failure within frames tested. |

The chained eye check first fails between the G215 control's 50- and 100-frame
checks, and is visibly failed at every paired check from 200 onward. The direct
eye check does not fail within the tested 1,200 frames. There is no shot cut,
replay, crowd-only frame, or abrupt heavy zoom in this interval; it is a smooth
pan. Therefore cut handling and direct matching after an appearance break were
not measured.

## Labels-per-hour consequence

At 30 fps, one hour contains `30 * 60 * 60 = 108,000` frames. A chained horizon
of 50 frames implies `ceil(108,000 / 50) = 2,160` hand-labelled seeds per hour,
under the conservative assumption that every 50-frame span needs an independent
seed. The direct arm survived the observed 1,200-frame (40-second) horizon, so
the analogous conservative arithmetic is `ceil(108,000 / 1,200) = 90` seeds
per hour, assuming the observed horizon repeated without a camera shot break.

That 90 is not a measured corpus-wide label rate and is not an extrapolation
beyond 1,200 frames: it is the requested arithmetic using the longest tested
non-failing horizon. Actual shot boundaries, tighter zooms, faster pans, or
smaller feature overlap can require more seeds. The result nonetheless changes
the viability question on this one mechanism from thousands per hour under
naive chaining to at most 90 per hour under the stated repeated-horizon
assumption.

## Disk guard and cleanup

Before any pod output was written, `du -sm /workspace/nba-ai-system/data` was
**31,245 MiB**. The binding 4 MiB `dd` probe with `conv=fsync` passed and was
removed; `df` was not used. All measurement code was transmitted over stdin.
No corpus source was created, changed, or deleted.

Temporary artifacts removed were the 4,194,304-byte probe, the 4,000,997-byte
control directory, the 10,163,478-byte paired pod directory after copy-back,
and a 5,068,526-byte incomplete local copy removed after detecting that the
run was still active. Total temporary bytes freed: **23,427,305**. The complete
committed evidence artifact remains locally at
`docs/evidence/tracking/g222_direct_to_seed_propagation_artifact/` (14,164,475
bytes); it is not temporary. Final pod checks confirmed both G222 temporary
paths were absent.

## Verifier self-check and NOT VERIFIED

This memo cites `docs/evidence/tracking/VERIFIER_CONTRACT.md`. B1 does not
exclude any propagated frame: both denominators name all 1,200 decoded frames.
B2-B6 do not apply because this is an additive measurement harness with no
schema, gate, deployment, or retired-module change. B7 is avoided by the seven
evenly spaced paired renders. B8 is named rather than hidden: direct-reference
zero drift is self-reference, not independent accuracy. B9 does not apply: the
denominator is unique source frames. B10 does not apply: no threshold, bar,
court model, seed, coordinate contract, or production route changed. This is a
tracking measurement row, not an S-row, so Q requirements do not apply.

- No ground truth exists after the seed. Drift versus the direct composition is
  self-consistency, and render assessment is a single-labeller judgement.
- Direct-to-seed zero drift is tautological against its own reference; it must
  not be treated as an accuracy metric.
- One clip, one seed, and one continuous camera run measure a mechanism and
  decay shape, not a corpus rate or a guarantee over any other shot.
- Automatic anchors remain 0/17. This measures propagation from a hand label,
  not automatic seed acquisition.
- The non-deterministic tracking route was not run. No claim about that route's
  determinism is made.
- No cut, replay, crowd-only view, abrupt zoom, future frame beyond 1200, or
  learned/model-based re-anchoring policy was tested.

## Verification

`python -m pytest tests/platformkit/test_g222_direct_to_seed_propagation.py -q`
completed with `1 passed`. The added harness is 170 LOC, below the 300-LOC
rail, so it does not require a LOC-allowlist update.
