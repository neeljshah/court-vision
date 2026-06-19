# 00 - MASTER: Whole-Project Synthesis

Synthesis of the twelve area deep-dives (01-12) into one picture of the system at
`C:/Users/neelj/nba-ai-system`. READ-ONLY synthesis; ASCII only.

Binding honesty rails (carried from every area doc): markets are efficient; the
honest north star is CALIBRATION (match the Shin-devigged closing line within noise),
NOT a dollar edge. Everything betting-side is PAPER-only, `executed=False`. The famous
retracted artifacts (+18.38% / 0.119 / +54% / 78.11) are documented measurement
artifacts and are never repeated as live results. An honest REJECT / NULL is a SUCCESS.
Where a thing is thin / in-sample / stranded / unvalidated, it is flagged as such.

Area citations below use [NN] = `docs/research/project-deep-dive/NN-*.md`.

---

## 1. EXECUTIVE OVERVIEW

**One repo, two systems.**

- **Half A -- the origin NBA CV/AI system** (~3 months, 1,470 commits). A broadcast-
  video computer-vision -> ML -> FastAPI production stack: YOLOv8 detection -> SIFT
  homography -> Kalman+Hungarian tracking -> OSNet/HSV re-ID -> EasyOCR -> EventDetector
  produces court-coordinate tracking [10], which feeds a ~190-feature multi-output
  prop/win-prob ML stack [07], a player-level possession Monte-Carlo simulator + 2K-style
  role-aware ratings [08], a large descriptive intelligence/atlas layer [09], a legacy
  in-game projector [11], a Kelly/CLV betting layer, ~99 FastAPI endpoints, and an
  autonomous LLM-free signal-discovery loop. This half is "real engineering history" and
  the NBA data substrate, but it is largely NOT the live product and contributes ~0
  measured predictive lift [01][09][10].

- **Half B -- the current frontier: a domain-agnostic calibrated multi-sport forecasting
  + betting-decision-support product** (2026-06). Per-sport adapters
  (`domains/<sport>/predictor.py`) emit a coherent pregame market surface + an in-game
  repricer, judged by a sport-blind fail-closed eval gate [06], surfaced through a
  snapshot-backed React/FastAPI front end [02], fed by a keyless multi-book odds + prop
  aggregator [03], with paper-only prop engines for World Cup soccer [04] and MLB [05],
  and an always-on paper-bet + self-improve loop [06][12]. Five sports
  (NBA, MLB, soccer/EPL, World Cup, tennis) implement the same `predict` / `to_jd` /
  `predict_live` interface.

**The funnel** (as wired in Half B):
DATA (`ingest_*`) -> SIGNALS (`signal_catalog`, leak-safe `asof_*`) -> MODELS
(`ratings.py`: Elo/per-90/serve-hold + calibration) -> ENGINES (`predictor.py` +
`sim_framework.JointDistribution` + `live_repricer`) -> PREDICTIONS (`markets.py` full
surface -> CLI / snapshot / front end) -> INTELLIGENCE (`atlas*` -> `brain_*` ->
`sport_read`; LLM writes prose only, the gate + engine compute every number) [01].

**Current state.** The validation spine, the cohesion seam (one win-prob anchors
ML/spread/total/in-game), adapter parity across 5 sports, and graceful degradation are
genuinely built and solid [01][06][11]. But: the aspirational sport-blind `kernel/` is
mostly empty stubs (the real shared machinery lives in `scripts/platformkit/`) [01];
the intelligence funnel is largely DEAD (atlas features are injected but the served
model was never trained on them, and honest ablation shows no point-accuracy lift) [09];
the prop verticals are data-starved (World Cup = 24 matches; MLB prop calibration =
0 scored predictions on a 17-day corpus) [04][05]; CLV -- the honest yardstick -- is
essentially uncaptured (0 settled bets carry real CLV; the self-improve ratchet is
48/48 INSUFFICIENT_DATA) [06]; and the polished React UI is built but not actually
served at :8098 [02].

Bottom line: **architecturally mid-maturity, methodologically senior-grade.** The
honesty discipline and validation rigor are the real product; the predictive ceiling is
calibration (match the close), reached on team-strength markets and structurally
unbeatable beyond that.

---

## 2. SYSTEM MAP (how the areas connect)

