# S551 pre-build design critique (Opus, sole critic; astra turn.failed)

VERDICT: REVISE. The core mechanics are sound: tape_fill_sim can carry the ordering
contract, and I checked that in memory. Six BLOCKING findings are all text fixes
to the spec. None needs a redesign.

Base: master 026c77413. tape_fill_sim.py was last touched at 95bb1253a, so the file
is identical to the spec's cited 186204040.

## What I checked, and how

- Scratch `sim_check.py` in this scratchpad called the real `simulate_fills` with S=C=6.0.
  - Arrival boundary: a print at 106.0 does not fill; a print at 106.5 fills (through).
  - Pending cancel: an order submitted at 90, with cancel decided at 100, fills at 105.9 and not at 106.0.
  - Replace: a touch print of 5 at t=97 depletes the displayed queue of 5. A later 1-lot at t=110 then fills
    the ORIGINAL order (touch_queue). The replacement submitted at 100 with `replaces` does NOT fill,
    because its queue is re-read at 5. Priority loss is confirmed.
  - C > S is NOT refused by the simulator (b arrives 101, a ends 106). The replay must enforce C <= S itself.
- Float boundary: arrival = parse(iso_s) + 6.0 was compared with parse(iso of s + 6 s) for
  20,000 random microsecond instants at 2026 epochs. There were 0 mismatches, so open question 5 is moot
  for whole-second latencies.
- Archive, streamed and prefiltered to NYMTEX-TEX 2026-09-24:
  - Record counts: trade 6912, snapshot 706, snapshot_bulk 13, trade_backfill_closed 81, trade_gap 1.
  - Focus snapshot gap p10/p50/p90 = 4.98 / 5.17 / 5.59 s. The span is 61.9 min, so depth covers about the first hour only.
  - 4732 of 6912 prints (68 pct) have a FRACTIONAL count_fp.
  - Side combos: (taker_side, taker_outcome_side, taker_book_side) = (yes, yes, bid) 5437 and (no, no, ask) 1475.
    Against the prior snapshot touch, taker_side yes sits at the ask 190 times vs at the bid 70 times.
    That fits the mapping that a yes-taker fills a resting NO bid (the mapping of from_s341_trade :116).
  - State for game 822842: 269 rows over 162.7 min (one row about every 36 s).
    `state_changed` is true on 180 rows. last_play_id changes 171 times, score 3, inning/half 33.
    Median gap between state_changed rows is 47.4 s, and 17 pct of gaps are under 30 s.
- make_quotes at book 49/50 with the S550 caps gives 47/52, i.e. 2c behind. Case 22 holds.
  At 2/3 the bid side is `no_passive_price` WITHOUT a `pulled` key.

## BLOCKING

B1. Pooling across dates is unspecified.
The floor, the confirmatory look and the bootstrap are "cumulative", but the CLI takes a single `--date D`,
and the ledger and receipt are keyed per D. MLB yields about 1.1 OK game per served day
(8 OK of 21 served MLB entries in the week), so no single D ever reaches the floor. Add to item 10:
"Cumulative pool: the receipt for D pools the per-game sufficient statistics of every
`docs/evidence/forward/exec_policy/<D'>.games.jsonl` with D_seal < D' < D. Each is admitted only if its
receipt `<D'>.json` carries the same prereg sha and seal, and the sidecar's sha256 equals the
`games_sha256` field recorded in that receipt (a mismatch exits 3, `prior_sidecar_mismatch`).
D's own games are then added. A game_key already present in an earlier sidecar is refused
`duplicate_game_across_dates`. The receipt lists `pooled_dates` and `pooled_games`."

B2. Case 28 cannot pass as written, and the tests would write into data/.
Case 28 runs the CLI twice for byte-equal receipts. But item 10 exits 4 on an existing
(mode, arm, scenario, D) ledger, and the ledger root is hard-coded to data/cache/exec_policy/. Add to the CLI
in item 10: "`--ledger-root PATH` (default data/cache/exec_policy/ledger), `--prereg PATH` (default
docs/evidence/forward/exec_policy/PREREG_S551.json) and `--repo-root PATH` (default the repo top level).
Every test passes tmp_path roots for all three and for --out. Case 28's two processes use two distinct
tmp ledger roots and out paths. The byte comparison is between the two receipts."
Also define "FINAL" in exit 4, or delete it: "4 = the ledger for (mode, arm, scenario, D) exists, or <D>.json exists under --out".

B3. Pin one simulate_fills call per (arm, scenario, game).
simulate_fills shares each print's budget across every quote in the call
(tape_fill_sim.py:207-274; quotes are sorted by -price then arrival at :191-192). If arms go into one call,
the arms consume each other's prints and the pairing is contaminated without any error. Add to item 6:
"Phase 2 calls simulate_fills once per (arm, scenario, game). The YES and NO sides of one arm share a call.
Quotes of different arms never share a call."

