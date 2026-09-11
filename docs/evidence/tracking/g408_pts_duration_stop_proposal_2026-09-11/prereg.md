# G408 preregistration

## Scope

Preparation only. This artifact defines the later sealed measurement protocol. No rating, inference, scoring, producer execution, deployment, restart, flag change, register write, ledger change, or pod job is authorized in this preparation pass.

## Fixed input and time contract

The finisher must use exactly the 30 identities in G401's committed `draw.csv`, in its original even order, and no replacements. Each retained native original or complete presentation schedule must be rehashed and decoded at native resolution before measurement. The later evidence records full source path, bytes, dimensions, presentation PTS, original index, duplicate count, dropped-frame/gap count, malformed timestamp status, and EOF status.

For each section, `t0` is the first valid presented frame at the requested start. `deadline = t0 + 100.0`. The proposed rule admits only PTS strictly less than `deadline`. It checks that condition before stride or detector work, preserves stable source order for duplicate PTS, records the first crossing PTS without processing it, and never substitutes an FPS-derived deadline. Missing, nonfinite, or backwards PTS terminate `UNKNOWN`; true early EOF terminates `EOF_SHORT`; an explicit earlier frame cap terminates `FRAME_CAP`.

## Frozen comparisons and bars

Replay the legacy 3000-frame rule, the G401 FPS-count rule, and the proposed PTS rule exactly once over all 30 immutable schedules. Report every admitted index, last admitted PTS, first boundary PTS, elapsed gap/undershoot, anomaly count, and termination reason. The fixed temporal-containment bar is 30/30 complete schedules with zero processed PTS outside `[t0, deadline)` and exact stop reasons. Endpoint proximity remains descriptive; the inherited G401 fixed-count result remains unchanged.

Thirty construct schedules are exhaustive and separate from the real-source denominator: regular, duplicate, missing, backward, and boundary-gap timestamp cases crossed with endpoints before start, at start, inside, just below deadline, exact deadline, and above deadline. No held-out selection, threshold sweep, or inference is permitted.

## Proposal constraints

The proposed diff is text only. It must preserve legacy behavior without a duration argument, preserve `_VRAM_FLUSH_INTERVAL = 3000`, retain stride behavior, keep receipt fields additive with aliases, and honor explicit `--frames` as an independent earlier frame cap. With duration enabled it must omit the caller implicit 3000-frame limit and explicitly bypass the downstream default. The diff must not be applied or executed in this worktree.

## Required later records

The finisher supplies all G408-specified evidence files, two fresh saved-input table/card reproductions, a reader survey, exact base and route hashes, field-aware Q6 scan, and a final memo ending in `NOT VERIFIED`. Delta sign convention: improvement equals baseline loss minus candidate loss; positive means candidate better. No loss comparison is performed in this preparation pass.
SEAL sha256 a419e4c00ec9936bc5eefd036f822c044936a7bf82004b55bc3b276f7e90ed88
