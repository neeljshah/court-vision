GAP G382 | sport basketball | worktree a20 | log cx_g382_court_stroke_specificity
**RANK 1 - COURT-SPECIFIC STROKE EXTRACTION AUDIT. Landed G379 found off-court supports and no accepted broadcast geometry. Input docs/evidence/tracking/g379_broadcast_geometry_2026-09-10/summary.json SHA-256 a61b9190343cb6a5303545d355e3670a9738a7e3f7b02d28b6fabd114a0fe4cb; stroke_split.csv SHA-256 f4085ed7ee6128929358de827fcfc733bae32ecf005e727d597fb6c7341916ea. Measure the extractor before spending another fitter-hour.**
**WHERE THIS ROW RUNS:** PC native reference rating; pod CPU extraction on preserved pixels, no fitter or GPU. Budget: preparation 30 min, reference 100, extraction/receipt 50.
**PREMISE (step 0, BINDING before-condition):** reproduce G379's 0/6 and 0/352 from the entire summary/refusal set; check the register for an existing stroke-specificity measurement. Already measured -> PREMISE FALSE with its receipt.
Before dispatch, census source availability and actual frame dimensions across the whole candidate manifest; if preserved native pixels cannot supply the sealed sample, report NOT VALIDATED without fitting or waiting for the daemon.
METHOD (sealed before extraction or rating):
1. Select 12 sections from >=6 video IDs evenly across competition/video/time ordering; five strictly interior even ticks each = 60 unique native frames. Use G386 receipts; preserve all draw failures, no replacements after rating.
2. Two blind raters independently trace visible painted straight court markings, assigning physical marking IDs and polygons on full native frames without extractor output. Separately mask stands, LED, score bug, other and unreadable regions.
3. Claude adjudicates disagreements with source pixels only, before extraction results are revealed. Archive both originals and final masks; report disagreement and unresolved regions, without treating rater agreement as truth.
4. Import frozen g362_strokes.extract_strokes at its 720p working scale twice in separate processes. Map reference masks with the exact resize transform; score ALL emitted whole strokes and their fixed 6 px supports, not a convenient subset.
5. Define stroke ON_MARKING when >=80 pct of its supports fall within a painted polygon dilated by 2 px at 720p; UNKNOWN support never contributes to that numerator. Report continuous support overlap beside this proposed descriptive cut.
6. Report on-marking strokes/all strokes; painted supports/all supports; per-frame shares and macro mean over frames with strokes; NO_STROKES/planned frames separately. Attribute remaining supports across the five non-marking labels.
7. Export marking-only observed strokes without splitting a physical marking; retain empty frames and families/lengths. This is an oracle diagnostic input for G383, not an automated extractor or training confirmation.
ACCEPTANCE RULE:
| field | binding value |
|---|---|
| metric | Two specificity shares from step 6, category counts, empty-frame share, reference completeness and process-repeat identity. |
| before | G379 eye evidence only; quantitative painted-marking specificity is NOT MEASURED. |
| bar | All 60 planned frames accounted for; >=30 decoded/rated frames; every emitted stroke classified including UNKNOWN; both extraction runs identical; no fitting. No minimum purity is required to accept an honest audit. |
| n | 60 planned frames / 12 sections / >=6 videos; all extracted strokes enumerated. Frames are sampling units; strokes are nested, not independent trials. |
| eye check | 30 frames evenly spaced over all 60, showing native pixels, reference polygons and every stroke; missing frames receive explicit cards. |
| must not move | G362/G365/G371/G374 code, constants and threshold 0.30; all producer fields, weights, flags and historical evidence. |
| verdict | DONE for complete reproducible audit; PARTIAL for missing/ambiguous evidence; PREMISE FALSE if already measured. No registration claim. |
EVIDENCE: docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10.md and matching directory containing frames.csv, masks/, ratings.csv, adjudication.csv, strokes.csv, support_labels.csv, marking_only.json, repeats.json, summary.json, renders/ and common receipts.
TEST: tests/platformkit/test_g382_court_stroke_specificity.py alone: transform roundtrip, UNKNOWN in denominator, no-stroke frames retained, complete physical marking identity and independent-process repeat receipt.
VERSION 2026-09-10 - proposed; protocol must be sealed before scoring.


ORCHESTRATOR FOOTER (binding, 2026-09-10 night): codex terra PREPARES (prereg sealed alone as its OWN commit, `SEAL sha256 <hex>` over every byte above the seal line); a Claude finisher MEASURES; codex-sol VERIFIES; `src/`, `kernel/`, `api/`, `intel/` READ only (PROPOSED diffs only); never write `data/registry/`, never flip a flag, never touch the register; **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** as the memo; every new file <= 300 lines; vocabulary follows contract Q6 with an automated scan (patterns built from character codes); n >= 30 with even sampling; ASCII stdout; **NEVER PARK.** Astra source: docs/research/astra_night_review_2026-09-10.md (local-only).
