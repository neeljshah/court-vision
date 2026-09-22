# S392 document-only build memo

Candidate disposition: REJECT untouched-validation claims on the historical
NBA corpus for A/B/C; D remains DESCRIPTIVE ONLY. Independent review is pending.
Artifact: docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md.
Spec: docs/evidence/tracking/specs/S392_spec.md; all five CHANGE items addressed.
Worktree: C:/Users/neelj/nba-harness-h51 only. No existing module was edited.

## Binding before-condition

Ran the exact command before writing: `ls docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md`.
Exit code 1. Verbatim output excerpt:

```text
ls : Cannot find path
'C:\Users\neelj\nba-harness-h51\docs\evidence\ingame\S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md' because it does not
exist.
```

The missing destination confirms the premise. Source quotes, ledger line
references, historical identity sets and document byte sizes are in the artifact.
The prompt's docs/evidence/VERIFIER_CONTRACT.md is absent; the binding contract
read was docs/evidence/tracking/VERIFIER_CONTRACT.md, as routed by harness-lane.
No imported API signatures or real-row fixture apply to this document-only row.

## Validation

Contract preflight: 9 PASS, 0 FAIL, exit 0 on the two owned documents.
Checks: vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact and row_duplication. These mechanical checks do not establish
historical independence or replace an independent verifier.
Command (Python bytecode writes disabled):

```text
python -B -m scripts.platformkit.tracking.contract_preflight --paths docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md docs/evidence/harness/S392_nba_exposure_disposition_2026-09-22.md --base master --spec docs/evidence/tracking/specs/S392_spec.md
```

Both files passed ASCII and LF-only checks. Length uses len(text.splitlines());
the disposition is under 250 lines and the memo under 300.
No modules, tests or CLIs were created; the orchestrator's document-only
instruction excludes tests and CLI-help runs. Test pass count: 0 (none run).
No prereg draft, ledger, registry, archive or feature flag was changed.

## FIX 1b

Binding finding 1, BLOCKING: incomplete exposure inventory. Added individual
S247, S261, S308, S317, S322 and S328 entries with exact ledger excerpts,
game/tick/state identities, fitting/selection and current reliance or NOT TRACED.
S247's zero qualifying simulator population does not erase its premise Brier
reads; S308's rejection does not erase its full-source outcome access. S317
feeds S322's scored stop decision; direct adoption by S382 remains NOT TRACED.
The incomplete FIX 1b ledger/memo search added five more scoring identities (S44, S87,
S225, S267, S305) and three documentary rereads (S71, S120, S56), each separately
quoted with identity scope and reliance limits: 14 additions in total.
S87 reuses H/all U; the new reads supply no independent population. Re-deriving
the disposition retains option (iii) through the documented S58/S86 lineage;
the new stop/repair/publication decisions have no traced direct S382 adoption.
Finding 2 is NOTE only: no correction requested. Its accepted reasoning,
Arm D evidence requirements, prereg paragraphs and MLB interpretation are retained.
The worktree spec and `git show master:docs/evidence/tracking/specs/S392_spec.md`
agree; neither contains an AMENDMENT block. Only the two owned documents change.

Minimal reproduction, before and after (PowerShell text membership, no archive):

```powershell
$inventory = Get-Content -Raw docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md
'S261','S308','S317','S322','S328','S247' | ForEach-Object {
  '{0}: in_inventory={1}' -f $_, $inventory.Contains($_)
}
```

```text
BEFORE
S261: in_inventory=False
S308: in_inventory=False
S317: in_inventory=False
S322: in_inventory=False
S328: in_inventory=False
S247: in_inventory=False
AFTER
S261: in_inventory=True
S308: in_inventory=True
S317: in_inventory=True
S322: in_inventory=True
S328: in_inventory=True
S247: in_inventory=True
```

Six of six presence checks now pass; exact source excerpts and identity details
were checked by document reading. No regression-test module is appropriate:
the final orchestrator instruction expressly requires documents only and only
contract preflight. This text recipe preserves the verifier's reproduction.

Additional documents read for the six named omissions (paths relative to this
worktree; byte sizes of text inputs, resolution not applicable):

