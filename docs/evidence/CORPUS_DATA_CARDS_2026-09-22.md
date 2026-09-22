# Corpus data cards + defect register (2026-09-22)

What this page is: one card per corpus this project measures on -- what it is, how it is keyed,
what is frozen, what is excluded -- then the register of every known defect in those corpora and
in the capture that feeds them. It is the page a reviewer reads BEFORE any result page, so a
number is read against its corpus and its defects rather than on its own. Descriptive and
counting language only. Every number carries a file:line citation to a TRACKED artifact that a
clone of this repository holds; where the only source is a private working note, the line says
NOT ON RECORD rather than citing a path a reader cannot open.

Citation keys used below: `JEP` = `docs/JOB_EVIDENCE_PACKET.md`; `RLS` =
`docs/evidence/RESULTS_LEDGER_SYSTEM.md`; `LIC` = `docs/evidence/LICENCE_LEDGER.md`; `GAPS` =
`docs/evidence/HARNESS_GAPS_2026-09-03.md`; `S402` / `S406` =
`docs/evidence/harness/S402_reconciliation_real_2026-09-22.md` and
`S406_census_real_2026-09-22.md`; `S392` / `S382` / `S347R` / `S347S` / `GA0` / `GA0S` =
`docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md`,
`S382_NBA_PREREG_DRAFT_r1_2026-09-21.md`, `S347_FOUR_ARM_RESULT_2026-09-21.md`,
`S347_PREREG_SEALED_2026-09-21.md`, `GATE_A0_2026-09-14.md`, `gate_a0_summary.md`; `SCHED` =
`docs/evidence/forward/schedules/`; `S397sp` / `S398sp` / `S410sp` / `S416sp` =
`docs/evidence/tracking/specs/S397_spec.md`, `S398_spec.md`, `S410_spec.md`, `S416_spec.md`.

Three standing use rules referenced by the cards:

- SPENT-WINDOW RULE: the one corpus whose charged attempt has been read, `mlb_segmented_r3`, is
  descriptive forever -- attempt 1 of 2 charged and read (`S347R:4-5`); no second charge.
- D-ONLY DESCRIPTIVE RULE: arm D (market + state + model) on the NBA corpus is DESCRIPTIVE_ONLY
  (`S402:22`; S392 disposition).
- SECOND-CORPUS RULE: no AHEAD conclusion from one corpus; a lift must hold on >= 2 independent
  corpora (`docs/guide/09_DATA_AND_SIGNALS.md:159`, `docs/guide/10_HONEST_LIMITS.md:29`).

---

## PART 1 -- DATA CARDS

### C1. `nba_checkpoints_r1` -- NBA in-game, Polymarket price side

- Source / venue: Polymarket in-play price checkpoints joined to ESPN state; built by the S360
  converter, which streams the checkpoint parquet in row groups and joins the as-of model side
  (`RLS:689`). Upstream inputs recorded as 321 Polymarket date-files / 330 MB / 1,688 event_slug
  docs plus 398 cached ESPN scoreboards and 1,610 summaries (`RLS:348`).
- Time span: 2024-10-22 .. 2026-06-13 (`RLS:689`).
- As-of rule: the model side joins on the exact (game_id, UTC instant) key; timestamps finer
  than a microsecond are REFUSED, never rounded (`RLS:689`).
- Rows / games: 1,593 files / 1,593 games / 465,249 ticks / 465,249 unique keys / 0 conflicting
  duplicates (`S402:12,18`; `RLS:703`). Eligible (live) 221,066 ticks in 1,593 games
  (`S402:13`). Post-warm-up primary 1,570 games, 23 warm-up, 311 folds, 5 warm-up folds
  (`S402:26,29,33,34`). Arm-D paired subset 109,108 ticks (`S402:44`, exposure_d placeholder).
  Corpus bytes 169,404,513 (`S402:23`).
- Period support: P1 44,428 / P2 68,825 / P3 52,645 / P4 284,586 / OT 14,765 ticks (`S402:28`).
  61 pct of ticks sit in period 4, so a tick-weighted primary would be a fourth-quarter
  measurement (`RLS:703`).
