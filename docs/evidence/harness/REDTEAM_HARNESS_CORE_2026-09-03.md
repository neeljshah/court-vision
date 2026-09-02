# Harness-core red team -- 2026-09-03 (adversarial, read-only)

Scope read on disk: `scripts/platformkit/eval_gate/{walkforward, cpcv_engine, dm_test,
deflated_metrics, pbo, backtest_runner, ledger, gate_manifest, scoring, shin,
false_discovery, romano_wolf, spa_test, null_ship_calibration, retro_correction,
run_gate, close_join, golden_loader}.py`, `scripts/platformkit/combo/{fwer_budget,
stack_fit, nested_cv, corpus_cache, planted_null_fdr, null_floor, combo_runner}.py`,
`scripts/platformkit/ingame/gap_effective_n.py`, `scripts/platformkit/hedge_trial_runner.py`
+ `hedge_trial_arms.py`, and the test files beside them.

Method: every row marked `yes` was EXECUTED this session against the code on disk.
Reproductions live ONLY under `C:/Users/neelj/AppData/Local/Temp/claude/.../scratchpad/`;
no repo file is touched by this lane except this memo. Calibration language only: no
verdict below is a market claim, and every REJECT / BEHIND / NULL here is a success.

Severity vocabulary: bar-moving | leak | circular | silent-cap | false-precision | docs-only.

## Findings