```
                         HALF A (origin NBA, legacy substrate)
  broadcast video
      |
  [10] CV TRACKING PIPELINE  -- YOLO->homography->Kalman/Hungarian->reID->OCR->events
      |  cv_features (17,254 rows; ~2.3% jersey reads, 10-slot ceiling -> ~25% coverage)
      v
  [07] NBA PROP / WIN-PROB MODELS (prop_pergame ~190 feats, q50/NNLS/isotonic)
  [08] NBA MONTE-CARLO SIM + 2K RATINGS (coherent joint; NYK/SAS-deep, league-shallow)
  [09] INTELLIGENCE / ATLAS LAYER (44 atlases, 86 signals) ---- DEAD FUNNEL:
      |        injected at predict time but model never trained on them; ~0 lift
      |        (only genuinely-wired use = correlation_recal for parlay coherence)
      |
      +--- src/loop/gate.FeatureBundle  <==[the ONE seam between halves]==+
                                                                          |
                         HALF B (current multi-sport product)             |
  [12] DATA: data/domains/<sport>/*.parquet (~93MB, keyless ingest, asof_* leak-free)
      |
      v
  domains/<sport>/ ratings.py + signal_catalog + asof_*  (per sport)
      |
      v
  domains/<sport>/predictor.py  -- predict() / to_jd() / predict_live()
      |   anchors ONE win-prob across ML/spread/total/in-game (the cohesion seam)
      |
      +--> [sim_framework.JointDistribution] coherent score matrix -> markets.py
      +--> [11] live_repricer.get_repricer(sport) -- in-game conditioning (the real win)
      +--> [04] soccer/WC PROP engine (per-90 x E[min] -> Poisson/NB -> p_over)
      +--> [05] MLB PROP engine (per-PA/BF x exposure -> count dist) [STRANDED]
      |
      v
  predict_matchup.build_result(sport,...)  -- the ONE buyer-facing seam (edge_claimed=False)
      |
      +--> [03] ODDS + PROP AGGREGATION (keyless ESPN/Kalshi/Polymarket/Underdog/PrizePicks)
      |          odds_shop (Shin devig, best-line, EV, arb) -> slate / bet_board / prop_edge
      |
      v
  [02] FRONTEND SERVING -- snapshot_writer (compute-once, atomic) -> data/frontend/snapshots/
      |   serve.py :8098 (reads snapshots; serves LEGACY static UI, not the React build)
      |   refresh_daemon (cadence)        React/shadcn app exists but is NOT mounted
      |
      v
  [06] EVAL / PROVING SPINE -- the judge for EVERY change:
      walk_forward (leak guard + purge + embargo) + scoring (Brier/BSS/ECE/CRPS/pinball)
      + cluster-robust Diebold-Mariano + Shin devig + frozen-baseline regression gate
      + self_improve ratchet (SHIP/HOLD/REJECT/INSUFFICIENT_DATA) + clv_ledger + prop_paper
      -> verdict: BEATS_CLOSE / MATCHES_CLOSE / BEHIND (all honest, only regression blocks)

  [12] OPS: pm_trading/auto_loop --forever (paper-trade -> grade -> self-improve),
       runs only while the 15GB Windows box is awake; no always-on host yet.
```

The eval spine [06] is the genuine hub: its `scoring` / `walkforward` / `dm_test` /
`shin` are reused across the odds engine, CLV, prop calibration, in-game proofs, and the
self-improve ratchet -- not a stranded island [06]. The single bridge between Half A and
Half B is `src.loop.gate.FeatureBundle`, imported by every `domains/<sport>/adapter.py`
so the original NBA discovery/gate engine runs sport-blind [01].

---

## 3. WHAT IS GENUINELY STRONG (cross-cutting)

1. **Validation discipline is the real product, and it is reused everywhere.** Leak-free
   expanding-window walk-forward with an assertion-level `assert_vintage` leak guard,
   purge (48h) + embargo (3d), cluster-robust Diebold-Mariano (unit-tested to be WIDER
   than naive i.i.d.), Shin devig, >=2-corpus accept, frozen-baseline regression block,
   fail-closed-on-empty. The gate is built to REFUTE, not confirm [06]. The same leak-free
   discipline is pervasive in the data layer (`asof_*` everywhere) [12], the prop engines
   [04][05], the NBA prop pipeline [07], and the discovery loop [09].

