# Claude Computer Use and Agentic Browsing
_Researched 2026-06-16. Scope: capabilities, reliability, cost, safety, and fit for sports-data / odds capture automation._

## TL;DR (5-8 bullets: the highest-leverage takeaways)

- Computer use is a **beta API feature** (beta header `computer-use-2025-11-24` required) that gives Claude screenshot capture + mouse/keyboard control inside a sandboxed VM or Docker container; it is NOT a direct OS connection.
- Benchmark scores are strong on paper (OSWorld ~72-83%, WebArena SOTA for single-agent systems) but **real-world task success on dynamic, asynchronous web UIs drops to ~50-60%** -- sportsbook pages and odds feeds are exactly the flaky-UI class that underperforms.
- **Prompt injection is the hard, unsolved problem**: any webpage Claude reads can override its instructions; Anthropic ships a classifier layer to pause and ask for human confirmation, but this layer is not reliable in headless/unattended mode and explicitly cannot be fully bypassed without contacting support.
- **Cost is high and non-obvious**: every screenshot is image-input tokens; every action decision is output tokens; tool definition overhead alone adds ~735 input tokens per call on Claude 4.x; a multi-step browsing session easily costs 5-20x more than a direct API call doing the same data extraction.
- **Execution speed is 5-10x slower than a direct integration** -- sportsbooks update odds in near-real-time; a screenshot-based loop cannot keep pace.
- **For any source that has a real API or structured feed (NBA Stats, ESPN, OddsAPI, Stathead), use the API directly.** Computer use is only justified when NO direct integration exists.
- The Anthropic reference implementation (`anthropic-quickstarts/computer-use-demo` on GitHub) bundles Docker + X11 virtual display + Firefox + an agent loop -- this is the right starting point if you do pursue it.
- Safety requires: dedicated VM with minimal privileges, no sensitive credentials in scope, allowlisted domains only, and a human confirmation gate on any action with real-world consequences (account logins, financial transactions).

---

## Key capabilities / techniques (concrete: names, what they do, when to use)

### What it can do

| Capability | How it works | Notes |
|---|---|---|
| Screenshot capture | Claude sees the current screen state as an image | Every screenshot = image input tokens billed |
| Mouse control | Click, drag, move cursor | Pixel-coordinate targeting; fails on high-DPI / responsive layouts |
| Keyboard input | Type text, keyboard shortcuts | Works well for form filling |
| Desktop automation | Control any app visible on a virtual display | Needs a running X11 display (Xvfb on Linux) |
| Browser navigation | Via Firefox or Chrome inside the VM | Claude decides what to click, type, scroll |
| Bash + text editor augmentation | Can combine with `bash_20250124` and `text_editor_20250728` tools | Adds file I/O and shell commands alongside screen control |

### The agent loop pattern

```
1. Send task + tools to Claude API (with beta header)
2. Claude responds with stop_reason=tool_use + action (screenshot / click / type)
3. Your code executes action in VM, takes screenshot, returns tool_result
4. Repeat until Claude returns stop_reason=end_turn or iteration limit hit
```

The `sampling_loop` pattern (shown in official docs) runs up to N iterations; typical multi-step web tasks take 10-30 iterations.

### Models that support it (as of 2026-06)

- Claude Opus 4.8, Opus 4.7, Opus 4.6, Sonnet 4.6, Opus 4.5 -> beta header `computer-use-2025-11-24`
- Claude Sonnet 4.5, Haiku 4.5 -> older header `computer-use-2025-01-24` (reduced capability)
- Claude Sonnet 4 and Opus 4 (original) -> retired from general API

### Infrastructure required

- Virtual X11 display (Xvfb) or a real display
- Window manager (Mutter + Tint2 is the reference config)
- Docker container is the recommended isolation boundary
- Applications must remain running (NOT serverless)

---

## How THIS project should use it (specific, actionable recommendations)

### Verdict: Do NOT use computer use as a primary data collection pipeline

The sports-data use case is nearly the worst possible fit:
- Sportsbook UIs are asynchronous, frequently updated, and actively anti-scraping
- Odds update faster than the screenshot-action loop can follow (~seconds vs. ~5-10s per iteration)
- Any logged-in session exposes account credentials to prompt injection risk
- Direct APIs exist for most of our data needs (OddsAPI, NBA Stats CDN, Stathead, ESPN)

### Where computer use COULD legitimately help this project (narrow cases)

| Task | Verdict | Why |
|---|---|---|
| Scraping a site with NO public API (obscure foreign soccer league) | Marginal | Use only if no other path; run in isolated VM; domain-allowlist the target only |
| One-off data pull from a paywalled stats tool (e.g., Sports Reference) | Risky | ToS concerns; prompt injection risk; use official data exports instead |
| Verifying a web UI element (e.g., checking the React live board looks correct) | Low-value | Use Playwright + headless Chrome directly instead -- 10x cheaper, 10x faster, deterministic |
| Automated odds snapshot from a single known URL at scheduled intervals | Plausible but brittle | OddsAPI covers this at far lower cost and risk |
| Research browsing agent (find a paper, extract a table) | Best fit | Low-stakes, structured output, no auth required; this is what the feature is actually good at |

