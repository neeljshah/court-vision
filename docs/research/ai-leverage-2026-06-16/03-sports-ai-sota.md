# Sports AI -- State of the Art for a Calibrated Multi-Sport Predictor

_Synthesis, 2026-06-16. Inputs: the seven sports briefs in `briefs/` (sports-data-sources, sports-modeling-core, calibration-scoring, market-efficiency-clv, ingame-live-modeling, sports-cv-tracking, llm-in-sports) plus the existing project research (`edge-taxonomy.md`, `data-sources.md`, `market-microstructure.md`, `validation-methodology.md`, `competitive-landscape.md`, `precedent-analysis.md`)._

> **The discipline first.** This project's north star is the BEST PREDICTIONS -- lowest OOS Brier/log-loss and tightest calibration against the devigged market-implied probability -- using our own data (freshness, in-game state, CV-derived spatial features, intelligence). It is NOT a fabricated dollar edge. Pregame markets are efficient on PRICE; "CLV ~ 0" is the correct, honest result, not a failure. Every claim below is filtered through that: where the existing project docs frame something as a "+EV edge," this document re-reads it as a CALIBRATION or RESOLUTION improvement, which is a real and achievable accuracy gain even when the price edge is zero. Honest rejects count as successes.

---

## 0. The one-paragraph state of the art

A modern solo calibrated predictor is a layered system: a **data layer** (free/cheap APIs + a proprietary CV moat), a **per-sport mechanistic model** (Dixon-Coles for soccer, Glicko-2/surface-Elo for tennis, hierarchical Bradley-Terry for MLB, possession Monte Carlo for NBA), wrapped in a **calibration + proper-scoring harness** (Platt/isotonic, Brier/log-loss with Murphy decomposition, Diebold-Mariano significance, reliability diagrams vs the devigged close), validated **only** by walk-forward + purge/embargo over >=2 corpora and benchmarked against Shin-devigged closing lines via CLV-as-diagnostic. The pregame layer matches but does not beat an efficient market. The **decisive, combinable advantage is in-game conditioning**: a pregame prior progressively overridden by realized state (score, time, foul trouble) on a 2D weight surface -- information the pregame line literally cannot contain. A **CV layer** turns broadcast video into spatial features (homography is the high-value primitive) that books do not price into props -- a real but fragile, honestly-ceilinged moat. An **LLM layer** sits at the edges: structured extraction of fresh news, orchestration, and narration -- never as a numeric probability source.

---

## 1. Data layer -- free/cheap backbone + the one real moat

The hierarchy: **odds (the benchmark), stats/PBP (the features), tracking (the moat).** All stats/odds below are available to any analyst -- they cannot be a differentiator. The only uncommoditized input is broadcast-CV-derived spatial data.

### Odds (the calibration benchmark, not a feed to model)
- **The Odds API ($30 Pro / $99 Business)** is the right backbone. Business tier unlocks player props, Pinnacle, and the historical archive back to June 2020 (10x credit multiplier -- cache every historical pull locally). 200K credits/mo covers ~5K daily snapshots.
- **Pinnacle is the sharp anchor for the devigged-close benchmark.** Direct Pinnacle API closed to the public July 2025; reach it via The Odds API Business or **OddsPapi free tier (250 req/mo, includes Pinnacle + no-vig lines, no historical penalty)** -- sufficient for a few games/day.
- **Betfair Exchange** gives true tick-by-tick clearing prices (best in-play calibration anchor) but US new-account access is jurisdiction-gated in 2026 -- route historical exchange/CLV reconstruction through **BettingIsCool** (2.7B records back to 2021) instead.
- Use these to compute the **devigged Pinnacle closing probability** = the best available estimate of true probability = the target our Brier must approach/beat. Never use a soft-book (DK/FD) close as the benchmark; it lags sharp money.

