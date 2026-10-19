# Candidate predictor registration runbook (registry E and the scoreboard arms), 2026-10-05

PAPER ONLY. Calibration wording only: a candidate is kept or dropped by its paired loss against
the venue mid under a sealed rule; an honest INSUFFICIENT or "trails the mid" is a valid result.
Map and ranked gaps: docs/evidence/harness/EVIDENCE_LOOP_MAP_2026-10-05.md.

## What is registered now (receipts of 2026-10-04)

| Arm | Where | What it is | Standing |
|---|---|---|---|
| A | scoreboard + registry E | venue YES mid (not devigged) | reference arm |
| B, C, B_lag | scoreboard (ingame/baseline_four_arm*.py, PREREG_2026-10-03 amendment) | ridge fits refit each night on the history window | INSUFFICIENT; C trails the mid on the one current-seal game (constant 0.99475 from a one-game history, S744) |
| D | scoreboard | served model probability | 0 ticks ever (S748, gated on S449) |
| C (registry E) | PREREG_E_2026-09-25 c_fields mid, inning, outs, score_home, score_away | fitted control | rows emitted; no paired verdict (floor 30) |
| E | BLOCK_CONFIG_E_2026-09-30: mid, team_state, microstructure, player_pitcher_workload, half_inning, base_occupancy, ball_strike_count | feature-rich fit | 0 ticks scored on every night (training_history_absent 09-30, 10-02; block_incomplete 10-04; max train games 2) |
| M2 | PREREG_M2.json (model2 read-out, morning task) | A on fresh receipts, PROJ (S542) on stale | MLB INSUFFICIENT by declaration through 2026; NBA from the opener |

Registry E scores MLB only (population counts other sports as unsupported_sport).

## How a candidate gets in (no step is pure config tonight)

1. Research module lands first (PREPARE only, walk-forward evidence, two verifier tiers), in
   scripts/platformkit/ingame/ or execution/. It must be causal: every input strictly before the
   scored tick, training rows settled before night minus the embargo (3 days).
2. Decide the vehicle:
   - New FEATURE BLOCK for arm E (same arms A/C/E, same PREREG_E): write a NEW dated
     docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_<date>.json (policy.effective_from, selected_blocks,
     selected_block_versions, manifest_hash, implementation_identity over the registry files listed in
     registry_scorer_e_config.py; inner sha256). The night chooses the block config through
     paper_night_budget.json producer args, whose bytes are pinned (S485, S501): the switch is a
     dated budget change through the seal calendar (paper-desk-improve), never an ad hoc edit.
   - New ARM (anything that is not a block of E, e.g. a recalibration of the mid or a prior): a NEW
     dated prereg (arms, fields, floors n_games 30 / n_clusters 5 unchanged, embargo, fit path,
     bootstrap seed) committed ALONE as seal commit A, effective the next UTC day; commit B wires it
     the day after, only after the previous receipt exists. Never two identity changes in one night.
3. Before either commit: grep docs/evidence/forward/**/PREREG*.json and the S515 memos for every
   basename you touch; run the four paper_night pin test files one at a time (memory note
   paper_night_edit_pins_2026_10_05); `contract_preflight --paths <files> --base master --spec <spec>`
   zero FAIL.
4. Scoring is then automatic: the night writes registry_e/<D>.json or scoreboard/<D>.json; the
   morning roll-up (cumulative/<D>.json, step 2c) counts its ticks and pooled games to date and
   projects its floor. The verdict needs the pooled window sealed (S721 prereg or an S503 window);
   until then every read is descriptive and labelled development.

## The refit path checked end to end (receipts 09-29..10-04)

- History admission: scoreboard_history.chronology(night, lookback 7, embargo 3) gives nights
  D-7..D-4 (four nights); the scoreboard of D fits on training/<D>.jsonl. 10-04 fit on 1 settled MLB
  game; 10-03 history was refused (free_ram_below_floor); 10-02 passed no history file.
- Embargo: 3 days (ingame_scoreboard.POLICY fit embargo_days; PREREG_E embargo_days) - respected.
- Floors: verdict floor 30 games per cell (POLICY n_games). Training floor: none today (S744); S746
  decided 20 settled games per sport with both outcomes. REACHABILITY: a four-night window holds
  about 3-4 MLB games at the current rate (6 settled in the last 7 days), so a floor of 20 is never
  met at lookback 7. S746's seal must carry a cumulative history (row S766).

## Candidates ready for a dated seal (spec rows, not built)

- S762: late-window mid recalibration arm from S644 (ingame/late_game_calibration_r2*.py, Prelec
  band map). Registered ONLY if the sealed S644 R2 read-out (PREREG_R2.json) returns OVERPRICED_LOSER
  or UNDERPRICED_LOSER; its prior is about 70 pct CALIBRATED, in which case the row closes as an
  honest null. Vehicle: new arm, new dated prereg.
- S763: pregame intelligence prior block from S423 (ingame/intel_prior_arm.py, intel_prior_join.py:
  C_intel and C_intx on identical folds, leak fix landed, r1 census committed). NBA first (opener
  10-20); needs registry E to admit NBA. Vehicle: new arm in a successor prereg.
- Not new: PROJ (S542) is already scored prospectively as M2 under PREREG_M2.
