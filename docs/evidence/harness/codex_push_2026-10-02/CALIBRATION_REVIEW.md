There are **zero recorded COMPLETE/FITTED nights**, but there is a fitted scorer artifact for 09-30. The binding constraints are orchestration, capture coverage, training availability, and nightly sample floors. The reviewed evidence supports a projection against **our own stale receipt of the venue mid**; it does not establish additional calibration value over a fresh mid.

All paths below are repository-relative. `F` means `docs/evidence/forward`; `N(D)` means `F/nights/D.json`; `T(D)` means `F/scoreboard/training/D.manifest.json`. Proposed thresholds are explicitly identified as proposals.

**1. SCOREBOARD AS BUILT**

| Arm | Actual definition |
|---|---|
| A | Latest valid ticker-YES mid received by the state-receipt instant. No sealed maximum book age. |
| B | Ridge logistic forecast using logit(mid), on state-complete eligible rows. |
| B_lag | In this scoreboard, the preceding book receipt's raw mid. It is not the fitted lagged-mid arm used elsewhere in the historical evaluator. |
| C | Ridge logistic forecast using logit(mid) plus the declared sport-state features. |
| D | C plus reconstructed model probability; requires model-present training and evaluation rows. |
| E | Separate registry forecast using selected state, workload, and microstructure blocks. Its primary outcome-Brier comparison is E-minus-A; incremental comparison is E-minus-C. |
| M2 | Separate deterministic, event-aware anchor projection. Fresh rows equal A; eligible stale rows may project. Nothing is fitted in the current M2 seal. |

Sources: `scripts/platformkit/execution/ingame_scoreboard.py:198-231`; `scripts/platformkit/ingame/baseline_four_arm.py:70-125`; `baseline_four_arm_features.py:246-272`; `registry_scorer_e.py:155-173`; `F/model2/PREREG_M2.json#rule`.

The main seal fixes arms, feature vectors, eligibility, receipt deduplication, ticker orientation, information timing, regulation segments, training embargo, and inference floors. Its floor is **30 games**, with bootstrap intervals unavailable below **5 game clusters** (`scoreboard/PREREG_2026-09-24.json#policy.n_games,n_clusters`; `entry_timing/study.py:30-45`). Amendments additionally pin implementation hashes. Training uses earlier games settled strictly before the scored date minus **3 days**, excludes evaluation-game identities, and scales features using training rows only (`ingame_scoreboard.py:115-147`; `baseline_four_arm.py:95-110`; `baseline_four_arm_features.py:248-253`).

A night scores served schedule entries, joining state receipts to backward-as-of book receipts across adjacent UTC shards. It reports Brier and log loss by sport, regulation segment, arm, and target:

- `target=outcome`: forecasting loss against settlement.
- `target=mid`: agreement with the contemporaneous recorded mid, not outcome calibration.
- `C_minus_B`: paired state-feature increment.

Standalone A and C cells can contain different rows. Only comparisons explicitly formed on their intersection support paired interpretation (`ingame_scoreboard.py:226-245`).

The exact status predicates are:

- **COMPLETE:** nonempty step list, with every step `step_status="RAN"` and `reason is None` (`paper_night.py:255-260`).
- **FITTED:** a fresh, valid scoreboard output, no refused schedule rows, and at least one tick with a finite B/C/D probability (`paper_night_steps.py:142-174`; reconstructible-count predicate at `:88-103`).
- **COMPLETE/FITTED:** both predicates hold. This does not require every arm, settlement, or a sufficient evaluation sample.
- **Input-window complete:** `as_of >= D+2 midnight UTC` (`paper_night_inputs.py:39-48`). This is recorded separately and is **not** part of the COMPLETE predicate.

**2. WHY ZERO COMPLETE FITTED NIGHTS**

