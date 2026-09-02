# G104 baseball landmark reachability census

**Verdict: CLOSED AT LIMIT (reachability measured).** This is an eye-judged
visibility census only. It follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7 and the B1-B10
self-check below. No solver, landmark registry, coordinate declaration,
threshold, or existing verdict changed.

## Fixed sample and label protocol

The six source clips were read from the pod only, then copied locally solely
for decoding and review. Nothing was copied to the pod and no pod process was
changed. With global seed `1042026`, two clips were drawn without replacement
from each feeder label's then-current pod inventory (13 MLB, 13 KBO, 7 NPB).
The same PRNG then made one uniform draw from each of 20 equal-sized temporal
strata in every selected clip. This is 120 decoded frames, not a head slice:

| Feeder | Clip | Decoded frames | Sampled |
|---|---|---:|---:|
| MLB | `mlb__mlb_5IA4jaKNOYg.mp4` | 28,801 | 20 |
| MLB | `mlb__mlb_3Oc4S_1np98.mp4` | 35,965 | 20 |
| KBO | `kbo__kbo_FDSWjM_OaTs.mp4` | 28,800 | 20 |
| KBO | `kbo__kbo_bGQwZl43E9Y.mp4` | 28,800 | 20 |
| NPB | `npb__npb_01_720p.mp4` | 18,001 | 20 |
| NPB | `npb__npb_jm2Ocr-LAtc.mp4` | 28,801 | 20 |
| **Total** | **six clips / all three feeders** | | **120** |

The exact draws, source-frame numbers, decoded dimensions, and render paths
are in [`g104_baseball_reach/sample_manifest.json`](g104_baseball_reach/sample_manifest.json).
The counting rules are predeclared in
[`g104_baseball_reach/label_protocol.md`](g104_baseball_reach/label_protocol.md).
Every selected frame was reviewed from the six full-set contact sheets and,
where feature identity could matter, the full-resolution render. The complete
per-frame judgment is in
[`g104_baseball_reach/frame_labels.csv`](g104_baseball_reach/frame_labels.csv);
all 120 individual renders and their six contact sheets are in
[`g104_baseball_reach/final_renders/`](g104_baseball_reach/final_renders/).

## Content confound retained in the denominator

Sixty of 120 selected frames are not baseball gameplay: all 20 frames in the
MLB-labelled `mlb__mlb_5IA4jaKNOYg.mp4` commentary/reaction programme and all
40 frames in the two KBO-labelled studio programmes. They are retained as
`baseball_non_game_program` rows, with no point identity attributed, rather
than silently dropped. This is feeder-content mismatch evidence for G99; it
does not assert that the studio programmes concern a different sport. The
other 60 frames are baseball game or replay-camera footage.

## Recomputed visibility result

The primary denominator is every one of the 120 seeded decoded frames. The
committed summary recomputes all rows and asserts 120 unique `(clip, slot)`
pairs against the manifest:
[`g104_baseball_reach/summary.json`](g104_baseball_reach/summary.json).

| Visible identifiable point features | Frames / 120 | Share |
|---|---:|---:|
| >= 2 | 13 | 0.108 |
| >= 3 | 3 | 0.025 |
| >= 4 | 1 | 0.008 |

The count distribution is 103 frames with zero, 4 with one, 10 with two, 2
with three, and 1 with four visible named points. The sole four-point frame is
the overhead whole-infield view in
`mlb__mlb_3Oc4S_1np98.mp4`, slot 14: home, first, second, and third base are
discernible. It is not the normal centre-field pitch view. Centre-field views
in the two NPB clips most often expose at most home plate and the pitching
rubber; they produce 11 of the 13 two-or-more-point frames, but no four-point
frame.

For context only, retaining the same rows but restricting the denominator to
the 60 rows explicitly classified as game/replay footage gives 13/60 at >=2,
3/60 at >=3, and 1/60 at >=4. This does not replace the primary full-corpus
denominator above.

### Straight-line directions

Foul-line directions were counted only where visibly discernible; the curved
infield-dirt edge was not promoted to a straight-line direction. The direction
distribution is 116 frames with zero independent directions, 2 with one, and
2 with two. No frame reaches three independent straight-line directions, and
no frame reaches four. The two visible foul lines in a wide infield view are
two non-parallel constraint families, not duplicate raw segments.

## Decision

**Baseball `court_feet` is reachable only on rare overhead whole-infield shots
(1/120 frames, 0.8%; 1/60 gameplay frames), not on the ordinary centre-field
view, which reaches at most two identifiable points in this sample.**

Unlike soccer's outfield-scale caveat, the successful view's four base points
belong to the dimensionally fixed infield: 90-foot base paths, with the rubber
at its fixed regulation offset. Thus the finding is a framing-frequency limit,
not an outfield-dimension ambiguity. It does not authorize a solver or a
coordinate-space declaration: the observed eligible view is too rare to claim
corpus-wide reachability.

## NOT VERIFIED

- No point, line, or mixed homography was implemented or scored.
- No detector's recovery of these manually visible features was measured.
- No clip declares `court_feet`, and no held-out distance error or temporal
  calibration was produced.
- The six-clip seeded census does not estimate every baseball-labelled clip in
  the pod; it measures the requested cross-feeder decision set.
- The content mismatch finding is visual evidence only; a corpus-wide G99
  audit remains required.

## Verifier self-check

- **A7:** every evidence path named in this memo exists in this worktree at
  memo time: the manifest, protocol, 120-row labels, summary, 120 renders,
  and six contact sheets.
- **B1 circular metric:** clear. Every seeded decoded frame remains in the
  primary 120-frame denominator, including 60 non-game programme frames.
- **B2 non-additive schema:** clear. No production schema, reader, field, or
  status value changed.
- **B3 fall-through loss:** clear. No gate or quarantine behavior changed.
- **B4 re-claim loop:** clear. No failure or claim behavior changed.
- **B5 pre-verification deploy:** clear. The pod was read-only; no file was
  copied to it and no deployment occurred.
- **B6 orphans:** clear. No module, import, test, or command was moved or
  retired.
- **B7 head-slice evidence:** clear. Every clip contributes one seeded draw
  from each of 20 temporal twentieths, with all resulting renders committed.
- **B8 self-fit as independent:** clear. This is an eye-judged visibility
  census, not a fit residual or solver validation.
- **B9 degenerate denominator:** clear. Each unit is one unique seeded
  `(clip, source_frame)` pair; the manifest-to-label join was asserted unique.
- **B10 moved bar:** clear. Every threshold, coordinate contract, existing
  verdict, and G91/G101 result is unchanged.
