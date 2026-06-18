# Fine-Tune vs RAG vs Prompt-Engineer vs Distill: Trade-offs and When to Use Each
_Researched 2026-06-16. Scope: decision framework for choosing LLM adaptation strategy, with honest take on structured sports prediction._

---

## TL;DR (7 bullets)

- **Exhaust prompt engineering first.** Zero infra, zero cost, instant iteration. Most teams reach for fine-tuning before they have tried a well-structured system prompt + few-shot examples. That is almost always a mistake.
- **RAG is the right default for knowledge freshness.** If the gap is "the model doesn't know current facts" (new box scores, injury reports, recent game results), RAG closes it at far lower cost than fine-tuning and stays current without retraining.
- **Fine-tuning is for style/format/behavior baked into weights, not knowledge injection.** It shines when you need consistent structured output format, a domain-specific tone, or a task the base model handles poorly (e.g., chain-of-thought forecasting policy). It is slow, brittle to distribution shift, and almost universally over-applied.
- **LoRA/QLoRA handle ~95% of fine-tuning needs.** Full fine-tuning of a 7B model needs 100+ GB VRAM (~$50k hardware). QLoRA does the same job on a $1,500 RTX 4090 with 80-90% quality retention. LoRA retains 90-95% quality and adds zero inference latency after weight merging.
- **Distillation (teacher -> student) is cost-effective only if you need cheap high-volume inference.** Use a big frontier model (Claude Opus / GPT-4o / Gemini Pro) to generate high-quality labeled outputs, then fine-tune a small open model on those outputs. Gains of 21-31% over prompting the small model directly have been documented. The prerequisite: the big model's outputs must be correct enough to be worth teaching from.
- **DPO > RLHF for preference alignment at smaller scale.** DPO needs no explicit reward model -- just (prompt, chosen, rejected) pairs -- and is cheaper than PPO-based RLHF. RLAIF scales pair generation by using an AI judge instead of humans; spot-check 5-10% of AI judgments to catch systematic errors.
- **For structured sports prediction (GBMs/Bayesian models vs LLMs): GBMs win on tabular data almost always.** LLMs are competitive only in extreme few-shot regimes (<64 labeled examples). The interesting role for LLM fine-tuning in this project is NOT the point-prediction model -- it is synthesis, summarization, and forecasting-policy calibration (see below).

---

## Key Capabilities / Techniques

### 1. Prompt Engineering
- Zero infrastructure beyond an API key. Test instantly.
- System prompt + few-shot examples + chain-of-thought reasoning covers the majority of LLM adaptation tasks.
- **Best for:** output formatting, persona, reasoning style, one-off tasks, prototyping any new use case.
- **Ceiling:** the base model's parametric knowledge is fixed; hallucination risk grows with specificity.

### 2. RAG (Retrieval-Augmented Generation)
- A retrieval layer fetches relevant documents at query time and injects them into the prompt context.
- Keeps knowledge current without retraining -- update the document store, not the model.
- Adds 100ms - 2s latency depending on index size and reranking.
- **Best for:** factual freshness (injury reports, recent box scores, current betting lines), private data access, reducing hallucination on domain-specific facts.
- **Ceiling:** retrieval quality determines answer quality. Garbage-in, garbage-out from the index. Requires careful chunking and embedding.

### 3. Supervised Fine-Tuning (SFT)
- Gradient updates on (input, target) pairs to bake behavior, format, or domain into weights.
- **Full fine-tuning:** 100+ GB VRAM for 7B models. ~$50k hardware. Rarely necessary.
- **LoRA:** injects low-rank adapter matrices. Zero added inference latency after merging. 90-95% quality of full FT. Min hardware: RTX 4090 24GB for 7B.
- **QLoRA:** 4-bit NormalFloat quantization + paged optimizers. Trains 70B on a single A100 80GB. 80-90% quality. Use when VRAM is the binding constraint.
- **Best for:** consistent structured output schema, domain-specific behavior the base model handles poorly, deploying a specialized small model at high inference volume.
- **Ceiling:** freezes in the training distribution. If inputs drift (new season, rule changes), quality degrades and you must retrain.