- Join keys: game_id + UTC instant (`RLS:689`); period/score state parsed to integral values
  only (`RLS:722`).
- Sealed / frozen: FROZEN, UNSEALED. Manifest SHA-256
  `5c4c1d109278c9262fbba1157d0d49afd6af16d2e9ead447b38baeb3526fd9a5` (`S402:17`);
  eligible-games identity
  `04c182de96f7433ee1e65d355102e82dcd58693f960bac266d62ef7c66453805` (`S402:25`);
  primary-games `3d1344bf1cc123da915d911c84c1a911ed88df922902a65fb18570f6abe838c9`
  (`S402:30`). No seal line is written; 11 do-not-seal items, all OPEN, plus a missing auditor
  pin (`S402:8,50-62`).
- Known exclusions: 244,183 post-final ticks, 52 pct of all ticks, 1,592 of 1,593 games repeat
  the final state (`S402:14`; `RLS:703`). `model_prob` exactly 0 or 1 on 116,459 ticks, refused
  for the model arm only (`RLS:703`). `model_prob` missing for arm D on 348,757 ticks
  (`S402:44`). Model coverage per game: all 26 / some 771 / none 796 (`S382:263`).
- Licence / access: Polymarket Gamma API, read-only, no auth; terms UNREAD -- client-rendered,
  the terms body never served to a plain fetcher (`LIC:367-377`). ESPN state side: DECIDE row 1
  of the licence ledger (`LIC:28`, clause block `LIC:L54-62`).
- May be used for: the frozen denominators of an NBA second-corpus preregistration; arms A/B/C
  on the full eligible population. May NOT be used for: any untouched-validation claim -- S58
  scored all 1,593 games and S86 reproduced its selection on 797, so the 796-game remainder is
  "less exposed", not untouched (`S392:3-6,24,46-48`; `S402:31-32`); arm D is DESCRIPTIVE_ONLY;
  nothing may be scored before a seal line exists.

### C2. `mlb_segmented_r3` -- MLB in-game, Kalshi price side, revision 3

- Source / venue: the S346 revision-3 segmenter over the MLB Kalshi in-game joined corpus
  (`RLS:680`).
- Time span: inherited from `mlb_clean`, 2026-06-20 .. 2026-07-12 (`GA0S:5`).
- As-of rule: each kept file is anchored on a STATED tick inside its window; files without a
  stated tick, outside the window, or with a constant market price are quarantined (`RLS:680`).
- Rows / games: 176 files / 176 games / 31,433 ticks; ELIGIBLE 29,887 ticks in 176 games;
  12,339 state-transition ticks; 15 date folds, 4 warm-up (`RLS:681,682`). Scored after warm-up:
  19,919 ticks in 135 games (all_tick) and 9,318 in 135 games (state transitions), 9,968
  warm-up keys excluded from every arm (`S347R:16`).
- Join keys: (game_id, tick time); identical repeats collapse, a conflicting key is excluded
  from every arm (`RLS:681`).
- Sealed / frozen: SEALED. Prereg seal `18b45d85...`; segmenter manifest SHA-256
  `7d9e8001e276ef5a...`; canonical PER-FILE hash manifest
  `f3b5e3f9364f7627404cac7e8f51ffbf95fa56ffc72e20020629958aac3f72b1`, and the scorer refuses to
  run unless every listed file hash matches (`S347S:163-168`; `RLS:682`); the pre-seal CORPUS
  manifest is `eae21e66593a5d45e4ffd911cea470300e5d6a92b834a6dcfc75f42e54e0540a` (`RLS:681`).
  Attempt 1 of 2 charged and read (`S347R:4-5`), canonical ledger row k_cumulative = 19
  (`S347R:5`); the window is treated as SPENT.
