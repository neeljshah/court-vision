# AUTOMATED PAPER DESK -- target architecture and build rows S691-S710 (2026-09-30)

PAPER ONLY. This desk never places, routes or simulates a venue order for real, and it has no
live promotion stage by design: the last stage of every ladder below is PAPER. Calibration and
execution-quality language only (Brier, log loss, markout in cents per contract, fill share,
coverage share, latency percentiles). Vocabulary rule: the claims rule under docs/operations/cloud/rules/
and VERIFIER_CONTRACT.md Q6 (docs/evidence/tracking/VERIFIER_CONTRACT.md:39).

Sources. Memos H (automated architectures), I (execution and paper fills), J (safety and unattended
ops), K (strategy pipeline and promotion) are local-only files under
`docs/research/industry_2026-09-30/`; they are cited by section and never copied. The earlier
slate `docs/evidence/harness/QUANT_GRADE_BUILD_SLATE_2026-09-30.md` (rows S660-S689, section 2)
and register rows S519, S551, S555, S557, S659, S666-S671, S676, S690 in
`docs/evidence/HARNESS_GAPS_2026-09-03.md` are referenced, never duplicated. Nothing here was
re-measured; every number names its source.

Owner directive 09-30: the best way to build automated systems of this kind; run paper trading at
the highest level automatically while making edits; usable in a quant shop.

---

## 1. Target architecture

```
 RECORDER BOX (Windows)                                         OUTSIDE THE PROCESS
 +-------------------------------------------------------+      supervisor (capture_supervisor +
 | VENUE ADAPTERS                                         |        S500 tick; S704 hang detect)
 |  books socket: snapshot + seq deltas, gap -> resnap,  |      adopt step (S659 a; S708 probe
 |  heartbeat, resume (S694 lib on S442/S660/S661)       |        + revert)
 |  state2 poll | tape | timer                          |      evidence push (S657 -> S690
 +---------------------------+---------------------------+        allowlist incl. heartbeat)
                             | one ordered event queue      off-box dead-man: trunk heartbeat
                             v  (integer us, receipt order)   checked by a cloud routine that
 +-------------------------------------------------------+    opens an issue (S676 AD-1);
 | SINGLE-THREADED CORE (S691)                           |    external ping (S697)
 |  journal-before-act: intent -> order state machine    |    clock guard (S664 journal ->
 |  blotter: orders, positions per family (S699)         |      S695 refuse)
 |  STRATEGIES emit INTENTS ONLY (quote_engine,          |
 |    exec_cancel_policy, live_shadow_quoter decide)     |
 |        |                                              |
 |        v                                              |
 |  RISK GATE (S702): ordered validators                 |
 |    S666 net delta -> S667 limits -> S668 breakers     |
 |    -> S695 clock / S694 book gap; state ACTIVE /      |
 |    REDUCING / HALTED; reason-coded denials; cancels   |
 |    always pass; logged re-arm                         |
 |        |                                              |
 |        v                                              |
 |  PAPER EXECUTION MODEL (S693 on S671 rules): amend    |
 |    priority, self-trade prevention, post-only reject, |
 |    expiration_time, venue delay, dead-man cancel,     |
 |    partial fills, queue that shrinks on cancels ahead,|
 |    feed latency + order latency from one declared     |
 |    latency object                                     |
 |        |                                              |
 |        v                                              |
 |  RECEIPTS: paper_account log, risk receipt (S669),    |
 |    stage state (S698, S670), monitors (S701)          |
 +-------------------------------------------------------+
 SAME CORE, THREE CONTEXTS: replay (archived tape, S692) | shadow (live feed, decisions
 logged, S710) | paper (live feed, simulated fills, S710). Restart = journal replay +
 reconciliation (S696).
```

1. Venue adapters turn socket snapshot and delta messages into book events; a sequence gap
   invalidates the book until a resnapshot, and a silent socket raises a named event (memo H
   section 5 item 2; memo I section 1.8; the S442 capture already tracks seq gaps,
   scripts/platformkit/ingame/kalshi_ws_capture.py:31-64, :94-95).
2. Every input (book, state, trade print, timer, control file) enters ONE queue ordered by capture
   receipt in integer microseconds, the clock contract S551 already uses
   (scripts/platformkit/execution/exec_policy_replay.py:3-12).
3. The core is single-threaded and deterministic; it reads no wall clock, only timer events (memo
   H section 1.2, nautilus kernel; memo H section 1.1, flumine handler queue).
4. Every intent and order transition is journaled before it acts, so a restart replays the
   journal to the same blotter (memo H section 5 item 3; memo I section 4).
