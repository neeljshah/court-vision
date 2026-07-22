# AI Engineering at the Current Frontier -- the five skills 2026 teams hire for, each mapped to committed code

> The AI-engineering job market has converged on a recognizable skill set: eval harnesses,
> fail-closed LLM answer systems, MCP tooling, guardrail engineering, and cost-aware model
> routing. This page claims the repo demonstrates each one -- not as a resume keyword but as a
> committed artifact a reviewer can open and run. This is an engineering-parity claim, **not**
> a performance or edge claim: it maps machinery, not results. It is the *skills* companion to
> [agent-fleet-direction.md](agent-fleet-direction.md) (how the system was built); read that
> for the orchestration mechanics this page does not repeat. Truth-source for any figure:
> [JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).

---

## The claim

The current-era AI-engineering interview does not ask "can you call an LLM API." It asks
whether you can make an LLM system *trustworthy in production*: measure it against held-out
truth, stop it from hallucinating, expose it as tooling other agents can call, guard it in
code rather than in prompt text, and pay for it sensibly. Those five competencies are the
job. This repo carries a working, committed artifact for each -- and each was built for a
forecasting system, where getting any of them wrong fails silently.

---

## The five skill areas, with receipts

**1. Eval harnesses.** [EVAL_PLATFORM_MAPPING.md](../EVAL_PLATFORM_MAPPING.md) maps this
system's validation loop one-to-one onto the primitives Braintrust, Galileo, and Arize sell:
scorers, an offline golden-set regression gate, online production monitoring, experiment /
regression diffing, eval-set leakage detection, and drift observability. Each row cites real
code -- a Murphy Brier-decomposition scorer (`scripts/platformkit/calibration_diagram.py`), a
walk-forward backtester that asserts `max_train_date < min_test_date` on *every* fold
(`src/prediction/walk_forward_backtester.py`), a multi-corpus acceptance gate that ships a
change only when it beats baseline on >=2 independent out-of-sample corpora
(`scripts/validate_calibration_multicorpus.py`), and a truncation-invariance property test
that caught a real look-ahead leak in the system's own pipeline
(`tests/test_ingame_leak_free.py`). Not reinventing the products -- building the same control
loop from first principles, then pointing it at my own work.

**2. Fail-closed LLM answer systems.** The binding
[AI_CONSUMER_CONTRACT.md](../AI_CONSUMER_CONTRACT.md) makes the model an *interface*, never
the source of truth. Every question routes through a resolver oracle
(`scripts/platformkit/answers/resolver_registry.py`) that returns a typed envelope: a
`status` the model must honor verbatim (`ok` / `no_data` / `not_supported` / `refused` /
`ambiguous`), numbers quoted exactly, and a `source_artifact` + `as_of` on every figure.
`contract_client.py` *is* that contract as executable code -- it classifies, resolves, and
formats with no model call -- and per-sport consistency tests prove the resolver path and the
client path return identical numbers. This is the hard version of retrieval-augmented chat:
the model cannot round up, borrow a stale number, or invent one, and when the data is absent
the only legal answer is `no_data`.

**3. MCP tooling.** The same engine ships as an MCP server
(`scripts/platformkit/mcp_server/server.py`) exposing typed tools -- `ask`,
`scouting_report`, `win_probability`, `matchup_preview`, `comparables`, `injury_report`,
`system_health`, `analytics_receipts` -- each returning the identical fail-closed envelope.
Connecting is one command, with no server and no account
([USE_WITH_CLAUDE.md](../USE_WITH_CLAUDE.md)), and three real, captured exchanges are quoted
verbatim in [mcp-live-demo.md](mcp-live-demo.md), including one where the engine discloses,
unprompted, that the market's Brier is lower than the model's in that game-state bucket.

