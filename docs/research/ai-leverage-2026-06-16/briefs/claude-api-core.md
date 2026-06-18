# Claude API Core for Builders
_Researched 2026-06-16. Scope: Tool use, structured outputs, extended thinking, streaming, vision/PDF, citations, message batches, and model selection for a solo-built calibrated sports prediction platform._

---

## TL;DR (5-8 bullets: the highest-leverage takeaways)

- **Sonnet 4.6 is the practical default** for this project: $3/$15 per MTok, 1M context, 64k output, fast, supports extended thinking and adaptive thinking -- Haiku 4.5 ($1/$5) for high-volume sub-tasks (enrichment, feature extraction); Opus 4.8 ($5/$25) only when multi-step agentic quality matters; Fable 5 ($10/$50) only for the most demanding frontier work.
- **Structured outputs (JSON schema + Pydantic) are GA** on all current models including Fable 5: use `client.messages.parse()` with a Pydantic model to get validated, schema-guaranteed JSON for prediction outputs, feature dicts, calibration summaries -- no regex fallback needed.
- **Tool use (function calling) is the highest-leverage primitive**: client tools (your Python functions: DB lookups, odds fetchers, stat APIs) + server tools (web_search, code_execution) let a single Claude call orchestrate multi-step data pipelines; `strict: true` on tool definitions guarantees type-valid inputs.
- **Extended thinking (budget_tokens) is best on Sonnet 4.6 / Haiku 4.5** -- NOT on Opus 4.8 or Fable 5 which use always-on adaptive thinking instead; use for complex multi-step calibration analysis, signal design, or agentic reasoning; skip for simple lookups.
- **Streaming is required** when max_tokens > ~21k and is straightforward via `client.messages.stream()`; extended thinking + streaming emit `thinking_delta` events before `text_delta` -- pass thinking blocks back unchanged in multi-turn tool loops.
- **Citations** are supported on all active models (not Haiku 3): pass documents with `citations: {enabled: true}` to get sentence-level grounded claims with zero extra output-token cost for `cited_text`; reportedly incompatible with structured outputs -- verify before combining.
- **Message Batches API** gives 50% cost reduction + up to 300k output tokens per request (via beta header `output-300k-2026-03-24`) -- ideal for walk-forward backtests, bulk signal evaluation, and nightly enrichment runs where latency is not critical.
- **Prompt caching cuts cached-input cost by 90%** -- attach `cache_control: {type: "ephemeral"}` to your system prompt and large context (signal catalogs, vault summaries, game history); works with citations and batches; a 1-hour cache duration is available for long-running agentic tasks.

---

## Key capabilities / techniques (concrete: names, what they do, when to use)

### Model Lineup (as of 2026-06-16)

| Model | API ID | Pricing (in/out per MTok) | Context | Max Output | Extended Thinking | Adaptive Thinking | Best for |
|---|---|---|---|---|---|---|---|
| Claude Fable 5 | `claude-fable-5` | $10 / $50 | 1M | 128k | No | Yes (always on) | Frontier agentic, most demanding reasoning |
| Claude Mythos 5 | `claude-mythos-5` | $10 / $50 | 1M | 128k | No | Yes (always on) | Invite-only (Project Glasswing), cybersec |
| Claude Opus 4.8 | `claude-opus-4-8` | $5 / $25 | 1M | 128k | No | Yes | Complex reasoning, long-horizon agentic coding |
| Claude Opus 4.7 | `claude-opus-4-7` | $5 / $25 | 1M | 128k | No | Yes | Vision-heavy workflows, legacy |
| Claude Opus 4.6 | `claude-opus-4-6` | $5 / $25 | 1M | 128k | Yes | Yes (deprecated in favor) | Still usable with manual extended thinking |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | $3 / $15 | 1M | 64k | Yes | Yes | Best speed/intelligence balance; **recommended default** |
| Claude Haiku 4.5 | `claude-haiku-4-5` | $1 / $5 | 200k | 64k | Yes | No | High-volume, sub-agent tasks, real-time |

