# 01 - EVERYTHING NEEDED TO GET TO EDGE (the master action list)
_Part of the edge-intelligence corpus. The single "if we did all this, here is how good it
could honestly get" document. Translates the project deep-dive roadmap
(docs/research/project-deep-dive/00-MASTER.md sections 5-6) into the corpus's executable
intelligence-build plan. ASCII only. Local-only. No fabricated $-edge -- every edge claim is
tagged HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN with the artifact that earns it._

Read first: 00-INTELLIGENCE-MASTER-PLAN.md + _framework/edge-theory.md +
_framework/cut-list-no-edge.md + _framework/proof-standards.md. Cited deep-dive areas use
[NN] = docs/research/project-deep-dive/NN-*.md.

---

## 0. THE THESIS IN ONE PARAGRAPH (honest)

The deep-dive's verdict is unambiguous: this system is "architecturally mid-maturity,
methodologically senior-grade," and "honestly AT its calibration ceiling on efficient
pregame markets" [00-MASTER s.1, s.6]. The work that remains to reach edge is NOT a hunt
for pregame alpha (proven mostly absent: full-season WF matches the close, CLV~0,
17 feature-add reverts) -- it is (a) CAPTURE the evidence we currently lack (closing lines /
CLV: today 0 of 14 settled team bets carry real CLV; ratchet 48/48 INSUFFICIENT_DATA
[06]), (b) CONCENTRATE data + modeling into the six beatable pockets (soft/DFS props, live
lag, stale lines, PM-vs-book, correlated SGP, niche) and CUT the efficient ones, and
(c) STAND UP the always-on host so forward CLV can actually accrue [12]. If we execute the
list below, the honest ceiling is: a clean multi-sport calibrated decision board that
MATCHES_CLOSE on mainlines (a success, not a target), with 1-3 prop pockets that have a
real shot at CALIBRATION-PROVEN -> CLV-PROVEN status once data deepens. That is the whole
honest upside. Anything beyond is unproven until CLV says otherwise.

---

## 1. HOW TO READ THIS LIST

Every item carries:
- **SIZE**: QUICK (days, low risk) / MEDIUM (weeks, modeling+wiring, gate-validated) /
  BIG (changes the ceiling).
- **POCKET**: which beatable pocket it serves (P1 soft/DFS props, P2 live lag, P3 stale/
  soft-book, P4 PM-vs-book, P5 correlated SGP, P6 niche) -- or CUT/INFRA (enables proof but
  is not itself a pocket).
- **BAR**: the validation bar that lets it advance an evidence tier (per proof-standards.md).
- **TIER NOW**: current honest evidence tier of any edge claim attached (HYPOTHESIS /
  CALIBRATION-PROVEN / CLV-PROVEN / NONE-yet).
- **PLAN**: pointer to the per-sport get-to-edge-plan that owns the detail (those files are
  WAVE-1 targets in the master plan; this doc is the cross-sport index that feeds them).

The roadmap IDs (Q*, M*, B*) map 1:1 to deep-dive 00-MASTER sections 5-6 so the corpus and
the deep-dive never drift. Where this doc adds an item the deep-dive did not number, it is
tagged [EI-n].

---

## 2. THE FOUNDATION LAYER -- evidence-capture + honesty (no edge is provable without this)

These do not create edge; they make edge KNOWABLE. They are the gating prerequisite for
every CALIBRATION-PROVEN / CLV-PROVEN claim below. Do these FIRST.

### F1 (=Q1) Capture closing lines -> accrue CLV. SIZE QUICK. POCKET INFRA. TIER NONE-yet.
The single highest-leverage lowest-effort fix in the whole project. Today every CLV metric
is None; CLV is the ONLY honest bridge from "calibrated" to "pays" (edge-theory.md s.2).
The code exists (scripts/platformkit/clv_ledger.py; data/frontend/clv_ledger.jsonl and
prop_line_history.jsonl exist but prop_line_history has ~1 line [06]). This is a
SCHEDULING/OPS fix: run prop_loop / pm_trading / prop_line_history on a cadence up to
kickoff so the closing-line time series accrues per market.
- BAR: a growing time series of (taken_price, ..., closing_price) per settled market; then
  CLV = sign(taken better than close) over N>=200 per sport (proof-standards.md s.6).
