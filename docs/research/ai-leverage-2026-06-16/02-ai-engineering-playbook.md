# AI Engineering Playbook -- Agents, RAG, Evals, Frameworks, LLMOps

_Synthesis, 2026-06-16. Inputs: briefs agentic-orchestration, rag-retrieval, evals-quality, finetune-vs-rag, agent-frameworks, llmops-observability. Audience: a solo, Claude-agent-driven builder of a multi-sport CALIBRATED prediction platform (Python core + React live board). North star: BEST PREDICTIONS (OOS accuracy/calibration vs devigged market-implied), never a fabricated $ edge. Local-only; honest rejects count as successes._

---

## How to read this document

This is the "how to build with LLMs" companion to the platform's modeling/edge research. One framing runs through every section:

- The **calibrated probability** (Brier, log-loss, CRPS) is owned by the statistical machinery -- GBMs, Bayesian models, the Monte Carlo possession sim, and the walk-forward gate. LLMs and agents NEVER produce the betting number.
- LLMs/agents own **everything around** that number: research velocity, signal proposal, intel synthesis, scouting narrative, orchestration, validation, and delivery.
- Every LLM-touched artifact is held to the same discipline as the models: leak-free, OOS, two-corpus, honest-reject-friendly, no edge language.

If you remember one thing: **eval-driven development is the spine** (Section 3). Agents, RAG, fine-tuning, and frameworks are all only as good as the eval that gates them.

---

## 1. Agent design patterns (with when-to-use)

The dominant lesson across the orchestration research: **the simplest architecture that passes the eval is the right one.** Multi-agent is not free -- single-agent agentic is ~4x chat token cost, multi-agent ~15x; token budget explains ~80% of performance variance; 40% of multi-agent pilots fail within 6 months (Gartner 2025), mostly from over-engineering. Reach for more agents only when the task is genuinely parallel, exceeds one context window, or the single-agent baseline accuracy on the subtask is below ~45%.

### Pattern catalog

| Pattern | What it is | Use WHEN | Avoid WHEN |
|---|---|---|---|
| **Tool-use loop (ReAct/ACI)** | One agent: call tool -> observe -> decide next. Backbone of Claude Code. | Default for almost everything. Bounded, sequential, tool-mediated tasks. | Never; this is the floor. Always set `max_iterations` + a stop condition. |
| **Single-agent + extended thinking** | One capable model reasons deeply on a bounded problem. | Focused reasoning: a calibration audit, signal gating, a tight modeling decision. Wins on normalized-compute reasoning (arxiv 2604.02460). | Task is genuinely parallel or exceeds one context window. |
| **Orchestrator-worker (mixed tiers)** | Lead model (Opus-class) decomposes + synthesizes; cheap workers (Sonnet/Haiku-class) execute in parallel. | Subtask list is unpredictable: open-ended research, multi-file code changes. (Anthropic: +90.2% over single Opus on research.) | Fundamentally sequential tasks. Vague worker scoping causes duplicate work. |
| **Parallel fan-out / map-reduce** | N independent workers on partitioned problem; reducer synthesizes. | Cross-sport/cross-hyperparameter experiments, literature sweeps, parallel feature engineering. Up to 90% time reduction. | Workers share mutable state (same parquet/DB row) -> corruption. Pre-assign non-overlapping ranges. |
| **Reflection / evaluator-optimizer** | Generator produces; evaluator scores vs rubric; revise; loop. | Clear checkable criteria: report completeness, code correctness, prediction-brief quality. Cap 2-5 rounds. | No checkable criteria. Same-model echo chamber -- use a different model/system prompt as evaluator. |
| **Debate / ensemble (adversarial verify)** | Independent answers/critiques; synthesis resolves. ARIS: executor + cross-family reviewer, 4 rounds, score 5.0 -> 7.5/10. | Verifying integrity of a result (leakage, cherry-picking, self-normalized scores). | Sequential reasoning -- ensemble does NOT beat single-agent there; sycophantic convergence undermines it. |
| **Planner-executor** | Planner (extended thinking) writes an auditable plan; executor carries it out. | Long-horizon (>20 step) tasks where the plan must be auditable; multi-sport signal campaigns. | Dynamic environments (live game state). Add a replanning trigger when an unexpected state hits. |
| **Routing** | Classifier/rules dispatch input to a specialized subpipeline. | Cost optimization (cheap model for simple queries), per-sport specialization, in-game vs full-audit tiers. | When a single prompt already handles the spread of inputs cheaply. |
| **Hierarchical delegation** | Orchestrator -> sub-orchestrators -> workers, bounded scope per layer, plus an assurance plane feeding corrections back. | Large campaigns needing a self-correcting loop. | Flat "bag of agents" -- up to 17.2x error amplification vs ~4.4x centralized (DeepMind). Always keep a hierarchy + verification layer. |

