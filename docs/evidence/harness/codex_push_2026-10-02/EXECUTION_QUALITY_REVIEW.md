## Verdict

No. The desk has useful conservative components, but a paper fill record is not yet transferable to a real venue. The primary blockers are zero-latency fill-realism runs, immediate cancellation in the direct paper path, incomplete full-game depth/tape coverage, and no completed weekly record with qualified or fill-bearing games. [C2] [C4]

Numeric commands:

```powershell
# C2: current fill-realism counts and assumptions
python -c "import json; d=json.load(open('docs/evidence/forward/fill_realism/2026-09-30.json')); print(d['assumptions']); [print(life,g,x['quotes_placed'],x['fills_credited'],round(100*x['fills_credited']/x['quotes_placed'],4),x['by_fill_basis'],x['partial_fills'],x['unknown_queue'],x['quote_life_expiry']) for life,z in d['quote_life'].items() for g,x in z['grid'].items() if g=='1']"

# C3: execution-quality receipt
python -c "import json; d=json.load(open('docs/evidence/forward/exec_quality/2026-09-22_2026-09-26.json')); print(d['census'],d['source_receipt_lag_s'],d['pools']['mlb'])"

# C4: weekly record
python -c "import json; d=json.load(open('docs/evidence/forward/weeks/2026-W39_maker_forward.json')); print(d['status'],d['missing_dates'],d['families'])"

# C5: sealed replay contract and execution register
Get-Content -Raw docs/evidence/forward/exec_policy/PREREG_S551.json
Select-String -Path docs/evidence/HARNESS_GAPS_2026-09-03.md -Pattern "fill|queue|markout|maker|latency" -CaseSensitive:$false
```

## 1. Fill model as built

There are two materially different paths.

| Topic | Direct paper maker | Archive/replay model |
|---|---|---|
| Order creation | One-contract YES/NO order, rounded to whole cents. `paper_maker.py:25-39,63-71,189-195` | Quote events carry price, quantity, submit/cancel times and replacements. `tape_fill_sim.py:105-117` |
| Queue position | No queue model. A touch explicitly does not fill. `paper_maker.py:131-141` | Queue ahead is the latest displayed size at the quote price at submit; absent/invalid depth becomes a 1,000,000-contract sentinel. `tape_fill_sim.py:53-73,121,167-169` |
| Fill rule | A later book must strictly trade through the quote; the system then creates a synthetic crossing book and fills at the resting price. It does not require a captured trade. `paper_maker.py:131-155,240-251` | Opposite-side captured prints fill only while strictly inside arrival/end time and at or below quote price. Through prints fill immediately; touch prints first deplete displayed queue. `tape_fill_sim.py:207-274` |
| Latency | No submission or cancel latency is applied in the direct path. `paper_maker.py:191-195,220-247` | Generic simulator accepts delays, but current fill-realism artifacts set both to zero. `tape_fill_sim.py:119-123,163-164`; [C2] |
| Partial fills | Direct path has quantity one, so its record cannot establish a partial-fill distribution. `paper_maker.py:25-39` | Simulator supports partial quantities and cumulative fees. `tape_fill_sim.py:232-274` |
| Cancel race | Suspension and TTL call cancel immediately. The mock can simulate a race only when explicitly configured; the maker adapter does not configure it. `paper_maker.py:220-227`; `mock_exchange.py:172-186` | Sealed S551 replay applies six-second submit and cancel latency and counts fills during pending cancellation. `exec_policy_replay.py:147-210`; [C5] |
| Fees | Kalshi maker formula is modeled as a whole-order, upward-cent-rounded fee. `venue_fees.py:71-73,108-124` | Per-fill incremental fee is charged from cumulative filled quantity. `tape_fill_sim.py:237-274` |
| Tick/spread | Whole-cent ticks. If only a mid exists, assumes a one-cent half-spread. The code itself labels this optimistic when actual spreads widen. `paper_maker.py:41-48,63-71` | Replay quote engine also fixes a one-cent tick. `quote_engine.py:31,69-90` |
| Adverse selection | A fill record is later marked fee-net of a later mid, but the direct fill decision is snapshot-through rather than tape-confirmed. `paper_maker.py:158-173`; `markout.py:35-57` | Receipt computes through/depletion splits and causal markouts when coverage permits. `exec_quality_audit.py` and `exec_policy_replay.py:192-210` |

