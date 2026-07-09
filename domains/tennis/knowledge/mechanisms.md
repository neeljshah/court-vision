# Tennis Mechanism Ledger

One entry per mechanical belief the system holds about tennis, with a receipt.
Fields, always in this order: **claim | causal story | expected signature in
our data | test spec | status | measured LOCAL magnitude | artifact link**.

Status values: `UNTESTED` (seeded, not yet run against local data),
`CONFIRMED` (survived a leak-free local test, ideally replicated),
`REJECTED` (tested locally and failed, or failed cross-corpus replication),
`PARTIAL` (mixed verdict across corpora/seasons), `NOT_TESTABLE` (the
ingredient this mechanism needs does not exist in our local corpus -- an
honest gap, not a failure).

Two independent local corpora feed this ledger (see `_data.py` for the exact
leak-audit notes): `slam_points.parquet` (2011-2015 Grand Slam POINT-level,
543,772 rows, singles majors only) for within-match/point dynamics, and
`matches.parquet` + `wta_matches.parquet` (2015-2025 ATP+WTA MATCH-level,
joined to `players.parquet` hand/dob and `schedule_density.parquet`
rest_days) for population/match-outcome mechanisms. Local receipts for this
session's 10 fresh validations live in
`domains/tennis/knowledge/validation_ledger.jsonl`. No `$` edge is claimed
anywhere in this file -- every magnitude below is a calibration/mechanism
receipt, not ROI.

---

## Pre-adjudicated (do NOT re-test -- closed classes, cited from real git history)

### 1. Serve-tier x return-tier style pairing -- the one real survivor
- **claim**: pairing a server's serve-strength tier against a returner's
  return-strength tier predicts point/game outcome beyond what raw player
  rank alone predicts.
- **causal story**: two players of the same rank can have very different
  serve/return profiles (a big server vs a grinder); the STYLE matchup, not
  just the rank gap, should move the outcome distribution.
- **expected signature**: outcome spread across serve-tier x return-tier
  cells should NOT collapse to noise once rank-tercile is controlled.
- **test spec**: 20-claim factory over serve-tier x return-tier pairing cells
  (reused `asof_hold`/`asof_return` formulas), rank-tercile control,
  ATP+WTA combined.
- **status**: CONFIRMED (survives rank-tercile control)
- **measured LOCAL magnitude**: outcome spread 0.278 -> 0.217 after
  rank-tercile control (does not collapse to near-zero, unlike the soccer
  analog in the same commit which DID collapse 0.341 -> 0.064); n=42,400
  perspective-rows ATP+WTA; 20/20 claims VERIFIED via the claims factory.
- **artifact link**: commit `07c771d0` "feat(soccer+tennis): style/serve-return
  interaction layers -- one real survivor"; `domains/tennis/serve_return_interaction.py`,
  `domains/tennis/serve_return_profiles.py`.

### 2. Individual-clutch 8-signal composite -- CLOSED, evidence-closed NULL
- **claim**: a composed player-level "clutch" z-score (break/game/set-point +
  tiebreak + deuce serve/return deltas + pressure_serve + set3+ stamina)
  predicts high-leverage point outcomes beyond as-of serve/return strength
  and surface.
- **causal story**: some players are individually better under pressure than
  their baseline serve/return numbers alone predict -- a "clutch gene."
- **expected signature**: server_composite - returner_composite term
  significant on high-leverage point outcome, net of baseline strength.
- **test spec**: as-of z-composite per player-year (>=200 prior high-leverage
  points floor), cluster-robust logit by match, K=2 Bonferroni alpha=0.025,
  reusing `prereg_point_mechanisms.py`'s walk-forward baseline.
- **status**: REJECTED (NULL, evidence-closed after 2 attempts)
- **measured LOCAL magnitude**: 4,048/5,924 player-years excluded below the
  >=200-point floor; the composite did not survive the Bonferroni-corrected
  test against the strength+surface baseline (NULL both passes).
