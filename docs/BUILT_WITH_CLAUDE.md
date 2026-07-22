# Built with Claude -- the agentic build pipeline

> **The system you see was designed by a human and built by a fleet of Claude agents under hard
> ship-gates.** This document explains that pipeline in depth: who plans, who writes code, how work
> stays honest, and -- importantly -- why **the running product contains no Claude at all**.
>
> Navigation: [Index](INDEX.md) - [Home](../README.md)

---

## The one-sentence version

A single **Opus orchestrator** acts as a lean dispatcher; it plans the work, spawns as many
**Sonnet and Opus sub-agents** as the task needs, hands each a frozen interface + an acceptance
test, collects a short structured result, runs it through an honest **evaluation gate**, and only
then records it as done -- looping like this for days, unattended, without ever pushing to a public
remote, flipping a feature flag, or claiming a dollar edge.

Claude is the **factory**. The **runtime** -- the thing that actually makes predictions -- is
classical (XGBoost / LightGBM / NNLS / Monte-Carlo / isotonic calibration) plus a deterministic
self-improvement loop. There is **no LLM call on the prediction path**, by design: it keeps the
product cheap, reproducible, auditable, and free of model-provider lock-in.

---

## Why an agentic pipeline at all

A solo human cannot hold ~430 source modules, ~680 platform-tooling files, five sport adapters, a
Monte-Carlo simulator, an eval framework, an odds layer, and a front-end in one head at once. The
agentic pipeline is how one person directs a code-base of that size: the human supplies
**judgment** (what to build, which results to trust, where the honesty line is); the agents supply
**volume** (reading, searching, writing, testing in parallel). The division is deliberate and it
is the differentiator -- not "an AI wrote my code", but "a human ran a disciplined, gated,
multi-agent build and can defend every line and every number".

---

## The roles

### Opus orchestrator -- the planner / dispatcher
One long-running Opus session is the control loop. Its job is to stay **lean**: it reads the live
ledger, decides the next slice of work, dispatches sub-agents, verifies their results, updates the
ledger, and repeats. It deliberately pushes reading/searching/building *into* sub-agents so its own
context never fills up. It owns the judgment calls -- the gate verdicts, the schema/contract
decisions, the final "this is a real result vs an artifact" call.

### Sonnet executors -- the builders
The bulk of mechanical volume runs on a parallel fleet of Sonnet agents: connectors, capture
daemons, ingest builders, UI components, per-file tests, refactors, cleanup. Each gets **one
discrete task** with a cold context, a **frozen interface** (not the upstream agent's reasoning),
and an **acceptance test**. They return a <=10-line structured summary -- what changed, the
signatures, the test result, file:line refs -- never a wall of pasted code.

### Specialist agents & skills
- **Explore / search agents** map the code-base on demand so the orchestrator never loads it whole.
- **Honesty-gate agent** adjudicates any market-beating claim -- default *refuted* until a
  leak-free, out-of-sample, real-price proof survives.
- **Code-review agent** reviews a diff before it counts as done.
- **Skills** (under `.claude/skills/`) package repeatable analyses as one-command tools:
  `eval-gate`, `calibration-report`, `signal-audit`, `cross-sport-benchmark`, `predict-matchup`,
  `state-roadmap`, `memory-curate`, plus the CV-pipeline skills (`benchmark`, `run-pipeline`,
  `train-checkpoint`, `debug-cv`).
- **Two standing roles** run continuously: **MEMORY** (curate durable facts) and **ORGANIZATION**
  (keep the repo + docs pristine), with a pass after every phase so quality compounds.

Deeper write-ups on these agent patterns (anthropic-agent-patterns, agentic-orchestration,
claude-skills) live in the internal research corpus, not the public clone.

---

## The operating model: work hard *and* lean

The hard part of running one session for days is **context hygiene** -- if the orchestrator's
window fills with file contents and tool output, it degrades. The pipeline enforces:

- **Externalize all state to files, not chat.** A live phase ledger (`NOW.md`), a single
  source-of-truth status doc (`STATUS.md`), and durable per-fact memory files. A fresh orchestrator
  can resume cold from those alone.
- **Saturate the fleet, keep the controller empty.** Many sub-agents in flight; the orchestrator
  transcript stays minimal. Independent calls are batched into one turn so they run concurrently.
- **Never re-read an established file; reference by `path:line`.** Targeted greps, never broad dumps.
- **Pre-assign disjoint write-ranges** to parallel agents so two builders never collide on the same
  file (a lesson learned the hard way -- concurrent appenders clobbered each other until ranges were
  partitioned up front).

---

## The honesty machinery (this is the real engineering)

Anyone can have an LLM generate code that *looks* like it beats a market. The value here is the
machinery built to stop that from happening:

- **The eval gate** (`src/loop/gate.py`, the `eval-gate` skill) -- a fail-closed golden-set
  validator: expanding-window walk-forward + permutation null-shuffle + ablation-vs-full +
  Benjamini-Hochberg FDR + a noise-p0 control. It votes SHIP / REJECT / HOLD / INSUFFICIENT_DATA.
- **The 5-gate ratchet** (`improve/`) -- a candidate ships only if it wins on *all* proper scores,
  replicates across **>=2 independent corpora** (single-fold lifts are treated as artifacts), and
  survives seed-stability. Versioned artifacts with atomic swap + auto-rollback.
- **The reject-ledger** -- every REJECT is recorded with its reason. The corpus of honest nulls is
  itself a deliverable: it proves the gate has teeth.
- **CLV over ROI** -- the scoreboard for "did we beat the price" is forward closing-line value on
  real captured prices, not small-sample P&L (which is mostly variance).

The same harnesses were pointed *inward* and retired the project's own early over-claims (a
market-follow ROI artifact, a Q4 look-ahead leak, an L5-proxy "edge" that was really a ceiling).
Building the instrument that refutes your own hype is the point. Full account:
[JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md) - [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md).