5. Strategies return intents only; the existing pure decision modules are the strategies
   (quote_engine.py:1-15 stateless, no I/O; exec_cancel_policy decide; live_shadow_quoter.py:1).
6. The risk gate runs validators in a fixed order and puts the desk in ACTIVE, REDUCING or HALTED
   with a reason code per denial; cancels are never blocked (memo H section 5 item 4; memo J
   section 1, flumine force-through and nautilus states).
7. S666-S668 are the validators; S669 records which one bound; S670 reads the receipts.
8. The paper execution model honours the venue's order semantics (memo I sections 1.2-1.7) and
   takes feed latency and order latency from one declared object used identically in every
   context (memo I section 3 item 4).
9. The latency object is loaded from measured distributions (S550 source-to-receipt lag p50
   21.2 s, p90 33.3 s, per memo I section 5; S663 ledger once landed), never a buried constant.
10. Receipts are the only output; the paper account log is the ledger of record
    (paper_account.py:1-27, canonical replay of the receipt set, restart-safe).
11. Replay, shadow and paper differ only in the event source and the execution sink (memo H
    section 2.2 and section 3, nautilus row).
12. Outside the process: the supervisor restarts crashed children (crash-only, memo H section
    1.2), the adopt step pulls trunk in a window (RECORDER_LAPTOP_RUNBOOK.md section 8 B), the
    evidence push commits every tick output (S690), and a dead-man lives off the box (memo J
    section 4 item 1).
13. Halts need a logged re-arm; there is no automatic resume from HALTED (memo J section 2).
14. Promotion moves a strategy between REPLAY, SHADOW and PAPER only, and between INSUFFICIENT
    and TRUSTED as a measurement state (memo K section 0 scope rule).
15. Nothing in the core imports a live client; the executor's live path stays double-gated and
    refused (memo H section 2, paper_maker bullet; paper_maker.py:1-5).

### 1a. CURRENT vs TARGET, by component

| component | current (proof) | target | row |
|---|---|---|---|
| book source | REST polling, cadence about 5.2 s, every served game fails BOOK_CADENCE on 09-29 (slate section 1 item 2); socket capture prepare-only with seq gap rows (kalshi_ws_capture.py:31-64) | seq-checked socket adapter feeding the core, gap = book invalid | S694 (lib), S660/S661 (socket), S710 (wiring) |
| event ordering | two separate paths: nightly two-phase replay (exec_policy_replay.py:1-12) and the shadow loop (live_shadow_quoter.py:1) | one ordered queue, one core, three contexts | S691, S692, S710 |
| order state | lifecycle state machine with idempotency keys (executor/lifecycle.py:1-3), no journal; paper_account "No runtime caller wires this in yet" (paper_account.py:27) | journal-before-act, blotter, restart = journal replay | S691, S696, S699 |
| risk | per-game and one global cap (slate S667 gap cell); circuit_breaker is a rolling-CLV volume breaker (circuit_breaker.py:1-3), not a halt | ordered validator chain, three states, reason codes | S666-S670 + S702 |
| fill model | risk-averse queue, unknown queue 1,000,000 contracts (tape_fill_sim.py:14); latency 0 s in fill_realism (fill_realism.py:268), 6 s in S551 (exec_cancel_policy.py:22); no self-trade, post-only, expiry-amend handling (memo I section 5 table) | venue semantics + measured feed and order latency + optional queue shrink | S671 (rules) + S693 |
| dead-man in the book | suspended or terminal ticks cancel (paper_maker.py:20-23); mock exchange cancel race only (executor/mock_exchange.py:70, :179); no heartbeat or cancel-all (memo I section 5) | silent book or stalled core -> HALTED + cancel-all receipts; expiration_time on every paper quote | S694 + S702 + S693 |
| restart | tick reconciles process launches (memo J section 3b item 10); nothing reconciles paper orders | journal + receipt log + exchange state diffed at start | S696 |
| supervision | backoff restart, heartbeat files, 30-minute tick (DESK_STATE.md:27-28; memo J section 3c items 13-15) | hang detection, 5-minute liveness, resume self-check, disk guard, step breaker | S704, S705, S706, S707 |
| alerting | issue file on the same machine; the 09-30 sleep outage 05:20Z-13:46Z was found by a person (DESK_STATE.md:38-39) | trunk heartbeat + cloud issue; external ping | S676 AD-1, S690 AD-1, S697 |
| clock | offset journal proposed (S664); only a one-time manual resync (memo J section 3c item 19) | offset journal read each tick; night refused past a declared bound | S664 + S695 |
| deploy | adopt step contract, UNVERIFIED (RECORDER_LAPTOP_RUNBOOK.md section 8 B) | post-restart probe and automatic revert | S659 (a) + S708 |
| promotion | only the 30-paired-game floor inside S551 stats (memo K section 2 stage 7) | tracked stage policy with tests, per-family accounts, challenger slots | S670 + S698, S699, S700 |
| monitoring | census, audits, issue files; no calibration-decay or feature-health monitor (memo K section 2 stage 13) | fail-closed decay and drift monitor in the daily report | S701 |
| config | absolute user-profile paths in paper_desk_config.json (memo J section 3e item 27) | DESK_ROOT resolution | S709 |