- Known exclusions: 51 of 227 source files quarantined (49 no_stated_tick, 1 outside_window,
  1 constant market price) and 78,986 source ticks reduced to 31,433 kept; 12 label
  disagreements RETAINED for audit (`RLS:680`). Within the kept files, 1,546 of 31,433 ticks
  excluded; the artifact prints four reason counts -- half missing 1,410; base or outs 700;
  inning or score 668; conflicting duplicate keys 104 (`RLS:681`). Those four sum to 2,882,
  above the 1,546 total (this page's arithmetic); the artifact does not state how they compose.
- Licence / access: Kalshi public API, keyless for public market data, terms UNREAD (HTTP 429
  on every attempt 2026-09-03) (`LIC:351-363`). Not published.
- May be used for: a DESCRIPTIVE re-read of the saved rows. May NOT be used for: a second
  charged window -- SPENT-WINDOW RULE; its one charged attempt was read and returned 96 of 96
  comparisons UNDERPOWERED (`S347R:11-14`), and a second window needs a fresh capture.

### C3. `mlb_clean` -- MLB in-game, Kalshi price side, revision 2

- Source / venue: Kalshi in-play mid joined to MLB state; the Gate A-0 corpus (`GA0:9`).
- Time span: 2026-06-20 .. 2026-07-12 (`GA0S:5`).
- As-of rule: paired ticks only -- the model is scored against the CONTEMPORANEOUS market price
  on identical ticks; the model updates only at parsed state transitions (`GA0:16,49`).
- Rows / games: 227 files / 78,986 rows / 227 games (`GA0:9`; `GA0S:5`).
- Fields / join keys: the eleven-column joined schema (sport, game_id, tick time, model and
  market probability, side, state summary, outcome and the close pair) at `GA0:11-12`.
- Sealed / frozen: no seal; a landed measured row (S330 `69427a5f7`, `RLS:629-630`;
  `GAPS:473`).
- Known exclusions / defects: 1,588 duplicate (game, time) keys (`RLS:681`).
- Licence / access: as C2 (`LIC:351-363`).
- May be used for: the Gate A-0 descriptive result -- model 0.23768 vs market 0.20665, delta
  +0.03103, game-clustered 95 pct interval [0.01704, 0.04535], BEHIND (`GA0S:5`). May NOT be
  used for: an AHEAD conclusion on one corpus (SECOND-CORPUS RULE); its band and
  minutes-to-close cells labelled UNDERPOWERED may not be read as results (`GA0S:21-22,28-31`).

### C4. `soccer_intl` -- international soccer in-game

- Source / venue: same joined-corpus family as C3 (`GA0:10`).
- Time span: 2026-06-22 .. 2026-07-12 (`GA0S:6`).
- As-of rule: as C3 (`GA0:16`).
- Rows / games: 51 files / 9,003 rows / 51 games (`GA0:10`; `GA0S:6`). Revision-3 segmentation
  keeps 26 games / 4,264 ticks from 51 games / 9,003 ticks, 25 quarantined (`RLS:680`).
- Sealed / frozen: no seal; declared UNDERPOWERED IN ADVANCE at 26 games, below the 30-game bar,
  with 5 warm-up date folds, runnable for a DESCRIPTIVE table only (`S347S:169-171`;
  `RLS:681,682`).
- May be used for: the descriptive Gate A-0 row -- 0.22789 vs 0.14273, delta +0.08516,
  [0.04876, 0.12696], BEHIND (`GA0S:6`). May NOT be used for: any powered conclusion.

### C5. `own_lines_backtest_nba.json` -- NBA pregame moneyline

- Source / venue: `data/cache/kalshi_complete/own_lines_backtest_nba.json`, dated 2026-07-18;
  MOV-Elo scored by `scripts/platformkit/proof_nba/ml_accuracy.py` against the Shin-devigged
  close (`JEP:186`).
- As-of rule: leak-free walk-forward, truncation-invariance proven (`JEP:186`).
- Rows / games: n = 743, held-out 372 (`JEP:186`).
- Sealed / frozen: no seal; the packet's reproducible pregame artifact of record.
- May be used for: Brier 0.1735 model vs 0.1666 close, gap +0.0069, 95 pct interval
  [-0.0036, +0.0175], verdict TRAILS_CLOSE (`JEP:186`). May NOT be used for: the superseded
  pregame pair that has no artifact and did not reproduce (`JEP:310-311`).

### C6. Props player-game corpus

- Source / venue: NBA Stats API via `nba_api` (`LIC:106-108`) plus ESPN box scores, row 1 of the
  licence ledger (`LIC:28`, clause block `LIC:L54-62`).
- As-of rule: last-20-percent-by-date chronological holdout, scored through the production
  inference path by `scripts/verify_production_mae.py`, which exits nonzero if any stat drifts
  more than 0.02 from the claimed values (`JEP:167-171`).
- Rows: 20,354 player-game rows in the holdout (`JEP:168`). A separate walk-forward OOF frame
  holds 50,954 rows per stat on a gitignored artifact (`JEP:173-174`).
- Sealed / frozen: no seal; the script is the reproduction check.
- Licence / access: NBA Stats API is a DECIDE row and stats.nba.com is blocked from this box
  (`LIC:106,138`).
- May be used for: the holdout MAE set under its own label -- PTS 4.83, REB 1.92, AST 1.39,
  FG3M 0.89, STL 0.71, BLK 0.44, TOV 0.89 (`JEP:167-168`). May NOT be used for: mixing holdout
  and OOF numbers in one citation -- on the OOF frame BLK reads 0.515, not 0.44
  (`JEP:178-180`); and the TRAINER behind these models is a player-season regressor with
  synthetic features (defect D8 below), so no prop number may be described as a per-game model
  result.

### C7. Forward capture archives -- Kalshi books, state, Polymarket, by UTC day

All C7 counts come from an UNLANDED S406 candidate with no verifier round (`GAPS:549`;
`S406:24-25`): a census, not a landed measurement.

- Source / venue: Kalshi public API books and trades into
  `data/cache/ingame_books_local/kalshi/<sport>/<day>.jsonl` (`S406:3`); state into
  `data/cache/ingame_state_local_v2` (`S397sp:197-200`). Polymarket live capture is NOT landed
  (S397 OPEN, `GAPS:540`); only bounded smoke archives exist (`S397sp:194,197-200`) and the
  landed Polymarket book capture has had no live run (`GAPS:480`).
- As-of rule: receipt semantics. Kalshi snapshot rows carry NO `api_ts`, so a book-age
  measurement must use `response_end_ts` (receipt) (`S406:15,21-22`).
- Rows, one day (2026-09-22): 122,193 mlb + 596 nba + 141,588 nfl + 182,271 tennis; soccer
  shard absent; unparseable lines 0; first / last `response_end_ts` 00:00:00Z .. 19:24:55Z
  (`S406:3-5`). By record type, all sports pooled: snapshot 26,927, snapshot_bulk 40,919,
  trade 367,276, trade_backfill_closed 11,383, trade_gap 143 (`S406:7`).
- Encoding: prices and sizes are Decimal-origin number text, at most 4 (prices) and 2 (sizes)
  fractional digits, no binary-float tails; `minutes_to_close` is the one float-origin field
  (`S406:10-14,18-19`).
- Join keys: exact `game_key` per sport plus the Kalshi event ticker (`RLS:731,732`).
- Sealed / frozen: not sealed; these are live archives.
- May be used for: counts, encoding class and cadence statements. May NOT be used for: any
  qualified-game or completed-week claim -- NO REAL GAME HAS BEEN QUALIFIED (`RLS:716,720`).

### C8. Prospective forward schedules

- Source / venue: the S386 writer over venue schedule responses, committed BEFORE first start
  so prospective selection is provable (`RLS:724`).
- Rows: `SCHED/2026-09-22_maker_forward_full_selection.json` holds 6 entries; the served subset
  `SCHED/2026-09-22_maker_forward.json` holds 3, with the remaining 3 named in
  `SCHED/2026-09-22_maker_forward.capacity_note.json:4-8`. Same 6/3 shape for 2026-09-23
  (`SCHED/2026-09-23_maker_forward.json.capacity_note.json:4-14`).
- As-of rule: `selected_at 2026-09-22T03:03:03.749878+00:00`
  (`SCHED/2026-09-22_maker_forward.json:7`). The capacity subset rule, verbatim: "earliest
  starts, ticker order on ties, subject to capture_scheduler.schedule_rows line 113 (any three
  consecutive starts must span >= 3600 s); score-blind, before any start"
  (`SCHED/2026-09-22_maker_forward.capacity_note.json:9`). The spacing clause is why a later
  start can be served over an earlier one.
- Join keys: `game_key` (MLB gamePk) beside `game_id` (Kalshi event ticker) and the canonical
  ticker (`SCHED/2026-09-22_maker_forward.json:4-9`; `RLS:731`).
- Census: mlb games_seen 16, linked 6, all via `team_set`; refused
  `missing_directional_team_evidence` 4 and `outside_utc_date` 6; ignored record types 74,107
  and derivative series 417 (`SCHED/2026-09-22_maker_forward.json.census.json:6,15,17-23`).
- Denominator of record: the full-selection file, never the served subset
  (`SCHED/2026-09-22_maker_forward.capacity_note.json:3`).

### C9. `data/nfl/schedules.parquet` -- NFL forward schedule

- Source / venue: an offline forward NFL schedule table no landed reader consumes (`S416sp:20-22`).
- Rows / span: 7,548 rows; `gameday` 1999-09-12 .. 2027-01-10; season 2026 `game_type` REG =
  272 rows, gameday 2026-09-09 .. 2027-01-10 (`S416sp:21-22`).
- Columns: game_id, season, game_type, week, gameday, gametime, home_team, away_team, espn --
  the `espn` column holds the ESPN event id (`S416sp:20-22`).
- May be used for: a supply statement only. May NOT be used for: any NFL in-game modelling --
  no NFL joined corpus or price series appears in the results ledger, and that absence is not
  itself a published measurement.

---

## PART 2 -- DEFECT REGISTER

Status vocabulary: OPEN | FIXED in row Sxxx | MITIGATED | ACCEPTED-DESCRIPTIVE.

| ID | First seen | Found by | Symptom + measured count | Status | Artifact |
|---|---|---|---|---|---|
| D1 | 2026-07 era | score-drift audit | 76 of 436 settled MLB paper rows drift from the resolver read | MITIGATED -- rows quarantine-flagged, never silently re-settled | `docs/evidence/execution-honesty.md:49-51,71` (`0d01a0e7`) |
| D2 | 2026-09-21 | S346 | Segmenter tick loss: mlb 227 files in / 176 kept, 51 quarantined, 78,986 ticks in / 31,433 kept; soccer 51 in / 26 kept, 9,003 ticks in / 4,264 kept | ACCEPTED-DESCRIPTIVE -- quarantine reasons counted, 12 label disagreements retained | `RLS:680` |
| D3 | 2026-09-22 | S404 | Linkage refusals: duplicate schedule identity in either direction refuses LINKAGE_INVALID and attributes zero rows; counted reasons state_key_absent / state_key_conflicted / book_event_absent / linkage_disagreement / duplicate_schedule_identity / invalid_schedule_game_key | FIXED in S404 (`46fb89cd0`) | `RLS:732`; `GAPS:547` |
| D4 | 2026-09-22 | S401 | State capture re-read a sport's whole shards per polled key: first tick 19 minutes / 914 CPU-s / 1.0 GB, second not complete 26 minutes later; 51 shard opens per tick | FIXED in S401 (`c997aa9b7`) -- recover once per process start and per UTC rollover; 51 opens per tick to 1 | `RLS:730`; `GAPS:544` |
| D5 | 2026-09-22 | first real S386 run | State rows carry no scheduled start, so a game window cannot be fixed from state alone | OPEN -- candidate only, not landed | `GAPS:536` |
| D6 | 2026-09-22 | S398 / S410 scan | Sparse pre-focus Kalshi polling on the real mlb shard: 45-49 snapshot receipts per ticker for the WHOLE day, median receipt gap 257 s, one gap of 45,164 s | OPEN -- no game can qualify on pre-focus receipts; the remedy is a better capture, never a moved bar | `GAPS:553`; `S410sp:4-8`; `S398sp:163-165` |
| D7 | 2026-09-22 | S398 / S406 | 45 Kalshi row refusals ("expected a decimal string") are snapshot rows whose price fields are NULL (292 such rows shard-wide) -- a null side of the book, not an encoding defect | MITIGATED -- attributed and scoped; reader decodes with `parse_float=Decimal` / `parse_int=Decimal` | `S406:19-21` |
| D8 | 2026-09-14 | source read | Props trainer is player-SEASON grain: `{stat}_roll`, `{stat}_bayes`, home/away averages and `{stat}_vs_opp` are generated as `season_{stat} * (1 + N(0, 0.08..0.30))`; tracking columns zero-filled in training and real only at inference | OPEN -- rebuild at player-game grain before any prop claim | `src/prediction/player_props.py:2649,2688-2716,2791-2796` (engine source; see Part 3) |
| D9 | 2026-09-14 | archive read | Kalshi timestamps in the historical `inplay_odds` archive are coarse, so lead/lag against the model side is UNDETERMINED | ACCEPTED-DESCRIPTIVE -- any residual must survive a lagged-mid control | NOT ON RECORD in a tracked artifact; the nearest tracked figure is the 60 s median tick cadence of the MLB price series (`RLS:243`) |
| D10 | 2026-09-22 | S406 / S397 | Two encodings, two verdicts. The KALSHI "float fields" claim is WITHDRAWN as a probe decoding artifact: the shard holds Decimal-origin number text, at most 4 / 2 fractional digits. The POLYMARKET writer DID store JSON floats on every price and size (smoke 4) | MITIGATED (Kalshi: no defect) / FIXED in the S397 candidate (UNLANDED) -- fix 1e decodes venue numbers as text; the fifth smoke wrote 1,368 rows with zero float paths | `S406:10-14,18-19`; `S397sp:164-170,194,197-200`; `GAPS:540` |
| D11 | 2026-09-22 | S406 | `api_ts` is NULL on all 26,927 Kalshi snapshot rows, so cross-venue book age must use receipt semantics | ACCEPTED-DESCRIPTIVE -- the quantity is named as a receipt, not an exchange timestamp | `S406:15,21-22` |
| D12 | 2026-09-21 | S377 | NBA corpus post-final rows: 244,183 ticks, 52 pct of all ticks; 1,592 of 1,593 games repeat the final state | MITIGATED -- excluded by rule in every NBA prereg | `RLS:703`; `S382:44,259` |
| D13 | 2026-09-21 | S377 | `model_prob` exactly 0 or 1 on 116,459 NBA ticks | MITIGATED -- refused for the model arm only | `RLS:703` |
| D14 | 2026-09-21 | S355 | Duplicate (game, time) keys in every real corpus; `mlb_clean` holds 1,588 | MITIGATED -- identical repeats collapse, conflicting keys excluded from every arm | `RLS:681` |
| D15 | 2026-09-21 | S355 | Declared MLB features base1 / base2 / base3 do not exist; real state carries one `base` field with values 0..7, which gave ZERO eligible MLB ticks | FIXED in S355 (`531f0525d`) -- one-hot over eight values, no bit order assumed | `RLS:681`; `GAPS:498` |
| D16 | 2026-09-22 | S387 first real census | The amended scorer excluded ALL 465,249 NBA ticks as `invalid_outcome`: the check required a strict int while the corpus stores a float label (1.0 / 0.0) | FIXED in S387 fix 2a (`865ad7176`) -- compared by VALUE | `RLS:723,728`; `GAPS:530` |
| D17 | 2026-09-22 | S403 | The schedule writer used the ESPN COMPETITION id for every non-MLB sport; the state capture never writes it, so no NBA / NFL / soccer schedule could ever have linked | FIXED in S403 (`3373f4360`) -- an underivable key is a counted `game_key_unavailable` refusal | `RLS:731`; `GAPS:546` |
| D18 | 2026-09-21 | S373 real-row probe | Capture-book adapter: 1,051 production snapshots gave 1,002 converted, 47 `inconsistent_touch`, 2 one-sided, 0 exceptions | MITIGATED -- inconsistent rows refused, not repaired | `RLS:691` |
| D19 | 2026-09-22 | S402 do-not-seal item 3 | Venue-time parser: four- and five-digit fractional seconds were not routed through the shared parser; today's six-digit NBA output makes the defect LATENT for this corpus, not resolved | OPEN -- do-not-seal item 3 | `S402:53` |
| D20 | 2026-09-21 | S361 scout | Tennis: 0 of 986 price-series matches (1,854,100 rows, 2026-05-22..2026-07-08) have a score observation with a wall-clock time inside their price window; the counted tennis "state" is reconstructed set boundaries | OPEN -- no tennis joined corpus is possible from these stores | `RLS:687` |
| D21 | 2026-09-22 | S386 / S403 census | Prospective schedule refusals on a real day: `missing_directional_team_evidence` 4 and `outside_utc_date` 6 against 16 games seen, 6 linked | ACCEPTED-DESCRIPTIVE -- refusals counted with the compared team-code sets recorded | `SCHED/2026-09-22_maker_forward.json.census.json:6,15,20-23` |
| D22 | 2026-09-22 | S399 | Venue certification: 95 checks, 55 PASS, 37 MISMATCH, 0 ERROR, 3 UNVERIFIED, UNCERTIFIED (exit 3) | OPEN -- every mismatch is a finding for the `venue_fees.py` owner; nothing edited | `RLS:735` |

---

## PART 3 -- NOT ON RECORD

Asked for while building this page, and not found in any artifact a clone of this repo holds:

- "The segmenter dropping roughly 14 percent of legitimate ticks" does not reconcile to any
  tracked count. The tracked S346 counts are 78,986 to 31,433 ticks and 227 to 176 files
  (`RLS:680`), and the tracked within-file exclusion is 1,546 of 31,433 (`RLS:681`). Neither
  ratio is 14 percent; the figure should be restated or withdrawn.
- The D8 citation is to the engine module `src/prediction/player_props.py`, which is tracked in
  the full repository but is not part of the public export; no public artifact restates it.
- The D9 timestamp-granularity measurement (see the D9 row) has no tracked home.
- The S397 Polymarket capture memo itself: the spec and its amendments are tracked (`S397sp`),
  the memo lives only in an unlanded candidate (`GAPS:540`).
- Bytes-on-disk beyond the pinned `CORPUS_BYTES` 169,404,513 (`S402:23`) and the S347
  15,669,023 (`S347S:163`).
- Licence CLAUSES for Kalshi and Polymarket: both rows UNREAD, no clause ever served
  (`LIC:358,375`); no access or redistribution permission may be asserted for either venue.
- Polymarket capture counts during games: the live capture has never run beside the Kalshi
  capture (`GAPS:480,540`), so there is no paired-instant count to report.
- Row counts inside the local state cache, and the per-sport day-file counts for the books and
  state archives: only the single-day record counts of C7 are on record (`S406:3-7`).
- The NFL per-ISO-week supply breakdown for Oct-Dec 2026; the tracked figure is 272 season-2026
  REG rows over 2026-09-09 .. 2027-01-10 (`S416sp:21-22`), not a per-week table.

---

Last verified: 2026-09-22.

NOT VERIFIED
- No corpus, cache or data file was opened to build this page; every count that lives only under
  `data/` is cited through the tracked artifact that transcribed it, not against the rows.
- Line numbers were read at the 2026-09-22 file state; a later edit to a cited artifact
  invalidates them.
- The S402 reconciliation ran with `allow_open: True`; every do-not-seal item was OPEN at run
  time and the auditor pin does not exist (`S402:7-8,65-66`).
- The S406 census null-side attribution of the 45 refusals is by COUNT, not by row identity,
  and the nba / nfl / tennis field classes were not tabulated (`S406:24-25`).
- S392's population identities are attributed to prior ledger records; exact membership and
  census reconciliation remain unverified and no per-game manifest was opened (`S392:35-36`).
- The S377, S387, S388, S391, S401, S403 and S404 memos were read, not re-run; every
  "FIXED in Sxxx" status was checked against the landed commit recorded in `GAPS`, not against
  `git log`.
