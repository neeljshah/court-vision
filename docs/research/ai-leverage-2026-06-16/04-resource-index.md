# Curated Resource Index -- Repos, Papers, Tools, Docs

_Synthesized 2026-06-16 from the ai-leverage briefs (github-sports-repos + every "Sources" link across all 23 briefs) and the project's existing research docs. The single best starting-point bookmark file for building a solo, Claude-agent-driven, calibrated multi-sport prediction platform._

## How to read this
- Each entry: **name** -- one-line value -- URL -- `tag`.
- Tags: `official-doc` (vendor/canonical docs), `repo` (code), `paper` (peer-reviewed / arXiv / preprint), `tool` (hosted product or library page), `blog` (blog/tutorial/comparison).
- De-duplicated across briefs; where a link appeared in several briefs it is listed once in its strongest category.
- Skeptic's note: anything tagged `blog` is orientation, not authority. Sports-betting repos that advertise ROI are architecture references only -- validate every signal through the project's own honest gate before trusting it.

---

## 1. Claude / Anthropic -- Official Docs & Engineering

### API core
- **Claude Models Overview** -- canonical model list/capabilities -- https://platform.claude.com/docs/en/about-claude/models/overview -- `official-doc`
- **Choosing a Model** -- Opus vs Sonnet vs Haiku selection guidance -- https://platform.claude.com/docs/en/about-claude/models/choosing-a-model -- `official-doc`
- **Tool Use Overview** -- function/tool-calling primitives -- https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview -- `official-doc`
- **Strict Tool Use** -- guaranteed-schema tool calls -- https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use -- `official-doc`
- **Structured Outputs** -- enforce JSON schema on responses (key for prediction pipelines) -- https://platform.claude.com/docs/en/build-with-claude/structured-outputs -- `official-doc`
- **Extended Thinking** -- reasoning-budget control -- https://platform.claude.com/docs/en/build-with-claude/extended-thinking -- `official-doc`
- **Adaptive Thinking** -- auto-scaled reasoning effort -- https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking -- `official-doc`
- **Streaming Messages** -- token streaming -- https://platform.claude.com/docs/en/build-with-claude/streaming -- `official-doc`
- **Citations** -- source-grounded responses -- https://platform.claude.com/docs/en/build-with-claude/citations -- `official-doc`
- **PDF Support** -- native PDF input -- https://platform.claude.com/docs/en/build-with-claude/pdf-support -- `official-doc`
- **Claude Opus model release notes (latest: 4.8)** -- model announcements (4.6/4.7 prior) -- https://www.anthropic.com/news -- `official-doc`

### Scale & cost
- **Prompt Caching** -- cache long system/context for ~90% input savings -- https://platform.claude.com/docs/en/build-with-claude/prompt-caching -- `official-doc`
- **Batch Processing / Message Batches API** -- 50% discount, async bulk jobs (ideal for backtests) -- https://platform.claude.com/docs/en/build-with-claude/batch-processing -- `official-doc`
- **Pricing** -- per-token costs -- https://platform.claude.com/docs/en/about-claude/pricing -- `official-doc`
- **Rate Limits** -- tier limits / 429 handling -- https://platform.claude.com/docs/en/api/rate-limits -- `official-doc`

### Agent SDK, Skills, Computer Use, MCP
- **Claude Agent SDK -- Overview** -- official agent-building SDK -- https://code.claude.com/docs/en/agent-sdk/overview -- `official-doc`
- **Extend Claude Code (features overview)** -- hooks/MCP/skills/subagents surface -- https://code.claude.com/docs/en/features-overview -- `official-doc`
- **Agent Skills overview** -- progressive-disclosure skill model -- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview -- `official-doc`
- **Skill authoring best practices** -- SKILL.md design -- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices -- `official-doc`
- **Computer Use tool** -- screen/keyboard/mouse control -- https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool -- `official-doc`
- **MCP Introduction** -- Model Context Protocol primer -- https://modelcontextprotocol.io/introduction -- `official-doc`
- **MCP Architecture** -- protocol internals -- https://modelcontextprotocol.io/docs/learn/architecture -- `official-doc`
- **MCP Registry** -- discover published MCP servers -- https://registry.modelcontextprotocol.io/ -- `official-doc`

### Anthropic engineering / research (agent design patterns)
- **Building Effective Agents** -- the foundational workflow-vs-agent taxonomy -- https://www.anthropic.com/research/building-effective-agents -- `official-doc`
- **How we built our multi-agent research system** -- concrete numbers (orchestrator-worker, token budgets) -- https://www.anthropic.com/engineering/multi-agent-research-system -- `official-doc`
- **Equipping Agents for the Real World with Agent Skills** -- skill-loading architecture -- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills -- `official-doc`
- **A statistical approach to model evaluations** -- rigor for eval design (CIs, significance) -- https://www.anthropic.com/research/statistical-approach-to-model-evals -- `official-doc`
- **Bloom: open-source automated behavioral evaluations** -- behavioral eval tooling -- https://www.anthropic.com/research/bloom -- `official-doc`
- **Enhancing RAG with Contextual Retrieval** -- Claude Cookbook contextual-embeddings guide -- https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide -- `official-doc`

