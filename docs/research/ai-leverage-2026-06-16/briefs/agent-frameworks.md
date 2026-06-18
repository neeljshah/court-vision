# Agent/LLM Framework Landscape 2026
_Researched 2026-06-16. Scope: LangGraph, CrewAI, AutoGen/AG2, DSPy, Pydantic AI, Mastra, LlamaIndex, Vercel AI SDK -- strengths, fit, and minimal-stack recommendation for a solo Claude-Code-centric Python sports-prediction builder._

## TL;DR (7 bullets)

- **For a solo Python builder already running Claude Code, the minimal viable stack is: Pydantic AI (structured agent calls) + LangGraph (if you need stateful loops) + DSPy (prompt optimization) + MCP for tool wiring.** You almost certainly do NOT need CrewAI, Mastra, or the Vercel AI SDK.
- **Pydantic AI v1.0** (stable since Sep 2025) is the highest-leverage addition for a calibrated prediction pipeline: strict type-safety on LLM outputs, `Usage Limits` to cap token spend, FastAPI-style ergonomics, and Logfire observability built in. It caught 23 production bugs in a 90-day enterprise benchmark; scored 8/10 developer experience vs LangChain 5/10.
- **LangGraph** is the right choice if you need durable, resumable agent loops (e.g., a walk-forward backtesting agent that runs overnight). Its checkpointer pattern (SQLite/Postgres/Redis) lets state survive crashes. Steep learning curve is real but pays off for complex cyclic workflows.
- **DSPy v3.2.1** (May 2026) is genuinely useful for optimizing structured prediction prompts -- classifiers, extraction, calibration assessors -- where you have evaluation data. MIPROv2 delivers 10-40% quality lift over hand-written prompts on structured tasks. Skip it for one-shot creative or real-time inference.
- **CrewAI** has documented production risks for solo devs: uncapped loops reached $414 in a single run; an Anthropic stop-sequence bug inflated costs 10x per call. Black-box abstractions make per-agent unit testing hard. Only use it if you want role-based agent delegation and can afford to babysit cost guardrails.
- **Mastra and Vercel AI SDK** are TypeScript/Next.js tools. Zero applicability to a Python modeling core; useful only if you build a React live-board with an agent-backed API and want streaming hooks.
- **AutoGen/AG2** is in maintenance mode (Microsoft shifted active development to a broader framework). Good for research/exploration, but trails LangGraph on persistence, retry policies, and background execution; not recommended for production prediction pipelines.

---

## Key Capabilities / Techniques

### LangGraph
- Graph-based state machine: nodes = Python functions, edges = conditional routing
- `TypedDict` state + checkpointer (SQLite / Postgres / Redis) persists every node transition
- Time-travel debugging: replay from any prior checkpoint
- Human-in-the-loop: pause graph at any node, resume after external approval
- Powers production agents at Klarna, Uber, LinkedIn (2026 adoption)
- Gotcha: `MemorySaver` is RAM-only; large state objects bloat checkpoints -- offload files to external storage
- Not serverless-compatible (Vercel/Cloudflare Workers timeout ceilings apply)

### CrewAI
- Four primitives: Agent, Task, Crew, Process
- Role, goal, and autonomous delegation as first-class objects
- 60% Fortune 500 adoption claimed, 44K+ GitHub stars
- Learning curve: easiest of the three (CrewAI > AutoGen > LangGraph)
- **Critical risk:** No built-in token budget limiter. Set `max_iters` before ANY deployment. Verify actual billing vs internal reporting (they diverge).
- Debugging individual agents is a documented gap; hierachical crews hit delegation reliability at scale

### AutoGen / AG2
- Conversation-based: GroupChat and RoundRobinGroupChat manage turn-taking
- Visual assembly via AutoGen Studio
- Microsoft shifted active investment to broader Microsoft Agent Framework -> AG2 is maintenance mode
- Thread persistence, background execution, and retry policies trail LangGraph significantly
- Best use: academic multi-agent conversation research, not production

### DSPy (Stanford NLP -- v3.2.1, May 2026)
- Declarative signatures (input -> output specs) replace hand-written prompt templates
- Modules compose into pipelines; compiler optimizes prompts against your eval data
- MIPROv2: Bayesian optimization over instructions + few-shot exemplars = 10-40% quality lift on structured tasks
- BootstrapFewShot: better for sparse label regimes
- Best for: QA, classification, extraction, multi-hop reasoning WITH evaluation data
- Skip for: one-shot creative tasks, real-time inference, anything without a metric
- Install: `pip install dspy` -- docs at dspy.ai