| Evidence input | Bytes |
|---|---:|
| docs/evidence/harness/S247_nba_sim_engine_vs_line_v2_2026-09-04.md | 11708 |
| docs/evidence/harness/S261_ingame_headline_rederive_v2_2026-09-04.md | 5938 |
| docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_2026-09-04.md | 4845 |
| docs/evidence/harness/S261_ingame_headline_rederive_v2_prereg_2026-09-04.md | 2857 |
| docs/evidence/harness/S211_ingame_headline_rederive_2026-09-04.md | 1510 |
| docs/evidence/harness/S308_band_functional_validity_attempt2_2026-09-08.md | 15416 |
| docs/evidence/harness/S317_series_schema_2026-09-08.md | 5535 |
| docs/evidence/harness/S322_sim_diagnostics_2026-09-08.md | 11850 |
| docs/evidence/harness/S328_asof_join_falsification_2026-09-08.md | 4736 |

Additional census sources read by the read-only census agent, same path base:

| Evidence input | Bytes |
|---|---:|
| docs/evidence/harness/S44_gate_corpus_event_date_2026-09-03.md | 6876 |
| docs/evidence/harness/S87_tick_informative_2026-09-03.md | 8363 |
| docs/evidence/harness/S225_ingame_intel_conditioning_rerun_2026-09-04.md | 6026 |
| docs/evidence/harness/S267_key_explicit_consumers_2026-09-04.md | 2692 |
| docs/evidence/harness/S305_master_failing_tests_repair_2026-09-04.md | 3569 |
| docs/evidence/harness/S71_answer_layer_fixes_2026-09-03.md | 8377 |
| docs/evidence/SIGNAL_INVENTORY_2026-09-03.md | 53836 |
| docs/evidence/harness/S56_public_numbers_2026-09-03.md | 6053 |
| docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04.md | 6705 |

The FIX 1b search excluded other-sport S43/S195/S206/S330, synthetic S301,
snapshot-only S255, schema/count censuses S323/S338/S348/S377 and S383's explicit
absence of an NBA score. This is a document census, not a per-game archive join.

FIX 1b validation: contract preflight 9 PASS, 0 FAIL, exit 0; all 14 added
identity rows present. Both documents are ASCII and LF-only; disposition 243
lines (under 250). Test pass count 0 (none run, document-only override).

## FIX 1c

Finding 1, BLOCKING: eight outcome-scoring identities were missing. Added
S132, S202, S205, S245, S248, S275, S284 and S297 individually to the disposition,
with contiguous ledger excerpts, populations, fitting/selection and reliance
or NOT TRACED. S297 L557 records sealing; L558 carries the scored result.
The earlier completeness wording above is corrected: FIX 1b was incomplete.
Findings 2 and 3 are NOTE only. No substantive correction or regression test
was requested; the document-only spec and orchestrator override generic module,
pytest and CLI-help instructions. No owned runtime module exists for this row.
Worktree and master specs agree and contain no AMENDMENT block.

Exact-ID minimal reproduction, run before editing and repeated after:

```powershell
$ids='S132','S202','S205','S245','S248','S275','S284','S297'
$inventory=Get-Content -Raw docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md
foreach ($id in $ids) {
 $hits=Select-String -Path docs/evidence/RESULTS_LEDGER_SYSTEM.md -Pattern ('\| '+$id+'(?:\+S\d+)? \|')
 '{0} inventory={1} ledger_line={2}' -f $id,([regex]::IsMatch($inventory,'\b'+$id+'\b')),$hits[0].LineNumber
}
```

```text
BEFORE
S132 inventory=False ledger_line=322
S202 inventory=False ledger_line=436
S205 inventory=False ledger_line=452
S245 inventory=False ledger_line=488
S248 inventory=False ledger_line=485
S275 inventory=False ledger_line=512
S284 inventory=False ledger_line=518
S297 inventory=False ledger_line=557
AFTER
S132 inventory=True ledger_line=322
S202 inventory=True ledger_line=436
S205 inventory=True ledger_line=452
S245 inventory=True ledger_line=488
S248 inventory=True ledger_line=485
S275 inventory=True ledger_line=512
S284 inventory=True ledger_line=518
S297 inventory=True ledger_line=557
```

The first lookup incorrectly assumed pipe-prefixed ledger rows and returned
empty line numbers; the corrected recipe above reproduces all verifier lines.

Whole-ledger grep (PowerShell Select-String; rg is unavailable), local text only:

