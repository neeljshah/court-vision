# Prediction Signal Gap Analysis v2 (cycle 84d research)

Follow-up to `prediction_signal_gaps.md` (cycle 78d). Research-only, no code
change. Focuses on **non-obvious second-order signals**, **variance-reduction
angles**, **player-cluster effects**, and **stat-specific architectural wins**.

Cross-referenced: cycle 78d TIER 1/2/3 (NOT re-listed) + CLAUDE.md "Saturated
angles" + cycles 79/81/82 empirical rejections (scale-by-status, pull_l5/l10,
B2B factor — all post-prediction adjustments now PROVEN dead on holdout).

**Key framing change from cycle 78d:** Post-prediction MULTIPLICATIVE
adjustments on holdout features don't free MAE (6/6 rejected). New gains
must come from (a) **new input features** that change tree splits, (b)
**conditional/segmented models** that route by player type, or (c)
**variance-reduction** rather than mean improvement.

---

## TIER 1 — NEW gaps (not in cycle 78d)

| # | Signal | Validatable on 99K holdout? | Effort hrs | Expected MAE impact | Sketch |
|---|---|---|---|---|---|
| 1 | **Per-segment models (top-USG vs role player)** | YES — split holdout by `bbref_usg_pct >= 0.25` vs < 0.20, train 2 XGBs per stat, validate WF | 6 | MEDIUM (-1 to -2% MAE on stars; role-player tail tighter) | Cycle-82 heteroscedasticity ("MAE 3.55 at pred<8 → 6.35 at pred>22") is exactly what segmentation fixes. Trees can't easily learn a different splitting policy for the right tail. |
| 2 | **AST-specific: assisted-FG-rate of teammates** | YES — recompute from gamelog | 4 | MEDIUM for AST | When teammates have low `pct_FG_assisted`, AST opportunities collapse (isolation-heavy teammates ≠ AST scorers). Pull `playertrackshooting` `pct_assisted` per teammate, weight by their L5 minutes; add as `team_assistability` feature. |
| 3 | **BLK-specific: opponent rim-frequency × player block_rate** | YES — `data/defender_matchups/` already pulled (cycle 78a `boxscorematchupsv3`) | 5 | MEDIUM-LARGE for BLK only | BLK is sparsest stat (mean ~0.7) — biggest % movement available. Interact `opponent_rim_FGA_rate` × `player_blk_pct_l20`. BLK already got -16% from q50 (median ≠ mean for rare events) — second architectural win likely here. |
| 4 | **TOV: opponent steal-rate × player USG interaction** | YES — opp_def_stl + usg_pct both exist | 1 | SMALL-MEDIUM for TOV | TOV is jointly determined by player ball-handling load AND opponent ball pressure. Raw `opp_def_tov` doesn't capture that high-USG players get hunted differently than low-USG. Tree can almost learn this, but explicit interaction often unlocks 0.5-1% MAE. |
| 5 | **Quantile head per-player-cluster calibration** | YES — cycle 40 quantile_calibration.py already shipped global scaling; extend per-cluster | 6 | VARIANCE (improves Kelly sizing > MAE) | Cycle 40 calibrates q10/q90 globally. Star scorers (μ~25 PTS, σ~8) and role players (μ~9, σ~5) have different empirical coverage. Per-cluster scale factor → tighter Kelly sizing on +EV bets. Doesn't move MAE; moves ROI. |
| 6 | **Stratified per-stat ensemble weights by player segment** | YES — re-run NNLS within each segment | 4 | SMALL-MEDIUM | NNLS weights are global today. For stars XGB-q50 might dominate; for role players LGB-q50 or mean-blend wins. Per-segment NNLS likely picks different mix. |
| 7 | **Game-script bias: AST/TOV in blowouts (model gap from cycle-82)** | YES — backfill vegas spread + flag `abs(score_diff_at_q3) >= 12` | 3 | SMALL-MEDIUM (specifically AST + TOV) | Cycle-82 stratified by rest/opp_def, never by SCORE STATE. Blowout 4th-quarter minutes are bench-heavy — AST/TOV per minute collapse, but model predicts as if starters were in. (Adjacent to cycle 78d's "blowout_risk" but pre-game spread only proxies this; the better feature is *historical* avg garbage-time-min per player.) |
| 8 | **Rolling **variance** of stat as feature (not mean)** | YES — compute std over L10 from existing gamelog | 2 | SMALL for MAE / MEDIUM for quantile heads | `l10_pts_std` already exists. Add to BLK/STL/FG3M where it's missing. Quantile heads benefit directly — pinball loss scales with σ. |
| 9 | **Player-archetype embedding (k-means on bbref pct features)** | YES — fit k=8 archetypes once, add cluster_id as categorical feature | 5 | SMALL | Trees auto-learn from raw bbref pcts already; explicit cluster id rarely beats it. Long-shot but cheap; ship if WF survives. |
| 10 | **Days-into-season interaction (early-season noise vs late-season role lock)** | YES — already have game_date | 2 | SMALL | Early-season L5 is noisier than late-season L5 (small sample × rotation churn). Decay `l5_*` weight as `games_played` rises, blend with prior-season. Half free, half overlap with `prev_<stat>`. |
| 11 | **Same-quarter usage substitution (when star sits Q2, who absorbs)** | YES if PBP lineups available — `possessions_enriched.csv` may have it | 8 | MEDIUM-LONG-SHOT | Stronger version of cycle 78d "teammate-usg-absorbed": condition on which specific bench unit plays the most off-star minutes. Player-by-player lineup combinations from PBP. |
| 12 | **Vegas line as FEATURE not adjustment (mentioned 78d but reframe)** | NO — historical lines not in holdout | 4 backfill + 2 wire | LARGE if backfilled (cycle 78d called this out) | Reframing: cycle 78d had this in TIER 1 but as 3 cheap features. The CRITICAL one is `vegas_total - 222.5` (deviation from neutral); raw total swamps it in tree splits. |

NOTE: #12 overlaps cycle 78d but the SUB-FEATURE engineering (deviation
from league mean) is new. Keep as TIER 1 with the caveat.

