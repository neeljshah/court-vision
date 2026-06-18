# REVAMP -- Locked Decisions + Phased Plan (living doc)
_Started 2026-06-17 planning session. Refines REVAMP_MASTER_PLAN.md with the user's
explicit decisions. This is the doc we iterate until the plan is LOCKED. No code until
the user says "plan is locked." ASCII only._

## North-star reframe (this session's biggest steer)
DROP the "we just match the close" defeatist default. The north star is the BEST
prediction, and the gaps the user has found are REAL: soft/lazy DFS + book props,
live in-game lag, stale lines, prediction-market vs book divergence, correlated SGPs.
The plan's job is to EXPLOIT those gaps using every data detail we have (deep per-sport
data, atlas/intelligence features that are built-but-not-read, in-game conditioning).

CLV is kept NOT as a brake but as the scoreboard that tells us WHICH gaps actually pay,
so we double down on winners. Reconciliation, binding: hunt aggressively, surface every
candidate edge, LABEL each by evidence tier (model-view -> calibration-proven ->
CLV-proven), let the paper loop sort real from fake fast. Ambition + rigor, not
defeatism, and never a fabricated $ number. Paper-only until proven positive CLV.

## Locked decisions (2026-06-17)
1. ODDS DATA: build our OWN deep scraper -- NOT a paid Odds API dependency.
2. SCRAPER SCOPE: go deep -- DraftKings/FanDuel event feeds + PrizePicks/Underdog
   projections + Kalshi/Polymarket. Full prop ladders, alt lines, 1000s of bets.
   (Fragile + ToS-gray; acceptable for personal paper use -- user's call.)
3. SCRAPER TECH: hybrid -- hidden-JSON HTTP adapters first, Playwright browser fallback
   only for sources that block direct calls. Plug-in adapters so one book breaking
   never darkens the whole board.
4. FIRST VERTICAL / FIRST EDGE: player props vs DFS/soft lines. PIVOTED 2026-06-17 to
   WORLD CUP soccer (was NBA) -- NBA is offseason (~0 live props until Oct); World Cup is
   the highest live prop volume right now (3,927 PrizePicks props). Our per-player
   projected DISTRIBUTIONS priced against PrizePicks/Underdog/soft-book prop ladders,
   engineered with every detail. NBA (with its MC-sim depth) becomes the 2nd vertical when
   its season returns.
5. PROP DISTRIBUTION METHOD: per-sport. WORLD CUP (1st vertical) = per-player per-90 RATE
   x expected-minutes -> Poisson/Negative-Binomial -> P(over line); SGP correlation from
   shared match state (team goals <-> player involvement). NBA (later) = Monte-Carlo
   possession sim (coherent joint distribution, native SGP). FIX the known "sigma too
   tight" / under-dispersion problem in EITHER engine (a too-tight distribution fabricates
   fake edges -> use NB over Poisson where overdispersed, conformal-calibrate the width).
6. HOSTING: local now, design portable (lift to a VPS later without rework).
7. SNAPSHOT STORE: flat JSON under data/frontend/snapshots/<sport>.json (matches the
   existing gitignored data/frontend/ pattern; portable; no new infra). [default,
   unobjected]
8. FRONTEND REAL-TIME: fast-poll off the snapshot first; SSE/WebSocket later. [default]
9. SEQUENCING: PARALLEL edge track -- a minimal Phase-0 snapshot stub now, then build
   scrapers (Phase 1) + the MC-sim prop engine (Phase 2) in parallel against it, so NBA
   prop edges vs PrizePicks/Underdog surface sooner. Backbone hardens alongside.
10. EDGE SURFACING: show ALL candidate edges immediately, each LABELED by evidence tier
   (model-view / calibration-proven / BSS>0 vs closing prop line / CLV-proven). The
   label sets trust; the paper loop accrues the proof over time. Not defeatist; honest.

## Track B feasibility probe + World Cup pivot (live, 2026-06-17)
Read-only probe of the deep-scrape sources (one request each):
- Underdog over_under_lines: HTTP 200 JSON, ~13MB, keyless, all sports w/ player_id +
  match_id + lines. WIDE OPEN -> primary DFS source. JSON adapter, no fallback.
