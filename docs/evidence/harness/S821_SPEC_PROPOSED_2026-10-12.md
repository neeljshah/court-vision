# S821 specification (PROPOSED) - ncaaf in the live shadow fit
PAPER ONLY. Calibration language only: no edge, ROI or profit wording. Read-only spec lead (Sonnet), 2026-10-12 ~16:3xZ.
No code was written, no python/pytest/replay was run; every claim below is a grep/sed read of the main tree.
Register row: S821 (docs/evidence/HARNESS_GAPS_2026-09-03.md). Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md A, B1-B10, Q1-Q8.
PREMISE VERDICT: TRUE WITH TWO CORRECTIONS. (C1) ncaaf shares tennis's sealed_history_unsupported refusal, and the cure is
NOT in the fit CLI: it sits in SEAL-PINNED files, so the full row is seal-day work. (C2) There is no data to fit: about 2 settled
ncaaf games exist against a floor of 20, so even a landed corpus gives fit_warmup / below_game_floor for weeks.

## 1. Premise (fresh reads)
1. Fit sport set is pinned in ONE tuple: live_shadow_fit_contract.py:10 `SPORTS = ('nba', 'nfl', 'soccer', 'tennis')`. It feeds the
   argparse choice (live_shadow_fit.py:140 `--sport choices=SPORTS`), build_fit's guard (live_shadow_fit.py:55
   `if sport not in SPORTS: raise ValueError('sport_unsupported')`) and artifact_path (contract.py:49). FEATURES (contract.py:11-18) has
   nba / nfl / soccer only; tennis has none because it never reaches a fit.
2. The tennis refusal: live_shadow_fit.py:74-77 `if sport not in CORPUS:` -> `counts['sealed_history_unsupported'] += 1; selected = []`.
   CORPUS is ingame_scoreboard_rules.py:141 `{"mlb": "mlb", "nba": "nba", "nfl": "nfl", "soccer": "soccer_intl"}`: no ncaaf. So an
   ncaaf fit takes the SAME branch for the SAME reason (no sealed corpus name). Status would be fit_warmup with arms {}.
3. Why a corpus is not a one-line add: select_rows calls sport_for(corpus) (baseline_four_arm_eligibility.py:55), which reads CORPORA
   (baseline_four_arm_features.py:26-34; `CORPORA['nfl'] = 'nfl'` at :34; no ncaaf). FEATURES in the same file (:15-23) has no
   ncaaf; state_eligibility (:76-79) routes only `sport == 'nfl'` to nfl_eligibility; parse_state (:186-191) indexes FEATURES[sport].
   The scoreboard's own FEATURES literal (ingame_scoreboard.py ~:40) likewise lists nfl, not ncaaf. The scoring side knows ncaaf
   for the clock only: ingame_scoreboard.py:47 regulation `ncaaf='(3600-game_seconds_remaining)/3600'` and
   ingame_scoreboard_rules.py:57 `elif sport in ('nfl', 'ncaaf')`. That is why 10-10 scored arm A (350 ticks) while B/C/D hit
   model_not_reconstructible (ingame_scoreboard.py:57 `absent='model_not_reconstructible'`, :244 per-arm count).
4. SEAL-PINNED set (docs/operations/DESK_STATE.md section 2 "Seal-pinned files"): ingame_scoreboard.py, ingame_scoreboard_rules.py,
   baseline_four_arm_eligibility.py, baseline_four_arm_features.py, baseline_four_arm_features_nfl.py (PREREG_2026-09-29/-30/-10-01).
   They are also SOURCE_FILES of scoreboard_cumulative_prereg.py:27-37, whose SPORTS (:41) already includes ncaaf, so the
   cumulative pair already carries ncaaf rows. The current seal is PREREG_2026-10-07.json (sha 806fa58a...85ea); grep shows
   baseline_four_arm_features_nfl and ingame_scoreboard_rules among its pinned names. live_shadow_fit.py and
   live_shadow_fit_contract.py are NOT in any PREREG, but both are in CODE_PATHS (contract.py:19-28).
5. CODE_PATHS identity trap: identities() hashes CODE_PATHS (contract.py:36-45) into every fit artifact, and the load path compares
   `doc['code_sha256'] != code` (contract.py:75-76). Editing live_shadow_fit.py or live_shadow_fit_contract.py therefore INVALIDATES
   every fit artifact already written (ALL sports) until they are refit.
6. Recorder side: live_shadow_sport.py:14 `SPORTS = ('mlb','nba','nfl','soccer','tennis')`; :17 STATE_MAX_AGE_S has no ncaaf;
   live_shadow_cli.py:182 `set(sports) <= {"mlb","nba","nfl","soccer","tennis"}` rejects ncaaf at parse time (:183).
   Capture of ncaaf exists (books argv names ncaaf, DESK_STATE switch 3; forward_schedule_writer.py:33 KXNCAAFGAME).
7. Floor and data: TRAIN_FLOOR_GAMES = 20 (ingame_scoreboard.py:28, S746; warmup_reason baseline_four_arm_eligibility.py:21-30
   returns 'below_game_floor'). Only scoreboard/2026-10-10.json has any ncaaf cell (1117 "ncaaf" tokens; n_games values seen
   across the file: 0, 1, 2 only). Scoreboards 10-02..10-09 have none. NCAAF is a Saturday sport and capture began 10-10, so
   reading says about 2 settled games, not 20.

## 2. Seal-day question (one line)
B/C/D reconstruction for ncaaf edits seal-pinned files (rules.py CORPUS, features.py CORPORA/FEATURES, eligibility.py state route,
scoreboard FEATURES literal), so it MUST ride a seal chain step (new PREREG alone, commit B the next day, never two identity changes
in one night, FREEZE rule in DESK_STATE section 2); only Part A (below) avoids the seal, and it forces an all-sports refit.

