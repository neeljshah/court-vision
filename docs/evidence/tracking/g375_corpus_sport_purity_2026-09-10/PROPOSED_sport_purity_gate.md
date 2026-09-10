# PROPOSED (research note only): an additive `sport_purity` field for the content gate

Row G375. Nothing here is landed, deployed, flagged on, or applied. The landed gate
`scripts/platformkit/footage_content_gate.py` was READ and IMPORTED only for this
row; no threshold in it was read back out and changed, and no file under
`/workspace/deploy` or `/workspace/nba-ai-system` was touched. This note exists so a
human can decide, later, whether the gap G375 measured is worth closing and how.

## What the landed gate actually decides

`decide()` (footage_content_gate.py:123-136) reads three cheap statistics over nine
seeked frames: `max_surface` (the largest per-frame fraction of pixels inside an
HSV band chosen by SPORT NAME in `_ranges()`, tan for basketball), `max_border`
(letterbox / pillarbox run) and `cut_fraction` (Bhattacharyya histogram distance
between the last four sampled frames). It rejects only two unambiguous
non-game shapes, calls anything thin `review`, and otherwise returns
`accept / playing_surface_and_shot_continuity_present`.

The gap: `_ranges()` picks its colour band FROM THE DECLARED SPORT, then asks only
whether that band is present. It never asks whether the band it found belongs to the
sport that was declared, and no other clause in the module looks at sport identity.
A clip whose declared sport is basketball and whose frames carry enough tan-band
pixels and enough shot continuity is `accept`, whatever game is being played. That is
by design -- the module's docstring calls itself an ingest decision that must never
change a score denominator -- and it is exactly why the census in this row was needed.

## What the census measured

Over 281 rated section midpoints: 452 per mille [395, 510] are not live basketball
play, but almost all of that is BASKETBALL_NONPLAY (119 of 127) -- a MIDPOINT-TICK
artifact rather than a corpus defect, because one sealed frame per section lands
wherever it lands. SPORT impurity, the thing this row was opened for, is 7 of 281 =
25 per mille [12, 51]: six OTHER_SPORT (soccer) and one NON_SPORT.

The decisive shape: all six soccer frames come from ONE video, `oW8psSa2hf4`,
ingested under the `bleague` tag, and that single video IS the entire `bleague`
stratum of the corpus (6 of 6 sections, 1000 per mille [610, 1000]). Remove it and
sport impurity over the rest is 1 of 275 = 4 per mille [1, 20]. The gap is a
SOURCE-ADMISSION gap on whole videos, not a frame-level leak spread thinly across
the corpus. A per-video check at fetch time is therefore a far cheaper fix than a
per-frame gate field, and a follow-up row should price that first.

## The proposed field

Additive, never a new reject branch:

    sport_purity: float | None        # 0..1, None when unavailable
    sport_purity_source: str          # "frozen_nn" | "unavailable"

computed as the cosine nearest-class score of a frozen ImageNet ResNet-18 embedding
against a small labelled reference, appended to `GateMetrics` and reported in the
feeder `SHIPPED` line beside `max_surface_permille`. `decide()` is NOT changed by
this proposal: the field is REPORTED for a review period, so a threshold can be
chosen from observed data rather than guessed, and so a bad signal cannot silently
quarantine good footage (B3: missing is not bad).

Cost, measured in this row on CPU: one 224x224 forward pass per sampled frame.

## What this row did NOT establish, and what a follow-up row must

- The diagnostic run here uses the G364 development reference, whose classes are
  COURT-PRESENCE classes (USABLE_COURT / CLOSEUP / CROWD_GRAPHICS), not sport
  classes. It is reported in `diagnostic.json` as a DIAGNOSTIC of an existing frozen
  artifact on new points; it is not a gate result and licenses no threshold. It also
  MEASURABLY FAILS as a sport signal: nearest-neighbour USABLE_COURT share is 916 per
  mille on BASKETBALL_PLAY but 176 on BASKETBALL_NONPLAY and 167 on OTHER_SPORT --
  it separates court from non-court and does NOT separate soccer from a basketball
  crowd shot. The candidate signal named in the spec is therefore REJECTED as a
  sport_purity source on this evidence.
- No sport-labelled reference set exists. The 281 adjudicated labels from this row
  are the obvious seed, but fitting anything on them and then scoring the same 281
  is self-fit and is not evidence (B8). A follow-up row needs a game-disjoint second
  draw.
- The gate screens the WHOLE section; this census rates ONE sealed midpoint frame per
  section. A section can be mostly basketball and impure at its midpoint, or the
  reverse. A per-section purity claim needs several ticks per section.
- No cost, latency or false-quarantine rate for the proposed field has been measured
  inside the feeder.
