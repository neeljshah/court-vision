GAP S309 | sport nba | worktree a15 | log cx_s309_canonical_loss_audit
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

## VERSION 2026-09-07 (finish audit)
ABSORBS S300 and S299 (MERGED 2026-09-07; no separate dispatch). EVERY acceptance clause above is RETAINED UNCHANGED;
the clauses below are ADDED, and each absorbed check is verified SEPARATELY BEFORE either transformation.
FROM S300 -- exhaustive side accounting and venue overlap: nba_price_series.parquet row group 0 has 171,546/200,000 rows
  sharing event+venue+ts with another side. Build ONE canonical home-side probability row per venue/event/timestamp:
  filter moneyline; Polymarket side=home is canonical; for Kalshi use side == parsed home, else complement the parsed
  away side. Account EVERY excluded source row by reason in a full accounting table; keep every source column and add
  aliases only. ADDED BARS: 0 duplicate canonical keys; 1,593/1,593 Polymarket games joined; probability replay error
  <= 1e-12; cross-venue game overlap PRINTED, and that arm is CLOSED AT LIMIT below 30 games. ADDED TESTS: complements,
  duplicate timestamps, two venue namespaces.
FROM S299 -- explicit design comparison, run AFTER S293 lands (strict-past generation alone is NOT this test): score ONE
  frozen tail calibrator (the S272 one) under BOTH forward-only walk-forward AND symmetric CPCV on the same 465,249
  ticks / 1,593 games, one prediction per game-tick per design, and report paired design differences with CIs. RETAINED
  S299 before values: S272 candidate improvement -0.000037 and tail ECE change -0.000248. ADDED BARS: exact S272 replay
  to 1e-12 FIRST, else stop and report NOT REPRODUCED; the DESIGN-SENSITIVE label uses ONLY the preregistered primary
  paired Brier CI and applies when that CI EXCLUDES ZERO; tail log loss and ECE stay NAMED SECONDARY diagnostics and
  every secondary score is still published. Forward-only is the deployment headline; CPCV is the labelled robustness
  companion. No promotion; nothing charged. ADDED TEST: future blocks never enter the forward fit. Archive fold
  membership, fitted parameters and tick losses; retain the HISTORICAL replay SEPARATELY from the strict-past fits.
ORDER: S293 precedes the absorbed S299 part. Retained throughout: the frozen +0.004 bar, the source stores, the
incumbent implementation, the S272/S280 artifacts and all prior dated evidence.

## VERSION 2026-09-07b (landing note; orchestrator-authorized)
Landing note: evidence stems are 2026-09-07 / 2026-09-07b / 2026-09-07c (mapping table in the c memo,
docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c.md); the EVIDENCE line's 2026-09-04 stem was never
written by this row. The shared evaluators are driven at game-cluster grain (1,593 states) emitting one prediction
per tick (465,249), as declared in the sealed prereg and supplement. The +0.004 bar is untouched.
