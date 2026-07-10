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
- **status**: CONFIRMED (REPLICATED on savant_full__2024 -- second-corpus receipt below)
- **measured LOCAL magnitude**: phi=1.389 (chi2=3339.4, df=2405, p=9.69e-34), pooled called-strike rate on taken borderline pitches=0.0485, n=2,406 games (2025). Replication (2024): phi=1.392 (chi2=3379.1, df=2427, p=1.36e-34), rate=0.0634, n=2,428 games.
- **artifact link**: `domains/mlb/knowledge/validate_called_strike_dispersion.py::called_strike_dispersion_exceeds_binomial_noise`; replication `domains/mlb/knowledge/validate_replication_wave1.py::replicate_called_strike_dispersion`; `validation_ledger.jsonl` row `called_strike_dispersion_exceeds_binomial_noise__replication_2024`.
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
- **status**: CONFIRMED (REPLICATED on savant_full__2024 -- second-corpus receipt below)
- **measured LOCAL magnitude**: h1: called-strike rate 0.0137 (pitcher's-count, n=21,803) vs 0.0903 (hitter's-count, n=3,191), effect=-0.0765, p=1.0e-48. h2: 0.0121 vs 0.0927, effect=-0.0807, p=2.5e-51 (savant_full__2025, split-half by date). Replication (2024, same design/bar): h1 effect=-0.0992, p=9.9e-64; h2 effect=-0.1026, p=1.1e-63, n=50,058 -- both halves clear the same |eff|>=0.05, p<0.01 bar, same direction.
- **artifact link**: `domains/mlb/knowledge/validate_research_wave1.py::compassionate_umpire_count_zone`; replication `domains/mlb/knowledge/validate_replication_wave1.py::replicate_compassionate_umpire`; `validation_ledger.jsonl` rows `compassionate_umpire_count_zone__h1`/`__h2`/`__combined` (2025) and `compassionate_umpire_count_zone__replication_2024` (2024).
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

## Replicated 2026-07-10 (second-corpus wave -- #39 and #43 both REPLICATED on savant_full__2024)

Cross-season replication of the 2 strongest CONFIRMED_LOCALs above, on the
independently-available `savant_full__2024.parquet` corpus (verified on disk,
2,428 games, 711,455 pitches). Both were ported with the ORIGINAL validator
functions imported and called unchanged (same zone set, same alpha/effect
bars, same split-half design where the original used one) -- no bar was
loosened for replication. Both REPLICATED; see #39 and #43 above for the
updated combined receipts.

- **called_strike_dispersion_exceeds_binomial_noise**: REPLICATED. phi=1.392
  (2024) vs phi=1.389 (2025) -- near-identical dispersion ratio, same bar
  (phi>=1.2 AND p<0.01) cleared on an independent season.
