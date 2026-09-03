# S171 period-grain corpus premise, 2026-09-04

## Scope and outcome

This is a read-only premise measurement for the two frozen period families. No
store, threshold, frozen specification, FWER ledger, or runtime code was
changed. No corpus was built.

Result: the premise is FALSIFIED for both families today. The local stores have
some period state, but neither has a labelled line for the frozen family market
at period grain. Therefore each possible junction has zero games and is below
the unchanged n >= 30 rail.

| family | state games | period-line games | both | date range | columns missing | verdict |
|---|---:|---:|---:|---|---|---|
| mlb_inning | 178 / 227 ingame-grade games with `inning=` state | 0 / 99 `total`-market games labelled as an inning/period total | 0 / 178 | state: 2026-06-28..2026-07-12; total candidate: 2026-07-01..2026-07-09 | period identifier; period-total line and probability; structured `home_score`, `away_score`, `inning`, and `half` columns in the grade log | NOT BUILDABLE today (LIMIT: 0 < 30) |
| nba_quarter_shape | 1,593 / 1,593 checkpoint games with timestamped periods 1..4 and scores | 0 / 9 `spread`-market games labelled as a quarter spread | 0 / 1,593 | state: 2024-10-22..2026-06-13; spread candidate: 2026-05-26..2026-06-14 | quarter identifier; quarter-spread or quarter-total line and probability; a declared bridge from Kalshi `event_key` to the frozen-family event id | NOT BUILDABLE today (LIMIT: 0 < 30) |

The denominators are the complete local candidate sets for the named stores,
not samples. `both` is exactly zero because each labelled-period-line set is
empty; no unlabelled whole-game total or spread was promoted to a period line.

## Store measurement

### MLB

`data/cache/ingame_grade_joined/mlb/*.jsonl` and `mlb_clean/*.jsonl` provide
the only current timestamped state found for the 2026 Kalshi identifiers.
Exhaustive one-file-at-a-time streaming found 227 unique `game_id` values and
178 whose `state_summary` contains `inning=`. The state is a string such as
`home_score=... away_score=... inning=... half=...`; it is not a structured
period-state table.

`data/cache/inplay_odds/mlb_price_series.parquet` has 13,473,591 rows and the
columns `game_date,event_key,market_type,ticker_or_slug,ts,prob` among its
schema. Its complete market-type counts are moneyline 3,792 games, spread 41
games, and total 99 games. The total candidates are only series
`KXMLBTOTAL`; the series specification declares it `total`, not an inning or
period market. No ticker identifies an inning or period. Thus its labelled
period-total count is 0 / 99. The 99 whole-game-total candidates must not be
relabelled as inning totals.

`data/domains/mlb/asof_inning.parquet` supplies the frozen feature columns,
not a contemporaneous inning score or market line. It has 28,004 distinct
`event_id` values; 27,985 have all six frozen members, with event-id date
range 2010-04-04..2021-11-02. It has no timestamp, market, line, probability,
or structured current-score column, and it does not overlap the 2026 line
window by date.

### NBA

The requested path
`data/cache/eval_gate/nba_checkpoints_full.parquet` is absent. This was
reported as absent, not inferred to be junctioned. A distinct file,
`data/cache/inplay_odds/nba_checkpoints_full.parquet`, exists and was measured
separately: 465,249 rows; columns
`game_id,game_date,ts,period,game_clock_s,score_home,score_away,margin,market_prob,market_ticker,outcome_home_win,venue`.
It has 1,593 distinct games, all with a timestamped period 1..4 score state
(periods range 1..6 overall). It is state evidence, but no existing junction
to a quarter-market corpus was assumed.

`data/cache/inplay_odds/nba_price_series.parquet` has 8,399,632 rows. Its
complete market-type counts are moneyline 1,826 games and spread 9 games.
The spread candidates are only `KXNBASPREAD`; no ticker carries a quarter
label. Therefore the labelled-quarter-spread count is 0 / 9. Whole-game
spreads were not treated as quarter spreads.

`data/domains/basketball_nba/linescores.parquet` is supplementary final
quarter-score evidence: 1,313 / 1,313 games have all eight home/away Q1..Q4
values, dated 2025-10-21..2026-05-24. It has no in-game timestamp, line,
probability, or Kalshi key. `asof_quarter_shape.parquet` has 2,634 event ids,
of which 2,618 supply all frozen members, but it has neither a date nor a
period-market-line field.

## Frozen definition and column coverage

Frozen grammar: `docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md`.

`mlb_inning` is `sport=mlb`, `horizon=period`, `market=total`, sourced from
`data/domains/mlb/asof_inning.parquet`. Its required members are:

`home_early_rate_asof`, `away_early_rate_asof`, `early_rate_diff_asof`,
`home_late_rate_asof`, `away_late_rate_asof`, and `late_rate_diff_asof`.

All six exist in `asof_inning.parquet` (27,985 complete event ids). The raw
grade logs instead provide `game_id`, `ts`, and text `state_summary`; they do
not supply the six members as columns. `mlb_price_series.parquet` supplies
`event_key,game_date,market_type,ticker_or_slug,ts,prob`, but no period id or
period-total label. Accordingly, the feature supply does not create a
period-total corpus.