- **artifact link**: commit `7fadfc21` "feat(tennis): composed pressure
  profile -- 8-signal z-composite vs high-leverage point outcomes, honest
  NULL". CLOSED CLASS -- do not re-attempt this exact 8-signal composite;
  distinct from #3 below (population-level pressure effects, which ARE real).

### 3. Pressure-point population dip (break/game/set/tiebreak/deuce) -- CONFIRMED
- **claim**: server performance (points-won delta + first-serve-in delta vs
  the server's OWN baseline) measurably dips at 5 distinct pressure
  situations: break point, game point, set point, tiebreak, deuce-battle --
  a POPULATION-level effect, not the individual-clutch composite in #2.
- **causal story**: elevated stakes at these score-states measurably tax
  execution (serve percentage, point-win rate) relative to the same
  player's non-pressure baseline, from both the server's and returner's
  perspective.
- **expected signature**: negative points-won/first-serve-in delta vs own
  baseline at each of the 5 situations, both perspectives.
- **test spec**: `pressure_situations.py` pure score-state detectors +
  `pressure_point_claims.py` claim-emission grid, per-situation min-n floors
  (200/200/50/50/30), charting PBP corpus, ranked descriptively.
- **status**: CONFIRMED (15/15 descriptive ranking claims VERIFIED)
- **measured LOCAL magnitude**: 15/15 claims (5 situations x
  server+returner perspective, minus overlaps) VERIFIED by
  `claims_validator.py`.
- **artifact link**: commit `f8d00bc8` "feat(tennis): pressure-point claim
  family -- 5 situations x server/returner over charting PBP";
  `domains/tennis/pressure_situations.py`, `domains/tennis/pressure_point_claims.py`.
  Do NOT re-test the break-point-specific conversion dip in isolation --
  it is the best-replicated cell of this already-CONFIRMED family.

### 4. Point-level score-state conditioning -- CLOSED, points ~iid given server
- **claim**: conditioning a point-win model on (server, score_bucket,
  set_bucket) beats a naive per-server constant-rate baseline on held-out
  point-level log-loss.
- **causal story**: pressure/fatigue/momentum within a game should make the
  server's win probability state-dependent, not a flat per-server constant.
- **expected signature**: lower held-out log-loss for the state-conditioned
  model vs the naive constant-rate baseline.
- **test spec**: fit 2011-2013, test 2014 (walk-forward), point-level
  log-loss, `PointModel` vs `naive_baseline`.
- **status**: REJECTED (NULL -- naive constant-rate baseline actually edges
  the state-conditioned model, consistent with the classic tennis literature
  that points are close to i.i.d. given server)
- **measured LOCAL magnitude**: held-out log-loss naive 0.6652 vs
  state-conditioned model 0.6693 (naive wins). Match-level MC chain still
  useful: match-winner Brier model 0.2284 beats naive 0.2320.
- **artifact link**: commit `989ef60c` "feat(tennis): point-level engine v1 --
  empirical score-state model + MC point->game->set->match chain";
  `domains/tennis/point_engine/validate.py`, `corpus.py`. CLOSED CLASS -- do
  not re-test raw point-to-point score-state dependence; a genuinely new
  conditioning variable (not just score-state) would be a different claim.

---

## Validated THIS SESSION (10 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

### 5. Serve advantage erodes on clay
- **claim**: the server's per-point win rate is lower on clay than on
  hard/grass combined.
- **causal story**: clay's slower bounce and higher ball-height give the
  returner more time to react, eroding the serve's structural advantage that
  faster surfaces preserve.
- **expected signature**: lower server win-rate on Clay vs Hard+Grass.
- **test spec**: Welch t-test, per-point server-won indicator by surface,
  slam_points 2011-2015 (all 4 majors).
- **status**: CONFIRMED
- **measured LOCAL magnitude**: server win-rate 0.5936 (Clay, n=142,143) vs
  0.6139 (Hard+Grass, n=399,461); effect -0.0202, p=1.13e-40, n=541,604.
- **artifact link**: `domains/tennis/knowledge/validate_point_dynamics.py::serve_advantage_by_surface`.
- **wiring**: in-game conditioning-feature candidate -- a surface-conditioned
  serve-hold prior, distinct from and complementary to the CONFIRMED
  serve-tier x return-tier pairing (#1).

### 6. Rally length: clay vs grass -- LOCAL NULL, folklore-defying
- **claim**: clay produces measurably longer rallies than grass (slower
  surface -> more shots per point).
- **causal story**: clay's high bounce and slow pace should force more
  defensive exchanges before a point ends, vs grass's low, fast, serve-and-volley-friendly bounce.
- **expected signature**: higher mean rally-shot-count on Clay vs Grass.
- **test spec**: Welch t-test, `rally` (shot count) by surface, slam_points
  2011-2015, points with a recorded rally count only.
- **status**: REJECTED (NULL_LOCAL) -- the single most interesting reject
  this session; textbook surface-speed intuition does not show up in this
  corpus at all.
- **measured LOCAL magnitude**: mean rally 3.724 shots (Clay, n=34,339) vs
  3.749 shots (Grass, n=21,368); effect -0.025, p=0.426, n=55,707. Direction
  is even backwards (Clay marginally SHORTER, not longer) though far from
  significant.
- **artifact link**: `domains/tennis/knowledge/validate_point_dynamics.py::rally_length_clay_vs_grass`.

### 7. Serve speed decays within a match
- **claim**: mean serve speed in the second half of a match's points is
  lower than in the first half -- a within-match fatigue signature.
- **causal story**: cumulative physical fatigue over a multi-hour match
  should measurably sap serve pace, independent of any score-state effect.
- **expected signature**: negative (2nd-half mean speed - 1st-half mean
  speed) per match, aggregated across matches.
- **test spec**: paired within-match comparison (ordinal point-index split at
  the match's median), one-sample t-test of the per-match diff against 0,
  matches with >=10 points/half, slam_points 2011-2015.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: mean per-match diff -0.904 km/h, p=3.9e-36,
  n=2,804 matches.
- **artifact link**: `domains/tennis/knowledge/validate_point_dynamics.py::serve_speed_decay_within_match`.
- **wiring**: in-game conditioning-feature candidate -- an as-of within-match
  serve-speed-trend feature for a live hold-probability re-pricer, using the
  `speed_kmh` column directly (a genuinely new ingredient vs the CLOSED
  point-level state-conditioning class in #4).

### 8. Double-fault rate falls (not rises) by set 3+ -- LOCAL NULL of the fatigue-DF story
- **claim**: double-fault rate rises deeper into a match (set 3+ vs set 1) as
  fatigue/pressure compounds -- a fresh angle distinct from the
  already-CONFIRMED break-point-specific DF dip (#3).
- **causal story**: cumulative fatigue should degrade the mechanically
  demanding second-serve motion, raising DF rate in later sets.
- **expected signature**: higher combined DF rate at set>=3 vs set==1.
- **test spec**: Welch t-test, combined-player DF-occurred indicator by set
  number, slam_points 2011-2015.
- **status**: REJECTED (CONFIRMED_LOCAL by the p-value/magnitude gate, but in
  the OPPOSITE direction from the causal story -- DF rate is LOWER, not
  higher, deeper into the match)
- **measured LOCAL magnitude**: DF rate 0.0353 (set>=3, n=176,374) vs 0.0422
  (set==1, n=185,868); effect -0.0069, p=4.66e-27, n=543,158. Read as: elite
  Slam players tighten up their second serve as stakes rise late in a match,
  the opposite of a pure-fatigue story.
- **artifact link**: `domains/tennis/knowledge/validate_point_dynamics.py::double_fault_rate_by_set_number`.

### 9. Deciding-set hold-rate shift -- statistically real, below-threshold magnitude
- **claim**: server win-rate (hold proxy) shifts in a match's final/deciding
  set vs its first set.
- **causal story**: fatigue/pressure in a decisive set could either erode
  serve dominance (fatigue) or sharpen focus (clutch) -- direction not
  assumed.
- **expected signature**: a hold-rate difference, final set vs set 1.
- **test spec**: Welch t-test, server-won indicator, final set (set_no ==
  match max, excluding 1-set matches) vs set 1, slam_points 2011-2015.
- **status**: REJECTED (NULL_LOCAL by the pre-declared minimum-effect gate --
  p is tiny but the magnitude is below the 0.01 floor set for this test, so
  it is reported honestly as a NULL despite the low p-value)
- **measured LOCAL magnitude**: server win-rate 0.5957 (final set, n=177,576)
  vs 0.6037 (set 1, n=184,314); effect -0.0080, p=8.26e-07, n=361,890.
- **artifact link**: `domains/tennis/knowledge/validate_point_dynamics.py::deciding_set_hold_rate_shift`.

### 10. Ranking-gap shape is closer to linear than quadratic -- LOCAL NULL
- **claim**: win probability vs ranking-gap is NOT linear -- it should flatten
  at the extremes (an already-decisive gap adds little more certainty).
- **causal story**: a 1-vs-500 match is already essentially a lock; widening
  the gap to 1-vs-1000 cannot push P(win) much closer to 1, so the
  rank-gap-to-win-prob curve should saturate (a classic logistic/sigmoid
  shape), not stay linear.
- **expected signature**: a quadratic term measurably improves the fit over a
  linear one across ranking-gap deciles.
- **test spec**: nested F-test (linear vs quadratic OLS, `numpy.polyfit`)
  across 12 ranking-gap quantile bins, ATP+WTA matches 2015-2025.
- **status**: REJECTED (NULL_LOCAL) -- decile-level binning may be too coarse
  to detect the saturation effect; a finer-grained logistic-regression design
  would be a natural follow-up, not attempted here.
- **measured LOCAL magnitude**: RSS improvement (linear->quadratic) 0.0022,
  p=0.657, n=40,802 matches (12 bins).
- **artifact link**: `domains/tennis/knowledge/validate_match_outcomes.py::ranking_gap_nonlinearity`.

### 11. Right-handed players outperform left-handed opponents (rank-controlled) -- CONFIRMED, folklore-reversing
- **claim**: in rank-close matchups, does facing a left-handed opponent
  change a right-handed player's win rate.
- **causal story**: conventional tennis folklore says lefties hold a
  structural advantage (unfamiliar spin/angles for righty-dominant tours) --
  this tests that folklore directly, without assuming the direction.
- **expected signature**: right-handed player win-rate vs left-handed
  opponent departs from 0.5.
- **test spec**: one-sample t-test of right-handed-player-win indicator
  against 0.5, restricted to mixed-handedness matches with |rank_diff|<=50,
  ATP+WTA 2015-2025, hand from `players.parquet`.
- **status**: CONFIRMED -- but in the OPPOSITE direction from the popular
  "lefty advantage" folklore: right-handers win MORE often against lefties
  in this rank-controlled sample, not less.
- **measured LOCAL magnitude**: right-handed-player win-rate 0.5350 vs
  left-handed opponents, effect +0.0350, p=5.85e-06, n=4,189 (|rank_diff|<=50).
- **artifact link**: `domains/tennis/knowledge/validate_match_outcomes.py::lefty_advantage_on_return`.

### 12. Age-24-29 "prime band" advantage -- LOCAL NULL
- **claim**: players in a 24-29 "physical prime" age band win at a higher
  rate than players outside that band.
- **causal story**: peak combination of physical conditioning and match
  experience should crest in the mid-to-late 20s.
- **expected signature**: higher population win-rate for the 24-29 band vs
  everyone else.
- **test spec**: Welch t-test, per-player-match win indicator (long format,
  2 rows/match) by age band, age from `players.parquet` dob, ATP+WTA
  2015-2025. Population-level comparison, not opponent-matched -- a
  declared simplification (selection effects by rank are not controlled).
- **status**: REJECTED (NULL_LOCAL) -- no detectable prime-band win-rate
  edge in this uncontrolled population cut.
- **measured LOCAL magnitude**: win-rate 0.5002 (age 24-29, n=25,098) vs
  0.5021 (other ages, n=44,595); effect -0.0018, p=0.642, n=69,693
  player-match rows.
- **artifact link**: `domains/tennis/knowledge/validate_match_outcomes.py::age_prime_band_advantage`.

### 13. Recent match load correlates with in-match retirement
- **claim**: combined recent match load (avg `matches_last_7d` across both
  players) is higher in matches that end in a retirement.
- **causal story**: a congested recent schedule leaves less recovery time,
  raising injury/exhaustion risk that manifests as a mid-match retirement.
- **expected signature**: higher combined recent-load in retirement=True
  matches vs retirement=False.
- **test spec**: Welch t-test, combined `matches_last_7d` (joined via
  event_id+player_id from `schedule_density.parquet`) by retirement flag,
  ATP+WTA 2015-2025.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: combined matches_last_7d 0.951 (retirement,
  n=1,044) vs 0.862 (no retirement, n=29,572); effect +0.0883, p=0.0062,
  n=30,616.
- **artifact link**: `domains/tennis/knowledge/validate_match_outcomes.py::fatigue_load_correlates_with_retirement`.
- **wiring**: in-game conditioning-feature candidate -- a pre-match
  recent-load differential as a live retirement-risk / injury-time prior,
  distinct from the within-match speed-decay signal (#7).

### 14. First-set winner wins the match (classic population claim, replicated locally)
- **claim**: winning the first set predicts winning the match at a rate far
  above a coin flip.
- **causal story**: the first set is real signal about who is playing better
  that day, plus a structural lead (must now win 2 of the remaining sets
  instead of 2 of 3 outright).
- **expected signature**: P(win match | won set 1) >> 0.5.
- **test spec**: one-sample t-test against 0.5; note the `score` string in
  this corpus is written from the MATCH WINNER's perspective in every set
  token (verified empirically: front-listed side wins the aggregate set
  count in 98.9% of matches, vs only 51.2% under a naive p1-first read --
  a data-format landmine this test had to detect and correct for), so
  P(winner won set 1) IS P(win match | won set 1) directly. ATP+WTA
  2015-2025.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: match-win rate given first-set win = 0.8071,
  effect +0.3071 vs the 0.5 null, p~0 (reported 0), n=41,634 matches.
- **artifact link**: `domains/tennis/knowledge/validate_match_outcomes.py::first_set_winner_match_win_rate`.

---

## Seeded, UNTESTED (highest-leverage remaining; run through a validate_*.py before believing)

### 15. Tiebreak-skill persistence vs noise
- **claim**: a player's tiebreak win rate is a repeatable skill, not just
  their overall serve/return strength expressed in a small sample.
- **causal story**: tiebreak-specific mental toughness/tactics (bigger first
  serve, risk tolerance) could be a distinct, persistent trait.
- **expected signature**: positive split-half correlation of per-player
  tiebreak win-rate, above what serve/return strength alone predicts.
- **test spec**: identify tiebreak games in slam_points (game reached at 6-6
  in a set), split-half (by year) Pearson r of player tiebreak win rate,
  min tiebreaks/half floor. Likely underpowered given how few tiebreaks a
  given player plays in this corpus -- an honest NULL is the expected,
  valid outcome here, not a failure to find one.
- **status**: UNTESTED

### 16. Momentum/streak myth (last-set/game win predicts next point)
- **claim**: winning the previous game or set measurably raises win
  probability on the very next point/game, beyond what server identity and
  score-state already predict.
- **causal story**: "momentum" folklore -- but the CLOSED point-level
  state-conditioning class (#4) already found points ~iid given server,
  which argues against this surviving.
- **expected signature**: near-zero incremental effect once server identity
  is controlled -- likely REJECTED.
- **test spec**: next-point-won ~ prior-game-won + server identity,
  cluster-robust by match, slam_points 2011-2015.
- **status**: UNTESTED

### 17. Fatigue from prior-match DURATION (minutes, not just count)
- **claim**: a longer previous match (by `minutes`) predicts worse
  performance in the current match, distinct from the recent-match-COUNT
  load signal already CONFIRMED in #13.
- **causal story**: total time on court, not just number of matches played,
  is the more direct physical-fatigue ingredient.
- **expected signature**: negative correlation, previous-match minutes vs
  current-match win probability, joined by player + date ordering.
- **test spec**: for each match, look up each player's immediately PRIOR
  match's `minutes` (as-of, strictly earlier date) from `matches.parquet`;
  Welch t-test or correlation vs current-match win, ATP+WTA 2015-2025.
- **status**: UNTESTED

### 18. Clay/grass specialization persistence
- **claim**: a player's clay-minus-hard win-rate differential is a stable,
  repeatable specialization, not noise.
- **causal story**: distinct movement/grip/patience skills reward some
  players disproportionately on clay (or grass) -- a real, persistent style
  fit, not a one-season fluke.
- **expected signature**: positive split-half (e.g. 2015-2019 vs 2020-2025)
  correlation of per-player clay-minus-hard win-rate.
- **test spec**: split-half Pearson r, player-level clay win-rate minus hard
  win-rate, players with a minimum match-count floor per surface per half,
  ATP+WTA 2015-2025.
- **status**: UNTESTED

### 19. Rally-length distribution by round
- **claim**: rally length changes systematically by tournament round (e.g.
  longer in later rounds as weaker early-round mismatches are filtered out).
- **causal story**: early rounds include lopsided matchups that end points
  quickly; later rounds pit closely-matched players against each other,
  extending rallies.
- **expected signature**: rally length rises from early rounds to
  quarterfinal/semifinal/final.
- **test spec**: `rally` column by round bucket (needs a round/tourney-stage
  ingredient on slam_points -- currently only `game_no`/`set_no` are present,
  no explicit round column, so this is likely NOT_TESTABLE on slam_points
  and would need a join to `matches.parquet`'s `round` column via match_id,
  which slam_points does not share -- pending a column/join check).
- **status**: UNTESTED

### 20. Deuce-game length effect on next-game server fatigue
- **claim**: a long, deuce-heavy game measurably reduces the SAME server's
  hold probability in the immediately following game.
- **causal story**: an unusually long service game is a acute fatigue/mental
  spike that should carry over one game, distinct from the whole-match
  fatigue signature already CONFIRMED in #7.
- **expected signature**: lower hold rate in game N+1 after a long
  (>=8-point) game N vs a short one, same server.
- **test spec**: per-game point-count vs next-game-same-server hold
  indicator, within-match, slam_points 2011-2015.
- **status**: UNTESTED

### 21. Seed/ranking upset-rate by round
- **claim**: the rate at which a lower-ranked player beats a higher-ranked
  one is not constant across rounds -- e.g. more upsets in early rounds
  (unseeded floaters) than in the late rounds (only strong players remain).
- **causal story**: round progression itself filters the field toward
  players who are already hard to upset, mechanically compressing the
  upset rate later in a tournament.
- **expected signature**: upset rate (lower-ranked player wins) falls
  monotonically from early to late rounds.
- **test spec**: upset-indicator by `round` bucket, ATP+WTA 2015-2025
  (`round` column exists directly on `matches.parquet`).
- **status**: UNTESTED

### 22. Retirement rate by round and surface
- **claim**: retirement rate itself (not the recent-load correlation already
  CONFIRMED in #13) varies systematically by round (later rounds = more
  fatigue accumulated) and by surface (clay's longer points/rallies could
  raise injury risk vs faster surfaces).
- **causal story**: cumulative tournament fatigue and surface-specific
  physical demand should both independently raise retirement incidence.
- **expected signature**: retirement rate rises by round; retirement rate
  differs by surface.
- **test spec**: retirement-indicator by round bucket and by surface,
  chi-square / proportion test, ATP+WTA 2015-2025.
- **status**: UNTESTED

### 23. Second-serve win-rate discount by surface
- **claim**: the point-win-rate GAP between first serve and second serve is
  smaller on clay than on hard/grass.
- **causal story**: clay neutralizes the raw pace advantage of a big first
  serve more than it neutralizes a slower, spin-heavy second serve, so the
  first-vs-second serve gap should compress on clay.
- **expected signature**: smaller (first-serve-win-rate - second-serve-win-rate)
  gap on Clay vs Hard+Grass.
- **test spec**: needs a first/second-serve indicator per point -- NOT
  present as an explicit column on slam_points (only `p1_ace`/`p1_double_fault`
  flags exist, no serve-number column); likely NOT_TESTABLE on this corpus
  pending a column check, a declared gap rather than an assumption.
- **status**: UNTESTED

### 24. Head-to-head recency bias vs current ranking
- **claim**: a player's recent head-to-head record against a specific
  opponent predicts the next meeting's outcome beyond the current
  ranking gap.
- **causal story**: matchup-specific tactical familiarity (a player who
  simply has your number stylistically) could be a real, persistent signal
  distinct from overall ranking.
- **expected signature**: positive partial correlation, prior-H2H-win-rate
  vs current-match outcome, controlling for rank_diff.
- **test spec**: as-of prior-H2H record (strictly matches before the current
  event_id's date) from `matches.parquet`, partial correlation / logistic
  regression vs rank_diff, ATP+WTA 2015-2025. Needs a minimum prior-meetings
  floor (most pairs meet 0-1 times) -- likely underpowered on this corpus.
- **status**: UNTESTED

### 25. Height advantage on serve, surface-interacted
- **claim**: taller players' serve advantage (ace rate, first-serve points
  won) is larger on faster surfaces (grass) than slower ones (clay).
- **causal story**: a taller player's steeper serve trajectory clears the
  net with more margin and produces a flatter, harder-to-read ball --
  advantages that should compound with a fast, low-bouncing surface.
- **expected signature**: positive height x fast-surface interaction on
  server points-won rate.
- **test spec**: needs a per-point server-height join (via `players.parquet`
  height, matched through slam_points name identity -- the same
  name-matching cost the corpus.py module already documents as NOT done for
  serve_return_interaction; likely NOT_TESTABLE without that join, or would
  need matches.parquet server-points-won aggregates instead of slam_points).
- **status**: UNTESTED

### 26. Break-point conversion rate by set number
- **claim**: break-point conversion rate (returner wins the point) itself
  shifts across set number, distinct from the already-CONFIRMED
  break-point-vs-baseline dip in #3 (which compares within-player to their
  own non-pressure baseline, not across sets).
- **causal story**: fatigue/pressure compounding across a match could make
  break points MORE convertible (server tires) or LESS (server bears down
  when it matters most) as the match wears on -- direction not assumed.
- **expected signature**: a break-point conversion-rate difference, set 1 vs
  set 3+.
- **test spec**: identify break points in slam_points (score_bucket ==
  break-point cell from `score_bucket()`), Welch t-test conversion rate by
  set number, slam_points 2011-2015. Do NOT confuse with the CLOSED #3
  family -- this is a set-number cut, not a re-test of the baseline-delta
  claim.
- **status**: UNTESTED

### 27. Best-of-5 vs best-of-3 upset-rate difference
- **claim**: the longer best-of-5 format (men's Slams) produces fewer
  upsets than best-of-3, because a longer match gives the stronger player
  more opportunities to assert quality over a single bad set.
- **causal story**: match length is itself a variance-reduction mechanism --
  the "better player wins" signal strengthens with more sets played.
- **expected signature**: lower upset rate in best_of==5 matches vs
  best_of==3, at comparable ranking gaps.
- **test spec**: upset-indicator by `best_of`, controlling for rank_diff
  bucket, ATP+WTA 2015-2025 (`best_of` column exists directly).
- **status**: UNTESTED
