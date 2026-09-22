# S402 real reconciliation run on the AMENDED draft, 2026-09-22 (counts, hashes and statuses only; tracked evidence for do-not-seal item 6)

Run: the landed seal package (5bab58a3e) over the amended, UNSEALED S382 draft (commit 028e495f4) with --allow-open and a scratch
--out; the orchestrator's Opus agent ran it at about 21:10Z; nothing sealed, no seal line written. Source JSON: the session
scratchpad s402c/s402_report.json (docs JSON is gitignored by pattern, so its facts are transcribed here verbatim).

status: DRAFT_OPEN_ITEMS | seal_line_written: False | allow_open: True | text_written: True
differing_keys: [] | corpus_refusals: {} | missing_pins: ['auditor'] | open_items: 11 | open_placeholders: 1

## reconciliation
- corpus_bytes: {"corpus": 169404513, "readiness": 169404513}
- eligible_games: {"census": 1593, "corpus": 1593, "readiness": 1593}
- eligible_ticks: {"census": 221066, "readiness": 221066}
- excluded_post_final: {"census": 244183, "readiness": 244183, "reason": 244183}
- files: {"census": 1593, "corpus": 1593, "readiness": 1593}
- games: {"census": 1593, "corpus": 1593, "readiness": 1593}
- manifest_sha256: {"corpus": "5c4c1d109278c9262fbba1157d0d49afd6af16d2e9ead447b38baeb3526fd9a5", "readiness": "5c4c1d109278c9262fbba1157d0d49afd6af16d2e9ead447b38baeb3526fd9a5"}
- ticks: {"census": 465249, "readiness": 465249}
- unique_keys: {"census": 465249, "readiness": 465249}

## frozen
- ARM_D_STATUS: "DESCRIPTIVE_ONLY (S392 disposition)"
- CORPUS_BYTES: 169404513
- ELIGIBLE_GAMES: 1593
- ELIGIBLE_GAMES_SHA256: "04c182de96f7433ee1e65d355102e82dcd58693f960bac266d62ef7c66453805"
- FOLDS: 311
- MANIFEST_SHA256: "5c4c1d109278c9262fbba1157d0d49afd6af16d2e9ead447b38baeb3526fd9a5"
- PERIOD_SUPPORT: "{\"1\":{\"games\":1592,\"ticks\":44428},\"2\":{\"games\":1593,\"ticks\":68825},\"3\":{\"games\":1593,\"ticks\":52645},\"4\":{\"games\":1593,\"ticks\":284586},\"overtime\":{\"games\":81,\"ticks\":14765}}"
- PRIMARY_GAMES: 1570
- PRIMARY_GAMES_SHA256: "3d1344bf1cc123da915d911c84c1a911ed88df922902a65fb18570f6abe838c9"
- S58_SCORED_GAMES: 1593
- S86_EXPOSED_GAMES: 797
- WARMUP_FOLDS: 5
- WARMUP_GAMES: 23

## pins
- period_module: c6600afd1b2aaabd2451da6eaa558ba1cfae1ad0
- scorer: c6600afd1b2aaabd2451da6eaa558ba1cfae1ad0
- trial_runner: 2df397247a57d0700160223fe13debaefd92de5d

