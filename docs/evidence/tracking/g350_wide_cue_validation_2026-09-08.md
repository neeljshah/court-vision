VERDICT: PARTIAL -- sealed 60-shot selection UNAVAILABLE (CLOSEUP unreachable by construction: 0 of 337 candidates; CROWD/UNKNOWN 2 of 337); WIDE cue NOT VALIDATED and NOT SCORED (no sealed compliant sample).
# G350 wide-cue validation
Spec: docs/evidence/tracking/specs/G350_spec.md. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md (A/B and Q1-Q4 self-check).
Machine: POD job 20260908161106_1891846_16023 for routing, blind sheets and the G341 report; LOCAL (`basketball_ai`) for raters, adjudication, scorer, tests.
Preregistration: docs/evidence/tracking/g350_prereg_2026-09-08.md; LF seal sha256 7b8627061383e2726d5bdfb9d40a7d03ad488320d762fbd357ea58e0be547993 -- unchanged, re-verified by the seal test.
## Binding premise
Fresh independent rerun (verifier, 2026-09-08) matches this row's per-mille UNKNOWN shares on 4 of 6 sections but differs on two: eurocup-qr 968/29/3 per-mille with 6 shots (candidate: 966/34/0, 5 shots) and nbl 3 shots (candidate: 5 shots); premise_router/shots.csv and the six premise_sheets/ JPEGs are retained. The rerun ran on master after G355 (adbc9ba94 -> a5aeb6b71) landed the single-descriptor guard, which changes shot segmentation on sections with one-descriptor frames -- likely cause, not confirmed. The premise conclusion (all six sections below 300 per-mille UNKNOWN) is unchanged by this.
## Sealed selection: UNAVAILABLE -- prereg PARTIAL branch
Of 65 declared pod inputs, 57 routed and 8 did not (route_failures.csv), giving 337 shot-level candidates: WIDE 335, CLOSEUP 0, CROWD_UNKNOWN 2.
The sealed rule needs 20 per group, so `choose_units` raised `sealed selection unavailable: {'CLOSEUP': 0, 'CROWD_UNKNOWN': 2}` (sealed_selection_result.txt, verbatim).
CLOSEUP is unreachable by construction: `_view_class` emits it only when `median_person_height_share` is not None, and this path calls `route_frames` with no person boxes, so it is always None. All 18 premise shots show closeup 000000.
Per the prereg (lines 25-26) the row is PARTIAL and the sealed bar is NOT applied to any smaller set: no subset of the 337 candidates is scored as the sealed result below.
## Rater screening (descriptive only -- not a cue score; n=22 is below the n>=30 rail)
22 units (20 WIDE + 2 CROWD by router prediction, sealed sha256-sort ordering on `G350-2026-09-08|unit_key` kept, 15 distinct videos, shots.csv) were sheeted to exercise the rater protocol; not the sealed 60-shot sample; no rebalancing after ratings; no verdict is scored from it.
Raters: codex terra (gpt-5.6-terra) and codex sol (gpt-5.6-sol), read-only sandbox, 3 batches each (10/10/2), sequential, free-RAM gate 2.6 GB. Sheets carry NO router label: `_sheet` draws only `SHOT <unit_id[-13:]>`, asserted by the focused test and confirmed by eye.
Cohen kappa (terra vs sol, 4 labels) = 0.8429 on these 22 sheets (descriptive rater-protocol statistic, not a cue score). Unrated units 0; batch re-runs needed 0.
Adjudicator claude-opus resolved 2 disagreements, each labelled from the sheet before any per-unit router prediction was read. Agreement with the adjudicated reference: terra 22/22, sol 20/22.
On the 22 rated sheets, 2 of 20 router-WIDE shots were rated USABLE_WIDE (descriptive; not the sealed score). No precision, recall, confidence interval, or abstention share is reported at this sample size (Q7 rail; the sealed bar of precision>=0.95 / recall>=0.80 needs n=60).
## Cut check (descriptive)
All 22 rated shots carry G341 propagation records (2876 steps over 15 sections, min 2 per shot). first_chain_length is 0 or 1 on every one, so cross_cut_chain = 0 of 22: no propagation chain crosses an annotated cut. attempt1/sealed_selection_traceback.txt is the gap-1 crash that aborted the first pass.
## NEW GAPS in landed G341 code -- reported, NOT fixed; no landed file was edited
1. `shot_router.py:68` `good = [a for a, b in pairs ...]` unpacks `knnMatch(k=2)` output as 2-tuples, but knnMatch returns min(k, n_train) per row, so a frame yielding one descriptor gives 1-element lists and raises `ValueError: not enough values to unpack (expected 2, got 1)`. Reproduced in isolation; it aborted a whole full-corpus pass, and 5 of 65 corpus videos die on it. The guard above checks only `desc is None` and `len(good) < 4`.
2. `floor_motion.propagate_frames` starts at position 1 and skips each shot's first frame, so a 1-frame shot emits no propagation rows and `g350_wide_cue_score.cut_check` raises on it.
3. Shot under-segmentation: unit 75d82c:000006 is one "shot" whose first/median/last kept frames are a team graphic, a wide court view and an arena kiosk -- three unrelated scenes merged, so per-shot view class and propagation rest on segments that are not single scenes.
4. The pod `footage_corpus` is a live rotating queue: the declared inventory went from 70 to 65 mp4s between two passes 15 minutes apart, and 3 videos vanished mid-run (FileNotFoundError). Units are keyed by video sha256, never by filename.
5. `router/propagation.csv` (the cut-check input, LF sha256 d8b7b2a3fd078c77cd6a6d159019134b15eeefacbf738231d58c70691c94ceba, 1,314,180 bytes) is untracked and absent from this commit; cut_check.csv is not recomputable from committed inputs alone.
## Input identity
65 declared inputs (input_paths.txt, this run); candidates.csv holds all 337 units. Each of the 15 selected sources is recorded in shots.csv with absolute pod path, sha256, byte size and native size; resolutions span 640x360 to 1920x1080.
## HONEST LIMITATIONS
Model raters proxy for human labels and cannot certify a negligible error rate; both are codex models of one vendor family. 22 shots are a screening, not the sealed 60, and score no verdict.
View class is NOT geometric validity: USABLE_WIDE says the court is visible, not that a homography or propagation on it is correct. Only 2 reference-positive units exist in the screening, so no recall estimate would carry power even if it were scored. The adjudicator also ran the selection and knew the set held 20 WIDE and 2 CROWD in aggregate, though not which unit carried which prediction at labelling time.
## NOT VERIFIED
- The sealed 60-shot selection never ran; no sealed-bar verdict exists for this row.
- No precision, recall, or interval estimate for the WIDE cue exists at any sample size in this row.
- Whether the 8 unroutable videos would change the class mix is unmeasured; no claim is made about calibration or downstream propagation quality from these labels.
## Artifacts and hashes (LF sha256)
shots.csv e859c37ed638e2e7b8df3794c79d223b1a6c80cb962b6f10e2035223b2e21393 ; ratings.csv c79473af9d9f24235ef5939037a06fa6c8583314cca8321d9ecfa3d7ae2026a3
confusion.csv 9006b5d33022307625e4c9ee261b57c47e149b60d20fb5624dbcea505223a0d0 ; cut_check.csv 96a0615abdcc7d0c46ba0589795c62a0f7e0bcb919c783ff1316f7b2081501dd ; adjudication.csv 048b1b6d4c4cd032dfc09cd50755547eb3a050487c3e5656fcf19370b24b618c
candidates.csv 0cc7a0e4ab2a1c41491394d934224ca7bc456dae802c87084a6f09c8b44ef6ca ; route_failures.csv 6cebe7f52543c2e66e2c4052c1b01483cbbdc537fe95af3ec4ed270adfd56f9b ; g350_wide_cue_sheets.py 8ba2cf104edd928f3ab78cd960602d61f188d006a1b99f83315f45099feae9fa
g350_wide_cue_score.py b3c5e076d2121716e973234fa41c5b4b2cca389a56b988debed8c794214cfdb4 ; shot_router.py (landed, unmodified) 1e979e375176becc56da9cc08c678b50afbe10a8db167a7f7ebcaf620d86bca9. 22 sheets committed, each <= 200 KB, largest 44,295 bytes.
TEST: `python -m pytest tests/platformkit/test_g350_wide_cue_validation.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 3 passed in 0.84s
Wall time 2 h 06 min (2026-09-08 20:57Z to 23:03Z), covering two pod launches: the first aborted on gap 1, the second is job 20260908161106_1891846_16023.
2026-09-08 lander: ACCEPT (codex-sol, contract A/B/Q, no corrections) on fix 1b after one REJECT (unsealed subset score withdrawn); NEW GAPS in the ledger (the fix rewrote its own unlanded ledger row; router/propagation.csv untracked so cut_check.csv is not recomputable from committed inputs).
2026-09-08 fix 1b: per the codex-sol REJECT (VERDICT REJECT, 2026-09-08 18:36), withdrew the unsealed 22-shot precision/recall/interval/abstention SCORE (prereg lines 25-26 forbid scoring a smaller set as the sealed result); retained the PARTIAL candidate counts, the sealed-selection unavailability, and the rater kappa as descriptive only; recorded fresh premise values in place of "unchanged" with the likely-cause note on the G355 single-descriptor guard; removed the line naming banned tokens directly and replaced it with this checked-clean statement; added NEW GAP 5 for the untracked router/propagation.csv cut-check input. This memo was checked against the contract's Q6 rail: 0 hits, no banned word or digit string is spelled out anywhere in it.
