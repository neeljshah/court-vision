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
- **status**: NOT_TESTABLE on `slam_points.parquet` specifically -- it has NO player-name/id column at all, only server-slot (1/2) identity WITHIN a match. A per-PLAYER split-half correlation across matches needs cross-match player identity, which does not exist locally on this point-level corpus (stronger than the documented cross-corpus-join gap: it's missing even WITHIN this one corpus). UNBLOCKED 2026-07-10 via a different corpus that does carry cross-match player identity -- see #32, which tests the same claim on `matches.parquet`/`match_stats.parquet` (REJECTED, honest NULL, not confirmed).
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

---

## Validated 2026-07-10 (4 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

New corpus this session: `travel_scouting.parquet` (55,446 rows, 27,723 events,
2015-2025 -- venue altitude + miles flown into the venue per player) joined
to `match_stats.parquet` (59,312 rows -- per-match serve/break-point counts)
and `matches.parquet`. The (event_id, is_p1) join between travel_scouting and
matches.parquet was verified this session: 100% event_id overlap with both
matches.parquet and match_stats.parquet, exactly one True/one False is_p1
row per event, and a 100% name-match rate against matches.parquet's
p1_name/p2_name for the same event_id.

### 28. Altitude effect on serve ace rate -- CONFIRMED, folklore-reversing
- **claim**: venue altitude changes serve effectiveness (thin-air folklore says higher altitude -> more aces).
- **causal story**: thinner air at altitude reduces drag on the serve, so the ball should carry faster and produce more untouched aces.
- **expected signature**: higher combined ace rate at high-altitude venues.
- **test spec**: Welch t-test, combined (p1+p2)/2 ace rate, venues >=500m vs <500m altitude (real tour venues clearing this: Madrid 667m, Bogota 2640m, Quito 2850m -- verified in data), ATP+WTA 2015-2025.
- **status**: CONFIRMED -- but in the OPPOSITE direction from the thin-air folklore.
- **measured LOCAL magnitude**: combined ace rate 0.0722 (>=500m, n=2,522) vs 0.0805 (<500m, n=24,941); effect -0.0083, p=2.94e-23, n=27,463.
- **artifact link**: `domains/tennis/knowledge/validate_travel_altitude.py::altitude_effect_on_serve_ace_rate`.

### 29. Long travel lowers win probability, net of ranking -- CONFIRMED
- **claim**: traveling further into the venue than your opponent measurably lowers win probability, beyond what the ranking gap already explains.
- **causal story**: jet lag / fatigue from a longer pre-match trip should erode performance independent of who is favored on paper.
- **expected signature**: negative travel-differential coefficient on win probability, controlling for rank_diff.
- **test spec**: logit p1_win ~ travel_diff_1000mi + rank_diff (partial effect over the full matched sample, not a rank-windowed bucket comparison), ATP+WTA 2015-2025.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: travel coefficient -0.0699 per 1000mi p1 traveled more than p2 (net of rank_diff), p=7.2e-52, n=26,950.
- **artifact link**: `domains/tennis/knowledge/validate_travel_altitude.py::long_travel_effect_on_win_prob_partial`.
- **wiring**: in-game conditioning-feature candidate -- a pre-match travel-differential adjuster alongside rank_diff, complementary to the CONFIRMED recent-match-load retirement signal (#13).

### 30. Break-point-save skill persistence, controlling for serve strength -- LOCAL NULL
- **claim**: a player's break-point-save rate is a repeatable skill beyond their overall serve win rate (guards the collinearity between the two, correlation ~0.80 at the player level).
- **causal story**: some servers might specifically raise their level under break-point pressure beyond what their baseline serve strength predicts -- a specific "clutch-on-serve" skill.
- **expected signature**: split-half bp_saved_pct correlation should survive controlling for split-half-A serve win rate.
- **test spec**: split-half persistence (>=5 matches/half, >=3 bp faced/match floor, >=15 players), raw pearson r for reference, then OLS bpB ~ bpA + svA (svA = leak-safe prior-half serve win rate control), ATP+WTA 2015-2025.
- **status**: REJECTED (NULL_LOCAL) -- raw persistence is real (r=0.44) but collapses once serve strength is controlled, meaning the raw correlation is serve-strength persistence in disguise, not an independent break-point-save skill.
- **measured LOCAL magnitude**: raw split-half pearson r=0.4422 (p=1.31e-17, n=338 players) vs OLS-controlled bpA partial coefficient=-0.0900 (p=0.251, NOT significant), n=338.
- **artifact link**: `domains/tennis/knowledge/validate_bp_save_persistence.py::bp_save_skill_persistence_partial`. Distinct from and a useful complement to #1 (the CONFIRMED serve-tier x return-tier interaction) -- this closes a narrower "independent clutch-on-serve" framing that #1 does not test.

### 31. Break-point-save differential predicts outcome, controlling for serve differential -- CONFIRMED, modest relative magnitude
- **claim**: the match-level bp_saved_pct differential relates to who wins, beyond the overall serve-win-rate differential.
- **causal story**: a mechanical, within-match relationship -- saving more break points than your opponent directly helps you win, but the question is whether it adds information beyond overall serve dominance.
- **expected signature**: bp_diff coefficient significant and nonzero after controlling for serve_diff in a joint logit.
- **test spec**: logit p1_win ~ bp_diff + serve_diff, >=3 bp faced/side floor, ATP+WTA 2015-2025.
- **status**: CONFIRMED, but read cautiously -- bp_diff's coefficient (4.01) is an order of magnitude smaller than serve_diff's (48.11) at comparable input scale, so the differential carries real but minor incremental information once overall serve dominance is known; large n (27,937) makes the p-value alone a poor discriminator here.
- **measured LOCAL magnitude**: bp_diff coefficient=4.0083, p=2.07e-268, vs serve_diff coefficient=48.1141, n=27,937.
- **artifact link**: `domains/tennis/knowledge/validate_bp_save_persistence.py::bp_save_differential_predicts_outcome_partial`.

---

## Seeded 2026-07-10 (research-wave -- literature-sourced, UNTESTED, M10 pool feedstock)

Fresh mechanism hypotheses from public tennis-analytics literature, checked
against every row above and against `data/frontend/reject_ledger.jsonl`
(0 keyword hits for `tiebreak`/`dominance`/`games_per_set`/`matches_last_14`
on sport=tennis) before seeding. No validator built this lane.

### 32. Tiebreak-skill persistence, via a corpus that carries player identity (unblocks NOT_TESTABLE #15)
- **claim**: a player's tiebreak win rate is a repeatable skill, not just noise -- the same claim as #15, but #15 was NOT_TESTABLE because `slam_points.parquet` has no cross-match player identity; `matches.parquet`/`match_stats.parquet` DOES carry player identity (`p1_id`/`p2_id`) across matches.
- **causal story**: same as #15 -- tiebreak points are high-pressure, sudden-death-adjacent; if some players have a durable tiebreak-specific edge (composure, big-point serving) beyond their overall level, it should show up as a stable, repeatable trait.
- **expected signature**: positive split-half Pearson r of per-player realized tiebreak win rate, first half of the corpus's date range vs second, that survives controlling for overall serve strength (guards the same collinearity as #30's bp-save lane: a tiebreak is itself a run of serve/return points).
- **test spec**: realized tiebreak outcomes parsed from `matches.parquet`'s `score` string (set tokens like `7-6(4)`) using the same match-winner-perspective correction already validated for row #14, split-half Pearson r per player (>=5 tiebreaks faced/half, >=15 players), THEN OLS `tbB ~ tbA + svA` (svA = split-half-A serve win rate from `match_stats.parquet`, same partial-effect design as #30) to guard the collinearity; declared bar |r or partial coef|>=0.15 AND p<0.01.
- **status**: REJECTED (NULL_LOCAL on both the raw split-half correlation and the serve-strength-controlled partial effect)
- **measured LOCAL magnitude**: raw split-half pearson r=0.0783 (p=0.263), OLS-controlled partial coefficient=0.0745 (p=0.268), n=206 players (>=5 tiebreaks faced/half, ATP+WTA). Neither clears the declared |.|>=0.15 & p<0.01 bar -- an honest NULL, echoing #15's original suspicion and #30's "no independent skill beyond serve strength" pattern, now confirmable on a corpus WITH player identity rather than blocked by a missing column.
- **artifact link**: `domains/tennis/knowledge/validate_research_wave1.py::tiebreak_skill_persistence_partial`. **Premise-check correction**: the seeded row (and the task brief that authored it) described `asof_setdetail.parquet` as carrying "player_id" directly -- it does not; that file has only `event_id` + p1_/p2_-prefixed feature columns, no id column at all. Player identity is reached by joining `event_id` to `matches.parquet`'s p1_id/p2_id (a prefixed variant, same join path #29/#31 already use), so this test uses `matches.parquet`'s realized score-string outcome instead of `asof_setdetail.parquet`'s rolling asof feature -- the row's own test spec named this as the "more direct" option.

### 33. Set-margin "dominance" metric predicts outcome beyond ranking gap
- **claim**: a player's trailing average-games-per-set-won (a game-margin "dominance" proxy, distinct from the win/loss-only signal already used everywhere else in this ledger) predicts the next match's outcome beyond the ranking-gap alone.
- **causal story**: two players can have the same rank but very different margins of victory in their recent matches (grinding out close wins vs. blowing opponents out); a game-margin trend should carry information about current form/dominance that rank (a slower-moving, longer-window statistic) does not fully capture.
- **expected signature**: nonzero `avg_games_per_set_asof_diff` coefficient in a joint logit alongside `rank_diff`.
- **test spec**: logit `p1_win ~ avg_games_per_set_asof_diff + rank_diff`, ATP+WTA 2015-2025, `data/domains/tennis/asof_setdetail.parquet`; declared bar |coef|/se >= 2 (p<0.05) net of rank_diff, same design family as #24 (H2H recency) and #25 (height x surface).
- **status**: CONFIRMED -- but in the OPPOSITE direction from the causal story, joining this ledger's other folklore-reversing rows (#11, #21, #28).
- **measured LOCAL magnitude**: logit p1_win ~ avg_games_per_set_asof_diff + rank_diff, coefficient=-0.0468 (coef/se=-2.11), p=0.0347, n=29,229 (ATP-only, since `asof_setdetail.parquet` is the ATP file per this row's own scope). A bigger prior game-margin edge over the opponent predicts a LOWER win probability net of rank, not higher -- consistent with the row's own cited FiveThirtyEight caveat ("trying to account for margins in tennis often leads to worse predictions"); a plausible confound is that a large recent-margin edge is itself informative about facing weak early-round opposition rather than current dominant form, which rank_diff does not fully net out.
- **artifact link**: `domains/tennis/knowledge/validate_research_wave1.py::dominance_margin_predicts_outcome_partial`.

### 34. Extended (14-day) match load degrades serve execution, net of the already-tested retirement link
- **claim**: a heavier trailing 14-day match load predicts worse serve execution (lower ace rate / first-serve-in%) in the next match -- a performance-degradation outcome, distinct from #13's CONFIRMED retirement-risk link (which used the 7-day window and an injury/withdrawal outcome, not an execution-quality outcome).
- **causal story**: cumulative match load over two weeks should tax serve mechanics (leg drive, shoulder fatigue) even short of the acute exhaustion that produces a retirement -- the same fatigue-on-serve-execution logic already CONFIRMED within a single match (#7, serve-speed decay), extended across matches using a window the retirement test did not use.
- **expected signature**: negative correlation between combined `matches_last_14d` and same-match `ace_rate`/`1st_in_pct`.
- **test spec**: Welch t-test (or Pearson r), `p1_ace_rate`/`p1_1st_in_pct` (and p2 symmetric) vs `matches_last_14d` tercile, `data/domains/tennis/schedule_density.parquet` joined to `match_stats.parquet` by event_id+player_id (via `matches.parquet`'s p1_id/p2_id, the same event_id+player_id join pattern already used by #13), ATP+WTA 2015-2025; declared bar |eff|>=0.01 (rate points) AND p<0.01.
- **status**: REJECTED (NULL_LOCAL by the pre-declared minimum-effect gate on BOTH metrics, despite tiny p-values -- same honest-NULL-despite-significance framing as #9) -- and in the OPPOSITE direction from the fatigue causal story.
- **measured LOCAL magnitude**: combined ace rate, top matches_last_14d tercile 0.0826 (n=8,948) vs bottom tercile 0.0773 (n=13,400), effect +0.0054, p=5.4e-18; combined 1st-serve-in%, top tercile 0.6239 vs bottom 0.6142, effect +0.0097, p=1.1e-34; n=29,256 (ATP+WTA). Both effects are POSITIVE (busier players serve BETTER, not worse) and both fall just under the declared 0.01-rate-point floor despite the tiny p-values -- read as a survivorship confound (players sustaining a heavy recent match load are disproportionately the stronger, deeper-running players in a draw), not evidence of fatigue.
- **artifact link**: `domains/tennis/knowledge/validate_research_wave1.py::load_14d_ace_rate_tercile`, `::load_14d_first_serve_in_tercile`.

---

## Seeded 2026-07-10 (research-wave 2 -- literature-sourced, UNTESTED, round-2 pool feedstock)

Fresh mechanism hypotheses from different literature areas than the
round-1 research wave (#32-34 above: tiebreak-skill persistence via
matches.parquet, dominance-margin, extended 14-day load). Checked against
every row above and against `data/frontend/reject_ledger.jsonl` (0 keyword
hits for `tiebreak`/`sub.*timing`/`within.*tourn`/`tourney.*rest` on
sport=tennis) before seeding. No validator built this lane.

### 35. Tiebreak serve-order (serving first) predicts winning it, net of the literature's own weaker-player confound
- **claim**: serving the FIRST point of a tiebreak predicts winning that tiebreak -- tested here as a raw local rate, explicitly flagging the same confound the cited literature already found (the first server in a TB is, on average, the WEAKER player entering that game, since the score sequence that produces a 6-6 tied set determines who serves first, not chance).
- **causal story**: the theoretical mirrored serve sequence (first two points AB, next two BA, i.e. a Prouhet-Thue-Morse-like pattern) should cancel out any structural service-order advantage -- but real-world tiebreaks are not randomized, so a naive raw win-rate read risks conflating "who serves first" with "who was already playing worse."
- **expected signature**: raw P(first-server wins the TB) vs 0.5 -- cited literature finds ~49.7% (near coin-flip, first server on average the weaker player), so the local read should be reported honestly whichever way it falls, not assumed to favor the first server.
- **test spec**: `domains.tennis.knowledge.validate_research_wave2.tiebreak_serve_order_win_rate` -- `data/cache/sackmann_pbp/slam_points.parquet` (2011-2015, 543,772 points, confirmed columns `match_id`/`set_no`/`game_no`/`point_number`/`point_server`/`p1_games_won`/`p2_games_won` this session), tiebreak games identified as the `game_no` where `p1_games_won==6 AND p2_games_won==6` within a `set_no` (standard 6-6 trigger), TB winner derived from whichever side's `p1_games_won`/`p2_games_won` shows 7 -- checked first on the TB game's OWN last row (true for ~46% of TBs sampled this session), falling back to the NEXT `game_no`'s first row (true for the rest) -- first-server = `point_server` at the minimum `point_number` within that TB's rows; one-sample t-test of first-server-won indicator against 0.5, min floor >=30 TBs for a first pass.
- **status**: NULL_LOCAL
- **measured LOCAL magnitude**: first-server won 0.5035 of n=1281 resolvable tiebreaks (t=0.251, p=0.802 vs 0.5) -- matches the cited ~0.497 literature reference within noise, no local deviation from coin-flip.
- **artifact link**: `domains/tennis/knowledge/validate_research_wave2.py::tiebreak_serve_order_win_rate`, `validation_ledger.jsonl` (hypothesis=tiebreak_serve_order_win_rate).
- **source**: "Does Serving First in a Tiebreak Give You an Edge?" (Jeff Sackmann, Tennis Abstract/Heavy Topspin), https://www.tennisabstract.com/blog/2015/10/14/does-serving-first-in-a-tiebreak-give-you-an-edge/ -- finds ~49.7% first-server win rate across ~2,500 WTA tiebreaks and explicitly flags that the first server is, on average, the weaker player (the confound this row's expected-signature framing accounts for); and "Testing the effect of serve order in tennis tiebreak" (ScienceDirect/Journal of Economic Behavior & Organization), https://www.sciencedirect.com/science/article/abs/pii/S0167268117303530.

### 36. Within-tournament rest gap predicts serve execution/win probability (distinct from the season-level windows already closed in #13/#17/#34)
- **claim**: the rest gap between a player's CONSECUTIVE matches WITHIN THE SAME TOURNAMENT predicts serve execution or win probability in the later match -- distinct from #13 (CONFIRMED, season-level 7-day retirement risk), #17 (REJECTED, prior-match duration), and #34 (REJECTED, season-level 14-day-load ace rate), none of which are scoped to a single tournament's own round-to-round schedule.
- **premise check**: `data/domains/tennis/schedule_density.parquet`'s `rest_days` is GLOBAL (days since the player's most recent match, ANY tournament) -- confirmed by column inspection this session (`event_id`/`player_id`/`player_name`/`date`/`year`/`surface`/`rest_days`/`matches_last_7d`/`matches_last_14d`, no `tourney_id` column). A genuinely NEW within-tournament-scoped rest-gap derivation from `data/domains/tennis/matches.parquet` (confirmed columns `event_id`/`tourney_id`/`tourney_name`/`tourney_level`/`round`, 30,616 rows) is required -- a plain per-player-per-tourney sort + consecutive-date-diff, not a fictitious ingredient.
- **causal story**: cited multi-day-tournament physiology literature finds measurable serve-accuracy and movement decline across consecutive days of match play WITHIN one event -- a within-tournament fatigue chain distinct from the season-level scheduling-density windows this ledger has already closed as NULL.
- **expected signature**: negative relationship between (days since this player's PREVIOUS match in the SAME `tourney_id`) and same-match ace-rate/1st-serve-in% -- i.e. a same-tournament short turnaround (e.g. 1-day gap, common in smaller draws) predicts worse serve execution than a longer within-tournament gap.
- **test spec**: `domains.tennis.knowledge.validate_research_wave2.within_tournament_rest_gap_ace_rate` / `_first_serve` -- derive `same_tourney_rest_days` from `matches.parquet` (`tourney_id`, `p1_id`/`p2_id`, `date`), per-player sort within each `tourney_id`, diff of consecutive match dates, joined to `match_stats.parquet` by `event_id` for `ace_rate`/`1st_in_pct` (same join pattern already used by #13/#34), ATP+WTA 2015-2025; Welch t-test, short within-tourney gap (<=1 day) vs longer (>=2 days), min n floor 200/bucket; declared bar |eff|>=0.01 (rate points) AND p<0.01, same bar family as #34.
- **status**: NOT_TESTABLE -- corpus premise failure, not underpowered
- **measured LOCAL magnitude**: n/a. `matches.parquet`'s `date` column is confirmed this session to be the TOURNAMENT START date, constant across every round of a `tourney_id` (2321/2322 tourney_ids have exactly 1 distinct date value across all their rows, ATP+WTA). A consecutive-match-date diff within `tourney_id` is therefore always 0 for all 36,996 player-match rows -- the row's own premise-check line ("a plain per-player-per-tourney sort + consecutive-date-diff, not a fictitious ingredient") assumed per-match date granularity this corpus does not have. `round` (R32/.../F) exists as a coarser ordinal but is a different metric than the day-level gap the causal story specifies, so it was not substituted in.
- **artifact link**: `domains/tennis/knowledge/validate_research_wave2.py::within_tournament_rest_gap_ace_rate`/`_first_serve`, `validation_ledger.jsonl` (hypothesis=within_tournament_rest_gap_ace_rate / _first_serve).
- **source**: "Consecutive Days of Prolonged Tennis Match Play: Performance, Physical, and Perceptual Responses in Trained Players" (Gescheit et al.), https://pubmed.ncbi.nlm.nih.gov/25710259/ -- finds measurable serve-accuracy and movement decline across consecutive tournament days, the physiological basis for testing a within-tournament (not season-level) rest-gap signal; local test blocked on corpus granularity, not on this literature basis.

---