---

## 2. Row table (S691-S710)

Platform: PORTABLE = code and construct tests run on Ubuntu (cloud); WINDOWS = needs the recorder
box; OWNER = an owner-only step gates it. Cost S under a day, M several days, L a week or more.
Rank 1 = build first. Every row keeps the sealed S551 v1 files (exec_policy_replay.py,
exec_cancel_policy.py, tape_fill_sim.py, the S551 PREREG) and every seal-pinned file in
DESK_STATE section 2 byte-unchanged; new code lives in new files.

| id | area | gap (cited) | what a lane builds (smallest version) | acceptance test | depends on / owner step | platform | cost | rank | sequencing note |
|---|---|---|---|---|---|---|---|---|---|
| S691 | core (event core + journaled order state machine + blotter) | Replay and shadow are separate code paths and paper_account has no runtime caller (memo H section 5 item 1; paper_account.py:27); no durable intent journal, a crash loses intent (memo H section 1.4, section 5 item 3) | `execution/desk_core.py`, `desk_events.py`, `order_journal.py` (each <= 300 LOC): typed events (book, state, print, timer, control) in one receipt-ordered queue, integer microseconds; order states NEW, PENDING_SUBMIT, RESTING, PARTIAL, FILLED, CANCEL_PENDING, CANCELLED, EXPIRED, REJECTED, DENIED with a transition table; journal-before-act ASCII JSONL; blotter of orders and positions per family; strategies plugged as pure callables returning intents | Same event stream twice gives byte-identical journals; every illegal transition refused with a reason; kill at 20 random points of a fixture night and restart from the journal: final blotter and journal equal the uninterrupted run, zero double fills, zero orphan resting orders (counts printed) | none | PORTABLE | L | 1 | new files only; imports quote_engine, exec_cancel_policy, lifecycle read-only |
| S692 | core (replay client + S551 parity) | The desk cannot show that its paper path and its replay path agree (memo H section 5 item 1 acceptance); S551 is two-phase with no tape in phase 1 (exec_policy_replay.py:1-12) | `execution/desk_replay_client.py`: reads archived shards (or fixture shards) into the S691 queue; an `s551_compat` execution sink that defers fills to one simulate_fills call per (arm, scenario, game) exactly as S551 does | On the tracked S551 fixtures the core in s551_compat mode reproduces the S551 replay's fills, cancels and receipt bytes; on one recorded night (laptop run) the same, or every differing fill is listed with its cause; parity runs as a per-file test | S691 | PORTABLE (fixtures) / WINDOWS (recorded night) | M | 2 | S551 v1 files and PREREG read-only; parity is a comparison, never a re-seal |
| S693 | execution (venue-semantics paper fill model in the core) | Latency mis-stated: 0 s in fill_realism (fill_realism.py:268), 6 s in S551 (exec_cancel_policy.py:22), measured lag p50 21.2 s / p90 33.3 s (memo I sections 5 and 6 items 1-2); queue ahead never shrinks from cancels (memo I section 6 item 1); no expiry, self-trade, post-only or venue-delay handling (memo I section 5 table) | `execution/paper_exec_model.py`: consumes S671's rule library for post-only reject-on-cross, self-trade prevention (declared mode taker_at_cross or maker), amend priority (price or size-up to the back, size-down or expiry-only keep place, memo I section 1.5), expiration_time, venue_delay_s as a declared parameter, partial fills; ONE latency object (feed_latency, order_latency) drawn from a declared distribution file seeded from S550 and later S663; queue model selectable: risk-averse (today) or probabilistic shrink on displayed-size drops (memo I section 3 item 1) | Fixtures: size-down amend keeps queue_ahead, price amend resets it; a crossing post-only is rejected and counted, never filled; zero fills against own resting quotes with a counted self-cross diagnostic; an expired quote never fills after expiration_time; fills are monotone non-increasing in order latency on a fixed tape; each latency and queue parameter appears in the receipt header; results reported at venue delay 0, 3 and 6 s | S691, S671 (rule library) | PORTABLE | M | 3 | never a sealed arm; any use in a scored series goes through a PROPOSED prereg sealed alone |
| S694 | capture (seq-checked socket book adapter for the core) | Book source is polling (slate section 1 item 2); the S442 capture writes gap rows but nothing turns a gap or a silent socket into a desk state (kalshi_ws_capture.py:31-64; memo H section 5 item 2; memo I section 4) | `execution/book_stream.py` (pure): applies snapshot + delta rows in the S442 archive shape to a per-ticker book; a seq gap marks the book INVALID and emits BOOK_GAP until a snapshot arrives; no message for a declared N s on a live ticker emits BOOK_SILENT; a resume after reconnect requires a fresh snapshot | Synthetic streams: an injected dropped seq yields BOOK_GAP within one message and a named gap row; no quote intent passes the S702 gate while INVALID; 5 synthetic shards with zero gaps rebuild top of book equal to the embedded snapshots; BOOK_SILENT fires at N s exactly on an injected clock | S691; real-socket half is S661 | PORTABLE | M | 5 | kalshi_ws_capture.py unchanged; live wiring waits for S660/S661 and S710 |
| S695 | ops (clock-drift watch with night refusal) | No offset check in code, only a one-time manual resync; the desk keys on UTC dates (memo J section 3c item 19, section 5 item 4); S664 journals the offset but nothing acts on it | `ops/clock_guard.py` (pure over the S664 journal): per tick state ok / warn / refuse with DECLARED bounds written in the spec before any real journal is read (proposed: warn above 250 ms, the S663 exclusion bound; refuse above 2,000 ms); refuse = the night for any day whose journal crossed the bound is written as CLOCK_REFUSED with the offset series, captures keep recording; PROPOSED tick hook diff | Fake journal fixtures: +45 s skew gives clock_skew_refuse and no night within one tick; removing the skew clears it next tick; a missing journal prints OFFSET_UNMEASURED, never ok; the receipt carries the bound and the max offset | S664 | PORTABLE (code) / WINDOWS (hook) | S | 4 | tick file edited only by the tick owner through the PROPOSED diff |
| S696 | core (startup reconciliation of paper state) | Nothing reconciles paper orders after a restart; executor/reconcile.py is an offline slippage check (executor/reconcile.py:1-3; memo I section 5 table row "Reconcile"); memo J section 3b item 9 | `execution/desk_reconcile.py`: on start, diff the S691 journal, the paper_account receipt log and the mock exchange order set; resting orders whose book was not observed across the restart gap are cancelled as of the restart instant with a receipt (never filled retroactively over the gap); duplicate fills refused by trade id | Fault injection: stop the core for N s mid-night; after restart zero resting orders survive the gap unobserved, a replayed duplicate fill stream leaves positions unchanged, and the three sources agree (diff count 0 printed) | S691 | PORTABLE | M | 8 | paper_account.py imported read-only |
| S697 | ops (external dead-man ping) | Detection is a file on the same machine; nothing alerts when the box itself dies (memo J section 3d item 23, section 5 item 1) | `ops/deadman_ping.py` (stdlib urllib): start, success and fail pings to a URL read from an environment variable; unset variable journals deadman_unconfigured and never fails the tick; PROPOSED tick hook | Unit: a raised network error inside the ping leaves the tick exit code unchanged within 1 s; recorder: stopping the task produces an alert within period + grace (declared, e.g. 30 + 20 min) | OWNER creates the check and sets the variable; complements S676 AD-1 | PORTABLE (code) / OWNER | S | 9 | no secret in any file; the URL lives only in the environment |
| S698 | promotion (stage policy file + gate) | No stated per-stage exit or kill criteria; "trusted" is whatever a reader decides (memo K sections 2 stage 7 and 5 (a), section 4 items 1 and 6) | `docs/operations/STRATEGY_STAGES.json` (tracked, hashed): stages RESEARCH, REPLAY, SHADOW, PAPER (terminal; no later stage exists); per family the minimum games, horizons, bar, interval method and kill criteria (inventory breach, repeated data fault, markout interval wholly below the floor after the minimum n); `eval_gate/stage_gate.py` recomputes each family's stage and trust state from receipts and S670 | A verifier recomputes every family's state from receipts alone; a moved bar without a new hash fails (B10 style); a file naming any stage after PAPER fails; a kill criterion met demotes to REPLAY with a reason | S670 | PORTABLE | S | 11 | values are DECLARED before accrual; changes only by amendment |
| S699 | core (parallel paper accounts per family + attribution) | One unified per-family ledger exists but is not wired (memo K section 4 item 8; paper_account.py:27); no attribution roll-up (memo K section 4 item 10) | In the S691 blotter: one PaperAccount per (family, version) fed from the same event stream; per-family limits read from the S667 table (new family scope); `execution/desk_attribution.py` sums per-family markout, fill share and refusals to a desk row without pooling sports (families_maker_forward.json independence rule) | Family rows sum to the desk row; a night with two tickers on one game respects caps across them; restart state equals canonical replay of each family's log; no cross-sport pooled interval is ever printed | S691, S667 | PORTABLE | M | 12 | paper_account.py unchanged |
| S700 | promotion (version registry + challenger slots) | No registry of strategy versions or a formal challenger slot (memo K section 2 stage 12, section 4 item 9) | `docs/operations/strategy_versions.json` + `eval_gate/version_registry.py`: seal id, code hash, parameter hash, role champion / challenger / retired; challengers run in their own S699 account on the same events with paired per-game differences archived (Q9) | Every receipt resolves to exactly one version; a parameter edit without a new seal id fails; challenger and champion share the same decision instants (count equality printed) | S699 | PORTABLE | S | 18 | no sealed parameter is edited; a challenger is a new version row |
| S701 | monitoring (calibration decay + feature health, fail closed) | No feature-drift or calibration-decay monitor (memo K section 1.4, section 2 stage 13, section 4 item 7) | `eval_gate/decay_monitor.py` (report-only): rolling reliability slope and ECE per family against its sealed reference window, PSI per model input, arm A book-age drift; a missing input prints UNKNOWN and the report fails closed; a block in the daily report | Injected-shift fixture flags within a stated number of games; stationary fixture false-flag share <= 5 pct over 200 seeds; missing input fails the report | none | PORTABLE (code) / WINDOWS (real run) | M | 13 | never changes a model or a seal |
| S702 | risk (ordered risk gate, three states) | S666-S668 specify the parts; nothing composes them before a submit, and cancels need force-through (memo H section 5 item 4; memo J section 2) | `execution/risk_gate.py`: calls in order S666 net delta, S667 limits, S668 breakers, S695 clock state, S694 book state; desk state ACTIVE / REDUCING / HALTED; each denial a reason-coded row; cancels always pass; HALTED triggers cancel-all with receipts; re-arm only by a logged control event; stub validators allowed until S666-S668 land | Frozen feed and delayed receipt fixtures: breach-to-halt <= one tick plus the declared cancel latency; zero new quotes after a halt until the logged re-arm; cancels pass while HALTED; false-halt share on clean fixture nights printed | S691; S666, S667, S668 (stubs until landed) | PORTABLE | M | 6 | S668's enum is shared, not redefined |
| S703 | execution (target-vs-live quote reconcile with churn tolerance) | Every refresh is cancel + new; no desired-set diff with a tolerance (memo H section 5 item 5) | A new v2 arm in a PROPOSED prereg: replace only when price or size moves past a declared tolerance | Held-out fixtures: cancels per fill and replaces per hour lower or equal vs the touch arm, fill count not lower by more than a declared tolerance, both with game-cluster intervals | S693 | PORTABLE | S | 19 | never an edit of sealed v1 arms |
| S704 | ops (hang detector + 5-minute liveness tick) | A supervisor alive with a stale heartbeat is reported, not restarted; detection lag up to 30 min (memo J section 3c item 14, section 5 items 5-6) | PROPOSED tick diff: capture_hung when heartbeat age > N x interval while the process lives; relaunch only through the owned launcher; a light 5-minute liveness task beside the 30-minute tick | Suspend a supervisor on the recorder: capture_hung journaled within 6 min, one relaunch after backoff; killing one supervisor gives a relaunch decision within 6 min | tick owner | WINDOWS | M | 15 | never kills an unidentified process (S500 amendment 1) |
| S705 | ops (continuous disk + log guard) | Free space checked at child start only; hidden-launch logs unbounded; about 1 GB/day growth (memo J section 3c items 17-18, section 5 item 7) | `ops/disk_guard.py` (pure with a disk_usage seam): disk_low warn and disk_refuse (declared GB bounds) deferring nights; size rotation of hidden-launch logs, never touching evidence | Seam returning 2.5 GB gives disk_refuse within one tick; a 60 MB log rotates to 5 files; evidence paths are never selected | none | PORTABLE (code) / WINDOWS (hook) | S | 7 | tick hook as a PROPOSED diff |
| S706 | ops (resume and reboot self-check) | The 09-30 sleep outage (DESK_STATE.md:38-39); reboot is an outage until auto-logon (memo J section 3c item 20, section 5 item 8) | A resume trigger plus a read-only boot self-check: boot_gap since the last heartbeat, AC standby setting, auto-logon present, captures checked | Sleep the recorder 20 min: within 5 min of resume a boot_gap row exists and missing settings are listed | S673 preflight shape | WINDOWS | S | 10 | read-only; never changes a system setting |
| S707 | ops (tick step error-rate breaker) | Nothing counts repeated failures of one tick step (memo J section 3a item 5, section 5 item 9) | `ops/step_breaker.py` (pure): sliding window per step, declared rate, step state shares S702's enum; alert once; re-arm file clears | Schedule step raising three ticks in a row: fourth tick skips with step_halted and one alert; the re-arm file clears it | S702 enum | PORTABLE | M | 16 | tick hook PROPOSED |
| S708 | ops (adopt post-restart probe + automatic revert) | The adopt step has no post-restart probe or revert (memo J section 3e items 28-29, section 5 item 12; RECORDER_LAPTOP_RUNBOOK.md section 8 B) | Extends the S659 (a) contract: heartbeat fresh within 120 s, child alive, NOT_IN_JOB; on failure revert to the prior sha and relaunch; receipt either way | Adopt a commit whose capture exits at once: within 180 s the receipt shows probe_failed, the prior sha is back and the capture runs | S659 (a) landed | WINDOWS | M | 17 | built on S659's script after it lands |
| S709 | ops (DESK_ROOT config) | Absolute user-profile paths in paper_desk_config.json (memo J section 3e item 27, section 5 item 13) | Resolve a DESK_ROOT variable with the current path as default | Tick contract cases pass from a different root | none | PORTABLE | S | 20 | default keeps today's behaviour byte-identical |
| S710 | core (live-tail shadow and paper contexts on the recorder) | Paper is a nightly replay; decisions are not made on the live feed through the same code (memo H section 2.1 diagram, section 5 item 1 live half) | A recorder process tailing the live capture into the S691 core in shadow (decisions logged) and paper (simulated fills) contexts; exclusive lock, heartbeat, RAM guard | Live dry run prints decision-to-intent latency p50 / p90 / max; the next morning the S692 replay of the same tape reproduces its journal or lists each difference | S691, S692, S693, S694, S702; OWNER approves a long-running process | WINDOWS + OWNER | L | 14 | S519-pinned live-shadow files untouched; a new process, not an edit of live_shadow_cli |

