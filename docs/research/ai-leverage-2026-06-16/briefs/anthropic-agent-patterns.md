# Anthropic Agent Patterns for Sports-AI Build Velocity
_Researched 2026-06-16. Scope: Anthropic's "Building Effective Agents" patterns (prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, autonomous agents, Agent Skills) mapped to a solo-built calibrated multi-sport predictor._

---

## TL;DR

- Anthropic distinguishes **workflows** (pre-defined code paths) from **agents** (LLM-directed paths); start with the simplest structure that works, add autonomy only when the decision tree cannot be pre-mapped.
- The five core patterns are: Prompt Chaining, Routing, Parallelization (Sectioning + Voting), Orchestrator-Workers, and Evaluator-Optimizer; layered into Autonomous Agents for open-ended tasks.
- In Anthropic's internal multi-agent research system, multi-agent Opus 4 + Sonnet 4 subagents outperformed single-agent Opus 4 by **90.2%** on complex queries; token usage explains ~80% of output quality variance.
- **Tool documentation quality is a first-order lever**: poor tool descriptions sent agents "down completely wrong paths"; improving them reduced task-completion time by 40%.
- **Agent Skills** (directory + SKILL.md + progressive disclosure) solve the context-window problem for domain-specific knowledge -- load metadata at startup, full spec only when relevant.
- For a solo build, the highest-leverage patterns are: Evaluator-Optimizer for model tuning/calibration loops, Orchestrator-Workers for parallel data ingestion, and Routing for model-tier cost control.
- Never use autonomous agents for high-stakes irreversible actions; always build in stopping conditions, read-only sandboxing, and human gates for destructive operations.

---

## Key Capabilities / Techniques

### 1. Prompt Chaining
- **What**: Sequential LLM calls where each output feeds the next; task decomposed into fixed subtasks.
- **When**: Task cleanly splits into ordered stages; predictable path; trade latency for higher per-step accuracy.
- **Canonical example**: raw game log -> structured event extraction -> signal computation -> narrative summary.
- **Key principle**: "Give the model enough tokens to think before it writes itself into a corner." Each call should be an easier, bounded task.

### 2. Routing
- **What**: Classify input, direct to specialized handler (different prompt, different model tier, different code path).
- **When**: Inputs fall into distinct categories better handled separately; misclassification is recoverable.
- **Canonical example**: simple prop line lookup -> Claude Haiku; full in-game re-pricing with calibration -> Claude Sonnet/Opus.
- **Key principle**: Prevents optimizing for one input type from hurting others; enables cost-proportional routing.

### 3. Parallelization
Two variants:
- **Sectioning**: Independent subtasks run concurrently (e.g., fetch NBA + MLB + soccer data simultaneously).
- **Voting**: Same task run N times, results aggregated for higher-confidence output (e.g., three independent signal screeners vote on a candidate edge).
- **When**: Subtasks are independent; speed matters; or confidence requires ensemble agreement.
- **Key finding**: "LLMs generally perform better when each consideration is handled by a separate LLM call."

### 4. Orchestrator-Workers
- **What**: Central LLM (orchestrator) dynamically decomposes the task, assigns to worker LLMs, synthesizes results. Subtasks NOT pre-defined -- determined from input.
- **When**: Complex tasks where the full solution path cannot be predicted upfront; "topographically similar" to parallelization but flexible.
- **Anthropic's internal result**: Lead Opus 4 orchestrator + parallel Sonnet 4 subagents (3-5 at a time, 3+ tools in parallel) cut research time by up to 90%.
- **Gotcha**: Spawning 50+ subagents on simple queries was an early failure; embed explicit scaling rules in the orchestrator prompt ("simple queries: 1 agent, complex: 10+ subagents").

### 5. Evaluator-Optimizer
- **What**: Generator LLM produces output; Evaluator LLM critiques with specific rubric; loop iterates until criteria met.
- **When**: Clear, verifiable evaluation criteria exist; LLM output demonstrably improves with feedback; analogous to iterative writing or code review.
- **Canonical example**: calibration pipeline that generates a recalibration patch, evaluates Brier improvement on held-out fold, loops until improvement < threshold.
- **Key principle**: Evaluation criteria must be explicit and unambiguous, not "make it better."

### 6. Autonomous Agents
- **What**: LLM plans and operates independently, observes environment, chooses tool sequence, loops.
- **When**: Open-ended; steps cannot be predicted; requires trust in LLM judgment.
- **Cost**: "Higher costs and potential for compounding errors." Only justified when task value >> token cost.
- **Required guardrails**: Maximum iteration budget; stopping conditions; read-only access where possible; human gate before destructive actions.

### 7. Agent Skills (Progressive Disclosure)
- **What**: Organized directory (SKILL.md + bundled files) loaded on demand. Three-tier hierarchy: (1) metadata in system prompt always; (2) full SKILL.md read when task matches; (3) sub-files accessed only as needed.
- **When**: Agent needs deep domain knowledge that would bloat the base context; multiple agents share the same specialized capability.
- **Key design**: Keeps context window bounded even with extensive docs. Skills can bundle pre-written scripts that run deterministically, avoiding re-generation.

---

## How THIS Project Should Use It

### Prompt Chaining -> data-to-prediction funnel
Each stage of the pipeline is already a natural chain link: raw API fetch -> event parsing -> signal computation -> model inference -> calibration -> prediction output. Make each stage an explicit, bounded LLM (or code) call. Do NOT merge all reasoning into one megaprompt. The current pipeline already does this structurally; ensure each agent step has a clear schema contract at its boundary.