### Pydantic AI (v1.0, Sep 2025 -- production-stable)
- FastAPI-style ergonomics: `@agent.tool` decorator auto-derives JSON Schema
- Full type safety: LLM outputs validated against Pydantic models; bugs caught at dev time
- Configurable `Usage Limits` bake token caps into agent config (critical for cost control)
- Dependency injection via RunContext
- Logfire integration is first-class for observability
- Stateless by default -- durable execution needs Temporal, DBOS, or Prefect integration
- Ecosystem ~15x smaller than LangChain; third-party integrations thin but growing fast
- MIT licensed; serverless-compatible

### Mastra (YC W25 -- TypeScript only)
- 21,100+ GitHub stars; 300,000+ weekly npm downloads
- TypeScript-first; built on Vercel AI SDK
- Four-layer memory: message history, working memory, semantic recall, observational (auto-compresses 5-40x at 30K tokens)
- Serverless-first (Vercel, Cloudflare Workers, Netlify)
- Production adoption: Replit, PayPal, Sanity, Brex
- Hidden cost: observational memory runs background LLM compression calls (Gemini 2.5 Flash by default) -- these do NOT appear in agent token usage
- **Python teams: irrelevant. TypeScript/Next.js only.**

### LlamaIndex
- RAG-first: 70+ document loaders, GraphRAG, multi-query routing
- Event-driven Workflow abstraction (similar to LangGraph nodes)
- Smoothest GraphRAG implementation per 2026 reviewer consensus
- Right choice when document ingestion and retrieval ARE the primary challenge, orchestration is secondary
- If agent orchestration dominates, LangGraph is better

### Vercel AI SDK (v6, 2026)
- 22,200+ GitHub stars; 20M+ monthly npm downloads
- `useChat` / `useCompletion` hooks stream state across 25+ LLM providers
- AI SDK 6: added `Agent` interface and `DurableAgent` for resumable workflows; full MCP support; DevTools panel
- Best for: streaming React/Next.js UIs; rapid frontend prototyping
- Hard limits: 300 sec (Pro) / 800 sec (Enterprise) timeouts -- non-negotiable constraint for long-running agents
- No automatic token counting, summarization, or persistence layer
- **Python modeling core: irrelevant. Use only if building the React live-board with AI-streamed responses.**

### MCP (Model Context Protocol -- cross-framework standard, 2026)
- LangChain, LlamaIndex, OpenAI Agents, Vercel AI SDK, and Mastra all added first-class MCP client support
- Decouples tools from frameworks -- write a tool once, use it in any framework
- **This project already uses MCP via Claude Code; this IS the minimal wiring layer and it is already there**

---

## How THIS Project Should Use It

This is a solo-built, Python-centric, calibrated sports prediction system. The recommendation is deliberately minimal:

**Tier 1 -- Use now (low cost, high leverage):**
1. **Pydantic AI for structured LLM calls in the prediction pipeline.** Any place the system calls Claude for structured output (scheme priors, signal proposals, LLM synthesizer calls) should route through a Pydantic AI agent with strict output types and `Usage Limits`. This replaces ad-hoc `json.loads(response.content)` patterns and catches malformed outputs at dev time. The type safety alone is worth the integration cost for a calibration-focused system where garbage-in from an LLM call corrupts a Brier score calculation.
2. **DSPy for prompt optimization of the most-used structured prompts.** The LLM synthesizer (`market_intelligence.py`), scheme prior (`scheme_prior.py`), and signal proposer are all structured tasks with evaluation data (you have ground truth: walk-forward Brier/log-loss). Run MIPROv2 on these prompts against your eval corpus. A 10-20% quality lift on the signal proposer means better candidates entering the gate. This does NOT require changing the gate itself -- only the upstream proposal quality.
3. **MCP for tool wiring.** Already in place via Claude Code. No additional framework needed here.

**Tier 2 -- Use if/when you build persistent agent loops:**
4. **LangGraph if you build an overnight research agent or autonomous signal discovery loop.** The existing `scripts/loop/run_discovery.py` pattern would benefit from LangGraph's checkpointer: a 6-hour walk-forward backtesting agent that crashes at hour 5 can resume from checkpoint rather than restart. The learning curve is real (plan 2-3 days) but justified once the loop runs unattended.

