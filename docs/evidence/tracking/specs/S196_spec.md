GAP S196 | sport all | worktree main | log cx_s196_neff_direct_requotes_main
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S173 closed at limit: in a codex worktree the per-unit series that 19 of the 23 RE-LABELLED n_eff rows
cite are absent by design (data/cache/eval_gate is never junctioned). This lane runs IN THE MAIN REPO
C:/Users/neelj/nba-ai-system where every series exists. RULES for a main-repo lane: create or modify files ONLY
under docs/evidence/harness/neff_requote_2026-09-04/ and the memo docs/evidence/harness/S196_neff_direct_requotes_
main_2026-09-04.md; NEVER run git add / git commit / git push (the orchestrator commits by pathspec); never write
under data/; never touch data/cache/eval_gate/backtest_fwer.jsonl; read ONE series at a time in chunks, never a
whole store over ~300 MB (the RAM guard kills large loads); no module edits.
PREMISE (step 0): for each of the 23 rows in manifest.csv with status RE-LABELLED (plus the 4 already converted
in S173 if the manifest still shows them RE-LABELLED), does its cited source_path exist here (count / 23)?
LIMIT (step 1): a row whose series is still absent stays RE-LABELLED with the path named.
CHANGE (step 2): for every present series re-quote n_eff DIRECTLY with
scripts/platformkit/ingame/gap_effective_n.effective_sample_size under the tick-selection rule the published
readout used (state it per row; informative rule = tick_informative.flag_ticks per game, eps 1e-9 + dup rule);
set status RE-QUOTED with byte_identical or the honest delta; copy the per-unit table when under 2 MB else record
per-file sha256 + row count + columns; append each new file to source_inventory.csv with its sha256; keep every
existing COPIED status untouched; append-per-row; assert 45 rows at the end.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = RE-LABELLED rows converted to direct RE-QUOTED / 23
  before        = 0 / 23 direct (S173: 4 of 23 series present in a worktree, 0 converted)
  bar           = every row whose series exists in the main repo converted (count reached stated; expect 23/23);
                  every re-quote reproduces the published value or carries the honest delta; 0 fabricated; no
                  verdict moves; existing COPIED statuses unchanged;
                  tests/platformkit/ingame/test_s161_neff_requote_manifest.py passes in the main repo
  n             = 23 (CONSTRUCT; the manifest is the list)
  eye check     = n/a (S-row); reproduction = the verifier recomputes 5 converted rows from the cited series
                  and diffs 3 sha256s
  must not move = gap_effective_n.py, the 22 originally re-quoted rows, every landed memo, the FWER ledger
NON-TAUTOLOGY: all 23 rows appear with their outcome; a still-absent series is a finding, not a drop.
EVIDENCE: the updated manifest + source_inventory + the memo (before/after counts, per-row rule, deltas,
NOT VERIFIED list). ASCII only. Calibration language only. Never paste a credential-shaped string.
TEST: run only tests/platformkit/ingame/test_s161_neff_requote_manifest.py (main repo).
REPORT: print the converted count, the list of any still-absent paths, and the test result. NO COMMIT. NEVER PARK.