- GOTCHA: betting_portfolio.record_clv() sign is BACKWARDS [07] and proxy-CLV is
  uninformative (last price == taken price -> CLV~0) [06]. Fix the sign and capture a TRUE
  later close, not the taken price echoed back.
- PLAN: every per-sport get-to-edge-plan depends on this; _proof/ ledger tracks it.

### F2 (=B1) Stand up an always-on host. SIZE BIG. POCKET INFRA. TIER NONE-yet.
The self-improving paper loop (pm_trading/auto_loop --forever) only compounds across a full
season; it dies when the 15GB Windows laptop sleeps [12]. ROADMAP Phase 21 (VPS) + Phase 34
(MLOps) both unchecked. A small VPS under supervisor running auto_loop --forever +
refresh_daemon with the ~93MB per-domain parquets synced.
- BAR: continuous uptime across a season so N escapes small-sample variance and the ratchet
  can leave 48/48 INSUFFICIENT_DATA (needs ~60 settled games AND dm.n>=200 per sport [06]).
- WHY BIG: it is the prerequisite for EVERY forward-validated claim. Without it the "+8% on
  paper" stays entirely prospective and no pocket can reach CLV-PROVEN.
- PLAN: _proof/ + cross-sport (host serves all 5 sports).

### F3 (=Q3) Resolve the dead intelligence funnel honestly. SIZE QUICK. POCKET CUT/INFRA.
Atlas features are injected at predict time (CV_PROP_EXTRA_FEATURES default ON) but the
served model was never trained on them, so atlas_* columns are silently DROPPED -- the
train/inference parity gap the project itself calls the most expensive bug class. Honest
3-fold ablation shows atlas features do NOT reduce pts/reb/ast MAE (they increase it);
only fg3m improves trivially [09]. Either (a) retrain per-stat models WITH
atlas_feature_names() then re-run eval_atlas_lift, OR (b) gate CV_PROP_EXTRA_FEATURES OFF
and label atlas scouting-only. Stop the silent no-op that implies intelligence feeds the
model.
- BAR: atlas features must beat raw on >=2 corpora (proof-standards.md s.4) or stay
  descriptive. Current measured verdict: NO LIFT -> default to CUT unless M5 finds a section.
- PLAN: nba/get-to-edge-plan + _framework (cut-list already names this).

### F4 (=Q7) Honesty plumbing on data + odds. SIZE QUICK. POCKET INFRA.
Regenerate/split DATA_INVENTORY.md against REAL data (census is stale: reports ~190
parquets mostly as 0-row [12]); stamp freshness + rowcount heartbeats; tag each odds venue
as sportsbook vs prediction_market so a thin PM "best" price is not shown as bettable
[03]; report n_with_real_close separately so the UI cannot imply CLV evidence it lacks [06].
- BAR: every surfaced price labeled by venue type; every corpus carries last-refresh +
  rowcount; no metric displayed that has 0 supporting settled outcomes.
- WHY IT MATTERS FOR EDGE: P4 (PM-vs-book) is only a real pocket if PM and book prices are
  NOT mixed into one best_line as if interchangeable -- the deep-dive's load-bearing
  correctness risk [03 s., 00-MASTER s.4.11].

### F5 (=M2) Run the eval gate against a REAL frozen corpus + wire CRPS/pinball. SIZE MEDIUM.
Today --golden runs only a SYNTHETIC near-oracle fixture with a toy ridge predictor;
--corpus raises offline; baselines are explicitly _synthetic:true [06]. So the gate proves
the HARNESS is non-regressing, not that the production model is calibrated. CRPS/pinball +
the in-game blend are built and tested but NOT wired into the verdict (binary BSS only).
- BAR: gate verdict computed on real per-sport frozen corpora with real Shin-devigged
  closes; continuous markets (totals/margins) and served prop intervals each get their own
  frozen baseline; only-improve-or-hold ratchet (proof-standards.md s.; gate is the ONLY
  arbiter).
- WHY: until this lands, NO claim above HYPOTHESIS is gate-backed. This is the machine that
  STAMPS the tier.

> **Foundation gate:** No item in sections 4-6 can be tagged above HYPOTHESIS until F1
> (CLV capture) + F5 (real-corpus gate) produce the artifact. F2 (host) is what lets the
> artifact reach meaningful N. This is the binding sequencing of the whole plan.

---