### Stats / PBP (free, abundant, commoditized features)
- **MLB StatsAPI (`statsapi.mlb.com`)** -- fully free, no key, pitch-by-pitch live feed, built-in win probability and leverage index. The richest free real-time feed of any sport here; the easiest sport to add real in-game features to.
- **nba_api** -- 70+ free endpoints, but `PlayByPlayV2` is dead (returns empty JSON); use `PlayByPlayV3`. stats.nba.com blocks cloud IPs -> keep the project's `cdn.nba.com/liveData` workaround for live PBP, residential proxy or 1-2s delays for the rest.
- **StatsBomb open data** (soccer) -- ~50 competitions of geolocated event JSON + 360 freeze frames for selected matches; shot-level xG is a principled input to the Poisson lambda. Research/attribution license (non-commercial).
- **Jeff Sackmann tennis repos** (CC BY-NC-SA) -- ATP/WTA results + rankings back to 1968, point-by-point for 5000+ charted matches, continuously updated. The foundational tennis corpus.
- **Retrosheet** (event files 1898-2025, Fall 2025 release) + **Lahman** (season-level, public domain) -- a second independent MLB corpus for the two-corpus rule. Parse `.evN` with Chadwick/pyretrosheet.
- **Baseball Savant / Statcast (via `pybaseball`)** -- free pitch + batted-ball tracking 2015-present; the most democratized tracking data in pro sports; starter-matchup Statcast is the most defensible MLB freshness feature.
- **ESPN hidden JSON endpoints** -- supplemental only; break without notice.

### Tracking (the moat -- and its honest limits)
- NBA raw optical tracking (Second Spectrum, 25fps XY) is **not** public; only aggregated `LeagueDashPtStats` and the one-off **SportVU 2015-16** release (631 games) exist. So the NBA spatial moat must come from **our own broadcast CV**, not a feed.
- This is the only place the project sees what others can't. The existing `edge-taxonomy.md` enumerates ~70 CV-derived signals (defender distance, convex-hull spacing, closeout speed, paint density, PnR detection, fatigue/gait, set recognition). Reframed honestly: these are **calibration/resolution inputs to the in-game heads**, not a pregame price edge.

**Freshness ladder** (the binding constraint on pregame calibration): Betfair in-play tick -> Odds API live -> MLB StatsAPI pitch -> nba_api quarter -> nba_api next-day box. The pregame model captures none of the top of this ladder; the in-game layer captures all of it. That is why in-game is the priority funnel investment.

---

## 2. Modeling per sport -- mechanistic core + GBM consumer + calibrator

The universal recipe: **mechanistic model -> output probability as a feature -> CatBoost/LightGBM on engineered features + mechanistic output -> isotonic/Platt calibration on walk-forward OOS. Never blend in-sample.** Per sport:

| Sport | Mechanistic core | Key upgrade from current | Scoring metric | Notes |
|---|---|---|---|---|
| **Soccer** | Dixon-Coles bivariate Poisson | Add time-decay (xi ~ 0.001, 4-season window) + rho ~ -0.13 low-score correction | RPS (3-way) | DC beats naive Poisson by only RPS 0.1915 -> 0.1891 -- tiny absolute, real calibration win on draws. Feed StatsBomb xG into lambda. |
| **Tennis** | Surface-specific Elo / Glicko-2 | Glicko-2 RD handles off-season gaps + gives per-player posterior variance (interval width) | Brier + reliability | Surface-split rating pools are the strongest feature lever. GNN paper found intransitive dominance (A>B>C>A) that ATP ranking misses -- relational features help where box-score plateaus. |
| **MLB** | Hierarchical Bradley-Terry (PyMC) | Pitcher-level attack + bullpen defense params; handles small-N early season | Brier + log-loss | log5 Bayesian variant (arXiv 1712.05879) is the validated next step. Retrosheet = corpus B. |
| **NBA** | Possession Monte Carlo (already built) | L-RAPM informed priors on player impact; Bayesian-hierarchical wrap on sim output | Brier + reliability; full score dist prices any prop | Sim's marginals must match per-player season averages (anchor constraint); dispersion must match empirical game-to-game variance. |

