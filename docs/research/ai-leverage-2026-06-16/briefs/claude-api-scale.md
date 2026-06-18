# Claude API at Scale: Cost, Caching, Batching, and Model Routing

_Researched 2026-06-16. Scope: How to run large agentic + eval workloads on the Claude API as cheaply as possible -- prompt caching, Batch API, Files API, token counting, rate tiers, and model routing for a solo sports-prediction platform._

---

## TL;DR (highest-leverage takeaways)

- **Prompt caching is the single biggest lever**: cache reads cost 0.10x base input price (90% off); 5-min write costs 1.25x (breaks even after 1 read); 1-hour write costs 2.0x (breaks even after 2 reads). Cache reads do NOT count against your ITPM rate limit on any current model except Haiku 3.5 (retired).
- **Batch API gives a flat 50% off** on both input and output for any async work (evals, signal scoring, bulk inference); stacks multiplicatively with prompt caching -- combined you can reach ~5% of unoptimized cost on repeated-context workloads.
- **Model routing creates a 5-25x cost spread**: Haiku 4.5 at $1/$5 per MTok vs Opus 4.8 at $5/$25; route grunt tasks (classification, formatting, simple extraction) to Haiku, reserve Opus for hard reasoning and final-pass synthesis.
- **Token counting API** (`POST /v1/messages/count_tokens`) lets you pre-check token counts before submitting, so you can gate on context size, avoid rate-limit surprises, and dynamically choose which model to route to.
- **Cache-aware ITPM** means effective throughput is far higher than the headline limit: at Tier 2 with 80% cache hit rate on Opus 4.x (limit 2M ITPM), you can push 10M total input tokens/minute because cached reads are excluded from the counter.
- **Opus 4.7+ uses a new tokenizer** that can consume up to 35% more tokens for the same text vs older models -- re-measure your typical prompt sizes before deploying.
- **Batch API max_tokens raised to 300k** for Opus 4.6 and Sonnet 4.6 batches; batches typically complete in under 1 hour; results expire after 29 days.

---

## Key capabilities / techniques

### Prompt Caching

**What it does**: Stores a prefix of your prompt server-side so subsequent requests pay only 0.10x for that portion.

**Two modes**:
- Automatic caching: add `cache_control: {"type": "ephemeral"}` at the top level of the request; system manages breakpoints as conversation grows. Recommended starting point.
- Explicit breakpoints: attach `cache_control` to individual content blocks; up to 4 breakpoints per request; useful when you have segments with different change frequencies (e.g., static system prompt + semi-static context + per-request query).

**TTL options**:
- 5-minute: 1.25x base write cost. Breaks even after 1 read. Use for request bursts.
- 1-hour: 2.0x base write cost. Breaks even after 2 reads. Use for long sessions or pre-warmed caches.

**Minimum prompt length to be eligible**:
- Haiku 4.5, Sonnet 4.6, Opus 4.8: 1,024 tokens
- Older Opus 4.x, Haiku 3.5 (retired): 2,048-4,096 tokens (varies)

**What can be cached**: tool definitions, system messages, user/assistant text, images, documents, tool results, prior thinking blocks (when they appear in assistant turns).

**Pre-warming**: send a request with `max_tokens: 0` to load the cache before real traffic hits. Charges only the cache write; produces no output.

**Rate limit benefit**: `cache_read_input_tokens` does NOT count against ITPM on any current model (Haiku 4.5, Sonnet 4.x, Opus 4.x). Effectively multiplies your throughput by 1/(1 - cache_hit_rate).

**Workspace isolation** (since 2026-02-05): caches are isolated per workspace, not per organization. Separate workspaces for prod/dev/eval prevent cross-contamination but also mean you cannot share a warm cache across workspaces.

### Batch API (Message Batches)

**What it does**: Asynchronous bulk inference at 50% off input and output tokens. No streaming, no immediate response.

**How it works**:
1. POST a batch of up to 100,000 requests to `/v1/messages/batches`.
2. Poll the batch status endpoint until `processing_status` is `ended`.
3. Fetch results (JSONL file, one result per request, keyed by `custom_id`).

**Limits per tier**:
- Tier 1: 100k requests in queue, 100k per batch
- Tier 2: 200k in queue, 100k per batch
- Tier 4: 500k in queue, 100k per batch

**Result expiry**: 29 days after creation.
**Typical latency**: most batches finish in under 1 hour.
**Stacks with prompt caching**: both discounts apply simultaneously.
**Does NOT stack with Fast mode** (Fast mode unavailable in batch).
**Not eligible for Zero Data Retention** -- data is retained under standard retention policy.