## 3. THE CUT LAYER -- stop spending here (reallocate to pockets)

Per cut-list-no-edge.md, grounded in measured nulls. Doing LESS here IS part of the plan.

| CUT | What | Evidence | Action |
|-----|------|----------|--------|
| C1 | Sharp pregame MAINLINES (h2h/spread/total, major sports) | Full-season WF matches close, CLV~0; +18.38% was a market-follow+in-sample+flat-payout artifact [00-MASTER s.4, cut-list C1] | Keep as calibrated decision-support + CLV yardstick; STOP hunting $-edge |
| C2 | NBA PREGAME team markets as edge | PTS/REB at data ceiling; 6 arch + 4 levers REJECT; recency>volume; 17 feature reverts [07] | No more NBA pregame team modeling; keep AST prop (RAW); redirect to freshness + props + in-game |
| C3 | Momentum / hot-hand as bet drivers | INT-81 momentum z_vs_null=-1.75; momentum-aligned bets WORSE than random | Form only as a RATE input; never a bet signal |
| C4 | Rare-event props w/ measured negative skill | WC Cards BSS -0.11, Assists -0.07, Goals -0.03, SoT ~0 [04]; likely MLB TB/RBI/Runs analog | DEMOTE to model-view-only; do not paper-bet |
| C5 | Over-flexible recal on thin data | Isotonic P(over) on 24 WC matches overfits OOS [04] | Gate every lever on leak-free OOS; refit only as data grows |
| C6 | Arbitrage as a profit center | Real arbs rare/fragile/limit-constrained | Keep arb DETECTION as a free flag; line-shop for best price as the durable execution edge |

Net: every hour not spent on C1-C6 flows to the pockets in section 4-6.

---

## 4. THE POCKET LAYER -- where edge plausibly lives (concentrate here)

Ranked by realistic beatability (edge-theory.md taxonomy P1-P6). Each pocket lists the
items that build it.

### POCKET P1 -- SOFT / DFS PLAYER PROPS (the primary pocket)
Lazily-priced, high-volume, per-player distributions we can model. THE pocket.

- **P1.1 (=Q5) Backfill MLB player gamelog corpus to 1-2 seasons.** SIZE QUICK. TIER NONE.
  ingest_player_stats.ingest_range (keyless), then re-run props_eval_mlb for the FIRST
  honest per-stat calibration scoreboard. MLB prop engine today = 0 scored predictions on a
  17-day corpus [05] -- it is at ~0% of its ceiling. Unblocks ALL MLB prop work.
  BAR: per-stat OOS Brier/BSS vs realized on a full season; >=2-corpus (use the frozen+
  current MLB era replay [12]). MLB is "the MOST favourable sport for honest calibration
  once a full season is loaded" [05]. PLAN: mlb/get-to-edge-plan.

- **P1.2 (=B3) Add NBA props through the keyless feed (the deep-data prop sport).** SIZE BIG.
  PrizePicks/Underdog NBA already on the same endpoints [03]; join to the existing NBA prop
  surface so prop calibration is cross-validated on MANY seasons, not 24 WC matches. "The
  credible ceiling for the prop board lives where data is deep" [00-MASTER B3].
  BAR: leak-free WF P(over) calibration per stat across multiple NBA seasons; CLV-vs-close
  undefined for DFS pick'em -> prove via P(over) calibration + realized ROI at fixed payout
  + DFS-line MOVEMENT (edge-theory.md note). PLAN: nba/get-to-edge-plan.

- **P1.3 (=M6) Prop-vertical correctness fixes (the calibration bugs that fake edge).**
  SIZE MEDIUM. Fit per-stat NegBinom r from realized outcomes (the widening lever EXISTS
  but is never set -> too-tight distributions invent fat tails -> absurd EVs, an overfit
  trap [proof-standards.md s.; 00-MASTER M6]); inflate NBA prop-interval sigma per the
  documented multiplier (blk ~x1.86 [07]); validate minute-projection error end-to-end
  (backtest with PROJECTED not realized minutes [04]).
  BAR: interval coverage matches nominal OOS; no |EV| flagged implausible after refit.
  WHY POCKET: a too-tight distribution manufactures a fake P1 edge; fixing it is what makes
  any surviving prop edge TRUSTWORTHY. PLAN: per-sport prop-<stat> deep files.

