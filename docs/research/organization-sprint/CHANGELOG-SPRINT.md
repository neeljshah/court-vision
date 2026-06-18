# CHANGELOG — Organization Sprint (2026-06-16)

> Live log. Every change: wave, files, rationale, test result. ASCII only.
> North star: organize the calibrated 4-sport predictor to the highest level across MEMORY, CODE,
> and the AGENT BUILD-LOOP, into a credible SELLABLE decision-support package. NEVER a $-edge product.
> Binding: local commits only; never push origin; human-gated dirs (src/kernel/api/scripts/team_system/intel)
> untouched; per-file tests only; build in scripts/platformkit or domains/<sport>; honest rejects are successes.

## Wave 0 — grounding + Phase 0 planning (orchestrator)
- Read CLAUDE.md, docs/JOB_EVIDENCE_PACKET.md (do-not-claim truth source), docs/PLATFORM.md,
  MORNING-BRIEF, IMPLEMENTATION-KICKOFF, reference-impl/README, memory MEMORY.md index.
- Recon: scripts/platformkit/ (no eval_gate/ yet), domains/{basketball_nba,mlb,soccer,tennis},
  .claude/ (no skills/, no settings.json, no scripts/hooks/), apps/ (8-dir sprawl), vault/_Organized.
- Created docs/research/organization-sprint/ ; seeded this changelog.
- Branch: fullsend-ingame-pregame-execution (LOCAL only; origin is PUBLIC -> never push).
- Next: Phase 0 Opus debate -> PLAN.md / TASK-LEDGER.md / RISK-REGISTER.md.

## Wave 1 — Stream 4a (eval-gate keystone) + Stream 2 (build-loop) launched
- S4a: copied verified reference-impl eval_gate/ (16 files) into scripts/platformkit/eval_gate/;
  ran run_all.py -> 34/34 GREEN in the new location. Completion workflow (run_gate CLI + golden
  fixture + baselines + kernel-reuse + Opus review) running.
- Verified Claude Code config via claude-code-guide (caught: no --max-turns/--max-budget-usd flags;
  imports use !import()). Probed deps: lancedb/sentence-transformers/etc MISSING -> RAG re-scoped offline-first.

## Wave 2 — Stream 2 build-loop scaffolding COMPLETE + committed (52b03525)
- Built (8-agent Opus workflow): 7 skills (.claude/skills/, gitignored), 4 cv-subagents (.claude/agents/),
  3 hooks (scripts/hooks/), predictor MCP skeleton (scripts/platformkit/mcp_server/), 4 path-scoped rules
  (.claude/rules/), cost_ledger.py, obs/langfuse_trace.py, and PROPOSED-{settings,mcp,CLAUDE}.* (human-confirm).
- Opus review = APPROVE WITH FIXES; honesty+collision = PASS (live config untouched, predictor never
  authors a number, no $-edge/retracted numbers, no secrets). Applied all 7 fixes:
  renamed colliding skills (benchmark->cross-sport-benchmark, run-pipeline->pipeline-rebuild);
  deleted 3 duplicate hooks (kept richer set); cv-explore model->haiku; fixed PROPOSED-settings.json
  deny-globs + fallbackModel + hook refs + matchers; added apply-notes to PROPOSED-CLAUDE.md + mcp checklist.
- Smoke-tested hooks: block git-push-origin (exit2), block full pytest (exit2), allow safe (exit0),
  warn on src/ edit (exit0+stderr), SessionStart context emit. All correct.