| Night | Specific recorded deficit | Classification |
|---|---|---|
| 09-24 | `N(2026-09-24)#reasons=["ceiling_exceeded"]`; qualification killed; artifact `bytes=0`; scoreboard `training_label=A_ONLY`, `no_fitted_arm=true`. | RAM ceiling and unavailable fitted forecasts. The recorded JSON decode error after termination does not independently prove capture corruption. |
| 09-25 | Qualification, fill, week, and scoreboard steps refused with `free_ram_below_floor`; scoreboard artifact absent. Capacity note lists **3 served / 3 not served**. | RAM deferral; separate schedule selection limit. Sources: night `steps`; `schedules/2026-09-25_maker_forward.json.capacity_note.json#served,not_served`. |
| 09-26 | Qualification, fill, week, scoreboard, and history refused for RAM. `qualification_inputs.per_sport.mlb` marks both 09-27 book and state shards false. E reports `config_not_effective`. | RAM deferral, missing adjacent-day capture, prospective seal timing. |
| 09-27 | No night receipt. `T(2026-10-01)#result.nights[date=2026-09-27]` reports `schedule_absent`. | Missing schedule record; nightly execution unverified. |
| 09-28 | No night receipt or served schedule found. | Unrecorded. An execution failure cannot be inferred from absent keys. |
| 09-29 | Scoreboard exits with `ValueError: amendment_mismatch`; output absent. E reports `config_not_effective`. Listed MLB/NFL adjacent-day shards are present. | Seal/code-version mismatch and prospective E timing. |
| 09-30 | Qualification killed for `step_deadline_exceeded`; artifact `bytes=0`. Scoreboard runs and reports FITTED, but overall night remains PARTIAL. | Processing deadline; fitted scoring succeeded separately. |
| 10-01 | No night receipt or scoreboard artifact. `T(2026-10-01)#result.complete=false`; historical inputs identify absent 09-27 shards and schedule. | Historical capture/schedule deficit; current nightly execution unverified. |

Inventory source: `Get-ChildItem docs/evidence/forward/nights -File` and `Get-ChildItem docs/evidence/forward/scoreboard -Recurse -File`.

Important separations:

- **Capture quality:** 09-29 qualification reports **0 qualifying games from 3 scheduled**, with `BOOK_CADENCE`, `COVERAGE_LOW`, `DECISIONS_LOW`, and `TAPE_INCOMPLETE` among the game refusal reasons. These maker qualification rules are separate from calibration inclusion (`N(2026-09-29)#steps[name=qualification].stdout_last_line`; `qualification/2026-09-29.json#games`).
- **Training supply:** `T(2026-09-30)#result.rows=2585`, but its historical 09-26 census has **6 unsettled games** and contributes no rows. Advancing the snapshot in `T(2026-10-01)` exposes missing adjacent-day inputs; the changed completeness flag alone is not a defect.
- **E timing versus fitting:** earlier E receipts explicitly refuse before `caller_policy.effective_from=2026-09-30`. On 09-30, production completes, but all **4767 rows** have `training_history_absent`, and `summary.n_games=0` (`registry_e/2026-09-30.json#rows,summary`).
- **Current fitted coverage:** 09-30 has **3156 B ticks, 3077 C ticks, and zero D ticks**, with B/C covering **3 games**. Command: `sum(t["arms"].get(a) is not None for t in d["ticks"])`, and the corresponding distinct-`game_key` count on `scoreboard/2026-09-30.json`.

Code/seal defects visible now:

- The 09-29 amendment pins scorer/rules hashes that differ from current bytes; the 09-30 pins match. This agrees with the recorded 09-29 refusal. Source command: LF-normalized `hashlib.sha256(path.read_bytes().replace(b"\r\n",b"\n"))`, compared with each prereg's `implementation`.
- The 10-01 NFL amendment exists, but the current selector omits it, the verifier still returns MLB/soccer eligibility, and `CORPUS` omits NFL. Its rules/features pins also differ from current bytes. This is a current integration discrepancy, not proof of an unrecorded 10-01 run (`ingame_scoreboard_night.py:30-34`; `ingame_scoreboard_amendment.py:105-115`; `ingame_scoreboard_rules.py:140`).
- Terminal states can be scored before the final receipt arrives. The integrity audit identifies **9 terminal ticks** on 09-24 (`model2/s439_audit/2026-09-24.json#census.sports.mlb.terminal`).
- R2's adjacent-day reader can miss corrected finals arriving later, as recorded in `HARNESS_GAPS_2026-09-03.md:762`.