2. **Honesty is enforced in code, not just prose.** `edge_claimed=False` is a literal
   field on every result [01][02]; `brain_critic` scans narratives for edge-claims and
   reverts to a safe template [01]; `/api/intent` hard-stamps `executed:False` [02];
   `EDGE_CLAIMED=False` on every repricer [11]; tiered evidence ranking makes a weak-stat
   raw-EV blowup unable to outrank a proven stat [04][06]; INSUFFICIENT_DATA instead of a
   fabricated win [06]; the system caught and documented its own +18.38% artifacts [01].

3. **The cohesion seam is clean and consistent across all 5 sports.** One win-prob anchors
   ML/spread/total/in-game via a shared `JointDistribution` + shared `live_repricer`;
   pregame and in-game agree at tip-off by construction (the anchor pattern, W146/W156/
   W157) [01][05][11]. A model change propagates everywhere through ONE seam
   (`predict_matchup.build_result`) [02].

4. **The in-game conditioning win is real, principled, and the cleanest improvement in the
   project.** Conditioning on the realized score is genuinely new information; the
   score-anchor + Brownian-variance-collapse construction provably tightens onto the
   outcome (NBA Brier ~0.209 -> ~0.159; MLB ~0.241 -> ~0.126 on the cited corpora),
   leak-free, RMSE+bias-graded (never MAE), honestly labelled calibration-not-profit
   [01][11].

5. **Coherent joint distribution from first principles** (NBA possession sim): the
   shared-scoring-pie design makes teammate correlation EMERGE (~ -0.10, matching real)
   instead of being imposed; one ~3-4s GPU run prices the entire prop/combo/SGP surface
   coherently [08]. This is the one thing a marginal prop model structurally cannot do.

6. **Graceful degradation and operational robustness everywhere.** Fresh clone -> CLI
   prints "unavailable" and exits 0; snapshot writer writes a status envelope; every odds
   provider degrades to an `unavailable` sentinel and never fabricates a price; atomic
   `.tmp`+`os.replace` snapshot writes; "degrade, never die" daemons; full dependency
   fallbacks in the CV stack (SIFT/EasyOCR/HSV/PyAV/CSV) [01][02][03][10][12].

7. **Keyless, free, idempotent, leak-free data refresh** across 5 sports (~93MB, MLB
   StatsAPI / Sackmann GitHub / football-data / ESPN), with the frozen-corpus + current-
   extension pattern (MLB) so one walk-forward replays across both eras [12].

8. **Honest, modest, well-controlled NBA model metrics.** Per-game holdout R^2 0.31-0.51
   on volume stats with train/holdout gaps <0.075; 23 disabled feature blocks each
   annotated with the WF result that killed it -- the feature-ceiling evidence trail in
   line [07].

---

## 4. HONEST WEAKNESSES + RISKS (cross-cutting)

1. **The `kernel/` is mostly fiction -- the single biggest doc-vs-code gap.**
   `docs/PLATFORM.md` describes a populated sport-blind kernel; on disk those subpackages
   are 1-line stubs and the real machinery lives in `scripts/platformkit/`. A buyer
   reading PLATFORM.md then opening `kernel/` sees the discrepancy [01].

2. **The intelligence funnel is DEAD.** Atlas features are injected at predict time
   (`CV_PROP_EXTRA_FEATURES` default ON) but the served model was never trained on them,
   so `atlas_*` columns are silently dropped -- the train/inference parity gap the project
   itself calls "the most expensive bug class." Worse, the honest 3-fold ablation shows
   atlas features do NOT reduce pts/reb/ast MAE (they increase it); only fg3m improves and
   trivially. Discovery has shipped nothing (10/10 REJECT, flag OFF, SHIPs not auto-grafted).
   86 signals are all "folded" scouting taxonomy, not a live feature feed [09]. The public
   narrative of an "80-artifact intelligence layer feeding predictions" overstates reality.

3. **Thin / small-N corpora dominate the prop verticals.** World Cup = 24 matches, every
   player exactly 1 WC match; only Saves clears the "proven" bar (and that is a near-
   deterministic save-count artifact); isotonic recal correctly DEFERRED for overfit;
   opponent-adjustment measured NULL [04]. MLB prop engine = 0 scored predictions on a
   17-day gamelog corpus -- there is no MLB prop calibration number yet, positive or
   negative, and the engine is stranded (only its own backtest consumes it) [05]. "n=662
   per stat" is correlated player-stat predictions over ~24 matches, NOT 662 independent
   observations -- "proven" is suggestive, not bankable [04][06].

