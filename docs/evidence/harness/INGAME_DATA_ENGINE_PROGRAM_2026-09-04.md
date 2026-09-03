# In-game data + engine program -- every live source, the engine path, and what is unmeasured (2026-09-04)

Scope: the user's standing directive (memory `ingame_data_program_2026_09_04`): before tracking,
census EVERY in-game data point and API per sport, measure what is usable at what latency, wire it
into the simulations/engines, and test methods hard on the pod. This memo is the census plus the
ranked row set. Calibration language only (Q6): no dollar, ROI, profit or edge word appears, and
none of the retracted figures. An honest REJECT / NULL / CLOSED AT LIMIT is a success.

Every number carries a citation. Numbers marked **[m]** were measured read-only by this lane on
2026-09-04 from file listings and parquet metadata (no store was loaded). Everything else is a read
of a committed artifact. Nothing here was re-derived.

Sources read: `docs/research/ingame_api_census_2026-09-04.md` (the API-side census, sourced with
URLs -- this memo consumes it rather than restating its endpoint detail), `INGAME_SIGNAL_PROGRAM`,
`INGAME_GAP_MAP`, `INGAME_WAVE_VERDICT`, `S105_depth_capture_cadence`, `S115_ingame_models`,
`S119_mlb_ingame_supply`, `S123_nba_ingame_baseline`, `S16_pod_hour`, `S102_nba_pod_sweep`,
`S150_runner_leases`, `MODEL_QUALITY_PROGRAM_2026-09-04`, `docs/evidence/ingame-conditioning.md`,
`docs/research/organization-sprint/INGAME_CAPABILITY_2026-09-01.md`, register rows S79-S212, and the
memory notes named in section 8.

Rows S199-S212 are NOT duplicated here. This memo allocates **S213-S222** and states where they sit
against the already-queued S207, S209, S210, S211, S212.

---

## 1. DATA CENSUS -- per sport

Columns: source | fields that move win probability | cadence | latency (measured or documented) |
captured today (module + store + count) | missing.
"Cadence" is OUR poll interval where we own it; "latency" is the API server response or the measured
tick gap. **No end-to-end venue-truth-to-feature latency exists for any sport** -- see 1f.

### 1a. NBA

| source | WP-moving fields | cadence | latency | captured today | missing |
|---|---|---|---|---|---|
| cdn.nba.com liveData boxscore / playbyplay | score, period/clock, `game.actions[]` (shot/foul/timeout/sub), `inBonus`, `oncourt` | ours | unsourced; host returned 403 from this egress 2026-06-13 (API census) | `ingame/boxscore_read.py` parses the CDN payload for the API surface | reachability re-probe; no substitution-delta extraction anywhere |
| ESPN site.api scoreboard / summary | score, clock, linescores, fouls, timeouts, `winprobability[]` (reference only) | `inplay_capture_loop.LIVE_INTERVAL_SEC = 20.0` | nba is absent from `inplay_tick_latency.json` entirely (cell UNMEASURED, INGAME_CAPABILITY) | `ingame_live_state.live_state` -> (state_diff, frac_elapsed, p0) only | on-court 5, foul counts, timeouts, bonus are never extracted as features |
| Kalshi in-play moneyline (KXNBAGAME) | the price | 20 s loop; venue supports 5-10 s | ticker carries a date and no clock, so no tick is certifiable pre-tip (S81:51) | `nba_price_series.parquet` 8,399,632 rows / 2,572 events **[m]**; `nba_checkpoints_full.parquet` 465,249 rows / 1,593 games (S86) | -- |
| Polymarket CLOB book / midpoint | price, spread | -- | gamma `outcomePrices` is a lagged cache (memory `reference_ingame_data_sources`) | the 1,593-game checkpoint corpus is Polymarket | the live book is never captured for nba |
| Kalshi orderbook ladders | depth, queue, last-trade direction | `DEPTH_CAPTURE_EVERY_N_TICKS = 15` x 20 s = one pass / 300 s | -- | `data/cache/book_depth/kalshi/` is **empty, 0 files [m]**; no nba dir under `depth_history/` **[m]** | all of it -- S100's microstructure NULL is a CAPTURE verdict wearing a market verdict's label |
| paired grade store | (model_prob, devigged price) | per tick | -- | `data/cache/ingame_grade/nba/` **2 files [m]** | effectively nothing |

