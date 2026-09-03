GAP S166 | sport all | worktree a18 | log cx_s166_verifier_housekeeping
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): four small verifier findings from 2026-09-04 landings are open, each measurable in a minute:
  (a) docs/evidence/harness/S36_repro_2026-09-04.py still asserts that the legacy tick_date mode RAISES on the
      midnight-spanning corpus; since the S36 correction (3998d5a46) it counts self-leak instead -- run the
      script's assertion path in dry form or read it: quote the stale assert line;
  (b) the register row S36 quotes 'shipped' Briers 0.207033 / 0.252261 that master's default mode does not
      return today (0.206629024102877 / 0.251859443230625, S36 re-verifier) -- quote the memo lines;
  (c) scripts/platformkit/ingame/s90_microstructure_screen.py's default OUT_DIR is data/cache/eval_gate, so the
      memo's reproduction command writes under data/ although the memo says read-only -- quote the line;
  (d) scripts/platformkit/ingame/ingame_baseline_lock.py:133 returns {"n_games": 0, "n_eff": 0.0} on an empty
      pair set, a second unguarded shape of the effective_sample_size dict (now with n_eff_bound_ok) -- quote it.
LIMIT (step 1): n/a (CONSTRUCT, 4 items).
CHANGE (step 2): (a) update the repro script to assert the counted self_leak_pct (52.86) instead of a raise and
re-run it to a scratch path; (b) add a one-line NOTE in the S36 memo section 2 giving master's actual default-mode
values beside the register's numbers (docs only; the register itself is orchestrator-only -- do not edit it);
(c) make the S90 memo's reproduction command pass --out-dir <scratch> and say so; (d) route the fallback through
effective_sample_size's own empty-input return (or add n_eff_bound_ok: True to the fallback) so both shapes agree,
with one construct test. Nothing else.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = items fixed / 4, each with a before quote and an after quote
  before        = 0 / 4
  bar           = 4 / 4; S36 repro prints e4 0.206785778212713 / e2 0.254350980569173 and self_leak_pct 52.86
                  in a scratch run; S90 command carries --out-dir; ingame_baseline_lock test passes
  n             = 4 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier re-runs the S36 repro to scratch and the one new test
  must not move = every Brier, every threshold, the register file, the FWER ledger, data/ (never written)
NON-TAUTOLOGY: all four items reported even if one cannot be fixed (then say why).
EVIDENCE: docs/evidence/harness/S166_verifier_housekeeping_2026-09-04.md -- before/after per item, NOT VERIFIED
list. ASCII only. Calibration language only.
TEST: one new per-file test for (d) under tests/platformkit/ingame/; run only it plus test_ingame_baseline_lock.py.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