**4. Guardrail engineering.** [HONESTY_SYSTEM.md](../HONESTY_SYSTEM.md) documents a layered
guardrail stack enforced in code, not prompt politeness, cheapest-and-most-mechanical first.
A static repo lint (`scripts/platformkit/hygiene_lint.py`) exits non-zero if a banned number
or an edge/ROI phrase appears outside an explicit retraction context. A runtime response
middleware (`predict_service/honesty_mw.py`, `HonestyLinterMiddleware`) scans every JSON body
before it leaves the API and replaces a violating payload with a 500 honesty sentinel -- and
is fail-closed by design, so an exception while scanning counts as a violation, never a pass.
A machine-checkable `edge_claimed: false` field travels on every artifact that could be
mistaken for a result, and a `PreToolUse` hook (`scripts/hooks/pretooluse_guard.py`)
hard-blocks classes of dangerous commands regardless of what an agent believes it should do.

**5. Cost-aware model routing.** [BUILT_WITH_CLAUDE.md](../BUILT_WITH_CLAUDE.md) sets out the
routing economics: a lean Opus orchestrator owns judgment and dispatches a parallel fleet of
cheaper Sonnet executors, each with a cold context, a frozen interface, and an acceptance
test -- the expensive tier decides, the cheap tier does the volume. The load-bearing economic
decision is what runs at *inference*: nothing. The prediction path is entirely classical
(XGBoost / LightGBM / NNLS / Monte-Carlo / isotonic calibration) with no LLM call, which keeps
the product cheap, reproducible, auditable, and free of model-provider lock-in. Knowing *when
not* to put a model in the loop is the routing skill's sharper half.

---

## Receipts

| Skill area | What it demonstrates | Committed artifact |
|---|---|---|
| Eval harnesses | Scorer + offline gate + online monitor + regression diff + leakage + drift, mapped to Braintrust/Galileo/Arize primitives | [EVAL_PLATFORM_MAPPING.md](../EVAL_PLATFORM_MAPPING.md); `scripts/platformkit/calibration_diagram.py`; `src/prediction/walk_forward_backtester.py`; `scripts/validate_calibration_multicorpus.py`; `tests/test_ingame_leak_free.py` |
| Fail-closed answer system | Typed envelope, status honored verbatim, resolver-as-oracle, no model-memory numbers | [AI_CONSUMER_CONTRACT.md](../AI_CONSUMER_CONTRACT.md); `scripts/platformkit/answers/resolver_registry.py`; `scripts/platformkit/answers/contract_client.py` |
| MCP tooling | Typed tools over one-command MCP connect; identical envelope per tool; live captured demo | `scripts/platformkit/mcp_server/server.py`; [USE_WITH_CLAUDE.md](../USE_WITH_CLAUDE.md); [mcp-live-demo.md](mcp-live-demo.md) |
| Guardrail engineering | Static lint + runtime fail-closed middleware + `edge_claimed:false` field + PreToolUse git guards | [HONESTY_SYSTEM.md](../HONESTY_SYSTEM.md); `scripts/platformkit/hygiene_lint.py`; `predict_service/honesty_mw.py`; `scripts/hooks/pretooluse_guard.py` |
| Cost-aware routing | Opus-plans / Sonnet-executes tiering; zero-LLM classical runtime | [BUILT_WITH_CLAUDE.md](../BUILT_WITH_CLAUDE.md) |

---

## Reproduce on a fresh clone

```
# Fail-closed answer envelope -- returns a typed status + source_artifact, or no_data
python -m scripts.platformkit.answers.contract_client "does b2b_rest_penalty hold up" --sport nba

# Eval gate -- walk-forward with a per-fold leak assertion; exits non-zero on overfit
python scripts/run_walk_forward.py --gate

# Guardrail static lint -- exits non-zero on a banned number/phrase outside retraction context
python scripts/platformkit/hygiene_lint.py

# MCP server -- one-command install + connect (prints the exact Claude config)
python scripts/platformkit/publish_pack/install_pack.py
```

On a fresh clone the private corpora are absent, so data-dependent commands fail closed to
`no_data` / `VALIDATION_PENDING` rather than fabricating a number -- which is itself the
guardrail behavior this page is about.

---

## Why this matters to an employer

Every one of these five is a line on a 2026 AI-engineering job description, and every one is
usually asserted rather than shown. Here each is a file you can open and a command you can
run. An LLM system is only as good as the harness that measures it, the contract that stops
it lying, and the guardrails that hold when no human is watching. I built those first, and the
numbers second.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
