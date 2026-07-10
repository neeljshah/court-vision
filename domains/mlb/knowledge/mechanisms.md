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

## Validated 2026-07-09 (15 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

### 20. Times-through-order decay (raw, velo-independent)
- **claim**: wOBA-against rises from 1st to 3rd time through the order even controlling for velocity.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: OLS xwOBA ~ trip_number + velo_band(tercile), trip_number coef=+0.01218, p~0, n=179,383 PAs (trips<=4), 2025.
- **artifact link**: `domains/mlb/knowledge/validate_situational_state.py::tto_decay_net_of_velo`.
- **wiring**: in-game conditioning-feature candidate -- `trip_number` (this PA's nth time facing the same pitcher this game) as a live wOBA-against re-pricer, net of pitcher velo state.

### 21. Walk-economy baserunner inflation
- **claim**: run-expectancy lift per walk is state-dependent (bigger with runners on 2nd/3rd than bases empty).
- **status**: CONFIRMED
- **measured LOCAL magnitude**: runs-added-on-play after a walk, RISP (0.0650, n=4,139) vs bases empty (0.0000, n=8,079); effect +0.065, p=2.0e-62, n=12,218, 2025.
- **artifact link**: `domains/mlb/knowledge/validate_situational_state.py::walk_economy_baserunner_inflation`.

### 22. Big-inning generation (run clustering)
- **claim**: a leadoff baserunner disproportionately gates big (3+ run) innings.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: P(3+ runs this half-inning) | leadoff on-base 0.1219 (n=13,315) vs leadoff out 0.0260 (n=29,468); effect +0.096, p=7.0e-220, n=42,783, 2025.
- **artifact link**: `domains/mlb/knowledge/validate_situational_state.py::big_inning_leadoff_gating`.
- **wiring**: in-game conditioning-feature candidate -- leadoff-PA outcome as a live half-inning big-inning-probability re-pricer, usable the moment the leadoff PA resolves.

### 23. Sequencing and cluster luck
- **claim**: observed run totals diverge from context-neutral expectation in small samples and regress over a season.
- **status**: NOT_TESTABLE -- needs a full run-expectancy/linear-weights (RE24-style) model rebuilt from base-out state transitions; no such model exists locally and building one is a separate infra item, not a column check. A naive runs-per-game proxy would not isolate sequencing from talent, so was not substituted.
- **artifact link**: `domains/mlb/knowledge/validate_premise_blocked.py::sequencing_cluster_luck`.

### 24. Power/ISO run compression -- LOCAL NULL
- **claim**: high-ISO lineups have tighter strand-rate variance because HRs don't need sequencing.
- **status**: REJECTED (NULL_LOCAL) -- direction is even reversed (positive, not negative) though not significant at alpha=0.01.
- **measured LOCAL magnitude**: team ISO vs game-level runs-scored std (substitute proxy -- no LOB/strand field exists locally): r=+0.428, p=0.018, n=30 teams, 2025.
- **artifact link**: `domains/mlb/knowledge/validate_persistence_skill.py::iso_strand_variance_compression`.

### 25. Speed/baserunning advancement value
- **claim**: extra-base-taken rate on singles/doubles adds measurable run expectancy independent of power.
- **status**: NOT_TESTABLE -- `on_1b`/`on_2b`/`on_3b` are PRE-pitch occupant state only; there is no post-play base-state or explicit extra-bases-taken field. Inferring whether a runner from 1st reached 2nd vs 3rd on a single needs chaining consecutive PAs by runner identity (pinch-runner-safe), a bigger build than this check.
- **artifact link**: `domains/mlb/knowledge/validate_premise_blocked.py::speed_baserunning_advancement`.

### 26. Defensive-efficiency conversion -- LOCAL NULL
- **claim**: team defense suppresses BABIP below contact-quality expectation, stably across season halves.
- **status**: REJECTED (NULL_LOCAL).
- **measured LOCAL magnitude**: split-half pearson r, team residual-BABIP (actual - launch-condition-bin expected hit rate): r=0.2358, p=0.210, n=30 teams, 2025.
- **artifact link**: `domains/mlb/knowledge/validate_persistence_skill.py::defensive_efficiency_conversion`.

### 27. Pitch-count efficiency and starter durability
- **claim**: starters who throw fewer pitches/PA go deeper into starts.
- **status**: CONFIRMED (main correlation only; bullpen-vs-rotation ERA-gap sub-claim not tested this session)
- **measured LOCAL magnitude**: pearson r, starter-season avg pitches/PA vs avg innings-reached/start: r=-0.2544, p=2.2e-4, n=207 starters (>=8 starts), 2025.
- **artifact link**: `domains/mlb/knowledge/validate_persistence_skill.py::pitch_efficiency_durability`.

### 28. Leverage-index conversion
- **claim**: win-probability swing per event scales with game leverage (score margin x inning).
- **status**: NOT_TESTABLE-as-specified -- no true win-probability model exists locally; the only available run-swing proxy is confounded (blowout innings are mechanically higher-scoring-per-play than close innings), so it cannot isolate a leverage effect from that confound.
- **measured LOCAL magnitude**: run-swing proxy, late(inn>=7)+close(margin<=1) 0.0286 (n=79,417) vs early(inn<7)+blowout(margin>=5) 0.0349 (n=43,899); p=2.5e-6 but direction is confound-driven, not interpreted as a leverage verdict.
- **artifact link**: `domains/mlb/knowledge/validate_situational_state.py::leverage_index_conversion`.

### 29. High-leverage strand prevention
- **claim**: strikeout-heavy relievers strand RISP runners at a higher rate, especially late/close.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: pearson r, pitcher-season K-rate vs RISP strand-rate (inn>=7, |margin|<=2): r=0.1863, p=0.0068, n=210 pitchers (>=50 PA, >=15 RISP PA there), 2025.
- **artifact link**: `domains/mlb/knowledge/validate_situational_state.py::high_leverage_strand_prevention`.

### 30. Lineup-slot run value
- **claim**: batting-order slot carries its own run-value independent of the individual hitter.
- **status**: NOT_TESTABLE -- fresh column check on `savant_full__2025.parquet` (42 cols): no batting-order-slot column (0 hits for */order/,*/slot/,*/lineup/*); cannot be derived from `at_bat_number` alone (resets by half-inning, not by lineup turn).
- **artifact link**: `domains/mlb/knowledge/validate_premise_blocked.py::lineup_slot_run_value`.

### 31. Umpire zone-call consistency
- **claim**: individual plate umpires differ in, and repeat, their called-zone consistency.
- **status**: NOT_TESTABLE -- fresh column check on `savant_full__2025.parquet`: no umpire-identity column anywhere (0 hits for '*ump*').
- **artifact link**: `domains/mlb/knowledge/validate_premise_blocked.py::umpire_zone_call_consistency`.

### 32. Catcher game-calling (pitch sequencing) effect -- LOCAL NULL
- **claim**: catchers differ in how they sequence pitch types, and better sequencing suppresses contact quality.
- **status**: REJECTED (NULL_LOCAL) -- simplified to a split-half persistence check (raw xwOBA-allowed while catching, not pitcher/batter-adjusted) rather than a full 3-way fixed-effect regression; a cleaner FE design is a larger future build.
- **measured LOCAL magnitude**: split-half pearson r=0.168, p=0.178, n=66 catchers (>=100 PA/half), 2025.
- **artifact link**: `domains/mlb/knowledge/validate_persistence_skill.py::catcher_game_calling_persistence`.

### 33. Spin-rate deception (independent of velocity)
- **claim**: release spin rate predicts whiff rate on breaking pitches independent of velocity band.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: OLS whiff ~ release_spin_rate + release_speed (breaking pitches, swings only), spin coef=+4.33e-5, p=2.2e-16, n=100,280, 2025.
- **artifact link**: `domains/mlb/knowledge/validate_persistence_skill.py::spin_rate_deception`.
- **wiring**: in-game conditioning-feature candidate -- `release_spin_rate` as a live whiff-probability predictor on breaking pitches, additive to velocity band.

### 34. Launch-angle sweet-spot consistency
- **claim**: a batter's sweet-spot rate (launch angle 8-32 degrees) is a repeatable skill distinct from raw exit velocity.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: split-half pearson r=0.1942, p=5.0e-5, n=430 batters (>=20 BBE/half), 2025.
- **artifact link**: `domains/mlb/knowledge/validate_persistence_skill.py::sweet_spot_consistency`.
- **wiring**: in-game conditioning-feature candidate -- as-of sweet-spot-rate as a batter-quality attribute alongside the CONFIRMED contact-quality-persistence mechanism (#15).

### 35. Reliever back-to-back-day / 3-in-3-days appearance fatigue -- LOCAL NULL
- **claim**: a reliever pitching on back-to-back days (`is_b2b`), or on a 3rd appearance in the trailing 3 days (`appearances_last_3d`>=2), shows degraded same-outing run-prevention (higher xwOBA allowed) vs pitching on >=1 day rest. NOT the blocklisted velo-decline class -- outcome is contact quality allowed, never release_speed.
- **status**: REJECTED (NULL_LOCAL) for both flags, cross-season (2023/2024/2025 independent corpora). `is_b2b`: none of the 3 seasons clear alpha=0.01 (p=0.26/0.043/0.033), direction if anything mildly reversed. `appearances_last_3d>=2`: 2023/2024 NULL; 2025 clears alpha=0.01 but in the REVERSE direction (fatigued group allows LESS xwOBA, p=0.0067) -- per combine-logic discipline a reverse-direction significant season is never counted as support for a degradation hypothesis, so the combined verdict is NULL_LOCAL, not PROVISIONAL. Most plausible read: a selection confound (managers deploy their most-trusted/best relievers on heavy-usage stretches), not fatigue -- not tested further here.
- **measured LOCAL magnitude**: `is_b2b`: mean xwOBA allowed 0.288/0.284/0.283 (b2b) vs 0.293/0.293/0.292 (rested), n=15484/15605/15629, seasons 2023/2024/2025. `appearances_last_3d>=2`: 0.314/0.262/0.252 vs 0.296/0.297/0.296, n=9054/8897/8927.
- **artifact link**: `domains/mlb/knowledge/validate_reliever_b2b_fatigue.py::run` (corpus: `data/domains/mlb/bullpen_relief_chains.parquet` joined to `savant_full__2023/2024/2025.parquet`).

---

## Validated 2026-07-10 (game-level called-strike dispersion -- companion to #31, NO umpire identity)

Corpus: `savant_full__2025.parquet`, taken pitches (description in
{ball, called_strike}) in the Statcast shadow-zone corners {11,12,13,14}
(same EDGE_ZONES convention as #10's `validate_count_zone.py`), n>=20
qualifying pitches/game -> 2,406 games. GAME-LEVEL only -- no umpire
identity column exists locally (see #31, still NOT_TESTABLE for identity
claims); this tests whether an environmental factor (weather, a given day's
zone, scorer/PBP variance, etc.) makes per-game called-strike rate on
borderline pitches disperse MORE than pure sampling noise would predict.

### 39. Called-strike-rate dispersion exceeds binomial noise
- **claim**: the per-game called-strike rate on borderline (shadow-zone) taken pitches varies across games by more than binomial sampling noise alone would produce -- i.e. a real game-level environmental factor exists, independent of any umpire-identity claim.
- **causal story**: something about a given game (which umpire happens to be assigned, that day's specific zone-calling tendency, weather/lighting) shifts the whole game's borderline-call rate together, rather than each pitch being an independent draw from one fixed league-wide rate.
- **expected signature**: quasi-binomial dispersion ratio phi = chi2/df meaningfully above 1.0 (declared bar: phi>=1.2 AND p<0.01).
- **test spec**: per-game chi2 = sum((calls_g - n_g*p_bar)^2 / (n_g*p_bar*(1-p_bar))) ~ chi2(n_games-1) under the single-shared-rate null; phi=chi2/df is the effect size (p alone is not trusted given n_games in the thousands).
- **status**: CONFIRMED_LOCAL
- **measured LOCAL magnitude**: phi=1.389 (chi2=3339.4, df=2405, p=9.69e-34), pooled called-strike rate on taken borderline pitches=0.0485, n=2,406 games (2025).
- **artifact link**: `domains/mlb/knowledge/validate_called_strike_dispersion.py::called_strike_dispersion_exceeds_binomial_noise`.
- **wiring**: none yet -- this confirms a real per-game environmental factor EXISTS, not that it is attributable to umpire identity (that stays NOT_TESTABLE per #31) or usable as a live feature; a candidate for a future leak-free as-of per-park/weather join, not wired here.

### 40. Called-strike deviation vs game total runs -- LOCAL NULL
- **claim**: a game's called-strike-rate deviation on borderline pitches (the same per-game z-deviation that drives #39's dispersion) relates to that game's total runs scored.
- **status**: REJECTED (NULL_LOCAL) -- essentially zero relationship.
- **measured LOCAL magnitude**: pearson r=0.0084, p=0.68, n=2,406 games (2025).
- **artifact link**: `domains/mlb/knowledge/validate_called_strike_dispersion.py::called_strike_deviation_relates_to_total_runs`.

---

## Validated 2026-07-10 (contact-quality x park-factor interaction, C14)

### 41. Trailing contact-quality x park-factor interaction on batted-ball wOBA -- LOCAL NULL
- **claim**: a batter's as-of trailing contact quality (expanding mean launch_speed, strictly prior batted balls) interacts with the park run-environment to predict batted-ball outcome (estimated_woba_using_speedangle) BEYOND what the two additive base terms alone explain.
- **causal story**: a hitter with elite contact quality might convert park-friendly conditions into disproportionately more value than an average hitter would (a genuine multiplicative interaction), rather than each factor just adding its own independent share.
- **expected signature**: nonzero partial correlation of (trailing_contact x park_factor) against the wOBA outcome, after residualizing both against the base terms [trailing_contact, park_factor].
- **test spec**: split-half by date (2 corpora); per half, OLS-residualize outcome and the interaction term against [1, contact, park], Pearson-correlate the residuals; declared bar |r|>=0.02 AND p<0.01.
- **status**: REJECTED (NULL_LOCAL) both halves -- h1: r=0.0006, p=0.883, n=56,725; h2: r=0.0092, p=0.029 (misses alpha=0.01), n=56,529. No evidence of an interaction beyond the additive terms in this local corpus.
- **measured LOCAL magnitude**: see above (savant_full__2025, split-half by date).
- **artifact link**: `domains/mlb/knowledge/validate_contact_park_interaction.py::run`.

---

## Validated 2026-07-10 (staff-wide day-after fatigue chain, C18)

### 42. Team staff-wide high-pitch-count day precedes next-day run-prevention degradation -- PROVISIONAL
- **claim**: after a day where a team's whole pitching staff throws a lot of pitches (top-quartile team pitch count that day), the team allows more runs the very NEXT calendar day (true back-to-back, gap_days==1) than after a light-pitch-count day (bottom quartile).
- **premise check**: neither savant_full__*.parquet nor bullpen_relief_chains.parquet has a literal `pitch_count` column; savant_full is pitch-level (1 row = 1 pitch), so team daily pitch count is derived as a row-count grouped by pitching team (home team pitches on inning_topbot=="Top", away team on "Bot") and game_date -- a plain aggregation, not a fictitious-column workaround.
- **causal story**: a heavy team pitch-count day usually means extra innings or a bullpen-taxing blowout/comeback; the next day's available relievers are more fatigued/less optimally deployed, degrading run prevention.
- **expected signature**: mean next-day runs-allowed higher in the top-pitch-count-quartile group than the bottom-quartile group, same direction and significant in >=2 of 3 independent season corpora.
- **test spec**: `domains.mlb.knowledge.validate_staff_dayafter_chain.run` -- 2023/2024/2025 seasons tested independently (Welch t-test, top vs bottom quartile of prior-day team pitch count, min group n=20), bar |eff|>=0.1 AND p<0.01, combined per the reliever_b2b_fatigue convention (>=2 same-direction significant seasons -> CONFIRMED, 1 -> PROVISIONAL).
- **status**: PROVISIONAL (1 of 3 seasons significant support) -- 2023: NULL_LOCAL (eff=+0.079, p=0.580, n=2,087); 2024: CONFIRMED_LOCAL (eff=+0.392, p=0.0043, n=2,160); 2025: NULL_LOCAL (eff=+0.327, p=0.023, misses alpha=0.01, n=2,078). All three seasons point the same (support) direction but only one clears significance -- not a replicated finding, do not quote as confirmed.
- **measured LOCAL magnitude**: see above (savant_full__2023-2025, team-day pitch-count quartile split).
- **artifact link**: `domains/mlb/knowledge/validate_staff_dayafter_chain.py::run`; `validation_ledger.jsonl` rows `staff_dayafter_fatigue_chain` (x3) + `__combined`.

---

## Validated 2026-07-10 (research-wave 1 -- #43 CONFIRMED, #44/#45 NULL)

Fresh mechanism hypotheses from public sabermetrics literature, seeded
2026-07-10 (checked against every row above and against
`data/frontend/reject_ledger.jsonl`, 535 rows, 0 keyword hits for
`fielding_alignment`/`umpire`/`sequenc` on sport=mlb, before seeding).
Validated same day via `validate_research_wave1.py`: split-half-by-date
(2 corpora, `savant_full__2025.parquet`) supplies the >=2-corpora
replication the honesty rail requires even though each row's own test spec
only asked for one season; combine rule requires BOTH halves to
individually clear their declared p AND effect-size bar (not p alone --
see #45, where p<1e-4 both halves but the effect sits below the declared
bar and reverses the claimed direction, same discipline as #35's
reverse-direction rule).

### 43. Umpire called-strike zone size varies by count state ("compassionate umpire")
- **claim**: the called-strike rate on borderline (shadow-zone) pitches shrinks in pitcher's counts (e.g. 0-2) and expands in hitter's counts (e.g. 3-0) -- the umpire's effective zone size is count-conditional, not fixed.
- **premise check**: identity-free by construction, same as #31/#39/#40 -- no umpire-identity column exists locally and this row's own spec never asked for one (game/count-level only); no adaptation needed. Columns `zone`/`type`/`balls`/`strikes`/`description` all confirmed present on `savant_full__2025.parquet`.
- **causal story**: umpires subconsciously balance outcomes -- a called third strike at 0-2 ends the PA on a borderline pitch, a called ball at 3-0 walks the batter, so the psychological cost of a "wrong" call is asymmetric by count, biasing the zone.
- **expected signature**: lower called-strike rate on taken edge-zone pitches (same `zone in {11,12,13,14}` definition as row #10/#39) at pitcher's counts (0-2, 1-2) than at hitter's counts (3-0, 3-1), pooled across games -- distinct from #10 (pitcher TARGETING behavior) and #39/#40 (game-level dispersion, no count axis).
- **test spec**: `domains.mlb.knowledge.validate_research_wave1.compassionate_umpire_count_zone` -- Welch t-test on the called-strike indicator (proportion-test analog, same convention as the sibling count/dispersion validators), pitcher's-count vs hitter's-count on taken edge-zone pitches, split-half by date (2 corpora); declared bar |eff|>=0.05 AND p<0.01, both halves must clear it, same direction.
- **status**: CONFIRMED (both halves clear the bar, same direction)
- **measured LOCAL magnitude**: h1: called-strike rate 0.0137 (pitcher's-count, n=21,803) vs 0.0903 (hitter's-count, n=3,191), effect=-0.0765, p=1.0e-48. h2: 0.0121 vs 0.0927, effect=-0.0807, p=2.5e-51 (savant_full__2025, split-half by date).
- **artifact link**: `domains/mlb/knowledge/validate_research_wave1.py::compassionate_umpire_count_zone`; `validation_ledger.jsonl` rows `compassionate_umpire_count_zone__h1`/`__h2`/`__combined`.
- **source**: "The Strike Zone Expansion is Out of Control" (Hardball Times, quoting John Walsh's "Compassionate Umpire"), https://tht.fangraphs.com/the-strike-zone-expansion-is-out-of-control/ -- "the zone shrinks as the pitcher gains the edge... its size at 0-2 is only 64 percent as large as it is in a 3-0 count." Also "The Strike Zone Is Shrinking. Here's How." (FanGraphs), https://blogs.fangraphs.com/the-strike-zone-is-shrinking-heres-how/.

### 44. Shaded outfield alignment suppresses extra-base-hit rate on fly balls/line drives -- LOCAL NULL
- **claim**: a non-standard outfield alignment (shaded toward a batter's pull/spray tendency) lowers extra-base-hit rate on fly balls and line drives vs a standard alignment -- the outfield analog of the (post-ban-null) infield-shift test (#14), using a column the infield test did not touch.
- **premise check**: `of_fielding_alignment` locally has ONLY {Standard, Strategic, None} -- there is no "Shaded" value for the outfield column (unlike `if_fielding_alignment`, which has a distinct "Infield shade" bucket per #14's validator). Fixed inline: the tested non-standard bucket is `{Strategic}` only, the sole value that actually exists.
- **causal story**: repositioning outfielders toward a batter's known spray pattern should convert more deep fly balls/line drives into catchable outs or singles instead of doubles/triples, the same logic as infield shifts but for the outfield and unaffected by the 2023 infield-shift ban.
- **expected signature**: lower XBH-rate on FB/LD batted balls under `of_fielding_alignment` in {Strategic} vs {Standard} (bucket adjusted per premise check above).
- **test spec**: `domains.mlb.knowledge.validate_research_wave1.of_alignment_xbh_suppression` -- Welch t-test, XBH-indicator (double/triple, decided events only) by `of_fielding_alignment` bucket, restricted to `bb_type` in {fly_ball, line_drive}, split-half by date (2 corpora); declared bar |eff|>=0.03 AND p<0.01 (same design/bars family as #14).
- **status**: REJECTED (NULL_LOCAL) both halves -- effect sign is not even consistent across halves.
- **measured LOCAL magnitude**: h1: XBH rate 0.1035 (Strategic, n=1,150) vs 0.1155 (Standard, n=29,733), effect=-0.0120, p=0.191. h2: 0.1317 (n=995) vs 0.1171 (n=29,272), effect=+0.0146, p=0.181 (savant_full__2025, split-half by date). No evidence of outfield-shading suppression locally, consistent with #14's post-ban infield-shift null.
- **artifact link**: `domains/mlb/knowledge/validate_research_wave1.py::of_alignment_xbh_suppression`; `validation_ledger.jsonl` rows `of_alignment_xbh_suppression__h1`/`__h2`/`__combined`.
- **source**: Statcast's `of_fielding_alignment` field was introduced specifically to study outfield shifting; MLB's own Statcast glossary and multiple Statcast-era analytics writeups (e.g. FanGraphs/Baseball Savant shift-tracking coverage) treat outfield shading as the fly-ball/line-drive analog of the infield shift -- this row tests whether that analog shows up locally the way the infield version (post-ban) did not.

### 45. Same-pitch-type repeat (back-to-back within a PA) suppresses whiff rate vs a type change -- LOCAL NULL
- **claim**: when a pitcher throws the SAME pitch type as his immediately preceding pitch to that batter (within the same PA), the whiff rate on that pitch is lower than when he changes pitch type -- a batter pattern-recognition/anticipation effect, distinct from #32's catcher-level sequencing-STYLE persistence test (REJECTED NULL_LOCAL).
- **causal story**: once a batter has seen a pitch type in this PA, his timing/recognition for that same shape is primed; changing shape (fastball -> breaking or vice versa) disrupts that priming and should raise whiff probability more than repeating it.
- **expected signature**: lower whiff rate (swing description in {swinging_strike, swinging_strike_blocked}) on same-type-repeat pitches vs type-change pitches, among swings only.
- **test spec**: `domains.mlb.knowledge.validate_research_wave1.same_type_repeat_whiff` -- Welch t-test, whiff-indicator (swings only) by same-type-vs-prior-pitch (True/False, computed via `at_bat_number`+`pitch_number` ordering within `game_pk`), split-half by date (2 corpora); declared bar |eff|>=0.02 AND p<0.01, both halves must clear it, same direction.
- **status**: REJECTED (NULL_LOCAL) -- both halves are statistically significant (n in the hundred-thousands makes p tiny) but the effect is BELOW the declared 0.02 bar in both halves (0.0092, 0.0129) AND points the OPPOSITE direction of the claim: same-type-repeat pitches have a HIGHER whiff rate, not lower. Per the #35 reverse-direction/below-bar discipline, this never counts as support -- combined verdict is NULL_LOCAL.
- **measured LOCAL magnitude**: h1: whiff rate 0.2320 (same-type, n=50,218) vs 0.2228 (type-change, n=88,942), effect=+0.0092, p=9.6e-5. h2: 0.2395 (n=48,655) vs 0.2266 (n=89,099), effect=+0.0129, p=6.8e-8 (savant_full__2025, split-half by date).
- **artifact link**: `domains/mlb/knowledge/validate_research_wave1.py::same_type_repeat_whiff`; `validation_ledger.jsonl` rows `same_type_repeat_whiff__h1`/`__h2`/`__combined`.
- **note**: distinct from #32 (catcher game-calling persistence, split-half by catcher, REJECTED NULL_LOCAL) -- that tests whether CATCHERS differ and are internally consistent; this tests a universal batter-cognition effect independent of catcher identity, at the individual-pitch level.
- **source**: "Pitch Sequencing Analysis: A Deeper Look at Tunneling" (Magnus), https://www.seemagnus.com/blog-posts-test/pitch-sequencing-analysis-a-deeper-look-at-tunneling -- notes same-pitch-twice results are "counterintuitive" relative to naive sequencing theory, i.e. the direction is genuinely open, not assumed; flagged there as needing empirical (not folklore) testing -- the measured LOCAL direction here (higher whiff on repeat) is the counterintuitive one the source anticipated.

---