## 2. Optimism ledger

Ranked by likely execution-quality impact.

1. Zero submission and cancellation latency in the current fill-realism artifacts. Both are zero in the latest report. This lets orders arrive before a real acknowledgement and lets cancels win before fills that could occur during the race. Bound it with receipt-time books, state rows, and tape; S551's sealed replay uses six seconds for each latency. [C2] [C5]

2. Direct paper fills infer a fill from a later book crossing, not from a matched captured aggressor trade. A displayed book can move because liquidity cancels or the snapshot misses the actual queue sequence. This can create false fills at the resting price. Bound it with tape-versus-snapshot agreement and only count tape-supported fills.

3. Direct cancellation is immediate, while observed state receipt lag has a 21.867-second median and 34.064-second P90 in the main MLB receipt. A state-triggered pull can therefore react after the venue book has moved. [C3]

4. The fixed one-cent half-spread for mid-only ticks is optimistic during wider or late-game books. The code documents this limitation. Per-tick captured spread/depth can bound it, but depth coverage is incomplete. `paper_maker.py:41-48`.

5. Current direct records are quantity-one only. That avoids estimating partial-fill and queue depletion behavior, but makes any inference about larger resting size unsupported. The tape simulator can model partials; the paper maker cannot measure them. `paper_maker.py:25-39`; `tape_fill_sim.py:232-274`.

6. Queue depth is only a displayed snapshot at submit. It does not identify hidden liquidity, cancellations ahead, exact matching priority, or the desk's actual queue rank. Missing queue is conservatively assigned a 1,000,000-contract sentinel, so this particular fallback suppresses fills rather than inflating them; the known-depth assumption remains uncalibrated. `tape_fill_sim.py:53-73`.

7. Fee arithmetic is implemented, and one-contract cent rounding is conservative at interior prices, but account-specific precision, batch behavior, and any applicable series exception are not verified. This is an uncertainty rather than demonstrated optimism. `venue_fees.py:8-20`; `paper_maker.py:27-38`.

8. Replacement priority loss is modeled in S551, but not established from a real venue order lifecycle. The sealed replay removes priority after replacement; the direct path has no realistic venue acknowledgement/cancel confirmation. `exec_policy_replay.py:163-184`; `lifecycle.py:209-266`.

## 3. What the evidence says now

The latest fill-realism artifact, dated 2026-09-30, is explicitly count-only and assumes zero submit/cancel latency. At the one-times displayed-queue scenario:

- Five-second quote life: 7 fills from 16,292 quotes, 0.0430 percent; all 7 were through fills; 0 partials; 14,118 expired. [C2]
- Thirty-second quote life: 19 fills from 16,292 quotes, 0.1166 percent; 18 through and 1 touch-queue fill; 0 partials; 795 expired. [C2]
- The same run recorded 9,076 unknown-queue quote contexts. That makes these counts unsuitable as a calibrated fill-rate estimate. [C2]

The stronger execution-quality receipt covers 19 served entries from 2026-09-22 through 2026-09-26: 8 MLB games OK, 9 with no live state, 1 with no depth, and 1 tape-missing. [C3]

Its independent one-contract join proxies are useful diagnostics, not desk throughput:

- At touch: 60-second fill probability 0.3358 across 8 games and 2,064 opportunities; 300-second probability 0.6042. [C3]
- Engine-priced: 60-second fill probability 0.1345 across 8 games and 1,844 opportunities; 300-second probability 0.4094. [C3]
- About 92.64 percent of touch fills and 93.55 percent of engine fills were through prints, across 7 games. [C3]
- Touch simulated fee-net 60-second markout was -0.6746 cents per contract, 90 percent interval [-0.8578, -0.5026], across 7 games and 676 scored fill-horizons. [C3]
- Engine simulated fee-net 60-second markout was -0.1458 cents, interval [-0.6059, 0.3110], across 7 games and 240 scored fill-horizons. This is not distinguishable from zero at that interval. [C3]
- For play events, the book had moved before state receipt 50.90 percent of the time versus 43.76 percent in matched-lag controls. [C3]