## placeholders
- 0: {"anchor": "_grade_joined/nba_checkpoints_r1. canonical per-file manifest sha-256:", "key": "manifest", "line": 94, "status": "FILLED", "value": "5c4c1d109278c9262fbba1157d0d49afd6af16d2e9ead447b38baeb3526fd9a5"}
- 1: {"anchor": "urce archive hashes, converter/scorer/model versions and corpus bytes:", "key": "corpus_pins", "line": 101, "status": "FILLED", "value": "manifest SHA-256 5c4c1d109278c9262fbba1157d0d49afd6af16d2e9ead447b38baeb3526fd9a5; corpus bytes 169404513; period_module=c6600afd1b2aaabd2451da6eaa558ba1cfae1ad0; scorer=c6600afd1b2aaabd2451da6eaa558ba1cfae1ad0; trial_runner=2df397247a57d0700160223fe13debaefd92de5d"}
- 2: {"anchor": "exposure-restricted and d-paired fold/game/tick denominators:", "key": "exposure_d", "line": 118, "status": "FILLED", "value": "eligible games 1593 / eligible ticks 221066; arm D paired ticks 109108 (model_prob missing for D 348757); excluded ticks 244183, all post_final; folds 311, warm-up folds 5; arm D DESCRIPTIVE_ONLY per S392; S86 exposed games 797, S58 scored games 1593"}
- 3: {"anchor": "cohort counts, including period support within exposure and d subsets:", "key": "period_support", "line": 179, "status": "FILLED", "value": "{\"1\":{\"games\":1592,\"ticks\":44428},\"2\":{\"games\":1593,\"ticks\":68825},\"3\":{\"games\":1593,\"ticks\":52645},\"4\":{\"games\":1593,\"ticks\":284586},\"overtime\":{\"games\":81,\"ticks\":14765}}"}
- 4: {"anchor": "l bars and min_corpora_eff at that k. launch values not yet available:", "key": "launch_values", "line": 230, "status": "OPEN"}
- 5: {"anchor": "ently rename the corpus. unknown complete source/model/version hashes:", "key": "corpus_pins", "line": 252, "status": "FILLED", "value": "manifest SHA-256 5c4c1d109278c9262fbba1157d0d49afd6af16d2e9ead447b38baeb3526fd9a5; corpus bytes 169404513; period_module=c6600afd1b2aaabd2451da6eaa558ba1cfae1ad0; scorer=c6600afd1b2aaabd2451da6eaa558ba1cfae1ad0; trial_runner=2df397247a57d0700160223fe13debaefd92de5d"}
- 6: {"anchor": "e folds and training sizes, exposure-subset and d-paired denominators:", "key": "exposure_d", "line": 270, "status": "FILLED", "value": "eligible games 1593 / eligible ticks 221066; arm D paired ticks 109108 (model_prob missing for D 348757); excluded ticks 244183, all post_final; folds 311, warm-up folds 5; arm D DESCRIPTIVE_ONLY per S392; S86 exposed games 797, S58 scored games 1593"}

## do_not_seal (index | status | item)
- 1 | OPEN | S383 period-stratified scorer extension landed and its bootstrap behavior frozen.
- 2 | OPEN | Eligibility amendment landed: live exclusion, strict probabilities, full A/B/C population and identical-key D-paired comparisons; r1 corpus mapping resolved.
- 3 | OPEN | Venue-time parser amendment landed: timestamp() routes ts and close_ts through scripts.platformkit.execution.venue_time.parse_venue_time; four- and five-digit fraction regressions pass for both fields. Today's six-digit NBA output makes the defect latent for this corpus, not grounds to seal with it unresolved.
- 4 | OPEN | Integral NBA state amendment landed: quarter, home_score and away_score are finite INTEGRAL values; booleans and fractions are refused with counted reasons. Regressions cover the fractional-quarter post-final bypass and fractional source scores, plus all state-validation cases specified in eligibility above.
- 5 | OPEN | S385 provenance memo available and D's permitted interpretation resolved.
- 6 | OPEN | Census rerun byte-identical, complete manifest pinned and amended denominators reconciled; exposure identities and S58/S86 decision frozen without new scores.
- 7 | OPEN | MLB trial verdict read and its auditor S379 available; comparable MLB/NBA estimands and exposure constraints reviewed before a two-corpus conclusion.
- 8 | OPEN | The orchestrator reviews this draft and commits the eventual seal before metrics; ONE trial is charged and launch K is recorded before any authorized score.
- 9 | OPEN | The period module emits the declared primary contrast C_minus_B for both metrics, computed through the reported cells' own machinery and weighting, and the trial runner selects it as primary with C-minus-A beside it as SECONDARY; landed with per-file tests before sealing. Closing row: S417.
- 10 | OPEN | The B_lag arm is landed end to end -- eligibility counting no_prior_tick_for_b_lag, scorer arm and paired losses, period cells on the B_lag subset, auditor arm inventory -- or this amendment is withdrawn from the text before sealing. It is never dropped silently after the trial. Closing row: S417.
- 11 | OPEN | S405 landed (D_minus_C for both metrics and d_subset.scored_keys) and the S395 auditor landed with its primary reconstruction pointed at the declared primary contrast, so the charged trial has no producer gap. Closing row: S417 (with S405 and S395).

warmup_games: 23

NOT VERIFIED: the run used --allow-open (every item OPEN at run time); the auditor pin does not exist (S395 unlanded);
this note transcribes the report and adds nothing.
