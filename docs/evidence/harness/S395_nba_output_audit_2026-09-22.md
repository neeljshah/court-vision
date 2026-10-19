# S395 NBA output auditor - FIX 1k - 2026-09-23

PREPARE only. AMENDMENTS 1-10 of docs/evidence/tracking/specs/S395_spec.md
and VERIFIER_CONTRACT.md sections A, B and Q govern this work.
AMENDMENT 6 is in scope following the landed S417 ruling.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h54.
All evidence below is CONSTRUCT; no real trial or corpus was run.
Only the three S395 NBA auditor modules, four test files and this memo are owned.

## Dependency and producer contracts

The unchanged landed four_arm_output_audit dependency executes its checks.
The NBA wrapper supersedes its MLB-only A.denominators check, preserving the
original status as landed.A.denominators. AMENDMENT 4(h) also supersedes the
soccer-specific attempt requirement, preserving landed.A.attempt and checking
the attempt number, charge agreement and any supplied descriptive_soccer field.
Absence of descriptive_soccer is not required for NBA and is never a refusal.

The landed nba_four_arm_trial.py writes primary.json through
trial._primary(stratified_cells(primary_predictions), primary_predictions); the runner writes
trial_summary.json. The fixture calls that actual primary transformation.
The runner writes attempt and hypothesis_hash in attempt.json; the fixture
does likewise. No runner invocation or fitting is needed to construct it.

RECONSTRUCTION_ABS_TOL = 1e-9 remains inclusive. Counts and categories are exact.
N_MIN_GAMES and verdict are imported from gate_a0_ingame_vs_market; neither
is redeclared. The independent reconstruction uses the fixed seed-13,
2000-draw stream and the unchanged maximum of 20 discarded draws.
Only N_BOOT and SEED are imported from the producer estimator module; no estimator is called.
The fixture alone imports stratified_cells and the landed primary transform.

The sealed census permits the NBA_CENSUS compact JSON line, ten CENSUS echoes,
or both with agreement. PRIMARY and ELIGIBLE game counts and SHA-256 identity
pins are read from the sealed text. S86/S58 inventories remain independent
nonnegative counts, never used to derive either population.
LF/CRLF seal normalization, charge accounting, atomic audit writing and
redaction remain inherited. Audit output carries no estimates; failed population pins list identities.

## FIX 1f - AMENDMENT 4

(a) X.exposure now requires eligible_ids == primary_scored_ids | warmup_ids.
The fixture includes g4 in PRIMARY: four scored games, five eligible games.
A repinned, internally reconstructed PRIMARY that drops g4 still refuses.
Warm-ups and overtime retain the AMENDMENT 2 population convention.

(b) Both rows files are checked for repeated (game_id, key) pairs before the
landed dependency or any row map runs. Warm-up and overtime rows are included.
A changed timestamp cannot hide a repeated key. Both insertion orders and
both files have end-to-end refusal cases.

(c) P.secondary checks the actual SECONDARY label, every game-first field
and n_leave_one_out_discarded. D.subset reconstructs the same secondary
diagnostics, including its nested SECONDARY DESCRIPTIVE game-first labels
and interval_verdict. Seeded label, count and numeric corruptions refuse.

(d) P.inputs loads trial_summary.json. P.trial_summary recursively compares
its primary copy with the audited primary artifact, including strict counts
and labels, then requires exact copy equality and primary_verdict agreement.
The source primary must independently pass reconstruction before release.
The copy cannot drift by accumulating two allowed endpoint tolerances.
Tests corrupt the summary verdict, point, count and nested label.

(e) The imported verdict rule is applied to saved interval endpoints as
well as reconstructed endpoints. A saved straddling interval refuses its
SINGLE-WINDOW or AHEAD label even when its endpoint errors are within 1e-9.

(f) C.labels recursively applies N_MIN_GAMES to labelled cells in summary,
primary and trial_summary, including enclosing cells without an interval.
A negative interval below the bar refuses even where inherited C.intervals
accepts SINGLE-WINDOW. Tests cover both positive labels and enclosing cells.

(g) Every line beginning CENSUS. must fully match the echo grammar and name
a known key. Trailing whitespace, comma-formatted numbers and unknown keys
refuse even beside a correct NBA_CENSUS line.

(h) The fixture no longer invents descriptive_soccer. Its absence releases
on the complete landed-shaped construct. The original dependency refusal
is visible under landed.A.attempt with status SUPERSEDED.

(i) Endpoint agreement is not evidence of the producer's actual random
configuration. See NOT VERIFIED below.

Historical FIX 1f reproductions are retained in the construct tests; their
validation totals are recorded below.

