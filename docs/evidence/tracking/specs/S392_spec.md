GAP S392 | sport nba | worktree harness-h51 (master-based) | log cx_s392_nba_exposure_disposition
# NBA exposure and provenance disposition (document only; design: ASTRA_ROUND14 row 9 and self-deceptions 1 and 3)

SINGLE PROBLEM: the NBA prereg draft treats the 796 games outside S86 as candidates for an untouched claim, but S58 scored ALL
1,593 games at one checkpoint and the model constants have unknown provenance (row S385). Which population, if any, can carry an
untouched claim, and for which arms, must be decided and written BEFORE the seal, not discovered after.

BINDING BEFORE-CONDITION: `ls docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md` fails. Read and quote:
docs/evidence/harness/S385_S86_MODEL_PROVENANCE_SCOUT_2026-09-21.md; docs/evidence/harness/S86_nba_every_tick_2026-09-03.md; the
ledger lines for S58, S86, S98, S103 in docs/evidence/RESULTS_LEDGER_SYSTEM.md (grep each id); docs/evidence/ingame/
S382_NBA_PREREG_DRAFT_r1_2026-09-21.md sections on exposure and populations; docs/evidence/harness/ASTRA_NBA_SECOND_CORPUS_AUDIT_
2026-09-21.md section 1; docs/evidence/ingame/S347_FOUR_ARM_RESULT_2026-09-21.md (what the MLB result licenses).

CHANGE (NEW document only): docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md, ASCII, contract Q6, under 250 lines:
1. EXPOSURE INVENTORY by identity: for each prior row that read NBA outcomes (S58, S86, S98, S103 and any other you find by grep),
   which games, which ticks, what was fitted or selected using them, and what DECISION in the current program used that output
   (quote the ledger line). A game is EXPOSED if any decision the current program relies on used its outcome.
2. DISPOSITION: state, with the reason, which of these can carry an untouched-validation claim for arms A / B / C: (i) all 1,593,
   (ii) the 796 outside S86, (iii) none -- and recommend one. Astra's warning stands: "outside S86" is not "untouched" if S58
   exposure fed a decision; say whether it did.
3. ARM D: descriptive only until parameter authoring evidence for commit ee7087200 exists; list exactly what evidence would
   change that (the file or record that would show which games informed the constants) and who holds it (owner / session history).
4. The prereg text (two paragraphs) to paste into the S382 draft's exposure and populations sections, with every population size
   marked TO-FREEZE-FROM-CENSUS.
5. What the MLB result (all UNDERPOWERED; model arm above the market) implies for the NBA design: one paragraph, no prediction.
Memo docs/evidence/harness/S392_nba_exposure_disposition_2026-09-22.md (short; NOT VERIFIED last).

CONTROLS: document only, no code, no data run, no network. ACCEPTANCE: contract preflight passes; ASCII; no seal line; the memo ends
with a NOT VERIFIED list.
