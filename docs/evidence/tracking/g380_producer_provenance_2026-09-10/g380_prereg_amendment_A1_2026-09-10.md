# G380 preregistration amendment A1 -- the sampling frame, 2026-09-11

The sealed preregistration (`prereg.md`, SEAL
d04ee2c4873c621944a2596131d0603dd32d9e3533fbe0fc41274d6e76471c95) is NOT edited by this
amendment and remains binding. This file amends ONE thing: how the >= 30 preserved sections
are drawn. It is written and sealed BEFORE the amended sampling is used to produce any
number, and it moves NO bar.

## Why

The first paired replay drew a sealed NAME list: an even sample of 30 sections over the 45
`.mp4` files present in `/workspace/data/footage_corpus` at 2026-09-11T00:05Z, corpus listing
sha256 `6890c37e648188ccd1a7dcf56500f245afd0cce576537c2c42e94ccdd7b1422c`, written to
`plan.csv`. That run finished with 6 OK pairs, 2 ARM_FAILED and 22 SOURCE_GONE: the pod quota
guard (`/workspace/quota_guard.sh`, HIGH 35000 MB, LOW 32000 MB, MIN_AGE_MIN 90) deleted the
named sources before their pair could run, and the corpus fell from 45 files to 20 during the
run. The loss is recorded per section in `replay_pairs_plan_sealed.csv` and is evidence, not
an error to be hidden. A name list sealed against a rotating queue cannot reach n = 30 here.

The 2 ARM_FAILED rows are a separate, real defect found by this row and are retried under this
amendment: a `game_id` beginning with `-` (e.g. `-Oa_BpdVT64_s1372`) is read as a flag by
`scripts/run_clip.py`'s argument parser, so the run exits in about 6 seconds having produced
nothing. `scripts/platformkit/track_daemon.py:build_command` passes `"--game-id", game_id` in
exactly that form, so the LIVE route cannot track any section whose video id begins with a
hyphen. This lane changes no production file; it records the finding and uses the `=` form in
its own replay driver.

## The amended sampling rule

Sections are drawn from the corpus AS IT ROTATES instead of from a frozen name list:

1. A top-up step lists `/workspace/data/footage_corpus/*.mp4`, records the listing's sha256
   and file count, and copies sections not already held or already attempted into
   `/workspace/g380_scratch/sources/`, taken in EVEN steps across the sorted listing, until
   the scratch pool holds its budget of files or `du -sm /workspace` exceeds 40800 MB.
2. Every copy is appended to `copy_manifest.csv` (copy time, listing sha256, listing count,
   name, game_id, bytes) and to `pool_plan.csv`, which is the sampling frame actually used.
3. The replay consumes the pool in copy order, runs both arms, then deletes the copy.
4. Top-up and replay alternate until 30 pairs complete or the corpus can supply no more.

Nothing else changes: the same single pinned scratch copy of `/workspace/deploy/nba-ai-system`
serves both arms, the same weights and the same `--frames 3000` cap, one GPU job at a time
with free VRAM read first, thread caps OMP/MKL/OPENBLAS = 1, sources deleted after each pair,
and the trace hook on the kept pair only so the paired seconds ratio is never inflated by it.

## Bars, restated verbatim and unmoved

Trace-label agreement 1.000000; receipt-trace agreement 1.000000; unchanged-field differences
0; paired median seconds ratio at most 1.10 on n >= 30 sections over >= 10 videos, else the
throughput clause is NOT VALIDATED; live receipt coverage 1.000 on >= 30 sections / >= 10
videos in the authorized deploy phase; missing events labelled UNKNOWN and reported, never
dropped; 30 evenly spaced source-coloured overlays including HELD and CLAMP where they occur.
No deploy occurs before an authorized ACCEPT.

SEAL sha256 903dabcb737d97860bb9fdaa094bdd8293a958e87a90c2fe10a0e661c60da282
