# G401 preregistration

Gap: G401. Owner worktree: a11. Date: 2026-09-11.

This preregistration is sealed before any G401 scored comparison or policy
measurement. This preparation run will not run a census, decode, shadow,
inference, rating, scoring, pod job, deploy, restart, flag change, registry
write, or daemon edit.

## Fixed protocol

- Re-run the binding premise condition: resolve the current daemon cwd and
  `/workspace/data/tracking/track_daemon_ledger.jsonl`; hash `build_command`
  and its callers; verify the active `--frames 3000` cap; capture the exact
  feeder selector bytes and activation UTC for 270 -> 312 -> 301 -> 311 -> 300
  with probe bar 720.
- Freeze a completed post-preference window at its census UTC. Enumerate every
  terminal attempt and select the earliest terminal ORIGINAL attempt per
  section. Preserve repeats, failures, ABSENT, malformed PTS, EOF, and UNKNOWN
  independently.
- Define available span from decoded native PTS. Define cap-limited span from
  the recorded start, cap, and source-frame order. Define loss as
  `max(0, min(100 s, available span) - cap-limited span)`.
- Primary policy metric: `count(loss > 5 s due to cap) / all window sections`.
  Zero-loss sufficiency requires zero UNKNOWN sections. Any UNKNOWN prevents a
  sufficiency verdict. The target is 100 s and the decision is 5 s; neither
  value may change.
- Independently sort retained native 59-61 fps sections by competition, game,
  section, and digest. Select 30 with `floor(j*(N-1)/29+0.5)` for j=0..29,
  without replacement or substitution. Require every selected source to have
  raw-byte and full-PTS identity before either mechanics arm.
- Mechanics arm A uses cap 3000. Arm B uses
  `ceil(100 * validated_native_fps)`. Preserve source order, start index, and
  the existing stride algorithm. Invalid or variable-rate PTS uses legacy 3000
  with `cap_basis=UNKNOWN`; never default optimistically to 30 fps.
- Arm B passes its fixed mechanics check only when its processed time extent
  reaches 100 s within one native frame interval for all 30 valid 60 fps
  sources. Record last admitted PTS, first excluded PTS, source count, and
  actual shadow read count for both caps.
- Construct-only argv fixtures cover 30, 29.97, 59.94, 60, unknown,
  variable-rate, and short-source cases. The proposed path is additive and
  retains existing cap/count aliases and all fixed daemon semantics.

## Fixed reporting language

This work measures duration mechanics only. It does not establish tracking
quality, production throughput, runtime resource behavior, or a deployment
decision. Every evidence memo ends with an explicit NOT VERIFIED list.

## Fixed comparison convention

No loss comparison is run in this preparation. If a later comparison reports a
delta, its sign convention is: improvement equals baseline loss minus candidate
loss; positive means candidate better.
SEAL sha256 35133397a0d6ef07f71ebbb05b4248867acf498889056cf48e34b48bf12cd568
