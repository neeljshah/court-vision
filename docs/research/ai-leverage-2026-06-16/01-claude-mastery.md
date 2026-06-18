# Claude Mastery -- Wielding Claude Code / SDK / API / Skills / MCP at the Highest Level

_Synthesis, 2026-06-16. Source briefs: claude-skills, claude-code-power, claude-mcp, claude-agent-sdk, claude-api-core, claude-api-scale, anthropic-agent-patterns, claude-computer-use._

This is the operator's manual for using Anthropic's full agent stack to build a solo, multi-sport CALIBRATED prediction platform at 10x velocity. North star: the BEST PREDICTIONS (OOS accuracy + calibration vs the devigged market-implied baseline), never a fabricated $ edge. Every automation here serves BUILD VELOCITY and PREDICTION QUALITY -- none of it manufactures market alpha, and that framing is load-bearing (it shapes which skills, hooks, and eval loops you build).

---

## 0. The one-paragraph thesis

Put binding rules in **hooks** (the only real enforcement), domain knowledge in **skills** (progressive disclosure, near-zero idle cost), file/data/DB/scrape access in **MCP servers** (write once, reuse everywhere), and orchestration in **Claude Code (interactive)** or the **Agent SDK (scripted/CI)**. Drive cost down with **prompt caching + Batch API + model routing** (stacked, this reaches ~5% of naive cost on repeated-context workloads). Use **Opus 4.8** to plan/review/synthesize, **Sonnet 4.6** as the default worker, **Haiku 4.5** for high-volume grunt work, and **Fable 5 only** for the most demanding frontier reasoning. Wrap the whole thing in an **Evaluator-Optimizer calibration loop** that targets Brier/log-loss on a held-out OOS fold and treats honest REJECTs as successes.

---

## 1. The toolbelt -- Claude Code vs Agent SDK vs raw API (when each)

These are three entry points to the **same underlying agent loop**. Pick by control surface and automation level, not by capability.

| Surface | What it is | Use it when | Don't use it when |
|---|---|---|---|
| **Claude Code (CLI/IDE)** | Interactive harness with skills, subagents, hooks, MCP, plan mode | Day-to-day building, exploration, plan-then-execute waves, one-off tasks | You need an unattended programmatic pipeline with parsed results |
| **Claude Code headless `-p`** | Same harness, non-interactive, JSON/stream output, exit codes | Cron jobs, CI, nightly benchmark/eval runs, shell-scriptable pipelines | Long stateful multi-stage runs needing in-process control of the loop |
| **Agent SDK** (`pip install claude-agent-sdk`) | The Claude Code loop as a Python/TS library (`async for message in query(...)`) | Long-running autonomous pipelines on your machine, subagent fleets, SSE streaming to the React board, session resume/fork | 1-2 turn generation with no tools (use raw API); interactive dev (use CLI) |
| **Raw Messages API** (`anthropic` SDK) | Direct `messages.create/parse/stream` | 1-2 turn generation, structured outputs, fully custom tool plumbing, the React board's per-call inference | A task needs many autonomous tool-use turns (let the SDK own the loop) |
| **Managed Agents** (Anthropic-hosted REST) | Anthropic runs the loop + sandbox; adds scheduler, "dreaming pass", rubric grading | Future productized/SaaS deployment with zero infra to manage | Solo local build today -- SDK on your box is cheaper and gives filesystem control |

**Decision rule for THIS project:**
- Interactive build waves and the autonomous "go" loop -> **Claude Code** (where it already lives).
- Nightly benchmark / signal-catalog sweep / WF eval -> **headless `-p`** or a thin **Agent SDK** script.
- The React live board's pregame/in-game inference calls -> **raw Messages API** (`messages.parse` with Pydantic + streaming).
- Defer Managed Agents until the productize track ships; prototype with the SDK so the migration is a hosting change, not a rewrite.

**Sharp edges that bite all three:**
- **cwd keys the session.** Agent SDK sessions persist as JSONL under `~/.claude/projects/<encoded-cwd>/`; if cwd drifts, `resume` silently starts fresh. This is the same root cause as the project's "prefix every bash with `cd /c/Users/neelj/nba-ai-system &&`" gotcha. Always set cwd explicitly.
- **Effective SDK context is ~60-80k tokens, not 200k** -- it auto-compacts, with no pre-compaction checkpoint hook. Break long pipelines into multiple `query()` calls, each a logically complete, independently re-runnable unit, chained with explicit `resume`.
- **Model self-downgrade observed** (Opus 4.x -> Sonnet mid-session). Pin the model and verify from response metadata when model choice matters.
- **Cost burns fast** in agentic loops with Bash/web/file tools ($1-2/run on complex pipelines). Set `max_budget_usd` and `max_turns` from day one; log `total_cost_usd` per run to a cost-ledger parquet.

---

## 2. Skills -- how to author + which to build for THIS project

