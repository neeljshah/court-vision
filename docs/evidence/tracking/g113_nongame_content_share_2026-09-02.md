# G113 non-game content-share census

**Verdict: ACCEPT WITH CORRECTIONS.** The content issue is real and
concentrated in the current baseball-family corpus, rather than being normal
at the same level across every sampled sport. This is a corpus-quality census
only: no clip was re-downloaded, re-tracked, re-scored, moved, or deleted; no
threshold, coordinate contract, gate, or prior verdict changed. It follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7 and the section B
self-check below.

## Fixed vocabulary, declared before labels

The fixed mutually exclusive vocabulary and full decision rules were written
before visual classification in
[`g113_content/label_protocol.md`](g113_content/label_protocol.md):
`live_action`, `replay`, `studio_or_desk`, `advert`,
`graphic_or_scoreboard`, `crowd_or_filler`, and `pregame_warmup`. `live_action`
means primary coverage of the actual contest, including a game-camera athlete
close-up or in-game between-play coverage. It does not include generic crowd,
coach, venue, analyst, commercial, graphic, replay, or warm-up content. Every
other label is non-live for this census. No category was added while labelling.

## Current population and seeded sample

This is deliberately a different question from G99's three-frame sport-label
audit and G104's six-clip baseball visibility census. A live read-only pod
inventory found 69 readable clips, not G99's 66-clip snapshot: football 5,
KBO 13, MLB 13, NCAA basketball 6, NPB 8, soccer 10, tennis 9, and WNBA 5.
The current inventory is committed as
[`g113_content/inventory.csv`](g113_content/inventory.csv).

Before viewing a G113 frame, global seed `11320260902` was fixed with Python
`random.Random` (MT19937). Every filename was bytewise sorted. For every clip,
one source frame was drawn from each of `[10%,35%)`, `[35%,65%)`, and
`[65%,90%)` of its decoded frame range. This gives three seeded interior
temporal strata per clip, no head-only contribution, and 207 distinct decoded
`(file_name, source_frame)` units. Exact frame numbers, dimensions, decode
status, and render path are in
[`g113_content/sample_manifest.csv`](g113_content/sample_manifest.csv).

All 207 frames decoded. Every one was classified by eye in
[`g113_content/frame_labels.csv`](g113_content/frame_labels.csv), which joins
one-to-one to the manifest. The individual retained renders are under
[`g113_content/renders/`](g113_content/renders/); the eight all-frame sport
contact sheets are under [`g113_content/contact_sheets/`](g113_content/contact_sheets/).
The independently reproducible aggregation, including uniqueness assertions,
is [`g113_content/summary.json`](g113_content/summary.json).

## Live-action share by current corpus group

Intervals are two-sided Wilson 95 percent intervals with z = 1.959963984540054.
The denominator is every sampled decoded frame in its group: no studio,
graphic, or filler frame was dropped.

| Current group | Live / n | Live share | Wilson 95 pct CI | Non-live composition |
|---|---:|---:|---|---|
| football | 15 / 15 | 1.000 | [0.796, 1.000] | none sampled |
| kbo | 3 / 39 | 0.077 | [0.027, 0.203] | 18 graphics, 18 studio/desk |
| mlb | 21 / 39 | 0.538 | [0.386, 0.684] | 8 graphics, 10 studio/desk |
| ncaa_basketball | 14 / 18 | 0.778 | [0.548, 0.910] | 3 crowd/filler, 1 graphic |
| npb | 23 / 24 | 0.958 | [0.798, 0.993] | 1 crowd/filler |
| soccer | 30 / 30 | 1.000 | [0.886, 1.000] | none sampled |
| tennis | 24 / 27 | 0.889 | [0.719, 0.961] | 3 crowd/venue filler |
| wnba | 15 / 15 | 1.000 | [0.796, 1.000] | none sampled |

The baseball-family aggregate (KBO, MLB, and NPB) is **47 / 102 = 0.461,
Wilson 95 pct CI [0.367, 0.557]**. Its non-baseball comparison (football,
basketball, soccer, and tennis) is **98 / 105 = 0.933, [0.869, 0.967]**.
Thus roughly half non-game is not normal across this sampled broadcast corpus:
baseball is descriptively the lower-live-content outlier. The mechanism is
not uniform baseball footage. NPB is 23/24 live, MLB is mixed at 21/39, while
12 of 13 currently KBO-labelled clips are a studio/statistics programme and
yield only 3/39 live frames. These intervals treat frames as census units;
they are not a formal independent-clip hypothesis test, because three frames
from a clip are clustered.

## Exposure of published whole-clip frame numbers