Cross-cutting:
- **Elo/Glicko-2 are baselines or input features, not standalone predictors.** Elo is a gradient-descent approximation to the Bradley-Terry MLE; it often matches heavier models on raw win-rate but is poorly calibrated without a validated logistic mapping.
- **Bayesian hierarchical (PyMC/Stan) is the principled small-N path** -- posterior predictive distributions are natively calibrated probability intervals; wide when a team has 3 games, sharp later. Use ADVI for iteration speed, NUTS for production. R-hat < 1.01, ESS > 400.
- **GBM accuracy numbers in papers are inflated by in-game box-score leakage** (the 83.27%/AUC 0.92 NBA stack used 2PA/TRB/FG -- not pregame). Pregame-only NBA win prediction is ~65-68%, consistent with this project's market-efficiency findings. Always state the feature cutoff time.
- **Honest discipline overrides complexity.** Complexity is justified only by a sustained Brier/log-loss reduction (> ~0.005 Brier) over >= 2 independent corpora with DM p < 0.05 -- never in-sample.

---

## 3. Calibration + proper scoring -- THE BAR

This is where "best predictions" is operationalized. The honest evaluation bar to claim we beat the best available predictor:

> **(a)** OOS walk-forward Brier (or log-loss) lower than the devigged-close Brier, with **Diebold-Mariano p < 0.05**; **(b)** reliability diagram closer to the diagonal across all bins; **(c)** holds on **>= 2 independent corpora/seasons**. A single-season gain is an artifact.

Toolkit:
- **Brier decomposes (Murphy 1973) into Reliability - Resolution + Uncertainty.** To beat the market you need lower **Reliability** (better calibrated) AND competitive or higher **Resolution** (sharpness/discrimination) -- not just a lower raw Brier. Uncertainty is fixed by the dataset.
- **Calibration methods:** Platt scaling (2-param, use for calibration sets < ~1000), isotonic (non-parametric, use for >= ~1000), beta calibration (asymmetric -- for underdog-heavy moneylines, tennis, MLB). **Temperature scaling does NOT apply** -- the cores are trees/MC, not neural nets with logits. Calibration set must be fully disjoint from training (walk-forward: train 1..N, calibrate N+1, test N+2).
- **Reliability diagrams are mandatory; ECE is a diagnostic only** (not a proper rule -- never optimize it; it hides S-shaped/regime miscalibration and depends on binning). Overlay our curve vs the devigged-close curve on the same axes.
- **Log-loss punishes confident wrongness** far harder than Brier -- report both, plus median/trimmed-mean per-game log-loss (one catastrophic 90%-loss can dominate the mean).
- **Conformal prediction** gives OOS calibration guarantees under exchangeability only -- validated better-calibrated at low-probability tails on NCAA basketball. The natural fit is the **in-game layer** (highly non-stationary mid-game state) and the **tails of totals/props**. Report intervals: "at halftime, A win prob 0.61 [0.52, 0.70]."
- **Devig correctly before any comparison.** Raw odds include vig and look "over-calibrated." Use **Shin** as the default for two-outcome props (closed form; z ~ 0.02-0.04 NBA, solve per market, never hard-code) and **power** for multi-outcome; multiplicative is fine only at near-even (-110/-110). The existing `validation-methodology.md` already specifies the Shin solver. Caveat: use a vetted Shin implementation (mberk/shin or kernel.devig2) -- the closed-form quoted in the older validation-methodology.md does not normalize correctly; do not transcribe it.
- **Calibration != edge.** A model perfectly matching the devigged close has zero improvement over the market. The goal is better-calibrated AND sharper -- which requires OWN data (freshness, in-game, CV, intelligence). That is achievable; converting it to dollar ROI is a separate, harder bar requiring real price capture + forward CLV.

---

## 4. Market / CLV evaluation -- efficient pregame is the honest finding

The academic and project consensus (2023-2025): **sports markets satisfy weak-form efficiency; detectable inefficiency is short-lived and sport/league-specific.** This project's own season backtest (model Brier 0.208 vs close 0.198) and "CLV ~ 0" reads are the *correct verdict*, not a sample-size failure.

