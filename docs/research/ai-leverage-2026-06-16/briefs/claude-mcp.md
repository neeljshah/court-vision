# Model Context Protocol (MCP): Architecture, Servers, and Sports-Data Use
_Researched 2026-06-16. Scope: MCP architecture, transport types, official + community servers, security model, and which servers most accelerate a solo-built multi-sport calibrated-prediction platform._

---

## TL;DR (highest-leverage takeaways)

- MCP is a JSON-RPC 2.0 open standard (host -> client -> server) that lets any AI application (Claude Code, Cursor, VS Code, etc.) call tools, read resources, and use prompt templates from external servers -- "USB-C for AI."
- Two transports: **stdio** (local process, zero-auth, best performance) and **Streamable HTTP** (remote, requires OAuth 2.1 + PKCE, supports many concurrent clients via SSE).
- Three server-side primitives: **Tools** (callable functions), **Resources** (data sources), **Prompts** (templates). Two client-side primitives: **Sampling** (LLM calls back through host) and **Elicitation** (server asks user for input).
- The official `modelcontextprotocol/servers` repo now has only 7 reference servers (Fetch, Filesystem, Git, Memory, Sequential Thinking, Time, Everything/test); the rest were archived. The real ecosystem is the MCP Registry (10,000+ community servers).
- For this project the highest-value MCP servers are: **Filesystem** (read parquet/JSON data files), **SQLite or Postgres** (query modeling DBs), **Playwright or Firecrawl** (scrape sports APIs + odds pages), and a **custom MCP server** wrapping the project's own `predict_matchup` + in-game endpoints.
- Security gotcha: local stdio servers inherit full process privileges -- apply least-privilege at the tool level even locally. Remote servers MUST use OAuth 2.1/PKCE; unauthenticated remote MCP is a real, documented exposure.
- Build once, run anywhere: an MCP server written once works in Claude Code, Cursor, VS Code Copilot, and any other MCP host -- zero re-integration cost per tool.

---

## Key capabilities / techniques

### Architecture layers

```
MCP Host (e.g. Claude Code)
  |
  +-- MCP Client 1 --[stdio]--> Local MCP Server A (Filesystem)
  +-- MCP Client 2 --[stdio]--> Local MCP Server B (SQLite)
  +-- MCP Client 3 --[HTTP/SSE]--> Remote MCP Server C (Sentry, Brave Search...)
```

- **Host**: the AI application (Claude Code, Claude Desktop, Cursor). Manages all client sessions.
- **Client**: one per server, maintains a stateful JSON-RPC channel, handles capability negotiation.
- **Server**: exposes primitives. Local servers serve one client; remote servers serve many.

### Transport types

| Transport | Use case | Auth | Performance | Notes |
|---|---|---|---|---|
| stdio | Same-machine process | None (OS-level) | Best (no network) | Launch server as subprocess; each connection = one client |
| Streamable HTTP | Remote / cloud | OAuth 2.1 + PKCE required | Network-bound | HTTP POST for requests; SSE for streaming; stateless subset possible |

SSE (Server-Sent Events) deprecated as a standalone transport as of protocol version 2025-03-26; Streamable HTTP supersedes it.

### Data-layer primitives (server-side)

- **Tools**: `tools/list` to discover, `tools/call` to invoke. Each has a JSON Schema input spec. Used for: DB queries, API calls, running computations, file writes.
- **Resources**: `resources/list` + `resources/read`. Data sources the LLM reads as context (file contents, schema docs, live standings). Read-only by design.
- **Prompts**: reusable templates with arguments. Good for standardized analytical prompts (e.g. "analyze calibration for this Brier score").

### Client-side primitives (server-to-client)

- **Sampling** (`sampling/createMessage`): server asks the host LLM to complete a sub-task. Enables recursive agent loops without embedding a second LLM key in the server.
- **Elicitation**: server asks the human user for confirmation or additional input mid-task.

### Lifecycle

1. Client sends `initialize` with `protocolVersion` + `capabilities`.
2. Server responds with its own capabilities (which primitives it supports, whether `listChanged` notifications fire).
3. Client sends `notifications/initialized`.
4. Normal operation: `tools/list`, `tools/call`, `resources/read`, etc.
5. Server can push `notifications/tools/list_changed` if its tool set changes dynamically.

### Official reference servers (active, `modelcontextprotocol/servers` repo)

