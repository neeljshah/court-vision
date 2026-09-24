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

AMENDMENT 5 (2026-09-22 21:4xZ; binding; from the fix 1f report on AMENDMENT 4, which closed (a)-(h) with
reproductions and left one gap). (a) THE PRODUCER'S SEED AND N_BOOT ARE AUDITED OR NAMED UNAUDITED: MEASURED -- fix 1f
implemented every AMENDMENT 4 ruling with a BEFORE/AFTER flip per case, but closed with "Producer SEED/N_BOOT usage
remains unverified", so the auditor never establishes that the producer drew with the sealed seed and bootstrap count.
RULING: the auditor reads SEED and N_BOOT from the producer's own artifact and requires them to equal the sealed
constants (imported, never re-declared); when the artifact carries neither, the check is NOT_AUDITABLE with reason
producer_seed_absent -- never PASS -- and the memo's NOT VERIFIED list names it in those words. Tests: a mismatched
seed refuses; an absent seed field yields NOT_AUDITABLE with that reason; a matching seed passes.
(b) ONE SOURCE PER FIXTURE: MEASURED -- the first exposure run failed (1 failed, 83 passed) and passed only after the
fixture copies were synchronized by hand, so the same fixture exists in more than one place and can drift silently
between the boundary and exposure suites. RULING: each audited fixture has ONE on-disk source, loaded by both suites
through a single helper; a second copy is a defect, not a maintenance task. Test: the exposure suite loads the
boundary suite's fixture path and a deliberate edit to that one file changes both suites' outcomes.
(c) NOTED, unchanged: AMENDMENT 3's producer gap stands -- the landed S394 runner emits no D_minus_C_<metric> and no
d_subset.scored_keys, both audited as NOT_AUDITABLE with reason producer_field_absent, and the release verdict is
reached with C.means NOT_AUDITABLE, said in words in the seal and the trial memo. Fix 1f is UNVERIFIED: no
independent verdict on it exists, so the next round is the FIRST verification of AMENDMENT 4, not a re-verification.

AMENDMENT 6 (2026-09-22 22:5xZ; binding; follows S417 AMENDMENT 1): the auditor reconstructs the PRIMARY contrast per the
prereg's DECLARED arms -- after S417 lands the primary is C versus B (C_minus_B_<metric> == brier / logloss primary cells) with
C_minus_A_<metric> audited as SECONDARY, and C_minus_Blag_<metric> audited as a secondary against the B_lag arm; the declared arms
are read from the sealed draft's text, never assumed; a primary that names an arm the runner did not emit is NOT_AUDITABLE with
reason producer_arm_absent. Scope: the next S395 fix round after S417 lands.

AMENDMENT 7 (2026-09-23 18:2xZ; binding; after fix 1h applied AMENDMENT 6 on the LANDED S417 producer d2ae4b4f3 -- Opus fix
agent continuing the codex lane cut off by quota; 172 construct tests). The owned set gains the helper
scripts/platformkit/ingame/nba_four_arm_output_audit_declared.py (<= 300 lines: parses the DECLARED arms from the sealed
draft's PRIMARY and secondary lines) and the companion tests tests/platformkit/ingame/test_nba_four_arm_output_audit_fix1g.py
and test_nba_four_arm_output_audit_fix1h.py (the checks module sits at the 300-line rail). RULING confirmed from the fix report:
the landed producer writes each comparison's game_first twice (inside secondaries.comparisons[<name>] and in
secondaries.game_first[<name>]); the auditor no longer requires the two copies equal as a mapping precondition -- the labelled
copy is judged by P.secondary and the embedded copy by P.primary, so a numeric defect in either is a NAMED failure, never a
'prerequisite evidence unavailable' NOT_AUDITABLE; a declared C-minus-Blag secondary with no B_lag arm yields L.inventory and
L.subset NOT_AUDITABLE producer_arm_absent (arm B_lag) with release refused. P.seed stays NOT_AUDITABLE producer_seed_absent and
C.means NOT_AUDITABLE (no per-arm mean fields) until the producer emits them. The three S417-landed producer files are never
edited (diff against master empty). The next round is the FIRST independent verification of AMENDMENT 6 and of this amendment.

