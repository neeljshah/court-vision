# S779 -- NBA + soccer scoring readiness for the first all-games nights (2026-10-06)

Owner: NBA + soccer scoring readiness lead (dispatcher 2026-10-06 ~00:5xZ). PAPER ONLY.
Calibration wording only: every number below is a count, a refusal reason or a Brier /
log-loss cell; nothing here is a scored result in any other sense.

Goal under test: from the 10-07 schedule (switch 1, aa8b4b586) the desk serves nba
(preseason) and soccer rows. By the night that scores day 10-07 (06:05Z 10-08) those rows
must be SCORED by the night (qualification, fill realism, scoreboard arms A..D + settlement,
registry_e) rather than refused, without breaking the seal chain.

## 1. Premise check (fresh reads, master dc133cc21)

1. The scorer already supports both sports. ingame_scoreboard.py:32-43 declares nba and soccer
   feature tuples and regulation clocks; ingame_scoreboard_rules.py:54-62 segments nba
   (period / clock_sec) and soccer (minute clock); :141 CORPUS maps nba -> nba and
   soccer -> soccer_intl; :89-105 ticker_outcome settles a draw as 0 for the ticker.
   baseline_four_arm.py:53 and baseline_four_arm_eligibility.py:43 make nba model-optional
   in code; the live seal PREREG_2026-10-03 and the candidate PREREG_2026-10-07 list
   model_optional_sports mlb, nfl, soccer ("nba already model-optional").
2. The night dispatches every sport it finds in the population. paper_night_inputs.py:101-129
   loops `for sport in sorted(population)` and dispatches a sport whose day-D book and state
   shards exist; the scoreboard argv carries `--sports *plan["sports"]`
   (paper_night_steps.py:297). There is no sport allow-list on the night path.
3. The rehearsal memo (REHEARSAL_NBA_NIGHT_2026-10-05.md) did NOT see an nba refusal by the
   scorer: the nba row was scored by arm A (23 pre-live ticks), stayed unsettled (no final in
   the window), and its contrast read INSUFFICIENT (n_games 0). Its qualification verdict was
   FAIL on data reasons, because the box slept through the game (no book rows in the focus
   hour). The only sport refusal by name was registry_e unsupported_sport.
4. Soccer has NO game day before 10-09. Every open soccer event in the books archive is dated
   26OCT09 or later (books soccer/2026-10-05.jsonl: OCT09 474 rows ... OCT19 612 rows) and no
   soccer state row in the archive has status live (09-28..10-05: pre or final only; the finals
   of 09-28 / 09-29 have no book rows). The first soccer night is 06:05Z 10-10 (day 10-09).
5. Live nba preseason data exists tonight: state/nba/2026-10-05.jsonl + 2026-10-06.jsonl hold
   live and final rows for MEM at ATL, PHX at DET, NYK at PHI (start 23:00Z 10-05) and MIN at
   MIL (00:00Z 10-06); books nba/2026-10-05.jsonl holds 2,000-5,900 rows per ticker for them.
   This is the first real nba game window the night code can be exercised on.

## 2. Refusal map (step -> reason -> file:line -> hashed by a seal?)

