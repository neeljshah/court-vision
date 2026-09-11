# G380 adjudication -- 2026-09-11

Row: producer provenance (`docs/evidence/tracking/g380_producer_provenance_2026-09-10.md`).
Two codex-sol verifications REJECTED this row. The orchestrator adjudicates the clauses that
are structurally unmeetable by this row, and the finisher re-measured the one clause that was
improvable. No bar is moved by this file. Nothing is deployed.

## Verifier verdicts

Attempt 1 (`G380_VERIFY_att1_REJECT_2026-09-11.md`):

`ACCEPTANCE FAIL: receipt equality is 0/1 traced section, unchanged-column identity is 0/30,
and live coverage is unmeasured; the memo correctly labels these unverified (receipts.csv:2;
memo:25-26).`

`ACCEPTANCE FAIL: 30 even unique overlays span frames 0-2898, but none contains HELD; five
evenly spaced renders were inspected (overlays_index.csv:2-31; memo:22-23).`

Fix 1b (`G380_VERIFY_fix1b_REJECT_2026-09-11.md`):

`ACCEPTANCE RECEIPTS FAIL: reproduced equality 0/4, containment 4/4, with 2/15/10/56
receipt-only ticks; n=4 also misses the sampled n>=30 rail
(g380_producer_provenance_2026-09-10/receipts_trace.csv:2).`

`ACCEPTANCE IDENTITY FAIL: reproduced 0/30 identical legacy-field pairs, claimed 0/30
(g380_producer_provenance_2026-09-10/summary.json:57).`

`ACCEPTANCE LIVE FAIL: 60-min coverage phase not run (g380_producer_provenance_2026-09-10.md:20).`

`ACCEPTANCE EYE FAIL: 30 unique even frames span 0..2898 and include CLAMP, but no HELD; two
separate CONSTRUCT images do not satisfy the sealed live set
(g380_producer_provenance_2026-09-10.md:18).`

`CORRECTION DIFF 1: - trace set = frames with emitted rows; + trace every producer-evaluated
attempt before row filtering and require equality on >=30 sections.`

`CORRECTION DIFF 2: - nondeterministic A/B identity; + pin environment/seeds without production
behavior changes and retain 30/30 zero-difference legacy-field pairs.`

`CORRECTION DIFF 3: - construct-only HELD outside the even live set; + satisfy the sealed live
eye bar, or close G380 at limit without deployment.`

`CORRECTION DIFF 4: - live phase unrun; + run it only after steps 1-4 receive a fresh ACCEPT.`

Both verifications PASSED the premise, the label agreement (2,453/2,453 over 998 frames), the
throughput clause (median 1.017054 on 30 pairs / 20 videos against the 1.10 bar), the 10/10
CONSTRUCT branch controls, the additivity and reader survey, every B clause except B10 (cured by
amendment A2 before fix 1b), and every Q clause except the Q3/Q7 findings that A2 and the fix-1b
coast control cured.

## Orchestrator adjudication

### (i) Unchanged-column identity -- CLOSED AT LIMIT

CORRECTION DIFF 2 asks for 30/30 zero-difference legacy-field pairs after pinning environment
and seeds. Measured here: 0/30 pairs byte-identical, relative row delta between the arms median
0.076798. The A/A control ran the SAME UNPATCHED producer twice on one source under the same cap
and gave 2,811 vs 2,535 rows with different digests, relative row delta 0.098186 -- LARGER than
the patched-versus-unpatched delta. The bar asks this row to detect a difference smaller than
the route's own run-to-run noise, so it cannot be met by any measurement this row can make.

The remedy the correction names has already been measured and falsified by another row, which
is why this is a limit and not an omission. G195 (`RESULTS_LEDGER.md:207`, ACCEPT) crossed the
cuDNN tuner on/off with `cv2.setRNGSeed(1952026)` on/off over four arms and three fresh pod
processes, seeding all six unseeded OpenCV sites at once: NO arm was identical across its three
runs, and the fully pinned arm D -- tuner OFF and seeded -- still gave 1,118 / 1,108 / 1,072
player rows. G190 had already shown that turning the tuner off makes the DETECTOR bit-exact and
that torch seeds add nothing; G193 that tuner-off is insufficient for the route. The route's
residual variance is downstream of inference, and G195's orchestrator named the leading
remaining candidate as a thread race in the YOLO prefetch cache
(`unified_pipeline.py:301-311`, a non-blocking `peek()` that discards the frame index, popped at
`advanced_tracker.py:1194-1200`), dispatched as G198 and not yet measured. Both
`torch.backends.cudnn.benchmark = True` sites (`src/pipeline/unified_pipeline.py:657`,
`src/tracking/player_detection.py:79`) and the prefetch cache live in HUMAN-GATED `src/`, and
changing any of them changes production behaviour -- which CORRECTION DIFF 2 itself forbids.

