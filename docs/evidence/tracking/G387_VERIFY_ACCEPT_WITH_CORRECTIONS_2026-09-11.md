VERDICT: ACCEPT WITH CORRECTIONS
Candidate: `82d51e5a2`; verification date requested by row: 2026-09-10.
PASS ACCEPTANCE input/accounting: 60 unique states, 49 ready, 11 absent; sealed even indices select 30 unique frames over 12 videos/sections; 180 transforms and 30 context/180 tile/30 control hashes match (`G387_spec.md:24`, `selection.csv:2`).
FAIL ACCEPTANCE known-position claim: redispatch at `g387_paint_localization_controls_2026-09-11.md:33` violates no-retry `G387_spec.md:16`; admissible result is 13/30, not 19/30, and remains PARTIAL below 27/30 (`G387_spec.md:25`).
PASS ACCEPTANCE real-paint outcome: independently 1/30, 1/22 visible, 1/12 shared-id; control bar is unmet, so PARTIAL is correct (`G387_spec.md:26`, `per_frame.csv:2`).
PASS ACCEPTANCE reproducibility: fresh probes both `610eb3c2...935c`; independent score digest `7b7ca56f...409d1` matches (`G387_spec.md:27`, `repeats.json:2`).
PASS B1: fixed denominators are 30 controls and 30 real frames; absent/unknown remain charged (`summary.json:8`, `summary.json:12`).
PASS B2: the only touched module additively adds `receipts`; no field/status/removal or reader change (`scripts/platformkit/tracking/g387_run.py:146`).
PASS B3: all 30 rows remain in each denominator; absent evidence does not quarantine an item (`controls/control_results.csv:2`, `per_frame.csv:2`).
PASS B4: no claim lifecycle or reclaim path is introduced (`scripts/platformkit/tracking/g387_run.py:160`).
PASS B5: no deployed-tree change is present or claimed (`g387_paint_localization_controls_2026-09-11.md:36`).
PASS B6: no module was moved/retired and no test/import reference was orphaned (`scripts/platformkit/tracking/g387_run.py:146`).
PASS B7: selection reproduces indices 0,2,3,...,46,48, not a head slice (`selection.csv:2`, `g387_paint_localization_controls_2026-09-11.md:21`).
PASS B8: controls use sealed known positions; no fitter or self-fit claim exists (`G387_spec.md:20`, `g387_paint_localization_controls_2026-09-11.md:29`).
PASS B9: metric units are 30 unique real frame keys and 30 paired control contexts (`G387_spec.md:24`, `summary.json:8`).
PASS B10: 27/30, 24/30, 3 px, 6 px and 8/9 bars match the spec (`G387_spec.md:25`, `summary.json:7`).
PASS Q1: seal `fbb6c987...d093` verifies at prereg line 51; commit `fb1111522` predates label/scoring commits.
PASS Q2: this is not a charged trial or comparative model metric (`g387_paint_localization_controls_2026-09-11.md:36`).
PASS Q3: all bars remain byte-consistent with the spec; the retry correction does not lower any bar (`G387_spec.md:25`, `summary.json:7`).
PASS Q4: no OOS comparison or meta-learner is run or claimed (`g387_paint_localization_controls_2026-09-11.md:36`).
PASS Q5: no AHEAD result is claimed (`g387_paint_localization_controls_2026-09-11.md:36`).
PASS Q6: independent scoped scan found 0 prohibited-vocabulary hits (`q6_scan.json:2`).
PASS Q7: both sampled decision sets have n=30 and the source draw is even (`G387_spec.md:24`, `selection.csv:2`).
PASS Q8: premise was recorded first and independently reproduced (`G387_spec.md:7`, `g387_paint_localization_controls_2026-09-11.md:7`).
PASS PREMISE: claimed 60/49/11, 57 paired/34 zero-overlap, 49 hashes/dimensions, 135177764 bytes, and 0 supplied strokes; reproduced exactly (`g387_paint_localization_controls_2026-09-11.md:7`).
PASS HEADLINES: post-redispatch data reproduce 19/30, endpoint p50 2.3 px, p90 3.2 px, max 33.1 px, 49/60 endpoints and 59/60 midpoints; admissible no-retry result is 13/30 (`g387_paint_localization_controls_2026-09-11.md:25`).
PASS RECEIPTS/LOC/ADDITIVITY: 213/213 paths exist and hash; touched Python file is 163 LOC; no test imports `g387_run` (`SHA256SUMS:1`, `scripts/platformkit/tracking/g387_run.py:1`).
PASS MEMO LIMITS: a NOT VERIFIED list is present (`g387_paint_localization_controls_2026-09-11.md:42`).
TEST: `cd C:\Users\neelj\nba-track-a21 && python -m pytest tests/platformkit/test_g387_paint_localization.py -q` -> 7 passed in 0.68s.
TEST: `cd C:\Users\neelj\nba-ai-system && python -m pytest tests/platformkit/test_g387_paint_localization.py -q` -> exit 4, 0 tests; file absent on current master.
CORRECTION DIFF: memo lines 3,17,25 and `RESULTS_LEDGER.md:738`: replace headline `19/30` with `13/30 admissible (19/30 post-redispatch diagnostic)`; outcome stays PARTIAL.
CORRECTION DIFF: memo line 40 says 167 scanned text artifacts; change to the recorded 164 in `q6_scan.json:2`.
RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G387 | admissible controls 13/30 after excluding retry; post-redispatch diagnostic 19/30; real localization 1/30; premise 60/49/11; repeat digests identical | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: The current master lacks the G387 spec test, so contract A1 cannot run there before candidate landing; the worktree test is green.
NEW GAP: The automated vocabulary scan predates the final memo/ledger text; verifier rescanning found 0 hits in the completed row scope.
NEW GAP: Native contexts, tiles and control pixels are present only in the temporary cache, not the committed matching evidence directory; current hashes verify, but later replay depends on that cache.
NEW GAP: Targeted Git and the sanctioned lane helper cannot create the external linked-worktree index lock; an external path-specific committer must commit this sole memo.