Note: Opus 4.8 knowledge cutoff = Jan 2026; Sonnet 4.6 reliable cutoff = Aug 2025. Opus 4.8 defaults `effort` to `high`; use `xhigh` for the most demanding agentic/coding passes.

### Tool Use / Function Calling

Two flavors:
- **Client tools**: You define the function schema; Claude emits `tool_use` blocks; your code executes them; you return `tool_result`. Pattern: `stop_reason = "tool_use"` -> execute -> loop.
- **Server tools**: Anthropic-hosted (web_search `web_search_20260209`, code_execution, web_fetch) -- you just see results, no execution loop.

Key parameters:
- `tool_choice`: `{"type": "auto"}` (default), `{"type": "any"}` (force a tool call), `{"type": "tool", "name": "X"}` (force specific tool).
- `strict: true` on a tool definition -> grammar-constrained sampling guarantees schema-valid inputs. Limit: 20 strict tools per request, 24 total optional params, 16 union-typed params.
- Tool system prompt overhead: ~290-590 tokens depending on model + `tool_choice` type.

### Structured Outputs (JSON)

Two complementary mechanisms:
1. `output_config.format` with `type: "json_schema"` -> guaranteed valid JSON response matching your schema.
2. `strict: true` on tool definitions -> guaranteed valid tool inputs.

Best Python pattern: `client.messages.parse(output_format=MyPydanticModel, ...)` -> `response.parsed_output` already validated.
TypeScript: `zodOutputFormat(MyZodSchema)` helper.

Schema constraints:
- The official SDKs auto-transform unsupported constraints rather than reject: `additionalProperties: false` is injected automatically, and unsupported constraints (numerical bounds like `minimum`/`maximum`/`minLength`, complex regex) are silently stripped or folded into descriptions -- they are generally not user-facing errors when using the SDK helper.
- Recursive schemas NOT supported (no auto-transform; will error).
- `anyOf` supported (limited).
- Grammar cached for 24h; changing name/description does NOT bust cache but changing schema does.
- Max 20 strict tools per request.

Reportedly incompatible with citations -- verify before combining (behavior may have changed).

### Extended Thinking