### 2a. Memo proposals folded into existing rows (no new id)

- **S676 AMENDMENT AD-1** (status cell): the off-box dead-man is the recorder heartbeat
  `docs/evidence/forward/desk_health/heartbeat.json` written every tick and pushed with the
  evidence push; the staleness check runs in every desk-improve / desk-improve-b run (3 h cadence)
  with a declared bound, plus the 07:00Z morning check; the issue is opened with an owner-provided
  GitHub token in the cloud environment (memo J section 5 item 2; section 4 below).
- **S690 AMENDMENT AD-1**: the allowlist includes `desk_health/` (S676 heartbeat) and the S695
  clock-guard receipts (memo J section 5 item 3 is S690 itself).
- **S671 AMENDMENT AD-1**: the rule library also carries expiration_time, size-down and
  expiry-only amends that keep queue place, and venue_delay_s with uncancellable-during-delay
  (memo I section 7 items 2 and 5); S693 consumes it in the core.
- **S668 AMENDMENT AD-1**: BOOK_GAP / BOOK_SILENT (S694) and the S695 clock state are breaker
  inputs; the state enum is shared with S702 and S707.
- **S669 AMENDMENT AD-1**: markout also split by fill cause (through print, touch queue, within X
  s after a captured state change) with the queue-model variant as a column (memo I section 7
  item 11).
