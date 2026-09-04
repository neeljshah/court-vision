GAP S244 | sport mlb (pregame) | worktree a13 | log cx_s244_mlb_batter_pitcher_line
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: data/frontend/prop_history_corpus_mlb.jsonl has 3,000 rows (strikeouts etc.) with
market_prob null on the sampled row; gate_corpus_mlb.parquet (39,162 rows) is team/game grain, not
player-line grain. If S240's census has not landed, this row's premise repeats the non-null-price
count itself rather than assuming it.
PREMISE (step 0): parse prop_history_corpus_mlb.jsonl fully (one streaming pass); report total
rows, distinct players, distinct prop_stat values, non-null market_prob count, and how many settle
against a box score already on disk (join key prop_player + date).
LIMIT (step 1): if the non-null-market-price count is < 30 game clusters, report NOT SCORABLE
against a market and score ONLY vs the naive as-of baseline (batter/pitcher's own trailing
distribution); never fit a market-relative model to a null-price row.
CHANGE (step 2): additive only -- new module scripts/platformkit/mlb_batter_pitcher_line_dist.py:
pick ONE stat family (whichever has more non-null rows per PREMISE) and build a CRPS/pinball
10/50/90 distribution conditioned on as-of MLB features already on disk (mlb_batter_context_
platoon_*.parquet, vs_pitch_type sidecars -- read schemas first, assume no columns). Walk-forward
via walkforward_embargo_prereg.py (S233).
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or
ledger; no edits under src/ kernel/ api/ intel/ scripts/team_system/ or token-gated eval_gate
modules; new helpers <= 300 lines.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = settled priced rows and game clusters; then CRPS and pinball at q10/q50/q90 vs the
      closing line (SCORABLE) or the naive baseline (NOT SCORABLE)
  before        = 0 MLB player-prop rows scored against either a market or a baseline; corpus
      parsed only at 1 sampled row before now
  bar           = all 3,000 rows reported with 0 unparsed, none skipped silently; if >= 30 game
      clusters carry a non-null market_prob, both losses reported side by side; otherwise the naive
      loss alone with the exact non-null count that made it NOT SCORABLE
  n             = >= 30 game clusters either way, else CLOSED AT LIMIT
  eye check     = n/a (S-row); reproduction = the verifier re-parses the jsonl, diffs row counts and
      the CRPS/pinball table
  must not move = prop_history_corpus_mlb.jsonl (read-only); every threshold; the ledger
NON-TAUTOLOGY: the parse counts every row including null-market ones; a NOT SCORABLE verdict names
the exact non-null count, never rounds it up.
EVIDENCE: docs/evidence/harness/S244_mlb_batter_pitcher_line_2026-09-04.md plus the parsed schema
and CRPS/pinball table. ASCII only, calibration language only; NOT SCORABLE is a success.
TEST: one new per-file test (a fixture with mixed null/non-null market_prob rows parses correctly;
the naive-baseline path runs without a market column), run only that file.
REPORT: parse counts, SCORABLE/NOT-SCORABLE verdict, CRPS/pinball table, test line, SHA. Commit by
pathspec, no push. NEVER PARK.