### Token Counting API

**Endpoint**: `POST /v1/messages/count_tokens`

**What it does**: Returns the exact token count for a message (including tool definitions, system prompt, messages) without making an inference call. No cost charged.

**Use cases**:
- Dynamically route to cheaper model when context is small.
- Gate on context size before submitting to avoid 400 errors.
- Pre-check whether a prompt meets the minimum for caching (1,024 tokens).
- Monitor fleet token budgets programmatically.

### Files API

**What it does**: Upload files (documents, PDFs, images) once and reference them by file_id across multiple requests, avoiding re-uploading the same content.

**Supported on**: Claude API (first-party), Claude Platform on AWS, and Batch API.
**Cost**: standard input token pricing for the content when referenced; no separate file storage fee beyond token costs.

### Model Routing

**Price spread** (per million tokens, input/output):

| Model | Input | Output | Batch Input | Batch Output |
|---|---|---|---|---|
| Haiku 4.5 | $1 | $5 | $0.50 | $2.50 |
| Sonnet 4.6 | $3 | $15 | $1.50 | $7.50 |
| Opus 4.8 | $5 | $25 | $2.50 | $12.50 |

**Rule of thumb**: Haiku is 5x cheaper than Opus on input, 5x cheaper on output. Use Haiku for all high-volume, low-reasoning steps; Sonnet for production inference where quality matters; Opus only where reasoning depth or calibration review is worth the premium.

**Tokenizer warning**: Opus 4.7 and later use a new tokenizer that can use up to 35% more tokens for identical text vs older models. Factor this into cost estimates and minimum-cache-size checks before upgrading.

### Rate Limit Tiers

**Tier advancement**: automatic when cumulative credit purchases hit thresholds.

| Tier | Credit purchase required | Monthly spend limit |
|---|---|---|
| 1 | $5 | $500 |
| 2 | $40 | $500 |
| 3 | $200 | $1,000 |
| 4 | $400 | $200,000 |

**Opus 4.x ITPM limits** (uncached input only):
- Tier 1: 500k ITPM, 50 RPM
- Tier 2: 2M ITPM, 1,000 RPM
- Tier 3: 5M ITPM, 2,000 RPM
- Tier 4: 10M ITPM, 4,000 RPM

**Cache-aware effective ITPM example**: Tier 2 Opus at 2M ITPM limit + 80% cache hit rate -> 10M total input tokens/minute effectively processed.

**Rate limit algorithm**: token bucket (continuous replenishment, not fixed-interval reset). Short bursts can still trigger 429s even if your per-minute average is under the limit.

**Response headers**: `anthropic-ratelimit-input-tokens-remaining`, `anthropic-ratelimit-tokens-reset`, `retry-after` -- read these programmatically rather than hardcoding sleep intervals.

### Fast Mode (Opus 4.6/4.7/4.8 only)

**What it does**: Significantly faster output at premium pricing ($30/$150 per MTok for Opus 4.6/4.7; $10/$50 for Opus 4.8). Research preview.
**Not compatible with Batch API.**
**When to use**: real-time in-game prediction paths where latency matters more than cost.

---

## How THIS project should use it

### 1. Cache the prediction system prompt + signal context (biggest win)

Every call to Opus for a game prediction repeats the same large system prompt (model config, sport rules, signal definitions). Cache that block with a 1-hour TTL. With Opus 4.8 at $5/MTok, a 5k-token system prompt cached and reread 20 times per game costs: 1 write at $0.050 + 20 reads at $0.005 each = $0.15 total vs $0.50 uncached. At eval scale (thousands of games), this is a 3x-5x cost reduction on the dominant token source.

### 2. Run bulk eval workloads via Batch API

The walk-forward backtests, signal-catalog scoring loops, and cross-season OOS validation runs are not latency-sensitive. Submit them as message batches at 50% off. Stacked with prompt caching on the system prompt, a 10k-game eval run through Sonnet 4.6 drops from ~$30 to ~$7 (estimate: 3k tokens/game, Sonnet batch input $1.50/MTok, 80% cache hit).

### 3. Route by task complexity

- **Haiku 4.5**: signal pre-screening, token counting, JSON extraction, simple classification (in-game event type, lineup parsing). At $1/$5 MTok, even high-volume use is nearly free.
- **Sonnet 4.6**: standard production inference -- pregame predictions, in-game re-pricing, calibration scoring. Good quality/cost balance.
- **Opus 4.8**: final cross-sport calibration review, hard reasoning over conflicting signals, autonomous agent loops that plan multi-step tasks. Budget these calls carefully; cache everything reusable.

