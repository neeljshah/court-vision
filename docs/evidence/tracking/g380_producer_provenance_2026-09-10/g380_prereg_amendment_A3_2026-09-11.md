# G380 preregistration amendment A3 -- the attempt-level trace and the 30-section draw, 2026-09-11

The sealed preregistration (`prereg.md`, SEAL
d04ee2c4873c621944a2596131d0603dd32d9e3533fbe0fc41274d6e76471c95) is NOT edited by this
amendment, and neither is A1 (SEAL
903dabcb737d97860bb9fdaa094bdd8293a958e87a90c2fe10a0e661c60da282) or A2 (SEAL
8a331a042b61f87743f08ff1bb328bedd8bac3fdebbf937f5fddd4fa726cf571). A sealed file is never
edited; a correction is a new sealed file. This amendment MOVES NO BAR. It fixes the
DEFINITION of one measured set and the DRAW of the sections it is measured on, and it is
written and sealed BEFORE it produces any number.

## Why

The codex-sol verification of fix 1b rejected on CORRECTION DIFF 1: `- trace set = frames with
emitted rows; + trace every producer-evaluated attempt before row filtering and require
equality on >=30 sections`. The finding is correct and is accepted here. Fix 1a and fix 1b
built the trace's tick set from the hook's `L` records, which fire once per EMITTED PLAYER ROW,
so a tick the producer evaluated and emitted no row for could only ever be receipt-only.
Equality measured that way tests a set the sealed bar never meant. It was also measured on 4
sections, below the sealed n >= 30 rail.

## The attempt-level trace definition

The producer's evaluated-attempt entry is the point in `src/pipeline/unified_pipeline.py` where
a decoded, gate-passing frame becomes an evaluated tick: immediately BEFORE the post-clamp
duplicate suppression that filters that tick's rows, and before `predictions.append` and
`gameplay_frames += 1`. The PROPOSED diff calls `g380_provenance.note_attempt(_g380_ticks,
frame_idx)` at exactly that point, once per evaluated attempt, and the run-end receipt is
written from `_g380_ticks` instead of from the `predictions` buffer -- which the 3000-frame
VRAM flush clears, so a run longer than that interval would otherwise lose tick ids from its
own receipt.

The independent import-time hook (`g380_trace_hook_sitecustomize.py`, on `PYTHONPATH`, never
imported by the producer) wraps `note_attempt` the moment the provenance module is first
imported and logs `A,<tick>`. The TRACE ATTEMPT SET is the set of those `A` ticks. The RECEIPT
SET is the `evaluated_tick_ids` array of `evaluated_tick_receipt.json`, which reaches the disk
through the accumulating set, the results dict and `scripts/run_clip.py`. The two are compared
as SETS: equality is exact set equality, containment is trace-subset-of-receipt, and
receipt-only and trace-only tick counts are reported per section.

## The draw

At least 30 unique sections over at least 10 distinct videos, drawn EVENLY and never as a head
slice: the 30 full replay objects G386 retained on the PC under
`data/pod_backup_2026-09-10/g386_objects/`, whose per-object sha256 is recorded in G386's
`receiver_receipts.csv`. That set is itself G386's even draw over the pod corpus, and being
held off-pod it is immune to the quota guard that cost the first paired replay 22 of its 30
sealed names. Each object is copied to `/workspace/g380_scratch/sources/` one at a time, its
sha256 is verified against the G386 receipt after the copy, the PATCHED arm alone is run on it
under the hook, and the copy is deleted before the next is sent. EVERY section drawn stays in
the denominator, including any that fails to run for any reason (SOURCE_GONE, ARM_FAILED,
preflight refusal): it is reported by name with its reason and is never dropped from the count.

## Bars, restated verbatim and unmoved

    Bars are unchanged: trace-label agreement 1.000000; receipt-trace agreement
    1.000000; unchanged-field differences 0; paired median seconds ratio at most 1.10
    on n >= 30; and live receipt coverage 1.000 on at least 30 sections from 10
    videos.

    The 30 source-coloured overlays must be evenly spaced and include HELD and CLAMP.

The receipt-trace bar stays 1.000000, on n >= 30 sections over >= 10 videos. Whatever this
amendment's measurement returns is reported as measured: an unmet bar is reported unmet --
PARTIAL, NOT VALIDATED, or CLOSED AT LIMIT with the measured reason -- and is never lowered to
fit the measurement. A1's sampling frame for the PAIRED replay and A2's restored overlay bar
both stand unaltered. No deploy occurs before an authorized ACCEPT.
SEAL sha256 f9286816d553d537fb8cf8126d12853b3eeb61cfce3f057ea3702c5fcd885260
