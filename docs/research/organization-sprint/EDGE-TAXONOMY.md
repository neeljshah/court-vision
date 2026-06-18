# EDGE-TAXONOMY -- Ranked Master Map of Information-Edge Candidates

*The ranked enumeration of every information-edge candidate from the 10 domain
sweeps (availability-latency, warmup-visual-CV, referees-officiating,
lineup-rotation, schedule-fatigue, motivation-situational, market-microstructure,
in-game-state, environment-weather, sentiment-meta), scored against the 3 tests.*

THESIS (binding): the edge is NOT a better prediction -- the market is efficient on
PRICE. The edge is a PROPRIETARY + PREDICTIVE + TIMELY input the market has not
priced yet, MANUFACTURED by intelligence-at-scale (an LLM extracting unstructured
sources faster/more completely than the market), then COMBINED into ONE bounded net
adjustment on an EXISTING model knob that fires only BEFORE the line moves.

THE 3 TESTS (else honest REJECT, recorded as SUCCESS):
1. PROPRIETARY -- the market lacks it or cannot process it at our scale/speed.
2. PREDICTIVE -- provably lowers OOS Brier vs the SHIN-devigged close, leak-free, on
   >=2 real corpora.
3. TIMELY+EXECUTABLE -- availability_timestamp BEFORE the line move; placeable before
   close.

HONESTY RAILS: the LLM extracts FACTS + an EXTRACTION confidence ONLY -- never a
probability/number that enters the prediction chain. Every signal carries an
availability_timestamp; the vintage guard asserts it < line/pred time. NO edge is
CLAIMED until it passes the gate on REAL data with forward CLV. The deliverable is the
MACHINE + the MAP, never a fabricated found edge. No $-edge / ROI / +EV language.

---

## THE COMBINE STRATEGY (2 lines)

Each weak signal is extracted as a FACT + EXTRACTION confidence and mapped (deterministically)
to a signed lean in {-1,0,+1} on ONE existing model knob (pace / off_eff / def_eff /
minutes_load / total_pts); `edge_engine/combine.py` fuses them as
`eff = 1 + sum_i(gate_weight_i * confidence_i * lean_i)`, hard-clamps to a TIGHT per-knob band,
and FIRES only when |combined lean| >= threshold AND every contributor's availability_ts precedes
the line move (one hindsight row refuses the whole fusion). Weak/conflicting evidence nets to ~0 =
a no-op (the honest default); the LLM authors no number, the gate assigns every weight, and the
single bounded multiplier is the only thing that touches a prediction.

---

## WHAT CAN BE TESTED NOW vs WHAT NEEDS A HUMAN-RUN / TIME-BOUND INPUT

The deliverable is the MACHINE (`source -> extract -> vintage -> score(gate) -> combine`,
all built and tested in `scripts/platformkit/edge_engine/`) + this MAP. NO edge is claimed.

**TESTABLE NOW (hermetic, on committed fixtures / replayable corpora):**
- The full pipeline end-to-end on offline fixtures: `FileSource/MockSource -> extract_rule
  (deterministic) -> schema.validate_signal -> score.score_candidate -> combine.combine_all`.
- The honesty rails: banned-field rejection, the vintage guard refusing a hindsight row, the
  combiner no-op on weak/conflicting evidence -- all per-file tested.
- The SCORER against ANY already-timestamped corpus: signals whose values are reconstructable
  leak-free from PBP-strictly-before-t (in-game foul-out, garbage-time onset) via the existing
  `pbp_replay` harness, scored vs a devigged close with clustered DM.

**NEEDS A LIVE FEED (forward-capture-only; cannot be backfilled without quarantine):**
- Every P0 latency signal (beat-writer pre-report, late scratch, warmup non-participation,
  MLB SP down-velo/scratch, mid-game injury exit). The whole edge is the lead in minutes; a
  post-hoc reconstruction is `is_fallback_proxy=True` = OPTIMISTIC_UPPER_BOUND, never a headline.
  Requires a running X filtered-stream / presser-ASR / broadcast poll with server-stamped
  created_at.