| step | nba (preseason, from day 10-07) | soccer (from day 10-09) | hashed |
|---|---|---|---|
| planner (sport dispatch) | none: dispatched when both day-D shards exist (paper_night_inputs.py:118-121) | none today; WITH S534: refused `soccer_dependency_*` from night 10-09 if any of 8 orientation files drifts from the addendum (S534 adds paper_night_inputs.py:122-123) | no (paper_night_inputs.py is LOC-pinned, not sealed) |
| qualification | none by sport: per-game verdict; FAIL reasons are data reasons (COVERAGE_LOW, DECISIONS_LOW, STATE_GAP, BOOK_CADENCE, TAPE_INCOMPLETE; LINKAGE_INVALID counted at forward_replay_qualification.py:186 for book rows whose ticker is not the served ticker) | same code path | no |
| fill_realism | none: pooled counts read every dispatched shard (memo: nba shards read) | same | no |
| scoreboard arm A | scored (mid of the served home ticker) | scored, orientation via label_code on the yes_sub_title (ingame_scoreboard_rules.py:76-80, refusal `orientation_unresolved`) | YES (7-file seal) |
| scoreboard B / C / D | no fit until training rows exist: history excludes preseason by policy (nba_history_filter.py:24-31 `preseason_1`, POLICY regular_only_v1, S494) and the candidate seal adds a 20-settled-game floor per sport (S746); counted `model_not_reconstructible:<arm>` (ingame_scoreboard.py:236) | no fit until 20 settled soccer games exist (S746 floor); counted the same way | YES (policy + floor are sealed identity) |
| settlement | final state row -> ticker_outcome (ingame_scoreboard_rules.py:194-205) | same, draw = 0 for the ticker | YES |
| contrasts | INSUFFICIENT below 30 games (ingame_scoreboard_rules.py:135) | same | YES |
| registry_e (arm E) | refused by name: `unsupported_sport` (registry_scorer_e_night.py:109, `if entry['sport'] != 'mlb'`); PREREG_E_2026-09-25 c_fields are MLB fields (inning, outs, score_home, score_away) | same refusal | the refusal line is not in a hash list, but PREREG_E's c_fields / blocks are MLB-only by seal: an nba / soccer E is a NEW PREREG_E + NBA blocks (S482), a model change |
| history (training rows) | preseason rows excluded (`preseason_1`), counted in the manifest | admitted (soccer_intl corpus) | no (nba_history_filter.py), but the exclusion IS the S494 identity |

Answers to the four premise questions:
(a) No night step refuses nba or soccer by sport except registry_e (`unsupported_sport`,
    registry_scorer_e_night.py:109). Everything else scores them or counts data reasons.
(b) The scorer, segmentation, settlement, B/C/D populations and the training floor are in the
    seven seal-hashed files (PREREG_2026-10-03 / PREREG_2026-10-07). registry_scorer_e_night.py
    and every consumer (qualification, fill_realism, history, paper_night_*) are unhashed.
(c) S534: see section 4.
(d) Arms A + settlement for nba and soccer need NO change (config already in force from 10-07).
    B/C/D for nba preseason would need a policy change (admit preseason into training) =
    identity change, not config. Arm E for nba / soccer = S482 = new registry blocks + a new
    PREREG_E = model change. Neither is tonight's work; both are out of scope by the rails.

## 3. Design (what S779 is)

S779 is a READINESS ROW, not a scorer change:
- R1 (evidence): a scratch-root night over a real nba day (10-05, three live preseason games
  with book rows, as the served schedule plus nba rows) showing arm A ticks across live
  segments, settlement settled, qualification verdicts with counted reasons, registry_e
  `unsupported_sport` counted, and mlb / nfl outputs unchanged. Section 5.
- R2 (evidence): a scratch-root scoreboard pass over a real soccer row (a 10-09+ game with
  pre-live book and state rows) showing the soccer orientation path resolves (no
  `orientation_unresolved`) on real yes_sub_title labels. Pre-live only: no live soccer row exists.
- R3 (build, only if R1 / R2 expose a defect in an UNHASHED consumer): fix on
  cxp/S779-2026-10-06 with a test; nothing that changes what is scored or how.
- Out of scope (identity / model, recorded for the dispatcher): nba preseason into training
  (S494 policy), nba / soccer arm E (S482), any scorer edit (seal).

## 4. S534 (soccer night-path re-seal) -- what it still needs

State: VERIFIED, NOT LANDED; private parked/S534-h261-rebased 46e4ac4ce on base 1cdae0ee8.
Diff vs base: 13 files (addendum 8-file re-seal, soccer_dependency_gate.py NEW, label_words.py
NEW, cross_venue_link.py, paper_night_inputs.py +3 lines, soccer_s490_evidence.py,
test_soccer_data.py, two new tests, a fixture, memo + S534_memo.py, .gitattributes).
Measured 2026-10-06 00:5xZ: none of the eight dependency files and none of S534's other code
files changed on master since 1cdae0ee8 (`git log 1cdae0ee8..master -- <files>` empty except
.gitattributes), so the rebase is mechanical and `--seal` should reproduce the same digests.
Still needed: (1) rebase onto master (keep both .gitattributes blocks); (2) confirm the eight
digests; (3) its 16 test files one per process on the rebased tip; (4) land on its OWN night
(dispatcher order: 10-06, never the night of seal A / commit B), strictly before
2026-10-08T00:00Z; (5) re-verify the 8 hashes on main. Without it, soccer nights from 10-09
score under the S490 addendum with the known UCL label defect (Bayern v Manchester United
-> orientation_unresolved) and no runtime dependency gate.
Interaction with switch 1: S534's gate only refuses soccer when the files drift; with S534
landed and the files unchanged, soccer dispatches on 10-09 exactly as without it.