### Routing -> model-tier cost control
Route agent tasks by complexity:
- Simple lookups, formatting, label generation -> Claude Haiku (fast + cheap).
- Signal screening, data validation, feature QA -> Claude Sonnet.
- Calibration audits, evaluator passes, architecture decisions -> Claude Opus.
This alone can cut per-wave token cost by 3-5x without sacrificing quality on hard steps.

### Parallelization (Sectioning) -> parallel sport ingestion
The four sports (NBA/MLB/Soccer/Tennis) have fully independent data pipelines. Run them as parallel subagents in each wave. Current sequential execution is the bottleneck; sectioning gives near-linear speedup with no accuracy tradeoff.

### Parallelization (Voting) -> signal screening confidence
For borderline signals that the gate almost passes/rejects, run N=3 independent screener agents with different random seeds or prompt variants; require 2/3 agreement before gating ON. Reduces single-seed artifact risk (already a known failure mode: "single-fold lifts are artifacts").

### Orchestrator-Workers -> per-game intelligence build
When building pre-game intelligence for a matchup: Orchestrator receives the game spec, spawns workers for (a) injury/lineup scrape, (b) recent form signal refresh, (c) head-to-head retrieval, (d) market line fetch, (e) in-game state if live. Workers run in parallel; orchestrator synthesizes. This cuts the serial intelligence-build time that currently blocks prediction latency.

### Evaluator-Optimizer -> calibration loop automation
The most direct win: wrap the current manual recalibration cycle as an Evaluator-Optimizer loop.
- Generator: proposes a recalibration patch (isotonic knots, Platt parameters, shrinkage weights).
- Evaluator: scores Brier + reliability diagram slope on the held-out OOS fold; rejects if Brier worsens.
- Loop: max N=5 iterations; accept best; log all intermediate states.
This is already the conceptual workflow; the pattern formalizes it and makes it autonomous.

### Autonomous Agents -> bounded improvement proposals only
Use autonomous agents ONLY for open-ended research/proposal tasks (e.g., "find new publicly available features for NBA team strength"), NOT for any step that writes to the model store, commits code, or modifies calibration state. Those remain human-gated. This matches the existing invariant ("src/kernel/api/scripts human-gated").

### Agent Skills -> sport-domain knowledge loading
Package each sport's domain knowledge as a Skill:
- `skills/nba/SKILL.md` -- rules, data sources, signal catalog, known failure modes.
- `skills/mlb/SKILL.md` -- pitcher hand, park factors, Poisson model context.
- `skills/soccer/SKILL.md` -- O/U model, xG sources, competition tiers.
- `skills/tennis/SKILL.md` -- Elo model, surface adjustments, ATP/WTA quirks.
Agents load only the relevant skill per task, keeping per-call context lean and reusable across waves.

### Tool documentation -> first-order investment
Based on Anthropic's finding that poor tool docs caused 40% slower completion: audit every tool definition used by wave agents. Add usage examples, edge cases, expected output formats. This is the highest-ROI documentation investment for build velocity.

---

## Gotchas / Limits

- **Do NOT use autonomous agents for irreversible actions.** Stopping conditions and human gates are mandatory, not optional. The project's existing invariant (no auto-push, human-gated src/) already enforces this -- preserve it.
- **Frameworks obscure prompts.** LangChain/CrewAI and similar frameworks "can obscure the underlying prompts, making them harder to debug." Prefer direct API calls with a thin orchestration layer for this project; Claude Code as the harness already provides this.
- **Token cost scales fast.** Anthropic's multi-agent system uses ~15x more tokens than single-turn chat. Budget per wave carefully; Opus for the orchestrator only, Sonnet/Haiku for workers.
- **Subagent count must scale with task complexity.** Hardcode scaling rules into the orchestrator prompt; "spawn as many as needed" leads to 50+ agents on trivial queries.
- **Concurrent brain rebuilds corrupt the vault.** Already a known failure (WinError 32 / rmtree collision). Evaluator-Optimizer and Orchestrator-Workers must serialize any step that writes to vault/_Organized.
- **Voting/ensemble is not free from leakage.** Three agents independently screening the same signal against the same training corpus do NOT provide independent corpora -- they provide variance estimates, not leak-free replication. Still require >=2 separate time-period corpora for any honest edge claim.
- **LLM-as-judge has source-selection bias.** Anthropic found early agents "consistently chose SEO-optimized content farms over authoritative sources." Explicitly instruct evaluator agents to prefer primary sources (official stats APIs, academic papers) over aggregators.
- **Calibration accuracy != prediction edge.** These patterns accelerate the build and improve calibration quality; they do NOT create a pricing edge against efficient markets. The Evaluator-Optimizer loop should target Brier/log-loss on OOS data, never ROI on in-sample bets.

---

## Sources

- [Building Effective AI Agents - Anthropic Research](https://www.anthropic.com/research/building-effective-agents) -- the primary reference; Erik Schluntz and Barry Zhang; December 2024.
- [How We Built Our Multi-Agent Research System - Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system) -- internal system post with concrete performance numbers (90.2% gain, 80% variance explained by tokens, 40% tool-doc speedup).
- [Equipping Agents for the Real World with Agent Skills - Anthropic Engineering](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) -- progressive disclosure architecture for domain-specific skill loading.
- [Anthropic Cookbook: patterns/agents - GitHub](https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents) -- reference notebooks: basic_workflows.ipynb, evaluator_optimizer.ipynb, orchestrator_workers.ipynb, async_multi_agent_orchestration.ipynb.
- [Building Effective Agents: Practical Framework - ZenML LLMOps Database](https://www.zenml.io/llmops-database/building-effective-agents-practical-framework-and-design-principles) -- secondary summary with additional implementation framing.
