# G269: Physical reassociation headroom from G267's retained detector boxes

## Verdict

**FRAGMENTATION, NOT ASSOCIATION HEADROOM: the sealed 40 ft/s reassociation
reduces the strict-over-40-ft/s fraction from 4,090 / 29,973 = 0.136 to 0 /
29,932 = 0.000, but increases IDs from 98 to 139 and reduces p90/max track
length from 841.700 / 1,639 to 526.400 / 777 observations.** The zero after
fraction is mechanically enforced by the sealed candidate-edge rule; it may
not be read alone. The 41.837 percent ID increase, 37.460 percent p90 drop,
and 52.593 percent maximum drop make this a fragmentation result under G269's
predeclared interpretation, not evidence of usable association improvement.
Under the row's decision rule, the defect therefore redirects to the
detector-box population rather than association. This does not establish a
cause: no identity ground truth exists, and a physically plausible connection
can still be the wrong person or a non-person box.

Denominator: one non-deterministic detector draw, one G233d map, one WNBA
clip/arena/pre-cut shot, source frames 19599--23399 inclusive (3,801 frames),
and 30,071 retained finite class-0 detector-box footpoints. These are detector
boxes, not authenticated players: officials, bench personnel, spectators, and
duplicates can occur in the population. G225's 19 boxes for two visibly
on-court people remains a direct warning against treating this denominator as
people.

## Sealed constraint and exact reused input

The preregistration was committed before the first baseline or reassociation
score in commit `ad76cca25679ed5b852349b5983c9435461f0d8e`. Its LF-payload
SHA-256 seal is
`5391eeb4838a5f57897c3af002b0e407e48dc7cb6f34990af64ab0e4ee78220f`.
It fixes the sole reference as a step **strictly greater than 40.0 ft/s**;
there was no alternate reference, sweep, refit, redetection, relabelling, or
production change.

The only measurement input opened was G267's retained
[`g267_measurement.json`](g267_court_space_physical_plausibility_artifact/g267_measurement.json),
SHA-256 `183b195f0f3ea7b8a81c47a384c229b4e10ca464dc32f2ecfc1a52ccef6fdedb`.
It contains the G267 detector boxes and G233d projections for exactly the
declared span. The original video was not reopened; G267 identified it as
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes, 1920x1080. Thus this row reuses that one retained draw,
not a fresh non-deterministic detector pass.

Before reassociation, G267's analysis was rerun unchanged on those records and
matched its named baseline exactly: 30,071 finite boxes, 98 emitted IDs, 29,973
same-ID consecutive steps, and 4,090 strict-over-40-ft/s steps. A mismatch is
an execution error in the harness and aborts scoring.

## Fixed post-hoc procedure

For source frames in ascending order, each current finite detector-box
footpoint considered the most recent box of every earlier reassociated ID. An
edge was eligible only when its actual-frame-gap court speed was at most 40.0
ft/s. A one-to-one assignment first maximized the number of eligible edges and
then minimized total distance divided by the edge's permitted distance; stable
ascending IDs and detector-box indexes resolve exact ties. An unmatched current
box began a new ID. No box was discarded, and the rule used no appearance,
team, image, detector confidence, original ID, future frame, or added timeout.
This is a post-hoc headroom measurement, not a tracker proposal.

## Required before/after set

| Measure | G267 emitted association | Sealed court-space reassociation |
|---|---:|---:|
| Finite detector-box footpoints | 30,071 | 30,071 |
| Strict-over-40-ft/s same-ID steps / all same-ID steps | 4,090 / 29,973 | 0 / 29,932 |
| Strict-over-40-ft/s fraction | 0.136 | 0.000 |
| Track IDs | 98 | 139 |
| Track length median observations | 120.000 | 194.000 |
| Track length p90 observations | 841.700 | 526.400 |
| Track length maximum observations | 1,639 | 777 |
| Detector boxes left unassociated | 0 | 0 |

The post-hoc IDs rise by 41 while their upper length distribution contracts.
The increased median does not undo that fragmentation evidence: the mandated
ID count, p90, and maximum expose it. Therefore the apparent 0.136 reduction
does not quantify real available association headroom. Per the predeclared
decision rule, the next diagnostic should regard the detector-box population
as the binding defect rather than treat this reassociation result as a fix.

The full before/after records and all assigned IDs are retained in
[`g269_measurement.json`](g269_physical_reassociation_headroom_artifact/g269_measurement.json),
13,486,974 bytes, SHA-256
`9f0fa89282e252986dbffeda75d62c38f1b5ade75c842578dca633cd522f702d`.
The [sealed preregistration](g269_physical_reassociation_headroom_artifact/g269_preregistration.md)
and the small harness preserve the exact input, constraint, and computation.

## Machine, disk guard, and verification

This ran locally in `C:\Users\neelj\nba-track-a6`; no pod computation or
source-video access occurred. As required, `df` was not used. The authoritative
pod path `/workspace` is absent in this Windows worktree, so `du -sm
/workspace` returned no MB value (`No such file or directory`); that is not
silently substituted with a local quota figure. G267's earlier pod run recorded
36,920 MB for `/workspace`, but it is historical context, not a current G269
measurement. The binding local pre-write command `dd if=/dev/zero
of=.g269_disk_probe bs=1 count=1 conv=fsync status=none` succeeded and removed
its 1-byte probe. A preceding 1-byte local filesystem preflight also removed
its probe. Known temporary bytes freed: 2. No corpus source, bridge partial,
or other material was deleted.

```text
python -m pytest scripts/platformkit/tracking/test_g269_physical_reassociation_headroom.py -q -p no:cacheprovider
2 passed in 1.12s
```

Contract self-check: A7 artifacts named above exist; A9 source identity is
inherited and named without reopening the source; B1 retains all 30,071 finite
boxes and names the structural speed pairing; B2--B6 change no schema,
production route, lifecycle, deployment, or gated tree; B7 has the complete
retained span; B8 uses no fit residual; B9 states box, ID, and step
denominators; B10 uses G267's fixed 40 ft/s reference. Q does not apply to
this tracking measurement. The new 212-line harness and 39-line focused test
do not grow an allowlisted file, so A12 requires no rail change.

## NOT VERIFIED

- Real identity, person precision/recall, on-court status, or whether any
  physically plausible reassociated box sequence is the correct individual.
- Any causal split of the G267 impossible steps into detection, association,
  projection, or real movement; the fragmentation classification is a metric
  safeguard, not causal proof.
- Another clip, shot, arena, G233d map, sport, detector draw, or an independent
  repeat. G241 found 808 of 1,201 records changed on a detector rerun.
- Map correctness below the roughly 20-px G257 eye limitation. Court-space
  speeds inherit that map limitation.
- A production tracker, threshold, gate, tuning choice, or readiness claim.
