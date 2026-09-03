# G161 Rally-View Census Protocol

This protocol was fixed before any G161 frame labels were reviewed.

## Sample

- Source: `data/videos/reference/tennis.mp4`, decoded-frame extent `0..28772`.
- Seed: `16120260903`.
- Sampling: one systematic sample of 300 indices over the full decoded extent.
  The seed selects a single phase in the 95/96-frame spacing lattice; sample
  indices are then sorted and differ by either 95 or 96 frames. No head slice,
  clip substitution, rally conditioning, or post-label sample replacement is
  permitted.

## Verbatim labelling rule

> Label `RALLY-VIEW` only when the primary broadcast picture is the elevated,
> wide tennis-court camera and enough of the playable court is visible to show
> the net and both player halves (normally both baselines), whether a point is
> in progress or a player is preparing to serve. Label `NOT_RALLY` for every
> replay, even a wide replay; every close-up, crowd, bench, player-walk,
> changeover, or low/net-level angle; and every full-screen scoreline,
> transition, or graphic. A persistent small score bug over an otherwise
> qualifying wide live-court picture still counts as `RALLY-VIEW`; a scoreline
> graphic that replaces or materially obscures the court counts as `NOT_RALLY`.

The second pass uses precisely the same rule and is performed without opening
the first-pass labels.
