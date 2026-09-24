# S421 probe results (read-only; landed functions)

## Item 2 -- 2026-09-22 books shard only, decoded parse_float=Decimal parse_int=Decimal
### MIACHC
  adapter_refused: 197
  books_reason:inconsistent_touch: 197
  kind_snapshot: 300
  kind_snapshot_bulk: 25
  quote_adapter_refused: 197
  quote_reason:inconsistent_touch: 197
  rows: 325
  touch_ok_both: 128
### MILPHI
  adapter_refused: 540
  books_reason:inconsistent_touch: 540
  kind_snapshot: 722
  kind_snapshot_bulk: 23
  quote_adapter_refused: 540
  quote_reason:inconsistent_touch: 540
  rows: 745
  touch_ok_both: 205
### TORBAL
  adapter_refused: 146
  books_reason:inconsistent_touch: 146
  kind_snapshot: 753
  kind_snapshot_bulk: 24
  quote_adapter_refused: 146
  quote_reason:inconsistent_touch: 146
  rows: 777
  touch_ok_both: 631
queue shapes seen (type, keys, side type, level type): {"('dict', ('market_status', 'no', 'state', 'ticker', 'ts', 'yes'), 'list', 'list')": 892, "('dict', ('market_status', 'no', 'ticker', 'ts', 'yes'), 'list', 'list')": 72}

## Item 4 -- S390-equivalent path: 09-22 full + 09-23 first 27402739 bytes; landed native_rows -> _common/_book -> chronological, as_of 2026-09-23T06:00:00Z
native_rows counts: {} ; chronological counts: {'duplicate_records': 0}
### MIACHC
  in_adapter_refused:pre:inconsistent_touch: 575
  in_rows: 690
  in_touch_ok_both: 115
  out_rows: 95
  out_touch_ok_both: 95
  IN-WINDOW not-accepted from adapter + touch + pre-175 downstream: 575
  in-window touch-fail rows by record_type: {}
### MILPHI
  in_adapter_refused:pre:inconsistent_touch: 529
  in_rows: 658
  in_touch_ok_both: 129
  out_adapter_refused:pre:inconsistent_touch: 11
  out_rows: 88
  out_touch_ok_both: 77
  IN-WINDOW not-accepted from adapter + touch + pre-175 downstream: 529
  in-window touch-fail rows by record_type: {}
### TORBAL
  in_adapter_refused:pre:inconsistent_touch: 146
  in_rows: 660
  in_touch_ok_both: 514
  out_rows: 118
  out_touch_ok_both: 118
  IN-WINDOW not-accepted from adapter + touch + pre-175 downstream: 146
  in-window touch-fail rows by record_type: {}

## Item 3 -- state shard 2026-09-22 (timestamp field: response_end_utc)
  game_key 823327: ABSENT from shard
  game_key 823412: ever_live True
    status 'live': rows 592 first 2026-09-22T22:19:58.674230Z last 2026-09-22T23:59:54.598951Z
    status 'pre': rows 316 first 2026-09-22T16:58:35.824596Z last 2026-09-22T22:18:57.852908Z
  game_key 824624: ever_live True
    status 'live': rows 262 first 2026-09-22T23:15:47.440471Z last 2026-09-22T23:59:55.973249Z
    status 'pre': rows 371 first 2026-09-22T16:58:37.925253Z last 2026-09-22T23:14:46.503076Z
  game_key 824710: ABSENT from shard
  game_key 824785: ever_live False
    status 'pre': rows 417 first 2026-09-22T16:58:34.287948Z last 2026-09-22T23:59:53.580093Z
  game_key 824868: ABSENT from shard

## Item 4b -- inconsistent_touch anatomy (which _touch candidates disagree)
### MIACHC (in-window refused rows; per failing side)
  deviating=raw.no_ask+raw.yes_bid kind=snapshot: 534
  deviating=raw.no_bid+raw.yes_ask kind=snapshot: 549
  side_no: 549
  side_yes: 534
  spread_cents=1: 563
  spread_cents=2: 331
  spread_cents=3: 129
  spread_cents=4: 60
    example 2026-09-22T23:40:17.881857Z side no candidates [('row.no_bid', '32.0000'), ('row.yes_ask', '32.0000'), ('ladder_max', '32.0000'), ('raw.no_bid', '34.0000'), ('raw.yes_ask', '34.0000')]
    example 2026-09-22T23:40:23.072367Z side no candidates [('row.no_bid', '32.0000'), ('row.yes_ask', '32.0000'), ('ladder_max', '32.0000'), ('raw.no_bid', '34.0000'), ('raw.yes_ask', '34.0000')]
    example 2026-09-22T23:40:43.849532Z side yes candidates [('row.yes_bid', '69.0000'), ('row.no_ask', '69.0000'), ('ladder_max', '69.0000'), ('raw.yes_bid', '65.0000'), ('raw.no_ask', '65.0000')]
    example 2026-09-22T23:40:43.849532Z side no candidates [('row.no_bid', '30.0000'), ('row.yes_ask', '30.0000'), ('ladder_max', '30.0000'), ('raw.no_bid', '34.0000'), ('raw.yes_ask', '34.0000')]