AMENDMENT 8 (2026-09-23 19:0xZ; binding; from round 6 on fix 1h -- Opus tier 1 REJECT and Opus tier 2 ACCEPT WITH CORRECTIONS). Tier 1 confirmed the AMENDMENT 6-7 mechanics on the S417-shaped construct (release True on consistent numbers;
P.secondary FAIL on a 2e-9 change to the labelled game_first copy and P.primary FAIL on the embedded copy; a declared
C-minus-Blag with no B_lag arm -> L.inventory / L.subset NOT_AUDITABLE producer_arm_absent, arm B_lag, release refused; the
AMENDMENT 1-5 closures in place; 172 tests) and found ONE blocker against the draft that WILL be sealed: (a) THE DECLARED-ARMS
PARSER MUST READ THE SEAL RUNBOOK'S TEXT: nba_four_arm_output_audit_declared.py:30-33 requires a line starting 'SECONDARY: ' or
containing ' are secondary'; after the runbook's text-only amendments (docs/direction/nba_seal_runbook_2026-09-23.md B2 steps a1
and b2, replacing draft lines 14-15 and inserting the standing-control paragraph) no such line exists -- the secondaries sit
INSIDE the PRIMARY paragraph ("DEMOTED TO SECONDARY, reported beside B-minus-A, D-minus-A and D-minus-C") and in the paragraph
beginning 'STANDING CONTROL (SECONDARY, never promoted): C-minus-B_lag and B-minus-B_lag'; declarations() on that text raised
ValueError 'artifact invariant', frozen_pins raised, P.inputs failed and every P.* / D.* check went NOT_AUDITABLE with release
False. RULING: the primary is the single contrast token on the 'PRIMARY: ' line; the secondaries are every OTHER contrast token
in the PRIMARY paragraph (to the next blank line) plus every token in the paragraph beginning 'STANDING CONTROL (SECONDARY'; the
old 'SECONDARY: ' / ' are secondary' forms stay accepted; a primary that also appears among the secondaries is refused by name;
a test seals the runbook's a1 + a2 + b2 text WORD FOR WORD (built from the r1 draft in memory) and expects primary (C, B),
secondaries {(C, A), (B, A), (D, A), (D, C), (C, B_lag), (B, B_lag)} and release True on the S417-shaped construct. (b) THE
'PRIMARY METRIC:' LINE IS READ when present (draft line 122, changed by step a2): its contrast token must equal the PRIMARY line's
token or the draft is refused by name (primary_metric_line_disagrees); one test. (c) The memo's FIX 1h item 1 names the reason as
the code emits it: reason producer_arm_absent with a separate arm field (AMENDMENT 7), never 'producer_arm_absent: <arm>'.
(d) The memo is condensed to <= 300 lines (the harness lands memos at the rail). NOTE recorded: the b2 block's LATENCY-EXPLAINED
labelling rule has no auditor check; S417 AMENDMENT 8(c) says the runner never emits that label, so the auditor asserts its
ABSENCE from the output (one check, one test) rather than auditing it.
(e) THE B_lag AUDIT CAN NEVER BE SKIPPED: L.inventory and L.subset ran only when the draft declared a B_lag contrast or
primary.json carried a non-empty b_lag_subset (declared.py:130-131); an output whose rows carry B_lag / mid_lag with an emptied
b_lag_subset and an undeclared B_lag released with no L.* check, even with no_prior_tick_for_b_lag off by one. The landed
producer ALWAYS emits b_lag_subset (baseline_four_arm.py:123), so that shape is a producer defect to audit. RULING: the L checks
also trigger when any paired row carries the b_lag_subset key or summary.json carries no_prior_tick_for_b_lag; an emptied
subset with lag rows present is L.subset FAIL by name (b_lag_subset_empty); one test pins the construct. (f) DECLARED D
CONTRASTS ARE CRITICAL AFTER S405: a declared D-minus-C the producer does not emit reported D.contrast_d_minus_c NOT_AUDITABLE
producer_field_absent and still released (declared.py:85 leaves D pairs out of the declared check; neither D check is
critical). S405 landed (the draft at :305 says 'no producer gap'), so an absent D field is a producer defect. RULING: when the
draft declares D-minus-C (the runbook's a1 text does), D.contrast_d_minus_c and D.scored_keys are CRITICAL and their absence
refuses release with reason producer_field_absent; AMENDMENTS 3 and 5(c) are superseded on this point. (g) NAMED REASONS: a
reversed secondary ('B-minus-C'), a missing or ambiguous PRIMARY line, a primary repeated among the secondaries, and an
emptied b_lag_subset each refuse under their own named reason, never the generic 'missing, malformed or inconsistent
evidence'. NOTES: the S382 r1 draft on master still declares C-minus-A (P.primary correctly FAILs against the landed producer
until the runbook's amendments are pasted); a producer comparison named 'C-minus-A' would collide with C_brier in normalize --
not reachable today (the producer hard-codes C-minus-B), named in NOT VERIFIED.

AMENDMENT 9 (2026-09-23 18:3xZ; binding; from round 7 on fix 1i -- Opus tier 1 ACCEPT WITH CORRECTIONS, Opus tier 2 ACCEPT WITH
CORRECTIONS; no blocker). Both tiers sealed the runbook's a1 + a2 + b2 text over the r1 draft in memory and reproduced primary
(C, B), secondaries {(C, A), (B, A), (D, A), (D, C), (C, B_lag), (B, B_lag)} and release True on the S417-shaped construct; the
PRIMARY-METRIC disagreement, the repeated primary, the removed STANDING CONTROL paragraph (L checks still run), the declared-D
producer_field_absent refusal of release, the emptied b_lag_subset, the no_prior off-by-one, the LATENCY-EXPLAINED label, order
independence, 195 tests, 9 PASS preflight and the byte-identical S417 producer files. CORRECTIONS RULED (fix 1j): (a) A REVERSED
B_lag SECONDARY REFUSES BY NAME: a declared 'Blag-minus-B' (parsed (B_lag, B)) escapes the reversal test at declared.py:118-120
(which reads only saved['comparisons'], holding no B_lag cell) and reaches L.subset's generic 'missing, malformed or
inconsistent evidence'; release is refused (fails closed) but under the wrong reason. RULING: subset() refuses
secondary_contrast_reversed when any wanted pair is absent from expected_pairs while its reverse is present, before the generic
require; one test asserts the reason on the lag construct. (b) A SECONDARY DECLARED TWICE REFUSES BY NAME: a second harmless
prose line ('B-minus-A and D-minus-C are secondary.') or a repeated token in a declaring paragraph trips the generic
require(len(explicit) == len(set(explicit))) at declared.py:70, turning P.inputs FAIL and every P./D. check into
'prerequisite evidence unavailable' (the silent-whole-output refusal shape). RULING: a repeated secondary token is refused
secondary_repeated (named, one test); the sealed runbook text does not trigger it (both tiers verified) and stays the
reference construct. (c) The memo's NOT VERIFIED section names the UNAMENDED r1 draft: on master the draft still declares
C-minus-A, so P.primary FAILs until runbook step B2 pastes a1 / a2 / b2 -- the auditor is correct to refuse until then.
(d) Memo line 99 ('the landed producer still declares period-first C-minus-A') is marked historical (the landed
nba_four_arm_trial.py:81 emits period-first C-minus-B since S417). NOTES kept as wording: the runbook's a1 / a2 / b2 blocks must
be pasted at column 0 (an indented a1 refuses primary_line_missing by name; indented a2 / b2 silently skip the PRIMARY METRIC
cross-check and drop the B_lag secondaries while release still holds through the L checks) -- the orchestrator adds 'at column
0' to runbook step B2 (a runbook edit, outside this row); every contrast token in the PRIMARY paragraph is a declared secondary,
prose included (fails closed on a reversed prose token -- the draft author is told); the DEMOTED-TO-SECONDARY step only feeds
repeated-primary detection. No other file changes; the checks module stays at 300 lines and the memo at or under 300.

AMENDMENT 10 (2026-09-23 19:0xZ; binding; from round 8 on fix 1j -- Opus tier 1 ACCEPT, Opus tier 2 ACCEPT WITH CORRECTIONS; no
blocker). Both tiers sealed the runbook text in memory again (primary (C, B), the six secondaries, release True) and reproduced
AMENDMENT 9 (a)-(d) as closed with 198 tests. TWO CORRECTIONS, RULED (fix 1k): (a) AN INDENTED DECLARATION LINE REFUSES BY
NAME: an indented a1 already refuses primary_line_missing, but an indented a2 silently skips the PRIMARY METRIC cross-check and
an indented b2 silently drops the two B_lag secondaries -- and with a producer that emits NO lag fields, indented b2 means no L
check runs and release is True where column-0 b2 gives L.inventory / L.subset NOT_AUDITABLE producer_arm_absent and release
False (tier 2's construct). RULING: any line whose stripped text starts with 'PRIMARY:', 'PRIMARY METRIC:' or 'STANDING CONTROL'
but whose raw text does not (leading whitespace) is refused declaration_line_indented, one test per line kind; the memo states
what an indented a2 / b2 would otherwise change. (b) THE CONTRAST TOKEN NEEDS A LEADING WORD BOUNDARY: 'BLAG-minus-B' parses as
('G', 'B') (refused, but as producer_arm_absent for arm G, not by the reversal name) and 'C-minus-BLAG' is dropped silently.
RULING: a leading \b on the token pattern (declared.py:33, 86); 'BLAG-minus-B' and 'C-minus-BLAG' then refuse by a name
(secondary_contrast_reversed for the former; an unknown arm token refuses arm_token_unknown for the latter -- never dropped);
tests for both spellings; 'Blag' and 'B_lag' keep normalizing to B_lag. NOTES kept as memo wording: the generic reasons on the
no_prior off-by-one and the popped b_lag_subset stay (AMENDMENT 8(e) permits them); a RuntimeError inside a check escapes
audit() and crashes -- the report is never written and release is never True; a stale earlier --audit-out file survives a
crash, so the runbook's operator deletes it before the run (a runbook note, outside this row); memo 298 -> at most 300 lines.