### 4. DPO (Direct Preference Optimization)
- Trains on (prompt, chosen_response, rejected_response) triplets with a contrastive loss. No explicit reward model needed.
- Cheaper and more stable than PPO-based RLHF.
- **RLAIF variant:** use a frontier LLM as the AI judge to generate chosen/rejected pairs at scale, then spot-check 5-10%.
- **Best for:** alignment, tone calibration, reducing unwanted outputs (overconfident predictions, hallucinated stats).
- **Ceiling:** preference label quality is the bottleneck. AI judges inherit the frontier model's biases.

### 5. Distillation (Big Model -> Small Model)
- Teacher (large frontier model) generates high-quality outputs on a curated input set.
- Student (small open model) is fine-tuned on those outputs.
- Documented gains: Llama 3.1 8B Instruct +21%, Phi-3 Mini +31% over directly prompting the student.
- The "slow thinking" -> "fast thinking" distillation pattern: teacher uses chain-of-thought reasoning; student learns the compressed policy.
- Cost: one-time teacher inference cost (API calls) + cheap student training (QLoRA on RTX 4090).
- **Best for:** high-volume inference at low cost where a frontier model is too expensive per call; embedding a specific reasoning policy into a deployable on-device model.
- **Ceiling:** the student cannot exceed the teacher's accuracy ceiling; if the teacher makes systematic errors (biased priors, stale data), the student learns those errors.

### 6. LLM Fine-Tuning for Forecasting (Research State-of-the-Art 2025)
- RL fine-tuning of gpt-oss-120b on ~10,000 binary forecasting questions improved Metaculus scores from 38.6 to 45.8 (+7 pts), reaching frontier-model level.
- **Critical caveat from the paper:** without pre-generated research summaries and specialized tools, the same fine-tuning yielded only +3 pts instead of +7. The data pipeline did most of the work, not the gradient updates alone.
- BoostLLM (2025): boosting-inspired adapter stacking matches XGBoost on tabular classification in few-shot regimes (<128 examples) but requires multiple forward passes per inference and a pre-trained GBM model as scaffolding. GBMs still win when data is abundant and inference speed matters.

---

## How THIS Project Should Use It

This project uses GBMs/Bayesian/Monte Carlo engines for the core calibrated prediction numbers. LLMs are correctly positioned as synthesizers and intelligence layers, NOT as the prediction model. The following is the right stack:

### Where RAG wins here
- **Intel synthesis at query time:** game-night queries like "who is Wembanyama's matchup tonight and what are his recent PBP tendencies?" -- pull from the Obsidian vault via RAG (vault/_Organized as the document store), not from fine-tuning. The vault is the knowledge base; keep it as a retrieval index.
- **Freshness injection:** injury updates, lineup confirmations, recent game results. Build a nightly ETL that writes structured documents to the RAG index. The LLM then conditions on fresh text without retraining.
- **Why not fine-tuning here:** the vault changes daily. Fine-tuning can't keep up. RAG is the correct architecture.

### Where distillation wins here
- If you call Claude Opus or GPT-4o for game summaries / scheme analysis at scale (e.g., 30 games/night), inference cost compounds fast.
- Pattern: use Opus to generate 500-2000 high-quality game analysis examples. Fine-tune a Phi-3 Mini or Llama 3.1 8B student on those outputs (QLoRA, your RTX 4060 Ti can handle it). Deploy the student for nightly volume at near-zero cost.
- Prerequisite: Opus outputs must first be validated for accuracy against box scores / PBP data. The student will faithfully learn Opus's mistakes.

### Where SFT / DPO wins here
- **Calibration-aware output formatting:** fine-tune a small model to always emit structured JSON with `{"prediction": X, "confidence_interval": [...], "calibration_tier": "A/B/C", "honest_caveats": [...]}` rather than prose. This is a format/behavior task -- exactly where SFT excels.
- **DPO for honesty calibration:** generate (prompt, overconfident_response, calibrated_response) pairs. Fine-tune the model to prefer calibrated, hedged outputs over confident ones. This directly reinforces the project's north star without requiring hand-holding in every prompt.
- **Forecasting policy:** if you build a large labeled set of (game-context, accurate-probability-assessment) pairs graded against devigged market closes, SFT on that set builds a forecasting policy inside the model. This is the research-proven path (Mantic/Thinking Machines result). Prerequisite: you need ~5,000-10,000 examples minimum.

### Where prompt engineering remains sufficient (do this first, always)
- Intel narrative generation: structured system prompt + few-shot examples handles 90%+ of summary and analysis tasks today with no training cost.
- Scheme-prior elicitation: a well-structured prompt asking for bounded multipliers on existing sim knobs (CV_LLM_SCHEME pattern already built) is the right level of investment for that signal's measured impact.
- Agent orchestration: routing, planning, tool-use decisions -- prompt engineering with good system design is the correct tool.

