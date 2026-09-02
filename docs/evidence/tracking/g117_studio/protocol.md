# G117 clip-review protocol

## Purpose

This review distinguishes a baseball game broadcast from a programme about
baseball. It does not re-label a sport, re-score tracking, or alter an
existing metric denominator.

## Predominance rule, declared before the G117 review

A clip is **predominantly non-game** only when at least 4 of its 5 spread
frames (80 percent) are not `live_action`. This strict supermajority avoids
moving a genuinely mixed clip on a marginal majority.

The content vocabulary is the immutable G113 vocabulary: `live_action`,
`replay`, `studio_or_desk`, `advert`, `graphic_or_scoreboard`,
`crowd_or_filler`, and `pregame_warmup`. Only `live_action` counts as live;
the other six values count as non-live. A G117 label uses the same G113
decision rule: primary coverage of the actual contest, including an in-game
athlete close-up or between-play game coverage, is `live_action`; a presenter,
analyst desk, full-screen programme statistic or graphic is not.

## Candidate and five-frame sample construction

The preliminary candidate set is every KBO clip with 0 of 3 G113
`live_action` labels. Each candidate's five-frame sheet contains its three
already-seeded G113 interior frames plus frame `floor(0.20 * frame_count)` and
frame `floor(0.80 * frame_count)`, sorted in ascending source-frame order.
The two additions extend the retained interior evidence without head-only
sampling. They were selected mechanically before their pixels were inspected.

Each sheet is a direct read-only decode from the named pod corpus file. Panel
order and the exact source-frame keys appear in `review_manifest.csv`; a
reviewer can reproduce an individual panel by seeking the named source file
to its listed zero-based frame index. `labels.csv` retains the individual
five-frame decisions and the final 4-of-5 calculation.

## Quarantine convention

After five-frame confirmation only, the clip is moved from
`data/footage_corpus/` to `data/footage_quarantine/` using the existing
`quarantine_manual` convention: a reversible source move plus an adjacent JSON
sidecar containing `reason`, `quarantine_reason`, `sport_verified: false`, and
`metrics: null`. No file is copied to `data/footage_bridge`.
