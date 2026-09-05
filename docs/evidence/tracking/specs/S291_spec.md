GAP S291 | sport nba (in-game) | worktree aXX | log cx_s291_ingame_comeback_states
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: nba_checkpoints_full.parquet (465,249 ticks/1,593 games; cols confirmed: game_id, game_date, ts, period,
  game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue) has
  no precomputed "remaining game clock" column.
CONTEXT: period runs 1-6; periods 5-6 contain 14,765 OT ticks; game_clock_s runs 0-720.
  Trailing-team comeback conditioning is a tail state the S272/
  S277/S289 rows never isolated: they conditioned on market_prob, not on the underlying score/clock state.
PREMISE (step 0): reproduce remaining_s = (4-period)*720 + game_clock_s for period<=4 (OT rows keep only
  game_clock_s, named and excluded from the headline if their remaining semantics differ). The condition
  |margin| >= 12 AND remaining_s <= 720 (12 min) measures 133,319 ticks across 1,113 games; outcome_home_win
  splits 77,516/55,803 in that subset (informational, not yet team-relative).
CHANGE (step 1): additive module scripts/platformkit/ingame/s291_ingame_comeback_states.py (<=300 LOC):
  restricts to the 133,319-tick/1,113-game subset, computes TRAILING-team win rate (the team behind by >= 12 at
  that tick) vs market_prob-implied trailing-win-rate and vs the recal_null incumbent (unmodified
  scripts/platformkit/foundry/ingame_incumbent_nba.py apply_incumbent import), with log-loss and reliability,
  through cpcv_evaluate (purge + symmetric embargo); ALSO all-ticks Brier improvement with CI (non-inferiority).
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> --
  <command>. Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = trailing-team win rate vs market and vs recal_null, log-loss + reliability, game-clustered
                  95 pct CI on the comeback-state subset; PLUS all-ticks Brier improvement CI (non-inferiority)
  before        = no prior row conditioned on margin+clock jointly; 133,319/1,113 is the first measurement of
                  this state's size
  bar           = frozen +0.004 all-ticks Brier bar untouched; all-ticks improvement CI LOWER BOUND > -0.0005 (preregistered
                  non-inferiority tolerance = 1/8 of the bar; a CI merely not below 0 proves nothing)
  n             = 133,319 ticks / 1,113 game clusters (>= 30)
  eye check     = n/a (S-row); reproduction = verifier recomputes remaining_s, the subset mask, log-loss,
                  reliability and both CIs from the archived paired-loss CSV
  must not move = nba_checkpoints_full.parquet; the +0.004 bar; apply_incumbent byte-identical (SHA-256
                  printed); nothing charged
NON-TAUTOLOGY: the subset is defined by margin/clock alone, fixed before scoring; report ticks where the
  trailing team still lost, never restrict to completed comebacks (that would make the win rate circular).
EVIDENCE: docs/evidence/harness/S291_ingame_comeback_states_2026-09-04.md + summary JSON + paired-loss CSV (Q9).
TEST: one per-file test recomputing remaining_s and the subset count from a small fixture plus one archived tick.
REPORT: subset size, trailing win-rate table, CIs, RSS, test line, SHA. No push. NEVER PARK.