| Server | What it does | R/W |
|---|---|---|
| Filesystem | Secure local file ops (read, write, search) with configurable access controls | R/W |
| Fetch | Fetches any URL, converts HTML to markdown for LLM consumption | R only |
| Git | Read, search, manipulate git repositories | R/W |
| Memory | Knowledge-graph persistent memory (entities + relations) | R/W |
| Sequential Thinking | Dynamic multi-step reasoning through thought sequences | Internal |
| Time | Timezone-aware time queries | R only |
| Everything | Test/demo server exercising all primitives | Demo |

Note: PostgreSQL, SQLite, GitHub, Slack, Google Drive servers were moved to `modelcontextprotocol/servers-archived`. Active community forks exist and are listed in the MCP Registry.

### High-signal community servers (2026)

**Databases**
- `postgres-mcp` (official archived, still widely used): read-only schema inspection + SQL queries against Postgres; safe default for prod DBs.
- `postgres-mcp-pro` (crystaldba): adds health analysis, index tuning, query optimization. Repo: github.com/crystaldba/postgres-mcp
- `sqlite-mcp`: CRUD + schema inspection on local SQLite files; ideal for prototyping and local parquet-converted DBs.
- MindsDB MCP: federated SQL queries across multiple DBs and SaaS APIs in one tool call.

**Browser automation / scraping**
- Playwright MCP (Microsoft): accessibility-snapshot-based browser control; lower token cost than vision-based; 5,600+ FastMCP installs. Best for structured web data (odds tables, box scores from JS-rendered pages).
- Firecrawl MCP (mendableai): converts any URL to clean markdown, strips ads/nav. 85,000+ GitHub stars. Best for bulk page ingestion.
- Puppeteer MCP: screenshot + PDF; useful for visual page verification.

**Search / web data**
- Brave Search MCP: privacy-first web search; $5/1,000 queries; no tracking.
- Tavily MCP: citation-ready snippets; 1,000 free searches/month.
- Exa MCP: semantic / similarity search; good for "find papers like this."

**Filesystem**
- Desktop Commander: terminal access + process management + ripgrep-powered file search; extends native file ops.

**Sports-specific**
- FIFA World Cup 2026 MCP: 18 tools covering matches, teams, standings, odds, bracket, historical matchups; zero external API dependencies. Repo: glama.ai/mcp/servers (search FIFA).
- No NBA/MLB/tennis-specific MCP servers found in current ecosystem -- an open niche.

---

## How THIS project should use it

### 1. Wrap `predict_matchup` as an MCP server (highest leverage)

Build a local stdio MCP server (`scripts/mcp_server/sports_predictor.py`) that exposes:
- `tools/predict_pregame`: takes sport + matchup IDs, returns calibrated probability + Brier-honest confidence interval.
- `tools/predict_ingame`: takes sport + game_id + current score/time, returns live-conditioned probabilities.
- `tools/calibration_report`: runs walk-forward Brier/log-loss for a sport over a date range.
- `resources/edge_map`: returns `docs/research/...` edge map as a resource (LLM reads it as context before reasoning).

This makes every MCP-capable tool (Claude Code, future CI agents, etc.) a first-class predictor client with zero extra API code.

Use Python MCP SDK (`mcp` on PyPI, maintained by Anthropic). Stdio transport is correct for local use -- no auth complexity.

### 2. Filesystem MCP server -> direct parquet/JSON data access

Configure the official Filesystem server pointed at `data/` (read-only) and `vault/` (read-only). Agents can then read signal catalogs, model outputs, and intelligence notes as resources without you writing file-I/O glue code. Restrict write access to avoid accidental data mutation (honor the gitignore-data invariant).

### 3. SQLite MCP -> query modeling outputs interactively

Convert key result tables (walk-forward Brier scores, signal gate results, calibration outputs) to SQLite alongside parquet. Wire the SQLite MCP server so any agent can run `SELECT sport, brier_score FROM calibration_results WHERE split='oos' ORDER BY brier_score` interactively during research sessions. Faster iteration than reading parquet files manually.

### 4. Playwright MCP -> automated odds + box score ingestion

Use Playwright MCP to scrape JS-rendered odds pages (DraftKings, FanDuel public markets) for devigged probability capture without a paid Odds API subscription. Also useful for pulling live box scores from sites that block direct API access. Run as a local stdio server.

### 5. Firecrawl MCP -> bulk ingestion of sports analytics papers and API docs