### 4. Use token counting before expensive Opus calls

Before submitting a large context to Opus, call `count_tokens` to verify size. If the uncached portion is under 2k tokens, skip the cache overhead and route to Sonnet. If over 20k, ensure the cache breakpoint is placed correctly to avoid a full reprocess.

### 5. Pre-warm caches before game-time

Before tip-off, send a `max_tokens: 0` pre-warm request with the full system prompt + static signal context. This ensures the cache is hot for the live in-game re-pricing calls where latency matters. Then use the standard 5-minute TTL and refresh every 4 minutes if the session lasts longer.

### 6. Use Files API for repeated reference documents

The signal catalog, playstyle definitions, and domain rules are large and static. Upload them once via Files API, reference by file_id across all requests in a session. Avoids re-tokenizing the same content; pairs naturally with prompt caching (the file content still benefits from caching once it is in context).

### 7. Monitor cache hit rate on the Usage page

The Claude Console Usage page shows the cache rate for input tokens. Target >70% cache hit rate on eval workloads; if below, check that breakpoint placement is correct (the breakpoint must be on the LAST static block, not a dynamic one).

### 8. Ramp traffic gradually to avoid acceleration limits

The 429 "acceleration limit" fires on sharp usage spikes even if per-minute average is under the cap. For overnight batch runs, submit at a steady rate rather than flooding all 100k requests simultaneously. The token bucket replenishes continuously, so steady submission saturates the bucket without triggering spike detection.

---

## Gotchas / limits

- **Breakpoint placement is everything**: if your `cache_control` tag lands on a block that changes per request (e.g., a timestamp, user query, or per-game context), the prefix hash never matches and you pay cache write cost with zero cache reads. Audit placements carefully.
- **20-block lookback window**: the system searches at most 20 content blocks backward from your breakpoint for a prior cache entry. In long multi-turn conversations, use multiple explicit breakpoints to keep stable content within the window.
- **Concurrent requests and cache**: for parallel requests sharing a cache, the cache entry only becomes available after the FIRST response begins. Send the pre-warm request and wait for its response before firing the parallel fleet.
- **Opus 4.7+ tokenizer change**: up to 35% more tokens for the same text. Re-benchmark your prompt sizes and minimum cache thresholds when upgrading from Opus 4.5/4.6.
- **Batch API retains data**: not eligible for Zero Data Retention. If the project ever processes sensitive personal data, check retention policy implications.
- **Batch result expiry at 29 days**: download and store results before they expire; do not treat the Batch API as a persistent store.
- **Fast mode and Batch API are mutually exclusive**: cannot get both speed and the 50% discount simultaneously.
- **US-only inference_geo adds 1.1x multiplier**: default global routing is cheaper; only opt into US-only if data residency is required.
- **Extended thinking (budget_tokens) deprecated for Opus 4.7+**: Sonnet 4.6 still supports it during transition. If you were using extended thinking for hard calibration reasoning, check which models still support the explicit API.
- **Tool use adds hidden system prompt tokens**: Opus 4.8 adds 290 tokens for `auto` tool choice, 410 for `any`/`tool`. These count against ITPM. In a multi-tool agentic setup with many tool definitions, count_tokens before assuming a call is cheap.
- **Tier 1 Opus ITPM is only 500k/min**: fine for single-game live use, but insufficient for parallel eval fleets. Move to Tier 2 ($40 cumulative spend) to unlock 2M ITPM on Opus.
- **Batch max_tokens 300k**: only for Opus 4.6 and Sonnet 4.6 batches; earlier models have lower limits -- check before sending large-output batch requests.

---

## Sources

- [Prompt caching - Claude API Docs (platform.claude.com)](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Pricing - Claude API Docs (platform.claude.com)](https://platform.claude.com/docs/en/about-claude/pricing)
- [Batch processing - Claude API Docs (platform.claude.com)](https://platform.claude.com/docs/en/build-with-claude/batch-processing)
- [Rate limits - Claude API Docs (platform.claude.com)](https://platform.claude.com/docs/en/api/rate-limits)
- [Claude API Cost Optimization Guide for Enterprises 2026 (cleveroad.com)](https://www.cleveroad.com/blog/claude-api-cost-optimization-enterprise/)
- [Anthropic API Pricing 2026 (finout.io)](https://www.finout.io/blog/anthropic-api-pricing)
- [Claude API Rate Limits April 2026 (tokencalculator.com)](https://tokencalculator.com/blog/claude-api-rate-limits-april-2026)