- **CLV is the gold-standard diagnostic because it has ~10x lower variance than ROI** (SD ~0.10 vs ~1.00 per unit). A 5% signal needs ~50 CLV observations vs thousands of bet outcomes for significance (Buchdahl: 19,930-bet study, 3.4% realized vs 4.0% CLV-implied -- within noise). Test: `ttest_1samp(clvs, 0)`, gate mean_clv > 0 AND p < 0.05 AND N >= 500.
- **Even when CLV ~ 0, the devigged close is the best proxy for true probability** -- so the Brier-vs-close gap IS the honest measure of where our probability estimates fall short. Decompose that gap by market type and time-in-season to find where calibration is weakest.
- **Validation design is non-negotiable:** expanding-window walk-forward + **purge** (drop same-team games within 48h / 2 games) + **embargo** (3-day gap to kill rolling-window spillover). K-fold on time-ordered data is a correctness bug. Use **CPCV** (combinatorial purged CV) for signal-catalog evaluation. **>= 2 corpora** before any signal leaves research; cross-sport robustness > same-sport two-season; report per-corpus, never pooled (distribution shift survives multi-corpus).
- **Favorite-longshot bias** matters only in lopsided markets; Shin/power diverge from multiplicative on heavy favorites/longshots. In-game props carry higher vig + more FLB -- run a per-decile FLB audit (mean devigged-implied vs actual rate) and devig with Shin so calibration isn't flattered by multiplicative bias.
- **Early-season window** (games 1-20) is structurally under-modeled by books -- run it as a separate calibration evaluation so a freshness/timing effect is not mistaken for a model structural advantage.
- The existing `edge-taxonomy.md` (164 enumerated edges) and `precedent-analysis.md` (Voulgaris/Benter/Thorp) describe a *betting* program. For THIS project they are read as a **prioritized feature/calibration backlog and an existence proof that information advantage is real** -- not a license to claim ROI. The honest deliverable is calibration + in-game, with CLV used diagnostically.

---

## 5. In-game -- the decisive combinable signal

This is the single highest-leverage technical area, because it is the only dimension where the predictor can measurably depart from an efficient pregame prior on NEW information the line could not contain (realized score, elapsed time, foul trouble, ejections).

**The core pattern (directly wirable into the existing MC engine):**
1. P0 = existing pregame MC simulation output (already calibrated vs the devigged close).
2. P_live = lightweight XGBoost/logistic on `(score_differential, seconds_remaining)` -- a trivial 2-column dataset.
3. `final = w(t, margin) * P_live + (1 - w) * P0`, where **w is a 2D weight surface** computed from a HELD-OUT season (computing w on the evaluation games is the documented overfit trap).
4. The surface is asymmetric: a pregame-underdog leading early gets more weight on P_live than a pregame-favorite with the same lead.

Evidence: state-dependent blended models hit Brier ~0.16 vs ~0.165 XGBoost-only and far better than pregame-only; Q4 accuracy ~88% (Brier ~0.085); in-game conditioning reduces Brier 0.04-0.09 over a game relative to pregame-only. This is a structural, calibration-level gain -- not a market-beating claim.

Build notes:
- **Keep features minimal.** `(score_diff, seconds_remaining, pregame_prob)` explains >90% of variance; add **foul-trouble differential** and **bonus state** next. The project's own PBP-replay validation confirmed the per-player projector with a **foul-out adjustment was the only in-game modification that survived** -- foul state is the highest-impact unpriced event. Do NOT add PBP sequence embeddings until the simple model saturates.
- **Enforce temporal smoothness** (DTAI neighbor-coupling L2, or EMA over last 3-5 possessions) to avoid jagged per-possession probability jumps that look like miscalibration.
- **Per-quarter reliability audit.** The project's pbp_replay harness showed Q1-Q3 Brier 0.34-0.40 (worse than a coin flip) -- exactly the early-game regime where w should be ~0 (trust P0). The 2D blend is the fix; re-run per-quarter diagrams after wiring it.
- **Garbage-time clamp:** |margin| > 20 with < 2 min -> near-deterministic output; handle intentional fouling explicitly.
- **Latency is a prediction-quality axis, not just commercial.** The posterior shifts fastest right after high-impact events; every second of lag serves a stale posterior. Target < 2s end-to-end PBP-event -> React-board update via SSE/WebSocket push (not polling); the bottleneck is the cdn.nba.com feed (~1-3s), not the model re-run.
- **MLB is the easiest in-game win** -- the free StatsAPI pitch-by-pitch feed plus its own published win probability give an immediate calibration ladder (sim -> MLB official WP -> exchange mid).

