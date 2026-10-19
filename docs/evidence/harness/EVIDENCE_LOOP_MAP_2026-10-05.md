# Evidence loop map 2026-10-05 (evidence-loop lead, rows S761-S766)

PAPER ONLY. Calibration and execution-quality wording only. Question: what turns the nightly
receipts into (a) better probabilities and (b) better paper quoting and a truer fill model,
automatically and under pre-registration? Read-only map; every count below is from a receipt or
a file named in the row, read on 2026-10-05.

## 1. Nightly artifacts, consumers, decisions

| Artifact (writer) | Consumer | Decision it can change | Path | Pre-registered |
|---|---|---|---|---|
| nights/<D>.json (paper_night) | tick validator, issue scan, morning report | nothing (operations record) | automatic | n/a |
| schedules/<D>_maker_forward*.json (D1 tick) | every night step | capacity (which games are served) | automatic | capacity rule dated (S736) |
| qualification/<D>.json (forward_replay_qualification) | week step, coverage receipt, morning report | candidate promotion of a maker family (weekly floor 4 qualified games) | automatic, but NO game has ever qualified | S390 gates, yes |
| weeks/<YYYY>-W<NN>_maker_forward.json (forward_week_report) | morning report | family promotion streak | automatic; exits 3 every night (week INCOMPLETE: 09-30 and 10-01 qualification receipts are zero-byte files left by deadline kills) | yes |
| fill_realism/<D>.json (fill_realism, COUNTS ONLY) | morning report | fill-model parameter (in principle) | automatic write, MISSING consumer: no step reads it into a fill-model parameter or a quoting parameter | no (counts only) |
| scoreboard/<D>.json (ingame_scoreboard, sealed) | morning report, m2 read-out, s439 audit, coverage receipt, pooled reader (by hand) | model refit evidence; the nightly 30-game cell floor never clears (3-4 MLB games a night) | automatic per night; cumulative read MISSING (S503 needs a sealed window that does not exist; S721 prereg PROPOSED only) | per night yes; cumulative no |
| scoreboard/training/<D>.jsonl + manifest (history step) | next night's B/C fit and registry E fit | model refit (B, C, E) | automatic; window = nights D-7..D-4 (lookback 7, embargo 3) | yes (PREREG_2026-10-03 + amendment) |
| registry_e/<D>.json (registry_scorer_e_night) | morning report | candidate promotion (arm E vs C vs A) | automatic; E has scored 0 ticks on every night (training_history_absent 09-30, 10-02; block_incomplete 10-04) | yes (PREREG_E, BLOCK_CONFIG_E, CALLER_POLICY_E) |
| model2/m2/<D>.json, s439_audit (m2_readout) | morning report | read-out of arm M2 (PROJ on stale receipts) | manual (morning task runs it by hand) | yes (PREREG_M2) |
| coverage/<D>.json (S743) | morning report | capacity (served vs listed per sport) | manual (morning step 2b) | no (counts only) |
| latency/<D>_<D>_latency_ledger.json (S663) | nobody until today | quoting parameter (latency declared), fill model (stale-quote exposure) | MISSING until tonight: backfilled 09-24..10-03 and added as morning step 2d | spec bounds fixed before results (S663) |
| fill_realism/<D>_queue_sensitivity.json (S724) | nobody | fill-model parameter (queue arm) | manual, one run (10-02); needs 3 GB free and a census input | arms fixed before results |
| exec_policy/PREREG_S551.json (S551 sealed maker look) | nothing yet | quoting parameter (cancel arm), one confirmatory look at 30 paired games | MISSING: no qualified tape, no runner wired | yes |
| core/paper_exec_model.py, queue_model.py, latency.py, venue_rules.py (S693) | nothing (standalone) | fill model | MISSING: not called by any night or morning step | no |
| exec_receipt_step.py (S558 seam) | nothing (S558 PROPOSED night diff not applied) | execution receipts per night | MISSING: night steps pinned four ways (paper_night_edit_pins) | proposal only |

## 2. What the receipts say today (from the first roll-up, cumulative/2026-10-04)

- 10 nights with a receipt (2 COMPLETE); 29 MLB and 5 NFL games served; 0 qualified; 0 qualified decisions.
- Pooled C-minus-A (outcome target, S721 descriptive reader): MLB seal 801af61b 3 games, seal 6abb1a85
  (current) 1 game; every group INSUFFICIENT (floor 30). On the current seal C trails the mid on its
  one game (C was the constant 0.99475 from a one-game history, S744). Arm D: 0 ticks on every night.
