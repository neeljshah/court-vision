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

## Seeded, UNTESTED (highest-leverage remaining; run through a validate_*.py before believing)

### 14. Home-advantage decomposition (crowd component)
- **claim**: home-field advantage is not monolithic -- a crowd/atmosphere sub-component is separable from travel and referee-bias sub-components.
- **causal story**: crowd noise affects referee decisions and opponent composure independent of the travel-fatigue or officiating-bias channels.
- **expected signature**: home win-rate should NOT fully explain away once a proxy for attendance/stadium size is added as a control.
- **test spec**: needs an attendance/stadium-capacity ingredient per match -- check `matches/*.json` (`stadium` field is present; attendance is not, per a quick schema check this session).
- **status**: UNTESTED

### 15. Home-advantage decay/growth across a season
- **claim**: the home-win-rate edge is not constant -- it may compress or widen as the season progresses (e.g. fatigue, fixture congestion for away sides).
- **causal story**: early-season home advantage reflects preseason prep asymmetries; late-season may reflect run-in fatigue asymmetries.
- **expected signature**: home win-rate by match-week tercile trending non-flat.
- **test spec**: corpus A only (has `match_week` in the cached `matches/*.json` files); home win-rate by week-tercile, chi-square.
- **status**: UNTESTED

### 16. Referee card-rate individual consistency (split-half)
- **claim**: individual referees differ in how card-happy they are, and that tendency is a stable personal trait, not per-match noise.
- **causal story**: officiating style (letting play flow vs quick to card) is a referee-level trait that should persist across that referee's matches.
- **expected signature**: split-half correlation of a referee's cards-per-match rate.
- **test spec**: the ingredient DOES exist locally (`data/cache/statsbomb/matches/*.json` carries a `referee.name`/`referee.id` field, confirmed this session by reading `2_27.json`) but is not yet joined to `match_meta.parquet` or wired into `_data.py` -- a straightforward follow-up loader, not a data gap.
- **status**: UNTESTED

### 17. Yellow-card accumulation suspension effect
- **claim**: a team missing a suspended player (accumulated-yellows ban) performs worse in that match than its baseline.
- **causal story**: losing any starter to suspension is a talent downgrade; specifically-accumulated (not red-card) suspensions are a clean natural experiment since the absence is scheduled, not injury-correlated with recent form.
- **expected signature**: lower goal differential in a suspension-affected match vs that team's other matches.
- **test spec**: needs a suspension/ban ingredient (accumulated-yellow tracking across a full season) -- likely NOT_TESTABLE on the 200-of-380-match subsample (accumulated-yellow tracking requires the FULL season's card history per player, which our subsample doesn't have); check with the full `matches/*.json` card history before running.
- **status**: UNTESTED

### 18. Set-piece share of total xG
- **claim**: a meaningful share of a team's total shot xG comes from set pieces (corners/free kicks/penalties), and that share varies systematically by team style.
- **causal story**: possession-light, direct-style teams should lean more heavily on set-piece xG share than possession-dominant teams.
- **expected signature**: set-piece xG share correlated with a team's overall possession-share proxy.
- **test spec**: per-team set-piece-xG / total-xG ratio vs team possession share, cross-sectional Pearson r.
- **status**: UNTESTED

### 19. Pressing intensity (PPDA proxy) vs opponent turnover rate
- **claim**: a team's passes-allowed-per-defensive-action (PPDA, a pressing-intensity proxy) predicts how often it forces opponent turnovers.
- **causal story**: aggressive pressing (low PPDA) should directly produce more regains/interceptions in the opponent's build-up zone.
- **expected signature**: negative correlation, PPDA vs opponent-turnovers-per-possession.
- **test spec**: derivable from event data alone (Pressure/Interception/Ball Recovery/Duel event counts vs opponent Pass counts), full event cache, team-match grain.
- **status**: UNTESTED

### 20. Goalkeeper distribution style vs possession retention
- **claim**: a goalkeeper's distribution style (short vs long) predicts how well the team retains possession from that restart.
- **causal story**: short buildup from the keeper should retain possession more often than a long punt into a contested aerial duel.
- **expected signature**: higher immediate-possession-retention rate after short GK distribution vs long.
- **test spec**: `Goal Keeper` event type, distribution length/outcome fields, vs whether the ensuing possession stays with the same team.
- **status**: UNTESTED

