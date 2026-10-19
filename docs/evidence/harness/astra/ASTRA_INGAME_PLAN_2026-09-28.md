A. PER-SPORT TABLE

Code paths below are relative to `scripts/platformkit/`; documentation paths are relative to the repository root.
No fresh capture was evidenced: book/state heartbeats stop at 2026-09-26 02:13Z, or September 25 21:13 Chicago. No September 28 shards or dated scoreboard receipts were found.
With the current paper-night wiring, the best available result is an A_ONLY market baseline. Arm E is separate, and fitted-arm history has no producer.

| Sport | Model actually reachable by tonight's scorer | Inputs | Capture feeds it live? | Last measured versus mid | Biggest defect |
|---|---|---|---|---|---|
| MLB | S439: `ingame/baseline_four_arm.py:107`; separate E: `execution/registry_scorer_e_fit.py:138` | C: mid, score, inning, half, outs, bases. E: mid, inning/outs/scores, pitcher workload, encounters, bullpen, microstructure | Code connection exists; current receipts absent; E not scheduled | Current arms UNMEASURED. Legacy Brier 0.23768 versus 0.20665, 227 games [1] | E omits half, bases, balls and strikes already present in capture |
| NFL | No fitted route: `execution/ingame_scoreboard.py:119` returns none | Capture has score, clock, period, possession, down, distance, timeouts | State adapter exists; no fitted consumer or fresh receipts | UNMEASURED | No market-plus-football-state scoring route |
| Soccer | Intended C: `ingame/baseline_four_arm.py:107` | Mid, score difference, minute, card features; current reconstruction supplies only score/minute | EPL adapter exists; missing `model_prob` rejects fitted arms; no fresh receipts | Current arms UNMEASURED. Legacy soccer_intl Brier 0.22789 versus 0.14273, 51 games [1] | Eligibility incorrectly makes B/C depend on the absent standalone-model probability |
| Tennis | No fitted route: `execution/ingame_scoreboard.py:119` | Captured player names, sets won, winner | No compatible scoring bridge; no fresh receipts | UNMEASURED | Capture lacks server, point score and game score |
| WNBA | No fitted route: `execution/ingame_scoreboard.py:119` | No WNBA state source on this capture path | No | UNMEASURED | Missing registration across capture, identity, schedule and scorer |
| NBA | Intended C: `ingame/baseline_four_arm.py:107` | Mid, score difference, quarter, clock | Basic-state connection exists; player blocks do not reach this scorer; no fresh receipts | UNMEASURED on this sealed path | Scoring discards possession, fouls, lineups and player state |

[1] `docs/evidence/ingame/GATE_A0_2026-09-14.md:29`. These are historical standalone-model comparisons, not measurements of the current C/E implementations or current EPL coverage.
MLB omissions: `ingame/feature_registry.py:123`, `execution/registry_scorer_e.py:201`; captured fields: `ingame/ingame_gumbo_mlb.py:154`.
Soccer eligibility defect: `ingame/baseline_four_arm_eligibility.py:107`; NBA reconstruction: `execution/ingame_scoreboard.py:142`.

B. THE FIRST-SCORED-NIGHT PATH

Required chain: prospective full/served schedule -> linked venue books and receipt-stamped state -> available scoring shards -> captured final -> eligible historical features -> committed prereg/config -> sequential paper-night scoring -> paired losses, source/code hashes, refusal census and artifact digest.
Each sport must have its own scheduled, captured, joined, settled and scored counts; an omitted sport must remain visible as zero coverage.

| Sport | Minimum sport-specific connection |
|---|---|
| MLB | StatsAPI gamePk/GUMBO -> verified winner ticker -> state blocks -> C/E -> captured final |
| NFL | ESPN event and correct UTC kickoff date -> winner ticker -> football-state C/E -> captured final |
| Soccer | Explicit competition/date -> team-win ticker with draw semantics -> score/clock/cards C/E -> compatible final |
| Tennis | Match/player identity -> server/point/game/set state -> tennis-specific segments and settlement -> C/E |
| WNBA | Native WNBA registration -> 10-minute-quarter state/identity -> basketball C/E -> final |
| NBA | ESPN event -> basic state plus receipt-causal PBP blocks -> basketball C/E -> final |

Breaks found in the inspected paths:

- Capture/scoring directory mismatch: live defaults to `data/cache/ingame_books_local` (`ingame/local_capture_runner.py:17`); budget consumes `ingame_capture_view_v2` (`execution/paper_night_budget.json:10`). Automatic view refresh was not located; `execution/forward_capture_bridge.py:244` is a reader, not a materializer.
- One missing sport shard suppresses the entire scoreboard: `execution/paper_night.py:103`, `:113`. Sports absent from the schedule disappear from its inferred population at `:91`.
- No historical-training-row producer exists: `execution/paper_night_steps.py:275`. Empty accepted history returns no fitted predictions at `execution/ingame_scoreboard.py:164`.
- MLB/soccer B/C eligibility requires `model_prob`, although native state rows omit it: `ingame/baseline_four_arm_eligibility.py:107`; `ingame/local_state_capture.py:34`.
- Arm E is not an unattended step: `execution/paper_night_steps.py:285` invokes S439 only; E needs its own input manifest and command at `execution/registry_scorer_e.py:225`.
- NFL primetime is a date trap: `execution/forward_schedule_writer.py:215` refuses `outside_utc_date`. September 28 local games starting after midnight UTC need a September 29 schedule. `--utc-day-window` fetches adjacent listings but does not widen acceptance.
- Restarting after kickoff cannot recreate prospective selection: `execution/forward_schedule_writer.py:217` refuses `not_pregame`/`not_prospective`.
- MLB postseason coverage needs a series census: capture hardcodes series at `ingame/kalshi_series_scope.py:47`; schedule admits `KXMLBGAME` at `execution/forward_schedule_writer.py:28`, rejecting other series at `:105`. A different postseason series is a conditional risk, not a verified venue fact.
- Soccer books cover six leagues, while schedule/state use EPL only: `ingame/kalshi_series_scope.py:51`, `execution/forward_schedule_sources.py:21`, `ingame/local_state_capture_sources.py:220`. UCL books alone do not create scoreable games.
- NBA/soccer state polling ignores the supplied date (`ingame/local_state_capture_sources.py:185`); NFL also uses a dateless request (`:269`). Default-date rollover can lose unfinished games or finals.
- Tennis live ticks refuse `regulation_unavailable` (`execution/ingame_scoreboard_rules.py:60`); captured tennis finals use player/set fields (`ingame/local_state_capture_sources.py:254`), but settlement requires home/away scores (`execution/ingame_scoreboard_rules.py:65`).
- WNBA is absent from capture sports, state sources, schedule routes and identity aliases: `ingame/local_capture_runner.py:19`, `ingame/local_state_capture_sources.py:34`, `execution/forward_schedule_sources.py:20`, `ingame/game_market_link.py:25`.
- NFL/tennis/WNBA have no fitted scorer mapping (`execution/ingame_scoreboard.py:119`). WNBA additionally lacks basketball segmentation (`execution/ingame_scoreboard_rules.py:51`).
- Missing captured finals leave games unsettled; venue settlement is not a fallback: `execution/ingame_scoreboard.py:223`.
- MLB enrichment defaults off and requires `mlb_live`: `ingame/local_state_capture.py:81`, `ingame/mlb_lineup_seam.py:42`. A landed block is not evidence of live use.
- S439 permits arbitrarily old mids (`execution/ingame_scoreboard.py:37`); E permits 21,248 seconds under `docs/evidence/forward/scoreboard/PREREG_E_2026-09-25.json:22`. Receipt ordering alone does not establish contemporaneous information.
- E rejects any input event before config effectiveness (`execution/registry_scorer_e.py:194`), while training requires settlement before the scoring midnight minus three days (`execution/registry_scorer_e_fit.py:110`). The history/config interaction must be resolved prospectively; backdating seals or shortening embargo is not a remedy.

C. RANKED NEXT ROWS

These are eight proposals, not allocated S-IDs. Every model comparison must report loss(E,y)-loss(mid,y) and paired E-minus-C on identical eligible ticks; closeness to the mid itself is not forecasting performance.