- PrizePicks: HTTP 200 JSON, keyless, 101 leagues via /leagues. JSON adapter.
- FanDuel: HTTP 200 JSON keyless via static _ak app key (multi-step content->event).
- DraftKings: 403 Akamai "Access Denied" on direct GET -> needs the PLAYWRIGHT fallback
  (validates the hybrid decision; DK is the one source that needs a browser).
SEASONALITY (the pivot driver): mid-June live PrizePicks volume is World Cup 3,927 / MLB
2,515 / WNBA 2,259 / Tennis 940 / NBA ~0. NBA has the deep models but no live props now.
WORLD CUP prop stat-types (model targets, by volume): Shots 711, Fouls Drawn 650, Fouls
577, Shots-on-Target 344, Cards 339, Tackles 297, Goal+Assist 289, Assists 216, Offsides
173, Passes 76, Goalie Saves 74, ... Goals only 26 (rare binary). => COUNT-STAT modeling
(per-90 rate x minutes -> Poisson/NB), the lazy-priced soft pocket.
SOCCER PLAYER DATA -- RESOLVED (probed live 2026-06-17): ESPN fifa.world/summary already
returns PER-PLAYER stats in the rosters[].roster[].stats block (existing ingest_espn_box.py
parses only TEAM level -> just extend it). Covered keyless (~85% of WC prop volume):
totalShots, shotsOnTarget, foulsCommitted(Fouls), foulsSuffered(Fouls Drawn), yellow/red
Cards, goalAssists(Assists/Goal+Assist), offsides, totalGoals, saves. Minutes derivable
from starter/subbedIn/subbedOut + substitution keyEvents. NOT in ESPN per-player: Tackles
(297), Passes(76), Dribbles, Clearances, Crosses (~15%) -> defer to a richer hidden-JSON
source (Sofascore/FotMob, same scrape pattern). World Cup is LIVE now (matches every day
Jun 11-16 completed). soccer_intl/results.parquet has 9,868 WC matches incl. 2026 for
team ratings; ESPN rosters add the player layer.

## Reuse vs build (grounded in a code map, not guesses)
REUSE (built + sound, don't rebuild):
- Paper-loop + proving spine: auto_loop.py, paper_autobet.py (Kelly), clv_ledger.py,
  grade_paper.py, self_improve.py (eval-gate ratchet), eval_gate/ (Brier/ECE/BSS/DM,
  leak-free walk-forward).
- Odds math core: odds_shop.py (best_line/devig/detect_arb/ev) + odds_provider/
  (ESPN + Kalshi + Polymarket ALREADY keyless-wired -- 2 of 3 PM sources done).
- Props base (safe area): domains/basketball_nba/player_props.py -- leak-free
  price_prop(player, stat, line, date), Gaussian mean/sigma + L5/L10/L20 hit-rates,
  derived markets (PRA/PR/PA/RA, double-double).
- Live in-game: live_board.py + predict_live (works on real games).

NET-NEW (the edge build; all in safe areas: scripts/platformkit/, domains/, docs/):
- A) Deep odds scrapers (DK/FD/PrizePicks/Underdog) as plug-in adapters.
- B) MC-sim prop distribution + full ladder + SGP pricer in domains/ (wrap the
     possession sim; fix sigma-too-tight). NOTE: possession sim lives in human-gated
     src/sim/ -- we CALL it read-only from a domains wrapper (calling != editing; OK).
- C) Snapshot service (compute once/cycle -> snapshot JSON; serve + paper loop read it).
- D) Props-specific eval gate (extend eval_gate/scoring.py: P(over) calibration + BSS
     vs the devigged CLOSING PROP line -- current gate only scores team win-prob).

## Phased build order (props-first, edge-hunting)

### Phase 0 -- Fast backbone (the keystone; foundation FIRST)
- Snapshot service: per sport, compute predictions + bet board + live + ranked bets
  ONCE per cycle -> data/frontend/snapshots/<sport>.json.