A **skill** is a filesystem directory with a `SKILL.md` at root. Only the YAML `name` + `description` (~100 tokens) is pre-loaded into the system prompt; the body loads when triggered; bundled files load only when SKILL.md references them. This **progressive disclosure** means context cost scales with use, not with install count.

### Authoring rules (the load-bearing ones)
- **Frontmatter has exactly two required fields:** `name` (lowercase-hyphens, max 64 chars) and `description` (max 1024 chars). Every other field (`model`, `context`, `allowed-tools`, `disable-model-invocation`, `user-invocable`) works in the Claude Code CLI but is **silently stripped before model context in API usage** (GitHub issue #13005). Put anything load-bearing in the body, not custom fields.
- **The description is the ONLY selector** Claude uses to pick among installed skills. Write it third person, state WHAT it does AND WHEN to invoke, and include the exact domain terms you'll say ("walk-forward", "Brier score", "in-game", "calibration", "REJECT"). Vague descriptions silently never trigger.
- **Three loading tiers:** metadata (always) -> SKILL.md body (on trigger, keep < 300 lines for this project, tighter than the 500-line official soft limit) -> bundled `reference/*.md` and `scripts/*.py` (only when referenced). Scripts run via bash; **only their output enters context, not their code** -- deterministic compute for free.
- **Keep references ONE level deep.** SKILL.md -> a.md -> b.md breaks: Claude may `head -100` the intermediate file and miss content.
- **Naming:** gerund form preferred (`processing-game-logs`, `running-walk-forward`, `evaluating-calibration`). Forbid `helper`/`utils`/`tools`/`data`, "claude"/"anthropic", uppercase, spaces.
- **Frontmatter levers that matter here:** `disable-model-invocation: true` (forces explicit `/name`; mandatory for side-effectful skills like commit/brain-rebuild), `context: fork` (runs in an isolated subagent so noisy output can't bloat main context), `model: opus|sonnet|haiku` (per-skill routing). Arg substitution: `$ARGUMENTS`, `$0/$1`, `${CLAUDE_SKILL_DIR}`.
- **Dev loop:** build with Claude A (expert), test with Claude B (fresh instance), watch where B fails, tighten. Best skills start as "a few lines and a single gotcha" and grow only where B stumbled.

### Skills to build for THIS project (prioritized)

**Tier 1 -- encode the pipeline + the invariants (do first):**

| Skill | Triggers on | Encodes | Notes |
|---|---|---|---|
| `running-walk-forward` | "walk-forward", "OOS eval", "leak-free backtest" | WF split rules, anti-leak checklist, per-file pytest only | `reference/{nba,mlb,soccer,tennis}.md` domain-scoped |
| `evaluating-calibration` | "Brier", "calibration", "accuracy vs edge" | Brier/log-loss scripts, honest-reject framing, NO ROI | bundle `scripts/calibration_audit.py` |
| `committing-changes` | "commit" | ALWAYS targeted `git add`; NEVER push (origin public); local only | overrides default GSD commit behavior |
| `adding-sport-adapter` | "new sport", "add adapter", "domains/<sport>" | kernel/adapter contract, zero-kernel-edit rule, proof harness | |
| `running-ingame-regrade` | "in-game", "live regrade", "CV_INGAME" | regrade pipeline + the shrink-toward-current MAE-artifact WARNING | |

**Tier 2 -- formalize the loops you already run:**
- `processing-game-logs`, `auditing-signal-catalog` (gate path; REJECT = success), `building-obsidian-brain` (serialize; never two concurrent rebuilds -- WinError 32), and the existing `/benchmark`, `run-pipeline`, `train-checkpoint`, `debug-cv`, `dataset-status` (formalize each with `disable-model-invocation: true`, `model: sonnet`, `context: fork`).

**The keystone skill -- `evaluating-calibration` / `calibration-audit`:** a bundled `scripts/calibration_audit.py` that takes predictions + actuals and emits a structured Brier / reliability-diagram / log-loss report, with a description that **explicitly says "never claims edge; frames results as calibration accuracy vs the devigged market baseline."** This makes the project's honesty discipline a build-time guardrail any agent auto-invokes, not a runtime hope.

**Borrow, don't rebuild:**
- **obra/superpowers** (MIT, in the official marketplace, methodology-as-skill): install now for `brainstorming`, `planning`, `systematic-debugging`, and especially `verification-before-completion` -- it forces Claude to prove a fix worked (run the test, observe output) before declaring done. That is exactly the WF-integrity discipline this project needs.
- **machina-sports/sports-skills** (`npx skills add machina-sports/sports-skills`): 14 read-only sports-data skills (ESPN/FastF1, zero API key) for freshness-bump data; a pure-compute `betting` skill (Kelly, odds conversion, edge detection -- no network) reusable in the in-game regrade; a `markets` skill as a template if you ever validate Kalshi/Polymarket as a calibration benchmark.

**Encode gotchas as in-skill WARNINGS, not just memory.** Every relevant skill body should carry the hard-won guardrails ("NEVER two concurrent brain rebuilds", "prefix bash with `cd ...`", "forward slashes in all path references even on Windows") so the rule rides along with the trigger instead of depending on memory loading.

**Surface note:** Claude Code skills are filesystem-only with **full network access** and git-tracked in `.claude/skills/` -- the right home here. API-uploaded skills get **no network and no pip** (pre-bundle deps); claude.ai skills are user-only. Skills do NOT sync across surfaces.

---

## 3. Subagents / hooks / MCP / workflows

### Subagents -- context isolation is the real value
- Types: `Explore` (read-only, Haiku default), `Plan` (read-only, Sonnet), `GeneralPurpose` (full tools), plus custom in `.claude/subagents/`. Recursive to 5 levels (design for <=3 to leave headroom).
- The point is **context hygiene**: a file-heavy task (signal-catalog sweep, vault read, research fan-out) runs in an isolated subagent and returns only a summary -- your decision-layer context stays clean.
- SDK form: `AgentDefinition` + `agents={}` in `ClaudeAgentOptions`, with the **`Agent` tool in `allowed_tools`** (omit it and delegation silently never happens). **Subagents do NOT inherit parent history** -- embed every file path and constraint in the subagent prompt or it hallucinates paths / does nothing.
- `isolation: worktree` gives each subagent its own git worktree for conflict-free parallel edits -- but heed the prior lesson: **one file -> one agent** in any fleet to avoid concurrent-write collisions.

**This project:** make the signal-catalog sweep an `Explore` (Haiku) subagent that returns a 10-line candidate list; the main session decides what to gate without reading the raw files. Use a `signal-validator` subagent (read-only + Bash, Sonnet) to run the WF gate and report Brier/log-loss/REJECT, and a `code-reviewer` subagent to flag >300 LOC files and leak risk. This maps directly onto the existing self-improving loop and removes multi-process orchestration glue.

### Hooks -- the ONLY true enforcement layer
CLAUDE.md and skill bodies are *requests*; a `PreToolUse` hook is a *guarantee*. Hooks fire **before all permission checks and even win over `bypassPermissions`** -- use them for hard invariants. Zero context cost unless the hook returns output (so keep output minimal: a path + an error count, never a 200-line lint dump).

Event types include `PreToolUse`, `PostToolUse`, `Stop`/`SessionEnd`, `SessionStart`, `SubagentStart/Stop`, `PreCompact`, `UserPromptSubmit`. `PreToolUse` can return `updatedInput` to rewrite a command before it runs. SDK form uses `HookMatcher`; an SDK hook returns `{"decision": "block", "reason": "..."}`.

**Install these on this project immediately** (`.claude/settings.json` hooks, or SDK `hooks=`):
- `PreToolUse` on `Bash` -> block `git push origin` / `git push --force` (origin is PUBLIC).
- `PreToolUse` on `Bash` -> block bare `pytest tests/` (full suite freezes the box); allow per-file pytest.
- `PreToolUse` on `Bash` -> if a command lacks the cwd prefix and isn't absolute, prepend `cd /c/Users/neelj/nba-ai-system &&`.
- `PreToolUse` on `Read|Bash` -> block `.env`, `secrets/`, and writes into gitignored `data/`/`vault/`.
- `PostToolUse` on `Edit|Write` -> warn if file > 300 LOC; loudly flag any edit touching `src/`/`kernel/` (human-gated).
- `Stop` -> emit final cost + turn count to a run-metrics parquet (the existing `vault_session_close.py` is a `Stop` hook already).

### MCP -- write a tool once, use it in every host
MCP is JSON-RPC 2.0 (host -> client -> server). Transports: **stdio** (local subprocess, zero-auth, best perf -- correct for this project) and **Streamable HTTP** (remote; MUST use OAuth 2.1 + PKCE -- a 2026 scan found ~every public remote MCP exposed its tool list unauthenticated). Primitives: Tools / Resources / Prompts (server) and Sampling / Elicitation (client; avoid Sampling in production -- recursive and hard to audit). MCP tools appear as `/mcp__<server>__<tool>`; tool-search defers idle schemas so idle servers cost little context.

**Highest-leverage MCP additions here:**
1. **Custom `sports_predictor` stdio server** (`scripts/mcp_server/`, Python `mcp` SDK): `predict_pregame`, `predict_ingame`, `calibration_report` tools + an `edge_map` resource. Makes `predict_matchup` a first-class tool for Claude Code, CI agents, and any future IDE -- zero re-integration per consumer.
2. **Filesystem server** pointed read-only at `data/` and `vault/` -> agents read parquet/JSON/intel notes as resources without you writing I/O glue (honor the gitignore-data invariant; restrict writes).
3. **SQLite server** over result tables (WF Brier, gate results, calibration) converted alongside parquet -> interactive `SELECT ... ORDER BY brier_score` beats hand-reading parquet. (No MCP server reads `.parquet` natively; convert to SQLite or expose a thin `pandas.read_parquet` tool.)
4. **Playwright server** for JS-rendered odds/box-score pages where no API exists (devigged market capture without a paid Odds API); **Firecrawl** for bulk ingest of stat-API docs / analytics pages into the vault as Resources.
5. **Memory server** (knowledge graph) so research agents durably remember which signals were tested/REJECTed and the current Brier baseline -- stops re-running documented experiments.

**MCP security discipline:** local stdio = full OS trust, so scope filesystem servers to a specific subdir (never `/`); log every tool call; never let a tool call another tool that can write production data; pin community-server versions (Anthropic archived the Postgres/SQLite/GitHub/Slack/Drive reference servers).

### Workflows vs agents -- the framing
Anthropic distinguishes **workflows** (pre-defined code paths) from **agents** (LLM-directed paths): start with the simplest structure that works; add autonomy only when the decision tree can't be pre-mapped. The five composable patterns (next section) layer up into autonomous agents only for open-ended work. **Agent Teams** (experimental, default-OFF) are peer-to-peer full Claude instances -- much more expensive than subagents; reserve for genuinely parallel independent work and prefer subagents otherwise.

---

## 4. Anthropic's agent patterns mapped to this project

The five patterns from "Building Effective Agents", with the concrete win for a calibrated predictor:

- **Prompt Chaining** -> the data-to-prediction funnel (fetch -> parse -> signal -> inference -> calibration -> output). Keep each stage a bounded call with a schema contract at its boundary; do NOT merge into one megaprompt.
- **Routing** -> model-tier cost control: simple lookup/format -> Haiku, signal screening/validation -> Sonnet, calibration audit/architecture -> Opus. 3-5x token savings with no quality loss on hard steps.
- **Parallelization / Sectioning** -> run NBA/MLB/soccer/tennis ingestion as parallel subagents (fully independent pipelines; near-linear speedup).
- **Parallelization / Voting** -> for borderline gate signals, run N=3 screeners with different seeds and require 2/3. BUT: voting gives a **variance estimate, not independent corpora** -- still require >=2 separate time-period corpora before any honest edge claim.
- **Orchestrator-Workers** -> per-game intelligence build: orchestrator spawns workers for injury/lineup, recent-form refresh, head-to-head, market line, live state; synthesizes. Anthropic's internal lead-Opus + parallel-Sonnet system cut research time up to 90% and beat single-agent Opus by 90.2% on complex queries. **Hardcode scaling rules** ("simple: 1 agent; complex: 10+") or you get 50 subagents on a trivial query.
- **Evaluator-Optimizer** -> THE direct win: wrap recalibration as a loop. Generator proposes a patch (isotonic knots / Platt params / shrinkage weights); Evaluator scores Brier + reliability-slope on the held-out OOS fold and rejects if Brier worsens; max ~5 iterations, accept best, log all states. Evaluation criteria must be explicit ("Brier improves on OOS fold"), never "make it better".

**Pattern-level cautions:** ~80% of multi-agent output-quality variance is explained by token usage, and multi-agent systems use ~15x the tokens of single-turn chat -- budget per wave (Opus orchestrator only; Sonnet/Haiku workers). **Tool documentation is a first-order lever** -- poor tool docs sent agents down wrong paths and cost 40% in completion time; audit every tool definition with examples and expected output formats. LLM-as-judge has source-selection bias (it picks SEO content farms over authoritative sources) -- instruct evaluators to prefer primary sources (official stats APIs, papers). And the binding one: **these patterns accelerate the build and sharpen calibration; they do not create a pricing edge against efficient markets.** The Evaluator-Optimizer targets Brier/log-loss on OOS, never in-sample ROI.

---

## 5. API power features + cost / caching / batch

### Power primitives (raw Messages API)
- **Structured outputs (GA, all current models incl. Fable 5):** `client.messages.parse(output_format=PydanticModel, ...)` -> validated `parsed_output`, no regex retry loops. Use for `GamePrediction`, feature dicts, calibration summaries. Constraints: `additionalProperties: false` required; **no recursive schemas, no numeric constraints (`minimum`/`maximum`), no complex regex**; grammar cached 24h (schema change busts it, name/description change does not). **Mutually exclusive with citations** (400 if both).
- **Tool use:** client tools (your functions: odds fetch, stat DB, vault read, WF gate) + server tools (`web_search_20260209`, `code_execution`, `web_fetch`). `strict: true` -> grammar-constrained, type-valid inputs (limit 20 strict tools, 24 optional params, 16 union-typed). `tool_choice`: `auto` (default) / `any` (force a tool) / `tool` (force a named one). Tool overhead ~290-590 tokens.
- **Extended vs adaptive thinking** -- this is a model-split, get it right:
  - **Extended thinking** (`thinking: {type:"enabled", budget_tokens:N}`): Sonnet 4.6, Haiku 4.5, Opus 4.6 and earlier. `budget_tokens < max_tokens`; quality improves up to ~32k; **must pass thinking blocks back unchanged** in multi-turn tool loops; with thinking only `tool_choice: auto|none` allowed.
  - **Adaptive thinking** (`thinking: {type:"adaptive"}` + `effort: low|medium|high|xhigh|max`): Fable 5, Opus 4.8, Opus 4.7. Manual `budget_tokens` returns **400** on these. Opus 4.8 defaults `effort: high`; use `xhigh` for the hardest agentic/coding passes.
- **Streaming:** `client.messages.stream()`; **required when `max_tokens` > ~21k**; thinking emits `thinking_delta` before `text_delta`. For the React board use `display: "omitted"` so thinking tokens add no wire latency.
- **Citations** (all active models except retired Haiku 3): `citations: {enabled:true}` per document -> sentence-level grounded claims; `cited_text` costs no output tokens; works with caching; **incompatible with structured outputs**. Use to ground vault-intelligence reasoning so every prediction modifier traces to a source note.
- **Vision/PDF:** all current models take images (base64 or URL) and PDFs (`type:"document"`); URL sources skip base64 overhead.

### Cost engine -- caching + batch + routing (stacked)
- **Prompt caching is the single biggest lever.** Cache reads = **0.10x** input price (90% off). 5-min write = 1.25x (breaks even after 1 read); 1-hour write = 2.0x (breaks even after 2 reads). Min cacheable prefix on current models = 1,024 tokens. **Cache reads do NOT count against ITPM** -> effective throughput multiplies by 1/(1 - hit_rate). Cache the prediction system prompt + static signal context (1-hour TTL); **pre-warm before tip-off** with a `max_tokens: 0` request so live in-game calls hit a hot cache. Caches are workspace-isolated (since 2026-02-05).
- **Batch API = flat 50% off input+output** for async work (WF backtests, signal scoring, nightly enrichment); **stacks multiplicatively with caching** -> ~5% of naive cost on repeated-context workloads. Up to 100k requests/batch; results keyed by `custom_id`; finish usually <1h; expire after 29 days; `output-300k-2026-03-24` beta raises max output to 300k for Opus 4.6/4.7/4.8 + Sonnet 4.6. **Not ZDR-eligible**; not compatible with Fast mode.
- **Token counting** (`POST /v1/messages/count_tokens`, free): pre-check size to route model, gate on context, and verify the 1,024-token cache minimum before paying cache-write overhead.
- **Files API:** upload large static docs (signal catalog, playstyle defs) once, reference by `file_id`; pairs with caching.

**Caching gotchas that silently cost money:** the `cache_control` breakpoint must land on the **last STATIC block** -- if it lands on anything per-request (timestamp, query, per-game context) the prefix hash never matches and you pay writes with zero reads. 20-block lookback window (use multiple explicit breakpoints in long conversations). For a parallel fleet, **wait for the pre-warm response before firing** -- the cache entry only becomes available after the first response begins. Target >70% cache hit rate on the Console Usage page.

---

## 6. Model selection (Opus 4.x / Fable / Sonnet / Haiku)

| Model | ID | In/Out per MTok | Context / Max out | Thinking | Role here |
|---|---|---|---|---|---|
| Fable 5 | `claude-fable-5` | $10 / $50 | 1M / 128k | Adaptive only | Most demanding frontier reasoning ONLY; rarely needed |
| Opus 4.8 | `claude-opus-4-8` | $5 / $25 | 1M / 128k | Adaptive (`effort`) | Plan / review diffs / cross-sport calibration synthesis / orchestrator |
| Sonnet 4.6 | `claude-sonnet-4-6` | $3 / $15 | 1M / 64k | Extended + adaptive | **Default worker**: WF eval, pregame/in-game inference, signal screening |
| Haiku 4.5 | `claude-haiku-4-5` | $1 / $5 | 200k / 64k | Extended | High-volume grunt: enrichment, extraction, classification, Explore subagents |

**Routing policy for this project:**
- Nightly enrichment / bulk feature extraction -> **Haiku 4.5 + Batch** (5x cheaper than Opus, 50% batch discount on top).
- WF eval / signal research / pregame + in-game inference -> **Sonnet 4.6** (1M context, fast, best $/quality).
- Plan-phase, diff review, cross-sport calibration audit, the orchestrator role -> **Opus 4.8** (`effort: xhigh` for the hardest passes), cache everything reusable.
- Real-time React board updates -> **Haiku 4.5** streamed, `display: "omitted"`.
- **Fable 5** -> reserve for genuinely frontier reasoning; at $10/$50 it is rarely the right call here. (Mythos 5 is invite-only / cybersec -- ignore.)

In Claude Code, set `model: claude-sonnet-4-6` and `env: { CLAUDE_CODE_SUBAGENT_MODEL: "haiku" }` globally; override `model: opus` in the plan/review skill frontmatter. Set `fallbackModel: ["claude-sonnet-4-6", "claude-haiku-4-5"]` to survive 529 overloads (the documented API-529 gotcha that kills overnight runs).

**Model gotchas:** Opus 4.7+ uses a **new tokenizer that can consume up to 35% more tokens** for the same text -- re-measure prompt sizes and cache minimums before assuming costs carry over. Tier-1 Opus ITPM is only 500k/min (fine for single-game live, too low for parallel eval fleets -- $40 cumulative spend unlocks Tier-2's 2M). The rate limiter is a continuous token bucket, so bursts trigger 429s even under your per-minute average -- submit batches at a steady rate and read `retry-after` headers rather than hardcoding sleeps. Opus 4.1 retires 2026-08-05; migrate to 4.8.

### Computer Use -- the deliberate non-recommendation
Computer use (beta header `computer-use-2025-11-24`; screenshot + mouse/keyboard in a sandboxed VM) is **the wrong tool for sports-data collection** and should NOT be a primary pipeline here. Real-world success on dynamic/async web UIs drops to ~50-60%; it is 5-10x slower than a direct integration (2-8s per screenshot-action round trip vs <1s API) and **cannot keep pace with live odds**; cost is 5-20x a direct call; and **prompt injection is unsolved** (a March 2026 Oasis Security demo chained injection -> exfiltration -> C2 via a binary Claude was tricked into running; the classifier defense pauses for human confirmation and thus breaks unattended runs). For every data need there is a better tool: OddsAPI for odds, `cdn.nba.com/.../liveData` for PBP, Statcast bulk CSV, Playwright + headless Chromium for board verification (deterministic, ~0.1s, free). Computer use is only defensible for low-stakes, no-auth, structured research browsing -- and even then run it in an isolated Docker container, domain-allowlisted, `max_iterations<=15`, on Sonnet not Opus, with structural validation of every output.

---

## 7. The 10x build-loop blueprint (solo builder)

A concrete, layered loop. Each layer is independently shippable; do them roughly in order.

**Layer 0 -- Foundation (do this week):**
1. Refactor `CLAUDE.md` to < 200 lines (architecture, build commands, binding invariants); move detail to `.claude/rules/` path-scoped files: `src-kernel.md` (paths `src/**`,`kernel/**` -> "HUMAN-GATED, stop"), `vault-gitignored.md` (`vault/**`,`data/**` -> "never commit"), `no-edge-claims.md` (the honesty guardrail as a named rule).
2. Install the enforcement **hooks** from S3 (block push, block full pytest, prepend cwd, block secrets, LOC/human-gate warnings). This is the single highest-confidence move -- it converts every prose rule into a guarantee.
3. `settings.json`: `model: sonnet`, `CLAUDE_CODE_SUBAGENT_MODEL: haiku`, `fallbackModel`, `defaultMode: acceptEdits`, `env: { PYTHONPATH: "." }`.
4. Install **obra/superpowers**; adopt `planning` + `verification-before-completion` as the default wave wrapper.

**Layer 1 -- Skills + MCP (the leverage):**
5. Author Tier-1 skills (S2): `running-walk-forward`, `evaluating-calibration` (+ bundled `calibration_audit.py`), `committing-changes`, `adding-sport-adapter`, `running-ingame-regrade`. Formalize the existing `/benchmark` family with `disable-model-invocation: true` + `context: fork`.
6. Stand up the **custom `sports_predictor` MCP server** + Filesystem (read-only `data/`,`vault/`) + SQLite (result tables) + Memory (tested/REJECTed signal log).

**Layer 2 -- The autonomous build loop (velocity):**
7. **Plan mode before every multi-file wave**: `--permission-mode plan`, append "think hard", review/edit the plan, then approve. #1 quality lever for complex changes.
8. **Orchestrator-Workers wave**: Opus orchestrator (in plan mode) decomposes; spawns parallel Sonnet workers (sectioned by sport / by file -- one file per agent); Explore/Haiku subagents do read-heavy research and return summaries.
9. **Headless nightly cron**: `claude -p "<skill or prompt>" --output-format json --max-turns 20 --max-budget-usd 1 --allowedTools "Bash,Read,Glob,Grep,Edit" --session-id "nightly-$(date +%Y%m%d)"` for benchmark + signal-catalog sweep + WF eval, with `fallbackModel` set to survive 529s. Or schedule via the cloud `schedule`/cron trigger.

**Layer 3 -- The calibration improvement loop (quality, the north star):**
10. Wrap recalibration as an **Evaluator-Optimizer** loop (S4): generator proposes a patch, evaluator scores Brier + reliability-slope on the held-out OOS fold and rejects regressions, max ~5 iters, log every state. Submit the WF backtest sweep through the **Batch API** (50% off) with the system prompt + signal context **prompt-cached** (90% off the cached portion) -> a 10k-game Sonnet eval drops from ~$30 to ~$7.
11. Stream pipeline progress to the React board via an Agent SDK `query()` generator bridged to an SSE/WebSocket endpoint (Haiku, `display:"omitted"`).
12. Every prediction output flows through `evaluating-calibration` automatically; honest REJECTs are logged as successes; nothing claims a $ edge.

**The daily rhythm:** interactive (Claude Code, plan-then-execute) for new work -> headless cron for repeatable eval/benchmark -> Batch+cache for the heavy sweeps -> Evaluator-Optimizer for calibration tuning -> Opus diff review before any commit (local only). Cost ledger logged per run; cache hit rate watched on the Usage page.

---

## 8. Action checklist

- [ ] Refactor `CLAUDE.md` to < 200 lines; move detail into `.claude/rules/` path-scoped files (kernel human-gate, vault/data no-commit, no-edge-claims).
- [ ] Add enforcement **hooks** in `.claude/settings.json`: block `git push origin`, block bare `pytest tests/`, prepend cwd, block `.env`/`secrets`/gitignored writes, warn on >300 LOC and `src/`/`kernel/` edits.
- [ ] Set `settings.json`: `model: claude-sonnet-4-6`, `CLAUDE_CODE_SUBAGENT_MODEL: haiku`, `fallbackModel: ["claude-sonnet-4-6","claude-haiku-4-5"]`, `defaultMode: acceptEdits`.
- [ ] Install **obra/superpowers**; adopt `planning` + `verification-before-completion`. Install **machina-sports/sports-skills** for read-only data + the compute-only `betting` skill.
- [ ] Author Tier-1 skills with the **keystone `evaluating-calibration`** (bundled `calibration_audit.py`; description explicitly "never claims edge"). Use domain-scoped `reference/{nba,mlb,soccer,tennis}.md`. Embed hard-won gotchas as in-body WARNINGS.
- [ ] Mark all side-effectful skills `disable-model-invocation: true`; mark noisy ones `context: fork`; route plan/review skills `model: opus`.
- [ ] Build the custom **`sports_predictor` stdio MCP server** (`predict_pregame`, `predict_ingame`, `calibration_report`, `edge_map` resource); add Filesystem (RO `data/`,`vault/`), SQLite (result tables), Memory (signal log). Scope filesystem servers to a subdir; log all tool calls.
- [ ] Use **plan mode + "think hard"** before every multi-file wave; review the plan before approving.
- [ ] Wire the **Orchestrator-Workers** wave: Opus orchestrator, parallel Sonnet workers (one file / one sport per agent), Explore/Haiku for research; hardcode subagent scaling rules.
- [ ] Stand up a **headless `-p` nightly cron** for benchmark + signal sweep + WF eval with `--max-turns`, `--max-budget-usd`, `--session-id`, `fallbackModel`.
- [ ] Run the heavy WF/eval sweeps through **Batch API + prompt caching** (system prompt + signal context on a 1-hour TTL; pre-warm before tip-off; breakpoint on the LAST static block; target >70% hit rate).
- [ ] Implement the **Evaluator-Optimizer calibration loop** targeting Brier + reliability-slope on a held-out OOS fold; max 5 iters; log every state; honest REJECT = success.
- [ ] Adopt structured outputs (`messages.parse` + Pydantic) for all prediction/feature/calibration JSON; use citations to ground vault reasoning (remember: cannot combine with structured outputs).
- [ ] Pin models (guard against self-downgrade); set `max_budget_usd`/`max_turns` on every SDK/headless run; log `total_cost_usd` to a cost-ledger parquet; verify Tier-2 ITPM before any parallel eval fleet.
- [ ] Re-measure prompt token sizes for the **Opus 4.7+ tokenizer (+up to 35%)** before relying on cost/cache estimates.
- [ ] **Do NOT** build a computer-use data pipeline; use OddsAPI / `cdn.nba.com` liveData / Statcast CSV / Playwright headless instead. Reserve computer use for low-stakes no-auth research browsing only, sandboxed.
- [ ] Keep all of it serving CALIBRATION and BUILD VELOCITY -- never frame any output as a $ edge; never push to public origin; never two concurrent brain rebuilds; never run the full pytest suite.

---

## Sources / References

**Claude Skills**
- [Agent Skills overview -- platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Skill authoring best practices -- platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Equipping agents for the real world with Agent Skills -- Anthropic](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [obra/superpowers -- GitHub](https://github.com/obra/superpowers/)
- [machina-sports/sports-skills -- GitHub](https://github.com/machina-sports/sports-skills)
- [SKILL.md frontmatter reference -- anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/command-development/references/frontmatter-reference.md?plain=1)
- [Custom frontmatter fields stripped issue #13005 -- anthropics/claude-code](https://github.com/anthropics/claude-code/issues/13005)
- [Claude Agent Skills: A First Principles Deep Dive -- leehanchung.github.io](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)

**Claude Code power features**
- [Extend Claude Code (official docs) -- code.claude.com](https://code.claude.com/docs/en/features-overview)
- [Claude Code CLI: Complete Guide -- Hooks, MCP, Skills (blakecrosley.com)](https://blakecrosley.com/guides/claude-code)
- [Claude Code in CI/CD and Headless Automation (hidekazu-konishi.com)](https://hidekazu-konishi.com/entry/claude_code_cicd_and_headless_automation.html)
- [Understanding Claude Code's Full Stack: MCP, Skills, Subagents, Hooks (alexop.dev)](https://alexop.dev/posts/understanding-claude-code-full-stack/)
- [Claude Code Features and Settings Reference 2026 (hidekazu-konishi.com)](https://hidekazu-konishi.com/entry/claude_code_features_settings_reference_2026.html)
- [Claude Code Headless Mode Autonomous Agents (mindstudio.ai)](https://www.mindstudio.ai/blog/claude-code-headless-mode-autonomous-agents-2)
- [Adaptive Thinking -- Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking)

**MCP**
- [MCP Official Introduction -- modelcontextprotocol.io](https://modelcontextprotocol.io/introduction)
- [MCP Architecture Documentation -- modelcontextprotocol.io](https://modelcontextprotocol.io/docs/learn/architecture)
- [modelcontextprotocol/servers -- GitHub](https://github.com/modelcontextprotocol/servers)
- [MCP Registry -- registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io/)
- [MCP Server Security Best Practices -- Descope](https://www.descope.com/blog/post/mcp-server-security-best-practices)
- [Best MCP Servers in 2026 -- OpenclawMCP](https://openclawmcp.com/blog/best-mcp-servers-2026)
- [postgres-mcp-pro -- crystaldba GitHub](https://github.com/crystaldba/postgres-mcp)

**Claude Agent SDK**
- [Claude Agent SDK Official Docs -- Overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK: Production Guide to Tracing, Subagents, Evaluation (inference.net)](https://inference.net/content/claude-agent-sdk-production-guide/)
- [Anthropic Agent SDK: What It Ships vs. What It Leaves to You (Augment Code)](https://www.augmentcode.com/guides/anthropic-agent-sdk-what-ships-vs-what-you-build)
- [What Is the Claude Agent SDK? (MindStudio)](https://www.mindstudio.ai/blog/what-is-claude-agent-sdk-vs-claude-api)
- [Code with Claude: Managed Agents, Proactive Workflows (InfoQ)](https://www.infoq.com/news/2026/05/code-with-claude/)
- [Claude Agent SDK: Subagents, Sessions and Why It's Worth It (ksred.com)](https://www.ksred.com/the-claude-agent-sdk-what-it-is-and-why-its-worth-understanding/)

**Claude API core**
- [Claude Models Overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Choosing a Model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model)
- [Tool Use Overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Strict Tool Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use)
- [Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Extended Thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)
- [Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [Citations](https://platform.claude.com/docs/en/build-with-claude/citations)
- [PDF Support](https://platform.claude.com/docs/en/build-with-claude/pdf-support)
- [Batch Processing / Message Batches API](https://platform.claude.com/docs/en/build-with-claude/batch-processing)

**Claude API at scale**
- [Prompt caching -- Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Pricing -- Claude API Docs](https://platform.claude.com/docs/en/about-claude/pricing)
- [Rate limits -- Claude API Docs](https://platform.claude.com/docs/en/api/rate-limits)
- [Claude API Cost Optimization Guide for Enterprises 2026 (cleveroad.com)](https://www.cleveroad.com/blog/claude-api-cost-optimization-enterprise/)
- [Anthropic API Pricing 2026 (finout.io)](https://www.finout.io/blog/anthropic-api-pricing)

**Anthropic agent patterns**
- [Building Effective AI Agents -- Anthropic Research](https://www.anthropic.com/research/building-effective-agents)
- [How We Built Our Multi-Agent Research System -- Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Anthropic Cookbook: patterns/agents -- GitHub](https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents)
- [Building Effective Agents: Practical Framework -- ZenML LLMOps Database](https://www.zenml.io/llmops-database/building-effective-agents-practical-framework-and-design-principles)

**Computer use**
- [Computer use tool -- Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
- [Claude Computer Use API: Architecture, Constraints (claudecode.jp)](https://claudecode.jp/en/news/engineer/dispatch-and-computer-use)
- [Claude Computer Use: A Ticking Time Bomb -- prompt.security](https://prompt.security/blog/claude-computer-use-a-ticking-time-bomb)
- [Claude Computer Use API 2026: OSWorld Score (tokenmix.ai)](https://tokenmix.ai/blog/claude-computer-use-api-2026)
- [anthropics/claude-quickstarts (computer-use-demo) -- GitHub](https://github.com/anthropics/claude-quickstarts)
