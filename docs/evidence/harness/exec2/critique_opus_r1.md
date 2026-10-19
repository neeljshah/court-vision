# EXECUTION 2.0 plan: Opus adversarial critique r1 (2026-09-29)

VERDICT: REVISE. Four headline numbers do not survive re-derivation (the 17x event lift, the "majority before receipt" reading, the 22.7 pct touch fill rate, the reading of the ~1c touch-fill markout as adverse selection). The engine 2c figure and the taker_side mapping hold.

Method: an independent streaming script (scratchpad `e2_check.py`, `e2_clock.py`; peak 36 MB; no probe import) over 2026-09-24 + 2026-09-25 shards for two 09-24 games, NYM@TEX (KXMLBGAME-26SEP241435NYMTEX-TEX, game_key 822842) and CLE@BOS (...241845CLEBOS-BOS, 824707). I also reran the tracked probe per day (main-repo copy; it differs only in CRLF line endings) for per-day cluster values. Two games is a small sample, so read the per-game values as a check on the method, not as new baselines. Paper and execution-quality language only.

## Re-derivations

| Number | Plan | Mine (NYMTEX / CLEBOS) | Verdict |
|---|---|---|---|
| (a) touch fill within 60 s | 22.7 pct (11 games) | 38.7 / 39.4 pct (probe-equivalent strict parse: 37.8 / 38.1; probe rerun on 09-24 alone: 39.9 pct) | the pooled value is wrong, see B3 |
| (a) touch markout at fill +60 s | -0.53c | -0.98 / -0.57c (strict: -1.05 / -0.65; probe on 09-24: -0.62c) | direction agrees; the meaning does not, see B5 |
| (b) play 5 s move rate | 23.4 pct | 25.8 / 25.3 pct (n 66 / 79) | agrees |
| (b) 5 s base rate | 1.4 pct | probe method 0.0 / 0.8 pct; random-time control 13.1 / 13.2 pct | artifact, see B1 |
| (c) engine behind touch | always 2c | 2c at spread 1 (662/706, 655/698); 1c at spread 2-3 (43, 42); 0c at spread 5 (1, 1) | mostly holds, see N1 |

## Findings

B1 BLOCKING. The base-rate control is a sampling artifact. `exec2_audit_cluster.py:9-26` puts the control grid ON snapshot timestamps and uses that snapshot as m0. The next snapshot is about 5.2 s away, so the 5 s window almost never contains a later snapshot, and the 15 s window holds 2 snapshots where an event window holds about 3. Events (`exec2_audit_measure.py:47-56`) fall at arbitrary times after the last snapshot. With a control at uniform random times that uses the same m0 method as the events:

- 5 s: base 13.1 / 13.2 pct vs events 25.8 / 25.3 pct.
- 15 s: 31.2 / 32.4 pct vs 45.5 / 40.5 pct.
- 30 s: 47.6 / 52.1 pct vs 62.1 / 60.8 pct.

The lift is about 1.9x at 5 s and 1.25-1.45x at 15-30 s, not 17x. The "17x" sentence and the pooled `base_move_control` must be retracted and recomputed with a random-time control. S553 must use that control.

B2 BLOCKING. "In 501 of 962 moves the book moved before our receipt" has no null. Under the null (a random time t, a lag drawn from the event lags, and the first 1c move within 120 s) the share before t+lag is 47.2 / 47.4 pct. The events give 59.0 / 57.7 pct. The excess is about 11 pp, not "the majority".

The receipt lag is mostly our own poll interval: the state poll p50 is 42.7 s on NYMTEX and 16.2 s on CLEBOS, and the receipt lag p50 is 23.7 / 23.2 s. The remedy is capture cadence (S556), not only book-driven cancels. S553 must report poll cadence and source-to-venue lag separately.

B3 BLOCKING. Games with no captured tape are counted as zero-fill games. The touch and engine fill rates pool 11 games, and at least three of them have no captured in-game prints:

- 09-29: NFL PHI@CHI and MLB PHI@ATL, 460 joins and 0 fills, caused by the trade drain lag.
- 09-22: MIL@PHI, 0 prints.
- 09-22: MIA@CHC has only 178 prints in a 360-min window. That window is also capped because no final row arrived.

Per-day probe reruns give a 60 s touch fill of 39.9 pct (09-24), 31.0 pct (09-25), 13.9 pct (09-22) and 0.0 pct (09-29). Games with tape pool to roughly 33 pct, not 22.7 pct. The engine arm (8.5 pct) and the 300 s rates are biased low the same way. Fix: treat a window without trade coverage (use the `trade_gap` and `trade_backfill_closed` drain watermarks) as censored, INSUFFICIENT and not zero. Label the NFL game separately from the MLB numbers.

