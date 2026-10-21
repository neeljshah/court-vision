# How stale is our in-play view? A latency readout from committed ledgers

Neel Shah, CourtVision. Operations readout; paper only. Drafted 2026-10-20.

**Summary.** This paper measures how far behind the game our in-play state capture runs: the time
from the official play clock to the moment our recorder held the response. Every table below is
written by one script from tracked JSON files under `docs/evidence/forward/`, which a reader can
re-run without the private engine (section 7). MLB is the only sport with enough nights to pool.
NFL and NCAAF are reported per night and labelled INSUFFICIENT. NBA, soccer and tennis carry no
play-clock events in these ledgers, so their feed latency is not measured here. Latency describes
how stale our view is. It says nothing about achievable results, and no such statement is made.

## 1. The question

When the desk prices a live game, how old is the state it is pricing from, and how does that age
compare with the 15 s receipt-age split that the sealed S542 staleness backstop is read out at?

## 2. Data

- **Nightly latency ledgers (S663, schema `s663_latency_ledger_v1`).**
  `docs/evidence/forward/latency/*_latency_ledger.json`, one per night. The script reads all tracked
  ledgers (Table 1 header, appendix). Each ledger
  stores, per game and pooled per sport, quantiles of receipt minus play clock on a 0.5 s bin grid,
  counts of events, a book-moved-first numerator and denominator, and its own per-game floor flag.
  Ledgers store quantiles, not raw lags, so a true pooled quantile across nights cannot be rebuilt.
  Table 1 therefore gives the spread (min / median / max) of the nightly quantiles.
- **S542 arm M2 read-outs.** `docs/evidence/forward/model2/m2/2026-*.json`. Each live cell counts
  ticks by our receipt age (state receipt minus the receipt of the book we used), split at
  `fresh <= 15 s < stale` (the `age_label` field of every read-out). Table 3 sums the `live`,
  `segment = all` cells.
- **Gaps.** Calendar nights in the ledger span with no committed ledger are listed in the
  generated block. The operator issue file `docs/evidence/forward/issues/2026-09-29.md` records a
  books capture_outage at 09-28T15:21, night_partial on 09-26, and schedule_missing on 09-27 and 09-28. The ledger set does
  not record a cause for 10-11.
- **Sports.** Whatever the ledgers list (Table 1). MLB uses the statsapi REST feed. Every other
  sport uses the ESPN scoreboard, which carries no play clock for NBA, soccer or tennis.

## 3. Method

