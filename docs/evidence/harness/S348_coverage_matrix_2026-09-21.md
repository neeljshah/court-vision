# S348 capture-to-scoring coverage matrix

PREPARE-ONLY. Construct validation only; no real-data census or calibration
measurement was run. The pod is OFF. No files under data/ were written.
Vocabulary follows contract Q6; automated scan required.

## Before-condition

PowerShell equivalent of the spec's grep command:
`Select-String -Path scripts/platformkit/ingame/inplay_capture_loop.py -Pattern '^DEFAULT_SPORTS|^_MODEL_SPORTS'`

Observed source lines:
```text
93:DEFAULT_SPORTS: List[str] = ["mlb", "soccer_intl", "tennis", "wnba", "npb", "kbo", "nba"]
99:_MODEL_SPORTS: Tuple[str, ...] = ("mlb", "soccer_intl", "nba")
```
`Test-Path scripts/platformkit/ingame/coverage_matrix.py` returned False before
construction. The capture/model dispatch mismatch remains the stated premise.

## Design and interpretation

The new module parses the capture constants with the standard-library AST,
without importing capture machinery. Default rows add nfl, nhl, ncaaf, ncaab.
An explicit --data-root controls source discovery; no alternate checkout is
guessed. Sources include cache/ingame, price-series parquet files, NBA full
checkpoints, the four specified book directories, trade/print/tape paths,
settlement stores, joined stores, and domain outputs. NBA domain outputs use
the basketball_nba directory. Domain outputs are checked under both the
selected data root and this module's repository root.

Shared book and trade files require a matching sport field. Trade files do
not count as book files. A source linked outside a searched tree is skipped.
JSONL and CSV stream records; parquet projects census columns in small
batches. JSON documents have a size cap; large parquet row groups and
excess distinct identifiers cause PARTIAL, never a fabricated exact count.
Pyarrow already occurs in s215_tennis_inplay_census.py in the same directory.
No full-store dataframe is constructed. All source handles are read-only.

Each input reports present, path list, file_count, distinct_games, first_date,
last_date, bytes and status. Dates are UTC calendar dates when timezone data
exists. Duplicate game identifiers within a cell count once. Identifiers are
not normalized across schemes; no join is performed. Missing identifiers
or incomplete reads make the distinct denominator null. Rows and reasons
are also retained. Empty or unreadable files remain visible as PARTIAL.
Settlement requires a non-null result field, including zero-valued outcomes.
Joined records require model_prob, market_prob and outcome in addition to
identity and date. Mixed incomplete rows keep the cell PARTIAL.

AVAILABLE means a readable, nonempty input with census identity/date fields;
PARTIAL means present but empty, incomplete, unsupported, or resource-limited;
ABSENT means no discovered source. All non-AVAILABLE classes appear in the
ordered MISSING list: state, price_series, books, prints, model, settlement,
joined. SCORABLE_NOW means all census prerequisites are AVAILABLE, and is
not a validation verdict for a model or joined corpus.

The model cell is explicitly static_dispatch_only; runtime_not_verified.
It reports the live_board.live_model_home_prob module for configured sports
when the module file exists; it never calls a predictor. Game/date fields
are null for this code artifact. A source's ticker alone is not treated as
a game identity. Such tapes can therefore be present but PARTIAL.

## Reproduction and finisher handoff

Run from C:/Users/neelj/nba-harness-h3. Keep temporary fixtures inside the
worktree and suppress Python bytecode writes:
```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/platformkit/ingame/test_coverage_matrix.py -q -p no:cacheprovider --basetemp=.s348-test-tmp
python -m scripts.platformkit.ingame.coverage_matrix --help
```
Construct cases enumerate complete versus price-only sports, all empty or
incomplete row variants, corrupt input, bounded identifiers, explicit-root
isolation, default sports, incomplete joins, settlement from state, CLI
output protections, source-byte preservation, and ASCII/Q6/LOC checks.
The hygiene test scans all three deliverables automatically.
Validation result: the per-file construct tests passed, including the
automated ASCII/Q6/LOC scan. The module --help self-check exited successfully.

Only the FINISHER runs the following command, from this worktree, after
review. The input path is supplied explicitly and the new output stays here:
```powershell
python -m scripts.platformkit.ingame.coverage_matrix --data-root C:/Users/neelj/nba-ai-system/data --out docs/evidence/harness/S348_coverage_matrix_real_2026-09-21.json
```
The builder did not run that command. The output must not already exist.

## Contract self-check

B1/B7/B8/B9: no sampled, fitted, or scored metric; constructed denominators
only. B2/B6: new files only; no renamed schema or retired callers. B3/B4:
read-only reporting, no quarantine or claims. B5: no deployment. B10/Q3:
no existing threshold changed. Q1/Q2/Q4/Q5/Q9: no scored comparison or trial.
Q6: automated vocabulary scan is part of the per-file test. Q7: CONSTRUCT
enumeration. Q8: before-condition rerun against source before construction.
No register or results record is changed in this prepare-only handoff.

NOT VERIFIED
- Real input availability, counts, date ranges, and sport coverage.
- Live predictor execution, probability availability, and model calibration.
- Settlement correctness, identity equivalence, and joined-corpus validity.
- Unrecognized storage layouts, schemas, or missing sport tags in shared files.
- Peak RSS below the specified limit on the real corpus and oversized records.
- Finisher execution, independent verifier reproduction, and landing commit.