Design blueprints for the eval gate, calibration-scoring, and evals-quality live in the
internal research corpus.

---

## Memory, hooks, and the rails

- **Persistent auto-memory** -- durable facts (locked decisions + why, what shipped + its honest
  verdict, landmines, cross-session state) live in an indexed memory store, curated under a size
  cap. It is how a fresh session knows what already failed and why, instead of re-deriving it.
  Design notes on the memory architecture live in the internal research corpus.
- **Hooks enforce the invariants mechanically**, not on trust. A PreToolUse hook hard-blocks
  `git push origin`, a full `pytest` run (which freezes the box), and `--force`. Other guards block
  edits to human-gated trees and block flipping a feature flag on while unattended.
- **The binding rails** (in `.claude/rules/`): local commits only / never push to public origin;
  no `data/` or `vault/` ever committed; human-gated paths (`src/`, `kernel/`, `api/`) are not
  edited autonomously; per-file tests only; **no dollar-edge claim anywhere**; ASCII-only output.

These rails are why an unattended, days-long build is safe: the destructive or irreversible moves
are blocked at the harness level, and the one genuinely irreversible action -- a real-money flip --
is reserved for an explicit human decision.

---

## The never-stop builder + the always-on self-improve loop

The build itself runs as a **never-stop** loop: the orchestrator self-continues on every wake,
ending only on an explicit stop. Each cycle is a small, reversible, per-file-tested, smoke-verified
step that leaves the stack working.

The *product* has its own loop -- a Claude-free, deterministic **self-improvement daemon**: per
settled game it updates ratings, re-fits calibration on a rolling window, widens the validated
search, requires cross-corpus replication, and atomically swaps in a new artifact (with
auto-rollback on regression). It emits proposals but never touches memory, the registry, or feature
flags directly. This is what lets the system get sharper over time without a human or an LLM in the
loop. Design blueprints for the build loop, freshness pipeline, and in-game blend live in the
internal research corpus.

---

## Where to go next
- The deeper AI-leverage research corpus (patterns, MCP, skills, eval/proving-spine wiring) is internal / local-only
- The honest results that machinery produced: [PROOFS](PROOFS.md) - [ML_MODELS](ML_MODELS.md)
- Back to the map: [INDEX](INDEX.md)

---

*Claude is the factory, not a runtime dependency. Every prediction number this pipeline produced is
calibration / sharpness, never a dollar edge; truth-source [JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md).*
