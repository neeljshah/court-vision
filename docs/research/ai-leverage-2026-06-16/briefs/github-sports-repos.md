# GitHub Sports Repos -- Curated High-Signal Index
_Researched 2026-06-16. Scope: 30+ repos across sports modeling, CV tracking, odds/devig, agent frameworks, eval, and RAG -- prioritized for a solo-built calibrated multi-sport prediction platform._

## TL;DR (highest-leverage takeaways)
- **JeffSackmann's tennis data repos** (tennis_atp / tennis_wta) are the canonical free ATP/WTA dataset used by every serious tennis Elo model; CC-BY-NC-SA so commercial use needs care.
- **pybaseball** (1.5k stars, MIT) and **nba_api** (3.7k stars, MIT) are the go-to Python clients for Statcast/FanGraphs and NBA.com respectively; both actively maintained through 2026.
- **ML-KULeuven/socceraction** (VAEP/xT framework) + **probberechts/soccerdata** (multi-source scraper) cover the soccer analytics stack; soccer_xg adds plug-and-play xG model training.
- **roboflow/sports** (5.1k stars, MIT) is the fastest path to field/court keypoint detection, ball detection, jersey OCR -- directly relevant to the broadcast CV moat.
- **WagerBrain** and **shin** are the clearest devig/calibration math libraries; avoid repos that claim ROI/edge without OOS proof.
- Agent frameworks: **LangGraph** for stateful multi-step agents, **RAGFlow** (70k stars) for document-anchored RAG, **Dify** for workflow deployment -- all production-tested in 2025-2026.
- **RAGAS** and **LangSmith** are the eval layer; run calibration (Brier/log-loss) on any LLM-generated probability the same way you run it on model outputs.
- Many sports-betting repos claim high ROI with single-fold backtests -- treat as prototypes, not validated edges. Always check for walk-forward and OOS discipline.

---

## Key Capabilities / Techniques

### BASKETBALL (NBA)

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **swar/nba_api** | Python client for all NBA.com Stats + Live endpoints; DataFrames out of the box; covers play-by-play, boxscores, lineups, shot charts | https://github.com/swar/nba_api | 3.7k stars | MIT |
| **kyleskom/NBA-Machine-Learning-Sports-Betting** | End-to-end NBA win-prob + props pipeline with calibrated Kelly sizing; useful as a reference architecture (not a validated edge source) | https://github.com/kyleskom/NBA-Machine-Learning-Sports-Betting | ~1k stars | MIT |

### BASEBALL (MLB)

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **jldbc/pybaseball** | Scrapes Statcast (pitch-level), Baseball Reference, FanGraphs; includes Retrosheet game logs via Chadwick Bureau | https://github.com/jldbc/pybaseball | 1.5k stars | MIT |
| **chadwickbureau/retrosheet** (data) | Historical MLB event files (Retrosheet) re-hosted on GitHub; pairs with pybaseball for deep historical modeling | https://github.com/chadwickbureau/retrosheet | ~300 stars | Public domain (Retrosheet terms) |