| id | file:line | scenario (inputs -> wrong verdict) | severity | repro | smallest additive fix |
|----|-----------|------------------------------------|----------|-------|-----------------------|
| RT-1 | `eval_gate/romano_wolf.py:68` | The joint branch divides by `scales` with no `scales > 0` mask (`spa_test.py:107` HAS that mask). A family containing one degenerate arm (constant loss differential -- e.g. a control arm identical to the benchmark) gives 0/0 -> NaN in `boot`; `np.max` propagates the NaN; `nan >= observed` is False for every draw, so `adjusted_p` collapses to `1/(B+1)`. MEASURED: the arm alone -> adjusted_p 0.0840, rejected False; add the control arm -> adjusted_p 0.00050, **rejected True**. A non-significant arm is turned into a FWER-"corrected" rejection BY the correction. | bar-moving | yes | mirror `spa_test.py:107`: compute `usable = scales > 0.0` and set `boot[b][~usable] = 0.0` instead of dividing. |
| RT-2 | `hedge_trial_arms.py:177` | `key = id(train)` caches the Hedge state on the CPython ADDRESS of the train list. `cpcv_evaluate` rebinds `train_states` per split and drops the old list, so addresses get reused. MEASURED inside the real `cpcv_evaluate` (64 states, 28 splits): only **3 distinct `id(train)` addresses** and **400 predictor calls served a stale split's state**. The CPCV block's hedge numbers are produced by weights fit on a different split's games, which can include the current test block. | leak | yes | key on content, not identity: `key = tuple(s["game_id"] for s in train)`. |
| RT-3 | `backtest_runner.py:153,209` + `tracking/worktree_data_links.py:15` | `--ledger` is a caller-supplied path with no canonical-path assertion, and `_charge_ledger` CREATES it (`mkdir(parents=True)`). `FORBIDDEN = ["cache/eval_gate", "registry"]` means codex worktrees never receive the ledger junction, so a charged trial run in a worktree necessarily starts a fresh ledger. MEASURED: canonical ledger max `k_cumulative`=13 -> `dm_alpha` 0.003846; a fresh path -> `k_cumulative`=1 -> `dm_alpha` **0.05**, a 13x looser per-test bar. | bar-moving | yes | assert the resolved `ledger_path` equals the repo-root canonical path unless an explicit `--allow-scratch-ledger` flag is given, and stamp that flag into the report. |
| RT-4 | `dm_test.py:111` | `ci95` uses the normal 1.96 while `p_value` (line 110) uses Student-t with `g-1` df. At small cluster counts the two disagree. MEASURED (g=4): p_value(t,3)=0.1441, NOT significant -- yet the reported ci95=(0.00141, 0.97697) EXCLUDES 0 and reads as significant; the honest t(3) interval is (-0.30281, 1.28119) and straddles 0. `hedge_trial_runner.verdict_of:101` reads `dm_ci95_improvement[0] > 0` as one AND-ed condition and `:241` prints it. | false-precision | yes | use the same t quantile the p-value uses in place of the literal 1.96. |
| RT-5 | `eval_gate/false_discovery.py:26` and `:15` | `within_noise_floor = len(survivors) <= math.ceil(expected)`; `ceil` of any expectation in (0,1] is 1, so ONE survivor is always "within the noise floor". MEASURED: 85 rows, expected_false_survivors=0.050000, observed=1, `within_noise_floor=True`. Separately `measured` requires BOTH `n_trials_this_sweep` and `n`; a `ship_eligible` row missing `n` is dropped from `n_tested` AND from `survivor_ids` -> observed 0, `within_noise_floor=True`. | silent-cap | yes | compare against the Poisson tail rather than `ceil`, and emit `n_unscorable` for rows the key filter drops instead of skipping them silently. |
| RT-6 | `null_ship_calibration.py:43,47` | `passed = ship_rate <= 2.0 * nominal_alpha` and `.passed` never consults `.provisional`. MEASURED: `CalibrationResult(candidates=1, ships=0, provisional=True)` -> `passed=True` and `main()` exit 0, so a one-candidate wall-timed-out run reports PASS. MEASURED: 200 candidates with **19 pure-noise SHIPs** (rate 0.095 against a nominal 0.05) -> `passed=True`, because the ceiling is twice alpha. | silent-cap | yes | `passed = (not provisional) and candidates >= DEFAULT_CANDIDATES and ship_rate <= threshold`. |
| RT-7 | `gate_manifest.py:142,209` | `effective = _parse_dt(as_of_field) or mtime` -- freshness is SELF-DECLARED by the artifact, an unparseable `as_of` silently falls back to WRITE time, and `main()` exits non-zero only on UNREADABLE, never on staleness. MEASURED at `as_of=2026-09-03`: a row declaring `as_of=2031-01-01` -> `staleness_days=-1581.0`, status OK; a row declaring `as_of="not-a-date"` -> `staleness_days=0.8` from mtime, status OK; summary `unreadable=0` -> exit 0. This is S09 exactly. | silent-cap | yes | add an `as_of_source` field ("field"/"mtime") and `status="STALE"` when `effective` is absent, in the future, or older than a named cap; make `main()` exit 1 on any STALE row. |
| RT-8 | `combo/planted_null_fdr.py:112-118` | `except Exception -> verdict = "ERROR"`, logged at DEBUG only, counted as a non-ship. MEASURED with a gate that always raises: 20/20 nulls errored, yet `FDRResult(fdr_hat=0.0, n_shipped=0, frozen=False)` -- the lane reports "the gate is not manufacturing ships" having measured nothing, and there is no `n_error` field to catch it. Separately the budget clause is DEAD: `frozen = n_shipped > 0 or fdr_hat > budget`, and `fdr_hat > 0` implies `n_shipped > 0`, so `fdr_budget(eps, K)` can never be the deciding term. | circular | yes | add `n_error` to `FDRResult` and use `frozen = n_shipped > 0 or n_error > 0 or (n_run - n_error) < _MIN_NULLS`. |
| RT-9 | `combo/null_floor.py:129` | `n_key = str(min(max(1, int(n_extra_params)), MAX_EXTRA_PARAMS))` silently grades a candidate against a floor built for FEWER free columns. MEASURED: `n_extra=12 -> table key "4"`. A 12-column noise candidate is compared to the 4-column noise floor, which sits lower, and returns PROCEED. | silent-cap | yes | raise `KeyError` when `n_extra_params > MAX_EXTRA_PARAMS` instead of clamping -- "no matched floor" is an honest stop. |
| RT-10 | `hedge_trial_runner.py:229,236` | `charge if sport == "mlb" else None` -- only the first sport charges; every later corpus reuses the previous block's `k_cum`. The charge lambda also hardcodes `"mlb"` as the ledger `sport` field whatever is being scored. MEASURED on the real artifact `data/cache/eval_gate/hedge_trial_2026-09-01.json`: `soccer_intl` carries `ledger_row=None` and `k_cumulative=12` inherited from mlb -- two corpora scored, one trial charged. (Both verdicts are BEHIND, so no live claim rests on it.) | bar-moving | yes | charge once per (predictor, corpus): pass `charge` for every sport and write the real sport name in the row. |
| RT-11 | `eval_gate/shin.py:23,47,62` | Both price guards are bare `assert`s and the bisection returns no convergence flag. MEASURED: `shin_devig([1.1111, 0.4762])` (a price below 1 upstream) cannot bracket a root, yet line 62 `p = p / p.sum()` normalizes and returns `p=[0.81746, 0.18254], z=0.734065, sum=1.000000` with no error. Under `python -O` the asserts vanish and `shin_devig_decimal([0.9, 2.1])` returns those same silently-wrong fair probabilities. A corrupted benchmark is the direct route to a wrong verdict. | leak | yes | replace both asserts with `raise ValueError`, and raise on non-convergence instead of normalizing an unconverged `z`. |
| RT-12 | `combo/nested_cv.py:133` | An EMPTY sealed holdout still returns a score. MEASURED: 3 game_ids over `n_folds=5` with an empty `holdout_fold` -> `n_holdout_games=0`, `outer_score=0.0`, nothing raised, no status field. A caller reading `outer_score` cannot tell a 0-game holdout from a real one. | circular | yes | `if not holdout: raise ValueError("sealed outer holdout is empty")`. |
| RT-13 | `hedge_trial_arms.py:160-163` | `code = gid.rsplit("-",1)[-1][-6:]; home = code[3:]; away = code[:3]` synthesizes team keys from the game_id suffix, and `cpcv_engine` then purges on them. MEASURED: `"mlb-2026-06-28-NYY-BOS" -> home='' away='BOS'`; every MLB game shares `home=''`, so `_same_team` is True for EVERY pair while `_same_matchup` fires only on a shared last token. The team dimension of the purge is not a team dimension. Direction is conservative (over-purge), but `n_train` and any "purged by team" statement in the artifact are not what they say. | circular | yes | carry the real `home`/`away` through `load_corpus` into `game_states`, or set both to the `game_id` and say so in the artifact. |
| RT-14 | `eval_gate/retro_correction.py:12,31` | `RETRO_SWEEP_TRIALS = 85` is hardcoded with no assertion against the catalog, and line 31 hardcodes the prose "60 current catalog classes". MEASURED today: `len(catalog_signals()) = 60`, `RETRO_SWEEP_TRIALS = 85`. The printed `bonferroni_eps` is pinned at 0.05/85 whatever the catalog does. Prior-red-team finding 1.4, still open. | false-precision | yes | keep 85 as the pre-registered width but add `assert len(pairs) <= RETRO_SWEEP_TRIALS` and render the count from `len(pairs)` rather than the literal. |
| RT-15 | `eval_gate/pbo.py:66` | `np.array_split` yields UNEQUAL blocks when `n_obs % s_blocks != 0`, so the IS half and its OOS complement hold different row counts across combos -- the same non-uniform-rank problem `_check_s_blocks` (lines 49-50) documents for odd `s_blocks`, left unguarded. MEASURED: `contiguous_blocks(70, 16)` -> sizes `[5,5,5,5,5,5,4,4,4,4,4,4,4,4,4,4]`; an IS half holds 32..38 rows. | false-precision | yes | trim to `n_obs - (n_obs % s_blocks)` rows, and report the trim, so every block is equal. |
| RT-16 | `backtest_runner.py:86-87` | `if p_close is None or ...: continue` drops unpriceable joined rows with NO counter, and `run_backtest` reports `n_games` over survivors only. MEASURED on a synthetic corpus: 10 joined rows, 5 carrying a corrupt price -> 5 states returned, 5 dropped, nothing in the report names the 5. The scored denominator is not the corpus denominator. | false-precision | yes | count the skips and emit `"dropped_unpriceable": k` beside `n_games`. |
| RT-17 | `eval_gate/close_join.py:115` | `_joined` correctly captures `counts = dict(close.attrs)` at line 101, but `gate_corpus_states` does `joined, _ = _joined(...)` -- it DISCARDS those drop counts and then applies its own four-way `notna` + `_spine_join == "both"` filter with no count of what that removes. MEASURED that the carrier is fragile too: a `Series.attrs` dict survives on the Series but is `{}` after assignment into a DataFrame and `{}` after a merge. | false-precision | yes | return the counts from `gate_corpus_states` and add `spine_unmatched` / `null_target` counters for its own filter. |
| RT-18 | `eval_gate/walkforward.py:110-113`, `cpcv_engine.py:44` | The test-row redaction is a DENY-list of four names. MEASURED: a state carrying a NEW settled column (`final_margin`) reaches `predict_fn` un-redacted and an oracle scores **Brier 0.0000** with no `LeakError`. The 2026-09-01 hardening plugged the four known keys; the next settled column added to a state schema leaks by default. `backtest_runner._redact:98` already uses the safe shape (an ALLOW-list `keep` tuple) -- the two harnesses disagree. | leak | yes | invert both to an allow-list (`keep = ("game_id","state_ts","features","feature_avail","home","away")`), matching `backtest_runner._redact`. |
| RT-19 | `clv_ledger_io.py:119-121,130-136` | `ledger_lock` is documented "NEVER raises on lock failure or timeout -- the block still runs unlocked", so `_charge_ledger`'s read-max + append critical section can run unserialized. MEASURED on this box (`_LOCK_KIND="msvcrt"`, a real backend): a contended `_acquire` returns **False** after its timeout and the caller proceeds anyway. Two concurrent charges then both read `prior=K` and both write `K+1` -- a lost update that UNDERCOUNTS K and loosens `eps_eff`, the exact failure `_charge_ledger`'s own comment claims to prevent. | bar-moving | yes | let `_charge_ledger` fail closed rather than the generic helper: have `ledger_lock` yield the acquisition result and raise in `_charge_ledger` when it is False. |
| RT-20 | `combo/combo_runner.py:135,203` | `prior_k = int(cur.get("combo_k", 0))` reads K from a per-sport CHECKPOINT file, never from `backtest_fwer.jsonl`, and `cur["combo_k"]` is persisted only at the checkpoint step AFTER the gate loop. MEASURED: a fresh or deleted checkpoint -> `prior_k=0` -> per-test bar `eps_eff=0.05000`; a warm one at 240 -> `0.0002083`. Deleting one JSON restores the bar by 240x, and a mid-cycle crash gates trials that K never records. | bar-moving | yes | seed `prior_k` from `max(checkpoint_k, ledger_k)` with `ledger_k` read from `backtest_fwer.jsonl`, and persist `combo_k` BEFORE the gate loop. |
| RT-21 | `eval_gate/test_false_discovery.py:20`, `test_retro_correction.py:10-11`, `test_null_ship_calibration.py:22` | Three tautological tests. (a) `assert row["within_noise_floor"] is True` PINS the RT-5 rounding hole as correct behaviour (expectation 0.05, one survivor). (b) `assert len(pairs) == 60` and `assert "n_trials_this_sweep=85" in text` pin the RT-14 MISMATCH side by side; a 61st catalog class breaks the wrong assertion and never the K. (c) `assert 0 <= result.ships <= result.candidates` is vacuous -- a gate shipping 100% of pure-noise candidates passes it, and `.passed` is never exercised. | circular | yes | (a) assert the Poisson-tail form; (b) assert `n_trials_this_sweep` against `RETRO_SWEEP_TRIALS` and `len(pairs) <= RETRO_SWEEP_TRIALS`; (c) assert `result.ships == 0` for a 2-candidate noise run plus one `.passed is False` case. |

