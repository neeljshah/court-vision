GAP S161 | sport all | worktree a10 | log cx_s161_neff_requote_archive
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): the S158 memo (docs/evidence/harness/S158_neff_audit_2026-09-04.md) enumerates 61 published
n_eff readouts; 45 could not be re-quoted because their per-unit series live under data/cache/eval_gate/ (never
copied under docs/evidence). data/ is a read-only junction in this worktree. Measure: for each of the 45, does its
source path exist locally today (yes/no, size, mtime)? Report the count reached, not intended.
LIMIT (step 1): a series that no longer exists is LOST -- record the last date it was cited and stop for that row.
No local load over ~300 MB: read per-unit tables one file at a time; never load a whole store.
CHANGE (step 2): create docs/evidence/harness/neff_requote_2026-09-04/ holding, per readout: the per-unit table
copied verbatim when it is under 2 MB, otherwise its sha256 + row count + column list + the re-quoted n_eff; a
manifest.csv (readout id, source path, exists, bytes, sha256, n_ticks, n_games, rho, n_eff_published,
n_eff_requoted, byte_identical, note). Append each row as it finishes so a kill leaves an honest partial record;
assert rows == 45 at the end. No module changes; scripts/platformkit/ingame/gap_effective_n.py is read-only here.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = readouts with a durable artifact under docs/evidence (copied table or sha256 record) / 45
  before        = 0 / 45 durable
  bar           = 45 / 45 accounted (each either durable-and-requoted, byte-identical or honestly re-labelled
                  with the delta, or LOST with its last-seen date); 0 fabricated values; no verdict moves
  n             = 45 (CONSTRUCT; the S158 enumeration is the list)
  eye check     = n/a (S-row); reproduction = the verifier picks 5 manifest rows, recomputes n_eff from the
                  copied table with effective_sample_size, and diffs the sha256 of 3 copied files
  must not move = gap_effective_n.py, every landed memo, the FWER ledger data/cache/eval_gate/backtest_fwer.jsonl
                  (absent here by design; never touched), every threshold
NON-TAUTOLOGY: all 45 rows appear in the manifest; a LOST row is a finding, never dropped.
EVIDENCE: docs/evidence/harness/S161_neff_requote_2026-09-04.md -- the manifest summary (durable / re-labelled /
LOST counts), the denominator reached, a NOT VERIFIED list. ASCII only. Calibration language only.
TEST: one new per-file test tests/platformkit/ingame/test_s161_neff_requote_manifest.py asserting the manifest has
45 rows, every row has a status, and every copied table's sha256 matches; run only that file.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