- Latency (S663 ledger, MLB statsapi): our state receipt trails the play clock by 18.5-24.0 s at the
  median per night, and the venue book moved before our receipt on 29-62 pct of plays. The in-game
  state reaches us after the price has reacted, which is consistent with the measured finding that
  the in-game models trail the venue mid.
- 33 receipts on disk are NOT tracked by git (nights, scoreboard, qualification, fill_realism,
  registry_e after 09-26): the morning task's `git add` list omits them, so the private trunk, the
  cloud routines and any later reader do not hold the evidence. Missing link 1 below.

## 3. Missing links, ranked by evidence gained per night

1. EVIDENCE NOT COMMITTED (S761 morning step): receipts after 09-26 exist only on the laptop disk.
   Fix landed tonight as a morning-task step (roll-up lists every untracked receipt path; the step
   adds exactly those paths). Gain: every night's evidence becomes durable and readable by the cloud.
2. FITTED ARMS CAN NEVER LEAVE WARMUP AT LOOKBACK 7 (S766 + note on S746): the history window is
   nights D-7..D-4 (4 nights). MLB settled 6 games in the last 7 days, so the window holds about 3-4
   games; the decided S746 training floor of 20 settled games per sport can never be met, and B/C
   would read warmup on every night. The S746 seal must also declare a cumulative history (all
   settled games from a dated start, embargo kept) or the floor is dead on arrival.
3. NO CUMULATIVE READ (S761 built; S721 / S503 seals): one artifact now counts everything to date;
   a verdict still needs the S721 pooled prereg (or an S503 window) sealed. Projected at the current
   rate on the current MLB seal: 1 game, need 29 more (projection is past the MLB season end ~11-01).
4. NO QUALIFIED TAPE (owned by the capture-qualification lead, S732-S734): every execution measure
   (S551 look, fill model, queue arms) waits on the first qualified game.
5. EXECUTION MEASURES NOT ACCUMULATING (S765): latency ledger now nightly via the morning task;
   S724 queue sensitivity and S551 stay manual until a game qualifies (spec in S765).
6. QUOTING PARAMETERS SET BY HAND (S764 spec): no declared grid is compared on the same tape.
7. ARM E NEVER SCORES (registry E): every selected block must be present on the tick and on every
   training row; with lookback 7 / embargo 3 the E training set held at most 2 games (10-04).
   Same reachability fix as item 2; block-set change = new dated BLOCK_CONFIG via the seal calendar.
8. ARM D NEVER SCORES (S748, gated on S449): no state row carries a served probability.

## 4. Efficiency (night records 09-26..10-04; wall s and peak working set MiB)

| step | 10-04 | 10-03 | 10-02 | 10-01 | 09-30 | 09-29 | note |
|---|---|---|---|---|---|---|---|
| qualification | 29 / 93 | 158 / 206 | 164 / 128 | 903 / 98 (deadline) | 900 / 412 (deadline) | 514 / 484 | quadratic run fixed by S734/S750 today |
| fill_realism | 85 / 97 | 265 / 355 | 28 / 49 | refused RAM | 489 / 345 | 511 / 254 | |
| week | 0.5 / 20 | 0.5 / 20 | 0.5 / 20 | refused | 0.5 / 20 | 0.5 / 20 | exit 3 every night (INCOMPLETE) |
| scoreboard | 15 / 133 | 52 / 148 | 3 / 96 | refused | 109 / 189 | 1.5 / 77 | |
| history | 65 / 150 | refused RAM | 20 / 115 | refused | 50 / 132 | 59 / 131 | |
| e | 978 / 219 | refused RAM | 454 / 172 | 1802 / 134 (deadline) | 395 / 164 | 26 / 106 | SLOWEST; grows with the window |

Worst offender: step e (978 s of a 1,173 s night on 10-04; deadline-killed at 1,802 s on 10-01). It
re-reads every state and book shard of the 7-day window (plus D+1) from the capture archive every
night, although the night's books shard was already parsed by qualification, fill_realism and
scoreboard, and nights D-7..D-4 by history. Its code is identity-sealed (BLOCK_CONFIG_E
implementation_identity) and the budget is byte-pinned, so no fix is pin-safe tonight: row S766
(per-night population slice cached once, E reads only the new night). No small, measured, pin-safe
fix exists in the night tonight.

## 5. What changed tonight (S761, S765 morning steps)

Morning task steps 2c (latency ledger for each closed night) and 2d (cumulative roll-up + commit of
the untracked receipts it lists). Spec rows S762-S764, S766 in the register. Runbook:
docs/evidence/harness/CANDIDATE_REGISTRATION_RUNBOOK_2026-10-05.md.
