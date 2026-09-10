VERDICT: PARTIAL -- bounded compatibility reconstruction; named clauses not verified (compatibility check only, no phase-1 claim). NOT VERIFIED.
# G367 initialisation modulo the court symmetry group -- POST-LOSS reconstruction, 2026-09-10
The original phase-1 implementation and candidate outputs were lost; these are newly reconstructed implementation results on the stated fixtures, and agreement with the surviving memo does not establish independent-data replication.
Scope, per `docs/research/astra_pod_loss_review_2026-09-10.md` sections A and B: the full phase-1 search was NOT re-run this week. This memo certifies ONLY the dependency G371 imports (`g367_search.py`), through a BOUNDED four-fixture compatibility check run ONCE with the sealed K / M. No noise sweep, no overlay render, no section fetch, no rating, no cue scoring. No code or parameter was adjusted to move any number toward the surviving memo, and the surviving orientation ratings were NOT re-rated.
Spec: `docs/evidence/tracking/specs/G367_spec.md` (VERSION 2026-09-09). Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (A2, A7, A9, A11, A12, B8, B10, B11; Q1, Q3, Q6, Q7, Q8, Q9).
Prereg `g367_init_symmetry_2026-09-09/g367_prereg_2026-09-09.md` is unchanged since 2026-09-09; its seal was verified this session over the COMMITTED bytes (`git show HEAD:<path>` into `g334_seal verify`): `SEAL HOLDS`. No new prereg was written, so no separate Q1 prereg commit was required. No bar, band, K, M, seed or threshold was moved (Q3, B10).
Machine (S1): ON THE POD, `/workspace/wt/a10`, branch track-a10, base d750eae3 plus the one disclosed fix below. CPU only; OMP / MKL / OPENBLAS / OPENCV threads = 1; `CUDA_VISIBLE_DEVICES=-1`; `nice -n 19`. Builder codex terra 2026-09-10; finisher claude-opus.
Tests, per file only, never a full pytest: `tests/platformkit/test_g367_init_symmetry.py` 6 passed; `tests/platformkit/test_loc_rail_scope.py` 1 passed (A12: no allowlisted file grew).
DISCLOSED FIX, not a tuning change: the re-prepared `g367_search.py` raised `TypeError: not enough arguments for format string` on the first geometry -- a progress `print` carrying six format specifiers and five arguments. The missing `reachability` argument was supplied. No metric, bar, seal, seed, parameter or CSV column changed; both fields were already written to `search.csv`.
## Premise (spec step 0, Q8) -- `reconstruction_2026-09-10/recovery.csv`, exit 0 = PREMISE TRUE
Labelled gap / modulo gap in image px with the attaining group element; the 4-corner winner, then that winner refined by G365 candidate B.
    geometry        G362 state   corner4 labelled / modulo (elem)      candidate B labelled / modulo (elem)
    G1_SYNTH_QUAD   VALID          1.651646 / 1.651646 (identity)        1.128714 / 1.128714 (identity)
    G2_WIDE         REFUSED      469.208252 / 1.915938 (mirror_x)      469.380798 / 1.068990 (mirror_x)
    G3_TIGHT        REFUSED        2.015967 / 2.015967 (identity)        1.116470 / 1.116470 (identity)
    G4_OFF_AXIS     REFUSED        1.800281 / 1.800281 (identity)        0.763620 / 0.763620 (identity)
PREMISE TRUE, re-measured rather than assumed: candidate B does not already recover modulo symmetry on all four. The four LABELLED candidate-B figures reproduce the landed G365 artifacts at 4 dp (G1 1.1287, G3 1.1165, G4 0.7636, G2_WIDE 469.3808), which is the spec step-0 reproduction requirement.
Against the surviving memo MODULO premise figures on G2_WIDE: corner4 1.915938 here against 1.9174 there, absolute difference 0.001462; candidate B 1.068990 here against 1.0750 there, absolute difference 0.006010. The surviving memo itself names 1.0690 as "form two" of the sealed modulo definition beside its own form one, so the reconstruction implements form two. Reported, not reconciled; no definition was altered to close the gap.
## Bounded compatibility check -- `reconstruction_2026-09-10/search.csv`, 32 refined rows; K=7, M=8, SYM_EQ_PX=2.0, AMBIG_BAND=0.005
Per geometry the reconstructed refined modulo residual sits beside the LOST run memo number with the absolute difference. This is a REPORT of agreement between two implementations on the same four synthetic fixtures. It is not a target, not a bar, and not evidence of independent-data replication.
    geometry        refined modulo (elem)   memo (lost run)   abs diff    reach / select           gate-valid
    G1_SYNTH_QUAD   1.128714 (identity)     1.1286            0.000114    NOT_REACHED/AMBIGUOUS    10463
    G2_WIDE         1.065403 (mirror_x)     1.0654            0.000003    NOT_REACHED/AMBIGUOUS    14644
    G3_TIGHT        0.715832 (identity)     0.7158            0.000032    REACHED/AMBIGUOUS        8120
    G4_OFF_AXIS     0.763620 (identity)     0.7636            0.000020    REACHED/AMBIGUOUS        15538
