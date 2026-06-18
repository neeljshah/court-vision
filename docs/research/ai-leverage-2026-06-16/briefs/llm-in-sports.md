# LLMs Applied to Sports Forecasting and Intelligence
_Researched 2026-06-16. Scope: how LLMs can improve a calibrated multi-sport prediction platform via structured extraction, synthesis, and orchestration -- what they can and cannot do._

## TL;DR (highest-leverage takeaways)

- **LLMs are bad predictors, good synthesizers.** Using an LLM to output a win probability directly is a reliability failure: ECE values range 0.12-0.39 across all major models, positional/lexical biases contaminate numeric outputs, and only one frontier model (Claude Opus 4.5) achieves a positive Brier Skill Score vs. base rate. Never route raw numeric prediction through an LLM.
- **LLMs as an ensemble reach human-crowd-level forecasting accuracy** on general binary questions (Brier ~0.20 vs. human crowd 0.19), but only via aggregation of 12+ models -- not a single call. For sports, this ceiling is far below a well-calibrated quantitative model with domain features.
- **The killer app is structured extraction.** LLMs reliably convert injury reports, lineup news, press conferences, and beat-writer text into typed JSON schemas (player, status, team, confidence, source) -- feeding fresh signals into the quant pipeline. This is production-proven and available via every major provider's structured-output API.
- **LLM-as-orchestrator, not predictor.** The right architecture: LLM routes, synthesizes, and generates bounded prior multipliers; the quantitative model (Monte Carlo sim, calibrated regression) computes every number. This mirrors how the project already uses `scheme_prior.py`.
- **Wordalisation / scouting synthesis is validated.** Pipelines that convert model feature contributions into natural-language scouting narratives (for coaches or a product UI) work well -- percentile bucketing + few-shot prompting is the proven pattern.
- **Agentic RAG is now the default pattern** for ingesting heterogeneous sports content: agents choose between semantic search, structured DB query, and real-time web fetch depending on query type. In 2026 this is mature infrastructure, not research.
- **Calibration -- not accuracy or ROI -- is the only safe optimization target** when LLM outputs touch the prediction stack. A sports-specific result confirms: ML models selected by calibration returned +34.69% vs. -35.17% for accuracy-selected models (diagnostic, not a recommended betting strategy; cited to note calibration matters for model selection even here).

## Key capabilities / techniques

### 1. Structured extraction (unstructured -> typed JSON)
- **What it does:** takes raw text (injury report, tweet, beat-writer article, press conference transcript) and extracts typed fields: `{player: str, team: str, status: "OUT"|"QUESTIONABLE"|"PROBABLE", body_part: str, game_date: str, source_url: str, confidence: float}`.
- **How it works in 2026:** Anthropic tool-use / OpenAI structured outputs / Gemini structured-output API all enforce schema compliance at the token level. XGrammar (default backend for vLLM, SGLang, TensorRT-LLM as of March 2026) delivers grammar-constrained generation at under 40 microseconds/token with near-zero overhead.
- **Production pattern (Simon Willison 2025):** run schema extraction over N sources -> log to SQLite -> aggregate and query via SQL. Reuse saved schema templates. Note 100% reliability is never guaranteed; validate with a downstream schema check.
- **For sports:** extract injury/lineup deltas from ESPN, Rotowire, Twitter/X, team beat writers. Each extracted record = a feature delta fed into the pregame model freshness layer.

### 2. Agentic ingestion pipeline (Agentic RAG)
- **What it does:** an orchestrating agent decides, per query, whether to: (a) retrieve from a local vector index of past scouting notes, (b) run a structured DB query against historical features, or (c) fire a live web search for breaking news. Agents iterate over multiple retrieval steps before synthesizing a context packet.
- **When to use:** for dynamic pre-game context assembly -- "what is the freshest info on Giannis's ankle?" -- rather than static nightly batch jobs.
- **Key advantage over vanilla RAG:** agents handle messy, multi-hop retrieval (e.g., "get the lineup, then check who replaces the injured starter, then pull their last-5-game splits") without brittle hand-coded pipelines.
- **Maturity level:** production-ready as of 2026; Azure AI Search, LangGraph, and bare Anthropic tool-use all support it.

