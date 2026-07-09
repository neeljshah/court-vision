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

## Validated 2026-07-09 (13 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

### 15. Tiebreak-skill persistence vs noise
- **claim**: a player's tiebreak win rate is a repeatable skill, not just their overall serve/return strength.
- **status**: NOT_TESTABLE -- `slam_points.parquet` has NO player-name/id column at all, only server-slot (1/2) identity WITHIN a match. A per-PLAYER split-half correlation across matches needs cross-match player identity, which does not exist locally on this point-level corpus (stronger than the documented cross-corpus-join gap: it's missing even WITHIN this one corpus).
- **artifact link**: `domains/tennis/knowledge/validate_premise_blocked.py::tiebreak_skill_persistence`.

### 16. Momentum/streak myth (last-set/game win predicts next point)
- **claim**: winning the previous point/game measurably raises win probability on the next one.
- **status**: CONFIRMED (as a same-server, same-game point-to-point effect -- a narrower operationalization than the original "prior game/set" framing, since slam_points carries no cross-match player identity to test the broader claim; see #15's blocker).
- **measured LOCAL magnitude**: same-server-same-game momentum: server-won rate after winning the previous point 0.6173 (n=267,014) vs after losing it 0.5958 (n=189,369); effect +0.0216, p=6.5e-49, n=456,383 points (slam_points 2011-2015). Notable given the CLOSED #4 finding that points are ~iid at the score-state level -- this point-to-point streak effect is a different (narrower, contemporaneous) claim and does survive.
- **artifact link**: `domains/tennis/knowledge/validate_pointlevel_dynamics.py::point_to_point_momentum`.

### 17. Fatigue from prior-match DURATION (minutes, not just count) -- LOCAL NULL
- **claim**: a longer previous match (by minutes) predicts worse performance in the current match.
- **status**: REJECTED (NULL_LOCAL) -- distinct from the CONFIRMED recent-match-COUNT signal (#13); raw duration alone doesn't show it.
- **measured LOCAL magnitude**: win-rate after a >=150min prior match 0.4979 (n=11,222) vs <150min 0.5055 (n=60,176); effect -0.0076, p=0.137, n=71,398 (ATP+WTA 2015-2025).
- **artifact link**: `domains/tennis/knowledge/validate_match_population.py::prior_match_duration_fatigue`.

### 18. Clay/grass specialization persistence
- **claim**: a player's clay-minus-hard win-rate differential is a stable, repeatable specialization.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: split-half pearson r=0.3003, p=6.6e-5, n=171 players (>=5 matches per surface per date-half, ATP+WTA 2015-2025).
- **artifact link**: `domains/tennis/knowledge/validate_match_population.py::clay_grass_specialization_persistence`.
- **wiring**: in-game conditioning-feature candidate -- a per-player surface-specialization index as a pregame strength adjuster, complementary to the CONFIRMED surface-level serve-advantage-erosion mechanism (#5).

### 19. Rally-length distribution by round
- **claim**: rally length rises from early tournament rounds to later rounds.
- **status**: NOT_TESTABLE -- `slam_points.parquet` has no `round` column (only set_no/game_no); `match_id` format ('YYYY-tourney-NNNN') does not encode round, and there is no local join key shared with `matches.parquet`'s `round` column for these specific charted matches.
- **artifact link**: `domains/tennis/knowledge/validate_premise_blocked.py::rally_length_by_round`.

### 20. Deuce-game length effect on next-game server fatigue
- **claim**: a long, deuce-heavy game reduces the SAME server's hold probability in the immediately following (same-server) game.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: next-hold-rate for the same server 2 games later, after a long (>=8pt) game 0.7093 (n=16,531) vs a short game 0.7407 (n=50,694); effect -0.0313, p=7.9e-15, n=67,225 (slam_points 2011-2015).
- **artifact link**: `domains/tennis/knowledge/validate_pointlevel_dynamics.py::deuce_game_length_next_server_fatigue`.
- **wiring**: in-game conditioning-feature candidate -- a live prior-game-point-count feature as a next-service-game hold-probability discount, distinct from the whole-match speed-decay signal (#7).

### 21. Seed/ranking upset-rate by round -- CONFIRMED, direction opposite the seeded claim
- **claim (as seeded)**: upset rate falls monotonically from early to late rounds (round progression filters toward hard-to-upset players).
- **status**: CONFIRMED that upset rate varies by round -- but REJECTED as originally framed: the local data shows upset rate RISING into the later rounds (SF highest), not falling.
- **measured LOCAL magnitude**: chi2 p=2.0e-9, n=40,794; upset rate by round: RR 0.312, R64 0.335, R128 0.350, R16 0.354, QF 0.360, R32 0.363, F 0.365, SF 0.388 (ATP+WTA 2015-2025). Read as: the "only strong players remain" filtering story does not dominate locally -- a plausible confound is that early rounds are often lopsided seed-vs-qualifier matchups with WIDE rank gaps (mechanically LOW upset rate by definition of upset), while SF/F match two already-strong, closely-ranked players where a coin-flip-ish result more often reads as an "upset" by raw rank.
- **artifact link**: `domains/tennis/knowledge/validate_match_population.py::upset_rate_by_round`.

### 22. Retirement rate by round and surface -- PARTIAL
- **claim**: retirement rate varies by round AND by surface.
- **status**: PARTIAL -- round effect CONFIRMED, surface effect NOT significant.
- **measured LOCAL magnitude**: retirement-rate chi2 by round p=6.3e-12 (n=41,886); by surface p=0.084 (not significant at alpha=0.01), surface rates: Clay 0.029, Grass 0.028, Hard 0.033, Unknown 0.014 -- directionally Hard is highest, but the claimed "clay raises injury risk" story is not supported.
- **artifact link**: `domains/tennis/knowledge/validate_match_population.py::retirement_rate_by_round_and_surface`.

### 23. Second-serve win-rate discount by surface
- **claim**: the first-vs-second-serve win-rate gap is smaller on clay than on hard/grass.
- **status**: NOT_TESTABLE -- `slam_points.parquet` has no serve-number column. The sibling `charting_points.parquet` DOES carry `is_second_serve` but covers ALL charted tour-level matches (not just the 4 majors) with no tourney/surface column and a free-text match_id (e.g. '...-Davis_Cup_Finals-...') that does not map through `SURFACE_OF_TOURNEY` -- deriving surface would need parsing thousands of distinct tournament-name strings, a bigger build than this check.
- **artifact link**: `domains/tennis/knowledge/validate_premise_blocked.py::second_serve_discount_by_surface`.

### 24. Head-to-head recency bias vs current ranking
- **claim**: prior H2H record predicts the next meeting's outcome beyond the current ranking gap.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: logit p1_win ~ prior_h2h_rate_p1 + rank_diff, prior-H2H coefficient=+1.4493, p=1.6e-33, n=3,583 matches (pairs with >=3 prior meetings, ATP+WTA 2015-2025). Less sparse than the spec's own worry ("most pairs meet 0-1 times") -- 3,583 matches cleared the >=3-prior-meetings floor.
- **artifact link**: `domains/tennis/knowledge/validate_match_population.py::h2h_recency_vs_ranking`.
- **wiring**: in-game conditioning-feature candidate -- as-of prior-H2H win-rate as a pregame adjuster alongside rank_diff, for the subset of matchups with enough history.

### 25. Height advantage on serve, surface-interacted
- **claim**: taller players' serve/win advantage is larger on faster surfaces (grass) than slower ones (clay).
- **status**: CONFIRMED (ATP-only, since `players.parquet` height is ATP-only -- WTA rows are naturally excluded by the same NaN-height-join pattern already used by `lefty_advantage_on_return`, #11).
- **measured LOCAL magnitude**: logit p1_win ~ height_diff*is_grass, interaction coefficient=+0.0257, p=1.6e-9, n=12,130 (Grass+Clay matches only, ATP).
- **artifact link**: `domains/tennis/knowledge/validate_match_population.py::height_x_surface_interaction`.

### 26. Break-point conversion rate by set number
- **claim**: break-point conversion rate shifts across set number.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: break-point conversion rate, set>=3 0.4113 (n=16,102) vs set==1 0.4283 (n=18,043); effect -0.017, p=0.0015, n=34,145 (slam_points 2011-2015, own break-point detector: returner's before-point score rank exceeds server's). Conversion FALLS late in the match -- consistent with the CONFIRMED #8 finding that DF rate also falls late (servers bear down under rising stakes), not a pure-fatigue story.
- **artifact link**: `domains/tennis/knowledge/validate_pointlevel_dynamics.py::break_point_conversion_by_set_number`.

### 27. Best-of-5 vs best-of-3 upset-rate difference
- **claim**: best-of-5 produces fewer upsets than best-of-3 at comparable ranking gaps.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: logit upset ~ (best_of==5) + |rank_diff|, best_of==5 coefficient=-0.3059, p=1.5e-23, n=40,802 (ATP+WTA 2015-2025).
- **artifact link**: `domains/tennis/knowledge/validate_match_population.py::best_of_5_vs_3_upset_rate`.
- **wiring**: in-game conditioning-feature candidate -- `best_of` as a variance/upset-probability adjuster on top of rank_diff, complementary to the ranking-gap-shape null (#10).
