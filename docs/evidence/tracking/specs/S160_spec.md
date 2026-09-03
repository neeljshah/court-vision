GAP S160 | sport all | worktree a15 | log cx_s160_funnel_connectivity
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: the product funnel is DATA -> SIGNALS -> MODELS -> ENGINES -> PREDICTIONS -> INTELLIGENCE with the harness
(signal foundry -> eval gate -> FWER ledger -> backtest -> execution/paper -> evidence) connecting every stage. The
user wants proof that everything is CONNECTED end to end today, measured, not asserted.
PREMISE (step 0): enumerate the links and MEASURE each one read-only on this worktree (data/ is a read-only
junction; never write under it; never touch data/cache/eval_gate/backtest_fwer.jsonl, which is absent here by
design -- say so where a link needs it). Links, each = one command + its pass/fail + the number it printed:
  L1 eval-gate reference core (the eval-gate skill command: golden set + walk-forward / shin / blend / freshness /
     ledger scoreboard); L2 calibration report (calibration-report skill command) per sport; L3 cross-sport
     benchmark (cross-sport-benchmark skill command); L4 signal audit gate for one sport (signal-audit skill);
  L5 foundry: seed_queue --limit 50 into a TMP sqlite + foundry_runner --max-passes 1 --predictor real
     --sport mlb on it (FOUNDRY_PORTABLE_CORPUS=1), screens > 0, tracebacks 0; L6 results_db -> family_p_values(tier)
     -> family_bars: a construct call chain returns; L7 predict_service.produce.produce_sport("mlb") dry (status ok,
     predictions > 0); L8 the answer layer: scripts/mcp_server tools harness_health / system_health callable in
     process (import + call) and their envelope status; L9 evidence: every artifact path cited in
     docs/PUBLIC_EVIDENCE.md exists (n/n); L10 the in-game chain: tick_informative.flag_ticks on the landed MLB joined
     store -> gap_effective_n -> a CI (construct on 1 game); L11 execution/paper: the paper CLV readout (S20 module)
     on the local ledger copy returns without error. Read the skills' SKILL.md files under .claude/skills/ for the
     exact commands.
LIMIT (step 1): a link that needs the pod or the real ledger is reported NOT TESTABLE HERE with the reason,
never faked. No local load over ~300 MB (subsample and say so). Append each link's result to the table as it
finishes so a kill leaves an honest partial record; state the denominator reached; assert 11 rows at the end.
CHANGE (step 2): NO code change unless a link is broken by a trivial import/path error; then the smallest additive
fix + one per-file test, and name every reader checked. Otherwise docs only.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = links measured / 11, each with its command, exit code, the number it printed, and pass/fail
  before        = unknown (never measured end to end on one date)
  bar           = 11/11 measured (pass, fail, or NOT TESTABLE HERE with reason); 0 fabricated numbers
  n             = 11 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier re-runs any 3 links from the memo's commands verbatim
  must not move = every threshold, every landed artifact, the FWER ledger (never written), data/ (never written)
NON-TAUTOLOGY: every link above is reported; none dropped because it failed.
EVIDENCE: docs/evidence/CONNECTIVITY_2026-09-04.md (11-row table: link, command, exit, number, verdict, notes) +
a NOT VERIFIED list. ASCII only. Calibration language only (no edge/ROI words; a failing link is a finding).
TEST: one new per-file test under tests/platformkit/ops/ that asserts the CONNECTIVITY table has 11 rows and every
row carries a verdict; run only that file. Per-file tests only.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