- **compassionate_umpire_count_zone**: REPLICATED. Both 2024 halves clear the
  same |eff|>=0.05, p<0.01 bar, same direction (pitcher's-count effective
  zone smaller than hitter's-count), effect magnitude actually larger on
  2024 (-0.099/-0.103) than on 2025 (-0.077/-0.081).
- **artifact link**: `domains/mlb/knowledge/validate_replication_wave1.py`;
  `validation_ledger.jsonl` rows `called_strike_dispersion_exceeds_binomial_noise__replication_2024`,
  `compassionate_umpire_count_zone__replication_2024`.

---

## Seeded 2026-07-10 (research-wave 2 -- literature-sourced, UNTESTED, round-2 pool feedstock)

Fresh mechanism hypotheses from different literature areas than the
round-1 research wave (#43-45 above: compassionate umpire, outfield
alignment, same-pitch-type repeat). Checked against every row above and
against `data/frontend/reject_ledger.jsonl` (0 keyword hits for
`framing.*decline`/`tto.*platoon`/`platoon.*persist`/`platoon_delta` on
sport=mlb) before seeding. No validator built this lane.

### 46. Catcher framing multi-season trend (decline-curve proxy, no local age column)
- **claim**: an individual catcher's borderline-called-strike-rate ("framing" skill) trends downward across 3 consecutive seasons in our local window (2023->2024->2025), for catchers who appear in all 3 seasons.
- **premise check**: no birth_date/age/debut-year column exists anywhere locally for batters/catchers -- confirmed this session (`pitchers.parquet` has no age field: `['event_id','date','season','home_team','away_team','home_sp_name','away_sp_name','home_sp_present','away_sp_present','home_innings','away_innings']`; no bio parquet found under `data/domains/mlb/`). This row is therefore a WITHIN-CATCHER season-in-window trend proxy for a true age-anchored aging curve, not the aging curve itself -- an honest scope-reduction, same discipline as #38's team-day pitch-count derivation.
- **causal story**: cited literature finds framing peaks ~age 25 and declines gently from the early 30s onward; a catcher already past his peak within our 2023-2025 window should show a negative same-catcher trend across the 3 seasons.
- **expected signature**: negative within-catcher slope of borderline-called-strike-rate across season-index (1=2023, 2=2024, 3=2025).
- **test spec**: `domains.mlb.knowledge.validate_research_wave2.catcher_framing_multiseason_trend` (not yet built) -- per-catcher (`fielder_2`, confirmed present on all 3 files) borderline called-strike rate, same shadow-zone-corner methodology already used by `data/cache/intel_claims/mlb_framing_claims.jsonl` (`zone in {11,12,13,14}`, `description in {called_strike, ball}`), computed independently on `data/cache/statcast/savant_full__2023.parquet` / `__2024.parquet` / `__2025.parquet` (all 3 confirmed present locally), min n>=500 borderline takes/season/catcher (same floor as the existing framing_claims rankings), catchers present in all 3 seasons only; paired one-sample t-test of (season3_rate - season1_rate) against 0; declared bar |eff|>=0.01 AND p<0.01.
- **status**: REJECTED (NULL_LOCAL) -- confound caught: the RAW (non-league-adjusted) per-catcher delta alone was CONFIRMED_LOCAL (eff=-0.01299, p=9.1e-14, n=51), but the league-wide edge-zone called-strike rate moved by almost the identical amount over the same window (2023=0.0607 -> 2025=0.0485, delta=-0.0121) -- almost certainly a zone-definition/rule/measurement shift, not catcher-specific aging. League-demeaning each catcher's rate before the paired test (net of that season's league-wide rate) collapses the effect to null.
- **measured LOCAL magnitude**: league-demeaned paired one-sample t-test, season3(2025)-season1(2023) delta: eff=-0.00086, p=0.505, n=51 catchers (>=500 borderline takes/season, present all 3 seasons, 2023/2024/2025).
- **artifact link**: `domains/mlb/knowledge/validate_research_wave2.py::catcher_framing_multiseason_trend`; ledger row `catcher_framing_multiseason_trend` in `domains/mlb/knowledge/validation_ledger.jsonl` (run_ts 2026-07-10T09:43:14Z is the sole surviving row -- the final league-adjusted NULL_LOCAL verdict). An earlier same-session run_ts 09:41:38Z produced the superseded raw/confounded CONFIRMED_LOCAL; that row was removed from the ledger rather than kept live, because `effect_graph.py` emits one un-deduped edge per ledger row and a live CONFIRMED_LOCAL row for a mechanism whose honest verdict is NULL_LOCAL would pollute the effect graph with a false edge (the same class of bug 78d503ee fixed). The full raw-vs-adjusted confound story is preserved verbatim in this row's note and above in this entry -- no information lost. Existing receipt for the base metric: `data/cache/intel_claims/mlb_framing_claims.jsonl` (2023/2024 per-catcher rankings, `catcher_id`-keyed, n>=500 floor already applied there).
- **source**: "Catcher Framing: Does Size Matter, And Is Age Just a Number?" (Hardball Times), https://tht.fangraphs.com/catcher-framing-does-size-matter-and-is-age-just-a-number/ and "Catcher Aging Curves in the Mainstream" (FanGraphs Instagraphs), https://blogs.fangraphs.com/instagraphs/catcher-aging-curves-in-the-mainstream/ -- both establish framing peaks ~age 25 then declines gently from the early 30s, the literature basis for testing a within-window decline trend even without a direct local age column.

