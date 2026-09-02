# S58 trial 2 -- NBA halftime checkpoint: NOT RECONSTRUCTIBLE (no charge; 2026-09-03)

## VERDICT: NOT RECONSTRUCTIBLE -- stopped BEFORE any charge (a valid result)

The inventory memo's row 2 ("NBA halftime checkpoint, CI [-0.0098, 0.0015], the closest-to-
resolving row") names an artifact whose MODEL side cannot be regenerated from disk. No prereg
was sealed, no ledger row was appended (K unchanged by this trial), nothing was scored.
Calibration language only.

## The artifact and the exact comparison it names (located, read, not re-run)

- Artifact: `scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json`
  (mtime 2026-07-18 00:47). Producer: `.../crps_market/ingame_nba_winprob.py`.
- Corpus: `data/cache/inplay_odds/nba_checkpoints_full.parquet` -- PRESENT, 465,249 rows x 13
  columns (game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin,
  market_prob, traded, market_ticker, outcome_home_win, venue). Games considered 1,593;
  checkpoints scored 6,371 (= 1,592 end_q1 + 3 x 1,593); ticker parse fail 0; dispatch fail 0.
- Halftime row (verbatim from the JSON): n = 1,593; model Brier mean 0.1677 vs market 0.1638;
  log-loss 0.5064 vs 0.4900; paired delta (market - model Brier) -0.0040; bootstrap 95 pct CI
  [-0.009833149837413686, 0.0015363951420276217] (`ingame_mlb._verdict`, seed 0);
  verdict UNDERPOWERED, provisional False.
- Checkpoint = the LAST tick at or before elapsed minute 24 (`checkpoint_row`, OT-aware
  `_elapsed_minutes`); MARKET = `market_prob` on that same tick (Polymarket in-play
  moneyline); MODEL = `winprob_dispatch.dispatch("nba", home, away, ingame_state=
  {elapsed, home_score, away_score})`, a subprocess over `predict_matchup.py` that calls
  `domains/basketball_nba/predictor.py:222 NBAPredictor.predict_live(home, away,
  elapsed_minutes, home_score, away_score)`.

## What is missing (each one measured on disk this session)

1. MODEL VINTAGE. `predict_live` carries NO as-of argument; its pregame prior is the
   predictor's Elo state at RUN time (`self.elo`), and `dispatch` stamps `as_of = now`
   (probe call this session: `dispatch("nba","BOS","NY", halftime 55-50)` -> status ok,
   p_home 0.7385, as_of 2026-09-02T15:18:16Z, 4.1 s). The model state of 2026-07-18 that
   produced 0.1677 is not on disk and cannot be regenerated; any rerun scores a DIFFERENT
   predictor against the same market, which is a new trial, not this artifact's comparison.
2. PER-GAME DELTAS NOT ARCHIVED. The JSON holds rounded means and the bootstrap CI only; the
   1,593 halftime paired deltas were never written, so the CI [-0.0098, 0.0015] cannot be
   recomputed from disk (A2 fails by construction).
3. COST, for completeness: 6,371 subprocess dispatches x 4.1 s = ~7.3 h wall, and item 1 makes
   the result a different comparison regardless.

## Premise finding (Q8) -- the row's leak-free status

The artifact's `honest_note` claims leak-freeness for CHECKPOINT-ROW SELECTION only (never a
tick past the anchor). Nothing in the model path asserts that the pregame prior fed into
`predict_live` predates each game's date: with no as-of, an Elo state at run time includes
results after -- and possibly of -- the scored game. So even as a historical number the row is
not a leak-free market-relative verdict in Q4's sense; the inventory memo's "closest-to-
resolving" reading rests on a CI whose model side has an unasserted vintage.

The leak-free NBA prior that DOES exist is `domains/basketball_nba/adapter.py:121
baseline_probability(event, as_of)` (Elo replay strictly before `as_of`). A prereg'd halftime
trial on THAT prior + the artifact's repricer path, with archived per-game deltas, is a NEW
charged trial on a corpus that is present and adequate (1,593 games; the corpus_unit split
2024-25 / 2025-26 could even satisfy the S08 two-corpora floor). It is not a reconstruction
and was not run here.

## Artifacts

- `data/cache/eval_gate/s58_trial2_nba_halftime_2026-09-03.json` -- the NOT RECONSTRUCTIBLE
  record (artifact path, corpus shape, the halftime row verbatim, the three missing pieces,
  ledger row count at the time, `charged: false`).

## NOT VERIFIED

- Whether the 2026-07-18 Elo state actually contained post-game results for the scored games
  (the exposure is structural -- no as-of -- but the state itself is gone, so it cannot be
  measured either way).
- The end_q1 / end_q3 / q4_under5 rows were read, not re-derived; the same three gaps apply.
- `nba_checkpoints_full.parquet` was shape-checked only; its tick content, the ticker decode
  and the OT-aware elapsed-minute mapping were not re-verified.
- No test file was run for this trial; nothing was computed beyond one probe dispatch call.

NEW GAP: NBA halftime checkpoint as a prereg'd charged trial on the as-of Elo prior
(`adapter.baseline_probability`) with archived per-game deltas -- corpus present, model path
absent; and `ingame_nba_winprob.py` should archive per-game deltas so its CI is recomputable.