1. **Restore a complete prospective capture census.** Measurement: six-sport scheduled/captured/linked/final counts, including UTC primetime, league and postseason-series refusals. Rank: missing receipts are irrecoverable. Owner: terra build / sol verify. Dependency: current supervisor/source configuration and valid pre-kickoff schedules.
2. **Produce the first unattended sealed A/C/E receipt.** Measurement: per-sport history eligibility, arm coverage, E-minus-A/E-minus-C, explicit warmup and unavailable-sport counts. Include training-row production, independent B/C eligibility, E dispatch, directory agreement and per-sport failure isolation. Rank: makes every later model change measurable. Owner: Sonnet build / sol verify / Opus seal review. Dependency: row 1; resolve config/history chronology before scoring.
3. **Bound combined capture and scoring memory.** Measurement: peak combined working set and completion/refusal census with unchanged paired losses. Rank: protects both tonight's capture and tomorrow's receipt. Owner: terra build / sol verify. Dependency: frozen representative inputs from row 1; preserve row 2's scoring contract.
4. **Make MLB E use the complete live count and lineup state.** Measurement: nested E-minus-C and E-minus-mid for half, bases, balls/strikes, workload and available lineup blocks; coverage by inning. Rank: these fields are already captured and postseason opportunities are scarce. Owner: Sonnet build / sol verify / Opus prereg review. Dependency: row 2, S471, new prospective block config; do not substitute S450 strikeout-distribution results for winner-market evidence.
5. **Connect NFL's captured possession state to a market anchor.** Measurement: football-state coverage and E-minus-C using score/time, possession, down/distance, timeouts and verified field position. Rank: capture tonight's scarce weekly observations now; fit only when history qualifies. Owner: Sonnet build / sol verify. Dependency: rows 1-2, correct UTC schedule and sufficient archived state.
6. **Expand soccer state to the leagues already captured.** Measurement: league-specific book/state/final join census, then score/clock/cards E-minus-C with ticker-specific draw handling. Rank: converts recurring book-only coverage into daily evidence. Owner: Sonnet build / sol verify. Dependency: rows 1-2; explicit competition/date/settlement mappings and prospective freshness policy.
7. **Share a basketball adapter across WNBA and NBA.** Measurement: WNBA playoff coverage first; separately sealed score/clock/possession/foul/player-block E-minus-C by league. Rank: WNBA supplies immediate observations before NBA's larger calendar. Owner: Sonnet build / sol verify / Opus scope review. Dependency: rows 1-2, WNBA registration, S468; S472 inferred lineups remain excluded until its required live boxscore comparison passes.
8. **Capture tennis point and server state before fitting.** Measurement: match-identity, serve/point/game/set and settlement census; then market-anchored E-minus-C by tour. Rank: frequent matches help only after the fundamental state deficit is repaired. Owner: Sonnet build / sol verify. Dependency: rows 1-2, an accessible timestamped state source and a tennis-specific settlement/segment contract.

Keep game-clustered intervals, embargo, missingness counts and separate corpora. A few nights can establish operational evidence; they cannot guarantee the 30-game floors or calibrated improvement. A confidence interval crossing zero is not proof of equivalence.

D. RAM

These are the largest unbounded allocations found by code inspection; actual peak RSS was not measured.

1. **Qualification replay:** `execution/forward_capture_bridge.py:250` materializes books, states, trades and journals; `execution/forward_replay_io.py:185` retains and sorts the visible population. Smallest fix: reuse the existing disk-offset/SQLite approach, stream in global receipt order, and retain shared reservation/cap state so qualification semantics remain unchanged.
2. **Scoreboard and E replay:** `execution/ingame_scoreboard.py:199`, `:210`, `:240`, `:260` retain history, shards, ticks and paired losses; `execution/registry_scorer_e.py:232` builds all input games, with whole-shard readers at `ingame/registry_readers.py:24`. Smallest fix: filter/project during reading, process one game at a time, spool reconstructible pairs, keep compact feature matrices, and bootstrap from game-level sums/counts.
3. **Capture restart/rollover recovery:** `ingame/local_state_capture_io.py:139` retains two days of complete receipt rows before yielding at `:174`, although `recover_states()` ultimately needs latest states. Smallest fix: disk-index receipt identities/conflicts and fold valid records into latest-per-game state while preserving duplicate/conflict rules.

Fill realism already disk-indexes inputs (`execution/fill_realism_io.py:112`); its remaining resident unit is a whole ticker at `:163`, so preserve that improvement.
The budget's 1,572,864,000-byte ceiling is per child (`execution/paper_night_budget.json:2`), not the combined stack. Target roughly 1 GB for the sequential worker and reserve the remainder of the 1.5 GB allowance for capture/supervisors; verify combined peaks before claiming the laptop target is met.

E. PROCESS WASTE

1. **Resolve acceptance contradictions before dispatch.** Supply one consolidated chronology/clock/refusal contract with executable boundary examples. S450 repeatedly repaired training pools and chronology (`docs/evidence/tracking/specs/S450_spec.md:32`); S462 corrected a formula that contradicted its own construct after round five (`S462_spec.md:32`). Keep the verifier's bar fixed.
2. **Make the first build prove persistence and recovery through the real caller.** Require producer -> strict JSON serialization -> archive -> restart -> consumer, including malformed types, reordered receipts and partial failures. S467 emitted invalid JSON that recovery discarded (`docs/evidence/tracking/specs/S467_spec.md:41`); S466 still journaled before acquiring ownership in round six (`S466_spec.md:44`).
3. **Generate evidence inventories from the final candidate and preserve mandatory disclosures.** Freeze case counts, hashes, denominators and NOT VERIFIED items; review prose-only corrections against unchanged code identity. S460's verified code incurred further rejection when memo condensation removed disclosures (`docs/evidence/harness/S460_arm_e_registry_2026-09-25.md:161`); S462 and S467 reached memo-only round-eight corrections.

The register records S466 as seven two-tier rounds, not eight; S450 records sixteen sol plus six Opus rounds (`docs/evidence/HARNESS_GAPS_2026-09-03.md:593`, `:609`). No files were edited, and no tests or model jobs were run.