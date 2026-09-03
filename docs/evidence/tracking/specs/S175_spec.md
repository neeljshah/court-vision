GAP S175 | sport harness | worktree a16 | log cx_s175_screen_p_writer
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- self-check every line of section B AND section Q (S-row) before you report.
PREMISE (step 0): re-measure first. Measured 2026-09-04 on master HEAD fae6adb76: results_db.record
adds the column only `if "screen_p" in row` (results_db.py:134) and the only two ResultsDB.record
call sites -- foundry_runner._record (row :142-147, call :155) and s58_t2_first_trial.py:113-119 --
put the DM screen p nowhere but `archive` (tiers.py:247). Census of data/cache/eval_gate/
s85_screen_2026-09-03.sqlite: result has 20 columns and NO screen_p column; 1,302 rows (T0 958 /
T1 344); raw_p non-NULL = 0 in both tiers; 344/344 T1 artifact JSONs carry screen_p under `archive`
only. Construct on a tmp DB with the exact _record row seeded from a real S85 T1 trial: stored
raw_p=None, screen_p=None while archive["screen_p"]=0.009006401254327563; family_p_values('famX')
-> [] and (...,'T1') -> []. Both production family_p_values callers are untiered
(charge_path_followups.py:63, s58_t2_first_trial.py:108); zero callers pass tier='T1'. If falsified,
STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): none expected; the value is on result.archive at record time. If _record cannot reach it, report CLOSED AT LIMIT and do not fix.
CHANGE (step 2): in foundry_runner._record lift `screen_p` from result.archive into the top-level
row when present (T0/T2 carry none and stay unchanged); correct the now-false docstring line
tiers.py:235. Additive only: no rename, no removal, no SQL edited, no bar moved, no consumer rewired.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric = fraction of T1 result rows whose result.screen_p equals that trial's artifact JSON
    archive["screen_p"] to 1e-12; denominator = every T1 row the screen run records
  before = 0 of 344 T1 rows in s85_screen_2026-09-03.sqlite (column absent); 0 of 1 in the construct
  bar = 344/344 on a re-run of the S85 seed (--predictor real, charges OFF), AND
    family_p_values(family, tier='T1') returns exactly that family's T1 screen p-values in result.id
    order for all 5 screened families (nba_opp_allowed 120, soccer_style_fingerprints 112,
    nba_player_adv 48, nba_player_value_features 32, mlb_bullpen_relief_chains 32)
  n = 344 (recorded T1 rows)
  eye check = n/a (S-row); reproduction = SELECT hash, screen_p, artifact_path FROM result WHERE
    tier='T1' on the re-run sqlite, compare each to json.load(path)['archive']['screen_p']
  must not move = untiered family_p_values SQL byte-identical, tiers._run_screen archive CONTENTS
    byte-identical, the 20 existing result columns, data/cache/eval_gate/backtest_fwer.jsonl
    (18 rows, md5 a4ae7c13995672e478d59770591b83ba)
NON-TAUTOLOGY: covers every T1 row the re-run records, none excluded. T0 (958) and T2 are out of
scope -- tiers writes screen_p only on the T1 path; report their counts, never drop them.
EVIDENCE: docs/evidence/harness/screen_p_writer_2026-09-04.md -- before/after table, n, denominator,
the 5-family reproduction, a "NOT VERIFIED" list; copy the re-run summary JSON and the per-family
p-value lists under docs/evidence/ so a verifier needs no local DB.
TEST: exactly one new per-file test; run only that file. <= 300 LOC per file.
POD: none -- local re-run only. Charges OFF; never touch the real FWER ledger.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha. NEVER PARK: poll your own jobs
in a blocking loop; never end waiting.