## 5. Evidence (scratch roots only)

Setup (2026-10-06 01:26Z-03:59Z): scratch worktree C:/Users/neelj/cv-s779-scratch at master
f59304241; books / state shards for days <= 10-05 hard-linked read-only from the live archive;
the 10-06 shards (mlb, nba, nfl, soccer) static copies taken 02:45Z trimmed to the last full
line; capture view = junctions to the scratch roots; scoreboard training rows, registry_e inputs
and all forward evidence copied in; scratch vault/S362 empty; nothing written to live roots.
Each variant restored from the same pristine copy (s779/pre) before its run. One process at a time.

R2 soccer (scoreboard only, ingame_scoreboard_night, day 10-05, as_of 10-06T00:00Z, 7 real
home-ticker games with real books + pre state: BVB, MCF, RCL, ARS, MUN (EPL), ATM, VIK (UCL v
BMU)): exit 0; 4,069 pre-live ticks, every one home_oriented; 0 orientation_unresolved, 0
tick refusals other than 82 book_absent; arm A and B_lag cells scored (pre-live, mid target);
7 unsettled (no finals yet); contrasts INSUFFICIENT; B/C/D model_not_reconstructible 4,069
(no history). Live soccer ticks and soccer settlement are NOT exercised (no live soccer row exists).

R1 nba night (paper_night entry point, --date 2026-10-05 --as-of 2026-10-06T06:00:00Z).
Variant A = live served schedule (1 mlb row, CWS at CLE). Variant B = A + the four real
preseason home-ticker rows MEM at ATL, PHX at DET, NYK at PHI (23:00Z), MIN at MIL (00:00Z)
in both schedule files (season_type 1, as the D1 writer emits them).

| step | A | B |
|---|---|---|
| dispatch | mlb 1 | mlb 1, nba 4, both dispatched, planner_reason none |
| qualification | RAN 77 s, CLE FAIL | RAN 161 s, CLE identical; 4 nba FAIL (data reasons) |
| fill_realism | RAN 393 s, row_count 76,818 | KILLED step_deadline_exceeded at 600 s (exit 15), no artifact |
| scoreboard | RAN 122 s | RAN 146 s, 5 games, 4 nba settled |
| history | refused as_of_future (scratch as_of later than wall clock; same both) | same |
| e | RAN 1,490 s, unsupported_sport 4 | RAN 1,419 s, unsupported_sport 8 |

Scoreboard, nba (B): settlement 4 of 4 settled (finals 431 / 336 / 455 / 20; ATL 0, DET 1,
PHI 1, MIL 0). Ticks: pre-live 2,232, early 938, middle 934, late 712; every tick home_oriented.
Arm A and B_lag cells scored in all four segments for both targets (n_games 4 each). B / C / D
not reconstructible (no nba training rows: preseason excluded by policy; no history passed),
contrasts INSUFFICIENT. Counted, data-caused, not by sport: tick_refused:invalid_decimal 810 nba
live state rows (709 of them carry clock_sec null at period breaks, 398 at period 2 = halftime;
segment() calls _number(clock_sec), ingame_scoreboard_rules.py:55 + :20; the other 101 NOT
attributed); model_state_refused +2,232 = the pre-live ticks (period null; B/C features only).

Qualification, nba: every game FAIL with COVERAGE_LOW, DECISIONS_LOW, RESERVATION_INVALID,
plus STATE_GAP / STATE_STALE / NOT_LIVE / BOOK_CADENCE on some. LINKAGE_INVALID 1,945 / 2,375 /
785 / 32: forward_replay_qualification.py:183-187 counts every book row whose event matches the
served game (targets(), :117-122) but whose ticker is the sibling (unserved) side. Same rule
fires for mlb (CLE 3,713 in both variants): a per-row diagnostic count of the other side's
book rows, not a refusal and not nba-specific. Not a defect.

