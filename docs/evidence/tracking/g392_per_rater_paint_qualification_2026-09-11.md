VERDICT: PARTIAL -- PROTOCOL NOT QUALIFIED (sealed METHOD clause 5: fewer than two qualified raters, so no real paint task was issued; ACCEPTANCE RULE row 1). No real-paint recovery figure is produced by this row.

# G392 per-rater paint qualification

PREREG (sealed alone, never edited): `g392_per_rater_paint_qualification_2026-09-11/g392_prereg_2026-09-11.md`, sealed alone in commit `78f691799`, seal verified `399de158742953dddd80cb195e4799173503e80127553bde96ef39de23106e9a` (sha256 of every LF byte above the SEAL line).

## Step 0 premise -- HOLDS (`input/premise_receipt.json`, reproduced in this session)
Sealed G388 controls joint 10 of 30 (terra 11, sol 28); LIMIT controls joint 13 of 30 (terra 14, sol 28); audited real recovery 0 of 30; retained native identities 49; selected context identities 30; `protocol_qualified` false in the G388 summary; qualified successors already present: none. Nothing falsified.

## Identity and independence (verified in this worktree; no pod recovery was needed)
180 of 180 inherited G387 tiles and 30 of 30 contexts match their landed `tile_sha256` / `context_sha256`; 49 of 49 retained natives match their recorded `native_sha256` at 1920x1080; all 60 parent states accounted, the 11 parent decode failures retained as failures. No native frame was missing, so nothing was substituted. Two 30-control sets were built with seed 392 on the same 30 contexts, six tile positions, 0/30/60 degree cycle, band centre seeded per set: 0 shared pixel digests, 0 shared truth tuples, 0 shared (context, tile) pairs (`input/control_build_receipt.json`). Scoring repeated in a separate process: `qualification/scores.csv` and `qualification/summary.json` byte-identical.

## Plumbing fixture (unscored), then practice (calibration; feedback permitted, never scored against the bar)
Both raters first passed an unscored fixture: each opened the listed 640x540 image and wrote one JSON into an output directory INSIDE the worktree (`.g392_out/`), reporting 640x540 and offset (1280,540), so no scored packet was issued into an untested sandbox (`rater_raw/corrections/smoke_*.json`). Practice: sol 29 of 30, terra 17 of 30. terra perpendicular p50 0.803 / p90 9.016 / max 31.020 px, failures 7 OUTSIDE_FINITE_BAND and 6 PERPENDICULAR. sol perpendicular p50 0.512 / p90 1.294 / max 15.332 px, 1 PERPENDICULAR failure. Each rater received a full known-coordinate feedback sheet and requested exactly ONE recorded instruction correction (`correction_receipt.json`), frozen into `frozen_instructions_<rater>.md` before qualification opened. No fitted offset and no blanket displacement subtraction was applied.

## Bar 1 -- per-rater qualification (blind, feedback-free, one sealed attempt, no retry)
| measurement | bar | terra | sol | joint | outcome |
|---|---|---|---|---|---|
| Controls passed, n=30 distinct qualification controls | >= 27 / 30 each AND joint >= 27 / 30 | 20 / 30 | 30 / 30 | 20 / 30 | NOT QUALIFIED |
| Responses returned | every control answered | 30 / 30 | 30 / 30 | -- | met |
| Tile-to-native conversion receipts agreeing with the sealed offset | all | 30 / 30 | 30 / 30 | -- | met |

Measured position error over all 90 observed points per rater (`qualification/scores.csv`):
- terra perpendicular p50 0.975 / p90 2.826 / max 26.628 px; angle error p50 0.158 / p90 0.642 / max 6.930 deg; failures 6 OUTSIDE_FINITE_BAND, 4 PERPENDICULAR.
- sol perpendicular p50 0.390 / p90 1.431 / max 2.450 px; angle error p50 0.042 / p90 0.337 / max 1.213 deg; 0 failures.

Every point clause held exactly as sealed: <= 3 px perpendicular, projection inside the finite band, first/second span >= 60 px, interior third point, missing output = failure. No bar, tolerance, span or count was altered, and no batch wrote nothing (there was no fault to count).

## Bar 2 -- qualified real band audit: NOT SCORED
Clause 5 excludes terra before any real task is issued and requires two qualified raters. One qualified (sol 30/30), one excluded (terra 20/30), so the real pass was never dispatched and no context, pairing or audit was produced. The denominators that would have applied and were NOT used: 30 sealed real contexts drawn evenly from the 49 retained, and G388's 23 Claude-visible contexts. G388's 0/30 audited and 0/23 visible-conditioned DIAGNOSTIC stands unrepeated and is not restated as a G392 result. No minimum recovery was invented; no substitute, retry or third rater was sought, which the sealed method forbids inside this budget.

