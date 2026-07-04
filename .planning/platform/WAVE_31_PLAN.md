# WAVE-31 PLAN (Fable-architected 2026-07-04 ~19:15Z, while wave-30 fleet wf_56124b67-c33 runs)

Launch IMMEDIATELY when wave-30 lands (no-downtime rule 4h). Lane list is contingent
on wave-30 verdicts -- adjudicate first, then prune per the contingency notes.

## Lanes (file-disjoint, Sonnet build + Opus adversarial review each)

1. reprocessing-harness (mission spine #2 -- the core standing machinery).
   OWNS: scripts/platformkit/reprocess/ (new pkg). Given an intelligence-layer
   variant (first client: wave-30 composition blend vs canonical naive), re-run
   historical + new games' predictions and score vs stored devigged closes AND
   outcomes, walk-forward, >=2 provenance-separated corpora; emit
   reprocess_verdict.json {improve|regress|null} with numbers. Makes every future
   intelligence change gateable by one command. CONTINGENT: reuse composition
   gate harness from wave-30 L7 regardless of its verdict (machinery > verdict).

2. mlb-sp-fatigue-redesign (conductor rank 4 redo, pre-registered at wave-29).
   Stronger fatigue proxy = within-start velocity decline (Statcast overlap);
   materialize consolidated velo parquet first (spec limit #8), then clone gate.
   Planted-null mandatory (the wave-29 NOT_TESTABLE catch is the reference).

3. line-history-retention (storage R1, ADOPTED). REUSE inplay_retention.sweep_all
   onto data/cache/line_history/ (uncapped stream). Small; test + one dry-run proof.

4. soccer-tier-gate (conductor rank 7). domains/soccer_intl/tier_calibration_gate.py;
   tiers {WC, qualification, Friendly}; >=100 matches/tier/fold; planted-null =
   shuffle tier; MATCH-not-beat framing; decade-block walk-forward + WC2026 OOS.

5. vault-feed-generator (conductor vault_feed design). Build + test the
   claims->dossier section generator (VERIFIED claims only, claim_id provenance
   lines) but NEVER invoke brain_pipeline -- it runs inside the next HUMAN-run
   build. Same lane: atlas-dimension graph-hub note generator from truth-spec
   JSONs. Deliverable = modules + tests + PROPOSED integration snippet.

6. ask-anything-v2 (contingent on wave-30 L8 PASS): add fit/scheme/matchup
   question families + wire the verdict-claim sibling (conductor contract gap 2,
   verdict_claims_validator.py, ~120 LOC) so gate verdicts become queryable with
   provenance. UNANSWERABLE stays honest.

7. weight-hierarchy-step2 (FABLE DESIGNS at adjudication, not pre-written):
   positional/contextual weight gate (big's 3P% vs guard's) -- design ONLY after
   composition_gate_verdict.json is read; the composition result decides whether
   step2 blends indices or attribute models. DO NOT let a Sonnet lane design this.

## Standing rails (copy into every brief)
Safe areas only; no human-gated trees; planted-nulls; REJECT=success; no $-edge;
ASCII; <=300 LOC; per-file tests; cd prefix; orchestrator commits (targeted adds).

## GPU policy (user directive 2026-07-04: "make sure its using gpu and working
effectively") -- use the RTX 4060 where it actually helps, never for show:
- Any lane fitting gradient-boosted/torch models on >100K rows (e.g. the 220K
  MLB pitch-states in lane 2, reprocessing harness at scale in lane 1) MUST try
  xgboost device="cuda" (tree_method hist) with an automatic CPU fallback and
  log which path ran + wall-clock for both when cheap to measure.
- VRAM cap ~6GB (8GB card, desktop uses ~1.2GB; never freeze the box); free
  models between folds; no torch dependency added solely for GPU (ponytail #5).
- Small-data gates (hundreds of players/games, sigmoid/bootstrap) stay CPU --
  GPU would be slower after transfer overhead; do not cargo-cult it.
- CV/tracking and any retrain lanes inherit the existing CUDA 11.8 conda env.

## SPEED RULES (user directive 2026-07-04: waves must run FAST) -- every brief:
1. PROOF-BY-ARTIFACT: any wall-clock-bound proof (network cycle, long gate run)
   runs ONCE; its output is SAVED as an artifact; the Opus reviewer verifies the
   ARTIFACT + re-runs only the fast per-file test, NEVER the long cycle. Fix
   rounds re-run the long proof only if the fix touched the hot path.
2. EXACT PATHS in briefs: give agents the real file/parquet paths (Haiku
   pre-scout them if unknown); discovery capped at 2 globs then report BLOCKED
   -- an agent burning 15 tool calls on find-the-file is the #1 waste.
3. EFFORT TIERS: mechanical lanes (retention wire, table builds) run at
   effort=low; only gates/reviews at default. Same model, fewer thinking tokens.
4. TIME BUDGET stated per lane (~10 min gate cap; checkpoint + report partial
   rather than grind); briefs say what NOT to do (no full corpus re-scans when
   a cached parquet exists).
5. NO BARRIERS: keep pipeline() so each lane streams build->review->fix
   independently; a slow lane (m13-class network proofs) never blocks the rest.
6. The orchestrator NEVER idles waiting: adjudicate + commit finished lanes as
   the slow tail runs; launch the next wave's independent lanes early when they
   do not depend on the tail.

## Adjudication checklist when wave-30 returns (Fable, in-window)
- Per lane: review verdict PASS? artifacts exist? -> targeted commit per lane.
- composition_gate_verdict.json -> decides lane 7 design + lane 1 client shape.
- m13-circuit proof -> if SLA fixed, note in ledger; if not, wave-31 hotfix lane.
- espn-injuries HONEST_NEGATIVE is fine -> record probe result in program doc.
- NOW.md ledger entry <=15 lines; stash wave-30-partial-UNREVIEWED becomes
  disposable once fresh lanes commit (drop only after verifying overlap).
- NPB/KBO first grades: morning wake ~09-10Z 07-05 (not this wave).
