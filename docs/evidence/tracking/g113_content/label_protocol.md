# G113 fixed content taxonomy and sampling protocol

This protocol was written before any G113 frame content label. It is additive
evidence for the G113 corpus-quality census and changes no corpus object,
tracking result, threshold, or coordinate contract.

## Sampling population and deterministic draw

The population is every readable `.mp4` in the live pod directory
`/workspace/nba-ai-system/data/footage_corpus/`, grouped by its current
filename sport prefix. The inventory, frame count, dimensions, and every
selection are retained in `sample_manifest.csv`.

Global seed: `11320260902`, using Python's `random.Random` (MT19937). Sort
the filenames in bytewise ascending order. For each clip, take exactly one
integer source frame uniformly from each of these three non-overlapping
interior temporal strata, inclusive of the lower bound and exclusive of the
upper bound:

1. `[0.10 * frame_count, 0.35 * frame_count)`
2. `[0.35 * frame_count, 0.65 * frame_count)`
3. `[0.65 * frame_count, 0.90 * frame_count)`

Bounds are `floor(fraction * frame_count)`, clamped to valid source-frame
indices. The PRNG is consumed in sorted-clip, ascending-stratum order. Each
selected source frame is decoded exactly once, JPEG rendered, and retained.
Thus every sampled frame is interior, the sample has three temporal strata per
clip, and no clip has a head-only contribution.

## Fixed, mutually exclusive content vocabulary

Assign exactly one label by eye to every rendered source frame. The label is
the visual programme content, not the filename sport label.

| Label | Fixed decision rule |
|---|---|
| `live_action` | Primary broadcast coverage of the actual contest, including a game-camera athlete close-up or in-game between-play coverage. The frame need not show the full surface, but it must be coverage of participating athletes rather than a generic crowd, analyst, or non-contest programme. A small scorebug over such footage does not change this label. |
| `replay` | A replayed segment of contest footage, identified by replay treatment, a repeated prior play, or replay graphics; do not call it live even when it shows athletes on the surface. |
| `studio_or_desk` | Presenter, commentator, analyst, control-room, or desk programming not showing the contest as primary coverage. |
| `advert` | Commercial, sponsor promotion, or branded sales segment. |
| `graphic_or_scoreboard` | Full-screen score, statistics, schedule, title, animation, or other graphic whose primary content is not the contest footage. |
| `crowd_or_filler` | Crowd, mascot, venue exterior, fan, cheerleader, or other non-playing filler shot. |
| `pregame_warmup` | Warm-up, practice, introductions, or pre-contest player activity rather than regulation contest coverage. |

If an image contains multiple elements, use the primary visual programme
content. Do not introduce a new category. A frame is counted as live action
only when its label is `live_action`; all other fixed labels are non-live.

## Metrics

For every current filename sport prefix, report `live_action / all sampled
frames` with two-sided Wilson 95 percent intervals (z = 1.959963984540054).
The primary denominator retains every selected readable frame, including all
non-live classes. A frame unreadable after a deterministic seek is retained in
the manifest as `decode_failed`, is not silently replaced, and is named in the
memo; the census then reports the readable-frame scope explicitly.