`nba_quarter_shape` is `sport=nba`, `horizon=period`, `market=spread`, sourced
from `data/domains/basketball_nba/asof_quarter_shape.parquet`. Its required
members are:

`home_q1_margin_asof`, `away_q1_margin_asof`, `diff_q1_margin_asof`,
`home_first_half_margin_asof`, `away_first_half_margin_asof`,
`diff_first_half_margin_asof`, `home_second_half_margin_asof`,
`away_second_half_margin_asof`, `diff_second_half_margin_asof`,
`home_q4_margin_asof`, `away_q4_margin_asof`, `diff_q4_margin_asof`,
`home_quarter_volatility_asof`, `away_quarter_volatility_asof`, and
`diff_quarter_volatility_asof`.

All 15 exist in `asof_quarter_shape.parquet` (2,618 complete event ids). The
inplay checkpoint supplies `game_id,game_date,ts,period,game_clock_s,score_home,
score_away,margin,market_prob,market_ticker`; it does not supply the 15 frozen
members or a period-market label. `nba_price_series.parquet` supplies
`event_key,game_date,market_type,ticker_or_slug,ts,prob`, but no quarter id or
quarter-spread label. Accordingly, the feature supply does not create a
quarter-spread corpus.

## Reproduction: exact count commands

These are the two commands used for the decision rows. They stream JSONL one
file at a time and query only named Parquet columns. They do not write files;
DuckDB aggregates in process and is not used to materialize a store.

### MLB

```powershell
$all=[Collections.Generic.HashSet[string]]::new();$state=[Collections.Generic.HashSet[string]]::new();$lo='9999-99-99';$hi='';Get-ChildItem 'data/cache/ingame_grade_joined/mlb','data/cache/ingame_grade_joined/mlb_clean' -File -Filter *.jsonl|%{foreach($line in [IO.File]::ReadLines($_.FullName)){if($line -match '"game_id": "([^"]+)"'){$id=$Matches[1];[void]$all.Add($id);if($line -match '"state_summary": "[^"]*inning='){[void]$state.Add($id);if($line -match '"ts": "(\d{4}-\d{2}-\d{2})'){$d=$Matches[1];if($d -lt $lo){$lo=$d};if($d -gt $hi){$hi=$d}}}}}};"state=$($state.Count)/$($all.Count) dates=$lo..$hi";python -c "import duckdb;p='data/cache/inplay_odds/mlb_price_series.parquet';q='''select count(distinct event_key),count(distinct case when regexp_matches(lower(ticker_or_slug),'inning|period') then event_key end),min(game_date),max(game_date) from read_parquet(?) where market_type='total' and split_part(ticker_or_slug,'-',1)='KXMLBTOTAL' ''';print('total_candidates|labelled_period|first|last='+ '|'.join(map(str,duckdb.connect().execute(q,[p]).fetchone())))"
```

Expected output: `state=178/227 dates=2026-06-28..2026-07-12` and
`total_candidates|labelled_period|first|last=99|0|2026-07-01|2026-07-09`.

### NBA

```powershell
python -c "import duckdb;c=duckdb.connect();p='data/cache/inplay_odds/nba_checkpoints_full.parquet';q='''select count(distinct game_id),count(distinct case when period between 1 and 4 and score_home is not null and score_away is not null and ts is not null then game_id end),min(game_date),max(game_date) from read_parquet(?)''';print('checkpoint_games|quarter_state|first|last='+ '|'.join(map(str,c.execute(q,[p]).fetchone())));p='data/cache/inplay_odds/nba_price_series.parquet';q='''select count(distinct event_key),count(distinct case when regexp_matches(lower(ticker_or_slug),'quarter|q[1-4]|[1-4]q') then event_key end),min(game_date),max(game_date) from read_parquet(?) where market_type='spread' and split_part(ticker_or_slug,'-',1)='KXNBASPREAD' ''';print('spread_candidates|labelled_quarter|first|last='+ '|'.join(map(str,c.execute(q,[p]).fetchone())))"
```

Expected output: `checkpoint_games|quarter_state|first|last=1593|1593|2024-10-22|2026-06-13`
and `spread_candidates|labelled_quarter|first|last=9|0|2026-05-26|2026-06-14`.

## NOT VERIFIED

- The unlabelled Kalshi whole-game total/spread candidates are not period lines.
  Their probability cannot be used as an inning or quarter probability.
- No existing bridge was verified between Kalshi `event_key` and every frozen
  source `event_id`; no bridge was fabricated.
- No as-of reconstruction was performed for the final `linescores` table.
- No claim is made about market availability outside the measured local files.

## Verifier checklist

`metric=2/2` complete decision rows; `before=0/2`; `n=2 (CONSTRUCT)`; eye
check is n/a. The unchanged rail is n >= 30. Both rows are non-tautologically
reported and fail it at the measured, labelled-period `both=0` limit.

## Corrections at landing (Opus verifier, 2026-09-04)

- nba_checkpoints_full.parquet has 13 columns on disk (the list above omits `traded`); no count depends on it.
- Verifier reproduced both rows exactly: mlb_inning state 178/227, period-line 0/99, both 0/178; nba_quarter_shape state 1,593/1,593, period-line 0/9, both 0/1,593; zero tickers matching inning|period|quarter across 21.87M price rows.
- The MLB grade-log command is PowerShell-only; a portable equivalent (python over the log files) is owed with any future re-run.
