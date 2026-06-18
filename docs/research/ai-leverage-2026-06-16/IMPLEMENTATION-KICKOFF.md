# Implementation Kickoff -- Ordered Execution Plan

_The single doc a future build session opens to start work. Synthesizes the six blueprints
(eval-gate, ingame-blend, freshness-pipeline, knowledge-rag, claude-build-loop, mcp-and-ledger),
the elevation roadmap, and the installed toolkit into one ordered, validated build sequence.
ASCII only. North star: BEST PREDICTIONS (OOS calibration vs the devigged close), never a $ edge.
An honest BSS <= 0 / "no edge" is a recorded SUCCESS._

---

## The sequence in one screen

Do these in this order. Each line says why it comes when it does.

1. **N1 -- Brier-Skill-Score CI gate + golden dataset** (`blueprints/eval-gate.md`).
   FIRST because everything else is judged by it. Until the gate exists, no later change can be
   honestly called "shipped". It is the contract; it compounds every other item.
   N2 (Shin-devigging standardization + calibration audit) is folded into this deliverable:
   the gate scores every corpus against the Shin-devigged Pinnacle close (never multiplicative,
   never a soft book) and ships reliability diagrams (ECE diagnostic paired with sharpness and
   resolution) as part of its done-criteria. N2 is therefore a prerequisite of N1's scoring
   metric, not a separate later step.
2. **N4 -- Hooks + skills + routing + CLAUDE.md refactor** (`blueprints/claude-build-loop.md`).
   SECOND because it makes the no-push / no-leak / per-file-pytest discipline MECHANICAL (a hook,
   not prose) before autonomous build velocity ramps up. The hooks themselves need no shared-config
   edit to write (only to install -> human-confirm). Cheap force-multiplier, do it early.
3. **N3 -- In-game blend surface** (`blueprints/ingame-blend.md`).
   THIRD because it is the #1 prediction-quality lever -- the one place the model can honestly beat
   the pregame close (realized state is information the close never had). Judged by N1's gate.
4. **X1 -- Structured-extraction freshness pipeline** (`blueprints/freshness-pipeline.md`).
   FOURTH: the #2 lever (capturable freshness, the pregame model's one structural gap). Feeds the
   existing vacated-load model; LLM extracts only, never emits a number.
5. **X3 -- Track-record ledger + drift monitor (+ sports_predictor MCP)** (`blueprints/mcp-and-ledger.md`).
   FIFTH: the trust moat. Build the number-RECORDER (ledger PART B) before the number-SERVER (MCP
   PART A). Turns "best predictions" into a reproducible, append-only, timestamped artifact.
6. **knowledge-RAG vault layer** (`blueprints/knowledge-rag.md`).
   SIXTH: L3 prep. Feeds X1 pre-game context assembly and the future board narrative. Pure
   retrieval/synthesis; it NEVER touches a probability. Lands any time after N1; no hard blocker.
7. **X2 -- MLB in-game** (in `blueprints/ingame-blend.md`, MLB adapter section).
   The second corpus for the in-game architecture; runs the same blend pattern on the free MLB
   statsapi feed. Comes after N3 proves the NBA pattern.

Force-multipliers (N1 gate, N4 loop) go first; the two highest-quality levers (N3 in-game, X1
freshness) go next; the trust moat (X3) and the synthesis layer (RAG) follow; MLB widens to the
second corpus last.

---

## 30 / 60 / 90 day plan

Each item: blueprint -> done-criteria (from the blueprint) -> toolkit skills/agents -> rough days ->
the leak-free validation that must pass before it "ships".

### Days 0-30 -- make the measurement honest and lock the loop

**N1 + N2. BSS CI gate + golden dataset + Shin-devigging standardization + calibration audit** -- `blueprints/eval-gate.md`
N2 (standardize devigging on Shin + calibration audit) is delivered as part of N1, not
separately: the gate baseline IS the Shin-devigged Pinnacle close, and the reliability diagrams
(ECE diagnostic, sharpness, resolution) ARE the calibration audit. There is no intermediate state
where N1 is "done" without N2 -- the Shin-devigged close is the denominator of BSS itself.

