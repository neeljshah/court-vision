GAP S224 | sport nba (in-game) | worktree a13 | log cx_s224_ingame_tail_calibration
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: the in-game work is all pooled Brier; no lane has reported calibration INSIDE the tail states the product is
asked about. Measured 2026-09-04 on nba_checkpoints_full.parquet (465,249 ticks / 1,593 games): the trailing-side cell
market_prob <= 0.10 holds 136,809 ticks / 775 games with realized outcome_home_win 0.006652; the two-sided extreme
cell (<= 0.10 or >= 0.90) holds 308,756 ticks / 1,590 games. Neither cell has a reliability table, an ECE or a power
statement. S210 audits EXISTING screens for power; this row prices cells never scored at all.
PREMISE (step 0): reproduce the two cell counts and the 0.006652 rate from the parquet, and report the mirror
(market_prob >= 0.90) side through the same code path. If either count is not reproduced, that is the finding.
LIMIT (step 1): compute the 80 pct-power minimum detectable Brier delta per bin under game clustering. If every bin
MDE exceeds 0.004 the tail is UNMEASURABLE at the frozen bar today -- report CLOSED AT LIMIT and fit no arm.
CHANGE (step 2): additive only -- a new module under scripts/platformkit/ emitting, per 1 pct bin over [0, 0.10] and
[0.90, 1.00], the count, realized rate, market Brier and ECE, the S123 leak-free incumbent's Brier, n_eff under game
clustering, and the MDE. Optionally join data/intelligence/garbage_time_segments.parquet (1,226,606 rows, game_id +
period + game_clock_sec) to split decided-game ticks from live comeback ticks; if the id spaces do not join, report
that and run without it.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-bin reliability over the 20 frozen 1 pct bins, on checkpoint ticks
  before        = no reliability table exists for either cell; pooled counts 136,809 / 775 and 308,756 / 1,590
  bar           = both tails reported symmetrically with all 20 bins present (a zero-count bin printed as zero),
      market and incumbent Brier plus n-weighted ECE per bin, n_eff and the 80 pct-power MDE per bin, 0 ticks dropped
      from the 465,249 denominator without a printed reason, each bin labelled SCORABLE or UNDERPOWERED
  n             = 465,249 ticks / 1,593 game clusters
  eye check     = n/a (S-row); reproduction = the verifier re-runs the module and diffs the per-bin CSV
  must not move = the +0.004 bar; the checkpoint parquet; every threshold; the FWER ledger
NON-TAUTOLOGY: every tick is assigned to exactly one bin or to the explicit middle band; no game is excluded for being
lopsided, since that is the state under study.
EVIDENCE: docs/evidence/harness/S224_ingame_tail_calibration_2026-09-04.md plus the per-bin CSV and summary JSON.
ASCII only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (bin edges frozen; a synthetic corpus reproduces its own rates), run only that file.
REPORT: the two tail tables, the MDE column, how many bins are SCORABLE, the test line, SHA. Commit by pathspec, no
push. NEVER PARK.
