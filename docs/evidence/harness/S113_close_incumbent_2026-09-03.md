# S113 -- the pregame factory's nba/mlb incumbent becomes the market close (opt-in), and 147 of 240 Elo-relative promotions vanish (2026-09-03)

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S113 (harness).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked in section 7).
Calibration language only. A SCREEN is a NON-FINDING. **NOT VERIFIED** -- this is the lane's own
report; no independent verifier has re-run it.

---

## VERDICT

**NULL on both sports, and the promotion list is mostly an artifact of the Elo reference.** With the
S112 market close as the incumbent, 10 of 945 nba+mlb screens beat it at all (against 725 of 977 that
"beat" Elo on the same code and the same seeds), the best improvement in ANY of the 11 families is
`+0.000640` with a cluster-robust 95 pct CI of `[-0.003011, +0.004291]` -- straddling zero and under
the `+0.004` bar -- and **147 of the 240 Elo-relative promotions (61.3 pct) do not survive the switch**.
Against the historical S58 promotion list, **92 of its 140 nba/mlb promotions vanish**.

No prereg DRAFT is written: no arm clears `+0.004` vs the close with a CI excluding zero.
Uncharged -- `_charge_ledger` never called, `data/cache/eval_gate/backtest_fwer.jsonl` never opened
(18 rows, md5 `a4ae7c13995672e478d59770591b83ba` before and after), `data/registry/` untouched, no
flag flipped ON, nothing read or written under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/`. The pod's live `gate_corpus_{nba,mlb}.parquet` were never rewritten.

---

## 1. STEP 0 -- PREMISE (Q8): HELD

The exact lines that picked the incumbent, read on disk before the change
(`scripts/platformkit/foundry/screen_predictor.py` at 277bfa90b):

* line 37 -- `INCUMBENT = {"soccer": "devig_close", "tennis": "devig_close", "nba": "p_base", "mlb": "p_base"}`
* `corpus_states`, nba/mlb branch -- `rows = rows[rows["y"].notna() & rows["p_base"].notna()]` then
  `"devig_close_prob": float(row["p_base"])` for every state. `p_base == p_elo` byte-identically (S98),
  so the served incumbent WAS Elo.
* return -- `return states, ..., INCUMBENT[sport]`, i.e. the literal label `p_base`.

Where the label goes: `corpus_states` -> `foundry_runner.screen_queue` -> `ScreenQueue.incumbent` ->
`foundry_runner._record`, which writes `row["incumbent"]` into the **trial JSON only**.
`results_db._RESULT_FIELDS` (results_db.py:36) does not list `incumbent`, so the sqlite `result`
table has **no incumbent column at all** -- the only corpus label a DB reader sees is
`result.corpus`, which says `nba` / `mlb` and cannot distinguish Elo from a close.
`promotion_report.screens` recovers the label by re-reading the trial JSON.

Incumbent handling is GENERIC downstream, as the row assumed: `grep -n incumbent` over
`foundry/tiers.py`, `foundry/promotion.py` and `foundry/results_db.py` returns **zero** matches.
`promotion.promote` ranks on `r.brier_model - r.brier_close` where `brier_close` is whatever the
served `devig_close_prob` scored (`tiers._run_screen`), so nothing but `corpus_states` decides what
"the incumbent" is.

**How much is Elo-relative** (counted, not asserted):

| source | nba | mlb | total |
|---|---|---|---|
| S58 screen DBs `data/cache/eval_gate/s58_screens/<sport>.sqlite`, `result` rows at tier T1 | 564 | 48 | **612** |
| S58 promotion list (`S58_promotion_list_2026-09-03.md`), nba/mlb families | 100 (5 families x 20) | 40 (2 x 20) | **140** |
| this lane's local control re-run (same code, `--frozen` seed, flag OFF) T1 rows | 889 | 80 | **969** |

The premise is NOT falsified: the incumbent read `p_base`, never `p_close`. (`p_close` did not exist
on the live corpora at all -- S112 wrote it to separate `_close` files.)

---

## 2. THE CHANGE (smallest additive)

`scripts/platformkit/foundry/screen_predictor.py` only (+37 / -5 lines, 332 total):

* `CLOSE_INCUMBENT_ENV = "FOUNDRY_CLOSE_INCUMBENT"` -- **default OFF**. `corpus_states(sport,
  close_incumbent=None)` reads the env when the keyword is None, so the pod run is byte-unchanged
  until the orchestrator exports the variable at relaunch. An explicit `close_incumbent=False`
  overrides the env (tested).
* ON, for nba/mlb only: the corpus becomes `load_close_corpus(sport, portable=...)` --
  `gate_corpus_{nba,mlb}_close.parquet` through `corpus_cache`'s own staleness/sidecar contract, so
  `FOUNDRY_PORTABLE_CORPUS=1` keeps working on a pod host -- and the rows are **restricted to
  `p_close.notna()`**. `devig_close_prob` is then `p_close`; `features.p_base` is untouched, so
  `p_base` stays screenable as a feature against the close.
* `incumbent_label` is built per `close_source` from `CLOSE_LABEL` and joined with `+` over the
  served rows. **DEVIATION from the row's wording, deliberate:** the row asked for
  `devigged_close` / `first_inplay_tick`. mlb's single source (`pre_first_pitch_two_sided`,
  `DEVIG_TWO_SIDED`) is labelled `devigged_close`. nba's pregame source
  (`pregame_last_tick_before_commence`) is a `VENUE_PROB_ONE_SIDED` quote that
  `close_join_nba_mlb.py` explicitly says "is NOT a devigged fair close and is never labelled one",
  so it carries `pregame_venue_close`, not `devigged_close`. Calling it a devigged close would have
  been the one thing in this diff that overstates the evidence.
* The six S112 close columns are dropped from the returned feature table when the flag is ON, so the
  incumbent can never be enumerated as a hypothesis about itself. Flag OFF the drop set is empty, so
  the table is unchanged.
* `INCUMBENT[sport]` (`p_base`) survives as the **labelled fallback** whenever the flag is off.

No bar moved (Q3/B10): `tiers._COVERAGE_FLOOR` is still `0.8` and now binds the RESTRICTED window;
`PromotionRule` still comes off `FACTORY_TIERS_SPEC_2026-09-03.md`
(`b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3`, top_n 20, seed 20260903), unedited.
One stale-comment fix in `foundry/family_combo_screen.py` ("nba/mlb carry NO close") -- prose only.

### Window before / after (the restriction, stated)

| sport | flag | states | screen side | **served window** | verdict side | screen partition sha |
|---|---|---|---|---|---|---|
| nba | OFF (Elo) | 1,814 | 867 | **800** | 947 | `1a32541d44aa7fcb` |
| nba | ON (close) | 952 | 499 | **499** | 453 | `1980f64c6a21fc1e` |
| mlb | OFF (Elo) | 39,162 | 19,589 | **800** | 19,573 | `ad743c924c7c4547` |
| mlb | ON (close) | 894 | 452 | **452** | 442 | `bee51ac662607eb5` |

The two OFF shas reproduce S58's exactly (`1a32541d44aa7fcb`, `ad743c924c7c4547`), which is the A2
check that the default path is unchanged.

### Tests -- `tests/platformkit/foundry/test_screen_predictor.py`, 5 passed in 9.77 s

Two new tests on a SYNTHETIC corpus (40 events, the close covering the last 12), no real data:
`test_close_incumbent_off_is_byte_identical_and_never_sees_the_close` (label `p_base`, every state's
incumbent equals its own `p_base`, no close column in the feature table, explicit False beats the
env) and `test_close_incumbent_on_uses_p_close_labels_it_and_restricts_the_window` (12 of 40 states,
a strict subset of the Elo window, every incumbent equals that row's `p_close` and none equals its
`p_base`, label `first_inplay_tick+pregame_venue_close`, close columns still absent from the table).
Also re-run: `test_family_combo_screen.py` 3 passed, `test_foundry_runner_s16.py` 7 passed,
`test_close_join_nba_mlb.py` 8 passed.

---

## 3. THE LOCAL FACTORY SCREEN

`seed_queue --frozen --sport <s>` into a scratch sqlite (nba 1,440 / mlb 486 enumerated), then
`foundry_runner --predictor real --sport <s> --screen-rows 800 --batch 200 --idle-exit` with a
scratch `--db`, `--trials-dir` and `--ledger`, `--allow-charge` NOT passed. Run twice: once with
`FOUNDRY_CLOSE_INCUMBENT=1` and once without (the control). Every promotion printed
`promotions_held ... reason=allow_charge_off`; `charges=0` on every pass; the scratch ledger files
were never created.

| | nba T0 COVERED / UNCOVERED | nba T1 | nba beat incumbent | mlb T0 COVERED / UNCOVERED | mlb T1 | mlb beat incumbent |
|---|---|---|---|---|---|---|
| control (Elo, n=800) | 889 / 191 | 889 | **718 / 889** | 80 / 42 | 80 | 0 / 80 |
| **vs close** (n=499 / 452) | 889 / 191 | 889 | **6 / 889** | 48 / 74 | 48 | **0 / 48** |

NBA coverage is unaffected by the restriction (889 covered either way); MLB loses 32 screens because
the whole `mlb_inning` family falls under the unchanged 0.8 coverage floor on the 452-row window.

### n T1 rows vs the close, and the BEST improvement per family with a cluster-robust 95 pct CI

Improvement = `Brier(incumbent) - Brier(model)`; positive means the screen beat the close. The CI is
the cluster-sum estimator over the corpus's declared cluster key, recomputed **from the archived
differential alone**.

| family | n screens (close) | beat the close | best improvement | 95 pct CI | n | clusters | screen DM p |
|---|---|---|---|---|---|---|---|
| mlb_bullpen_relief_chains | 32 | 0 | -0.003590 | [-0.007293, +0.000113] | 452 | 29 | 0.0677 |
| mlb_gate | 16 | 0 | -0.003621 | [-0.007494, +0.000251] | 452 | 29 | 0.0775 |
| nba_boxdetail | 250 | 0 | -0.001183 | [-0.004998, +0.002632] | 499 | 30 | 0.5480 |
| nba_carryover | 50 | 0 | -0.001444 | [-0.004579, +0.001691] | 499 | 30 | 0.3741 |
| nba_defender_rollup | 72 | 0 | -0.001399 | [-0.004228, +0.001429] | 499 | 30 | 0.3403 |
| nba_gate | 88 | 4 | +0.000263 | [-0.002933, +0.003459] | 499 | 30 | 0.8730 |
| **nba_opp_allowed** | 120 | 1 | **+0.000640** | [-0.003011, +0.004291] | 499 | 30 | 0.7338 |
| nba_player_adv | 48 | 0 | -0.000167 | [-0.004795, +0.004461] | 499 | 30 | 0.9440 |
| nba_player_value_features | 32 | 1 | +0.000178 | [-0.002319, +0.002674] | 499 | 30 | 0.8899 |
| nba_quarter_shape | 125 | 0 | -0.000506 | [-0.003827, +0.002814] | 499 | 30 | 0.7672 |
| nba_team_adv | 112 | 4 | +0.000263 | [-0.002933, +0.003459] | 499 | 30 | 0.8730 |

Best of all 11 families: `+0.000640` against a `+0.004` bar, CI `[-0.003011, +0.004291]` including
zero, DM p 0.73. **The expected null.** Distribution over all screens: 10 of 945 rows have
`delta < 0` (model better) vs 725 of 977 in the Elo control.

Note the sign flip on the S85 headline: `nba_player_value_features` was the family whose best
vs-Elo screen was `-0.005221` (an improvement of `+0.005221`); vs the close its best family member
improves by `+0.000178` with a CI straddling zero -- the same collapse S112 measured on that one
hypothesis, now measured across the whole factory.

### Promotions held vs the Elo-relative list

Same code, same frozen rule, same seeds; the only difference is the incumbent and the window.

| family | promoted vs Elo (control) | promoted vs close | Elo promotions that VANISH |
|---|---|---|---|
| mlb_bullpen_relief_chains | 20 | 20 | 12 |
| mlb_gate | 20 | 16 | 7 |
| mlb_inning | 20 | **0** | 20 |
| nba_boxdetail | 20 | 20 | 19 |
| nba_carryover | 20 | 20 | 8 |
| nba_defender_rollup | 20 | 20 | 4 |
| nba_gate | 20 | 20 | 15 |
| nba_opp_allowed | 20 | 20 | 14 |
| nba_player_adv | 20 | 20 | 10 |
| nba_player_value_features | 20 | 20 | 7 |
| nba_quarter_shape | 20 | 20 | 12 |
| nba_team_adv | 20 | 20 | 19 |
| **TOTAL** | **240** | **216** | **147 (61.3 pct)** |

`mlb_inning` disappears entirely (its members no longer clear the unchanged 0.8 coverage floor on
452 rows) and `mlb_gate` fills only 16 of 20 slots for the same reason; the other 24 lost slots are
the two effects together.

Against the **historical S58 list** (its hashes parsed straight out of
`docs/evidence/harness/S58_promotion_list_2026-09-03.md`):

| S58 family | promoted vs Elo (S58) | still promoted vs close | VANISH |
|---|---|---|---|
| mlb_gate | 20 | 13 | 7 |
| mlb_inning | 20 | 0 | 20 |
| nba_boxdetail | 20 | 1 | 19 |
| nba_carryover | 20 | 12 | 8 |
| nba_defender_rollup | 20 | 16 | 4 |
| nba_gate | 20 | 5 | 15 |
| nba_team_adv | 20 | 1 | 19 |
| **TOTAL** | **140** | **48** | **92 (65.7 pct)** |

The 48 survivors are survivors of a RANKING, not findings: every one of them is still behind the
close (only 10 of 945 screens are ahead at all, none by a margin whose CI excludes zero).

**No prereg is written.** Nothing clears `+0.004` vs the close with a CI excluding zero.

---

## 4. EVIDENCE PATHS (all in-repo, all exist)

* `scripts/platformkit/foundry/screen_predictor.py` -- the change.
* `tests/platformkit/foundry/test_screen_predictor.py` -- 5 passed.
* `docs/evidence/harness/S113/promotions_vs_close.md` -- the full 216-row close-relative promotion list.
* `docs/evidence/harness/S113/promotions_vs_elo_control.md` -- the 240-row Elo-relative control list
  (its shared families reproduce S58's best deltas exactly: nba_boxdetail -0.002244, nba_gate
  -0.002755, nba_carryover -0.001483, nba_defender_rollup -0.002747, nba_team_adv -0.002181,
  mlb_gate +0.002978, mlb_inning +0.004620).
* `docs/evidence/harness/S113/best_arm_differentials.csv` -- 5,395 rows (Q9): one row per scored
  event for the best arm of each of the 11 families, carrying `family, hash, event_id, ts, cluster,
  loss_model, loss_incumbent`. **A2: every improvement and CI in section 3 recomputes from this CSV
  alone to the printed digits.**
* Scratch (NOT in the repo, this session only): the four sqlite DBs and the trial JSONs under the
  session scratchpad `s113/`.

---

## 5. ORCHESTRATOR SECTION

**Ship to the pod (three items):**

1. `data/cache/combo/gate_corpus_nba_close.parquet` + `gate_corpus_nba_close.sources.json`
2. `data/cache/combo/gate_corpus_mlb_close.parquet` + `gate_corpus_mlb_close.sources.json`
3. `scripts/platformkit/foundry/screen_predictor.py` (this commit)

The two parquets are the S112 artifacts, unmodified by this lane. They are NOT tracked in git
(`data/` is gitignored) -- copy them, do not expect a checkout to bring them.

**Relaunch env for the pregame factory runner:**

```
FOUNDRY_CLOSE_INCUMBENT=1
FOUNDRY_PORTABLE_CORPUS=1      # already set on the pod; the close corpora carry S68 sidecars
```

Nothing else changes: the same `foundry_runner --predictor real --sport nba,mlb` command line, the
same spec, the same `--allow-charge` default (OFF). Without the env the pod behaves exactly as it
does today.

**Consequences the orchestrator should expect at relaunch:** the nba/mlb screen windows drop to 499
and 452 rows, the mlb T1 count roughly halves (mlb_inning stops clearing the coverage floor), the
`incumbent` field in every new nba/mlb trial JSON reads `devigged_close` or
`first_inplay_tick+pregame_venue_close` instead of `p_base`, and the screen partition shas for those
two sports change (`1980f64c6a21fc1e` / `bee51ac662607eb5`) -- a T2 charged against a pre-S113 nba/mlb
screen partition must not be mixed with a post-S113 one.

**Standing recommendation:** the 140 nba/mlb promotions on the S58 list should not be charged as
market-relative candidates. 92 of them are not on the close-relative list at all, and the 48 that
survive are behind the close.

---

## 6. WHAT THIS DOES NOT SHOW

* The nba close is a ONE-SIDED venue probability and 732 of its 952 covered rows are the FIRST
  IN-PLAY TICK (median 21 s after tip, S81), not a pregame price. It is a de-facto close and the
  label says so; it is not a devigged fair pregame line, and a screen that trails it is not thereby
  shown to trail a real pregame market.
* One window per sport, one corpus each: any AHEAD reached from here would be SINGLE-WINDOW (Q5).
  Nothing here is an AHEAD.
* The verdict side of the partition was never opened, so nothing here is a verdict.
* The control run is the same code and seeds as the close run but NOT the same run as S58: S85/S111
  landed as-of bridges after S58, which is why the control shows 969 T1 rows where S58 showed 612 and
  12 families where S58 listed 7 for these two sports. Both comparisons are reported separately above
  rather than blended.

---

## 7. CONTRACT SELF-CHECK

* **B1** no row was excluded after seeing its metric; the close-covered restriction is a property of
  the CORPUS (p_close present), fixed before any screen ran, and the excluded set is named (nba 862
  of 1,814 rows, mlb 38,268 of 39,162).
* **B2** additive only: `corpus_states` keeps its 3-tuple return and gains one optional keyword; the
  five callers (`foundry_runner`, `family_combo_screen`, `s108_features`, `s112_rescore_vs_close`,
  `s58_t2_first_trial`) were grepped and all unpack the same 3-tuple. No column renamed or removed;
  the six close columns are added to the corpus by S112 and dropped from the FEATURE table only.
* **B3** missing != bad: a row with no `p_close` is not quarantined, it is simply outside the
  close-covered window and stays fully available on the default (Elo) path.
* **B5** nothing was copied to the pod; section 5 is a shipping list for the orchestrator.
* **B6** no module moved or retired.
* **B10 / Q3** `_COVERAGE_FLOOR` 0.8, `top_n` 20, `partition_seed` 20260903, the `+0.004` bar --
  all byte-identical to master and to the spec. The coverage floor binds the RESTRICTED window and
  was not lowered to compensate; `mlb_inning` failing it is reported, not fixed.
* **Q1 / Q2** no prereg sealed and no ledger row appended, because nothing is claimed: every screen
  is a NON-FINDING and `--allow-charge` was never passed. K was never read.
* **Q4** every screen ran through `eval_gate.walk_forward` inside `tiers._run_screen` with
  `select_inside=True`; no meta-learner exists here.
* **Q5** not applicable -- no AHEAD.
* **Q6** calibration language only; no dollar, ROI, profit or edge word appears; none of the
  retracted figures appears anywhere in this memo.
* **Q7** `n = 11 families (CONSTRUCT)` for the per-family table -- every family that produced a
  close-relative screen is listed, none omitted. The screens themselves are n = 945.
* **Q8** premise re-measured and HELD (section 1).
* **Q9** the per-event paired-loss differential for every reported CI is archived in
  `docs/evidence/harness/S113/best_arm_differentials.csv` with cluster ids and timestamps, and the
  CIs reproduce from it alone.