- Committed TRACKED artifacts only (targeted add): scripts/hooks/, cost_ledger.py, mcp_server/, obs/.
  .claude/* + docs/research/organization-sprint/* are gitignored local-only (correctly excluded).
- HUMAN-CONFIRM left staged-not-applied: enabling .claude/settings.json (hooks+routing) + .mcp.json (servers).

## Wave 3 — Stream 4a eval-gate keystone (N1) COMPLETE + committed (ec2fada2)
- 11-agent Opus workflow completed run_gate CLI + golden fixture + baselines + kernel-reuse + review.
- gen_golden -> 103 stratified SYNTHETIC states (9 regimes), schema-valid, vintage-clean.
- run_gate --golden: ~1.2s offline, exit 0; scoreboard nba_2023_24 BEHIND (bss -0.241),
  nba_2024_25 MATCHES_CLOSE (bss -0.188); mlb_2024 skip-until-X2. Blocks only on regression/leak.
- 34/34 core + 7/7 gate tests green. baselines byte-exact with live run (_synthetic:true).
- Opus review SHIP-with-fixes; applied 2 real bugs: (1) baseline.py --freeze imported a nonexistent
  symbol -> fell back to a wrong n=100 generator; rewrote to freeze from the SAME fixture+predictor
  path the gate runs -> re-freeze reproduces n=51/52 byte-exact (reproducibility landmine defused).
  (2) run_gate --corpus now threads corpus_dir -> fails closed CORPUS_ABSENT instead of scoring the
  real model on synthetic states. Re-verified: freeze n=51/52, gate exit 0, --corpus exit 1, tests green.
- Committed scripts/platformkit/eval_gate/ + tests/fixtures/golden/ (targeted add). LOCAL only.

## Wave 4 — Stream 4b/c funnel levers (N3 in-game / X1 freshness / X3 ledger) launched
- eval-gate dir released -> promoting ingame_blend/freshness_schema/ledger into domains/+platformkit
  with eval-gate as judge + honest "real-corpus OOS validation = human-run" flags. Workflow running.

## Wave 4 RESULT — Stream 4b/c funnel levers COMPLETE + committed (121e9be7)
- N3 in-game blend (domains/basketball_nba/ingame_blend_{prior,plive,surface,eval}.py): sim as BLACK-BOX
  prior, 2D weight surface fit-A/eval-B + B->A, overfit gap 0.0027/0.0072 (<0.01), EMA + garbage clamp. 10/10.
- X1 freshness (scripts/platformkit/freshness/): vintage leak guard trips on planted late row; LLM extraction
  stub emits text+confidence only (never a number); proxy quarantine OPTIMISTIC_UPPER_BOUND. 12/12.
- X3 track-record ledger (scripts/platformkit/ledger/): append-only atomic idempotent; grade_outcomes no-overwrite
  + drops pred_ts>=game_date leaks; drift_check exit-2 on >1-sigma; replay_proof deterministic 0.01s (<30s),
  NO units/roi/edge column. The sellable trust artifact. 12/12.
- Opus review PASS (1 import bug fixed); honesty+leak PASS (edge_claimed=False everywhere, REAL_OOS_VALIDATION
  _PENDING flagged, no real-data win fabricated). eval-gate non-regressing (34/34 + exit 0). Spot-verified in-hand.
- Known non-blocking: running freshness+ledger test files TOGETHER cross-contaminates bare module names
  (schema/metrics) -> 3 spurious fails; each PASSES in isolation (the binding per-file-only contract). Accepted.

## Wave 5 — Stream 5 sellable calibration-record launched
- eval-gate + ledger done -> building the GAP vs the 2026-06-15 productize wave: public CALIBRATION_RECORD.md
  (reliability diagrams + Brier/BSS vs Shin-devigged close + "market-efficient here" first-class), reliability
  generator, startup calibration banner, SELL-READINESS.md, PROPOSED live_board_ui wiring. Workflow running.

## Wave 5 RESULT — Stream 5 sellable calibration-record COMPLETE + committed (30f8714b)
- Finding: package was ~95% pre-built (2026-06-15 productize wave). Workflow assessed, reused, verified end-to-end.
- docs/CALIBRATION_RECORD.md regenerates in 0.05s from committed golden+ledger fixtures (real numbers):
  reliability tables (pred vs obs, n/bin, SPARSE<30), Brier/BSS vs Shin-devigged close, SOURCE badges,
  "MARKET-EFFICIENT HERE" first-class headline. Deterministic byte-stable.
- calibration_banner.py wired into predict_matchup.py (stderr, --no-banner): "calibration not edge; we MATCH
  the close, never beat it". reliability_diagram.py bug-fixed (broken golden path + wrong keys -> derives
  per-row via the SAME eval_gate.walk_forward; Pred-mean shows true per-bin mean). docs/SELL-READINESS.md honest.
- Opus review + honesty/GTM gate PASS (no $-edge/picks/ROI live copy; decision-support framing; disclaimer;
  edge_claimed=False; no retracted numbers live). Deduped: removed underscore SELL_READINESS.md + thinner
  tests/platform calibration-test copies (kept comprehensive package-adjacent). 21+16 tests green.
  apps/live_board_ui UNTOUCHED (PROPOSED wiring snippet only). Committed (incl .gitignore PNG+RAG-index ignores).

### SCOREBOARD: 4 waves committed locally (S2 52b03525, S4a ec2fada2, S4b/c 121e9be7, S5 30f8714b).
### STILL RUNNING: Phase 0 plan, recon (MEMORY/CODE audit), RAG offline. GATED: memory reorg, code-org, vault reorg.

## Wave 6 — Stream 1c RAG COMPLETE + committed (fa582818)
- Offline-first queryable brain (scripts/platformkit/knowledge/ + scripts/mcp_server/vault_knowledge.py):
  sklearn TF-IDF hybrid + RRF + relevance-floor honest-reject over ~4113 vault notes + auto-memory; pluggable
  upgrade interface; sha-incremental + lockfile. HARD BOUNDARY tested: emits NO probability (test_boundary 6/6).
  31 per-file tests green. Spot-verified in-hand before commit. data/index gitignored.

## Wave 7 (USER: wind down + execute + Sonnet) — gap fleet + memory reorg launched
- 50-OPUS GAP-COHERENCE FLEET (w5vvhi5tj): 40 surface auditors + 6 cross-coherence + 4 synth -> GAP-REGISTER.md
  + COHERENCE-PLAN.md + P0 triage + completeness critic. Read-only audit; P0 fixes to execute when it lands.
- S1a MEMORY REORG (Sonnet+Opus, conservative): in-place link/date/frontmatter fixes + MEMORY.md<=200 +
  MEMORY-MAP.md; risky merges/deletes -> MEMORY-REORG-PROPOSAL.md (human-gated, NOT auto-applied). Running.

### SCOREBOARD: 5 waves committed (S2, S4a, S4b/c, S5, S1c). RUNNING: Phase0 plan, recon, gap-fleet, memory-reorg.
### REMAINING: gap-fleet P0 fixes, code-org (S3, awaits CODE-AUDIT), vault reorg (S1b, deferred-risky), SPRINT-SUMMARY.

## Wave 8 RESULT — 50-OPUS GAP FLEET COMPLETE (GAP-REGISTER.md + COHERENCE-PLAN.md) + P0 fixes
- 50 Opus agents (4.4M tokens, 1396 tool uses). Honest verdict: honesty/leak DISCIPLINE genuinely intact
  where it is the design center (no $-ROI/picks live; retracted numbers only in guards/retraction framing;
  LLM authors no scored number; edge_claimed=False pervasive; eval-gate core math provably correct).
  Defects in 5 themes; real P0 bugs found + FIXED.
- P0 FIXES BATCH 1 (committed 7a408ad2, verified in-hand):
  #1 ledger vintage guard string-compared timestamp vs date -> dropped ALL same-day pre-tip predictions;
     now parses dates (same-day = leak-free, only post-game-day = leak).
  #2 ledger produced ZERO rows (tennis fully broken): key mismatch (home_win_prob vs predict_matchup's
     p_home_win); now maps p_home_win->ml (tennis p1_match_win) + over_2.5->total_o2.5, dedup aliases.
  #4 HONESTY LEAK: RAG vault_search/related_nodes/note-resource returned raw vault text (incl retracted
     +18.38% ROI) to an LLM client unscrubbed; now _scrub() on every returned snippet/title/body +
     hardened _scrub (full-decimal percent + explicit retracted-figure block-list). Boundary 10/10 green.
- P0 FIXES BATCH 2 (Sonnet workflow w2yc3tylo running): #3 promptfoo invalid exec provider, #5 freshness
  tz-aware TypeError bypasses leak guard, #6 supersede tie-break order-dependent, P1 in-game "0.209->0.159
  WIN" doc drift -> reframe to honest fixture no-improvement. Opus review on commit.
- NOTED for SPRINT-SUMMARY (P1, human-decision): ingame_blend_* (N3) is a VALIDATION surface only -- not
  wired into the live predict_live path; coherence gap needing human confirm. Concurrent-append row-loss (P1).

## Wave 9 (WIND-DOWN) — P0 batch 2 + memory reorg + capstone + final close
- P0 BATCH 2 committed 408e8d0d (promptfoo provider, freshness tz+tie-break, in-game doc honesty across 5 docs).
- HONESTY-FIX TAIL committed 3fb00302: de-hardcoded "NBA 0.209->0.159 WIN" / "all 4 WIN" in
  ingame_scoreboard.py + system_map.py (runtime-derived; NBA scoped VALIDATION_PENDING / SYNTHETIC ANCHOR /
  edge_claimed=False). Smoke-tested.
- S1a MEMORY REORG COMPLETE (Opus-reviewed): 172 files intact (0 deletions, 0 lost facts), MEMORY.md=200 lines
  (<=200), all 127 links resolve, MEMORY-MAP.md + MEMORY-REORG-PROPOSAL.md (human-gated) written. Recorded the
  sprint in the persistent brain: new memory project-org-sprint-2026-06-16.md + START-HERE pointer (172->173).
- SPRINT-SUMMARY.md written (capstone + HUMAN-CONFIRM list).
- FINAL VERIFICATION SWEEP all green: eval-gate 34/34 + gate 7/7 (exit 0), ledger 12, freshness 14,
  in-game blend 10, RAG boundary+assemble 10. Working tree CLEAN. origin NEVER pushed.

### FINAL: 8 sprint commits (52b03525 S2, ec2fada2 S4a, 121e9be7 S4b/c, 30f8714b S5, fa582818 S1c,
###        7a408ad2 P0-1, 408e8d0d P0-2, 3fb00302 honesty-tail). Discipline held end-to-end.
### DEFERRED (remaining-work, in HUMAN-CONFIRM list): S1b vault rebuild (risky), S3 full apps/ code-org
###        (awaits the still-finishing recon CODE-AUDIT), enabling hooks/MCP/slim-CLAUDE.md, real-corpus OOS.