4. **CLV -- the declared honest yardstick -- is essentially uncaptured.** Of 14 settled
   team bets, 0 carry a real CLV; `prop_line_history.jsonl` has 1 line; the self-improve
   ratchet is 48/48 INSUFFICIENT_DATA and structurally cannot SHIP until ~60 settled games
   AND dm.n>=200 accrue per sport. The "+8% measured on paper" is entirely prospective.
   The "CLV-proven" top tier does not exist in code [06]. The proxy-CLV path is
   uninformative (last price == taken price -> CLV~0) [06].

5. **The eval gate has never run against real data offline.** `--golden` runs only a
   SYNTHETIC near-oracle fixture with a toy ridge predictor; `--corpus` raises offline.
   So the gate proves the HARNESS is non-regressing, not that the production model is
   calibrated; baselines are explicitly `_synthetic:true`. CRPS/pinball and the in-game
   blend are built and tested but NOT wired into the gate verdict (binary BSS only) [06].

6. **Stranded / parallel / superseded surfaces everywhere (maintenance debt + "what is
   real?" confusion).** The React UI is built but not mounted (serve.py returns the legacy
   vanilla-JS table) [02]; FanDuel prop provider is built but in no consumer and never run
   against real prop data [03]; `multitask_props.py` is a dead NotImplementedError stub
   [07]; three parallel sim stacks (basketball_sim/fast_sim vs older possession_simulator
   vs the loop AsOfContext the API calls) [08]; two divergent in-game stacks (2719-line
   legacy live_engine vs the platform repricer) feeding different consumers [11]; ~25
   `_backup_iterNN_*` model dirs (1.3GB), 6.5GB tracking + 1.6GB shadow, dozens of in-game
   artifact families mostly unwired [11][12]; `app.py`/`board*.py` legacy servers [02].

7. **Half A's CV moat is a measured noise wall.** Jersey OCR ~2.3% true read rate
   (resolution wall, not effort); 10-slot tracker ceiling -> ~75% of player-games missing;
   scoreboard period 100% NaN; shot recall ~9.6% median; defender-distance contaminated on
   30-50% of rows. Net downstream predictive value is thin; the defensible value is the
   geometry asset + the systems-engineering proof [10].

8. **Coverage is NYK/SAS-deep, league-shallow in the sim.** Recency rates, real assist
   network, and team tov/ft_force exist ONLY for NYK/SAS; every other matchup silently
   falls back to defaults -- the deepest signal is effectively a two-team artifact. Sim
   constants are calibrated on one in-sample season; rates are full-season (mild leak) and
   no leak-free WF of the sim's prop predictions exists [08].

9. **Schema / parity drift risk in the live NBA path.** Live model artifacts are 85-col
   legacy while the canonical schema is 129-col; `predict_pergame` survives only by slicing
   to `n_features_in_`; the `_BBREF_REORDER_FIX` documents 5/85 feature slots were fed
   WRONG values on the live slate (fix exists, default OFF). Prop interval sigma is too
   tight on every stat. `betting_portfolio.record_clv()` sign is backwards [07].

10. **No always-on host; refresh is manual/loop-driven.** The self-improving paper loop
    only compounds if it runs 24/7 across a season, but it dies when the laptop sleeps
    (ROADMAP Phase 21 VPS + Phase 34 MLOps both unchecked). `DATA_INVENTORY.md` census is
    stale/misleading (reports ~190 parquets mostly as 0-row). MLB pitcher data is era-
    limited (2010-2021), so recent MLB runs pitcher-blind. Live odds are single-venue
    ESPN -> no real arb [03][12]. The validated SP lever exists but is NOT wired into the
    live MLBPredictor [05].

11. **Cross-source odds matching is the load-bearing correctness risk.** Strict matcher
    biased to false-negatives (correct posture) but aliases (Man City) miss; Kalshi/
    Polymarket are prediction markets mixed into `best_line` as if bettable book lines;
    only moneyline is priced (totals/spreads show fair-odds only) [03].

---

## 5. CONSOLIDATED IMPROVEMENT ROADMAP (prioritized across the whole project)

### QUICK WINS (days; low risk, high clarity)

