# AI / Model Landscape Beyond Claude -- June 2026
# For: solo-built calibrated multi-sport prediction platform (Claude-Code-centric)
# Audience: the builder, not a reader -- concrete and skeptical

---

## TL;DR

Stay Claude-first for all agentic build work, reasoning chains, and code generation.
The gap between Claude Opus 4.8 and competitors on SWE-bench and multi-step agents
is real and measurable. Use Gemini Flash or DeepSeek for cheap bulk inference when
latency tolerance is high. Run Qwen3-8B or DeepSeek-R1-8B locally on the RTX 4060
for private/offline extraction, adversarial cross-checking, and cost-free iteration.
Use an open-weight embedding model (Qwen3-Embedding or BGE-M3, self-hosted) for the
vault RAG layer -- the quality now beats OpenAI's hosted embeddings by ~7-10 MTEB
points and costs near zero at this project's scale.

---

## 1. FRONTIER MODEL LANDSCAPE (hosted/API)

### Claude Opus 4.8 (Anthropic)
- SWE-bench Verified: 83.5% -- current leader for coding agents
- Intelligence Index rank 1 (LM Council, June 2026)
- Multi-turn agentic chains and complex instruction following: best in class
- Pricing: $5/$25 per 1M tokens (in/out)
- Weakness: most expensive output; slower on pure math than GPT-5.5 Pro
- For this project: the right primary model -- already in use

### GPT-5.5 (OpenAI)
- SWE-bench: 80.6% -- strong but behind Claude on agentic tasks
- FrontierMath Tier 4: 39.6% -- best pure math of the public flagship set
- GPQA Diamond: 94.6% -- top science reasoning
- Pricing: $5/$30 standard; $30/$180 Pro tier
- Best for this project: a second-opinion math/stats verification call (adversarial
  cross-check) where you want a different training run than Claude
- Weakness: pricier for long-context agentic loops; smaller context efficiency

### Gemini 3.1 Pro / 3.5 Flash (Google)
- Gemini 3.1 Pro: 94.1% GPQA Diamond, 46.4% Humanity's Last Exam (top reasoning)
  -- native Google Search grounding, 1M token context
- Gemini 3.5 Flash: ~40% cheaper than Pro, best price-performance for bulk agent tasks
  -- pricing $1.50/$9.00 (Flash) vs $2-$4/$12-$18 (Pro)
- Best for this project: bulk enrichment calls (stats lookups, text summarization at
  scale, cheap pre-screening before expensive Claude calls); Flash at $1.50/1M in is
  the cheapest capable hosted option after DeepSeek
- Weakness: ecosystem and tooling less mature than Claude Code integration; multimodal
  strength not needed for this text/tabular project

### Grok 4.3 (xAI)
- Native X/Twitter grounding -- genuine real-time signal ingestion
- 1M-2M token context, cheapest flagship pricing: $1.25/$2.50 per 1M
- GPQA and reasoning: competitive (arena Elo top-5)
- Best for this project: if you ever need real-time sports news/injury grounding at
  minimal cost; NOT the right choice for agentic coding or multi-step build work
- Weakness: smallest ecosystem; fewer Claude Code-equivalent integrations; guardrails
  are looser which can produce overconfident outputs (a problem for calibration work)

### Mistral Large 3
- Rank 2 among open-source models on LMArena (June 2026)
- Good coding, low cost via self-hosted or Mistral API (~$2/$6 per 1M on API)
- Best for this project: viable cheap adversarial reviewer if you want to avoid
  OpenAI/Google lock-in; weaker than Claude on complex agentic chains
- The quality gap between open and closed frontier is now small for single-turn tasks

### DeepSeek V4-Flash (open-weight, MIT license)
- Intelligence Index 47; 1M context; $0.14/$0.28 per 1M via hosted API
- The cheapest frontier-adjacent hosted option by a large margin
- Best for this project: high-volume pre-screening, cheap batch label generation,
  any task where you want 100k+ calls without budget concern
- Weakness: reasoning on complex multi-step agentic work lags Claude by ~15-20%

---