### Anthropic official repos
- **anthropics/anthropic-sdk-python** -- official Python SDK (the primitive under Claude Code) -- https://github.com/anthropics/anthropic-sdk-python -- `repo`
- **anthropics/anthropic-cookbook (patterns/agents)** -- reference notebooks: basic_workflows, evaluator_optimizer, orchestrator_workers, async_multi_agent -- https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents -- `repo`
- **anthropics/claude-quickstarts** -- computer-use-demo reference implementation -- https://github.com/anthropics/claude-quickstarts -- `repo`
- **anthropics/claude-plugins-official (SKILL.md frontmatter ref)** -- canonical skill frontmatter schema -- https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/command-development/references/frontmatter-reference.md -- `repo`
- **obra/superpowers** -- community Claude Code skills collection -- https://github.com/obra/superpowers/ -- `repo`
- **machina-sports/sports-skills** -- sports-specific Claude agent skills -- https://github.com/machina-sports/sports-skills -- `repo`

---

## 2. Agent Frameworks & Orchestration

- **langchain-ai/langchain** -- largest LLM framework ecosystem (chains/tools/memory) -- https://github.com/langchain-ai/langchain -- `repo`
- **langchain-ai/langgraph** -- stateful graph agent workflows; best fit for propose -> gate-test -> accept/reject loops -- https://github.com/langchain-ai/langgraph -- `repo`
- **crewAIInc/crewAI** -- role-based multi-agent crews (parallel specialist fleet) -- https://github.com/crewAIInc/crewAI -- `repo`
- **microsoft/autogen (AG2)** -- code-executing multi-agent conversations -- https://github.com/microsoft/autogen -- `repo`
- **stanfordnlp/dspy** -- programmatic prompt optimization / compile-not-tune -- https://github.com/stanfordnlp/dspy -- `repo`
- **crystaldba/postgres-mcp** -- production-grade Postgres MCP server -- https://github.com/crystaldba/postgres-mcp -- `repo`
- **modelcontextprotocol/servers** -- reference MCP server implementations -- https://github.com/modelcontextprotocol/servers -- `repo`
- Choosing an agent framework (LangChain/LangGraph/CrewAI/PydanticAI/Mastra/Vercel) -- Speakeasy comparison -- https://www.speakeasy.com/blog/ai-agent-framework-comparison -- `blog`
- AI Agent Frameworks 2026 deep dive -- youngju.dev -- https://www.youngju.dev/blog/culture/2026-05-16-ai-agent-frameworks-langchain-langgraph-llamaindex-crewai-autogen-pydanticai-mastra-dspy-mcp-2026-deep-dive.en -- `blog`
- LangGraph vs CrewAI vs AutoGen 2026 (or skip frameworks) -- DEV Community -- https://dev.to/cristian_iridon_286794874/langgraph-vs-crewai-vs-autogen-in-2026-pick-the-right-ai-agent-framework-or-skip-frameworks-4m2c -- `blog`
- 6 Multi-Agent Orchestration Patterns for Production -- beam.ai -- https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production -- `blog`
- Claude Agent SDK: Production Guide (tracing/subagents/eval) -- inference.net -- https://inference.net/content/claude-agent-sdk-production-guide/ -- `blog`
- Claude Code Full Stack: MCP/Skills/Subagents/Hooks -- alexop.dev -- https://alexop.dev/posts/understanding-claude-code-full-stack/ -- `blog`
- Claude Code in CI/CD & Headless Automation -- hidekazu-konishi.com -- https://hidekazu-konishi.com/entry/claude_code_cicd_and_headless_automation.html -- `blog`

### Orchestration papers (read before scaling a fleet)
- **Single-Agent LLMs Outperform Multi-Agent on Multi-Hop Under Equal Token Budgets** -- the "don't reach for multi-agent reflexively" result -- https://arxiv.org/html/2604.02460v1 -- `paper`
- **ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration** -- https://arxiv.org/html/2605.03042v1 -- `paper`
- **A-MapReduce: Wide Search via Agentic MapReduce** -- fan-out search pattern -- https://arxiv.org/pdf/2602.01331 -- `paper`
- **Talk Isn't Always Cheap: Failure Modes in Multi-Agent Debate** -- https://arxiv.org/pdf/2509.05396 -- `paper`
- Why Your Multi-Agent System Is Failing: the 17x Error Trap -- Towards Data Science -- https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/ -- `blog`

---

## 3. Eval, Observability & LLMOps