### 1b. WNBA

| source | WP-moving fields | cadence | latency | captured today | missing |
|---|---|---|---|---|---|
| cdn.wnba.com boxscore / playbyplay (Referer required) | `team.inBonus`, `players[].oncourt`, `timeoutsRemaining`, running score per action | ours | WAF-blocked from a later egress: HTTP 200 + Akamai HTML, detect by JSON-parse failure (memory) | fixture-verified code only | live reachability; the same lineup / foul / timeout fields as NBA |
| ESPN site.api | score, clock, `winprobability[]` (confirmed present for wnba) | 20 s | UNMEASURED | the play-by-play cache behind the S192 join | -- |
| Kalshi in-play moneyline | price | 20 s | -- | `wnba_price_series.parquet` 967,102 rows / 287 events **[m]**; 186,736 in-play ticks over 85 games (S192) | -- |
| state join | period, clock, score | -- | state age median 15 s, p90 132 s, 0 above 300 s (S192) | `wnba_checkpoints_full.parquet` 18,650 rows **[m]** = the 9.99 pct that joined | S199: PRE 165,191 / GAP 723 / POST 2,089 / FUTURE_ONLY 790 ticks unrecoverable |
| depth | ladders | 300 s hook | -- | `depth_history/wnba/` 14 files, 2026-07-05..07-27 **[m]** | never joined to the tick store |

### 1c. MLB

| source | WP-moving fields | cadence | latency | captured today | missing |
|---|---|---|---|---|---|
| statsapi GUMBO `feed/live` + `diffPatch` | base-out (`currentPlay.runners`), count, outs, inning/half, pitch velo/spin, `pitching.numberOfPitches`, pitching changes | `CV_GUMBO_LIVE_SEC` default 10 s, floor 5 s, backoff to 60 s | sub-250 ms server response (memory, 2026-07-04) | `gumbo_mlb_poller.py`; `data/domains/mlb/gumbo_live/` **1 file [m]** | the historical backfill (~3,780 GETs -> 1,601 games) is Neel's S62 row 3, licence DECIDE |
| ESPN summary `winprobability[]` | external reference | -- | -- | not captured | reference-only by rule, never a feature |
| Kalshi in-play moneyline (KXMLBGAME) | price | 20 s capture loop | tick p50 31.0 s / p90 82.0 s over 371 games / 79,441 ticks (INGAME_CAPABILITY) | `mlb_price_series.parquet` 13,473,591 rows **[m]**; `ingame_grade/mlb/` **405 files [m]**; scored 47,104 ticks / 158 game_ids = 392 real games (S119, S106) | only 4.68 pct of the 3,780 priced events can be given state (memory `ingame_signals_first`) |
| Kalshi orderbook ladders | depth, ms trade tape | `mlb_book_capture.TARGET_CADENCE_SEC = 5.0`; achieved median 30.0 s / p90 64.8 s while live (S105) | the pass itself costs about 30 s | pod `mlb_book_capture`: 3,818 rows over 6 game_pk on 2026-09-02 (S105); local `depth_history/mlb/` 15 files 2026-07-05..09-02 **[m]** | `m37_ingame_enrichment` has NEVER run on the pod (S105) |
| cross-venue lag | -- | -- | `latency_audit.json` median 34.0 s, whose own caveat records 129/135 = 95.6 pct of matched events moving on Kalshi BEFORE our tick (INGAME_CAPABILITY) | -- | a real venue timestamp: `schema_has_venue_ts = false` for every sport |
| domain as-of tables | bullpen, platoon, umpire, catcher | pregame | -- | 1 of 5 members suppliable (umpire only) on the screen side (S119 0b) | bullpen ends 2026-07-02; `home_sp_hand` 0 non-null of 459; no catcher assignment; no pitch-grain feed joined |

