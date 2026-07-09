# MLB Mechanism Ledger

One entry per mechanical belief the system holds about MLB, with a receipt.
Fields, always in this order: **claim | causal story | expected signature in
our data | test spec | status | measured LOCAL magnitude | artifact link**.

Status values: `UNTESTED` (seeded, not yet run against local data),
`CONFIRMED` (survived a leak-free local test, ideally replicated),
`REJECTED` (tested locally and failed, or failed cross-corpus replication),
`PARTIAL` (mixed verdict across corpora/seasons), `NOT_TESTABLE` (the
ingredient this mechanism needs does not exist in our local corpus -- an
honest gap, not a failure).

Local receipts for `CONFIRMED`/`REJECTED`/`NOT_TESTABLE` rows live in
`data/cache/intel_claims/prereg_hypothesis_ledger.jsonl` (the long-running
prereg ledger) and `domains/mlb/knowledge/validation_ledger.jsonl` (this
session's 10 fresh validations). No `$` edge is claimed anywhere in this
file -- every magnitude below is a calibration/mechanism receipt, not ROI.

---

## Pre-adjudicated (do NOT re-test -- closed classes, cited from the existing ledgers)

### 1. Platoon (pitcher-hand x batter-stand) x pitch type
- **claim**: same-handed batter/pitcher matchups suppress batter performance vs opposite-handed, and the suppression is pitch-type-specific.
- **causal story**: same-side release point + break plane gives the batter a worse look at breaking stuff; opposite-hand matchups remove that angle disadvantage.
- **expected signature**: negative interaction term on `is_k`/contact outcome for same-hand x breaking-pitch-share.
- **test spec**: cluster-robust logistic interaction, PA-level, FWER-tightened budget (interaction_factory discipline).
- **status**: CONFIRMED (REPLICATED across 3+ corpora)
- **measured LOCAL magnitude**: effect -0.0755, p=2.8e-4, n=182,220 (2024-25 replication); originally -0.077, p=1.3e-7, n=366,080.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl` rows verdict=REPLICATED, hypothesis="platoon (P-hand x B-stand) x pitch type"; also `domains/mlb/matchup/pa_outcome_v2.py`, `domains/mlb/platoon_split_index.py`.

### 2. Count leverage (ahead/behind) x pitch-mix
- **claim**: pitchers change their pitch-mix by count state (ahead vs behind), and that mix shift measurably changes strikeout probability.
- **causal story**: ahead in the count, a pitcher can throw a chase pitch out of the zone; behind, he must throw a strike, narrowing his mix toward fastballs -- the batter's advantage/disadvantage tracks that mix shift.
- **expected signature**: negative interaction term on `is_k` for count-state x mix-diversity.
- **test spec**: same cluster-robust interaction design as #1.
- **status**: CONFIRMED (REPLICATED across 3+ corpora, strongest survivor in the ledger)
- **measured LOCAL magnitude**: effect -0.0989, p=1.6e-17, n=584,705; earlier passes -0.080 (p=1.3e-22, n=1,177,944) and -0.110 (p=6.4e-7, n=162,383).
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="count leverage (ahead/behind) x pitch-mix", verdict=REPLICATED (3 rows); `domains/mlb/pitch_engine/selection.py`.

### 3. Base-out state x contact type (GB/FB)
- **claim**: the base-out state (runners/outs) changes which contact type (ground ball vs fly ball) is most run-suppressing, i.e. batted-ball value is state-dependent, not fixed.
- **causal story**: a ground ball with a runner on first and <2 outs risks a double play; a fly ball with a runner on third and <2 outs risks a sac fly -- the "right" contact type to suppress runs flips with state.
- **expected signature**: interaction term on run-value outcome for base-out-state x contact-type.
- **test spec**: cluster-robust interaction, PA-level.
- **status**: CONFIRMED (REPLICATED, though earlier passes were BLOCKED/NULL before the feature builder existed)
- **measured LOCAL magnitude**: effect -0.056, p=0.041, n=124,280 (REPLICATED pass); earlier SURVIVES_PREREG pass -0.116, p=2.7e-5, n=124,127.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="base-out state x contact type (GB/FB)", verdict=REPLICATED.

### 4. Starter velo-band x times-through-order (TTO) -- CLOSED
- **claim**: a starter's fastball velocity band interacts with times-through-the-order to predict the wOBA-against penalty.
- **causal story**: velocity decline within a start (fatigue) compounds with batter familiarity (TTO) to produce a steeper third-time-through penalty for tiring pitchers.
- **expected signature**: positive interaction term, velo-decline x TTO, on wOBA-against.
- **test spec**: cluster-robust interaction; independently, a standalone velo-decline-in-game regression.
- **status**: REJECTED (FAILED_REPLICATION twice: -0.024/p=0.69 and -0.056/p=0.067, after an initial SURVIVES_PREREG at -0.101/p=2.6e-6 that did not hold)
- **measured LOCAL magnitude**: initial pass n=366,080 eff=-0.101 p=2.6e-6; replication n=50,424 eff=-0.024 p=0.69; second replication n=182,220 eff=-0.056 p=0.067.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="starter velo-band x TTO", verdict=FAILED_REPLICATION (x2). CLOSED CLASS -- do not re-attempt (see `feedback_mlb_sp_fatigue_closed_2026_07_04`).

### 5. SP-fatigue class (velo-decline-in-game as a standalone predictor) -- CLOSED
- **claim**: in-start velocity decline alone predicts imminent performance collapse, independent of TTO.
- **causal story**: same fatigue mechanism as #4 but isolated to velocity trend, no batter-familiarity term.
- **expected signature**: negative correlation, velo-decline-in-game vs same-start run-prevention.
- **test spec**: as-of velo-decline feature vs in-game outcome, leak-free.
- **status**: REJECTED / CLOSED (NOT_TESTABLE on this corpus + an honest velo-decline REJECT; globally blocklisted so the interaction factory never silently re-tests it)
- **measured LOCAL magnitude**: n/a (closed before a clean magnitude was recorded; the closure itself is the receipt).
- **artifact link**: `scripts/platformkit/interaction_factory/generator.py` `GLOBAL_BLOCKLIST_ATTRS = {"velo_decline_in_game"}`; memory `mlb_sp_fatigue_closed_2026_07_04`.

### 6. Pitch-mix diversity x times-through-order
- **claim**: a more diverse pitch mix (more distinct pitch types thrown with real frequency) blunts the TTO penalty.
- **causal story**: diversity delays batter pattern-recognition, so a diverse-mix pitcher's third-time-through penalty should be smaller than a two-pitch pitcher's.
- **expected signature**: negative interaction, mix-diversity x TTO, on wOBA-against (i.e. diversity reduces the TTO penalty).
- **test spec**: cluster-robust interaction, PA-level.
- **status**: REJECTED (NULL)
- **measured LOCAL magnitude**: effect -0.063, p=0.195, n=366,080.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="pitch-mix diversity x times-through-order (TTO)", verdict=NULL.

### 7. Catcher framing x count leverage (interaction)
- **claim**: framing skill (extra strikes stolen on borderline pitches) is amplified in high-leverage counts.
- **causal story**: umpires' subjective zone judgment has the most room to move on 2-strike/3-ball counts where the batter's expectation is sharpest -- a good framer should gain more strikes exactly there.
- **expected signature**: positive interaction, framing-skill x count-leverage, on called-strike-above-expected.
- **test spec**: cluster-robust interaction; framing itself already has a standalone VALIDATED_CLAIM (see below), only the INTERACTION with leverage is at issue here.
- **status**: REJECTED (NULL then FAILED_REPLICATION -- the interaction does not hold, though framing as a standalone skill remains a validated claim)
- **measured LOCAL magnitude**: n=111,713 eff=57.0 p=0.885 (NULL); replication n=107,528 eff=103.7 p=0.0021 (FAILED_REPLICATION -- sign/magnitude unstable across corpora).
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="catcher framing x count leverage"; standalone framing claim: `data/cache/intel_claims/mlb_framing_claims.jsonl`, attribute `framing` (status=VALIDATED_CLAIM) in `domains/mlb/profiles/attribute_registry.py`.

### 8. Bullpen fatigue-chain x leverage / bullpen leverage chaining -- data gap
- **claim**: routing the highest-strikeout reliever into the highest-leverage moment (not a fixed inning) preserves more win probability than role-fixed deployment.
- **causal story**: WP swing per half-inning peaks with runners on and a 1-2 run lead; the best arm should go there, not to a predetermined 9th inning.
- **expected signature**: positive gap between leverage-optimal and role-fixed deployment in strand rate / WPA.
- **test spec**: needs a per-appearance leverage-index and reliever-quality-rank ingredient; neither exists locally.
- **status**: NOT_TESTABLE (BLOCKED n=0 three separate attempts in the prereg ledger; this session's fresh column check confirms no `pitcher_role`/`reliever_rank`/`leverage_index` column anywhere in `savant_full__*`)
- **measured LOCAL magnitude**: n=0 (x4 total attempts across both ledgers).
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="bullpen fatigue-chain x leverage", verdict=BLOCKED (x3); `domains/mlb/knowledge/validation_ledger.jsonl`, hypothesis="bullpen_leverage_chaining", verdict=NOT_TESTABLE (this session).

### 9. Pregame team-level aggregates (composed challenger class) -- CLOSED
- **claim**: a composed pregame team-strength aggregate (Elo differential, season-to-date team stats) predicts game outcome/PA outcome beyond what the market already prices.
- **causal story**: n/a -- this is the "does aggregating known team quality add anything" null-hypothesis class, not a specific mechanism.
- **expected signature**: none surviving FWER correction after 3 independent composed-challenger attempts.
- **test spec**: composed-challenger vs market-implied baseline, leak-free walk-forward.
- **status**: REJECTED x3 (NULL every time)
- **measured LOCAL magnitude**: pregame Elo differential n=214,843 eff=-0.00087 p=0.293 (NULL); `pa_outcome_v2b_pregame` composed n=184,058 eff=0.00971 p n/a (NULL), though a later replication of the SAME composed pregame feature came back REPLICATED at a smaller magnitude (eff=0.0197, p=1.1e-4, n=177,508) -- flagged PARTIAL rather than fully closed; treat as closed for NEW pregame aggregates, not as license to re-run this exact one.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypotheses "pregame Elo differential (identity), as-of game date" (NULL) and "pa_outcome_v2b_pregame(...)" (NULL then REPLICATED); `domains/mlb/matchup/pa_outcome_v2b_pregame.py`.

---

## Validated THIS SESSION (10 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

### 10. Edge-zone widening in two-strike counts
- **claim**: pitchers work the shadow/chase zone (Statcast zone 11-14) more often once the count reaches 2 strikes.
- **causal story**: with 2 strikes a pitcher no longer needs to throw a hittable strike -- he can induce a chase, so his target shifts to the zone's edge/outside.
- **expected signature**: higher edge-zone pitch rate at strikes==2 vs strikes<2.
- **test spec**: within-pitch group comparison (Welch t-test), `zone in {11,12,13,14}` rate by `strikes` bucket, one season.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: edge-zone rate 0.568 at strikes==2 vs 0.463 at strikes<2; effect +0.105, p<1e-300 (reported 0), n=702,794 pitches (2025).
- **artifact link**: `domains/mlb/knowledge/validate_count_zone.py::edge_zone_widens_with_two_strikes`; row in `validation_ledger.jsonl`.
- **wiring**: in-game conditioning-feature candidate -- `count_state x edge_zone_rate` as a live pitch-sequencing signal (not yet in the interaction_factory templates; `mlb_pa_attr_x_count_state` is the natural home once a zone-rate attribute is added to the MLB registry).

### 11. Two-strike chase-rate rise
- **claim**: batters expand their swing zone (chase more out-of-zone pitches) once at 2 strikes.
- **causal story**: the cost of a called third strike exceeds the cost of a bad swing, so a rational batter protects the zone edge at 2 strikes.
- **expected signature**: higher (swing AND out-of-zone) rate at strikes==2.
- **test spec**: same within-pitch Welch-t design as #10.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: chase rate 0.216 at strikes==2 vs 0.106 at strikes<2; effect +0.111, p<1e-300, n=702,794 (2025).
- **artifact link**: `domains/mlb/knowledge/validate_count_zone.py::two_strike_chase_rate_rises`.
- **wiring**: in-game conditioning-feature candidate -- a batter's own two-strike chase-rate delta as a live PA-progression signal, alongside the CONFIRMED count-leverage x pitch-mix mechanism (#2).

### 12. First-pitch strike suppresses walk rate
- **claim**: a first-pitch strike lowers the walk probability for the rest of that plate appearance.
- **causal story**: falling behind 0-1 removes the pitcher's need to throw a hittable pitch on 2-0/3-1, so the PA is less likely to end in a walk.
- **expected signature**: lower walk rate on PAs with a first-pitch strike vs first-pitch ball, restricted to PAs that continued past pitch 1.
- **test spec**: Welch t-test, `is_walk` by first-pitch outcome, one season.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: BB rate 0.050 after a first-pitch strike vs 0.145 otherwise; effect -0.095, p<1e-300, n=160,137 (2025).
- **artifact link**: `domains/mlb/knowledge/validate_count_zone.py::first_pitch_strike_suppresses_bb`.
- **wiring**: in-game conditioning-feature candidate -- `first_pitch_outcome` as a live within-PA walk-probability re-pricer, usable the moment pitch 1 resolves.

### 13. Park-factor run modulation (split-half stability) -- LOCAL NULL, textbook-defying
- **claim**: park run environment is a stable, repeatable per-venue signal.
- **causal story**: altitude, dimensions, and foul territory should produce a park-level run-scoring bias that persists within a season.
- **expected signature**: strong positive split-half correlation of average total-runs/game across parks (first half of season vs second half).
- **test spec**: split-half Pearson r across 30 home-park groups, one season.
- **status**: REJECTED (NULL_LOCAL) -- the single most interesting reject this session
- **measured LOCAL magnitude**: r=0.336, p=0.069, n=30 parks (2025) -- directionally positive but NOT significant at alpha=0.01, and likely underpowered (n=30, one season split in half). Do not treat park factor as unreliable outright; treat "one-season split-half is enough to see it" as REJECTED.
- **artifact link**: `domains/mlb/knowledge/validate_contact_park.py::park_factor_split_half`.

### 14. Infield shift suppresses ground-ball BABIP -- LOCAL NULL post-ban
- **claim**: non-standard infield alignment (shade/strategic) lowers ground-ball hit rate vs standard alignment.
- **causal story**: repositioning fielders toward a batter's pull tendency should convert more ground balls into outs.
- **expected signature**: lower GB hit-rate under shade/strategic alignment vs standard.
- **test spec**: Welch t-test, GB hit-rate by `if_fielding_alignment` bucket, one season, batted balls with a decided event only.
- **status**: REJECTED (NULL_LOCAL) -- consistent with the 2023 shift-ban shrinking "shade"/"strategic" to much weaker alignments than the pre-ban true shift.
- **measured LOCAL magnitude**: GB hit-rate 0.245 (shaded/strategic, n=17,522) vs 0.251 (standard, n=34,307); effect -0.006, p=0.146, n=51,829 (2025).
- **artifact link**: `domains/mlb/knowledge/validate_contact_park.py::infield_shift_suppresses_gb_babip`.

### 15. Contact-quality persistence (split-half)
- **claim**: batted-ball contact quality (exit velocity) is a repeatable batter skill, not noise.
- **causal story**: bat speed/swing quality is a stable batter trait, so mean launch_speed should correlate across a season's two halves.
- **expected signature**: strong positive split-half correlation of mean launch_speed per batter.
- **test spec**: split-half Pearson r, batters with >=20 batted-ball events per half, one season.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: r=0.593, p=3.2e-42, n=430 batters (2025).
- **artifact link**: `domains/mlb/knowledge/validate_contact_park.py::contact_quality_persists_split_half`.
- **wiring**: in-game conditioning-feature candidate -- an as-of mean-launch-speed attribute is already the right shape for `mlb_pa_batter_x_pitcher`'s left pool once added to the batter registry (`domains/mlb/profiles/attribute_registry.py` already has `contact_quality`, currently DESCRIPTIVE; this split-half result is the receipt that would upgrade it toward VALIDATED_MECHANISM).

### 16. Ground-ball double-play suppression
- **claim**: ground balls with a force at first and <2 outs produce double plays at a much higher rate than other batted-ball outcomes in the same state.
- **causal story**: a ground ball to an infielder with a force in progress is a two-out mechanical opportunity that a fly ball/line drive cannot produce.
- **expected signature**: much higher double-play rate on GB vs non-GB in the same force state.
- **test spec**: Welch t-test, DP rate by `bb_type==ground_ball` within (`on_1b` occupied, outs<2, decided event), one season.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: DP rate 0.319 (GB, n=9,753) vs 0.023 (non-GB, n=11,456); effect +0.296, p<1e-300, n=21,209 (2025).
- **artifact link**: `domains/mlb/knowledge/validate_data_gaps.py::gb_double_play_suppression`.
- **wiring**: in-game conditioning-feature candidate -- `bb_type x force_state` as a live GIDP-risk re-pricer for base-out win-probability, adjacent to the CONFIRMED base-out-state x contact-type mechanism (#3).

### 17. Weather/park HR modulation -- data gap
- **claim**: temperature/wind conditions shift home-run rate.
- **causal story**: warmer air is less dense (more carry); wind direction/speed changes fly-ball distance directly.
- **expected signature**: n/a until a weather ingredient exists.
- **test spec**: column-existence check on `savant_full__*`.
- **status**: NOT_TESTABLE
- **measured LOCAL magnitude**: n=0 -- no `temperature`/`temp`/`wind_speed`/`wind_dir`/`weather` column anywhere in the local Statcast extract.
- **artifact link**: `domains/mlb/knowledge/validate_data_gaps.py::_not_testable("weather_park_hr_modulation", ...)`.

### 18. Bullpen leverage chaining -- data gap (fresh column check, same conclusion as #8)
- **status**: NOT_TESTABLE -- see #8; this session's column check independently confirms no role/leverage-index ingredient exists locally.
- **artifact link**: `domains/mlb/knowledge/validate_data_gaps.py::_not_testable("bullpen_leverage_chaining", ...)`.

### 19. Stolen-base break-even rate -- data gap
- **claim**: stolen-base attempts cluster near the ~73% success rate that breaks even on run expectancy.
- **causal story**: a rational baserunner/coach only runs when expected success exceeds the break-even threshold implied by the run-expectancy cost of an out.
- **expected signature**: n/a until SB/CS events exist locally.
- **test spec**: `events` value-set check on `savant_full__*`.
- **status**: NOT_TESTABLE
- **measured LOCAL magnitude**: n=0 -- no `stolen_base_*`/`caught_stealing_*` value present in the local `events` column at all (2025 season file).
- **artifact link**: `domains/mlb/knowledge/validate_data_gaps.py::_sb_not_testable`.

---

## Seeded, UNTESTED (highest-leverage remaining; run through the interaction factory or a future validate_*.py before believing)

### 20. Times-through-order decay (raw, velo-independent)
- **claim**: wOBA-against rises from 1st to 3rd time through the order even controlling for velocity.
- **causal story**: batter familiarity/pattern-recognition compounds independent of pitcher fatigue.
- **expected signature**: monotonic wOBA-against rise by trip number, net of a velo-band control.
- **test spec**: PA-level regression, wOBA-against ~ trip_number + velo_band, cluster-robust by pitcher.
- **status**: UNTESTED

### 21. Walk-economy baserunner inflation
- **claim**: run-expectancy lift per walk is state-dependent (bigger with runners on 2nd/3rd than bases empty).
- **causal story**: a walk advances the base-out state; the marginal RE gain differs by which bases are occupied.
- **expected signature**: RE-added per walk higher in RISP states than bases-empty.
- **test spec**: base-out state x walk-event RE-added, descriptive, one season.
- **status**: UNTESTED

### 22. Big-inning generation (run clustering)
- **claim**: ~60-65% of runs score in innings with 3+ runs; a leadoff baserunner disproportionately gates big innings.
- **causal story**: run expectancy is non-linear in base-out state; the first baserunner of an inning is the critical gating event.
- **expected signature**: same-inning scoring probability jumps sharply after a leadoff single/walk.
- **test spec**: inning-level, P(3+ runs this inning | leadoff on-base) vs P(3+ runs | leadoff out).
- **status**: UNTESTED

### 23. Sequencing and cluster luck
- **claim**: observed run totals diverge from context-neutral expectation in small samples and regress over a season.
- **causal story**: hit sequencing/timing is close to random; short-sample divergence is variance, not skill.
- **expected signature**: early-season (actual - expected runs) gap shrinks by roughly half by game ~81 (team-season).
- **test spec**: rolling actual-vs-expected-run gap by games-played, team-season.
- **status**: UNTESTED

### 24. Power/ISO run compression
- **claim**: high-ISO lineups have tighter strand-rate variance because HRs don't need sequencing.
- **causal story**: a home run scores runners without requiring a multi-hit sequence, compressing the run distribution.
- **expected signature**: negative correlation between team ISO and strand-rate variance.
- **test spec**: team-season ISO vs strand-rate std, cross-sectional.
- **status**: UNTESTED

### 25. Speed/baserunning advancement value
- **claim**: extra-base-taken rate on singles/doubles adds measurable run expectancy independent of power.
- **causal story**: first-to-third on a single converts an ~0.85-run state to ~1.19-run state.
- **expected signature**: positive RE-added per extra-base-taken event.
- **test spec**: base-state-transition RE-added on singles with a runner on first, one season (derivable from on_1b/on_2b/on_3b transitions -- does not need the missing SB/CS events).
- **status**: UNTESTED

### 26. Defensive-efficiency conversion
- **claim**: team defense suppresses BABIP below contact-quality expectation.
- **causal story**: range/positioning converts marginal balls in play into outs beyond what exit velocity/launch angle alone predict.
- **expected signature**: negative residual (actual BABIP - xBABIP-from-launch-conditions) for good defensive teams, stable across season halves.
- **test spec**: team-level residual BABIP, split-half persistence check (same design as contact-quality persistence, #15, at team grain).
- **status**: UNTESTED

### 27. Pitch-count efficiency and starter durability
- **claim**: starters who throw fewer pitches/inning go deeper, displacing higher-ERA bullpen innings.
- **causal story**: first-pitch-strike rate and low walk rate produce quick innings; each saved bullpen inning avoids a worse expected-run rate.
- **expected signature**: negative correlation, pitches/inning vs innings/start; positive gap between bullpen ERA and rotation ERA.
- **test spec**: starter-season pitches/PA vs innings/start correlation; team bullpen-vs-rotation ERA gap.
- **status**: UNTESTED

### 28. Leverage-index conversion
- **claim**: win-probability swing per event scales with game leverage (score margin x inning).
- **causal story**: the same run has far more win-probability impact in a late, tied game than an early blowout.
- **expected signature**: WPA per run event rises monotonically with a leverage proxy (inning x |margin| bucket).
- **test spec**: post_home_score/post_away_score delta-based WPA proxy by inning x margin bucket, one season.
- **status**: UNTESTED

### 29. High-leverage strand prevention
- **claim**: strikeout-heavy relievers strand RISP runners at a higher rate than contact-oriented ones, especially late/close.
- **causal story**: eliminating contact removes both advancement and hit risk simultaneously with a runner on.
- **expected signature**: positive correlation, reliever K-rate vs RISP strand rate, conditioned on late-inning/close-game appearances.
- **test spec**: pitcher-season K-rate vs RISP-strand-rate, restricted to innings>=7 and |margin|<=2.
- **status**: UNTESTED

### 30. Lineup-slot run value
- **claim**: batting-order slot carries its own run-value independent of the individual hitter (e.g. leadoff OBP matters more than slot-6 OBP).
- **causal story**: the same OBP produces more runs in a slot that gets more plate appearances with runners on ahead of the top of the order.
- **expected signature**: RE-added per walk/single differs systematically by lineup slot even holding batter quality roughly fixed.
- **test spec**: needs a batting-order-slot column, not present in `savant_full__*` (probably NOT_TESTABLE pending an ingredient check).
- **status**: UNTESTED

### 31. Umpire zone-call consistency
- **claim**: individual plate umpires differ in how consistently they call the rulebook zone, and that consistency is a repeatable umpire trait.
- **causal story**: umpire zone tendencies (wider/tighter, corner biases) are personal and stable across games.
- **expected signature**: split-half correlation of an umpire's called-strike rate on borderline (zone 11-14) pitches.
- **test spec**: needs an umpire-identity column -- likely NOT_TESTABLE on `savant_full__*` pending a column check (no umpire id seen in the schema pulled this session).
- **status**: UNTESTED

### 32. Catcher game-calling (pitch sequencing) effect
- **claim**: catchers differ in how they sequence pitch types within a PA, and better sequencing suppresses contact quality independent of framing.
- **causal story**: unpredictable sequencing (not just individual pitch quality) disrupts batter timing.
- **expected signature**: catcher (via `fielder_2`) fixed-effect on PA-level contact quality, net of pitcher and batter effects.
- **test spec**: PA-level regression with catcher fixed effect (`fielder_2` as the catcher id), controlling pitcher and batter identity.
- **status**: UNTESTED

### 33. Spin-rate deception (independent of velocity)
- **claim**: release spin rate predicts whiff rate on breaking pitches independent of velocity band.
- **causal story**: spin drives late break/deception; two pitches at the same velocity can have very different swing-and-miss profiles by spin.
- **expected signature**: positive partial correlation, `release_spin_rate` vs whiff rate, controlling `release_speed`.
- **test spec**: pitch-level regression, whiff ~ release_spin_rate + release_speed, breaking-pitch-type subset.
- **status**: UNTESTED

### 34. Launch-angle sweet-spot consistency
- **claim**: a batter's sweet-spot rate (launch angle 8-32 degrees) is a repeatable skill distinct from raw exit velocity.
- **causal story**: swing plane/timing consistency governs launch angle independent of bat speed.
- **expected signature**: split-half correlation of sweet-spot rate per batter (same design as #15, different metric).
- **test spec**: split-half Pearson r, batter sweet-spot rate, >=20 BBE/half.
- **status**: UNTESTED
