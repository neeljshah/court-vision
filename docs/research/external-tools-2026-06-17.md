# External tools that would make the system smarter (2026-06-17)

Curated against the ACTUAL stack. The north-star: calibration + the in-game
conditioning edge + freshness. In an efficient market, "smarter" = (1) harder honest
rejection and (2) fresher information -- not a bigger model. Tools ranked by leverage
against those two. All marked [free] are free / self-hostable.

## Already have -- do NOT re-add
Langfuse LLM-obs (`obs/langfuse_trace.py`) - RAG knowledge layer (`knowledge/`) -
own MCP server (`mcp_server/sports_predictor_server.py`) - eval-gate framework -
calibrator zoo/sweep/select - CLV ledger + forward capture + drift reports + SLO -
odds providers (ESPN / Kalshi / Polymarket). Context7 + serena MCPs.

## Top recommendations (ranked)

### 1. An injury / lineup freshness feed  [the actual edge]
Your own evidence packet says the gap you can't close is *freshness you can't see*
(injuries, confirmed starters, late scratches). This is the single highest-leverage
add and it's a DATA problem, not a model problem.
- **Free first:** NBA official Injury Report (published structured 2x/day), the ESPN
  injuries endpoint (you already use ESPN site.api -- extend the existing
  `odds_provider/espn.py` seam), and `balldontlie` API (now carries injury status).
- **Paid if you want confirmed late scratches:** Rotowire / Lineups.com.
- **Integration:** new adapter under `scripts/platformkit/freshness/` feeding an
  availability prior into the pregame predictor and the in-game state. Feeds the ONE
  durable edge. Env-keyed, degrade-clean (match the `odds_provider` pattern).

### 2. DVC -- data + model versioning  [free, kills a documented landmine]
You have a recorded landmine: prop pkl `n_features_in_` silently drifting from
`_meta.json` feature count -> zero-bet failures (`feedback_prop_model_artifact_drift`).
DVC versions `data/` corpora + model artifacts with git-like semantics, so a
(corpus, model) pair is reproducible and a hash-pin makes drift a hard error instead of
a silent one. Cheap insurance; stays local (no public push).

### 3. Optuna -- systematic calibrator / blend search  [free, drop-in]
You hand-roll `calibrator_sweep` / `calibrator_select`. Optuna gives pruned, resumable
search over recalibration + in-game-blend hyperparameters with far better sample
efficiency than a grid. Wrap it around the eval-gate's walk-forward Brier as the
objective -- the gate stays the judge, Optuna just searches smarter. Lands in
`scripts/platformkit/`.

### 4. gitleaks (or Semgrep) pre-commit  [free, defense-in-depth]
You move betting ledgers + PII and the public `origin` is one bad `git add` away. Your
PreToolUse guard + `check_no_public_push.py` block the obvious paths; a `gitleaks`
pre-commit hook adds secret/credential scanning on staged content as a second wall.
Semgrep adds light SAST if you want it. Both run locally, no network.

### 5. A live market websocket (Kalshi / Polymarket)  [you already trade there]
In-game edge is latency-bound: the faster you see realized state + market reprice, the
more your conditioning is worth. You already have REST `odds_provider/{kalshi,polymarket}`;
their websocket feeds cut the poll latency on the exact venues you use. Pure freshness
on the surface where freshness converts. Integration: streaming variant of the existing
providers feeding `live_repricer.py`.

### 6. MLflow or W&B  [free tier; only if hand-rolled tracking strains]
You already track calibration via `calibration_record` + `improve_ledger` + drift
reports. Adopt a real tracker ONLY when version-diffing Brier/ECE across model
generations outgrows the JSONL ledgers. MLflow self-hosts; W&B has a free tier. Lower
priority precisely because you've built most of this already.

## Honest "skip these"
- A bigger/newer base model to "beat the close" -- won't; the close is efficient.
- promptfoo / LangSmith for agent-output eval -- you have a prediction eval gate; agent
  prompt A/B is marginal at your maturity. Revisit only if skill regressions bite.
- Postgres MCP / pghero -- only worth it once you're actually DB-write-bound (80-game
  load); not now.

## One-line summary
Spend on **freshness (1, 5)** and **reproducibility/safety (2, 4)** -- those convert to
real calibration + the in-game edge and harden the moat. Treat 3 and 6 as quality-of-life.
