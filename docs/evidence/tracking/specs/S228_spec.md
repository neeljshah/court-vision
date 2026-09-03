GAP S228 | sport nba (pregame) | worktree aXX | log cx_s228_pregame_prop_close_upset
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: a player-level market exists on disk and has never entered the harness. Measured 2026-09-04:
data/cache/cv_fix/closing_props/ holds 77 JSON files, one per game, each an odds-API payload with commence_time,
home_team, away_team and bookmakers; nothing in the S-register references it. prop_calibration_history.parquet (4,942
rows) scores props against our OWN baseline only. As-of-safe conditioning: momentum_signals 673,204 rows,
per_player_calibration 307,643 (rolling bias, sigma_resid), gt_weighted_forms 99,157, schedule_strength_7d 99,498.
PREMISE (step 0): parse all 77 files ONE AT A TIME into a tidy table (game, commence_time, player, stat, line,
over_price, under_price, book, capture_ts) and report exact counts: files parsed, games, distinct players, distinct
stats, priced player-stat rows, and how many settle against a box score already on disk.
LIMIT (step 1): if the settled priced rows do not reach >= 30 game clusters the market-relative comparison is NOT
SCORABLE -- report the census and CLOSED AT LIMIT, exactly as S204 did for the team close. Do not fit a model to it.
CHANGE (step 2): additive only -- a new module under scripts/platformkit/ that (a) builds the tidy prop-close table
and (b), only if the limit clears, scores two targets on identical rows: the player's stat distribution by CRPS and
pinball plus Brier with 10 reliability bins on P(over the closing line), and the tail target P(a named player
outscores that game's pregame favourite scorer) by log-loss against the observed base rate. Every conditioning column
is joined as-of by game_date, walk-forward, never from a snapshot store.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = settled priced player-stat rows and game clusters; then CRPS, pinball and Brier-with-bins vs the
      devigged closing prop line
  before        = 0 prop rows have ever been scored against a market; own-baseline mae and rmse only (4,942 rows)
  bar           = all 77 files reported with 0 unparsed and none skipped silently; if >= 30 game clusters settle, both
      targets are scored on identical rows with clustered CIs and the market's own loss beside the model's; if fewer,
      the row reports NOT SCORABLE with the exact n and stops
  n             = >= 30 game clusters if scored; otherwise 77 files (CONSTRUCT census)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the parse and diffs the tidy table row count and
      the census JSON
  must not move = the closing_props JSON files (read-only); prop_calibration_history.parquet; every threshold; the
      FWER ledger
NON-TAUTOLOGY: the census counts every file and every player-stat row including those with no settlement; a NOT
SCORABLE verdict names which step lost the rows.
EVIDENCE: docs/evidence/harness/S228_pregame_prop_close_upset_2026-09-04.md plus the census JSON and the tidy table
schema. ASCII only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (a fixture payload parses to the tidy schema; a missing bookmaker block yields no row),
run only that file.
REPORT: the census counts, the SCORABLE / NOT SCORABLE verdict with its n, any scored table, the test line, SHA.
Commit by pathspec, no push. NEVER PARK.