### SOCCER / FOOTBALL

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **ML-KULeuven/socceraction** | SPADL format converter + VAEP (action value) + xT (expected threat) models; works with StatsBomb, Wyscout, Opta | https://github.com/ML-KULeuven/socceraction | ~800 stars | MIT |
| **ML-KULeuven/soccer_xg** | Plug-and-play xG model training (logistic, gradient boosted, neural net) on SPADL event data | https://github.com/ML-KULeuven/soccer_xg | ~300 stars | MIT |
| **probberechts/soccerdata** | Scrapes Club Elo, FBref, ESPN, Football-Data.co.uk, Understat, Sofascore, WhoScored into unified DataFrames | https://github.com/probberechts/soccerdata | 1.8k stars | MIT |
| **Torvaney/mezzala** | Dixon-Coles and Poisson regression team-strength models for soccer; small but high-signal for calibrated score distribution | https://github.com/Torvaney/mezzala | ~40 stars | MIT |
| **statsbomb/statsbombpy** | Official StatsBomb Python client; access free open-data (Women's World Cup, EURO, Champions League samples) | https://github.com/statsbomb/statsbombpy | ~700 stars | MIT (data has separate terms) |
| **Friends-of-Tracking-Data** (org) | Repository of tracking-data tutorials, Metrica Sports open data, Opta F24 parsers -- the reference collection for pitch-tracking analysis | https://github.com/Friends-of-Tracking-Data-Analysis | org-level; multiple repos | Mixed MIT/CC |
| **abailey81/MatchOracle** | Deep ensemble EPL predictor: Dixon-Coles + 13 base learners + 376 features + NLP sentiment; useful as architecture reference | https://github.com/abailey81/MatchOracle | ~5 stars | check repo |

### TENNIS

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **JeffSackmann/tennis_atp** | Historical ATP match results, rankings, stats from 1968 to present -- the canonical free dataset for Elo models | https://github.com/JeffSackmann/tennis_atp | 1.6k stars | CC BY-NC-SA 4.0 |
| **JeffSackmann/tennis_wta** | Same as above for WTA; complete from 1968 | https://github.com/JeffSackmann/tennis_wta | ~310 stars | CC BY-NC-SA 4.0 |
| **JeffSackmann/tennis_MatchChartingProject** | Point-by-point charted data for pro matches (user-submitted); best source for serve/return breakdowns | https://github.com/JeffSackmann/tennis_MatchChartingProject | 347 stars | CC BY-NC-SA 4.0 |
| **JeffSackmann/tennis_pointbypoint** | Sequential point-by-point data for tens of thousands of pro matches | https://github.com/JeffSackmann/tennis_pointbypoint | ~200 stars | CC BY-NC-SA 4.0 |
| **buildoak/tennis-xgboost-autoresearch** | Karpathy-style autonomous loop for tennis prediction: 245K matches, chess Elo + XGBoost; documents the "gaming the eval gate" failure mode -- required reading for loop design | https://github.com/buildoak/tennis-xgboost-autoresearch | low stars | check repo |
| **damienld/Tennis-predict** | ATP/WTA Elo + surface-adjusted predictions vs bookmaker odds; transparent implementation | https://github.com/damienld/Tennis-predict | ~50 stars | check repo |

---

### SPORTS COMPUTER VISION

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **roboflow/sports** | CV toolkit for sports: player/ball detection, field/court keypoint detection, jersey number OCR, re-ID; pip-installable; Roboflow Universe datasets included | https://github.com/roboflow/sports | 5.1k stars | MIT |
| **avijit9/awesome-computer-vision-in-sports** | Curated paper list: player tracking, ball localization, action spotting, team recognition, SoccerNet benchmark; survey starting point | https://github.com/avijit9/awesome-computer-vision-in-sports | ~400 stars | N/A (list) |
| **Darkmyter/Football-Players-Tracking** | YOLOv8 + ByteTrack for player, referee, ball tracking in football video; good reference implementation | https://github.com/Darkmyter/Football-Players-Tracking | ~200 stars | check repo |
| **MichlF/sports_object_detection** | Object detection + tracking in sports video; includes TrackNetV2 for tennis ball detection -- directly applicable to tennis ball tracking | https://github.com/MichlF/sports_object_detection | ~50 stars | check repo |
| **SoccerNet** (datasets) | Major benchmark for broadcast soccer: action spotting, player re-ID, camera calibration, tracking -- pairs with models from CVPR/ECCV challenges | https://github.com/SoccerNet | org-level | research/academic |
| **ultralytics/ultralytics** | YOLOv8/YOLO11: the detection backbone used by every sports CV repo above; train custom player/ball detectors | https://github.com/ultralytics/ultralytics | 40k+ stars | AGPL-3.0 |

---

### ODDS / DEVIG / CALIBRATION TOOLS

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **mberk/shin** | Python implementation of Shin's method for removing bookmaker margin from implied odds; the most rigorous single-method devig library | https://github.com/mberk/shin | ~100 stars | MIT |
| **sedemmler/WagerBrain** | Core betting math: odds conversion (American/decimal/fractional), devig (multiplicative/additive/power/Shin), Kelly criterion, expected value -- zero dependencies | https://github.com/sedemmler/WagerBrain | ~300 stars | check repo |
| **betcode-org/flumine** | Betfair exchange trading framework; useful if live liquidity data becomes a signal source | https://github.com/betcode-org/flumine | ~240 stars | MIT |
| **pretrehr/Sports-betting** | Portfolio-style sports betting assistant with optimization over multiple markets | https://github.com/pretrehr/Sports-betting | ~524 stars | check repo |

---

### AGENT FRAMEWORKS

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **langchain-ai/langchain** | Modular LLM framework: chains, tools, memory, retrieval, multi-agent; largest ecosystem; use for orchestrating signal-proposer and LLM-scheme layers | https://github.com/langchain-ai/langchain | 130k+ stars | MIT |
| **langchain-ai/langgraph** | Stateful graph-based agent workflows on top of LangChain; best for multi-step, multi-agent orchestration with conditional branching | https://github.com/langchain-ai/langgraph | ~15k stars | MIT |
| **crewAIInc/crewAI** | Role-based multi-agent crews; simpler than LangGraph for parallel specialist agents (e.g. signal-discovery fleet) | https://github.com/crewAIInc/crewAI | ~30k stars | MIT |
| **microsoft/autogen** (AG2) | Microsoft's multi-agent conversation framework; strong for code-executing agents with back-and-forth reasoning | https://github.com/microsoft/autogen | ~40k stars | MIT |
| **anthropics/anthropic-sdk-python** | Official Anthropic Python SDK; use for direct Claude API calls, tool use, streaming -- the primitive under Claude Code | https://github.com/anthropics/anthropic-sdk-python | ~3k stars | MIT |

---

### RAG / KNOWLEDGE RETRIEVAL

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **infiniflow/ragflow** | End-to-end RAG engine: document ingestion, vector indexing, citation tracking, tool-using agents; enterprise-grade and self-hostable | https://github.com/infiniflow/ragflow | 70k+ stars | Apache 2.0 |
| **run-llama/llama_index** | LLM data framework: index any data source (parquet, JSON, PDFs), structured/unstructured hybrid retrieval; pairs well with vault knowledge ingestion | https://github.com/run-llama/llama_index | 48k+ stars | MIT |
| **langgenius/dify** | Visual workflow builder + RAG management + MCP integration + deployment API; good for wrapping prediction pipelines as queryable agents | https://github.com/langgenius/dify | 130k+ stars | Apache 2.0 |

---

### EVAL / OBSERVABILITY TOOLS

| Repo | What it does | URL | Popularity | License |
|---|---|---|---|---|
| **explodinggradients/ragas** | RAG evaluation framework: faithfulness, answer relevance, context recall -- run the same rigor on LLM outputs as Brier score on model predictions | https://github.com/explodinggradients/ragas | ~10k stars | Apache 2.0 |
| **langchain-ai/langsmith** (SDK) | Tracing + testing + eval for LangChain/LangGraph agents; production observability | https://github.com/langchain-ai/langsmith-sdk | ~1k stars | MIT |
| **Arize-ai/phoenix** | Open-source LLM observability: traces, evals, embeddings; pairs with any agent framework | https://github.com/Arize-ai/phoenix | ~5k stars | ELv2 |

---

## How THIS Project Should Use It

**Data acquisition:**
- **nba_api** -> already in use; cover live endpoints (nba_api.live) for in-game state signals.
- **pybaseball** -> Statcast pitch-velocity / exit-velocity / launch-angle are the freshest per-at-bat signals; plug into the MLB in-game conditioning layer.
- **JeffSackmann/tennis_atp** + **tennis_wta** -> feed directly into the ATP/WTA Elo engine; point-by-point data (tennis_pointbypoint) unlocks in-game serve/return conditioning (exactly the decisive in-game edge proven 4/4).
- **probberechts/soccerdata** -> one-stop multi-source scraper for the soccer domain; replaces ad-hoc scrapers.

**Soccer modeling:**
- **Torvaney/mezzala** (Dixon-Coles) -> use as the score-distribution prior; feeds into calibrated O/U prediction, mirroring the Poisson approach already validated for soccer.
- **socceraction** VAEP -> player-action value for in-game "realized state" conditioning; treat as a signal, not a betting edge.

**Computer vision:**
- **roboflow/sports** -> fastest path to court keypoint detection (homography), player detection, jersey OCR on broadcast clips; MIT license means it can ship.
- **ultralytics/ultralytics** -> YOLOv8/YOLO11 as the detector backbone; already the industry standard for real-time inference.
- **MichlF/sports_object_detection** -> pull TrackNetV2 for the small-ball (tennis) tracking problem.

**Odds / calibration:**
- **WagerBrain** + **shin** -> use for devig (produce true probabilities from market odds) for the calibration benchmark; the devigged close is the bar to beat on accuracy -- these libraries implement the math cleanly.
- Do NOT use repos that claim ROI without published walk-forward OOS proof.

**Agent / RAG layer:**
- **LangGraph** -> upgrade the signal-proposer / LLM-scheme layer from single-call to a stateful graph that can iterate: propose -> gate-test -> accept/reject -> next signal.
- **LlamaIndex** -> index the Obsidian vault (parquet + Markdown notes) for retrieval; enables "query the intelligence graph" without rebuilding manually.
- **RAGFlow** or **Dify** -> if the prediction pipeline needs to be queryable as a product (API + UI); not urgent while solo.

**Eval:**
- **RAGAS** -> evaluate any LLM-generated probability or scheme-prior for faithfulness to source data (vault notes); run alongside Brier score.
- **Phoenix** -> add traces to the LLM-scheme layer so you can see which vault nodes the LLM cited when generating a prior multiplier.

---

## Gotchas / Limits

- **JeffSackmann tennis data**: CC BY-NC-SA 4.0 -- non-commercial only; the productized sellable package CANNOT include this data directly; must be user-supplied or replaced with a commercial source.
- **nba_api rate limits**: NBA.com blocks aggressive scraping; use built-in rate limiting and caching; the CDN liveData endpoint (cdn.nba.com) is more reliable than stats.nba.com for live PBP.
- **roboflow/sports**: MIT for the code but the Roboflow Universe datasets have separate terms; check before embedding in a commercial product.
- **ultralytics AGPL-3.0**: requires open-sourcing any derivative work distributed as a product; for a commercial predictor package, audit carefully or use the Ultralytics commercial license.
- **socceraction** is no longer actively maintained (as of 2025); use it for reproducibility / paper re-implementation, but don't rely on it for ongoing data pipeline.
- **LangChain ecosystem churn**: the framework evolves fast; pin versions in requirements; LangGraph is more stable than the base LangChain chains API.
- **All sports-betting repos claiming ROI**: nearly all use single-fold backtests or in-sample tuning; treat as architecture references only; validate any signal they use through the existing honest gate (src.loop.gate) before trusting it.
- **buildoak/tennis-xgboost-autoresearch** is a cautionary tale: the autonomous loop learned to game its own evaluation metric -- directly relevant to the self-improving loop design; read the README.
- **pybaseball Retrosheet**: event files are large and parsing is slow; pre-process to parquet once and cache.

---

## Sources

- [ML-KULeuven/soccer_xg on GitHub](https://github.com/ML-KULeuven/soccer_xg)
- [ML-KULeuven/socceraction on GitHub](https://github.com/ML-KULeuven/socceraction)
- [probberechts/soccerdata on GitHub](https://github.com/probberechts/soccerdata) (via soccer-analytics topic page)
- [swar/nba_api on GitHub](https://github.com/swar/nba_api)
- [jldbc/pybaseball on GitHub](https://github.com/jldbc/pybaseball)
- [JeffSackmann/tennis_atp on GitHub](https://github.com/JeffSackmann/tennis_atp)
- [JeffSackmann/tennis_wta on GitHub](https://github.com/JeffSackmann/tennis_wta)
- [JeffSackmann/tennis_MatchChartingProject on GitHub](https://github.com/JeffSackmann/tennis_MatchChartingProject)
- [roboflow/sports on GitHub](https://github.com/roboflow/sports)
- [avijit9/awesome-computer-vision-in-sports on GitHub](https://github.com/avijit9/awesome-computer-vision-in-sports)
- [buildoak/tennis-xgboost-autoresearch on GitHub](https://github.com/buildoak/tennis-xgboost-autoresearch)
- [GitHub topics: soccer-analytics (Python, stars desc)](https://github.com/topics/soccer-analytics?l=python&o=desc&s=stars)
- [GitHub topics: sports-prediction (Python, stars desc)](https://github.com/topics/sports-prediction?l=python&o=desc&s=stars)
- [GitHub topics: betting (Python, stars desc)](https://github.com/topics/betting?l=python&o=desc&s=stars)
- [Top AI GitHub Repositories in 2026 -- ByteByteGo](https://blog.bytebytego.com/p/top-ai-github-repositories-in-2026)
- [Best AI Agent Frameworks 2026 -- LangChain resources](https://www.langchain.com/resources/ai-agent-frameworks)
- [Roboflow blog: Ball Tracking in Sports with Computer Vision](https://blog.roboflow.com/tracking-ball-sports-computer-vision/)
- [GitHub topics: sports-ai (Python)](https://github.com/topics/sports-ai?l=python&o=desc&s=stars)
- [damienld/Tennis-predict on GitHub](https://github.com/damienld/Tennis-predict)