---

## TIER 2 — Worth a probe if cheap

| Signal | Effort hrs | Expected impact |
|---|---|---|
| **Per-stat huber delta tuning per-segment** (cycle 18 sqrt+Huber is global) | 3 | SMALL — Huber delta differs by σ; stars need bigger δ |
| **Lineup-mate offensive rating** (different from teammate-out: who's ON the court) | 8 | SMALL-MEDIUM for AST |
| **Per-coach pace tendency** (in-season cumulative) | 3 | SMALL — overlaps team pace |
| **Foul trouble carryover (l5_fouls > 4 → next-game minutes proxy)** | 2 | SMALL |
| **Days-since-30-min-game** (cycle 78d TIER 2; minor reframe = "blowout-rest indicator") | 2 | SMALL |
| **Half-court vs transition split** (player's pts per possession-type from Synergy) | 6 | SMALL — overlaps existing pt_* freq features |
| **Specific announcer/broadcast injury flags** (user-mentioned long-shot) | 20 | NEAR-ZERO — beat-writer Twitter already in 78d TIER 3 as poor signal |
| **Per-REF-assignment (not crew)** | 3 | TINY — referee individual game logs accessible but signal-to-noise low |

---

## TIER 3 — Long shots (label honestly)

- **Travel-altitude × player asthma history** — no public data, dead.
- **Weather** — confirmed dead in 78d TIER 3.
- **Crowd attendance** — dead.
- **Per-ref tendency on specific players** (does ref X call player Y differently?)
  — sample too thin per pair, dead.
- **Sleep tracker / wearable data** — not public.
- **In-game tweet sentiment 15 min pre-tip** — latency lower than 78d's
  90-min Twitter signal but still noisy; UNLIKELY.

---

## Considered but RULED OUT

**Already in cycle 78d TIER 1:**
- Vegas total/spread (kept #12 above only to add the deviation-from-mean
  engineering note — otherwise dupe)
- Projected minutes from lineups
- Teammate-out usage absorption (cycle 78d already proposed; #11 above is
  the stronger same-quarter version)
- DvP / position-aware defense
- Sportsbook line as feature
- Team pace
- Recent-minutes-only form

**Saturated per CLAUDE.md / commit history:**
- Older-season weighting (recency_decay tuned)
- CatBoost 4th learner (cycle 13)
- Prior-season player tracking (cycle 14)
- Officials crew standalone (cycle 15)
- Per-game advanced rolling stats (cycles 6, 8)
- WinProb arch (cycle 45)
- Multitask bootstrap AST/STL (cycle 45)
- Huber-on-log1p for 6 stats (cycle 19)
- Per-minute rates as features (cycle 4)
- AST q50 dispatch (cycle 27 — WF positive, prod negative)
- HP micro-sweeps, single-feature additions, alt loss surfaces

**Empirically dead per cycles 79/81/82:**
- Scale-by-status (aggressive AND mild)
- Pull-toward-L5 / pull-toward-L10
- B2B multiplicative factor
- Any post-prediction multiplicative on existing features

---

## Recommended next 2 cycles

### Cycle 85d — Per-segment models (#1)

Single highest-ROI new idea. Cycle-82 stratified analysis proved MAE
heteroscedasticity is real (3.55 → 6.35 across pred-magnitude buckets) and
that simple scaling can't capture it (cycles 79/81/82 all rejected).
Segmented models CAN — they learn a different tree topology per segment.
Split by `bbref_usg_pct >= 0.25` (stars) vs < 0.20 (role) vs middle, train
3 XGBs per stat, WF-gate. Expected: -1 to -2% PTS/REB/AST MAE on stars.
Cheap (one new training loop, no new data).

### Cycle 86d — BLK-specific opp rim-frequency interaction (#3)

BLK already got the biggest single-stat win this loop (-16% from q50).
The next BLK win is the rim-attempt interaction — already have the data
(`data/defender_matchups/` from cycle 78a). Wire `opp_rim_fga_rate ×
player_blk_pct_l20` as one new feature, WF-gate. Expected: -2 to -5% BLK
MAE (BLK is sparse so % moves are large; absolute MAE delta small).

Both fit the dual-gate (WF 4/4 AND prod single-split MAE down) and are
testable in under 2 hours of compute each.

---

## Closing note

Cycle 78d called out "remaining gains are DATA problems." This v2 adds:
**remaining gains are also SEGMENTATION problems**. The model is at
empirical ceiling on a GLOBAL features-list approach; per-segment training
+ stat-specific architectural moves (like BLK→q50) are the unexploited
direction. Most TIER 1 items here ARE validatable on the existing 99K
holdout — no historical backfill required (unlike 78d's Vegas wires).