- **P1.4 Concentrate on the PROVEN stats only.** SIZE QUICK. TIER CALIBRATION-PROVEN(thin).
  WC: only Saves clears the proven bar (and that is near-deterministic save-count [04]);
  candidate MLB: Hits / Pitcher-Ks / Walks. NBA: AST is the lone near-durable model
  divergence (~+7%, both directions, never playoffs, keep RAW [07, cut-list KEEP]).
  BAR: each survives >=2-corpus leak-free OOS BSS>0 before it is paper-bet. NOTE: WC "n=662
  per stat" is correlated predictions over ~24 matches, NOT 662 independent obs [04][06] --
  "proven" is suggestive, not bankable. PLAN: per-sport prop-<stat> deep files + _proof/.

### POCKET P2 -- LIVE / IN-GAME LAG (the decisive combinable lever)
Books lag realized state by seconds-to-minutes; the cleanest improvement in the project.

- **P2.1 (=M3) Run the real-corpus NBA in-game blend OOS; end the PENDING flag.** SIZE
  MEDIUM. TIER CALIBRATION-PROVEN(partial). Wire ingame_blend_eval to the 1313-game
  linescore corpus (NOT the synthetic generator); publish ONE leak-free in-game calibration
  scoreboard across all 4 sports: Brier(conditional) vs Brier(pregame) + ECE per game-time.
  The conditioning win is real (NBA Brier ~0.209->~0.159; MLB ~0.241->~0.126 on cited
  corpora, leak-free, RMSE+bias-graded [11][00-MASTER s.3.4]).
  BAR: Brier(conditional) < Brier(pregame) OOS per game-time bin, leak-free, on real
  linescores; >=2 corpora. HONEST CAP: a live book ALSO sees the realized score plus subs/
  pace/injuries we cannot -> this is forecaster QUALITY, dollar-edge ceiling ~zero unless a
  THIN/SLOW in-play market lags us [11][00-MASTER s.6]. PLAN: _live/ + per-sport.

- **P2.2 (=B6 partial) In-game prop DISTRIBUTIONS conditioned on realized minutes/usage.**
  SIZE BIG. TIER HYPOTHESIS. "The highest-upside frontier, bound by live-feed depth +
  leak-free corpus size (N=3 PBP replay)" [11]. Build a real live possession/event NBA feed
  (substitutions/pace/foul state) and condition prop distributions on it.
  BAR: leak-free OOS calibration of the conditioned prop vs realized, on a corpus far larger
  than N=3. Until the feed + corpus exist this stays HYPOTHESIS. PLAN: _live/ + nba.

### POCKET P3 -- STALE / SOFT-BOOK LINES (execution edge, model-free)
Line-shopping for best price is the durable execution edge (cut-list C6: arb is NOT).

- **P3.1 Best-line + stale detection across venues.** SIZE QUICK-MEDIUM. TIER HYPOTHESIS.
  odds_shop already does Shin devig / best-line / EV / arb [03]. Make stale-detection a
  first-class flag (one venue lags consensus after movement elsewhere). Capped by keyless
  breadth: ESPN republishes ~one book [03] -> P3 is thin until more venues are wired.
  BAR: realized price improvement vs consensus close on taken bets (a CLV-adjacent metric).
  PLAN: _scrapers/ + per-sport markets-and-props.

### POCKET P4 -- PREDICTION-MARKET vs SPORTSBOOK divergence (two crowds)
Kalshi/Polymarket vs books. REAL only if venues are NOT mixed (see F4).

- **P4.1 PM-vs-book divergence detector.** SIZE MEDIUM. TIER HYPOTHESIS. Keyless Kalshi/
  Polymarket already ingested [03]. After F4 tags venue type, compute the divergence and
  test whether the book or the PM is the better predictor of the outcome (which crowd leads).
  BAR: leak-free OOS -- does taking the divergent side beat the consensus close? CLV on the
  book side. CAVEAT: PM contracts are not always bettable size; treat as signal not income
  until proven. PLAN: per-sport inefficiency-catalog + _scrapers/.

### POCKET P5 -- CORRELATED SGP MISPRICING (the one structural advantage)
Books price SGP legs independently, misjudging joint probability; we have a COHERENT joint.