- **UKGovernmentBEIS/inspect_ai** -- rigorous open eval framework (UK AISI) -- https://github.com/UKGovernmentBEIS/inspect_ai -- `repo`
- **Inspect AI documentation** -- eval authoring docs -- https://inspect.aisi.org.uk/ -- `official-doc`
- **explodinggradients/ragas** -- RAG/LLM-output eval (faithfulness/relevance/recall) -- https://github.com/explodinggradients/ragas -- `repo`
- **langchain-ai/langsmith-sdk** -- tracing/testing/eval for LangChain/LangGraph -- https://github.com/langchain-ai/langsmith-sdk -- `repo`
- **Arize-ai/phoenix** -- open LLM observability (traces/evals/embeddings) -- https://github.com/Arize-ai/phoenix -- `repo`
- **langfuse/langfuse** -- self-hostable LLM observability + LLM-as-judge evals -- https://github.com/langfuse/langfuse -- `repo`
- Langfuse Observability Docs -- https://langfuse.com/docs/observability/overview -- `official-doc`
- Langfuse Self-Hosting -- https://langfuse.com/self-hosting -- `official-doc`
- LLM-as-a-Judge -- Langfuse docs -- https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge -- `official-doc`
- **LLMs-as-Judges: A Comprehensive Survey** -- when/whether to trust an LLM judge -- https://arxiv.org/pdf/2412.05579 -- `paper`
- LLM-as-a-Judge tutorial & best practices -- Patronus AI -- https://www.patronus.ai/llm-testing/llm-as-a-judge -- `blog`
- Rubric-Based Evals & LLM-as-a-Judge -- Adnan Masood (Medium) -- https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80 -- `blog`
- Best AI Eval Tools for CI/CD 2026 -- Braintrust -- https://www.braintrust.dev/articles/best-ai-evals-tools-cicd-2025 -- `blog`
- Top 5 LLM Observability Platforms 2026 (Langfuse/LangSmith/Helicone/Arize/W&B) -- https://guptadeepak.com/tools/top-5-llm-observability-platforms-2026/ -- `blog`
- Best LLM Observability Tools 2026 -- firecrawl.dev -- https://www.firecrawl.dev/blog/best-llm-observability-tools -- `blog`
- LLM Observability with self-hosted Langfuse + vLLM -- pyimagesearch -- https://pyimagesearch.com/2026/05/18/llm-observability-with-self-hosted-langfuse-and-vllm/ -- `blog`
- Mastering LLM Guardrails: 2026 Guide -- orq.ai -- https://orq.ai/blog/llm-guardrails -- `blog`

---

## 4. RAG / Retrieval / Knowledge Graphs

- **infiniflow/ragflow** -- end-to-end self-hostable RAG engine w/ citations -- https://github.com/infiniflow/ragflow -- `repo`
- **run-llama/llama_index** -- index parquet/JSON/PDF for hybrid retrieval (vault ingestion) -- https://github.com/run-llama/llama_index -- `repo`
- **langgenius/dify** -- visual RAG/workflow builder + MCP + deploy API -- https://github.com/langgenius/dify -- `repo`
- **microsoft/graphrag** -- graph-structured RAG over a corpus -- https://github.com/microsoft/graphrag -- `repo`
- Project GraphRAG -- Microsoft Research -- https://www.microsoft.com/en-us/research/project/graphrag/ -- `official-doc`
- Graphiti: Knowledge-Graph Memory for Agents -- Neo4j blog (fits the Obsidian vault graph) -- https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/ -- `blog`
- **A Hybrid Retrieval & Reranking Framework for Evidence-Grounded RAG** -- https://arxiv.org/abs/2605.01664 -- `paper`
- **Agentic RAG: A Survey** -- https://arxiv.org/html/2501.09136v4 -- `paper`
- **Survey on Reasoning Agentic RAG** -- ACL/IJCNLP 2025 -- https://aclanthology.org/2025.findings-ijcnlp.122.pdf -- `paper`
- RAG Is Not Dead: Advanced Retrieval Patterns 2026 -- DEV Community -- https://dev.to/young_gao/rag-is-not-dead-advanced-retrieval-patterns-that-actually-work-in-2026-2gbo -- `blog`
- Optimizing RAG with Hybrid Search & Reranking -- Superlinked VectorHub -- https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking -- `blog`
- Vector DB Comparison 2026 (Chroma/Qdrant/pgvector/Pinecone/LanceDB) -- 4xxi -- https://4xxi.com/articles/vector-database-comparison/ -- `blog`
- Vector DB Benchmarks 2026 -- CallSphere -- https://callsphere.ai/blog/vector-database-benchmarks-2026-pgvector-qdrant-weaviate-milvus-lancedb -- `blog`

