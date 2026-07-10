# NBA Mechanism Ledger

One entry per mechanical belief the system holds about NBA, with a receipt.
Fields, always in this order: **claim | causal story | expected signature in
our data | test spec | status | measured LOCAL magnitude | artifact link**.

Status values: `UNTESTED`, `CONFIRMED` (survived a leak-free local test,
ideally replicated), `REJECTED` (tested locally and failed, or failed
cross-corpus replication), `PARTIAL` (mixed verdict across corpora/specs),
`NOT_TESTABLE` (the ingredient does not exist in our local corpus).

Local receipts for `CONFIRMED`/`REJECTED`/`NOT_TESTABLE` rows live in
`data/cache/intel_claims/prereg_hypothesis_ledger.jsonl` (the long-running
prereg ledger) and `domains/basketball_nba/knowledge/validation_ledger.jsonl`
(the first session's 10 fresh validations, 2,381-game 2024-25 + 2025-26
`player_boxscores.parquet` corpus, plus a 2026-07-09 second batch of 10 more
covering every remaining UNTESTED row -- see "Validated 2026-07-09" section).
No `$` edge is claimed anywhere in this file.

---

## Pre-adjudicated (do NOT re-test -- closed classes, cited from the existing ledgers)

### 1. Stint continuity x defensive rebound rate
- **claim**: lineups that have played more consecutive seconds together (stint continuity) grab a higher share of available defensive rebounds.
- **causal story**: box-out assignments and help-rotation timing are learned within a stint; a fresher-together lineup boxes out more reliably than one just substituted in.
- **expected signature**: positive continuity-seconds coefficient on DREB rate, stable across seasons.
- **test spec**: stint-level OLS/logit, continuity_s vs DREB rate, cluster-robust by lineup.
- **status**: CONFIRMED (REPLICATED across 3 seasons)
- **measured LOCAL magnitude**: n=116,960 eff=0.000574 p=1.9e-16 (repeated identically across re-runs); H2_continuity_diff spec: 2024-25 REPLICATED eff=0.000283 p=2.8e-4 (n=27,958), 2023-24 REPLICATED eff=0.000279 p=8.5e-6 (n=27,086) -- note a differently-specified variant of the SAME test also produced FAILED_REPLICATION rows at those same seasons, so the finding is spec-sensitive; the single-factor spec is the one that held 3-for-3.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="stint continuity x defensive rebound rate", verdict=REPLICATED (x3+); `domains/basketball_nba/prereg/nba_hypotheses.py` h7.

### 2. Lineup spacing x transition frequency
- **claim**: a lineup's floor-spacing composite interacts with transition-possession frequency to change efficiency, beyond either factor alone.
- **causal story**: spacing matters more in transition (defense not yet set) than in a set halfcourt possession.
- **expected signature**: positive spacing x transition-frequency interaction on points/possession.
- **test spec**: possession-level cluster-robust interaction.
- **status**: CONFIRMED (REPLICATED; was BLOCKED before the feature builder existed, then survived and replicated)
- **measured LOCAL magnitude**: eff=-0.0082 p=1.6e-5 n=219,629 (REPLICATED pass, 2025-26); eff=-0.0099 p=8.7e-10 n=213,696 (SURVIVES_PREREG pass). Sign is negative in both passes (higher combined spacing+transition reduces the outcome metric as specified, not a "more is always better" story) -- direction should be read from the actual regression spec, not assumed.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="lineup spacing x transition frequency", verdict=REPLICATED.

### 3. Lineup spacing x late-clock (<=7s) efficiency
- **claim**: spacing's efficiency benefit is larger late in the shot clock than earlier.
- **causal story**: late-clock possessions have less time to generate a great look; spacing widens driving/passing lanes exactly when the offense most needs one.
- **expected signature**: positive spacing x late-clock interaction on efficiency.
- **test spec**: possession-level cluster-robust interaction.
- **status**: CONFIRMED (REPLICATED)
- **measured LOCAL magnitude**: eff=0.00385 p=0.0098 n=219,629 (REPLICATED); eff=0.00567 p=1.3e-4 n=213,696 (SURVIVES_PREREG).
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="spacing x late-clock (<=7s) efficiency", verdict=REPLICATED.