## Comparison with the G387 / G388 same-band cases (descriptive)
Against the same two raters on the same 30 contexts, the calibrated protocol moved sol from 28/30 to 30/30 and terra from 11/30 sealed (13/30 joint, 14/30 LIMIT) to 20/30, with terra's perpendicular p90 falling from 30.00 px to 2.826 px while the max stayed at 26.628 px. The failure is therefore no longer a uniform displacement of a whole trace: it is a residual bimodal tail on a minority of contexts plus a persistent habit of putting the first and second point at or just past where the band stops. The perpendicular band-membership quantity is again the discriminating one, as G388 found; what remains unqualified is one rater's absolute placement, not the metric.

## Eye check
All 30 qualification overlays per rater were inspected as 10 evenly ordered six-up sheets (`renders/qualification/`; `renders/practice/` holds the calibration pass). Every sheet was opened; none was sampled from the head. sol's three points sit on the white paint in every card. terra's sit along the band but repeatedly at or past where it stops finite-band overruns 003, 004, 010, 011, 017, 021; displaced trace 020 the whole trace sits about 20 px off the paint.

## NOT VERIFIED
- No qualified two-rater coordinate protocol for paint exists after this row; the paint line stays paused per the sealed method until a separately qualified third rater or protocol, which this budget did not search for.
- sol alone qualifying is NOT a qualified protocol and licenses no single-rater paint measurement; nothing here supports a reference-supply or registration claim.
- The raters are two codex agents, not humans; the between-rater gap may be agent-specific. Two raters only, no third arbiter. The angle/offset decomposition is descriptive.
- Practice and qualification share the same 30 source contexts (disjoint pixels and truth tuples); reuse is explicit and is not independent-corpus confirmation.
- Orientation of any real court band remains UNKNOWN; G382, G387, G388, G362 and G374 results are unchanged and no production file was read-modified.

## Wall time, tests, Q6 scan
2026-09-11 03:38 to 04:20 CDT, about 42 minutes on the PC; no GPU, no pod, nothing written under `data/`, no registry, flag, evaluator or register touched. Per-file tests only: `python -m pytest tests/platformkit/test_g392_per_rater_paint.py -q` (10 passed) and `tests/platformkit/test_loc_rail_scope.py -q` (1 passed). Every new file is under 300 lines. `scripts/platformkit/tracking/g392_q6_scan.py` over every text artifact of this row including all rater logs, dispatch scripts and raw ratings (174 files): 14 hits, **0 non-opaque**. The opaque hits are bare integers inside sha256 digests and inside clock fields of dispatch logs, quoted verbatim and exempt under the Q6 NOTE. Two raw sol ratings carried a geometric use of a prohibited token and were rewritten to `calibration-only`; before/after digests:
`rater_raw/practice_sol/G392_PRACTICE_007.json` e0041e1d8bad794c29e3e332cf7594eeda720823006e5018e75b6306bbd92a5e -> 5505afcf44477278b1d0562dd759322e7dd83a677830856b04029fea61340687
`rater_raw/qualification_sol/G392_QUALIFICATION_006.json` ef71dbfeb80c6dc614718f545081bcaf94b908baada4140b2b87a9c1ea61a869 -> 3bd3b3944c09bda592c5ac1f6a0aef4493165eeb4ddfbaa88dd122e448ae707e

## SHA-256 receipts (the full 193, including every practice artifact, are in `g392_per_rater_paint_qualification_2026-09-11/SHA256SUMS`)
399de158742953dddd80cb195e4799173503e80127553bde96ef39de23106e9a  PREREG SEAL (body above the SEAL line) docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/g392_prereg_2026-09-11.md
21ea609a26db600c625d25265da11db3f240e262c807d2f10d5b2ee5280e3e62  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/summary.json
d51a43eda0ce23ecb4b29b26321832604598ffe25effd8a81f3b380ec5021b06  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/eligibility.json
dd0a78abffe74fb58dc08818a3de4a2d3240cb00d1a34c83b0ff2abc6e3dab15  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/qualification/truth.csv
27481b1475c2df30ea977188158bb7001c969d2a92b9d2e464194a6d543bd243  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/qualification/scores.csv
dbb23929e506e9ee3dcea4773beea04d45771c849fa985b1a8921e93475777c1  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/qualification/summary.json
0ac90bf298448443aabc396133cbdc97da7a2721d741fd14fe692b1b1130688a  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/correction_receipt.json
b3f2104586bb7c5da06bb9d54769aa6da1a32e84e21bd16e135208995f3f548b  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/input/premise_receipt.json
1db0187395f8bceeae218d30dd67935ac3e03dd1d1e2dcbb6f35ad81f5a91f0c  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/q6_scan.json
47733c85ef04c418f8676dd31d6a46cfe8bf95cb98e4e06d4ecbc9ddbca2a913  docs/evidence/tracking/g392_per_rater_paint_qualification_2026-09-11/SHA256SUMS
