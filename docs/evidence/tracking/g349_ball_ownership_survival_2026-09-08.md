VERDICT: PARTIAL -- diagnosis DONE (located cause: player_within_radius, first sub-0.10F stage in-radius 8/1560); resealed evaluation NOT VALIDATED (evaluation list unsealed; eligible pairs 6 of the required 100; shuffle bar unmet)

# G349 ball ownership survival (2026-09-08, LOCAL, FINISHER)

Interpreter: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe. Prereg `g349_prereg_2026-09-08.md` seal `1465df2d7c688c8bb3ef822fd81fd43eec6ce11eed0dbb417933e52924e599c0` (verified). Free RAM before start: 3,485,960 KB. No pod/GPU/video/data-write/src-edit/consumer-wire.

PREMISE (binding, 24 G344 windows + 2 WNBA, F=1560, `docs/evidence/tracking/g349_ball_ownership_survival_2026-09-08/survival.csv`):
stage n share detail
frames 1560 1000pm
any_ball_row 285 183pm  (raw row exists, incl. non-finite coords)
detected_ball 237 152pm  (== G344 OBSERVED_VALID pooled, cross-check exact)
player_rows 216 138pm
player_within_radius 8 5pm  <- FIRST STAGE BELOW 0.10F
prerequisite_available 2 1pm
motion_agreement 1 1pm
accepted_ownership 1 1pm  (== G344 owner_share 1/1560, cross-check exact)

DIAGNOSIS: the first sub-0.10F stage is `player_within_radius`, not `any_ball_row` (183pm survives comfortably above the 100pm bar). Per the sealed prereg's binding rule this is NOT a join defect; no fix triggered. Coordinate check: most windows show ball_x/y ranges compatible with player_x/y ranges (e.g. 0022500004 ball_x 960-983 vs player_x 110-1234); 3 of 26 windows show ball_x 2-30x outside the player_x range (0022500630: ball_x 4075-24624, no in-window player rows to compare; 0022500906: ball_x 3288-3324 vs player_x -327..1008; 0022500799: ball_x max 3241 vs player_x max 1134) -- a real, per-window-inconsistent scale anomaly in raw ball_x2d, not a single fixable constant, and not touchable (data/ is read-only here). Age: 100% of detected-ball rows carry age=0 (structural, matches G344). Of the 8 `player_within_radius` frames, 6 (75%, 0.4% of F) lack the frame-3 history prerequisite.

CORRECTIONS: none needed (binding rule not triggered; no uniformly-correctable unit bug found; 0 src/module edits beyond the lane's).

RESEALED EVALUATION (DESCRIPTIVE ONLY, NOT VALIDATED: fresh, non-overlapping sample: 30 NBA ids systematically sampled every-11th of 330 eligible lexical ids + wnba_02 + wnba_05 = 32 games/windows, [600,659] each; evaluation list unsealed because `resealed_window_manifest.csv` was assembled in the result commit):
full-frame denominator = 1920 (32x60). eligible observed-ball motion-pair denominator (prerequisite_available=1, baseline) = 6 -- SHORTFALL vs the sealed >=100 bar: 6/100 (94 short); corpus cannot supply it at this window count.
state_OBSERVED_VALID 256/1920 (13.3%); state_INFERRED 0/1920 -- ablation is trivial, no inferred-ball rows exist in this corpus.
accepted_ownership (baseline) = 0/1920 (worse than the G344 diagnosis corpus's 1/1560).
SHUFFLE CONTROL (agreement = accepted/eligible-pairs, +/-30f ~= 1s): baseline 0/6=0.0%; shift-30f 0/12=0.0% (delta 0pm, no drop); shift+30f 3/11=27.3% (delta -273pm -- agreement ROSE, wrong direction). Sealed >=200pm(20pp)-drop bar: NOT MET either direction; n (6-12) is too small for a stable estimate regardless of verdict.

CONSUMER-BLINDNESS CONTROL: swapped 0022500054's player rows onto 0022500093's ball rows -> the module's own output changes (accepted_owner 1->0, state_OBSERVED_VALID 20->10, abstain_motion_disagreement 1->5); ball input removed entirely (empty table) on 0022500054 -> 100% ABSENT (60/60), structural. `git grep -n "ball_shadow_possession\|shadow_states" -- src kernel api domains intel` = 0 hits in this worktree; combined with the G339 census (sim and intel/ are BALL_BLIND to the raw ball_tracking.csv table itself), 0 master readers would see any change from this swap or removal.

Sign convention: improvement = baseline loss minus candidate loss, positive = candidate better. No scored comparison performed; this is a survival/coverage diagnosis, not a calibration claim. EYE CHECK: NONE.

NOT VERIFIED:
- Nearest in-radius player is not necessarily the ball handler; the 1-2 accepted-ownership hypotheses across both corpora are not validated against video.
- source_height=720 for NBA tables remains an assumption (no such column; matched to the WNBA tables' explicit column), unchanged from G344.
- The 3-of-26-window ball_x scale anomaly is named, not root-caused (upstream detector/writer, out of this row's touchable scope) and not confirmed absent from the resealed 32-window sample (not re-checked there).
- Eligible-pair and shuffle-control ns are severely underpowered at both 6-window diagnosis-scale and 6-12-pair resealed-scale; neither corpus can currently support a stable ownership-signal verdict.
- Dynamic/runtime consumer paths are not traced past a static grep; only src/kernel/api/domains/intel were checked in this worktree.

FILES: `survival.csv` (26 windows, 1560-frame pooled diagnosis), `resealed_states.csv` (32 fresh windows, 1920-frame baseline states), `resealed_window_manifest.csv` (unsealed evaluation list), `input_manifest.csv` (raw evaluation inputs); per-window intermediates under `by_window/` and `resealed_by_window/`.

SHA-256 (LF-normalized bytes): survival.csv=3d153fe7010dad41a70d2e2a6a215868f6d70774f57e5c9c1381851220866526 (21873 B); resealed_states.csv=ef870b81574280ff7f2419c0132ccbc122c83583b8f1dc17463e3a4640decaf5 (100755 B); resealed_window_manifest.csv=544fcccc88c6b654a20cf92b2da024a74759466a857a36ca451dc41b174ee2ca (1355 B).
input_manifest.csv=3be00543986b3a66d46a133ff75f50acaaea8da97b8d35b54865b8ce632b5d53 (6868 B).

2026-09-08 fix 1b: relabelled PARTIAL per the codex-sol REJECT; the evaluation list was assembled in the result commit (no embedded seal) and is descriptive only; a sealed untouched list and a purged walk-forward or CPCV evaluation are attempt-2 work; input_manifest.csv added (64 files, 0 ABSENT).

2026-09-08 fix 1c (orchestrator): the fix-1b ledger edit overwrote row 630 in place; row 630 restored byte-exact from a08ad94b3^ and the corrected PARTIAL row appended as a new row (append-only); tests/platformkit/test_g349_input_manifest.py added (present file, ABSENT file, comment-skipping ids).

2026-09-08 lander: ACCEPT (codex-sol, contract A/B/Q, no corrections) on fix 1c; NEW GAPS in the ledger (local eligible NBA pool 328 vs memo 330, pool membership not archived; the fix-1c ledger restoration inserted the restored row before the corrected row rather than at EOF).
SCAN: prohibited-vocabulary search returned 0 non-measured hits; measured collision: `resealed_states.csv:1154` has `nearest_distance_px=8.94427190999916` (window 0022500743, frame 612), a pixel `math.dist()` value (sqrt(80)).

WALL TIME: 2026-09-08 14:50-15:08 CDT (~18 min).