## 2. OPEN-WEIGHT MODELS FOR LOCAL INFERENCE (RTX 4060 8GB)

### Hard constraints
- 8GB VRAM: 7B-8B parameter models at Q4_K_M quantization are the practical ceiling
- Q4_K_M: 4-5GB VRAM, ~30-50 tok/s on RTX 4060
- Q5_K_M: slightly better quality, ~25-40 tok/s -- use when quality matters more
- 14B models: borderline; require aggressive quantization (Q3) and lose quality
- Recommended tool: Ollama (simplest, GPU-verified via `ollama ps`); llama.cpp for
  fine-grained control; vLLM is overkill for a single-GPU dev machine

### Recommended local model stack for this project

Qwen3-8B (Q4_K_M) -- primary general-purpose local model
- Best 8B-class reasoning and math as of mid-2026
- VRAM: ~5.2GB; comfortable on 8GB
- Use for: offline draft reasoning, cheap iteration on signal logic, privacy-sensitive
  text parsing (no data leaves the machine)
- `ollama pull qwen3:8b`

DeepSeek-R1-8B (Q4_K_M) -- reasoning-heavy and chain-of-thought tasks
- Purpose-built for multi-step reasoning; strong on structured analysis
- VRAM: ~5GB
- Use for: adversarial cross-checking Claude's model architecture decisions,
  independent probability estimate for calibration sanity checks
- `ollama pull deepseek-r1:8b`

Qwen2.5-Coder-7B -- code generation and review
- 72%+ HumanEval; specifically tuned for code
- Use for: local code review, generating boilerplate, offline CI-adjacent tasks
- `ollama pull qwen2.5-coder:7b`

Gemma 3 4B (Q4_K_M) -- lightweight fallback
- 3GB VRAM; leaves 5GB headroom for context or concurrent work
- Use for: light summarization, fast pre-screening, running alongside other processes
- `ollama pull gemma3:4b`

### What NOT to do locally
- Do not chase 13B/14B models on 8GB -- they force Q3 which degrades quality below
  the 8B Q4 baseline
- Do not use vLLM for single-GPU dev; startup overhead is not worth it at this scale
- llama.cpp GGUF is the right backend if Ollama's abstraction costs you control

---

## 3. EMBEDDING MODELS FOR THE RAG LAYER

### Context for this project
The vault has ~660 player + 30 team Obsidian notes plus signal catalogs. The RAG
layer needs high retrieval accuracy on structured sports/analytics text, not
multimodal or multilingual breadth. Scale is small (thousands to low-millions of
chunks), so hosting cost is not the primary driver -- quality and zero-latency
local serving are.

### Recommended: Qwen3-Embedding-8B (self-hosted, open-weight)
- Top of MTEB v2 leaderboard among open-weight models (~75% average MTEB score)
- Beats text-embedding-3-large by 7-10 MTEB points
- Self-hosted cost: near zero (CPU inference is fine for embedding at this scale;
  embedding is fast even without GPU)
- Dimensions: configurable via Matryoshka (can truncate to 512/1024 without major
  quality loss for faster retrieval)
- Run via: `ollama pull qwen3-embedding` or HuggingFace transformers + FAISS

### Strong alternative: BGE-M3 (BAAI, open-weight)
- Dense + sparse + colbert retrieval in one model -- good for hybrid search
- 567M params; CPU-friendly; well-tested in production RAG stacks
- MTEB competitive with text-embedding-3-large; self-hosted = free
- Use this if you want a proven, stable embedding over the newer Qwen3 variant

### Budget alternative: nomic-embed-text (137M, open-weight)
- Smallest credible option; runs fast even on CPU
- Quality drops at >4K context chunks -- keep chunk size under 2K tokens
- Good enough for the vault's short Obsidian notes

### When to use hosted embeddings (rare cases)
- OpenAI text-embedding-3-large: $0.13/1M tokens -- only worth it if you need the
  OpenAI ecosystem pipeline and are embedding <1M chunks total
- Gemini Embedding 2: best multilingual + long-doc (32K tokens); API-based; use
  only if chunks are very long and cross-lingual
