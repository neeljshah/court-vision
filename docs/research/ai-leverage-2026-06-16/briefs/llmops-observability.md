# LLMOps / Observability + Reliability for Solo Builders
_Researched 2026-06-16. Scope: minimal, high-leverage observability, tracing, prompt management, guardrails, caching, and evals-in-CI for a solo Python developer running a calibrated sports prediction platform._

## TL;DR (5-8 bullets)

- **Langfuse is the default pick for solo builders**: MIT open-source, self-hostable (Docker Compose), hierarchical trace spans, prompt versioning, LLM-as-judge evals, and a dataset regression harness -- all in one. Acquired by ClickHouse in Jan 2026; architecture now requires Postgres + ClickHouse + Redis for self-host (meaningful but manageable). Cloud free tier exists; $59/mo for managed.
- **Helicone (proxy-based) is the fastest cold start**: route LLM calls through their proxy, get automatic cost + latency logging with zero SDK integration. Acquired by Mintlify (Mar 2026); 100K requests/month free. Best if you just want cost visibility in under 10 minutes; less powerful for evals.
- **Prompt caching is the single highest-ROI cost lever**: Anthropic/Claude requires explicit `cache_control` markup; OpenAI auto-caches prefixes >1024 tokens. Documented savings: 71-85% cost reduction per session past the first turn. The cache is byte-exact and TTL is 5 minutes for ephemeral; any dynamic content (timestamps, per-request IDs) in the cached prefix will bust the cache and turn savings into write-premium costs.
- **Instructor + Pydantic is the production standard for structured output**: pass a Pydantic model as `response_model`, cap `max_retries=3`, and the library feeds the validation error back to the model as a self-correction prompt. Cost: sub-5ms overhead per call. Schema = Enums/Literals for discrete choices, `Field(ge=0, le=1)` for probabilities, custom `field_validator` for business rules.
- **The minimal eval-in-CI pattern is a 50-200 example golden set + a pytest assertion**: run the agent on known inputs, assert schema validity + a quality threshold (Brier score or accuracy), gate the PR on it. No SaaS required; Langfuse can optionally store the dataset and score runs.
- **Semantic caching (Redis + embeddings) yields 60-85% cache hit rates** on repeated/similar queries at 96.9% latency reduction per hit. Only worth adding if >30% of your LLM queries are semantically similar (e.g., the same game-state query pattern across multiple users or cron triggers).
- **LangSmith is the best alternative if you live in LangChain**: 5K traces/month free, native graph visualization, annotation queues, Prompt Hub with A/B testing. Weaker self-host story (enterprise-only). Not recommended for a framework-agnostic stack.
- **Arize Phoenix** (MIT, self-hosted) is worth knowing as a lightweight dev-time tracing alternative -- no cloud dependency, OpenTelemetry-native, good for local debugging before adding a full Langfuse instance.

---

## Key Capabilities / Techniques

### Tracing

| Tool | Model | Free Tier | Self-Host | Best For |
|------|-------|-----------|-----------|---------|
| Langfuse | SDK + async spans | Cloud free tier | Yes (MIT) | Full observability + evals |
| Helicone | Proxy-based | 100K req/mo | Yes (Apache 2.0) | Zero-code cost logging |
| LangSmith | SDK + graph | 5K traces/mo | Enterprise only | LangChain-native teams |
| Arize Phoenix | OpenTelemetry | MIT open-source | Yes | Dev-time local debugging |

**Langfuse trace anatomy**: every LLM call becomes a `generation` span nested inside a `trace`. A trace can contain spans for retrieval, tool calls, sub-agents. Each span records: input, output, token counts, cost, latency, custom metadata. Traces are sent async in the background (no latency impact). Session grouping lets you link multi-turn prediction flows (e.g., pregame -> in-game update -> final output).

**Helicone proxy**: swap `https://api.openai.com` for `https://oai.helicone.ai` in your client init, add one header. No SDK import needed. Works for Anthropic too via its proxy endpoint.

### Prompt Management

Langfuse ships a prompt registry with:
- Named, versioned prompts (major/minor versions)
- A/B variant assignment
- SDK fetch at runtime: `langfuse.get_prompt("game-summary-v2")`
- Rollback to any prior version
- Labels (production / staging / development)

Alternative: store prompts as plain files in Git (`prompts/game_summary.jinja2`) with a version comment header. Simpler, no infra. Sufficient for solo work.

### Cost Dashboards

Minimum viable cost tracking without any SaaS:
```python
# log every LLM call
import csv, time
def log_call(model, input_tok, output_tok, cost_usd, purpose):
    with open("data/llm_costs.csv", "a") as f:
        csv.writer(f).writerow([time.time(), model, input_tok, output_tok, cost_usd, purpose])
```
Visualize with a pandas one-liner or Grafana. Track by `purpose` (pregame / in-game / eval / CI) to find where spend concentrates.

Langfuse cloud dashboard shows: cost-per-trace, token trends, model distribution, p50/p95 latency -- all automatic once you add the SDK.