B4. The game floor must match Q7, and it must bind PAIRED games.
VERIFIER_CONTRACT Q7 says `n >= 30` binds a scored metric, and S516 uses 30 for that reason.
The spec also excludes `pair_no_fill` games, so 20 eligible games can leave, for example, 12 pairs.
The floor is sealed in the prereg, so it must be settled before the build. Replace the floor text in items 7/8 and case 31 with:
"INSUFFICIENT for a comparison cell when fewer than 30 games are PAIRED in that cell
(both arms have at least one fill; equality 30 is sufficient; Q7). The confirmatory look is the first receipt at which
EVERY non-baseline cell has >= 30 paired games. Cells are never looked at separately."
Case 31 becomes "29 vs 30 paired games".
Disclose in the memo: at about 1.1 OK MLB game per day and a single postseason, 30 pairs are unlikely before
the 2027 regular season. This is an estimate from the 09-22..09-29 census, not a measurement.

B5. The decision bar is ambiguous.
The phrase "applies to the point estimate AND the bound" has two readings: does AHEAD need a lower bound >= 0.3,
or a point estimate >= 0.3? BEHIND is also unadjusted while AHEAD is Holm-adjusted. Replace with:
"AHEAD_SINGLE_WINDOW iff all four hold: paired mean difference >= +0.3 cents (point estimate);
Holm-adjusted one-sided bootstrap p < 0.05; fill-rate ratio vs static_touch >= 0.5 (point estimate);
per-eligible-hour sum difference >= 0 (point estimate). BEHIND iff the Holm-adjusted one-sided p for
'difference < 0', computed as (1 + draws with mean >= 0) / 5001, is < 0.05. Otherwise NULL."
Both directions then use one multiplicity rule.

B6. False premise: S550 has no drain watermark and no PROVISIONAL status.
Item 9 says to "honour trade_gap / trade_backfill_closed watermarks as S550 does". S550's spec has no
watermark, no PROVISIONAL status and no `drain watermark` census field. Its census ends at NO_LIVE_STATE / NO_DEPTH /
TAPE_MISSING / OK. The archive does carry the data: a trade_backfill_closed row at 23:59:10Z has
drain_watermark 21:11:09Z, and a trade_gap row carries gap_kind, gap_start_ts and gap_end_ts. Replace with:
"S551 derives tape completeness itself, from the trade_backfill_closed and trade_gap rows its own
iter_trade_rows role returns. A game is PROVISIONAL (not counted toward the floor, excluded from
pools) when (a) the max drain_watermark over its ticker's trade_backfill_closed rows with receipt <= the run
instant is earlier than the depth-window end, or (b) any trade_gap row for the ticker has
[gap_start_ts, gap_end_ts] intersecting the depth window (a null gap_start_ts means the gap is open back to
-infinity). Counted as `tape_provisional`."
Also add the census field names to open question 1: the role names are still unconfirmed against the landed S550.

## NOTE

N1. Stale line citations in the reuse map (tape_fill_sim.py is unchanged since 95bb1253a):
arrival/end are at :163-164, not :154/:155; the `_queue` call is at :167, not :159; the replace close is at :174-190
(old end at :190), not :190-193; latencies are at :119-120, not :100-101. The quote_engine pull reasons are at
:108-127, not :107-118. The other cites check out: forward_replay :106-110 / :146, markout :44 / :108,
make_quotes :94, from_s341_trade :111, attest :149. A verifier re-reads every cite, so fix them.

N2. The latency rationale double-counts observation delay.
Decisions already happen only at snapshot RECEIPT instants, so the 5.2 s cadence is already inside "when we
knew". Adding it again to the order latency penalises the cancel arms, which are the latency-sensitive
ones. opus r1 N3's worry (a cancel at t_s must not pre-empt a print created in (t_s-3, t_s]) is
already met for ANY C >= 0, because the effective end is t_s + C > created_time.
The plan mandates ">= one cadence + round trip", so keep 6.0 as the sealed primary. Replace the second sentence of item 3 with:
"6.0 s is a conservative declared value; decisions are already taken at receipt, so the cadence part
is a deliberate margin, not a modelled delay."
Replace the sensitivity set with {(S=2.0, C=1.0) (S516-comparable, answers open question 7), (S=C=12.0)}, still descriptive and excluded from Holm.
Also require S > 0 and C > 0 (exit 2 otherwise). With both positive, the within-instant order
(match, decide, latency) is automatically honoured by the batch simulator, because no decision at t can affect (t, t+min(S,C)].