- **Q1. Capture closing lines (CLV).** [06][04][12] Run `prop_loop`/`pm_trading`/
  `prop_line_history` on a cadence up to kickoff so the closing-line time series accrues.
  This is the single highest-leverage, lowest-effort fix: today every CLV metric is None,
  and CLV is the ONLY honest path toward any edge discussion. Code exists; it is a
  scheduling/ops fix.
- **Q2. Reconcile `kernel/` with reality.** [01] Either move the genuinely sport-blind
  platformkit modules into the matching `kernel/` subpackages and re-export, or rewrite
  `docs/PLATFORM.md` to say the kernel currently lives in `scripts/platformkit/`. Closes
  the largest doc-vs-code honesty gap.
- **Q3. Resolve the dead funnel honestly.** [09] Either retrain the per-stat models WITH
  `atlas_feature_names()` columns (then re-run `eval_atlas_lift`), OR gate
  `CV_PROP_EXTRA_FEATURES` OFF by default and label atlas-injection scouting-only. Stop the
  silent no-op that implies intelligence feeds the model. Update `.planning/NOW.md` and
  public docs so the layer reads as "built, leak-safe, mostly unread."
- **Q4. Mount the React build + surface freshness.** [02] Add `app.mount` for `web/dist`
  so the premium UI is default at :8098; render a "snapshot N s ago / STALE" pill from the
  `freshness.as_of` already in the envelope. Biggest single UX jump; the good UI exists.
- **Q5. Backfill the MLB player gamelog corpus to 1-2 seasons** via
  `ingest_player_stats.ingest_range` (keyless), then re-run `props_eval_mlb` for the first
  honest per-stat calibration scoreboard. [05] Unblocks all MLB prop work.
- **Q6. NBA schema/interval fixes.** [07] Inflate prop-interval sigma per the documented
  per-stat multiplier (blk ~x1.86) for honest coverage; retrain on the 129-col schema +
  flip `_BBREF_REORDER_FIX` ON (with pkl integrity check); fix `record_clv()` sign; flag
  STL/BLK props as low-confidence; delete the `multitask_props.py` stub.
- **Q7. Honesty plumbing on data + odds.** [12][03][06] Regenerate/split
  `DATA_INVENTORY.md` against real data + add a per-domain manifest with last-refresh;
  stamp freshness + rowcount heartbeats; tag each odds venue as sportsbook vs
  prediction_market so a thin PM "best" price is not shown as bettable; report
  `n_with_real_close` separately so the UI cannot imply CLV evidence it lacks.

### MEDIUM (weeks; modeling + wiring, all gate-validated)

- **M1. Finish the snapshot keystone end-to-end + wire `/api/live` and `/api/props` into
  React.** [01][02] Every surface reads the snapshot; nothing recomputes in the request
  path; live games + the World Cup prop board get first-class screens; the CLV tracker tab
  replaces the placeholder; slate sources today's real schedule from `live_board` so slate
  and live agree.
- **M2. Run the eval gate against a real frozen corpus offline + wire CRPS/pinball into the
  verdict.** [06] Converts the gate from "harness non-regressing" to "the real model is
  non-regressing"; extends it to continuous markets (totals/margins) and served prop
  intervals with their own frozen baselines.
- **M3. Run the real-corpus NBA in-game blend OOS and end the PENDING flag.** [11] Wire
  `ingame_blend_eval` to the 1313-game linescore corpus (not the synthetic generator);
  publish ONE leak-free in-game calibration scoreboard across all 4 sports
  (Brier(conditional) vs Brier(pregame) + ECE per game-time).
- **M4. Wire the MLB SP lever into the live MLBPredictor.** [05] Promote the validated
  `sp_elo_offset` (logit + w*z_sp) so the delivered win-prob reflects who is pitching --
  the biggest single MLB game variable, currently absent from the live number.
- **M5. Per-section atlas lift + promote the 5 already-validated signals.** [09] Run
  `eval_atlas_by_section.py` to find the 1-3 sections that clear all-folds and wire ONLY
  those; explicitly graft + retrain + re-gate the 5 VALIDATED signals
  (pbp_origin_transition, rest_x_age, shot_clock_leverage, opp_position_defense_reb,
  oreb_matchup).
- **M6. Prop-vertical correctness fixes.** [04][05] Fit per-stat NegBinom r from realized
  outcomes (the widening lever exists but is never set); compound/joint model for MLB Total
  Bases / H+R+RBI; validate minute-projection error end-to-end (backtest with PROJECTED
  not realized minutes) so live-board calibration is measured, not optimistic; expand
  team-name/alias maps and add resolver-coverage reporting.
