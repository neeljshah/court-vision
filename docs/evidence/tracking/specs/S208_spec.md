GAP S208 | sport nba (in-game) | worktree aXX | log cx_s208_nba_phase_recal
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S88_phase_recal_2026-09-04.md section 5, verbatim: "NBA (`probe_R12_B32*`) is untouched: no S06-equivalent
leak-free partition or incumbent exists for it, so it stays an unreviewed cache artifact". That was the only reason
NBA was excluded, and S123 has landed a leak-free line-anchored NBA incumbent (foundry/ingame_incumbent_nba.py).
Per-phase recalibration is the one in-game method with a CI excluding zero (S88 MLB late|leading_big +0.031643
[0.0088, 0.0572]) and it never ran where the power is.
PREMISE (step 0): re-measure and print: the NBA corpus 465,249 ticks / 1,593 games / 2024-10-22..2026-06-13, 0 nulls
(S86); corpus_units 2024-25 (656) and 2025-26 (937); the S94 global recalibration null and its SCREEN NEGATIVE verdict
(market ECE P1|close 0.055593, P2|close 0.064157); and that foundry/ingame_incumbent_nba.py exists, default
byte-identical (S123). If falsified, STOP, FALSIFIED.
LIMIT (step 1): re-score the GLOBAL single-bucket recalibration null FIRST, with a game-clustered CI. S94 found a
global recalibration null is itself BEHIND the raw line; if the per-phase arm cannot beat it, phase conditioning
bought nothing and the verdict is CLOSED AT LIMIT. State that before any bucket table.
CHANGE (step 2): smallest additive change -- run the EXISTING S88 machinery (outer expanding game-first-date
walk-forward; the two bucket_recalibration SPECS chosen on an INNER holdout carved from outer-train dates only) on the
NBA corpus with the S123 incumbent; arms differ ONLY by the phase|margin bucketing. Additive only, nothing renamed;
helper <= 300 lines within test_loc_rail_scope.py; never write data/; no flag on; no edits in src/ kernel/ api/ intel/
scripts/team_system/; one store at a time, never > 300 MB; never touch register or ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per phase|margin bucket and pooled: Brier incumbent, Brier per-phase recal, Brier market, the
                  game-clustered delta with a 95 pct CI and n_eff, plus ECE for all three; denominator = the printed
                  scored-tick count over the printed clusters
  before        = none exists (S88 section 5); the nearest numbers are S94's global recalibration null (SCREEN
                  NEGATIVE) and S58 trial B halftime -0.006583 [-0.011503, -0.001664] BEHIND the market
  bar           = every bucket and the pooled row scored with a CI and n_eff, BH-adjusted across the enumerated family
                  at q = 0.05, the step-1 global-null comparison beside the pooled row, each bucket labelled IMPROVED
                  / NO_CHANGE / WORSE by its own CI. A pooled NO_CHANGE, or a WORSE bucket, is expected
  n             = game clusters per bucket and pooled (>= 30 pooled); print tick and cluster counts per bucket
  eye check     = n/a (S-row); reproduction = the verifier recomputes the pooled and per-bucket deltas and CIs from
                  the archived per-game paired-loss series alone
  must not move = bucket_recalibration.py SPECS and every eval_gate threshold; the S88 MLB artifact byte-identical;
                  foundry/ingame_incumbent_nba.py defaults; backtest_fwer.jsonl untouched, K unread; nothing charged
NON-TAUTOLOGY: enumerate every phase|margin bucket and report all, empty and tiny ones with their n. Reporting only
IMPROVED buckets, or pooling after dropping a WORSE one, is circular -- REJECT; a per-bucket claim without BH is a
multiple-comparison artifact.
EVIDENCE: docs/evidence/harness/S208_nba_phase_recal_2026-09-04.md -- the full bucket table, the global-null
comparison, the BH table, a NOT VERIFIED list, summary JSON and per-game series (Q9).
TEST: scripts/platformkit/ingame/test_s208_nba_phase_recal.py -- one new per-file test; run only that file.
REPORT: pooled delta and CI, the bucket table, BH survivors, test line, SHA. Commit by pathspec, no push. NEVER PARK.
