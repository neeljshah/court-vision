# Consolidated seal candidate S746 + S747 + S766 (seal A 2026-10-06, commit B 2026-10-07; X = 2026-10-07)

PAPER ONLY. Calibration wording only. Dispatcher decision 2026-10-05 (DESK_STATE section 2): ONE identity
change, then a FREEZE until a cell reaches its 30-game floor or the season ends (critical defect excepted).
S625 joins ONLY if the owner's fixture ruling arrives before commit A (it had not on 10-05). This file is the
spec amendment for all three rows and the exact runbook the paper-desk-improve run executes. Candidate
branch: private parked/consolidated-seal-2026-10-06 (code on top of master; NOT landed, NO seal cut).

## 1. Declared values (fixed here, before any night they apply to)

| Row | What | Declared value | Where (hashed by the seal) |
|---|---|---|---|
| S746 | training floor for B, C, D | TRAIN_FLOOR_GAMES = 20 settled games per sport in the causal history, both outcomes; below it the tick is warmup (B/C/D None, counted model_warmup:below_game_floor / one_outcome when the sport has history rows; NO model_warmup counts when the history pair is absent or a sport has no history rows (ingame_scoreboard.py:153 returns first): identified by history_refused / history_refusal_reason / training_label A_ONLY, as on nights/2026-10-02.json: history_refused 0, empty --history, A_ONLY) | ingame_scoreboard.py, baseline_four_arm.py, baseline_four_arm_eligibility.py |
| S747 | MLB Middle / End with outs 3 | Middle i -> bottom i outs 0; End i -> top i+1 outs 0; base_state carried as recorded; other outs-3 states stay refused | ingame_scoreboard_rules.py, baseline_four_arm_features.py |
| S766 | cumulative causal history | HISTORY = dict(start='2026-09-22', max_games_per_sport=120): the history for night D is every served night from 2026-09-22 (the first served maker_forward schedule; capture archive starts 09-21) through D-4; embargo unchanged (3 days: ticks and settlement strictly before D-3 00:00Z, applied by the producer boundary AND again by the scorer); admission by settlement (a game enters only with a real 0/1 outcome and close before the boundary); at least the newest 120 settled games per sport are kept (whole slices: the oldest kept slice may take the count past 120), older (night, sport) slices are dropped whole and counted history_cap_excluded | constants in ingame_scoreboard.py; producer scoreboard_history.py + scoreboard_history_slices.py (NOT in the seven hashed files; see disclosure d) |

The verdict floor (30 games / 5 clusters per cell) does not move. The budget file and the night argv are
untouched: the night still passes `--lookback 7`; the producer treats it as a minimum and reaches back to
HISTORY start (cumulative_lookback). Cost bound: each (night, sport) scorer result is computed ONCE at its
final snapshot ((d + 2)T00:00Z - 1 us; the scorer reads only shards d and d + 1) and cached under
data/cache/forward/scoreboard/training/slices/ (local only), keyed by the code identity of 11 files, the policy
prereg sha256, the embargo and the row fields; reuse also requires every recorded source to keep its byte
size. A night therefore re-scores only D-4 (not final yet) and D-5 (first final pass) instead of the window.

## 2. Measured on the live archive (scratch, candidate code via sys.path, outputs under data/ scratch only)

- History for night 2026-10-07 (nights 09-22..10-03): 14,821 rows, 17 MLB games with rows (9 outcome 0,
  8 outcome 1) plus 1 NFL game; manifest 25,479 B (limit 256 KiB); first run 141 s (no cache).
- Night 2026-10-08 with the cache warm: 4 s; rows file and manifest BYTE-IDENTICAL to a cold recomputation.
- First cumulative fit on night 2026-10-03 (5,395 ticks; boundary 09-30 admits the 09-22..09-25 nights):
  floor 20 -> B and C warmup on all 2,351 state-complete ticks (model_warmup:below_game_floor 2,351); with the
  floor lowered to 2 (scratch only) B scores 2,351 ticks with 70 distinct values (0.0569-0.6125) and C 2,351
  with 275 distinct values (0.0182-0.9852): the constant 0.99475 of S744 is gone. S747 is visible: 3,044
  refused vs 3,480 under the sealed code (the Middle / End ticks now encode).
- Projection: the history holds 17 MLB games for night 10-07 and gains about 1-2 settled games per served
  night, so B and C leave warmup at the first night whose history reaches 20 (about nights 10-09..10-11 if
  the laptop stays up through games). NFL has 1 game: warmup all season unless far more NFL games are served.