**3. STATISTICAL POWER**

There is no established positive rate of complete fitted nights. The recorded fitted scorer yield is **3 games across the 8 requested calendar dates**, or **0.375 games/date**; missing receipts prevent treating this as a stable capture rate. Conditional arithmetic gives **80 calendar dates** for a new pooled sample of 30 at that recorded yield, versus **10 successful collection nights** at 3 eligible games/night.

Arithmetic command:

```text
python -c "import math; print(3/8, math.ceil(30/(3/8)), math.ceil(30/3), math.ceil(30/2), math.ceil(90/3), math.ceil(250/3))"
```

| Sealed estimand | Declared floor and current support | Time to readable floor |
|---|---|---|
| S439 arm losses and C-minus-B, per sport/segment/target/night | Floor 30; current fitted live-segment cells have 3 games, pre-live 2. | **Never by accumulating nights:** each output resets its evaluation population. |
| D outcome comparisons | Current prediction yield zero. | No finite projection at this rate. |
| E-minus-A / E-minus-C nightly outcome Brier | Floor 30; current scored fitted support zero. | No finite projection. Even repaired training cannot overcome a small nightly population through waiting. |
| M2 cumulative stale/live headline | Floor 30; no prospective readout found. | No measured finite projection. Conditionally 10 nights at 3 stale-eligible games/night. |
| M2 MLB headline | Seal forces `INSUFFICIENT`. | **Never under this seal**, regardless of count. |
| R2 late-entry reliability residual, separately by sport | Admission floor 30; register reports September late-window coverage 0/12. | No positive observed qualifying yield; no finite projection at that yield. Conditionally 10 nights at 3 admitted games/night. |

Sources: S439 `cells[].brier.n_games`; E `PREREG_E_2026-09-25.json#policy` and `registry_scorer_e_night.py:183-196`; M2 prereg `constants.floor,mlb_insufficient,rule`; R2 prereg `floor,population,looks`; register `:762`.

The R2 admission floor is not a power guarantee. Its declared planning table gives detectable reliability deviations of **0.14 at 30 games, 0.08 at 90, and 0.05 at 250**, under its stated assumptions (`late_game/PREREG_R2.json#mde,mde_label`). At a hypothetical yield of 3 admitted games/night, those counts require **10, 30, and 84 nights**, respectively, from the arithmetic command above. The plan's approximate MLB postseason ceiling of **53 games** makes the latter two targets unreachable in that cohort even before band exclusions (`INGAME_MODEL_2_PLAN_2026-09-29.md:198-199`).

The cheapest honest redesign is a **new additive prereg**:

- Pool prospective nights within sport, venue, seal identity, information timing, and fixed eligibility.
- Give each game equal total weight; keep all its ticks and episodes in one cluster.
- Declare one primary paired outcome-Brier contrast; log loss and regime splits are secondary.
- Keep existing nightly outputs intact; historical development rows cannot become prospective confirmation.
- Use a proposed admission floor of **30 games** and a fixed final look at **90 games**, separately by corpus. These counts follow the existing floor/planning table.
- Sequential boundary: interim reports remain descriptive; **no early efficacy stopping**. Permit one final inferential look at the declared count or deadline. A deadline below the floor remains insufficient.
- Require independent replication before generalizing. Increasing tick counts does not increase independent-game support.

**4. WHERE A MODEL COULD STILL ADD CALIBRATION VALUE**

The current evidence supports the narrower staleness question. S542 records `ACCEPT_STALENESS_BACKSTOP_ONLY`; the amended plan rejects a resolved improvement over fresh price and withdraws the earlier late-tail interpretation (`S542_anchor_projection_replay_2026-09-29.json#verdict`; model plan `:254-269`). This does not prove all future fresh-book candidates impossible, or establish the fitted B/C arms as successful backstops.

The following are **proposed tests**, not findings. Minimum admission is 30 independent games per regime/corpus; confirmation requires independent replication and adequate interval precision.