Build all of this in `scripts/platformkit` or `domains/<sport>` to respect the local-only / no-kernel-edit invariants.

---

## 6. CV moat -- high value, honest ceilings

Broadcast video -> court coordinates is the project's most defensible asset (~$0.10/game vs six/seven-figure vendor feeds). But the honest ceilings must stay central.

- **Detection is NOT the bottleneck.** Fine-tuned YOLOv8/v11/RF-DETR exceed 90% mAP for player boxes. The hard problems are **re-ID across occlusion** and **jersey-number assignment**. The project's own 14% detection ceiling (bug39) confirms association + OCR, not detection, is the wall.
- **Backbone:** Ultralytics **YOLOv8 + BoT-SORT** (BoT-SORT's global motion compensation is required for broadcast camera pan; ByteTrack alone ID-switches on fast pans). **Team ID is solved** (SigLIP embeddings -> K-means, 2 clusters/game; or OSNet on ~2 uniforms). **Player ID is fragile** -- jersey OCR tops out ~93%/crop, degrades badly < 15px / motion blur (~140 errors over a 48-min game). Use the **PBP-anchor pattern** (match CV events to PBP events by time/type) instead of chasing OSNet player re-ID.
- **Homography is the highest-value primitive** -- pixel (u,v) -> court (x,y) unlocks spacing (convex hull), zone occupancy, transition speed, closeout distance, paint density. SoccerNet 2025 SOTA: SegFormer + ResNet18 on 74 court landmarks -> GS-HOTA 63.81. NBA needs curve-fitting (arcs), and **jump-aware correction** (feet leave the ground plane) or frame exclusion.
- **Pose (RTMPose ~10-30ms/frame, ViTPose ~50-100ms) and SAM2 (1-2 FPS -- offline only)** add fatigue, contested-shot posture, gait asymmetry -- run overnight on stored clips, store as `(game_id, frame_idx, clock_str)` parquet joined to PBP.
- **Honest expected value:** spacing correlates ~0.15-0.25 with 3PA rate; adding spatial features to the in-game heads likely shifts in-game Brier by ~0.005-0.020 -- **small but real and leak-free.** It is a CALIBRATION improvement for in-game, not a pregame edge. The moat is the *integration* (CV + PBP + intelligence for in-game conditioning), not any single feature, and it is fragile to Hawk-Eye/SportVU democratization.
- **No public NBA broadcast ground truth exists** -- use SportVU 2015-16 (edge 17) to calibrate CV precision and PBP-anchored weak supervision; OOS-validate spatial-feature models train-2023/24 -> test-2024/25, honest reject if no Brier improvement.

---

## 7. LLM-as-intel-layer -- synthesizer and orchestrator, never predictor

> **LLMs are bad predictors, good synthesizers.** Raw LLM numeric probabilities have ECE 0.12-0.39 across all major models; only one frontier model achieves a positive Brier Skill Score vs base rate on general forecasting, and sports markets are harder. **Never route a raw LLM float into the prediction chain.**

The four safe roles:
1. **Structured extraction (the killer app).** Convert injury reports, lineup news, beat-writer text, pressers into typed JSON (`{player_id, team_id, status, severity, game_date, source, extracted_at, confidence}`) via grammar-constrained / tool-use structured output. Run nightly + re-run ~2h pre-game. Each `status=OUT` row drives the **vacated-load redistribution** -- this is the freshness lever the pregame model is missing (edges 13/14/28/58 in the taxonomy). Validate every extraction against the schema downstream (~12% failure on hard nested cases even with constrained decoding).
2. **Agentic RAG for pre-game context assembly.** An agent pulls fresh structured injury/lineup deltas, retrieves relevant vault scouting notes (semantic search), and fires a last-4-hours web search; the packet feeds `scheme_prior.py` as **bounded multipliers** (e.g., 0.85-1.15x on a turnover rate) with leak-flag metadata -- the sim recomputes every number. Multi-hop is fine pre-game (10-30s); in-game requires single-hop extraction with a warm cache.
3. **Wordalisation / scouting narration (product, not prediction).** Percentile-bucket the MC sim's feature contributions, few-shot the LLM to a one-paragraph summary on the live board. Safe because the LLM only narrates numbers it did not compute; it improves engagement, not accuracy.
4. **LLM-as-orchestrator.** Claude tool-use calls `run_pregame_sim(...)`, `get_injury_delta(...)`, `score_in_game_state(...)`; the LLM routes/sequences/diffs and emits a structured update record with a confidence tier. The quant tools compute every probability.

Guardrails: overconfidence at high confidence (80/90%+) is the worst failure mode -- especially dangerous for in-game where it would masquerade as a strong signal. Acquiescence/positivity bias understates injury severity and assumes starters play -- counter with empirical "P(plays | status word)" tables, not the model's prior. Any LLM-touching layer change must be followed by an OOS Brier/ECE check before shipping. For genuinely sparse matchups (early-season novelty, mid-season scheme change) a clearly-labeled 3-5 model LLM-ensemble prior is "better than nothing" but must be labeled a weak prior and updated as data accrues.

---

## 8. Highest-leverage technical bets (prioritized)

Ordered by expected calibration gain per unit of effort, all respecting local-only / no-kernel-edit / no-edge-claim invariants.

1. **Wire the 2D in-game blend surface into the MC engine (NBA first, then MLB).** The single biggest measurable Brier gain (0.04-0.09 over a game), trivial data, and it captures information the efficient pregame line cannot. Compute w on a held-out season; add foul-out + bonus state; per-quarter reliability audit on the pbp_replay harness. **(Section 5)**
2. **Stand up the calibration + DM-test harness as the project's scoreboard.** Per sport/season: Brier + log-loss + Murphy decomposition + reliability diagram overlaid vs Shin-devigged Pinnacle close, with Diebold-Mariano p-values and the >=2-corpus gate. This is how "best predictions" is proven or honestly rejected. **(Section 3-4)**
3. **Build the structured-extraction + vacated-load freshness pipeline.** Nightly + 2h-pre-game LLM extraction -> SQLite -> usage redistribution. This is the missing pregame freshness lever and feeds bounded `scheme_prior.py` multipliers. **(Section 7, edges 13/14/28/58)**
4. **Upgrade per-sport mechanistic cores where calibration is weakest:** Dixon-Coles time-decay (soccer draws), Glicko-2 surface pools (tennis off-season + interval width), hierarchical Bradley-Terry (MLB early-season small-N). Validate each by Brier-vs-close on two corpora; honest reject if no >0.005 sustained gain. **(Section 2)**
5. **Homography -> in-game spatial features.** ResNet18 keypoint detector on NBA court landmarks (SoccerNet code as template) + BoT-SORT; compute spacing/paint-density/transition at PBP-detected possession boundaries; feed the in-game heads. Expected ~0.005-0.020 in-game Brier shift -- small, real, leak-free, and the true own-data moat. **(Section 6)**
6. **Add second corpora everywhere** (Retrosheet for MLB, Sackmann current season for tennis, StatsBomb xG for soccer) to make the two-corpus rule routinely satisfiable and turn honest rejects into recorded research findings. **(Section 1-2)**
7. **Conformal intervals on the in-game layer and prop tails.** Honest, distribution-free OOS coverage for the most non-stationary regime; report intervals, not point estimates. **(Section 3)**
8. **Latency: SSE/WebSocket push to the React board, < 2s target.** Freshness is a calibration axis; stale posteriors after big swings are a real error source. **(Section 5)**

Explicitly NOT a priority: chasing pregame alpha over the close (it is efficient -- CLV ~ 0 is the right answer), OSNet player-level re-ID without working jersey OCR, PBP sequence embeddings before the simple in-game model saturates, and any LLM raw-probability output. The win is calibration + in-game + own-data, claimed confidently and only where leak-free OOS proves it.

---

## Sources / References

### Project research (existing docs)
- `docs/research/edge-taxonomy.md` -- 164 enumerated edges (re-read here as a calibration/feature backlog)
- `docs/research/data-sources.md`, `docs/research/market-microstructure.md`
- `docs/research/validation-methodology.md` -- CLV protocol + Shin devig solver
- `docs/research/competitive-landscape.md`, `docs/research/precedent-analysis.md` (Voulgaris / Benter / Thorp)

### Data layer
- [The Odds API V4 Docs](https://the-odds-api.com/liveapi/guides/v4/) - [Odds API Pricing 2026 (OddsPapi)](https://oddspapi.io/blog/odds-api-pricing-2026-comparison/)
- [nba_api GitHub](https://github.com/swar/nba_api) - [PlayByPlay notebook](https://github.com/swar/nba_api/blob/master/docs/examples/PlayByPlay.ipynb) - [nba-on-court](https://github.com/shufinskiy/nba-on-court)
- [MLB-StatsAPI (toddrob99)](https://github.com/toddrob99/MLB-StatsAPI) - [Endpoints wiki](https://github.com/toddrob99/MLB-StatsAPI/wiki/Endpoints)
- [StatsBomb Open Data](https://github.com/statsbomb/open-data)
- [Sackmann tennis_atp](https://github.com/JeffSackmann/tennis_atp) - [tennis_wta](https://github.com/JeffSackmann/tennis_wta) - [MatchChartingProject](https://github.com/JeffSackmann/tennis_MatchChartingProject) - [pointbypoint](https://github.com/JeffSackmann/tennis_pointbypoint)
- [Retrosheet Fall 2025](https://www.retrosheet.org/fall2025release.html) - [SABR announcement](https://sabr.org/latest/retrosheet-announces-fall-2025-updates/)
- [Pinnacle API 2026](https://sportsapis.dev/pinnacle-api) - [SharpAPI](https://sharpapi.io/sportsbooks/pinnacle-odds-api) - [BettingIsCool](https://api.bettingiscool.com/)
- [Free football data (McKay Johns)](https://mckayjohns.substack.com/p/where-to-get-free-football-data)

### Modeling
- [Which model to predict football? (penaltyblog)](https://pena.lt/y/2025/03/10/which-model-should-you-use-to-predict-football-matches/) - [Dixon-Coles + time-weighting (dashee87)](https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/)
- [Stacked Ensemble NBA prediction (PMC12357926)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12357926/)
- [Hierarchical rugby model (PyMC)](https://www.pymc.io/projects/examples/en/latest/case_studies/rugby_analytics.html) - [Hierarchical Bayesian BT for MLB (arXiv 1712.05879)](https://arxiv.org/pdf/1712.05879)
- [L-RAPM (arXiv 2601.15000)](https://arxiv.org/pdf/2601.15000) - [RAPM impl (vraja2)](https://github.com/vraja2/rapm) - [Neil Paine NBA-Elo](https://github.com/Neil-Paine-1/NBA-elo)
- [ML for soccer prediction (arXiv 2403.07669)](https://arxiv.org/pdf/2403.07669) - [Glicko (Wikipedia)](https://en.wikipedia.org/wiki/Glicko_rating_system)

### Calibration + proper scoring
- [Accuracy vs calibration (Walsh & Joshi, arXiv 2303.06021)](https://arxiv.org/abs/2303.06021) - [Systematic review of ML in sports betting (arXiv 2410.21484)](https://arxiv.org/html/2410.21484v1)
- [Conformal win probability (NCAA 2020)](https://www.tandfonline.com/doi/full/10.1080/00031305.2023.2283199) - [Score decompositions / reliability (arXiv 2106.14345)](https://arxiv.org/pdf/2106.14345)
- [Classifier calibration survey (arXiv 2112.10327)](https://arxiv.org/pdf/2112.10327) - [Post-hoc methods at scale (arXiv 2601.19944)](https://arxiv.org/pdf/2601.19944)
- [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html) - [Diebold-Mariano (EmergentMind)](https://www.emergentmind.com/topics/diebold-mariano-test) - [Calibration over accuracy (OpticOdds)](https://opticodds.com/blog/calibration-the-key-to-smarter-sports-betting)

### Market efficiency / CLV / devig
- [CLV demystified (Buchdahl)](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl) - [Devig methods (Outlier)](https://help.outlier.bet/en/articles/8208129-how-to-devig-odds-comparing-the-methods) - [Devig methods (BetHero)](https://betherosports.com/blog/devigging-methods-explained)
- [shin (mberk, PyPI)](https://github.com/mberk/shin) - [Hegarty & Whelan 2024](https://www.sciencedirect.com/science/article/abs/pii/S2773161824000193) - [Weak-form efficiency (AJM 2023)](https://www.researchgate.net/publication/371069739_Weak_Form_Efficiency_in_Sports_Betting_Markets)
- [Exploiting soccer inefficiencies (arXiv 2303.16648)](https://arxiv.org/abs/2303.16648) - [Tennis GNN intransitivity (arXiv 2510.20454)](https://arxiv.org/pdf/2510.20454) - [Walk-forward (QuantInsti)](https://blog.quantinsti.com/walk-forward-optimization-introduction/) - [CPCV (Towards AI)](https://towardsai.net/p/l/the-combinatorial-purged-cross-validation-method)

### In-game / live
- [Bayesian in-game NBA WP (arXiv 2207.05114)](https://arxiv.org/abs/2207.05114) - [State-dependent framework (Statsurge)](https://statsurge.substack.com/p/a-state-dependent-framework-for-basketball) - [Bayesian in-game WP (DTAI KU Leuven)](https://dtai.cs.kuleuven.be/static/sports/blog/a-bayesian-approach-to-in-game-win-probability/)
- [iWinRNFL (arXiv 1704.00197)](https://arxiv.org/abs/1704.00197) - [Deep learning live NBA WP (Springer)](https://link.springer.com/chapter/10.1007/978-3-032-27272-0_7) - [Low latency at scale (Ably)](https://ably.com/blog/low-latency-sports-betting)

### CV / tracking
- [SoccerNet Game State Reconstruction (arXiv 2504.06357)](https://arxiv.org/html/2504.06357v1) - [Detect/track/ID basketball players (Roboflow)](https://blog.roboflow.com/identify-basketball-players/) - [TrackID3x3 (arXiv 2503.18282)](https://arxiv.org/pdf/2503.18282)
- [Sports video event detection survey (arXiv 2505.03991v3)](https://arxiv.org/html/2505.03991v3) - [Ultralytics tracking docs](https://docs.ultralytics.com/modes/track) - [SoccerNet sn-tracking](https://github.com/SoccerNet/sn-tracking) - [SRITrack (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0957417426014120)

### LLM in sports
- [Silicon-crowd LLM ensemble forecasting (PMC 2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11800985/) - [LM probabilities not calibrated in numeric contexts (arXiv 2410.16007)](https://arxiv.org/abs/2410.16007) - [LLMs for football outcomes (OSF 2025)](https://sciety.org/articles/activity/10.31235/osf.io/e5wpy_v2)
- [Wordalisation of footballing actions (arXiv 2504.00767)](https://arxiv.org/html/2504.00767v1) - [LLM schemas for structured extraction (Simon Willison)](https://simonwillison.net/2025/Feb/28/llm-schemas/) - [Agentic RAG survey (arXiv 2501.09136)](https://arxiv.org/html/2501.09136v4) - [SportsMetrics (arXiv 2402.10979)](https://arxiv.org/pdf/2402.10979)