The subsequent 2026-09-27 through 2026-09-29 receipt has only 2 OK MLB games and 1 tape-missing NFL game; it correctly marks all pools insufficient. [C3]

There are no completed weekly records. Week 39 has 6 scheduled MLB games, 0 qualified games, and 0 fill-bearing games; all sport families fail their weekly floor of 4. [C4] Therefore no aggregate paper markout or transfer conclusion is supported.

## 4. Highest-value improvements

1. Receipt-time causal fill ledger
   - Goal: make every paper fill tape-supported and receipt-time causal.
   - Files: `exec_policy_replay.py`, `tape_fill_sim.py`, `live_shadow_fills.py`.
   - Buildable today: yes, offline against tape-complete archive windows.
   - Contract: no fill without an eligible opposite-side print after simulated arrival.
   - Acceptance: sealed S551 comparison, at least 30 paired games per cell.
   - Acceptance: at most 20 percent missing primary-horizon marks.
   - Control: retain through-only and displayed-depletion scenarios.
   - Control: preserve game-paired comparison and fee-inclusive 60-second markout.
   - Status: machinery/prereg exist; confirmatory scoring does not.

2. Full-game depth and near-real-time tape capture
   - Goal: eliminate focus-hour and backfill artifacts from execution measurement.
   - Files: capture-owner paths; S556/S597/S598 interface.
   - Buildable today: no; requires new capture behavior and prospective evidence.
   - Contract: timestamp book, state, and tape at independent receipt times.
   - Acceptance: proposed 95 percent live-game depth coverage across at least 30 games.
   - Acceptance: proposed tape receipt P90 at or below 2 seconds.
   - Control: report all gaps, not just successful games.
   - Control: fail execution scoring when tape completeness fails.
   - Rationale: current tape can arrive minutes to hours late. [C5]

3. Real cancellation lifecycle receipt
   - Goal: distinguish requested cancel, acknowledged cancel, and fill-before-cancel.
   - Files: `executor/lifecycle.py`, `live_shadow_fills.py`, reconciliation paths.
   - Buildable today: partly; receipt schema is buildable, venue confirmation is not.
   - Contract: each intent has submit, acknowledgement, terminal fill/cancel, and reason.
   - Acceptance: 100 percent linkage on at least 30 tape-complete paper games.
   - Acceptance: zero unclassified terminal orders.
   - Control: unknown cancellation remains exposed inventory, never assumed cancelled.
   - Control: keep pending-cancel fills eligible.
   - Rationale: immediate mock cancellation is not a transfer model.

4. Measured latency distribution, not a constant
   - Goal: parameterize submit/cancel timing from observed component delays.
   - Files: `exec_policy_prereg.py`, `exec_policy_replay.py`, latency receipts.
   - Buildable today: historical receipt-lag decomposition only.
   - Contract: separate state source delay, poll cadence, book receipt, and order lifecycle.
   - Acceptance: report P50/P90/P99 by sport and event type for 30 games.
   - Acceptance: freeze replay parameters before its next scoring window.
   - Control: score sensitivity at P50, P90, and P99, not a single favorable value.
   - Control: no tape-driven live trigger until tape is timely.
   - Rationale: observed state receipt lag is already material. [C3]

5. Queue uncertainty calibration and sensitivity
   - Goal: replace a single displayed-size assumption with bounded queue scenarios.
   - Files: `tape_fill_sim.py`, `touch_queue_sensitivity.py`, `fill_realism.py`.
   - Buildable today: yes, offline using stored snapshots and trades.
   - Contract: report no-depth, displayed-depth, and conservative queue-ahead arms.
   - Acceptance: at least 30 tape-complete games and all arms retained in every report.
   - Acceptance: report fill-rate range, partial-fill range, and 60-second markout range.
   - Control: do not select the most favorable queue arm after observing results.
   - Control: treat unknown depth as insufficient for calibration, not as evidence.
   - Rationale: 9,076 unknown queues occur in the latest artifact. [C2]

6. Instrument-specific book/tick/spread contract
   - Goal: stop using a universal one-cent half-spread when only a mid is present.
   - Files: `paper_maker.py`, `quote_engine.py`, capture-book adapter.
   - Buildable today: partly; raw book data exists only in limited coverage.
   - Contract: record instrument tick, best bid/ask, depth, and book age per decision.
   - Acceptance: proposed 100 percent of scored decisions have explicit bid/ask and tick.
   - Acceptance: at least 30 games per sport before a sport-specific default is allowed.
   - Control: mid-only records are withheld from fill-quality scoring.
   - Control: preserve passive-price checks.
   - Rationale: the fixed spread is documented as optimistic. `paper_maker.py:41-48`.