B4 BLOCKING. About 10 pct of prints are dropped silently. `exec2_audit_probe.py:36-37` parses with `datetime.fromisoformat`. On Python 3.10.0 (the interpreter that ran the probe) that call rejects `created_time` values with fewer than 6 fractional digits, for example `...40.85955Z`. `:105-109` then counts them as `trade_unparsed` and drops them: 3,037 on 09-24, 1,302 on 09-22, 685 on 09-25, 534 and 244 on 09-29.

- On the two games the fix changes prints from 5,429 / 5,757 to 6,037 / 6,360, the fill rate by +0.8 to +1.3 pp and the markout by +0.07 to +0.09c.
- The dropped rows are close to a random subsample, so tape markouts are not biased but their n is understated.
- On Py3.12 (RunPod) nothing is dropped, so S550's byte-identical-rerun target fails across interpreters.
- Fix: use the existing `scripts/platformkit/execution/venue_time.parse_venue_time`, which parses the same string correctly.

B5 BLOCKING (interpretation, and it shapes S551's target). The touch "queue proxy" works as a trade-through detector. Displayed size ahead at the touch is 25k to 74k contracts. On the two games 168 of 185 touch fills (90.8 pct) came from a print through our price, and only 16 came from queue depletion. "Fill at touch within 60 s" therefore mostly means "price traded through our level within 60 s", so its -0.5 to -1.0c markout is adverse by construction and is not an estimate of a resting quote's selection cost.

Consequences:

- Any cancel rule keyed on a same-side touch tick deletes exactly those fills. S551's "+0.3c at fill rate >= half" target can then be met mechanically.
- Cancels ahead of us are ignored, so queue-depletion fills are missed and the fill rate is not "conservative" in any useful sense. It is a different quantity.

S551 must pre-register at least two queue scenarios, for example the existing `touch_queue_sensitivity.py` scenarios (displayed-ahead, partial or pro-rata cancel ahead). It must report the through-fill and depletion-fill split, and state its target per scenario.

B6 BLOCKING (look-ahead for S551 and S552). In the archive the trade tape is not available in real time:

- All in-game trade rows on both games are backfill-origin (`backfill_open: true`).
- `capture_ts - created_time` is p50 307 s / p90 1,611 s on NYMTEX and p50 3,867 s / p90 8,801 s on CLEBOS.

S551 trigger (b) ("same-side prints >= Q in last k s") and S552's feature "prints in the last 60 s" keyed on `created_time` would use information the live recorder (S515) does not have. Pre-register an availability clock (`capture_ts`) arm, or state explicitly that the feature needs a real-time tape feed that does not exist today.

Separately, the snapshot book explains a print (a yes print at the ask, a no print at the bid) in only 67 / 80 pct of cases at offset 0, rising to a peak of 72 / 84 pct at +2..+3 s (N3). A replay cancel at snapshot capture time t_s must not pre-empt a print with `created_time` in (t_s - 3 s, t_s]. Pre-register the cancel latency as at least one cadence (about 5.2 s) plus an assumed venue round-trip.

N1 NOTE. "Always exactly 2c behind" should say "2c at a 1c spread (about 94 pct of snapshots); 1c at a 2-3c spread; 0c at 5c". p10 = p90 = 2 hides the tail. The fee arithmetic is right: ceil(0.0175 * 100 * p(1-p)) = 1c at every interior p, plus the 1c pad `thresholds.py:14`.

N2 NOTE. The taker_side mapping (`exec2_audit_measure.py:71`, `:115-116`) is correct:

- NYMTEX: 864 of 904 yes prints are at or above the ask, and 162 of 172 no prints are at or below the bid.
- CLEBOS: 1,331 of 1,369 yes prints are at or above the ask, and 185 of 197 no prints are at or below the bid.
- `taker_book_side == "bid"` holds exactly when `taker_side == "yes"` (904/904 and 1,369/1,369).
- The remaining 3-6 pct is book motion between snapshots.

N3 NOTE. The clock offset between trade `created_time` and snapshot `response_end_ts` cannot be resolved below one cadence. Touch consistency peaks with the snapshot at or before `created_time` + 2 to 3 s (0.72 and 0.84), and the request-to-response time is 38-39 ms. This does not matter for the +60 s markouts. It does matter at +5 s: the tape "+5 s" markout is really +5 to +10 s, because it takes the first snapshot at or after t+5.

N4 NOTE. Duplicates: 0 duplicate trade_ids on the two games; the dedupe at `exec2_audit_probe.py:102-104` is fine. `trade_gap` and `trade_backfill_closed` records are ignored. There is only one `before_first_contact` gap per game here, but S550 must honor gaps the way `forward_replay.py:165-167` does.

N5 NOTE. The 10 s mark rule (`exec2_audit_probe.py:31,153-159`) loses only 2 to 4 of about 90 +60 s marks per game. At the 300 s fill horizon and the +600 s tape horizon, fills late in the focus hour lose their marks, so those cells skew toward early-hour fills. Report the share of missing marks per cell.

N6 NOTE (survivorship and coverage). Depth spans 61.9 / 62.0 min per game. The live window starts at the first `status == live` state row, which comes 14.1 / 21.8 min before the first play. Depth snapshots in that pregame gap are 67 of 706 and fifty-four of 698 (count spelled out for the vocabulary gate). So about 9 pct of "in-game" depth time is pregame, and the rest covers the early innings only. Start the window at the first play and label every number as first-hour.

N7 NOTE (look-ahead in the buckets). `Game.since_event` (`exec2_audit_probe.py:162-164`) buckets tape and queue rows on the SOURCE clock, which is known only about 20 s later at receipt. The buckets are not a headline, but S552 and S551 features must use the receipt clock.

N8 NOTE. MIA@CHC's live window ran to the 6 h cap (`exec2_audit_probe.py:79`) because no final row arrived. NFL PHI@CHI is pooled into the "MLB" base-rate and fill denominators.

N9 NOTE (reuse). The repo already has `tape_fill_sim.simulate_fills`, `markout_causal.markout_strict`, `touch_queue_sensitivity.py`, `venue_time.parse_venue_time` and `fill_realism*`. S550 and S551 must build on these, not re-implement them. Otherwise the S550 baseline and orchestrator 4's S516 receipt (which uses `simulate_fills` + `markout_strict`) will disagree on the same fills.

## Rows

- **S550: REVISE.**
  - Fix B1 to B4.
  - Honor trade gaps and drain watermarks.
  - Start the window at the first play.
  - Compute a random-time base rate.
  - Split sports.
  - The target "the probe's headline numbers reproduced" is wrong, because the probe numbers are wrong. Replace it with the corrected values plus a per-finding delta table against the probe.
  - Pin the timestamp parser so reruns match byte for byte across interpreters.
- **S551: REVISE.** Pre-register all of the following before any replay:
  - (1) A small fixed parameter grid (Q, k, staleness, cool-down) with no post-hoc selection, or else a split: tune on 09-22..09-25 and score only on games captured after the spec commit.
  - (2) Queue scenarios, at least two (B5), with a through/depletion fill split.
  - (3) A cancel latency of at least one snapshot cadence plus the venue round-trip; a cancel is not effective against prints created within that latency.
  - (4) Tape availability on `capture_ts`, or the trigger declared feed-dependent (B6).
  - (5) One primary metric, the fee-inclusive +60 s markout per filled contract, with fills counted per scenario.
  - (6) The S550 minimum of 20 games per cell. Only about 7 tape-bearing MLB games exist, so S551 is INSUFFICIENT by its own rule today. Say so up front.
  - The +0.3c target is partly mechanical under the current proxy (B5).
- **S552: REVISE, and defer until 20 or more tape-bearing games.**
  - Overfit risk: about 7 games and about 2k joins against 5 features.
  - The labels are about 90 pct trade-through events, so the model is really a 60 s price-move predictor.
  - "Distance from touch" alone separates 38 pct from about 9 pct, so beating a constant baseline is trivial. The baseline must be a distance- and spread-stratified empirical rate.
  - Every feature must use the receipt or availability clock (B6, N7).
  - Walk forward by date, not only leave-one-game-out: the 4 games of 09-24 share regime.
- **S553: KEEP with revisions.** Use the random-time control (B1) and report poll cadence separately from source lag (B2). Its output must not be tuned on the same games S551 is scored on.
- **S554: KEEP, stays OFF.** Pre-register the definition of sigma_cal (band edges, the source receipt) before the replay. It depends on S540 or the S515 blend, so keep it last.
- **S555: REVISE.**
  - The qty-100 fee step (0.44c vs 1c) ignores that 100 contracts at the touch sit behind 25k-74k contracts of displayed queue, and that partial fills re-round the fee per fill.
  - It needs S552 and B5's queue scenarios.
  - The inventory target must name max inventory and its measurement.
- **S556: KEEP (hand-off).** Add these measured items:
  - `status == live` starts 14-22 min before the first play.
  - Trade drain lag p50 5 to 64 min.
  - State poll cadence p50 16-43 s, which is the main driver of receipt lag.
  - The three zero-tape games.
  - The 6 h cap hit on MIA@CHC.

## Overlap with S515-S519

- S516 already produces per-arm fills and fee-netted markouts from `simulate_fills` + `markout_strict` over recorded quotes.
- S551's replay ledger duplicates that machinery offline. It should call the same simulator and markout function, and define its static arm as S515's "mid" arm (anchor=None, qty 1), so the offline and shadow receipts can be compared cell for cell.
- No file overlap is proposed. B6 (tape latency) and N6 (pregame live status) also affect S516, so pass them to orchestrator 4.
