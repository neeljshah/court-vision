# Prompt Caching and Batch API Plan

## 1. Prompt Caching for Static Context

### What to cache

The signal catalog and vault context are large and nearly static (updated once per rebuild,
not per call). They are ideal cache-breakpoint candidates.

Target content blocks:
| Block                                  | Est tokens | Cache benefit |
|----------------------------------------|-----------|---------------|
| vault/Intelligence/_Simulation_Signals.md | ~8K    | High          |
| scripts/platformkit/adapter_interface_spec.py | ~3K | High       |
| CLAUDE.md + docs/JOB_EVIDENCE_PACKET.md  | ~6K    | High          |
| Active sport signal catalog snapshot    | ~5K      | High          |
| Total static context                    | ~22K     | ~$0.02 saved per 100 calls |

### How to apply cache breakpoints (Anthropic SDK)

Prompt caching is controlled via `cache_control: {"type": "ephemeral"}` on content blocks.
Cache lifetime: 5 minutes (ephemeral). Reads cost 10% of write price after first hit.

```python
import anthropic

client = anthropic.Anthropic()

STATIC_CONTEXT = open("vault/Intelligence/_Simulation_Signals.md").read()
SPEC_CONTEXT = open("scripts/platformkit/adapter_interface_spec.py").read()

def call_with_cache(user_prompt: str, model: str = "claude-haiku-4-5") -> dict:
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": STATIC_CONTEXT,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": SPEC_CONTEXT,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response
```

Key rules:
- Cache breakpoints must appear in the SAME position across calls to hit the cache.
- Do NOT include any dynamic content (timestamps, game IDs) before the cache breakpoint.
- Dynamic per-call content goes AFTER the last cache_control block.
- Cache is per-account, per-model. Switching model = cache miss.

### Recommended wrapper location

`scripts/platformkit/obs/cached_client.py` -- a thin wrapper around anthropic.Anthropic()
that pre-loads static context once at module import and attaches cache_control blocks.
All nightly jobs import from this wrapper instead of instantiating their own clients.

```python
# scripts/platformkit/obs/cached_client.py (to be written)
# Pattern:
#   from scripts.platformkit.obs.cached_client import cached_complete
#   result = cached_complete(user_prompt="...", model="claude-haiku-4-5")
```

### Cache hit verification

Check `response.usage.cache_read_input_tokens` vs `response.usage.cache_creation_input_tokens`.
If cache_read > 0, the cache hit. Log both to cost_ledger.parquet.

```python
usage = response.usage
cache_hit = usage.cache_read_input_tokens > 0
savings_usd = usage.cache_read_input_tokens * HAIKU_CACHE_READ_PRICE_PER_TOKEN
```

---

## 2. Batch API Plan (50% cost reduction for nightly bulk work)

### What is the Batch API

Anthropic's Message Batches API processes requests asynchronously at 50% off standard pricing.
Batch results are available within 24 hours (typically 1-4 hours for small batches).
Batches can contain up to 10,000 requests, each up to the standard token limits.

Reference: https://docs.anthropic.com/en/docs/build-with-claude/batch-processing

### Use cases in this system

| Job                          | Batch-able? | Reason                                |
|------------------------------|-------------|---------------------------------------|
| Nightly bulk enrichment      | YES         | ~30-150 player/team nodes to update   |
| Backtest signal evaluation   | YES         | Many independent signal assessments   |
| Vault node regeneration      | YES         | Each node is independent              |
| Eval gate (time-sensitive)   | NO          | Needs results before 06:00 UTC tipoff |
| Benchmark (sequential steps) | NO          | Pipeline steps are dependent          |
| Calibration drift alert      | PARTIAL     | Alert is urgent; pre-computation is not |

### Batch API usage pattern

```python
import anthropic
import time

client = anthropic.Anthropic()

def submit_enrichment_batch(player_ids: list, signal_context: str) -> str:
    """Submit a batch of player enrichment requests. Returns batch_id."""
    requests = []
    for pid in player_ids:
        requests.append({
            "custom_id": f"enrich_{pid}",
            "params": {
                "model": "claude-haiku-4-5",
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": f"{signal_context}\n\nEnrich player {pid}. "
                                   "Output JSON with keys: form, matchup_edge, vault_delta."
                    }
                ]
            }
        })

    batch = client.beta.messages.batches.create(requests=requests)
    return batch.id


def poll_batch(batch_id: str, poll_interval_s: int = 60) -> list:
    """Poll until batch complete, return list of (custom_id, result) tuples."""
    while True:
        batch = client.beta.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        time.sleep(poll_interval_s)

    results = []
    for result in client.beta.messages.batches.results(batch_id):
        results.append((result.custom_id, result.result))
    return results
```

### Nightly bulk enrichment schedule

Suggested cron job (scripts/cron/nightly_batch_enrich.sh):

```bash
#!/usr/bin/env bash
# 1. Submit batch at 23:00 UTC (off-peak, results back by 03:00 UTC)
# 2. Poll + apply results at 04:30 UTC (after cal_drift check)
set -euo pipefail
python scripts/platformkit/batch_enrichment.py --submit --sport nba
```

And the apply step at 04:30:
```bash
python scripts/platformkit/batch_enrichment.py --apply --sport nba
```

Cron lines:
```
0 23 * * * cd /c/Users/neelj/nba-ai-system && python scripts/platformkit/batch_enrichment.py --submit --sport nba >> data/ops/cron_batch.log 2>&1
30 4 * * * cd /c/Users/neelj/nba-ai-system && python scripts/platformkit/batch_enrichment.py --apply --sport nba >> data/ops/cron_batch.log 2>&1
```

### Backtest signal evaluation via batch

For signal_catalog evaluation (each signal is independent):
- Submit one request per signal candidate
- Each request asks: "Given corpus X, does signal Y pass the gate?"
- 50% cost reduction on what can be 60-100 requests per evaluation cycle
- Batch turnaround fits within overnight window (submit at 22:00, results at 01:00)

Estimated savings for a 60-signal evaluation batch:
- Standard: 60 x ~$0.005 = ~$0.30
- Batch (50% off): ~$0.15
- Monthly (2 evaluations/week): ~$1.20 -> $0.60

---

## 3. Combined strategy: cache + batch together

For nightly batch enrichment, use prompt caching INSIDE each batch request:
- Each batch request includes the static signal catalog with cache_control
- Cache hits within a batch are billed at 10% of normal read price
- Combined savings: ~50% (batch) + additional ~15-20% (cache hits within batch)
- Note: cache is warm from the prior nightly cron run (same 5-min ephemeral window
  does NOT apply across batch jobs; cache must be pre-warmed separately if needed)

For multi-sport batches: submit sport-grouped sub-batches to maximize cache reuse
(same static context block = higher cache hit rate within the batch).

---

## 4. Implementation order

1. Write `scripts/platformkit/obs/cached_client.py` -- cache wrapper for all nightly jobs
2. Update nightly_eval_gate.sh and nightly_cal_drift.sh to import cached_client
3. Write `scripts/platformkit/batch_enrichment.py` (--submit / --apply pattern)
4. Add batch job to cron (nightly_batch_enrich.sh)
5. Add cache_read_input_tokens logging to cost_ledger.py columns
6. Monitor cache hit rate for 1 week; tune breakpoint placement if hit rate < 70%

---

## 5. What NOT to cache

- Any content that changes per game/date (current scores, live PBP)
- Prompt content containing session IDs or run timestamps
- System prompts with dynamic game context (these defeat the cache breakpoint)
- Anything that must reflect the latest vault rebuild (check rebuild timestamp vs cache age)
