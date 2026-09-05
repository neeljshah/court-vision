GAP S308 | sport nba | worktree aXX | log cx_s308_band_functional_validity
CONTEXT: allocated from the GPT-6 Astra research memo (orchestrator-held; NOT a lane input); all inputs below
  are tracked paths or data/ stores; verify each by printing path, rows, columns and first 3 ids.
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9; B5 NOTE.
WHERE: local source audit/test; full nested refit on pod; coordinate as an amendment to S307.
POD: ~/bin/pod_run <aN> --ship <code> --fetch <evidence> -- <cmd>; scratch /workspace/wt/<aN> only.
INPUTS: data/cache/inplay_odds/nba_checkpoints_full.parquet (465,249 rows; game_id first 401704627); the landed S294
  memo docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_2026-09-04.md, its prereg, and
  scripts/platformkit/eval_gate/s276_incumbent_conformal_band_full_attempt2.py; replay the baseline unchanged.
PREMISE: S294 ALL is grouped coverage=1.0; ladder_base, not recal_null; test nested label dependencies.
LIMIT: absent nested independence or comparable groups => no conformal guarantee; report diagnostic only.
SEAL: the LANE seals a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal
  line via git show :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF
  to LF, hashes above the seal line).
CHANGE: fit/calibrate/evaluate disjoint game blocks; calibration OOF models exclude the outer test fold.
Keep six S86 blocks for historical replay; strict-past companion for deployment-oriented interpretation.
ACCEPTANCE RULE: metric=group-frequency interval score, coverage and width at 0.80/0.90.
before=S294 ALL half-widths=0.031114796/0.019952038 at 0.90/0.80; not individual outcome intervals.
bar=0 outer-label dependencies; report S307 frozen coverage/width bars unchanged, including failures.
sign=improvement = baseline loss minus candidate loss; positive = candidate better.
n=465249 ticks/1593 games in replay; >=30 games/cell; publish calibration/test group sizes.
eye check=n/a (S-row); reproduction=one nested fold plus group membership and interval-score sums.
must not move=S294/S307 bytes, 400-tick rail or 0.004 global Brier bar.
NON-TAUTOLOGY: equal group construction in calibration/test; report phase and ALL separately.
EVIDENCE: docs/evidence/harness/S308_band_functional_validity_2026-09-04.md plus memberships, train dependencies and
  intervals.
TEST: python -m pytest tests/platformkit/test_s308_band_functional_validity.py -q -p no:cacheprovider (run only that file)
Test changing an outer-test outcome cannot alter calibration residuals, widths or fitted predictions.
BAN: never write data/ or docs/research/; new evidence only; no deploy, flags, registry or shared-ledger writes.
REPORT: validity result, every coverage/width/score, RSS, test, NOT VERIFIED; SCREEN only; NEVER PARK.
BAN2: never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames). The memo
  ENDS with an explicit NOT VERIFIED list and states the sign convention of every delta.