### Fine-tune vs RAG (decide before training)
- **Training LLMs to Predict World Events** -- Mantic/Thinking Machines; forecasting-fine-tune evidence -- https://thinkingmachines.ai/news/training-llms-to-predict-world-events/ -- `blog`
- **BoostLLM: Boosting-Inspired Fine-Tuning for Few-Shot Tabular Classification** -- https://arxiv.org/html/2605.06117v2 -- `paper`
- RAG vs Fine-Tuning vs Prompt Engineering -- k2view -- https://www.k2view.com/blog/rag-vs-fine-tuning-vs-prompt-engineering/ -- `blog`
- Prompting vs RAG vs Fine-Tuning: not a ladder -- The New Stack -- https://thenewstack.io/prompting-vs-rag-vs-fine-tuning-why-its-not-a-ladder/ -- `blog`
- Fine-Tuning Infra: LoRA/QLoRA/PEFT at scale -- Introl -- https://introl.com/blog/fine-tuning-infrastructure-lora-qlora-peft-scale-guide-2025 -- `blog`

---

## 5. Sports Data Sources & Clients

### Clients / scrapers (Python)
- **swar/nba_api** -- NBA.com Stats + Live endpoints to DataFrames (in-use) -- https://github.com/swar/nba_api -- `repo`
- **nba_api PlayByPlay example notebook** -- live PBP recipe -- https://github.com/swar/nba_api/blob/master/docs/examples/PlayByPlay.ipynb -- `repo`
- **shufinskiy/nba-on-court** -- on-court lineup attribution for NBA PBP -- https://github.com/shufinskiy/nba-on-court -- `repo`
- **jldbc/pybaseball** -- Statcast / Baseball Reference / FanGraphs / Retrosheet -- https://github.com/jldbc/pybaseball -- `repo`
- **toddrob99/MLB-StatsAPI** -- Python wrapper for MLB Stats API -- https://github.com/toddrob99/MLB-StatsAPI -- `repo`
- **MLB-StatsAPI Endpoints Wiki** -- endpoint catalog -- https://github.com/toddrob99/MLB-StatsAPI/wiki/Endpoints -- `repo`
- **probberechts/soccerdata** -- one scraper for Club Elo/FBref/ESPN/Understat/Sofascore/WhoScored -- https://github.com/probberechts/soccerdata -- `repo`
- **statsbomb/statsbombpy** -- official StatsBomb client -- (see Modeling; client) -- https://github.com/statsbomb/statsbombpy -- `repo`
- **statsbomb/open-data** -- free StatsBomb event data -- https://github.com/statsbomb/open-data -- `repo`
- **statsbomb/amf-open-data** -- StatsBomb American football open data -- https://github.com/statsbomb/amf-open-data -- `repo`

### Tennis (canonical -- CC BY-NC-SA 4.0, non-commercial)
- **JeffSackmann/tennis_atp** -- ATP results/rankings 1968-present -- https://github.com/JeffSackmann/tennis_atp -- `repo`
- **JeffSackmann/tennis_wta** -- WTA equivalent -- https://github.com/JeffSackmann/tennis_wta -- `repo`
- **JeffSackmann/tennis_MatchChartingProject** -- charted serve/return point data -- https://github.com/JeffSackmann/tennis_MatchChartingProject -- `repo`
- **JeffSackmann/tennis_pointbypoint** -- sequential point-by-point (in-game conditioning) -- https://github.com/JeffSackmann/tennis_pointbypoint -- `repo`

### Baseball history
- **chadwickbureau/retrosheet** -- historical MLB event files on GitHub -- https://github.com/chadwickbureau/retrosheet -- `repo`
- Retrosheet Fall 2025 Release -- latest event-file drop -- https://www.retrosheet.org/fall2025release.html -- `official-doc`
- Retrosheet Game Data -- https://retrosheet.org/game.htm -- `official-doc`

### Live / public APIs (no client needed)
- **MLB Stats API** -- free official live API; base `https://statsapi.mlb.com/api/v1/` -- https://statsapi.mlb.com/api/v1/ -- `official-doc`
- **ESPN hidden scoreboard API** -- live scores: `site.api.espn.com/.../scoreboard` -- https://site.api.espn.com/apis/site/v2/sports/ -- `official-doc`
- **ESPN summary endpoint** -- PBP + box score by eventId -- https://site.api.espn.com/apis/site/v2/sports/ -- `official-doc`
- Free Football Data Guide -- SportsCampus -- https://english-programs.sportsdatacampus.com/free-football-data-websites/ -- `blog`
- Where to Get Free Football Data -- McKay Johns -- https://mckayjohns.substack.com/p/where-to-get-free-football-data -- `blog`

### GitHub topic feeds (discovery)
- Topic: soccer-analytics (Python, by stars) -- https://github.com/topics/soccer-analytics?l=python&o=desc&s=stars -- `repo`
- Topic: sports-prediction (Python, by stars) -- https://github.com/topics/sports-prediction?l=python&o=desc&s=stars -- `repo`
- Topic: betting (Python, by stars) -- https://github.com/topics/betting?l=python&o=desc&s=stars -- `repo`
- Topic: sports-ai (Python, by stars) -- https://github.com/topics/sports-ai?l=python&o=desc&s=stars -- `repo`

---

## 6. Sports Modeling (rating systems, score distributions, ensembles)

