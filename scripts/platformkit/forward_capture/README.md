# forward_capture -- the FORWARD-CAPTURE / CLV-CLOCK recorder

The edge hunt proved the one missing ingredient is a **real timestamped forward archive
of line movement** (the legacy `odds_snapshots` was a live-poll snapshot format, not a
movement corpus) **plus forward CLV** graded against the devigged close. This package is
the recorder so that clock can start: the moment a real feed is wired it (a) archives
timestamped line movement forward and (b) logs predictions BEFORE the line moves, so
forward CLV can be graded honestly over time.

It **claims nothing**. It RECORDS the data that will one day PROVE or REJECT an edge. No
`$` / ROI / +EV figure is computed or stored anywhere; the ledger schema has no column to
hold one. The LLM authors no number: every value is an observed price, a deterministic
devig of observed prices, or a timestamp comparison.

## What is in here

| File | Role |
|------|------|
| `schema.py` | `OddsSnapshot` (book, market, sport, game_id, side, price, captured_at) + `LineMoveRecord` (open/close/devig). Honesty rail: `validate_snapshot` rejects any `$`/edge field on a price row. |
| `capture.py` | `OddsFeed.poll() -> List[OddsSnapshot]` interface; deterministic `MockFeed`; offline `FileFeed`; **env-gated `RealFeed` stub** (raises `NotImplementedError`, no secret, no live call). |
| `archive.py` | Append-only, atomic (`os.replace`), idempotent timestamped archive to `data/forward_capture/` (GITIGNORED). Idempotent on `snapshot_sha(game_id, book, market, side, captured_at)`. `build_all_line_moves()` reduces the corpus to open->close moves. |
| `clv.py` | Given the archive + a logged prediction (`pred_ts`), compute CLV vs the devigged close (reuse `eval_gate/shin`) -- **only** for predictions whose `pred_ts` is strictly BEFORE the captured line move (vintage via `freshness/as_of_reader.assert_vintage`). A hindsight prediction is EXCLUDED. |
| `run_capture.py` | The "start the clock" headless runner: poll the feed, archive snapshots, log any pregame prediction to the X3 ledger with `pred_ts`. With no real feed/key it runs the `MockFeed` and prints a clear **DRY RUN** banner. Cron / headless-able. |

## Reuse (READ-ONLY -- this package edits none of them)

- `scripts/platformkit/ledger/` -- the X3 append-only track-record ledger. Predictions are
  logged here via `append_prediction` / `append_from_result` (forward_capture adds **zero**
  new ledger code).
- `scripts/platformkit/edge_engine/` -- the adapter pattern (`source.py` `LiveSource` stub,
  schema) that `capture.py` mirrors for an odds tape.
- `scripts/platformkit/eval_gate/shin.py` -- Shin devig of the captured close.
- `scripts/platformkit/freshness/as_of_reader.py` -- the strict `pred_ts < line-move` vintage
  guard (`assert_vintage`).

## How to wire a real feed and START THE CLOCK

1. **Set the env key** (never hardcoded; read by presence only, never logged):

   ```
   # PowerShell
   $env:FORWARD_CAPTURE_ODDS_API_KEY = "<the_odds_api key>"
   # bash
   export FORWARD_CAPTURE_ODDS_API_KEY=<the_odds_api key>
   ```

2. **Implement `RealFeed.poll()`** in `capture.py` (a HUMAN-RUN step). The contract it MUST
   honour:
   - poll the_odds_api (or read a book tape) for each tracked game/market;
   - build a raw quote dict with `book/market/sport/game_id/side/price` (DECIMAL odds);
   - stamp `captured_at = utc_now_iso()` **at poll time** (the vintage floor; never back-date);
   - do NOT devig, do NOT compute an edge, do NOT emit a probability here.

3. **Start the clock** (headless / cron):

   ```
   # one tick
   python -m scripts.platformkit.forward_capture.run_capture --once
   # forever, every 60s
   python -m scripts.platformkit.forward_capture.run_capture --interval 60 --max-ticks 0
   # log specific pregame predictions this tick
   python -m scripts.platformkit.forward_capture.run_capture --once --predictions preds.json
   ```

   When **no** key is set the runner prints the DRY RUN banner and runs the deterministic
   `MockFeed`: a self-test, not a real corpus. The real clock has not started until step 1+2.

## How to read forward CLV from the ledger

CLV is graded **only** for predictions whose `pred_ts` is strictly before the captured close.

```python
from scripts.platformkit.forward_capture import archive, clv
from scripts.platformkit.ledger.ledger import read_ledger

moves = archive.build_all_line_moves("nba")          # open->close from the forward corpus
preds = read_ledger().to_dict("records")             # logged predictions (with pred_ts)
results = clv.grade_forward_clv(preds, moves)         # hindsight rows are EXCLUDED
gmap = clv.to_grade_map(results)                      # {pred_id: {devig_close_prob: ...}}
# ledger.grade_outcomes(gmap) then writes the REAL captured close onto each row immutably.
# clv.aggregate_clv(graded_ledger, sport, market) reports Brier/ECE/DM vs close + mean CLV
# (probability space). edge_claimed is ALWAYS False -- a DM p>=0.05 is an HONEST REJECT.
```

CLV is reported in **probability space**, never dollars. Matching the devigged close within
noise is the honest, defensible read; a measured gap is information, not a claim.

## Binding invariants

- NO live API call, NO secret in code (real feed = env-gated stub).
- Append-only, vintage-strict, idempotent. `data/forward_capture/` is gitignored, LOCAL only.
- The LLM authors no number. NO `$`-edge claim -- this RECORDS; it claims nothing.
