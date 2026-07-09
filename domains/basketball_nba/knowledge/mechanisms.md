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
(this session's 10 fresh validations, 2,381-game 2024-25 + 2025-26
`player_boxscores.parquet` corpus). No `$` edge is claimed anywhere in this
file.

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

## Seeded, UNTESTED (highest-leverage remaining)

### 24. Clutch lineup shortening
- **claim**: coaches shorten their rotation specifically in clutch minutes (distinct from #21's overall-game rotation stability).
- **causal story**: trust narrows under pressure -- fewer players see clutch possessions than see full-game minutes.
- **expected signature**: distinct-player-count in clutch possessions (via `pbp_clutch_shots_attempted`/`pbp_clutch_pts_scored` nonzero rows) smaller, per team-game, than the game's overall rotation size.
- **test spec**: paired comparison, clutch-rotation-size vs full-game-rotation-size, same team-games.
- **status**: UNTESTED

### 25. Rim-pressure defensive continuity x DREB
- **claim**: a lineup's interior defensive-pressure attribute (`rim_pressure_def`, currently DESCRIPTIVE) predicts team DREB rate.
- **causal story**: contesting rim shots and controlling paint positioning should translate into more contested-rebound opportunities won.
- **expected signature**: positive correlation, rim_pressure_def vs on-court DREB rate.
- **test spec**: stint-level regression using `zone_onoff.py`'s per-player rim on/off splits joined to stint DREB outcome.
- **status**: UNTESTED

### 26. Usage-redistribution persistence after a high-usage player is out
- **claim**: when a high-usage player sits, the redistributed usage among remaining players follows a predictable (not random) pattern that persists across multiple absences.
- **causal story**: a team's offensive hierarchy has a stable "next man up" order, not a uniform spread.
- **expected signature**: split-half correlation of each teammate's usage-share gain across two different absence occasions for the same missing star.
- **test spec**: reuse `data/cache/team_system/interactions/usage_redistribution_*.parquet`; split-half by absence occasion.
- **status**: UNTESTED

### 27. Assist-network hub dependency
- **claim**: teams whose assist network concentrates through one "hub" passer are more efficient offensively than teams with a flat network, up to a point.
- **causal story**: a stable primary facilitator creates predictable movement patterns and better shot quality, but over-concentration invites defensive keying.
- **expected signature**: an inverted-U relationship between hub-concentration (e.g. top passer's share of team assists) and offensive rating.
- **test spec**: team-season hub-concentration vs offensive rating, quadratic term test.
- **status**: UNTESTED

### 28. Transition-frequency pace mismatch (distinct from overall pace variance, #22)
- **claim**: a team's transition-possession rate specifically (not overall pace) predicts its efficiency edge against slow-transition-defense opponents.
- **causal story**: transition offense exploits opponents who are specifically slow getting back, not just opponents who play a slow overall pace.
- **expected signature**: positive interaction, own transition-rate x opponent transition-defense-allowed-rate, on points/possession.
- **test spec**: game-level interaction using `atlas_team_transition_defense.parquet`'s transition_freq (noting its own ~50%-opponent-mixed caveat).
- **status**: UNTESTED

### 29. Clutch free-throw pressure dip
- **claim**: FT% drops in clutch situations (last 5 min, close game) relative to a player's season FT%.
- **causal story**: crowd noise, fatigue, and stakes-driven mechanical tightening reduce free-throw consistency under pressure.
- **expected signature**: negative gap, clutch FT% - season FT%, for players with a meaningful clutch-FTA sample.
- **test spec**: player-season FT% (from `player_boxscores.ftm/fta`) vs clutch-window FT% (from `pbp_clutch_shots_attempted`-adjacent clutch tracking, needs a clutch-FT-specific column check first).
- **status**: UNTESTED

### 30. Second-unit (bench lineup) continuity effect
- **claim**: continuity's DREB benefit (#1) is at least as strong for bench-only lineups as for starter-heavy lineups.
- **causal story**: chemistry effects should be lineup-composition-agnostic if the mechanism is genuinely about shared repetitions, not about individual starter talent.
- **expected signature**: a continuity-s coefficient on DREB rate of similar magnitude when the stint sample is restricted to bench-heavy lineups (majority non-starters on court).
- **test spec**: same regression as #1, restricted subsample by starter-count on court.
- **status**: UNTESTED

### 31. Travel/time-zone fatigue (distinct from simple rest-days, #14)
- **claim**: a team crossing 2+ time zones for a road game underperforms its rest-days-adjusted expectation.
- **causal story**: circadian disruption is a real physiological cost beyond a simple day-count.
- **expected signature**: negative residual margin (after controlling for rest_days) for cross-time-zone road games.
- **test spec**: needs a per-game travel-distance/time-zone-delta ingredient -- not present in `player_boxscores.parquet`/`league_team_game.parquet`; likely NOT_TESTABLE pending an arena-location join.
- **status**: UNTESTED

### 32. Foul-trouble minutes reduction (early foul trouble)
- **claim**: a starter who picks up 2 fouls in the first half plays fewer total minutes than his season average that game.
- **causal story**: coaches sit players in early foul trouble to avoid disqualification risk, at some node cost.
- **expected signature**: negative gap, actual minutes vs season-average minutes, on early-foul-trouble games.
- **test spec**: needs a foul-by-quarter/foul-by-time column; `player_boxscores.parquet` only has game-total `pf`, so this is likely NOT_TESTABLE on the current corpus pending a quarter-level box ingredient (see `ingest_quarter_box.py`, which may already carry this -- check before re-seeding as UNTESTED next session).
- **status**: UNTESTED

### 33. Star-injury usage-vacuum overreaction (market/pricing angle, calibration only)
- **claim**: when a star is ruled OUT, the market/model over- or under-estimates the redistributed production for teammates in the first 1-2 games back.
- **causal story**: usage redistribution (#26) takes a game or two to stabilize; an early-game projection that assumes instant full redistribution will systematically miss.
- **expected signature**: teammate production in game 1 without the star undershoots the season-long redistribution average; games 2+ converge.
- **test spec**: event-study style, teammate usage-share by games-since-absence-started.
- **status**: UNTESTED