**Tier 3 -- Use only for the React live-board (if you add AI streaming):**
5. **Vercel AI SDK** if you add AI-powered streaming commentary or live predictions to the React board. Do NOT use it for the Python modeling core. The `useChat` hook + `streamText` from the board's API route is the right pattern for live game overlays with minimal boilerplate.

**Skip entirely:**
- CrewAI: cost risks + black-box debugging are antithetical to the honest-reject discipline. A calibration system where an agent loop can silently inflate costs 10x is unacceptable.
- AutoGen/AG2: maintenance mode; no production persistence.
- Mastra: TypeScript only.
- LlamaIndex: the system is not document-retrieval-centric; the Obsidian vault is already built and accessed directly.

**Decision rule for new agent work:** If the task is a one-shot structured call -> Pydantic AI. If it needs a loop that must survive crashes -> LangGraph. If the prompt has an eval metric and runs frequently -> DSPy to optimize it. Everything else -> plain Claude API call with Pydantic output validation.

---

## Gotchas / Limits

- **CrewAI token cost bug is real and undocumented in most tutorials.** The Anthropic stop-sequence bug inflated costs 10x per call in documented cases. Never deploy CrewAI against a live prediction pipeline without explicit `max_iters` and external billing checks.
- **LangGraph checkpoint bloat.** `MemorySaver` is RAM-only and bloats with large state. Offload corpus slices and parquet frames to the existing `data/cache/` layer; pass only keys through graph state.
- **DSPy compilation overhead.** MIPROv2 runs many LLM calls during optimization -- treat it as an offline step, not real-time. Budget 50-200 API calls per compilation run on typical structured tasks.
- **Pydantic AI is stateless by default.** For walk-forward backtesting agents that need to persist iteration state, pair with LangGraph or a simple SQLite checkpoint; do not expect Pydantic AI to manage durable state.
- **MCP tool decoupling is 2026's real unlock.** Writing tools as MCP servers means you can call them from Claude Code today and from a LangGraph agent tomorrow without rewriting. Invest in clean MCP tool definitions first, framework choice second.
- **AutoGen/AG2 is not dead but not growing.** Papers and research use it; do not build production prediction infrastructure on a framework in maintenance mode.
- **The "skip frameworks entirely" argument is legitimate for this project.** The existing Claude Code + plain Python + Pydantic validation + MCP stack already handles most agent patterns. Add a framework only when the abstraction pays for its learning cost.
- **Observability gap.** None of these frameworks include sports-domain eval metrics out of the box. For calibration (Brier/log-loss), you still own the walk-forward harness. Frameworks give you token tracing, not prediction quality tracing.

---

## Sources

- [Choosing an agent framework: LangChain vs LangGraph vs CrewAI vs PydanticAI vs Mastra vs Vercel AI SDK -- Speakeasy](https://www.speakeasy.com/blog/ai-agent-framework-comparison)
- [AI Agent Frameworks 2026 Deep Dive -- LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, PydanticAI, Mastra, DSPy, MCP (youngju.dev)](https://www.youngju.dev/blog/culture/2026-05-16-ai-agent-frameworks-langchain-langgraph-llamaindex-crewai-autogen-pydanticai-mastra-dspy-mcp-2026-deep-dive.en)
- [AI Agent Frameworks Compared: LangGraph vs CrewAI vs AutoGen (2026) -- PEC Collective](https://pecollective.com/blog/ai-agent-frameworks-compared/)
- [AI Agent Frameworks Comparison 2026: LangGraph vs CrewAI vs AutoGen -- Arsum](https://arsum.com/blog/posts/ai-agent-frameworks/)
- [DSPy GitHub repo (stanfordnlp/dspy) -- v3.2.1, May 2026](https://github.com/stanfordnlp/dspy)
- [LlamaIndex Agents vs Pydantic AI: Which Should You Choose? (2026 Comparison) -- xpay.sh](https://www.xpay.sh/resources/agentic-frameworks/compare/llamaindex-vs-pydantic-ai/)
- [Agentic AI Frameworks Compared 2026 -- Knowlee Blog](https://www.knowlee.ai/blog/agentic-ai-frameworks-comparison-2026)
- [LangGraph vs CrewAI vs AutoGen in 2026: Pick the Right AI Agent Framework (Or Skip Frameworks Entirely) -- DEV Community](https://dev.to/cristian_iridon_286794874/langgraph-vs-crewai-vs-autogen-in-2026-pick-the-right-ai-agent-framework-or-skip-frameworks-4m2c)
