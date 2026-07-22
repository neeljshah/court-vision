# Solo Human Architect, Directing an Agent Fleet -- how this system was actually built

> This repo was built mostly by AI agents under one person's direction. About 91% of the
> commits are authored by the agent identity (`GSD Executor`), and a reviewer can recount that
> in one `git` command below. That is stated up front as the point, not buried as a
> confession: the engineering judgment, the ship/reject gates, and the validation methodology
> are the human's; the keystrokes are mostly the fleet's. The single truth-source for any
> figure below is [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).

---

## The claim

One person -- [Neel Shah](https://neelshahportfolio.netlify.app) -- directed a fleet of Claude
agents to build and validate a production sports-forecasting system across 3,200+ commits
(Mar-Jul 2026). He did not hand-type those commits, and he does not claim to have. The role
is architect and director: a planner model orchestrates cheaper executor models under hard,
automated ship gates that the agents cannot override. The load-bearing human contributions
are the ones a fleet cannot supply on its own -- the validation methodology, the ship/reject
decisions, and the honesty rails that make an agent's output trustworthy. The share of
agent-authored keystrokes (~91%, and rising) is the feature: it is what proves the workflow
scaled without the human becoming the bottleneck.

---

## How it actually works

**A cost-aware orchestration playbook.** The loop routes work by model tier -- an expensive
planner decides *what* to build and *whether it ships*; cheaper executors implement in
parallel, each on an isolated branch so concurrent agents never clobber a shared working
tree; state is written atomically so a crash resumes instead of corrupting. (The playbook
document `.claude/commands/workday-loop.md`, ~297 lines, is kept local-only and gitignored --
it references private ops paths -- so cite the committed machinery it drives:
`src/loop/orchestrator.py` and `scripts/loop/run_loop.py`, which carry the checkpoint/resume,
FDR-budget, and one-time-held-out logic; 166/168 of the loop tests pass.)

**A fail-closed ship gate built to refute, not confirm.** `src/loop/gate.py` decides whether
a candidate signal ships. It never tests a signal in isolation. Every candidate must clear
five criteria jointly: expanding walk-forward where *all* folds must improve; a null-shuffle
permutation control (real ablation delta must beat the shuffled-label null by z >= 3);
ablation-vs-full (the signal's marginal lift when added to the *full* production feature
matrix, not alone); calibration/coverage; and closing-line value. A Benjamini-Hochberg FDR
correction runs across every signal ever tested, and a final held-out set is touched exactly
once. If no leak-safe data bundle can be built, the gate returns DEFER -- never a false SHIP.

**An LLM-free, inexhaustible proposer.** `src/loop/discovery.py` enumerates feature
transforms from residuals, screens them with a cheap statistical filter, and hands survivors
to the same honest gate. No LLM is required to generate candidates, so discovery never runs
out of hypotheses -- but the gate still decides, so volume never becomes noise.

**Guardrails the agents cannot talk their way past.** Two constraints are enforced in
committed code, not politeness. `scripts/bot_guards/pre_edit_check.py` marks the production
trees (`src/`, `api/`, the engine internals) as protected: an agent that tries to edit them
is denied and told to route the change through human review. `governance/honesty_linter.py`
plus the no-edge rail ban dollar/ROI/edge language from any output, so an agent physically
cannot ship a profit claim. These are the mechanical reason an autonomous fleet stays honest
overnight.

---

## Receipts

| Claim | Committed artifact |
|---|---|
| ~91% of commits agent-authored; 3,200+ commits Mar-Jul 2026 | `git log` (recount command below); JOB_EVIDENCE_PACKET s4 |
| Fail-closed 5-criterion ship gate (walk-forward all-folds, permutation z>=3, ablation-vs-full, BH-FDR, held-out-once) | `src/loop/gate.py` |
| LLM-free signal proposer | `src/loop/discovery.py` |
| Orchestration / checkpoint-resume loop driver | `src/loop/orchestrator.py`, `scripts/loop/run_loop.py` |
| Protected-tree enforcement (agents cannot edit `src/`, `api/`) | `scripts/bot_guards/pre_edit_check.py` |
| No-edge / honesty language enforcement | `governance/honesty_linter.py`; [docs/HONESTY_SYSTEM.md](../HONESTY_SYSTEM.md) |
| 513 recorded REJECT/DEFER verdicts (negative-result count dwarfs the positive) | `scripts/platformkit/reject_ledger.py`; JOB_EVIDENCE_PACKET s2 |
| Orchestration playbook (described; local-only, gitignored) | `.claude/commands/workday-loop.md` -- not committed; machinery it drives is the row above |

---

## Verifiable from the outside

A reviewer does not have to take the authorship split on faith. On a fresh clone:

```
# Total commits and date span
git rev-list --count HEAD
git log --reverse --format='%as' | head -1   # first commit
git log --format='%as' | head -1             # latest commit

# Share of commits authored by the agent identity
git log --format='%an' | grep -c 'GSD Executor'

# Commits carrying a Claude co-author trailer
git log --format='%(trailers:key=Co-Authored-By)' | grep -ci Claude

# The signal graveyard -- every candidate the gate rejected, with reason and source
# (`show` prints the latest verdict per signal; the 513 figure is the full recorded
# history of REJECT/DEFER verdicts, re-adjudications included)
python -m scripts.platformkit.reject_ledger show
```

The reject ledger is the honesty exhibit at scale: the count of candidates that did *not*
survive the gate dwarfs the count that did, which is the expected shape of honest signal
discovery in an efficient market. The self-refutation trail lives alongside it in the
[retraction story](retraction-story.md).

---

## Why this matters to an employer

The current-era senior signal is not "can you write code" -- a fleet writes the code. It is
whether you can *direct* that fleet so the output is trustworthy: route work by cost, run
executors in parallel without corrupting the repo, and gate every result behind validation
strict enough to reject your own best ideas. This repo is the artifact of exactly that skill.
The human wrote the gate, the guardrails, and the methodology; the agents wrote the
implementation; and the split is recorded in `git`, not asserted. For an AI-engineering or
agent-orchestration role, the honest ~91% is the resume line, not the fine print.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
