# Morning Brief -- 2026-06-16

Good morning. Here is what ran overnight and what it means, in 3 minutes.

## What I did

1. **Finished the live-sports front end** (`apps/live_board_ui/`): 14 build waves, 238 tests, ~88KB gzip,
   light/dark, virtualized 300+ rows, search/sort/filter, dynamic columns, density, legend + tap-a-game
   detail dialogs, live score flash, honest freshness/stale/reconnecting signaling, PWA, a11y skip-link.
   All committed LOCALLY (never pushed); the `/api/board` contract was never changed.
2. **Ran a 28-agent research fleet** on "how to use AI at the highest level + sports-AI SOTA" -> 24 cited
   briefs + 5 synthesis docs in this folder. Start with **05-elevation-roadmap.md**.

## The one thing to take away

The pregame markets you compete against are efficient on price (you proved this 4/4 sports -- that is the
correct, honest result). So the win is **not** a dollar edge; it is **the best probability estimates**: a
calibrated predictor that matches the devigged close everywhere and **beats it where it has information the
close cannot have -- in-game state and own-data freshness.** That is achievable and measurable. The biggest
accelerant is not any single feature -- it is a tight **eval-driven build loop** (Claude + one disciplined
human) that judges every change honestly so the work compounds instead of drifts.

## The top moves (the "NOW" phase, weeks 0-4)

1. **Build the Brier-Skill-Score CI gate + golden dataset** (the keystone). A walk-forward backtest that
   fails the build if calibration vs the devigged close drops on either of two corpora. Nothing compounds
   without this. ~2-4 days. (Evaluator-Optimizer pattern + promptfoo, local.)
2. **Standardize devigging on Shin + build the calibration audit** (per-sport/market/quarter reliability
   diagrams, Murphy decomposition). The close is only the right baseline once devigged correctly. ~2-3 days.
3. **Wire the 2D in-game blend into the existing Monte Carlo prior** -- `final = w(t,margin)*P_live + (1-w)*P0`.
   This is the #1 leverage lever: new information by construction, an honest calibration gain the pregame
   close can't match. Foul-out already survived your own replay validation. ~1 week, built in `domains/`.
4. **Lock the invariants as Claude Code hooks, not prose** -- PreToolUse hooks that block `git push origin`,
   block full `pytest tests/`, prepend the cwd, warn on `src/`/`kernel/` edits + >300 LOC. CLAUDE.md is a
   request; a hook is a guarantee. ~half a day. (I did NOT add these overnight -- they touch shared
   `.claude/` config another session may rely on; they're proposed for your go-ahead.)

## Where the real leverage is (ranked, from the roadmap)

In-game conditioning (1) > data freshness/own-data (2) > calibration rigor (3) > eval-driven loop (4,
force-multiplier) > multi-sport breadth (5) > CV moat (6) > LLM intel layer (7) > build velocity via Claude
(8, force-multiplier). The two force-multipliers (4, 8) are cheap -- do them early.

## "Make it something" -- the honest product

Not a picks/profit service (that destroys the trust moat). A **4-sport calibrated forecasting system with
transparent OOS validation and in-game conditioning** -- decision-support for people who value rigor. Lead
with the calibration record; make "honest reject / market-efficient here" a first-class UI citizen; the hero
interaction is the pregame->live update; one-command reproducible proof; the data moat (own CV + intel vault
+ append-only track-record ledger) is the compounding asset. Full detail in 05 Section 4.

## How to navigate

- **HOW-TO-USE-AI-AT-THE-HIGHEST-LEVEL.md** -- the direct answer to your question (principles + your AI operating rhythm).
- **IMPLEMENTATION-KICKOFF.md** -- the single ordered execution plan + a ready first-session prompt. Open this to START BUILDING.
- **05-elevation-roadmap.md** -- read first for the why/what; it's the plan.
- **06-productization-gtm.md** -- "make it something": the honest decision-support GTM (comparables, trust artifacts, distribution).
- **blueprints/** -- 6 build-ready designs (eval-gate, in-game blend, freshness, RAG, build-loop, MCP+ledger) with real pseudocode.
- **INSTALLED-TOOLKIT.md** -- the skills/agents/tools you already have, mapped to each roadmap item.
- **01 / 02** -- how to wield Claude + AI engineering (the "how to build it fast and honestly" companions).
- **03** -- the sports-AI technical SOTA (the "what to build" reference).
- **04** -- the curated links bookmark.
- **briefs/** -- the 27 raw cited research briefs behind the synthesis.

## Package status (all done overnight)

The full package is complete and was adversarially QA'd by 4 reviewers (honesty, Claude-fact accuracy with
live doc spot-checks, sports/design soundness vs your existing record, cross-doc coherence). Verdict: the
honest discipline held across all 39 docs; the review caught and I FIXED one real blocking statistical bug
(the in-game blend's Diebold-Mariano test was not clustered by game_id -- it now reuses the eval-gate's
cluster-robust version), tightened a freshness-pipeline leak caveat, reconciled counts/versions, and softened
a few unverifiable Claude-specific specifics to "verify against official docs." It is ready to act on.

And I went past planning into VERIFIED CODE for the whole NOW phase + key NEXT items, in
`reference-impl/eval_gate/` (34/34 tests pass offline with your conda env; `python run_all.py` proves it):
- N1 (keystone, COMPLETE): proper scoring (Brier/BSS/log-loss/ECE) + cluster-robust Diebold-Mariano +
  golden-set leak guard + the leak-free WALK-FORWARD engine (expanding window + purge + embargo + vintage);
- N2: a CORRECT Shin devig (the QA found the old closed-form did not normalize -- this one does);
- N3 (#1 lever): the in-game blend -- blend fn + a weight surface fit on season A, shown to beat
  pregame-only OUT-OF-SAMPLE on season B (the honest gain), clustered DM by game_id;
- X1: the freshness schema + vintage leak guard + fallback-proxy quarantine (the QA fix made concrete);
- X3: the append-only track-record ledger + calibration-drift monitor (the trust moat);
- plus `demo.py`: the end-to-end loop (devig -> blend -> score vs close -> ledger) that honestly reports
  MATCHES_CLOSE on synthetic data, not a fabricated win.
It is in the private research dir (no collision with the active branch). Copy `eval_gate/` into
`scripts/platformkit/eval_gate/` when you give the go-ahead, then wire the corpus loaders + the golden
fixture around it per `blueprints/eval-gate.md`. I did NOT add code to the shared/tracked tree or touch
the human-gated core overnight -- that's your call.

## Honest caveats

Briefs are AI-assembled from web sources dated 2026-06-16; the strategy is grounded in your own measured
state, but verify volatile specifics (CLI flags, versions, pricing, API field names) against official docs
before relying on them. Effort estimates are rough. Nothing here was pushed to any remote; all local.
