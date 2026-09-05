GAP S309 | sport nba | worktree aXX | log cx_s309_canonical_loss_audit
CONTEXT: allocated from the GPT-6 Astra research memo (orchestrator-held; NOT a lane input); all inputs below
  are tracked paths or data/ stores; verify each by printing path, rows, columns and first 3 ids.
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9; B5 NOTE.
WHERE: local read-only census, arithmetic, per-file test; full regeneration on pod if RSS exceeds 500 MB.
POD: ~/bin/pod_run <aN> --ship <code> --fetch <evidence> -- <cmd>; scratch /workspace/wt/<aN> only.
INPUTS: data/cache/inplay_odds/nba_checkpoints_full.parquet (465,249 rows; game_id first 401704627);
  data/cache/inplay_odds/nba_price_series.parquet (8,399,632 rows; event_key first KXNBAGAME-26APR26BOSPHI);
  data/domains/basketball_nba/espn_nba_game_bridge.parquet (1,299 rows); the landed S272 paired CSV
  docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv and the S280 paired archive
  docs/evidence/harness/S280_*_2026-09-04*.csv; record absolute paths, bytes and hashes.
PREMISE: A=465249/1593; P4plus clock-zero=244183; S280 tick/game deltas differ by 0.000130557.
LIMIT: without receipt/final timestamps, label terminal status UNKNOWN; preserve frozen all-tick scoring.
SEAL: the LANE seals a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal
  line via git show :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF
  to LF, hashes above the seal line).
CHANGE: additive audit sibling, canonical home-side keys and one state per tick with real game/team ids.
Replay old scores; regenerate strict-past null, retaining original bar/denominator as a separate replay.
ACCEPTANCE RULE: metric=key/provenance violations and paired Brier/log-loss replay error.
before=0 duplicate A keys, 244183 terminal-like ticks, mismatched S280 estimands; no validated live mask.
bar=0 unaccounted rows; replay error<=1e-12; fit/purge provenance exhaustive; report candidate-specific MDE.
sign=improvement = baseline loss minus candidate loss; positive = candidate better.
n=all 465249 ticks/1593 games; ratio bootstrap on game sums/counts, seed=901, 10000 replicates.
eye check=n/a (S-row); reproduction=verifier replays sums/counts and one callback fold.
must not move=0.004 bar, source stores, incumbent implementation and all prior dated evidence.
NON-TAUTOLOGY: all, positive-clock, zero-clock and unknown-status tables; no outcome-based exclusions.
EVIDENCE: docs/evidence/harness/S309_canonical_loss_audit_2026-09-04.md plus JSON, keys, folds, paired losses and
  hashes.
TEST: python -m pytest tests/platformkit/test_s309_canonical_loss_audit.py -q -p no:cacheprovider (run only that file)
Test variable cluster sizes, recycled ticks, future-label propagation and probability/side complements.
BAN: never write data/ or docs/research/; new evidence only; no deploy, flags, registry or shared-ledger writes.
REPORT: correction deltas, exclusions, RSS, test result, NOT VERIFIED; SCREEN only, no promotion; NEVER PARK.
BAN2: never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames). The memo
  ENDS with an explicit NOT VERIFIED list and states the sign convention of every delta.