- serve.py reads the snapshot (instant); a refresh daemon owns cadence (adaptive:
  ratings daily, lines minutes, live seconds).
- Warm predictor cache -- kill the per-request predictor rebuild.
- Cleanup pass: archive dead/duplicate modules + _archive/worktrees; obey 300 LOC.
- DONE-WHEN: :8098 serves the snapshot instantly; the paper loop reads the SAME
  snapshot; nothing in the HTTP path blocks on compute/network.

### Phase 1 -- Deep odds scraping (breadth + the soft prop-line source)
- Adapter framework (hidden-JSON first, Playwright fallback) beside the working
  ESPN/Kalshi/Polymarket providers.
- DK + FD event feeds (game markets + player props + alt ladders).
- PrizePicks + Underdog projections (the soft DFS lines = the props edge target).
- Normalization: extend aggregate.py resolver to team + market + PLAYER matching across
  books AND DFS apps (load-bearing correctness; a false match = a fake edge -> bias to
  false-negative, never wrong price).
- Robustness: per-source health, degrade to unavailable + as_of, never fabricate.
- DONE-WHEN: the snapshot carries 1000s of real bets incl. prop ladders + DFS lines,
  normalized + cross-matched; any source down degrades honestly.

### Phase 2 -- Prop distribution + ladder + the props edge engine (NBA)
- MC-sim distribution pricer in domains/ wrapping the possession sim -> per-player
  joint distribution; full ladder (every alt line) + derived (PRA) + SGP correlations
  priced from the ONE joint sim.
- FIX sigma-too-tight: calibrate sim output width vs realized residuals (conformal).
- "Use every detail": wire the dead funnel -- atlas/intelligence features that are
  built-but-NOT-read at predict time, same-day freshness/availability, matchup -> feed
  the sim. This is where prediction quality (and the edge) actually comes from.
- Props eval gate (D above): score P(over) calibration + BSS vs the devigged closing
  PROP line, leak-free walk-forward.
- Edge surfacing: our distribution vs PrizePicks/Underdog/DK prop lines -> ranked
  candidate prop edges, each LABELED by evidence tier.
- DONE-WHEN: NBA player props priced as full ladders; edges ranked vs DFS/soft lines;
  the props gate scores calibration vs closing prop lines (not just team win-prob).

### Phase 3 -- EV ranking + advanced frontend
- Kelly-growth, correlation-aware ranker over the 1000s of bets (don't double-count
  SGP legs; limit/variance/payout aware).
- React UI served from the snapshot: live board (all sports), +EV/edge feed, arb feed,
  click-game -> full report incl. the priced prop LADDER, bet tracker/CLV, freshness
  dots. Honesty UI rails (evidence-tier labels) throughout. Fast-poll off snapshot.
- DONE-WHEN: UI shows ranked edges incl. props, fast; click a player -> full priced
  ladder; CLV tracker visible; nothing blocks.

### Phase 4 -- Paper auto-bet at scale + PROVE the props edge
- auto_loop drives snapshot -> rank -> paper-bet the prop edges -> grade -> CLV ->
  eval-gate ratchet (only-improve-or-hold from real settled outcomes).
- Accrue per-MARKET CLV (prove the PROP edge specifically, not just team markets).
- Real money HARD-GATED on proven positive prop CLV (place_order stubs raise;
  ENABLED=False; kill-switch).
- DONE-WHEN: prop edges accrue a CLV track record; the ratchet only-improves; we get the
  honest measured verdict on whether the props edge is real.

## Risks / unknowns (track + revisit)
- Scraper fragility / anti-bot on DK/FD/DFS -- biggest EXTERNAL risk. Mitigation: hybrid
  + per-source health + honest degradation; adapters isolated so one break != board dark.
- MC-sim per-cycle COST: GROUNDED at ~3.4s/game (10k sims, GPU fast_sim) / ~13.5s (1k CPU).
  A full NBA slate amortizes fine in the snapshot. Mitigation: GPU path, cache the sample
  arrays per game, recompute only on roster/availability change.