### Prompt Caching (Anthropic/Claude)

```python
# Mark the static system prompt + large corpus as cacheable
system = [
    {"type": "text", "text": STATIC_SYSTEM_PROMPT,
     "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": large_game_context,
     "cache_control": {"type": "ephemeral"}}
]
# User query goes in messages[], NOT in system[], so it never busts the cache key
```

Rules:
- Cache is byte-exact; any variation in the cached block = full miss + write premium
- Ephemeral TTL = 5 minutes from last access (keep sessions alive or re-warm)
- Never put timestamps, request IDs, or per-game dynamic fields inside the cached block
- First call in a session pays write premium (~25% extra on input); subsequent calls pay ~10% of normal input cost
- Savings are proportional to the ratio of cached tokens to total tokens; works best with large stable system prompts + small dynamic user queries

### Structured Output Validation + Guardrails

**Instructor** (pip install instructor):
```python
import instructor
from pydantic import BaseModel, Field
from anthropic import Anthropic

class PredictionOutput(BaseModel):
    home_win_prob: float = Field(ge=0.0, le=1.0)
    confidence_tier: Literal["high", "medium", "low"]
    reasoning: str = Field(min_length=10, max_length=500)

client = instructor.from_anthropic(Anthropic())
result = client.messages.create(
    model="claude-opus-4-5",
    response_model=PredictionOutput,
    max_retries=3,   # feeds validation error back to model
    messages=[{"role": "user", "content": prompt}],
    max_tokens=1024
)
```

**Layered guardrails**:
1. Schema validation (Pydantic) -- structural + type correctness
2. Field validators -- business rules (prob in [0,1], confidence threshold gates)
3. Retry-with-error-feedback (Instructor) -- up to 3 retries, then raise or use fallback
4. Fallback response -- define a safe default if retries exhausted (never silently return None)

**Validation vs. guardrails distinction**: validation = "is the output well-formed JSON matching the schema"; guardrails = "is the content allowed" (PII, hallucinated player names, out-of-range probabilities). Both are needed. Wire both in sequence.

### Evals-in-CI

Minimal pattern (no SaaS required):
```
tests/evals/
  golden_set.jsonl        # 100-200 input/expected_output pairs
  test_llm_outputs.py     # pytest + schema assertion + quality metric
```

```python
# tests/evals/test_llm_outputs.py
import pytest, json
from your_pipeline import run_prediction

GOLDEN = [json.loads(l) for l in open("tests/evals/golden_set.jsonl")]

@pytest.mark.parametrize("case", GOLDEN[:50])  # 50 cases in CI, full set nightly
def test_schema_valid(case):
    out = run_prediction(case["input"])
    assert 0.0 <= out.home_win_prob <= 1.0
    assert out.confidence_tier in ("high", "medium", "low")

def test_brier_regression():
    results = [run_prediction(c["input"]) for c in GOLDEN]
    probs = [r.home_win_prob for r in results]
    actuals = [c["actual_home_win"] for c in GOLDEN]
    brier = sum((p - a)**2 for p, a in zip(probs, actuals)) / len(actuals)
    assert brier < 0.26  # set threshold from last known-good run
```

Gate the PR on this. Run the full golden set nightly (cheaper, covers more cases). Langfuse can optionally store the dataset and score runs server-side for trend tracking.

---

## How THIS Project Should Use It

This project already uses Claude agents heavily (build agents, research agents, in-game LLM synthesis). The LLM calls are for: prompt-based scheme priors, intelligence synthesis, signal proposers, and the `predict_matchup` command. Here is the prioritized action list:

**Priority 1 -- Prompt caching (immediate, high ROI)**
- The `predict_matchup` and in-game paths pass large static system prompts + sport-specific context. Wrap the static portions in `cache_control: ephemeral` blocks. With a typical 4K-token system prompt and 3-5 follow-up calls per game, estimated savings: 65-75% on input token cost for multi-turn sessions.
- Never put game ID, timestamp, or dynamic score in the cached block.

**Priority 2 -- Instructor + Pydantic schemas on all LLM outputs (immediate, reliability)**
- The scheme prior (`src/sim/scheme_prior.py`) and any LLM-synthesizer calls should return a typed Pydantic model, not raw text. This prevents pipeline crashes when the model returns malformed JSON. Cap retries at 3 and define a neutral fallback (e.g., `multiplier=1.0` for scheme priors) so the sim always gets a valid number.
- Pin enums for scheme names and confidence tiers to prevent hallucinated values from silently corrupting prediction inputs.

**Priority 3 -- Minimal cost CSV logging (immediate, no infra)**
- Add a `log_llm_call(model, purpose, input_tok, output_tok, cost)` wrapper around every Claude/OpenAI call. Log to `data/llm_costs.csv` (already gitignored). Review weekly. This alone will surface which pipeline stage dominates spend.

