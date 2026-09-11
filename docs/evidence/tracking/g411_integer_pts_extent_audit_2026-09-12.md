VERDICT: DONE (DIAGNOSTIC, PROPOSED ONLY) - exact integer-PTS recomputation on the same 30 G401 timelines passes the SAME inherited bar 30/30 on both endpoint definitions; G408's four marginal misses are a six-decimal serialization artifact, not a real extent miss.
What it means for the G401 decision: the endpoint-definition choice G408 raised is not forced by precision - under exact rationals both the first-excluded and the last-admitted definitions clear the unmoved bar on all 30 sources, so the user can decide on mechanics grounds alone.

# G411 integer PTS / time-base extent audit

Preregistration `docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/prereg.md`, sealed alone at f207c8360, seal f7d5b33dc3ec131b744244f97597a9ffc950e3af99b6b893733d679a9414923b. Preparation (codex terra) sealed the protocol; this memo reports the measurement. No amendment was needed.

## PREMISE step 0 - reproduced from the archived unrounded values

Replaying the archived decimal schedules (`g408/g401_frame_pts/`, 30 files) through the sealed mechanics reproduces G408 exactly: temporal containment 30/30; arm C first-excluded extent within the inherited bar 30/30; arm C under the earlier last-admitted computation 26/30; and the four excesses are each 0.000000333333 s on the four 60/1 sources (draw_j 0, 1, 3, 4). All 30 stored `first_boundary_extent_s` values re-derive to the byte-identical six-decimal render. Premise holds; no reconciliation was required.

## Method actually run

Two independent readers took integer PTS from the retained bytes at `C:/Users/neelj/g401_receiver/sources` (rehashed; 30/30 match `draw.csv`): (1) `ffprobe -show_frames` integer `pts` plus the stream `time_base`, and (2) a stdlib MP4 `stbl` parser reading `mdhd` timescale, `stts`, `ctts` and `elst` straight from the container bytes with no ffmpeg involvement. Both readers agree on `time_base` (1/90000 on all 30) and on the PTS multiset for all 30 sources. ffprobe emits a few frames in locally swapped output order on 13 sources; the archived G401/G408 stream is presentation-sorted, so the replay binds to the sorted order and all 1305 swaps are retained in `anomalies.csv`. No float seconds field was read from any container and no integer was manufactured from a rounded seconds column.

Every endpoint is an exact `fractions.Fraction`. The bar is byte-identical to the inherited one - `abs(first_boundary_extent_s - 100) <= 1/validated_fps`, using the archived `validated_fps` decimal as an exact rational (60.0 and 59.94005994005994), one native interval, no rounding, no added tolerance, no epsilon, no endpoint switch.

## Result

| quantity | archived decimal | exact rational |
|---|---|---|
| arm C temporal containment | 30/30 | 30/30 |
| arm C first-excluded extent within bar | 30/30 | 30/30 |
| arm C last-admitted extent within bar | 26/30 | 30/30 |
| decimal stream re-derived from integers | - | 30/30 sources, 0 mismatching frames |

No timeline terminated UNKNOWN under either representation. Eight rows in `endpoint_comparison.csv` change bar outcome between the two representations (`marginal_cases.csv`): the four 60/1 sources under the last-admitted definition, in arms B and C. In each, the exact extent is 5999/60 s, the bar is exactly 1/60 s, and `abs(5999/60 - 100)` equals 1/60 exactly - on the bar, so it passes. The six-decimal render 99.983333 sits 1/3000000 s (0.000000333333 s) further from 100 than the true value, which is the entire excess G408 recorded. All eight changes are flagged `serialization_explains_change=True`; no other row changes outcome, and no genuine missing-frame extent failure was converted into a pass.

The historical G408 verdict is NOT altered. It stands as recorded (arm A 0/30, arm B 29/30, arm C 30/30 first-excluded, 26/30 last-admitted); the rational result is stated beside it, in this row's own tables.
Fix 1b (2026-09-12, codex-sol REJECT x1, B2): `paired_stops.csv` now carries the seven G408 parent columns (last_admitted_pts, first_excluded_pts, span_s, endpoint_gap_s, last_admitted_gap_s, overshoot_s, native_frame_interval_s) as same-semantics seconds aliases rendered from the exact rationals (12 places; parent: float seconds; span_s = last_admitted_extent_s, endpoint_gap_s = last_admitted_gap_s = 100 - span_s, overshoot_s = first_boundary_extent_s - 100, native_frame_interval_s = the exact 1/fps); the G408 header is asserted to be a subset of the G411 header; the pre-fix tables sit under `pre_fix1b/`; no measured value, bar or verdict moved (only the paired_stops.csv digest changed).
Fix 1c (2026-09-12, codex-sol REJECT x2, B2): restored parent `read_frames`, absolute `deadline_s`, and last-admitted `contained`; retained G411 meanings as `retained_stream_frames`, `deadline_from_origin_s`, and `boundary_reached`. No exact endpoint value, bar, 30/30 or 26/30 count, or eight marginal cases moved; `parent_field_audit.csv` records all 90 keyed rows.
Fix 1d (2026-09-12, codex-sol REJECT x3, B2): UNKNOWN rows restore retained parent state after admissions, including read/admitted, deadline, last PTS, span, gap and contained; `unknown_reason` is the parent string and `unknown_reason_g411` is the alias.
The fixture compares parent and candidate values over missing, backwards and EOF-short timelines; `pre_fix1d/` retains the prior tables. No real row changed.
Fix 1e (2026-09-12, codex-sol REJECT x4, B2): an empty schedule now preserves parent `EOF_SHORT` / `start_outside_schedule` state and blank fields; the fixture compares every parent field.
`source_receipts.csv` now adds retained ffprobe `width`; `pre_fix1e/` retains the prior receipt table. No real row, bar, count or verdict changed.
## Controls, reproduction, receipts