- **S667 AMENDMENT AD-1**: the limit table gains a per-family scope read by S699.
- **S670 AMENDMENT AD-1**: its states feed S698's stage policy; kill criteria live in S698.
- Covered, not amended: memo K items 1-5 = S670, S675, S682, S684, S689; memo J items 10 and 11 =
  S680 and S677; memo J item 3 = S690; memo H item 6 = S671 + S693.

### 2b. Considered, not rowed

- Queue-position calibration against the venue label and own-order delta stripping (memo I
  section 7 items 1 and 7): the venue reports queue position only for the account's own resting
  orders, and this desk places none; out of scope while PAPER ONLY.
- Paper-to-shadow realism check (memo K section 4 item 11): needs observed fills; none exist.
- Polymarket fill lifecycle and rebate constant (memo I section 7 items 9 and 10): no Polymarket
  paper family yet; the constant never enters paper fees.
- Pluggable logging sinks and multiprocess replay (memo H section 5 items 7 and 9): the S691
  journal plus S690 cover the first; the second raises peak RAM on a box gated at about 3 GB free.
- Venue heartbeat feeder and order-group kill switch (memo J section 5 item 14): dormant, no live
  path exists or is planned.

---

## 3. Dispatch list

### 3a. PORTABLE rows: cloud one-off override paragraphs