- **P5.1 Price SGPs from the NBA possession joint sim.** SIZE BIG. TIER HYPOTHESIS. The
  shared-scoring-pie sim makes teammate correlation EMERGE (~-0.10, matching real); one
  ~3-4s GPU run prices the entire prop/combo/SGP surface coherently -- "the one thing a
  marginal prop model structurally cannot do" [08][00-MASTER s.3.5]. correlation_recal is
  already the one genuinely-wired intelligence use (parlay coherence) [09].
  BAR: the joint's SGP price must beat the book's independent-leg price OOS on realized SGP
  outcomes; AND the sim's in-sample constants must clear a leak-free multi-corpus WF gate
  (currently UNVALIDATED, NYK/SAS-deep only [08]). Two bars: prove the joint, then prove the
  SGP edge. PLAN: nba/inefficiency-catalog + deep archetype-correlation files. CUT GUARD:
  do not bet SGPs whose legs include CUT stats (C4) or momentum (C3).

### POCKET P6 -- NICHE / LOW-ATTENTION markets
Thin bookmaker attention -> lazier pricing.

- **P6.1 World Cup / soccer-intl + niche prop ladders.** SIZE MEDIUM. TIER HYPOTHESIS.
  WC engine exists (24 matches; bound by DATA DEPTH first [04]). Niche international /
  lower-league markets get less sharp attention.
  BAR: once matchdays accrue, leak-free OOS P(over) calibration on the 2-4 high-volume
  near-deterministic markets (Saves first). Bound by data depth THEN minute-projection error
  THEN efficiency [04]. PLAN: soccer_intl/get-to-edge-plan.

---

## 5. THE LEVER LAYER -- the one real pregame lever + the structural-debt items

### L1 (=B2) Same-day FRESHNESS ingest (the ONLY real pregame accuracy lever). SIZE BIG.
TIER HYPOTHESIS. Everything historical is at the data ceiling; this is the one input that
could close the gap to the close on totals/props [07][05][08]. Ingest projected minutes /
starting lineups / late scratches / load-management / weather / confirmed pitcher at SLATE
time and wire them in BOTH train and inference builders (parity -- the most expensive bug
class).
- BAR: leak-free WF lift vs the close (NOT vs our own past). HONEST CAVEAT: the sharp book
  ALSO sees the confirmed lineup/pitcher/weather [00-MASTER s.6] -> freshness likely only
  closes the gap to MATCHES_CLOSE on the soft/slow venues, not beats Pinnacle. Keyless feeds
  do NOT give same-day lineups/closing lines [12] -> acquisition is itself a sub-project.
- PLAN: per-sport data-sources + datasource-<name> deep files.

### L2 (=M4) Wire the MLB SP lever into the live MLBPredictor. SIZE MEDIUM. TIER HYPOTHESIS.
The validated sp_elo_offset (logit + w*z_sp) is built but NOT wired into the live number
[05] -- so the delivered MLB win-prob ignores WHO IS PITCHING, the single biggest MLB game
variable. MLB pitcher data is era-limited (2010-2021) so recent runs go pitcher-blind [12].
- BAR: leak-free WF -- does adding SP improve the team-model Brier vs the close? Promote
  only if it does not regress the frozen baseline (gate ratchet).
- PLAN: mlb/get-to-edge-plan + model-levers.

### L3 (=M5) Per-section atlas lift + promote the 5 validated signals. SIZE MEDIUM.
Run eval_atlas_by_section.py to find the 1-3 sections that clear ALL folds and wire ONLY
those; explicitly graft+retrain+re-gate the 5 VALIDATED signals (pbp_origin_transition,
rest_x_age, shot_clock_leverage, opp_position_defense_reb, oreb_matchup) [09].
- BAR: each section/signal must beat raw on >=2 corpora (selection trap: 44 atlases, do NOT
  report the best of many -- pre-commit or bonferroni [proof-standards.md s.4]). Most atlas
  sections measured ~0 lift -> expect mostly CUT (a null is a success). PLAN: nba/model-levers.

### L4 (=B4) Wire next-tier data + the funnel. SIZE BIG. TIER HYPOTHESIS.
Stop discarding next-tier data at ingest; make atlas/intelligence an ACTUAL gated predict-
time input (must beat raw on >=2 corpora or stay descriptive); backfill per-date atlas
snapshots so historical backtests can even SEE atlas state [01][09].
- BAR: gated lift over raw on >=2 corpora. Measured baseline is NO LIFT [09] -> burden of
  proof is high; default outcome is "stays descriptive scouting asset." PLAN: nba + _live.