- **G104 baseball landmark reachability is directly diluted, and already
  records the arithmetic.** Its primary whole-sample denominator retains all
  120 frames, including 60 non-game programme frames. The same retained
  numerators become 13/60 rather than 13/120 for visible points >= 2, 3/60
  rather than 3/120 for >= 3, and 1/60 rather than 1/120 for >= 4 when its
  explicitly identified game/replay subset is used. In each case the
  whole-sample rate is exactly one half of that subset rate. This memo does
  not replace G104's primary denominator or recompute its result; it names the
  intended corpus-quality exposure.
- **G11 baseball night pitch-view acceptance fractions are exposed but cannot
  be quantified from this census.** `baseball_night_pitchview_2026-09-01.md`
  reports 302/398 and 313/398 day-clip acceptance plus 16/398 and 156/398
  night-clip acceptance after evenly sampling each whole clip. Its persisted
  frame-level accepts and the G113 content labels are not on the same sampled
  source-frame keys, so a joint live-only fraction was not inferred or
  recomputed here.
- **G34 view/rally shares and the daemon's clip-level coverage figures are
  whole-broadcast quantities, but they are not detector-quality rates to
  correct using this result.** G34 intentionally includes close-ups, replay,
  crowd, and graphics in its denominator to bound achievable whole-clip
  calibration coverage (tennis rally share 125/300, WNBA WIDE 199/300, soccer
  WIDE 195/300). The daemon census's tennis coverage 0.15 to 0.67 similarly
  describes whole-clip operating coverage. It should retain that scope. Also,
  G34 separately established that the current harness counts emitted tracking
  frames rather than all decoded frames, so G113 cannot apply a content-share
  multiplier to those published harness fields.

## Existing content gate and recommendation

[`scripts/platformkit/footage_content_gate.py`](../../../scripts/platformkit/footage_content_gate.py)
already supplies a cheap, fail-open ingest screen: it seeks nine frames and
uses playing-surface color, dark-border share, and cut rate to return
`accept`, `review`, or an unambiguous no-surface `reject`. It is intentionally
not consulted by tracking metrics. It does **not** classify `live_action`, and
the current retained KBO studio/statistics clips show that it is either not
applied to this corpus block or is not sufficient to distinguish a programme
about baseball from a contest feed. No conclusion about an individual gate
decision was manufactured without running the gate.

Recommended next step: preserve this fail-open acquisition check, add a
separate live-action filter before detector scoring, and record a per-clip
usable fraction in the corpus ledger. A score should then state whether its
denominator is all decoded frames or filtered live-action frames. This is a
recommendation only; G113 builds no filter, changes no scoring denominator,
and applies no gate to existing clips.

## NOT VERIFIED

- This is a three-frame-per-current-clip sample, not a duration-weighted
  measurement of every source frame or a permanent per-sport broadcast
  constant.
- One observer supplied the eye labels; no blinded second pass or inter-rater
  agreement was measured.
- The current 69-clip inventory differs from G99's 66-clip snapshot. This
  memo does not determine why the inventory or filename sport groups changed.
- No existing detector, pitch-view gate, tracking coverage, landmark count,
  or published harness score was recomputed on live-only frames.
- No content-gate run was performed on the corpus, so its live-action recall,
  precision, and current call sites remain unmeasured here.

## Verifier self-check

- **A2/A4:** `summary.json` recomputes the headline counts from labels and
  asserts 207 manifest rows, 207 label rows, and 207 unique keys in each,
  with an exact key join. **A3/B7:** all retained renders were viewed; each
  clip contributes one seeded draw from each of three interior temporal
  strata, rather than a head slice. **A5:** no production field or reader was
  changed; this is additive evidence only. **A6:** no master landing was
  attempted by this lane; a verifier must use the contract's explicit archive
  procedure if landing this worktree into master. **A7:** every evidence path
  named above exists in this worktree at memo time.
- **B1 circular metric:** clear. Every decoded selected frame remains in its
  sport denominator; non-live rows are named, labelled, and retained.
- **B2 non-additive schema:** clear. No schema, field, status value, or reader
  changed.
- **B3 fall-through loss / B4 re-claim loop:** clear. No gate, queue, claim,
  or failure behavior changed.
- **B5 pre-verification deploy:** clear. The pod was read-only; frames were
  decoded and streamed to local evidence without a pod write or deployment.
- **B6 orphans:** clear. No module, import, test, or command was moved or
  retired.
- **B8 self-fit as independent:** clear. This is a direct eye census, not a
  fitted residual or held-out performance assertion.
- **B9 degenerate denominator:** clear. Each unit is a unique sampled
  `(file_name, source_frame)` pair, and uniqueness is asserted.
- **B10 moved bar:** clear. No threshold, coordinate contract, gate value,
  clip, or prior verdict changed.