### If you DO build a computer-use data agent, follow these guardrails

1. **Isolated Docker container** -- no access to `nba-ai-system` local files, no cloud credentials, no production DB.
2. **Domain allowlist** -- e.g., only `cdn.nba.com`, `stats.nba.com` -- never open internet.
3. **Human gate on any action** -- no autonomous login, no form submission, no financial action.
4. **Short iteration cap** -- set `max_iterations=15`; if not done, fail loudly and log.
5. **Validate output structurally** -- computer use output is unstructured text from screenshots; always re-parse and validate before ingesting into any model or DB.
6. **Use Sonnet 4.6 not Opus** -- Opus costs 3-5x more per token; for data extraction Sonnet 4.6 with computer use is sufficient and cheaper.

### Better alternatives for each data-collection use case

| Data need | Better tool than computer use |
|---|---|
| Live odds | OddsAPI (`/v4/sports/.../odds`) -- REST, structured, real-time |
| NBA play-by-play | `cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{gameId}.json` -- no auth |
| Historical game data | Stathead data exports + local parquet cache |
| European soccer results | Football-Data.org API or OpenLigaDB |
| Tennis results | ATP/WTA official JSON feeds or RapidAPI tennis endpoints |
| MLB Statcast | Baseball Savant bulk CSV downloads |
| Verification / screenshot of live board | Playwright + headless Chromium (deterministic, ~0.1s, free) |

---

## Gotchas / limits

### Prompt injection (critical, no clean fix)

"In some circumstances, Claude will follow commands found in content even if it conflicts with the user's instructions." -- Anthropic official docs, Computer Use page.

The classifier-based defense pauses for human confirmation, which BREAKS unattended pipelines. Turning it off requires contacting Anthropic support AND accepting full liability for autonomous action without that safety net.

Real attack demonstrated (Oasis Security, March 2026): chained invisible prompt injection -> data exfiltration -> C2 connection via a downloaded binary Claude was tricked into executing. This is not theoretical.

### Cost blowup in agentic loops

- Tool definition overhead: ~735 input tokens per API call (Opus 4.x)
- Each screenshot: ~1,000-3,000 input tokens depending on resolution (1024x768 ~ 1,500 tokens)
- A 20-step browsing session on Opus 4.8 ($15/M output tokens): 20 screenshots * 2,000 tokens = 40K image tokens + action outputs. Rough estimate: $1-3 per completed task on Opus; $0.30-0.80 on Sonnet. For recurring data pipelines running hourly, this adds up fast.

### Speed

Each screenshot-action round trip takes 2-8 seconds (model inference + screenshot capture + action execution). A 20-step task takes 40-160 seconds. Structured API calls return in <1 second. For real-time odds capture this is completely unusable.

### Coordinate scaling / resolution fragility

The model targets pixel coordinates. Sportsbook UIs are responsive; layout shifts on scroll, popup modals, and dynamic content will cause misclick failures. The docs recommend using 1024x768 or 1366x768 virtual display and scaling screenshots; even then, failure rates on modern dynamic UIs are significant.

### Beta status

Still formally labeled beta as of June 2026. Anthropic has not committed to a stable API; the beta header version (`computer-use-2025-11-24`) may be superseded. Do not build a production pipeline on it without an explicit fallback.

### Multi-window / tab context loss

Switching between 3+ windows or tabs causes the model to lose track of state; Anthropic engineering notes specifically flag this as a known failure pattern.

### Platforms

The reference implementation runs Linux (X11/Xvfb inside Docker). Running on macOS or Windows natively via the Cowork/Claude Code product requires a paid plan and the desktop app to remain open -- not suitable for server-side automation.

---

## Sources

- [Computer use tool - Claude API Docs (platform.claude.com)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
- [Claude Computer Use API: Architecture, Constraints (claudecode.jp)](https://claudecode.jp/en/news/engineer/dispatch-and-computer-use)
- [Claude Computer Use in 2026: API vs Cowork vs Claude Code (blog.laozhang.ai)](https://blog.laozhang.ai/en/posts/claude-computer-use)
- [Claude Computer Use: A Ticking Time Bomb - prompt.security](https://prompt.security/blog/claude-computer-use-a-ticking-time-bomb)
- [Claude Computer Use: 5 Security Risks You Must Contain (kunalganglani.com)](https://www.kunalganglani.com/blog/claude-computer-use-security-risks)
- [Claude Computer Use API 2026: 72.5% OSWorld Score (tokenmix.ai)](https://tokenmix.ai/blog/claude-computer-use-api-2026)
- [anthropics/anthropic-quickstarts on GitHub (computer-use-demo reference implementation)](https://github.com/anthropics/claude-quickstarts)
- [Claude Code Pricing 2026 (verdent.ai)](https://www.verdent.ai/guides/claude-code-pricing-2026)