| Opportunity | Data on disk | Leak control and falsification |
|---|---|---|
| Our stale-book intervals | Scoreboard `mid_age_us`, paired losses, native book/state receipts; S542 replay; E quote-age fields. | Compare on identical rows against carried A. Retain current fresh A as a separate comparator. Falsify incremental calibration if the paired Brier interval establishes no reduction; an interval spanning zero remains unresolved. |
| Actual halts | Native `market_state`, touch/book validity, linked state and settlements. | Establish explicit halt status first; null/empty books alone are insufficient. Compare frozen-prior/state fallback against last-valid-mid carry. Falsify if fallback has no resolved Brier reduction or worsens log loss. Actual halt sample size is unverified. |
| Thin or one-sided markets | Regime census R6, spread, depth/imbalance, trade counts; E microstructure support. | Freeze thinness definitions using development data; never select from realized loss. Existing R6 support is only **2 games** (`regime_census/2026-09-22_fix1c.json#pooled.regimes.R6.games_with_ge1_instant`). Same paired-loss falsification. |
| State changes inside feed lag | `last_play_ts`, state receipt times, event-response inputs, delayed S542 scenarios. | State becomes available only at receipt. Replay availability must use measured lag, not play time. MLB measured median lag is **21.8 seconds** (`probe_mlb_latency_stdout.txt`, `capture_ts-last_play_ts`). Falsify a state mechanism if its reduction disappears after delay or matches the state placebo. |
| End-of-game regimes | Final receipts, terminal audit, focus snapshots, R2 seal. | Remove terminal and post-final rows, including terminal states preceding final receipt. Freeze entry/band before outcome lookup. Falsify the proposed reliability distortion if the locked result detects none; do not resurrect the withdrawn historical tail claim. |

All tests need backward-as-of joins, delayed state availability, train-only fitting, settlement embargo, and truncation invariance. The event-response archive's observed quote-change lag is not measured venue reaction time: it includes sparse capture and censoring.

**5. TOP 6 IMPROVEMENTS**

All files below are proposed NEW files. Prefixes `P= scripts/platformkit/ingame/paper_calibration_additive/` and `O= docs/evidence/forward/calibration_additive/` were absent when checked with `Test-Path`. No existing seal-pinned file is owned by these specs. Numerical acceptance values below are proposed unless attributed to an existing seal/register.

