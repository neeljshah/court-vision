# G272: Box-jump visual classification prerequisite audit

## Verdict

**CLOSED AT LIMIT / FALSIFIED INPUT PREREQUISITE.** The required count does
reproduce: **1,454 / 2,507 = 0.580** of retained both-endpoints-on-court
strict-over-40-ft/s same-ID detector-box steps have bottom-centre image
displacement above 83 px. But the landed G267 retained artifact does **not**
retain drawable detector bounding boxes. It retains only each box's
bottom-centre footpoint and associated fields. Therefore G272's required
before/after full-resolution pair with that ID's retained box drawn cannot be
made exactly without either (1) re-detecting, which G272 forbids because G241
showed non-determinism, or (2) inventing rectangle geometry. Neither was done.

This is not a category distribution. No sample was selected, no paired frame
was decoded, no randomized blind order was created, no visual verdict was
entered, and no image render was committed. In particular, this memo does not
misstate absent measurements as zero: categories (a), (b), (c), and (d) are
all **not measured**, with (d) remaining separate.

The population remains retained finite detector boxes / associated observations,
not authenticated players. The reproduced count is over one non-deterministic
detector draw, one WNBA clip, one arena, one pre-cut camera shot, G233d's
published map, source frames 19599--23399, 2,507 on-court impossible steps,
and 1,454 box-jump steps. It is not a player count.

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`.

## Exact input and count reproduction

The only measurement input opened was
`C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g267_court_space_physical_plausibility_artifact\g267_measurement.json`,
12,446,681 bytes, SHA-256
`0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`.
Its inherited, unopened source is
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes, 1920x1080, 30 fps. No source video was decoded for G272;
no detection, association, map fit, map change, or reassociation was run.

Using the landed G271 analysis route on every G267 frame record reproduced:

| Retained quantity | Count |
|---|---:|
| Finite detector-box feet | 30,071 |
| All-position same-ID steps | 29,973 |
| Strict-over-40-ft/s steps | 4,090 |
| Both-endpoints-on-court impossible steps | 2,507 |
| Above-83-px box-jump steps | **1,454** |

The exact command was:

```text
python -c "import json; from pathlib import Path; from scripts.platformkit.tracking import g271_implausibility_concentration_and_image_displacement as g271; p=Path('docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json'); source=json.loads(p.read_text(encoding='ascii')); report=g271.analyze(source['frame_records']); split=report['descriptive_movement_split']['counts']; print('G271_REPRODUCED_BOX_JUMPS=' + str(split['box_jump'])); assert split['box_jump'] == 1454"
```

It printed `G271_REPRODUCED_BOX_JUMPS=1454`.

## Falsified retained-box premise

Every retained G267 detection record has exactly these fields:

```text
track_id, source_frame, foot_x_px, foot_y_px, court_x_ft, court_y_ft,
finite, nearest_previous_track_id, nearest_previous_id_changed
```

The landed producer
`scripts/platformkit/tracking/g267_court_space_physical_plausibility.py` likewise
serializes only those fields. There is no `xyxy`, left/right/top/bottom,
width/height, or other rectangle representation in the artifact. A retained
footpoint cannot determine the source detector rectangle. Consequently, a
rectangle placed around it would not be G267's retained box and would make the
specified visual evidence non-reproducible.

The required categorical judgement would be appropriate *if* the preserved
boxes existed: deciding whether two marked bodies are the same person is a
coarse categorical judgement, not the sub-pixel court-overlay geometry that
G257 bounded at roughly 20 px. That distinction does not authorize a fabricated
box, so the categorical eye check was not performed.

## Sampling, blind verdicts, and consequence

The requested even, multi-ID sample and its rendered frame pairs have `n=0`
because their required input is absent. There is no blind randomization order,
no pre-unblinding verdict artifact, no distinct-ID coverage, and no category
fraction to report. This is deliberately not presented as a sample of the 1,454
steps.

Accordingly, G272 supplies no evidence to choose among identity association,
non-person detections, duplicate/wrong-person boxes, map error, detector motion,
or real motion. It does not establish that (b) or (c) dominates, and it does
not qualify the existing physical-implausibility framing via category (a).
No production change, filter, gate, threshold, or tracker change is proposed.

## Disk guard, tests, and contract self-check

No pod render job was started. A fresh executable-and-argument process census,
excluding its own checker process and parent, found active pod routes `a15` and
`a17`; G272 therefore did not take a third lane. Since the requisite renders
could not be made, no `/workspace` write or `dd conv=fsync` render preflight was
performed. This memo records no invented disk figure: `du -sm /workspace` is
not available in this Windows worktree, and no historical pod figure is
substituted. Bytes freed: 0. Render bytes committed: 0.

```text
python -m pytest scripts/platformkit/tracking/test_g271_implausibility_concentration_and_image_displacement.py -q -p no:cacheprovider
2 passed in 0.99s
```

Contract self-check: A7 names the only artifact path and it exists; A9 names
the exact opened artifact and inherited video identity; A11 is not a pod-run
claim. B1 retains the full G267 population for count reproduction and names the
structural on-court condition; B2--B6 alter no schema, lifecycle, deployment,
production route, or module; B7 uses the entire retained pre-cut span rather
than a head slice; B8 uses no fit residual; B9 states all applicable detector
box, ID, and step denominators; B10 moves no threshold. Q does not apply to
this tracking measurement. No harness was added, so A12 does not require a LOC
rail change.

## NOT VERIFIED

- Any visual category count or fraction, including whether a retained ID jumps
  to a different person, tracks a non-person, or represents real fast motion.
- Any before/after box render, sample coverage, blind verdict, or identity
  claim; raw box rectangles were not retained.
- Another clip, shot, arena, map, sport, or detector draw.
- Person precision/recall, on-court status, duplicate status, or true identity.
- Any production filter, gate, threshold, tracker change, or readiness claim.