Counter-example worth preserving: `test_hedge_trial_arms.py:61` asserts the LITERALS
`R.BAR == 0.004` and `R.LOCK ~= -0.0343` rather than the imported constants. That is the
correct B10 shape -- a bar that moves breaks the test. Copy it; do not change it.

## Answers to the ten commissioned questions

1. **Metric before `_charge_ledger`?** No in-tree caller does. `_charge_ledger` has exactly
   three call sites -- `backtest_runner.run_backtest:153` (before `load_states`),
   `hedge_trial_runner:229` via `run_sport:172` (before `arm_series`), and
   `student_gate.py:162` (before `:183`) -- and all three charge first. Readers of
   `backtest_fwer.jsonl`: `backtest_runner._charge_ledger`, `hedge_trial_runner.py:37`,
   `signals/foundry_run.py:21`, `analytics_showcase/mechanism_foundry.py:29`,
   `analytics_showcase/test_mechanism_wiring.py:124`, `gate_manifest` (as a manifest row),
   and `tracking/worktree_data_links.py:15` (to EXCLUDE it). The exposure is not ordering; it
   is RT-3 (the ledger path is a parameter), RT-10 (a second corpus scored uncharged), RT-19
   (the lock fails open) and RT-20 (a second, independent K counter).
2. **`select_inside` / embargo same-day or same-matchup leakage?** `select_inside` is
   RECORDED ONLY inside the gate: `walkforward.py:123` stores it, and neither
   `backtest_runner.run_backtest` nor `pbo.build_pred_matrix` reads
   `WalkForwardResult.select_inside`. Its only consumer is `governance/leak_audit.py:131,139`,
   so a caller that does not route through `leak_audit.audit` gets no enforcement. The embargo
   itself is sound: `ts >= t` is strictly-before and tie-safe; `_same_matchup` + `EMBARGO_DAYS=3`
   and `_same_team` + `PURGE_HOURS=48` are applied backward; and `backtest_runner.load_states:89`
   stamps every same-date game with an identical `state_ts`, so same-day rows leave the train
   set entirely (conservative). No same-day or same-matchup leak found. The real leak here is
   RT-18.