The clause is therefore CLOSED AT LIMIT with the measured reason: NOT met, NOT excused, bar
unchanged at zero differences. A determinism repair of the route -- the G198 prefetch race, then
a re-run A/A to show reproducibility before any A/B identity claim -- is a NEW GAP, not a repair
this row can make.

### (ii) HELD in the live overlay set -- CLOSED AT LIMIT

The sealed eye bar (restored verbatim by amendment A2) requires 30 evenly spaced
source-coloured overlays including HELD and CLAMP. Measured: CLAMP is present; HELD is emitted
on 0 of 109,060 live rows across all 30 replayed sections and on 0 of the 998 traced frames of
the rendered section. HELD means "no branch wrote this tick", and a row is emitted only for a
tick some branch wrote, so a live HELD row is unreachable in the producer as it stands -- the
label exists for the case where a slot has been seen before but this tick has no write, which
the emission path never reaches. The clause is CLOSED AT LIMIT on live output with that
measured reason. Two CONSTRUCT overlays rendered from the forced coast scene are supplied
BESIDE the 30 even live overlays, stamped `CONSTRUCT (not live output)`, and replace none of
them; the verifier is right that they do not satisfy the sealed live set, and this file does not
claim they do. CORRECTION DIFF 3 offers exactly this disposition: "satisfy the sealed live eye
bar, or close G380 at limit without deployment".

### (iii) The 60-minute live coverage phase -- NOT RUN, deferred

Live receipt coverage 1.000 on >= 30 sections from >= 10 videos is a DEPLOY-PHASE bar: it needs
the overlay on the live route, a backup, a smoke run, ONE daemon restart and a 60-minute window.
That phase is separately authorized (the 2026-09-08 user authorization to apply PROPOSED `src`
diffs and deploy the daemon) and is governed by the G372 protocol: deploy, measure for at least
60 minutes, and watch the ledger repeat-or-duplicate row share on a 30-minute cadence against
the pre-deploy hour, reverting on the first sign of a re-claim wave. It is NOT RUN here and NOT
CLAIMED, in agreement with CORRECTION DIFF 4, which places it after a fresh ACCEPT of the code.
The orchestrator schedules it after this row lands. The G372 carry-over it must clear is already
discharged in code and tested: the bind is stateless and idempotent, holds no `_PENDING` state,
caches an absolute weight digest, and degrades to an empty bind on any failure.

### (iv) Receipt-versus-trace equality -- RE-MEASURED under amendment A3, bar MET

This is the one clause CORRECTION DIFF 1 showed to be improvable rather than structural, and it
was re-measured. Fix 1a and 1b built the trace's tick set from the hook's per-EMITTED-ROW
records, so a tick the producer evaluated without emitting a row could only ever be
receipt-only: equality 0/4 with containment 4/4 and 0 trace-only ticks in EVERY section was the
signature of a wrongly defined set, not of a broken receipt. Amendment A3 (sealed ALONE at
`b608fbe5b`, seal `f9286816d553d537fb8cf8126d12853b3eeb61cfce3f057ea3702c5fcd885260`) fixed the
definition BEFORE the measurement: the PROPOSED diff now calls `note_attempt` at the producer's
evaluated-attempt entry, before the duplicate suppression that filters that tick's rows, and the
independent import-time hook wraps that call and logs `A,<tick>`.

MEASURED, patched arm alone, on the 30 replay objects G386 retained off-pod (`a3_sources.csv`,
each sha256-verified on arrival, `receipts_trace_a3.csv`): 30 of 30 sections ran, over 21
distinct videos, and receipt-versus-trace set EQUALITY is 30 / 30 = 1.000000, containment 30 /
30, with 0 receipt-only and 0 trace-only ticks across 21,177 evaluated ticks. The sealed bar is
1.000000 on n >= 30 / >= 10 videos: MET, and not moved to fit -- the measurement moved to the
set the bar always meant. The diagnosis is confirmed rather than assumed: in 14 of the 30
sections the emitting-frame count is BELOW the evaluated-tick count (20,900 emitting frames
against 21,177 evaluated ticks, 277 ticks that evaluated and emitted no player row), and every
one of those would have been scored a false receipt-only tick under the fix-1b definition.
The earlier n=4 rows stay in the package, superseded and labelled, not deleted.

## Landing status

PARTIAL (adjudicated). The code is complete, additive and tested; the premise, labels,
controls, throughput, additivity, reader survey and now attempt-level receipt equality (30/30)
are verified; identity and the live HELD overlay are CLOSED AT LIMIT with measured reasons; the
live coverage phase is deferred to the authorized deploy phase, which the orchestrator schedules
after this row lands. No threshold moved, nothing was deployed, no daemon was restarted, and
no file under `src/`, `kernel/`, `api/`, `intel/`, `scripts/run_clip.py` or
`scripts/platformkit/track_daemon.py` was edited in any landing tree.