### 3. Scouting-report and scheme-prior synthesis
- **What it does:** LLM ingests structured signals (percentile-bucketed feature contributions from the quantitative model) and emits a bounded natural-language narrative and/or a small set of multipliers on existing model knobs.
- **Proven pattern (football xG paper, 2025):** 4-step "wordalisation" pipeline -- (1) system-prompt role, (2) 43 Q&A examples, (3) convert numbers to percentile descriptions, (4) few-shot output format. Achieved highest engagement with near-highest accuracy vs. raw number output.
- **For this project:** `scheme_prior.py` already uses this pattern. The extension is to source the input not just from static scheme knowledge but from freshly extracted pre-game news/lineup data.
- **Multiplier bounding is mandatory:** LLM must emit multipliers in a constrained numeric range (e.g., 0.85-1.15x on turnover rate) with leak-flag metadata; the sim recomputes every downstream number. Raw LLM probability outputs must never enter the prediction chain.

### 4. LLM-as-feature (embeddings / semantic similarity)
- **What it does:** convert scouting notes, coaching tendency text, or play-description strings into dense embeddings; use cosine similarity or retrieval to find analogous historical matchups.
- **Honest limitation:** this adds a qualitative layer, not a numeric edge. Similarity to "past high-tempo games" is a routing signal, not a calibrated probability adjustment.
- **Safe use:** as an input to the matchup-selection step (which historical games are genuinely comparable for this calibration bucket?) or for surfacing relevant past-game scouting notes in a UI.

### 5. LLM ensemble forecasting (research context only)
- **Finding:** an ensemble of 12 LLMs achieves Brier ~0.20, statistically tied with a 925-person human forecasting crowd on general binary questions (Metaculus tournament). GPT-4 and Claude 2 improved from Brier 0.17->0.14 and 0.22->0.15 respectively after seeing human crowd medians.
- **Caveat for sports:** general-event LLM forecasting is far weaker than a domain-specific calibrated model. The LLM crowd result holds for heterogeneous geopolitical/tech questions; sports markets are more efficient and structured models dominate LLM-only approaches.
- **Legitimate use case:** for markets where structured data is sparse (e.g., early-season novelty matchups, team schema changes mid-season with no recent games), an LLM ensemble can provide a reasoned prior that is better than nothing. Must be clearly labeled as a weak prior, not a model output.

### 6. LLM-as-orchestrator for the prediction pipeline
- **Pattern:** LLM acts as the routing and synthesis layer; specialized quantitative sub-agents (MC sim, calibrated model, live scoring, injury-delta calculator) do numeric work. LLM selects which sub-agents to call, in what order, and synthesizes their outputs into a user-facing report.
- **Concrete implementation:** use Claude tool-use to call `run_pregame_sim(team_a, team_b, context)`, `get_injury_delta(player_id)`, `score_in_game_state(game_id, quarter, score_diff)` as typed tools. LLM assembles the narrative; tools compute numbers.
- **Why this is the right architecture:** LLMs are unreliable at computing probabilities from scratch but excellent at deciding which tools to use, interpreting their outputs, and generating coherent summaries. Separating concerns eliminates the numeric calibration failure mode.

## How THIS project should use it

1. **Build a structured-extraction agent for daily lineup/injury ingestion.** Schema: `{player_id, team_id, status, severity, game_date, source, extracted_at, confidence}`. Run nightly (and re-run 2h before each game). Store to SQLite. Each `status=OUT` row subtracts that player's usage and redistributes via the vacated-load model -- this is the freshness lever the pregame model is missing.

2. **Wire agentic RAG into pre-game context assembly.** Before running the sim for a matchup, an agent: (a) pulls fresh structured injury/lineup records, (b) retrieves relevant past-scouting notes from the Obsidian vault via semantic search, (c) runs a web search for any breaking news in the last 4 hours. The assembled context packet feeds into `scheme_prior.py` as bounded multipliers, not raw probability adjustments.

3. **Extend wordalisation to the live React board.** Take the feature contributions from the MC sim (e.g., "Wemby's defensive impact reduces opposing field-goal rate by 8.2%") -> percentile-bucket them -> LLM generates a one-paragraph scouting summary. Display alongside the prediction on the live board. This is a product feature, not a prediction improvement, and is safe because the LLM is only narrating numbers it did not compute.

4. **Use LLM-as-orchestrator for the in-game repricing flow.** When live game state changes (a starter fouls out, a lead changes), an orchestrating LLM agent: (a) detects the event via structured extraction from the live PBP feed, (b) calls the in-game sim tool with updated state, (c) diffs the new probability vs. pregame, (d) emits a structured update record with the delta and confidence tier. No raw LLM probability in the output.