3. **Is `deflated_p`'s K read from the ledger at launch everywhere?** No. `deflated_p` has one
   production caller, `hedge_trial_runner.py:95`, and it does read K from the launch charge
   (`run_sport:173`) -- for the FIRST sport only (RT-10). There are THREE independent K
   universes on disk: `backtest_fwer.jsonl` (13 rows, max K=13); `combo_runner.py:135`'s
   per-sport checkpoint `combo_k` (RT-20); and `retro_correction.RETRO_SWEEP_TRIALS = 85`
   (RT-14). `run_gate.py:149` adds a fourth convention, `n_trials = len(CORPORA) = 2`. Nothing
   reconciles them.
4. **Does `cpcv_evaluate` purge by group AND embargo symmetrically?** Yes. `_purged`
   (`cpcv_engine.py:52-60`) takes `abs()` on both the calendar-day delta and the timestamp gap,
   and `cpcv_evaluate:85-86` evaluates it against EVERY test row in the split
   (`any(... for j in test_idx)`), so a train row adjacent on either side is dropped. The
   engine's own forward-only embargo is correctly disabled (`embargo_blocks=0`, line 81). The
   defect here is not the geometry but the purge KEYS on the live corpus (RT-13).
5. **Does `pbo.cscv_pbo` score with the same loss as the verdict?** Yes. `cscv_pbo:131-132`
   uses per-config Brier; `backtest_runner:177` and `hedge_trial_runner:87` use squared-error
   loss DIFFERENTIALS. Within one split the reference (close, or raw) Brier is constant across
   configs, so ranking by absolute Brier and by the differential give the same ordering. No
   loss mismatch. RT-15 is the only PBO issue found.
