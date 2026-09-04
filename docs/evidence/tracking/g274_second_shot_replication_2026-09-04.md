# G274: Second-camera-shot replication stop -- no valid map

## Verdict

**CLOSED AT LIMIT (measurement only): the G267/G270/G271 defect profile was not replicated because no valid second-shot map exists from the published 19599 seed without a second hand label.** The selected different shot is source frames **23476--24127 inclusive (652 frames)**. Its direct-to-seed records are finite, but that is not a usable court map: at the independent mid-shot render (source frame 23599, distance 4000) the broadcast is a tight player close-up with no painted court supporting the overlay, and the yellow projected court is visibly off the court. No second label was made and no map was forced.

Accordingly, no detector was run on the second shot. There are **0 newly measured detector boxes, 0 newly measured emitted association IDs, and 0 newly measured same-ID steps** in this row. The answer is **NOT EVALUATED, not "replicates" and not "differs"**: the one-shot tracking-defect chain cannot presently be tested across this cut without another hand label. The G267 first-shot figures therefore remain figures for one framing/play context, not system-wide figures.

Denominator and scope: one WNBA clip in one arena, two camera-shot intervals; the first has 3,801 frames and G267's retained non-deterministic detector-box draw, while the second has 652 frames but no detector-box measurement because its geometry prerequisite failed. These are detector boxes and associated observations, never authenticated players. Identity remains unvalidated.

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changes no production code, map, label, threshold, coordinate contract, `src/`, `domains/`, daemon, keeper, corpus source, or bridge partial.

## Second-shot selection and no-cut verification

G241b's retained 10,000-frame direct series starts at source frame 19599. I re-ran its scene inventory on the named source with this streamed, no-output-decode command:

```text
ffmpeg -hide_banner -nostdin -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -vf 'trim=start_frame=19599:end_frame=29599,select=gt(scene\,0.40),showinfo' -an -f null -
```

At the two bracketing candidates, `showinfo` gave PTS 12,019,200 and 12,353,536. With its 1/15360 timebase and 30 fps, those are source frames 23,475 and 24,128 (`PTS / 512`). The selected interior interval is therefore 23,476--24,127. The same complete 10,000-frame scene scan returned no `scene > 0.40` candidate inside that interval. It is clearly after G267's pre-cut span (19599--23399) and is shorter than 3,801 frames because the next cut arrives after 652 interior frames.

## Geometry decision

The direct-to-19599-seed records were read from G241b's committed extended artifact, not recomputed. All 652 selected records are numerically finite and eligible, but their numerical finiteness does not validate a court image after the cut.

| Direct-to-seed quantity, source 23476--24127 | Result |
|---|---:|
| Finite / eligible records | 652 / 652 |
| Matches, minimum--maximum | 81--395 |
| Inliers, minimum--maximum | 44--350 |
| Inlier ratio, minimum--maximum | 0.381--0.905 |
| RMS reprojection residual, minimum--maximum px | 0.285--1.434 |
| First selected record, source 23476 | 360 matches; 312 inliers; 0.867 ratio; 0.440 px RMS |
| Independent mid-shot render, source 23599 (distance 4000) | 116 matches; 60 inliers; 0.517 ratio; 0.569 px RMS; invalid visual geometry |
| Last selected record, source 24127 | 121 matches; 58 inliers; 0.479 ratio; 0.543 px RMS |

The [distance-4000 direct-to-seed render](g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_4000.jpg) is independent of the fitted seed paint corners: it shows a close-up of a player and graphic, with no court markings by which a full-court projection could be supported. The projected yellow court runs across the person and broadcast graphic. This is the same G241b geometry failure mode after the first cut, not evidence of a new fit. Reporting matches, inliers, or low residual alone as a valid map here would be exactly the direct-to-seed-across-a-cut error G274 forbids.

## Required side-by-side record

First-shot values below are quoted from G267, G270, and G271 retained records; G267 was not re-detected. "Not measured" in the second column is intentional: the no-map stop occurs before the detector and association route.