Manual mode (`thinking: {type: "enabled", budget_tokens: N}`):
- Supported: Sonnet 4.6, Haiku 4.5, Opus 4.6, Opus 4.5 and earlier 4.x.
- NOT supported (returns 400): Fable 5, Mythos 5, Opus 4.8, Opus 4.7 -- use adaptive thinking (`thinking: {type: "adaptive"}`) for these.
- `budget_tokens` must be < `max_tokens`; Claude may use less; quality improves up to ~32k.
- Response includes `thinking` content blocks (internal chain of thought) + `text` blocks.
- Streaming required when max_tokens > ~21k; emits `thinking_delta` events.
- `display: "summarized"` (default on 4.x) -> compact summary visible; `display: "omitted"` -> empty thinking field but signature preserved (faster streaming, use when you don't show thinking to users).
- You are billed for full thinking tokens even with summarized/omitted display.
- In multi-turn tool loops: MUST pass thinking blocks back unchanged in the assistant turn.
- With tool use: only `tool_choice: auto` or `none` allowed (cannot force tool with thinking enabled).

Adaptive thinking (Fable 5, Opus 4.8, Opus 4.7):
- Always on, no budget_tokens parameter.
- Use `effort` parameter (`low`/`medium`/`high`/`xhigh`/`max`) to tune compute vs latency within a model.

### Streaming

Enable with `stream: true` or use `client.messages.stream()`.
- SSE event types: `message_start`, `content_block_start`, `content_block_delta` (subtypes: `text_delta`, `thinking_delta`, `citations_delta`, `input_json_delta` for tools), `content_block_stop`, `message_delta`, `message_stop`.
- Python SDK: `with client.messages.stream(...) as stream: for text in stream.text_stream` or handle events directly.
- Extended thinking + streaming: handle `thinking_delta` before `text_delta`; with `display: "omitted"` no thinking deltas sent (lower latency).
- Required when `max_tokens` > ~21,333.

### Vision and PDF Support

- All current Claude models support image input (JPEG, PNG, GIF, WEBP).
- Images can be sent as base64 or URL (`{"type": "image", "source": {"type": "url", "url": "..."} }`).
- PDFs: pass as `{"type": "document", "source": {"type": "base64" | "url" | "file", ...}}` -- Claude extracts text + understands charts/visuals.
- URL source blocks (images + PDFs) avoid base64 encoding overhead.
- PDF image citations not yet supported (text-only citations from PDFs).

### Citations

- Enable per-document: `citations: {enabled: true}` on each document block.
- Document types: plain text (sentence chunking -> char indices), PDF (sentence chunking -> page numbers), custom content (your chunks -> block indices).
- `cited_text` field in response does NOT count toward output tokens or input tokens on re-use.
- Works with prompt caching: apply `cache_control` to document blocks.
- Streaming: emits `citations_delta` events.
- Reportedly incompatible with structured outputs -- verify before combining.
- Use `context` field (not `title`) to embed metadata that won't be cited but is visible to the model.
- All active models supported except Haiku 3 (retired).

### Message Batches API

- Submit up to many requests as a single batch; processed asynchronously (most < 1 hour).
- 50% cost reduction vs synchronous API.
- Extended output beta header `output-300k-2026-03-24`: allows up to 300k output tokens per request for Opus 4.8, 4.7, 4.6, Sonnet 4.6 via Batches.
- Poll for status or use webhooks.
- NOT eligible for Zero Data Retention (data retained per standard policy).
- Ideal for: bulk backtest runs, nightly signal evaluation, large walk-forward sweeps.

### System Prompts and Prompt Caching

- Prompt caching: 90% cost reduction on cached input tokens; attach `cache_control: {type: "ephemeral"}` to system prompt blocks, large context docs, or conversation history.
- 1-hour cache duration available for long agentic sessions.
- Changing thinking budget invalidates message cache (not system prompt cache).
- Grammar cache for structured outputs: 24h, invalidated by schema change.

---

## How THIS project should use it (specific, actionable recommendations)

### Model routing for the sports prediction platform

```
Nightly enrichment / bulk feature extraction   -> Haiku 4.5 + Batches (50% cheaper, 200k ctx)
Signal analysis / research pass (walk-forward) -> Sonnet 4.6 (1M ctx, fast, $3/$15)
Complex agentic pipeline orchestration         -> Sonnet 4.6 with effort=high or Opus 4.8
Deep multi-step calibration audits             -> Opus 4.8 or Fable 5 (1M ctx, 128k output)
Real-time in-game React board updates          -> Haiku 4.5 (fastest, lowest latency)
```

### Structured outputs for prediction pipeline

Use `client.messages.parse()` with Pydantic to emit type-safe prediction dicts:
```python
class GamePrediction(BaseModel):
    home_win_prob: float
    calibrated_brier: float
    confidence_tier: str  # "high" | "medium" | "low"
    signals_used: list[str]
    walk_forward_validated: bool
```
This replaces fragile JSON prompt engineering and retry loops. Works GA on Sonnet 4.6 and all current models.

### Tool use for data orchestration

Define client tools for: odds API fetch, stat DB lookup, vault note read, walk-forward gate call.
Use `tool_choice: {"type": "auto"}` + `strict: true` so Claude orchestrates the multi-step enrichment loop and inputs are always type-valid.
Server tool `web_search_20260209` can supplement with live data (player injury news, lineup updates) without a separate API key.

### Extended thinking for calibration design

On Sonnet 4.6, enable `thinking: {type: "enabled", budget_tokens: 16000}` when asking Claude to:
- Design a new signal and reason through leak-free OOS validation steps.
- Audit a calibration curve and propose a recalibration approach.
- Plan a multi-step walk-forward backtest.

Skip extended thinking for routine inference calls -- it adds latency and token cost.

### Citations for grounded vault intelligence

When Claude reasons over vault notes (team atlases, signal catalogs), enable citations so every claim in the output is grounded to a specific sentence in your Obsidian notes. This makes the pipeline auditable: you can trace each prediction modifier back to its source document. Cache vault documents with `cache_control` to cut cost by 90% across repeated queries in a session.

### Batches for walk-forward backtests

Submit the full walk-forward game list as a batch at nightly schedule:
- 50% cheaper than synchronous.
- Up to 300k output tokens per game (beta header) -- enough for full reasoning traces.
- Non-blocking: kick off at end of day, results ready in < 1 hour.

### Streaming for the React live board

Use `client.messages.stream()` on Haiku 4.5 for real-time in-game prediction updates:
- Stream `text_delta` events directly to the React board via SSE.
- Keep `max_tokens` < 21k to avoid mandatory streaming mode restriction (or just always stream).
- For in-game extended thinking, use `display: "omitted"` so thinking tokens don't add wire latency.

---

## Gotchas / limits

- **Extended thinking + Opus 4.8 / Fable 5**: manual `budget_tokens` returns a 400 error; use adaptive thinking (`effort` param) instead.
- **Structured outputs + Citations**: reportedly incompatible -- verify before combining (behavior may have changed; soften assumption of a guaranteed 400).
- **Recursive schemas**: not supported in structured outputs (not auto-transformed; will error).
- **Numerical constraints** (`minimum`, `maximum`, `minLength`): SDK auto-strips/folds these into descriptions rather than rejecting -- generally not a user-facing error via the SDK helper.
- **Grammar cache**: first request per schema incurs compilation latency; cache lasts 24h; only schema changes (not name/description) bust it.
- **Thinking blocks in multi-turn tool loops**: MUST be passed back unchanged; modifying them returns 400.
- **Tool choice restriction with extended thinking**: only `auto` or `none` allowed; cannot force a specific tool.
- **Opus 4.7 new tokenizer**: 30% more tokens for the same text compared to pre-4.7 models -- budget accordingly.
- **Batches not ZDR-eligible**: data retained per standard policy; don't batch requests with sensitive PII if ZDR is required.
- **Haiku 4.5 context**: only 200k tokens (vs 1M for Sonnet 4.6 / Opus 4.8) -- not suitable for full-vault in-context reasoning.
- **Sonnet 4.6 max output**: 64k tokens (vs 128k for Opus 4.8 / Fable 5) -- use Opus/Fable for very long generation tasks.
- **Opus 4.1 deprecated**: retires August 5, 2026; migrate to Opus 4.8.
- **Batch output 300k beta**: only for Opus 4.8, 4.7, 4.6, Sonnet 4.6 via Batches API; requires explicit beta header.
- **`cited_text` not counted** toward output tokens but IS visible in response and NOT counted toward input tokens on re-use -- still count it for context window budgeting.

---

## Sources

- [Claude Models Overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Choosing a Model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model)
- [Tool Use Overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Strict Tool Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use)
- [Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Extended Thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)
- [Adaptive Thinking](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking)
- [Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [Citations](https://platform.claude.com/docs/en/build-with-claude/citations)
- [PDF Support](https://platform.claude.com/docs/en/build-with-claude/pdf-support)
- [Batch Processing / Message Batches API](https://platform.claude.com/docs/en/build-with-claude/batch-processing)
- [Claude Opus 4.6 announcement](https://www.anthropic.com/news/claude-opus-4-6)
- [Anthropic API pricing comparison (third-party)](https://www.metacto.com/blogs/anthropic-api-pricing-a-full-breakdown-of-costs-and-integration)
