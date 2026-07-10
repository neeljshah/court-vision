# Soccer Mechanism Ledger

One entry per mechanical belief the system holds about soccer, with a
receipt. Fields, always in this order: **claim | causal story | expected
signature in our data | test spec | status | measured LOCAL magnitude |
artifact link**.

Status values: `UNTESTED` (seeded, not yet run against local data),
`CONFIRMED` (survived a leak-free local test, ideally replicated),
`REJECTED` (tested locally and failed, or failed cross-corpus replication),
`PARTIAL` (mixed verdict across corpora), `NOT_TESTABLE` (the ingredient
this mechanism needs does not exist, or exists too sparsely, in our local
corpus -- an honest gap, not a failure).

Local corpus: StatsBomb open-data event cache, `data/cache/statsbomb/events/*.json`
(~3,400 cached matches, used for within-match structural checks) and
`data/cache/statsbomb/match_meta.parquet` (400 matches with date/home-away/
final-score -- corpus A = Premier League 2015/16 men's, corpus B = FA WSL
women's, used for anything needing date or a completed result). This
session's fresh receipts live in `domains/soccer/knowledge/validation_ledger.jsonl`.
No `$` edge is claimed anywhere in this file -- every magnitude below is a
calibration/mechanism receipt, not ROI.

---

## Pre-adjudicated (do NOT re-test -- closed classes, cited from git history)

### 1. Possession-tier x press-style pairing -- ghost effect under strength control
- **claim**: a team's possession tier paired with its pressing style predicts match outcome beyond either factor alone.
- **causal story**: possession-heavy teams that also press high should compound an advantage (territorial control + fast recovery); the interaction, not just each ingredient, should carry signal.
- **expected signature**: an outcome-spread gap between style-pairing cells that survives controlling for team strength.
- **test spec**: style-fingerprint x press-tier pairing cells, 25,834 matches, outcome spread before/after a team-strength control.
- **status**: REJECTED (the pairing effect is a ghost -- it collapses under strength control)
- **measured LOCAL magnitude**: 0.341 outcome spread collapses to 0.064 once team strength is controlled for -- possession-tier pairing mostly just proxies team strength, not an independent interaction.
- **artifact link**: commit `07c771d0a1f0148cf61fed85a3b9762dc6f63c12` "feat(soccer+tennis): style/serve-return interaction layers -- one real survivor"; `domains/soccer/style_fingerprints.py`, `domains/soccer/style_interaction.py`. (The tennis half of that same commit, serve-tier x return-tier, DID survive rank-tercile control -- noted here only for contrast; that finding belongs to the tennis ledger, not this one.)

### 2. (Team, time, score)-state-conditioned shot model -- REPLICATED NULL vs naive baseline
- **claim**: conditioning shot frequency on (team, time-bucket, score-bucket) beats a naive per-team constant shot-rate baseline.
- **causal story**: teams should shoot more/less depending on game state (chasing a deficit, protecting a lead, garbage time) -- state-conditioning should sharpen the shot-frequency model over a flat per-team rate.
- **expected signature**: lower possession-level log-loss and match-level Brier for the state-conditioned model vs the naive constant-rate model, replicated across two independent corpora.
- **test spec**: empirical P(shot | team, time_bucket, score_bucket) with team->league backoff, MC-chained through 6 time buckets to full-match goal totals; walk-forward 70/30 split per corpus; two independent corpora (A = EPL 2015/16, B = FA WSL).
- **status**: REJECTED (REPLICATED NULL -- state conditioning does not beat the naive baseline in either corpus)
- **measured LOCAL magnitude**: possession-level log-loss A: 0.3757 (model) vs 0.3694 (naive); B: 0.3548 vs 0.3504. Match-level home-win Brier A: 0.2482 vs 0.2424; B: 0.1960 vs 0.1955. Naive baseline wins narrowly in all four readings. Corpus B ALSO loses on total-goals CRPS vs a per-corpus Poisson-climatology baseline: model 0.9773 vs climatology 0.8867 (`model_beats_climatology_crps: false`) -- a second, previously-invisible miss on top of the Brier loss above, from the same `soccer_chain_engine_v1.json` artifact.
- **artifact link**: commit `dd33ce8a9dc16373b04eea3f060ed49e80e88d91` "feat(soccer): possession-chain engine v1"; `domains/soccer/chain_engine/{corpus.py,shot_model.py,match_sim.py}`; `data/frontend/ops/soccer_chain_engine_v1_scoreboard.json`. Honest REJECT of possession-state conditioning as scoped (team+time+score cells only) -- not a claim of "no signal in soccer" generally; the commit itself flags this as a v2-corpus-expansion opportunity (only 400 of 3,443 cached matches have match_meta built).

### 3. Governing leak rule: never replay a static predictor's state through time without an as-of cutoff
- **claim**: methodology mechanism, not a testable domain claim -- a predictor's internal state must be rebuilt as-of each target date, never a single static snapshot reused across a corpus that includes dates the snapshot has already absorbed.
- **causal story**: `IntlSoccerPredictor.__init__` built team strength via `ratings.replay(m)` with no `until` cutoff -- one static snapshot folding the ENTIRE results file was reused for every `predict_live()` call regardless of the target match's date, so predicting an early-corpus match used a state that had already seen later/contemporaneous results.
- **expected signature**: a static-snapshot readout and a leak-free as-of readout diverge on any game whose true fixture date precedes dates already folded into the snapshot.
- **test spec**: `ratings.goals_state_asof(until=game_date)` rebuild vs the static snapshot, same repricer chain, side-by-side on the same 83-game corpus.
- **status**: methodology CLOSED CLASS -- cite, do not re-litigate; every soccer in-game benchmark in this ledger must build state via an explicit `until=` cutoff.
- **measured LOCAL magnitude**: n/a (a leak rule, not a magnitude) -- the corrected leak-free readout on the same 83-game/10,415-tick corpus was Brier 0.1206 (model) vs 0.1404 (market), CI [-0.0032, 0.0444] straddling zero -- honest MATCH, not a beat-the-close claim.
- **artifact link**: commit `9b343b0fdb2f664254ef028f0c9b935464251f75` "feat(soccer): leak-free WC-2026 in-game benchmark -- static predictor state was in-sample"; `scripts/platformkit/ingame/soccer_wc_checkpoint_benchmark.py`.

---

## Validated THIS SESSION (6 real leak-free local tests, receipts in `validation_ledger.jsonl`)

### 4. First-goal timing predicts final result
- **claim**: the team that scores first in a match wins the (decisive) match at a rate well above a coin flip.
- **causal story**: scoring first both reflects and compounds an in-match advantage -- the scoring team can play a more controlled/defensive shape with a lead, and it directly needed to be the better side in that passage of play to score at all.
- **expected signature**: binomial win-rate for the first-scoring team significantly above 0.5, draws excluded.
- **test spec**: `domains.soccer.knowledge.validate_season_structure.first_goal_timing_win_effect` -- resolved goal timeline (incl. own goals credited to the opponent) vs match_meta final score, 400-match corpus, decisive matches only, `scipy.stats.binomtest` vs p=0.5.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: first-scoring team won 263/310 decisive matches (0.848); effect +0.348 over the 0.5 baseline, p=1.4e-37, n=310 (both corpora pooled).
- **artifact link**: `domains/soccer/knowledge/validate_season_structure.py::first_goal_timing_win_effect`; row in `validation_ledger.jsonl`.
- **wiring**: in-game conditioning-feature candidate -- `first_goal_scored` as a live win-probability re-pricer the instant the first goal event resolves, analogous to MLB's CONFIRMED "first-pitch strike suppresses walk rate" (same "first resolved event reprices the rest" shape).

### 5. Finishing-skill persistence (split-half, goals minus xG) -- LOCAL NULL
- **claim**: a player's finishing over/under-performance (goals scored minus summed shot xG) is a repeatable skill, not season-to-season noise.
- **causal story**: if finishing quality (composure, technique) is a stable trait, a player who outperforms his shot xG in one half of the season should also outperform it in the other half.
- **expected signature**: positive split-half Pearson r of per-player (goals - sum xG), computed WITHIN each corpus (corpus A and B don't overlap in time at all, so the split must be per-corpus -- see leak-audit note in the file docstring; a naive global-median split silently puts all of A in h1 and all of B in h2, a bug this session caught and fixed before trusting the result).
- **test spec**: split-half Pearson r, players with >=8 shots per half, per-corpus median date split, pooled across corpora.
- **status**: REJECTED (NULL_LOCAL)
- **measured LOCAL magnitude**: r=-0.0238, p=0.793, n=124 players (>=8 shots/half) -- no detectable persistence at this sample size/threshold; consistent with the well-known result that shot-level xG overperformance is mostly noise/variance over a partial season, not proof finishing skill doesn't exist at all.
- **artifact link**: `domains/soccer/knowledge/validate_season_structure.py::finishing_skill_persistence_split_half`.

### 6. Momentum / hot-hand myth (last-result effect) -- LOCAL NULL
- **claim**: winning the previous match predicts winning the next one, beyond a naive baseline.
- **causal story**: the popular "momentum" narrative -- confidence/form carries over match to match independent of team quality.
- **expected signature**: higher win-rate after a prior win than after no prior win (loss or draw).
- **test spec**: per-team chronological match sequence (corpus A only -- weekly, near-contiguous fixture spacing; corpus B's WSL date gaps are wildly irregular, see #9), `prev_win` indicator vs current win, Welch t-test.
- **status**: REJECTED (NULL_LOCAL) -- the honest, market-efficient-consistent result
- **measured LOCAL magnitude**: win-rate after a prior win 0.412 (n=136) vs after no prior win 0.332 (n=244); effect +0.080, p=0.126, n=380 (corpus A) -- directionally positive but not significant.
- **artifact link**: `domains/soccer/knowledge/validate_season_structure.py::momentum_last_result_effect`.

### 7. Fixture-congestion (short-rest) performance penalty -- LOCAL NULL
- **claim**: teams playing on short rest (<=4 days since their previous in-sample match) perform worse (lower goal differential) than on normal rest.
- **causal story**: less recovery time between matches should show up as physical fatigue -- fewer high-intensity actions, more mistakes, worse results.
- **expected signature**: lower goal differential in short-rest matches vs normal-rest matches.
- **test spec**: per-team rest-day gap from match_meta dates (corpus A only, same rationale as #6), Welch t-test on goal_diff, short-rest (<=4d) vs normal-rest.
- **status**: REJECTED (NULL_LOCAL)
- **measured LOCAL magnitude**: goal-diff short-rest 0.042 (n=24) vs normal-rest -0.003 (n=356); effect +0.045, p=0.869, n=380 (corpus A) -- and n=24 short-rest instances is itself thin (this 200-of-380-match subsample only weakly preserves true fixture congestion, see #9's rest-day feasibility note).
- **artifact link**: `domains/soccer/knowledge/validate_season_structure.py::fixture_congestion_short_rest_effect`.

### 8. Red card suppresses the carded team's shot rate for the rest of the match
- **claim**: a team reduced to 10 (or fewer) men takes fewer shots per minute for the remainder of the match than before the sending-off.
- **causal story**: down a player, a team must shift possession/defensive resources to cover the extra space, at the direct cost of attacking numbers -- shot output should drop.
- **expected signature**: lower shots/min after the card than before, same team, same match (paired).
- **test spec**: matches with exactly one sending-off (Red Card or Second Yellow), >=5 min on each side of the card event, paired t-test on before/after shots-per-minute.
- **status**: REJECTED (NULL_LOCAL) -- direction is even backwards from the claim
- **measured LOCAL magnitude**: shots/min after send-off vs before, same team+match; effect -0.03385, p=3.58e-15, n=428 sendings-off (full 3,443-match event-cache scan). Statistically significant but the WRONG SIGN and below the declared min-effect bar (0.05) -- a down-to-10-men team does not shoot meaningfully less, if anything marginally less by a trivial margin, not the "must retreat" story.
- **artifact link**: `domains/soccer/knowledge/validate_ingame_state.py::_accumulate` (red-card branch); `validation_ledger.jsonl` row `red_card_suppresses_shot_rate`.

### 9. Leading-team defensive shell (game-state shot suppression)
- **claim**: a team currently leading in a match takes fewer shots per minute than while the score is tied (a defensive-shell/game-management effect).
- **causal story**: once ahead, a team's incentive shifts from maximizing scoring chances to protecting the lead -- fewer forward risks, fewer shots.
- **expected signature**: lower shots/min while leading than while tied, same team-match unit (paired across the two teams of every match).
- **test spec**: goal-timeline state segments (StatsBomb goal/own-goal events, chronological), team-match units with >=5 min in both the leading and tied states, paired t-test.
- **status**: CONFIRMED -- but the OPPOSITE direction of the claim (a real, replicable effect, textbook-defying)
- **measured LOCAL magnitude**: shots/min while leading (higher) vs tied; effect +0.02423, p=2.15e-37, n=3,352 team-match units (full 3,443-match scan). Leading teams take MORE shots per minute than while tied, not fewer -- no "defensive shell" locally; consistent with a leading team pressing to extend the lead / opponent committing more numbers forward while chasing, not the popular game-management narrative.
- **artifact link**: `domains/soccer/knowledge/validate_ingame_state.py::_accumulate` (leading/tied branch); `validation_ledger.jsonl` row `leading_team_shot_rate_suppression`.
- **wiring**: in-game conditioning-feature candidate -- `score_state x shot_rate` (leading vs tied) as a live shot-frequency re-pricer, the strongest single-effect CONFIRMED_LOCAL row in this ledger (p=2.15e-37).

### 10. Set-piece vs open-play shot conversion
- **claim**: set-piece shots (corners, free kicks) convert to goals at a different rate than open-play shots.
- **causal story**: set pieces are a rehearsed, defense-organized situation (lower quality on average per shot) vs open play's higher-variance, sometimes clear-cut chances -- or the reverse, if set-piece routines target a specific weakness.
- **expected signature**: a shot-level goal-rate gap between set-piece and open-play shots, pooled across the full event cache.
- **test spec**: Welch t-test, goal indicator by `shot.type.name` in {Corner, Free Kick} vs Open Play, all cached matches.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: goal rate set-piece (n=4,174) lower than open-play (n=82,169); effect -0.03489, p=9.83e-18, n=86,343 shots (full scan). Set-piece shots convert at a meaningfully lower rate than open play -- consistent with set pieces being lower-quality-per-shot chances on average (defense pre-organized) even though they're a valuable VOLUME source.
- **artifact link**: `domains/soccer/knowledge/validate_ingame_state.py::_accumulate` (shot-type branch); `validation_ledger.jsonl` row `setpiece_vs_openplay_conversion`.
- **wiring**: in-game conditioning-feature candidate -- `shot_type` (set-piece vs open-play) as an xG-quality prior, complementary to the real `shot.statsbomb_xg` field already used by chain_engine.

### 11. Substitution shot-rate shift
- **claim**: a team's shot rate changes in the window right after its first substitution vs right before.
- **causal story**: ambiguous sign a priori -- a like-for-like tactical sub might not move the rate; a fresh attacking sub (chasing a game) should raise it; a defensive sub (protecting a lead) should lower it. Treated as an exploratory two-sided test, not a directional claim.
- **expected signature**: a shots/min gap between the 15 minutes before and the 15 minutes after a team's first substitution, paired.
- **test spec**: first substitution per team per match, >=10 min available on both sides, paired t-test.
- **status**: REJECTED (NULL_LOCAL) -- statistically detectable but below the declared min-effect bar
- **measured LOCAL magnitude**: shots/min 15min after 1st sub vs 15min before, per team-match; effect +0.00863, p=6.28e-07, n=6,729 team-match units (full scan). p is tiny at this sample size but the effect itself (<0.01 shots/min) is below the 0.05 min-effect threshold -- a statistically-significant-but-substantively-trivial bump, not a usable in-game signal.
- **artifact link**: `domains/soccer/knowledge/validate_ingame_state.py::_accumulate` (substitution branch); `validation_ledger.jsonl` row `substitution_shot_rate_change`.

### 12. Penalty-conversion-rate stability (split-half by taker) -- data gap
- **claim**: an individual penalty-taker's conversion rate is a stable, repeatable skill.
- **causal story**: same rationale as finishing-skill persistence (#5), specialized to the from-the-spot situation where shot quality is fixed and only taker skill/nerve varies.
- **expected signature**: n/a until the same taker has enough penalties in both halves of the season to correlate.
- **test spec**: split-half per-taker conversion rate, players with >=1 penalty in both halves.
- **status**: NOT_TESTABLE
- **measured LOCAL magnitude**: 92 penalties across 56 distinct takers in the 400-match corpus; 0 takers have a penalty in BOTH season halves -- far too sparse for a per-taker split-half correlation.
- **artifact link**: `domains/soccer/knowledge/validate_data_gaps.py::penalty_conversion_stability_gap`.

### 13. Weather/pitch-condition effect on match outcome -- data gap
- **claim**: temperature, wind, rain, or pitch condition shift shot volume/quality or overall goal rate.
- **causal story**: same physical-conditions story as MLB's weather/HR mechanism -- wetter/colder/windier conditions should change ball behavior and player output.
- **expected signature**: n/a until a weather/pitch-condition ingredient exists locally.
- **test spec**: column-existence check on `match_meta.parquet` and the StatsBomb event schema.
- **status**: NOT_TESTABLE
- **measured LOCAL magnitude**: n=0 -- no `weather`/`temperature`/`pitch_condition`/`wind_speed` column anywhere in `match_meta.parquet`, and no such field in the StatsBomb event JSON schema either.
- **artifact link**: `domains/soccer/knowledge/validate_data_gaps.py::weather_pitch_condition_gap`.

---

## Validated 2026-07-09 (14 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

### 14. Home-advantage decomposition (crowd component)
- **claim**: home-field advantage is not monolithic -- a crowd/atmosphere sub-component is separable from travel and referee-bias sub-components.
- **status**: NOT_TESTABLE -- `matches/*.json` (3,961 records, joined 400-for-400 to `match_meta.parquet` this session) has a `stadium` field but NO `attendance` field anywhere (0 non-null of 400 rows checked); no crowd-size proxy exists locally.
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::_premise_blocked` (home_advantage_crowd_component).

### 15. Home-advantage decay/growth across a season
- **claim**: the home-win-rate edge is not constant across a season -- it may compress or widen as the season progresses.
- **status**: REJECTED (NULL_LOCAL) -- directionally rising (0.343 early -> 0.45 late) but not significant at alpha=0.01.
- **measured LOCAL magnitude**: chi2 p=0.458, home win-rate by match-week tercile: early 0.3429, mid 0.400, late 0.450; effect +0.107, n=200 (corpus A only, `matches/*.json` `match_week` joined to `match_meta.parquet`, confirmed present for all 400 rows this session).
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::home_advantage_by_matchweek`.

### 16. Referee card-rate individual consistency (split-half)
- **claim**: individual referees differ in card-happiness, and that tendency is a stable personal trait.
- **status**: NOT_TESTABLE on the original 400-match StatsBomb slice (82 referees, fewer than 10 with >=3 matches in BOTH halves) -- UNBLOCKED 2026-07-10 by row #34's 10,251-match flat-file corpus, earned verdict REJECTED (NULL_LOCAL): split-half r=0.2999, p=0.0636, n=39 referees -- effect clears the declared |r|>=0.15 bar but misses p<0.01, so the "differ + persist" claim is not confirmed at this significance bar (directionally positive, underpowered at alpha=0.01, not a clean null).
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::referee_card_rate_persistence` (original NOT_TESTABLE reading, StatsBomb slice); `domains/soccer/knowledge/validate_referee_xg_fouls.py::referee_card_rate_persistence_at_scale` (unblocking reading, flat-file corpus); `validation_ledger.jsonl` row `referee_card_rate_persistence_at_scale`.

### 17. Yellow-card accumulation suspension effect
- **claim**: a team missing a suspended player performs worse in that match than its baseline.
- **status**: NOT_TESTABLE -- accumulated-yellow suspension tracking needs each player's FULL-season card history; the 400-match corpus is a partial slice (200/380 per corpus) so any suspension inferred from it would be an artifact of the missing games, not a real ban.
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::_premise_blocked` (yellow_card_suspension_effect).

### 18. Set-piece share of total xG -- LOCAL NULL
- **claim**: set-piece xG share varies systematically with a team's overall possession-share (style proxy).
- **status**: REJECTED (NULL_LOCAL).
- **measured LOCAL magnitude**: pearson r=0.0288, p=0.017, n=6,879 team-match units (full 3,443-match event-cache scan, pass-share as possession proxy).
- **artifact link**: `domains/soccer/knowledge/validate_pressing_defense.py::setpiece_xg_share_vs_possession`.

### 19. Pressing intensity (PPDA proxy) vs opponent turnover rate
- **claim**: a team's PPDA (pressing-intensity proxy) predicts how often it forces opponent turnovers.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: pearson r=-0.558, p~0, n=6,886 team-match units (full event-cache scan); PPDA-proxy = opponent passes / own Pressure+Duel+Interception count, turnover rate = (interceptions+recoveries)/opponent passes. Direction matches the claim: lower PPDA (more pressing) -> higher turnover rate. The strongest single-effect CONFIRMED_LOCAL row in this session's soccer batch.
- **artifact link**: `domains/soccer/knowledge/validate_pressing_defense.py::pressing_ppda_vs_turnover_rate`.
- **wiring**: in-game conditioning-feature candidate -- team PPDA-proxy as a live pressing-intensity prior for opponent-turnover-rate re-pricing.

### 20. Goalkeeper distribution style vs possession retention
- **claim**: short GK distribution retains possession more often than long distribution.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: goal-kick retention rate, short/ground (0.986, n=17,786) vs long/high (0.391, n=38,476); effect +0.595, p~0, n=56,262 (full 3,443-match event-cache scan, `pass.type.name=="Goal Kick"` height-classified, retained = no Incomplete/Out/Offside/Unknown outcome).
- **artifact link**: `domains/soccer/knowledge/validate_event_windows.py::goalkeeper_distribution_vs_retention`.
- **wiring**: in-game conditioning-feature candidate -- goal-kick height/type as a live possession-retention-probability re-pricer at every restart.

### 21. Formation-change mid-match impact
- **claim**: a `Tactical Shift` event measurably changes a team's shot rate.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: shots/min after own team's 1st Tactical Shift vs before, paired; effect +0.0205, p=1.2e-43, n=4,356 team-match units (full event-cache scan, >=10min on both sides of the shift).
- **artifact link**: `domains/soccer/knowledge/validate_event_windows.py::tactical_shift_shot_rate_change`.
- **wiring**: in-game conditioning-feature candidate -- `Tactical Shift` event as a live shot-rate re-pricing trigger, same shape as the CONFIRMED substitution-window design (#11's reject) but this one clears the bar.

### 22. Injury-time added-goals rate -- LOCAL NULL
- **claim**: goals-per-minute in added time differs from regulation time.
- **status**: REJECTED (NULL_LOCAL) -- direction is positive (added time slightly higher) but below the declared min-effect bar.
- **measured LOCAL magnitude**: goals-per-minute, added-time 0.0329 (654 goals / 19,890 min) vs regulation 0.0297 (9,192 goals / 309,812 min); effect +0.0032, p=0.0099, n=9,846 goals (full event-cache scan, added time = period1 minute>45 or period2 minute>90).
- **artifact link**: `domains/soccer/knowledge/validate_event_windows.py::injury_time_added_goals_rate`.

### 23. Corner-to-shot conversion by delivery side
- **claim**: corner delivery side/footedness changes shot-producing probability.
- **status**: NOT_TESTABLE -- corner-taker footedness is not in the StatsBomb event or lineup schema locally; would need an external footedness lookup, a v2 ingredient.
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::_premise_blocked` (corner_delivery_side_conversion).

### 24. Extra-time/knockout fatigue
- **claim**: teams playing extra time show worse output in the extra 30 minutes vs regulation.
- **status**: NOT_TESTABLE -- both corpora (EPL 2015/16, FA WSL) are league-season round-robin competitions with no knockout legs; every cached event file's `period` value-set is {1,2}, confirmed this session -- no extra-time periods exist to test.
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::_premise_blocked` (extra_time_knockout_fatigue).

### 25. Squad-rotation (cup vs league) fixture effect
- **claim**: teams rotate their strongest XI for lower-stakes cup fixtures vs league fixtures.
- **status**: NOT_TESTABLE -- `competition_stage` for all 400 corpus matches (joined from `matches/*.json` this session) is uniformly "Regular Season"; no cup fixtures exist in this slice to contrast against league fixtures.
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::_premise_blocked` (squad_rotation_cup_vs_league).

### 26. Defensive-block height vs opponent shot location -- LOCAL NULL
- **claim**: a deeper defensive block concedes shots from further out (lower opponent xG-per-shot) than a high press.
- **status**: REJECTED (NULL_LOCAL) -- block-height proxy adapted to a direction-agnostic form (StatsBomb does not label attacking direction per period, so absolute pitch-side block depth cannot be computed directly; proxy = |own defensive-action mean x - own shot mean x|, a compactness measure, declared simplification).
- **measured LOCAL magnitude**: pearson r=0.0078, p=0.517, n=6,872 team-match units (full event-cache scan).
- **artifact link**: `domains/soccer/knowledge/validate_pressing_defense.py::defensive_block_height_vs_opponent_xg`.

### 27. Away-goal timing asymmetry -- LOCAL NULL
- **claim**: an away team's first goal shifts combined shot rate more than a home team's first goal of the same match-minute.
- **status**: REJECTED (NULL_LOCAL).
- **measured LOCAL magnitude**: combined shot-rate shift (after-before, matched window around the match's first goal), away-team-scored 0.0618 (n=158) vs home-team-scored 0.0570 (n=172); effect +0.0048, n=330, 400-match corpus.
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::away_goal_timing_asymmetry`.

### 28. Trailing prior-xG composite beats a goals-only pregame base -- LOCAL NULL
- **claim**: strictly-prior trailing EW real-xG-for/against diff (asof_pregame.parquet) lowers held-out home-win Brier over a goals-based EW-Poisson base.
- **causal story**: shot quality (xG) is a lower-variance proxy of team strength than the noisier goals-scored signal, so conditioning on it should sharpen the base's win-prob estimate.
- **expected signature**: held-out Brier(base+xg_prior_diff) < Brier(base alone), DM-significant, replicated across both StatsBomb corpora (A=EPL men, B=WSL women).
- **test spec**: chronological 50/50 train/test split per corpus, logistic refit BASE vs BASE+feature, clustered DM by match_id, degenerate-base + planted-null guards (reuses `scripts.platformkit.gate_run_soccer_statsbomb`'s existing goals-Poisson base and split machinery).
- **status**: REJECTED (NULL_LOCAL) -- neither corpus ships; A's held-out Brier got WORSE with the feature (base already captures most of the signal from only 170-190 held-out matches), B improved but short of DM significance.
- **measured LOCAL magnitude**: split-half A(EPL): n=170, Brier 0.238090->0.246773, DM p=0.233 (feat worse). B(WSL): n=154, Brier 0.202416->0.184934, DM p=0.068 (feat better, not significant at eps=0.05). Combined n=324.
- **artifact link**: `domains/soccer/validate_prior_xg_pregame.py`.

### 29. Live cumulative xG diff adds to a (score, minute) in-game base -- LOCAL NULL
- **claim**: the as-of minute-level cumulative real-xG diff (asof_ingame.parquet) lowers held-out home-win Brier over a goal-diff-only in-game base at the same minute.
- **causal story**: goal difference is a sparse, discrete signal; the underlying shot-quality trend (who is actually creating better chances right now) should carry incremental in-play information over goals alone, especially before the next goal lands.
- **expected signature**: held-out Brier(goal-diff-base+xg_diff_asof) < Brier(goal-diff-base alone) at a fixed minute snapshot, DM-significant, replicated across both corpora, leak-free (xg_diff_asof folded strictly minute<=t).
- **test spec**: same chronological 50/50 split-half design as #28, applied per-minute-snapshot frame at minute 30/60/75 (robustness across match phase); planted-null and degenerate-base guards identical.
- **status**: REJECTED (NULL_LOCAL) -- 0/3 minute snapshots ship in both corpora; the goal-diff base already dominates and xg_diff_asof does not clear DM significance at any of the 3 checkpoints in either corpus.
- **measured LOCAL magnitude**: min30 A n=200 Brier 0.197271->0.195606 p=0.420 | B n=200 0.170695->0.159971 p=0.578. min60 A n=200 0.127919->0.129006 p=0.678 | B n=200 0.112323->0.125312 p=0.351. min75 A n=200 0.086762->0.092818 p=0.122 | B n=200 0.093832->0.105763 p=0.270. Combined n=1200.
- **artifact link**: `domains/soccer/validate_xg_diff_ingame.py`.

---

## Validated 2026-07-10 (4 -- fresh leak-free local tests, receipts in `validation_ledger.jsonl`)

### 30. Home-advantage magnitude collapses at neutral venues
- **claim**: the "home" team's goal-diff and win-rate edge is largely a true-venue effect (crowd/travel/pitch familiarity) -- it should shrink sharply when the match is played at a neutral site, even though a "home team" label is still assigned by convention.
- **causal story**: crowd support, no travel, and pitch/weather familiarity are the standard home-advantage ingredients; none of them exist at a neutral site, so only whatever residual (seeding/fixture-quality) survives should remain.
- **expected signature**: lower goal-diff and lower win-rate for the nominal home team at neutral venues than at true-home venues.
- **test spec**: `domains.soccer.knowledge.validate_tournament_context.home_advantage_neutral_vs_true` -- Welch t-test (goal-diff) + chi2 (win-rate), soccer-intl full-history corpus (`data/domains/soccer_intl/results.parquet`, 49,477 rows 1872-2026, 52 unplayed WC-2026 fixtures dropped -> 49,425 played matches).
- **status**: CONFIRMED
- **measured LOCAL magnitude**: goal-diff true-home 0.6744 (n=36,350) vs neutral 0.3007 (n=13,075), effect +0.3738, p=2.98e-45. Win-rate true-home 0.5074 vs neutral 0.4418, effect +0.0656, p=7.91e-38. Both readings confirm: roughly half the raw goal-diff edge and about two-thirds of the win-rate edge survive at a neutral site -- a real residual (seeding/fixture strength) remains, but the bulk of home advantage is venue-tied.
- **artifact link**: `domains/soccer/knowledge/validate_tournament_context.py::home_advantage_neutral_vs_true`; `validation_ledger.jsonl` rows `home_advantage_neutral_vs_true_goal_diff` / `home_advantage_neutral_vs_true_win_rate`.
- **wiring**: pregame-model implication (not yet gated) -- a `neutral_venue` flag should down-weight the home-advantage term in any pregame team-strength prior; this magnitude (roughly half the goal-diff edge) is large enough to be worth a follow-up gated pregame-Brier test, not just a descriptive note.

### 31. Neutral-venue split replicates across era (split-half stability)
- **claim**: the home-advantage-collapses-at-neutral effect (#30) is not an artifact of one era of the corpus -- it should replicate independently pre- and post-2000.
- **causal story**: if #30 were driven by a handful of early-corpus (pre-professionalization, sparser fixture) matches, splitting the 154-year corpus by era should make the effect vanish or flip in one half.
- **expected signature**: same-sign, independently-significant goal-diff effect in both the pre-2000 and post-2000 halves.
- **test spec**: `domains.soccer.knowledge.validate_tournament_context.home_advantage_neutral_split_half_by_era` -- same true-home-vs-neutral goal-diff comparison, re-run separately on match-year<2000 and >=2000 slices.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: pre-2000 effect +0.2187 (n=24,062, p=7.50e-08); post-2000 effect +0.4985 (n=25,363, p=1.50e-46). Both halves independently clear the bar with the same sign -- the effect replicates, though it is more than 2x stronger post-2000 (more neutral-venue major tournaments, likely mix-shift toward higher-stakes neutral fixtures in the modern era) -- a magnitude-drift caveat, not a directional one.
- **artifact link**: `domains/soccer/knowledge/validate_tournament_context.py::home_advantage_neutral_split_half_by_era`; `validation_ledger.jsonl` row `home_advantage_neutral_split_half_by_era`.

### 32. Tournament (competitive) context lifts the scoring environment vs friendlies
- **claim**: matches in a named competitive tournament (anything not labelled "Friendly") produce more total goals per match than friendlies.
- **causal story**: ambiguous a priori -- tournament stakes could tighten play (more caution, fewer goals) or the opposite (stronger/more-motivated squads, knockout urgency, weaker friendly-fixture effort/rotation) could raise output. Treated as an exploratory two-sided test.
- **expected signature**: a total-goals-per-match gap between competitive and friendly matches.
- **test spec**: `domains.soccer.knowledge.validate_tournament_context.tournament_vs_friendly_scoring_environment` -- Welch t-test on total goals, same 49,425-match corpus.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: total-goals/match competitive 2.9774 (n=31,037) vs friendly 2.8748 (n=18,388); effect +0.1027, p=8.52e-08. Direction is competitive-scores-more, small in absolute size (~0.1 goals/match) but well above both the significance and the declared 0.05 min-effect floor.
- **artifact link**: `domains/soccer/knowledge/validate_tournament_context.py::tournament_vs_friendly_scoring_environment`; `validation_ledger.jsonl` row `tournament_vs_friendly_scoring_environment`.

---

## Validated 2026-07-10 (PPDA x forward shot-quality-conceded, C15)

### 33. First-half pressing intensity vs second-half shot quality conceded -- LOCAL NULL
- **claim**: a team's own first-half PPDA-proxy (pressing intensity) predicts the shot quality (xG-per-shot) it concedes in the SECOND half -- a genuine forward split, distinct from #19 (same-match PPDA vs opponent turnover rate) and #26 (direction-agnostic block-height proxy vs opponent xG, REJECTED).
- **causal story**: a team that presses harder (lower PPDA) in the first half disrupts opponent build-up more, which should carry into fewer/lower-quality chances conceded in the second half if pressing reflects a durable tactical identity rather than a one-off spell.
- **expected signature**: nonzero pearson r between own 1st-half PPDA-proxy and opponent's 2nd-half xG-per-shot, replicated with the same sign across >=2 independent competition groups.
- **test spec**: `domains.soccer.knowledge.validate_ppda_shot_quality.run` -- 400-match corpus with competition metadata (corpus A=EPL 2015/16, B=FA WSL), tested independently per corpus, min n=30, bar |r|>=0.05 AND p<0.01.
- **status**: REJECTED (NULL_LOCAL) both corpora -- A: r=0.0494, p=0.327, n=397 team-match units; B: r=0.0019, p=0.970, n=389. No evidence first-half pressing intensity forecasts second-half shot quality conceded in this local corpus.
- **measured LOCAL magnitude**: see above (statsbomb match_meta 400-match corpus, split by competition group).
- **artifact link**: `domains/soccer/knowledge/validate_ppda_shot_quality.py::run`; `validation_ledger.jsonl` rows `ppda_h1_vs_shot_quality_conceded_h2` (x2) + `__combined`.

---

## Seeded 2026-07-10 (research-wave -- literature-sourced, M10 pool feedstock) -- validated this session

Fresh mechanism hypotheses from public football-analytics literature,
checked against every row above and against `data/frontend/reject_ledger.jsonl`
(535 rows) before seeding, then validated this session (1 CONFIRMED, 2
REJECTED/NULL_LOCAL) via `domains/soccer/knowledge/validate_referee_xg_fouls.py`.

### 34. Referee card-rate individual consistency, at scale (unblocks NOT_TESTABLE #16 with a bigger corpus)
- **claim**: individual referees differ in card-happiness, and that tendency is a stable personal trait -- the same claim as #16, but #16 was NOT_TESTABLE on the 400-match StatsBomb slice (fewer than 10 referees with >=3 matches in both halves); a much larger local corpus now exists.
- **causal story**: same as #16 -- referees vary in disciplinary strictness as a personal trait, not match-to-match noise.
- **expected signature**: positive split-half correlation of per-referee card rate (or foul-to-card conversion rate), first half of the corpus's date range vs second, for referees with enough matches in both halves.
- **test spec**: split-half Pearson r, per-referee `total_cards / total_fouls` (or raw card rate), referees with >=5 matches/half, `data/domains/soccer/referee_card_foul_profiles.parquet` (10,251 event-referee rows across multiple divisions/years) joined to `match_stats.parquet` (25,834 matches) by `event_id`; declared bar |r|>=0.15 AND p<0.01.
- **status**: REJECTED (NULL_LOCAL) -- premise-checked clean (both parquets load with every named column, join is 100% coverage by `event_id`, no bare/prefixed mismatch found); the ingredient exists and is testable at scale, unblocking #16 to an earned verdict, but the split-half correlation misses the declared p<0.01 bar.
- **measured LOCAL magnitude**: split-half pearson r=0.2999 (n=39 referees, >=5 matches/half), p=0.0636 -- effect clears the |r|>=0.15 bar but is not significant at alpha=0.01 (directionally consistent with the literature's "time consistency" finding, underpowered rather than a clean null at n=39).
- **artifact link**: `domains/soccer/knowledge/validate_referee_xg_fouls.py::referee_card_rate_persistence_at_scale`; `validation_ledger.jsonl` row `referee_card_rate_persistence_at_scale`.
- **source**: "Are football referees really biased and inconsistent?" (Dobson & Dawson, Nottingham Trent University), https://irep.ntu.ac.uk/id/eprint/16418/1/196365_392%20Dobson%20PostPrint.pdf -- academic study rejecting the "refereeing consistency" null hypothesis (referees DO differ significantly), while separately finding a "time consistency" result (each referee's own average is stable over time) -- exactly the two-part claim (differ + persist) this row tests locally.

### 35. Trailing xG-supremacy is a stable team trait (persistence, not incremental-Brier)
- **claim**: a team's trailing (as-of) combined xG-supremacy (attack minus defense) is internally stable -- split-half persistent -- as a team trait, independent of whether it improves win-probability Brier over a baseline (a separate, already-closed question).
- **causal story**: if xG-supremacy reflects real, durable team quality (not shot-luck noise), a team's trailing supremacy value early in a sampling window should correlate with its trailing supremacy value later in the same window.
- **expected signature**: positive split-half Pearson r of `diff_xg_supremacy_asof` per team, first-half-of-corpus-dates vs second.
- **test spec**: split-half Pearson r, per-team mean `home_xg_supremacy_asof`/`away_xg_supremacy_asof` (unified to a per-team-per-date series, joined to `match_stats.parquet` for team identity + date), min n games/half declared at 10; declared bar |r|>=0.20 AND p<0.01.
- **status**: CONFIRMED (REPLICATED on 2 disjoint competition groups -- second-corpus receipt below) -- premise-checked clean (all named columns present, `event_id` join 100% coverage). Magnitude is large enough to be independently suspicious, so a robustness check was run before trusting it: a gap-buffered re-split (both halves trimmed 120 days off the median-date boundary, to rule out the EW-smoothing state simply bridging across the split point) gives r=0.9228, p=1.33e-53, n=127 -- effectively unchanged from the un-buffered reading, so this is not a smoothing-continuity artifact. Only 25/187 teams ever switch division, so it is also not purely a promotion/relegation division-label split in disguise; it reads as genuine multi-year team-strength persistence (big clubs stay big, small clubs stay small) rather than an artifact.
- **measured LOCAL magnitude**: split-half pearson r=0.9254 (n=140 teams, >=10 games/half), p=5.38e-60. Robustness (120-day gap-buffered split): r=0.9228, p=1.33e-53, n=127. Second-corpus (disjoint-competition-group) replication: english_pyramid (div E0/E1) r=0.8469, p=1.74e-14, n=49 teams -- REPLICATED; continental_top4 (div D1/F1/I1/SP1) r=0.9495, p=1.45e-46, n=91 teams -- REPLICATED.
- **artifact link**: `domains/soccer/knowledge/validate_referee_xg_fouls.py::xg_supremacy_persistence`; replication `domains/soccer/knowledge/validate_replication_wave1.py::replicate_xg_supremacy_persistence`; `validation_ledger.jsonl` rows `xg_supremacy_persistence`, `xg_supremacy_persistence__replication_english_pyramid`, `xg_supremacy_persistence__replication_continental_top4`.
- **note**: distinct from `soccer_diff_xg_supremacy_asof` in `data/frontend/reject_ledger.jsonl` (REJECT -- "ablation-positive + sig p but NULL guard FAIL... shot-based xG-proxy is team strength already priced") -- that closed the INCREMENTAL win-prob-over-market question. This row asks the prior descriptive question (is the trait itself stable), the same persistence-vs-incremental-value split already used for #28/#29 (xG-diff predictive-value REJECTS) vs this new row.
- **source**: general xG-persistence literature underlying the widely-cited claim that "xG is more repeatable than goals across a season" (the standard justification for using xG-based team ratings at all in modern football analytics, e.g. Opta/Analyst xGOT coverage: https://theanalyst.com/2021/06/what-are-expected-goals-on-target-xgot/) -- this row tests the repeatability premise directly against the local corpus rather than assuming it.

### 36. Fouls-committed rate suppresses opponent shot generation in the same match (tactical fouling)
- **claim**: a team's fouls-committed rate correlates negatively with its opponent's shots-on-target in that match -- fouling (especially "tactical"/strategic fouls that stop transitions) suppresses the opponent's attacking output.
- **causal story**: a foul stops the clock and resets the opponent's attacking shape/momentum, particularly transition fouls that prevent a counter-attack from developing into a shot -- a well-known coaching tactic ("professional foul"), distinct from and untested by any card/discipline row above (which measure the foul's cost to the fouling team, not its effect on the fouled team's output).
- **expected signature**: negative correlation between a team's `home_fouls`/`away_fouls` and the OPPONENT's `sot` in the same match, net of overall match shot volume.
- **test spec**: Pearson r (or partial r controlling for `total_shots`), team fouls vs opponent SOT, `data/domains/soccer/match_stats.parquet` (25,834 matches, both sides pooled); declared bar |r|>=0.05 AND p<0.01 given the large n.
- **status**: REJECTED (NULL_LOCAL) -- premise-checked clean (all named columns present as `home_/away_`-prefixed, no bare-name mismatch). The raw correlation is negative and "significant" only because of the huge n (a `total_shots` confound: low-shot-volume matches have both fewer fouls and fewer opponent shots); once partialled out, the direction flips positive and the magnitude stays below the declared bar -- no real suppression effect survives confound control.
- **measured LOCAL magnitude**: raw r=-0.0149 (p=0.00072, i.e. "significant" but below the |r|>=0.05 bar and sign-misleading); partial r (controlling `total_shots`)=+0.0369, p=4.57e-17, n=51,662 team-match units pooled both sides -- clears p<0.01 but not the |r|>=0.05 effect-size bar, and the direction is the OPPOSITE of the claim once the volume confound is removed.
- **artifact link**: `domains/soccer/knowledge/validate_referee_xg_fouls.py::fouls_suppress_opponent_sot`; `validation_ledger.jsonl` row `fouls_suppress_opponent_sot`.
- **source**: tactical/"professional" fouling as a recognized strategic tool to stop transitions is standard coaching-analytics discourse (e.g. Opta/Analyst and StatsBomb writeups on "stopping counter-attacks"); this row is the first local test of fouls as a DEFENSIVE-suppression mechanism rather than a discipline-risk one -- no existing row in this ledger tests fouls against opponent output.

---

## Seeded 2026-07-10 (research-wave 2 -- literature-sourced, UNTESTED, round-2 pool feedstock)

Fresh mechanism hypotheses from different literature areas than the
round-1 research wave (#34-36 above: referee card-rate at scale, xG-supremacy
persistence, tactical fouling). Checked against every row above and against
`data/frontend/reject_ledger.jsonl` (0 keyword hits for `sub.*timing`/`trailing`
on sport=soccer) before seeding. No validator built this lane.

### 37. First-substitution timing (early vs late) moderates the shot-rate shift
- **claim**: the shot-rate shift around a team's first substitution (already tested pooled-across-all-timings in #11, REJECTED as below the declared min-effect bar) is MODERATED by how early or late that substitution is made -- #11 never split by sub timing, only by before/after the (any-timing) sub.
- **causal story**: cited substitution-timing literature argues a losing team's sub should come before ~53min to have enough remaining minutes to matter; if timing itself is the moderator, EARLY subs (more remaining minutes to compound an effect) should show a larger |shot-rate shift| than LATE subs (little time left to matter), independent of #11's already-REJECTED pooled/trivial average.
- **expected signature**: |shot-rate shift| (after minus before, same paired design as #11) is larger for early-sub team-matches (sub_t<=60) than late-sub team-matches (sub_t>=75).
- **test spec**: `domains.soccer.knowledge.validate_research_wave2.run` (`substitution_timing_moderates_shift`) -- reuses #11's exact before/after shots-per-minute accumulator (`facts["subs"]` first-sub-per-team minute + the match's `shots` list from `_data.py::extract_match_facts`), split into early (sub_t<=60) vs late (sub_t>=75) buckets, Welch t-test comparing the two buckets' (after-before) shift distributions, full 4,235-match StatsBomb event cache (grew from the 3,443 at seed time), same >=10min-both-sides floor as #11; declared bar |eff|>=0.02 shots/min AND p<0.01.
- **status**: CONFIRMED within-corpus (split-half by match-index parity, >=2 independent groups, both clear the bar) but PARTIAL on second-corpus (disjoint-competition-group) replication -- see receipt below; the match-index split-half is NOT a true second corpus (same pooled competition mix on both sides), so the disjoint-competition-group result is the stronger test and the honest one to weight.
- **measured LOCAL magnitude**: pooled: effect +0.03629, p=1.58e-07, n=4,732 team-match units (early n=4,207, late n=525). Split-half robustness (`run_split_half`, even/odd match index): half A effect +0.03165 p=6.9e-04 CONFIRMED_LOCAL; half B effect +0.04066 p=6.8e-05 CONFIRMED_LOCAL -- both halves replicate direction and clear the |eff|>=0.02/p<0.01 bar independently, so this is NOT a single-fold artifact. Direction matches the expected signature (early-sub shift larger/more positive than late-sub shift). Second-corpus (disjoint-competition-group) replication: big4_2015_16 (Serie A/La Liga/Premier League/Ligue 1, single 2015/16 season, n_matches=1,517) effect +0.0186, p=0.152 -- NULL_LOCAL, FAILED_REPLICATION (below both the |eff|>=0.02 and p<0.01 bars). rest_competitions (all other 76 competitions in match_meta_full.parquet -- other seasons, women's leagues, internationals, n_matches=2,444) effect +0.0404, p=6.15e-06 -- CONFIRMED_LOCAL, REPLICATED. Reads as PARTIAL: the effect holds across the broader multi-season/multi-competition mix but does not clear the bar within one single-season top-4-league slice (plausibly a power issue at n_matches=1,517, late-sub n=155 -- not ruled out as a true competition-specific null).
- **artifact link**: `domains/soccer/knowledge/validate_research_wave2.py::run`/`run_split_half`; replication `domains/soccer/knowledge/validate_replication_wave1.py::replicate_substitution_timing`; `validation_ledger.jsonl` rows `substitution_timing_moderates_shift` + `substitution_timing_moderates_shift__split_A`/`__split_B` + `substitution_timing_moderates_shift__replication_big4_2015_16` (FAILED_REPLICATION) + `substitution_timing_moderates_shift__replication_rest_competitions` (REPLICATED).
- **wiring**: in-game conditioning-feature candidate -- sub-timing (not just sub-occurrence) as a moderator on the already-known-trivial pooled substitution effect (#11); needs an in-game blend design before any live use, this row only establishes the local structural effect.
- **note**: distinct from #11 (REJECTED, pooled all sub timings, found a real-but-trivial <0.01 shots/min average shift) -- this asks whether the SIZE of that shift depends on WHEN the sub happens, not whether an average shift exists.
- **source**: "A Proposed Decision Rule for the Timing of Soccer Substitutions" (Myers), https://www.researchgate.net/publication/227378915_A_Proposed_Decision_Rule_for_the_Timing_of_Soccer_Substitutions -- argues a losing team's first sub should land before minute 53 to have time to matter; and a UEFA EURO 2024 substitution-timing review (PMC12287015), https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12287015/, finding subs made 60-85min are more likely to have a positive match-outcome impact than earlier or later subs -- both motivate timing (not just occurrence) as the variable of interest.

### 38. Trailing-team shot-rate vs tied (extends #9's leading/tied state machine to the previously-discarded trailing case)
- **claim**: a team currently TRAILING in a match takes a different shot rate per minute than while the score is tied -- extends #9 (leading vs tied, CONFIRMED reversed-direction: leading teams shoot MORE, not less) to the trailing state, which #9's own state-segment logic computes but silently discards.
- **premise check**: `validate_ingame_state.py::_accumulate`'s leading/tied segment loop sets `state = "leading" if diff_x > 0 else ("tied" if diff_x == 0 else None)` -- the `diff_x < 0` (trailing) case falls through to `state is None` and is dropped (confirmed by reading the function this session, lines ~56-71); the trailing bucket has never been computed, only leading and tied.
- **causal story**: cited StatsBomb reference argues trailing teams out-shoot due to a mix of desperation to equalize and the leading team's tactical conservatism; #9 already shows leading teams shoot MORE than tied (the opposite of the classic "defensive shell" story), so the trailing side of the same three-state comparison is not automatically implied and needs its own direct test against the same tied baseline.
- **expected signature**: shots/min while trailing higher than shots/min while tied (per the cited literature), same team-match paired design as #9.
- **test spec**: `domains.soccer.knowledge.validate_research_wave2.run` (`trailing_team_shot_rate`) -- extends the existing `_accumulate` leading/tied state-segment logic to also bucket the previously-discarded `diff_x<0` case as `"trailing"`, paired t-test trailing-rate vs tied-rate, same >=5min-both-states floor and full 4,235-match event cache (grew from the 3,443 at seed time) as #9; declared bar |eff|>=0.02 shots/min AND p<0.01 (same convention as #9's family).
- **status**: PROVISIONAL -- pooled sample clears the declared bar, but split-half (>=2 independent groups) does NOT replicate it in both halves; do not treat as CONFIRMED until a second corpus or a wider-margin re-test settles it.
- **measured LOCAL magnitude**: pooled: effect +0.02031, p=1.89e-35, n=4,122 team-match units -- clears the |eff|>=0.02 bar by only 0.00031, essentially AT the threshold. Split-half robustness (`run_split_half`, even/odd match index): half A effect +0.02189 p=2.9e-21 CONFIRMED_LOCAL; half B effect +0.01871 p=5.7e-16 NULL_LOCAL (below the 0.02 bar despite p<<0.01). The effect direction (trailing > tied) is consistent and highly significant in both halves, but the MAGNITUDE straddles the declared min-effect bar rather than clearing it robustly -- a boundary-hugging pooled result, not a confidently replicated one.
- **artifact link**: `domains/soccer/knowledge/validate_research_wave2.py::run`/`run_split_half`; `validation_ledger.jsonl` rows `trailing_team_shot_rate` + `trailing_team_shot_rate__split_A`/`__split_B`.
- **wiring**: none yet -- PROVISIONAL, do not wire as a live conditioning feature until the split-half instability is resolved (either the effect is smaller than 0.02 shots/min in truth, or this corpus's even/odd split happens to straddle it; a genuinely independent second corpus is the next honest step).
- **source**: "Score Effects" (StatsBomb Blog Archive), https://blogarchive.statsbomb.com/articles/soccer/score-effects/ -- the canonical soccer-analytics reference for game-state-conditioned shot/possession inflation, cited directly for the trailing-team-out-shoots claim this row tests locally for the first time (only the leading side was tested in #9).

---

## Seeded 2026-07-10 (research-wave 3 -- literature-sourced, UNTESTED, round-3 pool feedstock)

Fresh mechanism hypotheses on xG-momentum/rebound structure and defensive-block
depth vs counterattack profile (distinct outcome from the CLOSED #26 block-depth-
vs-opponent-xG-per-shot NULL_LOCAL row). Checked against every row above and
against `data/frontend/reject_ledger.jsonl` (535 rows, 0 keyword hits for
`xg.?momentum`/`rebound.*shot`/`block.?depth`/`counter.?attack`) before seeding.
No validator built this lane.

### 39. xG additivity breaks down in same-team shot-rebound clusters (multi-shot possessions overstate combined scoring probability)
- **claim**: when a team takes 2+ shots in the SAME possession within a short time window (a rebound/second-chance sequence), the summed `statsbomb_xg` across those shots systematically overstates the possession's realized goal probability, relative to single-shot possessions -- distinct from any existing row, none of which test within-possession shot clustering.
- **premise check**: confirmed this session directly on raw StatsBomb event JSON (`data/cache/statsbomb/events/*.json`, 4,235 files) -- shot events carry both `possession` (a per-match possession id) and `shot.statsbomb_xg` (confirmed keys on a sampled shot: `body_part`/`end_location`/`first_time`/`freeze_frame`/`key_pass_id`/`outcome`/`statsbomb_xg`/`technique`/`type`), enough to group same-team shots by `possession` id and test cluster-vs-single xG-sum calibration directly -- no derived/fictitious ingredient.
- **causal story**: cited xG-methodology critique argues shot models treat shots as independent, so a blocked/saved shot immediately followed by a rebound shot in the same possession double-counts scoring chances that share the same underlying possession quality -- inflating naive summed xG beyond the possession's true one-goal-max scoring probability.
- **expected signature**: summed `statsbomb_xg` over a same-team multi-shot possession, minus the possession's realized goal indicator (0/1), is systematically positive (over-prediction) and larger than the equivalent single-shot-possession calibration gap.
- **test spec**: `domains.soccer.knowledge.validate_research_wave3.xg_rebound_cluster_calibration` -- group shots by `(match, team, possession)` using the raw event `possession` field, cluster = 2+ shots by the same team in the same possession id; compare mean(summed cluster xG - goal-in-cluster indicator) vs mean(single-shot xG - goal indicator) via Welch t-test on the calibration-gap distributions; declared bar |eff|>=0.03 xG-points AND p<0.01, split-half by match index (even/odd).
- **status**: CONFIRMED -- split-half validated (>=2 independent groups, both clear the bar)
- **measured LOCAL magnitude**: pooled: effect +0.10411 xG-points, p=4.70e-143, n=99,284 possession units (cluster n=8,114, single-shot n=91,170), full 4,235-match event cache. Split-half robustness (`run_split_half`, even/odd match index): half A effect +0.10239 p=1.63e-71 CONFIRMED_LOCAL (n=49,833); half B effect +0.10584 p=1.89e-73 CONFIRMED_LOCAL (n=49,451) -- both halves replicate direction and clear the |eff|>=0.03/p<0.01 bar independently and by a wide margin (~3.4x the declared bar), not a boundary-hugging result.
- **artifact link**: `domains/soccer/knowledge/validate_research_wave3.py::run`/`run_split_half`; `validation_ledger.jsonl` rows `xg_rebound_cluster_calibration` + `__split_A`/`__split_B`.
- **wiring**: none yet -- a calibration-structure finding (naive summed xG overstates same-team rebound-cluster scoring probability by ~0.10 xG-points on average); a live use would need a possession-level xG-correction/decay model, not a direct in-game conditioning feature as-is.
- **source**: "Beyond Expected Goals: A Probabilistic Framework for Shot Occurrences in Soccer" (arXiv:2512.00203), https://arxiv.org/html/2512.00203v2 -- directly documents the "double-chance" xG-inflation problem (a Feb-2025 match example: 4 rapid-fire rebound shots totaling 1.63 xG) and proposes correcting for it; this row tests whether the same inflation pattern is locally measurable in the StatsBomb corpus before any correction is attempted.

### 40. Defensive block depth predicts a team's own counterattack-shot share (distinct outcome from the CLOSED #26 opponent-shot-quality NULL)
- **claim**: a deeper defensive block (reusing #26's own compactness proxy) predicts a HIGHER share of a team's own shots coming from counterattacks (`play_pattern=='From Counter'`) -- #26 tested whether block depth changes the OPPONENT's shot quality (REJECTED, NULL_LOCAL); this row asks whether it changes the team's OWN attacking shot MIX, a different outcome variable entirely.
- **premise check**: confirmed this session that StatsBomb's `play_pattern` field (native categorical tag) is present on 100% of a 785-shot sample (5 matches) with `'From Counter'` as one of 9 observed categories (~5.1% of shots in that sample) -- a directly available, non-derived counterattack tag, no proxy needed for the outcome side (only the block-depth predictor reuses #26's existing compactness proxy).
- **causal story**: cited low-block tactical literature argues a deep, compact defensive shape conserves energy and creates space in transition specifically BECAUSE the team is not committing numbers forward -- once possession is regained, the team is better positioned (and more inclined, tactically) to break quickly rather than build possession, raising its counterattack-shot share.
- **expected signature**: positive correlation between #26's block-depth-compactness proxy and a team's own `play_pattern=='From Counter'` share of total shots, per team-match.
- **test spec**: `domains.soccer.knowledge.validate_research_wave3.block_depth_counterattack_share` -- reuses `validate_pressing_defense.py::defensive_block_height_vs_opponent_xg`'s exact compactness proxy (`|own defensive-action mean x - own shot mean x|`) as the predictor, per-team-match `play_pattern=='From Counter'` share of own shots as the outcome (both from the full 4,235-match event cache); Pearson r; declared bar |r|>=0.05 AND p<0.01, split-half by match index.
- **status**: CONFIRMED -- split-half validated (>=2 independent groups, both clear the bar)
- **measured LOCAL magnitude**: pooled: pearson r=+0.11262, p=2.73e-25, n=8,462 team-match units, full 4,235-match event cache. Split-half robustness (`run_split_half`, even/odd match index): half A r=+0.12906 p=3.50e-17 CONFIRMED_LOCAL (n=4,232); half B r=+0.09497 p=6.06e-10 CONFIRMED_LOCAL (n=4,230) -- both halves replicate the positive direction and clear the |r|>=0.05/p<0.01 bar independently, ~1.9-2.6x the declared bar. A deeper/more compact defensive block does predict a higher own-counterattack-shot share, distinct from #26's closed opponent-shot-quality NULL.
- **artifact link**: `domains/soccer/knowledge/validate_research_wave3.py::run`/`run_split_half`; `validation_ledger.jsonl` rows `block_depth_counterattack_share` + `__split_A`/`__split_B`.
- **wiring**: in-game/pregame team-style conditioning-feature candidate -- block-depth proxy as a predictor of a team's own attacking shot MIX (counterattack share), not yet wired into any live model; this row only establishes the local structural correlation.
- **source**: "Low Block In Soccer: Tactical Defensive Approach", https://stmichaelssoccer.com/rules/low-block-in-soccer-tactical-defensive-approach/ and "Low-Block – Football Tactics Explained" (The Football Analyst), https://the-footballanalyst.com/low-block-football-tactics-explained/ -- both describe the low-block-enables-fast-counterattack mechanism directly (conserving energy, exploiting space left by a pressing opponent), the basis for testing block depth against counterattack SHARE rather than #26's already-closed shot-quality-conceded question.

---

## Seeded 2026-07-10 (research-wave 4 -- literature-sourced, UNTESTED, round-4 pool feedstock)

Fresh mechanism hypothesis on set-piece specialization PERSISTENCE (a team
trait question), distinct from #10 (population-level set-piece vs open-play
CONVERSION RATE, already CONFIRMED) and #35 (overall xG-supremacy
persistence, not scoped to set pieces). Checked against every row above and
against `data/frontend/reject_ledger.jsonl` (535 rows, 0 keyword hits for
`set.?piece.*persist`/`corner.*xg`/`specializ`) before seeding. Full premise
check: `docs/research/research_seed_wave4_2026-07-10.md`. No validator
built this lane.

### 41. Team set-piece shot quality (xG per corner/free-kick shot) is a stable, persistent trait, distinct from the population-level conversion-rate question #10 already closed
- **claim**: a team's own mean `statsbomb_xg` on set-piece shots (corners + free kicks pooled, same `shot.type.name` definition already used and CONFIRMED-populated by #10) is internally stable across a season -- split-half persistent -- i.e. some teams are genuinely better "set-piece specialists" (delivery quality, rehearsed routines, aerial targeting) in a repeatable way, not the population-level "set pieces convert lower than open play on average" question #10 already answered.
- **premise check**: confirmed this session on the full 4,235-match StatsBomb event cache (grown from #10's original 3,443-match scan) that `shot.type.name` includes `{Corner, Free Kick, Open Play, Penalty, Kick Off}` with `shot.statsbomb_xg` present on every shot row (reused verbatim from #10's already-validated design, no new ingredient).
- **causal story**: cited set-piece analytics literature (a 5-league/5-season, 484-team-season dataset) documents that dead-ball delivery quality and specialist personnel (e.g. a designated corner/free-kick taker) are a real, coached team investment distinct from open-play attacking quality -- if that investment is real and durable, a team's set-piece xG-per-shot should correlate across two halves of a season, not wash out as shot-to-shot noise the way #5 (soccer finishing-skill persistence) already found for open-play finishing.
- **expected signature**: positive split-half Pearson r of per-team mean set-piece `statsbomb_xg`, first-half-of-corpus-dates vs second half.
- **test spec**: `domains.soccer.knowledge.validate_research_wave4.setpiece_xg_persistence` -- per-team mean `shot.statsbomb_xg` restricted to `shot.type.name` in {Corner, Free Kick}, split-half by match date across the full 4,235-match event cache, teams with >=10 set-piece shots per half (mirrors the min-n floor style already used by #16/#34's persistence designs); Pearson r; declared bar |r|>=0.15 AND p<0.01, split-half by match index (even/odd) as the 2nd independent group for the replication bar.
- **status**: PROVISIONAL -- one of the two declared-independent splits clears the |r|>=0.15 AND p<0.01 bar, the other clears the effect-size bar but NOT the p<0.01 bar; the replication requirement (both independent groups clear the bar) is not met, same PROVISIONAL convention as #38.
- **measured LOCAL magnitude**: date-split (per-competition median match date, 3,961 dated matches of 4,235): effect +0.38782, p=0.004501, n=52 teams-with->=10-shots/half -- CONFIRMED_LOCAL, clears both bars. Index-split (even/odd event-file position, full 4,235-match cache): effect +0.27827, p=0.04161, n=54 -- NULL_LOCAL, effect clears |r|>=0.15 comfortably but p=0.04161 is an order of magnitude above the declared p<0.01 bar. Both splits agree on direction (positive persistence, teams that were set-piece-strong in one half stay set-piece-strong in the other) and both have a decent-effect-size point estimate, but only one of two independent groups is significant at the declared threshold -- a directionally-consistent, not-yet-replicated result, not a confidently confirmed one.
- **artifact link**: `domains/soccer/knowledge/validate_research_wave4.py::run`; `validation_ledger.jsonl` rows `setpiece_xg_persistence__by_date` (CONFIRMED_LOCAL) + `setpiece_xg_persistence__by_index` (NULL_LOCAL).
- **wiring**: none -- PROVISIONAL, do not wire as a live conditioning feature until a second independent corpus or a larger n (only ~52-54 teams clear the >=10-set-piece-shots/half floor) settles whether the index-split's p=0.04 is sampling noise around a real effect or the date-split's p=0.0045 is the noisier read.
- **source**: "Corners, Free Kicks, and Set Pieces Across Europe's Top Football Leagues: What the Data Actually Says" (Mathieu Acher), http://blog.mathieuacher.com/CornersSetPiecesFootballEN/ -- multi-season (5 leagues, 5 seasons, 484 team-seasons), the direct literature basis for testing set-piece performance as a repeatable team trait rather than a one-season snapshot; "Set Pieces Only: Quantifying the Value of James Ward-Prowse" (From The Byline), https://fromthebyline.substack.com/p/set-pieces-only-quantifying-the-value -- documents an individual dead-ball specialist consistently outperforming the ~0.06 xG free-kick baseline, motivating the team-level persistence question this row tests locally.

---

## Replicated 2026-07-10 (second-corpus wave -- disjoint competition groups, #35 and #37)

Cross-competition replication of the 2 strongest research-wave CONFIRMED_LOCALs
above, using disjoint competition/league groups never isolated by the original
tests (#35 pooled all 6 flat-file divisions; #37 pooled the full StatsBomb
event cache with zero competition awareness at all). Both were ported with
the ORIGINAL validator functions imported and called unchanged (same
thresholds, same design) -- no bar was loosened for replication. `domains/
soccer/knowledge/validate_replication_wave1.py`.

- **xg_supremacy_persistence** (#35): REPLICATED on both disjoint groups --
  english_pyramid (E0/E1) r=0.8469 p=1.74e-14 n=49; continental_top4
  (D1/F1/I1/SP1) r=0.9495 p=1.45e-46 n=91. Same |r|>=0.20/p<0.01 bar cleared
  by a wide margin on both, independent of the original's date-based split.
- **substitution_timing_moderates_shift** (#37): PARTIAL -- REPLICATED on
  rest_competitions (n_matches=2,444, effect +0.0404, p=6.15e-06) but
  FAILED_REPLICATION on big4_2015_16 (n_matches=1,517, effect +0.0186,
  p=0.152). Honest read: the pooled/index-split-half CONFIRMED status
  reflected the SAME competition mix on both sides, not a real second
  corpus; the disjoint-competition-group test is the first genuine
  out-of-population check and it is mixed, not a clean confirm. Do not cite
  this row as fully replicated without the PARTIAL qualifier.
- **artifact link**: `domains/soccer/knowledge/validate_replication_wave1.py`;
  `validation_ledger.jsonl` rows `xg_supremacy_persistence__replication_english_pyramid`,
  `xg_supremacy_persistence__replication_continental_top4`,
  `substitution_timing_moderates_shift__replication_big4_2015_16`,
  `substitution_timing_moderates_shift__replication_rest_competitions`.

---

## Seeded 2026-07-10 (research-wave 5 -- literature-sourced, UNTESTED, round-5 pool feedstock)

Fresh mechanism hypothesis on goalkeeper distribution style vs downstream
BUILDUP chance quality, deliberately scoped DISTINCT from #20 (CONFIRMED --
short distribution retains possession more than long, a pure pass-
completion test). Checked against every row above and
`data/frontend/reject_ledger.jsonl` (535 rows, 0 keyword hits for
`goalkeep`/`gk_dist` beyond the already-CONFIRMED #20) before seeding. No
validator built this lane.

### 42. Goalkeeper distribution style vs downstream buildup xG (distinct from #20's retention-only test)
- **claim**: short/ground goal-kick distribution leads to higher expected-goal (xG) value in the ensuing possession than long/high distribution -- a downstream BUILDUP-QUALITY question. NOT a re-test of #20: #20 (CONFIRMED) measures only whether the goal-kick pass itself is retained (0.986 short vs 0.391 long); this row asks whether the possessions that ARE retained then produce better chances, a question #20's design cannot answer.
- **premise check**: `data/cache/statsbomb/events/*.json` (same corpus as #19-#21) confirmed this session to carry a `possession` integer field on every event (sampled file: 3,762 events, 15 goal-kick Pass events, `possession` present on all) and `shot.statsbomb_xg` on every Shot event (sampled shot xg=0.077) -- a goal-kick's `possession` id links directly to any shot(s) sharing that id.
- **causal story**: StatsBomb's own xG Chain/xG Buildup (xGB) framework credits pre-shot possession contributions distinct from raw retention; a short goal-kick keeps the ball at the keeper's feet under less pressure and may enable a more deliberate, higher-quality buildup even though it is not always the higher-retention choice for every single pass -- this tests whether RETAINED short-distribution possessions specifically convert into better chances, not whether retention itself is higher (already answered at #20).
- **expected signature**: positive gap, mean/median max-shot-xG-in-possession (0 if no shot occurs in that possession) for short/ground goal kicks vs long/high goal kicks.
- **test spec**: `domains.soccer.knowledge.validate_research_wave5.gk_distribution_vs_buildup_xg` -- for every goal-kick Pass event, collect all Shot events sharing the same `possession` id within the same match; buildup_xg = max(`shot.statsbomb_xg`) in that possession, else 0; Mann-Whitney U (right-skewed, zero-inflated) short vs long goal-kick possessions' buildup_xg; declared bar |median or mean gap|>=0.01 xG AND p<0.01, given the ~56,262-goal-kick population #20 already established.
- **status**: REJECTED (NULL_LOCAL) -- statistically significant (huge n makes any p tiny, not trusted alone per house convention) but the mean/median gap does not clear the declared 0.01 xG practical-effect bar.
- **measured LOCAL magnitude**: buildup xG, short/ground goal-kick possessions mean=0.0084 (median=0.0, n=25,193) vs long/high mean=0.0042 (median=0.0, n=44,202); mean_gap=+0.0041 (below the 0.01 bar), median_gap=+0.0000, p=7.68e-87, n=69,395 goal kicks (full local event-cache scan).
- **artifact link**: `domains/soccer/knowledge/validate_research_wave5.py::gk_distribution_vs_buildup_xg`; `domains/soccer/knowledge/validation_ledger.jsonl`, hypothesis=`gk_distribution_vs_buildup_xg`.
- **source**: "Upgrading Expected Goals" (StatsBomb Blog Archive), https://blogarchive.statsbomb.com/articles/soccer/upgrading-expected-goals/ -- documents the xG Chain/xG Buildup (xGB) framework crediting pre-shot possession contributions, the literature basis for testing goal-kick style against downstream chance quality rather than mere retention (already CONFIRMED at #20).

---