**N1. BSS CI gate + golden dataset** -- `blueprints/eval-gate.md`
- Done-criteria: `python -m scripts.platformkit.eval_gate.run_gate --golden` runs < 60s offline on a
  git-tracked 90-120 state golden fixture; reports per-corpus BSS = 1 - Brier_model/Brier_close vs the
  Shin-devigged close, Brier +/- 95% CI clustered by game_id, log-loss, ECE (diagnostic), resolution,
  sharpness, and a Diebold-Mariano stat+p; exits 1 on regression-vs-frozen-baseline on EITHER corpus
  OR any leak-guard failure; labels each corpus BEATS/MATCHES/BEHIND (none of those block); promptfoo
  wrapper with identical exit semantics; per-file tests green.
- Toolkit: `/gsd:plan-phase` to plan -> **Workflow** for parallel build -> `/code-review` on the diff
  -> per-file pytest. `/claude-api` for any volatile API detail. promptfoo for the CI wrapper.
- Days: 2-4. Day 1 = pure-function metrics + DM + schema (no data); Day 1-2 = golden builder + fixture
  (human-run once from real `data/` + `pbp_replay.py` + Shin closes); Day 2-3 = walk-forward + gate;
  Day 3-4 = promptfoo + docs.
- Ships when: green on BOTH corpora (NBA 2023-24 + 2024-25), leak-guards fire on planted leaks, the
  cluster-robust DM SE is provably wider than naive, and a human re-blesses the frozen baseline JSON.

**N4. Hooks + skills + routing + CLAUDE.md refactor** -- `blueprints/claude-build-loop.md`
- Done-criteria: hooks block `git push origin`/`--force`/`pytest tests/`, rewrite bare bash to add the
  cwd prefix, warn on human-gated-path edits and >300-LOC files; five SKILL.md files (predict-matchup,
  benchmark, eval-gate, signal-audit, brain-rebuild); `CLAUDE_CODE_SUBAGENT_MODEL=haiku` + fallbackModel
  list; nightly headless `claude -p` gate run appends a ledger row and exits 0/1 on drift; CLAUDE.md
  < 200 lines with three path-scoped `.claude/rules/` files.
- Toolkit: build-loop blueprint + `/update-config`; `/init` for the CLAUDE.md refactor. Test each hook
  by piping a fake hook JSON into the script (no settings edit needed to validate).
- Days: 1.5-2. Steps 1-3 (hooks, skills, rules, CLAUDE.md) are NEW files -> SAFE NOW. Step 4
  (`.claude/settings.json` creation) is the only shared-config touch -> HUMAN-CONFIRM, do LAST.
- Ships when: each hook fires on one manual trigger (transcript shows BLOCKED / rewrite / warning); the
  eval-gate skill runs the REAL leak-free gate; nightly dry-run produces a parseable JSON + ledger row.

### Days 30-60 -- widen the honest signal surface

**N3. In-game blend surface (NBA)** -- `blueprints/ingame-blend.md`
- Done-criteria: `final = w(t,margin)*P_live + (1-w)*P0` beats the `pbp_replay.py` Phi-margin baseline
  in EVERY quarter bucket on a held-out NBA season (target Q1-Q3 0.34-0.40 -> < 0.25; Q4 -> < 0.10);
  beats pregame-only with DM p < 0.05 clustered by game_id; per-quarter reliability closer to diagonal
  with lower Murphy reliability term and >= resolution; in-sample-vs-OOS Brier gap on `w` < 0.01 (the
  Statsurge overfit tell); garbage-time clamp + EMA smoothing in place.
- Toolkit: **Workflow** (build in `domains/basketball_nba/`), `/verify`, the N1 gate as the judge.
- Days: ~1 week. Day 0 = new wrapper deriving P0 from the existing sim margin dist (no src edit); Day
  1-2 = P_live + features; Day 2-3 = weight surface + blend; Day 3-4 = eval harness; Day 5 = ablate
  features (keep only what lowers OOS Brier+reliability; record honest rejects).
- Ships when: A->B AND B->A cross-season splits both pass; overfit gap < 0.01; ablation table recorded;
  N1 gate green (no regression). An ablated feature that does not help is dropped, recorded as success.