Point Firecrawl at sports-reference pages, API docs (NBA Stats, Baseball Reference, ATP/WTA stat pages) to ingest clean markdown into the Obsidian vault as Resources. Avoids hand-coding per-site scrapers.

### 6. Build a custom "Sports Data Broker" MCP server

Consolidate data-access tools that today live scattered in `scripts/`:
- `tools/fetch_nba_pbp`: call cdn.nba.com liveData endpoint, return structured PBP.
- `tools/fetch_odds`: devigged market probabilities for a matchup.
- `tools/fetch_box_score`: latest box score for in-game conditioning.

One server, reusable in any future agent or IDE integration. Use caching layer inside the server to avoid re-fetching within a session.

### 7. Memory MCP server -> persistent agent working memory

Use the official Memory server (knowledge graph) to give research agents durable memory of which signals have been tested, which were REJECTed, and what the current Brier baselines are. Prevents agents from re-running experiments already documented in the improvement log.

### 8. Remote MCP for CI/cloud agents (future)

When moving to cloud CI, expose the predictor MCP server via Streamable HTTP. Implement OAuth 2.1 + PKCE (use a library; do not hand-roll). Bind tokens to the specific server using Resource Indicators (RFC 8707). Keep API keys for downstream data sources in a secrets manager (not env vars in the server process).

---

## Gotchas / limits

- **Local stdio = implicit full trust**: a local MCP server runs with the same OS permissions as Claude Code. Scope tool access explicitly (e.g. filesystem server should be pointed at a specific subdirectory, not `/`). Prompt injection via untrusted content in tool results can still cause damage.
- **Unauthenticated remote MCP is a real risk**: a 2026 scan of ~2,000 public remote MCP servers found every verified instance exposed its tool listing without authentication. Do not expose remote MCP without OAuth 2.1.
- **Tool poisoning / prompt injection**: malicious content in a fetched web page or DB result can instruct the LLM to call other tools unexpectedly. Log all tool calls; review agentic sessions; never give a tool the ability to call another tool that has write access to production data.
- **Official server churn**: Anthropic archived the Postgres, SQLite, GitHub, Slack, and Drive reference servers from the main repo. Community forks are active but may lag on security patches. Pin versions.
- **Stateful by default**: MCP is a stateful protocol (connections persist). Long-lived connections to remote servers accumulate risk if tokens are not rotated. Use short-lived tokens + the Tasks primitive (experimental as of 2026) for long-running batch jobs.
- **Sampling adds complexity**: the Sampling primitive (server calls back through the LLM) creates recursive loops that are hard to audit. Avoid it for production prediction pipelines; use it only for internal agent scaffolding.
- **No native Parquet support**: no official MCP server reads `.parquet` directly. Options: convert to SQLite for query access, or write a thin tool in the custom server that uses `pandas.read_parquet` and returns JSON.
- **Python SDK is the primary SDK**: the `mcp` Python package is the most mature. TypeScript SDK also official. Other language SDKs are community-maintained; verify activity before use.

---

## Sources

- [MCP Official Introduction - modelcontextprotocol.io](https://modelcontextprotocol.io/introduction)
- [MCP Architecture Documentation - modelcontextprotocol.io](https://modelcontextprotocol.io/docs/learn/architecture)
- [modelcontextprotocol/servers - GitHub (reference implementations)](https://github.com/modelcontextprotocol/servers)
- [MCP Registry - registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io/)
- [MCP Server Security Best Practices - Descope Engineering Blog](https://www.descope.com/blog/post/mcp-server-security-best-practices)
- [Best MCP Servers in 2026 - OpenclawMCP](https://openclawmcp.com/blog/best-mcp-servers-2026)
- [Complete Guide to MCP 2026 - DEV Community](https://dev.to/x4nent/complete-guide-to-mcp-model-context-protocol-in-2026-architecture-implementation-and-4a11)
- [MCP Cheat Sheet 2026 - Webfuse](https://www.webfuse.com/mcp-cheat-sheet)
- [MCP Security Best Practices 2026 - obot.ai](https://obot.ai/resources/learning-center/mcp-security/)
- [FIFA World Cup 2026 MCP Server - glama.ai](https://glama.ai/mcp/servers?query=FIFA)
- [postgres-mcp-pro - crystaldba GitHub](https://github.com/crystaldba/postgres-mcp)