**Priority 4 -- 50-example golden eval set in CI (medium, highest long-term value)**
- Build a `tests/evals/golden_set.jsonl` with 50 game prediction inputs + known-good outputs (schema valid + Brier < threshold). Run in CI on every model or prompt change. This is the only way to catch prompt regressions before they corrupt OOS prediction quality -- which is the north star metric.
- Do NOT use model output as the ground truth label; use actual game outcomes (already in `data/`). Keep the eval set strictly OOS relative to any training data.

**Priority 5 -- Langfuse self-hosted (medium, when you want trace history)**
- Docker Compose brings up Langfuse + Postgres + ClickHouse + Redis. Instrument the `predict_matchup` flow with `@observe` decorators. You get full trace history for every prediction run, which makes debugging calibration regressions much easier (compare exact prompts + outputs across runs).
- Alternative: use Langfuse Cloud free tier if you do not want to run the infra. Traces are async and add zero latency.

**Priority 6 -- Semantic caching (lower priority, conditional)**
- Only worth adding if the same game-state query is issued multiple times per session (e.g., a front-end polling pattern). The current architecture does not appear to have high query overlap, so skip until query volume grows.

---

## Gotchas / Limits

- **Helicone acquisition risk**: Mintlify acquired Helicone (Mar 2026); product direction is uncertain. Do not build hard dependencies on Helicone if you want stability. Langfuse (now ClickHouse-backed) is more stable.
- **Langfuse self-host infra is now heavier**: v3 requires Postgres + ClickHouse + Redis. On a Windows dev box, Docker Compose works but consumes real RAM. Cloud free tier is the easier start.
- **Prompt cache is byte-exact, not semantic**: the slightest wording change in the cached block (even a space) busts the cache and charges the write premium. Treat the cached system prompt as a versioned artifact; change it deliberately.
- **Ephemeral cache TTL = 5 minutes**: for batch-style prediction runs triggered by cron at long intervals, the cache will be cold on every run. You pay the write premium but get no savings. Use extended caching (where available) or structure batch calls to run within the 5-minute window.
- **Instructor retries consume context**: each retry appends the validation error to the conversation. With `max_retries=3` and a complex schema, a worst-case triple-retry on a 4K context can balloon to 12K+ tokens. Budget for this or use a smaller schema for the retry path.
- **Evals in CI cost real tokens**: running 50 golden-set cases per PR at frontier model prices can add up ($0.10-0.50/run depending on prompt length). Use a cheaper model (Haiku / GPT-4o-mini) for CI evals; reserve the full model for nightly regression runs.
- **LLM-as-judge evals can be biased toward their own outputs**: do not use Claude to judge Claude predictions on the same game without a clear rubric tied to actual outcomes. Use actual game results (Brier/log-loss) as the primary eval metric; LLM-as-judge is useful only for qualitative reasoning quality.
- **Semantic caching introduces non-determinism**: two "similar" queries that cache-hit to the same response may get different answers if the cache threshold is too loose. Set cosine similarity threshold >= 0.95 for prediction paths where precision matters.

---

## Sources

- [Langfuse Observability Docs (langfuse.com)](https://langfuse.com/docs/observability/overview)
- [Langfuse Self-Hosting (langfuse.com)](https://langfuse.com/self-hosting)
- [GitHub: langfuse/langfuse](https://github.com/langfuse/langfuse)
- [Top 5 LLM Observability Platforms 2026: Langfuse vs LangSmith vs Helicone vs Arize vs W&B (guptadeepak.com)](https://guptadeepak.com/tools/top-5-llm-observability-platforms-2026/)
- [Best LLM Observability Tools in 2026 (firecrawl.dev)](https://www.firecrawl.dev/blog/best-llm-observability-tools)
- [Top 7 LLM Observability Tools in 2026 (confident-ai.com)](https://www.confident-ai.com/knowledge-base/compare/top-7-llm-observability-tools)
- [Langfuse vs Helicone vs Portkey: LLM Observability Compared (buildmvpfast.com)](https://www.buildmvpfast.com/blog/llm-observability-stack-langfuse-helicone-portkey-2026)
- [Prompt Caching Cost Optimization: 80% Savings (web2md.org)](https://web2md.org/blog/prompt-caching-cost-optimization-guide-2026)
- [LLM Cost Optimization: Caching, Batching, Smart Routing (gmicloud.ai)](https://www.gmicloud.ai/en/blog/llm-inference-cost-optimization-caching-batching-routing)
- [AI Agent Guardrails and Output Validation 2026 (toolhalla.ai)](https://toolhalla.ai/blog/ai-agent-guardrails-io-validation-2026)
- [Mastering LLM Guardrails: Complete 2026 Guide (orq.ai)](https://orq.ai/blog/llm-guardrails)
- [LLMOps Guide 2026: Build Fast, Cost-Effective LLM Apps (redis.io)](https://redis.io/blog/large-language-model-operations-guide/)
- [LLM Observability with Self-Hosted Langfuse and vLLM (pyimagesearch.com)](https://pyimagesearch.com/2026/05/18/llm-observability-with-self-hosted-langfuse-and-vllm/)
