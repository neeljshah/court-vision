# Claude Agent SDK: Production Agents, Sessions, Subagents, Deployment
_Researched 2026-06-16. Scope: How to build long-running autonomous data/modeling agents with the Claude Agent SDK vs raw API vs Claude Code CLI, with patterns directly applicable to a solo-built calibrated sports predictor._

---

## TL;DR (5-8 bullets: the highest-leverage takeaways)

- The Agent SDK (`pip install claude-agent-sdk`) is the same agent loop that powers Claude Code, now callable as a Python/TypeScript library. The core primitive is `async for message in query(prompt, options)` -- an async generator that streams messages while the agent autonomously executes tools.
- Use the SDK (not raw API) when your agent must run multiple tool-use turns autonomously -- the SDK owns the tool loop, context compaction, and session persistence so you do not write boilerplate. Use the raw `anthropic` Messages API only for 1-2 turn tasks or when you need fully custom tool plumbing.
- Sessions persist as JSONL under `~/.claude/projects/<encoded-cwd>/` and can be resumed (`resume=session_id`) or forked (`fork_session=True`) -- critical for long pipeline runs that must survive crashes or be restarted from a checkpoint.
- Hooks (`PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`) are the production control surface: use them for audit logging, cost metering, blocking dangerous ops (file deletes, secret reads), and telemetry -- they fire before all other permission checks.
- Subagents (`AgentDefinition` + `agents={}` dict in options) let you build coordinator/specialist patterns: main agent delegates to specialized subagents with restricted tool subsets, own prompts, and max turn limits. Parent history is NOT inherited -- you must pass context explicitly in the subagent prompt.
- Managed Agents (Anthropic-hosted REST API, launched 2026) is the production alternative to self-hosted SDK: Anthropic runs the loop + sandbox, you call a REST API. Common pattern: prototype locally with the SDK, ship to Managed Agents for production. For a solo build where you control the machine, the SDK is fine and cheaper to start.
- As of June 15, 2026, the SDK draws from a separate "Agent SDK credit" in subscription plans. Use `max_budget_usd` on `query()` from day one -- agentic loops with file/web/bash tools can burn tokens fast.

---

## Key capabilities / techniques (concrete: names, what they do, when to use)

### Installation and auth
```
pip install claude-agent-sdk          # Python >= 3.10 required
npm install @anthropic-ai/claude-agent-sdk  # TypeScript; bundles native binary
export ANTHROPIC_API_KEY=...
# Also supports Bedrock (CLAUDE_CODE_USE_BEDROCK=1), Vertex (CLAUDE_CODE_USE_VERTEX=1),
# Azure (CLAUDE_CODE_USE_FOUNDRY=1), Claude Platform on AWS (CLAUDE_CODE_USE_ANTHROPIC_AWS=1)
```

### Core query API
```python
from claude_agent_sdk import query, ClaudeAgentOptions, SystemMessage, ResultMessage

async for message in query(
    prompt="Run the walk-forward backtest and write results to data/results/wf_latest.parquet",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",   # no interactive approval prompts
        max_turns=40,                    # prevent runaway loops
        max_budget_usd=0.50,            # hard cost cap
    ),
):
    if isinstance(message, SystemMessage) and message.subtype == "init":
        session_id = message.data["session_id"]   # capture for resume
    if isinstance(message, ResultMessage):
        print(message.result)
        print(message.total_cost_usd)
```
Result subtypes: `success`, `error_max_turns`, `error_max_budget_usd` -- branch on these.

### Built-in tools (no extra code required)
| Tool        | What it does                                      |
|-------------|---------------------------------------------------|
| Read        | Read any file                                     |
| Write       | Create new files                                  |
| Edit        | Precise in-place edits                            |
| Bash        | Run terminal commands, scripts, git               |
| Glob        | Find files by pattern (`**/*.parquet`)            |
| Grep        | Regex search over file contents                   |
| WebSearch   | Search the web for current information            |
| WebFetch    | Fetch and parse a URL                             |
| Monitor     | Watch a background script, react per output line  |
| AskUserQuestion | Ask user with multiple-choice options (interactive)|