### What NOT to do
- **Do NOT fine-tune an LLM to produce win probabilities directly** (replacing the GBM/Monte Carlo engine). The point-prediction task is tabular, structured, and data-rich -- GBMs strictly dominate. Fine-tuning an LLM for this would be slower, less interpretable, harder to validate for leakage, and worse in practice.
- **Do NOT use fine-tuning to inject knowledge that changes frequently** (box scores, injury reports, recent trends). That is RAG's job. Fine-tuning knowledge that decays in days wastes compute and produces a stale model.
- **Do NOT distill from a teacher that hasn't been validated** against leak-free OOS metrics first. If the teacher hallucinates stats or overfits to narrative, the student will too.

---

## Gotchas / Limits

- **Fine-tuning is not a knowledge injection tool.** It bakes behavior and style, not facts. RAG is the knowledge tool.
- **QLoRA quality on some tasks is noticeably worse than LoRA or full FT** due to quantization noise. Evaluate per task, do not assume 80-90% is acceptable without measuring.
- **LoRA rank choice matters.** Low rank (r=4-8) = good regularization, less capacity. High rank (r=64-128) = approaches full FT quality but uses more memory. Tune based on task complexity.
- **DPO can collapse** if chosen/rejected pairs are too similar or if the base model has already strongly preferred one. Add a KL penalty term (beta parameter) and monitor log probability ratios during training.
- **RLAIF pair quality degrades** on domain-specific tasks where the AI judge lacks ground truth. For sports prediction, the judge may not know which probability was actually better calibrated. Human spot-checking 10%+ is non-negotiable.
- **Distillation ceiling = teacher ceiling.** If the teacher (Opus/GPT-4o) achieves only weak calibration on a task, the student will not beat it.
- **BoostLLM / LLM-for-tabular approaches require multiple forward passes** per inference and rely on a pre-trained GBM as scaffolding. Not a practical replacement for production GBMs.
- **The Mantic/Thinking Machines result (+7 pts improvement) required a full retrieval + research pipeline** surrounding the fine-tuning. Gradient updates alone delivered only +3 pts. Infrastructure doing data fetching and summarization was most of the gain.
- **Data requirements:** DPO needs high-quality (chosen, rejected) pairs that are genuinely different in quality. SFT for forecasting policy needs ~5,000-10,000 examples minimum to generalize. Below that, GBMs or few-shot prompting will likely win.
- **On your RTX 4060:** 8GB VRAM. QLoRA for a 7B model needs ~12-16GB. You can fine-tune up to ~3B parameter models locally; use a cloud GPU (Vast.ai A100 ~$0.40/hr) for 7B+ models.

---

## Sources

- [Fine-Tuning Infrastructure: LoRA, QLoRA, and PEFT at Scale | Introl Blog](https://introl.com/blog/fine-tuning-infrastructure-lora-qlora-peft-scale-guide-2025)
- [RAG vs Fine-Tuning vs Prompt Engineering: And the Winner Is... | k2view](https://www.k2view.com/blog/rag-vs-fine-tuning-vs-prompt-engineering/)
- [Prompting vs. RAG vs. Fine-Tuning: Why It's Not a Ladder | The New Stack](https://thenewstack.io/prompting-vs-rag-vs-fine-tuning-why-its-not-a-ladder/)
- [Training LLMs to Predict World Events (Mantic/Thinking Machines Lab)](https://thinkingmachines.ai/news/training-llms-to-predict-world-events/)
- [BoostLLM: Boosting-Inspired LLM Fine-Tuning for Few-Shot Tabular Classification | arXiv](https://arxiv.org/html/2605.06117v2)
- [Distillation: Turning Smaller Models into High-Performance, Cost-Effective Solutions | Microsoft Azure AI Foundry Blog](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/distillation-turning-smaller-models-into-high-performance-cost-effective-solutio/4355029)
- [LoRA vs QLoRA: Best AI Model Fine-Tuning Platforms and Tools 2026 | Index.dev](https://www.index.dev/blog/top-ai-fine-tuning-tools-lora-vs-qlora-vs-full)
- [LLM Fine-Tuning Pricing 2026 | Price Per Token](https://pricepertoken.com/fine-tuning)
