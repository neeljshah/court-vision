# Multi-Agent Orchestration Patterns in Practice
_Researched 2026-06-16. Scope: production orchestration patterns, parallelism, adversarial verification, failure modes, and when multi-agent beats single-agent -- applied to a solo-built calibrated sports prediction platform._

---

## TL;DR (highest-leverage takeaways)

- **Orchestrator-worker with mixed model tiers** is the proven production pattern: a capable lead model (Opus-class) decomposes tasks and coordinates, cheap fast workers (Sonnet-class) execute in parallel. Anthropic's own research system showed a 90.2% performance gain over single-agent Opus when using this split.
- **Multi-agent is NOT free**: token usage is ~4x chat for single-agent agentic, ~15x chat for multi-agent. Token budget explains 80% of performance variance. Always account for this cost before adding agents.
- **Single-agent wins on normalized compute for reasoning**: a 2026 study (arxiv 2604.02460) showed single-agent LLMs match or beat multi-agent on multi-hop reasoning when token budgets are equalized. Multi-agent earns its keep on tasks that are genuinely parallel or exceed a single context window -- NOT on tasks that are fundamentally sequential.
- **The 45% threshold heuristic**: multi-agent coordination adds real value when baseline single-agent accuracy on the subtask is below ~45%. Above that, extra agents add noise, not signal. This is directly applicable to modeling experiments.
- **Adversarial verification (executor + cross-model reviewer) catches integrity failures** single agents miss: unsupported claims, data leakage, self-normalized scores, cherry-picking. Use a reviewer from a DIFFERENT model family. ARIS demonstrated an internal score lift from 5.0 to 7.5/10 across four reviewer cycles overnight.
- **The "bag of agents" anti-pattern kills reliability**: flat topology with no hierarchy produces up to 17.2x error amplification vs ~4.4x in centralized systems (DeepMind). Always use a hierarchy with a verification/assurance layer.
- **Failure mode #1 is hallucination cascade**: one agent hallucinates; downstream agents treat it as ground truth and elaborate on it. Break the cascade with independent inputs and explicit fact-check stages, not just chain-of-thought.

---

## Key capabilities / techniques (concrete: names, what they do, when to use)

### 1. Orchestrator-Worker
- Lead agent receives the full task, dynamically decomposes into subtasks, dispatches workers, synthesizes.
- Best for: tasks where the subtask list cannot be predicted in advance (e.g., open-ended research, multi-file code changes).
- Key: workers get clean contexts and explicit output formats. Vague task descriptions cause duplicate work.
- Gotcha: the orchestrator must explicitly scope each worker's assignment. "Divide research on NBA in-game calibration" is too vague; "search for walk-forward Brier calibration papers from 2023-2026 and return 5 URLs with one-sentence summaries" is right.

### 2. Parallel Fan-Out / Map-Reduce
- Dispatch N independent workers simultaneously for the same or partitioned problem; collect and reduce results.
- A-MapReduce (arxiv 2602.01331) formalizes this: a mapper agent splits the problem, workers process shards independently, a reducer agent synthesizes.
- Best for: parallel literature sweeps, running the same modeling experiment with different hyperparameters or corpora, parallel feature engineering across sports.
- Anthropic's research system runs 3-5 subagents simultaneously + 3+ parallel tool calls per subagent, cutting research time by up to 90%.
- Gotcha: workers must truly be independent. Shared mutable state (same parquet file, same DB row) causes corruption; pre-assign non-overlapping ranges to each worker.

### 3. Reflection / Evaluator-Optimizer Loop
- Generator agent produces an artifact; evaluator agent scores it against an explicit rubric; generator revises; loop until score threshold or max iterations.
- Best for: tasks with clear, checkable criteria -- translation quality, code correctness, calibration report completeness.
- Implementation: cap at 3-5 rounds. Diminishing returns set in fast. Use a DIFFERENT model (or same model with a separate system prompt) as evaluator to reduce echo-chamber risk.
- Anthropic explicitly calls out "clear evaluation criteria that can be checked programmatically or by an LLM" as the required precondition.