```powershell
$hits = @(Select-String -Path docs/evidence/RESULTS_LEDGER_SYSTEM.md -Pattern '\bNBA\b' | Where-Object { $_.Line -match 'Brier|\bECE\b|log[-_ ]?loss|coverage|calibrat' })
'whole_ledger_hits={0}' -f $hits.Count
$hits | ForEach-Object { '{0}: {1}' -f $_.LineNumber,$_.Line }
$hits = @(Select-String -Path docs/evidence/RESULTS_LEDGER_SYSTEM.md -Pattern 'Brier|\bECE\b|log[-_ ]?loss|coverage|calibrat')
'metric_only_hits={0}' -f $hits.Count
```

Results: whole_ledger_hits=121; metric_only_hits=272. Counts are matching
ledger lines, not unique identities or scored populations. Both searches read
the entire ledger, with no head slice. The second count removes the NBA-word
filter so terse cross-sport lines remain discoverable; it is a search count,
not a claim that all 272 lines scored NBA outcomes. Exact-ID lookups supplement
the lexical search for the eight omissions. For example, S202 lacks an NBA
label; S245's CRPS is outside the scoring-term set.
Neither lexical count establishes exhaustive historical outcome/reliance tracing.

The 121-hit review also found S128/S129 (L331: shared 800-row NBA screen,
32 comparisons) and S130 (L316: archived halftime CI reproduction on all H).
Added both quoted entries with fitting/selection and reliance limits. These
are three additional identities, not independent populations. S134/S135 on
the same ledger line are alias/lease controls, not separate outcome scores.
Remaining unmatched hits: operational/schema/count controls S46/S19/S21b/S60/
S54/S69/S77/S89/S91/S95/S141/S146/S140/S153/S182/S207/S262/S360/S363;
other-sport scoring with no NBA scoring established S22/S53/S16/S80/S82/S104/
S81/S121; S16b reports pass-through constructs and nothing scored.
The disposition's accepted sections 2 onward retain their pre-fix text hash:
913e16cb24bf2f02d1d19fd51705cd47f9ce3124ffa72ab746bdd252cb7d813d.
Ledger bytes at this search hash to SHA-256:
c8d7c8e0821db6b016fd80a70463b82df4377ecf00ccc33c9e6fcb48e48348c7.

Additional text inputs (worktree-relative paths; bytes; resolution n/a):

| Evidence input | Bytes |
|---|---:|
| _verdict_s392_1c.md | 2805 |
| docs/evidence/RESULTS_LEDGER_SYSTEM.md | 793873 |
| docs/evidence/harness/S202_two_way_neff_2026-09-04.md | 5617 |
| docs/evidence/harness/S205_calib_bakeoff_2026-09-04.md | 8029 |
| docs/evidence/harness/S245_ingame_live_boxscore_update_2026-09-04.md | 12600 |
| docs/evidence/harness/S248_nba_fatigue_conditioned_v2_2026-09-04.md | 5595 |
| docs/evidence/harness/S275_key_explicit_consumers_v2_2026-09-04.md | 4913 |
| docs/evidence/harness/S275_key_explicit_consumers_v2_2026-09-04_attempt2.md | 5101 |
| docs/evidence/harness/S284_orderflow_traded_2026-09-04.md | 6388 |
| docs/evidence/harness/S297_minutes_dnp_distribution_2026-09-04.md | 5926 |
| docs/evidence/harness/S297_minutes_dnp_distribution_2026-09-07_prereg.md | 3669 |
| docs/evidence/harness/S128_S129_asof_supply_leaks_2026-09-03.md | 15217 |
| docs/evidence/harness/S134_S135_S130_redteam2_fixes_db_alias_ticks_2026-09-03.md | 13483 |

FIX 1c documentary checks: minimal reproduction 8/8 present; all 11 added
identities present; all 10 new table entries' quotes match their cited ledger
lines. Accepted sections unchanged: 1/1 hash check. Both files pass ASCII,
LF-only, line limit, final NOT VERIFIED and no seal-assignment checks (2/2).
Disposition: 249 lines, below 250. Runtime tests: 0 run, document-only scope;
no row CLI/self-check exists. No regression-test file was requested by verdict.
FIX 1c contract preflight: 9 PASS / 0 FAIL, exit 0, using the exact two-path
command in Validation above; the verifier verdict file is excluded.

## NOT VERIFIED

- No test exercised any runtime path; no tests or CLI-help commands were run.
- Historical metrics, census, per-game memberships and input archive hashes were
  not reproduced; only documentary evidence was read.
- Parameter authoring, unseen decision history, model/archive vintage and receipt
  remain unknown. No independent verifier has accepted this candidate.
- No fresh scoring, network, pod, seal, charge or commit was performed.