- LEAK-FREE backtest wrinkle: the sim reads FULL-SEASON rate files, so a historical as-of-
  date prop backtest needs date-windowed rate rebuilds (human-gated team_system builders).
  Forward paper-trading is leak-free by construction (only past games exist at predict
  time) -> make FORWARD CLV accrual the primary proof; treat historical backtest as a
  later, optional, human-gated step.
- DESIGN REFINEMENT (anchor-hybrid): the sim's `anchor` scales players to a per-game mean.
  Option to anchor to the feature-rich projection (player_props.py reads ~190 features)
  for point accuracy while the sim supplies SHAPE + correlations -> "every detail" mean +
  coherent joint distribution. Evaluate in C2/C4; do not over-engineer before measuring.
- Cross-book / DFS PLAYER-name matching correctness -- load-bearing; false match = fake
  edge. Mitigation: explicit alias tables, bias to false-negative, log UNRESOLVED.
- Human-gated src/: the MC sim + quantile + correlation code is in src/. We CALL it
  read-only (allowed); if we ever need to EDIT it, write a PROPOSED diff for the human.
- Cold-start: props CLV needs a VOLUME of settled props to prove (like the ~60-game
  team threshold). The verdict accrues over time; small-N ROI is noise.

## MILESTONE 1 -- "First WORLD CUP prop edge, surfaced + paper-bet" (the parallel track)
Goal: the snapshot shows ranked World Cup player-prop edges (Shots / SOT / Fouls / Cards /
Tackles / Assists / Goal+Assist) vs PrizePicks/Underdog/FanDuel, each tier-labeled, and the
paper loop bets them and accrues per-market CLV. Three tracks build in parallel against a
thin snapshot, then converge. Every file <=300 LOC, per-file test, lives under
scripts/platformkit/ or domains/, degrades to unavailable, no $ claim.

### Track A -- minimal snapshot backbone (thin; full Phase-0 hardening later)
- A1 snapshot_writer.py: build_snapshot(sport) calls existing slate/bet_board/live ONCE,
  writes data/frontend/snapshots/<sport>.json + freshness envelope.
  DONE-WHEN: running it writes a valid nba.json; per-file test green.
- A2 serve.py: read the snapshot file if present (instant), else fall back to the current
  per-request compute. DONE-WHEN: /api/slate serves the snapshot file when present.
- A3 refresh_daemon.py (minimal): loop, call build_snapshot per sport on a cadence,
  last-good-on-error. DONE-WHEN: one tick writes snapshots; error tick preserves last-good.
  (Warm predictor cache + dead-code cleanup deferred to Phase-0 hardening.)

### Track B -- deep scrapers (DFS first = the soft prop-line target)
- B1 prop_provider base: interface fetch_player_props(sport)->normalized rows
  {player, team, stat, line, over_odds, under_odds, source, as_of}; health/unavailable
  contract. DONE-WHEN: interface + stub adapter + per-file test.
PROBED keyless-OK: Underdog (wide open), PrizePicks (101 leagues), FanDuel (static _ak).
DK = 403 Akamai -> Playwright. Build DFS first (the soft prop target).
- B2 Underdog adapter (hidden JSON over_under_lines; keyless). PRIMARY DFS source.
  DONE-WHEN: normalized World Cup rows (canned in test; live verified).
- B3 PrizePicks adapter (hidden JSON /projections?league_id=241 for World Cup). DONE-WHEN:
  same; handle the /leagues lookup so league ids aren't hard-coded.
- B4 FanDuel adapter (keyless via static _ak; content-page -> event odds, two-way prices
  for devig). DONE-WHEN: normalized prop rows w/ over/under odds.
- B5 DraftKings adapter via PLAYWRIGHT fallback (direct GET is 403). DONE-WHEN: normalized
  prop rows w/ odds + alt rungs, or documented deferred if browser path too costly for M1.
- B6 resolve_player(sport, raw_name)->canonical id: alias table, bias to FALSE-NEGATIVE,
  log UNRESOLVED (false match = fake edge). Soccer intl names are accent-heavy -> deaccent
  + alias. DONE-WHEN: maps UD/PP/FD names to our player table on a known-alias test set.