```text
1. Availability and seal-chain audit
Goal: explain every missing calibration output without conflating production and fitting.
Owner: NEW P/availability.py; NEW O/availability_spec.json and dated receipts.
Inputs: night JSON, training manifests, schedules, preregs, implementation bytes.
Unit: night, with arm-specific prediction and settled-game counts.
Acceptance: every requested date gets a recorded, absent, or refused classification.
Threshold: zero unexplained classifications; preserve every refusal reason.
Minimum n: all requested dates; no statistical calibration conclusion.
Control: reconcile against raw JSON keys and LF-normalized pin hashes.
Buildable today: YES, from existing receipts; missing nights remain unknown.
Seal boundary: report discrepancies without changing selection or pinned code.

2. Additive pooled paired calibration reader
Goal: make multi-night game support readable without changing nightly estimands.
Owner: NEW P/pooled_reader.py; NEW O/PREREG_POOLED.json and receipts.
Inputs: saved probabilities/losses, settlements, terminal flags, source seals.
Unit: equal-weight game; deduplicate games spanning receipts.
Acceptance: paired Brier and log loss, support counts, and deterministic reconciliation.
Threshold: Brier upper interval below zero; log-loss upper interval at most zero.
Minimum n: proposed 30-game admission and 90-game final look per corpus.
Control: same-row A; no efficacy stopping before the final look.
Buildable today: YES for descriptive reconstruction; prospective confirmation waits.
Seal boundary: historical rows remain development; original outputs remain intact.

3. Receipt-age and selection coverage census
Goal: distinguish fresh-price calibration from stale-receipt and selected-game results.
Owner: NEW P/coverage_age.py; NEW O/coverage_age_spec.json and receipts.
Inputs: mid_age_us, arm availability, full/served schedules, observation support.
Unit: game plus fixed receipt-age strata, separately by sport and venue.
Acceptance: every arm reports row intersection, age distribution, and excluded games.
Threshold: no outcome headline below the existing 30-game floor in its stratum.
Minimum n: census every available game; inference requires the stratum floor.
Control: full scheduled population and conservative missing-game Brier bounds.
Buildable today: YES; follows register S684 at HARNESS_GAPS line 794.
Seal boundary: propose age eligibility only in a new prereg.

4. Delayed-state staleness falsification
Goal: test whether projection improves calibration against our carried stale receipt.
Owner: NEW P/stale_replay.py; NEW O/PREREG_STALE_REPLAY.json and receipts.
Inputs: S542 rows, native timestamps, measured lag, scoreboard paired rows.
Unit: game; preserve event-aware anchoring and separate actual from simulated lag.
Acceptance: delayed-state paired losses and placebo comparisons reproduce.
Threshold: Brier upper interval below zero versus carry and versus placebo.
Minimum n: proposed 30 eligible games in each independent evaluation corpus.
Control: fresh A, unchanged-state placebo, and no projection after an event repricing.
Buildable today: YES for historical falsification; live NBA delay remains unverified.
Seal boundary: new replay only; do not alter M2 or reinterpret its MLB headline.

5. Halt, thin-market, and terminal eligibility audit
Goal: establish which difficult regimes can support an honest calibration experiment.
Owner: NEW P/regime_support.py; NEW O/regime_support_spec.json and receipts.
Inputs: book status/depth, R6 census, focus coverage, finals and terminal flags.
Unit: game; episodes and ticks are descriptive support only.
Acceptance: explicit halt evidence; fixed thinness; terminal/post-final exclusions.
Threshold: zero terminal/post-final admissions; unsupported status is UNKNOWN.
Minimum n: proposed 30 eligible games per regime before a calibration comparison.
Control: last-valid-mid carry; compare newer invalid books against older valid books.
Buildable today: YES for census; halt inference and sufficient samples are pending.
Seal boundary: preserve R2's population, lock, and existing final-reader limitation.

6. Reliability, sharpness, and decay report
Goal: make calibration uncertainty and feature health visible beside paired loss.
Owner: NEW P/reliability_health.py; NEW O/reliability_health_spec.json and receipts.
Inputs: game-weighted predictions/outcomes, missingness and receipt-age distributions.
Unit: game; retain sport, venue, arm, and seal identity.
Acceptance: reliability decomposition, sharpness, and interval uncertainty are printed.
Threshold: proposed stationary false-flag share at most 5 percent over 200 seeds.
Minimum n: proposed 90 evaluation games; smaller reports remain descriptive.
Control: stationary/null probes, same-row A, and missing inputs reported UNKNOWN.
Buildable today: YES for descriptive reports; monitor acceptance is not verified.
Seal boundary: additive report following S688 and S701, never a production switch.
```

The requested register review supports these priorities: S640-S642 are recorded landed; S643 is unsealed and closed at limit, with S646 its open successor; S644 retains capture/final-reading limitations; S645 documents cadence limits. S672, S684-S689, and S701 remain open. Registry sources: `HARNESS_GAPS_2026-09-03.md:723-725,761-763,782,794-800,813`. Their recorded validations were not rerun.

**6. NOT VERIFIED**

- No tests, scoring jobs, network calls, or file mutations were performed.
- Native data shards were not streamed or rehashed; this review used code and small evidence artifacts.
- Missing night receipts do not establish whether a run occurred.
- A stable prospective qualifying-game rate, sufficient halt sample, and independent second-venue comparison are not established.
- S542 explicitly leaves NBA clock alignment, price-point semantics, and actual live-feed delay unverified (`#disclosures,not_verified`).
- Intel-prior availability is reconstructed, not proven live (`intel_prior/2026-09-23_r1_join_fix1b/census.json#asof_kind`).
- None of the proposed thresholds, sequential rules, or redesigns has been implemented or validated.