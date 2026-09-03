GAP S173 | sport all | worktree a13 | log cx_s173_neff_direct_requotes
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): S161 (landed) accounted for 45 published n_eff readouts: 22 RE-QUOTED from series, 23
RE-LABELLED from summary JSON because their named per-unit series were absent from the worktree. The orchestrator
has now COPIED every series those 23 rows cite into this worktree under data/cache/eval_gate/ (same relative
paths; the FWER ledger stays absent by design). Measure first: for each of the 23 rows in
docs/evidence/harness/neff_requote_2026-09-04/manifest.csv with status RE-LABELLED, does its source_path exist
here now (count present / 23)?
LIMIT (step 1): a row whose series is still absent stays RE-LABELLED with the path named.
CHANGE (step 2): for every present series, re-quote n_eff DIRECTLY with
scripts/platformkit/ingame/gap_effective_n.effective_sample_size using the tick-selection rule the published
readout used (state it per row; the informative rule is tick_informative.flag_ticks per game, eps 1e-9 + dup rule),
read ONE series at a time and never a whole store over ~300 MB (chunk if needed), update the row to RE-QUOTED with
byte_identical or the honest delta, copy the per-unit table when under 2 MB else record per-file sha256 + row
count + columns, and append the file to source_inventory.csv with its sha256. Append-per-row; assert 45 rows at
the end; never write under data/; no module edits.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = RE-LABELLED rows converted to direct RE-QUOTED / 23
  before        = 0 / 23 (22 + 23 + 0)
  bar           = every row whose series is present converted (state the count reached); every re-quote
                  reproduces the published value or carries the honest delta; 0 fabricated; no verdict moves;
                  tests/platformkit/ingame/test_s161_neff_requote_manifest.py still passes
  n             = 23 (CONSTRUCT; the S161 manifest is the list)
  eye check     = n/a (S-row); reproduction = the verifier recomputes 5 of the converted rows from the copied
                  tables and diffs 3 sha256s
  must not move = gap_effective_n.py, the 22 already re-quoted rows, every landed memo, the FWER ledger
NON-TAUTOLOGY: all 23 rows appear with their outcome; a still-absent series is a finding, not a drop.
EVIDENCE: the updated manifest + docs/evidence/harness/S173_neff_direct_requotes_2026-09-04.md (before/after
counts, per-row rule, deltas, NOT VERIFIED list). ASCII only. Calibration language only. Never paste a
credential-shaped string.
TEST: run only tests/platformkit/ingame/test_s161_neff_requote_manifest.py.
COMMIT: explicit pathspec in the worktree (manifest, holding dir, memo), no push; never touch the register or the
ledger. Report the sha. NEVER PARK; finish with the report + SHA.