### 47. TTO penalty concentrated in platoon-disadvantage (same-handed) matchups
- **claim**: the times-through-the-order wOBA-against penalty (CONFIRMED net of velo in #20) is STEEPER in platoon-disadvantage (same-handed batter/pitcher) matchups than opposite-handed ones -- a genuinely different interacting variable (handedness) than the CLOSED velo-band x TTO class (#4/#5, globally blocklisted).
- **causal story**: batter familiarity/pattern-recognition (the TTO mechanism) should compound with the platoon angle-reading disadvantage (#1's CONFIRMED mechanism) -- a same-handed batter facing a pitcher for the 3rd time carries both disadvantages at once, so the TTO slope should be steeper for same-handed than opposite-handed matchups.
- **expected signature**: positive `trip_number x same_hand` interaction term on `estimated_woba_using_speedangle` (same-handed matchups show a STEEPER TTO increase than opposite-handed).
- **test spec**: `domains.mlb.knowledge.validate_research_wave2.tto_x_platoon_interaction` (not yet built) -- OLS `xwOBA ~ trip_number + same_hand + trip_number:same_hand`, PA-level, `trip_number = groupby(game_pk,pitcher,batter).cumcount()+1` capped at <=4 (reuses #20's exact derivation in `validate_situational_state.py`), `same_hand = (stand==p_throws)`, `data/cache/statcast/savant_full__2025.parquet` (`stand`/`p_throws`/`batter`/`pitcher`/`game_pk`/`at_bat_number`/`estimated_woba_using_speedangle` all confirmed present this session), split-half by date for the 2-corpora replication bar; declared bar |interaction coef|>=0.005 AND p<0.01, both halves.
- **status**: REJECTED (NULL_LOCAL) -- interaction term did not clear the declared bar in either half (both must, per the row's own spec).
- **measured LOCAL magnitude**: OLS xwOBA ~ trip_number + same_hand + trip_number:same_hand, PA-level (trips<=4), split-half by date: h1 interaction coef=-0.00076, p=0.826, n=90,807; h2 interaction coef=-0.00626, p=0.081, n=88,586 (2025).
- **artifact link**: `domains/mlb/knowledge/validate_research_wave2.py::tto_x_platoon_interaction`; ledger rows `tto_x_platoon_interaction__h1`/`__h2`/`__combined` in `domains/mlb/knowledge/validation_ledger.jsonl` (run_ts 2026-07-10T09:41:38Z).
- **note**: distinct from CLOSED #4/#5 (velo-band x TTO / velo-decline standalone, `GLOBAL_BLOCKLIST_ATTRS = {"velo_decline_in_game"}`) -- this interacts TTO with HANDEDNESS, not velocity, so it is not a re-attempt of that closed class; also distinct from #1 (platoon x pitch-type, no TTO term) and #20 (TTO net of velo, no platoon term).
- **source**: "A Bayesian analysis of the time through the order penalty in baseball" (Brill, Wyner et al.), https://arxiv.org/abs/2210.06724 -- finds handedness-match carries a same-order-of-magnitude effect size as the batter sequence number itself (roughly 18 fewer mean expected wOBA points on a handedness match, comparable to the raw TTO effect), the direct motivation for testing whether the two interact rather than just add independently.

### 48. Platoon-split persistence (batter's own platoon delta stable across season halves)
- **claim**: an individual batter's platoon split (on-base rate vs LHP minus vs RHP) is a repeatable, split-half-persistent trait -- the same persistence-design family already CONFIRMED for contact-quality (#15) and sweet-spot-rate (#34) in this ledger, applied to platoon split for the first time.
- **premise check**: `data/domains/mlb/platoon_split_index.parquet` already carries a `platoon_delta` field but only for one combined `season="2022_2023"` window (confirmed this session) -- not split-half testable as-is; this row instead re-derives the same on-base-rate-vs-hand metric directly from `savant_full__2025.parquet` (a single season, split by date) to get the needed two independent windows.
- **causal story**: cited literature treats platoon skill as the MOST stable split in baseball, driven by physical mechanics (pitch angle/break-plane) rather than random variance -- if that holds locally, a batter's first-half-of-season platoon_delta should correlate with his own second-half platoon_delta.
- **expected signature**: positive split-half Pearson r of per-batter platoon_delta (on-base rate vs `p_throws=='L'` minus vs `p_throws=='R'`), first-half-of-season dates vs second half.
- **test spec**: `domains.mlb.knowledge.validate_research_wave2.platoon_split_persistence` (not yet built) -- per-batter on-base-rate vs `p_throws` (events-derived on-base indicator, same on-base-outcome definition style already used by #21's walk-economy row), split-half by date, `data/cache/statcast/savant_full__2025.parquet`, batters with >=20 PA vs each hand per half (mirrors #15/#34's floor style); declared bar |r|>=0.15 AND p<0.01.
- **status**: REJECTED (NULL_LOCAL) -- split-half correlation did not clear the declared bar.
- **measured LOCAL magnitude**: split-half pearson r, per-batter platoon_delta (on-base-rate vs L minus vs R): r=0.0604, p=0.296, n=301 batters (>=20 PA/hand/half, 2025).
- **artifact link**: `domains/mlb/knowledge/validate_research_wave2.py::platoon_split_persistence`; ledger row `platoon_split_persistence` in `domains/mlb/knowledge/validation_ledger.jsonl` (run_ts 2026-07-10T09:41:38Z).
- **source**: "Schrodinger's Bat: The Irreducible Essence of Platoon Splits" (Baseball Prospectus), https://www.baseballprospectus.com/news/article/4970/schrodingers-bat-the-irreducible-essence-of-platoon-splits/ and "Estimating Hitter Platoon Skill" (FanGraphs), https://blogs.fangraphs.com/estimating-hitter-platoon-skill/ -- both describe platoon splits as sabermetrics' most stable/repeatable split category, the literature basis this row tests directly against the local corpus rather than assuming.

---

## Seeded 2026-07-10 (research-wave 3 -- literature-sourced, UNTESTED, round-3 pool feedstock)

Fresh mechanism hypotheses targeting the sim's worst-bucket family (pitch-engine
v3-candidate's named inn7|m2 composition-conditioned bucket, commit 6326d0d1 --
"the real ceiling is a per-game team-bullpen-tier covariate... absent from the
local corpus"; this lane does not build that covariate, only seeds middle-inning
bullpen-transition literature hypotheses adjacent to it). Checked against every
row above (especially #8/#18 NOT_TESTABLE bullpen-leverage-chaining, CLOSED
`GLOBAL_BLOCKLIST_ATTRS={"velo_decline_in_game"}`) and against
`data/frontend/reject_ledger.jsonl` (535 rows, 0 keyword hits for `opener`/
`bullpen.?game`/`pinch.?hit`) before seeding. No validator built this lane.

### 49. Bullpen-day/opener-style games show altered run-scoring structure vs traditional-starter games
- **claim**: games where no single pitcher on a team carries a traditional starter's workload (a proxy for the opener/bullpen-day strategy) show a different scoring distribution/win-rate pattern than standard-starter games -- distinct from #8/#18 (bullpen LEVERAGE chaining, CLOSED not-testable on a missing role/leverage-index ingredient) since this uses only a workload-shape proxy, no leverage ingredient.
- **premise check**: `pitchers.parquet`'s `home_innings`/`away_innings` fields are confirmed this session to be per-inning LINESCORE strings (e.g. `'0,1,0,0,1,3,3,1,x'`), NOT starter-innings-pitched as the field names suggest -- ruled out as this row's ingredient. `player_gamelogs.parquet` (confirmed columns incl. `game_pk`/`team`/`date`/`is_pitcher`/`inningsPitched`, 321,012 rows) is the real ingredient: bullpen-day proxy = a team-game's MAX single-pitcher `inningsPitched` among `is_pitcher==True` rows <=4 (confirmed this session: 18.7% of 21,878 team-games clear this bar). Confound flagged explicitly: this proxy also catches ordinary early-hook starts from poor performance/injury, not only deliberate opener/bullpen-day strategy -- an honest scope note, same discipline as #36's (soccer) confound framing.
- **causal story**: cited opener/bullpen-day literature (Rays-pioneered) argues spreading innings across max-effort relievers suppresses early scoring but bullpen fatigue by innings 6-9 can push full-game totals back up -- a structurally different run-distribution shape than a traditional single-starter game, not just a different mean.
- **expected signature**: bullpen-day team-games show a different early-inning-vs-late-inning scoring split and/or a different win-rate than matched traditional-starter games.
- **test spec**: `domains.mlb.knowledge.validate_research_wave3.bullpen_day_scoring_structure` -- team-game bullpen-day flag (above) joined to `games.parquet` via `date`+`team` (confirmed `home_team`/`away_team`/`home_runs`/`away_runs`/`target_home_win`; ~1.4% doubleheader date+team collision rate confirmed this session, flagged as an explicit exclusion/dedup step, not silently ignored); Welch t-test team runs-scored, bullpen-day vs traditional, plus win-rate comparison; declared bar |eff|>=0.15 runs AND p<0.01 for the scoring leg, split-half by date.
- **premise-check correction (validation session)**: `games.parquet` covers 2010-04-04..2021-11-02 while `player_gamelogs.parquet` (the bullpen-day-flag source) covers 2022-04-07..2026-07-02 -- ZERO date overlap, confirmed this session. `games_current.parquet` (same 9 columns, 2022-04-07..2026-06-16) is what actually overlaps and was substituted for the join. Team-code mismatch also found and fixed: `player_gamelogs` uses `{SF,TB,SD,KC,WSH,CHC,AZ,ATH}`, `games_current` uses `{SFO,TAM,SDG,KAN,WAS,CUB,ARI,OAK}` for the same 7 franchises -- an explicit `TEAM_MAP` translates; `ATH` (2025+ post-move Athletics code) has no `games_current` counterpart and is excluded by the inner merge (small honest coverage gap). `AL`/`NL` all-star rows dropped (not real team-games).
- **status**: REJECTED (NULL_LOCAL) both halves -- the scoring-shape leg does not clear the declared bar.
- **measured LOCAL magnitude**: Welch t-test own-runs, bullpen-day vs traditional, split-half by date: h1 eff=+0.0125 p=0.873 n=10,280 (1,981 bullpen-day/8,299 traditional); h2 eff=+0.0819 p=0.320 n=10,228 (1,809/8,419) (2025+2026 partial). Win-rate gap is large and DESCRIPTIVE ONLY, not gated (no bar was declared for it): bullpen-day win-rate ~0.31 vs traditional ~0.54 both halves -- plausible selection confound (bullpen days correlate with short-staffed/already-losing situations), not causally isolated here.
- **artifact link**: `domains/mlb/knowledge/validate_research_wave3.py::bullpen_day_scoring_structure`; ledger rows `bullpen_day_scoring_structure__h1`/`__h2`/`__combined` in `domains/mlb/knowledge/validation_ledger.jsonl` (run_ts 2026-07-10T11:04:38Z).
- **source**: "The Specialized Bullpen: History, Analysis, and Strategic Models for Success" (SABR), https://sabr.org/journal/article/the-specialized-bullpen-history-analysis-and-strategic-models-for-success/ and "Opener (baseball)" (Wikipedia), https://en.wikipedia.org/wiki/Opener_(baseball) -- both document the opener/bullpen-day strategy's run-suppression-then-fatigue structural signature, the basis for testing scoring SHAPE (not just mean) locally.

### 50. Mid-inning pitching change interrupts the batting team's scoring rate (raw pre/post gap, same design family as the CONFIRMED NBA #47 timeout-interrupt row)
- **claim**: a pitching change made MID-INNING (not at the inning break) is followed by a lower batting-team scoring rate in the PAs immediately after than in the PAs immediately before -- the "fireman" concept tested as a raw descriptive gap, explicitly not a causal claim (same scope discipline as NBA #47).
- **causal story**: a fresh reliever disrupts the batting team's rhythm/timing against the outgoing pitcher, similar in structure to a defensive timeout interrupting an opponent's scoring run -- cited Sloan Sports bullpen-strategy research treats mid-inning relief exactly as a rally-suppression tool.
- **expected signature**: batting-team runs-per-PA in a window of PAs after a mid-inning pitcher-ID change is lower than in the window before.
- **test spec**: `domains.mlb.knowledge.validate_research_wave3.mid_inning_pitching_change_interrupt` -- `savant_full__2025.parquet` (confirmed columns `game_pk`/`inning`/`inning_topbot`/`pitcher`/`at_bat_number`/`outs_when_up`/`post_home_score`/`post_away_score`/`home_score`/`away_score`), mid-inning change = consecutive at-bats within the same `game_pk`+`inning`+`inning_topbot` where `pitcher` id changes AND `outs_when_up>0` (excludes ordinary between-innings substitutions); paired comparison of batting-team score delta (`post_*_score - *_score`) summed over the 3 PAs before vs 3 PAs after (capped at the inning boundary, min 1-PA floor), paired t-test; declared bar |eff|>=0.02 runs/PA AND p<0.01, split-half by date.
- **status**: CONFIRMED_LOCAL, both halves, same direction.
- **measured LOCAL magnitude**: paired t-test, batting-team runs/PA after vs before a mid-inning pitcher-ID change, split-half by date: h1 eff=-0.0609 p=1.8e-08 n=2,074 events; h2 eff=-0.0759 p=1.6e-12 n=2,079 events (2025). SELECTION CONFOUND flagged explicitly, same non-causal scope as this row's own claim: relievers are typically summoned DURING an in-progress rally, so an elevated before-window reverting after is also the mechanical/regression-to-mean signature of WHEN changes get called, not proof of a reliever "interrupt" causal effect -- the row's claim was scoped as a raw descriptive gap from the start (not causal), so this verdict tests exactly what was declared, with the confound named rather than hidden.
- **artifact link**: `domains/mlb/knowledge/validate_research_wave3.py::mid_inning_pitching_change_interrupt`; ledger rows `mid_inning_pitching_change_interrupt__h1`/`__h2`/`__combined` in `domains/mlb/knowledge/validation_ledger.jsonl` (run_ts 2026-07-10T11:04:38Z).
- **wiring**: none -- a raw descriptive (non-causal) pattern, not isolated from the selection confound above; not a candidate for a live feature as-is.
- **source**: "Bullpen Strategies for Major League Baseball" (Sloan Sports Conference), https://www.sloansportsconference.com/research-papers/bullpen-strategies-for-major-league-baseball -- treats mid-inning relief-pitcher deployment as a deliberate rally-suppression decision; "Fireman" (BR Bullpen), https://www.baseball-reference.com/bullpen/Fireman -- the classical baseball-strategy term for entering specifically to "put out the fire" of an in-progress rally, the direct conceptual basis for this row's before/after design (same design family as the CONFIRMED NBA #47 timeout row in this ledger).

### 51. Pinch-hitter substitutions skew toward securing the platoon (opposite-hand) advantage against the current pitcher
- **claim**: when a team substitutes a new batter into a lineup slot mid-game, that substitute is more likely to be opposite-handed to the pitcher he actually faces than the local baseline same-hand rate across all PAs -- a deliberate managerial platoon-optimization pattern, distinct from #1 (platoon x pitch-type CONFIRMED, no substitution-timing angle) and #47 (TTO x platoon interaction, REJECTED, no substitution angle).
- **premise check**: `player_gamelogs.parquet`'s `batting_order` field (confirmed present, 1-9) combined with `game_pk`+`team` surfaces lineup-slot substitutions directly -- confirmed this session with a real example (a shared SS slot #9, `Taylor Walls` then `Oliver Dunn`, same `game_pk`). No explicit pinch-hit flag exists locally, so the substitute is identified via a proxy (the later-appearing, fewer-plate-appearance player in a shared slot) -- an honest heuristic that also catches pinch-runners/defensive subs, not only true pinch hitters, stated explicitly as a scope limitation. `player_gamelogs.player_id` and `savant_full.batter` are confirmed this session to share the same MLBAM id space (100% overlap of 2025 savant batter ids within player_gamelogs ids), enabling the join to `stand`/`p_throws` for the substitute's actual PA outcome.
- **causal story**: cited reporting finds managers overwhelmingly (ESPN's cited example: 94% of 5th/6th-inning pinch-hitters) insert a substitute specifically to face opposite-handed pitching once a new pitcher enters -- a real, actionable in-game platoon-optimization tactic.
- **expected signature**: substitute batters' same-hand rate (`stand==p_throws` at their first PA after entering) is LOWER than the season-wide same-hand PA rate.
- **test spec**: `domains.mlb.knowledge.validate_research_wave3.pinch_sub_platoon_targeting` -- per team-game-slot, identify the substitute (lower-PA player sharing a `batting_order` slot, `player_gamelogs.parquet`), join first PA to `savant_full__2025.parquet` via `batter`==`player_id` for `stand`/`p_throws`; one-sample proportion test of substitute same-hand rate vs the season-wide baseline same-hand PA rate; declared bar |eff|>=0.05 (rate points) AND p<0.01.
- **validation-session addition**: the row's own spec is a single global one-sample test (no split declared); this lane's binding >=2-corpora-for-affirmatives rule requires >=2 independent groups before any CONFIRMED verdict, so split-half by date (same discipline as #48/#50) was applied before testing, both halves required, same direction.
- **status**: CONFIRMED_LOCAL, both halves, same direction.
- **measured LOCAL magnitude**: one-sample proportion test, substitute same-hand rate vs same-half savant-PA baseline same-hand rate, split-half by date: h1 eff=-0.1744 p=3.4e-60 n=2,098 substitutes (rate=0.284 vs baseline=0.459); h2 eff=-0.1844 p=2.2e-71 n=2,213 substitutes (rate=0.266 vs baseline=0.450) (2025). Substitutes are ~17-18 points MORE likely to be opposite-handed to the pitcher they face than the baseline PA population -- direction matches the claim. Scope caveat carried from the row's own premise check: the substitute-identification proxy (lower-atBats player sharing a lineup slot) also catches pinch-runners/defensive subs, not only true pinch hitters.
- **artifact link**: `domains/mlb/knowledge/validate_research_wave3.py::pinch_sub_platoon_targeting`; ledger rows `pinch_sub_platoon_targeting__h1`/`__h2`/`__combined` in `domains/mlb/knowledge/validation_ledger.jsonl` (run_ts 2026-07-10T11:04:38Z).
- **wiring**: none yet -- confirms a real in-game managerial platoon-targeting pattern exists locally; a candidate for a future leak-free as-of substitution-event feature, not wired here.
- **source**: "What makes a good pinch hitter in 2026? One manager might have revealed the secret" (ESPN), https://www.espn.com/mlb/story/_/id/48475945/mlb-2026-pinch-hitting-hitters-swings-tyler-wade-texas-rangers-skip-schumaker -- reports 61/65 (94%) of 5th/6th-inning pinch-hitters in the cited sample entered specifically to face opposite-handed pitching; "The Three Batter Minimum's Effect on Late-Game Strategy" (FanGraphs), https://blogs.fangraphs.com/the-three-batter-minimums-effect-on-late-game-strategy/ -- context on how the 2020 three-batter-minimum rule reshaped this exact platoon-matching tactic.

---

## Seeded 2026-07-10 (research-wave 4 -- literature-sourced, UNTESTED, round-4 pool feedstock)

Fresh mechanism hypothesis on baserunning aggression vs outfield-arm
deterrence, using a corpus (`espn_boxscores.parquet`) distinct from the one
that closed #19 (savant_full, NOT_TESTABLE -- zero SB/CS events in that
file's `events` column). Checked against every row above and against
`data/frontend/reject_ledger.jsonl` (535 rows, 0 keyword hits for
`baserun`/`outfield.*arm`/`arm.*deterr`) before seeding. Full premise check:
`docs/research/research_seed_wave4_2026-07-10.md`. No validator built this
lane.

### 52. Batting-team baserunning aggression is suppressed against opponents with a strong outfield-arm reputation (unblocks the SB/CS ingredient gap that closed #19 on a different corpus)
- **claim**: a team's stolen-base-attempt rate (SB+CS) in a given game is lower when facing a fielding team whose season-long outfield-assist rate signals a strong/accurate-armed outfield -- distinct from and NOT a re-attempt of #19 (NOT_TESTABLE specifically on `savant_full__2025.parquet`, which has zero SB/CS `events` values at all; this row uses `espn_boxscores.parquet`, a different local corpus that DOES carry the needed columns).
- **premise check**: `data/domains/mlb/espn_boxscores.parquet` confirmed this session (3,880 rows, dates from 2025-03-27) to carry `home_bat_stolenBases`/`home_bat_caughtStealing`/`away_bat_stolenBases`/`away_bat_caughtStealing`/`home_fld_outfieldAssists`/`away_fld_outfieldAssists`, 3,874 non-null rows on the 6-column subset; combined SB+CS per team-game has real variance (mean=0.891, std=1.101, max=10), not a degenerate/sparse column.
- **causal story (scoped honestly)**: `home_fld_outfieldAssists` is a general outfield-arm/defensive-reputation proxy, not a steal-specific metric -- a stolen-base attempt is fundamentally a catcher-vs-runner event, not an outfielder-vs-runner one. This row's claim is therefore scoped to a broader "defensive-reputation deterrence" story: a defense publicly known for cutting down runners (via strong outfield arms) plausibly makes baserunners and third-base coaches more conservative across ALL advancement decisions, including stolen-base attempts, not a narrow mechanical claim that outfield arms specifically stop steals.
- **expected signature**: negative Pearson r between a batting team's SB+CS attempts in a game and the fielding team's season-long (leave-one-out) `outfieldAssists` rate.
- **test spec**: `domains.mlb.knowledge.validate_research_wave4.baserunning_aggression_vs_outfield_arm_deterrence` -- unpivot `espn_boxscores.parquet` to team-perspective rows (batting team's `bat_stolenBases`+`bat_caughtStealing` vs the OPPONENT's `fld_outfieldAssists`), fielding team's expected arm-reputation computed as its own season-long mean `outfieldAssists`/game excluding the target game (leave-one-out, avoids circularity); Pearson r, SB+CS attempts vs opponent's leave-one-out outfieldAssists rate; declared bar |r|>=0.05 AND p<0.01 (large-n floor given ~7,748 team-perspective rows), split-half by date, both halves required same sign.
- **status**: NULL_LOCAL
- **measured LOCAL magnitude**: n=7,746 team-perspective rows (h1 n=3,886 r=0.0177 p=0.271; h2 n=3,860 r=-0.0136 p=0.400) -- neither half clears the declared |r|>=0.05 AND p<0.01 bar, and the two halves flip sign; batting-team baserunning aggression shows no measurable relationship to the opponent's leave-one-out outfield-arm reputation in this corpus. Honest NULL, not evidence of the reverse.
- **artifact link**: `domains/mlb/knowledge/validate_research_wave4.py::baserunning_aggression_vs_outfield_arm_deterrence`, ledger rows in `validation_ledger.jsonl` (hypothesis `baserunning_aggression_vs_outfield_arm_deterrence__{h1,h2,combined}`).
- **source**: "Stolen Base Matchup Tool" (EV Analytics), https://evanalytics.com/mlb/research/sb-matchup-tool -- documents that modern SB-decision models already condition success probability on defensive-side inputs including outfielder throwing arm alongside catcher/pitcher factors, the literature basis for treating outfield-arm reputation as a plausible baserunning-aggression deterrent worth testing directly against the local box-score corpus.

---

## Seeded 2026-07-10 (research-wave 5 -- literature-sourced, UNTESTED, round-5 pool feedstock)

Two fresh mechanism hypotheses: (a) game-calling variance scoped IDENTITY-
FREE, mirroring the CONFIRMED+REPLICATED called-strike-dispersion design
(#39/#40) but on a whiff outcome instead of a call outcome -- distinct from
#32 (catcher-identity persistence, REJECTED NULL_LOCAL); (b) automatic-
runner ("zombie runner") extra-innings scoring environment, rule-era aware.
Checked against every row above and `data/frontend/reject_ledger.jsonl`
(535 rows, 0 keyword hits for `zombie`/`ghost`/`automatic_runner`/
`catcher` beyond the already-closed #32/#46 rows) before seeding. No
validator built this lane.

### 53. Per-game 2-strike putaway-whiff rate disperses beyond binomial noise (identity-free, mirrors #39)
- **claim**: the per-game swinging-strike rate on 2-strike ("putaway") pitches varies across games by more than binomial sampling noise alone would produce, independent of any catcher-identity attribution -- distinct from #32 (catcher-level sequencing persistence BY IDENTITY, REJECTED NULL_LOCAL); this row applies #39's identity-free game-level dispersion design to a different outcome column (whiff, not called-strike).
- **premise check**: `data/cache/statcast/savant_full__2025.parquet` confirmed this session -- columns `game_pk`/`strikes`/`description` present, 705,391 pitch rows / 2,406 games; 2-strike pitches n=210,696 (matches exactly). **Correction**: the row's `swinging_strike` (73,372) / `swinging_strike_blocked` (3,954) counts are the whole-season totals, not the 2-strike subset -- within `strikes==2` the true counts are swinging_strike=25,258 / swinging_strike_blocked=2,775 (28,033 combined whiffs); does not change testability, only the docstring number (floor is n>=20 2-strike PITCHES/game, mean ~88/game).
- **causal story**: cited sequencing-analytics coverage (Driveline, "Count-dependent Pitch Profile Manipulation") documents pitchers/catchers deliberately shift pitch-mix intensity specifically in 2-strike putaway counts to maximize whiffs; if that game-calling execution quality varies meaningfully by game (weather, that day's battery pairing, scouting-report freshness) beyond pure chance, the per-game putaway-whiff rate should disperse beyond binomial noise, same identity-free logic as #39.
- **expected signature**: quasi-binomial dispersion ratio phi=chi2/df above 1.0 (declared bar phi>=1.2 AND p<0.01, same bar as #39 since this is a direct outcome-column swap of that design).
- **test spec**: `domains.mlb.knowledge.validate_research_wave5.putaway_whiff_dispersion_exceeds_binomial_noise` -- per game_pk, subset to `strikes==2` pitches; whiff = `description` in {swinging_strike, swinging_strike_blocked} vs all other 2-strike outcomes; n>=20 qualifying 2-strike pitches/game floor (same floor as #39); phi=chi2/df under the single-shared-rate null; `savant_full__2025.parquet` vs `savant_full__2024.parquet` as the two-corpora replication legs, same design as #39's own replication.
- **status**: CONFIRMED_LOCAL (REPLICATED on savant_full__2024) -- both corpora independently clear phi>=1.2 AND p<0.01, same one-directional overdispersion signature as #39.
- **measured LOCAL magnitude**: 2025 phi=1.217 (chi2=2927.8, df=2405, p=8.21e-13), pooled putaway-whiff rate=0.1330, n=2,406 games. Replication (2024): phi=1.285 (chi2=3119.4, df=2427, p=3.31e-20), rate=0.1331, n=2,428 games.
- **artifact link**: `domains/mlb/knowledge/validate_research_wave5.py::putaway_whiff_dispersion_exceeds_binomial_noise`; `domains/mlb/knowledge/validation_ledger.jsonl`, hypothesis=`putaway_whiff_dispersion_exceeds_binomial_noise__2025`/`__2024`/`__combined`.
- **source**: internal design mirror of CONFIRMED+REPLICATED #39 (this ledger); "Count-dependent Pitch Profile Manipulation" (Driveline Baseball), https://www.drivelinebaseball.com/2021/03/count-dependent-pitch-profile-manipulation/ -- documents pitchers meaningfully shift pitch-type mix/intensity specifically in 2-strike putaway counts, the literature basis for treating 2-strike whiff execution as a plausible game-calling-sensitive, game-level dispersion candidate.

### 54. Automatic-runner ("zombie runner") extra-inning home/away scoring-rate parity check, rule-era aware
- **claim**: in automatic-runner extra innings, the home team's half-inning scoring rate is NOT measurably higher than the road team's, despite a theoretical "last licks" information advantage (home bats second, knowing the exact run target) -- testing a documented literature reversal directly on the local corpus.
- **premise check**: `data/cache/statcast/savant_full__2025.parquet` columns `game_pk`/`inning`/`inning_topbot`/`on_2b`/`post_home_score`/`post_away_score` confirmed; `inning>=10` rows n=8,674 across 204 games (2025); `on_2b` non-null (runner present) at the first pitch of every sampled `inning>=10` half-inning (588/588 = 100%), confirming the automatic-runner rule is active for the full local window.
- **rule-era note**: the automatic-runner rule was emergency-only 2020-2022, made PERMANENT starting 2023 (MLB.com); local corpora span 2023-2026 (`savant_full__2023/2024/2025/2026.parquet`) -- entirely inside the rule-active era, no pre-2020 mixing risk. Must NOT be extended to any pre-2020 corpus without adaptation (no automatic runner existed then) -- flagged here for whoever reuses this design.
- **causal story**: SABR ("Ghost Stories and Zombie Invasions") and FanGraphs ("The Math Behind the Extra Innings Home Field Disadvantage") both document that home teams have NOT been winning extra innings at the rate the "last licks" information advantage would predict, and an arXiv causal-inference study (Doan, "Bunting and the ghost runner") finds home teams under-bunt relative to the win-probability-optimal rate. This row tests the literal per-half-inning scoring-rate half of that documented reversal directly on the local corpus.
- **expected signature**: no positive home-scoring-rate edge (or a null/negative one) in `inning==10` half-innings, contradicting a naive "last licks" prior.
- **test spec**: `domains.mlb.knowledge.validate_research_wave5.zombie_runner_home_away_scoring_rate` -- restrict to `inning==10` games where both halves are played (game not already decided in the top 10th); per half-inning, scored = home/away post-score minus pre-score >=1; two-sample proportion test, home bottom-10th scoring rate vs away top-10th scoring rate; declared bar |diff|>=0.05 AND p<0.05 (relaxed alpha vs the 0.01 house default, stated explicitly given the smaller single-inning-slice n).
- **status**: REJECTED (NULL_LOCAL) -- no significant home/away scoring-rate difference detected; below the declared bar. Read plainly this null IS consistent with the row's own claim ("home NOT measurably higher") and the cited SABR/FanGraphs literature reversal -- reported here as NULL_LOCAL per the standard bar-clearing convention (no real effect of either sign detected at n=204 games), not smuggled into a CONFIRMED_LOCAL discovery.
- **measured LOCAL magnitude**: bottom-10th (home) scoring rate=0.5245 (n=204 half-innings) vs top-10th (away)=0.4951 (n=204); diff=+0.0294, p=0.552, n=408 total half-innings (2025, both-halves-played games only) -- well below the declared |diff|>=0.05 & p<0.05 bar.
- **artifact link**: `domains/mlb/knowledge/validate_research_wave5.py::zombie_runner_home_away_scoring_rate`; `domains/mlb/knowledge/validation_ledger.jsonl`, hypothesis=`zombie_runner_home_away_scoring_rate`.
- **source**: "Ghost Stories and Zombie Invasions: Testing the Myths of Extra-Inning Outcomes" (SABR), https://sabr.org/journal/article/ghost-stories-and-zombie-invasions-testing-the-myths-of-extra-inning-outcomes/; "The Math Behind the Extra Innings Home Field Disadvantage" (FanGraphs), https://blogs.fangraphs.com/the-math-behind-the-extra-innings-home-field-disadvantage/; "Automatic runner permanent, new MLB rules for position players pitching" (MLB.com), https://www.mlb.com/news/automatic-runner-permanent-new-mlb-rules-for-position-players-pitching -- documents the rule's 2020 emergency origin -> 2023 permanence, the rule-era boundary this row must respect.

---