## 3. Runbook (paper-desk-improve; one identity change; never the night of S534)

Preconditions every step: no process with paper_night in its command line; free RAM >= 2.5 GB; between
ticks (:26 and :56); not 05:00Z-08:45Z; `git status --short | grep -v '^??'` shows nothing foreign staged;
S534 has its own night 10-06 and is NOT in this change.

A0 (10-06, before seal A): `git fetch private`; rebase parked/consolidated-seal-2026-10-06 onto master in its
   own worktree; if the owner's S625 ruling arrived, stop and re-plan (S625 would join here); otherwise run,
   one file per process, the run set in section 4; all green except the SEAL-DEPENDENT pins listed there.
A1 Generate the seal LAST from the candidate tree:
   `python -m scripts.platformkit.execution.ingame_scoreboard_amendment --write docs/evidence/forward/scoreboard/PREREG_2026-10-07.json --effective-from 2026-10-07 --model-optional-sport mlb --model-optional-sport nfl --model-optional-sport soccer`
   Check: seven of seven implementation hashes equal the candidate files (sha256 of LF-normalised bytes);
   the payload differs from PREREG_2026-10-03.json only in effective_from, implementation and sha256.
A2 COMMIT A on master (UTC day 10-06 < X): that json ALONE, `git add docs/evidence/forward/scoreboard/PREREG_2026-10-07.json`,
   push private trunk. Inert check on master: nights 10-06 and 10-07 still select PREREG_2026-10-03.json.
B0 (10-07) Wait for docs/evidence/forward/scoreboard/2026-10-06.json (final; night 10-06 complete or its
   scoreboard step terminal). Gate: `git diff <commit A>..master` empty over the seven hashed files,
   ingame_scoreboard_night.py, ingame_scoreboard_amendment.py, scoreboard_history*.py and the seal;
   `contract_preflight --paths <commit-B files> --base master --spec docs/evidence/harness/CONSOLIDATED_SEAL_2026-10-06.md` zero FAIL.
B1 COMMIT B (fast-forward only, after B0, before 05:00Z 10-08): the candidate code files, the SEALS line
   `('amendment', 'docs/evidence/forward/scoreboard/PREREG_2026-10-07.json', None),` appended in
   ingame_scoreboard_night.py, the three new test files and every conversion in section 4, plus the
   SEAL-DEPENDENT pin updates naming PREREG_2026-10-07.json. Push private trunk.
B2 After B: selection rehearsal (`ingame_scoreboard_night.select('2026-10-07', SEALS)` selects PREREG_2026-10-07.json;
   '2026-10-06' selects PREREG_2026-10-03.json but EXPECT verify to raise amendment_mismatch for it on the new
   code: its implementation hashes name the pre-B files, which is the disclosed refusal below, not a B2 failure);
   seven of seven hashes on master; the run set one file at a time on master; confirm the next tick is tick_ok
   in data/cache/paper_desk/status.json.
B3 No hand step for history: training/2026-10-07.jsonl was produced by the old code during night 10-06
   (lookback 7: nights 09-30..10-03, about 4 games). The new scoreboard step checks the pair against
   cumulative_lookback('2026-10-07', 7) = 15, so night 10-07 EXPECTS history_refused 1 /
   history_refusal_reason config_mismatch and an empty --history; the cumulative history would be below the
   floor too, so night 10-07 is warmup either way. Night 10-07's history step (06:xxZ 10-08)
   is the first cumulative producer run (cold, about 2-3 min, slices written). Do NOT hand-run the producer
   for 10-07: the old pair's config differs and the producer refuses config_mismatch on it.
What night 10-07 should print (scoreboard/2026-10-07.json): amendment path PREREG_2026-10-07.json; NO
model_warmup counts (the history pair is refused, so --history is empty and no sport has history rows): the night
record shows history_refused 1, history_refusal_reason config_mismatch, training_label A_ONLY (same shape as
nights/2026-10-02.json, which had history_refused 0 and an empty --history); B/C/D absent from paired_losses, arm A cells
unchanged in kind; fewer model_state_refused than under the old code on any night with Middle / End ticks.
Night 10-08's manifest: config lookback_days 16, nights 2026-09-22..2026-10-04, and night 10-08 prints history_refused 0. After B the old seals'
nights refuse amendment_mismatch on new code (disclosed; receipts are immutable and never rescored).
FREEZE: no scoring-identity change after B until a cell reaches its 30-game floor or the season ends.
Next step on its own day after B: the S721 pooled prereg, sealed alone.