## 3. Constructs
PART A - smallest landable (no seal-pinned file). RECOMMENDATION: do NOT land it alone; bundle with Part B. It only turns an
argparse error into an honest sealed_history_unsupported artifact (zero new arms) and costs a code_sha256 churn.
A1. live_shadow_fit_contract.SPORTS gains 'ncaaf'; FEATURES stays without ncaaf (the unsupported branch never reads it).
    Test: build_fit([], 'ncaaf', day, root) returns status fit_warmup, arms {}, counts sealed_history_unsupported == 1, and is
    byte-identical on a second call (determinism, like the existing nfl test).
A2. live_shadow_fit.py:140 needs no edit (choices follows A1). Test: main(['--sport','ncaaf','--day',D,...]) exits 0 and writes
    data/cache/live_shadow/_fits/ncaaf/<D>.json under a tmp root; an unknown sport still raises SystemExit.
A3. Recorder list: live_shadow_sport.SPORTS plus STATE_MAX_AGE_S['ncaaf'] = 30.0, and the live_shadow_cli.py:182 set gain 'ncaaf'.
    Only together with A1 (the recorder reads the fit). Test: --sports ncaaf parses; the state bar returns 30.0.
A4. Refit gate: the landing run MUST refit nba/nfl/soccer/tennis for every day still due in the same hour (item 5) and check the
    recorder loads each (no fit_refused). A landing without A4 turns arms B/C dark for all sports.
PART B - seal day (Part A rides with it so code_sha256 changes ONCE).
B1. CORPUS['ncaaf'] = 'ncaaf' (rules.py:141); CORPORA['ncaaf'] = 'ncaaf'; FEATURES['ncaaf'] limited to fields the ncaaf state feed
    really emits (down, distance, possession, timeouts must be read from a captured row in
    data/cache/ingame_state_local_v2/state/ncaaf/2026-10-10.jsonl first: NOT established here).
B2. state_eligibility routes ncaaf to nfl_eligibility only if the field grammar is identical; otherwise a new
    baseline_four_arm_features_ncaaf.py (seal-pinned from birth). Mirror the S469 amendment shape.
B3. New PREREG_<seal day>.json ALONE (commit A), commit B the next day after a green night receipt. The S746 floor of 20 and the
    30-game cell floor are NOT lowered. Until 20 settled games the expected status is fit_warmup / below_game_floor: that is an
    honest result and a success, not a defect.
B4. Amendment: ncaaf joins model_optional_sports only if the sealed rule needs it (DEFAULT_SPORTS ingame_scoreboard_amendment.py:31
    is ('mlb','soccer'); _sports requires membership in CORPUS, :62-65).

## 4. Files owned (when built)
Part A: scripts/platformkit/execution/live_shadow_fit_contract.py, live_shadow_sport.py, live_shadow_cli.py;
tests/platformkit/execution/test_live_shadow_fit.py, test_live_shadow_fit_contract.py, test_live_shadow_cli.py.
Part B (seal day only): the four seal-pinned files of item 3 (+ an ncaaf features module if B2 needs it), a new PREREG json,
their pin tests. NOT touched: data/registry/, any flag, other sports' sealed windows.

## 5. Tests (per file, named)
- python -m pytest tests/platformkit/execution/test_live_shadow_fit_contract.py -q (A1 membership, artifact_path ncaaf)
- python -m pytest tests/platformkit/execution/test_live_shadow_fit.py -q (A1/A2 refusal artifact, determinism; B: ready fit on a synthetic 20-game ncaaf history)
- python -m pytest tests/platformkit/execution/test_live_shadow_cli.py -q (A3 parser)
- Part B: the existing pin/seal test for each edited pinned file (grep tests for baseline_four_arm_features), one file at a time.

## 6. Measured proof
After Part A + A4: `fit --sport ncaaf --day D` writes status fit_warmup with counts {sealed_history_unsupported: 1}; the other four
sports' fit artifacts reload (status ready where they were ready). After Part B and 20 settled games: ncaaf fit_warmup -> ready and
the night's B/C/D ncaaf cells stop reporting model_not_reconstructible (a count read from scoreboard/<day>.json). Report n_games
honestly; below 30 the verdict word stays INSUFFICIENT.

## 7. Risks / landmines
- code_sha256 churn (item 5): any edit to the two fit files invalidates all sports' fits. Land right after a night's fits; refit at once.
- Never edit a seal-pinned file outside its chain step; never two identity changes in one night; the post-commit-B FREEZE holds.
- Do not manufacture a corpus (live_shadow_fit.py:75 says so for tennis); no ncaaf history exists before 10-10.
- ncaaf state fields and overtime rules differ from the NFL; unverified.

## 8. Verifier contract
Contract tier: A and B1-B10 on the diff, Q1-Q8 on the tests; confirm Part A touches no seal-pinned path (git diff --name-only against
the item 3 list) and that the refit step A4 appears in the landing receipt.
Adversarial tier mutants (each must be killed): (m1) SPORTS omits ncaaf but the recorder accepts it; (m2) ncaaf mapped to the nfl
CORPUS name (silent reuse of nfl rows); (m3) fit emits ready on 2 games (floor bypass); (m4) FEATURES['ncaaf'] aliased with a missing
field defaulting to 0; (m5) the refusal path writes arms for ncaaf; (m6) A1 landed without A4 (other sports' fits fail to load);
(m7) an edit to a seal-pinned file under Part A; (m8) wording drift: any edge / ROI term in the artifact or memo.