- **ML-KULeuven/socceraction** -- SPADL + VAEP + xT action-value framework -- https://github.com/ML-KULeuven/socceraction -- `repo`
- **ML-KULeuven/soccer_xg** -- plug-and-play xG model training on SPADL -- https://github.com/ML-KULeuven/soccer_xg -- `repo`
- **Torvaney/mezzala** -- Dixon-Coles / Poisson team-strength for soccer score dist -- https://github.com/Torvaney/mezzala -- `repo`
- **Friends-of-Tracking-Data-Analysis** -- tracking tutorials + Metrica open data + Opta parsers -- https://github.com/Friends-of-Tracking-Data-Analysis -- `repo`
- **abailey81/MatchOracle** -- deep EPL ensemble (Dixon-Coles + 13 learners + 376 features); architecture reference -- https://github.com/abailey81/MatchOracle -- `repo`
- **damienld/Tennis-predict** -- transparent surface-adjusted Elo vs bookmaker odds -- https://github.com/damienld/Tennis-predict -- `repo`
- **kyleskom/NBA-Machine-Learning-Sports-Betting** -- end-to-end NBA win-prob/props reference arch (NOT a validated edge) -- https://github.com/kyleskom/NBA-Machine-Learning-Sports-Betting -- `repo`
- **Neil-Paine-1/NBA-elo** -- post-538 NBA Elo archive -- https://github.com/Neil-Paine-1/NBA-elo -- `repo`
- **vraja2/rapm** -- Regularized Adjusted Plus-Minus implementation -- https://github.com/vraja2/rapm -- `repo`
- **fonnesbeck/hierarchical_models_sports_analytics** -- Bayesian hierarchical sports models -- https://github.com/fonnesbeck/hierarchical_models_sports_analytics -- `repo`
- **A Hierarchical Model for Rugby Prediction** -- PyMC example gallery (transferable hierarchy) -- https://www.pymc.io/projects/examples/en/latest/case_studies/rugby_analytics.html -- `official-doc`

### Modeling papers
- **Stacked Ensemble Model for NBA Game Outcome Prediction** (2025) -- https://pmc.ncbi.nlm.nih.gov/articles/PMC12357926/ -- `paper`
- **Hierarchical Bayesian Bradley-Terry for MLB** -- https://arxiv.org/pdf/1712.05879 -- `paper`
- **Lineup Regularized Adjusted Plus-Minus (L-RAPM)** -- https://arxiv.org/pdf/2601.15000 -- `paper`
- **Machine Learning for Soccer Match Result Prediction** -- https://arxiv.org/pdf/2403.07669 -- `paper`
- **Generalizing the Elo Rating System** (York preprint) -- https://www-users.york.ac.uk/~bp787/Generalizing_Elo_arxiv.pdf -- `paper`
- Football Prediction Models: Which Work Best? -- penaltyblog -- https://pena.lt/y/2025/03/10/which-model-should-you-use-to-predict-football-matches/ -- `blog`
- Dixon-Coles + Time-Weighting in Python -- dashee87 -- https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/ -- `blog`
- Bivariate Dixon-Coles model overview -- EmergentMind -- https://www.emergentmind.com/topics/bivariate-dixon-and-coles-model -- `blog`
- Bayesian Hierarchical MLB Win Probabilities (PyStan) -- Medium -- https://medium.com/@dmgrifka_64770/applying-bayesian-hierarchical-methods-to-mlb-season-win-probabilties-with-pystan-468572abb932 -- `blog`
- Elo Rating System -- Wikipedia -- https://en.wikipedia.org/wiki/Elo_rating_system -- `blog`
- Glicko Rating System -- Wikipedia -- https://en.wikipedia.org/wiki/Glicko_rating_system -- `blog`

### Autonomous-loop cautionary tale (required reading)
- **buildoak/tennis-xgboost-autoresearch** -- Karpathy-style auto-loop on 245K matches; documents the "gaming the eval gate" failure mode -- https://github.com/buildoak/tennis-xgboost-autoresearch -- `repo`

---

## 7. Sports Computer Vision & Tracking

