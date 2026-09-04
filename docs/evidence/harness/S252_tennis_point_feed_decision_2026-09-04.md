# S252 Tennis Point-Level Feed Decision

## Binding premise re-measurement

This read-only re-measurement used the S215 classification rule and opened the
price Parquet one row group at a time; each state source was opened separately
for schema metadata. It confirms the S252 premise rather than falsifying it.

```text
price_metadata rows=1854100 row_groups=10
rows_scanned=1854100 distinct_event_key=986 class_counts={"IN_PLAY_JOINED": 0, "IN_PLAY_NO_STATE": 2806, "POST_MATCH": 0, "PRE_MATCH": 1851294, "UNRESOLVED_KEY": 0}
grade_counts={"final": 1237, "priced": 18, "rows": 1255}
state_timestamp_columns={"tennis_gamestate__atp.parquet": [], "tennis_gamestate__wta.parquet": [], "tennis_setdetail__atp.parquet": [], "tennis_setdetail__wta.parquet": [], "tennis_states__atp.parquet": [], "tennis_states__wta.parquet": []}
recoverable_state_rows=0
```

The binding inputs were the S215 tennis price-series Parquet and six tennis
state Parquets, opened read-only for the stated measurement. No store was
written.

## Candidate sections

The four complete candidate sections below are the public decision record.
Vendor pricing, contact, and contract detail remains only in
`docs/research/organization-sprint/S252_tennis_point_level_feed_decision_2026-09-04.md`
(local-only decision brief).

| Candidate | Cost | Cadence | Terms/ToS | Minimum viable capture | Sourced-or-unsourced flag |
|---|---|---|---|---|---|
| Sportradar Tennis | UNSOURCED: no public tennis rate was recorded in this public memo. | SOURCED: provider documentation reports a 1-second cache TTL and Tier 1 live-play updates. | SOURCED: public terms status was reviewed; detail is retained in the local-only decision brief. | Verify covered-match availability; persist provider event id, source update time, request-received UTC time, point/game state, and a price-side match-key crosswalk for every update. | SOURCED (terms; cadence) |
| Enetpulse | UNSOURCED: no numeric rate is recorded in this public memo. | UNSOURCED numeric cadence: provider material describes live point-by-point scoring on most ATP/WTA tour-level matches but gives no update interval. | SOURCED: public terms status was reviewed; detail is retained in the local-only decision brief. | Verify tournament coverage and point-event timestamps; record provider match id, received UTC time, state payload, and a price-feed crosswalk before any comparison. | SOURCED (terms) |
| Data Sports Group | UNSOURCED: no public tennis rate was recorded in this public memo. | SOURCED only qualitatively: provider material advertises real-time point-by-point feeds; no numeric interval is recorded. | UNSOURCED: no public terms source was recorded in the reviewed material. | Establish point-event timestamp semantics, coverage, and a stable match-id crosswalk to the price feed; archive every received state and receipt time. | UNSOURCED (cost and terms) |
| Self-serve REST/WebSocket pair: livetennisapi.com + tennis-api.com | SOURCED: public cost information exists; amounts are retained in the local-only decision brief. | SOURCED: provider material describes score-frame changes, a heartbeat near 15 seconds, and WebSocket match-event updates. | SOURCED for one provider and UNSOURCED for the other in the reviewed material; detail is retained in the local-only decision brief. | Start with a covered live match; subscribe to the point/event stream; persist provider match id, event sequence or source timestamp, receipt UTC time, score state, reconnect gaps, and a deterministic crosswalk to the price feed. | SOURCED (cost; cadence; partial terms) |

The table is exhaustive over the four candidates named by S215 and the S252
specification. It makes no capture or calibration claim: no candidate has yet
demonstrated a timestamp-aligned, point-state-to-price join on this corpus.

## Reproduction note

Reopen this public memo, locate its one table, and count four data rows. For
each row, verify that Cost, Cadence, Terms/ToS, Minimum viable capture, and
Sourced-or-unsourced flag contain non-whitespace text. The quoted premise
output can be reproduced with the read-only S215 row-group classification path;
it requires no evaluator, preregistration, charge, or ledger access.

## NOT VERIFIED

- No provider account or coverage-matrix entitlement was obtained.
- No live match capture tested source-time ordering, reconnect behavior, or a
  provider-to-price match-key crosswalk.
- No score, model, or calibration comparison was run.

Recommendation: no feed recommended.