## 4. Run set and conversions

See the candidate branch commit messages and section 4 table appended by the conversion pass (one file per
process). New: tests/platformkit/ingame/test_s746_training_floor.py (17), tests/platformkit/execution/
test_s747_middle_end.py (33), tests/platformkit/execution/test_s766_cumulative_history.py (7).

## 5. Disclosures

(a) The history producer is NOT one of the seven hashed files; its declared values (HISTORY) are, and its code
identity is recorded per manifest (observation.code: scoreboard_history.py, ingame_scoreboard.py and the slices
CODE_FILES digest) and in every slice key. (b) A slice is cached only when
complete; a night whose next-day shard is absent (laptop off) is recomputed each night. (c) Shard byte size is
the reuse check, not a full hash (re-hashing 100-360 MB shards nightly is what the cache removes); an
in-place edit that keeps the size is not detected. (d) The manifest grows with the window (about 1.8 KB per
night-sport); 256 KiB bounds it near 140 night-sports, after which history refuses size_budget_exceeded:
re-plan before the NBA season adds nights. (e) Registry E keeps its own 7-day window (CALLER_POLICY_E); it is
NOT made cumulative by this change (follow-up in S766). (f) Old-night failures do not stick: for consuming night N,
a night at or before N-5 whose schedule is invalid, or whose scoring raises input_error / census_mismatch /
boundary_violation, is recorded (incomplete, reason plus night_skipped:older_than_n_minus_5), contributes no rows,
is counted in the producer summary nights_skipped, and the pair is still published (exit 0) from the remaining
nights, subject to the floor; the newest window night (N-4) keeps the strict exit 3 / re-raise. Recovery: fix
the old schedule (the next night re-reads it) or leave it skipped.

## 6. Arm E: why zero ticks, and why no early exit

- Nights 09-30, 10-02 (10-01 deadline-killed, 10-03 refused for RAM): every row training_history_absent BY
  DESIGN: E's window is max(effective_from 2026-09-30, D-6)..D and training needs settlement before D-3
  00:00Z, so the first night with any eligible training is 10-04 (the 09-30 games).
- Night 10-04: all 36 published ticks were PREGAME (the laptop slept at 19:00Z, first pitch 20:00Z) and lack
  the microstructure block: microstructure_features.build_features reads only record_type 'snapshot' (focus
  captures), while the mid block also reads 'snapshot_bulk'; before focus (start - 120 s) only bulk snapshots
  exist, so no_prior_book -> e_refusal block_incomplete on 36 of 36 (C scored on 2 training games).
- Support exists: the 09-30 games carry 927 / 881 / 868 rows with every E field and outcomes 0, 0, 1.
- First E tick expected: night 10-05 (CWS at CLE, scored at 06:05Z 10-06) if capture runs through the game:
  live focus ticks carry all seven blocks and the training set (09-30 and 10-01 games) has both outcomes.
  NOT VERIFIED until that receipt exists.
- Early exit: rejected. The only cheap precondition (no eligible training in the window) is false on every
  night from 10-04 on, and the receipt's A / C rows and full census need the same re-read, so an early exit
  cannot produce the same receipt content. registry_scorer_e_night.py is outside BLOCK_CONFIG_E's
  implementation identity, so the real fix (a per-night cached E population, the slice idea of section 1)
  is buildable without a block re-seal; it is folded into S766 (i).

## 7. FIX ROUND 2026-10-05/06 (contract-tier REJECT of e183645b8)

Commits: b46ee3c9c (code, tests, runbook B2/B3 and cap wording), 11b0ea8b4 (S485 repin, S580 window pin), this
section. `git diff --name-only e183645b8..HEAD` touches none of the seven hashed files and not
PREREG_2026-10-07.json, so the seal bytes stand (no regeneration).

- BLOCK fixed: paper_night_steps.scoreboard_step builds history_config with
  scoreboard_history.cumulative_lookback(day, int(p['history_lookback_days'])), the producer's lookback (zero
  net lines; file stays 300). New e2e test_s766 `test_consumer_accepts_the_cumulative_pair_after_start_plus_7`:
  real producer for night 2026-10-08 (lookback_days 16), then scoreboard_step -> history_refused 0 and
  --history lists the pair. On the pre-fix step the same test fails `(1, 'config_mismatch') == (0, None)`.