- For this project: self-hosted Qwen3-Embedding or BGE-M3 is the correct call.
  The scale does not justify API spend and the quality is strictly better.

### Cost reality check
- At 100M tokens/day production scale: OpenAI = ~$13,000/month; self-hosted = ~$500
- For this project (vault RAG, small scale): OpenAI = under $5/month even at text-
  embedding-3-large; but self-hosted is free and better quality -- use self-hosted

---

## 4. HONEST VERDICT FOR THIS PROJECT

### Stay Claude-first for:
- All agentic build work (Claude Code is the right loop for this repo)
- Complex multi-step reasoning: signal logic, model architecture decisions, calibration
  analysis
- Code generation and debugging (SWE-bench gap is real; Claude Opus 4.8 leads)
- Anything where accuracy on the first attempt saves iteration cost

### Use a non-Claude model when:
a) BULK CHEAP INFERENCE -- Gemini 3.5 Flash ($1.50/1M) or DeepSeek V4-Flash
   ($0.14/1M) for pre-screening, batch enrichment, or generating large volumes of
   structured labels. Route simple tasks here before paying Claude rates.

b) LOCAL/OFFLINE/PRIVATE EXTRACTION -- Qwen3-8B or DeepSeek-R1-8B via Ollama on
   the RTX 4060. Zero data egress, zero cost, no API rate limits. Use for offline
   CV text extraction, parsing raw data files, iterating on prompt logic cheaply,
   and any task where you want to experiment without burning API budget.

c) ADVERSARIAL CROSS-CHECKING -- Run a second independent model (GPT-5.5 or local
   DeepSeek-R1-8B) on a prediction or calibration decision to catch Claude-specific
   failure modes. Two independent training runs disagreeing = flag for human review.
   This is the highest-leverage use of a non-Claude model for calibration work.

d) EMBEDDINGS -- Self-hosted Qwen3-Embedding or BGE-M3 for the vault RAG layer.
   Better MTEB scores than text-embedding-3-large, free to run, no API dependency.
   Set up once with FAISS or ChromaDB; no ongoing cost.

### What NOT to do:
- Do not switch primary model to Grok or Gemini to save cost on agentic coding loops;
  the 15-20% quality drop on complex multi-step tasks costs more in re-work than it
  saves in API spend.
- Do not use GPT-5.5 as a drop-in for Claude Code; the tooling integration and
  agentic reliability favor Claude for this specific workflow.
- Do not run 14B models locally on the 8GB GPU; use the hosted API instead for tasks
  that need that capability.
- Do not embed with OpenAI at this project's scale; self-hosted is strictly better.

### The one place to try GPT-5.5 concretely:
Math/stats sanity checks -- FrontierMath leadership means GPT-5.5 is the right
adversarial reviewer when Claude produces a Bayesian update or calibration formula.
A single cheap GPT-5.5 call (or local DeepSeek-R1-8B call) to verify the algebra
before committing a prediction model change is high-leverage and low-cost.

---

## Sources

- LM Council Benchmarks (June 2026): https://lmcouncil.ai/benchmarks
- felloai Best AI Models June 2026: https://felloai.com/best-ai-models/
- AIAgentsKit RTX 4060 Local LLMs: https://aiagentskit.com/blog/best-local-llms-rtx-4060-3070-5060/
- AIAgentsKit GPU Buyer's Guide: https://aiagentskit.com/blog/best-gpu-for-ai/
- WhatLLM Best Local LLMs 2026: https://whatllm.org/best-local-llm
- Milvus Embedding Model RAG 2026: https://milvus.io/blog/choose-embedding-model-rag-2026.md
- Presenc AI Open-Weight Embeddings 2026: https://presenc.ai/research/best-open-weight-embedding-models-2026
- PECollective Embedding Models 2026: https://pecollective.com/tools/best-embedding-models/
- Cheney Zhang Embedding Benchmark 2026: https://zc277584121.github.io/rag/2026/03/20/embedding-models-benchmark-2026.html
- LLM Stats Leaderboard: https://llm-stats.com/
- LocalAI Master Best Models May 2026: https://localaimaster.com/blog/best-ai-models-2026