## FIX 1f validation (historical)

Boundary 40, exposure 84 (after 1 failed / 83 from an unsynchronized copy);
124 passed; --help 0; preflight 9 PASS, 0 FAIL.

Contract B/Q: no threshold changes, no production changes, no deployment,
no commit, no registry access, no network. Full-package test imports remain.
The prior round's reported S395_spec.md modification belonged to the caller.

## FIX 1g

Binding review: `_verdict_s395_1g.md`, findings 1-4. Finding 5 (HISTORICAL,
pre-S417): the producer then declared C-minus-A; S417 emits C-minus-B.
Base then: 3f20a461b (HEAD = master); master advanced to 871baa498 with
S393/S397 spec-only commits. No dependency source was edited or copied.

1. P.seed imports N_BOOT and SEED from baseline_four_arm_period. It reads
seed/n_boot declarations from primary.json and trial_summary.json, rejects
mismatches and partial or malformed declarations, and reports NOT_AUDITABLE
producer_seed_absent when neither artifact declares them. P.seed is outside
NBA_CRITICAL; its absence permits release but is never reported as PASS.
MAX_DISCARDED remains local because the producer has no named constant.
2. The single fixture builder calls the landed `_primary(cells, rows)`.
Normalization accepts the exact S405 secondary key set, or the exact older
set with both contrasts absent. D-minus-C is audited in secondaries.comparisons
with SECONDARY DESCRIPTIVE labels and interval_verdict, including diagnostics.
The scored key list and n_scored must match non-warm-up D-subset rows in the
period set; OT is excluded. The pre-S405 absent-field path remains a counted
NOT_AUDITABLE producer_field_absent exception, outside NBA_CRITICAL.
3. PopulationMismatch preserves sorted observed/missing/extra game identities
in the audit JSON and stdout while retaining estimate redaction. Regression
cases drop g1 or add g9 and require the appropriate identity list in both.
Missing/extra are relative to the companion row population; a digest alone
cannot reveal an identity omitted from both row artifacts.
4. Amendment 5(b) is satisfied by the single imported build_fixture/template
builder; no separate on-disk fixture exists because all artifacts are generated
once by that builder and copied by the shared saved fixture.
The exposure suite now derives corpus game IDs from the built manifest's
files, with a test proving that a manifest change changes that inventory.

Reproductions (CONSTRUCT): finding 2 called the landed `_primary` on the
shared rows; finding 3 removed g1 from primary_paired_rows.json. fix1g covers
declarations, labels, OT/warm-up exclusion, n_scored, identities, manifest.

AFTER (construct): normalize PASS; P.seed NOT_AUDITABLE producer_seed_absent;
D.scored_keys and D.contrast_d_minus_c PASS; release True; X.exposure FAIL
naming missing g1; shared template and manifest corpus g0-g4 confirmed.
The regression assertions additionally passed for matching declarations,
mismatched declarations that refuse release, and absent declarations that
remain NOT_AUDITABLE. The identity refusal now includes the missing game.

FIX 1g final validation: 18 + 40 + 84 = 142 construct tests passed;
CLI help exited 0; contract preflight 9 PASS, 0 FAIL.

## FIX 1h

Binding findings: `_verdict_s395_1h.md` BLOCKING 1 and CORRECTION 2.
S417 landed on master at d2ae4b4f3. Its producer source was read on master:
`scripts/platformkit/ingame/baseline_four_arm_period.py`,
`scripts/platformkit/ingame/nba_four_arm_trial.py`, and
`scripts/platformkit/ingame/four_arm_output_audit_checks.py`.

1. The sealed PRIMARY line and secondary declaration now supply the arms.
The output comparison must match that declaration. Absent primary arms yield
P.primary NOT_AUDITABLE, reason `producer_arm_absent` with a separate `arm` field; release refuses.
The original D_minus_C checks and d_subset.scored_keys checks remain intact.
A row-owned declared helper keeps all Python modules within 300 lines.
Exact landed keys audited: primary.brier is C_minus_B_brier, primary.logloss
is C_minus_B_logloss. Both are reconstructed from the full paired population.
The C_minus_A_brier / C_minus_A_logloss path is now SECONDARY reconstruction;
C_brier / C_logloss aliases and the duplicated C_minus_B cells are audited too.
`secondaries.b_lag_subset.comparisons` carries C_minus_Blag_brier/logloss,
B_minus_Blag_brier/logloss, C_minus_B_brier/logloss, B_brier/logloss,
C_brier/logloss, and B_lag_brier/logloss. These use b_lag_subset's own A/B/C
and B_lag rows, counts, period means, intervals and game-first diagnostics.
`summary.json.no_prior_tick_for_b_lag` counts null mid_lag over ALL rows,
including warm-up and OT; both trial-summary secondary copies are reconciled.
Parent B_lag, paired_losses.B_lag, nested membership and training counts agree.
2. This section names the landed SHA, exact producer keys and secondary role.
NOT VERIFIED remains last and explicitly names the real charged trial.