32 CONSTRUCT boundary cases (4 observed time-base/modal-step pairs x exact-at-deadline, one unit below, one unit above, duplicate, missing, backwards, dropped deadline neighbor, skipped-by-stride) all match hand-declared expectations. Two fresh processes regenerated every delivered table and all 30 timeline cards from delivered bytes; `repeats.json` reports identical with per-table digests, stdout digests and returncode 0. This shows table reproduction, not inference repeatability. Q6 scanned 186 text paths including the scanner, memo and `.log.txt` receipts: 0 non-opaque hits, all code-built fixtures pass; the earlier 169 / 174 figures were superseded by the fix cycles. The shared-log receipt names `docs/evidence/tracking/RESULTS_LEDGER.md`, while `ledger_rows_g411.txt` has 0 hits. Tool identity: ffprobe/ffmpeg 8.1-full_build, ffprobe binary 70872c3ffbc43d0b2c570f9837f54d6e9a832f4ca25463e9735b6a3ec0621478, ffmpeg binary d1e2a156261ecc675081943197a85f08f2868784a0af499171ede89353edad31, CPython 3.10.0. Per-file digests for every delivered artifact, with the byte-domain declaration on line 1, are in that directory's `SHA256SUMS`. Model set empty - no model, route or asset was exercised. PC only; no pod, no GPU, no producer invocation, no daemon restart, no flag change, no registry write, no `src/` edit.

## Digests
44debbad60bf179afbac12e779bbf498c2ed10371c3d6c6ba4550e93254a5550 docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/prereg.md
d06ab776e223128e1c6a8bc4a09e0427707cf2b083c67abfb1019ec0bc4d82af docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/summary.json
08e011ea8e413f5439cf81308977f584ff7f1ddbbbd2694557a152c9344930ee docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/paired_stops.csv
03ea1bb752eebff9111bd9ec9e5c24b549620cb2474a464a668d33a1400a54de docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/parent_field_audit.csv
b4165f2df87a49e0a113cc2a29463305dd7b93def9ba2e037c70df292ebf5966 docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/endpoint_comparison.csv
8bbb51a0f529753615264c442b92cf75f8f175de30c6e12626b2f062ca543f1d docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/marginal_cases.csv
29eb43f07882485dcd2a5b3b0977237717167c949f82e73a640c52059fe2a73e docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/source_receipts.csv
028f5ae26c95642bcd3738f8a3e1f1d9cadbf4a98084fa13e401bd54767fd460 docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/stream_join.csv
c068bb47a2a665dcf2f29e848f26a714ed9554a5a1dd5731f49d8086132a8f41 docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/construct_cases.csv
4ec5296c4b6e6dba05163a71244cc710041483c49eda47e03a7c3096cb3e0bf7 docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/anomalies.csv
606723a2ffb4e962342c6ee279ab376efc809283875803a7a0cc81450d139643 docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/eye_index.csv
b250f5c0abba87a6a0e7068f8b0314c9e7ac2612bcb8d1d99ac3f4c3aea54347 docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/time_bases.csv
d0a3b30e0ea545dcc9d0704ed9ba754b25ec9459f31d0e1c07344d2b4f9e6835 docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12/extraction_receipts.json
## NOT VERIFIED
- Patched-module behavior, deployment, daemon restart, flag change, registry write, producer integration. Nothing was applied anywhere.
- Runtime cost or quality past the existing 3000-frame flush boundary, and the decoder's live PTS behavior inside the producer; only retained container bytes were read.
- Inference repeatability. Only table reproduction from delivered bytes is shown.
- Any source outside the sealed 30-source G401 draw, any time base other than the 1/90000 observed here, and whether an exact-rational endpoint is the right runtime mechanic. That last one remains the existing USER G401 decision; this row supplies precision evidence only.

Delta sign convention for any later loss comparison: improvement equals baseline loss minus candidate loss; positive means candidate better.