- **Receipt minus play clock** (the ledger's `receipt_minus_event`): recorder response-end time
  minus the source play clock, per S592 event (a new play id; a revisited play id still counts). Negative lags are kept.
  This is the capture leg only. Serve timestamps are not in any committed ledger, so the leg from
  receipt to a served number is not measured here.
- **Clock offset.** No offset journal exists on any night (generated block), so every row is
  `status: offset unmeasured` (replay status). The recorder clock is compared with a source clock it was never synchronised
  with. The S664 bound covers recorder versus UTC only and is never applied as a correction. A
  constant offset would shift every quantile by the same amount.
- **Pooling rule.** A sport is POOLED only when at least 10 nights carry events (`docs/evidence/harness/QUANT_EVIDENCE_BUILD_SLATE_2026-10-06.md`, section R7). Otherwise it is INSUFFICIENT and shown per night only.
- **Book-moved-first share.** The share of events where the venue book snapshot changed before our
  state receipt. Both instants are on the recorder clock, and a change inside the window may belong
  to a later play. It is shown with a game-clustered bootstrap interval. It is descriptive only. The interval contains 0.5, so neither ordering is established. The book time is our own snapshot receipt, not the venue's update time, so the complement is not evidence that our feed leads the venue. It is not an information advantage and not a pricing input.
- **Floor.** A night and sport whose games all sit under the ledger's per-game floor are labelled
  UNDERPOWERED. Rows the ledger refused (no events, no source clock) keep the ledger's reason.
- **Snapshot cadence.** NOT MEASURED. No committed receipt records per-minute capture counts in the
  focus windows. The ledgers' `max_wait_s` constant records the poll wait, not a realised cadence.

## 4. Results

<!-- BEGIN GENERATED results -->
Ledgers read: 20 nights, 2026-09-24 to 2026-10-16. Calendar nights in that span with no committed ledger: 3 (2026-09-27, 2026-09-28, 2026-10-11). Offset journal present on 0 nights.

Table 1. Receipt minus play clock (seconds), per sport, across nights. Nightly quantiles are summarised as min / median / max across nights; a sport with fewer than 10 nights carrying events is INSUFFICIENT.

| sport | feed | nights listed | nights with events | events n | p50 min/med/max | p90 min/med/max | p99 min/med/max | verdict |
|---|---|---|---|---|---|---|---|---|
| mlb | statsapi_rest | 18 | 17 | 11710 | 17.0 / 18.5 / 24.0 | 23.5 / 26.5 / 40.0 | 29.0 / 33.5 / 59.5 | POOLED |
| nba | espn_scoreboard | 9 | 0 | 0 | - | - | - | INSUFFICIENT |
| ncaaf | espn_scoreboard | 1 | 1 | 47 | 35.5 / 35.5 / 35.5 | 45.5 / 45.5 / 45.5 | 57.0 / 57.0 / 57.0 | INSUFFICIENT |
| nfl | espn_scoreboard | 6 | 5 | 733 | 36.5 / 40.0 / 41.5 | 50.0 / 53.5 / 57.5 | 61.5 / 76.5 / 106.5 | INSUFFICIENT |
| soccer | espn_scoreboard | 3 | 0 | 0 | - | - | - | INSUFFICIENT |
| tennis | espn_scoreboard | 2 | 0 | 0 | - | - | - | INSUFFICIENT |

Table 2. Book-moved-first share (POOLED sports only; descriptive, game-clustered percentile bootstrap, 2000 reps, seed 20261020).

| sport | games | num / den | share | 95% interval |
|---|---|---|---|---|
| mlb | 30 | 1637 / 3388 | 0.4832 | [0.4498, 0.5165] |

The interval contains 0.5, so neither ordering is established. The book time is our own snapshot receipt, not the venue's update time, so the complement is not evidence that our feed leads the venue. It is not an information advantage and not a pricing input.

Table 3. Live ticks by our receipt age at the S542 read-out's 15 s split (fresh <= 15 s < stale), summed over the committed M2 read-out nights.

| sport | read-out nights | fresh ticks | stale ticks | stale share |
|---|---|---|---|---|
| mlb | 9 | 5823 | 6001 | 0.5075 |
| nba | 3 | 2205 | 2676 | 0.5482 |
| nfl | 3 | 959 | 1948 | 0.6701 |
| soccer | 2 | 1752 | 1629 | 0.4818 |

Table 4. Per night and sport (receipt minus play clock, seconds). UNDERPOWERED = every game on that night is under the ledger's own per-game floor.

| night | sport | feed | games | events n | p50 | p90 | p99 | label |
|---|---|---|---|---|---|---|---|---|
| 2026-09-24 | mlb | statsapi_rest | 9 | 1132 | 22.5 | 37.5 | 58.5 | ok |
| 2026-09-25 | mlb | statsapi_rest | 20 | 2069 | 23.0 | 36.5 | 54.5 | ok |
| 2026-09-26 | mlb | statsapi_rest | 15 | 1352 | 24.0 | 40.0 | 59.5 | ok |
| 2026-09-29 | mlb | statsapi_rest | 3 | 652 | 19.0 | 26.5 | 34.0 | ok |
| 2026-09-29 | nfl | espn_scoreboard | 1 | 0 | - | - | - | NO_SOURCE_CLOCK |
| 2026-09-30 | mlb | statsapi_rest | 6 | 1484 | 19.5 | 27.5 | 34.0 | ok |
| 2026-10-01 | mlb | statsapi_rest | 4 | 244 | 18.5 | 26.5 | 34.0 | ok |
| 2026-10-02 | mlb | statsapi_rest | 1 | 0 | - | - | - | NO_EVENTS |
| 2026-10-03 | mlb | statsapi_rest | 2 | 573 | 18.5 | 26.5 | 38.5 | ok |
| 2026-10-04 | nfl | espn_scoreboard | 8 | 195 | 39.5 | 57.5 | 106.5 | UNDERPOWERED |
| 2026-10-05 | mlb | statsapi_rest | 2 | 341 | 18.5 | 25.0 | 31.0 | ok |
| 2026-10-06 | mlb | statsapi_rest | 3 | 580 | 18.0 | 25.0 | 31.5 | ok |
| 2026-10-06 | nfl | espn_scoreboard | 1 | 179 | 36.5 | 50.5 | 76.5 | ok |
| 2026-10-07 | mlb | statsapi_rest | 5 | 1087 | 19.0 | 28.0 | 36.0 | ok |
| 2026-10-07 | nba | espn_scoreboard | 5 | 0 | - | - | - | NO_EVENTS |
| 2026-10-08 | mlb | statsapi_rest | 4 | 337 | 17.5 | 24.0 | 30.0 | ok |
| 2026-10-08 | nba | espn_scoreboard | 8 | 0 | - | - | - | NO_EVENTS |
| 2026-10-08 | tennis | espn_scoreboard | 4 | 0 | - | - | - | NO_EVENTS |
| 2026-10-09 | mlb | statsapi_rest | 1 | 272 | 19.5 | 27.5 | 33.5 | ok |
| 2026-10-09 | nba | espn_scoreboard | 6 | 0 | - | - | - | NO_EVENTS |
| 2026-10-09 | nfl | espn_scoreboard | 1 | 108 | 41.5 | 53.5 | 61.5 | ok |
| 2026-10-09 | soccer | espn_scoreboard | 3 | 0 | - | - | - | NO_EVENTS |
| 2026-10-09 | tennis | espn_scoreboard | 8 | 0 | - | - | - | NO_EVENTS |
| 2026-10-10 | nba | espn_scoreboard | 1 | 0 | - | - | - | NO_EVENTS |
| 2026-10-10 | ncaaf | espn_scoreboard | 1 | 47 | 35.5 | 45.5 | 57.0 | ok |
| 2026-10-12 | mlb | statsapi_rest | 2 | 327 | 17.5 | 24.5 | 29.0 | ok |
| 2026-10-12 | nba | espn_scoreboard | 4 | 0 | - | - | - | NO_EVENTS |
| 2026-10-12 | soccer | espn_scoreboard | 4 | 0 | - | - | - | NO_EVENTS |
| 2026-10-13 | mlb | statsapi_rest | 3 | 190 | 17.5 | 25.0 | 31.5 | ok |
| 2026-10-13 | nba | espn_scoreboard | 5 | 0 | - | - | - | NO_EVENTS |
| 2026-10-13 | nfl | espn_scoreboard | 1 | 60 | 40.0 | 50.0 | 71.0 | ok |
| 2026-10-13 | soccer | espn_scoreboard | 7 | 0 | - | - | - | NO_EVENTS |
| 2026-10-14 | mlb | statsapi_rest | 2 | 334 | 17.0 | 24.5 | 30.0 | ok |
| 2026-10-14 | nba | espn_scoreboard | 7 | 0 | - | - | - | NO_EVENTS |
| 2026-10-15 | mlb | statsapi_rest | 3 | 354 | 17.5 | 25.5 | 30.0 | ok |
| 2026-10-15 | nba | espn_scoreboard | 7 | 0 | - | - | - | NO_EVENTS |
| 2026-10-16 | mlb | statsapi_rest | 1 | 382 | 17.0 | 23.5 | 31.0 | ok |
| 2026-10-16 | nba | espn_scoreboard | 2 | 0 | - | - | - | NO_EVENTS |
| 2026-10-16 | nfl | espn_scoreboard | 1 | 191 | 40.5 | 54.0 | 85.5 | ok |
<!-- END GENERATED results -->

## 5. What it means for pricing in play

Gate A-0 ([`GATE_A0_2026-09-14.md`](../evidence/ingame/GATE_A0_2026-09-14.md)) found that the
in-game models trail the contemporaneous venue mid on identical ticks (verdict BEHIND on MLB and
soccer). This readout is consistent with one reason for that. Our state arrives seconds after the
play (Table 1), while the venue book often moves within the same window (Table 2). A model fed this capture can price from a view older than the mid. This readout does not measure the venue's own latency, so it does not establish how often that happens.

The sealed S542 replay (`docs/evidence/RESULTS_LEDGER_SYSTEM.md`, 2026-09-29 row) returned
status: accept (staleness backstop only). Its projection recovers part of the loss from a stale price and is
never ahead of a fresh one. Table 3 shows how often our live ticks fall on the stale side of the
15 s split, which is when that backstop applies at all. The S662 push probe (same ledger,
2026-09-30 row, INSUFFICIENT at 2 games) suggests that a push feed would shorten the MLB capture
leg. No figure from it is pooled here.

Nothing in this section is a new claim. The tables measure freshness. They make no claim about
results achievable on any venue.

## 6. Limitations

- Clock offset is unmeasured on every night (section 3). Quantiles are relative to an
  unsynchronised source clock.
- Only the capture leg is measured. The serve leg and the venue's own book latency are not.
- Ledgers keep quantiles, not raw lags. Cross-night figures are spreads of nightly quantiles, not
  pooled quantiles. The maximum shown is the largest nightly p99, not the largest single lag.
- MLB is postseason-heavy after 09-30, with few games per night. NFL and NCAAF have too few nights
  to pool. NBA, soccer and tennis have no play-clock events in these ledgers at all.
- Table 3 measures receipt age at the read-out, on M2 read-out nights only, and covers fewer nights
  than the ledgers.
- The book-moved-first share mixes plays: a book change counted for one event may belong to the next.

## 7. Reproduce

From the repository root, with Python 3.10+ and numpy:

    python -m scripts.platformkit.eval_gate.inplay_latency_paper --repo-root . --check

`UP_TO_DATE` (exit 0) means the tables and `docs/papers/out/inplay_latency_2026.json` match a fresh
recompute from the files below. Drop `--check` to rewrite them. Only the generated blocks change.
Tests: `python -m pytest scripts/platformkit/eval_gate/test_inplay_latency_paper.py -q`.

## Appendix: input files and hashes

<!-- BEGIN GENERATED appendix -->
| file | sha256 (CRLF normalised to LF) |
|---|---|
| `docs/evidence/forward/latency/2026-09-24_2026-09-24_latency_ledger.json` | `99b917db1390c41cec68fb65ac8957b057cb6fa66e82a671ce98d485f6e8dcb0` |
| `docs/evidence/forward/latency/2026-09-25_2026-09-25_latency_ledger.json` | `9b0e945fbf0d7b854c47fb6761c8c51e4db9c6d51d7896c002352db8313d4ff9` |
| `docs/evidence/forward/latency/2026-09-26_2026-09-26_latency_ledger.json` | `551bac23a57f4a9109bc5f2c341369bf5ae7f3bc98cae95453a56399779b9a1a` |
| `docs/evidence/forward/latency/2026-09-29_2026-09-29_latency_ledger.json` | `5382961bcdf4c5f3bf03f8a133052146083bdc7674a904a6f777b12aa39321c4` |
| `docs/evidence/forward/latency/2026-09-30_2026-09-30_latency_ledger.json` | `732a9662305ba3e3838e4e0de1ea0642fed7fe0459971dfb1899586b97bad159` |
| `docs/evidence/forward/latency/2026-10-01_2026-10-01_latency_ledger.json` | `6c802fac65b7f4d8cbec4b7f421c16c9cc02207d03e651e3ceba3e79a171269a` |
| `docs/evidence/forward/latency/2026-10-02_2026-10-02_latency_ledger.json` | `5fe85c4f7f8dcb17bb904407eb5d53013dd8b766dfddf16ee10068e0f778462a` |
| `docs/evidence/forward/latency/2026-10-03_2026-10-03_latency_ledger.json` | `0a1632d701109dee7ad3bec93e60d6980447695417c9f145f45cabf525de0dc2` |
| `docs/evidence/forward/latency/2026-10-04_2026-10-04_latency_ledger.json` | `e6d09a9cca018c2b8d4934714fb93968ad9fb0be0801f7393903827e68ae4e74` |
| `docs/evidence/forward/latency/2026-10-05_2026-10-05_latency_ledger.json` | `d05f59467531295679d93697f6ce595501bddfa0797de338b39edfeb46b9dbc2` |
| `docs/evidence/forward/latency/2026-10-06_2026-10-06_latency_ledger.json` | `eec378143437c9d1a3cdc3f4727fdb0197de87beecf4305acdc89a77d49b2f8e` |
| `docs/evidence/forward/latency/2026-10-07_2026-10-07_latency_ledger.json` | `efdd87daa2f7d7dd2e6791031274da635202b1b8574d3a88a0342d357d56bef5` |
| `docs/evidence/forward/latency/2026-10-08_2026-10-08_latency_ledger.json` | `4f29f480d07fe59c2b46126b33790942dc72769ed4591dbb8e0db1676b9399ff` |
| `docs/evidence/forward/latency/2026-10-09_2026-10-09_latency_ledger.json` | `89525ef2a3e1f8321c5868ff6771f79c6b90503de5c9a7ebe629f531b29243a2` |
| `docs/evidence/forward/latency/2026-10-10_2026-10-10_latency_ledger.json` | `f35c4bbc7ec22ba974fda33cd0ada1f98bb202dee5f750a5c38aeb7d666ad9da` |
| `docs/evidence/forward/latency/2026-10-12_2026-10-12_latency_ledger.json` | `78ab542a871bb06a085da795e3d2116bad1241dac520c12d58d566407335f388` |
| `docs/evidence/forward/latency/2026-10-13_2026-10-13_latency_ledger.json` | `0e52de9cdd47c5dfe4d30bc95fd3ee56e1399c34198fa8918a8ff798023f17b9` |
| `docs/evidence/forward/latency/2026-10-14_2026-10-14_latency_ledger.json` | `32a8df4892949b2b8c40d434739748816854c91171ace6a67b7357433898077f` |
| `docs/evidence/forward/latency/2026-10-15_2026-10-15_latency_ledger.json` | `e14a8369636d3f8777a07ba660a8a95211d79cfc952a140688fdec3106482841` |
| `docs/evidence/forward/latency/2026-10-16_2026-10-16_latency_ledger.json` | `482c8b41d5592d6b63adac2a5fa8417b6d14f6a12f6cab91eee478ae5154513b` |
| `docs/evidence/forward/model2/m2/2026-10-02.json` | `2f384eb126750788ef5a116c54ad9e049f8ac3e3ae6694bac2db4c86f35be784` |
| `docs/evidence/forward/model2/m2/2026-10-03.json` | `caf77a4e0869eafdae3832083bed8724b155be3c9e424619c1bc9124c3f3b8e0` |
| `docs/evidence/forward/model2/m2/2026-10-04.json` | `d04956025a4012effff25c78909737cc47f812f60ddbf4b5559291f05e0c2dd9` |
| `docs/evidence/forward/model2/m2/2026-10-05.json` | `5a35b8b8132f404b04a594ceb72e43f943172548cfb3b2936629fdd1323973da` |
| `docs/evidence/forward/model2/m2/2026-10-06.json` | `89e10276e043cecd4c8f800a2a96825ff957d5b4715ee9950b2db5e59e66b543` |
| `docs/evidence/forward/model2/m2/2026-10-07.json` | `7b95bb218829c0525ad41ae138d3ca3f33745d47985ea07fb215db8ef3611351` |
| `docs/evidence/forward/model2/m2/2026-10-08.json` | `a40187874692ce2b42d06af08bb4cef3dba131b8aa03987fde0ebc0364bc47b1` |
| `docs/evidence/forward/model2/m2/2026-10-09.json` | `85dccf8de774f63a1f96c4b3af59aa8f896a5012e73706b074b6f1dfafe84fad` |
| `docs/evidence/forward/model2/m2/2026-10-10.json` | `9cbb2db82d6bcedf041858df317021847a7eed56081c9ded01e4353e82d8d051` |
| `docs/evidence/forward/model2/m2/2026-10-12.json` | `73a6d10e1103811fb9e083dba699e3a5cdc70649e30624c521e8262c58e166c3` |
| `docs/evidence/forward/model2/m2/2026-10-16.json` | `001639d62556f7033b0e3e46a49d10ad332207aa8a09150ffb4c536bbbd26873` |
<!-- END GENERATED appendix -->
