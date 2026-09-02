# G97 G84 render durability

Date: 2026-09-02. This is an evidence-durability repair only. It did not redraw
the G84 sample, relabel any frame, change a detector parameter or threshold, or
touch `line_calibration.py`.

## Result

**ACCEPT WITH CORRECTION.** The stated `before = 0 of 33 renders present`
premise is false in the current Git tree. All 33 fixed G84 JPEGs already exist
and are committed at
[g84_candidate_quality/renders/](g84_candidate_quality/renders/) by ancestor
`929e101c8`. The original G84 commit has 33 render paths and zero source
contact-sheet paths. The immediately preceding G93 refusal inherited those 33
render paths; its actual blocker was the absent source contact sheets needed to
derive fresh candidates.

I reran the unchanged G84 renderer against the surviving read-only G84 source
worktree into a temporary directory, rather than running its in-place mode
(which deletes its output directory before rendering). The rerun chose the same
33 identities from [selection.json](g84_candidate_quality/selection.json),
reproduced every candidate count in
[sample_manifest.csv](g84_candidate_quality/sample_manifest.csv), and produced
byte-identical JPEGs for all 33 files. Therefore no replacement binary was
written: the tracked render files already are the faithful regenerated output.

Renderer environment: `cv2 4.13.0`.

| check | result |
|---|---|
| selected frames | 33/33, fixed seed `84092026`, unchanged |
| candidate-count rerun | 33/33 exact matches to the committed manifest |
| regenerated JPEG bytes | 33/33 identical to the committed JPEGs |
| committed readable renders | 33/33 in `g84_candidate_quality/renders/` |

## Required candidate-count spot checks

The rerun matched all 33; these four source-spaced examples are displayed
explicitly rather than a head slice.

| clip | frame | manifest count | rerun count |
|---|---:|---:|---:|
| NCAA IB-_u4gW3ds | 16704 | 50 | 50 |
| NCAA IB-_u4gW3ds 1080p | 11760 | 46 | 46 |
| WNBA 01 | 13632 | 54 | 54 |
| WNBA 05 | 2304 | 49 | 49 |

## Eye check

I opened these regenerated JPEGs. Each is readable and shows a basketball court
frame with the yellow indexed candidate lines drawn; none is empty or corrupt.

| clip | frame | render |
|---|---:|---|
| NCAA IB-_u4gW3ds | 16704 | [JPEG](g84_candidate_quality/renders/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__f16704.jpg) |
| NCAA IB-_u4gW3ds 1080p | 11760 | [JPEG](g84_candidate_quality/renders/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__f11760.jpg) |
| WNBA 01 | 13632 | [JPEG](g84_candidate_quality/renders/wnba__wnba_01__f13632.jpg) |
| WNBA 05 | 2304 | [JPEG](g84_candidate_quality/renders/wnba__wnba_05__f2304.jpg) |

## Cause and prevention

The renders did survive: `929e101c8` committed them to the required tracked
path, so neither a gitignored render path nor an uncommitted render explains the
current state. The missing input was the 66 G68 contact sheets: they remained
untracked in the original G84 worktree (zero Git-index entries there and zero
such entries in its commit). They were not ignored by a repository ignore rule.
That made them worktree-local intermediate data which a dispatch-wrapper hard
reset can delete by design. Retaining the exact 33 source tiles (or the contact
sheets) under a tracked evidence path at G84 landing time would have made a
fresh detector rerun independently reproducible and would have prevented G93's
source-input outage.

## Verifier contract self-check

- A7: every linked evidence path in this memo exists now: this memo,
  `selection.json`, `sample_manifest.csv`, and all 33 render JPEGs.
- B1: no row was excluded; the fixed 33-frame selection was rerun in full.
- B2: additive memo only; no schema or reader changed.
- B3: no gate changed.
- B4: no claim, queue, or failure path changed.
- B5: no file was copied to the pod.
- B6: no module was moved or retired.
- B7: detector counts cover all 33; the printed spot checks span four clip
  families rather than a head slice.
- B8: no fit or residual is presented as independent evidence.
- B9: the denominator is 33 unique `(clip, frame_index)` identities.
- B10: the rerun used the committed G84 detector call and constants unchanged.

## Not verified

- G97 did not relabel the fixed G84/G76 sample or rerun the G84 quality audit.
  A supplemental preview of NCAA `sRtHQbywiTE` frame `9408` is an interview
  shot; this observation is recorded without changing its fixed membership or
  count, and its G76 eligibility is not verified by this durability row.
- The current original-worktree contact sheets are still not durable evidence.
  This run proves recovery while that worktree survives, not a clean-checkout
  source-tile recovery.
- No replacement detector, calibration setting, threshold, role rule, or G93
  recall result was evaluated.
