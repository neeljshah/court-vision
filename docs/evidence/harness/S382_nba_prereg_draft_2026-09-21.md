# S382 NBA prereg draft memo -- 2026-09-21

DRAFT WRITTEN, UNSEALED; independent verification pending.
Artifact: docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md.
Owned files: that draft and this memo only. No module, import, fixture, test or CLI
was created under the explicit document-only override. No scoring or fitting ran.
Machine: local C:/Users/neelj/nba-harness-h42; all reads and writes stayed here.

## Binding before-condition

Command: `ls docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md`
Exit code: 1. Output (primary error quoted verbatim):

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h42\docs\evidence\ingame\S382_NBA_PREREG_DRAFT_r1_2026-09-21.md' 
because it does not exist.
```

## Sources and relied-on interfaces

Read the S382 spec first, then the S347 template and design audit. The initial
ledger search failed because rg is unavailable; Select-String recovered S377.
No REAL ROW is specified: the binding real evidence is the S377 ledger census.
No module was imported in the initial draft pass. FIX 1b calls only pure parsers
on constructed inputs. These signatures informed the original draft:

- scripts/platformkit/ingame/baseline_four_arm_features.py:
  `def sport_for(corpus: str) -> str:` and
  `def phase(features: dict, sport: str) -> str:`;
  `'nba': ('score_diff', 'quarter', 'seconds_remaining'),`;
  `for suffix in ('', '_segmented', '_segmented_r3')`.
- scripts/platformkit/ingame/baseline_four_arm_eligibility.py:
  `def select_rows(rows: list[dict], corpus: str) -> tuple[list[dict], dict]:`;
  `for field in (() if duplicate else ('market_prob', 'model_prob')):`;
  `reasons.append(f'missing_{field}')`. Missing model excludes every arm today.
- scripts/platformkit/ingame/late_game_cohorts.py:
  `def build_cohorts(pairs: Iterable[tuple[Mapping[str, object], object]]) -> dict:`;
  `errors["unsupported_sport"] += 1`. NBA is absent from STATE_CELLS.
- docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md:
  "Use fixed ridge coefficient 1e-3 including the intercept, at most 100 Newton"
  and "steps with objective backtracking, and step tolerance 1e-9; no tuning search."
  Its eight section headings are retained verbatim and in order in the draft.
- docs/evidence/harness/ASTRA_NBA_SECOND_CORPUS_AUDIT_2026-09-21.md:
  "Choose a period-stratified primary: equal weights of 1/4 across Q1-Q4";
  "Missing model excludes D's paired population only under an amended instrument."
  It also reports S58 exposure for all games; the draft discloses that limitation.
- docs/evidence/RESULTS_LEDGER_SYSTEM.md, S377 line:
  "1,593 games, 465,249 ticks, 465,249 unique keys, 0 conflicting duplicates";
  "POST-FINAL ROWS 244,183"; "5 warm-up folds and 1,570 post-warm-up games /"
  "217,758 live ticks remain." These are attributed counts, not remeasurements.
- The spec's docs/evidence/VERIFIER_CONTRACT.md is absent; its existing local
  counterpart is docs/evidence/tracking/VERIFIER_CONTRACT.md, read Q1-Q6 and B.
  Q1: "No seal, no scored claim." Q5: "TWO CORPORA FOR ANY AHEAD".

## Scope review

All ten CHANGE items are covered. S383, the eligibility amendment, S385,
manifest/census reconciliation, exposure review, MLB verdict and S379 remain
explicit sealing prerequisites. No pre-existing module was edited. Per-file
pytest and CLI-help counts are zero: neither applies to this document-only row.
Validation is limited to construct parser reproduction and document checks,
including contract preflight; no runtime amendment is claimed by this row.

## Validation

Command: `python -m scripts.platformkit.tracking.contract_preflight --paths docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md docs/evidence/harness/S382_nba_prereg_draft_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S382_spec.md`
Exit code 0; 9 PASS, 0 FAIL:

```text
PASS vocab clean over 2 files
PASS crlf no index-side CRLF over 2 file(s); 2 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 3 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

Document checks: 8/8 section headings match the template exactly and in order;
2/2 documents are ASCII, use LF, remain under 300 lines and contain no seal line.
The loc preflight checks Python only; document lengths were counted separately
with len(text.splitlines()). Per-file tests: 0; CLI help invocations: 0.
No commit was created; the two documents remain on disk for lane_commit.

## FIX 1b

The root verifier verdict has two BLOCKING findings. Local and master S382 specs
were read; neither contains an AMENDMENT block. The orchestrator's document-only
override limits changes to this draft and memo; runtime modules stay unchanged.

1. Venue-time parser amendment. Added as a named eligibility amendment and a
   named do-not-seal-until item. Both ts and close_ts must use the canonical
   parser, with four-/five-digit regression cases. Six-digit converter output
   makes the defect latent for this corpus; resolution still precedes sealing.
2. Integral NBA state amendment. Added in both locations. All three source fields
   must be finite INTEGRAL values; boolean/fractional inputs require counted
   refusals before subtraction, phase assignment or post-final filtering.
   The draft names the regression cases required from the future amendment.

Before edits, local Python 3.10.0 reproduced both findings with constructed
inputs via baseline_four_arm_features.timestamp/state_eligibility/phase and
execution.venue_time.parse_venue_time (full package imports; python -B):

```text
INPUT 2026-09-21T12:00:00.1234Z
timestamp -> ValueError: Invalid isoformat string: '2026-09-21T12:00:00.1234+00:00'
parse_venue_time -> 1789992000.1234
INPUT 2026-09-21T12:00:00.12345Z
timestamp -> ValueError: Invalid isoformat string: '2026-09-21T12:00:00.12345+00:00'
parse_venue_time -> 1789992000.12345
INPUT home_score=10 away_score=9 quarter=3.5 seconds_remaining=0
OUTPUT score_diff=1.0; reasons=[]; phase=Q3
INPUT home_score=10.5 away_score=9 quarter=4 seconds_remaining=1
OUTPUT score_diff=1.5; reasons=[]; phase=Q4
FAIL Venue-time parser amendment named in eligibility and do-not-seal list: 0 / 2
FAIL Integral NBA state amendment named in eligibility and do-not-seal list: 0 / 2
```

The document checks count each amendment once in eligibility and once in the
do-not-seal list. Runtime failures remain unresolved; a document pass cannot
stand in for the future amendment's regression tests. No test file is created
under the document-only override. FIX 1b validation results are recorded below.

```text
PASS Venue-time parser amendment named in eligibility and do-not-seal list: 2 / 2
PASS Integral NBA state amendment named in eligibility and do-not-seal list: 2 / 2
PASS section headings: 8 / 8 match template in order
PASS document ASCII/LF/line-limit/unsealed: 2 / 2
PASS memo final section: NOT VERIFIED
```

The same preflight command above passed 9/9 checks, 0 FAIL for FIX 1b.
Per-file pytest: 0; row CLI help/self-check: 0 (no module, test or CLI in this row).
Only the two owned documents changed; all verifier-confirmed content is retained.

## NOT VERIFIED

- No runtime fix or regression test; only pure-parser construct reproduction.
- No CLI, scoring route, fit or bootstrap was exercised.
- No archive, network or pod was accessed; S377 counts and hashes were not rerun.
- No runtime verification of S383, the eligibility amendment or r1 mapping fix.
- No S385 provenance clearance, exposure-identity audit or independent power result.
- No MLB trial verdict or S379 availability check; those are sealing prerequisites.
- No seal, trial charge, launch K, cross-corpus conclusion or independent verifier acceptance.