Invariance (B with nba items removed vs A): qualification games identical; scoreboard games,
settlement, cells (48), ticks (1,604), paired_losses (3,208), contrasts identical; registry_e
rows, summary, full_population, selected_blocks, window and 13 other fields identical (only
counts.unsupported_sport 4 -> 8 and the receipt sha differ). fill_realism not comparable (B killed).

FINDING (risk, not a sport refusal): fill_realism reads every dispatched sport's book shards
pooled; nba adds 72.7 MB (10-05) + 68.9 MB (10-06) to mlb's 118 MB, and B exceeded the 600 s
step deadline (paper_night_budget.json deadline_s fill_realism 600). The box was loaded by
other leads (A took 393 s vs 85 s on the live 10-04 night), so the live wall is NOT measured;
but nights from day 10-07 carry nba and later soccer shards, so a killed fill_realism step
(night PARTIAL, no fill_realism/<D>.json) is a live risk. Both files are pinned (fill_realism.py,
paper_night_budget.json), neither is seal-hashed. PROPOSED (dispatcher decides, not built):
watch the fill_realism wall_s in nights/2026-10-07.json; if > 450 s, raise deadline_s
fill_realism to 900 (budget edit, hashed: no; identity: no) or read only served tickers'
rows (fill_realism change, hashed: no; identity: yes for the fill counts).

## 6. Calendar questions for the dispatcher

Q1: S534 landing slot (its own night, before 10-08T00Z) vs seal A 10-06 / commit B 10-07.
Q2: whether nba preseason B/C/D (training admission) is wanted at all before the 10-20 opener;
    recommendation: NO (preseason is a different population; S494 policy stands; regular
    season accrues the 20-game floor from ~10-24).
Q3: S482 (nba arm E) stays deferred: a new PREREG_E needs >= 30 settled nba games.
DECIDED (dispatcher 2026-10-06): Q1 S534 lands on night 10-05 (06:05Z 10-06) by a separate
landing lead; Q2 no preseason in B/C/D training; Q3 S482 deferred.
OPEN: Q4 the fill_realism deadline risk in section 5 (watch nights/2026-10-07.json).

## 7. Deadline raised (2026-10-06, dispatcher decision on Q4)

paper_night_budget.json deadline_s fill_realism "600" -> "1200"; no other value changed (ceilings,
margins, admission need unchanged). Measured basis: night 10-05 (one mlb game, unloaded box)
fill_realism wall_s 397.031 (nights/2026-10-05.json); scratch night B with 4 nba rows KILLED
step_deadline_exceeded at 600 s (exit 15, no artifact); nba adds ~142 MB of book reads to mlb's
~118 MB. Budget LF sha256 8f83eda9... -> 91df67a7e2646a5bdf32f114c7104d803beecb3c31bdd92b40e2dce0a9136a3c
(CRLF form 0979ed72... -> 8f5eadb04a8af1a53d16fa46243bf62a01a3228fcd44d8ae14ec12d883a85f07). Pins updated
test-only with an S779 comment: test_s526_admission_need (LF hash), test_paper_night_deferral c9,
test_registry_scorer_e_night_capacity c12, test_s485_baseline_contract frozen bytes, test_s558_round4
(proposal context line). Other timeouts: the tick's night child timeout is 7200 s (paper_desk_config.json
timeouts_s.night); the sum of step deadlines rises 5,400 -> 6,000 s, plus at most 600 s of S755 RAM wait
= 6,600 s, still under 7200, so no other value changes. Night 10-05 total ~30 min; worst case +600 s
keeps a 06:05Z night well before the 08:45Z window. Census: night_ram_census HISTORICAL_MARGINS lacks the
new hash, but post-S526 rows carry admission_floor_bytes, so no historical_margin_unknown refusal.
NOT VERIFIED: a live nba night's fill_realism wall_s under 1200 s (first check nights/2026-10-07.json).