### 4. Debate / Ensemble (Adversarial Verification)
- Multiple agents independently produce answers or critiques; a synthesis agent (or vote) resolves disagreements.
- ARIS pattern: executor drives forward; reviewer from a different model family critiques under a structured rubric; executor addresses action items; 4 rounds max.
- Three-stage audit cascade for research integrity: (1) experiment-integrity audit, (2) result-to-claim mapping, (3) fresh zero-context reviewer cross-checks numbers against raw evidence.
- Real failure mode: "tyranny of the majority" -- if most agents agree, minority agents conform (sycophancy). Fix: keep agents independent (no cross-talk) until a separate synthesis step.
- Real failure mode: RLHF-trained models converge on plausible-sounding consensus regardless of facts. Fix: use structured rubrics with explicit disconfirmation criteria, not free-form consensus.

### 5. Planner-Executor (with Extended Thinking)
- Planner agent (with extended thinking / scratchpad) reasons about strategy, produces a structured plan; executor agent carries it out step by step.
- Anthropic recommends making the plan explicit and transparent (surfaced to user/orchestrator) before execution begins.
- Best for: long-horizon tasks (>20 steps) where the plan itself needs to be auditable.
- Gotcha: plan-then-execute breaks down when the environment is dynamic (live game state changes mid-execution). Use a replanning trigger: executor signals the orchestrator when an unexpected state is hit.

### 6. Tool-Use Loop (ReAct / ACI pattern)
- Single agent in a loop: call tool -> observe result -> decide next action. Backbone of Claude Code and most production agents.
- Anthropic's Agent-Computer Interface (ACI) guidance: tool design is as important as model choice. Tools should use absolute paths not relative, avoid diff-counting or quote-escaping overhead, use formats naturally occurring in internet text, include usage examples and edge cases.
- Programmatic Tool Calling (Anthropic 2025): Claude can invoke tools in a code execution environment, reducing context window pressure vs. returning large blobs.
- Stop condition: always set max_iterations or a human checkpoint to prevent infinite loops chasing nonexistent results.

### 7. Routing
- A classifier agent (or rules) inspects the input and dispatches to a specialized subpipeline.
- Best for: cost optimization (route simple queries to cheap models), specialization (NBA vs. soccer vs. tennis pipelines), safety gating.
- Easy win: route "quick stat lookup" vs. "full calibration audit" to different agent tiers.

### 8. Hierarchical Delegation
- Orchestrator -> sub-orchestrators -> workers, in a tree. Each layer has bounded scope.
- The six-plane functional architecture (Control, Planning, Context, Execution, Assurance, Mediation) is a formalization of this.
- Assurance plane = closed-loop: evaluators feed corrections back to the Planner, making the system self-correcting rather than fire-and-forget.

---

## How THIS project should use it (specific, actionable recommendations)

### A. Parallel Modeling Experiments (the #1 win for solo builders)
- Run cross-sport or cross-hyperparameter experiments in parallel fan-out: one agent per sport (NBA, MLB, soccer, tennis) each independently trains and evaluates the same signal candidate, returns Brier/log-loss on OOS data. Reducer agent synthesizes: "signal X helps NBA and MLB, hurts tennis."
- Pre-assign file paths so workers never collide. This project already has the pattern (feedback_sonnet_concurrent_write_collisions.md: pre-assign ranges/files to parallel agents).
- Cap worker count at 4-5 for local GPU (RTX 4060 bottleneck). Parallelism without GPU contention = the sweet spot.

### B. Adversarial Verification of Calibration Claims
- Whenever a new model or signal candidate shows improvement (lower Brier, better calibration curve), invoke an adversarial reviewer agent with a cross-model check: "verify this result is leak-free (no future data), check the walk-forward split is real, confirm the improvement holds on corpus 2, flag any self-normalized scores or cherry-picked game windows."
- Use the three-stage ARIS audit cascade logic even if informal: (1) data-integrity check, (2) result-to-claim mapping (does the number in the code match the claim?), (3) fresh-context reviewer reading only raw outputs.
- This directly operationalizes the project's core invariant: honest rejects are successes. The adversarial agent's job is to find the reject.

### C. Parallel Research Sweeps
- For literature or API exploration (e.g., "find all publicly available in-game NBA data sources updated in real time"), dispatch 3-5 subagents with explicit scopes (official NBA APIs, third-party providers, academic datasets, sports-reference scraping, odds feeds). Each returns structured results. Orchestrator deduplicates and ranks by freshness + reliability.
- This matches the Anthropic research system's demonstrated 90% time reduction. For a solo builder, this is the clearest lever.