The four gate-valid counts equal the surviving memo counts (10463 / 14644 / 8120 / 15538) and reachability and selectability agree cell for cell on all four. The enumerated-candidate TOTAL does not agree and is named rather than reconciled: this run counts hypotheses (115976 / 107832 / 104748 / 106736) where the surviving memo counted their deduplicated symmetry images (435516 / 385659 / 386030 / 391049). That is a counter definition, not a measured quantity. Neither number was changed.
Every one of the 32 refined candidates carries `sym_class` 0 at the sealed SYM_EQ_PX = 2.0, so no distinct-class runner-up exists, the margin is empty on all four geometries and the sealed rule yields AMBIGUOUS on all four -- the same structural outcome the surviving memo recorded, and precisely the defect G371 exists to repair. `bar_all_within` false; `no_worsening_vs_candidate_b` true.
The winner here is still selected BY the modulo gap, which consults the labelled truth. It is an ORACLE upper bound on reachability and never a claim that a truth-free fitter could select it (B8). No px bar is claimed met by this memo; geometry bar 1 stands NOT MET exactly as the surviving memo recorded it.
## Orientation part -- PARTIAL BY CONSTRUCTION, quoted from the committed 2026-09-09 adjudication, NOT re-rated
Quoted from `g367_init_symmetry_2026-09-09/agreement.json` and `adjudication_note.md`, both read only and unmodified: reference label counts after adjudication left 12, right 16, unknown 26; labelled left-or-right 28; `per_class_rail_n_ge_30.meets_rail` false; raw agreement 0.888889 over the two primary raters; Cohen kappa 0.824485; adjudicated frames 6; `unadjudicated_frames` empty. The sealed floor of 60 rated frames and the `n >= 30` per-class rail (Q7) are both unmet, so bar 5 is PARTIAL by construction, and no cue precision, Wilson interval or abstention rate exists.
The blindness deviation disclosed in the committed adjudication note stands unchanged: the adjudicator saw the disputed label pair before opening those 6 sheets.
## Vocabulary scan (Q6) -- `g334_seal scan` over the prereg, the five modules, the test, this memo and the reconstruction artifacts
SCAN docs/evidence/tracking/g367_init_symmetry_2026-09-09/g367_prereg_2026-09-09.md hits=0
SCAN scripts/platformkit/tracking/g367_symmetry.py hits=0
SCAN scripts/platformkit/tracking/g367_search.py hits=0
SCAN scripts/platformkit/tracking/g367_sweep.py hits=0
SCAN scripts/platformkit/tracking/g367_orient.py hits=0
SCAN scripts/platformkit/tracking/g367_cues.py hits=0
SCAN tests/platformkit/test_g367_init_symmetry.py hits=0
SCAN docs/evidence/tracking/g367_init_symmetry_2026-09-09.md hits=0
SCAN docs/evidence/tracking/g367_init_symmetry_2026-09-09/reconstruction_2026-09-10/recovery.csv hits=0
SCAN docs/evidence/tracking/g367_init_symmetry_2026-09-09/reconstruction_2026-09-10/search.csv hits=0
SCAN docs/evidence/tracking/g367_init_symmetry_2026-09-09/reconstruction_2026-09-10/summary.json hits=0
SCAN_TOTAL_HITS 0 over 11 files
## SHA-256 (first 16 hex) of every module exercised (A11) and of every artifact written
    g367_symmetry.py 1cd388b792364822   g367_search.py 1f06bd9fbd036fec   g367_sweep.py 370d167c0f108024
    g367_orient.py 185c1749fa9482c4     g367_cues.py 1431a4ee0fce7079     test_g367_init_symmetry.py d405791f2abb5b8e
    recovery.csv 1392a11b8e841487       search.csv 9ef1ac0681552fcf       summary.json 912ee59f72ae16e1
    g367_premise.json 536710c905bfc17c  g367_search.json e3866835d3f58358
Wall time on the pod, CPU only, from printed UTC stamps: premise 15:38:27 to 15:39:08, 41 s; bounded search 15:41:11 to 15:43:51, 2 min 40 s; measured span 5 min 24 s. No GPU, no daemon, no feeder, no deploy tree and no MAIN checkout was touched, and `data/` was neither read nor written by this run.
## NOT VERIFIED
Everything the sentence at the top disclaims. This is not a replication of the lost phase-1 measurement, and the numeric agreement above cannot distinguish a faithfully reconstructed route from two implementations sharing one systematic error, because the original code and candidates no longer exist to diff against.
The noise sweep, the exact-control-under-sweep clause, the eight synthetic overlays and the eye check: NOT RUN in this session, so spec bars 2 and 4 are unmeasured here and no surviving-memo value for them is quoted anywhere above.
The whole orientation and cue result: no frame was rated or re-rated here, no cue was called, no precision, interval or per-class count was computed, and nothing is wired -- no `src/` hook, no flag, no change to `line_calibration.py`, `kernel/`, `api/` or `intel/`, and no register or `data/registry/` write.
Whether the sealed whole-template objective can select the correct court at all: the AMBIGUOUS cell measures its failure to do so here, not a bound on what another objective could do. G371 is the row that tests a truth-free selector.