**X1. Structured freshness pipeline** -- `blueprints/freshness-pipeline.md`
- Done-criteria: `run_extraction.py --window pregame` produces Pydantic-validated SQLite rows from >= 2
  source types, each stamped `extracted_at`; `as_of_out_ids(team, asof_ts)` NEVER returns a row with
  `extracted_at >= asof_ts` (proven by a planted-late-row unit test); OUT ids drive the EXISTING
  vacated-load reroute (no math change); leak-free walk-forward on NBA 2023-24 AND 2024-25 shows Brier
  no worse overall and better on the confirmed-pre-tip-OUT-delta subset (DM p < 0.05, N >= 200,
  clustered SE) OR an honest null; extraction precision/recall measured on a ~150-snippet golden set.
- Toolkit: `/deep-research` for source survey; LLM structured-output extraction (instructor/Pydantic,
  max_retries=3) with downstream re-validation; the N1 gate to judge the calibration arm.
- Days: 1.5-2 weeks. Build `schema.py`+`db.py` first, then `as_of_reader.py`+its vintage tests BEFORE
  the fetchers, then sources (NBA official report first for true historical timestamps), extract+resolve,
  orchestrator, golden set, then the longest block: the historical `extracted_at` reconstruction + the
  two-arm walk-forward.
- Ships when: the late-row-excluded test passes; both corpora pass independently (an honest null on the
  affected subset is an accepted, recorded outcome); LLM emits no number that enters predictions.

### Days 60-90 -- the trust moat, synthesis, and the second corpus

**X3. Track-record ledger + drift monitor + sports_predictor MCP** -- `blueprints/mcp-and-ledger.md`
- Done-criteria (PART B first): every CLI/MCP prediction appends ONE immutable row per prediction to
  `vault/_TrackRecord/predictions.parquet` (atomic, idempotent on pred_id); `grade_outcomes.py` fills
  outcome/devig_close_prob without overwriting; `drift_check.py` exits 2 on a >1-sigma Brier rise vs a
  30-day rolling baseline; `replay_proof.py` reproduces Brier/ECE/DM on a committed fixture ledger in
  < 30s. PART A: stdio MCP server exposing `predict_pregame`/`predict_ingame`/`calibration_report`/
  `list_sports` that shells into `predict_matchup.build_result` (the LLM never authors a number);
  no-corpus path returns `available:false` and never raises.
- Toolkit: `/schedule` + `ScheduleWakeup` + `PushNotification` for the nightly drift run; `pip install
  mcp`; `/code-review` on the diff.
- Days: ~4.5. Order: schema+ledger+metrics (1.5d) -> grade+fixture+replay_proof (1d) -> MCP server (1d)
  -> drift_check (0.5d) -> `.mcp.json` wiring LAST, HUMAN-CONFIRM (0.5d).
- Ships when: `replay_proof` reproduces the fixture numbers; vintage guard (`pred_ts < game_date`)
  drops+flags violators; calibration computed on >= 2 corpora per sport; a "beats the close" claim only
  logged with DM p < 0.05 AND lower Brier AND N >= 200, else recorded as an honest REJECT.

**knowledge-RAG vault layer** -- `blueprints/knowledge-rag.md`
- Done-criteria: cold index of all 4 sports' ~4113 notes < 10 min, incremental refresh < 30s; recall@5
  >= 0.90 overall and >= 0.85 per sport on a >= 120-row git-tracked golden set authored without seeing
  the index; pregame context bundle (<= 2K tokens, every claim citing a [[note]]) in < 30s; live warm-
  cache read p95 < 200ms; MCP server answers `vault_search` + `assemble_pregame_context`; honest-reject
  ("no relevant intel found") is first-class; the BOUNDARY test proves no numeric/predict tool is exposed.
- Toolkit: LanceDB (embedded), Haiku contextual prefixes via the Batches API, BAAI/bge-reranker-v2-m3;
  `/deep-research` only if a retrieval technique needs confirming.
- Days: ~6-8. ingest -> index+golden -> retrieve+ablation+tau -> contextual prefixes -> agentic assemble
  + boundary/faithfulness -> warm cache + MCP snippet.