### 1d. Soccer

| source | WP-moving fields | cadence | latency | captured today | missing |
|---|---|---|---|---|---|
| FotMob `matchDetails` | per-shot xG/xGOT (`content.shotmap.shots`), per-minute momentum, live team stats | ours | no documented limit; some paths need an `x-mas` header (API census NOT VERIFIED) | `fotmob_backfill_soccer.py`; `soccer_shotstates__*`, `soccer_cardstates__*`, `soccer_states__eng1` 7,220 rows (INGAME_SIGNAL_PROGRAM) | per-minute momentum series; substitution timeline; live cards |
| ESPN soccer summary | shots, SOT, possession, corners, cards (no xG) | 20 s | UNMEASURED | not wired to any feature path | cards and subs as first-class fields |
| Kalshi in-play (KXEPLGAME etc.) | price | 20 s | soccer_intl tick p50 29.0 s / p90 52.0 s over 68 games / 9,182 ticks (INGAME_CAPABILITY) | `soccer_price_series.parquet` 204,435 rows / 89 events; `soccer_intl_price_series.parquet` 2,261,903 rows **[m]**; `ingame_grade/soccer_intl/` 69 files **[m]** | **neither price-series store has ever been read by any module** (grep of `scripts/platformkit/` + `docs/evidence/` for `soccer_price_series`: 0 hits **[m]**) |
| scored corpus | -- | -- | -- | S117: 9,003 ticks / 51 games, usable 29 games / 3,658 ticks, scored 163 ticks / 2 clusters | the 2,466,338-tick price store above is 250x the scored one and uncensused |

### 1e. Tennis

| source | WP-moving fields | cadence | latency | captured today | missing |
|---|---|---|---|---|---|
| point-level serve / score state | server, point score, game and set score, break points | -- | -- | **none** | structurally absent keyless everywhere probed (repo 2026-07 probe + API census): ESPN caps at set-final linescores and has no tennis summary endpoint (400); ATP/WTA official 403/404; Sportradar Live Timelines is paid and tier-gated |
| Kalshi in-play (KXATPMATCH) | price | 20 s | `ingame_grade/tennis` is 812 games / 814 ticks = one snapshot per match (INGAME_CAPABILITY) | `tennis_price_series.parquet` 1,854,100 rows **[m]**; 1,864 events (S81:52) or 986 events (S80:79) -- the two artifacts DISAGREE; `ingame_grade/tennis/` 1,238 files **[m]**, 1,255 rows of which 1,237 are one `state_summary=FINAL` and 18 are priced with `home_score=0 away_score=0` (S80:78) | any state at all; the 1.85M-row store has never been classified in-play vs pre-match |
| offline states | surface, set / game score | -- | -- | `tennis_states__atp` 40,516 rows, `tennis_states__wta`, `tennis_gamestate__*` | no in-play close joined; ATP and WTA are disjoint key spaces (memory `soccer_tennis_corpus_wiring_blockers`) |

### 1f. The measurement missing in EVERY sport