Each paragraph is appended to `docs/operations/cloud/desk-improve.prompt.txt` for a one-off run
named `desk-row-<ROW>`. Replace `<date>` with the run's UTC date. Row text = this file, section 2.

- **S691.** ONE-OFF OVERRIDE of WHAT TO DO step 1: your row is PINNED to S691 (event core + journaled order state machine + blotter); the row text is S691 in docs/evidence/harness/AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md (the register line is a pointer). Branch cloud/S691-<date>. Do NOT edit docs/evidence/HARNESS_GAPS_2026-09-03.md or docs/operations/DESK_STATE.md on the branch. Never contact a venue or sports host; fixture shards are built in the test. New files only under scripts/platformkit/execution/; quote_engine.py, exec_cancel_policy.py, exec_policy_replay.py, tape_fill_sim.py, executor/lifecycle.py, paper_maker.py and paper_account.py unchanged. Steps 2-7 as written: spec, one Opus pre-build critic sub-agent, build, CONTRACT and ADVERSARIAL Opus tiers (adversarial tier kills the core at random journal offsets), result memo, push the branch only. NOT VERIFIED must list: a recorded night, Windows re-test, live tail (S710).
- **S692.** ONE-OFF OVERRIDE of step 1: row PINNED to S692 (replay client + S551 parity); build on S691's branch if not landed and say so. Branch cloud/S692-<date>; no register or DESK_STATE edits; no venue or sports hosts. The sealed S551 v1 files and PREREG are read-only; parity is a comparison, never a re-seal. Steps 2-7 with both Opus tiers (adversarial tier perturbs event order at equal receipts). NOT VERIFIED: parity on a recorded night (archive on the laptop).
- **S693.** ONE-OFF OVERRIDE of step 1: row PINNED to S693 (venue-semantics paper fill model); consume S671's library if landed, else build the minimal rule functions inside the new module and say so. Branch cloud/S693-<date>; no register or DESK_STATE edits; no venue or sports hosts; tape_fill_sim.py and fill_realism.py unchanged; the latency distribution file is DECLARED from the cited S550 percentiles, never fitted to an outcome. Steps 2-7 with both Opus tiers (adversarial tier mutates amend-priority and post-only rules). NOT VERIFIED: measured latency from S663, held-out nights.
- **S694.** ONE-OFF OVERRIDE of step 1: row PINNED to S694 (seq-checked book adapter); synthetic streams in the S442 archive shape only. Branch cloud/S694-<date>; no register or DESK_STATE edits; no venue or sports hosts; kalshi_ws_capture.py unchanged. Steps 2-7 with both Opus tiers (adversarial tier drops, duplicates and reorders seq). NOT VERIFIED: any live socket message (S661).
- **S695.** ONE-OFF OVERRIDE of step 1: row PINNED to S695 (clock guard); bounds written in the spec before any fixture result. Branch cloud/S695-<date>; no register or DESK_STATE edits; no venue or sports hosts; the tick hook is a PROPOSED diff under docs/evidence/harness/, never a tick edit. Steps 2-7 with both Opus tiers. NOT VERIFIED: real S664 journal, the hook.
- **S696.** ONE-OFF OVERRIDE of step 1: row PINNED to S696 (startup reconciliation); build on S691. Branch cloud/S696-<date>; no register or DESK_STATE edits; no venue or sports hosts; paper_account.py and executor/*.py unchanged. Steps 2-7 with both Opus tiers (adversarial tier replays duplicate fills and gaps). NOT VERIFIED: a real restart on the recorder.
- **S697.** ONE-OFF OVERRIDE of step 1: row PINNED to S697 (external dead-man ping); tests use a loopback HTTP server only. Branch cloud/S697-<date>; no register or DESK_STATE edits; no external host contacted; no URL or token in any file. Steps 2-7 with both Opus tiers. NOT VERIFIED: the owner's check, the tick hook, a real alert.
- **S698.** ONE-OFF OVERRIDE of step 1: row PINNED to S698 (stage policy + gate); values marked OWNER_TBD where the owner declares them. Branch cloud/S698-<date>; no register or DESK_STATE edits; no venue or sports hosts; no stage after PAPER may appear. Steps 2-7 with both Opus tiers. NOT VERIFIED: real family receipts.
- **S699.** ONE-OFF OVERRIDE of step 1: row PINNED to S699 (per-family accounts + attribution); build on S691 and S667 (stub the family scope if S667 is not landed and say so). Branch cloud/S699-<date>; no register or DESK_STATE edits; no venue or sports hosts; paper_account.py unchanged. Steps 2-7 with both Opus tiers. NOT VERIFIED: real nights.
- **S700.** ONE-OFF OVERRIDE of step 1: row PINNED to S700 (version registry + challenger slots). Branch cloud/S700-<date>; no register or DESK_STATE edits; no venue or sports hosts; no sealed parameter edited. Steps 2-7 with both Opus tiers. NOT VERIFIED: hashes of local-only artifacts (PENDING_LAPTOP).
- **S701.** ONE-OFF OVERRIDE of step 1: row PINNED to S701 (decay + feature-health monitor); report-only. Branch cloud/S701-<date>; no register or DESK_STATE edits; no venue or sports hosts; no model or seal touched. Steps 2-7 with both Opus tiers (adversarial tier runs the 200-seed stationary null). NOT VERIFIED: the real daily run.
- **S702.** ONE-OFF OVERRIDE of step 1: row PINNED to S702 (ordered risk gate); stub S666-S668 behind their slate interfaces if not landed and say so. Branch cloud/S702-<date>; no register or DESK_STATE edits; no venue or sports hosts; position_caps.py, circuit_breaker.py, quote_reservation.py unchanged. Steps 2-7 with both Opus tiers (adversarial tier injects frozen feed and delayed receipts). NOT VERIFIED: false-halt share on real nights.
- **S703.** ONE-OFF OVERRIDE of step 1: row PINNED to S703 (churn-tolerant reconcile arm); a PROPOSED prereg text only. Branch cloud/S703-<date>; no register or DESK_STATE edits; no venue or sports hosts; sealed v1 arms untouched. Steps 2-7 with both Opus tiers. NOT VERIFIED: held-out real nights.
- **S705.** ONE-OFF OVERRIDE of step 1: row PINNED to S705 (disk + log guard). Branch cloud/S705-<date>; no register or DESK_STATE edits; no venue or sports hosts; the rotator never selects a path under docs/evidence/ or data/; tick hook PROPOSED. Steps 2-7 with both Opus tiers. NOT VERIFIED: the recorder disk, the hook.
- **S707.** ONE-OFF OVERRIDE of step 1: row PINNED to S707 (step error-rate breaker). Branch cloud/S707-<date>; no register or DESK_STATE edits; no venue or sports hosts; tick hook PROPOSED. Steps 2-7 with both Opus tiers. NOT VERIFIED: the hook on the recorder.
- **S709.** ONE-OFF OVERRIDE of step 1: row PINNED to S709 (DESK_ROOT). Branch cloud/S709-<date>; no register or DESK_STATE edits; no venue or sports hosts; with the variable unset every tick contract case is byte-identical. Steps 2-7 with both Opus tiers. NOT VERIFIED: the Windows tick contract run.

### 3b. WINDOWS rows and halves: laptop lane briefs

- **S704**: write the PROPOSED tick diff and the second task; test by suspending one supervisor
  outside a live game; never kill an unidentified process.
- **S706**: add the resume trigger and the read-only self-check; one 20-minute sleep test in the
  06:00Z-16:00Z window with no live game.
- **S708**: after S659 (a) lands, add the probe and revert; test with a deliberately failing
  capture commit on a scratch branch.
- **S710**: after S691-S694 and S702 land and the owner approves the process: one live dry run,
  then shadow nights, then paper; RAM guard on; the REST capture stays the record.
- Real-run halves: S692 recorded-night parity, S701 daily run; hooks for S695, S697, S705, S707
  applied by the tick owner.

### 3c. OWNER steps by row (one line each)

- S676 AD-1: GitHub token for issue creation in the cloud environment (section 4 item 1).
- S697: create an external dead-man check and set its URL variable on the recorder.
- S698: declare the per-family minimums in STRATEGY_STAGES.json (or accept the drafted ones).
- S710: approve one more long-running process on the recorder.

---

## 4. Owner steps (never put a secret value in any file or chat)

1. GitHub token for issue creation: create a fine-grained token limited to court-vision-private
   with issues read and write only, and add it as an environment variable in the Claude cloud
   environment's settings (never a file). Why: the S676 dead-man check must open an issue that
   e-mails you.
2. Kalshi read-only API key: unchanged from DESK_STATE section 6 item 6 (S660, S661; S694's live
   half and S710 depend on it).
3. External dead-man (S697, optional): create one heartbeat check with a period and grace you
   choose, and set its ping URL as a user-level environment variable on the recorder.
4. Approve the S710 live-tail process under the RAM guard when S691-S694 and S702 have landed.
5. Declare or accept the stage minimums in S698's policy file before any family accrues under it.