### Sessions: resume and fork
```python
# Resume: pick up where you left off (same session_id)
options=ClaudeAgentOptions(resume=session_id)

# Fork: branch from an existing session without modifying it
options=ClaudeAgentOptions(resume=session_id, fork_session=True)
```
CRITICAL: Session JSONL is keyed to `cwd`. If cwd changes between runs, `resume` silently starts a fresh session instead of restoring history. Always prefix bash calls with `cd <absolute-path>` or set `cwd` explicitly.

### Hooks: lifecycle callbacks
```python
from claude_agent_sdk import HookMatcher

async def block_secret_reads(input_data, tool_use_id, context):
    path = input_data.get("tool_input", {}).get("file_path", "")
    if ".env" in path or "secrets" in path:
        return {"decision": "block", "reason": "Secret file access blocked"}
    return {}

async def log_writes(input_data, tool_use_id, context):
    # Append to audit log; return {} to allow
    return {}

options=ClaudeAgentOptions(
    hooks={
        "PreToolUse":  [HookMatcher(matcher="Read|Bash", hooks=[block_secret_reads])],
        "PostToolUse": [HookMatcher(matcher="Edit|Write", hooks=[log_writes])],
    }
)
```
Hook execution order: Hooks (PreToolUse) -> Deny rules -> Ask rules -> permission_mode -> Allow rules -> canUseTool callback. Hooks win even over `bypassPermissions` -- use them for hard security invariants.

### Subagents: coordinator/specialist pattern
```python
from claude_agent_sdk import AgentDefinition

options=ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Bash", "Agent"],   # "Agent" must be here
    agents={
        "signal-validator": AgentDefinition(
            description="Run OOS walk-forward validation on a single signal file",
            prompt="You are a leak-free validation specialist. Read the signal file path given, "
                   "run the WF harness, and return Brier/log-loss/calibration numbers only. "
                   "Never write files. Report honest REJECT if p>0.05.",
            tools=["Read", "Bash"],
            model="sonnet",
            max_turns=20,
        ),
        "code-reviewer": AgentDefinition(
            description="Review a Python module for correctness and LOC compliance",
            prompt="You are a strict code reviewer. Flag any file over 300 LOC, "
                   "any feature that could leak future data, and any edge claim.",
            tools=["Read", "Glob", "Grep"],
            model="sonnet",
            max_turns=10,
        ),
    },
)
```
Subagent messages carry `parent_tool_use_id` -- use this to associate subagent output with its parent invocation in your logs. Subagents do NOT inherit parent conversation history; put all needed context in the subagent prompt explicitly.

### MCP integration
```python
options=ClaudeAgentOptions(
    mcp_servers={
        "obsidian-db": {"command": "npx", "args": ["obsidian-mcp-server", "--vault", "./vault"]},
        "postgres":    {"command": "uvx", "args": ["mcp-server-postgres", DATABASE_URL]},
    }
)
```
MCP tunnels (research preview as of mid-2026) allow agents to reach MCP servers on private networks without public exposure -- relevant if you move to Managed Agents later.

### Skills: filesystem-based knowledge packages
```
.claude/skills/walk-forward/SKILL.md    # YAML frontmatter + instructions
.claude/skills/calibration-audit/SKILL.md
```
Load via `setting_sources=["user", "project"]` in options. Claude auto-invokes when task matches description (progressive loading -- full content pulled only when needed). The skills in the current Claude Code harness already use this pattern.

### SDK vs raw API vs Claude Code CLI -- decision table
| Situation                                      | Best choice           |
|------------------------------------------------|-----------------------|
| 1-2 turn generation, no tools                  | Raw Messages API      |
| Interactive dev, one-off tasks                 | Claude Code CLI       |
| CI/CD pipeline, automated pipeline runs        | Agent SDK             |
| Production with no infra to manage             | Managed Agents (REST) |
| Long-running agent, your own machine/server    | Agent SDK             |
| Need fully custom tool loop control            | Raw Messages API      |
| Prototype -> production path                   | SDK first, then Managed Agents |