N3. Define the state trigger exactly.
In the data, state_changed true is essentially every play (180 of 269 rows; median gap 47 s). With R = 30 s,
arm (4) sits out roughly 60 pct of eligible time, and its fill-rate ratio can fail the 0.5 bar mechanically.
That outcome is legitimate, but the spec must pin it. Replace with:
"trigger = a state row with state_changed is True (the forward_replay.py:108 convention), receipt time;
score, period and play are reported as a breakdown of trigger reasons only."
Disclose that the state poll is about 36 s per row on this game.

N4. Zero inventory and filled orders.
Phase 1 cannot see fills. A fully filled order still "occupies" its (game, side) until its end, and a
refresh or cancel can target an order that has already filled. This is causal and acceptable, but it must be disclosed.
It also affects two metrics. Quote uptime = arrival to end regardless of fill (state this). Cancel counts include
cancels of already-filled orders; report `cancel_after_full_fill` from the phase-2 join.
Replace "No new order on a (game, side) before the previous one has ended" with:
"a new order's arrival is never earlier than the previous order's end on that (game, side); static arms
re-submit at the first grid instant t with t + S >= previous end."

N5. Fractional prints and the fee.
With 68 pct fractional count_fp, one-contract quotes partially fill, and each order pays a 1c ceiling on its
first slice (fee_kalshi_maker(0.05, 0.5) = 0.01 = 20c per contract on that slice; later slices pay 0).
The contract-weighted game mean is correct if computed as
sum(qty * gross_markout) - sum(fee_units), divided by sum(qty). State that formula.
The per-fill 10th percentile must be contract-weighted, or it is dominated by tiny slices.
Pass fee_units/qty into markout_strict (the value is <= 1.0 because count_fp has 2 dp).
Disclose that arms issuing more orders pay more ceilings per contract, and that this is modelled, not measured (venue_fees.py docstring :8-12).

N6. Eligibility caps and per-side eligibility.
"caps as quote_engine.py's docstring :12-20" gives no values. Replace with S550 item 10's exact caps:
room 1 per side in game_room, correlated_room and global_room; seconds_to_close 3600; game_id = game_key; sport "mlb";
now = book src_ts = decision receipt, so age 0 < STATE_AGE_CEILING_SEC mlb 5.0.
Eligibility is per (instant, side): `pulled` absent AND side_reasons[side] == "quoted".
Otherwise static_engine has no price on a side that static_touch quotes (seen at 2/3 and 97/98).
Also: to_quote_book returns Decimal cents; decide() takes an int, so require integral touch cents and refuse `subcent_touch` (counted).

N7. Seal testability and trust.
Case 26 needs a tmp git repo with GIT_COMMITTER_DATE set, because attest uses the COMMITTER date
(seal_provenance.py:84-90). Say so in case 26.
Disclose that the committer date is self-asserted. As the anti-backdating anchor, push the seal commit to
private/trunk the same day and record its sha plus the remote ref in the memo. attest reads path
history, not a moving ref, but a worktree without the seal commit returns not_tracked, which exits 3.
Scored runs therefore run from the main master.

N8. Vocabulary.
The spec and the labels are clean: a grep for the four gate words over S551_spec.md returned 0 (list in g334_seal.BANNED_WORDS).
The archive keys `yes_price_dollars` / `no_price_dollars` would trip the gate if written in the new modules,
so all price access goes through from_s341_trade / capture_book_adapter and never names those keys.

N9. Holm 8 is correct: the baseline against itself is null by construction. The bootstrap minimum
p = 1/5001 is below the smallest Holm threshold 0.05/8, so this is coherent. Under the v1 cut below, the family is 4.

## Minimal v1 scope (so the first build lands under 300 LOC per file)

- Arms: static_touch (baseline), cancel_on_book_move, cancel_on_state_receipt.
  - DEFER static_engine: it is a pricing policy, not a cancel policy, and belongs with S554/S555.
  - DEFER `both`: a v2 prereg is needed if it is added.
  - The Holm family becomes 2 x 2 = 4.
- Scenarios: keep BOTH. displayed_depletion costs one list argument, and opus B5 requires it. Expect it to be
  near through-only (25k-74k contracts displayed ahead).
- DEFER the sensitivity reruns. Keep the params plumbing so v2 needs no code change.
- Keep: prereg + seal + exploratory mode, cumulative pooling (B1), the ledger, and the receipt.
- Cases: drop 22 and 24 (engine/union). Case 23 still asserts the shared set across 3 arms. n = 29.
- Module split: exec_cancel_policy (decide, about 90 LOC); exec_policy_replay (merge, grid, phase 1/2, about 250);
  exec_policy_prereg (build/verify/seal/eligibility, about 150); exec_policy_stats (paired bootstrap, Holm, verdict,
  about 120); exec_policy_report (marks, fees, pooling, receipt, CLI, about 280). Pre-authorise the fifth module now,
  per the landing lesson that fix agents otherwise delete assertions to fit.