- cumulative_lookback returns the plain lookback for a non-canonical date ('20261007' parses on Py3.11+;
  chronology refuses it), so test_s766:21 holds on any Python (run here on 3.10 only).
- slices: CODE_FILES adds cross_venue_link.py, coherence_scanner_inputs.py, ingame/game_market_link.py,
  ingame/local_state_capture_dates.py; load skips an outside_repo source only at index 0 (the scorer reads the
  prereg first; its sha256 is in the key) and treats any other outside_repo source as source_changed; save
  uses replace_retry; cap docstring and section 1 say "at least the newest 120" (whole slices).
  NOT changed: the matching comment in ingame_scoreboard.py:29 (a hashed file).
- producer summary emits slice_reused / slice_written / slice_source_changed (asserted 1/0/0 then reused 1).
- capped-manifest test: max_games_per_sport 0 -> 2026-09-24 mlb marked history_cap_excluded, census rows 0,
  rows file empty, and the consumer still accepts the pair (history_refused 0).
- test_s492_e2e.py 300 lines (S746_MOVED -> s469_seal_helper.s746_moved(), cached). Repins: C22 S746_PINNED
  scoreboard_history.py, S485 S746_REPIN paper_night_steps.py. test_s580 consumer child now pins the same
  windowed HISTORY start as its producer child (it is a legacy-pair construct, not a window test).

Run set (one file per process, 22:26Z-22:33Z 10-05, Py3.10, before the quiet window): 41 files, 905 passed,
3 skipped, 0 failed at 11b0ea8b4. Per file: test_s766_cumulative_history 9; test_s492_e2e 9;
test_paper_night_e_step_e2e 41; ingame/test_s746_training_floor 17; test_s747_middle_end 33; test_s492_landing 4;
test_paper_night_steps 56 / _1d 25 / _1e 8; test_paper_night_scoreboard_step 14 / _1c 4 / _1d 2 / _1e 1;
test_scoreboard_history 36; test_scoreboard_history_e2e 14; test_scoreboard_history_store 80;
test_s580_nba_consumer_policy 18 (2 failed before the 11b0ea8b4 window pin); test_s558_round4 3;
ops/test_s485_baseline_contract 4 (1 failed before the 11b0ea8b4 repin); test_exec_receipt_step 21;
test_ingame_scoreboard_night_e2e 8 / _night 34 / _night_replace 13 / _night_table 104;
test_ingame_scoreboard_amendment_model_optional 26; _legacy_guard 6; _policy_snapshot 22; _model_optional 16;
test_soccer_scoring_s490 12; test_nba_season_cohorts 39; test_paper_night 39; test_night_coverage_census 40;
test_paper_night_deadline 20; test_paper_night_deferral_r1 18 (+1 skipped); test_paper_night_inputs 40;
test_paper_night_inputs_e2e 11; ops/test_paper_desk_s520_night 20; test_s494_evidence 4;
ops/test_s492_memo_facts 28; ingame/test_m2_readout_e2e 4 (+1 skipped); ingame/test_s439_integrity_audit_e2e 2
(+1 skipped). The contract tier's "six files" were not named; this set is a superset of every file the
branch touches and every test importing a changed module.
NEXT: both verifier tiers (contract + adversarial) re-run on this tip; only after two ACCEPTs: A0..A2 (seal A).

Correction round 2 (65af25376, after contract ACCEPT + adversarial ACCEPT WITH CORRECTIONS on d9cf835d8):
(1) sections 1 and 3 reworded (no model_warmup counts without history rows; cite nights/2026-10-02.json);
(2) produce() skips + counts a failing night at or before N-5 (section 5(f)); (3) observation.code records the
slices CODE_FILES digest; (4) CODE_FILES + ingame/nba_state_enrichment.py, ingame/mlb_live_feed_state.py.
Run 22:49Z-22:51Z 10-05, one file per process: test_s766_cumulative_history 12; test_paper_night_e_step_e2e 41;
test_scoreboard_history 36; test_scoreboard_history_e2e 14; test_s492_e2e 9; test_soccer_scoring_s490 12;
test_nba_season_cohorts 39; test_s580_nba_consumer_policy 18; test_scoreboard_history_store 80 -- 9 files,
261 passed, 0 failed. Seven of seven implementation hashes still match; PREREG_2026-10-07.json sha256 still
806fa58a3517d28b4f320e89c26f32a73ad6d1a5fe1f153aa5bf0aa9db7f85ea (no regeneration).
NEXT: read-only re-check of the round-2 hunks, then A0..A2 (seal A).