- **M7. Consolidate the parallel stacks.** [02][08][11] One authoritative sim
  (basketball_sim/fast_sim; route the API through it); reconcile the two in-game stacks
  behind one `predict_live` win-prob interface; de-duplicate the frontend entry points;
  archive stranded artifact families under a labeled experiments dir.

### BIG BETS (the things that change the ceiling)

- **B1. Stand up a genuine always-on host (the single biggest structural gap).** [12] A
  small VPS running `auto_loop --forever` + `refresh_daemon` under supervisor with the
  ~93MB per-domain parquets synced. The self-improving paper loop only compounds across a
  full season; only at large N can the calibration story (and any CLV claim) escape small-
  sample variance and the ratchet leave INSUFFICIENT_DATA. This is the prerequisite for
  every honest forward-validated claim.
- **B2. Same-day freshness ingest (the only real pregame accuracy lever).** [07][05][08]
  Ingest projected minutes / starting lineups / late scratches / load-management / weather
  / confirmed pitcher at slate time and wire them in BOTH train and inference builders
  (parity). Everything historical is at the data ceiling; this is the one input that could
  close the gap to the close on totals/props. Measure as leak-free WF lift vs the close.
- **B3. Add a deep-data prop sport end-to-end (NBA props through the keyless feed).** [03]
  An NBA prop provider (PrizePicks/Underdog NBA already on the same endpoints) joined to
  the existing NBA prop surface, so prop calibration can be cross-validated on many seasons
  rather than 24 WC matches -- the credible ceiling for the prop board lives where data is
  deep.
- **B4. Wire next-tier data + the funnel (turn INTELLIGENCE from decoration into a gated
  input).** [01][09] Stop discarding next-tier data at ingest; make atlas/intelligence an
  ACTUAL gated predict-time input (must beat raw on >=2 corpora or stay descriptive);
  backfill per-date atlas snapshots so historical backtests can even see atlas state.
- **B5. Fix the CV keystone: scoreboard OCR per frame.** [10] Make `scoreboard_ocr.py`
  read period + a decrementing clock + score per frame. This one change unblocks PBP-
  anchoring (bypasses the jersey-OCR and shot-detection walls at once) AND per-quarter slot
  resolution (kills the 10-slot collapse) -- it dominates every other CV item. Then land
  the Bug-1 defender-distance fix and re-derive features.
- **B6. Model what the chain cannot.** [08][11] Native same-player joint correlation
  (replace the bolt-on CV_MIN_VAR corrector); explicit minutes/foul-out rotation model;
  extend recency + PBP knowledge + team_defense builders to all 30 teams; build a real live
  possession/event NBA feed (substitutions/pace/foul state) -- the in-game math ceiling is
  data-bound. In-game prop DISTRIBUTIONS conditioned on realized minutes/usage are the most
  credible frontier.

---

## 6. HOW GOOD CAN IT GET (honest overall ceiling)

**The honest north star is CALIBRATION vs the Shin-devigged closing line -- not a dollar
edge.** Every area independently reaches the same verdict: markets are efficient; the best
honest pregame outcome on sharp team-strength markets is MATCHES_CLOSE (BSS ~ 0, CLV ~ 0),
and that is a SUCCESS by design, not a target to beat [01][06][12].

**Where markets are efficient (no durable edge, and none claimed):** mainline team
moneyline / spreads / totals, run lines, liquid star props -- the book sees the same
public data, the confirmed lineup/pitcher, and the weather [01][05][07]. A live book also
sees the realized score in real time plus substitutions/pace/injuries we cannot, so even
the in-game calibration win is forecaster QUALITY, not tradeable alpha [11].

**Where the genuinely beatable pockets (if any) plausibly live -- all to be PROVEN by CLV,
never asserted:** soft/recreational books and lazily-priced DFS props/alt-lines; live lag
in thin/slow in-play markets; stale lines; prediction-market vs sportsbook gaps; correlated
SGP mispricing that a coherent joint sim can exploit [01][03][08]. The platform is
correctly built to surface and paper-trade these; the verdict is empirical and not yet in
(CLV uncaptured).