- **roboflow/sports** -- player/ball detection, court keypoints (homography), jersey OCR, re-ID; MIT, pip-installable -- https://github.com/roboflow/sports -- `repo`
- **ultralytics/ultralytics** -- YOLOv8/YOLO11 detector backbone (AGPL-3.0 -- audit for commercial use) -- https://github.com/ultralytics/ultralytics -- `repo`
- **avijit9/awesome-computer-vision-in-sports** -- curated CV-in-sports paper list -- https://github.com/avijit9/awesome-computer-vision-in-sports -- `repo`
- **Darkmyter/Football-Players-Tracking** -- YOLOv8 + ByteTrack reference impl -- https://github.com/Darkmyter/Football-Players-Tracking -- `repo`
- **MichlF/sports_object_detection** -- includes TrackNetV2 for small-ball (tennis) tracking -- https://github.com/MichlF/sports_object_detection -- `repo`
- **SoccerNet** (org) -- broadcast-soccer benchmarks: action spotting, re-ID, calibration, tracking -- https://github.com/SoccerNet -- `repo`
- **SoccerNet/sn-tracking** -- open MOT benchmark + baselines -- https://github.com/SoccerNet/sn-tracking -- `repo`
- **Multi-Object Tracking with Ultralytics YOLO** -- BoT-SORT/ByteTrack/OC-SORT configs, ReID models -- https://docs.ultralytics.com/modes/track -- `official-doc`
- **SoccerNet Game State Reconstruction** (2025) -- SegFormer homography + OSNet TeamID + YOLOv5m pipeline, HOTA results -- https://arxiv.org/html/2504.06357v1 -- `paper`
- **TrackID3x3: Multi-Player Tracking + Pose for Basketball** (2025) -- YOLOX + ByteTrack + ViTPose -- https://arxiv.org/pdf/2503.18282 -- `paper`
- **Deep Learning for Sports Video Event Detection Survey** (2025) -- SoccerNet mAP benchmarks, T-DEED, COMEDIAN -- https://arxiv.org/html/2505.03991v3 -- `paper`
- **SRITrack: Online MOT for Sports Broadcasting w/ Re-entry ID** (2025) -- re-entry identity stability -- https://www.sciencedirect.com/science/article/abs/pii/S0957417426014120 -- `paper`
- Homography-based Player Identification in Live Sports (2023) -- court-mapping methodology -- https://www.researchgate.net/publication/373127328_Homography_based_Player_Identification_in_Live_Sports -- `paper`
- How to Detect/Track/Identify Basketball Players -- Roboflow blog (RF-DETR + SAM2 + SigLIP) -- https://blog.roboflow.com/identify-basketball-players/ -- `blog`
- Ball Tracking in Sports with CV -- Roboflow blog -- https://blog.roboflow.com/tracking-ball-sports-computer-vision/ -- `blog`

---

## 8. Odds / Devig / Calibration Tools

- **mberk/shin** -- Shin's-method margin removal; the rigorous single-method devig lib -- https://github.com/mberk/shin -- `repo`
- **sedemmler/WagerBrain** -- odds conversion + devig (multiplicative/additive/power/Shin) + Kelly/EV, zero deps -- https://github.com/sedemmler/WagerBrain -- `repo`
- **betcode-org/flumine** -- Betfair exchange trading framework (live liquidity signal) -- https://github.com/betcode-org/flumine -- `repo`
- **pretrehr/Sports-betting** -- portfolio optimization over markets -- https://github.com/pretrehr/Sports-betting -- `repo`
- **scikit-learn Probability Calibration** -- isotonic / sigmoid / reliability curves -- https://scikit-learn.org/stable/modules/calibration.html -- `official-doc`
- **The Odds API V4 Documentation** -- multi-book odds API -- https://the-odds-api.com/liveapi/guides/v4/ -- `official-doc`
- Odds API Pricing 2026 Comparison -- OddsPapi -- https://oddspapi.io/blog/odds-api-pricing-2026-comparison/ -- `blog`
- Pinnacle API 2026 Overview -- sportsapis.dev -- https://sportsapis.dev/pinnacle-api -- `blog`
- SharpAPI Pinnacle Odds API -- https://sharpapi.io/sportsbooks/pinnacle-odds-api -- `tool`
- BettingIsCool Historical Odds API -- https://api.bettingiscool.com/ -- `tool`
- How to Devig Odds (methods compared) -- Outlier -- https://help.outlier.bet/en/articles/8208129-how-to-devig-odds-comparing-the-methods -- `blog`
- Devigging Methods Explained (Power/Shin/Additive/Multiplicative) -- BetHero -- https://betherosports.com/blog/devigging-methods-explained -- `blog`
- Auto De-Vig Pinnacle Odds (4 methods) -- PinnacleOddsdropper -- https://www.pinnacleoddsdropper.com/guides/how-to-devig-pinnacle-s-odds-for-betting-on-soft-books -- `blog`
- Closing Line Value (CLV) Demystified -- Buchdahl / PinnacleOddsdropper -- https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl -- `blog`

---

## 9. Calibration, Scoring Rules & Market-Efficiency Papers

### Calibration & proper scoring (the project's north-star metrics)
- **ML for sports betting: accuracy or calibration?** (Walsh & Joshi 2024) -- the keystone "calibrate, don't chase accuracy" paper -- https://arxiv.org/abs/2303.06021 -- `paper`
  - ScienceDirect version -- https://www.sciencedirect.com/science/article/pii/S266682702400015X -- `paper`