### 4. Lineup synergy / talent differential (H3 on/off talent diff)
- **claim**: a lineup's on/off talent differential predicts point differential, and is a much stronger predictor than continuity or spacing alone.
- **causal story**: raw talent stacking dominates chemistry effects at the margin our corpus can see.
- **expected signature**: large positive coefficient, on/off talent diff vs point differential, dwarfing the continuity/spacing terms.
- **test spec**: same lineup-quality-composition design as #1/#2, run alongside H1/H2.
- **status**: CONFIRMED (REPLICATED 3 seasons -- by far the strongest survivor of the lineup-composition batch)
- **measured LOCAL magnitude**: 2025-26 eff=0.256 p~8e-143 n=28,736; 2024-25 eff=0.248 p~3e-150 n=27,958; 2023-24 eff=0.275 p~1e-130 n=27,086. Two full orders of magnitude bigger than the continuity effect (#1) on the same corpus -- the honest read is "raw talent >> chemistry" for point-differential prediction.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="H3_onoff_talent_diff", verdict=REPLICATED (x3).

### 5. endQ1 x star_minutes_load -- PARTIAL
- **claim**: a star's cumulative minutes load by end of Q1 changes how the rest of the game prices/plays out (a freshness proxy).
- **causal story**: a star who logged unusually heavy Q1 minutes (foul trouble avoidance aside) has less in the tank for crunch time.
- **expected signature**: a real, non-zero endQ1 x load interaction on a game outcome/pricing target -- but signature should be spec-sensitive given the mixed verdict below.
- **test spec**: game-segment regression, endQ1 state x star_minutes_load.
- **status**: PARTIAL (REPLICATED in the original prereg spec 2-of-3 corpora; a differently-specified "freshness live-state" variant came back NULL)
- **measured LOCAL magnitude**: original spec REPLICATED eff=0.00404 p=0.0028 n=486; freshness live-state variant NULL eff=-0.000264 p=0.367 n=189,601 (much larger n, much smaller/insignificant effect -- the live-state framing likely washes out the original small-sample signal).
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypotheses "endQ1 x star_minutes_load" (REPLICATED) and "endQ1 x star_minutes_load (freshness live-state)" (NULL).

### 6. endQ1 x floor_quality -- REJECTED, CLOSED
- **claim**: end-of-Q1 floor-quality state interacts with subsequent scoring.
- **status**: REJECTED (FAILED_REPLICATION, eff=0.00123 p=0.132 n=486) -- globally blocklisted as a pair so the interaction factory never re-tests it.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="endQ1 x floor_quality_now"; `scripts/platformkit/interaction_factory/generator.py` `GLOBAL_BLOCKLIST_PAIRS = {frozenset({"endQ1","floor_quality"})}`.

### 7. 12-attr lineup-quality composite -- PARTIAL (pregame confirmed, in-game conditioning null)
- **claim**: a composed 12-attribute lineup-quality index predicts point differential pregame, and further conditions in close-and-late situations.
- **causal story**: the composite aggregates spacing/continuity/talent into one predictive index; a real in-game conditioning effect would mean the composite matters MORE when the game is close late.
- **expected signature**: pregame -- positive composite-diff coefficient on margin. In-game -- a further positive composite x close-late interaction.
- **test spec**: walk-forward train 2024-25/test 2025-26 for the pregame composite; H2 in-game interaction on the same frame.
- **status**: PARTIAL -- pregame composite CONFIRMED (SURVIVES_PREREG then REPLICATED), in-game close-late conditioning REJECTED (NULL); OOS lift over the pregame-only composite is negligible.
- **measured LOCAL magnitude**: pregame SURVIVES_PREREG eff=0.202 p=1.9e-7 n=30,837; REPLICATED eff=0.255 p=1.8e-15 n=30,332. In-game H2_composed_quality_x_close_late NULL eff=0.130 p=0.461 n=30,837.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypotheses "H1_composed_lineup_quality" / "H1_composed_lineup_quality_replication_2024_25" (REPLICATED) and "H2_composed_quality_x_close_late" (NULL).

### 8. Gravity x defensive-coverage type
- **claim**: a shooter's gravity (defender attention pulled away) interacts with the defense's coverage scheme (drop vs switch) to change efficiency.
- **status**: NOT_TESTABLE -- no defensive-coverage-type label (switch/drop) exists anywhere in the local PBP corpus (`actionType` is limited to 2pt/3pt/freethrow/other/substitution); no honest proxy was available.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="gravity x drop coverage", verdict=BLOCKED.

### 9. Raw spacing main effect (no interaction)
- **claim**: a lineup's spacing composite alone (not crossed with transition or late-clock) predicts point differential.
- **status**: REJECTED (NULL, both attempts) -- only the INTERACTIONS (#2, #3) survive; spacing alone does not.
- **measured LOCAL magnitude**: eff=0.028 p=0.867 n=7,296; eff=0.007 p=0.963 n=7,296.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="H1_spacing_diff", verdict=NULL (x2).

### 10. Spacing x clutch (<=5pt, <=5min)
- **claim**: spacing's efficiency benefit is larger in clutch situations.
- **status**: REJECTED (NULL, eff=0.0035 p=0.343 n=213,002) -- distinct from the CONFIRMED late-clock interaction (#3); "clutch" (score+time) and "late-clock" (shot-clock) are different conditioning variables and only one replicates.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="spacing x clutch (<=5 pt, <=5 min)", verdict=NULL.

### 11. Lineup continuity x realized starter disruption
- **claim**: continuity's benefit is larger when a game features an unplanned starter change (injury/ejection disruption).
- **status**: REJECTED (NULL, all 3 attempts: eff=1.4e-5/p=0.939 n=448; eff=3.4e-4/p=0.523 n=479; eff=2.2e-4/p=0.187 n=479).
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="lineup_continuity x realized starter disruption", verdict=NULL (x3).

### 12. In-game player-profile conditioning -- CLOSED at both corpus sizes
- **claim**: a player's rolling in-game statistical profile (beyond season averages) conditions live win-probability.
- **status**: REJECTED / CLOSED -- tested and REJECTED at both the 74-game and the fuller 1,299-game box-score corpus; raising the corpus size did not flip the verdict.
- **artifact link**: memory `nba_ingame_profile_closed_2026_07_05`; `domains/basketball_nba/asof_reclaim_gate.py`, `domains/basketball_nba/pregame_stack_gate.py`, `domains/basketball_nba/espn_nba_bridge.py` (the 74->1,299 game coverage note).

### 13. Composed pressure profile (H1)
- **claim**: a composed in-game "pressure" profile (combining multiple stress indicators) predicts an outcome beyond its parts.
- **status**: REJECTED (NULL, eff=-0.034 p=0.066 n=69,289) -- another composed-challenger-class null, consistent with the "composed challengers of team-level aggregates don't beat their parts" pattern seen elsewhere in this ledger.
- **artifact link**: `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`, hypothesis="H1 composed pressure profile", verdict=NULL.

---

## Validated THIS SESSION (10 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

Corpus: `data/domains/basketball_nba/player_boxscores.parquet` (2,381 games,
2024-25 + 2025-26, 51,237 player-game rows), joined to `pbp_possession_features.parquet`
and `four_factor_env.parquet` where noted. Leak audit: rest/schedule features
are schedule-only (no outcome leak); split-half and cross-sectional checks are
descriptive, not live per-game features (no season-final-aggregate-as-feature
violation -- these are mechanism checks, not production inputs).

### 14. Back-to-back (B2B) rest penalty
- **claim**: a team playing on zero days' rest performs worse (point differential) than a team with at least one day's rest.
- **causal story**: no rest for recovery/practice/scouting; travel fatigue compounds.
- **expected signature**: negative margin on 0-rest games vs rested games.
- **test spec**: Welch t-test, team-game margin, `rest_days==0` vs `rest_days>=1`.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: avg margin -1.41 (0-rest, n=856) vs +0.32 (rested, n=3,876); effect -1.73, p=0.0056, n=4,732 team-games.
- **artifact link**: `domains/basketball_nba/knowledge/validate_schedule_fatigue.py::b2b_rest_penalty`.
- **wiring**: in-game conditioning-feature candidate -- `rest_days==0` as a pregame team-strength adjuster (schedule-known well before tipoff, no leak).

### 15. Three-in-four fatigue -- LOCAL NULL
- **claim**: a team playing its 3rd game within a trailing 4-day window performs worse than one that is not.
- **status**: REJECTED (NULL_LOCAL) -- directionally consistent (-0.92 margin) but not significant at alpha=0.01 (p=0.092); the classic "3-in-4" schedule-fatigue claim does not clear the bar on this 2-season sample, unlike the sharper same-night B2B effect (#14).
- **measured LOCAL magnitude**: avg margin -0.67 (3-in-4, n=1,256) vs +0.24 (not, n=3,506); effect -0.92, p=0.092, n=4,762.
- **artifact link**: `domains/basketball_nba/knowledge/validate_schedule_fatigue.py::three_in_four_fatigue`.

### 16. Home-court advantage magnitude
- **claim**: home teams outperform their point-differential expectation vs the same team on the road.
- **causal story**: travel, crowd noise, officiating environment, and sleep/routine familiarity favor the home team.
- **expected signature**: positive home margin, home win% > 50%.
- **test spec**: Welch t-test, team-game margin, home vs away.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: avg margin +1.70 (home) vs -1.70 (away); effect +3.40, p=2.7e-13, n=4,762; home win% = 0.533 (a bit below the historical ~0.55-0.60 range, honestly reported as-is for this 2-season sample, not adjusted).
- **artifact link**: `domains/basketball_nba/knowledge/validate_schedule_fatigue.py::home_court_advantage_magnitude`.
- **wiring**: in-game conditioning-feature candidate -- `is_home` as a baseline pregame margin adjuster; already implicitly present wherever a model conditions on venue, but not yet a declared interaction_factory template term.

### 17. Garbage-time bench production inflation
- **claim**: bench players' per-minute production is inflated in blowout games relative to close games.
- **causal story**: garbage-time minutes come against opposing bench/lower-effort defense and with green-light usage bench players don't get in close games.
- **expected signature**: higher bench pts/min in |margin|>=20 games vs closer games.
- **test spec**: Welch t-test, bench (`starter==0`, min>=3) pts/min, blowout vs non-blowout.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: 0.409 pts/min (blowout, n=6,770) vs 0.369 (close, n=18,537); effect +0.041, p=1.7e-21, n=25,307.
- **artifact link**: `domains/basketball_nba/knowledge/validate_usage_garbage.py::garbage_time_bench_inflation`.
- **wiring**: in-game conditioning-feature candidate -- `|margin|>=20` as a live bench-production discount factor for in-game prop re-pricing (a blowout-state flag, not a season aggregate).

### 18. Clutch usage "compression" -- CONFIRMED, but REVERSED direction (amplification, not compression)
- **claim (as seeded)**: high-usage players see their shot-usage share shrink in clutch minutes (defenses key on them / coaches spread the offense out).
- **causal story (as seeded)**: opponent defensive attention concentrates on a high-usage player late, making his own shots harder to generate, so his clutch share of team shots should fall relative to his overall share.
- **test spec**: OLS regression of clutch-shot-share on overall-shot-share (same game, same player), test slope vs 1.0.
- **status**: CONFIRMED that usage share is NOT 1:1 in clutch -- but REJECTED as originally framed: the local data shows AMPLIFICATION (slope=1.67 > 1), i.e. high-usage players take an even LARGER share of team shots in the clutch than their overall share ("hero-ball"), the opposite of "compression."
- **measured LOCAL magnitude**: slope=1.673 (vs 1.0 null), r=0.508, p=1.98e-4, n=255 player-games with >0 team clutch shots.
- **artifact link**: `domains/basketball_nba/knowledge/validate_usage_garbage.py::clutch_usage_compression`.
- **wiring**: in-game conditioning-feature candidate -- `overall_fga_share` as a live clutch-usage-share predictor (amplification direction), relevant to in-game player-prop re-pricing in close-and-late states; note this sits adjacent to the CLOSED in-game player-profile-conditioning class (#12) -- this is a usage-share mechanism, not a profile-conditioning one, so it is not automatically subject to that closure, but should be gated with the same discipline before being trusted.

### 19. Player-level B2B scoring-efficiency dip -- LOCAL NULL
- **claim**: individual scoring efficiency (true-shooting proxy) drops on zero-rest games.
- **status**: REJECTED (NULL_LOCAL, borderline) -- the team-level B2B margin penalty (#14) is real, but it is NOT explained by individual scoring-efficiency decline; whatever drives the team-level effect (bench depth, turnovers, defensive effort) sits elsewhere.
- **measured LOCAL magnitude**: TS-proxy 0.5677 (0-rest, n=7,777) vs 0.5733 (rested, n=35,219); effect -0.0056, p=0.053, n=42,996 (min>=10 minutes).
- **artifact link**: `domains/basketball_nba/knowledge/validate_usage_garbage.py::player_b2b_scoring_dip`.

### 20. Rotation size vs net rating -- LOCAL NULL
- **claim**: teams with tighter (smaller) rotations have better average net point differential.
- **status**: REJECTED (NULL_LOCAL) -- no cross-sectional relationship found this session.
- **measured LOCAL magnitude**: r=-0.054, p=0.682, n=60 team-seasons.
- **artifact link**: `domains/basketball_nba/knowledge/validate_rotation_pace.py::rotation_size_stability_vs_net_rating`.

### 21. Rotation size persists (coach rotation-pattern stability)
- **claim**: a team's typical nightly rotation size is a stable team characteristic across a season.
- **causal story**: it reflects a coach's standing philosophy (shortened vs deep bench), not game-to-game noise.
- **expected signature**: strong positive split-half correlation of average rotation size per team.
- **test spec**: split-half Pearson r, avg players-with->=5-min per team-game, first half of season vs second half.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: r=0.681, p=3.5e-5, n=30 teams.
- **artifact link**: `domains/basketball_nba/knowledge/validate_rotation_pace.py::rotation_size_persists_split_half`.
- **wiring**: in-game conditioning-feature candidate -- team-level `avg_rotation_size` as a coach-tendency prior (descriptive team trait, not a per-game leak); pairs naturally with #20's null result (rotation size is stable but does not itself predict net rating).

### 22. Pace mismatch inflates game-margin variance -- LOCAL NULL
- **claim**: games between two fast-paced teams (high combined pace) show larger point-margin variance than slow-paced matchups.
- **status**: REJECTED (NULL_LOCAL) -- directionally present (high-pace tercile std 16.45 vs low-pace 15.91) but not significant at alpha=0.01.
- **measured LOCAL magnitude**: Levene p=0.163, n=4,762 (low tercile n=1,594, high tercile n=1,584).
- **artifact link**: `domains/basketball_nba/knowledge/validate_rotation_pace.py::pace_mismatch_variance`.

### 23. FT-rate environment vs wins -- LOCAL NULL
- **claim**: a team's free-throw-rate offensive environment (fta_rate_off) correlates with win percentage.
- **status**: REJECTED (NULL_LOCAL) -- single-snapshot cross-section, no relationship found.
- **measured LOCAL magnitude**: r=0.073, p=0.702, n=30 teams (four_factor_env vs season-pooled win%, not season-matched exactly -- a caveat, not a clean test; worth a cleaner re-test with season-aligned four-factor data before fully believing the null).
- **artifact link**: `domains/basketball_nba/knowledge/validate_rotation_pace.py::ft_rate_environment_wins`.

---

## Validated 2026-07-09 (10 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

### 24. Clutch lineup shortening
- **claim**: coaches shorten their rotation specifically in clutch minutes (distinct from #21's overall-game rotation stability).
- **causal story**: trust narrows under pressure -- fewer players see clutch possessions than see full-game minutes.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: clutch distinct-player count 3.05 vs full-game (>=5min) rotation size 9.39; effect -6.34, p~0, n=1,052 team-games that reached a clutch state.
- **artifact link**: `domains/basketball_nba/knowledge/validate_lineup_composition.py::clutch_lineup_shortening`.
- **wiring**: in-game conditioning-feature candidate -- expected clutch-rotation-size (~3 players) as a live-state prior for close-late player-prop re-pricing.

### 25. Rim-pressure defensive continuity x DREB -- LOCAL NULL
- **claim**: a lineup's interior defensive-pressure attribute (`rim_pressure_def`) predicts team DREB rate.
- **status**: REJECTED (NULL_LOCAL) -- no relationship found this session.
- **measured LOCAL magnitude**: r=0.0479, p=0.279, n=512 players (rim_fga>=30 both on/off states, minutes>=200), `zone_onoff_2024_25.parquet` vs season DREB/min.
- **artifact link**: `domains/basketball_nba/knowledge/validate_lineup_composition.py::rim_pressure_def_dreb`.

### 26. Usage-redistribution persistence after a high-usage player is out
- **claim**: when a high-usage player sits, the redistributed usage among remaining players follows a predictable (not random) pattern that persists across multiple absences.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: split-half (odd/even absence occasions) pearson r=0.8005, p~0, n=1,657 team/missing-player/teammate triples, season 2025-26.
- **artifact link**: `domains/basketball_nba/knowledge/validate_usage_events.py::usage_redistribution_persistence`.
- **wiring**: in-game conditioning-feature candidate -- teammate's own baseline `fga_share` (constructed from games where the high-usage teammate played) as a live redistribution-share predictor when that teammate is ruled OUT (a pregame-known-absence trigger, not a leak).

### 27. Assist-network hub dependency -- LOCAL NULL
- **claim**: teams whose assist network concentrates through one "hub" passer are more efficient offensively than teams with a flat network, up to a point (inverted-U).
- **status**: REJECTED (NULL_LOCAL) -- no significant quadratic term.
- **measured LOCAL magnitude**: OLS `ppp_all_off ~ hub_share + hub_share^2`, quadratic coef=4.21 (linear=-1.45), p=0.341, n=30 teams, season 2025-26.
- **artifact link**: `domains/basketball_nba/knowledge/validate_usage_events.py::assist_hub_concentration_offrtg`.

### 28. Transition-frequency pace mismatch (distinct from overall pace variance, #22)
- **claim (as originally framed)**: a team's transition-possession rate specifically (not overall pace) predicts its efficiency edge against slow-transition-defense opponents.
- **claim (as tested -- scoped)**: a team's own AS-OF trailing transition-shot-attempt rate, differenced against its opponent's, predicts point margin. This closes the original leak (event-level rebuild, no season aggregate) but does NOT test the opponent-transition-defense-matchup half of the original framing -- that needs a separate opponent-defense join not attempted this session.
- **status**: CONFIRMED_LOCAL -- single-season (2025-26) event-level evidence; not yet replicated across a second season/corpus, so read as LOCAL not REPLICATED.
- **measured LOCAL magnitude**: two legs, both required for CONFIRMED_LOCAL. (1) persistence: split-half (odd/even game occasion) pearson r=0.9581, p=9.6e-17, n=30 teams -- transition rate is a stable team tendency, not per-game noise. (2) margin relation: pearson r=0.1452, p=1.7e-6, n=1,077 games -- leak-free AS-OF trailing transition-rate differential (home minus away, >=5 prior games burn-in) correlates with home_margin. Season 2025-26 (the one season with event-level CDN pbp on disk locally, `data/cache/team_system/pbp`, 1,192 game files).
- **artifact link**: `domains/basketball_nba/knowledge/validate_transition_frequency.py::run`; `domains/basketball_nba/knowledge/validation_ledger.jsonl` hypothesis=`transition_frequency_pace_mismatch__combined` (+ `transition_rate_split_half_persistence`, `transition_rate_margin_relation`).
- **leak note**: transition_rate is derived from `domains.basketball_nba.composition.transition_flag`'s existing 6.0s-post-possession-start shot cut (reused, not reinvented; validated against the real 'fastbreak' qualifier on CDN files in that module). The AS-OF trailing feature uses `shift(1)` before the expanding mean, so game k's own outcome is never in its own predictor -- unlike the original NOT_TESTABLE `atlas_team_transition_defense.parquet` (n=30, one row per team, season-final aggregate).

### 29. Clutch free-throw pressure dip
- **claim**: FT% drops in clutch situations (last 5 min, close game) relative to a player's season FT%.
- **status**: NOT_TESTABLE -- `pbp_possession_features.parquet` has clutch FG tracking only (`pbp_clutch_shots_attempted`/`pbp_clutch_pts_scored`), zero clutch-specific FT columns; `player_boxscores.parquet` only has game-total ftm/fta. No clutch-window FT split exists anywhere in the local corpus.
- **artifact link**: `domains/basketball_nba/knowledge/validate_premise_blocked.py::clutch_ft_pressure_dip`.

### 30. Second-unit (bench lineup) continuity effect -- CONFIRMED, REVERSED direction vs full-lineup #1
- **claim**: continuity's DREB benefit (#1) is at least as strong for bench-only lineups as for starter-heavy lineups.
- **status**: CONFIRMED that continuity matters for bench-heavy stints -- but REJECTED as originally framed ("at least as strong, same direction"): the local data shows a NEGATIVE continuity coefficient for <=2-starters-on-court stints, the opposite sign of the positive full-lineup effect (#1, eff=0.000574 same single-season spec).
- **measured LOCAL magnitude**: logit `is_dreb ~ continuity_s` restricted to <=2-starters-on-court stints: eff=-0.00019, p=5.0e-6, n=76,418 rebound-events, season 2024-25 (cf. full-lineup #1 single-season eff=+0.000574 p=1.9e-16 n=116,960 on the same corpus).
- **artifact link**: `domains/basketball_nba/knowledge/validate_lineup_composition.py::bench_continuity_dreb`.
- **wiring**: flag before use -- bench-heavy stints show DREB rate falling (not rising) with continuity; this contradicts the naive "chemistry always helps" read of #1 and should not be assumed to generalize from the starter-inclusive result.

### 31. Travel/time-zone fatigue (distinct from simple rest-days, #14)
- **claim**: a team crossing 2+ time zones for a road game underperforms its rest-days-adjusted expectation.
- **status**: NOT_TESTABLE -- fresh glob this session for `*arena*`/`*travel*` under `data/domains/basketball_nba` returned 0 relevant hits; `rest_days` (#14) is the only schedule ingredient on disk. No arena-location/timezone join exists locally.
- **artifact link**: `domains/basketball_nba/knowledge/validate_premise_blocked.py::travel_timezone_fatigue`.

### 32. Foul-trouble minutes reduction (early foul trouble) -- LOCAL NULL (small effect)
- **claim**: a starter who picks up 2 fouls in the first half plays fewer total minutes than his season average that game.
- **status**: REJECTED (NULL_LOCAL) -- direction is correct and p<0.01, but the magnitude is too small to call a real effect at the 1.0-minute floor used here; reported honestly rather than rounded up.
- **measured LOCAL magnitude**: starter minutes-gap-vs-season-avg, >=2 first-half fouls (-0.47 min, n=3,392) vs <2 (-0.10 min, n=8,918); effect -0.37, p=2.7e-4, n=12,310 (quarter_box q1+q2 coverage, 1,231 games).
- **artifact link**: `domains/basketball_nba/knowledge/validate_usage_events.py::foul_trouble_minutes_reduction`.

### 33. Star-injury usage-vacuum overreaction -- LOCAL NULL
- **claim**: teammate production in game 1 without a missing star undershoots the season-long redistribution average; games 2+ converge.
- **status**: REJECTED (NULL_LOCAL) -- no significant game-1-vs-rest gap.
- **measured LOCAL magnitude**: fga_share deviation-from-normal-baseline, game-1-of-absence (0.0529, n=6,946) vs games>=2 (0.0511, n=5,818); effect +0.0019, p=0.030, n=12,764.
- **artifact link**: `domains/basketball_nba/knowledge/validate_usage_events.py::star_injury_usage_vacuum_event_study`.

---

## Validated 2026-07-10 (box-detail family -- newly-unlocked espn_boxscores.parquet detail columns)

Unlocks the entirely-dark box-detail family (fast_break_pts, paint_pts,
tov_pts, largest_lead, foul_trouble) already exposed by the leak-free
walk-forward as-of reader `domains/basketball_nba/boxdetail_asof.py` (built
same session, commits 132179ca/bcaa6d7a). The 3 rows below are the
DESCRIPTIVE mechanism check (same-game raw values, split-half + cross-
sectional, not a live per-game feature) that decides whether each stat is
worth carrying into the interaction factory. Corpus: `espn_boxscores.parquet`
box-detail slice, 2026-01-20..2026-05-24, n=1,342 team-games (671 games,
30 real teams; 3 All-Star exhibition rows excluded). Each hypothesis requires
BOTH a split-half persistence leg AND a same-game margin-relation leg to
clear p<0.01 + |r|>=0.15 for CONFIRMED_LOCAL.

**Power note (2026-07-10 PM, readout only -- no rerun this session)**:
`boxdetail_gate.py`'s SHIP/REJECT gate was NOT_TESTABLE because its
`_train_window_has_coverage` check finds the 70%-by-date TRAIN cutoff on
`games.parquet` (2022-10-18..2026-04-12, 4,846 games) lands at 2025-03-06,
entirely BEFORE box-detail coverage starts (2026-01-20 in
`espn_boxscores.parquet`, the only file `boxdetail_asof.py` currently reads)
-- the train window's box-detail column is all-NaN, degenerating every
test-row value to 0. `espn_boxscores_2024_25.parquet` covers
2024-10-22..2025-04-13, i.e. it DOES span the 2025-03-06 train cutoff --
merging it into `boxdetail_asof.py`'s input would give the train window
~4.3 months of real box-detail coverage before the cutoff, unblocking the
NOT_TESTABLE verdict into an actually-evaluated SHIP/REJECT. Not done here
(`boxdetail_asof.py`/`boxdetail_gate.py` are outside this lane's
`knowledge/`-only scope) -- follow-up: wire the new parquet into
`boxdetail_asof.py`'s espn-box input, rebuild `boxdetail_asof.parquet`,
rerun `boxdetail_gate.py`.

### 34. Fast-break points persistence + margin-relation
- **claim**: a team's fast-break scoring is a stable team trait (persists split-half) and relates to that game's scoring margin.
- **causal story**: transition offense is a coached, practiced tendency (push-the-pace identity), not game-to-game noise; more transition scoring should track winning.
- **expected signature**: positive split-half r across teams; positive same-game r(fast_break_pts, margin).
- **test spec**: split-half Pearson r (first-half-of-corpus-dates vs second, per team) + pooled Pearson r vs same-game margin.
- **status**: CONFIRMED (REPLICATED -- second corpus 2026-07-10 PM)
- **measured LOCAL magnitude**: persistence r=0.604, p=4.1e-4 (n=30 teams); margin relation r=0.298, p=5.8e-29 (n=1,342 team-games).
- **artifact link**: `domains/basketball_nba/knowledge/validate_boxdetail_persistence.py::hypothesis("fast_break_pts")`.
- **wiring**: candidate for the interaction factory's box_detail family (see `boxdetail_asof.py`'s `fast_break_pts_diff_asof`); thin single-season slice (box-detail only 2026-01-20 onward) -- not yet gated for a pregame outcome edge (see `boxdetail_gate.py` for that separate SHIP/REJECT track).
- **replication attempt (2026-07-10 AM)**: NOT_REPLICABLE_NO_CORPUS at the time -- fresh disk check confirmed `espn_boxscores.parquet`'s `home_fast_break_pts` non-null for 0 of the pre-2026 rows (1,977 total); the only other local `fast_break` column (`data/cache/player_breakdown_features.parquet`) is a player-SEASON aggregate (n=569, no date/game_id), wrong granularity. No second team-game-level corpus existed locally yet.
- **replication (2026-07-10 PM)**: REPLICATED on `espn_boxscores_2024_25.parquet` (1,235 games, 2024-10-22..2025-04-13, 0 event_id overlap with `espn_boxscores.parquet` -- a genuinely disjoint second corpus, same design/bars unchanged). persistence r=0.7033, p=1.46e-05 (n=30 teams); margin relation r=0.2809, p=7.56e-46 (n=2,460 team-games) -- same (positive) sign both legs. `domains/basketball_nba/knowledge/validate_replication_wave1.py::fast_break_pts_persistence_replication_2024_25`; `validation_ledger.jsonl` hypothesis=`boxdetail_fast_break_pts_persistence_replication_2024_25`.

### 35. Points-in-the-paint persistence + margin-relation
- **claim**: a team's paint scoring is a stable team trait and relates to that game's scoring margin.
- **causal story**: interior scoring reflects personnel (rim finishers, post touches) and offensive scheme, both season-stable; more paint points should track winning.
- **expected signature**: positive split-half r across teams; positive same-game r(paint_pts, margin).
- **test spec**: same design as #34.
- **status**: CONFIRMED (REPLICATED -- second corpus 2026-07-10 PM)
- **measured LOCAL magnitude**: persistence r=0.699, p=1.7e-5 (n=30 teams); margin relation r=0.335, p=1.2e-36 (n=1,342 team-games) -- the strongest of the 3 box-detail rows on both legs.
- **artifact link**: `domains/basketball_nba/knowledge/validate_boxdetail_persistence.py::hypothesis("paint_pts")`.
- **wiring**: candidate for the interaction factory's box_detail family; thin single-season slice, same caveat as #34.
- **replication attempt (2026-07-10 AM)**: NOT_REPLICABLE_NO_CORPUS at the time -- same disk check as #34: `home_paint_pts` non-null for 0 of the pre-2026 `espn_boxscores.parquet` rows; `player_breakdown_features.parquet`'s `misc_pts_paint` is again a player-season aggregate, wrong granularity.
- **replication (2026-07-10 PM)**: REPLICATED on `espn_boxscores_2024_25.parquet` (same disjoint second corpus as #34). persistence r=0.763, p=9.45e-07 (n=30 teams); margin relation r=0.248, p=8.31e-36 (n=2,460 team-games) -- same (positive) sign both legs. `domains/basketball_nba/knowledge/validate_replication_wave1.py::paint_pts_persistence_replication_2024_25`; `validation_ledger.jsonl` hypothesis=`boxdetail_paint_pts_persistence_replication_2024_25`.

### 36. Points off turnovers (tov_pts) persistence + margin-relation -- LOCAL NULL (persistence leg misses; margin leg flips sign)
- **claim**: a team's points-off-turnovers total is a stable team trait and relates positively to that game's scoring margin.
- **status**: REJECTED (NULL_LOCAL) -- persistence leg falls just short of the p<0.01 bar (p=0.0129, marginal miss, directionally real at r=0.449); the margin-relation leg IS significant but NEGATIVE (r=-0.307, p=1.0e-30), the opposite of the "more points off turnovers = better margin" prior -- an honest, mildly surprising result flagged here rather than smoothed over. A plausible confound: this column's own attribution (whether `tov_pts` credits points scored off the OPPONENT's turnovers vs. points the opponent scored off THIS team's own giveaways) is not independently verified against a second source in this session, so the sign should not be over-interpreted without a coverage/definition re-check.
- **measured LOCAL magnitude**: persistence r=0.4485, p=0.0129 (n=30 teams, misses ALPHA=0.01); margin relation r=-0.3072, p=1.0e-30 (n=1,342 team-games).
- **artifact link**: `domains/basketball_nba/knowledge/validate_boxdetail_persistence.py::hypothesis("tov_pts")`.
- **wiring**: none -- do not wire until the column-attribution ambiguity above is resolved; flagged as a re-check candidate, not a confirmed mechanism.
- **diagnostic rerun (2026-07-10 PM)**: on `espn_boxscores_2024_25.parquet` (disjoint second corpus, same as #34/#35) the NEGATIVE margin-sign flip REPRODUCES (r=-0.3344, p=2.37e-65, n=2,460) -- and this time BOTH legs clear the bar (persistence r=0.6164, p=2.86e-4, n=30 teams), i.e. CONFIRMED_LOCAL on the new corpus, still negative-signed. The flip reproducing across a fully disjoint (0 event_id overlap) corpus is evidence the negative relation is real, not a single-corpus artifact -- but the column-attribution ambiguity noted above is still unresolved, so this stays a flagged re-check candidate, not wired. `domains/basketball_nba/knowledge/validate_replication_wave1.py::tov_pts_persistence_replication_2024_25` (verdict left as measured, not forced to a REPLICATED/FAILED_REPLICATION label since the original was NULL_LOCAL not CONFIRMED_LOCAL).

---

## Validated 2026-07-10 (quarter-shape family -- linescores.parquet realized-value reuse)

Corpus: `data/domains/basketball_nba/linescores.parquet` (1,313 games) via
`domains/basketball_nba/asof_quarter_shape.py::_derive_realized` (read-only
reuse of the production leak-free as-of builder's realized-value formula,
not a new derivation) reshaped to 2,626 team-games, 30 teams. Split-half =
first-half-of-corpus-dates vs second half, per team. Descriptive only, same
discipline as the box-detail family above.

### 37. Quarter-scoring volatility persistence + margin-variance relation -- LOCAL NULL
- **claim**: a team's quarter-to-quarter scoring volatility (stdev of its own q1-q4 points) is a stable team trait (persists split-half) and relates to that team's full-game margin variance.
- **status**: REJECTED (NULL_LOCAL) -- persistence leg fails outright (wrong-signed r, not significant); the margin-variance leg is directionally positive but misses ALPHA=0.01.
- **measured LOCAL magnitude**: split-half persistence r=-0.1389, p=0.464 (n=30 teams); cross-sectional r(team avg quarter_volatility, team full-game margin std)=0.3022, p=0.105 (n=30 teams).
- **artifact link**: `domains/basketball_nba/knowledge/validate_quarter_volatility.py::quarter_volatility_persists_and_relates_to_margin_variance`.

### 38. Q1 slow-start tendency persistence
- **claim**: a team's Q1 scoring margin tendency (own_q1 - opp_q1, averaged) is a stable team trait across a season.
- **causal story**: some teams are habitually slow starters (bench-heavy openers, cold shooting patterns) or fast starters (starter-heavy aggressive openers) as a coached identity, not game-to-game noise.
- **status**: CONFIRMED (REPLICATED -- second corpus 2026-07-10)
- **measured LOCAL magnitude**: split-half persistence r=0.7171, p=8.24e-06 (n=30 teams, `linescores.parquet`/2025-26) -- the strongest split-half persistence result in this ledger to date, stronger than rotation-size persistence (#21, r=0.681).
- **artifact link**: `domains/basketball_nba/knowledge/validate_quarter_volatility.py::q1_slow_start_persists`.
- **wiring**: in-game conditioning-feature candidate -- a team's trailing as-of `q1_margin_asof` (already built leak-free in `data/domains/basketball_nba/asof_quarter_shape.parquet`) as a live Q1-state prior for in-game re-pricing; this validation is the receipt that the underlying trait is real and persistent, not that the asof feature itself has been gated for an outcome edge.
- **replication (2026-07-10)**: REPLICATED on `linescores_2024_25.parquet` (1,321 games, disjoint 2024-25 season, same design/bars ported verbatim -- ALPHA=0.01, MIN_EFFECT=0.15 unchanged). r=0.5855, p=0.0006759 (n=30 teams) -- weaker than the original but clears the bar with the same (positive/fast-starter) sign. `domains/basketball_nba/knowledge/validate_replication_wave1.py::q1_slow_start_persists_replication_2024_25`; `validation_ledger.jsonl` hypothesis=`q1_slow_start_persists_replication_2024_25`.

---

## Validated 2026-07-10 (foul-trouble teammate spillover, C17 -- raw PBP `data/nba/pbp_<game_id>_p1.json`)

Premise check: foul TIMING (not just the season-final PF total already in
`player_boxscores.parquet`) is required for this class and DOES exist
locally in the raw per-quarter PBP feed -- each foul event carries a
`(P<n>.T<n>)` personal-foul-count suffix + `game_clock_sec`. Coverage:
1,289 of 3,611 box-scored games (2023-24..2025-26) have a local period-1
file (35.7%) -- a real but partial local corpus. "2-3 fouls" is
operationalized as "PF reaches 2" (the earliest qualifying/conventional
bench-trigger moment); "usage/efficiency" is FG-attempts-only inside a
fixed post-trigger window of period 1, not full-game team offense --
scope simplifications made for this pass, not a data gap.

### 39. Starter early-foul-trouble x teammates' Q1-remainder usage/efficiency shift -- LOCAL NULL
- **claim**: when a starter reaches 2 personal fouls within the first 6 minutes of period 1, teammates' shot-attempt volume (usage) and points-per-attempt (efficiency) in the remainder of period 1 shift beyond normal (no-foul-trouble) games for that team.
- **causal story**: a compromised/benched starter forces the offense to redistribute shot creation to the remaining four players on the floor -- a rotation-driven usage/efficiency reallocation, not a talent-level effect.
- **expected signature**: teammates' FGA-per-minute and points-per-FGA differ (foul-trouble games vs control games) beyond noise, same-direction across both halves.
- **test spec**: same-game contemporaneous group comparison (Welch t-test), split-half by date (2 corpora); declared bars |eff|>=0.15 FGA/min (usage) and |eff|>=0.08 pts/FGA (efficiency), both at p<0.01.
- **status**: REJECTED (NULL_LOCAL) both metrics, both halves. Usage: h1 eff=+0.007 p=0.69 (n=5,972), h2 eff=+0.024 p=0.19 (n=5,935). Efficiency: h1 eff=-0.099 p=0.09 (n=5,972), h2 eff=-0.034 p=0.56 (n=5,935). No half clears alpha=0.01 on either metric.
- **measured LOCAL magnitude**: see above (player_boxscores + pbp_p1_json, 1,289 games, split-half by date).
- **artifact link**: `domains/basketball_nba/knowledge/validate_foul_trouble_spillover.py::run`.

---

## Seeded 2026-07-10 (research-wave -- literature-sourced, VALIDATED same night, M10 pool feedstock)

Fresh mechanism hypotheses from public NBA analytics literature, checked
against every row above and against `data/frontend/reject_ledger.jsonl`
(535 rows) before seeding. Each row names the exact local parquet + columns
a validator would read.

**Renumbered 2026-07-10 (validation pass)**: this section originally used
#40-42, colliding with the separate same-night "Validated 2026-07-10
(largest_lead persistence...)" section below, which also used #40-41.
Renumbered to #42-44 (next free numbers after that section's #41) to
de-collide; no other row in this file references #40/#41/#42 by number, so
this is a pure relabeling, no semantic change.

### 42. On-ball defensive matchup skill is a stable, predictively-valid trait
- **claim**: a defender's trailing (as-of) individual-matchup FG% allowed predicts his REALIZED FG% allowed in the next matchup window beyond chance -- i.e. individual on-ball defense is a measurable, persistent skill, not matchup-assignment noise.
- **causal story**: some defenders are consistently tougher covers (lateral quickness, discipline, effort) independent of scheme; if that skill is real, a defender's own trailing matchup numbers should out-of-sample-predict his next matchup outcomes.
- **expected signature**: positive correlation between `def_priorN_fg_pct_allowed_asof` and same-defender `realized_fg_pct_allowed` in the following window, split-half stable across two season slices.
- **test spec**: split-half (season-date median split) Pearson r of (per-defender mean as-of value) vs (per-defender mean realized outcome) within each half, min floor >=2 windows AND >=15 summed prior-possessions per defender per half; declared bar |r|>=0.15 AND p<0.01, both halves same sign.
- **status**: CONFIRMED_LOCAL
- **measured LOCAL magnitude**: h1 r=0.5603, p=1.48e-45 (n=535 defenders); h2 r=0.5139, p=1.19e-36 (n=524 defenders); Spearman cross-check rho=0.59/0.66 (both p<1e-50), confirms the effect is not Pearson-outlier-driven. Builder (`ingest_defender_matchup_states.py`) verified genuinely leak-free: shift1 snapshot-before-update, prior-N=10 bounded window, current game never informs its own as-of value.
- **artifact link**: `domains/basketball_nba/knowledge/validate_research_wave1.py::defender_matchup_skill_predictive_validity`.
- **note**: distinct from `nba_defender_matchup` in `data/frontend/reject_ledger.jsonl` (REJECT, `proposal_only: true`, no actual test run) -- that entry rejected a WIN-PROBABILITY calibration-gate proposal (does a defender-matchup feature beat Elo Brier); this row tests the underlying metric's own predictive/persistence validity, the prior descriptive question, same split as the box-detail-family pattern (#34/#35 above). CONFIRMED here (the trait is real and persistent) is fully consistent with a REJECT there (real skill, still priced/not incrementally useful over Elo) -- not a contradiction.
- **source**: "Using Individual Matchup Data to Evaluate Defense in the NBA" (Ahmed Cheema, Medium/The Spax), https://medium.com/@ahmed.cheema/using-individual-matchup-data-to-evaluate-defense-in-the-nba-76b86f62a8c9 -- matchup-tracking data (Second Spectrum, since 2018) is used specifically to isolate individual defender skill from team scheme.

### 43. Switch frequency correlates with worse defensive efficiency (mismatch-hunting cost)
- **claim**: a team's defensive switch rate correlates with worse points-allowed-per-36, i.e. switching concedes efficiency to offenses that hunt the resulting mismatch, net of who the team is.
- **causal story**: switching avoids a wide-open shooter off a screen but creates a size/speed mismatch the offense can isolate and attack; if mismatch-hunting dominates, higher switch rate should track worse defensive efficiency.
- **expected signature**: positive correlation, `def_switches_per_game_diff_asof` vs `def_pts_allowed_per36_diff_asof` (corrected column names -- see premise-check note), at the team-game level.
- **test spec**: cross-sectional partial Pearson r (switches vs pts_allowed_per36, controlling for blocks_per_game as a rim-protection confound), `data/domains/basketball_nba/asof_defender_rollup.parquet`, both home/away sides pooled; declared bar |r|>=0.10 AND p<0.01.
- **status**: NOT_TESTABLE
- **premise-check fix**: the row as originally seeded named bare `def_switches_per_game_asof` / `def_pts_allowed_per36_asof` / `def_blocks_per_game_asof`; the parquet only has `home_`/`away_`/`diff_`-prefixed variants of each (corrected above).
- **measured LOCAL magnitude**: n/a -- `home_def_switches_per_game_asof` / `away_def_switches_per_game_asof` / `def_switches_per_game_diff_asof` are a CONSTANT 0.0 across all 1,656 games (nunique=1) in this parquet. Switch tracking is a stub column, not actually populated locally; a correlation against a zero-variance series is undefined, not a measured null.
- **artifact link**: `domains/basketball_nba/knowledge/validate_research_wave1.py::switch_rate_defensive_efficiency`.
- **source**: "Flipping the Switch" (Cleaning the Glass), https://cleaningtheglass.com/flipping-the-switch/ and "Switch 5" (Ben Everett, Medium), https://medium.com/@beneverett/switch-5-part-1-what-tracking-era-numbers-reveal-about-the-nbas-hottest-trend-53dea6df3e09 -- both note switch-created mismatches give the offense "more of an advantage than it did when the possession started," the mechanistic basis for this claim; re-test if a real (non-stub) switch feed ever lands locally.

### 44. Team assist rate persistence + margin-relation (box-detail-family design, new column)
- **claim**: a team's assist total is a stable team trait (persists split-half) and relates to that game's scoring margin -- the exact test design already CONFIRMED_LOCAL for fast-break points (#34) and paint points (#35), applied to `ast` (untested column, same corpus).
- **causal story**: ball movement is a coached, practiced identity (motion offense vs iso-heavy); assists correlate with open, higher-percentage shots, so more assists should track both team identity and winning.
- **expected signature**: positive split-half r across teams (identity persists); positive same-game r(ast, margin).
- **test spec**: split-half Pearson r (first-half-of-corpus-dates vs second, per team) + pooled Pearson r vs same-game margin, `espn_boxscores.parquet` `home_ast`/`away_ast`.
- **status**: CONFIRMED (REPLICATED -- second corpus 2026-07-10 PM)
- **measured LOCAL magnitude**: persistence r=0.7189, p=7.63e-06 (n=30 teams); margin relation r=0.4329, p=1.06e-179 (n=3,940 team-games). NOTE: unlike #34-36, `ast` is populated corpus-wide (full 1,977-game espn_boxscores.parquet), not the thin box-detail-era slice (2026-01-20 onward, ~671 games) -- hence the larger n vs #34/#35's 1,342.
- **artifact link**: `domains/basketball_nba/knowledge/validate_research_wave1.py::ast_persistence_and_margin` (reuses `validate_boxdetail_persistence.py`'s generic `_persistence_split_half`/`_margin_relation`/`_verdict` helpers).
- **replication (2026-07-10 PM)**: REPLICATED on `espn_boxscores_2024_25.parquet` (1,235 games, disjoint from `espn_boxscores.parquet`, `ast` 1,230/1,235 non-null). persistence r=0.8386, p=7.24e-09 (n=30 teams); margin relation r=0.4164, p=9.34e-104 (n=2,460 team-games) -- same (positive) sign both legs. `domains/basketball_nba/knowledge/validate_replication_wave1.py::ast_persistence_replication_2024_25`; `validation_ledger.jsonl` hypothesis=`boxdetail_ast_persistence_replication_2024_25`.
- **note**: distinct from `nba_ast_rate_diff_asof` in `data/frontend/reject_ledger.jsonl` (REJECT x many via an automated reclaim-sweep daemon, win-prob Brier-over-Elo gate, `brier_delta=-1.4e-05`, DM p=0.776 -- "priced/redundant over Elo") -- that closes assists as an INCREMENTAL WIN-PROB feature; this row is the prior descriptive question (is the trait itself stable and margin-linked at all), the same box-detail-family split already run for #34/#35. CONFIRMED here is consistent with REJECT there (real, stable trait; still priced by the market).
- **source**: "Analyzing the Impact of Pass Volume and Quality on Recent NBA Offenses" (NBA Math), https://nbamath.com/analyzing-the-impact-of-pass-volume-and-quality-on-recent-nba-offenses/ and "A Guide To Passing Stats" (Basketball Index), https://www.bball-index.com/a-guide-to-passing-stats/ -- assist-rate/passing-quality literature as the mechanistic basis; NBA Math's own note that raw pass volume alone is not sufficient is exactly why the split-half+margin design (not a raw-count claim) is used here.

---

## Validated 2026-07-10 (largest_lead persistence + Q4-home-edge, deep-bench drain lane)

### 40. Largest-lead persistence + margin-relation -- 4th box-detail row, extends the #34/#35/#36 triple-pass to the previously-untested `largest_lead` column already named as "unlocked" in the family header above
- **claim**: a team's largest_lead that game is a stable team trait (persists split-half) and relates to that game's scoring margin -- extends garbage-time bench inflation (#17 CONFIRMED) to a team-level blowout-tendency angle.
- **causal story**: teams that build large leads are systematically stronger/deeper (roster-quality trait), so largest_lead should be both a repeatable team characteristic and mechanically tied to margin.
- **caveat**: the margin-relation leg is expected to run high almost by construction (a bigger largest_lead directly implies a bigger final margin for winning teams) -- the persistence leg is the informative test here, same-game margin is confirmatory not novel.
- **test spec**: same design as #34/#35 (split-half Pearson r + same-game Pearson r vs margin), same corpus/thresholds.
- **status**: CONFIRMED_LOCAL
- **measured LOCAL magnitude**: persistence r=0.779, p=3.97e-7 (n=30 teams); margin relation r=0.845, p~0 (n=1,342 team-games).
- **artifact link**: `domains/basketball_nba/knowledge/validate_boxdetail_persistence.py::hypothesis("largest_lead")`.
- **wiring**: candidate for the interaction factory's box_detail family (`boxdetail_asof.py`'s `largest_lead_diff_asof`); same thin-slice caveat as #34/#35, not gated for a pregame outcome edge.

### 41. Home Q4-specific edge vs. own Q1-Q3 average -- LOCAL NULL ("clutch home cooking" literature)
- **claim**: the home team's Q4 scoring margin (own_q4-opp_q4) is systematically LARGER than its own average per-quarter margin across Q1-Q3, i.e. a home-court edge specifically concentrated in the final quarter (officiating/crowd-pressure literature), beyond the ordinary home-court advantage present in every quarter.
- **causal story**: officiating deference and crowd pressure are hypothesized to peak in close, late-game situations, which cluster in Q4.
- **expected signature**: positive mean(home_q4_margin - home_avg_other_quarter_margin), paired by game.
- **test spec**: paired one-sample t-test, home team's q4_margin vs (full_game_margin - q4_margin)/3, bar p<0.01 AND |gap|>=0.5 pts.
- **status**: REJECTED (NULL_LOCAL) -- gap is small and wrong-signed (home teams marginally UNDER-perform their own Q1-Q3 pace in Q4, not over-perform).
- **measured LOCAL magnitude**: gap=-0.168 pts, p=0.547 (n=1,313 home team-games).
- **artifact link**: `domains/basketball_nba/knowledge/validate_quarter_volatility.py::home_q4_edge_exceeds_other_quarters`.
- **wiring**: none -- honest null, no Q4-specific home-officiating effect detectable in this local corpus.

---

## Validated 2026-07-10 (Q3-state family -- B11 handoff, sim2 P3|m3 bucket mechanism seed)

sim2's global-worst PIT/CRPS bucket is `P3|m3` (period 3, off-relative margin
in `[-3,3)` per `possession_model.py::_MARGIN_EDGES` -- see
`domains/basketball_nba/sim2/validate_v3.py` `NAMED` list). These 2 rows seed
Q3-state hypotheses using ONLY on-disk realized quarter scores from BOTH
`linescores.parquet` (2025-26, 1,313 games) and `linescores_2024_25.parquet`
(2024-25, 1,321 games) -- 2 genuinely independent season corpora, not a
split-half of one. "First-half-realized" state (own_q1+own_q2 margin) is
legitimate in-game state (known at halftime), not a live-mid-Q3 feature.

### 45. Q3 margin vs halftime deficit (halftime-adjustment asymmetry / reversion) -- LOCAL NULL, both corpora
- **claim**: a team's Q3 own-margin correlates with its own first-half margin -- specifically, teams trailing at half show systematic Q3 recovery beyond noise (a coaching-adjustment or mean-reversion signature).
- **causal story**: halftime adjustments (schematic changes, rotation tweaks) or simple regression-to-team-quality would produce a negative slope -- bigger halftime deficit predicts bigger Q3 recovery (and the mirror for teams leading big).
- **expected signature**: pearson r(first_half_margin, q3_margin) reliably negative and non-trivial in magnitude, same sign in both corpora.
- **test spec**: pooled team-game pearson r (both home/away rows), declared bar |r|>=0.15 AND p<0.01, both season corpora.
- **status**: REJECTED (NULL, both corpora independently) -- no detectable relationship either direction.
- **measured LOCAL magnitude**: 2024-25 r=-0.0146, p=0.4521, n=2,642 team-games; 2025-26 r=0.0306, p=0.1171, n=2,626 team-games. Both far below the |r|>=0.15 bar and neither clears p<0.01 -- Q3 margin looks statistically unrelated to how a team's first half went, in either direction.
- **artifact link**: `domains/basketball_nba/knowledge/validate_q3_state.py::q3_margin_vs_halftime_deficit`.
- **read for P3|m3**: rules out "systematic halftime recovery/give-back" as the mechanism behind the sim's worst-calibrated bucket -- whatever makes P3|m3 hard to fit, it is not a first-half-margin-linear effect on Q3 scoring.

### 46. Q3 volatility elevated in games close at half -- PARTIAL (real vs Q2 in both corpora, real vs Q4 in only one)
- **claim**: restricted to games close at halftime (|first_half_margin|<3, the sim's own margin-bucket-3 edge), Q3's own-quarter-points distribution is more volatile (higher stdev) than Q2's and Q4's -- a candidate reason the simulator underfits exactly the P3|m3 state.
- **causal story**: a close game at half keeps both benches live (no early garbage-time damping of variance) while Q3 is also where the first real tactical counter-adjustments land, plausibly widening the realized-scoring distribution beyond Q2's more "settled" pattern.
- **expected signature**: Levene test, Q3 own-quarter-points stdev > both Q2's and Q4's, on the close-at-half subset, both corpora.
- **test spec**: Levene test (Q3 vs Q2, Q3 vs Q4), close-at-half subset only; declared bar p<0.01 AND Q3 stdev >=10% higher than the comparison quarter's, BOTH legs required per corpus for that corpus to count as confirmed.
- **status**: PARTIAL -- the Q3-vs-Q2 leg replicates cleanly in both corpora; the Q3-vs-Q4 leg only clears the bar in one.
- **measured LOCAL magnitude**: 2024-25 (n_close=468 team-games): Q3 std=9.447 vs Q2 std=6.089 (p=2.4e-18, clears) vs Q4 std=8.243 (p=0.00125, clears -- ratio 1.146). 2025-26 (n_close=394 team-games): Q3 std=9.004 vs Q2 std=6.121 (p=6.0e-12, clears) vs Q4 std=8.798 (p=0.672, MISSES -- ratio only 1.023). So "Q3 more volatile than Q2 in close games" is a real, replicated, honest partial finding; "Q3 more volatile than Q4 too" is not replicated.
- **artifact link**: `domains/basketball_nba/knowledge/validate_q3_state.py::q3_volatility_close_halftime`.
- **read for P3|m3**: a genuine, replicated lead (Q3-vs-Q2 elevated variance in tight games) worth carrying forward as a sim2 gate-candidate input in a LATER lane (sim2 modules are read-only here per this lane's charter) -- but it is PARTIAL, not CONFIRMED, and should not be treated as a full explanation of the bucket's miscalibration on its own.

---

## Validated 2026-07-10 (research-wave 2 -- literature-sourced, round-2 pool feedstock)

Fresh mechanism hypotheses from different literature areas than the
round-1 research wave (#42-44 above: defender-matchup skill, switch rate,
assist persistence). Checked against every row above and against
`data/frontend/reject_ledger.jsonl` (0 keyword hits for `timeout`/`rest_diff`
on sport=nba) before seeding, then validated same lane:
`domains/basketball_nba/knowledge/validate_research_wave2.py`, both rows
split-half by date (2 independent groups within this run, per this ledger's
own >=2-corpora discipline for an affirmative).

### 47. Timeout interrupts opponent scoring run (raw pre/post gap, not a causal claim)
- **claim**: a team calling a timeout while conceding an opponent scoring run sees that opponent's raw points-per-minute drop in the window immediately after the timeout vs the window immediately before -- the local descriptive gap this ledger can test, distinct from the harder causal question (below).
- **causal story**: a timeout lets the trailing team reset defensive matchups/set a play, which should interrupt an opposing run's rhythm in the immediate aftermath -- tested here as a raw paired before/after gap, same design family as the CONFIRMED red-card (soccer #8) and garbage-time (#17) paired-window tests already in this program.
- **expected signature**: opponent points-per-minute in a fixed window before the timeout is higher than in the window after (window capped at period boundary, min floor to avoid degenerate tiny windows).
- **test spec**: `domains.basketball_nba.knowledge.validate_research_wave2.timeout_interrupts_opponent_run` -- raw pbp corpus `data/nba/pbp_<game_id>_p1.json` (period-1 only, 1,289/3,611 games have a local file, 35.7% coverage, confirmed exactly this session, same corpus/coverage note as #39's foul-trouble-spillover row), timeout events identified via `event_desc` containing "Timeout", team_abbrev blank on these rows (confirmed), calling team resolved via `domains/basketball_nba/team_name_resolver.py`'s existing 30-team alias map (reused, not a new lookup); paired t-test opponent PPM in a 3-min window before vs 3-min window after (min 60s floor if truncated by a period boundary); declared bar |eff|>=0.3 pts/min AND p<0.01, split-half by date, both halves required.
- **spec nit**: the row as seeded said "paired Welch t-test" -- Welch's correction is for INDEPENDENT unequal-variance samples, not a paired before/after design on the same timeout event. Implemented as the paired t-test (`scipy.stats.ttest_rel`) the design actually calls for.
- **status**: CONFIRMED (REPLICATED -- second corpus 2026-07-10) -- the raw descriptive gap replicates cleanly, both halves of the original corpus AND a fully disjoint second corpus, same sign throughout, well past the declared bar; not a causal claim (see source note).
- **measured LOCAL magnitude**: h1 opponent PPM after-before mean diff=-0.7314, p=2.0e-65 (n=1,357 timeouts); h2 diff=-0.7308, p=1.5e-64 (n=1,355 timeouts) -- opponent scoring slows by ~0.73 pts/min in the 3 minutes after a timeout vs the 3 minutes before, both halves essentially identical in magnitude. Consistent with the source paper's own raw-gap finding (deficit narrowing 3.74->1.20 pts) -- this row deliberately tests only that raw gap, not the paper's harder causal (selection-confound-adjusted) question.
- **artifact link**: `domains/basketball_nba/knowledge/validate_research_wave2.py::timeout_interrupts_opponent_run` (function name kept from the seed; ledger hypothesis keys are `timeout_interrupts_opponent_run__h1`/`__h2`/`__combined`).
- **replication (2026-07-10)**: REPLICATED on the 2022-23 season (1,230 local pbp games, fully disjoint from the original's 2023-24-dominant pool -- `player_boxscores.parquet`, the original's box source, has zero 2022-23 rows). Same design/bars ported verbatim -- ALPHA=0.01, MIN_EFFECT=0.3 pts/min, MIN_GROUP_N=20 unchanged, `game_samples`/`_paired_verdict` reused directly. Split-half: h1 eff=-0.6917 p=6.3e-58 (n in h1+h2=2,544 timeouts), h2 eff=-0.6564 p=1.8e-48 -- both halves CONFIRMED_LOCAL, same (negative) sign, magnitude close to the original's ~-0.73. `domains/basketball_nba/knowledge/validate_replication_wave1.py::timeout_interrupts_opponent_run_replication_2022_23`; `validation_ledger.jsonl` hypothesis=`timeout_interrupts_opponent_run_replication_2022_23`.
- **premise-check note**: the task brief assumed a "2024-25 pbp" second corpus; disk check found that 2024-25 pbp coverage (48 games) is already folded inside the original's pooled 1,289-game corpus (not independent) and too thin to stand alone. The 2022-23 season was used instead -- comparable size (1,230 vs the original's 1,230-dominant 2023-24 games), genuinely disjoint, no box-score join required (raw pbp + `games.parquet` date only).
- **source**: "The causal effect of a timeout at stopping an opposing run in the NBA" (Brill, Wyner et al., Annals of Applied Statistics / arXiv:2011.11691), https://arxiv.org/abs/2011.11691 -- finds a raw pre/post-timeout scoring-gap narrowing locally (opponent deficit 3.74->1.20 pts in the surrounding minute in their corpus) but a near-zero-to-slightly-negative CAUSAL effect once the selection confound (timeouts are called precisely during opponent runs) is accounted for. This row tests only the local RAW descriptive gap, explicitly not a causal claim -- an honest scope match to what a paired before/after design can actually support.

### 48. Rest-days DIFFERENTIAL between the two competing teams predicts margin (distinct from #14/#15's single-team-own-rest tests)
- **claim**: the rest-days gap BETWEEN the two teams in a game (home `rest_days` minus away `rest_days`) predicts point margin beyond what either team's own isolated rest state (#14 CONFIRMED b2b-vs-rested; #15 REJECTED three-in-4) already captures -- neither existing row conditions on the OPPONENT's simultaneous rest state.
- **causal story**: cited Wharton research finds the home ATS edge is driven by the RELATIVE rest gap (it shrinks/reverses specifically when the away team is comparably or better rested), not just whether the home team itself is tired in isolation.
- **expected signature**: positive Pearson r between `rest_diff` (home rest_days minus away rest_days) and home team's margin.
- **test spec**: `domains.basketball_nba.knowledge.validate_research_wave2.rest_differential_margin` -- `domains/basketball_nba/knowledge/_data.py::team_game_frame(load_player_boxscores())` (confirmed columns `game_id`/`team`/`is_home`/`rest_days`/`margin`, 7,222 team-games, confirmed exactly this session) self-joined on `game_id` to pair each game's home row against its away row, `rest_diff = home.rest_days - away.rest_days`, both sides' `rest_days` non-null; Pearson r vs home margin; declared bar |r|>=0.05 AND p<0.01, split-half by date, both halves required.
- **status**: REJECTED (NULL_LOCAL, both halves independently) -- no detectable relationship either direction, at a stricter effect floor (|r|>=0.05) than #14/#15 even used.
- **measured LOCAL magnitude**: h1 r=-0.0180, p=0.4445 (n=1,798 paired games); h2 r=-0.0105, p=0.6567 (n=1,798 paired games). Both far below the |r|>=0.05 bar and neither clears p<0.01 -- the home-minus-away rest gap does not predict home margin in this local corpus, distinct from (and not explained away by) the CONFIRMED single-team B2B effect (#14): b2b_rest_penalty fires on a team's OWN rest state regardless of the opponent's, this row's relative-gap framing does not add anything beyond it locally.
- **artifact link**: `domains/basketball_nba/knowledge/validate_research_wave2.py::rest_differential_margin` (ledger hypothesis keys `rest_differential_margin__h1`/`__h2`/`__combined`).
- **source**: "The Role of Rest in the NBA Home-Court Advantage" (Oliver Entine & Dylan Small, Wharton), https://faculty.wharton.upenn.edu/wp-content/uploads/2012/04/Nba.pdf -- finds home ATS win% (~50.6% when both teams equally rested/unrested) drops meaningfully once the rest gap shifts toward the away team, i.e. the differential (not a single team's own isolated rest state) is the literature's own framing of the mechanism. Not replicated locally (own-team B2B rest, #14, is the effect that survives here).

---

## Validated 2026-07-10 (research-wave 3 -- literature-sourced, round-3 pool feedstock)

Fresh mechanism hypotheses targeting the sim2 worst-bucket family via blowout-
rotation angles (P4|m2 clutch-lineup-shortening is already CLOSED/gated into
sim2 per commit 90bc1b9e -- #24/#18 below, NOT re-proposed). Checked against
every row above (especially #17 CONFIRMED bench-production, #18 CONFIRMED-
REVERSED clutch usage, #24 CONFIRMED clutch-lineup-shortening) and against
`data/frontend/reject_ledger.jsonl` (535 rows, 0 keyword hits for `garbage`/
`blowout`/`starter.?rest`) before seeding. Validated same night by
`validate_research_wave3.py`: #49 CONFIRMED_LOCAL (blowout-margin starter-
minutes proxy, both halves), #50 REJECTED (b2b x margin interaction, both
halves NULL).

### 49. Blowout margin threshold effect on starter minutes allocation (final-margin proxy for live win-probability garbage-time detection)
- **claim**: a team's STARTERS collectively play fewer total minutes as the final game margin widens -- distinct from #17 (CONFIRMED bench PRODUCTION per-minute in blowouts) which never tests starter minutes ALLOCATION, and from #24 (CONFIRMED clutch-specific rotation shrinkage, now sim2-gated) which is scoped to clutch state only, not blowout margin generally.
- **premise check**: the literature's own methodology (Cleaning the Glass, via Ben Falk) defines garbage time as a graduated time-remaining x margin threshold PLUS a live count of original starters still on court -- true live per-play lineup-by-clock data does not exist locally outside the period-1-only PBP text files (35.7% coverage, same corpus as #39/#47, and those carry event descriptions, not continuous on-court personnel). This row is therefore an honest SCOPE REDUCTION to a season-level final-margin proxy (total starter minutes per team-game vs final margin bucket), not a live-threshold replication of the CtG methodology itself.
- **causal story**: coaches pull starters once a game's outcome is effectively decided, to rest them and avoid injury risk in a low-value game state; a wider final margin should correlate with fewer total starter minutes that game.
- **expected signature**: negative relationship between |final margin| and summed starter minutes per team-game, roughly monotonic across increasing margin buckets (e.g. <10, 10-19, 20-29, >=30).
- **test spec**: `domains.basketball_nba.knowledge.validate_research_wave3.starter_minutes_vs_margin` -- per team-game, sum `min` where `starter==1` from `player_boxscores.parquet` (confirmed columns `game_id`/`team`/`starter`/`min`, 77,744 rows), joined to `domains/basketball_nba/knowledge/_data.py::team_game_frame`'s per-team-game `margin` (reused helper, confirmed present), bucketed by `|margin|` bands; Kruskal-Wallis across bands + linear trend test on band-midpoint vs mean starter-minutes; declared bar trend slope <=-0.05 min/margin-point AND p<0.01, split-half by date.
- **status**: CONFIRMED_LOCAL -- the trend replicates cleanly, both halves, same (negative) sign, well past the declared bar; expected given the direct final-margin proxy this row scopes itself to (not a claim about live in-game garbage-time detection, see premise-check scope reduction above).
- **measured LOCAL magnitude**: h1 band-midpoint trend slope=-1.0689 min/margin-pt, p=0.0030 (n=3,612 team-games, 4 margin bands); h2 slope=-0.9262, p=0.0017 (n=3,610 team-games). Both halves clear the <=-0.05 bar by roughly 20x; band means fall monotonically 159.3 -> 151.6 -> 139.6 -> 129.9 minutes across the <10/10-19/20-29/>=30 margin bands. Kruskal-Wallis across the raw per-band distributions is also significant both halves (h1 H=826.5 p=8e-179; h2 H=742.1 p=2e-160) -- consistent with the season-level proxy this row declared, not with live in-game garbage-time detection.
- **artifact link**: `domains/basketball_nba/knowledge/validate_research_wave3.py::starter_minutes_vs_margin` (ledger hypothesis keys `starter_minutes_vs_margin__h1`/`__h2`/`__combined`).
- **source**: "What is Garbage Time in the NBA? Definition and Methodology" (Hoops Junkie, summarizing Cleaning the Glass/Ben Falk's time-based-threshold + starters-on-court-count methodology), https://hoopsjunkie.io/methodology/garbage-time; "Estimating an NBA player's impact on his team's chances of winning" (arXiv:1604.03186), https://arxiv.org/pdf/1604.03186 -- both establish garbage time as a live win-probability-adjacent state that down-weights performance and that coaches respond to by altering rotations; the local test proxies the live threshold with the only outcome the corpus actually supports (final margin, season-aggregated), stated explicitly as a scope reduction rather than a full replication.

### 50. Back-to-back rest status moderates how sharply starter minutes fall in a blowout (schedule-fatigue x margin interaction)
- **claim**: the blowout-margin effect on starter minutes (row #49) is STEEPER for teams on zero rest (`rest_days==0`, the CONFIRMED #14 b2b-penalty definition) than for rested teams -- a genuinely new interaction (schedule state x margin), distinct from #14 (standalone b2b margin effect, no minutes-allocation outcome) and #49 (margin-only, no rest interaction).
- **causal story**: a coach managing a tired roster (b2b) has an added incentive -- beyond the blowout itself -- to shut starters down early once a big lead/deficit is established, compounding the #49 mechanism with schedule-fatigue risk management.
- **expected signature**: negative `rest_days==0 x |margin|` interaction coefficient on starter total minutes (b2b teams' starter-minutes drop faster per point of margin than non-b2b teams').
- **test spec**: `domains.basketball_nba.knowledge.validate_research_wave3.b2b_x_margin_starter_minutes` -- OLS `starter_minutes ~ abs_margin + is_b2b + abs_margin:is_b2b`, same per-team-game starter-minutes ingredient as #49, `is_b2b = (rest_days==0)` (reuses #14's exact definition from `validate_schedule_fatigue.py::b2b_rest_penalty`), `player_boxscores.parquet` team-game frame; declared bar |interaction coef|>=0.05 AND p<0.01, split-half by date.
- **status**: REJECTED (NULL_LOCAL, both halves independently) -- no detectable b2b x margin interaction on top of the standalone #49 effect.
- **measured LOCAL magnitude**: h1 interaction coef=-0.0372, p=0.624 (n=3,596 team-games, 622 on zero rest); h2 coef=-0.0998, p=0.162 (n=3,596 team-games, 656 on zero rest). Neither half clears p<0.01 and h1 doesn't even clear the |0.05| magnitude floor -- the direction is consistent with the causal story (both coefs negative) but far too noisy to call, distinct from (and not explained away by) #49's own robust standalone margin effect, which holds regardless of rest state.
- **artifact link**: `domains/basketball_nba/knowledge/validate_research_wave3.py::b2b_x_margin_starter_minutes` (ledger hypothesis keys `b2b_x_margin_starter_minutes__h1`/`__h2`/`__combined`).
- **source**: same Hoops Junkie/CtG methodology reference as #49 for the blowout-rotation mechanism, combined with "The Role of Rest in the NBA Home-Court Advantage" (Entine & Small, Wharton), https://faculty.wharton.upenn.edu/wp-content/uploads/2012/04/Nba.pdf (already cited for #48's rest-differential row) -- this row is the first to interact the two established schedule/margin mechanisms rather than testing either standalone.

### 51. Q1-lead extension beyond a naive AR(1) model, in the Q2 that follows (sim2 P2|m6 bucket target)
- **claim**: teams already up/down >=15 after Q1 (sim2's own top margin-bucket edge, `_MARGIN_EDGES[-1]` in `possession_model.py`) extend that lead in Q2 by MORE than a naive AR(1) fit on moderate-lead games (|q1_margin|<15) would predict -- the tail does not follow the population trend.
- **causal story**: a big Q1 lead lets the leading team control tempo/shot selection and lets the trailing team's rotation/effort sag before it's a true "garbage time" margin; a flat, population-average AR(1) possession-transition model (which sim2's v2 baseline effectively is) systematically understates this specific tail dynamic, which is exactly why P2|m6 (n=65, rank-4 worst bucket, no mechanism previously mapped per `docs/research/sim_heatmap_bucket_sweep_2026-07-10.md`) miscalibrates.
- **expected signature**: positive mean signed AR(1) residual (residual = actual Q2 own-margin minus the moderate-lead-fit AR(1) prediction, sign-flipped to the Q1 lead's own direction) for the |q1_margin|>=15 subset, both season corpora.
- **test spec**: `domains.basketball_nba.knowledge.validate_q2_blowout_state.q2_lead_extension_beyond_ar` -- AR(1) slope/intercept fit via `scipy.stats.linregress(q1_margin, q2_margin)` on moderate-lead team-games only, applied out-of-subset to the extreme-lead team-games; one-sample t-test of the signed residual vs 0; declared bar p<0.01 AND |mean signed residual|>=1.0 pt; two independent season corpora (`linescores.parquet` 2025-26, `linescores_2024_25.parquet` 2024-25), reusing `validate_q3_state.py::team_game_quarters`/`load_all_corpora` verbatim for the q1_margin/q2_margin ingredient.
- **status**: CONFIRMED (REPLICATED, both corpora)
- **measured LOCAL magnitude**: 2024-25: n_extreme=244, ar_slope=-0.0669, signed_resid_mean=+1.557 pts, p=0.0079; 2025-26: n_extreme=232, ar_slope=-0.0589, signed_resid_mean=+2.282 pts, p=3.4e-05. Both corpora clear the declared bar with the same (extension) sign -- big Q1 leads extend roughly 1.5-2.3 points further into Q2 than the moderate-lead AR(1) trend alone would predict.
- **artifact link**: `domains/basketball_nba/knowledge/validate_q2_blowout_state.py::q2_lead_extension_beyond_ar`; `domains/basketball_nba/knowledge/validation_ledger.jsonl`, hypothesis=`q2_lead_extension_beyond_ar`.
- **wiring**: sim2 gate-candidate ingredient for P2|m6 -- an asymmetric lead-extension adjustment (rather than a flat AR-implied margin transition) at |off_margin|>=15 entering/during Q2; not yet gated into a v3 candidate, this row only establishes the mechanism exists and replicates.

### 52. Q1-lead magnitude does NOT add incremental starter-minutes signal beyond #49's final-margin effect
- **claim (as seeded)**: in games where a team already has a big Q1 lead (proxy for "already in a Q2 blowout state," the sweep note's "bench-lineup exposure in Q2 blowout states" hypothesis for P2|m6), that team's starter minutes THAT game are reduced beyond what mechanism #49 (CONFIRMED_LOCAL, blowout FINAL margin -> fewer starter minutes) already explains -- i.e. early-blowout timing itself, not just final margin, drives extra bench deployment.
- **causal story (as seeded)**: a coach who sees a 15+ point lead already established after one quarter has an earlier signal to rest starters than one inferred only from the FINAL margin, so Q1-lead magnitude should carry incremental information over final |margin| alone.
- **expected signature**: negative, p<0.01 partial coefficient on `q1_blowout` (|q1_margin|) in `starter_minutes ~ abs_margin + q1_blowout`, controlling for final |margin|.
- **test spec**: `domains.basketball_nba.knowledge.validate_q2_blowout_state.q2_blowout_early_bench_deployment` -- OLS `starter_minutes ~ abs_margin + q1_blowout`; `abs_margin`/`starter_minutes` reused verbatim from `validate_research_wave3.py::build_dataset` (#49's own ingredient); `q1_blowout` = |q1_margin| from linescores (both season corpora), joined on date+team via `domains.basketball_nba.team_name_resolver.resolve` (normalizes ESPN abbreviations, e.g. "GS", to the box-score corpus key "GSW"); declared bar coef<=-0.05 AND p<0.01, split-half by date (mirrors #49/#50's own split-half discipline).
- **status**: REJECTED (NULL_LOCAL, both halves independently) -- no detectable incremental Q1-lead-timing effect on top of #49's standalone final-margin effect.
- **measured LOCAL magnitude**: h1 coef=-0.1121, p=0.0951 (n=2,390 joined team-games); h2 coef=-0.1492, p=0.0259 (n=2,372 joined team-games). Both halves are negative (direction matches the causal story) but neither clears p<0.01 -- final margin already captures the coach's substitution response; Q1-lead TIMING adds no statistically robust signal beyond it. This rules out early-bench-deployment timing as the specific driver of P2|m6's miscalibration (see #51 for the mechanism that DID replicate on this bucket).
- **artifact link**: `domains/basketball_nba/knowledge/validate_q2_blowout_state.py::q2_blowout_early_bench_deployment`; `domains/basketball_nba/knowledge/validation_ledger.jsonl`, hypothesis=`q2_blowout_early_bench_deployment`.

### 53. Q2 foul/pace-state interaction with lead size -- NOT_TESTABLE (no quarter-level ingredient on disk)
- **claim**: a large Q1/Q2 lead interacts with foul rate or pace state to change Q2 scoring dynamics (e.g. a trailing team fouling more, or pace slowing as a leading team protects the ball).
- **premise check**: fresh disk check this session -- `four_factor_env.parquet` is a team-SEASON aggregate (n=30 rows, one per team, no foul column at all, `poss_pg` is the only pace-adjacent column and it too is season-level); `player_boxscores.parquet`'s `pf` column is a game-TOTAL, not quarter-split; `linescores.parquet` carries points per quarter only, no foul or pace columns. No quarter-level foul or pace ingredient exists anywhere in the local corpus.
- **status**: NOT_TESTABLE
- **artifact link**: `domains/basketball_nba/knowledge/validate_q2_blowout_state.py::q2_foul_pace_state_interaction`; `domains/basketball_nba/knowledge/validation_ledger.jsonl`, hypothesis=`q2_foul_pace_state_interaction`.
- **note**: closes this sub-question of the P2|m6 bucket-mapping search rather than leaving it silently untried; would need a new PBP-derived quarter-foul/quarter-pace build to test, out of scope for this session.

---

## Seeded 2026-07-10 (research-wave 4 -- literature-sourced, UNTESTED, round-4 pool feedstock)

Fresh mechanism hypothesis on officiating-crew pace/whistle tendencies,
scoped IDENTITY-FREE (no referee/crew-identity column exists locally),
mirroring MLB's own identity-free called-strike-dispersion design (#39 in
that ledger). Checked against every row above and against
`data/frontend/reject_ledger.jsonl` (535 rows, 0 keyword hits for
`officiat`/`whistle`/`crew`/`referee.*pace`) before seeding. Full premise
check + dropped-candidate note: `docs/research/research_seed_wave4_2026-07-10.md`.
No validator built this lane.

### 54. Per-game whistle-tightness disperses beyond a team-adjusted Poisson null (identity-free, mirrors MLB #39)
- **claim**: after netting out each team's own season-average personal-foul rate (removing which two teams are playing), the residual game-level total personal-foul count still varies across games by more than Poisson sampling noise alone would produce -- i.e. a real per-game environmental factor exists (crew assignment, that night's whistle tightness, game flow) beyond team identity, without needing to attribute it to a specific referee.
- **causal story**: cited officiating-analytics coverage (DonaghyEffect, NBAstuffer) documents that NBA crews carry real, non-random foul-volume tendencies -- some crews average meaningfully more fouls/game than others, moving pace and free-throw volume by several points of total; the local corpus has no crew-identity column to test that directly, so this row tests the identity-free residual-dispersion signature the same way MLB #39 tested "does per-game called-strike rate vary beyond binomial noise" without ever claiming a specific umpire is responsible.
- **expected signature**: quasi-Poisson dispersion ratio phi = chi2/df meaningfully above 1.0 on the team-baseline-adjusted residual game-total-PF series (declared bar phi>=1.15 AND p<0.01 -- set slightly below MLB #39's 1.2 bar because a team-baseline adjustment, not a raw pooled rate, is used here, so residual variance should already be closer to pure noise if no real per-game factor exists).
- **test spec**: `domains.basketball_nba.knowledge.validate_research_wave4.foul_rate_dispersion_exceeds_poisson_noise` (not yet built) -- aggregate `data/domains/basketball_nba/player_boxscores.parquet` (confirmed columns `game_id`/`team`/`pf`, 77,744 rows) via `groupby(game_id,team)['pf'].sum()` to team-game PF, join each team's own season-mean PF (leave-one-out, excluding the target game, to avoid circularity) as that team's expected contribution, sum both teams' expected values to get each game's model-implied lambda, sum both teams' actual PF for the observed game-total; chi2 = sum((observed_g - lambda_g)^2 / lambda_g) ~ chi2(n_games-1) under the team-adjusted-Poisson null; phi=chi2/(n_games-1) is the effect size, full 3,611-game corpus (or a season-split subset if leave-one-out season means require a same-season floor), split-half by date for the 2-corpora replication bar.
- **status**: PROVISIONAL -- split-half by date: h1 (n=1806 games) phi=1.106 p=0.00099, does NOT clear the declared phi>=1.15 bar; h2 (n=1805 games) phi=1.184 p=8.9e-08, clears the bar. Only 1 of 2 replication groups confirms -- an honest single-half result, not a 2-corpora replication, so held at PROVISIONAL rather than promoted to CONFIRMED_LOCAL.
- **artifact link**: `domains/basketball_nba/knowledge/validate_research_wave4.py::foul_rate_dispersion_exceeds_poisson_noise`; `domains/basketball_nba/knowledge/validation_ledger.jsonl`, hypothesis=`foul_rate_dispersion_exceeds_poisson_noise__combined` (+ `__h1`/`__h2`).
- **source**: "How NBA Referees Affect Betting Lines, Totals & Player Props" (DonaghyEffect), https://www.donaghyeffect.com/nba/referees/explained -- documents that crews carry consistent foul-volume tendencies (some officials averaging notably more fouls/game than others) that measurably shift expected game totals; "The Referee Effect in the NBA" (NBAstuffer), https://www.nbastuffer.com/the-referee-effect-in-the-nba/ -- companion coverage of the same crew-tendency pattern. Neither source requires or provides individual-referee attribution on our local corpus; this row tests only the identity-free residual-dispersion signature their aggregate claims imply should exist.

---

## Seeded 2026-07-10 (research-wave 5 -- literature-sourced, UNTESTED, round-5 pool feedstock)

Fresh mechanism hypothesis on schedule-level roster stability (between-game
starting-lineup continuity), scoped explicitly DISTINCT from #1/#11/#30
(all within-game stint-composition tests) and from the A10a "chemistry
atlas cols" note (`.planning/ULTRA_DONE.md` line 102, `chemistry_score_std`/
`_median` -- CLOSED_CONFIRMED dead/no-action, an unrelated lineup_synergy
distribution-shape column this row does not touch). Checked against every
row above and against `data/frontend/reject_ledger.jsonl` (535 rows, 0
keyword hits for `roster`/`lineup_stab`) before seeding. No validator built
this lane.

### 55. Between-game starting-lineup continuity (roster-stability streak) vs point differential
- **claim**: a team's continuity streak -- consecutive games with an unchanged 5-man OPENING lineup -- predicts that game's point differential, a schedule-level roster-stability signal distinct from #1 (within-game stint-seconds continuity x DREB), #11 (continuity x starter-disruption, NULL x3) and #30 (bench-stint continuity, reversed sign) -- none of which test between-game lineup persistence.
- **premise check**: `data/cache/team_system/lineups/stints_2023_24.parquet` / `stints_2024_25.parquet` confirmed this session -- columns `game_id`/`team_id`/`period`/`lineup_key`/`start_s`/`pts_for`/`pts_against` present; opening lineup (first `period==1` stint by `start_s`) gives 2,460 team-game rows/season (30 teams x ~1,230 games); same-as-prior-game exact lineup_key match rate=42.9% (2024-25) -- a real, non-degenerate binary, not a rare or frozen event.
- **causal story (confound flagged honestly)**: an unchanged starting 5 game-to-game is close to tautological for a currently healthy/undisrupted roster, so a positive effect here more plausibly reflects "team is healthy right now" than genuine chemistry accrual -- still a distinct, worth-testing schedule-level signal separate from the within-game stint-composition mechanisms already closed above; any CONFIRMED result should be read as a health/availability proxy, not a chemistry claim, until an injury-report control is added.
- **expected signature**: positive relationship, continuity-streak length (or same-as-prior binary) vs that game's point differential (`pts_for`-`pts_against` summed across all stints for the team-game).
- **test spec**: `domains.basketball_nba.knowledge.validate_research_wave5.lineup_continuity_streak_vs_point_diff` (not yet built) -- per (game_id,team_id) opening lineup_key = first `period==1` stint by `start_s`; sort each team's games by `game_id` (chronological proxy, same convention used elsewhere in this repo); continuity_streak = count of consecutive prior games with identical opening lineup_key; Pearson r, streak_length vs point_diff; declared bar |r|>=0.05 AND p<0.01 (large-n floor, ~2,460 rows/season); 2023-24 vs 2024-25 as the two independent-corpora replication legs (2025-26, in progress at 1,192/1,230 games, held out).
- **status**: UNTESTED
- **source**: "Continuity Rankings: Breaking down roster turnover for all 30 teams" (NBA.com, 2025), https://www.nba.com/news/2025-continuity-rankings; "Roster Continuity" (Basketball-Reference), https://www.basketball-reference.com/friv/continuity.html -- both document roster/lineup continuity as a real, measured league construct, but explicitly note the relationship to performance is NOT a straightforward direct predictor (a low-continuity team improved +11.1 net rating one year; a high-continuity team declined) -- literature basis for treating this as a genuinely open empirical question, not an assumed-positive one, worth testing directly on the local stint corpus.
