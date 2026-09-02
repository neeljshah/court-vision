# In-game signal program -- ranked preregisterable hypotheses over data already on disk (2026-09-03, lane G1)

Scope: the in-game lane is the only lane with a measured advantage over its own raw model
(E4 +0.0297 vs raw on MLB window 1, S43's tail diagnostic), and it is still BEHIND the
market anchor everywhere it has been scored. Every hypothesis below is stated with its
corpus, incumbent, exact bar, the information it could add and its leak risks; none is a
claim. Calibration language only. The two top items were run as charged trials this
session (sections 2 and 3); the rest are queued in rank order.

Corpora on disk (STEP 0, all counted this session):
- MLB window 1: 178 games / 52,558 ticks / 7,158 in-window (2026-06-28..07-12); scored
  set 47,104 ticks / 158 games (`hedge_trial_arms.load_corpus`); window 2 accruing (S55).
- NBA checkpoint corpus: `data/cache/inplay_odds/nba_checkpoints_full.parquet` 465,249 rows
  / 1,593 games, 2024-10-22..2026-06-13, Polymarket, all traded; halftime checkpoint
  reachable in 1,593/1,593; corpus_units 2024-25 (656) / 2025-26 (937).
- Soccer in-game states: `data/cache/ingame/soccer_states__{eng1,esp1,ger1,ita1,wc_2026,
  combo_*}.parquet` (eng1 7,220 rows: minute, goals, p0, frac_elapsed) + shot / xG-location /
  card state tables; NO in-play market close on disk (S02's close is pregame).
- Tennis in-game states: `tennis_states__{atp,wta}.parquet` (ATP 40,516 rows: set/game
  score, p0, surface), `tennis_gamestate__*`, `tennis_setdetail__*`; NO in-play close.
- MLB pitch / at-bat / half-inning states 2021-2026 (`mlb_*states__*.parquet`); only 2021
  overlaps a close, and that close is pregame (S10).

## 1. Ranked list

| rank | hypothesis | corpus / incumbent | exact bar | expected information | leak risks | status |
|---|---|---|---|---|---|---|
| 1 | MARKET-ANCHOR CLAMP FAMILY: e4 leak-free game-first-date variant, clamp d in {0.10, 0.15, 0.25} x w_max in {0.5, 1.0, 2.0}, ONE family of 9, config chosen INSIDE the folds (inner cpcv_evaluate over train games, outer game-first-date walk-forward) | MLB window 1, 47,104 ticks / 158 games; incumbent e4_gd 0.206786 | improvement >= 0.004 AND game-clustered DM CI lower > 0 AND deflated_p < 0.05 at launch K AND family BH q 0.05 (9 configs + composite); PBO reported; SINGLE-WINDOW | the guard is where E4's gain lives (+0.0257 of +0.0297); the leaky PBO table ordered configs by clamp tightness -- market pull; S43: the gain is in the tail (share > 0.8 on the loser raw 0.42 / e4 0.16 / market 0.15) | inner selection must never see an outer score; self-leak across UTC midnight (S36, fixed by game-first-date folds); a tighter clamp converges on the anchor -- an AHEAD is calibration toward the market, never against it | TRIAL A -- section 2 |
| 2 | NBA HALFTIME ON THE AS-OF ELO PRIOR (S63 reconstructible version): p0 = ratings.replay strictly before game_date, pure repricer price_checkpoint, per-game deltas archived | NBA 1,593 halftime checkpoints; incumbent = the Polymarket halftime price | same four conditions; two corpus_units through replication_gate (Q5) | the old artifact's CI [-0.0098, 0.0015] was the closest-to-resolving in-game row but had no as-of and no deltas; thin in-play liquidity at halftime; a rating prior conditioned on the realised margin | prior vintage (run-time Elo in the old artifact); checkpoint selection; ticker home/away parse; stale prior for 78 playoff games (games.parquet ends 2026-04-12) | TRIAL B -- section 3 |
| 3 | REGIME-CONDITIONAL CLAMP: clamp width d chosen per inning bucket (early 1-3 / mid 4-6 / late 7+) inside the folds, family of 3 x 3 = 9 per bucket | MLB window 1, same 47,104 ticks; incumbent = the trial A composite if AHEAD, else e4_gd | same four conditions; family = ingame_mlb_clamp_regime (27 members) | E4's gain vs raw grows late (+0.0106 / +0.0226 / +0.0691 by bucket); S06 named regime heterogeneity (-0.0053 innings 1-3 vs +0.0484 innings 7+) | 27 members on one window -- family bar bites; the late bucket has the fewest ticks (11,911) and the highest ICC; S58-1 showed per-regime RECALIBRATION (e2) is BEHIND -- this differs only by clamping, not refitting | queued; run only after window 2 (S55) reaches 30 games, so the second corpus exists |
| 4 | TAIL-ASYMMETRIC GUARD: clamp tighter (d_hi) when the raw model is on the confident side (|p - 0.5| > 0.3) and looser (d_lo) otherwise, chosen inside the folds | MLB window 1; incumbent e4_gd | same four conditions; family of 6 (d_hi in {0.05, 0.10} x d_lo in {0.15, 0.25, 0.35}) | S43: the guard's whole gain is the tail (loser-peak share > 0.9 raw 0.358 vs e4 0.111 vs market 0.074); trial B reproduced the same tail defect on NBA (model > 0.8 on the loser 11.4 pct vs market 5.6 pct) | an asymmetric clamp is two parameters fit on 158 games; the confident-side cut (0.3) must be frozen, never tuned | queued behind 3 |
| 5 | NBA HALFTIME WITH AN AS-OF SIGMA: margin sigma re-estimated per season strictly before game_date (walk-forward) instead of the module's 13.5 constant | NBA 1,593 checkpoints, two units; incumbent = trial B's model (0.171360) and the market | same four conditions vs the market; vs trial B's model reported descriptively | trial B: ECE model 0.054 vs market 0.017 and a 2x tail-share excess -- the repricer's fixed sigma over-states confidence at halftime; a season-as-of sigma is the smallest change that could fix calibration without touching the prior | sigma must be fit on games strictly before each date (walk_forward); the 2024-25 unit has only one prior season of NBA margins on disk | queued; needs the S63 follow-up row |
| 6 | NBA end-Q3 and Q4-under-5 checkpoints on the as-of prior (the other three anchors of the old artifact) | NBA corpus, ~1,593 each | same as trial B | later anchors carry more realised information; the old artifact never separated them either | Q4-under-5 is close to determined; any AHEAD there is the market lagging a resolved game (freshness, not skill) -- must be labelled | queued |
| 7 | SOCCER in-game xG-location state vs the pregame close carried forward (no in-play close exists) | soccer_states + soccer_shotxgstates, eng1/esp1/ger1/ita1 | model-vs-model only (p0 carried vs p0 + state); NOT a market-relative verdict | the state tables exist and are joined by (game_id, asof_idx); a market-relative claim is impossible until an in-play soccer close is on disk | no market anchor: cannot enter the market-relative harness; would be a calibration-only row | blocked on an in-play soccer close |
| 8 | TENNIS set/game-state repricing (ATP/WTA as two corpus_units) vs the pregame devigged close carried forward | tennis_states__atp 40,516 rows / wta | model-vs-carried-close; NOT an in-play verdict | ATP + WTA is the one place the S08 two-corpora floor is native (S58 item 5); the pregame close is a weak in-game incumbent | no in-play tennis close on disk; a carried close is a straw incumbent and must be labelled as such | blocked on an in-play tennis close |

Ranks 1-2 were chosen because they are the only two with a real in-play market anchor on
disk AND a reconstructible model side; 3-6 reuse those two corpora; 7-8 have states but no
anchor and cannot produce a market-relative verdict today.

## 2. Trial A -- MARKET-ANCHOR CLAMP FAMILY (charged; ledger 15 -> 16; K = 16)

VERDICT: NULL (SINGLE-WINDOW). 47,104 ticks / 158 games: candidate (inner-selected
composite) 0.205920 vs incumbent e4_gd 0.206786, improvement +0.000866 (bar 0.004 unmet),
game-clustered DM CI [-0.000364, 0.002096], raw p 0.1662, deflated_p 1.0 at K = 16, family
BH (n = 10) bh_adj_p 0.2375 -- all four conditions fail. PBO over the 9 outer series 0.0;
ESS n_eff 566. The inner selection was operative on only 5 of 13 folds (12,947 ticks,
27.5 pct): on the first 8 folds an instrument defect (one purged-empty test state fails the
whole config's inner run) triggered the prereg'd fallback to the incumbent, so 72.5 pct of
the candidate IS the incumbent. Where it ran it was unanimous for the tightest clamp
(e4_w0.5_d0.10), and the descriptive per-config OUTER table puts every d=0.10 config
+0.0052 ahead (raw p ~0.0025) and every d=0.25 config -0.0115 behind -- the market-pull
ordering, now seen OOF, but NOT selectable on the outer score (prereg). NEW GAP filed:
repair the inner runner, re-prereg, re-charge (a new trial, never a re-score).

Memo: docs/evidence/harness/S58_trialA_clamp_family_2026-09-03.md; prereg
S58_TRIALA_PREREG_2026-09-03.md (9c88ea7e8, seal f93c07be...bbf).

## 3. Trial B -- NBA HALFTIME ON THE AS-OF ELO PRIOR (charged; ledger 16 -> 17; K = 17)

VERDICT: BEHIND, replicated on 0 of 2 corpus_units. Pooled 1,593 games: model 0.171360 vs
market 0.164777, improvement -0.006583 (bar 0.004 unmet), DM CI [-0.011503, -0.001664]
(cluster = game), raw p 0.008754, deflated_p 0.148822 at K = 17, family of one (NOT
frozen). Units: 2024-25 n 656 -0.011575 CI [-0.019090, -0.004060]; 2025-26 n 937 -0.003089
CI [-0.009593, 0.003415]. ECE model 0.054 vs market 0.017; the model put > 0.8 on the
eventual loser in 11.4 pct of lost games vs the market's 5.6 pct (S43's tail defect on a
second sport). The old run-time-Elo -0.0040 is not reproduced: the honest as-of number is
-0.0066 with a CI excluding 0. Per-game deltas archived (Q9). No pod job was needed: the
as-of replay is 0.1 s per date and the repricer is a pure function, so the "~7 h" of S63
was the subprocess dispatch path, not the computation.
Memo: docs/evidence/harness/S58_trialB_nba_halftime_asof_2026-09-03.md; prereg
S58_TRIALB_PREREG_2026-09-03.md (a6f5e614f, seal 5dbdff42...ecc).

## 4. What the two verdicts say together (calibration language)

Both in-game model sides are BEHIND their in-play anchor, and in both the shortfall is the
tail: premature confidence on the eventual loser. The MLB guard already borrows the market
to fix that; the NBA repricer does not, and pays 0.0066. The next honest step is not a new
signal but a calibration fix on the NBA side (rank 5) and the second MLB window (S55) so
that a clamp result can ever be more than SINGLE-WINDOW.

## NOT VERIFIED

- Ranks 3-8 are unscored; their "expected information" lines are reasons to prereg, not
  results.
- No in-play close exists for soccer or tennis on disk; ranks 7-8 are blocked, not tested.
- The MLB window 2 count was not re-measured this session (S55 says accruing).
