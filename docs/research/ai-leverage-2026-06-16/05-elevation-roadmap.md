# Project Elevation Roadmap -- From Foundation to Something

_Synthesis. 2026-06-16. Reads ALL briefs in `docs/research/ai-leverage-2026-06-16/briefs/` + the existing `docs/research/` corpus (edge-taxonomy, data-sources, market-microstructure, validation-methodology, competitive-landscape, precedent-analysis) against the project's north star. This is the document to read first: it says what the project IS, where the real leverage is, what to build in what order, how to validate each step leak-free, which AI-leverage technique accelerates it, and how the honest discipline keeps the whole thing from lying to itself._

---

## 0. The one-paragraph thesis

The pregame markets this project competes against are efficient on price (proven 4/4 sports; CLV ~ 0; that is the correct, honest result). So the goal is NOT a dollar edge. The goal is **the best probability estimates**: a calibrated multi-sport predictor that, on out-of-sample walk-forward data, is at least as well-calibrated as the devigged market close and is **measurably better wherever it has information the pregame line cannot have** -- chiefly **in-game state** and **own-data freshness**. Everything below ranks and sequences the work by how much it raises that prediction quality, not by how impressive it sounds. The single biggest accelerant is that one disciplined human plus Claude can run a tight eval-driven build loop faster than any feature it would chase -- so the meta-investment is the loop itself.

---

## 1. North star + non-negotiables

**North star:** Beat the best available predictor (devigged market-implied probability) on OOS **accuracy and calibration**, using our **own data**. Beating the vig (dollars) is explicitly NOT the goal; better predictions (Brier / log-loss / reliability) IS the goal and IS achievable -- in-game conditioning and freshness give the model information the pregame close literally does not have.

**Non-negotiables (binding invariants -- violating any one regresses the system):**