### 21. Formation-change mid-match impact
- **claim**: an in-match formation change (tactical shift, not just a personnel sub) measurably changes a team's shot rate or shots-conceded rate.
- **causal story**: a shape change should alter both attacking structure and defensive coverage simultaneously.
- **expected signature**: shot-rate-for and shot-rate-against gap before/after a `Tactical Shift` event, same design as the substitution check (#11).
- **test spec**: `Tactical Shift` event type (confirmed present in the event schema this session, ~558 instances in a 300-file sample), paired before/after window.
- **status**: UNTESTED

### 22. Injury-time added-goals rate
- **claim**: goals are disproportionately likely to be scored in the added-time minutes of each half relative to the added-time's share of total match duration.
- **causal story**: added time is disproportionately end-game-desperation (trailing team throws numbers forward) or game-management (leading team defends deep, concedes fewer chances) -- net direction is an empirical question.
- **expected signature**: goals-per-minute in added time (minute > 45 in period 1 / minute > 90 in period 2) vs goals-per-minute in regulation time.
- **test spec**: full event cache, goal timeline vs each match's own regulation-length cutoff (StatsBomb's own `minute` field already carries this), Welch t-test on per-minute goal rate.
- **status**: UNTESTED

### 23. Corner-to-shot conversion by delivery side
- **claim**: corners taken from one side (e.g. the attacking team's stronger-footed side) produce a shot more often than the other side.
- **causal story**: a right-footed corner-taker's natural inswinger from the left is a more direct threat than an outswinger from the right (or vice versa) -- delivery mechanics change shot-producing probability.
- **expected signature**: shot-within-possession rate differs by corner-taker's side vs foot.
- **test spec**: `Pass` events tagged as corners (`play_pattern.name == "From Corner"`), location + player footedness (not directly in the schema -- would need a footedness lookup, likely a v2 ingredient), vs whether the possession produced a shot.
- **status**: UNTESTED

### 24. Extra-time/knockout fatigue -- likely NOT_TESTABLE on this corpus
- **claim**: teams playing extra time in a knockout match show measurably worse output (shot rate, pass accuracy) in the extra 30 minutes vs regulation.
- **causal story**: accumulated fatigue over 90+ minutes should degrade execution quality in extra time specifically.
- **expected signature**: n/a until extra-time (period 3/4) matches exist in the corpus.
- **test spec**: check `period` value-set across the cached event files for values > 2.
- **status**: UNTESTED -- honest expectation is NOT_TESTABLE, since this corpus (EPL 2015/16 league season + FA WSL league matches) is not a knockout competition and observed periods in every file checked this session were only {1, 2}.

### 25. Squad-rotation (cup vs league) fixture effect
- **claim**: teams rotate their strongest XI out for lower-stakes fixtures (cup rounds vs league), and that rotation shows up as a measurable quality/output dip.
- **causal story**: manager incentive to rest starters for a lower-priority competition.
- **expected signature**: lower average lineup "quality" (proxied by starting-XI regular-starter overlap) in cup vs league fixtures for the same team.
- **test spec**: needs a competition-type tag per match beyond what `match_meta.parquet` carries (it has no competition/round field -- only date/teams/score/corpus); likely NOT_TESTABLE on the current 400-match slice without pulling competition metadata from `matches/*.json`.
- **status**: UNTESTED

### 26. Defensive-block height vs opponent shot location
- **claim**: a team defending in a deeper block concedes shots from further out (lower average shot xG per attempt) than a team pressing higher up the pitch, even though it may concede MORE shots overall.
- **causal story**: a deep block cedes the ball but protects the highest-value central/close-range area; a high press risks fewer-but-higher-quality chances against on the counter.
- **expected signature**: negative correlation between a team's average defensive-action location (proxy for block height) and opponent's average shot xG per attempt.
- **test spec**: average `location` of Pressure/Tackle/Interception events (defensive block height proxy) vs opponent's mean `shot.statsbomb_xg`, team-season grain.
- **status**: UNTESTED

### 27. Away-goal timing asymmetry (does the away team's first goal carry extra value)
- **claim**: an away team's first goal shifts win probability by more than a home team's first goal of the same match-minute, because it removes the crowd/atmosphere tailwind from the home side.
- **causal story**: silencing a home crowd has an extra psychological effect beyond the scoreline itself.
- **expected signature**: larger post-goal shot-rate shift (of both teams combined) for away-team goals than home-team goals, matched on match-minute.
- **test spec**: same state-segment machinery as the leading-team check (#9), split by which side (home/away) scored, matched-minute comparison.
- **status**: UNTESTED
