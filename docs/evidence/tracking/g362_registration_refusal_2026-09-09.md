VERDICT: PARTIAL -- sealed known-H recovery bar (<= 1.0 px) NOT MET: 1.6516 px
# G362 registration that can REFUSE -- finisher phase (gate run, row stops before broadcast)
Spec: docs/evidence/tracking/specs/G362_spec.md (VERSION 2026-09-09). Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md (A/B; Q1, Q3, Q6, Q7, Q8; A9, A11, B11).
Prereg: g362_registration_refusal_2026-09-09/g362_prereg_2026-09-09.md, SEAL sha256 316b3466fb249cb88b6a78c76d510ded7b62353778e992910af4a2780103f865 (last line). Builder: claude-opus on the pod (codex terra unauthenticated). Finisher: claude-sonnet on the pod, worktree /workspace/wt/a4.

## Corrected facts (prereg sections 0-1, sealed; the row never reached them, carried here unchanged)
G352 is NOT landed on master; its memo/metrics/five modules exist only as four unlanded commits in sibling worktree a6 (tip fd8700d3). BEFORE_NEGATIVES = 84 SCORED ARM CELLS (ARM_A 15 frames x 4 sections + ARM_B 6 frames x 4 sections), not 84 distinct frames, and not G334's own different "84" (its ARM_A valid-H count over 239 evaluation frames). BEFORE_POSITIVES = 0 of 6 is G334's landed result; G352 contributes 0 of 4, all four sections having no court.

## Known-H gate (prereg section 2, spec step 2) -- command run this session
`python3 -m scripts.platformkit.tracking.g362_controls known-h --out <EVID>` -> stdout `KNOWN_H VALID gap=1.6516 px bar=1.0 px -> PARTIAL`, exit 1.
| geometry | source | gap px | state | fwd median px | inv median px | n_strokes | held-out strokes | held-out pts | hypotheses |
|---|---|---|---|---|---|---|---|---|---|
| sealed SYNTH_QUAD | finisher, this session | 1.6516 | VALID | 5.874 | 4.6486 | 48 | 13 | 508 | 115976 |
| 3 further view geometries | builder phase, not re-run this session | 1.3326 / 1.7814 / 1.8884 | -- | -- | -- | -- | -- | -- | -- |
Bar 1.0 px. This run reproduces the builder's number exactly (deterministic, prereg section 11: no random draw in the search). Non-zero exit STOPS the row per spec step 2 and prereg section 9: premise, negatives and positives are NOT run; no section is fetched; the bar is not lowered.

## Diagnostic (read-only, <= 30 min; isolates the mechanism; never the gate result; not committed to the sealed path)
The winning H comes from intersecting 2 fitted W-family + 2 fitted L-family image lines (`enumerate_hypotheses`, g334_court_line_calibration.py:157) via one 4-point `cv2.getPerspectiveTransform`; no least-squares refinement over the other detected supports follows. Isolating run: replace the DETECTED, `cv2.fitLine`-fitted lines with EXACT lines (project the true court lines y=0/47 and x=0/50 through the known H_true -- no LSD, no grouping), run the identical corner-intersect + 4-point solve, reproject the 398-point template against H_true. Result: `reprojection_median_px=0.000000` (median Euclidean pixel distance, sign-free per `synth.reprojection_median`, consistent with prereg section 8's non-negative-pixel convention). This is exact, as expected of a 4-point projective solve fed data consistent with H_true, and it rules out the corner-solve/no-refinement mechanism, the gate-inside-search rule, and RANSAC (none exists here -- the search is a complete enumeration, contract B11) as the floor's source. The floor is therefore upstream: noise in the LSD-detected segment grouping and `cv2.fitLine` (DIST_L2) fit (`domains/basketball/tracking/line_calibration.py` `candidate_line_group_details`, `group_offset_px=18.0`), amplified by extrapolation across the 398-point template from a minimal 4-corner fit with no joint refinement over the other detected supports -- i.e. MISSING SUB-PIXEL REFINEMENT, not an integer-pixel detector artifact (LSD returns floats) and not the family-binning (already centred/wrapped, prereg section 3).

## Vocabulary (Q6) -- automated scan, required
`python3 -m scripts.platformkit.tracking.g334_seal scan` over 8 files (prereg, 4 modules, test, this memo, known_h.json): 7 files hits=0. This memo: 1 hit, `bare-integer` on the SHA-256 line for g362_synth.py -- a two-digit substring inside that hex digest (right after its leading "baf") coincidentally matches the Q6 bare-integer filter; it is a hash-digest coincidence, not a calibration or retracted-figure claim of any kind, and the hash is quoted verbatim rather than reformatted to dodge the scanner. SCAN_TOTAL_HITS 1 over 8 files, recorded honestly.

## Seal verification
`python3 -m scripts.platformkit.tracking.g334_seal verify g362_prereg_2026-09-09.md` -> SEAL HOLDS g362_prereg_2026-09-09.md

## SHA-256 (every artifact this phase wrote or read)
7d5700d3e542cb4207c65951b005ab1304938371a10747bd44b7cd67d5bd3d62 g362_prereg_2026-09-09.md
a3289dd79d57aced654683dd307060f8a9b12262f04e4f83485672e754ccb9e1 known_h.json
37e066086fb288d95b8ea9548d6b7ae6796702368d729ef32a373ed1be12db78 g362_strokes.py
bb02d8fa693304ca8f80d61fb5bb1efea915ea8a8701da9788d639e548871ee1 g362_fit_validate.py
44e040a70d0214738b5455d98b9104e5c63655f61eecf8dd6086b56a43d8a3c8 g362_controls.py
baf54c5ab32d4d336b8ea691de2e1373de05347d08e9af99bdb08adc321f903e g362_synth.py
8a7b1856025c82cca2c052a94e8b4f83dc61744a9daa2450ef811477f9c52f80 test_g362_registration_refusal.py

## TEST
`python3 -m pytest tests/platformkit/test_g362_registration_refusal.py -q -p no:cacheprovider` -> 14 passed in 11.83s. `tests/platformkit/test_loc_rail_scope.py` -> 1 passed in 0.73s. No full pytest was run.

## Wall time
Finisher session 2026-09-09 approx 19:02-19:12 UTC on the pod, approx 10 minutes: two test files, the known-H gate, the diagnostic, the seal scan and verify.

## NOT VERIFIED
Everything broadcast-related: premise, negatives and positives were never run (gate stop); `metrics.csv`, `negative_decisions.csv`, `residuals.csv`, `H.json`, `summary.json` do not exist. The 84 archived negative cells' pixels (not opened, recoverability unknown). Any accuracy claim of any kind (no ground-truth court coordinates exist or were created; every quantity here is refusal/self-consistency behaviour on a synthetic fixture). The RAW control's acceptance rate and the historical/fresh negative split (both unrun). No `src/`, `kernel/`, `api/` or `intel/` file was touched; no flag was flipped; nothing under `data/`, `data/registry/`, the register or the results ledger was read for output.

## SUCCESSOR
Fitter precision on a known H (<= 1 px) is a prerequisite row; allocate before any broadcast registration attempt.
agent: FINISHED, PARTIAL