1. **Calibration, not edge.** The target metric is Brier Skill Score vs the **devigged** close (Shin devig, not multiplicative on lopsided markets), plus reliability diagrams and ECE-as-diagnostic. Never optimize raw accuracy (it pulls predictions toward the line) and never optimize ECE directly (gameable by predicting 0.5; pair it with a sharpness/Resolution check).
2. **No fabricated $ edge.** No ROI claims without real captured prices + forward CLV. The retracted numbers stay retracted (+18.38% market-follow artifact, endQ3 0.119 Q4-leak, +54% L5-proxy). Honest "no edge / market efficient" outputs are **successes** and a product feature.
3. **Leak-free OOS only.** Walk-forward (expanding window) with purge (same-team within 48h) + embargo (3-day gap); feature selection and tuning happen INSIDE the window; vintage alignment (every feature's value as-of prediction time). K-fold on time-ordered data is a correctness bug.
4. **Two-corpus rule.** No signal leaves the research surface without passing on >= 2 independent corpora (seasons or sports). Single-fold lifts are artifacts. A pass-on-A / honest-reject-on-B is a valid finding, not a failure.
5. **Statistical honesty.** Every eval reports SEM / 95% CI and clusters SEs by game_id/season (naive SEs run ~3x too narrow). Prove "beats the close" with a Diebold-Mariano test (p < 0.05, N >= 200) on per-game Brier/log-loss differences, not a bare point delta.
6. **Local-only, human-gated.** Never push to public `origin`; never write `data/registry/`; never flip a flag ON; `src/`, `kernel/`, `api/`, `scripts/team_system`, `intel` are human-gated (build in `scripts/platformkit` or `domains/<sport>`); <= 300 LOC/file; no secrets; `data/` + `vault/` gitignored. Per-file tests only (full `pytest tests/` freezes the box). Bash cwd is flaky -> prefix every command with `cd /c/Users/neelj/nba-ai-system &&`.
7. **LLM never emits the number.** LLMs are bad probability estimators (ECE 0.12-0.39 across frontier models). They route, extract, synthesize, and emit bounded leak-flagged multipliers; the quantitative pipeline computes every probability.

---

## 2. Where the real leverage is (ranked)

Ranked by expected gain in OOS prediction quality per unit of effort, given the project's measured state (pregame efficient, in-game the proven combinable edge).

| Rank | Lever | Why it raises prediction quality | Headroom | Risk it's a mirage |
|---|---|---|---|---|
| 1 | **In-game conditioning** | The pregame model already matches the devigged close; the ONLY place it can honestly depart is on information the close never had -- realized score/time/foul state. Academic in-game models cut Brier 0.04-0.09 over pregame-only over a game; this project's own PBP replay already proved foul-out is the one surviving in-game modification. | HIGH | Low -- it's new information by construction, not a re-pricing of priced facts. |
| 2 | **Data freshness / own-data** | Freshness is the binding constraint on pregame calibration (the close moves on news the model can't see). The capturable version is structured injury/lineup deltas + the in-game live feed. Own CV-derived spatial features are not in any market signal. | MED-HIGH | Medium -- must prove the fresh signal was actually available at prediction time (vintage alignment) or it's a leak. |
| 3 | **Calibration rigor** | Cheap, immediate, and it's literally the north-star metric. Per-quarter/per-market reliability diagrams + Shin-devig baseline + DM tests turn vague "we're good" into auditable proof, and surface exactly where the model is over/underconfident (live models are overconfident in Q1). | MED (one-time, then compounding) | Low -- this is the measurement layer; the risk is NOT doing it. |
| 4 | **Eval-driven loop** | The meta-lever. A Brier-Skill-Score CI gate + golden dataset + two-corpus assertion means every future change is auto-judged honestly. This is what makes all other work compound instead of drift. | HIGH (force multiplier) | Low. |
| 5 | **Multi-sport breadth** | A second/third corpus per signal IS the two-corpus rule; MLB (free pitch-by-pitch live feed) is the easiest in-game win after NBA. Breadth also de-risks any single-sport overfit and widens the productizable surface. | MED | Medium -- breadth without depth dilutes; each sport must clear the same OOS bar. |
| 6 | **CV moat (broadcast -> court coordinates)** | The genuinely uncommoditized data asset; homography-derived spacing/zone features feed in-game conditioning and are in no market signal. ~$0.10/game vs six-figure vendors is the differentiator. | MED (long build) | Medium -- detection is NOT the bottleneck; association/OCR are; spatial features add ~0.005-0.02 Brier, real but small. |
| 7 | **LLM intelligence layer** | Structured extraction of injury/lineup/news into typed JSON is the freshness pipeline; agentic RAG assembles pregame context; wordalisation makes the board explainable. All synthesis/extraction, never the number. | MED | Medium -- easy to let an LLM number leak into the chain; overconfidence at 80-90% is documented. |
| 8 | **Build velocity via Claude** | Hooks/skills/subagents/headless-cron + model routing cut friction and cost 40-50% and enforce invariants mechanically. Velocity only matters if pointed at items 1-4. | HIGH (force multiplier) | Low, but "velocity at the wrong target" is the real risk. |

The two force-multipliers (4 and 8) are not features -- they make every feature land faster and more honestly. Do them early and cheaply.

---

## 3. Phased plan -- Now / Next / Later

For each item: **What - Why (prediction quality) - Validate (leak-free) - Effort - AI-leverage technique.**

### NOW (weeks 0-4): make the measurement honest and lock the loop

**N1. Brier-Skill-Score CI gate + golden dataset (THE keystone).**
- What: A `promptfoo`/pytest gate that runs the walk-forward backtest and fails (exit 1) if BSS vs devigged close drops below threshold on EITHER of two corpora. Build a git-tracked golden set of ~100 game states (true WP from PBP replay, post-game stats, scheme annotations) in `tests/fixtures/`.
- Why: Turns the north star into an enforced contract; every later change is auto-judged. Nothing else compounds without this.
- Validate: Walk-forward + purge + embargo baked in; assert `feature_availability_date < game_date` for every feature in the window; report Brier +/- 95% CI, clustered by game_id; DM p-value vs close.
- Effort: 2-4 days. AI-leverage: **Evaluator-Optimizer pattern**; `promptfoo` for CI (fully local); Anthropic statistical-eval discipline (SEM, paired-difference, pre-specified effect size).

**N2. Standardize devigging on Shin; build the calibration audit.**
- What: Use `mberk/shin` for all two/three-outcome devig (keep multiplicative only at near -110/-110 for speed). Produce per-sport, per-market, per-quarter reliability diagrams overlaying model vs devigged-Pinnacle close; report Murphy decomposition (Reliability / Resolution / Uncertainty).
- Why: The close is only the right baseline once devigged correctly; FLB in multiplicative devig makes a model look better-calibrated than it is. Decomposition tells you whether you need lower Reliability or higher Resolution.
- Validate: Use devigged Pinnacle (Odds API Business or OddsPapi free tier) as the reference; never a soft-book close.
- Effort: 2-3 days. AI-leverage: prompt-cache the static signal-catalog/vault context; route the audit narrative to Sonnet.

**N3. Wire the 2D in-game blend surface into the existing Monte Carlo prior.**
- What: `final = w(t, margin) * P_live + (1 - w) * P0`, where `P0` = existing calibrated pregame sim, `P_live` = a lightweight logistic/XGBoost on (score_diff, seconds_remaining), and `w` = empirical 2D weight surface. Add foul-trouble differential + bonus + garbage-time clamp as the next features. Exponential-smooth over the last 3-5 possessions for temporal smoothness.
- Why: This is the #1 lever. It is new information by construction -> a genuine, honest calibration gain the pregame close cannot match. Foul-out already survived this project's own replay validation.
- Validate: Compute `w` on a held-out season, evaluate on a different one (the Statsurge author's explicit overfitting trap); per-quarter reliability diagram on the `pbp_replay.py` harness (today Q1-Q3 Brier 0.34-0.40 -> must improve); two-corpus (NBA + MLB).
- Effort: 1 week. Build in `domains/` (no `src/`/`kernel/` edits). AI-leverage: **Routing** (live re-price = cheap fast path); minimal-feature discipline from the in-game brief.

**N4. Lock invariants as hooks, not prose.**
- What: `.claude/settings.json` PreToolUse hooks: block `git push origin` / `--force`, block `pytest tests/`, prepend the cwd to bash, warn on `src/`/`kernel/` edits and on files > 300 LOC. `fallbackModel` to dodge 529s overnight.
- Why: CLAUDE.md is a request; a hook is a guarantee. Protects every future autonomous session from breaking the no-push / no-leak discipline.
- Effort: half a day. AI-leverage: **Hooks as the enforcement layer**; model routing (`CLAUDE_CODE_SUBAGENT_MODEL=haiku`).

### NEXT (months 1-3): widen the honest signal surface

**X1. Structured freshness pipeline (injury/lineup deltas -> vacated-load).**
- What: Nightly + 2h-pre-game LLM structured-extraction agent: `{player_id, team_id, status, severity, game_date, source, extracted_at, confidence}` -> SQLite. Each `OUT` row subtracts usage and redistributes via the existing vacated-load model.
- Why: Freshness is the #2 lever and the pregame model's known structural gap; this is the capturable slice of the freshness edge.
- Validate: VINTAGE ALIGNMENT is the whole game -- store `extracted_at`, assert it precedes tip; walk-forward with the as-of value only; two-corpus.
- Effort: 1-2 weeks. AI-leverage: **LLM structured extraction** (Pydantic/`instructor`, `max_retries=3`); **Agentic RAG** for pre-game context assembly; schema-validate downstream (never trust constrained decoding semantically).

**X2. MLB in-game conditioning (fastest second sport).**
- What: Same blend pattern as N3 on MLB, fed by the free `statsapi.mlb.com .../feed/live` pitch-by-pitch state (count, runners, score, inning). Use MLB's own published win probability as a calibration baseline.
- Why: Delivers the two-corpus requirement for the in-game architecture AND the richest free real-time feed of any sport here. Pitcher Statcast (xFIP/SIERA via `pybaseball`) is the most defensible MLB freshness feature.
- Validate: Retrosheet (1898-2025) as an independent second MLB corpus; per-inning reliability.
- Effort: 1-2 weeks. AI-leverage: **Parallelization (Sectioning)** -- the four sports' pipelines are independent; run them as parallel subagents.

**X3. Calibration drift monitor + public track-record ledger.**
- What: Append-only CSV in the vault logging every prediction (timestamp, inputs, calibrated prob, outcome). Weekly automated drift check (recent Brier/ECE vs 30-day rolling baseline); alert on > 1-sigma drop.
- Why: The trust moat (Good Judgment pattern) -- an auditable multi-month calibration record is worth more than any single model upgrade and catches silent data-drift regressions.
- Validate: The ledger IS the validation artifact; commit the scripts so a skeptic can reproduce.
- Effort: 3-5 days. AI-leverage: **headless `-p` nightly cron** + `PushNotification` on drift; Langfuse (local, MIT) for trace/eval observability if the LLM layer grows.

**X4. Conformal intervals on the in-game layer.**
- What: Inductive conformal prediction on completed in-game sequences -> report intervals, not just points ("halftime: A 0.61 [0.52, 0.70]").
- Why: Mid-game state is highly non-stationary; conformal gives OOS coverage guarantees under exchangeability only and is better-calibrated at the tails -- honest uncertainty is itself a product feature.
- Validate: Calibrate nonconformity scores on a held-out set; verify coverage year-by-year (rule changes can break exchangeability).
- Effort: 1 week. AI-leverage: Evaluator-Optimizer loop to tune the calibrator against held-out Brier.

### LATER (months 3-12): the data moat and the product

**L1. CV homography -> in-game spatial features (the moat).**
- What: ResNet18 keypoint detector on ~74 NBA court landmarks + YOLOv8 + BoT-SORT (GMC for camera pan) + SigLIP->K-means team ID (2 clusters/game). At each PBP-anchored possession boundary, compute paint density, 3pt spacing (convex hull), corner occupation, transition speed. Feed as in-game conditioning signals. SAM2 + pose offline-only (1-2 FPS).
- Why: The genuinely uncommoditized own-data asset; spacing correlates ~0.15-0.25 with 3PA rate; expected in-game Brier shift ~0.005-0.02 -- small but real, leak-free, and in no market signal. Extractable WITHOUT reliable player re-ID (court positions, not identities).
- Validate: Train spatial models on 2023-24, test 2024-25; Brier improvement of in-game head WITH vs WITHOUT spatial features; honest reject if none. Detection is not the bottleneck -- association/OCR are; PBP-anchored weak supervision sidesteps jersey OCR.
- Effort: 4-8 weeks. AI-leverage: `roboflow/sports` (MIT) for keypoint/ball/jersey heads; **Orchestrator-Workers** for the offline enrichment fan-out; Message Batches API for bulk nightly enrichment (50% off).

**L2. Soccer + tennis freshness depth (breadth -> 3-4 corpora).**
- What: StatsBomb open-data xG to set the Poisson lambda (Dixon-Coles rho ~ -0.13, time-decay xi ~ 0.001-0.003/day); Sackmann ATP/WTA CSVs (surface, days-since-last-match fatigue, H2H) into the existing Elo.
- Why: Pushes the two-corpus rule to four; structural/relational features (tennis GNN intransitivity) may lift calibration where box-score features plateau.
- Validate: Per-sport OOS; RPS (not Brier) for 3-way soccer; treat each tennis surface as a mini-corpus.
- Effort: 2-3 weeks. AI-leverage: per-sport **Agent Skills** (`skills/nba|mlb|soccer|tennis/SKILL.md`) so agents load only the relevant domain context.

**L3. LLM-as-orchestrator for the live re-pricing flow + wordalisation on the board.**
- What: An orchestrating Claude agent detects a live event (structured extraction from PBP), calls `score_in_game_state(...)` as a typed tool, diffs vs pregame, emits a structured update with delta + confidence tier. Separately, percentile-bucket the sim's feature contributions -> one-paragraph scouting narrative on the React board.
- Why: LLMs excel at routing/synthesis/narration; the sim computes every number. Wordalisation drives engagement (the product), not accuracy (the model).
- Validate: Any LLM-touching pipeline change -> OOS Brier/ECE check before shipping; bounded multipliers only (e.g., 0.85-1.15x), leak-flagged.
- Effort: 2-3 weeks. AI-leverage: Claude **tool use** (`strict: true`); **single-hop pre-warmed extraction** for live (multi-hop agentic RAG's 10-30s latency is fine pregame, NOT live).

**L4. Productize the React board as calibrated decision-support (see Section 4).**

**Explicitly de-prioritized / do-not-do:** pregame "alpha" search (markets efficient -- the 60/60 gate REJECT is the honest answer); jersey-OCR player-level re-ID (high cost, fails on fast breaks -- use PBP anchoring); LLM-emitted probabilities; computer-use for odds scraping (5-10x slower/costlier than the Odds API; use the API); fine-tuning the point model (GBMs/MC win on tabular -- fine-tune only narrative/extraction style if ever, via QLoRA); CrewAI / heavy frameworks (uncapped-loop cost risk; Claude Code + thin orchestration is the stack).

---

## 4. "Make it something" -- credible productization as calibrated decision-support

The product is NOT a picks/profit service (that framing destroys the trust moat and attracts the wrong audience). It is a **4-sport calibrated probability forecasting system with transparent OOS validation and in-game conditioning** -- decision-support for analysts/media/orgs who value rigor.

**The five moves, in order of moat-building value:**

1. **Lead with the calibration record.** First thing on the board/README: "NBA pregame Brier 0.208 (market 0.198) | honest OOS walk-forward, 2 corpora | in-game conditioning is the measured gap." Says everything about prediction quality, nothing about the vig.
2. **Make "honest reject" a first-class UI citizen.** "No edge detected; market-efficient here" displayed prominently differentiates from every toy competitor and proves the discipline in real time.
3. **Hero interaction = the pregame -> live update.** "Pregame 47% | current state (Q3, +8) 71% [interval]." This is the one place the system measurably beats pregame-only -- build the workflow around it.
4. **One-command reproducible proof.** `predict_matchup` + committed fixtures reproducing in < 60s; CLI prints calibration context on startup ("last OOS Brier; last recalibration date").
5. **The data moat + track-record ledger.** The CV possession data + 660-player/30-team intel vault + the append-only prediction ledger are the irreplaceable, compounding assets (18-36 month flywheel). Document and timestamp them; frame as proprietary substrate.

**Why this is defensible (from competitive-landscape + precedent):** institutional quant firms are structurally excluded from this market (no hedge instrument, labor economics fail on a $50-100M edge pool, account-level blocks, sub-deployment limits) -- the field is sized for a disciplined solo operator with proprietary data, which is exactly Voulgaris/Benter/Thorp's template. The honest reframe: this project's analog of their proprietary-data advantage is **own CV + in-game integration**, and its product is **calibration rigor**, not a bet.

---

## 5. Risks + how the honest discipline guards against self-deception

| Risk (the lie the system could tell itself) | Guard already in the invariants |
|---|---|
| Single-fold lift looks like a real signal | Two-corpus rule; CPCV; the gate logs honest rejects as findings. |
| Feature secretly uses post-game info (leak) | Vintage alignment assertion (`availability_date < game_date`); purge + embargo; feature selection inside the window. |
| "Beats the close" is noise | DM test p < 0.05, N >= 200; SEM/95% CI on every eval; clustered SEs (else 3x too narrow). |
| ECE optimized into uselessness (predict 0.5) | ECE is diagnostic-only; pair with sharpness/Resolution; primary gate is Brier/log-loss vs devigged close. |
| Devig flatters the model (FLB) | Shin devig on lopsided markets; devigged Pinnacle, never a soft book, as baseline. |
| LLM number leaks into the chain | LLM emits bounded leak-flagged multipliers only; sim computes every number; OOS Brier/ECE check on any LLM-touching change. |
| In-game weight surface overfit | Compute `w` on held-out season, evaluate on a different one; per-quarter reliability. |
| Calibration win is just the early-season structural window | Separate eval for games 1-20 vs 21+ to attribute timing vs structure. |
| Autonomous agent breaks no-push / no-leak rules | Hooks (not prose) block push / full-pytest / src edits; human gates on `src/kernel/api`; never flip a flag ON. |
| Data moat is dirty parquets, not a moat | Curate data like code; the moat exists only when data demonstrably improves outputs. |
| Multi-agent hallucination cascade / cost blowout | Hierarchy + verification layer (not flat "bag of agents", 17x vs 4.4x error amplification); cross-model adversarial reviewer; `max_budget_usd` from day one; multi-agent only for genuinely parallel work. |
| The build chases impressive-sounding features | The eval gate (N1) judges every change on BSS vs the close; if it doesn't move the honest metric, it doesn't ship. |

**The meta-guard:** the project's headline achievement is that it built the harnesses that caught and retracted its own inflated numbers. That reflex -- treat every win as guilty until OOS-proven across two corpora with a CI and a DM test -- is the actual product. Keep it; it is what makes "best predictions" a claim a skeptic can verify rather than a slogan.

---

## Sources / References

**Project research corpus (existing):**
- `docs/research/edge-taxonomy.md` -- 164 enumerated edges (information/model/execution/structural); CV spatial features as the primary information moat.
- `docs/research/data-sources.md`, `docs/research/market-microstructure.md` -- data + market structure baselines.
- `docs/research/validation-methodology.md` -- leak-free OOS / walk-forward discipline.
- `docs/research/competitive-landscape.md` -- why institutional quant firms are structurally excluded from prop markets.
- `docs/research/precedent-analysis.md` -- Voulgaris / Benter / Thorp solo-operator template (proprietary data + modeling + automation).

**Briefs (this batch, `docs/research/ai-leverage-2026-06-16/briefs/`):** ingame-live-modeling, calibration-scoring, evals-quality, market-efficiency-clv, sports-cv-tracking, sports-data-sources, llm-in-sports, ai-product-moats, anthropic-agent-patterns, claude-code-power, agentic-orchestration, agent-frameworks, claude-skills, claude-mcp, claude-agent-sdk, claude-api-core, claude-api-scale, claude-computer-use, rag-retrieval, finetune-vs-rag, llmops-observability, sports-modeling-core, github-sports-repos.

**Key external links (preserved from briefs):**
- In-game WP: [Bayesian in-game NBA WP (arXiv 2207.05114)](https://arxiv.org/abs/2207.05114) - [Statsurge state-dependent framework](https://statsurge.substack.com/p/a-state-dependent-framework-for-basketball) - [DTAI KU Leuven Bayesian in-game](https://dtai.cs.kuleuven.be/static/sports/blog/a-bayesian-approach-to-in-game-win-probability/) - [iWinRNFL (arXiv 1704.00197)](https://arxiv.org/abs/1704.00197)
- Calibration/scoring: [Walsh & Joshi accuracy-vs-calibration (arXiv 2303.06021)](https://arxiv.org/abs/2303.06021) - [Conformal win probability (T&F)](https://www.tandfonline.com/doi/full/10.1080/00031305.2023.2283199) - [Diebold-Mariano test](https://www.emergentmind.com/topics/diebold-mariano-test) - [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html) - ["Calibeating" (arXiv 2209.04892)](https://arxiv.org/pdf/2209.04892)
- Market efficiency / devig / CLV: [Buchdahl CLV demystified](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl) - [mberk/shin](https://github.com/mberk/shin) - [Hegarty & Whelan 2024](https://www.sciencedirect.com/science/article/abs/pii/S2773161824000193) - [CPCV](https://towardsai.net/p/l/the-combinatorial-purged-cross-validation-method)
- Evals: [Anthropic statistical model evals](https://www.anthropic.com/research/statistical-approach-to-model-evals) - [Anthropic Bloom](https://www.anthropic.com/research/bloom) - [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) - [promptfoo](https://github.com/promptfoo/promptfoo)
- Agents / Claude: [Building Effective Agents (Anthropic)](https://www.anthropic.com/research/building-effective-agents) - [Multi-agent research system (Anthropic)](https://www.anthropic.com/engineering/multi-agent-research-system) - [Agent Skills (Anthropic)](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) - [Extend Claude Code](https://code.claude.com/docs/en/features-overview)
- LLM in sports / RAG: [LLM ensemble vs human crowd (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11800985/) - [LM probabilities not calibrated (arXiv 2410.16007)](https://arxiv.org/abs/2410.16007) - [Wordalisation of football actions (arXiv 2504.00767)](https://arxiv.org/html/2504.00767v1) - [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- CV: [SoccerNet Game State (arXiv 2504.06357)](https://arxiv.org/html/2504.06357v1) - [Roboflow basketball CV](https://blog.roboflow.com/identify-basketball-players/) - [roboflow/sports](https://github.com/roboflow/sports) - [TrackID3x3 (arXiv 2503.18282)](https://arxiv.org/pdf/2503.18282)
- Data: [The Odds API V4](https://the-odds-api.com/liveapi/guides/v4/) - [MLB-StatsAPI](https://github.com/toddrob99/MLB-StatsAPI) - [Jeff Sackmann tennis_atp](https://github.com/JeffSackmann/tennis_atp) - [Retrosheet Fall 2025](https://www.retrosheet.org/fall2025release.html) - [StatsBomb open-data](https://github.com/statsbomb/open-data)
- Modeling / moats / ops: [Dixon-Coles + sports-modeling sources in sports-modeling-core.md] - [AI Moats 2026 (Valtorian)](https://www.valtorian.com/blog/ai-moats-2026) - [Langfuse](https://langfuse.com) - [Pydantic AI](https://ai.pydantic.dev)