### D. Reflection Loop for Report and Prediction Validation
- When generating a pre-game prediction brief (the LLM scheme-prior layer + intelligence synthesis), run an evaluator-optimizer pass: generator emits the brief; evaluator checks against explicit rubric (claims backed by vault data? calibration tier honest? no edge language?); generator revises. Cap at 2 rounds for speed.
- Rubric items for this project: (1) all probability claims cite a Brier score, (2) no "beat the market" language, (3) in-game conditioning is flagged as the measured improvement, (4) sources are vault nodes not hallucinated.

### E. Tool-Use Loop for Data Freshness Harvesting
- A continuous tool-use loop agent can poll live NBA endpoints (cdn.nba.com liveData, which is already the project's source) on game nights, enrich the vault, and trigger in-game re-projection. Stop condition: game ends (final clock = 0:00).
- ACI guidance: make the endpoint tool return structured JSON with absolute game_id and period keys, not relative offsets. This matches the project's existing frustration with bash cwd flakiness -- the same principle applies to tool design.

### F. Planner-Executor for Multi-Sport Signal Campaigns
- For "run the full signal-catalog check across all 4 sports" campaigns, a planner agent with extended thinking generates the ordered work plan (respecting GPU contention, file non-collision, corpus dependencies) and writes it to a PLAN.md. Executor agents work the plan. Orchestrator monitors and replans on failure.
- Avoids the "no concurrent brain rebuilds" failure mode already documented (feedback-no-concurrent-brain-rebuilds.md) by putting serialization constraints in the plan explicitly.

---

## Gotchas / limits

- **Hallucination cascade is the #1 risk**: one bad intermediate output corrupts all downstream agents. Mitigation: ground truth tool calls (not just agent-to-agent messages) at each stage; adversarial reviewer with explicit disconfirmation rubric.
- **Token economics dominate**: multi-agent uses ~15x tokens of chat. For a budget-conscious local setup, fan-out of 4-5 agents is the practical ceiling before costs or rate limits bite.
- **Non-determinism compounds**: "minor prompt changes cascade into unpredictable behavioral changes" (Anthropic multi-agent research). Log every agent decision in a trace; never debug from final output alone.
- **Context handoff is fragile**: when an agent exhausts its context window, memory handoff to a fresh subagent loses information. Anthropic's fix: persist research plans to external memory BEFORE context is exhausted. For this project: write intermediate state to vault or a scratch JSON file, not just in-context.
- **Debate / ensemble does NOT reliably beat single-agent on reasoning tasks** (arxiv 2604.02460). The gain comes from parallelism and breadth, not the debate mechanism itself. Sycophantic convergence actively undermines it. Use ensemble only for tasks that are genuinely parallelizable, not for tasks that require tight sequential reasoning chains.
- **40% of multi-agent pilots fail within 6 months** (Gartner 2025 survey). Primary causes: over-engineering, unclear task decomposition, no assurance layer. The simplest agent architecture that works is the right one.
- **Single-agent with extended thinking often wins** on focused, bounded reasoning tasks (model calibration audit, signal gating). Reserve multi-agent for tasks that genuinely cannot fit in one context or need true parallelism.
- **Asynchronous multi-agent is harder than it looks**: Anthropic's own research system uses synchronous execution for subagents because async adds complexity in result coordination, state consistency, and error propagation. Start synchronous.
- **Workers must have clean contexts**: passing the full conversation history to every worker is expensive and introduces anchor bias. Workers should get only the scoped task and necessary tools.

---

## Sources

- [Building Effective Agents -- Anthropic](https://www.anthropic.com/research/building-effective-agents)
- [How we built our multi-agent research system -- Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets (arxiv 2604.02460)](https://arxiv.org/html/2604.02460v1)
- [ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration (arxiv 2605.03042)](https://arxiv.org/html/2605.03042v1)
- [Why Your Multi-Agent System is Failing: Escaping the 17x Error Trap -- Towards Data Science](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/)
- [A-MapReduce: Executing Wide Search via Agentic MapReduce (arxiv 2602.01331)](https://arxiv.org/pdf/2602.01331)
- [Talk Isn't Always Cheap: Understanding Failure Modes in Multi-Agent Debate (arxiv 2509.05396)](https://arxiv.org/pdf/2509.05396)
- [6 Multi-Agent Orchestration Patterns for Production (2026) -- beam.ai](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
