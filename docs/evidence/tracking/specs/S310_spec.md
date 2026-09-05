GAP S310 | sport nba | worktree aXX | log cx_s310_tail_beta_offset
CONTEXT: allocated from the GPT-6 Astra research memo (orchestrator-held; NOT a lane input); all inputs below
  are tracked paths or data/ stores; verify each by printing path, rows, columns and first 3 ids.
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9; B5 NOTE.
WHERE: local preflight/test; full A scorer on pod when RSS exceeds 500 MB.
POD: ~/bin/pod_run <aN> --ship <code> --fetch <evidence> -- <cmd>; scratch /workspace/wt/<aN> only.
INPUTS: data/cache/inplay_odds/nba_checkpoints_full.parquet (465,249 rows; game_id first 401704627); the S309
  canonical provenance once landed (else print the terminal-tick census yourself); the S289/S291/S293 metric work only
  after acceptance.
PREMISE: low .01-.05 has 649 games but 29 rare-outcome games; S272 trainable-tail oracle cap=0.002534.
LIMIT: insufficient rare outcomes => publish precision limit; never relabel a global NULL as global success.
SEAL: the LANE seals a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal
  line via git show :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF
  to LF, hashes above the seal line).
CHANGE: logit(p)=offset(logit(recal_null))+shrunk beta-shape residual in fixed baseline tail states.
Fit inside chronological outer folds with nested OOF calibration; identity is exactly feasible at zero.
ACCEPTANCE RULE: metric=tail log loss primary, global Brier guard; fixed bins and epsilon=1e-15.
before=S272=-0.000036668 global Brier; no measured beta-offset uplift.
bar=tail paired 95 pct lower>0 AND global Brier lower>-0.0005; NEW conditional proposal for Fable.
sign=improvement = baseline loss minus candidate loss; positive = candidate better.
n=all eligible tail ticks/games plus full grid; >=30 games; seed=905; Holm over any bin claims.
eye check=n/a (S-row); reproduction=replay per-tick loss/selection and one train-only fit.
must not move=0.004 global bar, incumbent, prior evidence; this is a TAIL-CONDITIONAL SCREEN.
NON-TAUTOLOGY: tails selected by frozen baseline, not outcome; outside tail candidate=incumbent.
EVIDENCE: docs/evidence/harness/S310_tail_beta_offset_2026-09-04.md plus probabilities, train keys, clips and paired
  losses.
TEST: python -m pytest tests/platformkit/test_s310_tail_beta_offset.py -q -p no:cacheprovider (run only that file)
Test identity nesting, exact endpoint handling, fixed denominator and future-label perturbations.
BAN: never write data/ or docs/research/; new evidence only; no deploy, flags, registry or shared-ledger writes.
REPORT: all bins/global CI, RSS, test, NOT VERIFIED; no AHEAD without fresh charged replication; NEVER PARK.
BAN2: never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames). The memo
  ENDS with an explicit NOT VERIFIED list and states the sign convention of every delta.
