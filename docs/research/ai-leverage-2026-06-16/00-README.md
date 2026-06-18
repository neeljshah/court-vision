# AI Leverage Research -- 2026-06-16

Overnight deep-research pass on **how to wield AI at the highest level** (Claude Code / SDK / API /
Skills / MCP, agent patterns, RAG, evals, frameworks, LLMOps) and the **sports-AI / quant state of the
art**, synthesized into an honest roadmap to take this calibrated multi-sport predictor from foundation
to a real product. Produced by a multi-wave agent research fleet (27 cited briefs -> 6 synthesis docs +
6 build blueprints + execution plan), adversarially QA'd.

## Read in this order

0. **[HOW-TO-USE-AI-AT-THE-HIGHEST-LEVEL.md](HOW-TO-USE-AI-AT-THE-HIGHEST-LEVEL.md)** -- the direct answer to
   "how can I use AI to the highest level": operating principles, the daily/nightly rhythm, the mindset shifts.
1. **[MORNING-BRIEF.md](MORNING-BRIEF.md)** -- 3-minute summary: what was found, the top moves, how to navigate.
2. **[05-elevation-roadmap.md](05-elevation-roadmap.md)** -- THE plan. Thesis, ranked leverage, Now/Next/Later
   phases (each with how-to-validate-leak-free + which AI technique accelerates it), productization, risk table.
3. **[01-claude-mastery.md](01-claude-mastery.md)** -- wield Claude: Code vs SDK vs API, Skills, subagents/hooks/MCP,
   API power features (caching/batch/structured output/extended thinking), model selection, a 10x build-loop blueprint.
4. **[02-ai-engineering-playbook.md](02-ai-engineering-playbook.md)** -- agent patterns, retrieval/knowledge layer,
   EVAL-DRIVEN development, fine-tune-vs-RAG, a minimal stack, observability.
5. **[03-sports-ai-sota.md](03-sports-ai-sota.md)** -- data, modeling per sport, calibration + proper scoring,
   market/CLV evaluation, in-game conditioning, the CV moat (honest ceilings), the LLM intel layer.
6. **[04-resource-index.md](04-resource-index.md)** -- curated repos / papers / tools / docs with links (the bookmark file).
7. **[06-productization-gtm.md](06-productization-gtm.md)** -- "make it something": how to productize calibration rigor as
   decision-support (comparables, trust artifacts, distribution, monetization, the 90-day first-public-artifact plan) -- never picks/tout.

## Implementation blueprints (`blueprints/`) -- ready-to-build designs

Concrete, copyable designs for the highest-leverage roadmap items (each: goal + done-criteria,
architecture, implementation sketch with real pseudocode/config, leak-free validation plan, effort,
gotchas). All grounded in the repo's actual files and the binding invariants.

- **[blueprints/eval-gate.md](blueprints/eval-gate.md)** -- N1, the keystone: Brier-Skill-Score CI gate + golden dataset.
- **[blueprints/ingame-blend.md](blueprints/ingame-blend.md)** -- N3/X2, the #1 lever: condition the pregame prior on live state.
- **[blueprints/freshness-pipeline.md](blueprints/freshness-pipeline.md)** -- X1: structured injury/lineup extraction -> vacated-load.
- **[blueprints/knowledge-rag.md](blueprints/knowledge-rag.md)** -- a retrieval layer over the intel vault (synthesis only, never the number).
- **[blueprints/claude-build-loop.md](blueprints/claude-build-loop.md)** -- hooks/skills/MCP/cron + model routing to 10x the loop (shared-config items flagged human-confirm).
- **[blueprints/mcp-and-ledger.md](blueprints/mcp-and-ledger.md)** -- a `sports_predictor` MCP server + the append-only track-record ledger (the trust moat).
- **[INSTALLED-TOOLKIT.md](INSTALLED-TOOLKIT.md)** -- the Claude Code skills/agents/tools actually available in this environment, mapped to project uses.
- **[IMPLEMENTATION-KICKOFF.md](IMPLEMENTATION-KICKOFF.md)** -- the single ordered 30/60/90 execution plan + a first-session prompt.
- **[reference-impl/README.md](reference-impl/README.md)** -- REAL, tested code for the keystone's pure core (scoring, cluster-robust
  Diebold-Mariano, golden-set schema + leak guard); 8/8 tests pass offline. Drop into `scripts/platformkit/eval_gate/` when ready.

## The 27 source briefs (`briefs/`)

Claude / Anthropic mastery: `claude-skills`, `claude-code-power`, `claude-mcp`, `claude-agent-sdk`,
`claude-api-core`, `claude-api-scale`, `anthropic-agent-patterns`, `claude-computer-use`.

AI engineering: `agentic-orchestration`, `rag-retrieval`, `evals-quality`, `finetune-vs-rag`,
`agent-frameworks`, `llmops-observability`.

Sports AI / quant: `sports-data-sources`, `sports-modeling-core`, `calibration-scoring`,
`market-efficiency-clv`, `ingame-live-modeling`, `sports-cv-tracking`, `llm-in-sports`.

Resources / strategy: `github-sports-repos`, `ai-product-moats`, `model-landscape`.

Productization / GTM: `gtm-comparables`, `gtm-trust-artifacts`, `gtm-distribution-monetization`.

## The binding frame (held throughout)

Best **predictions** (OOS accuracy + calibration vs the devigged market close), never a fabricated $ edge.
Markets are efficient on price; the honest departures are **in-game state** and **own-data freshness**.
Leak-free walk-forward, >= 2 corpora, calibration (Brier/log-loss) as the bar, honest rejects are successes.
Local-only; `src`/`kernel`/`api` human-gated. Every doc was honesty-scanned (no edge/ROI/profit claims;
no retracted numbers).

## Caveat

These briefs were assembled by AI agents from web sources on 2026-06-16. The strategy and prioritization
are sound and grounded in the project's own measured state, but **verify volatile specifics** (exact CLI
flags, version numbers, pricing, API field names) against current official docs before acting on them.
Effort estimates are rough order-of-magnitude.