**The durable, sellable ceiling is ENGINEERING + HONEST CALIBRATION, not alpha:** a clean
kernel/adapter platform where a new sport is mostly an adapter, judged by a fail-closed,
leak-free, cluster-robust, multi-corpus, distribution-aware eval gate, with honesty
enforced in code, served as a fast sub-second multi-sport decision-support board with CLV
as the truth metric. That ceiling is largely reached for 5 sports; the remaining gap is
structural maturity (real kernel, live funnel, snapshot service, served UI, always-on
host, captured CLV), not predictive accuracy [01][02][06][12].

### Per-area one-liners (honest ceiling)

- **[01] Architecture/funnel** -- Strong reused validation+adapter spine and a clean
  cohesion seam; ceiling = mid-maturity until the empty kernel is populated and the dead
  funnel is wired. Pregame already AT the calibration ceiling (matches close).
- **[02] Frontend/serving** -- Can become an excellent, fast, sub-second, fully-calibrated
  multi-sport decision-support board with live games + prop ladders + CLV + freshness; can
  NEVER become a profit machine -- the number ceiling is set entirely upstream.
- **[03] Odds/prop scrapers** -- A solid keyless multi-sport odds-NORMALIZATION + execution-
  only line-shopping layer; structurally capped by keyless breadth (ESPN republishes ~one
  book) and prop-corpus depth; never a profit engine.
- **[04] Soccer/WC prop engine** -- A well-calibrated, honestly-tiered board for 2-4 high-
  volume near-deterministic markets (Saves first) once matchdays accrue; bound by DATA
  DEPTH then minute-projection error then market efficiency.
- **[05] MLB prop engine** -- Correct machinery on a near-empty corpus; today ~0% of its
  ceiling (0 scored predictions). The team model is the genuine asset (leak-free, coherent,
  parity-with-close); MLB is the MOST favourable sport for honest calibration once a full
  season is loaded.
- **[06] Eval/proving spine** -- As a proving/honesty machine, near-bulletproof in DESIGN
  but currently null in EVIDENCE (no ships, no real CLV). The gap is closing-line capture +
  real-corpus gating + months of forward accrual, not missing algorithms.
- **[07] NBA prediction models** -- A well-calibrated prop/win-prob predictor that matches
  the devigged close with honest intervals (interval coverage is the current weakest link);
  at the historical-data ceiling (17 feature-add REVERTs); the one lever left is same-day
  freshness. AST is the lone near-durable model divergence and is fragile.
- **[08] NBA Monte-Carlo sim/ratings** -- A genuinely well-calibrated, fully-COHERENT box-
  score joint simulator pricing the entire prop/SGP surface from one ~3-4s run; the JOINT
  coherence is the durable asset. Capped by data depth (NYK/SAS-deep) and unvalidated in-
  sample constants until a leak-free multi-corpus WF gate clears them.
- **[09] Intelligence/atlas layer** -- Low ceiling as a point-prediction feature source
  (measured ~0 lift); real value is joint/correlation coherence (already live), in-game
  conditioning, and a deep provenance-stamped SCOUTING/demo asset.
- **[10] CV tracking pipeline** -- Strong engineering/cost story ($0.10-0.13/game broadcast
  MOT); medium as a geometry feature source IF the scoreboard-OCR keystone lands; low as an
  identity moat (2.3% jersey wall); zero as a prediction edge, and none claimed.
- **[11] Live/in-game layer** -- A well-calibrated in-game forecaster whose Brier strictly
  improves over the pregame prior -- achievable and partly demonstrated; the cleanest win in
  the project. Dollar-edge ceiling is structurally ~zero. In-game prop distributions are the
  highest-upside frontier, bound by live-feed depth + leak-free corpus size (N=3 PBP replay).
- **[12] Data/ops** -- Can reach a clean, fresh, manifested, 24/7, drift-alerted,
  honestly-calibrated multi-sport corpus; predictive ceiling permanently bounded by market
  efficiency and keyless-feed depth (no same-day lineups/closing lines keylessly).

**One-line bottom line:** the methodology is senior-grade and the engineering spine is
genuinely strong; the project is honestly AT its calibration ceiling on efficient pregame
markets, and the work that remains is structural maturity + forward CLV accrual -- not a
hunt for an edge that the system has correctly proven is mostly not there.


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../../INDEX.md) - [Home](../../../README.md) - [Glossary](../../GLOSSARY.md)