### MILPHI (in-window refused rows; per failing side)
  deviating=raw.no_ask+raw.yes_bid kind=snapshot: 528
  deviating=raw.no_bid+raw.yes_ask kind=snapshot: 512
  side_no: 512
  side_yes: 528
  spread_cents=1: 423
  spread_cents=17: 4
  spread_cents=18: 6
  spread_cents=19: 22
  spread_cents=2: 293
  spread_cents=2E+1: 2
  spread_cents=3: 141
  spread_cents=4: 64
  spread_cents=5: 50
  spread_cents=6: 32
  spread_cents=7: 1
  spread_cents=8: 1
  spread_cents=9: 1
    example 2026-09-22T22:40:08.513369Z side yes candidates [('row.yes_bid', '59.0000'), ('row.no_ask', '59.0000'), ('ladder_max', '59.0000'), ('raw.yes_bid', '58.0000'), ('raw.no_ask', '58.0000')]
    example 2026-09-22T22:40:08.513369Z side no candidates [('row.no_bid', '40.0000'), ('row.yes_ask', '40.0000'), ('ladder_max', '40.0000'), ('raw.no_bid', '41.0000'), ('raw.yes_ask', '41.0000')]
    example 2026-09-22T22:40:14.012650Z side yes candidates [('row.yes_bid', '59.0000'), ('row.no_ask', '59.0000'), ('ladder_max', '59.0000'), ('raw.yes_bid', '58.0000'), ('raw.no_ask', '58.0000')]
    example 2026-09-22T22:40:14.012650Z side no candidates [('row.no_bid', '40.0000'), ('row.yes_ask', '40.0000'), ('ladder_max', '40.0000'), ('raw.no_bid', '41.0000'), ('raw.yes_ask', '41.0000')]
### TORBAL (in-window refused rows; per failing side)
  deviating=raw.no_ask+raw.yes_bid kind=snapshot: 112
  deviating=raw.no_bid+raw.yes_ask kind=snapshot: 53
  side_no: 53
  side_yes: 112
  spread_cents=1: 165
    example 2026-09-22T22:50:57.370618Z side no candidates [('row.no_bid', '47.0000'), ('row.yes_ask', '47.0000'), ('ladder_max', '47.0000'), ('raw.no_bid', '48.0000'), ('raw.yes_ask', '48.0000')]
    example 2026-09-22T22:51:04.150016Z side yes candidates [('row.yes_bid', '52.0000'), ('row.no_ask', '52.0000'), ('ladder_max', '52.0000'), ('raw.yes_bid', '51.0000'), ('raw.no_ask', '51.0000')]
    example 2026-09-22T22:51:04.150016Z side no candidates [('row.no_bid', '47.0000'), ('row.yes_ask', '47.0000'), ('ladder_max', '47.0000'), ('raw.no_bid', '48.0000'), ('raw.yes_ask', '48.0000')]
    example 2026-09-22T22:51:11.950999Z side yes candidates [('row.yes_bid', '52.0000'), ('row.no_ask', '52.0000'), ('ladder_max', '52.0000'), ('raw.yes_bid', '51.0000'), ('raw.no_ask', '51.0000')]

## Reconciliation (item 4)
- In-window not-accepted rows on the S390 inputs (09-22 full + 09-23 prefix 27402739 bytes, as_of 2026-09-23T06:00:00Z): TORBAL 146, MILPHI 529, MIACHC 575 -- exactly the S390 ADAPTER_REFUSED counts.
- Every one is an ADAPTER refusal: reason inconsistent_touch (set as _refusal by forward_capture_bridge.load_native via books(), re-raised at forward_replay.py:66-67). touch_unavailable = 0 and downstream_refusal = 0 in window, for all three.
- In-window rows: TORBAL 660 (= NOT_LIVE 660), MILPHI 658, MIACHC 690. Accepted: 514 / 129 / 115; S390 qualified 0 / 117 / 103.
- Spec S421 (c) '777/745/325 accepted, 0 refused' is FALSE on the 09-22 shard: books() refuses 146 / 540 / 197 (all inconsistent_touch). to_quote_book RETURNS a {refused: True} dict, it never raises -- a probe counting exceptions sees 0 refused.
- Replay decision loop is per row, not on a cadence: forward_replay.py:231-232 calls qualification.decision in the finally for every book row; decision() counts reasons for each row whose _at is in [start, start+3600).
- Anatomy: in every refused row the orderbook ladder max and the row's yes_bid/no_ask/no_bid/yes_ask agree; raw_market *_dollars disagree (TORBAL always 1 cent; MILPHI 1-20; MIACHC 1-4).