### Managed Agents (2026 addition)
Anthropic-hosted REST API that wraps the same agent loop. Adds: scheduler, "dreaming pass" (background reasoning between sessions), rubric-based outcome grading. Trade-off: you give up in-process control, gain zero-infra operation. Agent works on an Anthropic-managed sandbox (not your filesystem directly).

---

## How THIS project should use it (specific, actionable recommendations for a solo-built calibrated sports predictor + React board)

### 1. Autonomous nightly pipeline agent
Replace any manual `python run_pipeline.py` with an SDK agent that:
- Is invoked from a cron job or a simple scheduler script
- Reads the current game slate, fetches fresh data, runs the WF backtest, writes parquet outputs
- Has `max_budget_usd=1.00` and `max_turns=60` as hard stops
- Logs `total_cost_usd` per run to a cost ledger parquet for trending

```python
async for msg in query(
    prompt="Run tonight's pre-game prediction pipeline for NBA. "
           "Fetch fresh box scores, run the WF harness, output predictions to "
           "data/predictions/nba_tonight.parquet. Log calibration metrics to "
           "data/logs/calibration_log.parquet. No edge claims -- report Brier and log-loss only.",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
        max_turns=60,
        max_budget_usd=1.00,
    ),
):
    ...
```

### 2. Signal validation subagent fleet
Use the coordinator/specialist subagent pattern for signal discovery:
- Coordinator agent proposes a new signal (already done by `src/loop/discovery.py`)
- Spawns a `signal-validator` subagent with read-only + Bash tools to run the actual WF gate
- Spawns a `code-reviewer` subagent to check the generated signal file for LOC compliance and leak risk
- Coordinator collects structured results, writes to improvement log
This maps naturally to the existing self-improving loop and eliminates the need for multi-process orchestration.

### 3. Session resume for interrupted runs
Long pipeline runs (full-season WF, multi-sport batch) should capture `session_id` at start and store it. If the run fails mid-way (API timeout, budget hit), resume from the same session rather than restarting from scratch. The JSONL on disk preserves all tool results and context.

### 4. Hooks for data integrity and cost control
At minimum, install these hooks on every autonomous agent run:
- `PreToolUse` on `Bash`: block any `pytest tests/` invocation (the full suite freezes the box -- existing GOTCHA)
- `PreToolUse` on `Read/Bash`: block access to `.env`, `secrets/`, `data/vault/` paths that should not be touched autonomously
- `PostToolUse` on `Edit/Write`: log every file change with timestamp and agent session ID to an audit log
- `Stop`: emit final cost + turn count to a run-metrics parquet

### 5. Skills for sports domain context
Package domain knowledge as skills so any agent invocation automatically loads it:
- `.claude/skills/calibration-rules/SKILL.md` -- honesty guardrails (no edge claims, leak-free WF, honest REJECTs)
- `.claude/skills/data-paths/SKILL.md` -- canonical path map so agents don't fabricate paths
- `.claude/skills/signal-gate/SKILL.md` -- how to interpret gate output (REJECT = success, not failure)
This is more reliable than relying on `CLAUDE.md` alone for long sessions where context can drift.

### 6. Streaming result bridge to React board
The async generator streams messages in real time. Wire this to a WebSocket or SSE endpoint so the React live board shows pipeline progress without polling:
```python
# FastAPI SSE endpoint pattern
async def pipeline_stream():
    async for message in query(prompt=..., options=...):
        if hasattr(message, "text"):
            yield f"data: {message.text}\n\n"
        if isinstance(message, ResultMessage):
            yield f"data: DONE {message.total_cost_usd}\n\n"
```

