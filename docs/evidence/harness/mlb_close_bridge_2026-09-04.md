# S194 MLB close bridge: CLOSED AT LIMIT

## Verdict

**CLOSED AT LIMIT.** The acceptance bar remains **>= 400 distinct `event_id`**
with both moneyline and total pre-commence closes, against the fixed
denominator of 641 in-window raw MLB game ids. Re-measurement shows that the
entire `games_current` date window represented by those 641 ids contains only
**337 distinct settled `event_id` values**. A one-row-per-`event_id` artifact
therefore cannot reach 400 even with a perfect bridge and quote coverage.

This is a Q8 falsified-premise closure, not a lower bar. No bridge module,
parquet artifact, or per-file test was added: the contract directs a row with
a falsified premise to close without a fix. No register or ledger was read or
written.

## Re-measurement and fixed denominator

| Measure | Current result |
|---|---:|
| MLB store rows streamed, one file at a time | 2,164,041 |
| Distinct raw game ids | 859 |
| Raw ids with a commence time | 686 |
| In-window raw ids (Eastern date exists in `games_current`) | 641 |
| Commence-time ids outside the outcome date set | 45 |
| Raw in-window ids with strict pre-commence moneyline and total quotes | 600 |
| Settled `games_current.event_id` capacity for those dates | 337 |
| Acceptance bar, unchanged | 400 |

The 173 ids without a commence time and the 45 commence-time ids outside the
`games_current` date set remain explicitly excluded from the fixed 641
denominator exactly as specified. The closure follows from the required output
grain, not from dropping an inconvenient raw id.

## Bridge feasibility evidence

An explicit 30-franchise exact-name map was used only for this read-only
measurement. Its singleton date/home/away bridge matched 604 raw ids to 331
distinct settled event ids. Of those singleton event ids, 314 have strict
pre-commence rows for both required markets. Six raw ids are doubleheader
ambiguous and eight otherwise valid-name ids have no date/team outcome match.
Resolving every one of those cases cannot exceed the 337-event capacity.

Per-book, per-market strict-pre-commence rows after singleton bridge and
one-row-per-event/market/side/book de-duplication:

| Book | Market | Rows |
|---|---|---:|
| espn:DraftKings | moneyline | 616 |
| espn:DraftKings | total | 616 |
| fanduel | moneyline | 476 |
| pinnacle | moneyline | 612 |
| pinnacle | spread | 594 |
| pinnacle | total | 594 |

The 6 doubleheader-ambiguous raw ids are: `401879401` (2026-06-24 NYM/CUB,
candidate sequences 2 and 3); `fd:35794959`, `401871790`, and `fd:35794951`
(2026-07-07 STL/MIL, sequences 1 and 2); and `fd:35808249` and `401889917`
(2026-07-11 PIT/MIL, sequences 1 and 2). The full unmatched valid-name list
is in the companion JSON.

## Instrument hazards

1. **Post-start last quote.** Of 6,174 MLB `(game_id, market_type, side,
   book)` tuples with a commence time, 3,630 (58.79 percent) have a last raw
   quote after commence. Median lead is -2.78 minutes. This describes the raw
   feed only; it is not a defect asserted against either existing on-disk
   consumer. This measurement selected only a quote whose own `captured_at`
   was strictly before its own `commence_time`.
2. **`captured_at_suspect` is absent, not clean.** In MLB it is present on
   3,366 of 2,164,041 rows (all present values are `false`) and absent on
   2,160,675 rows (99.8445 percent). The specified MLB-plus-tennis reference
   is 8,160 present fields out of 3,011,733 rows (0.27 percent), likewise all
   `false`; it must not be described as a zero-suspect result.
3. **Non-franchise names are rejected.** The 641 in-window ids expose 44
   distinct home/away values. Twelve futures/prop values are `Home Runs (8,
   9, 13, 14, 15, or 16 Games)` and their corresponding `Away Runs` values.
   The exact-name map also rejects `G2 Pittsburgh Pirates` and `G2 Milwaukee
   Brewers`; no silent normalization was applied. This rejects 23 raw ids:
   one G2 pair, and 4, 2, 11, 2, 1, and 2 ids for the 13-, 14-, 15-, 16-,
   8-, and 9-game Home/Away Runs pairs, respectively.

## Evenly spaced bridge sample

The companion JSON stores 12 rows selected at evenly spaced positions across
the 331 sorted singleton-matched event ids, including the first and last.
These are bridge evidence rows, not a produced close artifact and not a
performance comparison.

## Not verified

- No unique date/team/game-sequence bridge for the six doubleheader-ambiguous
  raw ids was materialized, because it cannot change the 337-event ceiling.
- No new close parquet exists, by Q8 closure.
- No scoring, forecast comparison, freshness verdict, or sharpening claim was
  performed.
- `data/cache/eval_gate/backtest_fwer.jsonl` was not opened; its K remains
  unread and no row was charged.

## Verifier self-check

Section B: B1 fixed 641 denominator and named exclusions; B2 additive
documentation only and no reader field changed; B3 no absent evidence was
quarantined; B4 terminal closed verdict prevents re-claim; B5 no pod action;
B6 no module moved; B7 sample is evenly spaced; B8 no fit or comparison; B9
the event-id capacity is the required output grain; B10 the 400 bar is
unchanged.

Section Q: Q1-Q2 and Q4-Q5 are inapplicable because nothing was scored or
charged; Q3 bar unchanged; Q6 calibration language only; Q7 no sampled or
scored result is claimed; Q8 premise re-measured before implementation and
falsified; Q9 is inapplicable because there is no scored comparison.