- Ships when: recall@5 thresholds met with a bootstrap CI; the ablation ladder (dense -> +BM25 ->
  +contextual -> +rerank) confirms each stage helps; the boundary test passes (no probability leaks).
  NOTE: validated as a RETRIEVAL system -- the Brier/DM machinery does NOT apply to its output.

**X2. MLB in-game (second corpus)** -- `blueprints/ingame-blend.md` (MLB adapter)
- Done-criteria: same blend on MLB state from the free `statsapi.mlb.com .../feed/live` pitch-by-pitch
  feed; blended per-inning Brier beats MLB's own published win probability, fit on one set of seasons,
  evaluated on Retrosheet-derived seasons (the independent second MLB corpus).
- Toolkit: **Parallelization (Sectioning)** -- run NBA + MLB pipelines as independent parallel subagents;
  the N1 gate (with the `mlb_2024` corpus slot activated) as judge.
- Days: 1-2 weeks. Imports the NBA core pure functions (`blend_prob`, `smooth_series`).
- Ships when: per-inning reliability passes on Retrosheet as the independent corpus; satisfies the
  two-corpus rule for the in-game ARCHITECTURE end-to-end.

---

## Dependencies + collision rules

**What unblocks what**
- N1 (gate) unblocks the honest "shipped" verdict for N3, X1, X3, X2. Build it first.
- N4 hooks/skills are independent of N1 content but should land early to enforce discipline during the
  build; the nightly-gate cron in N4 DEPENDS on the N1 gate + the X3 ledger schema.
- N3 day-0 P0 wrapper unblocks the whole in-game chain; P_live + surface -> blend -> harness -> ablation.
- X1 `schema.py`+`db.py` unblock everything in freshness; `as_of_reader.py` + its vintage tests come
  BEFORE the fetchers (the late-row test is the load-bearing correctness check).
- X3 PART B (ledger) is the substrate for PART A (MCP server, which logs every call) and for N4's
  nightly ledger row. Build the recorder before the server.
- RAG `assemble_pregame_context` is consumed by X1 pre-game context assembly and the future L3 board
  narrative; nothing blocks RAG step 1.
- X2 depends on the NBA N3 pattern being proven first.

**Branch ownership (coordinate)**
- The active branch **`fullsend-ingame-pregame-execution`** OWNS the in-game/pregame Python under
  `src/prediction/live_engine.py` and `src/sim/`. Treat the pregame sim as a BLACK-BOX prior; do NOT
  edit `src/`, `kernel/`, `api/`, `scripts/team_system`, or `intel`. N3 in particular adds only NEW
  files under `domains/<sport>/` and `scripts/platformkit/`. If you must touch in-game/pregame src,
  COORDINATE with that branch (or use `EnterWorktree` for isolation) -- do not both edit the same file.

**Build-path rules (allowed targets)**
- ALL new code lands in `domains/<sport>/` or `scripts/platformkit/` (plus git-tracked fixtures under
  `tests/fixtures/`). New MCP servers under `scripts/platformkit/mcp_server/` or `scripts/mcp_server/`.
  Hooks under `scripts/hooks/`, skills under `.claude/skills/`, rules under `.claude/rules/`.
- <= 300 LOC/file (spec DATA modules exempt, ~600-750 L). Per-file tests ONLY (full `pytest tests/`
  freezes the box). Prefix every bash command with `cd /c/Users/neelj/nba-ai-system &&`. ASCII only.

**Shared-config = human-confirm (do NOT auto-edit)**
- `.claude/settings.json` (N4 hooks/routing), `.mcp.json` (X3 MCP registration), the `mcpServers` block
  for the RAG/predictor servers, and any cron/scheduled-task install are ALL human-confirm-before-applying
  because the live `fullsend-ingame-pregame-execution` session reads `.claude/`. Ship these as
  copy-paste snippets + a one-line "human applies this" flag; never write them from an autonomous wave.
  Never `git add` from `vault/` or `data/` (gitignored); never write `data/registry/`; never push origin.

---

## Definition of done for each phase

A phase is DONE (= "shipped + validated") only when ALL hold:

1. **Green on >= 2 independent corpora** (two seasons or two sports). A lift on corpus A with a drop on
   corpus B is the overfit signature and FAILS -- it does not ship.
2. **Leak-free OOS**: expanding-window walk-forward, purge same-team within 48h, embargo 3-day gap,
   feature selection + tuning INSIDE the window, vintage alignment (`availability_date < prediction_time`)
   asserted (defense in depth: schema AND walk-forward).
3. **Statistically honest**: Brier/log-loss vs the SHIN-devigged close (never multiplicative on lopsided
   markets, never a soft book); 95% CI clustered by game_id/season (naive SE ~3x too narrow); "beats the
   close" only with a Diebold-Mariano test p < 0.05 AND N >= 200. ECE is diagnostic-only, always paired
   with sharpness/resolution so a collapse-to-0.5 cannot pass.
4. **Recorded honestly**: the result is written to a committed proof JSON / the ledger / a vault note.
   **BSS <= 0 (we do not beat the close here) is a SUCCESS, not a failure** -- it is the correct, honest
   verdict for an efficient pregame market, recorded and never tuned away.
5. **Invariants intact**: no `src/kernel/api/team_system/intel` edit, no flag flipped ON, no `data/registry/`
   write, no origin push, no shared-config auto-edit, per-file tests only, no hard-coded secrets, the LLM
   never emitted a number that entered the prediction chain.
6. **The N1 gate is green** (no regression vs the frozen baseline on either corpus) for any change that
   touches a scored prediction. The human re-blesses the baseline JSON only on an intentional re-freeze.

For the RAG layer specifically (no probability output): DONE = the retrieval recall@k / faithfulness /
boundary thresholds pass; the Brier/DM machinery explicitly does not apply, and saying so is part of the
discipline.

---

## FIRST-SESSION PROMPT (ready to paste)

Paste this into a fresh Claude Code session to begin N1:

```
We are starting the AI-leverage build. Read these first, in order:
  docs/research/ai-leverage-2026-06-16/IMPLEMENTATION-KICKOFF.md
  docs/research/ai-leverage-2026-06-16/blueprints/eval-gate.md
  docs/research/ai-leverage-2026-06-16/05-elevation-roadmap.md (sections 1 and 5)

GOAL THIS SESSION: build N1 -- the Brier-Skill-Score CI gate + golden dataset -- exactly as
blueprints/eval-gate.md specifies. It is the keystone: every future change is judged by it.

BINDING INVARIANTS (restate and obey, do not drift):
  - Calibration, NOT edge. Target = Brier Skill Score vs the SHIN-devigged close. Never optimize raw
    accuracy or bare ECE. An honest BSS <= 0 / "no edge / market efficient" is a recorded SUCCESS.
  - Leak-free OOS only: expanding-window walk-forward, purge same-team <48h, embargo 3-day gap, feature
    selection INSIDE the window, vintage alignment (availability_date < prediction_time) asserted.
  - Two-corpus rule: nothing ships without passing on >= 2 independent corpora (NBA 2023-24 + 2024-25).
  - Statistical honesty: 95% CI clustered by game_id; Diebold-Mariano p<0.05, N>=200 to claim a beat.
  - Local-only / human-gated: NEVER push to public origin; NEVER write data/registry/; NEVER flip a flag
    ON; do NOT edit src/, kernel/, api/, scripts/team_system, or intel. The active branch
    fullsend-ingame-pregame-execution owns in-game/pregame src -- do not touch it; coordinate if needed.
  - <= 300 LOC/file; per-file tests ONLY (NEVER `pytest tests/` -- it freezes the box); ASCII only;
    prefix EVERY bash command with `cd /c/Users/neelj/nba-ai-system &&`.
  - The LLM never emits a number that enters the prediction chain.

ALLOWED BUILD PATHS (everything new lands here):
  scripts/platformkit/eval_gate/  and  tests/fixtures/golden/
  Reuse read-only: kernel/validation/proof_metrics.py (brier, devig2/Shin, ece, reliability_slope),
  scripts/platformkit/proof_nba/* and beat_the_close_scoreboard.py, scripts/team_system/pbp_replay.py.
  Do NOT edit .claude/settings.json or any shared config -- the settings/CI hook is N4, human-confirm.

PROCESS (follow this loop):
  1. Run /gsd:plan-phase to produce a PLAN.md for the eval-gate build.
  2. Build via a Workflow (parallel fan-out per the blueprint's day-by-day file list:
     scoring.py + dm_test.py + schema.py first as pure functions; then golden builder; then
     walkforward.py + baseline.py + run_gate.py; then promptfoo.yaml + docs).
  3. Run /code-review on the diff before any local commit; fix findings.
  4. Validate with per-file pytest only:
     python -m pytest scripts/platformkit/eval_gate/test_gate.py -q  (and test_metrics, test_walkforward).
  5. Confirm `python -m scripts.platformkit.eval_gate.run_gate --golden` runs <60s offline and prints
     the per-corpus scoreboard with BSS, clustered-CI Brier, DM p, and BEATS/MATCHES/BEHIND verdicts.

Use /claude-api or claude-code-guide for any volatile Claude/API detail rather than guessing.
Report the verdict honestly: if we MATCH or are BEHIND the close, that is the correct, recorded result.
```