`inplay_tick_latency.json` reports `schema_has_venue_ts = false` for all sports and carries no
`src_ts_coverage_pct`, so `EVENT_REACTIVE` (lag_p90 <= 5.0 s AND coverage >= 95.0 pct, the frozen
gates in `latency_scoreboard.py`) is structurally unreachable and the capability matrix fails it
closed on both halves (INGAME_CAPABILITY). The API census reaches the same conclusion independently
(its ranked gap 8: no file measures broadcast-to-feature lag end-to-end for any sport). Every
cadence number in section 1 is therefore an OUR-POLL number, not a freshness bound. Two stores hold
the raw material for a partial answer: the GUMBO poller stamps `captured_at` (our receive time)
beside `ts` (MLB's event wall clock), and the Kalshi trade tape is ms-precision. **-> S213.**

### 1g. The REFRESH layer -- regularly-refreshed sources that are not live feeds

The in-game engine's conditioning is not only what a live poll returns. Four classes refresh on a
post-game or daily cadence and enter the tick through an as-of join, and none has a census saying
what refreshes when, from which endpoint, and whether the join is leak-free:

| class | example fields | refresh cadence | on disk today | the leak-free join question |
|---|---|---|---|---|
| play-by-play archives | possession, lineup stints, foul events | post-game | `pbp_states_2024_25 / 2025_26`, `pbp_foul_states_*`, `possession_states_*` **[m]** | are they joined strictly before the tick's own game, or same-game? |
| Statcast pitch-level | velocity, spin, release; **velocity dip within a start as a pitcher-state signal** | post-game (and live inside GUMBO) | `mlb_pitch_states__2022..2026` **[m]**, 25 columns, no price column (S81:54) | the pitch tables are NOT joined to any tick store (S119: no pitch-grain feed joined) |
| workload / fatigue | pitch counts, rest days, back-to-backs, recent minutes | daily | `bullpen_relief_chains.parquet` 71,523 rows, **last date 2026-07-02** (S119 0b) | censored by the source's end date, not missing at random -- a stale as-of table silently degrades to a constant |
| lineup minutes / rotation | minutes projections, stint patterns | daily | `data/cache/team_system/player_rates.parquet` feeds `basketball_sim` | never reaches the in-game path (section 2) |

This is where per-sport knowledge lives -- a starter's velocity dipping 1.5 mph in the sixth is a
pitching-change probability the price may not carry yet -- and it is the cheapest information class
we already own. The row is a CENSUS first, not a feature: what refreshes, from where, at what
staleness at tick time, and whether each join is provably as-of. **-> S222.**

---

## 2. THE ENGINE PATH AS IT EXISTS TODAY

    live state         ingame_live_state.live_state(sport, gid) -> (state_diff, frac_elapsed, p0)
                       p0 auto-supplied from the leak-free pregame snapshot (P1 wire)
    model probability  model_fn -> predictor.predict_live; per sport:
                         nba     nba_logistic_pricer / nba_mechanism_ladder (price_checkpoint
                                 over an as-of Elo prior)
                         mlb     mlb_winprob_v2..v7 + ingame_baseout_mlb / ingame_ladder_mlb_baseout
                         soccer  ingame_ladder_* / a carried pregame prior
                         tennis  a carried pregame prior only
    reprice + blend    repricer_router.reprice -> the per-sport repricer + blend_apply.apply_surface
                       (freshness-weighted pregame prior -> realized state)
    live price         inplay_kalshi.fetch_inplay(sport); an illiquid market emits NOTHING
                       (is_liquid gate), so no pair is ever formed against a fake price
    pair + decide      inplay_daytrader.on_tick -> live_grade.capture_pair_once writes
                       (model_prob, devigged price) to ingame_grade/<sport>/<gid>.jsonl and
                       paper-decides in UNITS, idempotent, executed always False
    label              settle_stamp.stamp_final appends the held-out binary outcome at FINAL
    scoring            ingame_screen / s88_phase_recal / ingame_calibration_report ->
                       Brier, ECE, game-clustered DM CI, n_eff, against the frozen +0.004 bar

Timestamps: the model side is as-of-tick, `p0` is pregame, the price is the same tick's quote, and
the outcome is stamped only at FINAL. Staleness handling exists but is not default: `quote_freshness`
supplies a fresh-tick mask, `blend_apply` weights the prior by freshness, and `ingame_segment_trust`
gates a segment. Nothing forces a scored comparison to use the fresh mask.

The possession Monte Carlo (`src/sim/basketball_sim.simulate_game`, 683 lines; the CUDA-batched
`src/sim/fast_sim.simulate_game_fast`) and the player-projection stack
(`src/prediction/live_engine.project_from_snapshot`, 2,718 lines) are **not on this path**. Nothing
under `scripts/platformkit/ingame/` imports them, and every NBA in-game arm scored to date is a
logistic or ladder form over (period, clock, margin, prior). The engine has never priced a tick.
**-> S216.**

### Known defects on the path

| defect | evidence | consequence |
|---|---|---|
| freshness / venue timestamp | `schema_has_venue_ts=false` all sports; cross-venue median lag 34.0 s with 95.6 pct of matched events moving on Kalshi first (INGAME_CAPABILITY) | every model-vs-line comparison is scored against a price we may already be behind |
| held / stale ticks | MLB corpus 74.97 pct held market and 91.71 pct held model ticks (S87); soccer 10-40 pct of ticks carry a genuinely new quote, runs up to 62 (INGAME_CAPABILITY) | n_eff inflated; the fresh mask exists and is not applied by default |
| merged game keys | 227 `game_id` keys are 392 real games; 144 of 227 files span over 6 h (S105, S106, S119) | cluster counts, hence every CI, were wrong until re-clustered |
| cadence dependence | dedup_period and line_move reads of the same 2 games differ in sign (memory `feedback_ingame_cadence_dependence`) | any decision cadence must be declared; a period-end read is a staleness ceiling, never a headline |
| news gap | market sharper at end_q1 (-0.0084 [-0.0161, -0.0008], n 1592), indistinguishable from halftime on (ingame-conditioning) | the early deficit is information (lineups, scratches), not calibration; the state-lag-artifact explanation was REFUTED at full power (memory `project_kalshi_paper_ready`) |
| tail defect | model above 0.8 on the eventual loser in 11.4 pct of lost NBA games vs the market's 5.6 pct (S58 trial B); the same on MLB (S43) | premature confidence is the shared shortfall of both model sides, and it has never been screened as a guard on NBA |
| capture, not market | `book_depth/kalshi/` empty **[m]**; `m37_ingame_enrichment` never ran on the pod (S105) | the microstructure NULL cannot be attributed to the market |

---

## 3. PER-SPORT HYPOTHESES -- where fresh state could be ahead of the in-play price

Each carries the metric that would prove it under the standing discipline: leak-free walk-forward
(purged, symmetric embargo), >= 2 corpora or corpus_units, n >= 30 game clusters, a game-clustered
DM CI, BH over the enumerated family, and a fresh-process reproduction from an archived per-game
series. None is a claim. The wave verdict already refutes the tick-resolution forms on NBA with data
on disk (INGAME_WAVE_VERDICT) -- do not re-run those.

| sport | hypothesis | mechanism the price may lag | metric that would prove it | row |
|---|---|---|---|---|
| nba | rest-of-game possession simulation from the tick state prices the tail better than a logistic form | the sim carries lineup, usage and pace structure that a ladder collapses into a margin term | tick-weighted Brier + ECE + max-loser-WP share above 0.8 vs the line, game-clustered CI over 1,593 clusters | S216 |
| nba | a tail-asymmetric guard: clamp tighter when abs(p - 0.5) > 0.3 | the shortfall is entirely in the confident tail on BOTH sports | improvement vs the S123 incumbent with the confident-side cut FROZEN, BH over the enumerated family | S219 |
| nba / wnba | on-court 5, foul trouble, bonus, timeouts remaining -- carried by payloads we already fetch and never extracted | a fifth foul or a bonus flip changes the rest-of-game distribution before the score does | first a CONSTRUCT census of which fields the parsers actually keep; no Brier until the fields exist | S218 |
| wnba | the per-phase recalibration that produced the one CI excluding zero on MLB | 85 clusters, state age p90 132 s | already allocated as S206; not duplicated here | S206 |
| mlb | a run-scoring event moves the state before it moves the line | GUMBO is sub-250 ms; our capture is 20-30 s; the line's own reaction time is unmeasured | lead-time distribution from the GUMBO event `ts` to the first line move, per event class, with a placebo on non-event ticks | S220 |
| mlb | base-out and leverage state read against depth captured DURING the game | the 300 s depth hook cannot see a within-inning ladder | first capture at <= 10 s during scored games; no arm until the store exists | S217 |
| mlb | starter velocity decline within the outing as a pitching-change and run-expectancy signal | Statcast pitch grain refreshes post-game and is never joined to a tick | first the refresh-layer census: what refreshes, at what staleness, joined how | S222 |
| soccer | in-play xG-state vs the price on the 2.47M-tick store nobody has read | a high-xGOT shot that misses moves xG-state and not the score | first classify the ticks in-play and count how many can receive an as-of state | S214 |
| tennis | point-level state vs the price | -- | not testable: no keyless point feed exists. First bound the price-side denominator honestly | S215 |

---

## 4. WHAT CANNOT BE DONE WITH DATA ON DISK, AND WHAT WOULD UNBLOCK IT

| blocked | why (cited) | what unblocks it |
|---|---|---|
| MLB state for the 3,780 priced events | only 4.68 pct can be given state from disk (memory `ingame_signals_first`) | Neel's S62 row 3: a keyless statsapi `feed/live` backfill, ~3,780 GETs -> 1,601 games. The licence ledger marks MLB Stats API DECIDE -- a HUMAN decision, never fetched autonomously |
| MLB pitch-grain members | no pitch-grain feed is joined to the tick store (S119 0a) | the same backfill at pitch grain; S222 first says whether the offline pitch tables can bridge it as-of |
| MLB bullpen / platoon / catcher as-of | bullpen ends 2026-07-02 with 8 rows over 2 teams; `home_sp_hand` 0 non-null of 459; no catcher assignment table (S119 0b) | forward accrual of the domain tables, which is a refresh-layer question (S222), not a model change |
| NBA / WNBA microstructure | `book_depth/kalshi/` empty **[m]**; depth captured pre-game only (S100) | S217's capture pattern extended to nba and wnba once it is proven on mlb |
| tennis in-play verdict | no keyless point or serve state anywhere; `ingame_grade/tennis` is 1,237 FINAL rows plus 18 priced rows with a zero score (S80:78) | a paid tier (Sportradar Live Timelines, tier-gated point-by-point) -- a HUMAN purchase decision. Until then tennis is a price-side denominator only |
| soccer in-game market-relative verdict | S117 CLOSED AT LIMIT at 2 scored clusters | S214 first; if the 2.47M ticks classify in-play and join a state, the corpus exists with no acquisition at all |
| any EVENT_REACTIVE claim | `schema_has_venue_ts=false` everywhere and `lag_p90` absent (INGAME_CAPABILITY) | S213 measures what the stores CAN answer and names what they structurally cannot |
| tracking-derived features | three hand-off conditions unmet (memory `tracking_handoff_contract_2026_09_04`) | out of scope this round, by the user's order |

---

## 5. HOW METHODS GET TESTED ON THE POD, AND HOW HARD IT CAN BE PUSHED

**Throughput measured today.** One pod hour produced 3,780 T1 screens over 6,000 claimed hypotheses
against a bar of 200 (18.9x), and the hour was QUEUE-BOUND, not throughput-bound: the queue drained
in 1,458.3 s, so the sustained rate while claimable work existed was **9,331.5 screens per hour**
(0.386 s per covered screen, 0.243 s per claim including fast failures) -- S16_pod_hour section 4.
The IN-GAME tier is about 3x more expensive per screen: S102 ran 576 NBA in-game hypotheses in
634.8 s = **3,266.7 screens per hour**, mean 1.07 s and median 0.93 s per screen (S102:208).

**What limits it.** The screens are pandas over a tick CSV, so the binding cost is CPU and store IO
per screen, not GPU; the GPU is idle for every screen in section 3 except S216's simulation, which
is the one row that can use it (`fast_sim` is CUDA-batched). The second limit is the queue: two of
the last three measured hours ended idle, which is a seeding problem, not a compute problem. The
third is sqlite -- seeding while the runner is live once killed it with `database is locked` (S109);
`results_db` now connects with `timeout=30.0` (S110) but the runbook rule stands: pause the runner
or seed in small batches.

**Scaling safely.** A second concurrent runner was unsafe: the 900 s lease had no renewal and
`reap_expired` was global, so runner B re-claimed runner A's live hypotheses at +901 s, and a
sport-NULL hypothesis was claimable only by an unbound runner (S135, reproduced). S135 landed a
`renew(hashes)` heartbeat; S150 landed lease scaling, `host:pid` claimer identity and
normal-exit / SIGTERM / SIGINT cleanup -- but S150 finished **unverified at session close**
(commit 3c72a5bbc). So multi-runner is *probably* fixed and *not proven*. Nothing in this program
should launch a second runner until a two-runner probe measures 0 double-claims and reports the
aggregate rate. **-> S221.**

**Lane rules for every pod job here.** A pod job is a script with a `__main__` and no interactive
input; the evening batch deploys and launches it, and the lane reports the files it WOULD deploy
without deploying them (contract B5). It runs under its own `nohup setsid nice` with a unique `/tmp`
log, kills nothing, does no git. A live-capture job (S217) must be **resumable** -- append-only,
keyed by (date, ticker, ts), so a restart never duplicates and never loses a window -- and
**rate-limit safe**: honour the existing 429 backoff (`TARGET_CADENCE_SEC` doubling to
`MAX_CADENCE_SEC`), never poll faster than the venue's documented 5-10 s guidance, and stop by
READING a stop flag, never by a kill. Backtests read one store at a time and never a store over
300 MB in one read; of the stores in section 1, `mlb_price_series` 33.9 MB, `nba_price_series`
25.1 MB, `soccer_intl` 5.8 MB and `tennis` 4.9 MB **[m]** are all under the cap, and the JSONL trees
are read file by file. Nothing is written under `data/` (never `data/registry/`), no flag is
flipped, and the register and ledger are never touched by a lane.

---

## 6. RANKED ROWS -- expected calibration effect per unit of work

Rank is across the new rows AND the already-queued in-game rows, so this is one queue.

| rank | id | sport | slug | why here | effort |
|---|---|---|---|---|---|
| 1 | S212 (queued) | all | regime_key_oof continuation | the published pregame table stays provisional until it lands | S |
| 2 | S217 | mlb | mlb_depth_capture_pod | a capture row accrues while every other row runs; starting it late costs games that never come back, and it converts S100's microstructure NULL from a capture artifact into an answerable question | M |
| 3 | S213 | all | ingame_latency_ledger | every cadence number in section 1 is an our-poll number; until this lands no freshness statement in any sport is a bound. Cheap: the material is already in the stores | S |
| 4 | S214 | soccer | soccer_inplay_census | 2,466,338 ticks no module has ever read, against a scored corpus of 163 ticks / 2 clusters. The largest possible denominator change for zero acquisition | M |
| 5 | S222 | all | refresh_layer_census | the cheapest information class we already own (pbp, Statcast pitch grain, workload, lineup minutes) and the one with a live staleness hazard measured on disk (bullpen ends 2026-07-02) | M |
| 6 | S207 (queued) | all | ingame_gap_decomposition | tells every later lane whether recalibration can pay at all on nba and wnba | M |
| 7 | S221 | harness | pod_multirunner_probe | unblocks pushing the pod hard; S150's fix is unverified and a second runner today can silently re-claim live work | S |
| 8 | S215 | tennis | tennis_inplay_census | bounds a whole sport honestly; the expected result is a price-side denominator with 0 joinable state, which closes the tennis in-game question with a number instead of a memo line | S |
| 9 | S218 | nba | nba_live_field_census | the API census's top uncaptured field (lineup delta) and its 4th (foul trouble, timeouts) sit in payloads we already fetch; a CONSTRUCT census costs one lane and sizes every later feature row | S |
| 10 | S209 (queued) | mlb | mlb_phase_recal_fwer | corrects the one measured in-game positive | S |
| 11 | S220 | mlb | mlb_event_lead_time | measures the market's own reaction latency to a scoring event -- power-independent, and the only direction the NBA wave (S96) found any movement in | M |
| 12 | S216 | nba | nba_sim_engine_vs_line | the possession engine has never priced a tick; the user's explicit "wire it into simulations". Expected BEHIND (S99 on MLB), which is the valid result | L |
| 13 | S219 | nba | nba_tail_guard_screen | the shared defect of both model sides, never screened on the 1,593-cluster corpus | M |
| 14 | S210 (queued) | all | ingame_power_audit | stops the program spending lanes on unmeasurable questions | M |
| 15 | S211 (queued) | all | ingame_headline_rederive | the flagship pairs are quoted publicly and were never re-run | M |

S206 (wnba first score) and S208 (nba phase recal) are already ranked in
`MODEL_QUALITY_PROGRAM_2026-09-04.md` section 3 and are not re-ranked here; on that memo's own
ordering both sit above rank 6 of this list.

---

## 7. THE THREE BIGGEST DATA GAPS

1. **MLB in-game state for the priced events.** 95.32 pct of the 3,780 priced events cannot be given
   state from disk. Unblocked only by Neel's S62 row 3 (statsapi backfill, licence DECIDE) -- a human
   decision, and the single largest corpus unlock in the program.
2. **Depth / microstructure captured during live games.** `book_depth/kalshi/` is empty and the
   enrichment runner has never run on the pod, so the entire microstructure class was closed on a
   capture defect. S217 fixes the capture; no arm is proposed until the store exists.
3. **Soccer and tennis in-play price stores nobody has read.** 4,320,438 ticks across
   `soccer`, `soccer_intl` and `tennis` price series have never been classified in-play, while the
   scored soccer corpus is 163 ticks over 2 clusters. S214 and S215 need no acquisition at all.

---

## 8. NOT VERIFIED

- No arm was run and no number was re-derived by this lane. The only fresh measurements are the
  **[m]** cells: parquet row and column counts, plus file-tree listings, taken 2026-09-04 read-only.
- `tennis_price_series` event counts DISAGREE between artifacts (S81:52 says 1,864 events, S80:79
  says 986). I did not reconcile them; S215 must re-measure before quoting either.
- The "never read by any module" claim for `soccer_price_series` rests on a grep of
  `scripts/platformkit/` and `docs/evidence/` only **[m]**; other trees were not searched.
- Section 1's latency column mixes measured tick gaps (mlb, soccer_intl) with UNMEASURED cells
  (nba, wnba, tennis). No cell is an end-to-end freshness bound -- see 1f.
- `INGAME_CAPABILITY_2026-09-01.md` is three days old; none of its cells was re-run today. The
  API-side endpoint facts (paths, auth, rate limits) are consumed from
  `docs/research/ingame_api_census_2026-09-04.md` and inherit that document's own NOT VERIFIED list,
  including current reachability of cdn.nba.com and cdn.wnba.com and whether Kalshi's orderbook read
  path requires signed headers.
- S150's landing is recorded as finished but UNVERIFIED at session close (commit 3c72a5bbc); the
  multi-runner statement in section 5 rests on that unverified state, which is why S221 exists.
- Section 1g's refresh cadences are inferred from store contents and builder names, not from
  observing a refresh; S222 must measure them.
- The engine-path diagram in section 2 was assembled from module docstrings and the S105 / S119 /
  S123 memos, not traced at runtime; rank order in sections 6 and 7 is my judgement of
  effect-per-work, not a measurement.