**NEEDS REAL HISTORICAL TIMESTAMPED DATA (>=2 corpora, walk-forward):**
- The PREDICTIVE test for every candidate. Tendency tables (ump zone, ref crew, contract base
  rates, status-word resolution) must be built strictly from games before the prediction date.
- Market-microstructure (RLM, steam, handle-vs-ticket) needs archived intraday multi-book +
  public-split snapshots with frozen poll timestamps (a PAID feed: The Odds API / Action / VSiN).

**NEEDS FORWARD CLV (the only honest proof of timeliness):**
- No SHIP verdict is valid until the signal is recorded in `ledger/` with a pred_ts BEFORE the
  line move and graded against the realized close. CLV > ROI; first real forward CLV is time-bound.

**NEEDS AN EXECUTION / SPEED LAYER:**
- The P0 latency + steam signals only pay if the bounded adjustment fires and a bet is placeable
  inside the 5-15 min (or seconds, for steam) window before the soft book catches up. That
  routing/speed layer is a separate human-gated build, not part of this map.

---

## P0 -- proprietary AND plausibly predictive AND timely (highest conviction)

| signal | sport | proprietary | predictive_hypothesis | timely_window | source+capture | llm_extracts | leak_free_capture | status |
|---|---|---|---|---|---|---|---|---|
| Beat-writer pre-report status tweet (status flip BEFORE official report) | nba | high | flips OUT/IN before official report leads the close; vacated-load reprices teammate ML/total/props | tweet created_at 1-20 min before official report; 5-15 min repricing | X filtered-stream on curated per-team beats; created_at = availability_ts | player, status enum, body_part, note span, confidence | created_at < official publish_ts; live stream only, no backfill | UNTESTED |
| Late SCRATCH detection (status flip to OUT 30-60 min pre-tip) | nba | high | latest+largest single move; arrives after market's main pass; vacated-load in seconds | 30-60 min pre-tip; books adjust 5-15 min | X stream beats/insiders/team channels; post created_at | player, status=OUT, span, confidence | extracted_at < tip; post-game DNP = fallback_proxy | UNTESTED |
| Warmup non-participation / abbreviated warmup of listed-active star | nba | high | QUESTIONABLE star not warming up => elevated late-scratch/minutes-limit vs morning report | 20-40 min pre-tip; before official scratch | RSN pre-show ASR + beat tweets, 30s poll; fetch_ts | player, in_warmup enum, observed_by, span, confidence | extracted_at < line snapshot; result-referencing text quarantined | UNTESTED |
| MLB pitcher down-velo bullpen + late starter scratch | mlb | high | down-velo/late-scratch shifts run environment the close (priced off announced SP) has not absorbed | bullpen ~30-40 min pre-first-pitch; scratch to lineup-card | curated MLB beat feeds, 30s poll; fetch_ts | pitcher, warmup_velo_note, scratch, replacement, span, confidence | extracted_at < first pitch; recap velo text quarantined | UNTESTED |
| Mid-game injury / gait-limp / trainer-attending event | nba | high | largest live re-pricing event; book waits for official ruling; vacated-load reprices live in seconds | minutes between visual cue and official in-game status | broadcast crop + announcer + CDN sub event, 5-10s poll | player, exit-event enum, returned, clock, confidence | extracted_at < live snapshot AND < official status; reuse freshness guard | UNTESTED |
| Star foul-out / foul-trouble bench risk (live) | nba | medium | foul state conditions minute-share/vacated-load the score-only live blend is blind to | instant whistled; 10-45s before next dead-ball repricing | CDN liveData foul column (spine) + broadcast graphic | personal_fouls:int, in_bonus, on_bench, clock, confidence | reconstruct count from PBP strictly-before-t; vintage < live snapshot | UNTESTED (foul-out is the ONE validated in-game lever) |
| MLB plate-umpire zone-size / CSAA -> total + team-K | mlb | high | larger zone raises K/called-strike, lowers runs; books under-weight the specific plate ump posted | assignment posts morning-of; total slow to absorb ump | UmpScorecards + Baseball Savant; scrape ts; tendency from prior games only | umpire_name, role=plate, game_date, source_url, note | extracted_at < first pitch; tendency walk-forward, no future pitch | UNTESTED (no prior art) |
| Soccer center-ref cards/pens/VAR -> total-cards + booking-points | soccer | high | card/pen rates strongly ref-specific; booking markets thin and lag the appointment | appointment 1-3 days pre-match; >24h to close | PGMOL/league appointment + ref-stats aggregators; scrape ts | match_id, center_ref_name, VAR official, source_url, note | extracted_at < kickoff; tendency same-competition, prior matches only | UNTESTED (goals likely REJECT; cards = the live test) |
| Confirmed-lineup CONFIRMATION-TIMESTAMP delta (NBA) | nba | medium | exact confirm/scratch moment lets vacated-load fire on teammate totals before book's 5-15 min pass | beat post / 30-min graphic; 5-15 min repricing | NBA report poll + beat X; extracted_at = post wall-clock | role-state transition, evidence span, source, confidence | extracted_at < close; box-score reconstruction = fallback_proxy | UNTESTED (extends freshness X1) |
| NEW starting-five / rotation-combo NOVELTY flag (NBA) | nba | high | never-before-seen unit has no stable team prior => WIDER realized dispersion than priced | lineup-lock 30 min pre-tip; not repriced until tip/mid-game | confirmed starters diffed vs rolling started-units table + presser | players in unit, is_first_start (deterministic), coach reason span | novelty bool from units start_date < game_date; interval-widening fit walk-forward | UNTESTED (the CHANGE-not-LEVEL signal the on/off REJECT left open) |
| Soccer projected-XI rotation leak under fixture-congestion | soccer | high | 5-7 starter rotation shifts both sides' xG; market reacts hard at team-sheet, leak precedes it | rotation hints 3-24h out; sheet at T-60min | beat/insider X + presser, poll to team-sheet; fetch_ts | player, rest-status enum, reason, span, confidence | extracted_at < kickoff AND < official sheet; else just the public sheet | UNTESTED |
| Tennis in-tournament physical-load + niggle -> retirement/under-perform | tennis | high | load+niggle is a CURRENT-CONDITION fact static surface-Elo cannot ingest | cumulative load known at round resolution; niggle leak minutes-hours pre-match | live-score feed (load) + injury-mention posts; fetch_ts | player, body_part, treatment/withdrawal status, span, confidence | load from prior rounds only; niggle extracted_at < match start; distinct from REJECTED surface-specialism | UNTESTED |
| Reverse line movement (RLM): line moves AGAINST public bet% | all | medium | book moving toward low-bet%/high-handle% side = informed flow; front-run the correction the book completes by close | minutes-hours before close; soft books lag steam leaders | multi-book aggregator + public-split feed, 60-90s poll; poll_ts | book, market, side, bet%, handle%, line, quote_ts (transcription only) | quote_ts < predicted move; forward-replay only; post-game splits quarantined | UNTESTED (paid feed; orthogonal to the 60/60 box-feature rejects) |
| Steam-move detection: 3+ books move same dir >0.5 pt in ~60s | all | medium | coordinated informed flow; soft lagging book not yet repriced; latency not a better model | seconds-to-minutes lag at the soft book | multi-book tape 30-60s + steam-alert text; alert_ts | market, side, from/to line, books listed, alert_ts (transcription only) | admissible only vs a book stale at same poll_ts; forward-replay >=2 corpora | UNTESTED (paid feed) |
| Tank-commitment regime shift (org pivot to development) | nba | high | explicit org pivot precedes observable rotation collapse; strength prior stale before box scores move | doc day-of/day-before; window ~3-5 days until form reprices | beat columns / GM pressers, AM poll; first_seen_utc | org_signaled_development bool, vet-rest facts, span, confidence | first_seen_utc < line snapshot; final-standings reconstruction quarantined | UNTESTED (standings flag REJECTs; qualitative text is the residual) |
| Coach hot-seat instability -> rotation-volatility regime | all | medium | job pressure widens outcome DISPERSION (totals) + soccer caretaker bounce on first game | instability builds over days; doc before sacking/first match | insider + beat + coach-firing odds, AM poll; first_seen_utc | job_security_threatened bool, scheme/rotation intent, span, confidence | doc < line; sacking date a separate deterministic fact; post-sack reconstruction quarantined | UNTESTED (targets DISPERSION = the proven-winning lever class) |
| Charter arrival disruption (late/cross-tz arrival) | nba | high | specific disruption deepens a generic (priced) b2b spot; conditions the b2b physics knob | night-before / morning-of; hours before total firms | beat X + ADS-B flight-tracker text; snapshot ts | charter delayed/diverted, arrival time, miles/tz crossed, span | availability_ts < line_move_ts; hindsight trips LEAK | UNTESTED |
| Actual travel party (who really made the trip) | all | high | fatigue is player-specific; box-calendar assumes full roster traveled (often false on long swings) | shootaround ~10am-noon local; before lineup line moves | beat availability/shootaround reports; report ts | which players traveled / stayed / arrived separately, names, span | report ts < line_move_ts | UNTESTED |
| Coach-stated rotation on a fatigue spot | nba | high | stated rest plan redistributes minutes the market has not priced on a known 3-in-4 spot | presser ~1-3h pre-tip; live minutes window | presser transcripts / beat quotes; post ts | verbatim rest/cap quote + player names, confidence | post ts < line_move_ts | UNTESTED |
| MLB September call-up / playoff-eliminated lineup shift | mlb | medium | eliminated team fields materially weaker roster than season form; ML/total slow until card | elimination flips on a date; shutdown/call-up text in following days | standings (deterministic) + beat shutdown/call-up reports; first_seen_utc | innings-limit/shutdown statements, prospect promotion, span | elimination as-of game date; doc < line; post-hoc quarantined | UNTESTED |
| Beat-reporter injury-rumor PROPAGATION SPEED (latency, not rumor) | nba | high | verbatim phrasing carries status delta minutes-hours before structured/priced; bet the opener in the gap | tweet-time to official report / book move | curated ~120 beats via X filtered stream; tweet created_at | player, claimed status, body_part, first-vs-confirmation, span, confidence | extracted_at = platform created_at < line move; post-hoc quarantined | UNTESTED (the validated #1 freshness/CLV lane) |

## P1 -- refinement / structural layers (real but smaller, some absorption risk)

| signal | sport | proprietary | predictive_hypothesis | timely_window | source+capture | llm_extracts | leak_free_capture | status |
|---|---|---|---|---|---|---|---|---|
| Official injury-report STATUS-WORD resolution P(plays) | nba | medium | per-team/player QUESTIONABLE resolution beats league-average prior the instant report drops | 1pm/5pm ET drops; soft tags reprice over hours | NBA injury report poll; as-of ts; base-rate table walk-forward | typed status row per player, body_part, severity (table is deterministic) | report as-of ts; resolution table strictly prior games | UNTESTED (likely partial/ABSORBED) |
| Minute-restriction / load-management LANGUAGE | nba | medium | restriction => stale-high prop + teammate usage up; book lags secondary props | report drop or pre-game beat; cascade slow | X stream + report; source created_at | minutes_restriction/ramp_up/b2b_sit_risk bools, span, confidence | created_at; flag->minutes map walk-forward; box-score inference quarantined | UNTESTED |
| G-League / two-way activation + call-up usage spike | nba | high | no NBA baseline => crude pricing; tighter G-League/college prior at activation time | activation hours-to-day pre-game; obscure player slow | transactions feed + team announcements; announcement ts | player, transaction_type, team, game_date, span, confidence | announcement ts < tip; prior table walk-forward | UNTESTED |
| NBA referee CREW (3-ref) joint foul/FTA/pace -> total | nba | medium | foul/FTA is a crew property (interaction), not a single-ref sum; books price marquee ref only | crew posts ~9am ET; trio component lingers | official.nba.com assignments 9am scrape | game_id, ref1/2/3, crew_chief flag, source_url | scrape ts < tip; crew tendency walk-forward | UNTESTED (single-ref likely ABSORBED; interaction is the test) |
| NBA L2M per-ref clutch-error profile -> live total micro-tilt | nba | high | high recent missed-call/make-up refs => fatter late FTs/stoppages; live total mis-calibrated | tendency known ahead; targets the LIVE late re-price | official L2M reports; post ts; rolling per-ref table | game_id, ref, call_type, decision enum, players, span | L2M post_ts < tip; same-game L2M does not exist pre-game | UNTESTED (likely redundant w/ crew foul-rate) |
| Garbage-time onset / starter-pull detection (live) | nba | medium | benched starters shift pace+variance; book reprices live total over a stoppage or two | substitution instant; warmups cue ~1 possession early | CDN sub events (spine) + bench crop, 10s poll | benched starters:int, warmups_on bool, score_diff, clock | reconstruct from PBP strictly-before-t; vintage < live total | UNTESTED |
| Coach timeout / ATO stabilization (live) | nba | medium | timeout by trailing team on a run => post-ATO stabilization the momentum-naive blend extrapolates | whistle instant; dead-ball ~60-90s | CDN PBP timeout event + graphic | calling_team, timeout_type, score_diff, run (PBP-computed) | timeout ts from PBP strictly-before; vintage < post-TO snapshot | UNTESTED (likely REJECT if redundant w/ margin) |
| Who-guards-whom matchup structure (NBA) | nba | high | book prices average-defense, not the specific confirmed-defender quality | lineup-lock; not repriced for the matchup | NBA leagueseasonmatchups + confirmed starters | stated cross-match span (assignment prob is deterministic), confidence | matchups as-of game date, no season-final; predicted from confirmed starters | UNTESTED (predictiveness UNVALIDATED) |
| Post-trade integration window (days-since-trade decay) | nba | medium | traded player underperforms ~first 10 games; books discount too small | trade post hours-days pre-game; refined at lock | transactions feed + first lineups + pressers | player, from/to team, trade_date (feed), coach role span | trade_date from feed; decay fit walk-forward; reconstruction quarantined | UNTESTED (SPARSE corpus -> single-fold risk) |
| MLB confirmed-SP / lineup-card timing | mlb | medium | confirmed SP is dominant total/ML input; capture confirm ts before full repricing | probables ~3-4h out; scratch to first pitch | MLB lineup cards + probable feeds + beat; post ts | confirmed/scratched SP, key bat rest, span, confidence | extracted_at < first pitch; SP-swap from prior ratings walk-forward | UNTESTED (well-watched -> pure speed) |
| Soccer confirmed-XI vs predicted-XI delta | soccer | medium | unexpected key rotation at ~60min sheet shifts O/U + match odds set on predicted XI | team sheets ~60 min pre-kickoff | official sheets + club X; sheet release ts | confirmed XI, unexpected in/out names, span, confidence | sheet ts < close; reconstructed sheets quarantined | UNTESTED |
| Tennis venue-day condition (heat/altitude/wind/roof) ball-speed | tennis | medium | fast conditions favor servers vs grinders; static surface-Elo treats surface constant | conditions firm day-of; roof/session hours pre-match | weather API + roof-decision posts; issue_ts/fetch_ts | roof_state, session, ball_brand, condition span (numbers from API) | issue_ts < match; archived forecast not realized; distinct from surface-specialism | UNTESTED |
| MLB wind VECTOR x park fence-geometry -> total | mlb | medium | books price scalar wind flag, not bearing-vs-fence dot-product / gust-vs-sustained | T-3h to T-1h forecast revision + roof decision | weather API + park geometry table + roof state; issue_ts | roof_state, precip flag, verbatim wind phrasing (numbers from API) | forecast issue_ts < first pitch; archived forecast only | UNTESTED (scalar-wind part likely REJECT) |
| Soccer pitch-condition + matchday weather total-suppression | soccer | medium | severe weather/degraded pitch suppresses tempo; books underweight extreme/inspection games | forecast day-of; inspection 2-4h pre-kick | weather API + pitch reports; issue_ts/fetch_ts | pitch-state phrasing, precip span (numbers from API) | issue_ts/fetch_ts < kickoff; archived forecast | UNTESTED (tail games only) |
| Seeding-locked motivation collapse + stated rest (NBA) | nba | medium | locked team that STATED rest != box-score average; timing gap locked->plan->box scores | lock flips a night; quotes following 1-3 days | standings (deterministic) + rest-intent quotes; first_seen_utc | rest-intent statements, span, confidence | magic-number as-of date; quote < line; split math-only vs early-text | UNTESTED (math half ABSORBED) |
| Bet%-vs-handle% divergence (dollars vs tickets) | all | medium | money% >> ticket% = few large informed bets; line not yet absorbed; available before any move | earliest of the family; minutes-hours | public-split feed (VSiN/Action); as-of/quote ts | market, side, ticket%, money% (transcription only) | quote_ts < move; no end-of-day final splits; intraday only | UNTESTED (thin data; paid) |
| Softest-book / line-origination profile | all | low | identify the consistently-laggy book; treat its number as a stale estimator of consensus | continuous open-to-close | multi-book tape; per-book lag profile rolling | book, opened/moved ts + lines (transcription only) | lag profile strictly past snapshots; soft catchup_ts > signal_ts | UNTESTED (supporting infra, multiplicative) |
| Cross-book dispersion / outlier-book | all | low | outlier book at T hasn't priced info consensus has; reverts to consensus | instantaneous; widest after news | multi-book tape cross-section; poll_ts | book, market, line, price, snapshot_ts (transcription only) | single-instant cross-section; consensus from same poll_ts only | UNTESTED (much is vig/limit, not info) |
| National-TV / marquee narrative LINE-INFLATION fade | all | medium | rec money inflates glamour side/OVER in marquee slots; persists to close | broadcast known days ahead; inflation peaks day-of | schedule + opening/closing lines; schedule-release ts | network, marquee flag, public-favorite side, reason, confidence | schedule-release ts (fixed, leak-free); narrative at publish ts | UNTESTED (raw dummy likely REJECT) |
| Hot/cold shooting variance mean-reversion (live) | nba | low | over-extrapolated hot streak; dispersion-correct reversion of remaining attempts | continuous; stoppage-to-stoppage | CDN box/PBP shot events (structured spine) | minimal: confirm broadcast callout (numbers from feed) | reversion from shots-before-t + pregame baseline; score RMSE+bias not MAE | UNTESTED (HIGH-skepticism; MAE-vs-RMSE artifact) |

## P2 -- least proprietary / sample-starved / structural (expect honest REJECT)

| signal | sport | proprietary | predictive_hypothesis | timely_window | source+capture | llm_extracts | leak_free_capture | status |
|---|---|---|---|---|---|---|---|---|
| Insider (Woj/Shams-tier) breaking-news latency | nba | low | breaks 3-10 min before official but is the STANDARD sharp baseline -> most-contested, likely ABSORBED | 3-10 min before official; seconds before fastest books | X stream on national insiders; post created_at | player, status, body_part, span, confidence | created_at < tip AND < official; post-hoc quarantined | UNTESTED (contrast baseline; expect ABSORBED) |
| Gait/limp asymmetry of returning player (human-observed, not CV pose) | nba | high | observed-limp predicts DNP-after-warmup the close underweights; LLM reads the human note, not pose | warmup 20-40 min pre-tip | beat/color-commentary ASR, 30s poll; fetch_ts | player, body_part, observation enum, observer_role, span | extracted_at < line; retrospective "clearly hurt" text quarantined | UNTESTED (swaps broken CV-pose sensor for LLM-over-observation) |
| Warmup shot-making streak (reported) | nba | low | warmup make-rate correlates only WEAKLY with game shooting | 20-40 min pre-tip | broadcast ASR / beat notes; fetch_ts | player, warmup_shooting enum, location, span | extracted_at < line; post-Q1 text quarantined | UNTESTED (near-certain REJECT: weak + mean-shift) |
| Late starting-lineup / rotation inferred from on-court presence | nba | medium | unannounced starter change shifts usage/spacing prior before the official lineup post | confirmed-starter chatter 25-45 min pre-tip | broadcast + beat tweets, 30s poll; fetch_ts | team, player, role_observed enum, span, confidence | first-credible-post ts < line; post-graphic notes dropped | UNTESTED |
| Soccer warmup-derived late team-news | soccer | medium | key attacker/keeper compromised in warmup shifts O/U + ML before official teamsheet | warmups ~45-60 min; expected-XI leaks precede sheet | club/beat pitchside X + ASR, 30s poll; fetch_ts | player, observation enum, likely_status, span, confidence | extracted_at < teamsheet; post-kickoff recaps quarantined | UNTESTED (likely ABSORBED at sheet) |
| Tennis warmup hampered / strapping / withdrawal-risk | tennis | high | hampered/retirement-risk knock pre-match underweighted by the close | warmup/practice minutes-hours pre-first-serve | on-site insider feeds, 30s poll; fetch_ts | player, observation enum, body_part, span, confidence | extracted_at < first serve; in-match trainer notes quarantined | UNTESTED (thin sourcing -> false-positive risk) |
| Officiating assignment CONFLICT / late-swap detector | all | high | actual official != expected one the line still encodes => unpriced time-boxed gap; conditional trigger | minutes-couple hours; cleanest timely case | multi-source assignment scrapes; first-conflict ts | role, name_per_source_A/B, conflict bool, span | conflict ts < move; rare-event subset; >=2 corpora | UNTESTED (sample-starved -> UNGRADEABLE; multiplies P0/P1) |
| Run/momentum as REGIME-SHIFT classifier (live) | nba | low | run WITH a named cause (zone switch, star benched) > random variance; book underweights | run continuous; cause-tag real-time | CDN PBP run + announcer cause text | leading team, run pts, defensive_change bool, span | run from PBP strictly-before-t; cause-tag ts < live snapshot | UNTESTED (fights momentum_worse_than_null; likely REJECT) |
| Revenge / return-to-former-team usage spike | all | low | small historical prop lift; affects props more than line; known to sharps | matchup known at schedule release; day-of health confirm | transactions (linkage) + human-interest quotes; first_seen_utc | player, former_team (deterministic), revenge_framing bool, span | linkage as-of game date; quote < prop snapshot; multiple-comparisons risk | UNTESTED (REJECT as standalone mean-shift) |
| Letdown / look-ahead schedule spot | all | low | underperformance in trap spots; schedule half fully public/priced | schedule weeks ahead; quote 1 day pre-game | schedule graph + trap-game quotes; first_seen_utc | look-ahead/complacency admission span (position deterministic) | schedule as-of; quote < line; explicit-quote subset too small | UNTESTED (REJECT for the line) |
| Contract-year / expiring-deal effort | all | low | altered usage but SIGN VARIES by player type; flag fully public | contract status season-long (not timely) | contract DB (deterministic) + walk-year quotes; first_seen_utc | contract status (DB), motivation-framing bool, span | as-of season; pre-registered buckets; both corpora or REJECT | UNTESTED (REJECT; sign-instability = single-fold artifact) |
| MLB park temp/humidity/air-density (carry) | mlb | medium | nonlinear density effect at extremes books' coarse temp model misses | T-3h to T-1h; tail games only | weather API + roof state; issue_ts | roof/condition facts + heat span (density deterministic) | issue_ts < first pitch; archived forecast; roof-open only | UNTESTED (partial REJECT vs mature books) |
| Trip illness / local disruption (team-level) | all | high | team-wide illness/sleep disruption the calendar cannot contain; conditions b2b knob | morning-of to hours pre-tip | beat reports; report ts | team illness/disruption bool, affected players, span | report ts < line_move_ts | UNTESTED |
| Schedule-loss letdown narrative framing | nba | medium | extracted narrative flags which generic letdown spots are live; narrative proxy not a fact | day-of before public money firms | beat/national narrative text; article ts | letdown/lookahead framing presence, span (no sentiment score) | article ts < line_move_ts | UNTESTED (softest; expect REJECT) |
| Altitude acclimatization window (NBA) | nba | medium | acclim days modulate SIZE of the (binary-priced) Denver/Utah effect | 1-2 days pre-tip when itinerary public | itinerary + early-arrival beat reports; report ts | days at altitude, early-vs-day-of, prior leg elevated (dates) | report ts < line_move_ts | UNTESTED (venue flag partly priced) |
| Cross-market sentiment-dislocation (morale/role conflict) | nba | high | acute conflict (trade request, benching friction) shifts effort/rotation; no structured feed | event post ts; effect persists days | player/team social + presser; post ts | event_type enum, polarity, self/teammate, span, confidence | post ts < line move; "we knew he was unhappy" reconstruction quarantined | UNTESTED (soft sentiment historically washes out) |
| RLM x LLM-quantified narrative intensity (confirmation filter) | all | medium | RLM cleaner when public-narrative volume HIGH; interaction beats RLM alone | splits/narrative crystallize hours pre-tip | public splits + national-narrative coverage; capture/post ts | narrative themes, outlet count, public side, headlines (counts only) | snapshot ts < move; narrative published-after rows rejected | UNTESTED (RLM alone likely priced; interaction is the test) |
| Sharp-consensus divergence oracle (Pinnacle/Circa vs soft) | all | low | sharp devig is the better predictor; essentially the efficiency definition -> a BENCHMARK | divergence intraday; collapses by close | Pinnacle/Circa vs soft books; capture ts | divergence cause annotation only (number from real prices) | matched-timestamp snapshots; SHIN-devig sharp close is the benchmark | UNTESTED (the BENCHMARK to beat, not a found edge) |
| Promo / odds-boost free-EV scanner | all | low | STRUCTURAL free-EV, NOT an information edge; fails the PREDICTIVE test by construction | promo-window-bound | book promo pages / trackers; posted/expiry ts | book, original/boosted odds, token, eligibility, posted/expiry ts | N/A for Brier test; quarantined to a structural map; never enters the ledger | PRIOR-REJECT (non-predictive by construction) |

---

## Notes on prior art, reuse, and expected outcomes

- The machine already exists and is per-file tested: `scripts/platformkit/edge_engine/`
  (`source.py` -> `extract.py` -> `schema.py`/`schema_source.py` -> `score.py` -> `combine.py`),
  plus the first concrete adapter `schedule_fatigue_map.py`. This map enumerates the candidates
  those modules will carry; it does not duplicate them.
- Reused READ-ONLY (never reimplemented): `freshness/` (the X1 LLM-extract-FACTS-only + vintage
  guard, the seed), `eval_gate/` (the JUDGE -- SHIN-devig + walk-forward + clustered DM + the
  in-game blend), `ledger/` (forward CLV). `docs/research/edge-taxonomy.md` (164 edges) is the
  loose prior enumeration this sharpens with the 3-test scoring + leak-free capture spec.
- Expected HONEST outcomes baked in (a REJECT is a SUCCESS): pregame team-strength markets are
  efficient (most structured-flag halves ABSORB); the residual worth gating is always the
  qualitative TEXT/TIMING captured before it manifests. Promo/boost is explicitly NON-predictive.
  Insider latency, warmup shot-making, revenge, letdown, contract-year, momentum-regime are
  flagged likely-REJECT. The conflict-detector is likely UNGRADEABLE until enough events accrue.
- The single binding deliverable: the MACHINE + this MAP. No edge is claimed until a candidate
  passes the gate on >=2 real corpora with forward CLV.