### The four failure modes to design against

1. **Hallucination cascade (#1 risk).** One agent hallucinates; downstream agents elaborate on it as ground truth. Break it with ground-truth tool calls at each stage (not agent-to-agent messages) and an adversarial fact-check stage with an explicit disconfirmation rubric.
2. **Tyranny of the majority / sycophancy.** Agents conform to consensus regardless of facts. Keep agents independent (no cross-talk) until a separate synthesis step; use structured rubrics, not free-form consensus.
3. **Context-handoff loss.** When an agent exhausts its window, the handoff drops information. Persist intermediate state to the vault or a scratch JSON BEFORE context is exhausted -- never debug from final output alone.
4. **Token blowup / runaway loops.** Multi-agent ~15x chat cost; uncapped loops have hit $414 in a single run. Cap worker count (4-5 is the practical ceiling on a local RTX 4060 GPU), set `max_iters`, and trace every decision.

### This project's highest-leverage agent uses

- **Parallel modeling experiments (the #1 solo win).** One worker per sport runs the same signal candidate, returns Brier/log-loss OOS; reducer synthesizes "signal X helps NBA+MLB, hurts tennis." Pre-assign file paths (the project's known concurrent-write-collision rule). Cap at 4-5 for GPU contention.
- **Adversarial verification of every calibration claim.** When a candidate shows a lower Brier, dispatch a cross-model reviewer: "verify leak-free, confirm the walk-forward split is real, confirm it holds on corpus 2, flag self-normalized or cherry-picked windows." This operationalizes "honest rejects are successes" -- the reviewer's job is to FIND the reject.
- **Parallel research sweeps** with explicitly scoped subagents (vague scopes cause duplicate work).
- **Reflection loop on prediction briefs** with a project-specific rubric: every probability claim cites a Brier score; no "beat the market" language; in-game conditioning flagged as the measured improvement; sources are real vault nodes, not hallucinations.
- Start **synchronous**; async multi-agent adds coordination/state/error-propagation complexity that Anthropic's own research system deliberately avoids.

---

## 2. Retrieval / knowledge layer

Naive RAG ("chunk -> embed -> cosine -> stuff") is a prototype floor, not production. The consensus 2025-2026 production pipeline is: **hybrid (semantic + BM25) -> RRF -> reranker -> LLM**, with **Anthropic Contextual Retrieval** layered on at ingestion as the single best-documented accuracy lift.

### The production pipeline

1. **Contextual Retrieval (do this first).** Before embedding each chunk, have Claude generate a 1-2 sentence situating context using the full parent document, prepend it, then embed AND BM25-index. Cuts retrieval failures 47-49%. One-time ingestion cost; prompt-cache the parent doc for ~69% discount; use Haiku for the context generation (it does not need a powerful model). Pass@10: 87.2% baseline -> 93.2% (+ BM25) -> 95.3% (+ rerank).
2. **Hybrid retrieve.** Dense vector + BM25 (`rank_bm25`), merged by Reciprocal Rank Fusion (`score = sum(1/(k+rank)), k=60`). Anthropic default weight 80% semantic / 20% BM25; lean BM25 higher for keyword-heavy corpora (exact player names, stat types). Retrieve 100-150 candidates.
3. **Rerank.** Cross-encoder scores (query, doc) jointly; keep top 5-20. Use `bge-reranker-large` self-hosted (free, no API cost) or Cohere Rerank 3.5. Adds 100-200ms -- fine for async pregame synthesis, too slow for a sub-100ms live overlay tick.
4. **Generate** with the reranked top-k in context.

### When to use which retrieval architecture

- **Structured data (box scores, PBP, signals, model outputs):** SQL / Parquet / direct Python. NO embedding search. Do not try to embed a 5000-row parquet as one RAG document.
- **Semi-structured (vault notes, atlas markdown, edge maps):** Contextual embeddings + hybrid + rerank. This is where RAG earns its keep.
- **External (news, injury reports):** agentic web-search tool AT query time, not pre-indexed.
- **Narrative/relational (scheme notes, coaching philosophy, archetype clusters):** GraphRAG (Microsoft) or lighter Graphiti/Neo4j -- "how are X and Y related" queries. Expensive to build (many LLM calls/doc); run ONLY over the highest-value narrative docs, never over box scores.

### Agentic RAG is the right shape for in-game queries

A query like "Q3 89-84, Brunson on 4 fouls -- projected win prob and what does our intel say about his foul behavior here?" needs three different sources: structured PBP state (SQL), the calibrated sim output (existing call), and vault foul-tendency intel (vector retrieval), plus optional news (web search). An agentic tool-use loop that routes each sub-query to the right function is cleaner and more accurate than embedding everything into one space. Add an explicit evidence-grounding check ("cite the vault note or data source for any claim") because agentic loops can hallucinate "sufficient evidence."

### Vector DB choice (5-10% of quality; pipeline dominates)

- **LanceDB** -- embedded, disk-based, reads/writes Lance files alongside existing parquets, no server to manage, native hybrid search. **Recommended default for this project.**
- **pgvector** -- fine if a Postgres instance ever joins the stack (< 2-3M vectors).
- **Qdrant** -- if rich metadata pre-filtering matters (filter before vector search -> faster + more accurate); good for multi-sport routing.
- Skip Pinecone (5-10x cost for a solo project) and Milvus (extreme-scale overkill).

### The hard boundary

**RAG does NOT improve calibration of numeric predictions.** It improves the LLM's reasoning over unstructured intel. The calibrated probability stays owned by the statistical model + walk-forward gate. A surfaced intel node ("Brunson shoots 38% when fatigued in Q4") is a SOFT PRIOR for scouting synthesis, never an override of the model probability. Keep that boundary explicit in the system prompt. Evaluate retrieval with RAGAS (Faithfulness, Context Precision/Recall); the project-specific metric is "does the correct foul-tendency node land in the top-5 for the relevant query?"

---

## 3. EVAL-DRIVEN development (the core discipline)

**This is the spine of the whole playbook.** Agents, RAG, fine-tuning, and frameworks give you token tracing, not prediction-quality tracing -- you own that. Every change to a model, feature, prompt, or agent must pass an eval before it ships, and an honest reject is a successful eval outcome.

### Two eval regimes -- never confuse them

| Output type | Evaluate with | NOT with |
|---|---|---|
| **Numeric probabilistic predictions** | Proper scoring rules: Brier, log-loss, CRPS; Brier Skill Score vs devigged close; ECE + sharpness | LLM-as-judge (no ground truth on numbers) |
| **Free-form text** (scouting summaries, scheme priors, intel nodes) | LLM-as-judge with a tight rubric (~85-90% human agreement), against a golden set | Proper scoring rules (no probability to score) |

### Proper scoring rules (the forecasting foundation)

- **Brier** = mean((p - y)^2); **log-loss** = heavier penalty for confident errors; **CRPS** for continuous distributions (point totals with uncertainty). All strictly proper -- only honest probabilities maximize expected score. Use multiple simultaneously; never optimize one in isolation.
- **Brier Skill Score = 1 - (Brier_model / Brier_reference).** The reference MUST be the **devigged market-implied probability**, not a coin flip. BSS > 0 vs 50/50 is trivial and meaningless; BSS > 0 vs the devigged close = measurably better calibration than the best available predictor. This is the project's north-star metric -- report it every run.
- **Calibration:** 10-bin reliability diagram, report ECE. **Guard against gaming:** ECE can be faked by predicting 0.5 everywhere -- always report **sharpness** (variance of predictions) alongside. ECE=0.01/sharpness=0.001 is useless; ECE=0.02/sharpness=0.05 is genuinely informative.

### Leak-free walk-forward (the only valid backtest for time-series sports)

- **Expanding window:** train 1..t, predict t+1, append, repeat. Never look ahead.
- **Vintage alignment:** every external-derived feature (injury reports, line moves) uses the value available AT prediction time. Add a `feature_availability_date` to the signal registry; assert `availability_date < game_date` for all features in the eval window.
- **Two-corpus rule (non-negotiable):** a change must show positive BSS on the NBA corpus AND at least one other sport/season. A lift on one with a drop on another = overfitting red flag. Single-corpus lift is an artifact.
- **Selection inside the window:** feature selection AND hyperparameter tuning must happen inside the expanding window, or a "leak-free" walk-forward is still optimistic.
- **Temporal gap:** 1-3 day buffer between train end and val start.

### Statistical rigor (Anthropic's eval methodology)

- **Always report SEM / 95% CI.** Stop reporting bare scores: "Brier = 0.208 +/- 0.003 (95% CI, N=847)." A 2-point gain with a 3-point CI is noise.
- **Clustered SEs.** When game-states cluster by game/season, naive SE underestimates uncertainty by 3x+. Cluster by `game_id` / season.
- **Paired-difference analysis** for v_n vs v_n+1: analyze per-game Brier deltas directly. Frontier models share right/wrong patterns (corr 0.3-0.7) -> 40-60% lower variance than independent comparison.
- **Pre-specify effect size** before running (suggest 0.005 absolute BSS), compute required N for 80% power. Avoid HARKing.

### LLM-as-judge (text only)

- Rubric design matters most; explain-then-rate slightly beats rate-then-explain. Calibrate the judge against a 50-100 example human-labeled golden set (target >80% agreement) before scaling.
- **Bias guards:** randomize order (position bias); never let a model judge its own output (self-preference); add a length-normalized criterion (verbosity bias); 2-3 judge ensemble with inter-judge agreement (Cohen's kappa > 0.6).

### Tooling

- **promptfoo** -- fastest CI regression gate. YAML eval cases, runs in GitHub Actions, fails the build on score drop. Fully local, zero infra. **Start here.**
- **Inspect AI** (UK AISI, MIT) -- rigorous Task/Solver/Scorer scaffold, `model_graded_qa()` with bootstrap CIs, Docker sandboxing for tool-using evals. Use for structured component evals (scheme prior, intel summaries). You write custom Scorers for Brier/log-loss; no CI wiring out of the box.
- **Anthropic Bloom pattern** -- auto-generate diverse edge-case game states ("20 states where in-game conditioning matters most: blowouts, foul trouble, garbage time, close 4th"). Manually validate ~10% before adding to the golden set (synthetic states can drift from the real distribution).
- **Braintrust** -- dataset versioning + per-PR experiment diffs, but SaaS (sends data to external servers) -> conflicts with the no-external-push invariant. Self-host or avoid for sensitive data; promptfoo is fully local.

### The eval-driven loop for THIS project

1. Build a **git-tracked golden set of ~100 game states** in `tests/fixtures/` (NOT `data/`, which is gitignored): known true win prob (from PBP replay with outcome known), post-game stats for prop evals, human-annotated scheme description for text evals. One afternoon to build; a stable regression anchor forever. Labels are ACTUAL outcomes, never model output.
2. **Primary CI gate:** every model/feature change runs the walk-forward and reports Brier vs devigged close, BSS, ECE+sharpness, log-loss. BSS < 0 on EITHER corpus -> reject (exit 1).
3. **promptfoo nightly cron:** if any scorer drops >1 sigma from the 30-day rolling mean, notify -- catches silent data-drift regressions, not just code changes.
4. **Inspect `model_graded_qa()`** quarterly on intel-node quality so the 660-player/30-team layer does not silently degrade as the vault grows.

---

## 4. Fine-tune vs RAG decision guide

The honest ladder is NOT a ladder -- pick by the gap you are closing. **Exhaust prompt engineering first** (zero infra/cost, instant iteration); most teams fine-tune before trying a structured system prompt + few-shot, which is almost always a mistake.

### Decision table

| The gap is... | Use | Why |
|---|---|---|
| Output format, persona, reasoning style, prototyping | **Prompt engineering** | Zero cost, instant. Covers the majority of LLM adaptation. |
| Model lacks CURRENT facts (box scores, injuries, recent results) | **RAG** | Closes freshness at far lower cost than retraining; stays current by updating the index, not the weights. |
| Need consistent structured-output schema or domain behavior the base model handles poorly | **SFT (LoRA/QLoRA)** | Bakes BEHAVIOR/FORMAT into weights. LoRA = 90-95% of full FT quality, zero added inference latency after merge. |
| Tone/honesty alignment (prefer calibrated over confident outputs) | **DPO** | (prompt, chosen, rejected) triplets; no reward model; cheaper/more stable than PPO-RLHF. |
| Cheap high-volume inference of a frontier-quality policy | **Distillation** | Frontier teacher labels -> small student via QLoRA. +21-31% over prompting the student directly. |

**Core rule: fine-tuning bakes behavior/style, NOT knowledge.** Knowledge that changes in days (box scores, injuries, lines) is RAG's job -- fine-tuning it wastes compute and produces a stale model.

### Hardware reality (RTX 4060, 8GB)

- QLoRA for a 7B model needs ~12-16GB -> you can fine-tune up to ~3B params locally; rent a cloud A100 (~$0.40/hr Vast.ai) for 7B+. LoRA min is RTX 4090 24GB for 7B.
- LoRA rank: r=4-8 = regularized/less capacity; r=64-128 = near-full-FT/more memory. Tune to task.
- DPO can collapse if chosen/rejected pairs are too similar -- add a KL penalty (beta), monitor logprob ratios.

### What this project should and should NOT do

**Where RAG wins (do this):**
- Intel synthesis at query time -- the Obsidian vault IS the knowledge base; keep it a retrieval index (Section 2).
- Freshness injection -- a nightly ETL writes structured documents (injuries, lineups, recent results) to the index; the LLM conditions on fresh text without retraining.

**Where prompt engineering remains sufficient (do FIRST, always):**
- Intel narrative generation (structured system prompt + few-shot handles 90%+).
- Scheme-prior elicitation -- the existing `CV_LLM_SCHEME` pattern (bounded multipliers on existing sim knobs) is the right investment level.
- Agent orchestration, routing, planning, tool-use decisions.

**Where SFT/DPO MIGHT win later (only with data + validated need):**
- Calibration-aware output formatting: SFT a small model to always emit `{"prediction", "confidence_interval", "calibration_tier", "honest_caveats"}` instead of prose.
- DPO for honesty: (prompt, overconfident, calibrated) pairs -> bake the north star into weights so it does not need re-prompting every call.
- Forecasting policy: needs ~5,000-10,000 (game-context, accurate-probability) pairs graded vs devigged closes. The research-proven +7pt path (Mantic/Thinking Machines) -- but note +4 of those 7 points came from the retrieval/research PIPELINE, not the gradients. Infrastructure does most of the work.

**Where distillation might win:** if you call Opus for game summaries at scale (30 games/night), distill validated Opus outputs into a Phi-3-Mini/Llama-3.1-8B student for near-zero nightly cost. Prerequisite: validate the teacher's outputs against box scores/PBP first -- the student faithfully learns the teacher's mistakes (and cannot exceed the teacher's ceiling).

**Hard NO:**
- Do NOT fine-tune an LLM to produce win probabilities directly, replacing the GBM/Monte Carlo engine. The point-prediction task is tabular and data-rich -- GBMs strictly dominate; an LLM here would be slower, less interpretable, harder to validate for leakage, and worse in practice. LLMs are competitive only at <64 labeled examples.
- Do NOT fine-tune to inject frequently-changing knowledge (that is RAG).
- Do NOT distill from an unvalidated teacher.

---

## 5. Minimal recommended stack for a solo Claude-centric builder

The legitimate default is **"skip frameworks until the abstraction pays for its learning cost."** The existing Claude Code + plain Python + Pydantic validation + MCP stack already handles most agent patterns. Add pieces only against a real need.

### The stack, by tier

**Tier 0 -- already in place**
- **Claude Code** as the orchestration + build harness.
- **MCP** for tool wiring. Write tools once as MCP servers -> callable from Claude Code today and any framework tomorrow. This is the minimal wiring layer and it is already there. Invest in clean MCP tool definitions FIRST, framework choice second.

**Tier 1 -- use now (low cost, high leverage)**
- **Pydantic AI (v1.0)** or **Instructor + Pydantic** for ALL structured LLM calls (scheme priors, signal proposals, synthesizer). Strict typed outputs validated at dev time, `Usage Limits` to cap token spend, neutral fallbacks (e.g., `multiplier=1.0`) so the sim always gets a valid number. Replaces ad-hoc `json.loads(response.content)` -- garbage from an LLM call must never silently corrupt a Brier calculation. Pin Enums/Literals for scheme names and confidence tiers so a hallucinated value cannot leak into prediction inputs. (Instructor `max_retries=3` feeds the validation error back as a self-correction prompt; budget for the context cost of triple retries.)
- **promptfoo** for CI eval gating (Section 3).
- **Anthropic prompt caching** -- the single highest-ROI cost lever (Section 6).

**Tier 2 -- use IF you build persistent agent loops**
- **LangGraph** for durable, resumable loops -- e.g., an overnight walk-forward backtesting or signal-discovery agent. Checkpointer (SQLite/Postgres/Redis) lets a 6-hour run that crashes at hour 5 resume from checkpoint. Learning curve is real (~2-3 days). Gotcha: `MemorySaver` is RAM-only -- offload parquet/corpus slices to `data/cache/`, pass only keys through graph state.
- **DSPy (v3.2.1)** to optimize the most-used structured prompts (synthesizer, scheme prior, signal proposer) -- you already have eval data (walk-forward Brier/log-loss). MIPROv2 = 10-40% quality lift on structured tasks. Offline step (50-200 API calls/compile), not real-time. A better signal proposer means better candidates entering the gate, without touching the gate.

**Tier 3 -- only for the React live-board**
- **Vercel AI SDK** if you add AI-streamed commentary/predictions (`useChat` + `streamText`). NOT for the Python core. Note the hard 300s (Pro)/800s (Enterprise) timeout ceiling -- not for long-running agents.

**Skip entirely**
- **CrewAI** -- no built-in token limiter (uncapped loops hit $414/run; an Anthropic stop-sequence bug inflated cost 10x/call); black-box per-agent debugging. Antithetical to a calibration system where a silent 10x cost inflation is unacceptable.
- **AutoGen/AG2** -- maintenance mode; trails LangGraph on persistence/retries/background execution.
- **Mastra / Vercel AI SDK** for the core -- TypeScript-only / frontend-only.
- **LlamaIndex** as an orchestrator -- the vault is already built and accessed directly; if document retrieval becomes the primary challenge, it has the smoothest GraphRAG, but orchestration-first work goes to LangGraph.

### The decision rule for any new agent work

> One-shot structured call -> **Pydantic AI / Instructor**. Loop that must survive crashes -> **LangGraph**. Prompt with an eval metric that runs frequently -> **DSPy** to optimize it. Everything else -> plain Claude API call with Pydantic output validation.

---

## 6. Observability essentials

Frameworks give you token tracing, not prediction-quality tracing. Keep observability minimal and local-first; the binding invariant is no secrets / no external data push.

### Priority order (highest ROI first)

1. **Prompt caching (immediate, biggest cost lever).** Anthropic requires explicit `cache_control: {"type":"ephemeral"}` on the static system prompt + large stable context blocks. Documented 71-85% cost reduction past the first turn; subsequent calls pay ~10% of normal input cost (first call pays ~25% write premium).
   - **Cache is byte-exact, not semantic.** A single changed space busts it and charges the write premium. Treat the cached system prompt as a versioned artifact.
   - **NEVER put dynamic content** (game_id, timestamp, live score, per-request ID) inside the cached block -- put the user query in `messages[]`, not `system[]`.
   - **Ephemeral TTL = 5 min.** Long-interval cron batches go cold every run (you pay the write premium, get no savings) -- structure batch calls to run within the 5-minute window, or use extended caching where available. This is exactly the ingestion pattern that makes Contextual Retrieval ~69% cheaper (Section 2).
2. **Structured-output validation on every LLM call (immediate, reliability).** Instructor/Pydantic AI schema + field validators (`Field(ge=0, le=1)` for probabilities) + retry-with-error-feedback (max 3) + an explicit safe fallback (never silently return None). Distinguish **validation** (well-formed JSON matching schema) from **guardrails** (content allowed: no hallucinated player names, no out-of-range probabilities) -- wire both in sequence.
3. **Minimal cost CSV logging (immediate, no infra).** A `log_llm_call(model, purpose, input_tok, output_tok, cost)` wrapper around every call -> `data/llm_costs.csv` (gitignored). Tag by `purpose` (pregame / in-game / eval / CI) to find where spend concentrates. Review weekly.
4. **50-example golden eval set in CI (medium, highest long-term value).** See Section 3. Use a cheaper model (Haiku) for per-PR CI evals; reserve the full model for nightly regression. Labels are actual game outcomes, never model output, strictly OOS.
5. **Langfuse self-hosted (medium, when you want trace history).** MIT, hierarchical trace spans (`generation` inside `trace`, with retrieval/tool/sub-agent spans), prompt versioning, LLM-as-judge, dataset regression harness; traces async (zero latency). Session grouping links pregame -> in-game update -> final output -- invaluable for debugging a calibration regression by comparing exact prompts/outputs across runs. Note v3 self-host needs Postgres + ClickHouse + Redis (real RAM on a Windows box); the Cloud free tier is the easier start but check the no-external-data rule first.
   - Lighter dev-time alternative: **Arize Phoenix** (MIT, OpenTelemetry-native, local).
   - **Helicone** is the fastest cold start (proxy swap, zero SDK, cost+latency in <10 min) but acquisition (Mintlify, Mar 2026) makes its direction uncertain -- do not build hard dependencies on it.
6. **Semantic caching (lower priority, conditional).** Redis + embeddings, 60-85% hit rate / 96.9% latency reduction per hit -- only worth it if >30% of queries are semantically similar (e.g., a front-end polling pattern). Set cosine threshold >= 0.95 on prediction paths or two "similar" queries can return mismatched answers. Skip until query overlap actually appears.

### Prompt management

For a solo build, plain Git files (`prompts/game_summary.jinja2` with a version-comment header) are sufficient. Graduate to Langfuse's versioned prompt registry (named major/minor versions, A/B labels, runtime fetch, rollback) only when you are running enough variants that file diffs stop being legible.

### Cross-cutting reliability guard

Log every agent decision in a trace. Non-determinism compounds -- "minor prompt changes cascade into unpredictable behavioral changes." Never debug a multi-agent run from the final output alone; you need the span tree.

---

## 7. Action checklist

**Do now (this week, low cost, high leverage):**
- [ ] Add `cache_control: ephemeral` to the static system prompt + large stable context in `predict_matchup` and in-game paths. Verify no dynamic content (game_id/timestamp/score) sits inside cached blocks.
- [ ] Route every LLM call through Instructor/Pydantic AI with typed outputs, `Field(ge=0,le=1)` on probabilities, Enums/Literals on scheme names + confidence tiers, `max_retries=3`, and a neutral fallback (`multiplier=1.0`). Kill all bare `json.loads(response.content)`.
- [ ] Add a `log_llm_call(...)` wrapper -> `data/llm_costs.csv`, tagged by purpose. Review weekly.
- [ ] Build `tests/fixtures/golden_set.jsonl` (~100 game states; actual-outcome labels; strictly OOS). One afternoon.
- [ ] Stand up `promptfoo.yaml` as the CI gate: report Brier vs devigged close, BSS, ECE + sharpness, log-loss; fail the build (exit 1) if BSS < 0 on either corpus. Use Haiku for per-PR runs.

**Do next (this month):**
- [ ] Adopt the SEM/CI + clustered-SE + paired-difference + pre-specified-effect-size discipline on every eval result; cluster by `game_id`/season.
- [ ] Build the Contextual Retrieval index over `vault/_Organized/` in LanceDB (Haiku for context generation, prompt-cache parent docs); implement hybrid (`rank_bm25` + RRF 80/20) -> `bge-reranker-large` rerank.
- [ ] Add an adversarial-verification reviewer agent (cross-model) that runs on every calibration improvement claim: leak-free? real split? holds on corpus 2? self-normalized/cherry-picked?
- [ ] Add the `feature_availability_date` column + assert `< game_date` across the walk-forward eval window.
- [ ] Add a promptfoo nightly cron with a >1-sigma-from-30-day-mean drift alert.

**Do later (conditional on a real need):**
- [ ] Stand up an agentic-RAG router for in-game queries (SQL state + sim output + vault intel + optional web search) with an explicit evidence-grounding check.
- [ ] Add LangGraph + checkpointer ONLY when an overnight loop must survive crashes; offload data to `data/cache/`, pass keys through state.
- [ ] Run DSPy/MIPROv2 (offline) on the signal-proposer + synthesizer prompts against the eval corpus.
- [ ] Self-host Langfuse (or start on Cloud free tier) for trace history once debugging across runs becomes painful.
- [ ] Consider distillation (validated Opus teacher -> small student) only if nightly summary volume makes frontier inference cost real; consider DPO/SFT for honesty-formatting only if you accumulate 5-10k graded pairs.

**Never (binding):**
- [ ] Never let an LLM/agent produce the calibrated betting number -- GBM/Bayesian/Monte Carlo + walk-forward gate own it.
- [ ] Never fine-tune to inject fast-changing knowledge (that is RAG) or to replace the tabular point model (GBMs dominate).
- [ ] Never relax the two-corpus rule, vintage alignment, or BSS-vs-devigged-close reference -- and never treat an honest reject as a failure.
- [ ] Never use a flat "bag of agents," an uncapped agent loop, or CrewAI against a live pipeline.
- [ ] Never use LLM-as-judge to score numeric calibration; never publish "beat the market" / fabricated-$-edge language.

---

## Sources / References

**Agentic orchestration**
- [Building Effective Agents -- Anthropic](https://www.anthropic.com/research/building-effective-agents)
- [How we built our multi-agent research system -- Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Single-Agent vs Multi-Agent Under Equal Thinking Token Budgets (arXiv 2604.02460)](https://arxiv.org/html/2604.02460v1)
- [ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration (arXiv 2605.03042)](https://arxiv.org/html/2605.03042v1)
- [Why Your Multi-Agent System is Failing: the 17x Error Trap -- Towards Data Science](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/)
- [A-MapReduce: Wide Search via Agentic MapReduce (arXiv 2602.01331)](https://arxiv.org/pdf/2602.01331)
- [Failure Modes in Multi-Agent Debate (arXiv 2509.05396)](https://arxiv.org/pdf/2509.05396)
- [6 Multi-Agent Orchestration Patterns for Production (2026) -- beam.ai](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)

**RAG / retrieval**
- [Enhancing RAG with Contextual Retrieval -- Anthropic Claude Cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)
- [RAG Is Not Dead: Advanced Retrieval Patterns 2026 -- DEV Community](https://dev.to/young_gao/rag-is-not-dead-advanced-retrieval-patterns-that-actually-work-in-2026-2gbo)
- [Vector Database Comparison 2026 -- 4xxi](https://4xxi.com/articles/vector-database-comparison/)
- [Vector Database Benchmarks 2026 -- CallSphere](https://callsphere.ai/blog/vector-database-benchmarks-2026-pgvector-qdrant-weaviate-milvus-lancedb)
- [Project GraphRAG -- Microsoft Research](https://www.microsoft.com/en-us/research/project/graphrag/) / [microsoft/graphrag](https://github.com/microsoft/graphrag)
- [Hybrid Retrieval + Reranking for Evidence-Grounded RAG (arXiv 2605.01664)](https://arxiv.org/abs/2605.01664)
- [Optimizing RAG with Hybrid Search and Reranking -- Superlinked VectorHub](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking)
- [Agentic RAG Explained -- Machine Learning Mastery](https://machinelearningmastery.com/agentic-rag-explained-in-3-levels-of-difficulty/)
- [Survey on Reasoning Agentic RAG -- ACL/IJCNLP 2025](https://aclanthology.org/2025.findings-ijcnlp.122.pdf)
- [Graphiti: Knowledge Graph Memory -- Neo4j Blog](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)

**Evals / forecasting rigor**
- [A statistical approach to model evaluations -- Anthropic](https://www.anthropic.com/research/statistical-approach-to-model-evals)
- [Bloom: automated behavioral evaluations -- Anthropic](https://www.anthropic.com/research/bloom)
- [Inspect AI -- UK AISI (GitHub)](https://github.com/UKGovernmentBEIS/inspect_ai) / [docs](https://inspect.aisi.org.uk/)
- [Best AI Eval Tools for CI/CD 2026 -- Braintrust](https://www.braintrust.dev/articles/best-ai-evals-tools-cicd-2025)
- [Proper Scoring Rules for Estimation and Forecast Evaluation (arXiv 2504.01781)](https://arxiv.org/pdf/2504.01781)
- [Proper scoring rules for multivariate probabilistic forecasts -- ASCMO 2025](https://ascmo.copernicus.org/articles/11/23/2025/ascmo-11-23-2025.pdf)
- [LLMs-as-Judges: A Comprehensive Survey (arXiv 2412.05579)](https://arxiv.org/pdf/2412.05579)
- [LLM-as-a-Judge -- Langfuse docs](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)

**Fine-tune vs RAG**
- [Fine-Tuning Infrastructure: LoRA, QLoRA, PEFT at Scale -- Introl](https://introl.com/blog/fine-tuning-infrastructure-lora-qlora-peft-scale-guide-2025)
- [RAG vs Fine-Tuning vs Prompt Engineering -- k2view](https://www.k2view.com/blog/rag-vs-fine-tuning-vs-prompt-engineering/)
- [Prompting vs RAG vs Fine-Tuning: Not a Ladder -- The New Stack](https://thenewstack.io/prompting-vs-rag-vs-fine-tuning-why-its-not-a-ladder/)
- [Training LLMs to Predict World Events -- Mantic/Thinking Machines Lab](https://thinkingmachines.ai/news/training-llms-to-predict-world-events/)
- [BoostLLM: Boosting-Inspired LLM Fine-Tuning for Few-Shot Tabular (arXiv 2605.06117)](https://arxiv.org/html/2605.06117v2)
- [Distillation: Smaller Models into Cost-Effective Solutions -- Microsoft Azure AI Foundry](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/distillation-turning-smaller-models-into-high-performance-cost-effective-solutio/4355029)
- [LoRA vs QLoRA: Best Fine-Tuning Tools 2026 -- Index.dev](https://www.index.dev/blog/top-ai-fine-tuning-tools-lora-vs-qlora-vs-full)

**Agent frameworks**
- [Agent framework comparison: LangChain/LangGraph/CrewAI/PydanticAI/Mastra/Vercel -- Speakeasy](https://www.speakeasy.com/blog/ai-agent-framework-comparison)
- [AI Agent Frameworks 2026 Deep Dive -- youngju.dev](https://www.youngju.dev/blog/culture/2026-05-16-ai-agent-frameworks-langchain-langgraph-llamaindex-crewai-autogen-pydanticai-mastra-dspy-mcp-2026-deep-dive.en)
- [LangGraph vs CrewAI vs AutoGen 2026 (Or Skip Frameworks) -- DEV Community](https://dev.to/cristian_iridon_286794874/langgraph-vs-crewai-vs-autogen-in-2026-pick-the-right-ai-agent-framework-or-skip-frameworks-4m2c)
- [DSPy (stanfordnlp/dspy), v3.2.1](https://github.com/stanfordnlp/dspy)
- [LlamaIndex vs Pydantic AI 2026 -- xpay.sh](https://www.xpay.sh/resources/agentic-frameworks/compare/llamaindex-vs-pydantic-ai/)

**LLMOps / observability**
- [Langfuse Observability Docs](https://langfuse.com/docs/observability/overview) / [Self-Hosting](https://langfuse.com/self-hosting) / [GitHub](https://github.com/langfuse/langfuse)
- [Top 5 LLM Observability Platforms 2026 -- guptadeepak.com](https://guptadeepak.com/tools/top-5-llm-observability-platforms-2026/)
- [Best LLM Observability Tools 2026 -- firecrawl.dev](https://www.firecrawl.dev/blog/best-llm-observability-tools)
- [Prompt Caching Cost Optimization: 80% Savings -- web2md.org](https://web2md.org/blog/prompt-caching-cost-optimization-guide-2026)
- [AI Agent Guardrails and Output Validation 2026 -- toolhalla.ai](https://toolhalla.ai/blog/ai-agent-guardrails-io-validation-2026)
- [LLMOps Guide 2026 -- redis.io](https://redis.io/blog/large-language-model-operations-guide/)