---

## Honesty checkpoints

Recurring questions to ask at every phase gate -- pulled from the roadmap risk table (section 5). If any
answer is "no" / "unsure", the change does NOT ship.

- **Single-fold artifact?** Did it pass on >= 2 independent corpora? A lift on A with a drop on B is the
  overfit signature -> reject. (Two-corpus rule.)
- **Hidden leak?** Is `availability_date < prediction_time` asserted for every feature, with purge +
  embargo + feature-selection-inside-window? Did a planted future-feature trip the leak guard?
- **"Beats the close" really noise?** Is there a DM test (p < 0.05, N >= 200) on per-game loss diffs with
  SEs CLUSTERED by game_id/season -- not a bare point delta? (Naive SE runs ~3x too narrow.)
- **ECE gamed?** Is ECE diagnostic-only, paired with sharpness/resolution so a collapse-to-0.5 cannot
  look good? Is the primary bar Brier/log-loss vs the devigged close?
- **Devig flattering the model?** Is the baseline the Shin-devigged Pinnacle close (not multiplicative on
  lopsided/FLB markets, not a soft book)?
- **LLM number leaking in?** Does the LLM only route/extract/synthesize? Is every probability computed by
  the quant pipeline? (Freshness LLM stores `confidence` for display only; RAG exposes no numeric tool;
  any intel that influences the number goes through the bounded, leak-flagged, human-gated scheme-prior.)
- **In-game weight surface overfit?** Was `w` fit on a held-out season and evaluated on a different one?
  Is the in-sample-vs-OOS Brier gap < 0.01?
- **Early-season structural window, not skill?** Is there a separate eval for games 1-20 vs 21+ to
  attribute timing vs structure?
- **Data moat or dirty parquets?** Does the data demonstrably improve OUTPUTS (lower OOS Brier), or is it
  just volume?
- **Velocity at the wrong target?** Is the build pointed at calibration/in-game/freshness (items 1-4), or
  chasing impressive-sounding features the gate would reject?
- **Autonomous agent breaking discipline?** Are the no-push / no-full-pytest / no-registry-write rules
  enforced by HOOKS (N4), not just prose? Did a shared-config edit get human-confirmed?
- **Is the honest reject being recorded?** A clean "no edge / market efficient / BSS <= 0" is a SUCCESS
  and a product feature -- is it written to the proof/ledger, not buried or tuned away?

The meta-guard: treat every win as guilty until OOS-proven across two corpora with a CI and a DM test.
That reflex is the actual product.
```

---

_Build order recap: N1+N2 -> N4 -> N3 -> X1 -> X3 -> RAG -> X2. N2 (Shin-devigging + calibration
audit) is folded into N1 -- the gate baseline is the Shin-devigged close and reliability diagrams
are part of N1's done-criteria, making N2 a prerequisite absorbed into step 1. N4 enforces
discipline mechanically; N3 in-game and X1 freshness are the real prediction-quality levers; the
ledger (X3) is the trust moat. Markets are efficient -- claim calibration, never a dollar edge._