Minimal reproduction, before edits (shared construct builder, sealed draft
PRIMARY C-minus-B, projected landed runner output):
```text
BEFORE producer comparison: period-first C-minus-B
BEFORE P.inputs: FAIL missing, malformed or inconsistent evidence
BEFORE P.primary: NOT_AUDITABLE prerequisite evidence unavailable
BEFORE verdict_release: False
BEFORE FIX 1h section present: False
BEFORE landed S417 sha present: False
```
Before-fix runs: boundary 3 failed / 37 passed (duplicate primary copies),
exposure 9 failed / 75 passed (embedded game_first copy compared in normalize);
now the labelled copy is checked in P.secondary, the embedded one in P.primary.
A declared C-minus-Blag secondary with no B_lag arm yields L.inventory and
L.subset NOT_AUDITABLE producer_arm_absent (arm B_lag), no FAIL, release False.
Landed keys: comparison "period-first C-minus-B", C_minus_B_brier/logloss,
secondaries.b_lag_subset, arm + '_minus_Blag', no_prior_tick_for_b_lag.
Validation (Python 3.10.0; one file per command, `-q -p no:cacheprovider`):
fix1h 30 passed; boundary 40 passed; fix1g 18 passed; exposure 84 passed
(one moved_game_first case now asserts P.secondary FAIL). CONSTRUCT n = 172.
`--help` exited 0. Contract preflight over all eight owned files: 9 PASS, 0 FAIL, exit 0.

## FIX 1i

Binding review: `_verdict_s395_1i.md`, both tiers, and AMENDMENT 8.
The runbook was read ONLY at
C:/Users/neelj/nba-ai-system/docs/direction/nba_seal_runbook_2026-09-23.md;
its a2/b2 blocks came from nba_prereg_amendments_2026-09-22.md beside it.
All writes remain in C:/Users/neelj/nba-harness-h54.

1. Tier 1 BLOCKING 1 / amendment (a): parse the PRIMARY paragraph and
STANDING CONTROL paragraph, retaining legacy secondary declarations. Explanatory
mentions of the primary are excluded; an explicit secondary declaration of the
primary refuses. The exact a1/a2/b2 text is embedded in fix1h's regression,
inserted into the r1 draft IN MEMORY, and sealed with synthetic pins only.
The original draft and runbook are unchanged. Expected primary is (C, B);
secondaries are (C, A), (B, A), (D, A), (D, C), (C, B_lag), (B, B_lag).
2. Tier 1 CORRECTION 2 / (b): a present PRIMARY METRIC line must have exactly
one contrast matching PRIMARY; mismatches name primary_metric_line_disagrees.
3. Tier 1 CORRECTION 3 / (c): FIX 1h now states reason producer_arm_absent
with a separate arm field, exactly matching the emitted report.
4. Tier 1 NOTE 4 / (d): historical reproduction prose is condensed below the
300-line memo rail. C.latency_label recursively rejects LATENCY-EXPLAINED in
producer output; the same words in sealed interpretation prose are allowed.
5. Tier 2 C1 / (e): either paired-row b_lag_subset keys or the summary's
no_prior_tick_for_b_lag key now triggers both L checks, even without declared
lag contrasts. An empty producer subset names b_lag_subset_empty before
attempting reconstruction; missing-arm handling remains unchanged.
6. Tier 2 C2 / (f): D.contrast_d_minus_c and D.scored_keys become critical
when D-minus-C is declared. Their absent-field status remains NOT_AUDITABLE
producer_field_absent, but release is False. The undeclared legacy case remains.
7. Tier 2 N1 / (g): missing/ambiguous PRIMARY, repeated primary, reversed
secondary and empty lag subset each have fixed redacted refusal reasons.
The duplicated primary copies, independent reconstruction, populations, time
precision, seed gap and missing-arm checks confirmed correct were preserved.

BEFORE (constructs): the runbook raised the generic artifact invariant; a
disagreeing metric line was accepted; inconsistent declarations, absent D
fields, the latency label and an empty lag subset all released; fix1g had
13 failed / 21 passed and fix1h 4 failed / 31 passed.
Before, those regressions returned the generic "missing, malformed or
inconsistent evidence"; explicit primary demotion now refuses by name.
FIX 1i validation, one file per command with `-q -p no:cacheprovider`:
- fix1g: 36 passed; previously 13 failed, 21 passed.
- fix1h: 35 passed; previously 4 failed, 31 passed before the lag fix.
- Boundary: 40 passed. Exposure: 84 passed. Final total: 195 (CONSTRUCT).
- AFTER: runbook parses (C, B) + six secondaries, release True; the named
  refusals and b_lag_subset_empty hold. `--help` 0; preflight 9 PASS, 0 FAIL.