| Fixed measure | First shot: source 19599--23399 | Second shot: source 23476--24127 |
|---|---:|---:|
| Frames / usable map | 3,801 / G233d map valid within pre-cut span | 652 / no valid map from seed |
| Finite class-0 detector-box feet | 30,071 | Not measured (0 new boxes) |
| Emitted association IDs | 98 | Not measured (0 new IDs) |
| Same-ID consecutive detector-box steps | 29,973 | Not measured (0 new steps) |
| Strict-over-40-ft/s steps (fraction) | 4,090 / 29,973 (0.136) | Not measured |
| p99 / maximum court speed, ft/s | 700.118 / 100,457.241 | Not measured |
| Both-inside steps; strict-over-40 fraction | 23,783; 2,507 / 23,783 (0.105) | Not measured |
| One-inside/one-outside strict-over-40 fraction | 766 / 1,001 (0.765) | Not measured |
| Both-outside strict-over-40 fraction | 817 / 5,189 (0.157) | Not measured |
| Both-inside share of all strict-over-40 steps | 2,507 / 4,090 (0.613) | Not measured |
| Affected emitted IDs / total IDs | 79 / 98 | Not measured |
| Worst five / ten ID share of both-inside strict-over-40 steps | 521 / 2,507 (0.208) / 889 / 2,507 (0.355) | Not measured |
| Both-inside strict-over-40 steps above 83 px image displacement | 1,454 / 2,507 (0.580) | Not measured |
| Both-inside strict-over-40 steps below 17 px image displacement | 218 / 2,507 (0.087) | Not measured |

## Inputs, machine, code identity, and disk guard

| Input opened | Full path | Bytes / identity |
|---|---|---|
| Source video (streamed scene scan only) | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 bytes; 1920x1080; 174,430 frames; 30 fps |
| Retained direct-map series | `docs/evidence/tracking/g241b_seed_horizon_to_failure_artifact/extended_10000/g241b_measurement.json` | 4,855,274 bytes; SHA-256 `b6a4f81e419c43c01e2bb516dfb061c08107f8407308b834c4e08645c97c0673` |
| Independent geometry render | `docs/evidence/tracking/g241b_seed_horizon_to_failure_artifact/extended_10000/paired/direct_seed_renders/render_distance_4000.jpg` | 80,007 bytes; SHA-256 `1cccab6e44ec47760e56695b78b69739c399573d1c5c0ce330be58bc3abd6202` |
| First-shot retained records | `docs/evidence/tracking/g267_court_space_physical_plausibility_2026-09-04.md`, `g270_implausibility_conditioned_on_position_2026-09-04.md`, and `g271_implausibility_concentration_and_image_displacement_2026-09-04.md` | quoted only; no detector re-run |

The pod was used because the read-only full-resolution source is there. The distinct active Python-worktree set before the scan was `{ /workspace/wt/a17 }`: PIDs 3084857 and 3085457 shared that one CWD, so one of the two permitted lanes was free. No process was interrupted. The stream used `ffmpeg` only; this row exercised no deployed Python route and introduced no harness. The retained G241b series records source hashes `f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3` (G196), `dd23887aca61f50a65be51085033b398c97d056985fb8892eb5ab37009c5031a` (G215), and `7788d31c7ae4f705af0ec494547a28e160fb6b3980c383a6896b932499cea450` (G222).

`df` was not used. Before any local evidence write, `du -sm /workspace` was **40,062 MB**. The required `dd if=/dev/zero of=/workspace/wt/a6/.g274_fsync_probe.bin bs=1M count=1 conv=fsync` passed, wrote 1,048,576 bytes, and that exact probe was removed, freeing **1,048,576 bytes**. A later read-only re-measure was 40,074 MB, reflecting shared-workspace activity; no corpus source or either abandoned bridge partial was deleted. No full decode, crop set, or scratch measurement artifact was written.

## Contract self-check and NOT VERIFIED

No harness was added, so no focused test applies; no full test suite was run. A2: selected-record counts and extrema were recomputed from the full committed G241b direct-record series, and first-shot figures were quoted from retained G267/G270/G271 records. A3/B7: the second-shot decision uses the full 652-frame interior, while the independent distance-4000 render is geometry evidence rather than a head-slice metric sample. A4: the selected records form one contiguous, unique source-frame range. A5/B2--B6: this memo and the ledger alter no schema, reader field, lifecycle, deployment, source module, or module location. A7: all linked retained artifacts exist at writing. A9 names each opened input; A11 records the exercised route situation and retained map-route hashes. B1 retains the whole selected geometry series and names the zero detector-box denominator; B8 does not treat fitted paint points or zero direct-reference drift as independent evidence; B9 names detector boxes rather than players; B10 changes no threshold or bar. A12 does not apply because no allowlisted file grew. Q does not apply to this tracking measurement.

**NOT VERIFIED:** a second hand label, a valid second-shot map, any second-shot detector draw, a second-shot defect fraction, replication or difference of the G267/G270/G271 profile, person precision/recall, on-court status, duplicate status, identity correctness, a cause for any first-shot implausible step, another clip/arena, or a population-level claim. Two shots of one clip in one arena would still not be a population even if the second map were valid.
