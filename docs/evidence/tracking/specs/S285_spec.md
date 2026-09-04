GAP S285 | sport nba (in-game) | worktree a17 | log cx_s285_event_conformal_width
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: Tibshirani, "Conformal Prediction Under Distribution Shift" (Berkeley STAT lecture notes), and
  Angelopoulos & Bates, arXiv 2107.07511 (2021), show marginal (static) conformal coverage can fail under a
  local covariate shift; Otting, Michels, Langrock, Deutscher, "The reaction to news in live betting," arXiv
  2108.00821 (2021/2022), find live markets over/under-react right after a scoring event. S265 (ACCEPT) built
  one STATIC conformal band for the S123 incumbent on a sealed 79,919-tick/269-game sample (worst OT coverage
  0.833); no COVARIATE-conditioned band exists. No event_key/action-type column exists on
  nba_checkpoints_full.parquet (verified NOT FOUND by S277/S281); only score_home/score_away/ts/period/
  game_clock_s are available.
PREMISE (step 0, INFORMATIONAL): reload S265's own sealed sample via
  scripts/platformkit/eval_gate/s265_incumbent_conformal_band_sample; derive
  ticks_since_last_score_change strictly from strictly-prior ticks per game (planted-future-row test); print n
  ticks in scope, p50/p90 of that distribution, and the near-event (<= p50) / settled (> p90) tick counts.
CHANGE (step 1): additive covariate-conditioned band only, no new incumbent fit: reuse S265's own coverage
  machinery (scripts/platformkit/eval_gate/s101_aci_coverage + scripts/platformkit/ingame/aci_online) to score
  empirical coverage and half-width of S265's STATIC band separately in the near-event and settled bins;
  report the interaction (near-event half-width minus settled half-width) with a game-clustered 95 pct CI.
  Never rewrites S265's archived JSON/CSV; new dated filenames only.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = S265's static-band empirical coverage and half-width, near-event bin / settled bin / pooled,
                  game-clustered 95 pct CI, plus the near-event-minus-settled interaction with its own CI
  before        = S265's band is scored only pooled and per STATIC cell; no event-proximity split exists
  bar           = nominal coverage undershoot by more than 5 pct in the near-event bin vs settled is the
                  signal; a CI-crossing-zero interaction is a valid NULL (band already adequate)
  n             = >= 30 game clusters in each of near-event and settled bins, printed separately
  eye check     = n/a (S-row); reproduction = verifier reruns the covariate derivation and diffs every number
  must not move = S265's/S276's archived summary JSON and paired-loss CSV, the S123 incumbent, MEMORY_LIMIT
                  600 MB
NON-TAUTOLOGY: the near-event/settled boundary is fixed at the sample's own p50/p90 before any bin is scored;
  refitting the boundary to maximize the interaction is circular and self-rejected. Every scored tick in
  S265's sample is assigned to a bin or a named exclusion.
EVIDENCE: docs/evidence/harness/S285_event_conformal_width_2026-09-04.md + summary JSON + paired-loss CSV.
TEST: one per-file test recomputing ticks_since_last_score_change on a fixture (a run, a lull, a game start)
  and reproducing one bin's coverage/half-width from the archived CSV.
REPORT: near-event/settled/pooled table, interaction CI, RSS, test line, SHA. No push. NEVER PARK.