## FIX 1j - AMENDMENT 9

Binding: AMENDMENT 9 and the round-7 verdicts (opus_verify_s395_r7_out.md,
opus_critique_s395_r7_out.md). Code: declared.py plus two test files.
BEFORE (constructs): 'C-minus-A, Blag-minus-B' on the lag construct gave
L.subset FAIL with the generic reason; a second 'B-minus-A and D-minus-C are
secondary.' line, or a repeated D-minus-C token, gave ValueError artifact invariant.
(a) L.subset refuses `secondary_contrast_reversed` when a declared lag pair is
absent from the expected pairs while its reverse is present, before the
generic subset check. AFTER: L.subset FAIL secondary_contrast_reversed.
(b) A repeated secondary token refuses `secondary_repeated` (P.inputs FAIL,
named). AFTER: both inputs above give Refusal secondary_repeated. The sealed
runbook a1/a2/b2 text still parses to (C, B) + six secondaries, release True.
(c) Tests: fix1h reversed-lag case; fix1g two secondary_repeated cases.
Validation: 40 + 84 + 38 + 36 = 198 (was 195).

## FIX 1k - AMENDMENT 10

Binding: AMENDMENT 10, round-8 verdicts (opus_verify/critique_s395_r8_out.md).
BEFORE, reproduced on constructs in this session before any edit:
```text
(a) runbook, b2 indented: parses; (C, B_lag), (B, B_lag) silently dropped
(a) runbook, a2 indented with C-minus-A: parses; metric cross-check skipped
(a) lag-less producer, b2 at column 0: release False; L.inventory, L.subset
    NOT_AUDITABLE producer_arm_absent
(a) lag-less producer, b2 indented: release True; no L check runs
(b) 'BLAG-minus-B' parsed as (G, B): P.primary NOT_AUDITABLE producer_arm_absent
(b) 'C-minus-BLAG' dropped silently: release True
```
Without the fix an indented a2 skips the PRIMARY METRIC cross-check, an
indented b2 drops both B_lag secondaries, and with a lag-less producer an
indented b2 releases where column 0 refuses. Now any line whose stripped text
starts PRIMARY:, PRIMARY METRIC: or STANDING CONTROL but whose raw text does
not refuses declaration_line_indented (all three indented pastes, above).
The contrast token has a leading word boundary; a misspelled arm refuses
arm_token_unknown ('C-minus-BLAG'), or secondary_contrast_reversed when its
lag spelling reverses a producer pair ('BLAG-minus-B'). Blag / B_lag still
normalize to B_lag; the sealed runbook still parses and releases.
Crash note: a RuntimeError inside a check escapes audit(); no report is
written and release is never True, but a stale --audit-out file survives.
Validation, one file per command: boundary 40, exposure 84, fix1g 43,
fix1h 38; total 205 (was 198).

## NOT VERIFIED

- The landed producer declares neither seed nor n_boot: P.seed reports
  NOT_AUDITABLE producer_seed_absent. Matching declarations do not prove the
  random settings were used; constant populations can have identical endpoints.
- A real NBA output, historical exposure inventories, a real seal package,
  real ledger accounting, fitting, OOF validity or scored performance.
- Pre-S405 output lacks D_minus_C_<metric> and d_subset.scored_keys; those
  checks remain NOT_AUDITABLE producer_field_absent when absent; a declared
  D-minus-C now prevents release. S405 writes both; constructs audit both. Release still occurs with the
  inherited C.means NOT_AUDITABLE, explicitly unaudited in this trial memo.
- Trial-summary secondary estimates beyond the inherited summary and primary
  reconstructions are not independently reconstructed as a separate report.
- Power loss or disk exhaustion; tests inject fsync/replace failures only.
- The real S402 --pin auditor run, the real charged trial, and the seal.
- A producer comparison named C-minus-A would collide with the C_brier alias
  in normalize; the landed producer hard-codes C-minus-B.
- The UNAMENDED r1 draft: on master it still declares C-minus-A, so P.primary
  FAILs until runbook step B2 pastes a1 / a2 / b2 (at column 0) -- a correct
  refusal; only the in-memory spliced construct was audited.
- No commit, charged trial, seal publication or deployment was performed.