7. Size and partial-fill paper ladder
   - Goal: make paper records explicit about the size regime they represent.
   - Files: `paper_maker.py`, `quote_engine.py`, `tape_fill_sim.py`.
   - Buildable today: simulator work yes; venue-valid sizing evidence no.
   - Contract: record requested, filled, cancelled, and remaining quantity separately.
   - Acceptance: no size greater than one is reported transferable without partial-fill evidence.
   - Acceptance: at least 30 games with size-stratified replay results before expansion.
   - Control: do not increase size to exploit fee rounding.
   - Control: retain the current one-unit baseline.
   - Rationale: current direct paper quotes are one unit. `paper_maker.py:25-39`.

8. Fee and account-rule certification
   - Goal: verify that reported fee increments equal the applicable venue/account rule.
   - Files: `venue_fees.py`, `venue_fees_decimal.py`, fee certification modules.
   - Buildable today: code review and historical reconciliation yes; account confirmation no.
   - Contract: store fee schedule version and exact whole-order rounding inputs.
   - Acceptance: 100 percent of filled paper rows reconcile to the frozen fee reference.
   - Acceptance: evaluate at least 30 distinct price/size batches.
   - Control: reject unknown fee tiers or instrument exceptions.
   - Control: do not infer multi-unit cost from one-unit results.
   - Rationale: current fee formula is modeled but account precision is unverified.

9. Automated evidence cadence and failure visibility
   - Goal: prevent a paper record from silently omitting execution receipts.
   - Files: proposed S558 paper-night/tick integration.
   - Buildable today: yes for report scheduling; no for missing capture evidence.
   - Contract: nightly fill, coverage, latency, and reconciliation receipts.
   - Acceptance: 8 consecutive complete weeks with at least 4 qualified games each.
   - Acceptance: at least 30 fill-bearing games in the sport-specific family.
   - Control: missing receipt means incomplete, not zero fills or neutral markout.
   - Control: retain separate sport strata.
   - Rationale: the current weekly record has 0 completed weeks. [C4]

## 5. Pre-live evidence checklist

This is an evidence gate list only. It is not a recommendation to submit a real order.

- A sealed, post-seal S551 result with at least 30 paired tape-complete games in every non-baseline cell; all queue scenarios reported; no hidden arm selection. [C5]
- At least 8 complete weekly records, each meeting the existing 4-game weekly floor, with at least 30 fill-bearing games for the sport. [C4]
- Full-game book-depth and tape completeness reported for every eligible game; no selective exclusion of stale, missing, or post-focus periods.
- Near-real-time receipt evidence for state, book, and tape, including P50/P90/P99 latency by sport and event type; replay sensitivity uses those distributions.
- Every paper intent reconciles to one terminal state: filled, confirmed cancelled, rejected, or explicitly unresolved. No assumed cancellation.
- Fee schedule version, batch rounding, tick size, and instrument constraints are certified for all scored paper fills.
- Fill-rate, partial-fill rate, and 60-second fee-inclusive markout are reported with game-cluster intervals under both through-only and displayed-depletion queue scenarios.
- No reliance on mid-only spread assumptions in scored transfer evidence, unless separately stratified and shown as insufficient.
- A prospective, continuous capture record with no unaccounted state, depth, tape, or mark gaps.
- A human owner reviews the evidence packet and unresolved limitations before any separate proposal is considered.

## 6. Not verified

- Actual venue acknowledgement latency, queue rank, matching priority, cancel acknowledgement, or cancel-race frequency.
- Whether a snapshot-through event corresponds to a tradable fill at the desk's queue position.
- A calibrated partial-fill distribution beyond one-contract paper quotes.
- Full-game depth availability or near-real-time tape availability.
- Account-specific fee precision, series exceptions, and instrument-specific tick constraints.
- Any aggregate paper markout conclusion: the weekly record has no completed week and no fill-bearing game. [C4]
- Transfer of any paper result to a real venue.