- B7 Playwright fallback harness (used by B5). DONE-WHEN: DK World Cup props proven via
  browser path, or documented not-needed for M1.

### Track C -- World Cup soccer player-prop engine (Poisson/NB rate model)
GROUNDED: targets are COUNT stats (per PrizePicks WC: Shots 711, Fouls Drawn 650, Fouls
577, Shots-on-Target 344, Cards 339, Tackles 297, Goal+Assist 289, Assists 216, Offsides,
Passes, Goalie Saves; Goals rare=26). Model = per-player per-90 rate x expected minutes
-> Poisson (or Negative-Binomial where overdispersed) -> P(over line.5). All in domains/
soccer_intl/ (or domains/soccer/ shared); team-level soccer_intl predictor stays as-is.
- C0 DATA (RESOLVED -- source confirmed): extend domains/soccer/ingest_espn_box.py to parse
  the rosters[].roster[].stats block of fifa.world/summary -> per-player table
  {match, player, team, starter, totalShots, shotsOnTarget, foulsCommitted, foulsSuffered,
  yellow/red, goalAssists, offsides, totalGoals, saves, minutes}. Minutes from
  subbedIn/subbedOut + substitution keyEvents. FIRST targets = ESPN-covered stats (~85% of
  WC prop volume). Tackles/Passes/Dribbles -> later Sofascore/FotMob ingest (deferred).
  DONE-WHEN: a player-match stat table exists for recent WC games w/ the target stats +
  minutes, leak-free (match date stamped).
- C1 player_rates.py: per-player per-90 rate priors per stat (shots/90, fouls/90, ...),
  shrunk to position/role baseline (striker vs mid vs def) when low sample (international
  players have few caps -> shrinkage is load-bearing). DONE-WHEN: rate(player, stat)->per90
  with a sample-size-aware shrink; test on known players.
- C2 minutes_model.py: expected minutes (starter vs sub vs benched) from lineup/rotation
  signal -- the dominant multiplier for every count prop. DONE-WHEN: E[minutes] per
  projected-to-play player; honest "unknown" when lineup not yet posted.
- C3 prop_distribution.py: lambda = per90_rate x E[min]/90 x opponent/match adjustment;
  Poisson/NB -> P(stat>line). FIX under-dispersion: NB where variance>mean, conformal width
  check. DONE-WHEN: P(over) for any (player, stat, line); OOS coverage ~ nominal.
- C4 ladder + SGP: price every alt rung from the same distribution; Goal+Assist and
  goalscorer (1-P(0 goals)) as derived; SGP via shared match-state correlation (team total
  goals <-> player goal involvement; a card <-> fouls). DONE-WHEN: full priced ladder + a
  2-leg SGP price.
- C5 "every detail" levers (the edge): opponent defensive strength (fouls/cards drawn vs
  conceded), home/NEUTRAL (World Cup neutral), set-piece + penalty taker (goalscorer/SOT),
  match importance/red-card state, recent form, referee card tendency (Cards stat!).
  DONE-WHEN: >=1 lever measurably shifts calibration on a holdout; documented.
- C6 eval_gate props extension: P(over) calibration + BSS vs the devigged CLOSING PROP
  line (or vs the DFS implied line where no two-way book price). PRIMARY proof = FORWARD
  accrual (leak-free natively: only past matches exist at predict time). DONE-WHEN: gate
  scores a forward-settled prop set -> Brier/ECE/BSS per stat.

### Convergence -- surface + prove the first edge
- D1 prop_edge.py: join our priced ladder vs scraped DFS/book prop lines -> EV/$1 per
  rung -> rank -> LABEL tier (model-view default; calibration-proven if C6 BSS>0 for that
  stat; CLV-proven if per-market CLV>0). DONE-WHEN: ranked World Cup prop-edge list w/ tiers
  for today's slate.
- D2 fold ranked prop edges into the snapshot + a board view. DONE-WHEN: snapshot carries
  ranked prop edges; visible on the board.