### L5 (=B5) Fix the CV keystone: scoreboard OCR per frame. SIZE BIG. TIER HYPOTHESIS(low).
Make scoreboard_ocr.py read period + decrementing clock + score per frame. Unblocks
PBP-anchoring (bypasses jersey-OCR ~2.3% + shot-detection walls at once) AND per-quarter
slot resolution (kills the 10-slot collapse) [10]. Then land the Bug-1 defender-distance
fix and re-derive features.
- BAR: even fixed, CV's net downstream PREDICTIVE value is thin (measured noise wall [10]);
  defensible value is the geometry asset + systems-engineering proof, ZERO as a prediction
  edge. -> This is INFRA/scouting, NOT a betting pocket. Listed for completeness; LOW
  priority for EDGE specifically (high priority for the CV product story). PLAN: nba/deep.

### L6 (=B6 rest) Model what the chain cannot. SIZE BIG. TIER HYPOTHESIS.
Native same-player joint correlation (replace bolt-on CV_MIN_VAR corrector); explicit
minutes/foul-out rotation model; extend recency + PBP + team_defense builders to all 30
teams (currently NYK/SAS-deep, league-shallow -> the deepest signal is a two-team artifact
[08]).
- BAR: leak-free multi-corpus WF of the sim's prop predictions (NONE exists today [08]).
  Coverage fix is the prerequisite to make P5 (SGP) generalize beyond two teams.
- PLAN: nba/deep archetype + sim deep files.

---

## 6. THE MATURITY / SERVING LAYER -- not edge, but the product the edge rides on

These are CUT/INFRA for edge but load-bearing for the sellable ceiling (engineering +
honest calibration, per 00-MASTER s.6). Do them, but do not mistake them for edge.

- **Mat1 (=Q2) Reconcile kernel/ with reality.** QUICK. Move sport-blind platformkit into
  matching kernel/ subpackages and re-export, OR rewrite docs/PLATFORM.md to say the kernel
  lives in scripts/platformkit/. Closes the largest doc-vs-code honesty gap [01].
- **Mat2 (=Q4) Mount the React build + freshness pill.** QUICK. app.mount web/dist so the
  premium UI is default at :8098; render a "snapshot N s ago / STALE" pill from
  freshness.as_of [02]. Biggest UX jump; the good UI exists but serve.py returns legacy.
- **Mat3 (=Q6) NBA schema/interval fixes.** QUICK. Retrain on 129-col schema + flip
  _BBREF_REORDER_FIX ON (5/85 live feature slots fed WRONG values; fix exists, default OFF)
  with pkl integrity check; inflate prop sigma; flag STL/BLK low-confidence; fix record_clv()
  sign; delete the multitask_props.py NotImplementedError stub [07].
- **Mat4 (=M1) Finish the snapshot keystone + wire /api/live + /api/props into React.**
  MEDIUM. Every surface reads the snapshot; nothing recomputes in the request path; live +
  WC prop board get first-class screens; CLV tracker tab replaces the placeholder; slate
  sources today's real schedule from live_board [01][02].
- **Mat5 (=M7) Consolidate parallel stacks.** MEDIUM. One authoritative sim (route API
  through basketball_sim/fast_sim); reconcile the two in-game stacks behind one predict_live
  interface; de-dup frontend entry points; archive stranded artifact families (~25
  _backup_iterNN_* dirs 1.3GB, 6.5GB tracking, FanDuel-provider-with-no-consumer) under a
  labeled experiments dir [02][08][11][03].

---

## 7. THE SEQUENCED PATH (if we did all this, in what order)

1. **Foundation first (F1, F4, F3 -- all QUICK; F5 MEDIUM).** Without CLV capture + a real-
   corpus gate + an honest funnel + venue tagging, nothing below HYPOTHESIS can be earned.
   F1 is the single highest-leverage action in the project.
2. **Stand up the host (F2 BIG).** The moment the gate is real, the loop must run 24/7 or N
   never reaches significance. F2 gates every CLV-PROVEN claim.
3. **Feed the primary pocket (P1.1 QUICK -> P1.3 MEDIUM -> P1.4 -> P1.2 BIG).** MLB backfill
   is the fastest path to a FIRST honest prop scoreboard; NBA-via-keyless-feed is the deepest.
