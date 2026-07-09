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
- **measured LOCAL magnitude**: possession-level log-loss A: 0.3757 (model) vs 0.3694 (naive); B: 0.3548 vs 0.3504. Match-level home-win Brier A: 0.2482 vs 0.2424; B: 0.1960 vs 0.1955. Naive baseline wins narrowly in all four readings.
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
- **status**: NOT_TESTABLE -- 82 distinct referees officiate the 400-match corpus, but fewer than 10 have >=3 matches in BOTH season halves; too sparse for a per-referee split-half correlation on this slice (referee identity itself was confirmed joinable this session -- the gap is sample density, not the ingredient).
- **artifact link**: `domains/soccer/knowledge/validate_referee_schedule.py::referee_card_rate_persistence`.

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