5. **Do NOT use LLM to generate game-outcome probabilities directly.** All probability estimates must come from the calibrated quantitative pipeline. LLM outputs that enter the prediction chain must be bounded multipliers with numeric constraints, not raw floats. This is especially important for the in-game layer where overconfidence at high confidence levels (80%+, 90%+) is documented as "alarmingly high" across all major models.

6. **For sparse matchups (e.g., early-season, roster-turnover games) where calibrated model has wide uncertainty:** a clearly labeled "LLM prior" from a 3-5 model ensemble (Claude + GPT-4 + one open-source) can serve as a weak Bayesian prior that is updated as game data accumulates. Label uncertainty tier explicitly in the UI.

7. **Calibration check on any LLM-touching layer.** Any pipeline change that routes LLM output into the prediction stack must be followed by an OOS Brier/ECE check on a held-out validation set before shipping. The known failure modes (positional bias, lexical artifacts, non-proportional probability allocation) will surface as systematic calibration drift.

## Gotchas / limits

- **LLMs cannot do reliable numeric probability estimation from scratch.** ECE 0.12-0.39 across all major models; position bias alone flips probability rankings between model families. Never trust a raw LLM-output probability for sports markets.
- **Only one frontier model beats base rate on general forecasting.** Claude Opus 4.5 achieves a positive Brier Skill Score; all others score negative vs. simply predicting the base rate. Sports domain is even harder -- structured domain models dominate.
- **Overconfidence at high confidence levels is the worst failure mode.** When an LLM says 90% confident, it is often far less accurate than that. This is especially dangerous for in-game repricing where overconfident LLM outputs could look like strong signals.
- **Structured output is reliable but not perfect.** Even with grammar-constrained decoding, complex schemas with nested conditionals fail at ~12% rate with GPT-4 on difficult extractions. Always validate extracted JSON against the schema downstream; do not assume constraint-decoded output is semantically correct.
- **Acquiescence bias / positivity bias in sports context.** LLMs tend to predict positive/favorable outcomes more than base rates warrant -- relevant for injury severity (understating severity), lineup availability (assuming starter plays), and game narratives (assuming "story" outcomes).
- **Latency of agentic pipelines.** Multi-hop agentic RAG (3+ tool calls with web fetches) can take 10-30 seconds. For pre-game context assembly this is acceptable; for in-game real-time repricing, a single-hop structured extraction with a pre-warmed cache is required.
- **LLM knowledge cutoff gap for fresh news.** Base model knowledge cuts off months before game day. All fresh-signal work must go through real-time retrieval (web search or live feed), not the model's parametric memory.
- **Do not conflate "LLM forecasting is human-level" with "LLM is useful for sports prediction."** The human-crowd parity result (Brier 0.20 vs. 0.19) is for heterogeneous general-event binary questions -- not for NBA/MLB/soccer where structured models with historical data significantly outperform crowd wisdom.
- **Wordalisation engages coaches but does not improve underlying model accuracy.** The football xG paper found a deliberate accuracy-engagement tradeoff: full wordalisation maximizes engagement but is not the most accurate output format. Use narratives for UX, not as inputs back into the quantitative model.

## Sources

- [Wisdom of the silicon crowd: LLM ensemble prediction capabilities rival human crowd accuracy (PMC 2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11800985/)
- [Language Model Probabilities are Not Calibrated in Numeric Contexts (arXiv 2024)](https://arxiv.org/abs/2410.16007)
- [Predicting Football Match Outcomes Using LLMs: A Comparative Study (Sciety/OSF 2025)](https://sciety.org/articles/activity/10.31235/osf.io/e5wpy_v2)
- [Automated Explanation of ML Models of Footballing Actions in Words (arXiv 2025)](https://arxiv.org/html/2504.00767v1)
- [Structured data extraction from unstructured content using LLM schemas (Simon Willison 2025)](https://simonwillison.net/2025/Feb/28/llm-schemas/)
- [Machine learning for sports betting: accuracy or calibration? (arXiv / ScienceDirect 2023)](https://arxiv.org/pdf/2303.06021)
- [Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG (arXiv 2025)](https://arxiv.org/html/2501.09136v4)
- [LLM Structured Outputs: Schema Validation for Real Pipelines 2026 (Collin Wilkins)](https://collinwilkins.com/articles/structured-output)
- [SportsMetrics: Blending Text and Numerical Data to Understand Information Fusion in LLMs (arXiv 2024)](https://arxiv.org/pdf/2402.10979)