6. **Is `gap_effective_n`'s ICC ever a stored constant?** No. `effective_sample_size:70` calls
   `intraclass_correlation` on the SAME `rows` it is summarizing, and
   `intraclass_correlation:34-50` recomputes between/within from those rows every time. A
   repo-wide grep for a hardcoded `0.291` / `87.4` (the S17 register figures) finds nothing in
   code. Clean.
7. **Where does `gate_manifest` fall back to mtime and silently pass?** `gate_manifest.py:142`
   (`effective = _parse_dt(as_of_field) or mtime`) and `:209`
   (`return 1 if manifest["summary"]["unreadable"] > 0 else 0`). See RT-7 for the measured run.
8. **Tautological tests?** Three, all listed in RT-21.
9. **Absent arm becomes 0.5 instead of a mask?** Yes, in the kernel:
   `kernel/validation/proof_metrics.py:164-165` -- `devig2` returns `(0.5, 0.5)` for any price
   `<= 1.0`. That is a coin flip, not a mask, and it is PINNED as intended behaviour by
   `tests/kernel/test_proof_metrics.py:57-60`, `tests/platform/test_soccer_proof_metrics.py:62`
   and `tests/platform/test_proof_metrics_equivalence.py:300` ("all prices <= 1.0 -> devig2
   returns 0.5 -> no movement -> all zeros"), which is how it silently dilutes
   `clv_sign_invariants` (`proof_metrics.py:220-221`). The in-scope paths are CLEAN by
   contrast: `close_join.close_column:61-63` masks `price <= 1.0` BEFORE calling `devig2`;
   `ingame/hedge_combiner.predict:74-78` drops an absent arm from both sums and returns None;
   `hedge_trial_arms.hedge_predictor:184` falls back to the labelled `raw_model`, not 0.5; and
   `stack_fit.standardize:88` imputes NaN to the train mean but `score_with_fallback:171` masks
   those rows back to `p_base`. `kernel/**` is human-gated -- flagged, not touched.
10. **Does `shin_devig_decimal` or `devig2` fail open silently on a bad price inside a scored
    path?** `devig2` yes, but not on a scored gate path (see 9 -- `close_join` guards it and
    the fail-open reaches `clv_sign_invariants` only). `shin_devig_decimal` yes, twice, and it
    is a reference the module docstring points at production: see RT-11.

## Prior red team (`HARNESS_REDTEAM_2026-09-01.md`) -- status on disk today

- **FIXED** -- oracle label read (agents 3/4/7): `walkforward.py:110-113` strips
  `outcome`/`devig_close_prob`/`truth_wp`/`index`, `cpcv_engine.py:44` mirrors it, and
  `null_ship_calibration.run_exploit_regressions:101-120` regression-tests LABEL-ECHO and
  MARKET-ECHO. Verified the four keys are absent from the predictor's view. The fix is a
  deny-list, which is RT-18.
- **FIXED** -- ISO-string vintage comparison (agent 3): `assert_vintage:61-78` now parses with
  `datetime.fromisoformat`, rejects date-only availability (`len(avail) == 10`) and rejects
  mixed naive/aware timestamps.
- **FIXED** -- DM normal-quantile p-value (agent 1.3): `dm_test.py:110` uses
  `_student_t_two_tailed_pvalue(abs(dm), g - 1)`. The interval beside it was NOT migrated -- RT-4.
- **FIXED** -- Windows lock no-op (agent 2.1): a real `msvcrt` backend exists and
  `_LOCK_KIND == "msvcrt"` on this box. It still fails open under contention -- RT-19.
- **NOT FIXED** -- FWER correction disconnected from the verdict string (agent 1.1):
  `run_gate.py:83` still returns `"BEATS_CLOSE"` on the RAW `dm.p_value < 0.05`, while
  `corrected_dm_p` and `ship_eligible` are written later at `:197-199` and never consulted by
  `_verdict`.
- **NOT FIXED** -- the `n >= 200` floor counts raw states, not game clusters (agent 1.3):
  `run_gate.py:44` `DM_MIN_N = 200` and `:83` tests `dm.n`, not `dm.n_clusters`.
- **NOT FIXED** -- multiplicity hardcoded to the corpus count (agent 3): `run_gate.py:149`
  `n_trials = len(CORPORA)` = 2, not the cumulative ledger K. See answer 3.
- **NOT FIXED** -- golden fixture / frozen baselines never hash-checked (agent 1.2):
  `golden_loader.load_golden:28-36` runs only `validate_golden` (structural + leak + coverage);
  there is no SHA-256 seal and the `schema` version int is never read. A schema-valid hand edit
  still redefines what "gate green" means.
- **NOT FIXED** -- `RETRO_SWEEP_TRIALS = 85` never asserted against the catalog (agent 1.4):
  RT-14, measured 60 on disk today.
- **OUT OF SCOPE this pass** (tracking-harness rails): agents 5 and 6 -- `median_track_len`
  never gated, all-None liveness thresholds, singleton-track vacuity, court-calibration sidecar
  self-reporting. Not re-checked here; they belong to the G register.

## UNVERIFIED HYPOTHESES (code-read only, NOT reproduced -- do not cite as measured)

- `hedge_trial_runner.pbo_block:122` drops any row where ANY config is non-finite
  (`rows = [i for i in order if all(_finite(s[i]) ...)]`). A single low-coverage arm should
  therefore shrink the scored row set for every other config and change the reported `n_obs`.
  Direction and size not measured; needs the real tick store.
- `null_floor.compute_null_floor_for_unit:81` takes `np.percentile(deltas, 99)` from
  `M_DRAWS = 40` draws. A p99 from 40 samples interpolates between the top two order statistics
  and should be very high-variance, making the prescreen floor itself unstable run to run.
- `null_floor._one_noise_delta:55` fits with `expanding_window_splits(n, 0.5, n_folds=1)`. The
  module claims the "IDENTICAL stack_fit path" as a real candidate; whether
  `stack_gate_pregame` actually uses `initial_train_frac=0.5, n_folds=1` was not traced. If it
  does not, every floor is matched to the wrong protocol.
- `fwer_budget.eps_eff:52` calls `int(k)`, which TRUNCATES a float K (2.9 -> 2) and loosens the
  bar. No caller currently passes a float; not reproduced.
- `fwer_budget.min_corpora_eff:68` returns 2 when `n_corpora == 1`, contradicting its own
  docstring ("never exceeds the number of AVAILABLE corpora"). The direction is conservative,
  so this is a docs/behaviour disagreement rather than a hole; not exercised against a caller.
- `gate_manifest._load:67-72` returns only the LAST line of a `.jsonl`, so a `verdict` on any
  earlier ledger row is invisible to the manifest. Not measured against a real multi-verdict
  ledger.
- `spa_test.hansen_spa:96` computes `sqrt(2 * log(log(n_games)))`, which is 0 for small
  `n_games` and drives `recenter` to include every candidate. Behaviour at `n_games in {2, 3}`
  was not exercised.
- RT-2's stale-cache hits were counted, but the resulting numerical delta in the published
  `cpcv` block of `hedge_trial_2026-09-01.json` was NOT recomputed. Those numbers are suspect;
  how wrong they are is unmeasured.

## NOT VERIFIED

- No file outside this memo was modified, and no test under `tests/` was run (per-file rule).
- `corpus_cache.py` was read only at the signature/staleness level (`_source_manifest:67`,
  `load_gate_corpus:278`); its four `_build_*` joins were not audited.
- `run_gate.py`, `close_join.py`, `golden_loader.py`, `combo_runner.py` and
  `kernel/validation/proof_metrics.py` are OUTSIDE the commissioned scope; they were read only
  far enough to answer the ten questions and to status the prior red team. `kernel/**` is
  human-gated -- nothing there was touched or proposed as a direct edit.
- `combo/stack_gate_pregame.py` and `combo/batch_gate.py` were not red-teamed, so RT-9's
  downstream consumer is not traced to a live call site.
- Every "smallest fix" column is a PROPOSAL. None has been implemented, tested or landed by
  this lane, and none should be applied without its own spec, register id and verifier pass.
- No S-id was allocated. The orchestrator numbers the register rows.
