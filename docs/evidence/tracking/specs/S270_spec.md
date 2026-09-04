GAP S270 | sport all (in-game) | worktree a14 | log cx_s270_ingame_power_feasibility
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: successor to S259 (in-game power audit v5, sha d7cbf4e34, committed in worktree a16 and reachable from
  this repo's object store via `git show d7cbf4e34:docs/evidence/harness/S259_ingame_power_audit_v5_2026-09-04.md`;
  NOT present in this repo's working tree -- verified). It names 8 UNDERPOWERED screens by MDE80 (the 80 pct-power
  minimum detectable Brier delta, vs the frozen 0.004 bar), with each row's n_eff: S06 MDE 0.060079 (n_eff
  296.611), S117 0.402243 (14.682), S119 0.007536 (214.827), S58_trial1 0.034040 (467.273), S79 0.006840
  (800.000), S80 0.042910 (79.252), S82 0.007536 (214.827, same underlying data as S119), S84 0.004948 (894.356).
PREMISE (step 0, INFORMATIONAL): re-read the v5 table via git show; print all 8 UNDERPOWERED rows' n_ticks,
  clusters, n_eff, and MDE80 verbatim against the values above; confirm none has since been re-screened past S259
  by grepping the register for a later S-id citing the same memo stem.
CHANGE (step 1): additive script under scripts/platformkit/ that, for each of the 8 UNDERPOWERED screens, computes
  required_n_eff = current_n_eff * (current_MDE80 / 0.004)^2 (the closed-form 80 pct-power scaling S224 used),
  then counts AVAILABLE game clusters for every named candidate pool via one-column (game_id only) streaming reads
  of stores already on disk (more seasons/prefixes of the same corpus, both NBA and WNBA where the screen's sport
  allows, more ticks per game where clustering not tick count is the binding constraint) -- enumerating every pool
  by exact store path and byte size, never estimating. Produces a ranked feasibility table (screen, required_n_eff,
  best available pool + its clusters, feasible yes/no). For the single most feasible screen (available >=
  required, else smallest shortfall), seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED
  bytes above the seal line via git show :<path>, verified with git show HEAD:<path>) and re-run that screen's
  own scorer unchanged on the enlarged pool through walk_forward or cpcv_evaluate under
  scripts/platformkit/eval_gate/ with purge and a symmetric nonzero embargo.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = feasibility-table coverage (8 of 8 UNDERPOWERED screens enumerated) plus the re-screened
                  screen's new MDE80 and Brier-delta result
  before        = the 8 S259 v5 MDE80s quoted above; no pooling feasibility has ever been computed for any of them
  bar           = all 8 rows present with required_n_eff, available clusters, and feasible yes/no; the re-screen
                  reports a new MDE80 and result on the enlarged pool (NULL or BEHIND is a valid success)
  n             = 8 (CONSTRUCT, exhaustive over S259 v5's UNDERPOWERED rows) for the table; the re-screen's own
                  sampled n is printed and >= 30 game clusters
  eye check     = n/a (S-row); reproduction = verifier reruns the pool-counting script and the sealed re-screen
  must not move = the +0.004 bar, S259's v5 memo/JSON, the re-screened screen's own frozen defaults; nothing else
                  under docs/evidence/harness/ from S259 is rewritten (new dated filenames only)
NON-TAUTOLOGY: a pool is "feasible" only when its clusters are counted from a real store, never assumed; a screen
  with no larger pool anywhere on disk is reported infeasible, not silently dropped from the table.
EVIDENCE: docs/evidence/harness/S270_ingame_power_feasibility_2026-09-04.md + feasibility JSON + re-screen CSV.
TEST: one per-file test recomputing required_n_eff for one screen from its frozen inputs and asserting the table
  has exactly 8 rows.
REPORT: feasibility table, chosen screen + reason, re-screen result, RSS, test line, SHA. No push. NEVER PARK.