- **A Systematic Review of ML in Sports Betting** (2024) -- https://arxiv.org/html/2410.21484v1 -- `paper`
- **"Calibeating": Beating Forecasters at Their Own Game** -- directly on the north star (beat the best predictor on calibration) -- https://arxiv.org/pdf/2209.04892 -- `paper`
- **Proper Scoring Rules for Estimation & Forecast Evaluation** -- https://arxiv.org/pdf/2504.01781 -- `paper`
- **Proper scoring rules for multivariate probabilistic forecasts** (ASCMO 2025) -- https://ascmo.copernicus.org/articles/11/23/2025/ascmo-11-23-2025.pdf -- `paper`
- **Classifier Calibration: a survey** -- https://arxiv.org/pdf/2112.10327 -- `paper`
- **Classifier Calibration at Scale: post-hoc methods** -- https://arxiv.org/pdf/2601.19944 -- `paper`
- **Verification of probability forecasts for football: reliability & discrimination** -- https://arxiv.org/pdf/2106.14345 -- `paper`
- **Conformal Win Probability** (NCAA 2020) -- distribution-free intervals -- https://www.tandfonline.com/doi/full/10.1080/00031305.2023.2283199 -- `paper`
- **Comparing Probabilistic Forecasting Systems with the Brier Score** (AMS) -- https://journals.ametsoc.org/view/journals/wefo/22/5/waf1034_1.xml -- `paper`
- Platt Scaling / Isotonic / Temperature deep dive -- KDnuggets -- https://www.kdnuggets.com/a-deep-dive-into-calibration-of-language-models-platt-scaling-isotonic-regression-temperature-scaling -- `blog`
- Brier vs Log Loss vs Calibration -- MetricGate -- https://metricgate.com/blogs/brier-score-vs-log-loss-vs-calibration/ -- `blog`
- Diebold-Mariano Test for Forecast Accuracy -- EmergentMind (model-vs-close significance) -- https://www.emergentmind.com/topics/diebold-mariano-test -- `blog`
- Calibration Over Accuracy in Sports Betting -- OpticOdds -- https://opticodds.com/blog/calibration-the-key-to-smarter-sports-betting -- `blog`

### Market efficiency, CLV & validation discipline
- **Comparing Two Methods for Testing Sports-Betting Market Efficiency** (Hegarty & Whelan 2024) -- https://www.sciencedirect.com/science/article/abs/pii/S2773161824000193 -- `paper`
- **Weak Form Efficiency in Sports Betting Markets** (2023) -- https://www.researchgate.net/publication/371069739_Weak_Form_Efficiency_in_Sports_Betting_Markets -- `paper`
- **Beating the Average: Exploiting Soccer Betting Inefficiencies** (2023) -- https://arxiv.org/abs/2303.16648 -- `paper`
- **Intransitive Player Dominance & Market Inefficiency in Tennis (GNN)** (2025) -- one of the few credible inefficiency claims -- https://arxiv.org/pdf/2510.20454 -- `paper`
- **Risk Aversion & Favourite-Longshot Bias** (Whelan, Economica 2024) -- https://onlinelibrary.wiley.com/doi/10.1111/ecca.12500 -- `paper`
- Walk-Forward Optimization -- QuantInsti (leak-free backtest discipline) -- https://blog.quantinsti.com/walk-forward-optimization-introduction/ -- `blog`
- Combinatorial Purged Cross-Validation -- Towards AI (Lopez de Prado method) -- https://towardsai.net/p/l/the-combinatorial-purged-cross-validation-method -- `blog`

---

## 10. In-Game / Live Modeling (the decisive edge in this project)

- **Bayesian estimation of in-game NBA home-team win probability** -- https://arxiv.org/abs/2207.05114 -- `paper`
- **iWinRNFL: Simple, Interpretable, Well-Calibrated In-Game NFL Win-Prob** -- the calibration-first template -- https://arxiv.org/abs/1704.00197 -- `paper`
- **A Deep Learning Approach for Live Win Probability in NBA** (Springer) -- https://link.springer.com/chapter/10.1007/978-3-032-27272-0_7 -- `paper`
- A State-Dependent Framework for Basketball Win Probability -- Statsurge -- https://statsurge.substack.com/p/a-state-dependent-framework-for-basketball -- `blog`
- A Bayesian Approach to In-Game Win Probability (soccer) -- DTAI KU Leuven -- https://dtai.cs.kuleuven.be/static/sports/blog/a-bayesian-approach-to-in-game-win-probability/ -- `blog`
- Estimating NBA In-Game Win-Prob with a (not so) deep NN -- Medium -- https://medium.com/@zukiewicz.piotr/estimating-nba-in-game-win-probability-with-a-not-so-deep-neural-network-f6731a2e0ea9 -- `blog`
- Low Latency at Scale: Competitive Edge in Sports Betting -- Ably (live infra) -- https://ably.com/blog/low-latency-sports-betting -- `blog`

---

## 11. LLMs Applied to Sports / Forecasting