4. **Lock the in-game win (P2.1 MEDIUM).** Real-corpus blend eval converts the project's
   cleanest improvement from PENDING to CALIBRATION-PROVEN.
5. **Wire the one real pregame lever (L1 BIG) + the MLB SP lever (L2 MEDIUM).** Freshness is
   the only thing that can move a pregame number; SP is the biggest unmodeled MLB variable.
6. **Probe the structural pockets (P5 SGP, P4 PM-vs-book, P3 stale).** Higher-variance bets;
   each needs its own proof and several are keyless-breadth-capped.
7. **Maturity layer (Mat1-5) in parallel throughout** -- it makes the product sellable but
   does NOT change the number ceiling.
8. **Cut continuously (section 3).** Every cycle, re-ask "is this in a CUT category?" before
   spending.

---

## 8. HOW GOOD CAN IT HONESTLY GET (the ceiling, stated plainly)

If EVERY item above lands and the data deepens:

- **Mainlines (all sports):** MATCHES_CLOSE, BSS~0, CLV~0. This is a SUCCESS by design, not
  a failure. We will never beat Pinnacle on a liquid mainline and we do not claim to.
- **In-game calibration (P2):** CALIBRATION-PROVEN across 4 sports (forecaster quality,
  Brier strictly under the pregame prior). Dollar-edge ~zero unless a thin/slow in-play
  venue lags us -- to be PROVEN by CLV, never asserted.
- **Soft/DFS props (P1):** the ONE place a CLV-PROVEN edge is plausible. Realistic outcome:
  1-3 stats per sport (WC Saves; candidate MLB Hits/Ks/Walks; NBA AST) reach
  CALIBRATION-PROVEN, and SOME subset reaches CLV-PROVEN once the host accrues forward CLV at
  the fixed DFS payout. Most prop stats will be CUT (measured negative/zero skill). This is
  the honest upside and it is modest, real, and unproven until the ledger fills.
- **SGP (P5):** the one structural advantage (coherent joint). Plausibly CALIBRATION-PROVEN
  if the sim's constants clear a leak-free WF gate and coverage extends past NYK/SAS; CLV
  edge is a HYPOTHESIS contingent on books genuinely mispricing correlation.
- **The durable, sellable ceiling is ENGINEERING + HONEST CALIBRATION, not alpha** [00-MASTER
  s.6]: a clean kernel/adapter platform, fail-closed leak-free multi-corpus distribution-
  aware gate, sub-second multi-sport board, CLV as the truth metric. That ceiling is largely
  REACHED for 5 sports; the remaining gap is structural maturity + forward CLV accrual.

**Bottom line:** the methodology is senior-grade and the spine is strong; the project is
honestly at its calibration ceiling on efficient pregame markets. "Everything needed to get
to edge" is mostly EVIDENCE CAPTURE + POCKET CONCENTRATION + an always-on host -- not a hunt
for an edge the system has correctly proven is mostly not there. The few places edge could
genuinely live are named above, each with its proof bar; every one of them is HYPOTHESIS
until CLV says otherwise, and a null is a success.

---

## 9. POINTERS (the per-sport plans this index feeds)

This cross-sport master list hands detail to the WAVE-1 per-sport files (master plan s.
"Generation plan"):
- nba/get-to-edge-plan.md         -- owns C2, P1.2, P1.4(AST), P2.*, P5.1, L1, L3-L6, Mat3.
- mlb/get-to-edge-plan.md         -- owns P1.1, P1.3(MLB), L2, P2.1(MLB).
- soccer_club/get-to-edge-plan.md -- owns C1(soccer mainline), L1(soccer freshness).
- soccer_intl/get-to-edge-plan.md -- owns P6.1, P1.4(WC Saves), C4(WC rare props).
- tennis/get-to-edge-plan.md      -- owns C1(serve-hold mainline), P1(tennis props if any).
- _proof/                         -- the living ledger for F1/F2 + every tier transition.
- _live/                          -- P2.* in-game pocket detail.
- _scrapers/                      -- P3/P4 venue acquisition + F4 venue tagging.
Each per-sport edge-map cites _framework/cut-list-no-edge.md (binding) and tags every claim
with its evidence tier + the gate artifact that earns it.