- D3 paper loop bets the prop edges -> per-MARKET CLV (market=prop). NOTE: DFS lines are
  often one-sided (no two-way devig) -> settle CLV vs the realized OUTCOME and vs the line
  move where available; record the line basis honestly. DONE-WHEN: prop bets recorded to
  clv_ledger; grade settles them from match player-stats; per-market prop CLV accrues.

MILESTONE-1 DONE-WHEN (all): open :8098 -> instant snapshot showing ranked WORLD CUP prop
edges vs PrizePicks/Underdog/FanDuel, each tier-labeled, click a player -> full priced
ladder; the paper loop is betting those edges and a per-market prop CLV track record is
accruing. THEN widen: MLB/tennis prop engines, NBA MC-sim vertical (Oct), more markets,
Phase-0 hardening, UI.

## Deferred decisions (set sensible defaults, revisit at the relevant phase)
- Paper-policy aggressiveness (min-EV, how many of the 1000s to bet, sizing caps):
  default conservative via existing AutoBetConfig; tune in Phase 4.
- Frontend SSE vs fast-poll: fast-poll first (Phase 3), SSE if latency demands.
- Hosting target (which VPS): decided post-proof; keep portable now.
</content>
</invoke>

## BUILD LOG -- Milestone 1 executed (2026-06-17)
Plan locked -> built end-to-end via subagents (one file per agent, per-file tests, all green).
~15 new modules under scripts/platformkit/ + domains/soccer/. Key findings + state:

DONE (tested green):
- Snapshot backbone: snapshot_writer.py (compute-once -> data/frontend/snapshots/<sport>.json,
  atomic write), serve.py prefers snapshot (live-compute fallback), refresh_daemon.py.
- Scrapers: prop_base.py (PropLine + canon_stat), prop_underdog.py, prop_prizepicks.py,
  prop_fanduel.py. FINDING: Underdog posts TWO-WAY vig-adjusted decimal_price (devig-able,
  true CLV) -- NOT fixed pick'em as assumed; 1039 live WC rows. PrizePicks = pick'em (3874
  rows, prices None). FanDuel keyless via static _ak but has NOT posted WC props yet (~2wk
  out) -> parser ready, degrades honestly. DraftKings 403 Akamai -> Playwright deferred.
- ESPN per-player ingest: ingest_espn_players.py (rosters block) -> 1241 rows / 24 matches.
- Prop engine: player_rates.py, player_minutes.py, prop_engine.py (Poisson/NB, pure-stdlib,
  leak-free). dispersion.py = NB width calibration from realized data (Shots phi=1.84, Saves
  4.15, Cards->Poisson) -- FIXES the too-tight-Poisson fake-edge problem.
- Edge board: player_resolver.py (98.1% name hit, deaccent), prop_edge.py (EV via odds_shop
  devig, tier=MODEL_VIEW, ev_flag ok/uncalibrated_thin/implausible, honesty-first ranking).
  Folded into snapshot + /api/props.
- Proving loop: prop_settle.py + prop_paper.py (records ONLY reliable+ok edges, grades vs
  realized ESPN stats, per-stat summary). Settlement proven on real data (3W/2L sample).
- THE UNLOCK: ingest_espn_athlete.py pulls CLUB-SEASON per-stat aggregates from ESPN athlete
  overview (statistics.splits, keyless, ids already match). Blended into player_rates as a
  strong prior -> 0 -> 321 RELIABLE edges on a 36-player sample. Backward-compatible.

HONEST STATE: with only ~1 WC match/player, edges are reliable ONLY where a club prior backs
them. Honesty guards intact: MODEL_VIEW tier everywhere, uncalibrated_thin flags thin rows,
implausible (|EV|>0.5) demoted, no $-edge claims, paper-only. CLV-vs-close needs closing-line
capture (not built). Proof = forward calibration + realized ROI until CLV is wired.

REMAINING (M1 polish + next): full ~1200-player club-prior build (running); C6 props
eval-gate (calibration/BSS on settled props); UI prop-board view; Sofascore deeper priors
(tackles/passes) + closing-line capture for true prop CLV; daemon cadence for unattended
record/grade.