- **Wisdom of the Silicon Crowd: LLM ensemble prediction rivals human crowds** (PMC 2025) -- https://pmc.ncbi.nlm.nih.gov/articles/PMC11800985/ -- `paper`
- **Language Model Probabilities are NOT Calibrated in Numeric Contexts** -- critical caveat for LLM-emitted probabilities -- https://arxiv.org/abs/2410.16007 -- `paper`
- **Predicting Football Match Outcomes Using LLMs: A Comparative Study** (2025) -- https://sciety.org/articles/activity/10.31235/osf.io/e5wpy_v2 -- `paper`
- **Automated Explanation of ML Models of Footballing Actions in Words** (2025) -- https://arxiv.org/html/2504.00767v1 -- `paper`
- **SportsMetrics: Blending Text & Numerical Data in LLMs** (2024) -- info-fusion limits -- https://arxiv.org/pdf/2402.10979 -- `paper`
- Structured data extraction via LLM schemas -- Simon Willison -- https://simonwillison.net/2025/Feb/28/llm-schemas/ -- `blog`
- LLM Structured Outputs: Schema Validation for Real Pipelines 2026 -- Collin Wilkins -- https://collinwilkins.com/articles/structured-output -- `blog`

---

## 12. AI Product Moats (positioning the platform)

- **The New Moat: Proprietary Data as the Durable Advantage** -- AI Ireland -- https://aiireland.ie/2026/03/25/the-new-moat-why-proprietary-data-is-your-only-durable-competitive-advantage-in-ai/ -- `blog`
- Data Flywheel: The Only AI Moat That Compounds -- Rohit Prabhakar -- https://www.rohitprabhakar.com/blog/market-of-one-data-flywheel-competitive-moat/ -- `blog`
- AI Moats in 2026: What Still Defends Your Product -- Valtorian -- https://www.valtorian.com/blog/ai-moats-2026 -- `blog`
- Foundation Models Are Commodities -- Here's Your Real AI Moat -- Ellithorpe (Medium) -- https://medium.com/@jellithorpe/foundation-models-are-commodities-heres-your-real-ai-moat-cc51ec47584c -- `blog`
- Building Competitive Strategic Moats with AI -- McKinsey/QuantumBlack -- https://www.mckinsey.com/capabilities/quantumblack/our-insights/from-ai-table-stakes-to-ai-advantage-building-competitive-moats -- `blog`
- AI Killed the Feature Moat (what defends SaaS in 2026) -- Steven Cen (Medium) -- https://medium.com/@cenrunzhe/ai-killed-the-feature-moat-heres-what-actually-defends-your-saas-company-in-2026-9a5d3d20973b -- `blog`
- Beyond Functionality: Durable Moats in the AI Era -- Codurance -- https://www.codurance.com/publications/beyond-functionality-building-durable-moats-in-the-ai-era -- `blog`
- How Calibration Supercharges an AI Sports-Betting Model -- SportBot AI -- https://www.sportbotai.com/blog/calibration-ai-sports-betting-model-1775671361692 -- `blog`

---

## Highest-leverage starting set (if you read only 10)
1. Building Effective Agents (Anthropic) -- agent vs workflow taxonomy.
2. ML for sports betting: accuracy or calibration? (Walsh & Joshi) -- the north-star metric, validated.
3. "Calibeating" (arXiv 2209.04892) -- formal version of "beat the best predictor on calibration."
4. anthropics/anthropic-cookbook patterns/agents -- runnable orchestrator-worker / evaluator-optimizer.
5. mberk/shin + sedemmler/WagerBrain -- devig the close into the probability bar to beat.
6. roboflow/sports -- the broadcast-CV moat in one MIT package.
7. iWinRNFL -- the calibration-first in-game win-prob template.
8. Single-Agent > Multi-Agent under equal token budgets (arXiv 2604.02460) -- don't over-build the fleet.
9. buildoak/tennis-xgboost-autoresearch -- how an auto-loop games its own gate (avoid this).
10. Walk-Forward + Combinatorial Purged CV -- the leak-free validation discipline backing every honest reject.

## Project-internal companions (read alongside this index)
- docs/research/edge-taxonomy.md -- catalog of edges per sport/market.
- docs/research/data-sources.md -- expanded data-source detail.
- docs/research/market-microstructure.md -- devig / CLV / book behavior.
- docs/research/validation-methodology.md -- the project's leak-free OOS protocol.
- docs/research/competitive-landscape.md and precedent-analysis.md -- who else does this and how.

## Sources
This index aggregates and de-duplicates the "Sources" sections of all briefs in `docs/research/ai-leverage-2026-06-16/briefs/`: anthropic-agent-patterns, agentic-orchestration, agent-frameworks, ai-product-moats, calibration-scoring, claude-api-core, claude-api-scale, claude-agent-sdk, claude-code-power, claude-computer-use, claude-mcp, claude-skills, evals-quality, finetune-vs-rag, github-sports-repos, ingame-live-modeling, llm-in-sports, llmops-observability, market-efficiency-clv, rag-retrieval, sports-cv-tracking, sports-data-sources, sports-modeling-core. Every URL above is preserved from those briefs; categorization and one-line value notes are editorial.