### 7. Managed Agents as a future hosting target
The current setup (SDK on local Windows box) is fine for solo development. If the project moves toward a SaaS/product deployment (the productize track mentioned in project memory), the Managed Agents REST API lets the agent loop run on Anthropic infra while your API server just sends prompts and streams back results. Prototype with SDK now, migrate later without rewriting agent logic.

---

## Gotchas / limits

- **cwd mismatch breaks session resume.** Sessions are keyed to the working directory encoded in the JSONL path. Always use absolute paths and set cwd explicitly. The existing project note about prefixing every bash call with `cd /c/Users/neelj/nba-ai-system &&` is essential here.
- **`bypassPermissions` ignores `allowed_tools`.** If you use `bypassPermissions` for speed, use `disallowed_tools` for hard blocks instead of `allowed_tools` -- the latter is silently ignored.
- **Subagents do NOT inherit parent history.** A subagent that gets "review the changes" without explicit file paths will silently do nothing or hallucinate paths. Always embed file paths and constraints in the subagent prompt.
- **`Agent` tool must be in `allowedTools` for subagent delegation to work.** If omitted, the main agent will never spawn subagents even if they are defined.
- **Effective context window is ~60-80k tokens, not 200k.** The SDK compacts automatically at a threshold, but there is no pre-compaction hook to checkpoint state. For very long pipelines, break work into multiple `query()` calls with explicit `resume`.
- **Wheel size is 270-340 MiB** depending on platform (bundles a native Claude Code binary). Factor this into Docker image budget.
- **Model self-downgrade observed.** Opus 4.x can silently self-downgrade to Sonnet mid-session. Pin the model explicitly and verify via response metadata if model choice matters for a specific task.
- **Full pytest suite freezes the box** (existing project GOTCHA). Block this via a `PreToolUse` hook on Bash that rejects `pytest tests/` without a specific file argument.
- **Cost accumulates fast.** Agentic sessions with Bash/WebSearch/file tools can hit $1-2 per run on complex pipelines. Set `max_budget_usd` from day one; log `total_cost_usd` per run.
- **No built-in durable execution / checkpointing.** The JSONL session log is a conversation log, not a workflow checkpoint. Design pipeline tasks so each `query()` call is a logically complete unit that can be re-run independently.
- **Evaluation pipeline costs are high.** One production report cited evaluation costs at 10x the baseline agent workload. Keep eval runs to targeted per-file tests (already the project pattern) and use the cheapest model that can judge the specific output quality.
- **Documentation gaps.** Several `ClaudeAgentOptions` fields (`hooks`, `agents`, `sandbox`, `plugins`) exist in source but were missing from official docs as of mid-2026. Treat the source code and CHANGELOG as authoritative over tutorial blog posts.

---

## Sources (markdown links to every URL used)

- [Claude Agent SDK Official Docs - Overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK: Production Guide to Tracing, Subagents, and Evaluation (inference.net)](https://inference.net/content/claude-agent-sdk-production-guide/)
- [Anthropic Agent SDK: What It Ships vs. What It Leaves to You (Augment Code)](https://www.augmentcode.com/guides/anthropic-agent-sdk-what-ships-vs-what-you-build)
- [What Is the Claude Agent SDK? How It Differs from the Claude API (MindStudio)](https://www.mindstudio.ai/blog/what-is-claude-agent-sdk-vs-claude-api)
- [Anthropic's Code with Claude: Managed Agents, Proactive Workflows (InfoQ)](https://www.infoq.com/news/2026/05/code-with-claude/)
- [Claude Agent SDK in 2026: What It Is, When To Use It (Totalum)](https://www.totalum.app/blog/claude-agent-sdk-totalum-2026)
- [AI Agent Frameworks 2026: 8 SDKs Compared (MorphLLM)](https://www.morphllm.com/ai-agent-framework)
- [Claude Agent SDK: Subagents, Sessions and Why It's Worth It (ksred.com)](https://www.ksred.com/the-claude-agent-sdk-what-it-is-and-why-its-worth-understanding/)
