# Charter Drift Notes -- for 2026-07-10 Opus weekly review

Scope: AUTONOMY_CHARTER.md vs sprint practice, wakes 1-15 (2026-07-03pm
- 2026-07-04 02:00). Sources: NOW.md wake entries, .bot_state/spend_
2026-07-03.json, git log, memory feedback_sprint_fleet_orchestration_
2026_07_03.md, docs/research/organization-sprint/PROPOSED_*.

1. SPEND (S3): rail lifted per user directive, as designed. Actual:
   15 wakes, 10-18 agents/wake, ~0.88M-1.56M subagent tokens/wake,
   sum ~17.6M tokens. No breach possible (rail off), no PAGE fired.
   RATIFY as written. AMEND: log per-wake token count into the spend
   file AT wake time (currently backfilled narratively), for audit.

2. WAKE PROTOCOL (S5): ran continuous, back-to-back (~18-45min gaps),
   matching the amendment; step 5 (NEXT from NOW.md) held every wake,
   never improvised. Digests written daily. RATIFY. AMEND: S5 step 9's
   "LAST WAKE BEFORE MORNING" trigger doesn't fit a continuous loop
   with no morning boundary -- change to "at least once per ~24h
   wall-clock."

3. DECISION RIGHTS -- orphan kill (S6/S7): wake 15 killed an orphaned
   pre-restart node holding port 3000 (evidence-verified stale PID vs
   restart timestamp, not the live process). S6 only enumerates
   "wedged PID" (S5's pinned timeout+CPU definition); an orphan is a
   different failure mode, stretched by analogy. No harm (m1_ui clean,
   m13 self-recovered). RECOMMEND AMEND S6: add "kill a verified ORPHAN
   process (stale PID from a prior restart cycle, confirmed by PID-
   start-time vs restart-timestamp evidence, holding a port the live
   supervisor set needs)" -- keep the evidence-verification language
   explicit so this doesn't widen into "kill anything that looks old."

4. HUMAN-GATE BOUNDARY (S6/S11): verified via git log --name-only
   filtered to src/ kernel/ api/ scripts/team_system/ intel/ since
   2026-07-03T12:00 -- ZERO matches. Zero flag flips, zero pushes.
   PROPOSED diffs used 2x (not 3): PROPOSED_soccer_inplay_suppression.md
   (wake 8) + PROPOSED_soccer_xg_wiring.md (wake 15). The wake-9
   scan_ledger fix was DIRECT-applied, not a PROPOSED diff -- it never
   touched a gated path, so it didn't need one. RATIFY boundary holds
   perfectly; CORRECT any retelling that says "3x PROPOSED" to "2x."

5. REPORT-CRASH RECOVERY: 3 builder structured-output crashes (wake 6
   npb-kanji, wake 8 tail-prereg, wake 15 wnba-states-gate) each
   handled by direct Opus review of the on-disk diff in place of the
   missing self-report, before any commit. Charter has no explicit
   clause for this. RECOMMEND ADD to S7/S8: "On builder crash pre-
   report, do not retry blind -- Opus reviews the working-tree diff
   directly; a diff not attributable to a specific lane brief is
   discarded, not guessed-and-applied."

6. RESTART PROVENANCE (S7): boot.ps1 confirmed 23:11 (13/13 PIDs,
   51s window); WHO/WHAT triggered it (watchdog AtLogOn vs human) is
   evidence-inconclusive -- NOW.md states the ambiguity rather than
   guessing. RECOMMEND AMEND S7: boot.ps1/watchdog stamp an initiator
   field into .bot_state/ on every boot to close this evidence gap.

7. NEW STANDING RULES (memory-only, not yet charter text): (a) FABLE-
   ARCHITECTS-EVERYTHING -- all wave/lane/queue/gate design and finding
   adjudication is Fable-only, stricter than S6's existing list; (b)
   PER-WAKE THRIFT -- one extraction call/wave, <=15-line commits and
   NOW.md entries, no re-reads of just-edited files (targets the
   orchestrator's window, not fleet size); (c) IN-GAME BREADTH UN-
   PARKED -- already self-healed, S4(iv) text already reflects the
   2026-07-04 directive in place. RECOMMEND: fold (a)+(b) into S3/S6 as
   permanent (proved useful over 15 wakes); (c) needs no further action.

Every item above traces to a cited artifact; none introduces a new
claim beyond what NOW.md / spend file / git log / memory already show.
