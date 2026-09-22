GAP S395 | sport nba | worktree harness-h54 (master-based) | log cx_s395_nba_output_audit
# NBA output auditor: reconstruct the period-first primary and the paired-subset D contrasts before any NBA verdict is read (design: ASTRA_ROUND14 row 11)

SINGLE PROBLEM: the landed auditor (row S379, extended by S387 to tolerate D null) audits the scorer's tick / equal-game cells. The
NBA primary is the period-first cell (row S383) written by the NBA runner (row S394) as primary.json, and arm D is compared only
on its paired subset. Nobody audits those; a wrong period weighting or a subset mismatch could release a false NBA verdict.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/ingame/nba_four_arm_output_audit.py` fails. Read on master and quote:
four_arm_output_audit.py + four_arm_output_audit_checks.py (check names, statuses, CRITICAL set, the redaction rule, the
RECONSTRUCTION_ABS_TOL constant, the LF / CRLF seal handling, the K convention), baseline_four_arm_period.py (the period-first
formula and the seed-13 draw stream), the S394 spec (primary.json shape) and docs/evidence/tracking/specs/S383_spec.md AMENDMENT 1.

CHANGE (NEW files only):
1. scripts/platformkit/ingame/nba_four_arm_output_audit.py (<= 300 LOC; helper nba_four_arm_output_audit_checks.py allowed): runs
   the landed audit first (all its checks, unchanged, as a dependency) and adds: P.primary -- recompute the period-first point,
   each M[p], the game counts, the discarded-draw count and both interval endpoints from paired_rows.json with an INDEPENDENT
   implementation (no import of stratified_cells for any estimate; numpy allowed for the identical draw stream), compare to
   primary.json to RECONSTRUCTION_ABS_TOL (counts exact); P.weights -- the four periods carry equal weight and OT rows are excluded
   and counted; P.support -- discarded draws <= 20 or the verdict is UNDERPOWERED period_support_insufficient; D.subset -- the
   d_subset population equals the d_eligible scored rows exactly, its A / B / C are RECOMPUTED on that subset (never the full
   population), D-minus-C is reported beside D-minus-A and labelled DESCRIPTIVE; X.exposure -- the games in the scored population
   are reconciled against the frozen exposure sets named in the sealed prereg (the S86 797 and the S58 all-games facts from row
   S392) and the population the prereg declares primary is the one audited; verdict_release requires every P / D / X check and
   the landed CRITICAL set to PASS. Stdout and the audit JSON carry statuses, counts and absolute discrepancies only -- no value.
2. tests/platformkit/ingame/test_nba_four_arm_output_audit.py: a synthetic NBA trial output built in the test (with S387-shaped
   rows incl. D null) that PASSES; seeded defects: a wrong M[p] weight, an OT row counted, a discarded-draw count off by one, a
   d_subset row that is not d_eligible, D compared on the full population, an exposure-set mismatch, a primary point altered by
   2e-9 -- each flips verdict_release false and names the check; no value in stdout or JSON. Runtime note: the bootstrap
   reconstruction takes minutes; keep the synthetic corpus small.
3. Memo docs/evidence/harness/S395_nba_output_audit_2026-09-22.md.

CONTROLS: PREPARE only, NEW files only, construct tests, no real output (none exists), no real ledger, no network. ACCEPTANCE:
per-file test passes; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list.

AMENDMENT 1 (2026-09-22 16:1xZ; binding; after verifier round 1 REJECT). (a) The landed four_arm_output_audit.py check
A.denominators is MLB-specific (it matches the landed MLB census keys) and can never PASS on NBA output; the NBA auditor therefore
runs every landed check unchanged as a dependency EXCEPT that A.denominators is re-implemented for NBA inside the NBA auditor: it
compares the trial's census (the S387 census-only keys: files, games, ticks, eligible_ticks, eligible_games, eligible_ticks_d,
model_prob_missing_for_d, non_integral_state, excluded_ticks, excluded_by_reason) against the frozen denominators parsed from the
SEALED NBA prereg, exact equality per key; the landed A.denominators status is reported verbatim under the name
landed.A.denominators with status SUPERSEDED and never counts toward verdict_release; four_arm_output_audit.py is NOT edited and its
MLB behaviour is untouched. A construct test proves that an unmocked NBA fixture (a synthetic sealed prereg plus a synthetic trial
output shaped like S394's) reaches verdict_release True, and that a one-off in any denominator key flips it false naming
A.denominators. (b) X.exposure requires EXACT SET EQUALITY between the game identities of the scored primary population in
paired_rows.json and the eligible-game identity list pinned in the sealed NBA prereg (a SHA-256 over the sorted identities joined
by newlines, plus the count; the seal package computes it from the census); a missing or an extra game FAILS with the identities
listed; the frozen inventory counts (S86 exposed games and S58 scored games) are read from the sealed prereg text, never from the
trial output or from caller arguments; tests: a scored game missing, an extra game, a wrong frozen count. (c) The S382 seal package
must pin, in these exact line formats, ELIGIBLE_GAMES_SHA256: <hex>, ELIGIBLE_GAMES: <n>, S86_EXPOSED_GAMES: <n>, S58_SCORED_GAMES:
<n>, plus the S387 census denominators; until it exists the NBA auditor's tests use a synthetic sealed prereg carrying those lines.

AMENDMENT 2 (2026-09-22 17:0xZ; binding; after round 2: Opus ACCEPT WITH CORRECTIONS, codex sol REJECT). (a) POPULATIONS: the
scored PRIMARY population is the post-warm-up population (the S382 draft, lines 111-112 and 216: 5 warm-up folds, 1,570
post-warm-up games, 217,758 live post-warm-up ticks; the census folds list marks the warm-up folds); the ELIGIBLE population is the
census eligible set (1,593 games, 221,066 ticks). They differ, and no arithmetic on S58 / S86 inventory counts may be used to
derive either. X.exposure therefore checks EXACT SET EQUALITY between the scored primary game identities in paired_rows.json and the
pinned PRIMARY_GAMES_SHA256 / PRIMARY_GAMES lines, AND that the union of scored and warm-up game identities equals the pinned
ELIGIBLE_GAMES_SHA256 / ELIGIBLE_GAMES; S86_EXPOSED_GAMES and S58_SCORED_GAMES are read from the sealed text as strict non-negative
inventory counts, reported, and never combined with the populations (the equality at nba_four_arm_output_audit.py:82 is removed).
(b) WARM-UP CONVENTION shared with the S394 runner (its fix 1c): the runner hands the FULL paired set to the landed
stratified_cells, which counts warm-ups itself, so primary.json reports n_input over all rows and n_warmup > 0; the auditor
reconstructs the primary from docs['rows'] with the producer's warm-up flag (never from a pre-filtered 'selected' subset) and audits
saved n_input / n_warmup against its own counts; a mismatch names the count. (c) Line formats: PRIMARY_GAMES_SHA256: <hex> and
PRIMARY_GAMES: <n> join the four AMENDMENT 1(c) lines; the seal package (S402 AMENDMENT 2) emits them; the census echo line is named
CENSUS.eligible_games so no unanchored pattern matches ELIGIBLE_GAMES twice; every consumer pattern is anchored to the line start.
(d) A game whose scored rows are all overtime stays in the primary population identity (it contributes nothing to periods 1-4);
count such games as ot_only_games. (e) Tests: eligible and primary counts intentionally differ in the fixture (warm-up games
present) while the exact identity pins release; a missing / extra scored game, a wrong PRIMARY_GAMES, a wrong ELIGIBLE_GAMES, a
duplicated pinned line and a wrong inventory count each flip release false naming X.exposure.

AMENDMENT 3 (2026-09-22 19:0xZ; binding; from fix 1d against the LANDED S394 runner shape). MEASURED by the fix agent on a fixture
built through trial._primary(stratified_cells(primary_rows)): the landed S394 runner emits NO D_minus_C_<metric> contrast and NO
d_subset.scored_keys, both named in this row's CHANGE clause. RULING: the auditor audits each when present and never invents
either; requiring them would fail every real S394 output. Their absence is recorded in the audit report as a producer gap
(check status NOT_AUDITABLE with reason producer_field_absent, never PASS) and in the memo's NOT VERIFIED list; closing it is an
additive S394 follow-up row (allocated by the orchestrator, not this row). The auditor's release verdict on the landed shape is
therefore reached with C.means NOT_AUDITABLE and those two checks NOT_AUDITABLE, and the seal / trial memo must say so in words.

AMENDMENT 4 (2026-09-22 19:0xZ; binding; from the codex sol round-5 verdict and the astra round-5 critique on fix 1e). (a)
IDENTITY CLOSURE: X.exposure requires eligible_ids == primary_scored_ids | warmup_ids (a non-warm-up eligible game absent from
PRIMARY refuses); the fixture's g4 embeds the defect and is corrected. (b) DUPLICATE KEYS REFUSE: a repeated (game_id, key) in
either primary_paired_rows.json or paired_rows.json refuses BEFORE any map is built (grain() silently overwrote, making the tick
restriction order-dependent; a D-ineligible row re-inserted with a changed timestamp evaded reconciliation); both duplicate
orders tested end to end. (c) FULL game_first RECONSTRUCTION: every field including the label VALUE ('SECONDARY'),
n_leave_one_out_discarded and the D-subset secondary diagnostics; a corrupted label or count refuses. (d) THE VERDICT ARTIFACT IS
AUDITED: trial_summary.json (written by the landed runner at nba_four_arm_trial.py:131 with the memo-facing verdict and copied
estimates) is loaded and every copied number and label must equal the reconstructed primary values; a summary claiming AHEAD
against contradictory primary values refuses. (e) THE SAVED INTERVAL'S OWN VERDICT: a saved interval that straddles zero can never
carry SINGLE-WINDOW or AHEAD whatever the tolerance -- the auditor applies the landed verdict rule (imported) to the SAVED
endpoints as well as to the reconstructed ones and refuses a label the saved endpoints do not support. (f) THE GAME-COUNT BAR ON
EVERY LABEL: the inherited check at four_arm_output_audit_checks.py:275 accepts a negative interval as SINGLE-WINDOW before the
game count; this auditor applies N_MIN_GAMES (imported) to every labelled cell itself and refuses a SINGLE-WINDOW / AHEAD label
below the bar. (g) MALFORMED CENSUS ECHOES REFUSE: any draft line beginning 'CENSUS.' that does not match the echo regex exactly
(trailing whitespace, comma-formatted number, unknown key) is a refusal, never ignored. (h) REAL SHAPE, NOT INVENTED: the landed
runner's attempt.json carries no descriptive_soccer; the auditor treats its absence on an NBA output as not-required (never a
refusal), and the fixture must not invent fields the landed runner does not write. (i) NOTED, not changed: endpoint agreement
cannot prove the producer's SEED / N_BOOT were used (outputs can coincide on constant populations); the memo says so.
