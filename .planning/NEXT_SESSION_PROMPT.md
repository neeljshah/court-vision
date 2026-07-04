# NEXT SESSION PROMPT -- paste this to start the new session

go on the loop. Continue the autonomous full-fleet build exactly where the last
session (2026-07-03..04, sprint waves 1-21) left off.

## Read FIRST (in order, nothing else before acting)
1. memory: feedback_sprint_fleet_orchestration_2026_07_03 (the standing loop
   rules: usage lifted thru 2026-07-06 EOD then standard rails; FABLE architects
   everything -- Sonnet executes, Opus reviews, Haiku reads; per-wake thrift;
   Workflow-tool fleets; if the loop model is not Fable, spawn
   Agent(model="fable") for every decision).
2. memory: project_sprint_2026_07_03_retrospective (what shipped + every honest
   verdict + the standing human queue).
3. memory: reference_ingame_data_sources_2026_07_04 (source recipes + traps).
4. .planning/NOW.md head (wake ledger + NEXT queue) + .planning/AUTONOMY_CHARTER.md.

## Operating contract (unchanged)
- Wake protocol per charter: lock -> stop-flag READ (.bot_state/live_status.json;
  `bot stop` = exit) -> scoreboard probe -> pull queue -> Sonnet lanes on
  disjoint paths -> Opus adversarial review per lane (builder report-crash ->
  direct Opus review of the on-disk diff) -> per-lane targeted local commits
  (never push; -f for .planning; watch 300-LOC caps; separate commits per lane)
  -> NOW.md ledger + spend + last_wake_ok -> next wave. Never stop on your own.
- CADENCE RULE: full 5-lane fleets ONLY when high-value work exists; when the
  bottleneck is wall-clock forward-evidence accrual, run LIGHT check-ins
  (~3600s): spine + feeds-vs-allowlist + capture + forward_evidence_scoreboard;
  escalate to a fleet only if a gate DECIDES (real headline_verdict, not the
  DECIDABLE_NOW heuristic), a regression appears outside the allowlist
  (pinnacle/soccer_intl, pinnacle/npb, fanduel/nba), or the user messages.
- HONESTY rails (absolute): no $-edge/ROI claims ever; REJECT/INSUFFICIENT =
  success; leak-free + >=2 independent corpora for any SHIP; provenance-separate
  validation vs forward corpora; never touch src/ kernel/ api/
  scripts/team_system/ intel/ or data/registry/; never flip a flag; paper-only.

## State at handoff (2026-07-04 ~14:00Z)
- 21 waves, ~84 lane commits, ALL Opus-reviewed; 632 tests/51 files GREEN;
  eval-gate 38/38; calibration ECE improved every sport.
- Forward gates accruing: MLB tail fwd=5 (needs ~20, ~5 days), soccer_intl
  PENDING, wnba/npb/kbo/nba pre-registered (nba stamped 2026-10-01).
- THE ONE HUMAN ACTION still pending: boot.ps1 restart -- activates grade-writer
  fix, 429 pacing, enrichment persistence, supervisor beat-thread fix, npb/kbo
  grading bridge. Verify after with:
  python -m scripts.platformkit.autonomy.post_restart_verify
- Standing HUMAN queue: restart (above); PROPOSED_soccer_xg_wiring.md;
  soccer-suppression memo; m32 weather SHIP_REVIEW; OddsAPI $59 NBA-closes
  brief; states-gate CI adoption at bigger n; prop-guard KEEP; UI-off option;
  reconcile_survivors adopt design; m2 bounce == the restart.
- Known-chronic (until restart): m1_ui flap (orphan-node factory fixed at next
  boot; if port 3000 is held by a NON-tracked stale node PID, killing that
  orphan is the established evidence-verified action).

## Queue seeds beyond NOW.md NEXT (Fable re-architects each wake)
- Post-restart verification wave the moment the human restarts (run the
  verifier, confirm enriched grade rows + npb/kbo grading + pacing counters).
- Gate-decision waves when forward floors clear (tail gates, enrichment gates).
- NBA-season readiness follow-ons (states corpus from linescores.parquet path,
  espn_wp nba probe, capture DEFAULT_SPORTS += nba nearer to October).
- WNBA/NPB/KBO first-grades verification as their finals land.
- Charter drift items -> the 2026-07-10 Opus review
  (.planning/CHARTER_DRIFT_NOTES_2026-07-04.md).

Work hard, stay honest, compact often, and keep every claim traceable to an
artifact. The yardstick is calibration vs venue/close -- never a dollar claim.
